import time
import json
import os
import math
from datetime import datetime, timezone, timedelta
from pytz import timezone as pytz_tz
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.text import Text

# Imports
from delta_client import DeltaClient
import ichimoku_config as config

# Setup timezone
IST = timezone(timedelta(hours=5, minutes=30))
console = Console()

class Leg:
    def __init__(self, symbol, side, entry_premium, size, role):
        self.symbol = symbol
        self.side = side             # always 'buy'
        self.entry_premium = float(entry_premium)
        self.current_premium = float(entry_premium)
        self.size = int(size)
        self.role = role             # 'major' or 'hedge'
        self.status = "OPEN"

    def to_dict(self):
        return {
            'symbol': self.symbol,
            'side': self.side,
            'entry_premium': self.entry_premium,
            'current_premium': self.current_premium,
            'size': self.size,
            'role': self.role,
            'status': self.status
        }

    @classmethod
    def from_dict(cls, d):
        if not d: return None
        leg = cls(d['symbol'], d['side'], d['entry_premium'], d['size'], d['role'])
        leg.current_premium = d.get('current_premium', d['entry_premium'])
        leg.status = d.get('status', 'OPEN')
        return leg


class IchimokuPosition:
    def __init__(self, legs_dict, entry_spot, direction):
        self.legs = legs_dict        # dict mapping role -> Leg: 'major' and 'hedge'
        self.entry_spot = float(entry_spot)
        self.direction = direction   # "CALL" or "PUT"
        self.entry_time = datetime.now(IST)
        self.exit_reason = None

    def to_dict(self):
        return {
            'legs': {role: leg.to_dict() for role, leg in self.legs.items()},
            'entry_spot': self.entry_spot,
            'direction': self.direction,
            'entry_time': self.entry_time.strftime("%Y-%m-%d %H:%M:%S") if isinstance(self.entry_time, datetime) else str(self.entry_time),
            'exit_reason': self.exit_reason
        }

    @classmethod
    def from_dict(cls, d):
        if not d: return None
        legs_dict = {role: Leg.from_dict(ld) for role, ld in d['legs'].items()}
        pos = cls(legs_dict, d['entry_spot'], d['direction'])
        entry_time_str = d.get('entry_time')
        if entry_time_str:
            try:
                pos.entry_time = datetime.strptime(entry_time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=IST)
            except:
                pos.entry_time = entry_time_str
        pos.exit_reason = d.get('exit_reason')
        return pos


