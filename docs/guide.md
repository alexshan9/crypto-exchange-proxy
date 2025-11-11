## 服务说明
对外提供restapi 和 ws通信转发服务，将下面的接口转发至不同的交易所，fastapi 端口使用 9100, 使用 uvicorn 进行管理。需要以docker 形式进行运行，实现 Dockerfile 和 docker compose
## 接口

### candlestick/historical 历史数据获取
支持 1min 5min 30min 1h 4h 8h 1d的 历史candlestick 获取，调用cctx 的接口获取

传入参数：
1. interval: 1min | 5min | 30min | 1h | 4h |  8h | 1d， candlestick 的间隔
2. coinpair: string，交易币对
3. limit：number 往前多少根candlestick
4. since: 返回一个时间点之后的所有的candlestick，如果这个字段存在，则忽略 limit

待优化方向：
1. 增加请求缓存，根据candlestick的interval 设置。但需要注意缓存的有效性，需要按照candlestick 实际的来。需要避免，用户没有请求到最新市场数据的情况。


cctx 接口调用参考：
```python
import ccxt

# 创建交易所实例
exchange = ccxt.okx()

# 获取BTC/USDT的1天K线数据，最近20条
data = exchange.fetch_ohlcv('BTC/USDT', '1d', limit=20)

# 数据格式：[timestamp, open, high, low, close, volume]
for candle in data:
    print(candle)
```

```python 
import ccxt
import time

exchange = ccxt.okx()
symbol = 'BTC/USDT'
timeframe = '1h'
since = exchange.parse8601('2024-01-01 00:00:00')  # 起始时间
all_data = []

while True:
    try:
        ohlcvs = exchange.fetch_ohlcv(symbol, timeframe)
        if len(ohlcvs) == 0:
            break
        since = ohlcvs[-1][0] + 1  # 更新为最后一条数据的时间戳+1
        all_data += ohlcvs
        time.sleep(exchange.rateLimit / 1000)  # 遵守速率限制
    except Exception as e:
        print(f'错误: {e}')
        break
# fetch_ohlcv 结构： [[1760832000000, 107175.5, 109450.0, 106110.5, 108649.8, 6780.74873937],...]
```

测试方式：使用 BTC/USDT 请求20根，时间分别设置为 1min | 5min | 30min | 1h | 4h |  8h | 1d，返回的数据接口和预期相同
### 实时数据转发 
对外提供ws 服务接口，如果有client 连接进来，才需要连接到okx 的 公共websocket 地址，进行数据转发。

okx对接参考：
```python
pip install python-okx
公共频道订阅（无需认证）
订阅 ticker 频道获取实时价格：​

python
import asyncio
import okx.PublicData as PublicData

# 创建 WebSocket 公共数据客户端
async def watch_ticker():
    # WebSocket 公共服务地址
    ws_public_url = "wss://ws.okx.com:8443/ws/v5/public"
    
    # 订阅消息格式
    subscribe_msg = {
        "op": "subscribe",
        "args": [
            {
                "channel": "tickers",
                "instId": "BTC-USDT"
            }
        ]
    }
    
    async with websockets.connect(ws_public_url) as websocket:
        # 发送订阅请求
        await websocket.send(json.dumps(subscribe_msg))
        
                
        # 持续接收消息
        while True:
            response = await websocket.recv()
            data = json.loads(response)
            print(data) # {'event': 'subscribe', 'arg': {'channel': 'tickers', 'instId': 'BTC-USDT'}, 'connId': '74d89929'}
            break

# 运行
asyncio.run(watch_ticker())
```

测试方式：
client 能正常连接，使用channel BTC-USDT， 接收10s，验证返回值