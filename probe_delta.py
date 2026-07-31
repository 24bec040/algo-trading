import requests
import json

base_url = "https://api.india.delta.exchange"
symbol = "C-BTC-67000-230626" 
url = f"{base_url}/v2/tickers/{symbol}"
resp = requests.get(url)
print(json.dumps(resp.json(), indent=2))
