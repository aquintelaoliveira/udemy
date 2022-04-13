import logging
import requests
import time
import typing

from urllib.parse import urlencode

import hmac
import hashlib

import websocket
import json

import threading

from connectors.models.bitmex_model import *

logger = logging.getLogger()

# https://testnet.bitmex.com/api/explorer/
class BitmexClient:
    def __init__(self, api_key: str, api_secret: str, testnet: bool):
        if testnet:
            self._base_url = "https://testnet.bitmex.com"
            self._wss_url = "wss://ws.testnet.bitmex.com/realtime"
        else:
            self._base_url = "https://www.bitmex.com"
            self._wss_url = "wss://ws.bitmex.com/realtime"

        self._api_key = api_key
        self._api_secret = api_secret

        self.contracts = self.get_contracts()
        self.balances = self.get_balances()

        self.prices = dict()

        self._ws = None

        t = threading.Thread(target=self._start_ws)
        t.start()
           
        logger.info("Bitmex Client successfully initialized")

    # https://bitmex.com/app/apiKeysUsage
    def _generate_signature(self, method: str, endpoint: str, expires: str, data: typing.Dict) -> str:
        message = f"{method}{endpoint}?{urlencode(data)}{expires}" if len(data) > 0 else f"{method}{endpoint}{expires}"

        return hmac.new(self._api_secret.encode(), message.encode(), hashlib.sha256).hexdigest()


    def _make_request(self, method: str, endpoint: str, data: typing.Dict):
        headers = dict()
        expires = str(int(time.time()) + 5) # valid for 5 seconds
        headers['api-expires'] = expires
        headers['api-key'] = self._api_key
        headers['api-signature'] = self._generate_signature(method, endpoint, expires, data)

        if method == "GET":
            try:
                response = requests.get(f"{self._base_url}{endpoint}", params=data, headers=headers)
            except Exception as e:
                logger.error(f"Connection error while making {method} request to {endpoint}: {e}")
                return None
        elif method == "POST":
            try:
                response = requests.post(f"{self._base_url}{endpoint}", params=data, headers=headers)
            except Exception as e:
                logger.error(f"Connection error while making {method} request to {endpoint}: {e}")
                return None
        elif method == "DELETE":
            try:
                response = requests.delete(f"{self._base_url}{endpoint}", params=data, headers=headers)
            except Exception as e:
                logger.error(f"Connection error while making {method} request to {endpoint}: {e}")
                return None
        else:
            raise ValueError()

        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Error while making {method} request to {endpoint}: {response.json()} (error code {response.status_code}")
            return None

    
    def get_contracts(self) -> typing.Dict[str, Contract]:

        instruments = self._make_request("GET", "/api/v1/instrument/active", dict())

        contracts = dict()

        if instruments is not None:
            for s in instruments:
                contracts[s['symbol']] = Contract(s)

        return contracts


    def get_balances(self) -> typing.Dict[str, Balance]:
        data = dict()
        data['currency'] = "all"

        margin_data = self._make_request("GET", "/api/v1/user/margin", data)

        balances = dict()

        if margin_data is not None:
            for a in margin_data:
                balances[a['currency']] = Balance(a)

        return balances


    def get_historical_candles(self, contract: Contract, timeframe: str) -> typing.List[Candle]:
        data = dict()
        data['symbol'] = contract.symbol
        data['partial'] = True
        data['binSize'] = timeframe
        data['count'] = 500

        raw_candles = self._make_request("GET", "/pai/v1/trade/bucketed", data)

        candles = []

        if raw_candles is not None:
            for c in reversed(raw_candles):
                candles.append(Candle(c, timeframe))

        return candles


    def get_order_status(self, order_id: str, contract: Contract):
        data = dict()
        data['symbol'] = contract.symbol
        data['reverse'] = True # return the newest order id first

        order_status = self._make_request("GET", "/api/v1/order", data)

        if order_status is not None:
            for order in order_status:
                if order['orderID'] == order_id:
                    return OrderStatus(order_status[0])


    def place_order(self, contract: Contract, order_type: str, quantity: int, side: str, price=None, tif=None) -> OrderStatus:
        data = dict()
        data['symbol'] = contract.symbol
        data['type'] = order_type.capitalize()
        data['orderQty'] = quantity
        data['side'] = side.capitalize()

        if price is not None:
            data['price'] = price

        if tif is not None:
            data['timeInForce'] = tif

        order_status = self._make_request("POST", "/api/v1/order", data)

        if order_status is not None:
            order_status = OrderStatus(order_status)

        return order_status


    def cancel_order(self, order_id: str) -> OrderStatus:
        data = dict()
        data['orderID'] = order_id

        order_status = self._make_request("DELETE", "/api/v1/order", data)

        if order_status is not None:
            order_status = OrderStatus(order_status[0])

        return order_status


    def _start_ws(self):
        self._ws = websocket.WebSocketApp(self._wss_url, on_open=self._on_open, on_close=self._on_close, on_error=self._on_error, on_message=self._on_message)

        while True:
            try:
                self._ws.run_forever()
            except Exception as e:
                logger.error(f"Bitmex error in run_forever() method: {e}")
            time.sleep(2) # just to give time to connection to restart instead of keep asking at every clock


    def _on_open(self, ws):
        logger.info("Bitmex websocket connection opened")

        self.subscribe_channel("instrument")


    def _on_close(self, ws):
        logger.warning("Bitmex websocket connection closed")


    def _on_error(self, ws, msg: str):
        logger.error(f"Bitmex websocket connection error: {msg}")


    def _on_message(self, ws, msg: str):
        data = json.loads(msg)

        if "table" in data:
            if data['table'] == "instrument":
                for d in data['data']:
                    symbol = d['symbol']
                    if symbol not in self.prices:
                        self.prices[symbol] = { 'bid': None, 'ask': None }
                    if 'bidPrice' in d:
                        self.prices[symbol]['bid'] = d['bidPrice']
                    if 'askPrice' in d:
                        self.prices[symbol]['ask'] = d['askPrice']


    def subscribe_channel(self, topic: str):
        data = dict()
        data['op'] = "subscribe"
        data['args'] = []
        data['params'].append(topic)

        try:
            self._ws.send(json.dumps(data))
        except Exception as e:
            logger.error(f"Websocket error while subscribing to {topic} updates: {e}", topic, e)