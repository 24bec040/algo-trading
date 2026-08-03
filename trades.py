import time
import json
import os
import collections
import math
from datetime import datetime, timezone, timedelta
from config import (DRY_RUN, TRADE_QUANTITY, PROFIT_MIN_PCT, PROFIT_MAX_PCT,
                    STOP_LOSS_PCT, RISK_FREE_RATE, HALF_PROFIT_PCT, HALF_STOP_PCT)

IST = timezone(timedelta(hours=5, minutes=30))

class Leg:
    def __init__(self, symbol, side, entry_premium):
        self.symbol = symbol
        self.side = side
        self.entry_premium = entry_premium
        self.current_premium = entry_premium
        self.status = "OPEN"
        self.pnl = 0.0
        try:
            self.strike = float(symbol.split('-')[2])
        except:
            self.strike = 0.0

    def update(self, current_premium):
        if self.status != "OPEN": return
        self.current_premium = current_premium
        if self.side == "sell":
            self.pnl = self.entry_premium - self.current_premium
        else:
            self.pnl = self.current_premium - self.entry_premium

    def get_pnl_pct(self):
        if self.entry_premium == 0: return 0
        return (self.pnl / self.entry_premium) * 100

class IronCondor:
    def __init__(self, legs_dict, entry_spot, entry_iv):
        self.legs = legs_dict
        IST = timezone(timedelta(hours=5, minutes=30))
        self.entry_time = datetime.now(IST)
        self.status = "OPEN"
        self.entry_spot = entry_spot
        self.entry_iv = entry_iv
        self.leg_exit_triggered = False
        self.exit_reason = None
        self.fees_usd = 0.0
        self.initial_premium = 0.0
        self.breakeven_reached = False

    @property
    def total_pnl(self):
        return sum(leg.pnl for leg in self.legs.values())

