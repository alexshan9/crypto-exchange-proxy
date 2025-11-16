"""数据库管理模块"""
import aiosqlite
import logging
from typing import List, Optional
from datetime import datetime, timedelta
from .models import CoinPairWatch, CandleData

logger = logging.getLogger(__name__)


class Database:
    """数据库管理类"""

    def __init__(self, db_path: str = "crypto_proxy.db"):
        """初始化数据库"""
        self.db_path = db_path
        self.db: Optional[aiosqlite.Connection] = None

    async def connect(self):
        """连接数据库"""
        self.db = await aiosqlite.connect(self.db_path)
        self.db.row_factory = aiosqlite.Row
        logger.info(f"数据库连接成功: {self.db_path}")

    async def close(self):
        """关闭数据库连接"""
        if self.db:
            await self.db.close()
            logger.info("数据库连接已关闭")

    async def init_tables(self):
        """初始化数据库表"""
        async with self.db.execute("""
            CREATE TABLE IF NOT EXISTS coin_pair_watch (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                coin_pair TEXT NOT NULL UNIQUE,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """):
            pass

        async with self.db.execute("""
            CREATE TABLE IF NOT EXISTS candle_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                coin_pair TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume REAL NOT NULL,
                volume_quote REAL NOT NULL,
                confirm INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(coin_pair, timestamp)
            )
        """):
            pass

        # 创建索引
        async with self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_candle_coin_pair
            ON candle_data(coin_pair)
        """):
            pass

        async with self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_candle_timestamp
            ON candle_data(timestamp)
        """):
            pass

        async with self.db.execute("""
            CREATE INDEX IF NOT EXISTS idx_candle_coin_timestamp
            ON candle_data(coin_pair, timestamp DESC)
        """):
            pass

        await self.db.commit()
        logger.info("数据库表初始化完成")

    # ========== coin_pair_watch 表操作 ==========

    async def add_watch_pair(self, coin_pair: str, enabled: bool = True) -> int:
        """添加监控交易对"""
        cursor = await self.db.execute(
            """
            INSERT INTO coin_pair_watch (coin_pair, enabled)
            VALUES (?, ?)
            ON CONFLICT(coin_pair) DO UPDATE SET
                enabled = excluded.enabled,
                updated_at = CURRENT_TIMESTAMP
            """,
            (coin_pair, 1 if enabled else 0)
        )
        await self.db.commit()
        logger.info(f"添加/更新监控交易对: {coin_pair}, enabled={enabled}")
        return cursor.lastrowid

    async def remove_watch_pair(self, coin_pair: str):
        """移除监控交易对"""
        await self.db.execute(
            "DELETE FROM coin_pair_watch WHERE coin_pair = ?",
            (coin_pair,)
        )
        await self.db.commit()
        logger.info(f"移除监控交易对: {coin_pair}")

    async def get_watch_pairs(self, enabled_only: bool = True) -> List[CoinPairWatch]:
        """获取监控交易对列表"""
        if enabled_only:
            sql = "SELECT * FROM coin_pair_watch WHERE enabled = 1"
        else:
            sql = "SELECT * FROM coin_pair_watch"

        async with self.db.execute(sql) as cursor:
            rows = await cursor.fetchall()
            return [
                CoinPairWatch(
                    id=row['id'],
                    coin_pair=row['coin_pair'],
                    enabled=bool(row['enabled']),
                    created_at=row['created_at'],
                    updated_at=row['updated_at']
                )
                for row in rows
            ]

    async def toggle_watch_pair(self, coin_pair: str, enabled: bool):
        """启用/禁用监控交易对"""
        await self.db.execute(
            """
            UPDATE coin_pair_watch
            SET enabled = ?, updated_at = CURRENT_TIMESTAMP
            WHERE coin_pair = ?
            """,
            (1 if enabled else 0, coin_pair)
        )
        await self.db.commit()
        logger.info(f"更新监控状态: {coin_pair}, enabled={enabled}")

    # ========== candle_data 表操作 ==========

    async def insert_candle(self, candle: CandleData):
        """插入K线数据（如果已存在则更新）"""
        try:
            logger.debug(f"[DB] 插入K线: {candle.coin_pair} @ {candle.timestamp}")
            
            cursor = await self.db.execute(
                """
                INSERT INTO candle_data
                (coin_pair, timestamp, open, high, low, close, volume, volume_quote, confirm)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(coin_pair, timestamp) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume,
                    volume_quote = excluded.volume_quote,
                    confirm = excluded.confirm
                """,
                (
                    candle.coin_pair,
                    candle.timestamp,
                    candle.open,
                    candle.high,
                    candle.low,
                    candle.close,
                    candle.volume,
                    candle.volume_quote,
                    candle.confirm
                )
            )
            await self.db.commit()
            
            # 记录是插入还是更新
            if cursor.rowcount > 0:
                logger.debug(f"[DB] ✓ K线数据已保存: {candle.coin_pair} @ {candle.timestamp}")
            else:
                logger.debug(f"[DB] ✓ K线数据已更新: {candle.coin_pair} @ {candle.timestamp}")
                
        except Exception as e:
            logger.error(f"[DB] ✗ 插入K线数据失败: {str(e)}", exc_info=True)
            logger.error(f"[DB]   - coin_pair: {candle.coin_pair}")
            logger.error(f"[DB]   - timestamp: {candle.timestamp}")
            raise

    async def insert_candles_batch(self, candles: List[CandleData]):
        """批量插入K线数据"""
        data = [
            (
                candle.coin_pair,
                candle.timestamp,
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                candle.volume,
                candle.volume_quote,
                candle.confirm
            )
            for candle in candles
        ]

        await self.db.executemany(
            """
            INSERT INTO candle_data
            (coin_pair, timestamp, open, high, low, close, volume, volume_quote, confirm)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(coin_pair, timestamp) DO UPDATE SET
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                volume = excluded.volume,
                volume_quote = excluded.volume_quote,
                confirm = excluded.confirm
            """,
            data
        )
        await self.db.commit()
        logger.info(f"批量插入 {len(candles)} 条K线数据")

    async def get_candles(
        self,
        coin_pair: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: Optional[int] = None
    ) -> List[CandleData]:
        """获取K线数据"""
        sql = "SELECT * FROM candle_data WHERE coin_pair = ?"
        params = [coin_pair]

        if start_time is not None:
            sql += " AND timestamp >= ?"
            params.append(start_time)

        if end_time is not None:
            sql += " AND timestamp <= ?"
            params.append(end_time)

        sql += " ORDER BY timestamp ASC"

        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)

        async with self.db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            return [
                CandleData(
                    id=row['id'],
                    coin_pair=row['coin_pair'],
                    timestamp=row['timestamp'],
                    open=row['open'],
                    high=row['high'],
                    low=row['low'],
                    close=row['close'],
                    volume=row['volume'],
                    volume_quote=row['volume_quote'],
                    confirm=row['confirm'],
                    created_at=row['created_at']
                )
                for row in rows
            ]

    async def get_latest_candle(self, coin_pair: str) -> Optional[CandleData]:
        """获取最新的K线数据"""
        async with self.db.execute(
            """
            SELECT * FROM candle_data
            WHERE coin_pair = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (coin_pair,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return CandleData(
                    id=row['id'],
                    coin_pair=row['coin_pair'],
                    timestamp=row['timestamp'],
                    open=row['open'],
                    high=row['high'],
                    low=row['low'],
                    close=row['close'],
                    volume=row['volume'],
                    volume_quote=row['volume_quote'],
                    confirm=row['confirm'],
                    created_at=row['created_at']
                )
            return None

    async def delete_old_candles(self, days: int = 30):
        """删除指定天数之前的K线数据

        Args:
            days: 保留最近多少天的数据，默认30天
        """
        # 计算截止时间戳（毫秒）
        cutoff_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)

        cursor = await self.db.execute(
            "DELETE FROM candle_data WHERE timestamp < ?",
            (cutoff_time,)
        )
        await self.db.commit()

        deleted_count = cursor.rowcount
        logger.info(f"清理旧数据完成，删除了 {deleted_count} 条记录（{days}天前的数据）")
        return deleted_count

    async def delete_candles_by_date(self, date_str: str):
        """删除指定日期的K线数据

        Args:
            date_str: 日期字符串，格式如 '2024-01-01'
        """
        # 解析日期
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        start_timestamp = int(date_obj.timestamp() * 1000)
        end_timestamp = int((date_obj + timedelta(days=1)).timestamp() * 1000)

        cursor = await self.db.execute(
            "DELETE FROM candle_data WHERE timestamp >= ? AND timestamp < ?",
            (start_timestamp, end_timestamp)
        )
        await self.db.commit()

        deleted_count = cursor.rowcount
        logger.info(f"删除 {date_str} 的数据，共 {deleted_count} 条")
        return deleted_count

    async def get_data_stats(self, coin_pair: str) -> dict:
        """获取数据统计信息"""
        async with self.db.execute(
            """
            SELECT
                COUNT(*) as total_count,
                MIN(timestamp) as min_timestamp,
                MAX(timestamp) as max_timestamp
            FROM candle_data
            WHERE coin_pair = ?
            """,
            (coin_pair,)
        ) as cursor:
            row = await cursor.fetchone()
            if row and row['total_count'] > 0:
                return {
                    'total_count': row['total_count'],
                    'min_timestamp': row['min_timestamp'],
                    'max_timestamp': row['max_timestamp'],
                    'min_date': datetime.fromtimestamp(row['min_timestamp'] / 1000).strftime('%Y-%m-%d %H:%M:%S'),
                    'max_date': datetime.fromtimestamp(row['max_timestamp'] / 1000).strftime('%Y-%m-%d %H:%M:%S')
                }
            return {
                'total_count': 0,
                'min_timestamp': None,
                'max_timestamp': None,
                'min_date': None,
                'max_date': None
            }


# 全局数据库实例
db = Database()
