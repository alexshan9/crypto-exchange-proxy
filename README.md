# Crypto Exchange Proxy

加密货币交易所代理服务，提供历史K线数据获取和实时ticker数据转发。

## 功能特性

- 📊 **历史K线数据API** - 支持11种时间周期（1m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d, 1w）
- 🔄 **智能数据轮询** - since参数自动循环获取大量历史数据
- 🚀 **实时数据转发** - WebSocket转发OKX交易所ticker数据
- 🔁 **失败重试机制** - 网络错误自动重试3次（指数退避）
- 💾 **智能缓存** - 根据时间周期自动设置缓存TTL
- 🐳 **Docker部署** - 完整的Docker和Docker Compose配置

## 快速启动

### 配置文件

首次使用前，可修改 `config.ini` 配置交易所和其他参数：

```ini
[exchange]
# 交易所类型（支持：okx, binance, huobi等）
type = okx

[server]
port = 9100
host = 0.0.0.0

[cache]
enabled = true
# ... 其他缓存配置
```

### 本地开发

```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务（自动读取config.ini）
python -m app.main

# 或使用uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 9100 --reload
```

### Docker部署

```bash
# 构建并启动
docker-compose up -d

# 查看日志
docker-compose logs -f
```

服务将在 `http://localhost:9100` 启动。

## API文档

启动服务后访问：
- **Swagger UI**: http://localhost:9100/docs
- **ReDoc**: http://localhost:9100/redoc

### 1. 历史K线数据

**接口**: `GET /candlestick/historical`

**支持的时间周期**: 1m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d, 1w

**请求参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| interval | string | 是 | K线间隔 |
| coinpair | string | 是 | 交易对（如BTC/USDT） |
| limit | integer | 否 | 返回数量（默认100，最大1000） |
| since | integer | 否 | 起始时间戳（毫秒），指定后忽略limit |

**请求示例**:

```bash
# 获取最近20根1小时K线
curl "http://localhost:9100/candlestick/historical?interval=1h&coinpair=BTC/USDT&limit=20"

# 获取指定时间后的所有日K线
curl "http://localhost:9100/candlestick/historical?interval=1d&coinpair=BTC/USDT&since=1704067200000"
```

**响应示例**:

```json
{
  "success": true,
  "data": [
    {
      "timestamp": 1704067200000,
      "open": 42500.5,
      "high": 42800.0,
      "low": 42300.0,
      "close": 42600.5,
      "volume": 1234.56
    }
  ],
  "count": 1,
  "request": {
    "interval": "1h",
    "coinpair": "BTC/USDT",
    "limit": 20,
    "since": null
  }
}
```

### 2. WebSocket实时数据

**接口**: `ws://localhost:9100/ws/ticker`

**功能**: 实时接收OKX交易所的BTC-USDT ticker数据

#### Python客户端

```python
import asyncio
import websockets
import json

async def connect():
    uri = "ws://localhost:9100/ws/ticker"
    async with websockets.connect(uri) as websocket:
        # 接收欢迎消息
        welcome = await websocket.recv()
        print(f"欢迎消息: {json.loads(welcome)}")
        
        # 持续接收ticker数据
        while True:
            message = await websocket.recv()
            data = json.loads(message)
            
            if 'data' in data:
                ticker = data['data'][0]
                print(f"BTC-USDT: ${ticker['last']} "
                      f"(买:{ticker['bidPx']} 卖:{ticker['askPx']})")

asyncio.run(connect())
```

#### JavaScript客户端

```javascript
const ws = new WebSocket('ws://localhost:9100/ws/ticker');

ws.onopen = () => {
    console.log('WebSocket连接已建立');
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    if (data.event === 'connected') {
        console.log('欢迎:', data.message);
    } else if (data.data) {
        const ticker = data.data[0];
        console.log(`BTC-USDT: $${ticker.last} (买:${ticker.bidPx} 卖:${ticker.askPx})`);
    }
};

ws.onerror = (error) => {
    console.error('WebSocket错误:', error);
};

ws.onclose = () => {
    console.log('WebSocket连接已关闭');
};
```

