"""
config.py
Central configuration for the IIFL VCP Scanner
"""

# ==========================================================
# IIFL API
# ==========================================================

IIFL_BASE_URL = "https://api.iiflcapital.com/v1"

EXCHANGE = "NSEEQ"

DEFAULT_INTERVAL = "1 day"

HISTORY_DAYS = 450


# ==========================================================
# SCANNER SETTINGS
# ==========================================================

MIN_PRICE = 100

MAX_PRICE = 100000

MIN_AVG_VOLUME = 300000

MIN_MARKET_CAP = 0

MIN_HISTORY = 250


# ==========================================================
# TREND TEMPLATE
# ==========================================================

USE_MINERVINI_TEMPLATE = True

MIN_TREND_SCORE = 80

MA_SHORT = 50

MA_MEDIUM = 150

MA_LONG = 200


# ==========================================================
# VCP SETTINGS
# ==========================================================

MIN_PRIOR_UPTREND = 30          # %

MAX_CONSOLIDATION = 25          # %

MAX_FINAL_CONTRACTION = 10      # %

MIN_CONTRACTIONS = 2

MAX_CONTRACTIONS = 5

MIN_VOLUME_DRYUP = 0.75

BREAKOUT_VOLUME_RATIO = 1.50

PIVOT_BUFFER = 3                # %


# ==========================================================
# RELATIVE STRENGTH
# ==========================================================

MIN_RS_SCORE = 70

COMPARE_WITH_NIFTY = True


# ==========================================================
# RISK MANAGEMENT
# ==========================================================

ATR_PERIOD = 14

STOPLOSS_ATR = 2.0

RISK_PER_TRADE = 1.0


# ==========================================================
# INDICATORS
# ==========================================================

EMA_FAST = 21

EMA_MEDIUM = 50

EMA_LONG = 150

EMA_EXTRA = 200

RSI_PERIOD = 14

MACD_FAST = 12

MACD_SLOW = 26

MACD_SIGNAL = 9


# ==========================================================
# SUPPORT / RESISTANCE
# ==========================================================

SWING_WINDOW = 5

LEVEL_TOLERANCE = 1.5

MAX_LEVELS = 5


# ==========================================================
# CHART SETTINGS
# ==========================================================

DEFAULT_CHART_DAYS = 250

SHOW_VOLUME = True

SHOW_MACD = True

SHOW_RSI = True

SHOW_EMA = True

SHOW_SUPPORT_RESISTANCE = True


# ==========================================================
# CACHE
# ==========================================================

HISTORICAL_CACHE_SECONDS = 300

INSTRUMENT_CACHE_SECONDS = 86400


# ==========================================================
# SCORING
# ==========================================================

WEIGHT_TREND = 25

WEIGHT_STAGE = 15

WEIGHT_VOLUME = 20

WEIGHT_VCP = 25

WEIGHT_RS = 15
