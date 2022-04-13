import logging

from interface.root_component import Root

from connectors.binance_futures import BinanceFuturesClient
from connectors.bitmex import BitmexClient

formatter = logging.Formatter('%(asctime)s %(levelname)s :: %(message)s')

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
stream_handler.setLevel(logging.INFO)

file_handler = logging.FileHandler('info.log')
file_handler.setFormatter(formatter)
file_handler.setLevel(logging.DEBUG)

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(stream_handler)
logger.addHandler(file_handler)

if __name__ == '__main__':

    binance = BinanceFuturesClient(
        'f1aba72d57ce8cc2b0fcb7fc20d560d293e719d009f33e2af2eedf89357a8a11',
        'd1f76db56ddbf8dcc7f768e6c696274aa3b22bf5f5294cbfd95beb6e5997ae73',
        True
    )

    bitmex = BitmexClient(
        'iHyVM47EbyQ6n2riU_YgFf29',
        'gd1nxnrKz-smXJReW05LqiCuhrjckRrSs3UVkyCaC8_qZWN_',
        True
    )

    root = Root()
    root.mainloop()