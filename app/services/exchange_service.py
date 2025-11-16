"""交易所服务模块"""
import ccxt
import time
import logging
from app.utils.cache import candlestick_cache

logger = logging.getLogger(__name__)


class ExchangeService:
    """交易所服务类，用于获取K线数据"""
    
    # interval映射：API格式 -> CCXT格式
    INTERVAL_MAPPING = {
        '1min': '1m',
        '5min': '5m',
        '15min': '15m',
        '30min': '30m',
        '1h': '1h',
        '2h': '2h',
        '4h': '4h',
        '6h': '6h',  # OKX支持6h，不支持8h
        '12h': '12h',
        '1d': '1d',
        '1w': '1w',
    }
    
    # 支持的interval列表
    SUPPORTED_INTERVALS = list(INTERVAL_MAPPING.keys())
    
    def __init__(self, exchange_name='binance'):
        """初始化交易所服务"""
        self.exchange_name = exchange_name
        self.exchange = self._create_exchange(exchange_name)
    
    def _create_exchange(self, exchange_name):
        """创建交易所实例"""
        exchange_class = getattr(ccxt, exchange_name)
        return exchange_class({
            'enableRateLimit': True,  # 启用速率限制
        })
    
    def _convert_interval(self, interval):
        """转换interval格式"""
        if interval not in self.INTERVAL_MAPPING:
            raise ValueError(
                f"不支持的interval: {interval}. "
                f"支持的值: {', '.join(self.SUPPORTED_INTERVALS)}"
            )
        return self.INTERVAL_MAPPING[interval]
    
    def _format_ohlcv_data(self, ohlcv_list):
        """格式化OHLCV数据"""
        formatted_data = []
        for ohlcv in ohlcv_list:
            formatted_data.append({
                'timestamp': ohlcv[0],
                'open': ohlcv[1],
                'high': ohlcv[2],
                'low': ohlcv[3],
                'close': ohlcv[4],
                'volume': ohlcv[5],
            })
        return formatted_data
    
    async def get_historical_candlestick(
        self,
        coinpair,
        interval,
        limit=None,
        since=None,
        use_cache=True,
        max_retries=3
    ):
        """获取历史K线数据，支持失败重试"""
        
        # 转换interval格式为CCXT格式
        ccxt_interval = self._convert_interval(interval)
        
        # 检查缓存
        if use_cache:
            cached_data = candlestick_cache.get(
                exchange=self.exchange_name,
                symbol=coinpair,
                interval=interval,
                since=since,
                limit=limit
            )
            if cached_data is not None:
                logger.info(f"从缓存获取数据: {coinpair}, {interval}")
                return cached_data
        
        # 带重试的数据获取
        retry_count = 0
        last_error = None
        
        while retry_count < max_retries:
            try:
                logger.info(f"获取K线数据 (尝试 {retry_count + 1}/{max_retries}): {coinpair}, {interval} (CCXT: {ccxt_interval}), limit={limit}")
                
                # 获取数据
                if since is not None:
                    # 如果指定了since，循环获取所有数据
                    all_data = []
                    current_since = since
                    
                    while True:
                        ohlcv = self.exchange.fetch_ohlcv(
                            symbol=coinpair,
                            timeframe=ccxt_interval,
                            since=current_since,
                            limit=1000
                        )
                        
                        if len(ohlcv) == 0:
                            break
                        
                        all_data.extend(ohlcv)
                        
                        # 更新since为最后一条数据的时间戳+1
                        current_since = ohlcv[-1][0] + 1
                        
                        # 如果获取的数据量小于请求的，说明已经是最新的了
                        # 但我们仍然需要检查是否还有更多数据
                        # 对于OKX，即使返回300条也可能还有更多数据
                        # 只有当返回0条或返回的最后一条时间戳没有变化时才停止
                        if len(ohlcv) < 100:  # 如果返回少于100条，可能已经到头了
                            break
                        
                        # 避免请求过快
                        rate_limit = self.exchange.rateLimit if self.exchange.rateLimit else 1000
                        time.sleep(rate_limit / 1000)
                        
                        logger.info(f"已获取 {len(all_data)} 条，继续获取...")
                    
                    formatted_data = self._format_ohlcv_data(all_data)
                else:
                    # 使用limit参数
                    ohlcv = self.exchange.fetch_ohlcv(
                        symbol=coinpair,
                        timeframe=ccxt_interval,
                        limit=limit or 100
                    )
                    formatted_data = self._format_ohlcv_data(ohlcv)
                
                # 缓存数据
                if use_cache:
                    candlestick_cache.set(
                        data=formatted_data,
                        exchange=self.exchange_name,
                        symbol=coinpair,
                        interval=interval,
                        since=since,
                        limit=limit
                    )
                
                logger.info(f"成功获取 {len(formatted_data)} 条K线数据")
                return formatted_data
                
            except ccxt.NetworkError as e:
                last_error = e
                retry_count += 1
                logger.warning(f"网络错误 (尝试 {retry_count}/{max_retries}): {str(e)}")
                if retry_count < max_retries:
                    wait_time = 2 ** retry_count  # 指数退避
                    logger.info(f"等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                    
            except ccxt.ExchangeError as e:
                last_error = e
                retry_count += 1
                logger.warning(f"交易所错误 (尝试 {retry_count}/{max_retries}): {str(e)}")
                if retry_count < max_retries:
                    wait_time = 2 ** retry_count
                    logger.info(f"等待 {wait_time} 秒后重试...")
                    time.sleep(wait_time)
                    
            except Exception as e:
                # 其他错误不重试，直接抛出
                import traceback
                logger.error(f"获取K线数据失败: {str(e)}")
                logger.error(f"详细错误: {traceback.format_exc()}")
                raise Exception(f"获取K线数据失败: {str(e)}")
        
        # 所有重试都失败
        error_msg = f"获取K线数据失败，已重试 {max_retries} 次: {str(last_error)}"
        logger.error(error_msg)
        raise Exception(error_msg)


# 全局单例交易所服务实例
from app.config import config
exchange_service = ExchangeService(config.get_exchange_type())

