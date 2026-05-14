"""
Phase 4 — Portfolio construction
Phase 5 — Assignment management (covered calls)

build_portfolio  — allocate capital across the best screened candidates,
                   returning one CSP position per stock.
find_covered_call — after assignment, find the best covered call to sell
                    immediately (delta 0.30-0.45, strike above cost basis).
"""

import logging
from datetime import datetime
from typing import Optional

import pandas as pd
import yfinance as yf

from .config import (
    CAPITAL_PER_POSITION_MAX,
    CAPITAL_PER_POSITION_MIN,
    CC_TARGET_DELTA_MAX,
    CC_TARGET_DELTA_MIN,
    MAX_POSITIONS,
    MAX_DEPLOYMENT_RATIO,
    RESERVE_CAPITAL,
    RISK_FREE_RATE,
    TARGET_DTE_MAX,
    TOTAL_CAPITAL,
)
from .greeks import black_scholes_delta
from .strike_selector import select_best_csp

logger = logging.getLogger(__name__)


def build_portfolio(
    candidates: pd.DataFrame,
    capital: float = TOTAL_CAPITAL,
) -> pd.DataFrame:
    """
    Build a diversified CSP portfolio from Phase 1+2 screened candidates.

    Capital allocation rules
    ------------------------
    • Maximum deployable = capital × MAX_DEPLOYMENT_RATIO − RESERVE_CAPITAL
    • Per-position size clamped between CAPITAL_PER_POSITION_MIN and MAX
    • At most MAX_POSITIONS concurrent positions
    • Stops adding positions if remaining deployable capital is exhausted

    Parameters
    ----------
    candidates  DataFrame produced by ``run_screener``.
    capital     Total available capital (default 50 000).

    Returns
    -------
    DataFrame where every row is an open CSP position.
    """
    deployable = capital * MAX_DEPLOYMENT_RATIO - RESERVE_CAPITAL
    per_position = min(
        CAPITAL_PER_POSITION_MAX,
        max(CAPITAL_PER_POSITION_MIN, deployable / MAX_POSITIONS),
    )

    logger.info(
        "Building portfolio: $%,.0f total  $%,.0f deployable  $%,.0f/position",
        capital, deployable, per_position,
    )

    positions: list[dict] = []
    total_deployed = 0.0

    for _, row in candidates.iterrows():
        if len(positions) >= MAX_POSITIONS:
            break
        if total_deployed + per_position > deployable:
            break

        ticker = str(row["ticker"])
        expiration = row.get("expiration")
        current_price = row.get("current_price")

        if not expiration or not current_price:
            continue

        best = select_best_csp(ticker, expiration, float(current_price), per_position)
        if best is None:
            logger.info("%s: no valid CSP found — skipping", ticker)
            continue

        capital_used = best["capital_at_risk"] * best["contracts"]

        positions.append(
            {
                "ticker": ticker,
                "strategy": "CSP",
                "expiration": expiration,
                "dte": best["dte"],
                "strike": best["strike"],
                "current_price": current_price,
                "contracts": best["contracts"],
                "mid_premium": best["mid_premium"],
                "total_premium": best["total_premium"],
                "delta": best["delta"],
                "iv": best["iv"],
                "ivr": row.get("ivr", 0),
                "capital_deployed": capital_used,
                "weekly_return_pct": best["weekly_return_pct"],
                "annualized_return_pct": best["annualized_return_pct"],
                "pct_otm": best["pct_otm"],
                "open_interest": best["open_interest"],
                "status": "OPEN",
                "entry_date": datetime.now().strftime("%Y-%m-%d"),
            }
        )
        total_deployed += capital_used
        logger.info(
            "Added %s CSP: strike=%.2f  contracts=%d  premium=$%.0f",
            ticker, best["strike"], best["contracts"], best["total_premium"],
        )

    if not positions:
        logger.warning("No positions could be built.")
        return pd.DataFrame()

    portfolio = pd.DataFrame(positions)
    logger.info(
        "Portfolio: %d positions  $%,.0f deployed  $%,.0f total premium",
        len(portfolio), total_deployed, portfolio["total_premium"].sum(),
    )
    return portfolio


