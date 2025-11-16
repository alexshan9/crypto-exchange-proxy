"""FastAPI主应用"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import candlestick, websocket, data
import logging
import asyncio
from contextlib import asynccontextmanager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 全局变量
okx_collector = None
scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global okx_collector, scheduler

    # 启动时执行
    logger.info("=" * 50)
    logger.info("Crypto Exchange Proxy 正在启动...")

    # 初始化数据库
    from app.db.database import db
    await db.connect()
    await db.init_tables()

    # 检查是否有监控的交易对，如果没有则添加默认的
    watch_pairs = await db.get_watch_pairs(enabled_only=True)
    if not watch_pairs:
        logger.info("没有配置监控交易对，添加默认交易对...")
        await db.add_watch_pair("BTC-USDT", enabled=True)
        await db.add_watch_pair("ETH-USDT", enabled=True)
        watch_pairs = await db.get_watch_pairs(enabled_only=True)

    # 启动OKX数据收集器
    from app.services.okx_websocket import OKXCandleCollector
    coin_pairs = [pair.coin_pair for pair in watch_pairs]
    logger.info(f"启动OKX数据收集，监控交易对: {', '.join(coin_pairs)}")
    okx_collector = OKXCandleCollector(db, coin_pairs)

    # 在后台任务中启动收集器
    asyncio.create_task(okx_collector.start())

    # 执行历史数据完整性检查
    await _verify_historical_data_completeness(db, coin_pairs)

    # 启动定时任务调度器
    from app.services.scheduler import TaskScheduler
    scheduler = TaskScheduler(db)
    scheduler.start()

    logger.info("服务端口: 9100")
    logger.info("API文档: http://localhost:9100/docs")

    yield


# 创建FastAPI应用实例
app = FastAPI(
    title="Crypto Exchange Proxy",
    description="加密货币交易所代理服务，提供历史K线数据和实时ticker数据转发",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体的域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(candlestick.router)
app.include_router(websocket.router)
app.include_router(data.router)


@app.get("/", tags=["root"])
async def root():
    """根路径"""
    from fastapi.responses import HTMLResponse
    from pathlib import Path

    # 读取HTML模板文件
    template_path = Path(__file__).parent / "templates" / "dashboard.html"
    with open(template_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    return HTMLResponse(content=html_content, status_code=200)

@app.get("/api/watch-pairs")
async def get_watch_pairs():
    """获取当前监听的币对列表"""
    from app.db.database import db

    # 获取所有启用的币对
    watch_pairs = await db.get_watch_pairs(enabled_only=True)

    # 获取每个币对的数据统计
    pairs_with_stats = []
    for pair in watch_pairs:
        stats = await db.get_data_stats(pair.coin_pair)
        pairs_with_stats.append({
            "coin_pair": pair.coin_pair,
            "data_count": stats.get("total_count", 0),
            "first_data": stats.get("min_timestamp", None),
            "last_data": stats.get("max_timestamp", None)
        })

    return {
        "pairs": pairs_with_stats
    }

from fastapi import Form

@app.post("/api/watch-pairs")
async def add_watch_pair(coin_pair: str = Form(...)):
    """添加新的监听币对"""
    from app.db.database import db

    try:
        # 验证币对格式
        if "-" not in coin_pair:
            raise ValueError("币对格式错误，应为 'BASE-QUOTE' 格式，如 'BTC-USDT'")

        # 添加到数据库
        await db.add_watch_pair(coin_pair.upper(), enabled=True)

        return {"success": True, "message": f"已添加币对 {coin_pair.upper()}"}
    except Exception as e:
        return {"success": False, "message": str(e)}


@app.get("/health", tags=["health"])
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "service": "crypto-exchange-proxy"
    }


async def _verify_historical_data_completeness(db, coin_pairs):
    """验证历史数据完整性 - 30天1分钟数据"""
    logger.info("=" * 80)
    logger.info("开始验证历史数据完整性...")
    logger.info("=" * 80)

    from datetime import datetime, timedelta

    for coin_pair in coin_pairs:
        # 获取该交易对的数据统计
        stats = await db.get_data_stats(coin_pair)

        total_count = stats.get('total_count', 0)
        min_timestamp = stats.get('min_timestamp', None)
        max_timestamp = stats.get('max_timestamp', None)

        # 计算预期数据量
        expected_count = 30 * 24 * 60  # 30天 * 24小时 * 60分钟 = 43,200条

        logger.info(f"[数据验证] 交易对: {coin_pair}")

        # 检查基础数据是否存在
        if total_count == 0:
            logger.info(f"[数据验证]   ├─ 数据条数: 0 条")
            logger.info(f"[数据验证]   ├─ 预期条数: {expected_count:,} 条 (30天)")
            logger.info(f"[数据验证]   ├─ 完整性: 0.00%")
            logger.warning(f"[数据验证]   └─ 状态: ★ 没有历史数据，开始补全...")
            # 请求历史数据并填充
            await _request_historical_data(db, coin_pair)
        else:
            # 格式化时间显示
            min_date_str = datetime.fromtimestamp(min_timestamp / 1000).strftime('%Y-%m-%d %H:%M')
            max_date_str = datetime.fromtimestamp(max_timestamp / 1000).strftime('%Y-%m-%d %H:%M')
            
            # 计算完整性百分比
            completeness = (total_count / expected_count) * 100
            
            logger.info(f"[数据验证]   ├─ 最旧K线: {min_date_str}")
            logger.info(f"[数据验证]   ├─ 最新K线: {max_date_str}")
            logger.info(f"[数据验证]   ├─ 数据条数: {total_count:,} 条")
            logger.info(f"[数据验证]   ├─ 预期条数: {expected_count:,} 条 (30天)")
            logger.info(f"[数据验证]   ├─ 完整性: {completeness:.2f}%")
            
            # 检查是否完整覆盖30天
            if completeness < 95.0:  # 如果少于95%的预期数据
                logger.warning(f"[数据验证]   └─ 状态: ★ 数据不完整，开始补全...")
                # 请求历史数据并填充缺失段
                await _request_historical_data(db, coin_pair, expected_count - total_count)
                
                # 重新获取统计以显示更新后的结果
                updated_stats = await db.get_data_stats(coin_pair)
                updated_count = updated_stats.get('total_count', 0)
                updated_completeness = (updated_count / expected_count) * 100
                logger.info(f"[数据补全]   └─ 补全后完整性: {updated_completeness:.2f}% ({updated_count:,} 条)")
            else:
                logger.info(f"[数据验证]   └─ 状态: ✓ 数据基本完整")

    logger.info("=" * 80)
    logger.info("历史数据完整性检查完成")
    logger.info("=" * 80)
    return {"status": "completed", "coin_pairs": coin_pairs}


async def _request_historical_data(db, coin_pair, missing_count=None):
    """请求历史数据并填充缺失的部分
    
    Args:
        db: 数据库实例
        coin_pair: 交易对
        missing_count: 缺失的数据条数（可选）
    """
    from datetime import datetime, timedelta
    from app.db.models import CandleData
    from app.services.exchange_service import ExchangeService
    from app.config import config
    
    try:
        logger.info(f"[数据补全] {coin_pair}: 开始下载缺失的历史数据...")
        
        # 计算30天前的时间戳（毫秒）
        thirty_days_ago = int((datetime.now() - timedelta(days=30)).timestamp() * 1000)
        current_time = int(datetime.now().timestamp() * 1000)
        
        # 获取现有数据的时间范围
        stats = await db.get_data_stats(coin_pair)
        min_timestamp = stats.get('min_timestamp', None)
        max_timestamp = stats.get('max_timestamp', None)
        
        # 创建交易所服务实例
        exchange_type = config.get_exchange_type()
        exchange_service = ExchangeService(exchange_type)
        
        # 确定需要下载的时间范围
        # 策略：只补充从30天前到现有最旧数据之间的缺失部分
        download_start = None
        
        if min_timestamp is None:
            # 没有任何数据，下载全部30天
            download_start = thirty_days_ago
            start_date_str = datetime.fromtimestamp(thirty_days_ago / 1000).strftime('%Y-%m-%d %H:%M')
            end_date_str = datetime.fromtimestamp(current_time / 1000).strftime('%Y-%m-%d %H:%M')
            logger.info(f"[数据补全] {coin_pair}: 下载 {start_date_str} 至当前时间 的数据")
        else:
            # 有数据，检查是否需要补充前面的数据
            # 即使最旧的数据早于30天前，但如果完整性不足95%，也需要补全
            expected_count = 30 * 24 * 60
            current_completeness = (stats.get('total_count', 0) / expected_count) * 100
            
            if min_timestamp > thirty_days_ago:
                # 最旧的数据晚于30天前，需要补充
                download_start = thirty_days_ago
                start_date_str = datetime.fromtimestamp(download_start / 1000).strftime('%Y-%m-%d %H:%M')
                end_date_str = datetime.fromtimestamp(min_timestamp / 1000).strftime('%Y-%m-%d %H:%M')
                logger.info(f"[数据补全] {coin_pair}: 补充历史数据 {start_date_str} 至 {end_date_str}")
            elif current_completeness < 95.0:
                # 数据时间范围覆盖了30天，但完整性不足，可能有间隙
                # 重新下载30天的数据来填补间隙
                download_start = thirty_days_ago
                start_date_str = datetime.fromtimestamp(download_start / 1000).strftime('%Y-%m-%d %H:%M')
                logger.info(f"[数据补全] {coin_pair}: 数据有间隙（完整性{current_completeness:.2f}%），重新下载 {start_date_str} 以来的数据")
            else:
                logger.info(f"[数据补全] {coin_pair}: 数据完整且覆盖30天，无需补全")
        
        # 使用 exchange_service 下载数据
        if download_start:
            try:
                # 使用 exchange_service 的 get_historical_candlestick 方法
                # 注意：需要转换interval格式为 '1min'
                logger.info(f"[数据补全] {coin_pair}: 正在从交易所下载数据...")
                
                candlestick_data = await exchange_service.get_historical_candlestick(
                    coinpair=coin_pair,
                    interval='1min',
                    since=download_start,
                    use_cache=False,  # 历史数据补全不使用缓存
                    max_retries=config.get_max_retries()
                )
                
                if candlestick_data:
                    # 数据库会自动处理重复数据（ON CONFLICT DO UPDATE）
                    # 所以直接使用所有下载的数据即可
                    filtered_data = candlestick_data
                    
                    logger.info(f"[数据补全] {coin_pair}: 获取到 {len(filtered_data):,} 条数据")
                    
                    # 转换为CandleData对象
                    candles_to_store = []
                    for candle in filtered_data:
                        candle_obj = CandleData(
                            coin_pair=coin_pair,
                            timestamp=candle['timestamp'],
                            open=candle['open'],
                            high=candle['high'],
                            low=candle['low'],
                            close=candle['close'],
                            volume=candle['volume'],
                            volume_quote=candle.get('volume', candle['volume']),  # 使用volume作为volume_quote
                            confirm=1  # 历史数据都是已确认的
                        )
                        candles_to_store.append(candle_obj)
                    
                    # 批量插入数据库
                    if candles_to_store:
                        await db.insert_candles_batch(candles_to_store)
                        total_downloaded = len(candles_to_store)
                        logger.info(f"[数据补全] {coin_pair}: 补全完成，新增 {total_downloaded:,} 条数据")
                    else:
                        logger.warning(f"[数据补全] {coin_pair}: 没有符合条件的新数据")
                else:
                    logger.warning(f"[数据补全] {coin_pair}: 未能从交易所下载到数据")
                    
            except Exception as e:
                logger.error(f"[数据补全] {coin_pair}: 下载数据时发生错误: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
            
    except Exception as e:
        logger.error(f"[数据补全] {coin_pair}: 请求历史数据失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())


async def _startup_data_verification(db, coin_pairs):
    """项目启动时进行历史数据完整性检查"""
    logger.info("开始历史数据完整性检查（30天1分钟数据）")

    for coin_pair in coin_pairs:
        logger.info(f"检查交易对: {coin_pair}")

    return True