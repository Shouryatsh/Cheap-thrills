"""
Black-Scholes greeks and volatility helpers used throughout the strategy tool.

Functions
---------
black_scholes_delta         — put or call delta via Black-Scholes
black_scholes_price         — theoretical option price
compute_historical_volatility — rolling annualised HV from a price series
compute_ivr                 — Implied Volatility Rank (0-100)
annualized_return           — weekly premium expressed as an annualised rate
"""

import numpy as np
from scipy.stats import norm


def black_scholes_delta(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str = "put",
) -> float:
    """
    Black-Scholes delta for a European option.

    Parameters
    ----------
    S           Current stock price
    K           Strike price
    T           Time to expiration in years  (DTE / 365)
    r           Annual risk-free rate         (e.g. 0.05)
    sigma       Annual implied volatility      (e.g. 0.30)
    option_type 'call' or 'put'

    Returns
    -------
    Delta as a float.  Put deltas are negative (range -1 … 0).
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0

    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    return float(norm.cdf(d1)) if option_type == "call" else float(norm.cdf(d1) - 1.0)


def black_scholes_price(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str = "put",
) -> float:
    """
    Black-Scholes theoretical option price.

    Returns intrinsic value when T ≤ 0.
    """
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return max(0.0, K - S) if option_type == "put" else max(0.0, S - K)

    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)

    if option_type == "call":
        return float(S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2))
    return float(K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))


def compute_historical_volatility(prices: np.ndarray, window: int = 20) -> np.ndarray:
    """
    Rolling annualised historical volatility (close-to-close log returns).

    Parameters
    ----------
    prices  Array of closing prices (chronological order)
    window  Rolling window in trading days (default 20 ≈ 1 month)

    Returns
    -------
    Array of annualised HV values. Length = max(0, len(prices) - window).
    """
    if len(prices) < window + 1:
        return np.array([])

    log_returns = np.log(prices[1:] / prices[:-1])
    hvs = [
        np.std(log_returns[i - window : i], ddof=1) * np.sqrt(252)
        for i in range(window, len(log_returns) + 1)
    ]
    return np.array(hvs)


def compute_ivr(current_iv: float, historical_hvs: np.ndarray) -> float:
    """
    Implied Volatility Rank expressed as a percentage (0–100).

    Uses historical realised volatility as a proxy for historical IV because
    yfinance does not expose historical implied-volatility time-series.

    IVR = (current_IV − 52w_low) / (52w_high − 52w_low) × 100

    The 5th / 95th percentiles of *historical_hvs* stand in for the
    52-week IV low and high respectively.
    """
    if len(historical_hvs) == 0 or current_iv <= 0:
        return 0.0

    iv_low = float(np.percentile(historical_hvs, 5))
    iv_high = float(np.percentile(historical_hvs, 95))

    if iv_high <= iv_low:
        return 50.0  # degenerate range → assume median rank

    ivr = (current_iv - iv_low) / (iv_high - iv_low) * 100.0
    return float(np.clip(ivr, 0.0, 100.0))


def annualized_return(premium: float, strike: float, dte: int) -> float:
    """
    Annualised return for a cash-secured put.

    annualized = (premium / strike) × (365 / dte)

    Parameters
    ----------
    premium  Mid-price premium received per share
    strike   Strike price (capital at risk per share)
    dte      Days to expiration

    Returns
    -------
    Annualised return as a decimal (e.g. 0.32 = 32 %).
    """
    if strike <= 0 or dte <= 0:
        return 0.0
    return (premium / strike) * (365.0 / dte)
