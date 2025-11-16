"""数据查询API端点"""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/data", tags=["data"])


@router.get("/candles")
async def get_candles(
    coin_pair: str = Query(..., description="交易对，如 BTC-USDT"),
    interval: str = Query("1m", description="时间周期，如 1m, 5m, 15m, 30m, 1h, 4h, 1d"),
    limit: int = Query(100, description="返回数量限制", ge=1, le=1000),
    start_time: Optional[int] = Query(None, description="开始时间戳（毫秒）"),
    end_time: Optional[int] = Query(None, description="结束时间戳（毫秒）")
) -> Dict:
    """获取K线数据（从数据库）

    支持多种时间周期的聚合数据
    """
    try:
        from app.db.database import db
        from app.services.aggregator import DataAggregator

        # 创建聚合器
        aggregator = DataAggregator(db)

        # 获取数据
        if start_time is not None or end_time is not None:
            # 按时间范围查询
            if start_time is None:
                start_time = int((datetime.now() - timedelta(days=1)).timestamp() * 1000)
            if end_time is None:
                end_time = int(datetime.now().timestamp() * 1000)

            candles = await aggregator.get_candles_by_time_range(
                coin_pair=coin_pair,
                interval=interval,
                start_time=start_time,
                end_time=end_time
            )
        else:
            # 获取最新的N条数据
            candles = await aggregator.get_latest_candles(
                coin_pair=coin_pair,
                interval=interval,
                limit=limit
            )

        return {
            "code": 0,
            "message": "success",
            "data": {
                "coin_pair": coin_pair,
                "interval": interval,
                "count": len(candles),
                "candles": candles
            }
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"获取K线数据失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取K线数据失败: {str(e)}")


@router.get("/stats")
async def get_stats(coin_pair: str = Query(..., description="交易对")) -> Dict:
    """获取数据统计信息"""
    try:
        from app.db.database import db
        from app.services.aggregator import DataAggregator

        aggregator = DataAggregator(db)
        stats = await aggregator.get_stats(coin_pair)

        return {
            "code": 0,
            "message": "success",
            "data": stats
        }

    except Exception as e:
        logger.error(f"获取统计信息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")


@router.get("/watch-pairs")
async def get_watch_pairs() -> Dict:
    """获取监控的交易对列表及其统计数据"""
    try:
        from app.db.database import db
        from app.services.aggregator import DataAggregator

        watch_pairs = await db.get_watch_pairs(enabled_only=False)
        aggregator = DataAggregator(db)

        pairs_with_stats = []

        for pair in watch_pairs:
            # 获取每个交易对的统计数据
            stats = await aggregator.get_stats(pair.coin_pair)

            # 格式化时间戳为 yyyy-MM-DD HH:mm
            first_data_formatted = None
            last_data_formatted = None

            if stats['min_timestamp']:
                first_data_formatted = datetime.fromtimestamp(stats['min_timestamp'] / 1000).strftime('%Y-%m-%d %H:%M')
            if stats['max_timestamp']:
                last_data_formatted = datetime.fromtimestamp(stats['max_timestamp'] / 1000).strftime('%Y-%m-%d %H:%M')

            pairs_with_stats.append({
                "id": pair.id,
                "coin_pair": pair.coin_pair,
                "enabled": pair.enabled,
                "created_at": pair.created_at,
                "updated_at": pair.updated_at,
                "data_count": stats['total_count'],
                "first_data": stats['min_timestamp'],
                "last_data": stats['max_timestamp'],
                "first_data_formatted": first_data_formatted,
                "last_data_formatted": last_data_formatted
            })

        return {
            "code": 0,
            "message": "success",
            "pairs": pairs_with_stats
        }

    except Exception as e:
        logger.error(f"获取监控列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取监控列表失败: {str(e)}")


@router.post("/watch-pairs")
async def add_watch_pair(
    coin_pair: str = Query(..., description="交易对，如 BTC-USDT"),
    enabled: bool = Query(True, description="是否启用")
) -> Dict:
    """添加监控交易对"""
    try:
        from app.db.database import db
        from app.main import okx_collector

        # 添加到数据库
        await db.add_watch_pair(coin_pair, enabled)

        # 如果启用，添加到收集器
        if enabled and okx_collector:
            await okx_collector.add_watch_pair(coin_pair)

        return {
            "code": 0,
            "message": "success",
            "data": {
                "coin_pair": coin_pair,
                "enabled": enabled
            }
        }

    except Exception as e:
        logger.error(f"添加监控交易对失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"添加监控交易对失败: {str(e)}")


@router.delete("/watch-pairs")
async def remove_watch_pair(coin_pair: str = Query(..., description="交易对")) -> Dict:
    """移除监控交易对"""
    try:
        from app.db.database import db
        from app.main import okx_collector

        # 从数据库删除
        await db.remove_watch_pair(coin_pair)

        # 从收集器移除
        if okx_collector:
            await okx_collector.remove_watch_pair(coin_pair)

        return {
            "code": 0,
            "message": "success",
            "data": {
                "coin_pair": coin_pair
            }
        }

    except Exception as e:
        logger.error(f"移除监控交易对失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"移除监控交易对失败: {str(e)}")


@router.put("/watch-pairs/toggle")
async def toggle_watch_pair(
    coin_pair: str = Query(..., description="交易对"),
    enabled: bool = Query(..., description="是否启用")
) -> Dict:
    """启用/禁用监控交易对"""
    try:
        from app.db.database import db
        from app.main import okx_collector

        # 更新数据库
        await db.toggle_watch_pair(coin_pair, enabled)

        # 更新收集器
        if okx_collector:
            if enabled:
                await okx_collector.add_watch_pair(coin_pair)
            else:
                await okx_collector.remove_watch_pair(coin_pair)

        return {
            "code": 0,
            "message": "success",
            "data": {
                "coin_pair": coin_pair,
                "enabled": enabled
            }
        }

    except Exception as e:
        logger.error(f"更新监控状态失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"更新监控状态失败: {str(e)}")
