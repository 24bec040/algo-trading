import requests
import time
from datetime import datetime
from config import DERIBIT_BASE_URL

class DeribitClient:
    def __init__(self, client_id=None, client_secret=None):
        self.base_url = DERIBIT_BASE_URL
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None

    def authenticate(self):
        """Placeholder for OAuth2 authentication."""
        if not self.client_id or not self.client_secret:
            return False
        return True

    def place_order(self, instrument_name, amount, side="sell", order_type="market"):
        """Placeholder for placing a real order."""
        if not self.token and not self.authenticate():
            print(f"[!] REAL EXECUTION FAILED: No API Credentials")
            return None
        
        print(f"[!] REAL ORDER PLACED: {side} {amount} {instrument_name}")
        return {"order_id": "MOCK_ID_123"}

    def get_btc_price(self):
        """Get Deribit BTC-PERPETUAL Mark Price (Fastest/Most accurate to exchange)."""
        url = f"{self.base_url}/public/get_book_summary_by_instrument?instrument_name=BTC-PERPETUAL"
        try:
            response = requests.get(url)
            data = response.json()
            return data['result'][0]['mark_price']
        except Exception as e:
            print(f"Error fetching perpetual price: {e}")
            return None

    def get_instruments(self, expiration=None):
        """Fetch available BTC options instruments."""
        url = f"{self.base_url}/public/get_instruments?currency=BTC&kind=option&expired=false"
        try:
            response = requests.get(url)
            data = response.json()
            instruments = data['result']
            if expiration:
                instruments = [i for i in instruments if expiration in i['instrument_name']]
            return instruments
        except Exception as e:
            print(f"Error fetching instruments: {e}")
            return []

    def get_nearest_expiration(self):
        """Find the earliest (daily) expiration available using actual date parsing."""
        insts = self.get_instruments()
        if not insts:
            return None
        
        unique_exp = list(set([i['instrument_name'].split('-')[1] for i in insts]))
        
        try:
            def parse_exp(e):
                return datetime.strptime(e, "%d%b%y")
            sorted_exp = sorted(unique_exp, key=parse_exp)
            return sorted_exp[0]
        except Exception as e:
            print(f"Error parsing expiration dates: {e}")
            return sorted(unique_exp)[0]

    def get_ticker(self, instrument_name):
        """Fetch the LATEST real-time ticker data for a specific instrument."""
        url = f"{self.base_url}/public/ticker?instrument_name={instrument_name}"
        try:
            response = requests.get(url, timeout=5)
            data = response.json()
            res = data['result']
            return {
                'mark_price': res['mark_price'],
                'best_bid': res.get('best_bid_price', 0),
                'best_ask': res.get('best_ask_price', 0),
                'iv': res.get('mark_iv', 40.0) / 100.0,
                'delta': res.get('greeks', {}).get('delta', 0),
                'oi': res.get('open_interest', 0)
            }
        except Exception as e:
            print(f"Error fetching ticker for {instrument_name}: {e}")
            return None

    def find_atm_strike(self, btc_price, expiration_label):
        """Find the strike closest to BTC price for a given expiration."""
        instruments = self.get_instruments(expiration_label)
        if not instruments:
            return None, None, None

        strikes = sorted(list(set([int(float(i['strike'])) for i in instruments])))
        atm_strike = min(strikes, key=lambda x: abs(x - btc_price))
        
        call_instrument = f"BTC-{expiration_label}-{atm_strike}-C"
        put_instrument = f"BTC-{expiration_label}-{atm_strike}-P"
        
        return atm_strike, call_instrument, put_instrument
