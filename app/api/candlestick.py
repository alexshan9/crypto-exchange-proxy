"""K线历史数据API模块"""
from fastapi import APIRouter, HTTPException, Query
from app.services.exchange_service import exchange_service


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
    description="获取指定交易对的历史K线数据，支持多种时间间隔"
)
async def get_historical_candlestick(
    interval: str = Query(..., description="K线间隔: 1m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d, 1w"),
    coinpair: str = Query(..., description="交易对，如BTC/USDT"),
    limit: int = Query(None, description="返回的K线数量，默认100，最大1000", ge=1, le=1000),
    since: int = Query(None, description="起始时间戳（毫秒），如果指定则忽略limit参数"),
):
    """获取历史K线数据
    
    Args:
        interval: K线间隔
        coinpair: 交易对
        limit: 返回的K线数量
        since: 起始时间戳
        
    Returns:
        K线数据响应
        
    Raises:
        HTTPException: 当请求参数错误或获取数据失败时
    """
    try:
        # 验证请求参数
        validated_interval = validate_interval(interval)
        validated_coinpair = validate_coinpair(coinpair)
        
        # 调用交易所服务获取数据
        candlestick_data = await exchange_service.get_historical_candlestick(
            coinpair=validated_coinpair,
            interval=validated_interval,
            limit=limit,
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
            }
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取K线数据失败: {str(e)}")

