# API Credentials
DELTA_API_KEY = "9Fi6OXbW4RKmaq0fgVljd1f005y4Wb"
DELTA_API_SECRET = "iNp4jbFsXY6jWpSMxOE1KcdQHSbwBWVmaSiWVzFecQ0x44qwBujK1Dx4OnKW"
DELTA_BASE_URL = "https://api.india.delta.exchange"

# Option Scalper Configuration
MAJOR_LEG_QUANTITY = 30          # Major leg contracts size (30 lots)
HEDGE_LEG_QUANTITY = 9           # Hedge leg contracts size (9 lots)
MAX_TRADES_PER_DAY = 2           # Enforce max trades per day (2 trades per day)

# Market Indicators
TIMEFRAME = "3m"                 # Candle interval ("1m", "3m", "5m")

# Take Profit & Stop Loss in USD (combined position)
TAKE_PROFIT_USD = 2.50           # Target net profit of $2.50 USD
STOP_LOSS_USD = 1.80             # Target net stop loss of $1.80 USD
BREAKEVEN_THRESHOLD_PCT = 0.60   # Lock break-even stop when PnL reaches >= 60% of TP ($1.50)

# Strategy Parameters
HEDGE_STRIKE_OFFSET = 400        # Strike price offset for the OTM hedge option
RUNWAY_MIN_USD = 0.0             # Minimum runway to S/R check (0.0 to disable project S/R block checks entirely)
ADX_MIN = 15.0                   # Minimum ADX trend strength (15.0 filters dead markets, 0.0 to disable)

# Time limits (IST)
ENTRY_WINDOW_START = "00:00"     # Starts at midnight
ENTRY_WINDOW_END = "23:59"       # 24-hour operation (settlement pause dynamically handled 16:45-17:30 IST)
FORCE_CLOSE_TIME = "17:00"       # Force close open positions at 5:00 PM IST to avoid settlement pin risk
MAX_HOLD_DURATION_MINUTES = 25  # Max hold duration for a trade in minutes (25 min option scalping limit)
MIN_HOLD_MINUTES = 5             # Minimum hold before ANY exit is allowed (prevents 7-second flip exits)
MAX_SPREAD_PCT = 12.0            # Max allowed bid-ask spread percentage to prevent slippage
MIN_LEG_OI = 5.0                 # Min open interest in options contract for trading liquidity
