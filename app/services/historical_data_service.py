"""历史K线数据服务 - 优先从DB获取,必要时从交易所下载"""
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class HistoricalDataService:
    """历史K线数据服务
    
    负责统一管理历史K线数据的获取:
    1. 优先从数据库查询1m数据
    2. 检查数据完整性
    3. 如果不完整,从交易所下载补全
    4. 聚合为目标interval返回
    """
    
    def __init__(self, db, aggregator):
        """初始化服务
        
        Args:
            db: 数据库实例
            aggregator: 数据聚合器实例
        """
        self.db = db
        self.aggregator = aggregator
    
    @staticmethod
    def convert_coinpair_format(coinpair: str, to_db: bool = True) -> str:
        """转换交易对格式
        
        Args:
            coinpair: 交易对字符串
            to_db: True表示转为DB格式(BTC-USDT), False表示转为API格式(BTC/USDT)
        
        Returns:
            转换后的格式
        """
        if to_db:
            return coinpair.replace('/', '-')
        else:
            return coinpair.replace('-', '/')
    
    @staticmethod
    def convert_interval_to_api_format(interval: str) -> str:
        """转换interval为API格式
        
        Args:
            interval: 间隔字符串 (如 1m, 5m, 1h, 1d)
        
        Returns:
            API格式的interval (如 1min, 5min, 1h, 1d)
        """
        # API格式映射
        mapping = {
            '1m': '1min',
            '5m': '5min',
            '15m': '15min',
            '30m': '30min',
            '1h': '1h',
            '2h': '2h',
            '4h': '4h',
            '6h': '6h',
            '12h': '12h',
            '1d': '1d',
            '1w': '1w'
        }
        return mapping.get(interval, interval)
    
    async def get_candlestick_data(
        self,
        coinpair: str,
        interval: str,
        limit: Optional[int] = None,
        since: Optional[int] = None
    ) -> List[Dict]:
        """获取历史K线数据的主入口，改进版的断点续传和渐进式下载逻辑

        流程:
        1. 转换coinpair格式 (BTC/USDT -> BTC-USDT)
        2. 计算需要的1m数据时间范围
        3. 检查DB数据完整性，根据现有数据智能判断下载范围
        4. 渐进式下载缺失数据，支持断点续传
        5. 缓存已下载数据，避免重复下载
        6. 从DB查询1m数据
        7. 聚合为目标interval

        Args:
            coinpair: 交易对 (API格式: BTC/USDT)
            interval: K线间隔 (如 1m, 5m, 1h)
            limit: 返回的K线数量
            since: 起始时间戳(毫秒)

        Returns:
            K线数据列表
        """
        # 步骤1: 转换格式
        db_coinpair = self.convert_coinpair_format(coinpair, to_db=True)

        logger.info(f"[HistoricalData] 数据处理请求开始: {coinpair} ({db_coinpair}), interval={interval}, limit={limit}, since={since}")

        # 步骤2: 计算需要的时间范围
        start_time, end_time = await self._calculate_time_range(
            db_coinpair, interval, limit, since
        )

        logger.info(f"[HistoricalData] 目标时间范围: {datetime.fromtimestamp(start_time/1000)} 至 {datetime.fromtimestamp(end_time/1000)}")

        # 步骤3: 检查数据完整性并获取断点信息
        is_complete, expected_count, actual_count = await self._check_data_completeness(
            db_coinpair, start_time, end_time
        )

        completeness_pct = (actual_count / expected_count * 100) if expected_count > 0 else 0
        logger.info(f"[HistoricalData] 初始数据状态: 已有 {actual_count}/{expected_count} 条数据 ({completeness_pct:.1f}%)")

        # 步骤4: 如果不完整,智能下载补全（支持断点续传）
        if not is_complete:
            logger.warning(f"[HistoricalData] 数据不完整 ({completeness_pct:.1f}%)，开始智能补全下载...")

            # 获取数据库中最新的数据点，用于断点续传
            latest_candle = await self.db.get_latest_candle(db_coinpair)
            if latest_candle:
                logger.info(f"[HistoricalData] 检测到最新数据点: {datetime.fromtimestamp(latest_candle.timestamp/1000)}, 将采用断点续传模式")

            await self._download_and_fill_data(
                db_coinpair, coinpair, start_time, end_time
            )

            # 重新检查完整性并计算实际改进效果
            is_complete_after, expected_count_after, actual_count_after = await self._check_data_completeness(
                db_coinpair, start_time, end_time
            )

            improvement_count = actual_count_after - actual_count
            improvement_pct = (improvement_count / expected_count * 100) if expected_count > 0 else 0

            if improvement_count > 0:
                logger.info(f"[HistoricalData] 补全完成: 新增 {improvement_count} 条数据，完整性由 {completeness_pct:.1f}% 提升至 {(actual_count_after/expected_count_after*100):.1f}%")
            else:
                logger.warning(f"[HistoricalData] 补全未新增数据，可能已最优或网络异常")
        else:
            logger.info(f"[HistoricalData] 数据完整性达标 {(completeness_pct):.1f}%，无需下载补全")

        # 步骤5 & 6: 查询并聚合
        logger.info(f"[HistoricalData] 开始聚合 {interval} K线数据...")
        aggregated_data = await self.aggregator.aggregate_candles(
            coin_pair=db_coinpair,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )

        logger.info(f"[HistoricalData] 聚合完成: 返回 {len(aggregated_data)} 条 {interval} K线数据")
        return aggregated_data
    
    async def _calculate_time_range(
        self,
        db_coinpair: str,
        interval: str,
        limit: Optional[int],
        since: Optional[int]
    ) -> Tuple[int, int]:
        """计算需要查询的时间范围
        
        Args:
            db_coinpair: 交易对 (DB格式)
            interval: K线间隔
            limit: 数量限制
            since: 起始时间戳
        
        Returns:
            (start_time, end_time) 时间戳(毫秒)
        """
        end_time = int(datetime.now().timestamp() * 1000)
        
        if since is not None:
            # 使用since参数
            start_time = since
        elif limit is not None:
            # 根据limit计算
            interval_minutes = self.aggregator._parse_interval(interval)
            if interval_minutes is None:
                raise ValueError(f"无法解析interval: {interval}")
            
            # 计算需要多少分钟的1m数据
            # 例如: limit=100, interval=5m, 则需要 100*5=500 分钟
            minutes_needed = limit * interval_minutes
            start_time = end_time - (minutes_needed * 60 * 1000)
            
            # 额外获取一些数据以确保有足够的数据进行聚合
            # 增加一个interval的buffer
            start_time -= (interval_minutes * 60 * 1000)
        else:
            # 默认返回最近100条
            interval_minutes = self.aggregator._parse_interval(interval)
            minutes_needed = 100 * interval_minutes
            start_time = end_time - (minutes_needed * 60 * 1000)
            start_time -= (interval_minutes * 60 * 1000)
        
        return start_time, end_time
    
    async def _check_data_completeness(
        self,
        db_coinpair: str,
        start_time: int,
        end_time: int,
        threshold: float = 0.95
    ) -> Tuple[bool, int, int]:
        """检查数据库中1m数据的完整性，优化算法避免重复下载已有数据

        Args:
            db_coinpair: 交易对 (DB格式)
            start_time: 开始时间戳(毫秒)
            end_time: 结束时间戳(毫秒)
            threshold: 完整性阈值 (默认95%)

        Returns:
            (is_complete, expected_count, actual_count)
        """
        # 计算预期的1分钟K线数量
        time_diff_minutes = (end_time - start_time) // (60 * 1000)
        expected_count = int(time_diff_minutes)

        # 查询实际数据量
        candles = await self.db.get_candles(
            coin_pair=db_coinpair,
            start_time=start_time,
            end_time=end_time
        )
        actual_count = len(candles)

        # 查找数据库中的最大时间戳
        latest_candle = await self.db.get_latest_candle(db_coinpair)
        latest_timestamp = latest_candle.timestamp if latest_candle else 0

        # 优化完整性检查逻辑：如果已有更新的数据，则无需下载缺失的部分
        if latest_timestamp >= start_time and latest_timestamp < end_time:
            # 重新计算需要的起始时间
            needed_start_time = latest_timestamp + 60000  # 从下一分钟开始
            if needed_start_time > end_time:
                # 数据库已有所有需要的数据
                logger.info(f"[完整性检查] {db_coinpair}: 数据库已有至 {datetime.fromtimestamp(latest_timestamp/1000)} 的数据，覆盖所需范围")
                return True, expected_count, actual_count
            else:
                # 需要下载的部分较少，可以降低阈值要求
                missing_range_minutes = (end_time - needed_start_time) // (60 * 1000)
                logger.info(f"[完整性检查] {db_coinpair}: 只需补全 {missing_range_minutes} 分钟数据 (从 {datetime.fromtimestamp(needed_start_time/1000)} 开始)")

                # 针对小范围缺失的数据，可以放宽完整性要求
                effective_threshold = threshold if (end_time - needed_start_time) > (end_time - start_time) * 0.1 else 0.8

                # 计算当前实际可用数据量（包括已有的和新下载的）
                actual_usable_count = actual_count + missing_range_minutes
                completeness_ratio = actual_usable_count / expected_count
                is_complete = completeness_ratio >= effective_threshold

                return is_complete, expected_count, actual_count

        # 判断完整性
        if expected_count == 0:
            is_complete = True
        else:
            completeness_ratio = actual_count / expected_count
            is_complete = completeness_ratio >= threshold

        return is_complete, expected_count, actual_count
    
    async def _download_and_fill_data(
        self,
        db_coinpair: str,
        api_coinpair: str,
        start_time: int,
        end_time: int
    ):
        """下载并填充缺失的数据，支持断点续传和渐进式写入

        Args:
            db_coinpair: 交易对 (DB格式: BTC-USDT)
            api_coinpair: 交易对 (API格式: BTC/USDT)
            start_time: 开始时间戳(毫秒)
            end_time: 结束时间戳(毫秒)
        """
        from app.services.exchange_service import ExchangeService
        from app.config import config
        from app.db.models import CandleData

        try:
            logger.info(f"[数据下载] {db_coinpair}: 开始下载 {datetime.fromtimestamp(start_time/1000)} 至 {datetime.fromtimestamp(end_time/1000)} 的数据")

            # 创建交易所服务实例
            exchange_type = config.get_exchange_type()
            exchange_service = ExchangeService(exchange_type)

            # 从数据库查找已有的最新数据点，确定断点续传的起始位置
            latest_candle = await self.db.get_latest_candle(db_coinpair)
            if latest_candle and latest_candle.timestamp >= start_time:
                # 存在比start_time更新的数据，从最新的时间点开始下载
                download_start_time = latest_candle.timestamp + 60000  # 从下1分钟开始
                if download_start_time > end_time:
                    logger.info(f"[数据下载] {db_coinpair}: 数据库已有所有需要的数据，无需下载")
                    return
                logger.info(f"[数据下载] {db_coinpair}: 检测到已有数据至 {datetime.fromtimestamp(latest_candle.timestamp/1000)}，从 {datetime.fromtimestamp(download_start_time/1000)} 开始续传")
            else:
                download_start_time = start_time

            # 分块下载和渐进式写入
            current_download_start = download_start_time
            chunk_size_hours = 24  # 每次下载24小时的数据块
            chunk_size_ms = chunk_size_hours * 60 * 60 * 1000

            total_downloaded = 0

            while current_download_start <= end_time:
                chunk_end_time = min(current_download_start + chunk_size_ms, end_time)

                logger.info(f"[数据下载] {db_coinpair}: 下载区间 {datetime.fromtimestamp(current_download_start/1000)} 至 {datetime.fromtimestamp(chunk_end_time/1000)}")

                try:
                    # 下载当前数据块
                    candlestick_data = await exchange_service.get_historical_candlestick(
                        coinpair=api_coinpair,
                        interval='1min',
                        since=current_download_start,
                        use_cache=False,
                        max_retries=3
                    )

                    if candlestick_data:
                        # 过滤出在当前块时间范围内的数据
                        filtered_data = [
                            candle for candle in candlestick_data
                            if current_download_start <= candle['timestamp'] <= chunk_end_time
                        ]

                        if filtered_data:
                            # 转换为CandleData对象
                            candles_to_store = []
                            for candle in filtered_data:
                                candle_obj = CandleData(
                                    coin_pair=db_coinpair,
                                    timestamp=candle['timestamp'],
                                    open=candle['open'],
                                    high=candle['high'],
                                    low=candle['low'],
                                    close=candle['close'],
                                    volume=candle['volume'],
                                    volume_quote=candle.get('volume_quote', candle['volume']),
                                    confirm=1
                                )
                                candles_to_store.append(candle_obj)

                            # 立即写入数据库
                            await self.db.insert_candles_batch(candles_to_store)
                            total_downloaded += len(candles_to_store)
                            logger.info(f"[数据下载] {db_coinpair}: 成功存储 {len(candles_to_store)} 条数据 (累计: {total_downloaded})")
                        else:
                            logger.warning(f"[数据下载] {db_coinpair}: 当前块没有符合条件的新数据")
                    else:
                        logger.warning(f"[数据下载] {db_coinpair}: 未能从交易所下载到当前块数据")

                    # 移动到下一个数据块
                    current_download_start = chunk_end_time + 60000  # 下一分钟开始

                except Exception as e:
                    logger.error(f"[数据下载] {db_coinpair}: 当前块下载失败: {str(e)}")
                    logger.error(f"[数据下载] 已成功下载 {total_downloaded} 条数据，继续下一块")
                    # 继续下一个数据块，不中止整个下载过程
                    current_download_start = chunk_end_time + 60000
                    continue

            logger.info(f"[数据下载] {db_coinpair}: 下载完成，总共下载 {total_downloaded} 条数据")

        except Exception as e:
            logger.error(f"[数据下载] {db_coinpair}: 下载过程发生严重错误: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            logger.info(f"[数据下载] 已成功下载 {total_downloaded} 条数据，下次将从断点继续")
            # 不抛出异常,允许继续使用已有的不完整数据


# 创建全局实例
from app.db.database import db
from app.services.aggregator import DataAggregator

aggregator = DataAggregator(db)
historical_data_service = HistoricalDataService(db, aggregator)















