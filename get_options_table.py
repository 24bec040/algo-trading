from delta_client import DeltaClient

def main():
    client = DeltaClient()
    btc = client.get_btc_price()
    exp = client.get_nearest_expiration()
    print(f"BTC Spot: ${btc}")
    print(f"Nearest Expiry: {exp}")
    
    insts = client.get_instruments(exp)
    tickers = client.get_all_tickers()
    
    calls = [i for i in insts if i['symbol'].startswith('C-')]
    puts = [i for i in insts if i['symbol'].startswith('P-')]
    
    calls.sort(key=lambda x: float(x['strike_price']))
    puts.sort(key=lambda x: float(x['strike_price']))
    
    print("\n--- CALL OPTIONS CHAIN ---")
    for c in calls:
        strike = float(c['strike_price'])
        # Only show calls around spot ($62,000 to $66,000)
        if 62000 <= strike <= 67000:
            sym = c['symbol']
            t = tickers.get(sym, {})
            mark = float(t.get('mark_price', 0))
            delta = float(t.get('delta', 0) or 0)
            print(f"Strike: ${strike:<6} | Symbol: {sym:<20} | Price: ${mark:<6.2f} | Delta: {delta:<5.3f}")
            
    print("\n--- PUT OPTIONS CHAIN ---")
    for p in puts:
        strike = float(p['strike_price'])
        # Only show puts around spot
        if 61000 <= strike <= 66000:
            sym = p['symbol']
            t = tickers.get(sym, {})
            mark = float(t.get('mark_price', 0))
            delta = float(t.get('delta', 0) or 0)
            print(f"Strike: ${strike:<6} | Symbol: {sym:<20} | Price: ${mark:<6.2f} | Delta: {delta:<5.3f}")

if __name__ == "__main__":
    main()
