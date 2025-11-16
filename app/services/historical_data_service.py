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
        """获取历史K线数据的主入口
        
        流程:
        1. 转换coinpair格式 (BTC/USDT -> BTC-USDT)
        2. 计算需要的1m数据时间范围
        3. 检查DB数据完整性
        4. 如果不完整,下载补全
        5. 从DB查询1m数据
        6. 聚合为目标interval
        7. 返回结果
        
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
        
        logger.info(f"[HistoricalData] 请求: {coinpair} ({db_coinpair}), interval={interval}, limit={limit}, since={since}")
        
        # 步骤2: 计算需要的时间范围
        start_time, end_time = await self._calculate_time_range(
            db_coinpair, interval, limit, since
        )
        
        logger.info(f"[HistoricalData] 时间范围: {datetime.fromtimestamp(start_time/1000)} 至 {datetime.fromtimestamp(end_time/1000)}")
        
        # 步骤3: 检查数据完整性
        is_complete, expected_count, actual_count = await self._check_data_completeness(
            db_coinpair, start_time, end_time
        )
        
        completeness_pct = (actual_count / expected_count * 100) if expected_count > 0 else 0
        logger.info(f"[HistoricalData] 数据完整性: {actual_count}/{expected_count} ({completeness_pct:.2f}%)")
        
        # 步骤4: 如果不完整,下载补全
        if not is_complete:
            logger.warning(f"[HistoricalData] 数据不完整,开始下载补全...")
            await self._download_and_fill_data(
                db_coinpair, coinpair, start_time, end_time
            )
            
            # 重新检查完整性
            _, _, actual_count_after = await self._check_data_completeness(
                db_coinpair, start_time, end_time
            )
            logger.info(f"[HistoricalData] 补全后数据量: {actual_count_after}/{expected_count}")
        
        # 步骤5 & 6: 查询并聚合
        logger.info(f"[HistoricalData] 开始聚合数据到 {interval}...")
        aggregated_data = await self.aggregator.aggregate_candles(
            coin_pair=db_coinpair,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
        
        logger.info(f"[HistoricalData] 聚合完成,返回 {len(aggregated_data)} 条数据")
        
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
        """检查数据库中1m数据的完整性
        
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
        """下载并填充缺失的数据
        
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
            
            # 下载数据 (使用API格式的coinpair)
            candlestick_data = await exchange_service.get_historical_candlestick(
                coinpair=api_coinpair,
                interval='1min',
                since=start_time,
                use_cache=False,
                max_retries=config.get_max_retries()
            )
            
            if candlestick_data:
                # 过滤出在时间范围内的数据
                filtered_data = [
                    candle for candle in candlestick_data
                    if start_time <= candle['timestamp'] <= end_time
                ]
                
                logger.info(f"[数据下载] {db_coinpair}: 获取到 {len(filtered_data)} 条数据")
                
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
                        confirm=1  # 历史数据都是已确认的
                    )
                    candles_to_store.append(candle_obj)
                
                # 批量插入数据库
                if candles_to_store:
                    await self.db.insert_candles_batch(candles_to_store)
                    logger.info(f"[数据下载] {db_coinpair}: 成功存储 {len(candles_to_store)} 条数据")
                else:
                    logger.warning(f"[数据下载] {db_coinpair}: 没有符合条件的新数据")
            else:
                logger.warning(f"[数据下载] {db_coinpair}: 未能从交易所下载到数据")
                
        except Exception as e:
            logger.error(f"[数据下载] {db_coinpair}: 下载数据失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            # 不抛出异常,允许继续使用已有的不完整数据


# 创建全局实例
from app.db.database import db
from app.services.aggregator import DataAggregator

aggregator = DataAggregator(db)
historical_data_service = HistoricalDataService(db, aggregator)















