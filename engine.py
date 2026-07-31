import math
import collections
import numpy as np

def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def norm_pdf(x):
    return math.exp(-0.5 * x**2) / math.sqrt(2.0 * math.pi)

def black_scholes_delta(spot, strike, t_years, iv, rate, option_type):
    if t_years <= 0 or iv <= 0:
        return 1.0 if option_type in ('C', 'call') else -1.0
    d1 = (math.log(spot / strike) + (rate + (iv ** 2) / 2.0) * t_years) / (iv * math.sqrt(t_years))
    if option_type in ('C', 'call'):
        return norm_cdf(d1)
    else:
        return norm_cdf(d1) - 1.0

def black_scholes_price(spot, strike, t_years, iv, rate, option_type):
    if t_years <= 0:
        return max(0.0, spot - strike) if option_type in ('C', 'call') else max(0.0, strike - spot)
    if iv <= 0:
        disc = math.exp(-rate * t_years)
        return max(0.0, spot - strike * disc) if option_type in ('C', 'call') else max(0.0, strike * disc - spot)
    d1 = (math.log(spot / strike) + (rate + (iv ** 2) / 2.0) * t_years) / (iv * math.sqrt(t_years))
    d2 = d1 - iv * math.sqrt(t_years)
    disc = math.exp(-rate * t_years)
    if option_type in ('C', 'call'):
        return spot * norm_cdf(d1) - strike * disc * norm_cdf(d2)
    else:
        return strike * disc * norm_cdf(-d2) - spot * norm_cdf(-d1)

def get_iv_percentile(daily_candles, vrp_scale=1.15, iv_min=0.20, iv_max=2.50):
    if not daily_candles or len(daily_candles) < 32:
        return 0.40, 100.0
    closes = [float(c['close']) for c in daily_candles]
    log_returns = [math.log(closes[i] / closes[i-1]) for i in range(1, len(closes))]
    
    iv_history = []
    for i in range(len(log_returns) - 30 + 1):
        window = log_returns[i:i+30]
        mean_r = sum(window) / 30.0
        var_r = sum((x - mean_r) ** 2 for x in window) / 29.0
        vol = math.sqrt(var_r) * math.sqrt(365)
        est_iv = vol * vrp_scale
        est_iv = max(iv_min, min(iv_max, est_iv))
        iv_history.append(est_iv)
        
    current_iv = iv_history[-1]
    trailing_ivs = iv_history[-30:] if len(iv_history) >= 30 else iv_history
    less_or_equal = sum(1 for x in trailing_ivs if x <= current_iv)
    percentile = (less_or_equal / len(trailing_ivs)) * 100.0
    return current_iv, percentile

class StrategyEngine:
    def __init__(self):
        self.btc_prices = collections.deque(maxlen=100)
        self.combined_premiums = collections.deque(maxlen=100)
        self.iv_values = collections.deque(maxlen=100)
        self.resistance_levels = {}
        self.support_levels = {}

    def add_sample(self, btc_price, combined_premium, iv):
        self.btc_prices.append(btc_price)
        self.combined_premiums.append(combined_premium)
        self.iv_values.append(iv)

    def calculate_volatility_levels(self, spot_price, annualized_iv):
        return {}, {}

    def get_safe_zone_status(self, current_price):
        return True

    def check_pullback(self, history, side="CALL"):
        return False

    def get_btc_change(self):
        if len(self.btc_prices) < 2: return 0.0
        return (self.btc_prices[-1] - self.btc_prices[0]) / self.btc_prices[0]

    def calculate_edge_score(self):
        return 80

    def get_decision(self, score, current_price):
        return "ENTER"
