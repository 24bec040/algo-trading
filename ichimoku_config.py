from config import DELTA_API_KEY, DELTA_API_SECRET, DELTA_BASE_URL

# Option Scalper Configuration
MAJOR_LEG_QUANTITY = 10          # Major leg contracts size (10 lots)
HEDGE_LEG_QUANTITY = 3           # Hedge leg contracts size (3 lots)
MAX_TRADES_PER_DAY = 1           # Enforce max trades per day (1 scalp + 1 Iron Condor = 2 total per day)

# Market Indicators
TIMEFRAME = "3m"                 # Candle interval ("1m", "3m", "5m")

# Take Profit & Stop Loss in USD (combined position)
TAKE_PROFIT_USD = 1.20           # Target net profit of $1.20 on combined position
STOP_LOSS_USD = 0.80             # Target net stop loss of $0.80 on combined position

# Strategy Parameters
HEDGE_STRIKE_OFFSET = 400        # Strike price offset for the OTM hedge option

# Time limits (IST)
ENTRY_WINDOW_START = "00:00"     # Starts at midnight
ENTRY_WINDOW_END = "16:45"       # Stops 45 minutes before 5:30 PM expiry
FORCE_CLOSE_TIME = "17:00"       # Force close open positions at 5:00 PM IST to avoid settlement pin risk
MAX_HOLD_DURATION_MINUTES = 30  # Max hold duration for a trade in minutes (exits if TP/SL not hit in 30 mins)
MAX_SPREAD_PCT = 12.0            # Max allowed bid-ask spread percentage to prevent slippage
MIN_LEG_OI = 5.0                 # Min open interest in options contract for trading liquidity