class TradeManager:
    def __init__(self, client):
        self.client = client
        self.active_position = None
        self.trade_history = []
        self.log_func = None
        self.load_trade_history()
        self.call_adverse_history = collections.deque([False, False], maxlen=2)
        self.put_adverse_history = collections.deque([False, False], maxlen=2)
        self.call_adverse_in_current_bar = False
        self.put_adverse_in_current_bar = False

    def _log(self, message):
        if self.log_func:
            self.log_func(message)
        print(message)

    def load_trade_history(self):
        dir_path = os.path.dirname(os.path.abspath(__file__))
        filepath = os.path.join(dir_path, "completed_trades.json")
        self.trade_history = []
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    self.trade_history = json.load(f)
            except Exception as e:
                self._log(f"Error loading trade history: {e}")

    def save_trade_history(self):
        dir_path = os.path.dirname(os.path.abspath(__file__))
        filepath = os.path.join(dir_path, "completed_trades.json")
        try:
            with open(filepath, 'w') as f:
                json.dump(self.trade_history, f, indent=4)
        except Exception as e:
            self._log(f"Error saving trade history: {e}")

    def enter_iron_condor(self, symbols_dict, tickers_dict, btc_price, entry_iv):
        # 1. Pre-trade Payoff & Greeks calculation and logging
        sells = sum(tickers_dict[symbol]['mark_price'] for role, symbol in symbols_dict.items() if 'sell' in role)
        buys = sum(tickers_dict[symbol]['mark_price'] for role, symbol in symbols_dict.items() if 'buy' in role)
        net_credit = sells - buys
        
        net_delta = 0.0
        net_theta = 0.0
        net_gamma = 0.0
        
        for role, symbol in symbols_dict.items():
            t = tickers_dict[symbol]
            multiplier = -1.0 if 'sell' in role else 1.0
            qty_mult = TRADE_QUANTITY * 0.001
            net_delta += multiplier * t['delta'] * qty_mult
            net_theta += multiplier * t['theta'] * qty_mult
            net_gamma += multiplier * t['gamma'] * qty_mult

        def get_strike(sym):
            try: return float(sym.split('-')[2])
            except: return 0.0
            
        call_width = abs(get_strike(symbols_dict['buy_call']) - get_strike(symbols_dict['sell_call']))
        put_width = abs(get_strike(symbols_dict['sell_put']) - get_strike(symbols_dict['buy_put']))
        max_spread_width = max(call_width, put_width)
        
        est_margin = max_spread_width * 0.001 * TRADE_QUANTITY
        max_loss = est_margin - (net_credit * 0.001 * TRADE_QUANTITY)
        max_profit = net_credit * 0.001 * TRADE_QUANTITY
        
        self._log("\n" + "=" * 65)
        self._log("       PRE-TRADE IRON CONDOR PAYOFF & GREEKS ANALYSIS       ")
        self._log("=" * 65)
        for role, symbol in symbols_dict.items():
            t = tickers_dict[symbol]
            side = 'SELL' if 'sell' in role else 'BUY'
            self._log(f" {side:<4} {role:<9} | {symbol:<18} | Prem: ${t['mark_price']:>5.1f} | Delta: {t['delta']:>+5.2f} | OI: {t['oi']:>4.0f}")
        self._log("-" * 65)
        self._log(f" Net Premium Collected             : ${net_credit:.2f} points (${max_profit:.2f} USD)")
        self._log(f" Estimated Margin / Capital Req     : ${est_margin:.2f} USD")
        self._log(f" Max Risk (Max Loss)               : ${max_loss:.2f} USD")
        self._log(f" Combined Position Delta            : {net_delta:>+7.5f}")
        self._log(f" Combined Position Theta            : {net_theta:>+7.5f} USD/day")
        self._log(f" Combined Position Gamma            : {net_gamma:>+7.5f}")
        self._log(f" Probability of Profit (Approx)    : ~80-85% (OTM Wings)")
        self._log("=" * 65 + "\n")

        legs = {}
        for role, symbol in symbols_dict.items():
            side = 'sell' if 'sell' in role else 'buy'
            prem = tickers_dict[symbol]['mark_price']
            if not DRY_RUN:
                res = self.client.place_order(symbol, side, size=TRADE_QUANTITY)
                if not res or 'result' not in res:
                    err_msg = res if res else 'No Response'
                    self._log(f"[!] FAILED: {symbol} | Response: {err_msg}")
                    continue
            legs[role] = Leg(symbol, side, prem)

        if len(legs) < 4:
            self._log(f"[!] FAILED: Iron Condor entry partial fill. Only {len(legs)}/4 legs succeeded. Rolling back/exiting placed legs...")
            if not DRY_RUN:
                for role, leg in legs.items():
                    side = 'buy' if leg.side == 'sell' else 'sell'
                    self.client.place_order(leg.symbol, side, size=TRADE_QUANTITY)
            return

        self.active_position = IronCondor(legs, btc_price, entry_iv)
        sells = sum(l.entry_premium for l in legs.values() if l.side == 'sell')
        buys = sum(l.entry_premium for l in legs.values() if l.side == 'buy')
        self.active_position.initial_premium = sells - buys
        total_entry_fee = 0.0
        for leg in legs.values():
            uncapped = 0.0001 * btc_price * (TRADE_QUANTITY * 0.001)
            capped = 0.035 * leg.entry_premium * (TRADE_QUANTITY * 0.001)
            total_entry_fee += min(uncapped, capped)
        self.active_position.fees_usd = total_entry_fee
        self._log(f"[*] ENTERED IRON CONDOR at Spot {btc_price} | IV {entry_iv * 100:.1f}%: {list(symbols_dict.values())}")

    def check_and_manage(self, tickers_dict, current_spot, current_iv):
        if not self.active_position: return
        pos = self.active_position

        for role, leg in pos.legs.items():
            if leg.status == "OPEN" and leg.symbol in tickers_dict:
                leg.update(tickers_dict[leg.symbol]['mark_price'])

        now_ist = datetime.now(IST)
        expiry_today = now_ist.replace(hour=15, minute=0, second=0, microsecond=0)
        remaining_hours = max(0.0, (expiry_today - now_ist).total_seconds() / 3600.0)
        t_years = remaining_hours / 8760.0
        current_time_str = now_ist.strftime("%H:%M")

        from config import TEST_ENTRY, FORCE_CLOSE_TIME
        if current_time_str >= FORCE_CLOSE_TIME and not TEST_ENTRY:
            self._log(f"[!] EOD FORCE CLOSE TRIGGERED ({FORCE_CLOSE_TIME} IST)")
            self.exit_all_remaining("force_close_eod", current_spot)
            return

        is_call_side_open = (
            (pos.legs.get('sell_call') and pos.legs['sell_call'].status == "OPEN") or 
            (pos.legs.get('buy_call') and pos.legs['buy_call'].status == "OPEN")
        )
        is_put_side_open = (
            (pos.legs.get('sell_put') and pos.legs['sell_put'].status == "OPEN") or 
            (pos.legs.get('buy_put') and pos.legs['buy_put'].status == "OPEN")
        )

        if is_call_side_open and is_put_side_open:
            if all(k in pos.legs for k in ['sell_call', 'sell_put', 'buy_call', 'buy_put']):
                sells_init = pos.legs['sell_call'].entry_premium + pos.legs['sell_put'].entry_premium
                buys_init = pos.legs['buy_call'].entry_premium + pos.legs['buy_put'].entry_premium
                initial_net_prem = sells_init - buys_init

                sells_curr = pos.legs['sell_call'].current_premium + pos.legs['sell_put'].current_premium
                buys_curr = pos.legs['buy_call'].current_premium + pos.legs['buy_put'].current_premium
                current_net_prem = sells_curr - buys_curr

                melt_fraction = 1.0 - (current_net_prem / initial_net_prem) if initial_net_prem > 0 else 0.0
                loss_fraction = (current_net_prem - initial_net_prem) / initial_net_prem if initial_net_prem > 0 else 0.0

                if loss_fraction >= STOP_LOSS_PCT:
                    self._log(f"[!] STOP LOSS MET (Loss: {loss_fraction * 100:.1f}%)")
                    self.exit_all_remaining("stop_loss", current_spot)
                    return

                if getattr(pos, 'breakeven_reached', False) and melt_fraction <= 0.02:
                    self._log(f"[!] BREAK-EVEN STOP MET (Melt fraction dropped back to {melt_fraction * 100:.1f}%)")
                    self.exit_all_remaining("cost_to_cost", current_spot)
                    return

                if melt_fraction >= PROFIT_MAX_PCT:
                    self._log(f"[!] TAKE PROFIT MAX MET (Melt: {melt_fraction * 100:.1f}%)")
                    self.exit_all_remaining("profit_max", current_spot)
                    return

                if melt_fraction >= PROFIT_MIN_PCT:
                    spot_moved_pct = abs(current_spot - pos.entry_spot) / pos.entry_spot
                    time_warning = current_time_str >= "13:00"
                    iv_increased = current_iv >= (pos.entry_iv + 0.02)
                    spot_warning = spot_moved_pct > 0.004
                    if time_warning or iv_increased or spot_warning:
                        self._log(f"[!] TAKE PROFIT MIN MET (Melt: {melt_fraction * 100:.1f}%)")
                        self.exit_all_remaining("profit_min", current_spot)
                        return
                else:
                    if not getattr(pos, 'breakeven_reached', False) and melt_fraction >= 0.15:
                        pos.breakeven_reached = True
                        self._log(f"[✔] BREAK-EVEN PROTECT: Melt reached {melt_fraction * 100:.1f}%. Cost-to-cost exit activated.")

            # Leg Exit logic
            candles = self.client.get_history(resolution="5m", limit=25)
            if candles and len(candles) >= 24:
                current_bar_volume = candles[-1]['volume']
                recent_2h_avg_volume = sum(c['volume'] for c in candles[:-1]) / len(candles[:-1])
                volume_gate_ok = current_bar_volume > recent_2h_avg_volume
            else:
                volume_gate_ok = False

            current_bar_index = int(time.time() // 300)
            if not hasattr(self, 'last_bar_index') or self.last_bar_index != current_bar_index:
                if hasattr(self, 'last_bar_index'):
                    self.call_adverse_history.append(self.call_adverse_in_current_bar)
                    self.put_adverse_history.append(self.put_adverse_in_current_bar)
                self.last_bar_index = current_bar_index
                self.call_adverse_in_current_bar = False
                self.put_adverse_in_current_bar = False

            # Call Check
            sell_call = pos.legs.get('sell_call')
            if sell_call:
                call_cond_1 = sell_call.current_premium >= 1.25 * sell_call.entry_premium
                call_cond_2 = current_spot >= 1.007 * pos.entry_spot
                call_cond_3 = current_iv >= pos.entry_iv - 0.05
                call_cond_4 = volume_gate_ok
                from engine import black_scholes_delta
                sell_call_delta = black_scholes_delta(current_spot, sell_call.strike, t_years, current_iv, RISK_FREE_RATE, 'C')
                call_cond_5 = abs(sell_call_delta) > 0.32

                if call_cond_1 and call_cond_2 and call_cond_3 and call_cond_4 and call_cond_5 and 'buy_call' in pos.legs:
                    self.call_adverse_in_current_bar = True
                    if len(self.call_adverse_history) == 2 and all(self.call_adverse_history):
                        self._log("[!] Call Side adverse conditions met for 3 consecutive bars. Closing CE side legs.")
                        self.exit_leg('sell_call', 'LEG EXIT TRIGGERED', current_spot)
                        self.exit_leg('buy_call', 'LEG EXIT TRIGGERED', current_spot)
                        pos.leg_exit_triggered = True
                        return

            # Put Check
            sell_put = pos.legs.get('sell_put')
            if sell_put:
                put_cond_1 = sell_put.current_premium >= 1.25 * sell_put.entry_premium
                put_cond_2 = current_spot <= 0.993 * pos.entry_spot
                put_cond_3 = current_iv >= pos.entry_iv - 0.05
                put_cond_4 = volume_gate_ok
                from engine import black_scholes_delta
                sell_put_delta = black_scholes_delta(current_spot, sell_put.strike, t_years, current_iv, RISK_FREE_RATE, 'P')
                put_cond_5 = abs(sell_put_delta) > 0.32

                if put_cond_1 and put_cond_2 and put_cond_3 and put_cond_4 and put_cond_5 and 'buy_put' in pos.legs:
                    self.put_adverse_in_current_bar = True
                    if len(self.put_adverse_history) == 2 and all(self.put_adverse_history):
                        self._log("[!] Put Side adverse conditions met for 3 consecutive bars. Closing PE side legs.")
                        self.exit_leg('sell_put', 'LEG EXIT TRIGGERED', current_spot)
                        self.exit_leg('buy_put', 'LEG EXIT TRIGGERED', current_spot)
                        pos.leg_exit_triggered = True
                        return
        else:
            sell_leg, buy_leg = None, None
            prof_reason, stop_reason = None, None
            if is_call_side_open:
                sell_leg = pos.legs.get('sell_call')
                buy_leg = pos.legs.get('buy_call')
                prof_reason, stop_reason = "half_profit_CE", "half_stop_CE"
            else:
                sell_leg = pos.legs.get('sell_put')
                buy_leg = pos.legs.get('buy_put')
                prof_reason, stop_reason = "half_profit_PE", "half_stop_PE"

            if sell_leg and buy_leg:
                init_val = sell_leg.entry_premium - buy_leg.entry_premium
                curr_val = sell_leg.current_premium - buy_leg.current_premium
                melt = 1.0 - (curr_val / init_val) if init_val > 0 else 0.0
                loss = (curr_val - init_val) / init_val if init_val > 0 else 0.0

                if melt >= HALF_PROFIT_PCT:
                    self._log(f"[!] POST-LEG-EXIT TP MET (Melt: {melt * 100:.1f}%)")
                    self.exit_all_remaining(prof_reason, current_spot)
                elif loss >= HALF_STOP_PCT:
                    self._log(f"[!] POST-LEG-EXIT SL MET (Loss: {loss * 100:.1f}%)")
                    self.exit_all_remaining(stop_reason, current_spot)

    def exit_all_remaining(self, reason, current_spot):
        pos = self.active_position
        if not pos: return
        pos.exit_reason = reason
        for role, leg in pos.legs.items():
            if leg.status == "OPEN":
                self.exit_leg(role, reason, current_spot)
        
        all_closed = all(leg.status == "CLOSED" for leg in pos.legs.values())
        if all_closed:
            pos.status = "CLOSED"
            record = {
                'entry_time': pos.entry_time.strftime("%Y-%m-%d %H:%M:%S") if isinstance(pos.entry_time, datetime) else str(pos.entry_time),
                'exit_time': datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
                'entry_spot': pos.entry_spot,
                'entry_iv': pos.entry_iv,
                'initial_premium': pos.initial_premium,
                'pnl_points': pos.total_pnl,
                'pnl_usd': pos.total_pnl * 0.001 * TRADE_QUANTITY,
                'leg_exit_triggered': pos.leg_exit_triggered,
                'exit_reason': pos.exit_reason,
                'fees_usd': pos.fees_usd
            }
            self.trade_history.append(record)
            self.save_trade_history()
            self.active_position = None
        else:
            self._log("[!] WARNING: Some legs failed to close. Retaining active position state to retry on next loop.")

    def exit_leg(self, role, reason, current_spot):
        leg = self.active_position.legs.get(role)
        if not leg or leg.status == "CLOSED": return
        self._log(f"[!] EXITING {role} ({leg.symbol}) | {reason} | PnL: {leg.pnl:.2f}")
        
        res = None
        if not DRY_RUN:
            exit_side = 'buy' if leg.side == 'sell' else 'sell'
            res = self.client.place_order(leg.symbol, exit_side, size=TRADE_QUANTITY)
            if not res or 'result' not in res:
                err_msg = res if res else 'No Response'
                self._log(f"[!] FAILED TO EXIT {role} ({leg.symbol}) via market order: {err_msg}")
                # Try limit order fallback crossing the spread
                try:
                    ticker = self.client.get_ticker(leg.symbol)
                    if ticker:
                        if exit_side == 'buy':
                            fallback_price = max(ticker.get('best_ask', 0), ticker.get('mark_price', 0)) + 3.0
                            if fallback_price <= 3.0: fallback_price = leg.current_premium + 3.0
                        else:
                            fallback_price = min(ticker.get('best_bid', 0), ticker.get('mark_price', 0)) - 3.0
                            if fallback_price <= 0: fallback_price = max(0.1, leg.current_premium - 3.0)
                        
                        self._log(f"[*] Fallback: Placing limit order to exit {role} at price {fallback_price:.3f}...")
                        res_limit = self.client.place_order(leg.symbol, exit_side, size=TRADE_QUANTITY, order_type="limit_order", price=fallback_price)
                        if res_limit and 'result' in res_limit:
                            self._log(f"[✔] Limit order fallback succeeded!")
                            res = res_limit
                except Exception as ex:
                    self._log(f"[!] Error placing fallback limit order: {ex}")

        if DRY_RUN or (res and 'result' in res):
            leg.status = "CLOSED"
            uncapped = 0.0001 * current_spot * (TRADE_QUANTITY * 0.001)
            capped = 0.035 * leg.current_premium * (TRADE_QUANTITY * 0.001)
            self.active_position.fees_usd += min(uncapped, capped)
        else:
            self._log(f"[!] CRITICAL: Leg {role} ({leg.symbol}) remains OPEN!")

    def sync_from_exchange(self, all_tickers, btc_price):
        positions = self.client.get_positions()
        if not positions: return
        legs = {}
        for pos in positions:
            symbol = pos.get('product_symbol') or pos.get('symbol')
            if not symbol or symbol not in all_tickers: continue
            size = float(pos.get('size', 0) or 0)
            if size == 0: continue
            side = 'sell' if size < 0 else 'buy'
            entry_price = float(pos.get('entry_price') or pos.get('avg_entry_price') or 0)
            role = None
            if symbol.startswith('C-'):
                role = 'sell_call' if side == 'sell' else 'buy_call'
            elif symbol.startswith('P-'):
                role = 'sell_put' if side == 'sell' else 'buy_put'
            if role:
                legs[role] = Leg(symbol, side, entry_price)
        if len(legs) == 4:
            self.active_position = IronCondor(legs, btc_price, 0.40)
            sells = sum(l.entry_premium for l in legs.values() if l.side == 'sell')
            buys = sum(l.entry_premium for l in legs.values() if l.side == 'buy')
            self.active_position.initial_premium = sells - buys

    def get_performance_metrics(self):
        history = self.trade_history
        total_trades = len(history)
        if total_trades == 0:
            return {
                'total_trades': 0, 'win_rate': 0.0, 'avg_win': 0.0, 'avg_loss': 0.0,
                'profit_factor': 0.0, 'total_pnl_usd': 0.0, 'max_drawdown_usd': 0.0,
                'sharpe_ratio': 0.0, 'avg_holding_time': 0.0, 'total_fees_usd': 0.0,
                'leg_exit_count': 0, 'leg_exit_pct': 0.0,
                'reasons': {r: 0 for r in ['profit_min', 'profit_max', 'stop_loss', 'cost_to_cost', 'half_profit_CE',
                                           'half_profit_PE', 'half_stop_CE', 'half_stop_PE', 'force_close_eod']}
            }
        pnl_usds = [t['pnl_usd'] for t in history]
        wins = [x for x in pnl_usds if x > 0]
        losses = [abs(x) for x in pnl_usds if x < 0]
        win_rate = (len(wins) / total_trades) * 100.0
        win_premium_pcts = []
        loss_premium_pcts = []
        for t in history:
            init_prem = t.get('initial_premium', 0)
            if init_prem > 0:
                pct = (t['pnl_points'] / init_prem) * 100.0
                if t['pnl_points'] > 0: win_premium_pcts.append(pct)
                elif t['pnl_points'] < 0: loss_premium_pcts.append(abs(pct))
        avg_win = sum(win_premium_pcts) / len(win_premium_pcts) if win_premium_pcts else 0.0
        avg_loss = sum(loss_premium_pcts) / len(loss_premium_pcts) if loss_premium_pcts else 0.0
        sum_wins = sum(wins)
        sum_losses = sum(losses)
        profit_factor = sum_wins / sum_losses if sum_losses > 0 else (float('inf') if sum_wins > 0 else 1.0)
        total_pnl_usd = sum(pnl_usds)
        running_equity = 0.0
        peak = 0.0
        max_drawdown = 0.0
        for p in pnl_usds:
            running_equity += p
            peak = max(peak, running_equity)
            dd = peak - running_equity
            max_drawdown = max(max_drawdown, dd)
        mean_pnl = sum(pnl_usds) / total_trades
        if total_trades > 1:
            var_pnl = sum((x - mean_pnl) ** 2 for x in pnl_usds) / (total_trades - 1)
            std_pnl = math.sqrt(var_pnl)
            sharpe_ratio = mean_pnl / std_pnl if std_pnl > 0.0 else 0.0
        else:
            sharpe_ratio = 0.0
        holding_times = []
        for t in history:
            try:
                ent = datetime.strptime(t['entry_time'], "%Y-%m-%d %H:%M:%S")
                ex = datetime.strptime(t['exit_time'], "%Y-%m-%d %H:%M:%S")
                holding_times.append((ex - ent).total_seconds() / 60.0)
            except: pass
        avg_holding_time = sum(holding_times) / len(holding_times) if holding_times else 0.0
        total_fees_usd = sum(t.get('fees_usd', 0) for t in history)
        leg_exit_count = sum(1 for t in history if t.get('leg_exit_triggered', False))
        leg_exit_pct = (leg_exit_count / total_trades) * 100.0
        reasons_breakdown = {r: 0 for r in ['profit_min', 'profit_max', 'stop_loss', 'cost_to_cost', 'half_profit_CE',
                                           'half_profit_PE', 'half_stop_CE', 'half_stop_PE', 'force_close_eod']}
        for t in history:
            reason = t.get('exit_reason')
            if reason in reasons_breakdown: reasons_breakdown[reason] += 1
        return {
            'total_trades': total_trades, 'win_rate': win_rate, 'avg_win': avg_win, 'avg_loss': avg_loss,
            'profit_factor': profit_factor, 'total_pnl_usd': total_pnl_usd, 'max_drawdown_usd': max_drawdown,
            'sharpe_ratio': sharpe_ratio, 'avg_holding_time': avg_holding_time, 'total_fees_usd': total_fees_usd,
            'leg_exit_count': leg_exit_count, 'leg_exit_pct': leg_exit_pct, 'reasons': reasons_breakdown
        }
