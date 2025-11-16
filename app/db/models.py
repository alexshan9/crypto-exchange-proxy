"""数据库模型"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class CoinPairWatch:
    """监控交易对配置表"""
    id: Optional[int] = None
    coin_pair: str = ""  # 交易对，如 BTC-USDT
    enabled: bool = True  # 是否启用监控
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class CandleData:
    """K线数据表"""
    id: Optional[int] = None
    coin_pair: str = ""  # 交易对
    timestamp: int = 0  # 时间戳(毫秒)
    open: float = 0.0  # 开盘价
    high: float = 0.0  # 最高价
    low: float = 0.0  # 最低价
    close: float = 0.0  # 收盘价
    volume: float = 0.0  # 成交量(基础币)
    volume_quote: float = 0.0  # 成交额(计价币)
    confirm: int = 0  # 是否确认 (0=未完成, 1=已完成)
    created_at: Optional[str] = None
