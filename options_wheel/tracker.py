"""
Phase 7 — Position tracking and monthly reporting.

Functions
---------
save_portfolio       — write portfolio DataFrame to CSV
load_portfolio       — read portfolio DataFrame from CSV
log_trade            — append one trade record to the trade log CSV
monthly_summary      — aggregate premium collected vs. monthly targets
print_portfolio_report — pretty-print the current portfolio table
print_monthly_report   — pretty-print the monthly P&L summary
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from .config import (
    MONTHLY_TARGET_HIGH,
    MONTHLY_TARGET_LOW,
    WEEKLY_TARGET_HIGH,
    WEEKLY_TARGET_LOW,
)

logger = logging.getLogger(__name__)

PORTFOLIO_FILE = "portfolio.csv"
TRADE_LOG_FILE = "trade_log.csv"


# ──────────────────────────────────────────────────────────────────────────────
# Persistence helpers
# ──────────────────────────────────────────────────────────────────────────────

def save_portfolio(
    portfolio: pd.DataFrame,
    filepath: str = PORTFOLIO_FILE,
) -> None:
    """Write the portfolio DataFrame to *filepath* (CSV)."""
    portfolio.to_csv(filepath, index=False)
    logger.info("Portfolio saved to %s", filepath)


def load_portfolio(filepath: str = PORTFOLIO_FILE) -> pd.DataFrame:
    """Read the portfolio CSV.  Returns an empty DataFrame when not found."""
    try:
        return pd.read_csv(filepath)
    except FileNotFoundError:
        logger.info("No portfolio file found at %s", filepath)
        return pd.DataFrame()


def log_trade(trade: dict, filepath: str = TRADE_LOG_FILE) -> None:
    """Append *trade* to the trade-log CSV, creating it if necessary."""
    trade = {**trade, "logged_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    new_row = pd.DataFrame([trade])

    try:
        existing = pd.read_csv(filepath)
        combined = pd.concat([existing, new_row], ignore_index=True)
    except FileNotFoundError:
        combined = new_row

    combined.to_csv(filepath, index=False)
    logger.info("Trade logged to %s", filepath)


# ──────────────────────────────────────────────────────────────────────────────
# Reporting
# ──────────────────────────────────────────────────────────────────────────────

def monthly_summary(trade_log: pd.DataFrame) -> dict:
    """
    Aggregate premium collected this calendar month vs. the monthly targets.

    Parameters
    ----------
    trade_log   DataFrame loaded from trade_log.csv.
                Must have a ``total_premium`` column.
                Optionally has an ``entry_date`` (YYYY-MM-DD) column for filtering.

    Returns
    -------
    dict with keys:
        month, total_premium, total_trades, target_low, target_high,
        pct_of_target_low, on_track
    """
    current_month = datetime.now().strftime("%Y-%m")

    if trade_log.empty:
        return {
            "month": current_month,
            "total_premium": 0.0,
            "total_trades": 0,
            "target_low": MONTHLY_TARGET_LOW,
            "target_high": MONTHLY_TARGET_HIGH,
            "pct_of_target_low": 0.0,
            "on_track": False,
        }

    # Filter to the current month when date info is available
    if "entry_date" in trade_log.columns:
        monthly = trade_log[
            trade_log["entry_date"].astype(str).str.startswith(current_month, na=False)
        ]
    else:
        monthly = trade_log

    total_premium = float(monthly.get("total_premium", pd.Series(dtype=float)).sum())
    total_trades = len(monthly)

    # Pro-rate the low target by fraction of month elapsed
    day_fraction = min(datetime.now().day / 30.0, 1.0)
    on_track = total_premium >= MONTHLY_TARGET_LOW * day_fraction

    return {
        "month": current_month,
        "total_premium": total_premium,
        "total_trades": total_trades,
        "target_low": MONTHLY_TARGET_LOW,
        "target_high": MONTHLY_TARGET_HIGH,
        "pct_of_target_low": total_premium / MONTHLY_TARGET_LOW * 100
        if MONTHLY_TARGET_LOW > 0
        else 0.0,
        "on_track": on_track,
    }


def print_portfolio_report(portfolio: pd.DataFrame) -> None:
    """Pretty-print the portfolio as a formatted table."""
    if portfolio.empty:
        print("No positions in portfolio.")
        return

    print("\n" + "=" * 80)
    print("PORTFOLIO POSITIONS")
    print("=" * 80)

    preferred_cols = [
        "ticker", "strategy", "strike", "expiration", "dte", "contracts",
        "mid_premium", "total_premium", "delta", "iv", "ivr",
        "capital_deployed", "annualized_return_pct", "status",
    ]
    display_cols = [c for c in preferred_cols if c in portfolio.columns]

    try:
        from tabulate import tabulate  # type: ignore[import]
        print(
            tabulate(
                portfolio[display_cols],
                headers="keys",
                tablefmt="grid",
                floatfmt=".2f",
                showindex=False,
            )
        )
    except ImportError:
        print(portfolio[display_cols].to_string(index=False))

    print(f"\nTotal Premium  : ${portfolio['total_premium'].sum():>10,.2f}")
    if "capital_deployed" in portfolio.columns:
        print(f"Total Deployed : ${portfolio['capital_deployed'].sum():>10,.2f}")
    print("=" * 80)


def print_monthly_report(summary: dict) -> None:
    """Print the Phase 7 monthly tracking report."""
    print("\n" + "=" * 80)
    print(f"MONTHLY TRACKING REPORT — {summary.get('month', 'Current Month')}")
    print("=" * 80)
    print(f"Premium collected : ${summary['total_premium']:>10,.2f}")
    print(f"Trades            : {summary['total_trades']:>10}")
    print(
        f"Monthly target    :  "
        f"${summary['target_low']:,.0f} – ${summary['target_high']:,.0f}"
    )
    print(f"Progress to low   : {summary['pct_of_target_low']:>9.1f}%")
    print(f"On track          : {'✓  YES' if summary['on_track'] else '✗  BEHIND'}")
    print("=" * 80)

    print("\nWEEKLY BREAKDOWN TARGETS:")
    for week in range(1, 5):
        print(
            f"  Week {week}: ${WEEKLY_TARGET_LOW:,.0f} – ${WEEKLY_TARGET_HIGH:,.0f}"
        )
    print(
        f"\n  Monthly total: ${MONTHLY_TARGET_LOW:,.0f} – ${MONTHLY_TARGET_HIGH:,.0f}"
    )
    print("=" * 80)
