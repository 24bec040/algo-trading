import json
import time
from delta_client import DeltaClient

client = DeltaClient()

print("[!] STARTING EMERGENCY CLOSE OF ALL POSITIONS...")

# 1. Fetch all positions
positions = client.get_positions()
if not positions:
    print("[*] No active positions found to close.")
else:
    for pos in positions:
        symbol = pos['product_symbol']
        size = float(pos['size'])
        if size == 0: continue
        
        # Side to close is the opposite of current size
        # If size is -10 (short), we buy 10 to close.
        # If size is 10 (long), we sell 10 to close.
        side = 'buy' if size < 0 else 'sell'
        abs_size = abs(int(size))
        
        print(f"[*] Closing {symbol} | Size: {abs_size} | Action: {side.upper()}")
        res = client.place_order(symbol, side, abs_size)
        
        if res and 'result' in res:
            print(f"   [+] SUCCESS: Closed {symbol}")
        else:
            err = res.get('error', {}).get('message', 'Unknown Error') if res else 'No Response'
            print(f"   [!] FAILED: {symbol} | Reason: {err}")

print("\n[✔] ALL ATTEMPTED CLOSES COMPLETE.")
