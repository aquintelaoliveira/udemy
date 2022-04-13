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

from connectors.models.binance_model import *

logger = logging.getLogger()

# https://binance-docs.github.io/apidocs/futures/en/#market-data-endpoints
class BinanceFuturesClient:
    def __init__(self, api_key: str, api_secret: str, testnet: bool):
        if testnet:
            self._base_url = "https://testnet.binancefuture.com"
            self._wss_url = "wss://fstream.binancefuture.com/ws"
        else:
            self._base_url = "https://fapi.binance.com"
            self._wss_url = "wss://fstream.binance.com/ws"

        self._api_key = api_key
        self._api_secret = api_secret

        self._headers = {"X-MBX-APIKEY": self._api_key}

        self.contracts = self.get_contracts()
        self.balances = self.get_balances()

        self.prices = dict()

        self._ws_id = 1
        self._ws = None

        t = threading.Thread(target=self._start_ws)
        t.start()
           
        logger.info("Binance Futures Client successfully initialized")


    def _generate_signature(self, data: typing.Dict) -> str:
        return hmac.new(self._api_secret.encode(), urlencode(data).encode(), hashlib.sha256).hexdigest()


    def _make_request(self, method: str, endpoint: str, data: typing.Dict):
        if method == "GET":
            try:
                response = requests.get(f"{self._base_url}{endpoint}", params=data, headers=self._headers)
            except Exception as e:
                logger.error(f"Connection error while making {method} request to {endpoint}: {e}")
                return None
        elif method == "POST":
            try:
                response = requests.post(f"{self._base_url}{endpoint}", params=data, headers=self._headers)
            except Exception as e:
                logger.error(f"Connection error while making {method} request to {endpoint}: {e}")
                return None
        elif method == "DELETE":
            try:
                response = requests.delete(f"{self._base_url}{endpoint}", params=data, headers=self._headers)
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
        enchange_info = self._make_request("GET", "/fapi/v1/exchangeInfo", dict())

        contracts = dict()
        if enchange_info is not None:
            for contract_data in enchange_info['symbols']:
                contracts[contract_data['pair']] = Contract(contract_data)
        
        return contracts


    def get_balances(self) -> typing.Dict[str, Balance]:
        data = dict()
        data['timestamp'] = int(time.time() * 1000)
        data['signature'] = self._generate_signature(data)

        balances = dict()

        account_data = self._make_request("GET", "/fapi/v1/account", data)

        if account_data is not None:
            for a in account_data['assets']:
                balances[a['asset']] = Balance(a)
        
        return balances


    def get_historical_candles(self, contract: Contract, interval: str) -> typing.List[Candle]:
        data = dict()
        data['symbol'] = contract.symbol
        data['interval'] = interval
        data['limit'] = 1000

        raw_candles = self._make_request("GET", "/fapi/v1/klines", data)

        candles = []
        if raw_candles is not None:
            for c in raw_candles:
                candles.append(Candle(c, interval))

        return candles


    def get_bid_ask(self, contract: Contract) -> typing.Dict[str, float]:
        data = dict()
        data['symbol'] = contract.symbol

        ob_data = self._make_request("GET", "/fapi/v1/ticker/bookTicker", data)

        if ob_data is not None:
            if contract.symbol not in self.prices:
                self.prices[contract.symbol] = {'bid': float(ob_data['bidPrice']), 'ask': float(ob_data['askPrice'])}
            else:
                self.prices[contract.symbol]['bid'] = float(ob_data['bidPrice'])
                self.prices[contract.symbol]['ask'] = float(ob_data['askPrice'])

            return self.prices[contract.symbol]


    def get_order_status(self, contract: Contract, order_id: int) -> OrderStatus:
        data = dict()
        data['symbol'] = contract.symbol
        data['orderId'] = order_id
        data['timestamp'] = int(time.time() * 1000)
        data['signature'] = self._generate_signature(data)

        order_status = self._make_request("GET", "/fapi/v1/order", data)

        if order_status is not None:
            order_status = OrderStatus(order_status)

        return order_status


    def place_order(self, contract: Contract, side: str, quantity: float, order_type: str, price=None, tif=None) -> OrderStatus:
        data = dict()
        data['symbol'] = contract.symbol
        data['side'] = side
        data['quantity'] = quantity
        data['type'] = order_type
        if price is not None:
            data['price'] = price
        if tif is not None:
            data['timeInForce'] = tif
        data['timestamp'] = int(time.time() * 1000)
        data['signature'] = self._generate_signature(data)

        order_status = self._make_request("POST", "/fapi/v1/order", data)

        if order_status is not None:
            order_status = OrderStatus(order_status)

        return order_status


    def cancel_order(self, contract: Contract, order_id: int) -> OrderStatus:
        data = dict()
        data['symbol'] = contract.symbol
        data['orderId'] = order_id
        data['timestamp'] = int(time.time() * 1000)
        data['signature'] = self._generate_signature(data)

        order_status = self._make_request("DELETE", "/fapi/v1/order", data)

        if order_status is not None:
            order_status = OrderStatus(order_status)

        return order_status


    def _start_ws(self):
        self._ws = websocket.WebSocketApp(self._wss_url, on_open=self._on_open, on_close=self._on_close, on_error=self._on_error, on_message=self._on_message)

        while True:
            try:
                self._ws.run_forever()
            except Exception as e:
                logger.error(f"Binance error in run_forever() method: {e}")
            time.sleep(2) # just to give time to connection to restart instead of keep asking at every clock


    def _on_open(self, ws):
        logger.info("Binance websocket connection opened")

        self.subscribe_channel(list(self.contracts.values()), "bookTicker")


    def _on_close(self, ws):
        logger.warning("Binance websocket connection closed")


    def _on_error(self, ws, msg: str):
        logger.error(f"Binance websocket connection error: {msg}")


    def _on_message(self, ws, msg: str):
        data = json.loads(msg)

        if "e" in data:
            if data['e'] == "bookTicker":
                symbol = data['s']

                if symbol not in self.prices:
                    self.prices[symbol] = {'bid': float(data['b']), 'ask': float(data['a'])}
                else:
                    self.prices[symbol]['bid'] = float(data['b'])
                    self.prices[symbol]['ask'] = float(data['a'])


    def subscribe_channel(self, contracts: typing.List[Contract], channel: str):
        data = dict()
        data['method'] = "SUBSCRIBE"
        data['params'] = []
        for contract in contracts:
            data['params'].append(f"{contract.symbol.lower()}@{channel}")
        data['id'] = self._ws_id

        try:
            self._ws.send(json.dumps(data))
        except Exception as e:
            logger.error(f"Webscoket error while subscribing to {len(contracts)} {channel} updates: {e}")
            return None

        self._ws_id += 1
