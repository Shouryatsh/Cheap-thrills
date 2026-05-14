"""
Central configuration for the Options Wheel Strategy tool.

All thresholds, targets and tunable parameters live here so they can be
adjusted in one place without touching strategy logic.
"""

# ──────────────────────────────────────────────────────────────────────────────
# Capital settings
# ──────────────────────────────────────────────────────────────────────────────
TOTAL_CAPITAL: float = 50_000.0          # Starting / total capital
MAX_DEPLOYMENT_RATIO: float = 0.80       # Never deploy more than 80 % of capital
RESERVE_CAPITAL: float = 12_500.0        # Hard buffer kept aside for assignments
MAX_POSITIONS: int = 8                   # Maximum simultaneous CSP positions
CAPITAL_PER_POSITION_MIN: float = 6_000.0
CAPITAL_PER_POSITION_MAX: float = 10_000.0

# ──────────────────────────────────────────────────────────────────────────────
# Phase 1 — Fundamental screening thresholds
# ──────────────────────────────────────────────────────────────────────────────
MIN_FCF: float = 0.0                     # Positive free cash flow required
MIN_NET_PROFIT_MARGIN: float = 0.15      # Net profit margin > 15 %
MAX_DEBT_TO_ASSETS: float = 0.50         # Debt-to-assets < 50 %
MIN_MARKET_CAP: float = 5_000_000_000.0  # $5 B+ for options liquidity
NEAR_52W_LOW_THRESHOLD: float = 0.15    # Within 15 % of the 52-week low

# ──────────────────────────────────────────────────────────────────────────────
# Phase 2 — Options viability thresholds
# ──────────────────────────────────────────────────────────────────────────────
MAX_BID_ASK_SPREAD: float = 0.15        # Tight spread = liquid market
MIN_IVR: float = 30.0                   # IVR > 30 % for elevated premiums
MIN_OPEN_INTEREST: int = 500            # Minimum OI on the target strike
TARGET_DTE_MIN: int = 7                 # Minimum days-to-expiration
TARGET_DTE_MAX: int = 14               # Maximum days-to-expiration

# ──────────────────────────────────────────────────────────────────────────────
# Phase 3 — Strike selection (cash-secured puts)
# ──────────────────────────────────────────────────────────────────────────────
MAX_DELTA: float = 0.05                 # Maximum absolute delta for CSPs
MIN_PREMIUM: float = 0.05              # Minimum mid-price premium per share ($5/contract)
RISK_FREE_RATE: float = 0.05           # Annual risk-free rate (5 %)

# ──────────────────────────────────────────────────────────────────────────────
# Phase 5 — Covered call settings (post-assignment)
# ──────────────────────────────────────────────────────────────────────────────
CC_TARGET_DELTA_MIN: float = 0.30      # Covered call delta range
CC_TARGET_DELTA_MAX: float = 0.45

# ──────────────────────────────────────────────────────────────────────────────
# Phase 6 — Risk management rules
# ──────────────────────────────────────────────────────────────────────────────
EARNINGS_BUFFER_DAYS: int = 14          # Close/roll if earnings within 14 days
MAX_LOSS_MULTIPLIER: float = 3.0        # Close/roll if option >= 3× entry premium
EARLY_CLOSE_PROFIT_PCT: float = 0.50   # Close early at 50 % of max profit

# ──────────────────────────────────────────────────────────────────────────────
# Phase 7 — Monthly targets
# ──────────────────────────────────────────────────────────────────────────────
MONTHLY_TARGET_LOW: float = 5_000.0
MONTHLY_TARGET_HIGH: float = 10_000.0
WEEKLY_TARGET_LOW: float = 1_250.0
WEEKLY_TARGET_HIGH: float = 2_500.0
