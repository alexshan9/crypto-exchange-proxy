"""K线历史数据API模块"""
from fastapi import APIRouter, HTTPException, Query
from app.services.exchange_service import exchange_service
from app.services.historical_data_service import historical_data_service
import logging

logger = logging.getLogger(__name__)


# 请求验证辅助函数
def validate_interval(interval):
    """验证interval参数"""
    supported_intervals = ['1m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d', '1w']
    if interval not in supported_intervals:
        raise ValueError(
            f"不支持的interval: {interval}. "
            f"支持的值: {', '.join(supported_intervals)}"
        )
    return interval

def validate_coinpair(coinpair):
    """验证coinpair参数"""
    if '/' not in coinpair:
        raise ValueError("coinpair格式错误，应为 'BASE/QUOTE' 格式，如 'BTC/USDT'")
    return coinpair.upper()


# 创建路由
router = APIRouter(prefix="/candlestick", tags=["candlestick"])


@router.get(
    "/historical",
    summary="获取历史K线数据",
    description="获取指定交易对的历史K线数据，支持多种时间间隔。优先从数据库查询1m数据并聚合，数据不足时自动从交易所下载补全。"
)
async def get_historical_candlestick(
    interval: str = Query(..., description="K线间隔: 1m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d, 1w"),
    coinpair: str = Query(..., description="交易对，如BTC/USDT"),
    limit: int = Query(None, description="返回的K线数量，默认100，最大1000", ge=1, le=1000),
    since: int = Query(None, description="起始时间戳（毫秒），如果指定则忽略limit参数"),
):
    """获取历史K线数据
    
    新的数据获取流程:
    1. 优先从数据库查询1m K线数据
    2. 检查数据完整性 (95%阈值)
    3. 如果数据不足,从交易所下载补全到数据库
    4. 从数据库聚合为目标interval
    5. 返回聚合后的数据
    
    Args:
        interval: K线间隔
        coinpair: 交易对 (格式: BTC/USDT)
        limit: 返回的K线数量 (如果不指定since)
        since: 起始时间戳 (如果指定则忽略limit)
        
    Returns:
        K线数据响应
        
    Raises:
        HTTPException: 当请求参数错误或获取数据失败时
    """
    try:
        # 验证请求参数
        validated_interval = validate_interval(interval)
        validated_coinpair = validate_coinpair(coinpair)
        
        logger.info(f"[API] 历史K线请求: {validated_coinpair}, {validated_interval}, limit={limit}, since={since}")
        
        # 使用新的历史数据服务获取数据
        # 该服务会自动处理: DB查询 -> 完整性检查 -> 下载补全 -> 聚合返回
        candlestick_data = await historical_data_service.get_candlestick_data(
            coinpair=validated_coinpair,
            interval=validated_interval,
            limit=limit or 100,  # 默认100条
            since=since
        )
        
        # 构造响应
        return {
            "success": True,
            "data": candlestick_data,
            "count": len(candlestick_data),
            "request": {
                "interval": validated_interval,
                "coinpair": validated_coinpair,
                "limit": limit,
                "since": since,
            },
            "source": "database",  # 数据来源标记
        }
        
    except ValueError as e:
        logger.error(f"[API] 参数验证失败: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[API] 获取K线数据失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"获取K线数据失败: {str(e)}")

