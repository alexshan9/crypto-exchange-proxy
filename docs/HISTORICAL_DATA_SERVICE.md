# 历史K线数据服务 - 实现说明

## 概述

本次更新重构了历史K线数据获取逻辑,实现了以下核心功能:

**接口调用流程:**
```
API请求 → 数据库查询1m数据 → 完整性检查 → 
[数据完整] 直接聚合返回 | [数据不足] 下载补全 → 重新查询聚合 → 返回
```

## 核心变更

### 1. 新增服务: `HistoricalDataService`

位置: `app/services/historical_data_service.py`

该服务负责统一管理历史K线数据获取,包含以下核心功能:

#### 1.1 格式转换
```python
convert_coinpair_format(coinpair, to_db=True)
```
- API格式: `BTC/USDT` (斜杠分隔)
- 数据库格式: `BTC-USDT` (短横线分隔)
- 双向转换支持

#### 1.2 时间范围计算
```python
_calculate_time_range(db_coinpair, interval, limit, since)
```
- **场景A - 使用limit参数:**
  - 根据`limit`和`interval`计算需要的1m数据量
  - 例: `limit=100, interval=5m` → 需要500分钟的1m数据
  - 额外增加一个interval的buffer以确保数据充足

- **场景B - 使用since参数:**
  - 从`since`时间戳到当前时间
  - 忽略`limit`参数

#### 1.3 数据完整性检查
```python
_check_data_completeness(db_coinpair, start_time, end_time, threshold=0.95)
```
- 计算预期的1分钟K线数量
- 查询数据库实际数据量
- 判断完整性(默认95%阈值)
- 返回: `(is_complete, expected_count, actual_count)`

#### 1.4 数据下载与补全
```python
_download_and_fill_data(db_coinpair, api_coinpair, start_time, end_time)
```
- 当数据不完整时触发
- 使用`ExchangeService`下载1m数据
- 自动存储到数据库(去重处理)
- 支持重试和错误处理

#### 1.5 主入口函数
```python
get_candlestick_data(coinpair, interval, limit, since)
```
完整流程:
1. 转换coinpair格式 (BTC/USDT → BTC-USDT)
2. 计算需要的1m数据时间范围
3. 检查数据库数据完整性
4. 如果不完整,下载补全
5. 从数据库查询1m数据
6. 聚合为目标interval
7. 返回结果

### 2. 重构API端点: `/candlestick/historical`

位置: `app/api/candlestick.py`

**主要变更:**
```python
# 旧逻辑 (直接调用交易所服务)
candlestick_data = await exchange_service.get_historical_candlestick(...)

# 新逻辑 (使用历史数据服务)
candlestick_data = await historical_data_service.get_candlestick_data(...)
```

**优势:**
- 优先使用数据库数据(快速响应)
- 自动补全缺失数据(无需手动维护)
- 统一的聚合逻辑(从1m聚合到任意interval)
- 详细的日志记录(便于调试)

## 使用示例

### 示例1: 获取最近100条5分钟K线

**请求:**
```bash
GET /candlestick/historical?coinpair=BTC/USDT&interval=5m&limit=100
```

**流程:**
1. 计算需要的时间范围: 当前时间 - (100 * 5 + 5) 分钟
2. 查询数据库中该时间范围的1m数据
3. 检查完整性: 需要505条1m数据
4. 如果数据完整(≥95%):
   - 直接聚合为5m K线
   - 返回最后100条
5. 如果数据不足(<95%):
   - 从交易所下载补全
   - 重新查询并聚合
   - 返回结果

**响应:**
```json
{
  "success": true,
  "data": [
    {
      "timestamp": 1699900800000,
      "open": 35000.5,
      "high": 35100.0,
      "low": 34900.0,
      "close": 35050.0,
      "volume": 123.45,
      "volume_quote": 4321000.0
    },
    ...
  ],
  "count": 100,
  "source": "database",
  "request": {
    "interval": "5m",
    "coinpair": "BTC/USDT",
    "limit": 100,
    "since": null
  }
}
```

### 示例2: 获取指定时间之后的数据

**请求:**
```bash
GET /candlestick/historical?coinpair=ETH/USDT&interval=1h&since=1699900800000
```

**流程:**
1. 从since时间戳到当前时间
2. 查询该范围的1m数据
3. 检查完整性并补全(如需要)
4. 聚合为1h K线
5. 返回所有数据(不限制条数)

### 示例3: 不同interval的聚合

支持的interval及其聚合规则:
- `1m`: 直接返回1m数据,无需聚合
- `5m`: 每5条1m数据聚合为1条5m数据
- `15m`: 每15条1m数据聚合为1条15m数据
- `30m`: 每30条1m数据聚合为1条30m数据
- `1h`: 每60条1m数据聚合为1条1h数据
- `2h`: 每120条1m数据聚合为1条2h数据
- `4h`: 每240条1m数据聚合为1条4h数据
- `6h`: 每360条1m数据聚合为1条6h数据
- `12h`: 每720条1m数据聚合为1条12h数据
- `1d`: 每1440条1m数据聚合为1条1d数据
- `1w`: 每10080条1m数据聚合为1条1w数据

