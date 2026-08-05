# Institutional Strategy Knowledge Base & Execution Standards

This document synthesizes the core rules, formulas, and risk management guidelines extracted from the official strategy handbooks:
1. **Options Trading IQ Iron Condor Strategy Guide** (37 Pages)
2. **Karen Péloille - Trading with Ichimoku Handbook** (182 Pages)

---

## 1. Iron Condor Strategy Rules (`config.py` & `bot.py`)

### A. Core Strategy Parameters
* **Target Delta:** `0.10` to `0.15` Delta for Short Call & Short Put legs (~88%–90% OTM win probability).
* **Entry Window (IST):** `05:30 IST – 09:30 IST` (Early morning high-premium collection window).
* **Execution Sizing:** `20 Lots` (0.02 BTC) per trade.
* **Profit Target:** `$1.00 – $1.50 USD` per trade (Fast 20%–50% premium melt target).
* **Stop Loss:** `$1.50 USD` per trade (Strict 1:1 risk-reward cap).

### B. The "Delta Dollars" Metric (PDF Page 19-20)
* **Formula:** $\text{Delta Dollars} = \text{Combined Net Delta} \times \text{Spot Price}$
* **Institutional Rule:** Monitor Delta Dollars exposure continuously to ensure the position remains strictly Delta-Neutral. Alert/Adjust if Delta Dollars exceed 200% of capital risk allowance.

### C. Volatility Term Structure & Market Regime (PDF Page 8-15)
* **Contango:** Front-month IV lower than back-month IV (normal, calm market). Optimal regime for Iron Condor theta decay.
* **Backwardation:** Front-month IV spikes above back-month IV (panic spike). Avoid opening new Condors until 1-2 weeks after the initial panic spike settles.

---

## 2. Ichimoku Scalping Strategy Rules (`ichimoku_config.py` & `ichimoku_bot.py`)

### A. Multi-Timeframe Alignment (Book Page 72-74)
* **4H Timeframe:** Macro Trend Bias (Bullish, Bearish, or Neutral).
* **1H Timeframe:** Intermediate Trend Bias.
* **15m Timeframe:** Dynamic Swing Support & Resistance level identification.
* **3m Timeframe:** Precision entry trigger execution.
* **Rule:** Never open a scalp when 4H and 1H trends are in conflict (e.g. 4H Bearish vs 1H Bullish).

### B. Kijun-Sen Equilibrium & Breakout (Book Page 58 & 71)
* **Kijun-Sen (26-period midpoint):** Represents baseline market equilibrium.
* **Impulse Entry Rule:** A valid BUY_CALL requires price to break cleanly above Kijun-sen (`p_close > prev_kijun`). A valid BUY_PUT requires price to break cleanly below Kijun-sen (`p_close < prev_kijun`).

### C. Kumo Cloud & Obstacle-Free Runway (Book Page 73-74)
* **Cloud Color Check:** BUY_CALL requires upward Green cloud (`Span A > Span B`). BUY_PUT requires downward Red cloud (`Span A < Span B`).
* **Runway Filter:** Enforce a minimum **$200+ USD clean runway** above overhead resistance or below underlying support before triggering entry.

---

## 3. Post-Trade Autonomous Diagnostics (`analyze_performance.py`)
* Automatically parses `completed_trades.json` to calculate win rate, average win/loss, hold duration, and exit reasons.
* Provides diagnostic recommendations if win rate drops below 85%.
