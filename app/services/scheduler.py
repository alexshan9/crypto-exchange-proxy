"""定时任务调度器"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class TaskScheduler:
    """定时任务调度器"""

    def __init__(self, db):
        """初始化调度器

        Args:
            db: 数据库实例
        """
        self.db = db
        self.scheduler = AsyncIOScheduler()

    async def cleanup_old_data(self):
        """清理30天前的旧数据"""
        try:
            logger.info("开始执行数据清理任务...")

            # 删除30天前的数据
            deleted_count = await self.db.delete_old_candles(days=30)

            logger.info(f"数据清理任务完成，删除了 {deleted_count} 条记录")

        except Exception as e:
            logger.error(f"数据清理任务失败: {str(e)}")

    def start(self):
        """启动调度器"""
        # 每天凌晨2点执行数据清理
        self.scheduler.add_job(
            self.cleanup_old_data,
            'cron',
            hour=2,
            minute=0,
            id='cleanup_old_data',
            replace_existing=True
        )

        # 启动调度器
        self.scheduler.start()
        logger.info("定时任务调度器已启动")
        logger.info("- 数据清理任务：每天凌晨2:00执行")

    def stop(self):
        """停止调度器"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("定时任务调度器已停止")

    def trigger_cleanup_now(self):
        """立即触发清理任务（用于测试）"""
        self.scheduler.add_job(
            self.cleanup_old_data,
            'date',
            run_date=datetime.now() + timedelta(seconds=1),
            id='cleanup_old_data_now'
        )
        logger.info("已触发立即清理任务")
