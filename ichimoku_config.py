from config import DELTA_API_KEY, DELTA_API_SECRET, DELTA_BASE_URL

# Option Scalper Configuration
MAJOR_LEG_QUANTITY = 30          # Major leg contracts size (30 lots)
HEDGE_LEG_QUANTITY = 9           # Hedge leg contracts size (9 lots)
MAX_TRADES_PER_DAY = 2           # Enforce max trades per day (2 trades per day)

# Market Indicators
TIMEFRAME = "3m"                 # Candle interval ("1m", "3m", "5m")

# Take Profit & Stop Loss in USD (combined position)
TAKE_PROFIT_USD = 2.00           # Target net profit of $2.00 USD
STOP_LOSS_USD = 2.00             # Target net stop loss of $2.00 USD

# Percentage-based Risk Targets (dynamic stop-loss / take-profit)
TAKE_PROFIT_PCT = 0.85           # 85% of major leg entry investment value
STOP_LOSS_PCT = 0.40             # 40% of major leg entry investment value
BREAKEVEN_THRESHOLD_PCT = 0.50   # Lock break-even stop when target rises >= 50% of Take Profit

# Strategy Parameters
HEDGE_STRIKE_OFFSET = 400        # Strike price offset for the OTM hedge option
RUNWAY_MIN_USD = 0.0             # Minimum runway to S/R check (0.0 to disable project S/R block checks entirely)

# Time limits (IST)
ENTRY_WINDOW_START = "00:00"     # Starts at midnight
ENTRY_WINDOW_END = "16:45"       # Stops 45 minutes before 5:30 PM expiry
FORCE_CLOSE_TIME = "17:00"       # Force close open positions at 5:00 PM IST to avoid settlement pin risk
MAX_HOLD_DURATION_MINUTES = 30  # Max hold duration for a trade in minutes (exits if TP/SL not hit in 30 mins)
MIN_HOLD_MINUTES = 5             # Minimum hold before ANY exit is allowed (prevents 7-second flip exits)
MAX_SPREAD_PCT = 12.0            # Max allowed bid-ask spread percentage to prevent slippage
MIN_LEG_OI = 5.0                 # Min open interest in options contract for trading liquidity
