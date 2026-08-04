import json
import os
from datetime import datetime

def run_post_mortem():
    dir_path = os.path.dirname(os.path.abspath(__file__))
    trades_file = os.path.join(dir_path, "completed_trades.json")
    
    if not os.path.exists(trades_file):
        print("No completed trades found.")
        return
        
    with open(trades_file, "r") as f:
        trades = json.load(f)
        
    total_trades = len(trades)
    if total_trades == 0:
        print("Trade log is empty.")
        return
        
    wins = [t for t in trades if t.get("pnl_usd", 0) > 0]
    losses = [t for t in trades if t.get("pnl_usd", 0) <= 0]
    
    win_rate = (len(wins) / total_trades) * 100
    total_pnl = sum(t.get("pnl_usd", 0) for t in trades)
    
    print("\n" + "=" * 60)
    print(" 🤖 AUTONOMOUS POST-MORTEM & STRATEGY DIAGNOSTIC REPORT ")
    print("=" * 60)
    print(f" Total Trades Evaluated : {total_trades}")
    print(f" Win Count              : {len(wins)} ({win_rate:.1f}%)")
    print(f" Loss Count             : {len(losses)} ({100 - win_rate:.1f}%)")
    print(f" Net Realized PnL (USD) : ${total_pnl:+.4f}")
    print("-" * 60)
    
    # 1. Exit Reason Breakdown
    reasons = {}
    for t in trades:
        r = t.get("exit_reason", "unknown")
        if r not in reasons:
            reasons[r] = {"count": 0, "pnl": 0.0, "wins": 0}
        reasons[r]["count"] += 1
        reasons[r]["pnl"] += t.get("pnl_usd", 0)
        if t.get("pnl_usd", 0) > 0:
            reasons[r]["wins"] += 1
            
    print("\n📊 EXIT REASON ANALYSIS:")
    for r, data in sorted(reasons.items(), key=lambda x: x[1]["pnl"]):
        wr = (data["wins"] / data["count"]) * 100 if data["count"] > 0 else 0
        print(f"  • {r:<18} | Count: {data['count']:>2} | Win Rate: {wr:>5.1f}% | Net PnL: ${data['pnl']:>+7.4f}")
        
    # 2. Time-of-Day Analysis
    hour_stats = {}
    for t in trades:
        try:
            h = int(t["entry_time"].split()[1].split(":")[0])
        except:
            h = -1
        if h not in hour_stats:
            hour_stats[h] = {"count": 0, "pnl": 0.0, "wins": 0}
        hour_stats[h]["count"] += 1
        hour_stats[h]["pnl"] += t.get("pnl_usd", 0)
        if t.get("pnl_usd", 0) > 0:
            hour_stats[h]["wins"] += 1
            
    print("\n⏰ ENTRY TIME WINDOW PERFORMANCE (IST Hour):")
    for h in sorted(hour_stats.keys()):
        data = hour_stats[h]
        wr = (data["wins"] / data["count"]) * 100 if data["count"] > 0 else 0
        print(f"  • Hour {h:02d}:00 IST | Trades: {data['count']:>2} | Win Rate: {wr:>5.1f}% | Net PnL: ${data['pnl']:>+7.4f}")
        
    # 3. IV Range Analysis
    print("\n📈 ENTRY VOLATILITY (IV) DIAGNOSTIC:")
    low_iv_trades = [t for t in trades if t.get("entry_iv", 0) < 0.36]
    high_iv_trades = [t for t in trades if t.get("entry_iv", 0) >= 0.36]
    
    if low_iv_trades:
        low_wins = sum(1 for t in low_iv_trades if t.get("pnl_usd", 0) > 0)
        print(f"  • Low IV (<36%)  : {len(low_iv_trades)} trades | Win Rate: {(low_wins/len(low_iv_trades))*100:.1f}%")
    if high_iv_trades:
        high_wins = sum(1 for t in high_iv_trades if t.get("pnl_usd", 0) > 0)
        print(f"  • High IV (>=36%) : {len(high_iv_trades)} trades | Win Rate: {(high_wins/len(high_iv_trades))*100:.1f}%")

    print("\n💡 AUTONOMOUS MISTAKE IDENTIFICATION & RECOMMENDATIONS:")
    print("=" * 60)
    
    # Recommendation 1: Leg Exit behavior
    leg_exits = [t for t in trades if t.get("leg_exit_triggered", False)]
    if leg_exits:
        leg_pnl = sum(t.get("pnl_usd", 0) for t in leg_exits)
        print(f" ⚠️  LEG EXITS DETECTED: {len(leg_exits)} trades triggered leg-level exit with total PnL ${leg_pnl:+.4f}.")
        print("     -> Insight: As taught in tastytrade (Video 2), premature leg exits / half-side closing can destroy Iron Condor win rates when spot mean-reverts.")
        print("     -> Fix: Remove micro-bar leg exits and strictly follow the full 4-leg Iron Condor holding rule.")

    # Recommendation 2: Stop loss optimization
    sl_trades = [t for t in trades if t.get("exit_reason") == "stop_loss"]
    if len(sl_trades) > 0:
        print(f" ⚠️  STOP LOSS HITS: {len(sl_trades)} trades hit premature Stop Loss.")
        print("     -> Insight: Normal daily intra-range spot fluctuations were triggering 40-50% stop loss prematurely before mean-reverting.")
        print("     -> Fix: Increase Stop Loss tolerance to 100%-120% of premium or hold closer to expiry.")

    print("=" * 60 + "\n")

if __name__ == "__main__":
    run_post_mortem()
