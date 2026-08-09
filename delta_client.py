import requests
import time
import hmac
import hashlib
import json
from datetime import datetime, timedelta
from config import DELTA_API_KEY, DELTA_API_SECRET, DELTA_BASE_URL, SHORT_CALL_DELTA_TARGET, SHORT_PUT_DELTA_TARGET, HEDGE_WIDTH_USD
class DeltaClient:
    def __init__(self):
        self.base_url = DELTA_BASE_URL
        self.api_key = DELTA_API_KEY
        self.api_secret = DELTA_API_SECRET
        self.product_cache = {}

    def _get_headers(self, method, path, payload=""):
        timestamp = str(int(time.time()))
        signature = self._generate_signature(method, path, timestamp, payload)
        return {
            "api-key": self.api_key,
            "signature": signature,
            "timestamp": timestamp,
            "Content-Type": "application/json"
        }

    def _generate_signature(self, method, path, timestamp, payload=""):
        message = method + timestamp + path + payload
        return hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    def get_btc_price(self):
        """Fetch BTC Perpetual price (matches TradingView chart)."""
        url = f"{self.base_url}/v2/tickers/BTCUSD"
        try:
            response = requests.get(url)
            data = response.json()
            return float(data['result']['mark_price'])
        except Exception as e:
            print(f"Error fetching Delta BTC perpetual price: {e}")
            return None

    def get_instruments(self, expiration_date=None):
        """Fetch available BTC options instruments from Delta."""
        url = f"{self.base_url}/v2/products?contract_types=call_options,put_options&underlying_asset_symbols=BTC"
        try:
            response = requests.get(url)
            data = response.json()
            insts = data['result']
            if expiration_date:
                insts = [i for i in insts if expiration_date in i['symbol']]
            return insts
        except Exception as e:
            print(f"Error fetching Delta instruments: {e}")
            return []

    def get_nearest_expiration(self):
        """Find the earliest (daily) expiration available on Delta."""
        insts = self.get_instruments()
        if not insts: return None
        expirations = list(set([i['symbol'].split('-')[-1] for i in insts if "BTC" in i['symbol']]))
        def parse_exp(e):
            return datetime.strptime(e, "%d%m%y")
        sorted_exp = sorted(expirations, key=parse_exp)
        return sorted_exp[0]

    def get_ticker(self, symbol):
        """Fetch real-time ticker for a specific Delta instrument."""
        url = f"{self.base_url}/v2/tickers/{symbol}"
        try:
            response = requests.get(url)
            data = response.json()
            return self._format_ticker(data['result'])
        except Exception as e:
            print(f"Error fetching Delta ticker for {symbol}: {e}")
            return None

    def get_all_tickers(self):
        """Fetch real-time tickers for all Delta instruments."""
        url = f"{self.base_url}/v2/tickers"
        try:
            response = requests.get(url)
            data = response.json()
            # Convert and format for fast O(1) checks
            tickers = {t['symbol']: self._format_ticker(t) for t in data.get('result', [])}
            return tickers
        except Exception as e:
            print(f"Error fetching Delta tickers: {e}")
            return {}

    def _format_ticker(self, res):
        quotes = res.get('quotes') or {}
        greeks = res.get('greeks') or {}
        return {
            'symbol': res['symbol'],
            'mark_price': float(res.get('mark_price', 0) or 0),
            'best_bid': float(quotes.get('best_bid', 0) or 0),
            'best_ask': float(quotes.get('best_ask', 0) or 0),
            'iv': float(quotes.get('mark_iv') or res.get('mark_vol') or res.get('mark_iv') or 0),
            'delta': float(greeks.get('delta', 0) or 0),
            'gamma': float(greeks.get('gamma', 0) or 0),
            'theta': float(greeks.get('theta', 0) or 0),
            'oi': float(res.get('oi', 0) or 0)
        }

    def find_iron_condor_legs(self, btc_price, expiry_label):
        """
        Dynamically find Call/Put sell legs and their matching hedges.
        Rules:
        - Anchor on the Call ATM leg strike.
        - Scan the subset of Put strikes from {-1, 0, +1} offsets of Call ATM strike.
        - Match the one that has the closest mark price to the selected Call leg.
        - Fixed hedge width = 4 strikes ($2000 offset).
        """
        insts = self.get_instruments(expiry_label)
        if not insts: return None
        
        # Filter for Calls and Puts
        calls = [i for i in insts if i['symbol'].startswith('C-')]
        puts = [i for i in insts if i['symbol'].startswith('P-')]
        if not calls or not puts: return None

        # Sort calls/puts by strike
        calls.sort(key=lambda x: float(x['strike_price']))
        puts.sort(key=lambda x: float(x['strike_price']))

        # Tickers for premiums
        tickers = self.get_all_tickers()
        if not tickers: return None

        # 1. Delta-Based strike selection (OTM target)
        call_candidates = [c for c in calls if c['symbol'] in tickers]
        if not call_candidates:
            # Fallback to ATM Call
            sell_call = min(calls, key=lambda x: abs(float(x['strike_price']) - btc_price))
        else:
            sell_call = min(call_candidates, key=lambda x: abs(tickers[x['symbol']]['delta'] - SHORT_CALL_DELTA_TARGET))
            
        call_strike = float(sell_call['strike_price'])
        
        # 2. Select Put Strike based on Put target delta
        put_candidates = [p for p in puts if p['symbol'] in tickers]
        if not put_candidates:
            # Fallback to ATM Put
            sell_put = min(puts, key=lambda x: abs(float(x['strike_price']) - btc_price))
        else:
            sell_put = min(put_candidates, key=lambda x: abs(tickers[x['symbol']]['delta'] - SHORT_PUT_DELTA_TARGET))
            
        put_strike = float(sell_put['strike_price'])
        
        # 3. Dynamic Wing Selection (using HEDGE_WIDTH_USD from config)
        # Determine whether HEDGE_WIDTH_USD or HEDGE_WIDTH_USD + 100 distance Call and Put legs have better liquidity (measured by Open Interest)
        call_near_target = call_strike + HEDGE_WIDTH_USD
        call_far_target = call_strike + HEDGE_WIDTH_USD + 100
        put_near_target = put_strike - HEDGE_WIDTH_USD
        put_far_target = put_strike - (HEDGE_WIDTH_USD + 100)

        # Find closest actual instruments
        c_near_inst = min(calls, key=lambda x: abs(float(x['strike_price']) - call_near_target))
        c_far_inst = min(calls, key=lambda x: abs(float(x['strike_price']) - call_far_target))
        p_near_inst = min(puts, key=lambda x: abs(float(x['strike_price']) - put_near_target))
        p_far_inst = min(puts, key=lambda x: abs(float(x['strike_price']) - put_far_target))

        # Liquidity (OI) check
        oi_near = float(tickers.get(c_near_inst['symbol'], {}).get('oi', 0) or 0) + float(tickers.get(p_near_inst['symbol'], {}).get('oi', 0) or 0)
        oi_far = float(tickers.get(c_far_inst['symbol'], {}).get('oi', 0) or 0) + float(tickers.get(p_far_inst['symbol'], {}).get('oi', 0) or 0)

        if oi_far > oi_near:
            buy_call = c_far_inst
            buy_put = p_far_inst
        else:
            buy_call = c_near_inst
            buy_put = p_near_inst
            
        # Find product ID and populate product cache for faster orders
        for inst in insts:
            self.product_cache[inst['symbol']] = inst['id']
        
        return {
            'sell_call': sell_call['symbol'],
            'sell_put': sell_put['symbol'],
            'buy_call': buy_call['symbol'],
            'buy_put': buy_put['symbol']
        }

    def place_order(self, symbol, side, size, order_type="market_order", price=None):
        """Place an order on Delta Exchange."""
        path = "/v2/orders"
        url = f"{self.base_url}{path}"
        
        # Check cache first
        product_id = self.product_cache.get(symbol)
        if not product_id:
            insts = self.get_instruments()
            for inst in insts:
                self.product_cache[inst['symbol']] = inst['id']
            product_id = self.product_cache.get(symbol)
            
        if not product_id:
            print(f"Error placing order: Product {symbol} not found.")
            return {"success": False, "error": {"code": "product_not_found", "context": f"Symbol {symbol} not listed on Delta"}}

        payload = {
            "product_id": product_id,
            "size": int(size),
            "side": side,
            "order_type": order_type
        }
        if price: payload["limit_price"] = str(price)

        payload_str = json.dumps(payload)
        headers = self._get_headers("POST", path, payload_str)
        
        try:
            response = requests.post(url, headers=headers, data=payload_str)
            return response.json()
        except Exception as e:
            print(f"Error placing order: {e}")
            return None

    def get_history(self, resolution="5m", limit=100):
        """Fetch historical candle data for BTCUSD using the correct history endpoint."""
        import time
        end_t = int(time.time())
        res_map = {
            "1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800,
            "1h": 3600, "2h": 7200, "4h": 14400, "1d": 86400
        }
        res_seconds = res_map.get(resolution, 60)
        start_t = end_t - (res_seconds * limit * 2)
        url = f"{self.base_url}/v2/history/candles?symbol=BTCUSD&resolution={resolution}&start={start_t}&end={end_t}"
        try:
            res = requests.get(url).json()
            return res.get('result', [])
        except Exception as e:
            print(f"Error fetching history: {e}")
            return []


    def get_daily_candles(self, limit=60):
        """Fetch daily candles for BTCUSD to calculate realized volatility."""
        import time
        end_t = int(time.time())
        start_t = end_t - (24 * 3600 * limit * 2)
        url = f"{self.base_url}/v2/history/candles?symbol=BTCUSD&resolution=1d&start={start_t}&end={end_t}"
        try:
            res = requests.get(url).json()
            candles = res.get('result', [])
            candles.sort(key=lambda x: x.get('time', 0))
            return candles
        except Exception as e:
            print(f"Error fetching daily candles: {e}")
            return []

    def get_positions(self):
        """Fetch all active positions for the account."""
        path = "/v2/positions"
        # Delta India requires underlying_asset_symbol filter
        query = "underlying_asset_symbol=BTC"
        url = f"{self.base_url}{path}?{query}"
        headers = self._get_headers("GET", f"{path}?{query}")
        try:
            res = requests.get(url, headers=headers).json()
            return res.get('result', [])
        except:
            return []