def find_covered_call(
    ticker: str,
    cost_basis: float,
    shares: int = 100,
) -> Optional[dict]:
    """
    Phase 5: Find the best covered call to sell immediately after assignment.

    Criteria
    --------
    • Strike strictly above cost basis (never lock in a loss on exit)
    • Call delta in [CC_TARGET_DELTA_MIN, CC_TARGET_DELTA_MAX]  (0.30–0.45)
    • Nearest weekly expiration within 3–28 DTE
    • Among qualifying strikes, pick the one with the highest total premium

    Parameters
    ----------
    ticker      Assigned stock symbol
    cost_basis  Effective cost basis per share (assignment strike − CSP premium)
    shares      Number of shares held (typically 100 per contract)

    Returns
    -------
    Dict describing the recommended covered call, or None.
    """
    try:
        t = yf.Ticker(ticker)
        info = t.info
        current_price = float(
            info.get("currentPrice") or info.get("regularMarketPrice") or 0
        )
        if current_price <= 0:
            logger.error("%s: cannot get current price", ticker)
            return None

        expirations = t.options
        if not expirations:
            return None

        today = datetime.now().date()
        target_exp: Optional[str] = None
        for exp in expirations:
            exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
            dte_candidate = (exp_date - today).days
            if 3 <= dte_candidate <= TARGET_DTE_MAX * 2:
                target_exp = exp
                break

        if target_exp is None:
            target_exp = expirations[0]

        dte = (datetime.strptime(target_exp, "%Y-%m-%d").date() - today).days
        T = max(dte, 1) / 365.0

        chain = t.option_chain(target_exp)
        calls = chain.calls.copy()
        if calls.empty:
            return None

        rows = []
        for _, row in calls.iterrows():
            strike = float(row["strike"])

            # Only consider strikes above cost basis
            if strike <= cost_basis:
                continue

            iv = float(row.get("impliedVolatility") or 0)
            bid = float(row.get("bid") or 0)
            ask = float(row.get("ask") or 0)

            if iv <= 0 or bid <= 0:
                continue

            delta = black_scholes_delta(
                current_price, strike, T, RISK_FREE_RATE, iv, "call"
            )
            if not (CC_TARGET_DELTA_MIN <= delta <= CC_TARGET_DELTA_MAX):
                continue

            premium = (bid + ask) / 2.0
            contracts = max(1, shares // 100)
            total_premium = premium * 100 * contracts
            profit_if_called = (strike - cost_basis) * shares + total_premium

            rows.append(
                {
                    "ticker": ticker,
                    "strategy": "CC",
                    "expiration": target_exp,
                    "dte": dte,
                    "strike": strike,
                    "current_price": current_price,
                    "cost_basis": cost_basis,
                    "bid": bid,
                    "ask": ask,
                    "mid_premium": premium,
                    "total_premium": total_premium,
                    "delta": delta,
                    "iv": iv,
                    "contracts": contracts,
                    "profit_if_called": profit_if_called,
                    "pct_otm": (strike - current_price) / current_price * 100,
                }
            )

        if not rows:
            logger.warning(
                "%s: no covered call found in delta range %.2f–%.2f",
                ticker, CC_TARGET_DELTA_MIN, CC_TARGET_DELTA_MAX,
            )
            return None

        best = (
            pd.DataFrame(rows)
            .sort_values("total_premium", ascending=False)
            .iloc[0]
            .to_dict()
        )
        logger.info(
            "%s: best CC → strike=%.2f  delta=%.3f  premium=$%.2f  "
            "profit if called=$%.0f",
            ticker, best["strike"], best["delta"],
            best["mid_premium"], best["profit_if_called"],
        )
        return best

    except Exception as exc:
        logger.error("%s: error finding covered call: %s", ticker, exc)
        return None