#### 命令行测试（wscat）

```bash
# 安装wscat
npm install -g wscat

# 连接WebSocket
wscat -c ws://localhost:9100/ws/ticker
```

#### 消息格式

**欢迎消息**:
```json
{
  "event": "connected",
  "message": "已连接到crypto-exchange-proxy，正在接收OKX BTC-USDT ticker数据"
}
```

**Ticker数据**:
```json
{
  "arg": {
    "channel": "tickers",
    "instId": "BTC-USDT"
  },
  "data": [
    {
      "instId": "BTC-USDT",
      "last": "42500.5",        // 最新成交价
      "bidPx": "42500.0",       // 买一价
      "bidSz": "2.3",           // 买一量
      "askPx": "42501.0",       // 卖一价
      "askSz": "1.5",           // 卖一量
      "open24h": "42000.0",     // 24小时开盘价
      "high24h": "43000.0",     // 24小时最高价
      "low24h": "41500.0",      // 24小时最低价
      "vol24h": "2910.5",       // 24小时成交量(币)
      "volCcy24h": "123456789", // 24小时成交额(USDT)
      "ts": "1704067200000"     // 时间戳
    }
  ]
}
```

## 项目结构

```
crypto-exchange-proxy/
├── app/                        # 应用代码
│   ├── main.py                # FastAPI主应用
│   ├── config.py              # 配置管理
│   ├── api/                   # API端点
│   │   ├── candlestick.py    # K线REST API
│   │   └── websocket.py      # WebSocket转发
│   ├── services/             # 业务服务
│   │   ├── exchange_service.py    # 交易所服务（CCXT）
│   │   └── websocket_manager.py   # WebSocket管理器
│   └── utils/                # 工具类
│       └── cache.py          # 缓存工具
├── tests/                    # 测试代码
│   ├── test_candlestick.py  # K线接口测试
│   └── test_websocket.py    # WebSocket测试
├── config.ini               # 配置文件（可修改交易所等参数）
├── Dockerfile               # Docker镜像
├── docker-compose.yml       # Docker编排
├── requirements.txt         # Python依赖
└── README.md               # 项目文档
```

## 技术栈

- **Web框架**: FastAPI + Uvicorn
- **交易所接口**: CCXT (支持多交易所)
- **WebSocket**: websockets
- **容器化**: Docker + Docker Compose
- **测试**: pytest + pytest-asyncio

## 缓存策略

系统根据K线周期自动设置缓存TTL（Time-To-Live），采用**被动过期**策略：

| K线周期 | 缓存TTL |
|---------|----------|
| 1m      | 30秒     |
| 5m      | 2分钟    |
| 15m     | 5分钟    |
| 30m+    | 10分钟   |

**工作原理**：

1. **首次请求**：从交易所获取数据并缓存
2. **缓存期内**：直接返回缓存数据（无需请求交易所）
3. **缓存过期**：下次请求时检测过期，重新从交易所获取
4. **独立缓存**：每个交易对、时间周期、查询参数独立缓存

**示例时间线**：
```
时刻0:00 → 请求1m K线 → 查询OKX → 返回数据 → 缓存30秒
时刻0:10 → 请求1m K线 → 命中缓存 → 直接返回
时刻0:20 → 请求1m K线 → 命中缓存 → 直接返回
时刻0:35 → 请求1m K线 → 缓存过期 → 查询OKX → 返回新数据 → 缓存30秒
```

**注意**：无定时任务，仅在有请求时检查并更新缓存

## 运行测试

```bash
# 运行所有测试
pytest

# 运行K线测试
pytest tests/test_candlestick.py -v

# 运行WebSocket测试
pytest tests/test_websocket.py -v
```

## 许可证

MIT License
