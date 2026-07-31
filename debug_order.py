import json
import requests
import time
from delta_client import DeltaClient
from config import DELTA_API_KEY, DELTA_API_SECRET

client = DeltaClient()

# Try to place a small test order for a random BTC option
print("Fetching instruments...")
insts = client.get_instruments()
if not insts:
    print("No instruments found!")
    exit()

test_product = insts[0]
print(f"Testing order for: {test_product['symbol']} (ID: {test_product['id']})")

path = "/v2/orders"
url = f"{client.base_url}{path}"

# Standard payload
payload = {
    "product_id": int(test_product['id']),
    "size": 1,
    "side": "buy",
    "order_type": "market_order"
}

payload_str = json.dumps(payload)
headers = client._get_headers("POST", path, payload_str)

print("\n--- SENDING TEST ORDER ---")
print(f"Payload: {payload_str}")
try:
    response = requests.post(url, headers=headers, data=payload_str)
    print(f"Status Code: {response.status_code}")
    print("Full Raw Response:")
    print(json.dumps(response.json(), indent=2))
except Exception as e:
    print(f"Request failed: {e}")