class IchimokuScalpBot:
    def __init__(self):
        self.client = DeltaClient()
        self.active_position = None
        self.trade_history = []
        self.log_messages = []
        self.trades_taken_today = 0
        self.last_timeframe_data = None
        self.last_entered_candle_time = None
        self.load_state()
        
    def add_log(self, text):
        timestamp = datetime.now(IST).strftime("%H:%M:%S")
        msg = f"[{timestamp}] {text}"
        self.log_messages.append(msg)
        if len(self.log_messages) > 30:
            self.log_messages.pop(0)

    def load_state(self):
        dir_path = os.path.dirname(os.path.abspath(__file__))
        # Active Position
        pos_path = os.path.join(dir_path, "ichimoku_active.json")
        if os.path.exists(pos_path):
            try:
                with open(pos_path, 'r') as f:
                    data = json.load(f)
                    if data:
                        # Check structure version
                        if isinstance(data, dict) and ('active_position' in data or 'last_entered_candle_time' in data):
                            pos_data = data.get('active_position')
                            if pos_data:
                                self.active_position = IchimokuPosition.from_dict(pos_data)
                            self.last_entered_candle_time = data.get('last_entered_candle_time')
                        else:
                            # Backward compatibility (raw position dict)
                            self.active_position = IchimokuPosition.from_dict(data)
                            self.last_entered_candle_time = None
                        
                        if self.active_position:
                            legs_str = ", ".join([f"{r}:{l.symbol}" for r, l in self.active_position.legs.items()])
                            self.add_log(f"Restored active position: {legs_str}")
            except Exception as e:
                self.add_log(f"Error loading active position: {e}")

        # Trades History
        hist_path = os.path.join(dir_path, "ichimoku_trades.json")
        if os.path.exists(hist_path):
            try:
                with open(hist_path, 'r') as f:
                    self.trade_history = json.load(f)
            except Exception as e:
                self.add_log(f"Error loading trade history: {e}")

    def save_state(self):
        dir_path = os.path.dirname(os.path.abspath(__file__))
        # Active Position
        pos_path = os.path.join(dir_path, "ichimoku_active.json")
        data = {
            'active_position': self.active_position.to_dict() if self.active_position else None,
            'last_entered_candle_time': self.last_entered_candle_time
        }
        try:
            with open(pos_path, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            self.add_log(f"Error saving active position state: {e}")

        # Trades History
        hist_path = os.path.join(dir_path, "ichimoku_trades.json")
        try:
            with open(hist_path, 'w') as f:
                json.dump(self.trade_history, f, indent=4)
        except Exception as e:
            self.add_log(f"Error saving trade history: {e}")


    def query_trades_today_count(self):
        current_date = datetime.now(IST).strftime("%Y-%m-%d")
        count = 0
        for tr in self.trade_history:
            ent = tr.get('entry_time', '')
            if ent.startswith(current_date):
                count += 1
        self.trades_taken_today = count

    def calculate_ichimoku(self, candles):
        if not candles or len(candles) < 78:
            return None

        # Sort time ascending
        candles.sort(key=lambda x: x.get('time', 0))

        highs = [float(c['high']) for c in candles]
        lows = [float(c['low']) for c in candles]
        closes = [float(c['close']) for c in candles]
        
        tenkan = []
        kijun = []
        
        for i in range(len(candles)):
            # Tenkan (9 periods)
            if i >= 8:
                tenkan.append((max(highs[i-8:i+1]) + min(lows[i-8:i+1])) / 2.0)
            else:
                tenkan.append(None)
                
            # Kijun (26 periods)
            if i >= 25:
                kijun.append((max(highs[i-25:i+1]) + min(lows[i-25:i+1])) / 2.0)
            else:
                kijun.append(None)

        span_a = []
        span_b = []
        for i in range(len(candles)):
            # Plotted 26 periods ahead, meaning current cloud is based on calculations 26 periods ago
            # Span A
            if i >= 26 and tenkan[i-26] is not None and kijun[i-26] is not None:
                span_a.append((tenkan[i-26] + kijun[i-26]) / 2.0)
            else:
                span_a.append(None)
                
            # Span B
            if i >= 77:
                sb_highs = highs[i-77:i-25]
                sb_lows = lows[i-77:i-25]
                span_b.append((max(sb_highs) + min(sb_lows)) / 2.0)
            else:
                span_b.append(None)

        return {
            'close': closes[-1],
            'prev_close': closes[-2] if len(closes) >= 2 else closes[-1],
            'prev2_close': closes[-3] if len(closes) >= 3 else (closes[-2] if len(closes) >= 2 else closes[-1]),
            'tenkan': tenkan[-1],
            'kijun': kijun[-1],
            'span_a': span_a[-1],
            'span_b': span_b[-1],
            'prev_tenkan': tenkan[-2] if len(tenkan) >= 2 else None,
            'prev_kijun': kijun[-2] if len(kijun) >= 2 else None,
            'prev_span_a': span_a[-2] if len(span_a) >= 2 else None,
            'prev_span_b': span_b[-2] if len(span_b) >= 2 else None,
            'prev2_tenkan': tenkan[-3] if len(tenkan) >= 3 else None,
            'prev2_kijun': kijun[-3] if len(kijun) >= 3 else None,
            'prev2_span_a': span_a[-3] if len(span_a) >= 3 else None,
            'prev2_span_b': span_b[-3] if len(span_b) >= 3 else None,
            'prev_time': candles[-2].get('time') if len(candles) >= 2 else None
        }

    def get_trend_bias(self, ichi):
        if not ichi or ichi['prev_span_a'] is None or ichi['prev_span_b'] is None:
            return "NEUTRAL"
        close = ichi['prev_close']
        top_cloud = max(ichi['prev_span_a'], ichi['prev_span_b'])
        bottom_cloud = min(ichi['prev_span_a'], ichi['prev_span_b'])
        
        if close > top_cloud:
            return "BULLISH"
        elif close < bottom_cloud:
            return "BEARISH"
        else:
            return "NEUTRAL"

    def get_all_timeframe_data(self):
        # Fetch 4H candles to compute trend bias
        candles_4h = self.client.get_history(resolution="4h", limit=80)
        ichi_4h = self.calculate_ichimoku(candles_4h)
        
        # Fetch 1H candles to compute trend bias
        candles_1h = self.client.get_history(resolution="1h", limit=80)
        ichi_1h = self.calculate_ichimoku(candles_1h)
        
        # Fetch 3m candles (or whatever configuration timeframe) for signal triggers
        candles_3m = self.client.get_history(resolution=config.TIMEFRAME, limit=80)
        ichi_3m = self.calculate_ichimoku(candles_3m)
        
        tfs = {
            '4h': ichi_4h,
            '1h': ichi_1h,
            '3m': ichi_3m
        }
        self.last_timeframe_data = tfs
        return tfs

    def evaluate_signal(self, timeframes_data):
        if not timeframes_data: return None
        ichi_4h = timeframes_data['4h']
        ichi_1h = timeframes_data['1h']
        ichi_3m = timeframes_data['3m']
        
        if not ichi_4h or not ichi_1h or not ichi_3m:
            return None
            
        bias_4h = self.get_trend_bias(ichi_4h)
        bias_1h = self.get_trend_bias(ichi_1h)
        
        # If 4H and 1H trends are NOT aligned, do not trade!
        if bias_4h == "BULLISH" and bias_1h == "BULLISH":
            # Check bullish entry on 3m chart (using closed candles: index -2 vs -3)
            p_close = ichi_3m['prev_close']
            p2_close = ichi_3m['prev2_close']
            
            p_span_a = ichi_3m['prev_span_a']
            p_span_b = ichi_3m['prev_span_b']
            p2_span_a = ichi_3m['prev2_span_a']
            p2_span_b = ichi_3m['prev2_span_b']
            
            if all(v is not None for v in [p_span_a, p_span_b, p2_span_a, p2_span_b]):
                top_cloud = max(p_span_a, p_span_b)
                prev_top_cloud = max(p2_span_a, p2_span_b)
                
                # Cloud breakout
                if p2_close <= prev_top_cloud and p_close > top_cloud:
                    return "BUY_CALL"
                    
                # Tenkan-Kijun crossover
                t_now, k_now = ichi_3m['prev_tenkan'], ichi_3m['prev_kijun']
                t_prev, k_prev = ichi_3m['prev2_tenkan'], ichi_3m['prev2_kijun']
                if all(v is not None for v in [t_now, k_now, t_prev, k_prev]):
                    if t_prev <= k_prev and t_now > k_now and p_close > top_cloud:
                        return "BUY_CALL"
                        
        elif bias_4h == "BEARISH" and bias_1h == "BEARISH":
            # Check bearish entry on 3m chart (using closed candles: index -2 vs -3)
            p_close = ichi_3m['prev_close']
            p2_close = ichi_3m['prev2_close']
            
            p_span_a = ichi_3m['prev_span_a']
            p_span_b = ichi_3m['prev_span_b']
            p2_span_a = ichi_3m['prev2_span_a']
            p2_span_b = ichi_3m['prev2_span_b']
            
            if all(v is not None for v in [p_span_a, p_span_b, p2_span_a, p2_span_b]):
                bottom_cloud = min(p_span_a, p_span_b)
                prev_bottom_cloud = min(p2_span_a, p2_span_b)
                
                # Cloud breakout
                if p2_close >= prev_bottom_cloud and p_close < bottom_cloud:
                    return "BUY_PUT"
                    
                # Tenkan-Kijun crossover
                t_now, k_now = ichi_3m['prev_tenkan'], ichi_3m['prev_kijun']
                t_prev, k_prev = ichi_3m['prev2_tenkan'], ichi_3m['prev2_kijun']
                if all(v is not None for v in [t_now, k_now, t_prev, k_prev]):
                    if t_prev >= k_prev and t_now < k_now and p_close < bottom_cloud:
                        return "BUY_PUT"

        return None


    def execute_entry(self, signal, btc_price, candle_time):
        self.query_trades_today_count()
        if self.trades_taken_today >= config.MAX_TRADES_PER_DAY:
            self.add_log(f"Entry signal {signal} ignored: Daily quota reached ({self.trades_taken_today}/{config.MAX_TRADES_PER_DAY})")
            return

        now_str = datetime.now(IST).strftime("%H:%M")
        if not (config.ENTRY_WINDOW_START <= now_str <= config.ENTRY_WINDOW_END):
            self.add_log(f"Entry signal ignored: Outside allowed entry window {config.ENTRY_WINDOW_START}-{config.ENTRY_WINDOW_END} ({now_str})")
            return

        expiry_label = self.client.get_nearest_expiration()
        if not expiry_label:
            self.add_log("Error getting nearest expiration date.")
            return

        self.add_log(f"Processing Entry Trigger: {signal}...")
        insts = self.client.get_instruments(expiry_label)
        if not insts:
            self.add_log("Error: Fetching options chain returned empty.")
            return

        major_symbol = None
        hedge_symbol = None
        
        calls = [i for i in insts if i['symbol'].startswith('C-')]
        puts = [i for i in insts if i['symbol'].startswith('P-')]
        
        if signal == "BUY_CALL":
            # Major leg: ATM Call (closest to btc_price)
            if not calls: return
            atm_call = min(calls, key=lambda x: abs(float(x['strike_price']) - btc_price))
            major_symbol = atm_call['symbol']
            major_strike = float(atm_call['strike_price'])
            
            # Hedge leg: OTM Put (closest to ATM strike - HEDGE_STRIKE_OFFSET)
            if not puts: return
            target_put_strike = major_strike - config.HEDGE_STRIKE_OFFSET
            hedge_put = min(puts, key=lambda x: abs(float(x['strike_price']) - target_put_strike))
            hedge_symbol = hedge_put['symbol']
            direction = "CALL"
        else:
            # Major leg: ATM Put (closest to btc_price)
            if not puts: return
            atm_put = min(puts, key=lambda x: abs(float(x['strike_price']) - btc_price))
            major_symbol = atm_put['symbol']
            major_strike = float(atm_put['strike_price'])
            
            # Hedge leg: OTM Call (closest to ATM strike + HEDGE_STRIKE_OFFSET)
            if not calls: return
            target_call_strike = major_strike + config.HEDGE_STRIKE_OFFSET
            hedge_call = min(calls, key=lambda x: abs(float(x['strike_price']) - target_call_strike))
            hedge_symbol = hedge_call['symbol']
            direction = "PUT"
 
        # Check market feed for mark prices
        tickers = self.client.get_all_tickers()
        if major_symbol not in tickers or hedge_symbol not in tickers:
            self.add_log(f"Error: Option tickers not ready in feed ({major_symbol} / {hedge_symbol}).")
            return

        # Experienced trader safety checks: bid-ask spread and volume/OI liquidity validation
        major_tick = tickers[major_symbol]
        hedge_tick = tickers[hedge_symbol]
        
        # 1. Spread Check
        # For major leg
        major_bid = major_tick['best_bid']
        major_ask = major_tick['best_ask']
        major_spread_pct = 999.0
        if major_bid > 0:
            major_spread_pct = ((major_ask - major_bid) / major_bid) * 100.0
            
        # For hedge leg
        hedge_bid = hedge_tick['best_bid']
        hedge_ask = hedge_tick['best_ask']
        hedge_spread_pct = 999.0
        if hedge_bid > 0:
            hedge_spread_pct = ((hedge_ask - hedge_bid) / hedge_bid) * 100.0

        max_allowed_spread = getattr(config, 'MAX_SPREAD_PCT', 12.0)
        if major_spread_pct > max_allowed_spread:
            self.add_log(f"Entry ignored (Slippage Safety): Major option {major_symbol} spread too wide ({major_spread_pct:.1f}% > {max_allowed_spread}%)")
            return
        if hedge_spread_pct > max_allowed_spread:
            self.add_log(f"Entry ignored (Slippage Safety): Hedge option {hedge_symbol} spread too wide ({hedge_spread_pct:.1f}% > {max_allowed_spread}%)")
            return

        # 2. Liquidity (Open Interest) check
        min_allowed_oi = getattr(config, 'MIN_LEG_OI', 5.0)
        if major_tick['oi'] < min_allowed_oi:
            self.add_log(f"Entry ignored (Liquidity Safety): Major option {major_symbol} Open Interest too low ({major_tick['oi']} < {min_allowed_oi} OI)")
            return
        if hedge_tick['oi'] < min_allowed_oi:
            self.add_log(f"Entry ignored (Liquidity Safety): Hedge option {hedge_symbol} Open Interest too low ({hedge_tick['oi']} < {min_allowed_oi} OI)")
            return

        major_prem = tickers[major_symbol]['mark_price']
        hedge_prem = tickers[hedge_symbol]['mark_price']

        # Pre-trade Greeks and payoff analysis logic
        qty_major = config.MAJOR_LEG_QUANTITY * 0.001
        qty_hedge = config.HEDGE_LEG_QUANTITY * 0.001
        
        net_delta = (major_tick['delta'] * qty_major) + (hedge_tick['delta'] * qty_hedge)
        net_theta = (major_tick['theta'] * qty_major) + (hedge_tick['theta'] * qty_hedge)
        net_gamma = (major_tick['gamma'] * qty_major) + (hedge_tick['gamma'] * qty_hedge)
        
        capital_req = (major_prem * qty_major) + (hedge_prem * qty_hedge)
        
        self.add_log("\n" + "=" * 65)
        self.add_log("       PRE-TRADE ICHIMOKU SCALPER PAYOFF & GREEKS ANALYSIS       ")
        self.add_log("=" * 65)
        self.add_log(f" BUY_ATM   major | {major_symbol:<20} | Prem: ${major_prem:>5.1f} | Delta: {major_tick['delta']:>+5.2f} | OI: {major_tick['oi']:>4.0f}")
        self.add_log(f" BUY_HEDGE hedge | {hedge_symbol:<20} | Prem: ${hedge_prem:>5.1f} | Delta: {hedge_tick['delta']:>+5.2f} | OI: {hedge_tick['oi']:>4.0f}")
        self.add_log("-" * 65)
        self.add_log(f" Total Premium Paid (Max Risk)     : ${capital_req:.2f} USD")
        self.add_log(f" Capital Required                 : ${capital_req:.2f} USD")
        self.add_log(f" Combined Position Delta          : {net_delta:>+7.5f}")
        self.add_log(f" Combined Position Theta          : {net_theta:>+7.5f} USD/day")
        self.add_log(f" Combined Position Gamma          : {net_gamma:>+7.5f}")
        self.add_log(f" Payoff Profile                   : Asymmetric Directional ({direction})")
        self.add_log("=" * 65 + "\n")

        self.add_log(f"Placing market BUY order for Major Leg ({config.MAJOR_LEG_QUANTITY} of {major_symbol}) and Hedge Leg ({config.HEDGE_LEG_QUANTITY} of {hedge_symbol})...")
        
        # Place major leg order
        major_res = self.client.place_order(major_symbol, "buy", size=config.MAJOR_LEG_QUANTITY)
        if not major_res or 'result' not in major_res:
            self.add_log(f"[!] MAJOR LEG ENTRY FAILED: {major_res}. Aborting entry.")
            return

        # Place hedge leg order
        hedge_res = self.client.place_order(hedge_symbol, "buy", size=config.HEDGE_LEG_QUANTITY)
        if not hedge_res or 'result' not in hedge_res:
            self.add_log(f"[!] HEDGE LEG ENTRY FAILED: {hedge_res}. Attempting retry in 1s...")
            time.sleep(1.0)
            hedge_res = self.client.place_order(hedge_symbol, "buy", size=config.HEDGE_LEG_QUANTITY)
            
            if not hedge_res or 'result' not in hedge_res:
                self.add_log(f"[!] HEDGE LEG ENTRY FAILED AGAIN. Rolling back Major Leg...")
                rollback_res = self.client.place_order(major_symbol, "sell", size=config.MAJOR_LEG_QUANTITY)
                self.add_log(f"Rollback status: {rollback_res}")
                return

        # Build position state
        major_leg = Leg(major_symbol, "buy", major_prem, config.MAJOR_LEG_QUANTITY, "major")
        hedge_leg = Leg(hedge_symbol, "buy", hedge_prem, config.HEDGE_LEG_QUANTITY, "hedge")
        
        legs_dict = {
            'major': major_leg,
            'hedge': hedge_leg
        }
        
        self.active_position = IchimokuPosition(legs_dict, btc_price, direction)
        self.last_entered_candle_time = candle_time
        self.save_state()
        self.add_log(f"SUCCESS: Opened 2-Leg Scalp position: {major_symbol} (${major_prem:.2f}) & {hedge_symbol} (${hedge_prem:.2f})")

    def execute_exit(self, reason, current_spot, tickers_dict):
        if not self.active_position: return
        pos = self.active_position
        self.add_log(f"Triggering Exit: {reason} | Closing positions...")

        pnl_record_legs = {}
        for role, leg in pos.legs.items():
            if leg.status == "OPEN":
                self.add_log(f"Placing market SELL order to close {role} ({leg.symbol})...")
                res = self.client.place_order(leg.symbol, "sell", size=leg.size)
                
                # Fetch actual price from tickers if available
                exit_prem = tickers_dict.get(leg.symbol, {}).get('mark_price', leg.current_premium)
                if not res or 'result' not in res:
                    self.add_log(f"[!] FAILED TO CLOSE {role} ({leg.symbol}): {res}. Will retry on next loop.")
                else:
                    leg.status = "CLOSED"
                    leg.current_premium = exit_prem
                    pnl_record_legs[role] = {
                        'symbol': leg.symbol,
                        'entry_premium': leg.entry_premium,
                        'exit_premium': exit_prem,
                        'size': leg.size
                    }

        # If any leg failed to close, we keep active_position open to retry
        any_open = any(l.status == "OPEN" for l in pos.legs.values())
        if any_open:
            self.save_state()
            return

        # Calculate final P&L
        total_pnl_usd = 0.0
        total_fees_usd = 0.0
        legs_pnl_summary = {}

        for role, pinfo in pnl_record_legs.items():
            leg_pnl_points = pinfo['exit_premium'] - pinfo['entry_premium']
            leg_pnl_usd = leg_pnl_points * 0.001 * pinfo['size']
            total_pnl_usd += leg_pnl_usd
            
            entry_fee = min(0.0001 * pos.entry_spot * 0.001 * pinfo['size'], 0.035 * pinfo['entry_premium'] * 0.001 * pinfo['size'])
            exit_fee = min(0.0001 * current_spot * 0.001 * pinfo['size'], 0.035 * pinfo['exit_premium'] * 0.001 * pinfo['size'])
            leg_fees = entry_fee + exit_fee
            total_fees_usd += leg_fees
            
            legs_pnl_summary[role] = {
                'symbol': pinfo['symbol'],
                'entry_premium': pinfo['entry_premium'],
                'exit_premium': pinfo['exit_premium'],
                'pnl_usd': leg_pnl_usd,
                'fees_usd': leg_fees
            }

        record = {
            'entry_time': pos.entry_time.strftime("%Y-%m-%d %H:%M:%S") if isinstance(pos.entry_time, datetime) else str(pos.entry_time),
            'exit_time': datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
            'direction': pos.direction,
            'entry_spot': pos.entry_spot,
            'exit_spot': current_spot,
            'legs': legs_pnl_summary,
            'total_pnl_usd': total_pnl_usd,
            'total_fees_usd': total_fees_usd,
            'net_pnl_usd': total_pnl_usd - total_fees_usd,
            'exit_reason': reason
        }

        self.trade_history.append(record)
        self.active_position = None
        self.save_state()
        
        self.query_trades_today_count()
        self.add_log(f"SUCCESSFUL EXIT: Closed scalp for Net PnL: ${record['net_pnl_usd']:+.2f} (PNL: ${total_pnl_usd:.2f}, Fees: ${total_fees_usd:.2f}) | Reason: {reason}")

    def run_one_loop(self):
        try:
            btc_price = self.client.get_btc_price()
            if not btc_price: return
            
            timeframes = self.get_all_timeframe_data()
            if not timeframes or not timeframes['3m']: return
            
            # 1. Update active position metrics and check exits
            if self.active_position:
                pos = self.active_position
                tickers = self.client.get_all_tickers()
                
                # Update current premiums for both options
                for role, leg in pos.legs.items():
                    if leg.status == "OPEN" and leg.symbol in tickers:
                        leg.current_premium = tickers[leg.symbol]['mark_price']
                
                # Compute total cumulative USD P&L
                total_pnl_usd = sum((leg.current_premium - leg.entry_premium) * 0.001 * leg.size for leg in pos.legs.values() if leg.status == "OPEN")
                
                # Compute elapsed holding time in minutes
                elapsed_minutes = 0.0
                if isinstance(pos.entry_time, datetime):
                    elapsed_minutes = (datetime.now(IST) - pos.entry_time).total_seconds() / 60.0

                # Exit criteria tests
                now_str = datetime.now(IST).strftime("%H:%M")
                if total_pnl_usd >= config.TAKE_PROFIT_USD:
                    self.execute_exit("take_profit", btc_price, tickers)
                elif total_pnl_usd <= -config.STOP_LOSS_USD:
                    self.execute_exit("stop_loss", btc_price, tickers)
                elif elapsed_minutes >= getattr(config, 'MAX_HOLD_DURATION_MINUTES', 30):
                    self.execute_exit("max_holding_time", btc_price, tickers)
                elif now_str >= config.FORCE_CLOSE_TIME:
                    self.execute_exit("force_close_eod", btc_price, tickers)
                else:
                    # Kijun line cross exit is disabled to prevent fee drag / false exits on 3m chart wiggles.
                    # We rely instead on the Take Profit, Stop Loss, and Max Hold Duration gates.
                    pass

            # 2. Check entry breakouts if no position is open
            else:
                ichi_3m = timeframes['3m']
                prev_time = ichi_3m.get('prev_time')
                if prev_time and prev_time == self.last_entered_candle_time:
                    # Already processed this closed candle, skip to avoid double entries
                    return
                    
                signal = self.evaluate_signal(timeframes)
                if signal:
                    self.execute_entry(signal, btc_price, prev_time)
                    
        except Exception as e:
            self.add_log(f"System Error in main bot scan check: {e}")


def make_layout():
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body", ratio=1),
        Layout(name="footer", size=10)
    )
    layout["body"].split_row(
        Layout(name="left", ratio=1),
        Layout(name="right", ratio=1)
    )
    return layout


