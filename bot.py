from datetime import datetime, timezone, timedelta
import collections
import time
from rich.console import Console
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich import box

from delta_client import DeltaClient
from engine import StrategyEngine, get_iv_percentile
from trades import TradeManager
from logger import DataLogger
import config
from config import (
    UPDATE_INTERVAL_SECONDS, DRY_RUN, ONLY_MANAGE, MAX_TRADES_PER_DAY,
    TRADE_WINDOW_START, TRADE_WINDOW_END, IV_PERCENTILE_THRESHOLD, TRENDING_THRESHOLD_60M,
    IV_VALUE_THRESHOLD, MIN_LEG_OI, MAX_SPREAD_PCT, MIN_VRP_GAP,
    TRADE_QUANTITY, PROFIT_MAX_PCT, STOP_LOSS_PCT
)

console = Console()

# ── Multi-Timeframe S/R Engine ────────────────────────────────────────────────
def find_sr_levels(client, btc_price):
    """
    Collect Support/Resistance levels from 4 timeframes:
      1W  → Weekly high/low (last 2 weeks from daily candles)
      1D  → Previous day high/low + today's high/low
      4H  → Swing highs/lows from last 5 days
      1H  → Swing highs/lows from last 48 hours
    Returns: (supports_list, resistances_list, log_lines)
    """
    levels = []   # list of (label, price)
    log_lines = []

    def find_swings(candles, label):
        """Find swing highs and lows in candle list (2-bar confirmation)."""
        found = []
        for i in range(2, len(candles) - 2):
            h = candles[i]['high']
            l = candles[i]['low']
            if (h > candles[i-1]['high'] and h > candles[i-2]['high'] and
                    h > candles[i+1]['high'] and h > candles[i+2]['high']):
                found.append((f"{label}_swing_H", h))
            if (l < candles[i-1]['low'] and l < candles[i-2]['low'] and
                    l < candles[i+1]['low'] and l < candles[i+2]['low']):
                found.append((f"{label}_swing_L", l))
        return found

    try:
        # 1. Weekly & Daily — from 1D candles (last 14 bars = 2 weeks)
        daily = client.get_history(resolution="1d", limit=14)
        if daily and len(daily) >= 2:
            daily.sort(key=lambda x: x.get('time', 0))
            # Previous day
            prev_day = daily[-2]
            levels.append(("PrevDay_H", prev_day['high']))
            levels.append(("PrevDay_L", prev_day['low']))
            # Today's range so far
            today = daily[-1]
            levels.append(("Today_H", today['high']))
            levels.append(("Today_L", today['low']))
            # Weekly (last 7 bars)
            week = daily[-7:] if len(daily) >= 7 else daily
            wk_h = max(c['high'] for c in week)
            wk_l = min(c['low'] for c in week)
            levels.append(("Week_H", wk_h))
            levels.append(("Week_L", wk_l))
            # Previous week (bars -14 to -7)
            if len(daily) >= 14:
                prev_week = daily[-14:-7]
                levels.append(("PrevWeek_H", max(c['high'] for c in prev_week)))
                levels.append(("PrevWeek_L", min(c['low'] for c in prev_week)))
            log_lines.append(f"S/R Daily: PrevH={prev_day['high']:.0f} PrevL={prev_day['low']:.0f} | WeekH={wk_h:.0f} WeekL={wk_l:.0f}")

        # 2. 4H swings (last ~5 days = 30 bars)
        h4 = client.get_history(resolution="4h", limit=30)
        if h4:
            h4.sort(key=lambda x: x.get('time', 0))
            swings_4h = find_swings(h4, "4H")
            levels.extend(swings_4h)
            log_lines.append(f"S/R 4H: {len(swings_4h)} swing levels found")

        # 3. 1H swings (last 48 bars)
        h1 = client.get_history(resolution="1h", limit=48)
        if h1:
            h1.sort(key=lambda x: x.get('time', 0))
            swings_1h = find_swings(h1, "1H")
            levels.extend(swings_1h)
            log_lines.append(f"S/R 1H: {len(swings_1h)} swing levels found")

    except Exception as e:
        log_lines.append(f"S/R fetch error: {e}")

    supports     = sorted([p for (_, p) in levels if p < btc_price], reverse=True)  # highest support first
    resistances  = sorted([p for (_, p) in levels if p > btc_price])                # lowest resistance first
    return supports, resistances, log_lines


