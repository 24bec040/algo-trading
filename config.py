# API Settings
DELTA_API_KEY = "9Fi6OXbW4RKmaq0fgVljd1f005y4Wb"
DELTA_API_SECRET = "iNp4jbFsXY6jWpSMxOE1KcdQHSbwBWVmaSiWVzFecQ0x44qwBujK1Dx4OnKW"
DELTA_BASE_URL = "https://api.india.delta.exchange"

# Strategy Structure
TRADE_QUANTITY = 30               # 30 contracts (0.03 BTC size) — margin ~$19.87, targets $1-2 USD net profit per day
MAX_TRADES_PER_DAY = 1           # Enforce max trades per day
TEST_ENTRY = False               # Bypass safety gates for testing when True

# Strike Selection Settings (OTM targets)
SHORT_CALL_DELTA_TARGET = 0.20   # Balanced setup: Target Delta for Call entries
SHORT_PUT_DELTA_TARGET = -0.20   # Balanced setup: Target Delta for Put entries
HEDGE_WIDTH_USD = 1000           # Balanced setup: Width of wings (hedge legs)

# Entry Window (IST)
TRADE_WINDOW_START = "07:00"     # IST Entry Start — after opening IV spike settles (was 05:30)
TRADE_WINDOW_END = "09:30"       # IST Entry End (07:00 to 09:30 gives 8-10 hrs theta remaining)
FORCE_CLOSE_TIME = "14:50"       # IST Force Close time before settlement

# Entry Filters (VRP & IV filters REMOVED as requested)
IV_PERCENTILE_THRESHOLD = 0      # REMOVED / Disabled
IV_VALUE_THRESHOLD = 0.0         # REMOVED / Disabled
MIN_VRP_GAP = -1.0               # REMOVED / Disabled
TRENDING_THRESHOLD_60M = 0.02    # 2.0% max spot movement in last 60 minutes
MIN_LEG_OI = 1.0                 # Require liquid contract
MIN_STRIKE_DISTANCE_USD = 400    # Short strikes must be >=400 USD from BTC — blocks near-ATM entries without being too strict
MAX_SPREAD_PCT = 35.0            # Allow standard OTM option bid-ask spreads

# Exit Thresholds — FIXED DOLLAR P&L (not % of premium)
PROFIT_TARGET_USD = 1.50         # Exit when position P&L reaches +$1.50 USD profit
STOP_LOSS_USD     = 1.50         # Exit when position P&L reaches -$1.50 USD loss

# Keep these for backward-compat with leg-exit code only
PROFIT_MIN_PCT = 0.50            # (used only for post-leg-exit half-side management)
PROFIT_MAX_PCT = 0.80            # (used only in payoff analysis display)
STOP_LOSS_PCT  = 0.80            # (used only for post-leg-exit half-side management)

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