def build_views(bot, layout):
    # Header
    now_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    layout["header"].update(Panel(
        f"[bold cyan]▲ ICHIMOKU CLOUD OPTIONS SCALPER BOT ▲[/bold cyan]   |   IST Time: {now_str}   |   Mode: [green]Active Live[/green]",
        style="white"
    ))

    # Left Column: Market Signals & Indicators
    tfs = bot.last_timeframe_data or {}
    ichi_4h = tfs.get('4h')
    ichi_1h = tfs.get('1h')
    ichi_3m = tfs.get('3m')
    
    btc_price = bot.client.get_btc_price() or 0.0

    indicators_table = Table(title="ICHIMOKU CLOUD MULTI-TIMEFRAME INDICATORS", expand=True)
    indicators_table.add_column("Indicator Line", style="cyan")
    indicators_table.add_column("4H Chart", style="magenta")
    indicators_table.add_column("1H Chart", style="green")
    indicators_table.add_column("3m Chart (Entry)", style="yellow")

    bias_4h = bot.get_trend_bias(ichi_4h) if ichi_4h else "NEUTRAL"
    bias_1h = bot.get_trend_bias(ichi_1h) if ichi_1h else "NEUTRAL"
    bias_3m = bot.get_trend_bias(ichi_3m) if ichi_3m else "NEUTRAL"

    def fmt_val(ichi, name):
        if not ichi or name not in ichi or ichi[name] is None: return "-"
        return f"${ichi[name]:,.2f}"

    indicators_table.add_row("BTCUSD Spot", f"${btc_price:,.2f}", f"${btc_price:,.2f}", f"${btc_price:,.2f}")
    indicators_table.add_row("Tenkan-Sen (9p)", fmt_val(ichi_4h, 'tenkan'), fmt_val(ichi_1h, 'tenkan'), fmt_val(ichi_3m, 'tenkan'))
    indicators_table.add_row("Kijun-Sen (26p)", fmt_val(ichi_4h, 'kijun'), fmt_val(ichi_1h, 'kijun'), fmt_val(ichi_3m, 'kijun'))
    indicators_table.add_row("Senkou Span A", fmt_val(ichi_4h, 'span_a'), fmt_val(ichi_1h, 'span_a'), fmt_val(ichi_3m, 'span_a'))
    indicators_table.add_row("Senkou Span B", fmt_val(ichi_4h, 'span_b'), fmt_val(ichi_1h, 'span_b'), fmt_val(ichi_3m, 'span_b'))
    
    def fmt_bias(bias):
        if bias == "BULLISH": return "[bold green]BULLISH[/]"
        if bias == "BEARISH": return "[bold red]BEARISH[/]"
        return "[bold yellow]NEUTRAL[/]"

    indicators_table.add_row(
        "Cloud Bias",
        fmt_bias(bias_4h),
        fmt_bias(bias_1h),
        fmt_bias(bias_3m)
    )

    layout["left"].update(Panel(indicators_table, style="blue"))

    # Right Column: Active Scalps & Stats
    right_column = Layout()
    right_column.split_column(
        Layout(name="active_pos", ratio=1),
        Layout(name="stats_box", ratio=1)
    )
    
    # Active Pos Panel
    pos = bot.active_position
    pos_table = Table(title="ACTIVE 2-LEG HEDGED POSITION", expand=True)
    pos_table.add_column("Leg Type (Role)", style="cyan")
    pos_table.add_column("Symbol", style="magenta")
    pos_table.add_column("Size", style="green")
    pos_table.add_column("Entry px", style="blue")
    pos_table.add_column("Current px", style="yellow")
    pos_table.add_column("Leg P&L USD", style="white")

    if pos:
        total_pnl = 0.0
        for role, leg in pos.legs.items():
            pnl_points = leg.current_premium - leg.entry_premium
            pnl_usd = pnl_points * 0.001 * leg.size
            total_pnl += pnl_usd
            color = "[green]" if pnl_usd >= 0 else "[red]"
            pos_table.add_row(
                f"{role.upper()} ({leg.side.upper()})",
                leg.symbol,
                str(leg.size),
                f"${leg.entry_premium:.3f}",
                f"${leg.current_premium:.3f}",
                f"{color}${pnl_usd:+.2f}[/]"
            )
        pos_table.add_section()
        color_tot = "[bold green]" if total_pnl >= 0 else "[bold red]"
        pos_table.add_row("COMBINED TOTAL", "", "", "", "", f"{color_tot}${total_pnl:+.2f} USD[/]")
    else:
        pos_table.add_row("No active scalp positions open", "", "", "", "", "")
        
    right_column["active_pos"].update(Panel(pos_table, style="magenta"))

    # Stats Panel
    bot.query_trades_today_count()
    wins = [x for x in bot.trade_history if x.get('net_pnl_usd', 0) > 0]
    total_trades = len(bot.trade_history)
    win_rate = (len(wins) / total_trades) * 100.0 if total_trades > 0 else 0.0
    net_usd = sum(t.get('net_pnl_usd', 0) for t in bot.trade_history)
    
    stats_table = Table(title="TRADING PERFORMANCE & LIMITS", expand=True)
    stats_table.add_column("Metric", style="cyan")
    stats_table.add_column("Value", style="magenta")
    stats_table.add_row("Trades Taken Today", f"{bot.trades_taken_today} / {config.MAX_TRADES_PER_DAY}")
    stats_table.add_row("Cumulative Trades (All Time)", str(total_trades))
    stats_table.add_row("Win Rate", f"{win_rate:.1f}%")
    stats_table.add_row("Net Profit (After Fees)", f"[green]${net_usd:.2f}[/]" if net_usd >= 0 else f"[red]${net_usd:.2f}[/]")
    stats_table.add_row("Take Profit Limit", f"${config.TAKE_PROFIT_USD:.2f} USD")
    stats_table.add_row("Stop Loss Cap", f"${config.STOP_LOSS_USD:.2f} USD")

    right_column["stats_box"].update(Panel(stats_table, style="green"))
    layout["right"].update(right_column)


    # Footer (Logs)
    logs_str = "\n".join(bot.log_messages[-8:])
    layout["footer"].update(Panel(logs_str, title="REALTIME ACTIVITY LOGS", style="white"))


# Main Thread Runner
if __name__ == "__main__":
    bot = IchimokuScalpBot()
    bot.add_log("Ichimoku Scalper Bot initialized successfully.")
    
    layout = make_layout()
    
    loop_count = 0
    with Live(layout, refresh_per_second=2, screen=True) as live:
        while True:
            try:
                bot.run_one_loop()
                build_views(bot, layout)
                time.sleep(5)
            except KeyboardInterrupt:
                break
            except Exception as e:
                bot.add_log(f"Loop error: {e}")
                time.sleep(5)