def check_sr_gate(btc_price, short_call_strike, short_put_strike, supports, resistances):
    """
    Iron Condor S/R gate:
      - Short call must be >= nearest resistance (call side protected by resistance wall)
      - Short put must be <= nearest support (put side protected by support wall)
    Returns: (gate_ok, status_string)
    """
    if not supports or not resistances:
        return True, "S/R:✔(no levels)"

    nearest_res = resistances[0]   # lowest resistance above BTC
    nearest_sup = supports[0]      # highest support below BTC

    call_ok = short_call_strike >= nearest_res
    put_ok  = short_put_strike  <= nearest_sup

    status = (f"S/R:{'✔' if call_ok and put_ok else '✘'} "
              f"Res={nearest_res:.0f}({'✔' if call_ok else f'Call {short_call_strike:.0f}✘'}) "
              f"Sup={nearest_sup:.0f}({'✔' if put_ok else f'Put {short_put_strike:.0f}✘'})")
    return (call_ok and put_ok), status
# ─────────────────────────────────────────────────────────────────────────────

def make_layout() -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="top", ratio=22),
        Layout(name="chain", ratio=28),
        Layout(name="logs", size=8),
        Layout(name="footer", size=3),
    )
    layout["top"].split_row(
        Layout(name="market", ratio=1),
        Layout(name="strategy", ratio=1),
        Layout(name="performance", ratio=1)
    )
    return layout

def generate_option_chain_table(expiry_label, all_tickers, btc_price) -> Table:
    table = Table(title=f"LIVE OPTION CHAIN - {expiry_label}", box=box.MINIMAL_DOUBLE_HEAD, expand=True, show_header=True)
    table.add_column("Strike", justify="center", style="bold yellow")
    table.add_column("Type", justify="center")
    table.add_column("Bid", style="green")
    table.add_column("Ask", style="red")
    table.add_column("Mark", style="white")
    table.add_column("Delta", style="magenta")
    table.add_column("Theta", style="cyan")
    table.add_column("IV", style="dim")
    table.add_column("OI", style="dim cyan")
    
    expiry_tickers = []
    for sym, t in all_tickers.items():
        if expiry_label in sym and (sym.startswith('C-') or sym.startswith('P-')):
            try:
                parts = sym.split('-')
                strike = float(parts[2])
                type = "CALL" if parts[0] == 'C' else "PUT"
                expiry_tickers.append((strike, type, t))
            except: continue
    
    expiry_tickers.sort(key=lambda x: x[0])
    unique_strikes = sorted(list(set([x[0] for x in expiry_tickers])))
    if not unique_strikes:
        return table
        
    atm_idx = min(range(len(unique_strikes)), key=lambda i: abs(unique_strikes[i] - btc_price))
    start_idx = max(0, atm_idx - 6)
    end_idx = min(len(unique_strikes), atm_idx + 7)
    visible_strikes = unique_strikes[start_idx:end_idx]

    for s in visible_strikes:
        c_tick = next((x[2] for x in expiry_tickers if x[0] == s and x[1] == "CALL"), None)
        p_tick = next((x[2] for x in expiry_tickers if x[0] == s and x[1] == "PUT"), None)
        if c_tick:
            table.add_row(
                f"{s:,.0f}", "CALL", f"{c_tick['best_bid']:.1f}", f"{c_tick['best_ask']:.1f}",
                f"{c_tick['mark_price']:.1f}", f"{c_tick['delta']:.3f}", f"{c_tick['theta']:.2f}",
                f"{c_tick['iv']*100:.1f}%", f"{c_tick['oi']:,.0f}"
            )
        if p_tick:
            table.add_row(
                f"", "PUT", f"{p_tick['best_bid']:.1f}", f"{p_tick['best_ask']:.1f}",
                f"{p_tick['mark_price']:.1f}", f"{p_tick['delta']:.3f}", f"{p_tick['theta']:.2f}",
                f"{p_tick['iv']*100:.1f}%", f"{p_tick['oi']:,.0f}"
            )
        table.add_section()
    return table

