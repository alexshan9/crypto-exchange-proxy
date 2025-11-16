"""测试重构后的数据验证功能（使用 exchange_service）"""
import asyncio
import logging
from app.db.database import Database
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """主测试函数"""
    logger.info("=" * 80)
    logger.info("测试重构后的数据验证功能（使用 exchange_service）")
    logger.info("=" * 80)
    
    # 连接数据库
    db = Database("crypto_proxy.db")
    await db.connect()
    
    # 获取监控的交易对
    watch_pairs = await db.get_watch_pairs(enabled_only=True)
    coin_pairs = [pair.coin_pair for pair in watch_pairs]
    
    if not coin_pairs:
        logger.error("没有配置监控交易对")
        return
    
    logger.info(f"测试交易对: {', '.join(coin_pairs)}")
    
    # 显示当前数据统计
    logger.info("")
    logger.info("当前数据统计:")
    logger.info("-" * 80)
    
    for coin_pair in coin_pairs:
        stats = await db.get_data_stats(coin_pair)
        total_count = stats.get('total_count', 0)
        min_date = stats.get('min_date', 'N/A')
        max_date = stats.get('max_date', 'N/A')
        
        expected_count = 30 * 24 * 60
        completeness = (total_count / expected_count) * 100 if total_count > 0 else 0
        
        logger.info(f"交易对: {coin_pair}")
        logger.info(f"  数据条数: {total_count:,} 条")
        logger.info(f"  完整性: {completeness:.2f}%")
        logger.info(f"  时间范围: {min_date} ~ {max_date}")
        logger.info("")
    
    # 测试数据验证功能
    logger.info("=" * 80)
    logger.info("执行数据验证和补全...")
    logger.info("=" * 80)
    
    from app.main import _verify_historical_data_completeness
    result = await _verify_historical_data_completeness(db, coin_pairs[:1])  # 只测试第一个交易对
    
    logger.info("")
    logger.info(f"验证结果: {result}")
    
    # 再次显示数据统计
    logger.info("")
    logger.info("=" * 80)
    logger.info("补全后的数据统计:")
    logger.info("=" * 80)
    
    for coin_pair in coin_pairs[:1]:
        stats = await db.get_data_stats(coin_pair)
        total_count = stats.get('total_count', 0)
        min_date = stats.get('min_date', 'N/A')
        max_date = stats.get('max_date', 'N/A')
        
        expected_count = 30 * 24 * 60
        completeness = (total_count / expected_count) * 100 if total_count > 0 else 0
        
        logger.info(f"交易对: {coin_pair}")
        logger.info(f"  数据条数: {total_count:,} 条")
        logger.info(f"  预期数量: {expected_count:,} 条")
        logger.info(f"  完整性: {completeness:.2f}%")
        logger.info(f"  时间范围: {min_date} ~ {max_date}")
        logger.info("")
    
    await db.close()
    
    logger.info("=" * 80)
    logger.info("测试完成")
    logger.info("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())

