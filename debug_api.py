import json
import requests
import time
from delta_client import DeltaClient

client = DeltaClient()

def debug_private_endpoint(path, method="GET", payload=""):
    url = f"{client.base_url}{path}"
    headers = client._get_headers(method, path, payload)
    print(f"\nChecking {path}...")
    try:
        response = requests.get(url, headers=headers) if method == "GET" else requests.post(url, headers=headers, data=payload)
        print(f"Status: {response.status_code}")
        print(json.dumps(response.json(), indent=2))
    except Exception as e:
        print(f"Failed: {e}")

# Check 1: Standard Positions
debug_private_endpoint("/v2/positions")

# Check 2: Positions for BTC
debug_private_endpoint("/v2/positions?underlying_asset_symbols=BTC")

# Check 3: Active Orders (to see if they are pending)
debug_private_endpoint("/v2/orders/active")

# Check 4: Wallet Balance (to verify API is working)
debug_private_endpoint("/v2/wallet/balances")
