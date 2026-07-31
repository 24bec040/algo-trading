import requests
import pandas as pd
from engine import StrategyEngine
from trades import Position

def fetch_trades(instrument):
    url = f"https://www.deribit.com/api/v2/public/get_last_trades_by_instrument?instrument_name={instrument}&count=1000"
    res = requests.get(url).json()
    if 'result' not in res or not res['result'].get('trades'):
        return None
    trades = res['result']['trades']
    df = pd.DataFrame(trades)
    # Average price per second to simplify
    df['timestamp'] = (df['timestamp'] // 1000)
    df = df.groupby('timestamp')['price'].mean().reset_index()
    return df

def run_trade_backtest():
    # Current ATM
    call_inst = "BTC-22JUN26-64000-C"
    put_inst = "BTC-22JUN26-64000-P"
    
    # We also need BTC price for conversion (using mark price of the trades or just a spot estimate)
    # For P&L ratio, we can work in BTC units directly if we want, or just assume BTC=64000
    BTC_PRICE = 64150.0 
    
    print(f"[*] Fetching last 1000 trades for {call_inst} and {put_inst}...")
    df_call = fetch_trades(call_inst)
    df_put = fetch_trades(put_inst)
    
    if df_call is None or df_put is None:
        print("Error: Could not fetch trade data.")
        return

    # Merge on timestamp with outer join and forward fill to handle sparse trades
    df = df_call.merge(df_put, on='timestamp', suffixes=('_c', '_p'), how='outer').sort_values('timestamp')
    df['price_c'] = df['price_c'].ffill()
    df['price_p'] = df['price_p'].ffill()
    df = df.dropna() # Remove start rows where ffill didn't work
    
    df['combined_prem'] = (df['price_c'] + df['price_p']) * BTC_PRICE
    
    print(f"[*] Simulating on {len(df)} reconstructed samples...")
    
    engine = StrategyEngine()
    history = []
    active_pos = None
    
    for i, row in df.iterrows():
        # Edge Score (mocking IV and movement based on price history)
        engine.add_sample(BTC_PRICE, row['combined_prem'], 0.4)
        score = engine.calculate_edge_score()
        decision = engine.get_decision(score)
        
        if decision == "ENTER" and active_pos is None:
            active_pos = Position(64000, row['combined_prem'], "BACKTEST")
        elif active_pos:
            active_pos.update(row['combined_prem'])
            if active_pos.get_pnl_pct() >= 15 or active_pos.get_pnl_pct() <= -50 or decision == "EXIT":
                active_pos.status = "CLOSED"
                history.append(active_pos)
                active_pos = None

    if active_pos:
        history.append(active_pos)

    if not history:
        print("No trades triggered.")
        return

    wins = [t.pnl for t in history if t.pnl > 0]
    losses = [abs(t.pnl) for t in history if t.pnl < 0]
    total_pnl = sum([t.pnl for t in history])
    
    avg_win = sum(wins)/len(wins) if wins else 0
    avg_loss = sum(losses)/len(losses) if losses else 0
    pl_ratio = round(avg_win / avg_loss, 2) if avg_loss > 0 else "N/A"

    print("\n" + "="*40)
    print(" RECENT TRADES BACKTEST RESULTS")
    print("="*40)
    print(f"Total Trades:    {len(history)}")
    print(f"Total P&L (USD): ${total_pnl:+.2f}")
    print(f"Avg Win:         ${avg_win:.2f}")
    print(f"Avg Loss:        ${avg_loss:.2f}")
    print(f"P&L Ratio:       {pl_ratio}")
    print("="*40)

if __name__ == "__main__":
    run_trade_backtest()
