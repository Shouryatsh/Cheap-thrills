# Cheap Thrills — Options Wheel Strategy Tool

A systematic Python tool that implements the **cash-secured put (CSP) wheel strategy** on a ~$50 K portfolio, targeting **$5 K–$10 K/month** in options premium income.

---

## Strategy Overview

| Phase | Description |
|-------|-------------|
| **1 — Fundamental Screen** | Filter stocks by FCF > 0, net margin > 15 %, debt/assets < 50 %, price within 15 % of 52-week low, market cap ≥ $5 B |
| **2 — Options Viability** | Check weekly options availability, bid-ask spread ≤ $0.15, IVR ≥ 30 % |
| **3 — Strike Selection** | Find OTM puts with \|delta\| < 0.05; rank by annualised return (premium / capital at risk) |
| **4 — Portfolio Construction** | Allocate $50 K across 5–8 positions (≤ 80 % deployed, $10–15 K reserve) |
| **5 — Assignment Management** | If assigned, immediately sell a covered call (delta 0.30–0.45, strike > cost basis) |
| **6 — Risk Management** | Weekly review: close at 50 % profit, roll at 3× loss, never hold into earnings |
| **7 — Monthly Tracking** | Weekly targets $1 250–$2 500, monthly goal $5 000–$10 000 |

---

## Installation

```bash
git clone https://github.com/Shouryatsh/Cheap-thrills.git
cd Cheap-thrills
pip install -r requirements.txt
```

> **Data source:** Yahoo Finance via [yfinance](https://github.com/ranaroussi/yfinance) — free, no API key required.

---

## Usage

### 1. Screen stocks (Phase 1 + 2)

```bash
# Screen the full S&P 500 (takes ~10-20 min due to API rate limits)
python main.py screen

# Screen a custom list of tickers
python main.py screen --tickers AAPL MSFT GOOGL META NVDA --top 5

# Adjust the API delay if you hit rate limits
python main.py screen --delay 2.0
```

Passing candidates are saved to **`candidates.csv`**.

---

### 2. Build a CSP portfolio (Phase 3 + 4)

```bash
python main.py portfolio --capital 50000
```

The tool reads `candidates.csv`, finds the best delta < 0.05 strike for each stock, allocates capital, and saves the portfolio to **`portfolio.csv`**.

---

### 3. Weekly risk review (Phase 6)

```bash
python main.py review
```

Checks every open position for:
- Upcoming earnings within 14 days → **CLOSE/ROLL**
- Position reached 50 % profit → **CLOSE** (free up capital)
- Position at 3× entry premium → **CLOSE/ROLL** (limit loss)

---

### 4. Manage an assignment — sell covered calls (Phase 5)

```bash
# Assigned 100 shares of AAPL at $145 strike, had received $1.20 CSP premium
python main.py assign --ticker AAPL --shares 100 --cost-basis 143.80
```

Finds the best covered call (delta 0.30–0.45, strike above cost basis) and logs the trade to **`trade_log.csv`**.

---

### 5. Monthly tracking report (Phase 7)

```bash
python main.py track
```

Shows premium collected vs. the $5 K–$10 K monthly target and whether you are on pace.

---

## Configuration

All strategy parameters are in **`options_wheel/config.py`**:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `TOTAL_CAPITAL` | 50 000 | Starting capital |
| `MAX_DEPLOYMENT_RATIO` | 0.80 | Max 80 % deployed at any time |
| `RESERVE_CAPITAL` | 12 500 | Kept aside as assignment buffer |
| `MAX_POSITIONS` | 8 | Max simultaneous CSP positions |
| `MIN_NET_PROFIT_MARGIN` | 0.15 | Phase 1: >= 15 % net margin |
| `MAX_DEBT_TO_ASSETS` | 0.50 | Phase 1: debt/assets < 50 % |
| `NEAR_52W_LOW_THRESHOLD` | 0.15 | Phase 1: within 15 % of 52-week low |
| `MIN_IVR` | 30 | Phase 2: IVR >= 30 % |
| `MAX_BID_ASK_SPREAD` | 0.15 | Phase 2: spread <= $0.15 |
| `MAX_DELTA` | 0.05 | Phase 3: delta < 0.05 |
| `TARGET_DTE_MIN/MAX` | 7 / 14 | Phase 3: 7–14 DTE window |
| `CC_TARGET_DELTA_MIN/MAX` | 0.30 / 0.45 | Phase 5: CC delta range |
| `EARNINGS_BUFFER_DAYS` | 14 | Phase 6: close if earnings < 14 days away |
| `MAX_LOSS_MULTIPLIER` | 3.0 | Phase 6: close/roll at 3× premium |
| `EARLY_CLOSE_PROFIT_PCT` | 0.50 | Phase 6: close at 50 % max profit |

---

## Key Watchouts

- **Delta < 0.05 + meaningful premium** is rare — you need elevated IVR (>= 30–40 %).  Best opportunities arise after market-wide selloffs (VIX > 25).
- Close or roll CSPs at least **2 weeks before earnings** to avoid binary event risk.
- Wide bid-ask spreads eat returns — stick to the `MAX_BID_ASK_SPREAD` filter.
- All premium income is taxed as **short-term capital gains** — consult a tax advisor.

---

## Project Structure

```
Cheap-thrills/
├── main.py                    # CLI entry point
├── requirements.txt
├── options_wheel/
│   ├── config.py              # All strategy thresholds and settings
│   ├── greeks.py              # Black-Scholes delta, IVR, annualised return
│   ├── screener.py            # Phase 1 + 2: fundamental + options filters
│   ├── strike_selector.py     # Phase 3: CSP strike selection
│   ├── portfolio.py           # Phase 4 + 5: portfolio construction + CCs
│   ├── risk_manager.py        # Phase 6: earnings risk, max-loss rules
│   └── tracker.py             # Phase 7: position tracking + monthly report
└── README.md
```

---

## Disclaimer

This tool is for **educational and research purposes only**.  Options trading involves substantial risk of loss.  Past performance does not guarantee future results.  Always consult a licensed financial advisor before trading.