## 性能优化

### 1. 缓存策略
- 数据库作为一级缓存
- 避免重复下载已有的历史数据
- 自动去重(使用UNIQUE约束)

### 2. 批量操作
- 批量插入K线数据
- 减少数据库I/O操作

### 3. 智能下载
- 只下载缺失的时间段
- 95%完整性阈值(避免为少量缺失数据重新下载)
- 支持断点续传(基于时间戳)

### 4. 日志记录
详细的日志帮助追踪数据流转:
```
[HistoricalData] 请求: BTC/USDT (BTC-USDT), interval=5m, limit=100, since=None
[HistoricalData] 时间范围: 2025-11-14 15:00:51 至 2025-11-14 23:25:51
[HistoricalData] 数据完整性: 505/505 (100.00%)
[HistoricalData] 开始聚合数据到 5m...
[HistoricalData] 聚合完成,返回 100 条数据
```

## 数据完整性保证

### 启动时检查
项目启动时会自动执行30天历史数据完整性检查:
```python
# app/main.py
await _verify_historical_data_completeness(db, coin_pairs)
```

### 运行时补全
API调用时会自动检查并补全数据:
- 95%完整性阈值
- 自动触发下载
- 透明对用户(用户无需关心数据来源)

### 实时更新
WebSocket订阅实时更新1m数据:
- OKXCandleCollector持续收集数据
- 自动更新到数据库
- 确保最新数据的完整性

## 错误处理

### 1. 参数验证
```python
# 无效的interval
GET /candlestick/historical?coinpair=BTC/USDT&interval=3m
→ 400 Bad Request: "不支持的interval: 3m. 支持的值: 1m, 5m, ..."

# 无效的coinpair格式
GET /candlestick/historical?coinpair=BTCUSDT&interval=5m
→ 400 Bad Request: "coinpair格式错误，应为 'BASE/QUOTE' 格式"
```

### 2. 下载失败处理
- 支持重试机制(max_retries)
- 下载失败不中断服务
- 使用现有的不完整数据返回
- 详细的错误日志

### 3. 数据库错误
- 自动重连机制
- 事务保护
- 冲突处理(ON CONFLICT DO UPDATE)

## 与现有系统的集成

### 1. 复用现有组件
- `DataAggregator`: 数据聚合逻辑
- `ExchangeService`: 交易所数据下载
- `Database`: 数据持久化
- `config`: 配置管理

### 2. 不影响现有功能
- WebSocket实时数据: 保持不变
- 数据管理API(`/data/*`): 保持不变
- 启动时数据检查: 保持不变

### 3. 向后兼容
- API端点路径不变
- 请求参数格式不变
- 响应格式增强(新增`source`字段)

## 测试结果

### 测试1: 格式转换 ✅
- API格式 ↔ DB格式转换正确

### 测试2: 时间范围计算 ✅
- limit参数: 505分钟 (100*5 + buffer) ✓
- since参数: 24小时 ✓

### 测试3: 数据完整性检查 ✅
- BTC-USDT: 43,217条数据
- 最近1小时: 58/60条 (96.67%) ✓

### 测试4: 完整流程 ✅
- 获取最近10条5分钟K线
- 耗时: 0.00秒
- 时间间隔: 5分钟 ✓

### 测试5: 不同interval聚合 ✅
- ETH-USDT 15分钟K线
- 24小时: 97条 (预期96条) ✓
- 时间间隔: 15分钟 ✓

## 配置说明

相关配置项(在`app/config.py`):
```python
EXCHANGE_TYPE = "okx"  # 交易所类型
MAX_RETRIES = 3  # 最大重试次数
COMPLETENESS_THRESHOLD = 0.95  # 完整性阈值
```

## 日志级别

建议的日志级别:
- 生产环境: `INFO`
- 开发环境: `DEBUG`
- 调试下载: `DEBUG`

关键日志标签:
- `[HistoricalData]`: 历史数据服务
- `[数据下载]`: 数据下载流程
- `[数据验证]`: 数据完整性检查
- `[API]`: API请求处理

## 未来优化方向

1. **多级缓存:**
   - Redis缓存热数据
   - 减少数据库查询

2. **异步下载:**
   - 后台任务队列
   - 避免阻塞API响应

3. **智能预加载:**
   - 预测常用查询
   - 提前准备数据

4. **数据压缩:**
   - 归档旧数据
   - 节省存储空间

5. **监控告警:**
   - 数据完整性监控
   - 下载失败告警

## 总结

本次重构实现了一个健壮、高效的历史K线数据服务,核心优势:

✅ **优先数据库** - 快速响应,减少交易所API调用  
✅ **自动补全** - 透明的数据完整性保证  
✅ **灵活聚合** - 支持任意interval的聚合  
✅ **错误容忍** - 完善的错误处理机制  
✅ **详细日志** - 便于调试和监控  
✅ **向后兼容** - 不影响现有功能  

---

*文档版本: 1.0*  
*更新时间: 2025-11-14*















