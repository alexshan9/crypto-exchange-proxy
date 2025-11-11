"""缓存工具模块"""
import time


class CandlestickCache:
    """K线数据缓存类"""
    
    # 根据不同的interval设置不同的缓存TTL（秒）
    INTERVAL_TTL = {
        '1m': 30,      # 1分钟K线缓存30秒
        '5m': 120,     # 5分钟K线缓存2分钟
        '15m': 300,    # 15分钟K线缓存5分钟
        '30m': 600,    # 30分钟K线缓存10分钟
        '1h': 600,     # 1小时K线缓存10分钟
        '2h': 600,     # 2小时K线缓存10分钟
        '4h': 600,     # 4小时K线缓存10分钟
        '8h': 600,     # 8小时K线缓存10分钟
        '1d': 600,     # 1天K线缓存10分钟
    }
    
    def __init__(self):
        # 缓存结构: {cache_key: (data, expiry_time)}
        self._cache = {}
    
    def _generate_key(self, exchange, symbol, interval, since=None, limit=None):
        """生成缓存键
        
        Args:
            exchange: 交易所名称
            symbol: 交易对
            interval: K线间隔
            since: 起始时间戳
            limit: 数量限制
            
        Returns:
            缓存键字符串
        """
        if since is not None:
            return f"{exchange}:{symbol}:{interval}:since:{since}"
        else:
            return f"{exchange}:{symbol}:{interval}:limit:{limit}"
    
    def get(self, exchange, symbol, interval, since=None, limit=None):
        """获取缓存数据
        
        Args:
            exchange: 交易所名称
            symbol: 交易对
            interval: K线间隔
            since: 起始时间戳
            limit: 数量限制
            
        Returns:
            缓存的数据，如果不存在或已过期则返回None
        """
        key = self._generate_key(exchange, symbol, interval, since, limit)
        
        if key not in self._cache:
            return None
        
        data, expiry_time = self._cache[key]
        
        # 检查是否过期
        if time.time() > expiry_time:
            # 删除过期缓存
            del self._cache[key]
            return None
        
        return data
    
    def set(self, data, exchange, symbol, interval, since=None, limit=None):
        """设置缓存数据
        
        Args:
            data: 要缓存的数据
            exchange: 交易所名称
            symbol: 交易对
            interval: K线间隔
            since: 起始时间戳
            limit: 数量限制
        """
        key = self._generate_key(exchange, symbol, interval, since, limit)
        
        # 获取对应interval的TTL，默认60秒
        ttl = self.INTERVAL_TTL.get(interval, 60)
        expiry_time = time.time() + ttl
        
        self._cache[key] = (data, expiry_time)
    
    def clear(self):
        """清空所有缓存"""
        self._cache.clear()
    
    def cleanup_expired(self):
        """清理所有过期的缓存"""
        current_time = time.time()
        expired_keys = [
            key for key, (_, expiry_time) in self._cache.items()
            if current_time > expiry_time
        ]
        
        for key in expired_keys:
            del self._cache[key]
        
        return len(expired_keys)


# 全局单例缓存实例
candlestick_cache = CandlestickCache()

