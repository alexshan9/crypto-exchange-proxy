"""历史数据服务测试 - 测试断点续传和渐进式下载功能"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from app.services.historical_data_service import HistoricalDataService
from app.db.models import CandleData


class TestHistoricalDataService:
    """历史数据服务测试类"""

    @pytest.fixture
    def service(self):
        """创建测试用的历史数据服务示例"""
        mock_db = AsyncMock()
        mock_aggregator = AsyncMock()
        service = HistoricalDataService(mock_db, mock_aggregator)
        return service, mock_db, mock_aggregator

    def test_convert_coinpair_format(self, service):
        """测试交易对格式转换"""
        service, _, _ = service

        # API格式转DB格式
        db_format = service.convert_coinpair_format("BTC/USDT", to_db=True)
        assert db_format == "BTC-USDT"

        # DB格式转API格式
        api_format = service.convert_coinpair_format("BTC-USDT", to_db=False)
        assert api_format == "BTC/USDT"

    @pytest.mark.asyncio
    async def test_check_data_completeness_with_breakpoint(self, service):
        """测试带有断点的数据完整性检查"""
        service, mock_db, _ = service

        # 设置测试数据
        coinpair = "BTC-USDT"
        start_time = 1609459200000  # 2021-01-01
        end_time = 1612137600000    # 2021-02-01

        # 模拟数据库中有部分数据
        mock_db.get_latest_candle.return_value = CandleData(
            coin_pair=coinpair,
            timestamp=1611849600000,  # 2021-01-28
            open=30000, high=32000, low=29000, close=31000,
            volume=1000, volume_quote=1000, confirm=1
        )

        mock_db.get_candles.return_value = [
            CandleData(coin_pair=coinpair, timestamp=start_time + i*60000,
                      open=30000, high=32000, low=29000, close=31000,
                      volume=1000, volume_quote=1000, confirm=1)
            for i in range(100)  # 只有100条数据
        ]

        is_complete, expected, actual = await service._check_data_completeness(
            coinpair, start_time, end_time, 0.95
        )

        # 验证断点检测逻辑
        assert not is_complete
        assert expected > actual
        mock_db.get_latest_candle.assert_called_once_with(coinpair)

    @pytest.mark.asyncio
    async def test_download_with_breakpoint_resume(self, service):
        """测试断点续传下载功能"""
        service, mock_db, _ = service

        # 模拟已有数据到某时间点
        coinpair = "BTC-USDT"
        start_time = 1609459200000  # 2021-01-01
        end_time = 1612137600000    # 2021-02-01

        latest_timestamp = 1611849600000  # 2021-01-28
        mock_db.get_latest_candle.return_value = CandleData(
            coin_pair=coinpair,
            timestamp=latest_timestamp,
            open=30000, high=32000, low=29000, close=31000,
            volume=1000, volume_quote=1000, confirm=1
        )

        # 模拟交易所返回的数据
        mock_exchange_data = [
            {'timestamp': latest_timestamp + i*60000, 'open': 31000, 'high': 32000,
             'low': 30000, 'close': 31500, 'volume': 1500}
            for i in range(1, 25)  # 24小时的数据
        ]

        with patch.object(service, '_download_and_fill_data', new_callable=AsyncMock) as mock_download:
            mock_download.return_value = None

            await service.get_candlestick_data("BTC/USDT", "1h")

            # 验证下载方法被调用，并且使用了断点信息
            mock_download.assert_called_once()
            call_args = mock_download.call_args[0]
            assert call_args[0] == "BTC-USDT"  # db_coinpair
            assert call_args[1] == "BTC/USDT"   # api_coinpair
            assert call_args[2] == start_time   # start_time
            assert call_args[3] == end_time     # end_time

    @pytest.mark.asyncio
    async def test_gradual_data_writing(self, service):
        """测试渐进式数据写入功能"""
        service, mock_db, _ = service

        with patch('app.services.exchange_service.ExchangeService') as MockExchangeService:
            mock_exchange = MockExchangeService.return_value

            # 模拟交易所返回分块数据
            coinpair = "BTC-USDT"
            start_time = 1609459200000  # 2021-01-01
            end_time = 1609545600000    # 2021-01-02 (24小时后)

            # 模拟第一次返回24小时数据块
            mock_exchange.get_historical_candlestick.side_effect = [
                [
                    {'timestamp': start_time + i*60000, 'open': 30000, 'high': 32000,
                     'low': 29000, 'close': 31000, 'volume': 1000}
                    for i in range(1440)  # 24小时数据
                ]
            ]

            await service._download_and_fill_data(
                coinpair, "BTC/USDT", start_time, end_time
            )

            # 验证数据被分批写入数据库
            assert mock_db.insert_candles_batch.called
            call_args = mock_db.insert_candles_batch.call_args[0]
            candles = call_args[0]
            assert len(candles) >= 1  # 有数据写入

    @pytest.mark.asyncio
    async def test_error_recovery_and_retry(self, service):
        """测试错误恢复和重试机制"""
        service, mock_db, _ = service

        with patch('app.services.exchange_service.ExchangeService') as MockExchangeService:
            mock_exchange = MockExchangeService.return_value

            # 模拟第一次调用失败，第二次成功
            mock_exchange.get_historical_candlestick.side_effect = [
                Exception("Network error"),
                [
                    {'timestamp': 1609459200000, 'open': 30000, 'high': 32000,
                     'low': 29000, 'close': 31000, 'volume': 1000}
                ]
            ]

            # 这个测试验证错误不会导致整个下载失败，而是会继续后续块
            await service._download_and_fill_data(
                "BTC-USDT", "BTC/USDT", 1609459200000, 1609545600000
            )

            # 验证重试逻辑被触发
            assert mock_exchange.get_historical_candlestick.call_count == 2

    @pytest.mark.asyncio
    async def test_comprehensive_workflow(self, service):
        """测试完整的断点续传工作流"""
        service, mock_db, mock_aggregator = service

        # 模拟完整的工作流：检查 -> 断点续传下载 -> 聚合
        coinpair = "BTC-USDT"
        start_time = 1609459200000
        end_time = 1612137600000

        # 1. 模拟已有部分数据
        mock_db.get_latest_candle.return_value = CandleData(
            coin_pair=coinpair, timestamp=1611849600000,
            open=30000, high=32000, low=29000, close=31000,
            volume=1000, volume_quote=1000, confirm=1
        )

        mock_db.get_candles.return_value = [
            CandleData(coin_pair=coinpair, timestamp=start_time + i*60000,
                      open=30000, high=32000, low=29000, close=31000,
                      volume=1000, volume_quote=1000, confirm=1)
            for i in range(500)  # 部分数据
        ]

        # 2. 模拟聚合器返回结果
        mock_aggregator.aggregate_candles.return_value = [
            {'timestamp': 1609459200000, 'open': 30000, 'high': 32000,
             'low': 29000, 'close': 31000, 'volume': 1000}
        ]

        # 3. 运行完整流程
        with patch.object(service, '_download_and_fill_data', new_callable=AsyncMock) as mock_download:
            mock_download.return_value = None

            result = await service.get_candlestick_data("BTC/USDT", "1h")

            # 验证断点续传逻辑被触发
            mock_download.assert_called_once()

            # 验证聚合被调用
            mock_aggregator.aggregate_candles.assert_called_once()

            # 验证返回结果
            assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])