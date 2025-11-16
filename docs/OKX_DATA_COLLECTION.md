# Crypto Exchange Proxy - OKX数据收集功能

## 功能概述

本项目新增了基于OKX WebSocket的实时数据收集功能，主要特性：

1. **SQLite数据库存储**：使用SQLite存储K线数据
2. **监控配置表**：`coin_pair_watch` 表用于配置需要监控的交易对
3. **自动数据收集**：项目启动后自动连接OKX WebSocket，收集1分钟级K线数据
4. **30天滑动窗口**：自动保留最近30天的数据，每天凌晨2点清理旧数据
5. **数据聚合**：支持将1分钟数据聚合为多种时间周期（5m, 15m, 30m, 1h, 4h, 1d等）
6. **WebSocket实时推送**：客户端可以连接并接收聚合后的实时数据

## 数据库表结构

### coin_pair_watch（监控配置表）
```sql
CREATE TABLE coin_pair_watch (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coin_pair TEXT NOT NULL UNIQUE,      -- 交易对，如 BTC-USDT
    enabled INTEGER NOT NULL DEFAULT 1,   -- 是否启用 (1=启用, 0=禁用)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### candle_data（K线数据表）
```sql
CREATE TABLE candle_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    coin_pair TEXT NOT NULL,             -- 交易对
    timestamp INTEGER NOT NULL,          -- 时间戳（毫秒）
    open REAL NOT NULL,                  -- 开盘价
    high REAL NOT NULL,                  -- 最高价
    low REAL NOT NULL,                   -- 最低价
    close REAL NOT NULL,                 -- 收盘价
    volume REAL NOT NULL,                -- 成交量（基础币）
    volume_quote REAL NOT NULL,          -- 成交额（计价币）
    confirm INTEGER NOT NULL DEFAULT 0,  -- 是否确认 (0=未完成, 1=已完成)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(coin_pair, timestamp)
);
```

## 安装依赖

```bash
pip install -r requirements.txt
```

新增依赖：
- `aiosqlite==0.19.0` - 异步SQLite数据库
- `apscheduler==3.10.4` - 定时任务调度

## 运行项目

```bash
python -m app.main
```

或者使用uvicorn：
```bash
uvicorn app.main:app --host 0.0.0.0 --port 9100 --reload
```

## 启动流程

1. **数据库初始化**：连接SQLite数据库，创建表结构
2. **检查监控配置**：如果没有配置监控交易对，自动添加 BTC-USDT 和 ETH-USDT
3. **启动OKX WebSocket**：连接到 `wss://ws.okx.com:8443/ws/v5/public` 并订阅1分钟K线
4. **启动定时任务**：每天凌晨2点自动清理30天前的数据
5. **提供API服务**：FastAPI服务在9100端口启动

## API接口

### 1. 查询K线数据
```
GET /data/candles
```

参数：
- `coin_pair` (必填): 交易对，如 BTC-USDT
- `interval` (可选): 时间周期，默认 1m，支持 1m, 5m, 15m, 30m, 1h, 4h, 1d
- `limit` (可选): 返回数量，默认100，最大1000
- `start_time` (可选): 开始时间戳（毫秒）
- `end_time` (可选): 结束时间戳（毫秒）

示例：
```bash
# 获取最近100条1分钟K线
curl "http://localhost:9100/data/candles?coin_pair=BTC-USDT&interval=1m&limit=100"

# 获取最近100条5分钟K线（自动聚合）
curl "http://localhost:9100/data/candles?coin_pair=BTC-USDT&interval=5m&limit=100"

# 按时间范围查询
curl "http://localhost:9100/data/candles?coin_pair=BTC-USDT&interval=15m&start_time=1704067200000&end_time=1704153600000"
```

### 2. 获取数据统计
```
GET /data/stats
```

参数：
- `coin_pair` (必填): 交易对

示例：
```bash
curl "http://localhost:9100/data/stats?coin_pair=BTC-USDT"
```

### 3. 查询监控列表
```
GET /data/watch-pairs
```

示例：
```bash
curl "http://localhost:9100/data/watch-pairs"
```

### 4. 添加监控交易对
```
POST /data/watch-pairs
```

参数：
- `coin_pair` (必填): 交易对
- `enabled` (可选): 是否启用，默认 true

示例：
```bash
curl -X POST "http://localhost:9100/data/watch-pairs?coin_pair=SOL-USDT&enabled=true"
```

### 5. 删除监控交易对
```
DELETE /data/watch-pairs
```

参数：
- `coin_pair` (必填): 交易对

示例：
```bash
curl -X DELETE "http://localhost:9100/data/watch-pairs?coin_pair=SOL-USDT"
```

