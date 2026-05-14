#!/usr/bin/env python3
"""
Options Wheel Strategy Tool
===========================

A systematic implementation of the cash-secured put (CSP) wheel strategy
targeting $5 K–$10 K/month in options premium on a ~$50 K portfolio.

Commands
--------
  screen      Screen stocks for wheel-strategy candidates (Phase 1 + 2)
  portfolio   Build a CSP portfolio from screened candidates (Phase 3 + 4)
  assign      Find a covered call after a CSP assignment (Phase 5)
  review      Weekly risk review of open positions (Phase 6)
  track       Monthly premium tracking report (Phase 7)

Quick start
-----------
  # 1. Screen the S&P 500 (takes a few minutes due to API rate limits)
  python main.py screen

  # 2. Build the portfolio from the saved candidates
  python main.py portfolio --capital 50000

  # 3. Weekly review
  python main.py review

  # 4. If assigned on AAPL at $145 (strike) minus $1.20 (CSP premium):
  python main.py assign --ticker AAPL --shares 100 --cost-basis 143.80

  # 5. Monthly P&L
  python main.py track
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

from options_wheel.screener import run_screener
from options_wheel.portfolio import build_portfolio, find_covered_call
from options_wheel.risk_manager import run_weekly_review
from options_wheel.tracker import (
    load_portfolio,
    log_trade,
    monthly_summary,
    print_monthly_report,
    print_portfolio_report,
    save_portfolio,
)


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Command handlers
# ──────────────────────────────────────────────────────────────────────────────

def cmd_screen(args: argparse.Namespace) -> None:
    """Phase 1 + 2: screen stocks for the wheel strategy."""
    print(f"\n{'=' * 60}")
    print("OPTIONS WHEEL STRATEGY — STOCK SCREENER")
    print(f"{'=' * 60}")

    tickers = args.tickers or None
    universe_label = (
        f"Custom ({len(tickers)} tickers)" if tickers else "S&P 500"
    )
    print(f"Universe  : {universe_label}")
    print(f"Top N     : {args.top}")
    print(f"API delay : {args.delay}s between calls\n")

    candidates = run_screener(tickers=tickers, delay=args.delay)

    if candidates.empty:
        print("\nNo candidates found matching all criteria.")
        print("Tips:")
        print("  • Try a broader set of tickers with --tickers")
        print("  • Relax thresholds in options_wheel/config.py")
        sys.exit(1)

    top = candidates.head(args.top)

    print(f"\n{'=' * 60}")
    print(f"TOP {len(top)} CANDIDATES")
    print(f"{'=' * 60}")

    display_cols = [
        "ticker", "current_price", "52w_low", "pct_above_52w_low",
        "net_profit_margin", "debt_to_assets", "ivr", "atm_iv",
        "expiration", "dte",
    ]
    available = [c for c in display_cols if c in top.columns]

    try:
        from tabulate import tabulate  # type: ignore[import]
        print(tabulate(top[available], headers="keys", tablefmt="grid",
                       floatfmt=".3f", showindex=False))
    except ImportError:
        print(top[available].to_string(index=False))

    top.to_csv("candidates.csv", index=False)
    print("\n✓ Candidates saved to candidates.csv")
    print(f"\nNext: python main.py portfolio --capital {args.capital}")


def cmd_portfolio(args: argparse.Namespace) -> None:
    """Phase 3 + 4: build a CSP portfolio."""
    print(f"\n{'=' * 60}")
    print(f"BUILDING PORTFOLIO  (capital: ${args.capital:,.0f})")
    print(f"{'=' * 60}")

    candidates_file = "candidates.csv"
    if Path(candidates_file).exists():
        candidates = pd.read_csv(candidates_file)
        print(f"Loaded {len(candidates)} candidates from {candidates_file}")
    else:
        print("candidates.csv not found — running screener first …")
        tickers = args.tickers or None
        candidates = run_screener(tickers=tickers)
        if candidates.empty:
            print("No candidates found. Exiting.")
            sys.exit(1)

    portfolio = build_portfolio(candidates, capital=args.capital)

    if portfolio.empty:
        print("Could not build any positions. Check candidates and capital.")
        sys.exit(1)

    print_portfolio_report(portfolio)

    total_premium = portfolio["total_premium"].sum()
    monthly_estimate = total_premium * 4
    print(f"\nExpected weekly premium      : ${total_premium:,.2f}")
    print(f"Expected monthly (×4 weeks)  : ${monthly_estimate:,.2f}")
    print(f"Monthly target range         : $5,000 – $10,000")

    if monthly_estimate < 5_000:
        print("⚠  Below target — consider more positions or higher-IV stocks.")
    elif monthly_estimate > 10_000:
        print("⚠  Above target — review position sizing and risk.")
    else:
        print("✓  On track to meet monthly target.")

    save_portfolio(portfolio)
    print("\n✓ Portfolio saved to portfolio.csv")
    print("Next: python main.py review")


def cmd_assign(args: argparse.Namespace) -> None:
    """Phase 5: find the best covered call after assignment."""
    print(f"\n{'=' * 60}")
    print(f"ASSIGNMENT MANAGEMENT — {args.ticker}")
    print(f"{'=' * 60}")
    print(f"Shares     : {args.shares}")
    print(f"Cost basis : ${args.cost_basis:.2f}/share\n")

    cc = find_covered_call(
        ticker=args.ticker,
        cost_basis=args.cost_basis,
        shares=args.shares,
    )

    if cc is None:
        print(f"⚠  No suitable covered call found for {args.ticker}.")
        print("   Try adjusting CC_TARGET_DELTA_MIN/MAX in config or wait for IV to rise.")
        sys.exit(1)

    print(f"{'=' * 60}")
    print("RECOMMENDED COVERED CALL")
    print(f"{'=' * 60}")
    print(f"  Ticker           : {cc['ticker']}")
    print(f"  Expiration       : {cc['expiration']}  ({cc['dte']} DTE)")
    print(f"  Strike           : ${cc['strike']:.2f}  ({cc['pct_otm']:+.1f}% OTM)")
    print(f"  Current price    : ${cc['current_price']:.2f}")
    print(f"  Cost basis       : ${cc['cost_basis']:.2f}")
    print(f"  Premium (mid)    : ${cc['mid_premium']:.2f}/share")
    print(f"  Total premium    : ${cc['total_premium']:.2f}")
    print(f"  Delta            : {cc['delta']:.3f}")
    print(f"  IV               : {cc['iv']*100:.1f}%")
    print(f"  Profit if called : ${cc['profit_if_called']:.2f}")

    log_trade({**cc, "entry_date": pd.Timestamp.now().strftime("%Y-%m-%d")})
    print("\n✓ Trade logged to trade_log.csv")


def cmd_review(args: argparse.Namespace) -> None:
    """Phase 6: weekly risk review of open positions."""
    print(f"\n{'=' * 60}")
    print("WEEKLY RISK REVIEW")
    print(f"{'=' * 60}")

    portfolio = load_portfolio()
    if portfolio.empty:
        print("No portfolio found. Run 'python main.py portfolio' first.")
        sys.exit(1)

    print_portfolio_report(portfolio)

    reviews = run_weekly_review(portfolio)
    if reviews.empty:
        print("No open positions to review.")
        return

    print(f"\n{'=' * 60}")
    print("RISK REVIEW RESULTS")
    print(f"{'=' * 60}")

    try:
        from tabulate import tabulate  # type: ignore[import]
        print(tabulate(reviews, headers="keys", tablefmt="grid", showindex=False))
    except ImportError:
        print(reviews.to_string(index=False))

    urgent = reviews[reviews["action"].isin(["CLOSE", "CLOSE/ROLL"])]
    if not urgent.empty:
        print(f"\n⚠  URGENT ACTIONS — {len(urgent)} position(s):")
        for _, row in urgent.iterrows():
            print(f"   → {row['ticker']}: {row['action']}  —  {row['reason']}")
    else:
        print("\n✓  All positions on track. No urgent actions needed.")


def cmd_track(args: argparse.Namespace) -> None:
    """Phase 7: monthly premium tracking."""
    print(f"\n{'=' * 60}")
    print("MONTHLY TRACKING REPORT")
    print(f"{'=' * 60}")

    try:
        trade_log = pd.read_csv("trade_log.csv")
    except FileNotFoundError:
        trade_log = pd.DataFrame()

    summary = monthly_summary(trade_log)
    print_monthly_report(summary)

    portfolio = load_portfolio()
    if not portfolio.empty:
        status_col = "status" if "status" in portfolio.columns else None
        open_pos = (
            portfolio[portfolio[status_col] == "OPEN"] if status_col else portfolio
        )
        expected = float(open_pos.get("total_premium", pd.Series(dtype=float)).sum())
        print(f"\nOpen positions            : {len(open_pos)}")
        print(f"Expected (open positions) : ${expected:,.2f}")


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wheel",
        description=(
            "Options Wheel Strategy Tool\n"
            "Target: $5 K–$10 K/month premium on a ~$50 K portfolio."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # ── screen ──────────────────────────────────────────────────────────────
    p_screen = sub.add_parser("screen", help="Screen stocks (Phase 1 + 2)")
    p_screen.add_argument(
        "--tickers", nargs="+", metavar="TICKER",
        help="Custom ticker list (default: S&P 500)",
    )
    p_screen.add_argument(
        "--top", type=int, default=10, metavar="N",
        help="Show top N candidates (default: 10)",
    )
    p_screen.add_argument(
        "--capital", type=float, default=50_000,
        help="Reference capital for next step (default: 50000)",
    )
    p_screen.add_argument(
        "--delay", type=float, default=1.0,
        help="Seconds between API calls (default: 1.0)",
    )

    # ── portfolio ────────────────────────────────────────────────────────────
    p_port = sub.add_parser("portfolio", help="Build CSP portfolio (Phase 3 + 4)")
    p_port.add_argument(
        "--capital", type=float, default=50_000,
        help="Total capital to deploy (default: 50000)",
    )
    p_port.add_argument(
        "--tickers", nargs="+", metavar="TICKER",
        help="Run screener on these tickers if candidates.csv is missing",
    )

    # ── assign ───────────────────────────────────────────────────────────────
    p_assign = sub.add_parser(
        "assign", help="Find covered call after assignment (Phase 5)"
    )
    p_assign.add_argument("--ticker", required=True, help="Assigned stock ticker")
    p_assign.add_argument(
        "--shares", type=int, default=100, help="Shares assigned (default: 100)"
    )
    p_assign.add_argument(
        "--cost-basis", type=float, required=True,
        dest="cost_basis",
        help="Cost basis per share = strike − CSP premium received",
    )

    # ── review ───────────────────────────────────────────────────────────────
    sub.add_parser("review", help="Weekly risk review (Phase 6)")

    # ── track ────────────────────────────────────────────────────────────────
    sub.add_parser("track", help="Monthly tracking report (Phase 7)")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    setup_logging(args.verbose)

    dispatch = {
        "screen": cmd_screen,
        "portfolio": cmd_portfolio,
        "assign": cmd_assign,
        "review": cmd_review,
        "track": cmd_track,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
