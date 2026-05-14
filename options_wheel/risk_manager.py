"""
Phase 6 — Risk management rules.

check_earnings_risk   — flag positions where earnings fall within EARNINGS_BUFFER_DAYS
assess_position_risk  — decide HOLD / CLOSE / CLOSE-ROLL based on P&L
run_weekly_review     — batch review of the whole portfolio
"""

import logging
from datetime import datetime
from typing import Optional

import pandas as pd
import yfinance as yf

from .config import EARNINGS_BUFFER_DAYS, EARLY_CLOSE_PROFIT_PCT, MAX_LOSS_MULTIPLIER

logger = logging.getLogger(__name__)


def check_earnings_risk(ticker: str) -> dict:
    """
    Check whether earnings are approaching for *ticker*.

    Uses yfinance's ``calendar`` property.  If the data is unavailable the
    function returns safely with ``earnings_risk=False``.

    Returns
    -------
    dict with keys:
        ticker, earnings_date, days_to_earnings, earnings_risk, action
    """
    result: dict = {
        "ticker": ticker,
        "earnings_date": None,
        "days_to_earnings": None,
        "earnings_risk": False,
        "action": "HOLD",
    }

    try:
        t = yf.Ticker(ticker)
        calendar = t.calendar

        if calendar is None or (hasattr(calendar, "empty") and calendar.empty):
            return result

        # yfinance ≥ 0.2 returns a dict; older versions return a DataFrame
        if isinstance(calendar, dict):
            earnings_dates = calendar.get("Earnings Date", [])
        else:
            if "Earnings Date" not in calendar.index:
                return result
            raw = calendar.loc["Earnings Date"]
            earnings_dates = list(raw) if hasattr(raw, "__iter__") else [raw]

        now = datetime.now()
        future_dates = [
            pd.to_datetime(d) for d in earnings_dates if pd.to_datetime(d) >= now
        ]
        if not future_dates:
            return result

        next_earnings = min(future_dates)
        days_to_earnings = (next_earnings.date() - now.date()).days

        result.update(
            {
                "earnings_date": next_earnings.strftime("%Y-%m-%d"),
                "days_to_earnings": days_to_earnings,
                "earnings_risk": days_to_earnings <= EARNINGS_BUFFER_DAYS,
                "action": (
                    "CLOSE/ROLL"
                    if days_to_earnings <= EARNINGS_BUFFER_DAYS
                    else "HOLD"
                ),
            }
        )

    except Exception as exc:
        logger.debug("%s: could not check earnings: %s", ticker, exc)

    return result


def assess_position_risk(
    ticker: str,
    entry_premium: float,
    current_option_price: float,
    early_close_pct: float = EARLY_CLOSE_PROFIT_PCT,
) -> dict:
    """
    Decide whether to HOLD, CLOSE early (profit), or CLOSE/ROLL (loss).

    Rules
    -----
    • CLOSE   — option has decayed ≥ *early_close_pct* of the premium received
                 (e.g. 50 % decay → keep half, free up capital).
    • CLOSE/ROLL — current option price ≥ MAX_LOSS_MULTIPLIER × entry premium
                 (e.g. option is now 3× what you sold it for → cut losses).
    • HOLD    — neither condition triggered.

    Parameters
    ----------
    ticker               Stock symbol (informational only)
    entry_premium        Mid-price premium received at entry (per share)
    current_option_price Current mid-price of the same option (per share)
    early_close_pct      Profit % at which to close early (default 0.50)

    Returns
    -------
    dict with keys: ticker, entry_premium, current_option_price,
                    profit_taken, profit_pct, loss_multiplier, action, reason
    """
    profit_taken = entry_premium - current_option_price
    profit_pct = profit_taken / entry_premium if entry_premium > 0 else 0.0
    loss_multiplier = (
        current_option_price / entry_premium if entry_premium > 0 else 0.0
    )

    action = "HOLD"
    reason = ""

    if profit_pct >= early_close_pct:
        action = "CLOSE"
        reason = (
            f"Reached {profit_pct*100:.0f}% of max profit "
            f"(≥ {early_close_pct*100:.0f}% threshold)"
        )
    elif loss_multiplier >= MAX_LOSS_MULTIPLIER:
        action = "CLOSE/ROLL"
        reason = (
            f"Option at {loss_multiplier:.1f}× entry premium "
            f"(≥ {MAX_LOSS_MULTIPLIER}× threshold)"
        )

    return {
        "ticker": ticker,
        "entry_premium": entry_premium,
        "current_option_price": current_option_price,
        "profit_taken": profit_taken,
        "profit_pct": profit_pct * 100,
        "loss_multiplier": loss_multiplier,
        "action": action,
        "reason": reason,
    }


def run_weekly_review(portfolio: pd.DataFrame) -> pd.DataFrame:
    """
    Phase 6: Run weekly risk review for every open position.

    For each open position the function:
      1. Checks for upcoming earnings.
      2. Reports the recommended action.

    (Real-time P&L check via ``assess_position_risk`` requires the live
    option price — pass that in when you track positions manually.)

    Parameters
    ----------
    portfolio   DataFrame produced by ``build_portfolio`` or loaded from CSV.

    Returns
    -------
    DataFrame with review results for every open position.
    """
    if portfolio.empty:
        logger.info("No positions to review.")
        return pd.DataFrame()

    open_positions = (
        portfolio[portfolio["status"] == "OPEN"]
        if "status" in portfolio.columns
        else portfolio
    )

    reviews: list[dict] = []
    for _, pos in open_positions.iterrows():
        ticker = str(pos["ticker"])
        earnings_check = check_earnings_risk(ticker)

        reviews.append(
            {
                "ticker": ticker,
                "strategy": pos.get("strategy", "CSP"),
                "strike": pos.get("strike"),
                "expiration": pos.get("expiration"),
                "entry_premium": pos.get("mid_premium", 0),
                "earnings_date": earnings_check["earnings_date"],
                "days_to_earnings": earnings_check["days_to_earnings"],
                "earnings_risk": earnings_check["earnings_risk"],
                "action": earnings_check["action"],
                "reason": (
                    "Earnings approaching — close or roll the position"
                    if earnings_check["earnings_risk"]
                    else "No imminent earnings risk"
                ),
            }
        )

    return pd.DataFrame(reviews)
