import pandas as pd
import os
from trades import TradeManager
from engine import StrategyEngine

def run_backtest(csv_file="trade_log.csv"):
    if not os.path.exists(csv_file):
        print(f"Error: {csv_file} not found. Run the bot for a while first to collect data.")
        return

    df = pd.read_csv(csv_file)
    
    # Filter out priming samples (Score 0) or interleaved duplicates from multiple bot runs
    df = df[df['edge_score'] > 0]
    
    if len(df) < 2:
        print("Not enough high-quality data to backtest.")
        return

    print(f"[*] Starting Clean Backtest on {len(df)} samples...")
    
    trade_manager = TradeManager()
    
    # We simulate row by row
    for index, row in df.iterrows():
        decision = row['decision']
        combined_prem = row['combined_prem']
        strike = row['atm_strike']
        
        # In a real backtest, we'd need to consider the expiration for each trade
        # For simplicity, we'll use a placeholder 'BACKTEST_EXP'
        if decision == "ENTER" and not trade_manager.active_position:
            trade_manager.enter_trade(strike, combined_prem, "BACKTEST")
        elif trade_manager.active_position:
            trade_manager.check_conditions(combined_prem, decision)

    history = trade_manager.trade_history
    
    # Final check: include current open position in report
    if trade_manager.active_position:
        trade_manager.active_position.update(df.iloc[-1]['combined_prem'])
        history.append(trade_manager.active_position)

    if not history:
        print("No trades were opened in this dataset.")
        return

    total_trades = len(history)
    wins = [t for t in history if t.pnl > 0]
    total_pnl = sum([t.pnl for t in history])
    win_rate = (len(wins) / total_trades) * 100

    print("\n" + "="*30)
    print(" BACKTEST PERFORMANCE REPORT")
    print("="*30)
    print(f"Total Trades:    {total_trades}")
    print(f"Win Rate:        {win_rate:.2f}%")
    print(f"Total PnL (pts): {total_pnl:+.2f}")
    if history:
        avg_pnl = total_pnl / total_trades
        print(f"Avg PnL/Trade:   {avg_pnl:+.2f}")
    print("="*30)

if __name__ == "__main__":
    run_backtest()