def generate_market_table(ui_data, engine) -> Table:
    table = Table(box=box.ROUNDED, expand=True, show_header=True)
    table.add_column("Level/Leg", style="cyan")
    table.add_column("Price/Mark", style="bold white")
    table.add_column("Delta/IV", style="magenta")
    table.add_column("Status", style="yellow")
    
    btc_spot = ui_data['btc_price']
    current_iv = ui_data.get('current_rv', 0.40)
    supp, res = engine.calculate_volatility_levels(btc_spot, current_iv)
    
    r1 = res.get('R1', btc_spot * 1.02)
    s1 = supp.get('S1', btc_spot * 0.98)
    
    table.add_row("RESISTANCE (R1)", f"[bold red]${r1:,.0f}[/]", "Upper Bound", "Channel Target")
    table.add_row("SUPPORT (S1)", f"[bold green]${s1:,.0f}[/]", "Lower Bound", "Channel Target")
    table.add_section()
    
    for role, ticker in ui_data.get('tickers', {}).items():
        table.add_row(
            role.upper().replace('_', ' '), 
            f"${ticker['mark_price']:.1f}",
            f"Delta: {ticker['delta']:>+5.3f} | IV: {ticker['iv']*100:.1f}%",
            f"B/A: {ticker['best_bid']:.1f}/{ticker['best_ask']:.1f}"
        )
    table.add_section()
    table.add_row("BTCUSD SPOT", f"[bold cyan]${btc_spot:,.1f}[/]", "Live Spot", "Active Market")
    return table

def generate_strategy_panel(data, position, gates_status) -> Panel:
    content = []
    vrp_val = data.get('vrp', 0.0)
    avg_option_iv = data.get('avg_option_iv', 0.0)
    current_rv = data.get('current_rv', 0.0)
    content.append(f"Decision:      [bold magenta]{data['decision']}[/]")
    content.append(f"Gates:         {gates_status}")
    content.append(f"Realized Vol:  [bold]{current_rv*100:.1f}%[/]")
    content.append(f"Average IV:    [bold]{avg_option_iv*100:.1f}%[/] (Threshold >= {IV_VALUE_THRESHOLD*100:.1f}%)")
    content.append(f"VRP Gap:       [bold]{vrp_val*100:.1f}%[/] (Required >= {MIN_VRP_GAP*100:.1f}%)")
    content.append(f"Spot 60m Move: [bold]{data['spot_move_60m']:.3f}%[/] (Threshold <= {TRENDING_THRESHOLD_60M*100:.1f}%)")
    content.append("-" * 25)
    
    if position:
        content.append(f"IC STATUS:     [bold cyan]OPEN[/]")
        for role, leg in position.legs.items():
            pnl_color = "green" if leg.pnl > 0 else "red"
            status_tag = f"[{pnl_color}]{leg.status}[/]"
            content.append(f"{role:10}: {leg.pnl:+.2f} ({leg.get_pnl_pct():+.1f}%) {status_tag}")
        total_pnl = position.total_pnl
        total_color = "green" if total_pnl > 0 else "red"
        content.append(f"TOTAL PNL:     [{total_color}]{total_pnl:+.2f}[/]")
    else:
        content.append("POSITION:      [dim]NONE[/dim]")
    return Panel("\n".join(content), title="Strategy & Iron Condor", border_style="blue")

