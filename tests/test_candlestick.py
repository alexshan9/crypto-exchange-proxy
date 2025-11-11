"""K线历史数据API测试"""
import pytest
from httpx import AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_get_historical_with_limit():
    """测试使用limit参数获取历史K线数据"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/candlestick/historical",
            params={
                "interval": "1h",
                "coinpair": "BTC/USDT",
                "limit": 10
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert len(data["data"]) > 0
        assert data["count"] > 0
        
        # 检查数据格式
        first_candle = data["data"][0]
        assert "timestamp" in first_candle
        assert "open" in first_candle
        assert "high" in first_candle
        assert "low" in first_candle
        assert "close" in first_candle
        assert "volume" in first_candle


@pytest.mark.asyncio
async def test_get_historical_with_since():
    """测试使用since参数获取历史K线数据"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # 使用一个过去的时间戳（2024年1月1日）
        since = 1704067200000
        
        response = await client.get(
            "/candlestick/historical",
            params={
                "interval": "1d",
                "coinpair": "BTC/USDT",
                "since": since
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert len(data["data"]) > 0
        
        # 验证返回的数据时间戳都在since之后
        for candle in data["data"]:
            assert candle["timestamp"] >= since


@pytest.mark.asyncio
async def test_invalid_interval():
    """测试使用无效的interval参数"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/candlestick/historical",
            params={
                "interval": "invalid_interval",
                "coinpair": "BTC/USDT",
                "limit": 10
            }
        )
        
        assert response.status_code == 400
        assert "不支持的interval" in response.json()["detail"]


@pytest.mark.asyncio
async def test_invalid_coinpair():
    """测试使用无效的coinpair参数"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/candlestick/historical",
            params={
                "interval": "1h",
                "coinpair": "INVALID",
                "limit": 10
            }
        )
        
        assert response.status_code == 400
        assert "coinpair格式错误" in response.json()["detail"]


@pytest.mark.asyncio
async def test_different_intervals():
    """测试不同的interval参数"""
    intervals = ["1min", "5min", "30min", "1h", "4h", "1d"]
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        for interval in intervals:
            response = await client.get(
                "/candlestick/historical",
                params={
                    "interval": interval,
                    "coinpair": "BTC/USDT",
                    "limit": 5
                }
            )
            
            assert response.status_code == 200, f"Interval {interval} failed"
            data = response.json()
            assert data["success"] is True
            assert len(data["data"]) > 0


@pytest.mark.asyncio
async def test_cache_effectiveness():
    """测试缓存是否生效"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # 第一次请求
        response1 = await client.get(
            "/candlestick/historical",
            params={
                "interval": "1h",
                "coinpair": "BTC/USDT",
                "limit": 5
            }
        )
        
        # 第二次请求（应该从缓存获取）
        response2 = await client.get(
            "/candlestick/historical",
            params={
                "interval": "1h",
                "coinpair": "BTC/USDT",
                "limit": 5
            }
        )
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        
        data1 = response1.json()
        data2 = response2.json()
        
        # 缓存数据应该相同
        assert data1["data"] == data2["data"]


@pytest.mark.asyncio
async def test_limit_boundaries():
    """测试limit参数的边界值"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        # 测试最小值
        response = await client.get(
            "/candlestick/historical",
            params={
                "interval": "1h",
                "coinpair": "BTC/USDT",
                "limit": 1
            }
        )
        assert response.status_code == 200
        
        # 测试最大值
        response = await client.get(
            "/candlestick/historical",
            params={
                "interval": "1h",
                "coinpair": "BTC/USDT",
                "limit": 1000
            }
        )
        assert response.status_code == 200
        
        # 测试超出范围（应该失败）
        response = await client.get(
            "/candlestick/historical",
            params={
                "interval": "1h",
                "coinpair": "BTC/USDT",
                "limit": 1001
            }
        )
        assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_ohlcv_data_integrity():
    """测试K线数据的完整性"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(
            "/candlestick/historical",
            params={
                "interval": "1h",
                "coinpair": "BTC/USDT",
                "limit": 10
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        for candle in data["data"]:
            # 验证价格逻辑
            assert candle["high"] >= candle["low"], "最高价应该大于等于最低价"
            assert candle["high"] >= candle["open"], "最高价应该大于等于开盘价"
            assert candle["high"] >= candle["close"], "最高价应该大于等于收盘价"
            assert candle["low"] <= candle["open"], "最低价应该小于等于开盘价"
            assert candle["low"] <= candle["close"], "最低价应该小于等于收盘价"
            assert candle["volume"] >= 0, "成交量应该大于等于0"

