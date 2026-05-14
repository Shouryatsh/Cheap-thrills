"""
Phase 3 — CSP strike selection.

For each screened stock and expiration date this module:
  1. Pulls the full put option chain.
  2. Filters to OTM puts with |delta| < MAX_DELTA (default 0.05).
  3. Further filters by open interest and minimum premium.
  4. Ranks surviving strikes by *annualised return* (premium / capital at risk).

The top-ranked strike is the recommended trade for that position.
"""

import logging
from datetime import datetime
from typing import Optional

import pandas as pd
import yfinance as yf

from .config import (
    MAX_DELTA,
    MIN_OPEN_INTEREST,
    MIN_PREMIUM,
    RISK_FREE_RATE,
)
from .greeks import annualized_return, black_scholes_delta

logger = logging.getLogger(__name__)


def find_csp_candidates(
    ticker: str,
    expiration: str,
    current_price: float,
    capital_available: float,
) -> pd.DataFrame:
    """
    Find all CSP strike candidates that satisfy the delta + liquidity filters.

    Parameters
    ----------
    ticker              Stock symbol
    expiration          Option expiration date string  (YYYY-MM-DD)
    current_price       Current stock price
    capital_available   Capital allocated to this position

    Returns
    -------
    DataFrame of viable strikes sorted by annualised return (best first).
    Empty DataFrame when no strikes qualify.
    """
    try:
        t = yf.Ticker(ticker)
        chain = t.option_chain(expiration)
        puts = chain.puts.copy()

        if puts.empty:
            return pd.DataFrame()

        dte = (
            datetime.strptime(expiration, "%Y-%m-%d").date()
            - datetime.now().date()
        ).days
        T = dte / 365.0
        if T <= 0:
            return pd.DataFrame()

        rows = []
        for _, row in puts.iterrows():
            strike = float(row["strike"])

            # Only out-of-the-money puts (below current price)
            if strike >= current_price:
                continue

            iv = float(row.get("impliedVolatility") or 0)
            bid = float(row.get("bid") or 0)
            ask = float(row.get("ask") or 0)
            open_interest = int(row.get("openInterest") or 0)
            volume = int(row.get("volume") or 0)

            if iv <= 0 or bid <= 0:
                continue

            premium = (bid + ask) / 2.0
            if premium < MIN_PREMIUM:
                continue

            delta = black_scholes_delta(
                current_price, strike, T, RISK_FREE_RATE, iv, "put"
            )
            abs_delta = abs(delta)

            if abs_delta > MAX_DELTA:
                continue

            if open_interest < MIN_OPEN_INTEREST:
                continue

            spread = ask - bid
            capital_at_risk = strike * 100          # 1 contract = 100 shares
            contracts = max(1, int(capital_available // capital_at_risk))
            total_premium = premium * 100 * contracts
            ann_ret = annualized_return(premium, strike, dte)

            rows.append(
                {
                    "ticker": ticker,
                    "expiration": expiration,
                    "dte": dte,
                    "strike": strike,
                    "bid": bid,
                    "ask": ask,
                    "mid_premium": premium,
                    "spread": spread,
                    "iv": iv,
                    "delta": delta,
                    "abs_delta": abs_delta,
                    "open_interest": open_interest,
                    "volume": volume,
                    "capital_at_risk": capital_at_risk,
                    "contracts": contracts,
                    "total_premium": total_premium,
                    "weekly_return_pct": premium / strike * 100,
                    "annualized_return_pct": ann_ret * 100,
                    "pct_otm": (current_price - strike) / current_price * 100,
                }
            )

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        return df.sort_values("annualized_return_pct", ascending=False).reset_index(
            drop=True
        )

    except Exception as exc:
        logger.error("%s: error finding CSP candidates: %s", ticker, exc)
        return pd.DataFrame()


def select_best_csp(
    ticker: str,
    expiration: str,
    current_price: float,
    capital_available: float,
) -> Optional[dict]:
    """
    Select the single best CSP for a stock: highest annualised return
    among all strikes that satisfy delta < MAX_DELTA.

    Returns None when no valid strike is found.
    """
    candidates = find_csp_candidates(
        ticker, expiration, current_price, capital_available
    )
    if candidates.empty:
        return None

    best = candidates.iloc[0].to_dict()
    logger.info(
        "%s: best CSP → strike=%.2f  delta=%.4f  premium=$%.2f  "
        "ann_return=%.1f%%",
        ticker,
        best["strike"],
        best["delta"],
        best["mid_premium"],
        best["annualized_return_pct"],
    )
    return best
