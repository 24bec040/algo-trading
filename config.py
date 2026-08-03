# API Settings
DELTA_API_KEY = "9Fi6OXbW4RKmaq0fgVljd1f005y4Wb"
DELTA_API_SECRET = "iNp4jbFsXY6jWpSMxOE1KcdQHSbwBWVmaSiWVzFecQ0x44qwBujK1Dx4OnKW"
DELTA_BASE_URL = "https://api.india.delta.exchange"

# Strategy Structure
TRADE_QUANTITY = 20               # Number of contracts per leg (0.001 multiplier)
MAX_TRADES_PER_DAY = 1           # Enforce max trades per day

# Strike Selection Settings (OTM targets)
SHORT_CALL_DELTA_TARGET = 0.16   # Target Delta for Call entries (targets $5-$6 daily return)
SHORT_PUT_DELTA_TARGET = -0.16   # Target Delta for Put entries (negative value)

# Entry Window (IST)
TRADE_WINDOW_START = "05:30"     # IST Entry start
TRADE_WINDOW_END = "12:30"       # IST Entry end
FORCE_CLOSE_TIME = "15:00"       # IST Force Close time
TEST_ENTRY = False               # Set to True to force-take a trade right now for testing

# Entry Filters
IV_PERCENTILE_THRESHOLD = 0      # Disabled (was 20)
IV_VALUE_THRESHOLD = 0.30        # Require average option IV >= 30%
MIN_VRP_GAP = 0.05               # Require Option IV >= Realized Volatility + 5%
TRENDING_THRESHOLD_60M = 0.008   # Spot max change <= 0.8% in 60m (12 bars * 5m)
MIN_LEG_OI = 5.0                 # Minimum leg Open Interest (liquidity indicator)
MAX_SPREAD_PCT = 5.0             # Maximum option spread percentage (max slippage checks)

# Normal Exit Thresholds (applied on net premium collected)
PROFIT_MIN_PCT = 0.10            # 10% melt (warning profit trigger)
PROFIT_MAX_PCT = 0.20            # 20% melt (fast target)
STOP_LOSS_PCT = 0.80             # 80% net loss stopping (optimized for small balance)

# Leg Exit Thresholds (close losing side only)
LEG_SHORT_EXPANSION_PCT = 0.25   # short option expanded >= 25%
LEG_SPOT_MOVE_PCT = 0.007        # spot price moved >= 0.7%
LEG_IV_DROP_LIMIT = 5.0          # IV dropped <= 5 points (0.05 in dec)
LEG_SHORT_DELTA = 0.32           # short delta >= 0.32

# Post Leg-Exit Thresholds (applied on remaining side entry premium)
HALF_PROFIT_PCT = 0.80           # 80% melt
HALF_STOP_PCT = 0.20             # 20% loss

# Black-Scholes Model Config
RISK_FREE_RATE = 0.05            # 5%
VOL_RISK_PREMIUM_SCALE = 1.15    # scale realized volatility * 1.15
IV_MIN_CLIP = 0.20               # 20%
IV_MAX_CLIP = 2.50               # 250%

# Misc Settings
UPDATE_INTERVAL_SECONDS = 5.0    # Frequency for checks (changed to 5s for API safety)
DRY_RUN = False                  # SET TO TRUE FOR TESTING (Live Dashboard)
ONLY_MANAGE = False              # IF TRUE, BOT WILL NOT TAKE NEW TRADES