def generate_performance_panel(trade_manager) -> Panel:
    metrics = trade_manager.get_performance_metrics()
    reasons = metrics['reasons']
    total_trades = metrics['total_trades']
    lines = [
        f"Trades:  {total_trades:<5} | Win Rate: {metrics['win_rate']:.1f}%",
        f"PF:      {metrics['profit_factor']:.2f} | Sharpe:   {metrics['sharpe_ratio']:.2f}",
        f"PnL:     ${metrics['total_pnl_usd']:.2f} | Max DD:   ${metrics['max_drawdown_usd']:.2f}",
        f"Fees:    ${metrics['total_fees_usd']:.2f} | Avg Hold: {metrics['avg_holding_time']:.1f}m",
        f"Leg Ex:  {metrics['leg_exit_count']} ({metrics['leg_exit_pct']:.1f}%)",
        "-" * 30,
        f"p_min: {reasons['profit_min']} | p_max: {reasons['profit_max']} | sl: {reasons['stop_loss']}",
        f"EOD:   {reasons['force_close_eod']} | half_p: C:{reasons['half_profit_CE']} P:{reasons['half_profit_PE']}",
        f"half_s: C:{reasons['half_stop_CE']} P:{reasons['half_stop_PE']}"
    ]
    return Panel("\n".join(lines), title="Strategy Performance Statistics", border_style="green")

def generate_log_panel(logs_deque) -> Panel:
    return Panel("\n".join(list(logs_deque)), title="Live Activity Log", border_style="dim")