### 6. 启用/禁用监控
```
PUT /data/watch-pairs/toggle
```

参数：
- `coin_pair` (必填): 交易对
- `enabled` (必填): 是否启用

示例：
```bash
curl -X PUT "http://localhost:9100/data/watch-pairs/toggle?coin_pair=BTC-USDT&enabled=false"
```

## 数据聚合说明

系统存储的是1分钟级K线数据，但支持查询多种时间周期：

- **1m**: 直接返回原始1分钟数据
- **5m**: 将5个1分钟K线聚合为1个5分钟K线
- **15m**: 将15个1分钟K线聚合为1个15分钟K线
- **30m**: 将30个1分钟K线聚合为1个30分钟K线
- **1h**: 将60个1分钟K线聚合为1个1小时K线
- **4h**: 将240个1分钟K线聚合为1个4小时K线
- **1d**: 将1440个1分钟K线聚合为1个1天K线

聚合规则：
- **开盘价**: 周期内第一个1分钟K线的开盘价
- **最高价**: 周期内所有1分钟K线的最高价
- **最低价**: 周期内所有1分钟K线的最低价
- **收盘价**: 周期内最后一个1分钟K线的收盘价
- **成交量**: 周期内所有1分钟K线的成交量总和

## 数据清理策略

### 自动清理
- **触发时间**: 每天凌晨2:00
- **清理范围**: 删除30天前的数据
- **保留数据**: 最近30天的数据（约43,200条1分钟K线/交易对）

### 手动清理
如果需要立即清理旧数据，可以调用调度器的触发方法（需要在代码中添加相应的API端点）。

## 数据存储容量估算

假设监控10个交易对：
- 每个交易对每天产生：1440条1分钟K线
- 保留30天：1440 × 30 = 43,200条/交易对
- 10个交易对：432,000条记录
- 每条记录约100字节：约40MB

## 项目结构

```
app/
├── db/                          # 数据库模块
│   ├── __init__.py
│   ├── database.py             # 数据库管理类
│   └── models.py               # 数据模型
├── services/
│   ├── okx_websocket.py        # OKX WebSocket客户端
│   ├── aggregator.py           # 数据聚合服务
│   └── scheduler.py            # 定时任务调度器
├── api/
│   ├── data.py                 # 数据查询API
│   ├── candlestick.py          # 历史K线API（原有）
│   └── websocket.py            # WebSocket API（原有）
└── main.py                     # 主应用入口
```

## 技术特点

1. **异步架构**：全异步设计，使用 asyncio 和 aiosqlite
2. **自动重连**：WebSocket断线自动重连，保证数据收集稳定性
3. **心跳机制**：WebSocket保持连接，防止超时断开
4. **批量插入**：支持批量插入K线数据，提高性能
5. **唯一性约束**：通过UNIQUE约束防止重复数据
6. **索引优化**：为查询字段创建索引，提升查询性能

## 监控与日志

系统会输出详细的日志信息：
- WebSocket连接状态
- 订阅成功/失败
- K线数据接收（仅记录已确认的K线）
- 数据清理任务执行结果
- 错误和异常信息

日志格式：
```
2024-01-10 10:30:00 - app.services.okx_websocket - INFO - [K线] BTC-USDT 2024-01-10 10:30:00 O:43250.5 H:43350.0 L:43200.0 C:43300.0 V:125.5
```

## 故障处理

### WebSocket断线
系统会自动重连，默认重连延迟5秒。重连时会自动重新订阅之前的频道。

### 数据库锁定
使用异步SQLite (aiosqlite)，避免阻塞问题。

### 数据缺失
如果因为断线导致数据缺失，可以使用原有的历史K线API补充缺失的数据。

## 未来优化方向

1. **数据压缩**：对历史数据进行压缩存储
2. **分表存储**：按月份或交易对分表，提高查询效率
3. **Redis缓存**：缓存热点数据
4. **多交易所支持**：支持Binance、Huobi等其他交易所
5. **实时推送优化**：基于已存储数据实现WebSocket实时推送给客户端
6. **数据备份**：定期备份数据库
7. **监控面板**：添加Web管理界面

## 注意事项

1. **首次启动**：首次启动时数据库为空，需要等待数据收集
2. **时区问题**：所有时间戳均为UTC时间的毫秒级时间戳
3. **速率限制**：OKX WebSocket有速率限制，避免频繁订阅/取消订阅
4. **数据延迟**：WebSocket推送频率为500ms，数据会有轻微延迟
5. **磁盘空间**：请确保有足够的磁盘空间存储数据

## 许可证

本项目遵循原有项目的许可证。
