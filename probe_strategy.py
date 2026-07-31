from delta_client import DeltaClient
from engine import StrategyEngine
import json

def test_strategy():
    print("--- TESTING DELTA API & STRATEGY ---")
    client = DeltaClient()
    
    # 1. Test BTC Price
    btc = client.get_btc_price()
    print(f"[1] BTC Spot Price: ${btc}")
    
    # 2. Test Expiration
    exp = client.get_nearest_expiration()
    print(f"[2] Nearest Expiration: {exp}")
    
    # 3. Test Iron Condor Leg Discovery
    if btc and exp:
        legs = client.find_iron_condor_legs(btc, exp)
        print(f"[3] Selection (Iron Condor):")
        print(json.dumps(legs, indent=2))
        
        # Check tickers for these legs
        tickers = {}
        for role, sym in legs.items():
            ticker = client.get_ticker(sym)
            if ticker:
                print(f"    {role:10}: ${ticker['mark_price']:<10} Delta: {ticker['delta']:.3f} IV: {ticker['iv']}%")
    
    # 4. Test S/R Levels (Professor Mode)
    # engine = StrategyEngine()
    # r, s = engine.calculate_volatility_levels(btc, 0.70)
    # print(f"\n[4] Active S/R Levels (Professor Mode):")
    # print(f"    R2: {engine.resistance_levels['R2']}")
    # print(f"    R1: {engine.resistance_levels['R1']}")
    # print(f"    Median: {engine.median}")
    # print(f"    S1: {engine.support_levels['S1']}")
    # print(f"    S2: {engine.support_levels['S2']}")
    # 
    # # 5. Check Safe Zone
    # safe = engine.get_safe_zone_status(btc)
    # print(f"\n[5] Current Position Safe: {'YES' if safe else 'NO'}")

if __name__ == "__main__":
    test_strategy()