def main():
    client = DeltaClient()
    engine = StrategyEngine()
    trade_manager = TradeManager(client)
    logger = DataLogger()
    
    logs_deque = collections.deque(maxlen=6)
    def add_log(msg):
        timestamp = datetime.now().strftime("%H:%M:%S")
        logs_deque.append(f"[{timestamp}] {msg}")
    
    trade_manager.log_func = add_log
    add_log(f"Bot Started - Mode: {'LIVE' if not DRY_RUN else 'DRY RUN'}")
    
    expiration_label = client.get_nearest_expiration()
    if not expiration_label:
        console.print("[red]Could not find active expirations.[/red]")
        return

    # Initialize Vol Percentile
    try:
        daily_candles = client.get_daily_candles(limit=60)
        current_iv, iv_percentile = get_iv_percentile(daily_candles)
        main.cached_iv = current_iv
        main.cached_iv_percentile = iv_percentile
        add_log(f"Initial IV: {current_iv*100:.1f}%, Percentile: {iv_percentile:.1f}%")
    except Exception as e:
        main.cached_iv = 0.40
        main.cached_iv_percentile = 100.0
        add_log(f"Failed to fetch initial IV: {e}")

    layout = make_layout()
    layout["header"].update(Panel(f"BTC Iron Condor Bot | Delta Exchange India | Expiry: {expiration_label}", style="bold white on blue"))
    layout["market"].update(Panel("Loading Market Data...", border_style="dim"))
    layout["strategy"].update(Panel("Calculating Strategy...", border_style="dim"))
    layout["chain"].update(Panel("Fetching Option Chain...", border_style="dim"))
    layout["logs"].update(Panel("Starting loop...", border_style="dim"))
    layout["footer"].update(Panel("Connecting to Delta...", style="dim"))
    
    with Live(layout, refresh_per_second=2, screen=True) as live:
        while True:
            try:
                now_time = time.time()
                # 0. Auto-rollover expiry (every 5 minutes)
                if not hasattr(main, 'last_expiry_key_check') or now_time - main.last_expiry_key_check > 300:
                    main.last_expiry_key_check = now_time
                    new_expiry = client.get_nearest_expiration()
                    if new_expiry and new_expiry != expiration_label:
                        expiration_label = new_expiry
                        layout["header"].update(Panel(f"BTC Iron Condor Bot | Delta Exchange India | Expiry: {expiration_label}", style="bold white on blue"))
                        add_log(f"Rolled expiry date to {expiration_label}")

                # 30-day Vol Percentile check (every 5 minutes)
                if not hasattr(main, 'last_iv_check') or now_time - main.last_iv_check > 300:
                    main.last_iv_check = now_time
                    try:
                        daily_candles = client.get_daily_candles(limit=60)
                        current_iv, iv_percentile = get_iv_percentile(daily_candles)
                        main.cached_iv = current_iv
                        main.cached_iv_percentile = iv_percentile
                        add_log(f"IV Percentile updated: {iv_percentile:.1f}%")
                    except Exception as e:
                        add_log(f"Error updating IV Percentile: {e}")

                btc_price = client.get_btc_price()
                if not btc_price:
                    layout["footer"].update(Panel("Error: API failed to fetch BTC price", style="red"))
                    time.sleep(1)
                    continue
                
                all_tickers = client.get_all_tickers()
                if not all_tickers:
                    layout["footer"].update(Panel("Error: API returned 0 tickers (Possible rate limit)", style="red"))
                    time.sleep(1)
                    continue

                if not hasattr(main, 'synced'):
                    trade_manager.sync_from_exchange(all_tickers, btc_price)
                    main.synced = True

                # Active Tickers
                active_tickers = {}
                legs_map = {}
                if not trade_manager.active_position:
                    legs_map = client.find_iron_condor_legs(btc_price, expiration_label)
                    if legs_map:
                        for role, sym in legs_map.items():
                            if sym in all_tickers: active_tickers[role] = all_tickers[sym]
                else:
                    for role, leg in trade_manager.active_position.legs.items():
                        if leg.symbol in all_tickers: active_tickers[role] = all_tickers[leg.symbol]

                # 60m trend check
                try:
                    candles_5m = client.get_history(resolution="5m", limit=13)
                    if candles_5m and len(candles_5m) >= 12:
                        price_12_bars_ago = float(candles_5m[0]['close'])
                        pct_move_60m = abs(btc_price - price_12_bars_ago) / price_12_bars_ago
                        trend_gate_ok = pct_move_60m <= TRENDING_THRESHOLD_60M
                    else:
                        pct_move_60m = 0.0
                        trend_gate_ok = False
                except Exception as e:
                    pct_move_60m = 0.0
                    trend_gate_ok = False

                IST = timezone(timedelta(hours=5, minutes=30))
                now_ist = datetime.now(IST)
                current_date_ist = now_ist.strftime("%Y-%m-%d")
                current_time_ist = now_ist.strftime("%H:%M")
                
                # Dynamically calculate trades taken today from history and active position
                trades_today = 0
                for tr in trade_manager.trade_history:
                    ent_time = tr.get('entry_time', '')
                    if ent_time.startswith(current_date_ist):
                        trades_today += 1
                if trade_manager.active_position:
                    pos = trade_manager.active_position
                    pos_date = pos.entry_time.strftime("%Y-%m-%d") if isinstance(pos.entry_time, datetime) else str(pos.entry_time)[:10]
                    if pos_date == current_date_ist:
                        trades_today += 1
                main.trades_taken_today = trades_today
                    
                time_gate_ok = (TRADE_WINDOW_START <= current_time_ist <= TRADE_WINDOW_END)
                trades_limit_ok = main.trades_taken_today < MAX_TRADES_PER_DAY
                iv_gate_ok = main.cached_iv_percentile >= IV_PERCENTILE_THRESHOLD

                # Leg-based gates (IV Value >= 40%, Liquidity/OI >= 5.0, Spread <= 5.0%)
                legs_iv_ok = False
                legs_liquidity_ok = False
                legs_spread_ok = False
                vrp_gate_ok = False
                strike_distance_ok = False
                sr_gate_ok = False
                sr_status = "S/R:?(no legs)"
                avg_short_iv = 0.0
                min_oi = 0.0
                max_spread_pct = 0.0
                vrp_gap = 0.0
                call_distance = 0.0
                put_distance = 0.0

                if legs_map:
                    all_present = all(sym in all_tickers for sym in legs_map.values())
                    if all_present:
                        # 1. Option IV value check
                        short_call_iv = all_tickers[legs_map['sell_call']]['iv']
                        short_put_iv = all_tickers[legs_map['sell_put']]['iv']
                        avg_short_iv = (short_call_iv + short_put_iv) / 2.0
                        legs_iv_ok = (avg_short_iv >= IV_VALUE_THRESHOLD)

                        # 2. Liquidity (OI) check
                        legs_oi = [all_tickers[sym]['oi'] for sym in legs_map.values()]
                        min_oi = min(legs_oi)
                        legs_liquidity_ok = (min_oi >= MIN_LEG_OI)

                        # 3. Bid-Ask Spread check
                        spread_pcts = []
                        for sym in legs_map.values():
                            tick = all_tickers[sym]
                            bid = tick['best_bid']
                            ask = tick['best_ask']
                            if bid > 10.0:
                                pct = ((ask - bid) / bid) * 100
                                spread_pcts.append(pct)
                            else:
                                # Exempt cheap options (e.g. far OTM wing protection contracts)
                                # if absolute spread <= 5.0 or ask price <= 15.0
                                if (ask - bid) <= 5.0 or ask <= 15.0:
                                    spread_pcts.append(0.0)
                                else:
                                    spread_pcts.append(999.0)
                        max_spread_pct = max(spread_pcts) if spread_pcts else float('inf')
                        legs_spread_ok = (max_spread_pct <= MAX_SPREAD_PCT)

                        # 4. Volatility Risk Premium (VRP) check
                        vrp_gap = avg_short_iv - main.cached_iv
                        vrp_gate_ok = (vrp_gap >= MIN_VRP_GAP)

                        # 5. Strike Distance check — short legs must be >= 400 USD from BTC
                        min_strike_dist = getattr(config, 'MIN_STRIKE_DISTANCE_USD', 400)
                        sell_call_sym = legs_map['sell_call']
                        sell_put_sym  = legs_map['sell_put']
                        try:
                            call_strike = float(sell_call_sym.split('-')[2])
                            put_strike  = float(sell_put_sym.split('-')[2])
                            call_distance = call_strike - btc_price
                            put_distance  = btc_price - put_strike
                            min_dist_actual = min(call_distance, put_distance)
                            strike_distance_ok = (call_distance >= min_strike_dist and put_distance >= min_strike_dist)
                        except:
                            call_distance = put_distance = min_dist_actual = 0.0
                            strike_distance_ok = False

                        # 6. S/R Multi-Timeframe Gate — strikes must be beyond key S/R levels
                        try:
                            sr_supports, sr_resistances, sr_logs = find_sr_levels(client, btc_price)
                            for sl in sr_logs:
                                add_log(sl)
                            sr_gate_ok, sr_status = check_sr_gate(
                                btc_price, call_strike, put_strike, sr_supports, sr_resistances)
                        except Exception as sr_err:
                            sr_gate_ok = True  # fail-open if S/R fetch fails
                            sr_status = f"S/R:!(err:{sr_err})"

                gates_status = (
                    f"Time:{'✔' if time_gate_ok else '✘'} | "
                    f"IV%tile:{'✔' if iv_gate_ok else '✘'} ({main.cached_iv_percentile:.1f}%) | "
                    f"IVVal:{'✔' if legs_iv_ok else '✘'} ({avg_short_iv*100:.1f}%) | "
                    f"VRP:{'✔' if vrp_gate_ok else '✘'} ({vrp_gap*100:.1f}%) | "
                    f"Trend:{'✔' if trend_gate_ok else '✘'} ({pct_move_60m*100:.2f}%) | "
                    f"Liq:{'✔' if legs_liquidity_ok else '✘'} ({min_oi:.1f}OI) | "
                    f"Sprd:{'✔' if legs_spread_ok else '✘'} ({max_spread_pct:.1f}%) | "
                    f"Dist:{'✔' if strike_distance_ok else '✘'} (C+{call_distance:.0f}/P+{put_distance:.0f}) | "
                    f"{sr_status} | "
                    f"Limit:{'✔' if trades_limit_ok else '✘'} ({main.trades_taken_today}/{MAX_TRADES_PER_DAY})"
                )

                # Entry Logic — STRICT: check completed trades + daily lock file
                if not trade_manager.active_position and not ONLY_MANAGE:
                    # Double-check daily lock file (persists across restarts)
                    import os
                    IST_today = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d")
                    lock_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"daily_lock_{IST_today}.flag")
                    lock_exists = os.path.exists(lock_file)

                    all_gates_passed = (time_gate_ok and iv_gate_ok and legs_iv_ok and vrp_gate_ok and
                                        trend_gate_ok and trades_limit_ok and legs_liquidity_ok and
                                        legs_spread_ok and strike_distance_ok and sr_gate_ok and not lock_exists)
                    is_test_mode = getattr(config, 'TEST_ENTRY', False)
                    if is_test_mode or all_gates_passed:
                        decision = "ENTER"
                        if is_test_mode:
                            add_log("TEST_ENTRY is active: Bypassing safety gates!")

                        # ── PAYOFF ANALYSIS (Delta-style Analyze page) ─────────
                        try:
                            sc_sym = legs_map['sell_call']; sp_sym = legs_map['sell_put']
                            bc_sym = legs_map['buy_call'];  bp_sym = legs_map['buy_put']
                            sc_mk = all_tickers[sc_sym]['mark_price']
                            sp_mk = all_tickers[sp_sym]['mark_price']
                            bc_mk = all_tickers[bc_sym]['mark_price']
                            bp_mk = all_tickers[bp_sym]['mark_price']
                            sc_strike = float(sc_sym.split('-')[2])
                            bc_strike = float(bc_sym.split('-')[2])
                            sp_strike = float(sp_sym.split('-')[2])
                            bp_strike = float(bp_sym.split('-')[2])
                            net_prem     = (sc_mk + sp_mk) - (bc_mk + bp_mk)
                            multiplier   = TRADE_QUANTITY * 0.001
                            call_spread  = bc_strike - sc_strike
                            put_spread   = sp_strike - bp_strike
                            max_prof_pts = net_prem
                            max_loss_pts = max(call_spread, put_spread) - net_prem
                            max_prof_usd = max_prof_pts * multiplier
                            max_loss_usd = max_loss_pts * multiplier
                            rr_ratio     = max_prof_usd / max_loss_usd if max_loss_usd > 0 else 0
                            be_call      = sc_strike + net_prem
                            be_put       = sp_strike - net_prem
                            tp_usd       = net_prem * PROFIT_MAX_PCT * multiplier
                            sl_usd       = net_prem * STOP_LOSS_PCT  * multiplier

                            # P&L at expiry for a given BTC final price
                            def pnl_at_expiry(F):
                                sc_pnl = sc_mk - max(0, F - sc_strike)
                                bc_pnl = -bc_mk + max(0, F - bc_strike)
                                sp_pnl = sp_mk - max(0, sp_strike - F)
                                bp_pnl = -bp_mk + max(0, bp_strike - F)
                                return (sc_pnl + bc_pnl + sp_pnl + bp_pnl) * multiplier

                            # 9 scenario points around the Iron Condor
                            step = int((call_spread + put_spread) / 2)
                            scenarios = sorted(set([
                                int(bp_strike - step), int(bp_strike),
                                int(sp_strike),        int(btc_price),
                                int(sc_strike),        int(bc_strike),
                                int(bc_strike + step),
                            ]))

                            add_log("=" * 58)
                            add_log(f"📊  PAYOFF ANALYSIS  |  {TRADE_QUANTITY} lots × 0.001 BTC")
                            add_log("=" * 58)
                            add_log(f"  SELL {sc_sym.split('-0')[0]:14s} @ ${sc_mk:>7.2f}   BUY {bc_sym.split('-0')[0]:14s} @ ${bc_mk:>7.2f}")
                            add_log(f"  SELL {sp_sym.split('-0')[0]:14s} @ ${sp_mk:>7.2f}   BUY {bp_sym.split('-0')[0]:14s} @ ${bp_mk:>7.2f}")
                            add_log("-" * 58)
                            add_log(f"  Max Profit : +${max_prof_usd:.3f} USD   Max Loss : -${max_loss_usd:.3f} USD")
                            add_log(f"  R/R Ratio  :  {rr_ratio:.2f}            Breakevens: ${be_call:.0f} / ${be_put:.0f}")
                            add_log(f"  Bot TP     : +${tp_usd:.3f} USD (75% melt)   SL: -${sl_usd:.3f} USD (80% exp)")
                            add_log("-" * 58)
                            add_log(f"  {'BTC Price':>10}  |  {'P&L at Expiry':>14}  |  Status")
                            add_log(f"  {'-'*10}  |  {'-'*14}  |  {'-'*16}")
                            for F in scenarios:
                                pnl = pnl_at_expiry(F)
                                if pnl >= max_prof_usd * 0.95:
                                    status = "🟢 MAX PROFIT ZONE"
                                elif pnl > 0:
                                    status = "🟡 Profitable"
                                elif pnl > -max_loss_usd * 0.5:
                                    status = "🟠 Small Loss"
                                else:
                                    status = "🔴 Large Loss"
                                marker = " ◀ NOW" if abs(F - btc_price) < step * 0.6 else ""
                                add_log(f"  ${F:>10,.0f}  |  {pnl:>+14.3f} USD  |  {status}{marker}")
                            add_log("=" * 58)
                        except Exception as pe:
                            add_log(f"Payoff calc error: {pe}")
                        # ────────────────────────────────────────────────────────

                        trade_manager.enter_iron_condor(legs_map, all_tickers, btc_price, main.cached_iv)
                        main.trades_taken_today += 1
                        # Write daily lock file immediately — survives bot restarts
                        try:
                            with open(lock_file, 'w') as lf:
                                lf.write(f"Trade entered at {datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime('%H:%M:%S')}")
                        except Exception as e:
                            add_log(f"Warning: Could not write daily lock file: {e}")
                        add_log(f"Entered trade {main.trades_taken_today}/{MAX_TRADES_PER_DAY} | Lock file written for {IST_today}")
                        if is_test_mode:
                            setattr(config, 'TEST_ENTRY', False)
                            add_log("TEST_ENTRY auto-disabled after initial fill.")
                    elif lock_exists:
                        decision = "WAIT (Daily Lock Active — 1 trade already done today)"
                    else:
                        decision = "WAIT (Gates Locked)"
                else:
                    decision = "HOLDING / MANAGING"

                # Position Management
                if trade_manager.active_position:
                    trade_manager.check_and_manage(all_tickers, btc_price, main.cached_iv)

                ui_data = {
                    'btc_price': btc_price,
                    'tickers': active_tickers,
                    'decision': decision,
                    'iv_percentile': main.cached_iv_percentile,
                    'spot_move_60m': pct_move_60m * 100,
                    'vrp': vrp_gap,
                    'avg_option_iv': avg_short_iv,
                    'current_rv': main.cached_iv
                }

                # CSV logging
                logger.log_sample({
                    "timestamp": datetime.now().isoformat(),
                    "btc_price": btc_price,
                    "atm_strike": int(round(btc_price/100)*100),
                    "call_prem": active_tickers.get('sell_call', {'mark_price': 0})['mark_price'],
                    "put_prem": active_tickers.get('sell_put', {'mark_price': 0})['mark_price'],
                    "combined_prem": sum(t['mark_price'] for t in active_tickers.values()) if active_tickers else 0,
                    "iv": main.cached_iv,
                    "btc_change_15m": pct_move_60m,
                    "edge_score": 0,
                    "decision": decision
                })

                layout["market"].update(generate_market_table(ui_data, engine))
                layout["strategy"].update(generate_strategy_panel(ui_data, trade_manager.active_position, gates_status))
                layout["performance"].update(generate_performance_panel(trade_manager))
                layout["chain"].update(generate_option_chain_table(expiration_label, all_tickers, btc_price))
                layout["logs"].update(generate_log_panel(logs_deque))
                layout["footer"].update(Panel(f"Update: {datetime.now().strftime('%H:%M:%S')} | BTC: ${btc_price:,.1f} | Mode: {'[red]LIVE[/]' if not DRY_RUN else '[yellow]DRY RUN[/]'}", style="dim"))

                time.sleep(UPDATE_INTERVAL_SECONDS)
            except KeyboardInterrupt:
                break
            except Exception as e:
                import os
                import traceback
                log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'traceback.log')
                with open(log_path, "a") as f:
                    f.write(f"\n--- ERROR AT {datetime.now()} ---\n")
                    traceback.print_exc(file=f)
                layout["footer"].update(Panel(f"Error: {e}", style="red"))
                time.sleep(2)

if __name__ == "__main__":
    main()
