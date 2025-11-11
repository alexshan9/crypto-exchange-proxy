import ccxt

# 创建交易所实例
exchange = ccxt.okx()

# 获取BTC/USDT的1天K线数据，最近20条
data = exchange.fetch_ohlcv('BTC/USDT', '1d', limit=20)

# 数据格式：[timestamp, open, high, low, close, volume]
for candle in data:
    print(candle)