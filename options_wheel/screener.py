"""
Phase 1 + Phase 2 stock screener.

Phase 1 — Fundamental filters
    • Market cap ≥ $5 B
    • Free Cash Flow > 0
    • Net Profit Margin ≥ 15 %
    • Debt-to-Assets < 50 %
    • Current price within 15 % of the 52-week low

Phase 2 — Options viability filters
    • Weekly options exist in the 7-14 DTE window
    • ATM bid-ask spread ≤ $0.15
    • Implied Volatility Rank (IVR) ≥ 30 %

Data source: Yahoo Finance via yfinance.
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

from .config import (
    EARNINGS_BUFFER_DAYS,
    MAX_BID_ASK_SPREAD,
    MAX_DEBT_TO_ASSETS,
    MIN_FCF,
    MIN_IVR,
    MIN_MARKET_CAP,
    MIN_NET_PROFIT_MARGIN,
    MIN_OPEN_INTEREST,
    NEAR_52W_LOW_THRESHOLD,
    RISK_FREE_RATE,
    TARGET_DTE_MAX,
    TARGET_DTE_MIN,
)
from .greeks import compute_historical_volatility, compute_ivr

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Fallback universe used when Wikipedia is unreachable
# ──────────────────────────────────────────────────────────────────────────────
FALLBACK_UNIVERSE: list[str] = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "BRK-B", "JNJ", "UNH",
    "V", "MA", "HD", "PG", "ABBV", "MRK", "LLY", "CVX", "XOM", "BAC", "WFC",
    "JPM", "GS", "MS", "COST", "TGT", "LOW", "NKE", "SBUX", "MCD", "DIS",
    "NFLX", "ADBE", "CRM", "ORCL", "INTC", "AMD", "QCOM", "TXN", "AVGO",
    "TMO", "DHR", "ABT", "MDT", "ISRG", "SYK", "BMY", "AMGN", "GILD",
    "CAT", "DE", "HON", "MMM", "GE", "BA", "LMT", "RTX", "NOC", "GD",
    "WMT", "TJX", "DLTR", "AZO", "ORLY", "F", "GM", "TSLA",
]


def get_sp500_tickers() -> list[str]:
    """Fetch current S&P 500 tickers from Wikipedia.  Falls back to a
    hardcoded list of quality large-caps if the network call fails."""
    try:
        tables = pd.read_html(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            timeout=10,
        )
        tickers = (
            tables[0]["Symbol"].str.replace(".", "-", regex=False).tolist()
        )
        logger.info("Fetched %d S&P 500 tickers from Wikipedia", len(tickers))
        return tickers
    except Exception as exc:
        logger.warning(
            "Could not fetch S&P 500 from Wikipedia (%s). Using fallback universe.",
            exc,
        )
        return FALLBACK_UNIVERSE


# ──────────────────────────────────────────────────────────────────────────────
# Phase 1 helpers
# ──────────────────────────────────────────────────────────────────────────────

def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def screen_fundamentals(ticker: str, info: dict) -> tuple[bool, dict]:
    """
    Apply Phase 1 fundamental filters.

    Returns
    -------
    (passes, metrics_dict)
    """
    metrics: dict = {
        "ticker": ticker,
        "market_cap": None,
        "current_price": None,
        "fcf": None,
        "net_profit_margin": None,
        "debt_to_assets": None,
        "pct_above_52w_low": None,
        "52w_low": None,
        "52w_high": None,
        "passes_fundamentals": False,
    }

    try:
        market_cap = _safe_float(info.get("marketCap"), 0)
        current_price = _safe_float(
            info.get("currentPrice") or info.get("regularMarketPrice"), 0
        )
        fcf = info.get("freeCashflow")
        profit_margin = info.get("profitMargins")
        total_debt = _safe_float(info.get("totalDebt"), 0)
        total_assets = _safe_float(info.get("totalAssets"), 0)
        low_52w = _safe_float(info.get("fiftyTwoWeekLow"), 0)
        high_52w = _safe_float(info.get("fiftyTwoWeekHigh"), 0)

        # Require these to be present and sensible
        if not (market_cap and current_price and total_assets and low_52w
                and fcf is not None and profit_margin is not None):
            logger.debug("%s: missing required fundamental data", ticker)
            return False, metrics

        debt_to_assets = total_debt / total_assets if total_assets > 0 else 1.0
        pct_above_52w_low = (
            (current_price - low_52w) / low_52w if low_52w > 0 else 1.0
        )

        metrics.update(
            {
                "market_cap": market_cap,
                "current_price": current_price,
                "fcf": float(fcf),
                "net_profit_margin": float(profit_margin),
                "debt_to_assets": debt_to_assets,
                "pct_above_52w_low": pct_above_52w_low,
                "52w_low": low_52w,
                "52w_high": high_52w,
            }
        )

        passes = (
            market_cap >= MIN_MARKET_CAP
            and float(fcf) > MIN_FCF
            and float(profit_margin) >= MIN_NET_PROFIT_MARGIN
            and debt_to_assets <= MAX_DEBT_TO_ASSETS
            and pct_above_52w_low <= NEAR_52W_LOW_THRESHOLD
        )
        metrics["passes_fundamentals"] = passes
        return passes, metrics

    except Exception as exc:
        logger.debug("%s: fundamental screening error: %s", ticker, exc)
        return False, metrics


# ──────────────────────────────────────────────────────────────────────────────
# Phase 2 helpers
# ──────────────────────────────────────────────────────────────────────────────

def _nearest_weekly_expiration(ticker_obj: yf.Ticker) -> Optional[str]:
    """Return the nearest expiration date that falls within [DTE_MIN, DTE_MAX].

    If none exists in that exact window, return the next available expiration
    after TARGET_DTE_MIN days (so we always have *something* to price).
    """
    try:
        expirations = ticker_obj.options
        if not expirations:
            return None

        today = datetime.now().date()
        target_min = today + timedelta(days=TARGET_DTE_MIN)
        target_max = today + timedelta(days=TARGET_DTE_MAX)

        # Prefer the tight window
        for exp in expirations:
            exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
            if target_min <= exp_date <= target_max:
                return exp

        # Broaden: first future expiration after target_min
        for exp in expirations:
            exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
            if exp_date >= target_min:
                return exp

        return None
    except Exception as exc:
        logger.debug("Error getting expirations: %s", exc)
        return None


def screen_options_viability(
    ticker: str,
    ticker_obj: yf.Ticker,
    current_price: float,
    hist_prices: pd.Series,
) -> tuple[bool, dict]:
    """
    Apply Phase 2 options viability filters.

    Returns
    -------
    (passes, options_metrics_dict)
    """
    metrics: dict = {
        "has_weekly_options": False,
        "expiration": None,
        "dte": None,
        "atm_iv": None,
        "ivr": None,
        "bid_ask_spread": None,
        "bid_ask_ok": False,
        "passes_options": False,
    }

    try:
        expiration = _nearest_weekly_expiration(ticker_obj)
        if not expiration:
            logger.debug("%s: no suitable expiration found", ticker)
            return False, metrics

        dte = (
            datetime.strptime(expiration, "%Y-%m-%d").date()
            - datetime.now().date()
        ).days
        if dte < 1:
            return False, metrics

        chain = ticker_obj.option_chain(expiration)
        puts = chain.puts.copy()
        if puts.empty:
            return False, metrics

        # ATM put: closest strike to current price
        puts["_strike_diff"] = abs(puts["strike"] - current_price)
        atm = puts.nsmallest(1, "_strike_diff").iloc[0]
        atm_iv = _safe_float(atm.get("impliedVolatility"), 0)
        if atm_iv <= 0:
            return False, metrics

        # IVR: use historical realised volatility as IV proxy
        hvs = compute_historical_volatility(hist_prices.values, window=20)
        ivr = compute_ivr(atm_iv, hvs) if len(hvs) > 0 else 0.0

        bid = _safe_float(atm.get("bid"), 0)
        ask = _safe_float(atm.get("ask"), 0)
        spread = ask - bid
        bid_ask_ok = 0 < spread <= MAX_BID_ASK_SPREAD

        metrics.update(
            {
                "has_weekly_options": True,
                "expiration": expiration,
                "dte": dte,
                "atm_iv": atm_iv,
                "ivr": ivr,
                "bid_ask_spread": spread,
                "bid_ask_ok": bid_ask_ok,
            }
        )

        passes = ivr >= MIN_IVR and bid_ask_ok
        metrics["passes_options"] = passes
        return passes, metrics

    except Exception as exc:
        logger.debug("%s: options viability error: %s", ticker, exc)
        return False, metrics


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def run_screener(
    tickers: Optional[list[str]] = None,
    delay: float = 1.0,
) -> pd.DataFrame:
    """
    Run the full Phase 1 + Phase 2 screener on a stock universe.

    Parameters
    ----------
    tickers     List of ticker symbols.  If *None*, uses the S&P 500.
    delay       Seconds to sleep between API calls (avoids rate-limiting).

    Returns
    -------
    DataFrame of candidates that pass both phases, sorted by IVR descending.
    """
    if tickers is None:
        tickers = get_sp500_tickers()

    logger.info("Screening %d tickers …", len(tickers))
    candidates: list[dict] = []

    for i, ticker in enumerate(tickers):
        if i > 0 and i % 10 == 0:
            logger.info(
                "Progress: %d/%d screened, %d candidates so far",
                i, len(tickers), len(candidates),
            )

        try:
            t = yf.Ticker(ticker)
            info = t.info

            # Phase 1
            passes_fund, fund_metrics = screen_fundamentals(ticker, info)
            if not passes_fund:
                time.sleep(delay * 0.2)
                continue

            logger.info("✓  %s passes fundamental screening", ticker)

            # Historical prices for IVR
            hist = t.history(period="1y")
            if hist.empty or len(hist) < 30:
                logger.debug("%s: insufficient price history", ticker)
                time.sleep(delay * 0.2)
                continue

            # Phase 2
            passes_opts, opts_metrics = screen_options_viability(
                ticker, t, fund_metrics["current_price"], hist["Close"]
            )

            if passes_opts:
                logger.info("✓✓ %s passes options viability screening", ticker)
                candidates.append({**fund_metrics, **opts_metrics})

        except Exception as exc:
            logger.warning("%s: unexpected error: %s", ticker, exc)

        time.sleep(delay)

    if not candidates:
        logger.warning("No candidates found matching all criteria.")
        return pd.DataFrame()

    df = pd.DataFrame(candidates).sort_values("ivr", ascending=False)
    return df.reset_index(drop=True)
