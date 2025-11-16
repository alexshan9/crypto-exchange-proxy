"""数据聚合服务"""
import logging
from typing import List, Optional, Dict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class DataAggregator:
    """数据聚合服务"""

    def __init__(self, db):
        """初始化聚合服务

        Args:
            db: 数据库实例
        """
        self.db = db

    async def aggregate_candles(
        self,
        coin_pair: str,
        interval: str = "5m",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """聚合K线数据

        将1分钟K线聚合为指定周期的K线

        Args:
            coin_pair: 交易对，如 'BTC-USDT'
            interval: 时间周期，如 '1m', '5m', '15m', '30m', '1h', '4h', '1d'
            start_time: 开始时间戳（毫秒）
            end_time: 结束时间戳（毫秒）
            limit: 返回数量限制

        Returns:
            聚合后的K线数据列表
        """
        # 解析interval
        interval_minutes = self._parse_interval(interval)
        if interval_minutes is None:
            raise ValueError(f"不支持的时间周期: {interval}")

        # 如果是1分钟，直接返回原始数据
        if interval_minutes == 1:
            candles = await self.db.get_candles(
                coin_pair=coin_pair,
                start_time=start_time,
                end_time=end_time,
                limit=limit
            )
            return [
                {
                    'timestamp': c.timestamp,
                    'open': c.open,
                    'high': c.high,
                    'low': c.low,
                    'close': c.close,
                    'volume': c.volume,
                    'volume_quote': c.volume_quote
                }
                for c in candles
            ]

        # 获取1分钟K线数据
        candles = await self.db.get_candles(
            coin_pair=coin_pair,
            start_time=start_time,
            end_time=end_time
        )

        if not candles:
            return []

        # 聚合数据
        aggregated = []
        current_group = []
        interval_ms = interval_minutes * 60 * 1000

        for candle in candles:
            # 计算当前K线所属的时间周期
            period_start = (candle.timestamp // interval_ms) * interval_ms

            # 如果是新的周期，处理上一个周期的数据
            if current_group and current_group[0].timestamp // interval_ms != period_start // interval_ms:
                aggregated_candle = self._aggregate_group(current_group, period_start - interval_ms)
                aggregated.append(aggregated_candle)
                current_group = []

            current_group.append(candle)

        # 处理最后一组
        if current_group:
            period_start = (current_group[0].timestamp // interval_ms) * interval_ms
            aggregated_candle = self._aggregate_group(current_group, period_start)
            aggregated.append(aggregated_candle)

        # 应用limit
        if limit is not None:
            aggregated = aggregated[-limit:]

        return aggregated

    def _parse_interval(self, interval: str) -> Optional[int]:
        """解析时间周期，返回分钟数

        Args:
            interval: 时间周期字符串，如 '1m', '5m', '15m', '1h', '4h', '1d'

        Returns:
            分钟数，如果无法解析则返回None
        """
        interval = interval.lower()

        if interval.endswith('m') or interval.endswith('min'):
            # 分钟
            try:
                return int(interval.rstrip('min'))
            except ValueError:
                return None
        elif interval.endswith('h') or interval.endswith('hour'):
            # 小时
            try:
                hours = int(interval.rstrip('hour'))
                return hours * 60
            except ValueError:
                return None
        elif interval.endswith('d') or interval.endswith('day'):
            # 天
            try:
                days = int(interval.rstrip('day'))
                return days * 24 * 60
            except ValueError:
                return None
        elif interval.endswith('w') or interval.endswith('week'):
            # 周
            try:
                weeks = int(interval.rstrip('week'))
                return weeks * 7 * 24 * 60
            except ValueError:
                return None

        return None

    def _aggregate_group(self, candles: List, period_start: int) -> Dict:
        """聚合一组K线数据

        Args:
            candles: 1分钟K线列表
            period_start: 周期开始时间戳

        Returns:
            聚合后的K线数据
        """
        if not candles:
            return {}

        return {
            'timestamp': period_start,
            'open': candles[0].open,
            'high': max(c.high for c in candles),
            'low': min(c.low for c in candles),
            'close': candles[-1].close,
            'volume': sum(c.volume for c in candles),
            'volume_quote': sum(c.volume_quote for c in candles)
        }

    async def get_latest_candles(
        self,
        coin_pair: str,
        interval: str = "1m",
        limit: int = 100
    ) -> List[Dict]:
        """获取最新的K线数据

        Args:
            coin_pair: 交易对
            interval: 时间周期
            limit: 数量限制

        Returns:
            K线数据列表
        """
        # 获取最后一条数据的时间
        latest = await self.db.get_latest_candle(coin_pair)
        if not latest:
            return []

        # 计算interval对应的分钟数
        interval_minutes = self._parse_interval(interval)
        if interval_minutes is None:
            raise ValueError(f"不支持的时间周期: {interval}")

        # 计算需要查询的时间范围
        interval_ms = interval_minutes * 60 * 1000
        start_time = latest.timestamp - (limit * interval_ms)

        # 聚合数据
        return await self.aggregate_candles(
            coin_pair=coin_pair,
            interval=interval,
            start_time=start_time,
            limit=limit
        )

    async def get_candles_by_time_range(
        self,
        coin_pair: str,
        interval: str,
        start_time: int,
        end_time: int
    ) -> List[Dict]:
        """按时间范围获取K线数据

        Args:
            coin_pair: 交易对
            interval: 时间周期
            start_time: 开始时间戳（毫秒）
            end_time: 结束时间戳（毫秒）

        Returns:
            K线数据列表
        """
        return await self.aggregate_candles(
            coin_pair=coin_pair,
            interval=interval,
            start_time=start_time,
            end_time=end_time
        )

    async def get_stats(self, coin_pair: str) -> Dict:
        """获取数据统计信息

        Args:
            coin_pair: 交易对

        Returns:
            统计信息字典
        """
        return await self.db.get_data_stats(coin_pair)
