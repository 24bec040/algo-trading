# API Settings
DELTA_API_KEY = "9Fi6OXbW4RKmaq0fgVljd1f005y4Wb"
DELTA_API_SECRET = "iNp4jbFsXY6jWpSMxOE1KcdQHSbwBWVmaSiWVzFecQ0x44qwBujK1Dx4OnKW"
DELTA_BASE_URL = "https://api.india.delta.exchange"

# Strategy Structure
TRADE_QUANTITY = 20               # Number of contracts per leg (0.001 multiplier)
MAX_TRADES_PER_DAY = 1           # Enforce max trades per day

# Strike Selection Settings (OTM targets)
SHORT_CALL_DELTA_TARGET = 0.10   # Target Delta for Call entries (~90% OTM probability)
SHORT_PUT_DELTA_TARGET = -0.10   # Target Delta for Put entries (~90% OTM probability)

# Entry Window (IST)
TRADE_WINDOW_START = "05:30"     # IST Entry start window
TRADE_WINDOW_END = "12:30"       # IST Entry end window
FORCE_CLOSE_TIME = "14:50"       # IST Force Close time before settlement

# Entry Filters (VRP & IV filters REMOVED as requested)
IV_PERCENTILE_THRESHOLD = 0      # REMOVED / Disabled
IV_VALUE_THRESHOLD = 0.0         # REMOVED / Disabled
MIN_VRP_GAP = -1.0               # REMOVED / Disabled
TRENDING_THRESHOLD_60M = 0.02    # 2.0% max spot movement in last 60 minutes
MIN_LEG_OI = 1.0                 # Require liquid contract
MAX_SPREAD_PCT = 15.0            # Allow standard option spreads

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
