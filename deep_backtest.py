import requests
import time
import pandas as pd
from datetime import datetime, timedelta
from engine import StrategyEngine
from trades import Position

def fetch_history(instrument, start, end):
    url = f"https://www.deribit.com/api/v2/public/get_tradingview_chart_data?instrument_name={instrument}&start_timestamp={start}&end_timestamp={end}&resolution=1"
    res = requests.get(url).json()
    if 'result' not in res or not res['result'].get('ticks'):
        return None
    data = res['result']
    df = pd.DataFrame({
        'timestamp': data['ticks'],
        'price': data['close']
    })
    return df

def run_deep_backtest():
    # 1. Setup
    now = int(time.time() * 1000)
    start = now - (8 * 3600 * 1000) # 8 hours
    
    # Current ATM
    call_inst = "BTC-22JUN26-64000-C"
    put_inst = "BTC-22JUN26-64000-P"
    
    print(f"[*] Fetching 8h history for {call_inst} and {put_inst}...")
    
    df_call = fetch_history(call_inst, start, now)
    df_put = fetch_history(put_inst, start, now)
    
    # Try multiple index tickers
    df_btc = None
    for ticker in ["BTC-INDEX", "BTC_USD", "BTC-USD"]:
        print(f"[*] Trying index ticker: {ticker}")
        df_btc = fetch_history(ticker, start, now)
        if df_btc is not None:
            break
            
    if df_call is None or df_put is None or df_btc is None:
        print("Error: Could not fetch complete historical data (Call, Put, or Index failed).")
        return

    # Merge data on timestamp
    df = df_btc.rename(columns={'price': 'btc_price'})
    df = df.merge(df_call.rename(columns={'price': 'call_price'}), on='timestamp', how='inner')
    df = df.merge(df_put.rename(columns={'price': 'put_price'}), on='timestamp', how='inner')
    df['combined_prem'] = (df['call_price'] + df['put_price']) * df['btc_price']
    
    if df.empty:
        print("Error: Data merge resulted in empty dataset. Check instrument synchronization.")
        return

    print(f"[*] Simulating on {len(df)} 1-minute samples...")
    
    engine = StrategyEngine()
    history = []
    active_pos = None
    
    # Simulate
    for i, row in df.iterrows():
        # IV is hard to fetch historically via chart, so we assume constant or mock relative to premium
        # For backtest purposes, premium change is the main driver.
        engine.add_sample(row['btc_price'], row['combined_prem'], 0.4) # Mock IV
        
        score = engine.calculate_edge_score()
        decision = engine.get_decision(score)
        
        if decision == "ENTER" and active_pos is None:
            active_pos = Position(64000, row['combined_prem'], "BACKTEST")
        elif active_pos:
            active_pos.update(row['combined_prem'])
            pnl_pct = active_pos.get_pnl_pct()
            
            # Exit logic (simplified from trades.py)
            if pnl_pct >= 15 or pnl_pct <= -50 or decision == "EXIT":
                active_pos.status = "CLOSED"
                history.append(active_pos)
                active_pos = None

    if active_pos:
        history.append(active_pos)

    # Reporting
    if not history:
        print("No trades triggered in the last 24h.")
        return

    wins = [t for t in history if t.pnl > 0]
    total_pnl = sum([t.pnl for t in history])
    win_rate = (len(wins) / len(history)) * 100
    avg_pnl = total_pnl / len(history)

    print("\n" + "="*40)
    print(" 24-HOUR STRATEGY BACKTEST RESULTS")
    print("="*40)
    print(f"Total Trades:    {len(history)}")
    print(f"Win Rate:        {win_rate:.1f}%")
    print(f"Total P&L (USD): ${total_pnl:+.2f}")
    print(f"Avg P&L/Trade:   ${avg_pnl:+.2f}")
    print(f"P&L Ratio (Avg Win/Avg Loss): {calculate_pl_ratio(history)}")
    print("="*40)

def calculate_pl_ratio(history):
    wins = [t.pnl for t in history if t.pnl > 0]
    losses = [abs(t.pnl) for t in history if t.pnl < 0]
    avg_win = sum(wins)/len(wins) if wins else 0
    avg_loss = sum(losses)/len(losses) if losses else 0
    return round(avg_win / avg_loss, 2) if avg_loss > 0 else "∞"

if __name__ == "__main__":
    run_deep_backtest()
