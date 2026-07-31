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
    IV_VALUE_THRESHOLD, MIN_LEG_OI, MAX_SPREAD_PCT
)

console = Console()

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
    
    for role, ticker in ui_data.get('tickers', {}).items():
        table.add_row(
            role.upper().replace('_', ' '), 
            f"{ticker['mark_price']:.2f}",
            f"{ticker['delta']:.3f} | {ticker['iv']*100:.1f}%",
            f"B/A: {ticker['best_bid']:.1f}/{ticker['best_ask']:.1f}"
        )
    table.add_section()
    table.add_row("BTCUSD SPOT", f"[bold cyan]${ui_data['btc_price']:,.1f}[/]", "", "")
    return table

def generate_strategy_panel(data, position, gates_status) -> Panel:
    content = []
    content.append(f"Decision:      [bold magenta]{data['decision']}[/]")
    content.append(f"Gates:         {gates_status}")
    content.append(f"IV %tile:      [bold]{data['iv_percentile']:.1f}%[/] (Threshold >= {IV_PERCENTILE_THRESHOLD}%)")
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
                avg_short_iv = 0.0
                min_oi = 0.0
                max_spread_pct = 0.0

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

                gates_status = (
                    f"Time:{'✔' if time_gate_ok else '✘'} | "
                    f"IV%tile:{'✔' if iv_gate_ok else '✘'} ({main.cached_iv_percentile:.1f}%) | "
                    f"IVVal:{'✔' if legs_iv_ok else '✘'} ({avg_short_iv*100:.1f}%) | "
                    f"Trend:{'✔' if trend_gate_ok else '✘'} ({pct_move_60m*100:.2f}%) | "
                    f"Liq:{'✔' if legs_liquidity_ok else '✘'} ({min_oi:.1f}OI) | "
                    f"Sprd:{'✔' if legs_spread_ok else '✘'} ({max_spread_pct:.1f}%) | "
                    f"Limit:{'✔' if trades_limit_ok else '✘'} ({main.trades_taken_today}/{MAX_TRADES_PER_DAY})"
                )

                # Entry Logic
                if not trade_manager.active_position and not ONLY_MANAGE:
                    all_gates_passed = (time_gate_ok and iv_gate_ok and legs_iv_ok and 
                                        trend_gate_ok and trades_limit_ok and legs_liquidity_ok and legs_spread_ok)
                    if config.TEST_ENTRY or all_gates_passed:
                        decision = "ENTER"
                        if config.TEST_ENTRY:
                            add_log("TEST_ENTRY is active: Bypassing safety gates!")
                        trade_manager.enter_iron_condor(legs_map, all_tickers, btc_price, main.cached_iv)
                        main.trades_taken_today += 1
                        add_log(f"Entered trade {main.trades_taken_today}/{MAX_TRADES_PER_DAY}")
                        if config.TEST_ENTRY:
                            config.TEST_ENTRY = False
                            add_log("TEST_ENTRY auto-disabled after initial fill.")
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
                    'spot_move_60m': pct_move_60m * 100
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
