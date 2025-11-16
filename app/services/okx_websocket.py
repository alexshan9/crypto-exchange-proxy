"""OKX WebSocket 客户端"""
import asyncio
import json
import logging
import websockets
from typing import Callable, Optional, List, Dict
from datetime import datetime

logger = logging.getLogger(__name__)


class OKXWebSocketClient:
    """OKX WebSocket 客户端"""

    # WebSocket连接地址 - K线数据需要使用business URL
    WS_URL = "wss://ws.okx.com:8443/ws/v5/business"

    def __init__(self):
        """初始化WebSocket客户端"""
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.subscriptions: Dict[str, Callable] = {}  # channel+instId -> callback
        self.running = False
        self.reconnect_delay = 5  # 重连延迟（秒）

    async def connect(self):
        """连接到OKX WebSocket"""
        try:
            logger.info(f"正在连接到OKX WebSocket: {self.WS_URL}")
            self.ws = await websockets.connect(
                self.WS_URL,
                ping_interval=20,  # 每20秒发送ping
                ping_timeout=10,
            )
            logger.info(f"✓ 成功连接到OKX WebSocket: {self.WS_URL}")
            logger.info(f"  - WebSocket状态: {'已连接' if self.ws else '未连接'}")
            return True
        except Exception as e:
            logger.error(f"✗ 连接OKX WebSocket失败: {str(e)}", exc_info=True)
            return False

    async def disconnect(self):
        """断开连接"""
        self.running = False
        if self.ws:
            await self.ws.close()
            logger.info("OKX WebSocket连接已关闭")

    async def subscribe(self, channels: List[Dict], callback: Callable):
        """订阅频道

        Args:
            channels: 订阅频道列表，例如 [{'channel': 'candle1m', 'instId': 'BTC-USDT'}]
            callback: 数据回调函数
        """
        if not self.ws:
            logger.error("✗ WebSocket未连接，无法订阅")
            logger.debug(f"  - 尝试订阅的频道: {channels}")
            return False

        # 构造订阅消息
        subscribe_msg = {
            "op": "subscribe",
            "args": channels
        }

        try:
            logger.info(f"→ 发送订阅请求...")
            logger.info(f"  - 频道数量: {len(channels)}")
            for ch in channels:
                logger.info(f"  - {ch['channel']}: {ch['instId']}")
            
            await self.ws.send(json.dumps(subscribe_msg))
            logger.debug(f"  - 订阅消息: {subscribe_msg}")

            # 保存订阅信息
            for channel in channels:
                key = f"{channel['channel']}:{channel['instId']}"
                self.subscriptions[key] = callback
                logger.debug(f"  - 已保存订阅: {key}")

            logger.info(f"✓ 订阅请求已发送，等待服务器确认...")
            return True
        except Exception as e:
            logger.error(f"✗ 订阅失败: {str(e)}", exc_info=True)
            return False

    async def unsubscribe(self, channels: List[Dict]):
        """取消订阅

        Args:
            channels: 取消订阅频道列表
        """
        if not self.ws:
            logger.error("WebSocket未连接，无法取消订阅")
            return False

        unsubscribe_msg = {
            "op": "unsubscribe",
            "args": channels
        }

        try:
            await self.ws.send(json.dumps(unsubscribe_msg))
            logger.info(f"已取消订阅: {channels}")

            # 移除订阅信息
            for channel in channels:
                key = f"{channel['channel']}:{channel['instId']}"
                if key in self.subscriptions:
                    del self.subscriptions[key]

            return True
        except Exception as e:
            logger.error(f"取消订阅失败: {str(e)}")
            return False

    async def _handle_message(self, message: str):
        """处理接收到的消息"""
        try:
            # 解析JSON
            data = json.loads(message)
            logger.debug(f"← 收到消息: {message[:200]}...")  # 只记录前200字符

            # 处理事件消息（订阅成功等）
            if "event" in data:
                event = data["event"]
                if event == "subscribe":
                    arg = data.get('arg', {})
                    logger.info(f"✓ 订阅成功: {arg.get('channel')}:{arg.get('instId')}")
                elif event == "unsubscribe":
                    arg = data.get('arg', {})
                    logger.info(f"✓ 取消订阅成功: {arg.get('channel')}:{arg.get('instId')}")
                elif event == "error":
                    error_msg = data.get('msg', 'Unknown error')
                    error_code = data.get('code', 'N/A')
                    logger.error(f"✗ OKX服务器错误 [{error_code}]: {error_msg}")
                return

            # 处理数据推送
            if "arg" in data and "data" in data:
                arg = data["arg"]
                channel = arg.get("channel", "")
                inst_id = arg.get("instId", "")
                key = f"{channel}:{inst_id}"
                data_count = len(data["data"])

                logger.debug(f"← 数据推送: {key}, 数据条数: {data_count}")

                # 调用对应的回调函数
                if key in self.subscriptions:
                    callback = self.subscriptions[key]
                    await callback(data)
                else:
                    logger.warning(f"⚠ 收到未订阅频道的数据: {key}")
                    logger.debug(f"  - 当前订阅: {list(self.subscriptions.keys())}")

        except json.JSONDecodeError as e:
            logger.error(f"✗ JSON解析失败: {str(e)}")
            logger.error(f"  - 原始消息: {message[:500]}")
        except Exception as e:
            logger.error(f"✗ 处理消息失败: {str(e)}", exc_info=True)
            logger.error(f"  - 消息内容: {message[:500]}")

    async def start(self):
        """启动WebSocket监听（带自动重连）"""
        self.running = True

        while self.running:
            try:
                # 连接
                if not await self.connect():
                    logger.warning(f"连接失败，{self.reconnect_delay}秒后重试...")
                    await asyncio.sleep(self.reconnect_delay)
                    continue

                # 如果有之前的订阅，重新订阅
                if self.subscriptions:
                    logger.info(f"检测到 {len(self.subscriptions)} 个待订阅频道，开始订阅...")
                    
                    # 按callback分组订阅（支持不同频道使用不同callback）
                    callback_groups = {}
                    for key, callback in self.subscriptions.items():
                        callback_id = id(callback)
                        if callback_id not in callback_groups:
                            callback_groups[callback_id] = {'callback': callback, 'channels': []}
                        
                        channel, inst_id = key.split(":", 1)
                        callback_groups[callback_id]['channels'].append({
                            "channel": channel,
                            "instId": inst_id
                        })
                    
                    # 对每组callback执行订阅
                    for callback_id, group in callback_groups.items():
                        await self.subscribe(group['channels'], group['callback'])

                # 接收消息
                async for message in self.ws:
                    await self._handle_message(message)

            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"WebSocket连接关闭: {str(e)}")
                if self.running:
                    logger.info(f"{self.reconnect_delay}秒后尝试重连...")
                    await asyncio.sleep(self.reconnect_delay)
            except Exception as e:
                logger.error(f"WebSocket运行错误: {str(e)}")
                if self.running:
                    logger.info(f"{self.reconnect_delay}秒后尝试重连...")
                    await asyncio.sleep(self.reconnect_delay)

        logger.info("OKX WebSocket客户端已停止")

    async def send_ping(self):
        """发送心跳（OKX使用标准WebSocket ping/pong）"""
        if self.ws:
            try:
                await self.ws.ping()
            except Exception as e:
                logger.error(f"发送ping失败: {str(e)}")


class OKXCandleCollector:
    """OKX K线数据收集器"""

    def __init__(self, db, watch_pairs: List[str]):
        """初始化收集器

        Args:
            db: 数据库实例
            watch_pairs: 监控的交易对列表，如 ['BTC-USDT', 'ETH-USDT']
        """
        self.db = db
        self.watch_pairs = watch_pairs
        self.client = OKXWebSocketClient()
        self.running = False

    async def _candle_callback(self, data: Dict):
        """K线数据回调函数"""
        try:
            arg = data["arg"]
            channel = arg["channel"]
            inst_id = arg["instId"]
            
            logger.debug(f"[K线回调] 处理 {inst_id} 的数据，数据条数: {len(data['data'])}")

            for candle_data in data["data"]:
                # candle格式: [timestamp, open, high, low, close, volume, volumeCcy, volumeCcyQuote, confirm]
                timestamp = int(candle_data[0])
                open_price = float(candle_data[1])
                high_price = float(candle_data[2])
                low_price = float(candle_data[3])
                close_price = float(candle_data[4])
                volume = float(candle_data[5])
                volume_quote = float(candle_data[7]) if len(candle_data) > 7 else 0.0
                confirm = int(candle_data[8]) if len(candle_data) > 8 else 0

                # 只保存已确认的K线（完整的1分钟K线）
                if confirm != 1:
                    logger.debug(f"[K线跳过] {inst_id} - 未确认的K线，timestamp={timestamp}, confirm={confirm}")
                    continue

                logger.debug(f"[K线解析] {inst_id} - timestamp={timestamp}, confirm={confirm}")

                # 导入模型
                from app.db.models import CandleData

                # 创建K线数据对象
                candle = CandleData(
                    coin_pair=inst_id,
                    timestamp=timestamp,
                    open=open_price,
                    high=high_price,
                    low=low_price,
                    close=close_price,
                    volume=volume,
                    volume_quote=volume_quote,
                    confirm=confirm
                )

                # 保存到数据库
                logger.debug(f"[K线存储] 准备保存到数据库: {inst_id} @ {timestamp}")
                await self.db.insert_candle(candle)
                logger.debug(f"[K线存储] ✓ 已保存: {inst_id} @ {timestamp}")

                # 记录已确认K线的日志
                time_str = datetime.fromtimestamp(timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S')
                logger.info(
                    f"💹 [K线已保存] {inst_id} {time_str} "
                    f"O:{open_price:.2f} H:{high_price:.2f} L:{low_price:.2f} C:{close_price:.2f} V:{volume:.4f}"
                )

        except Exception as e:
            logger.error(f"✗ 处理K线数据失败: {str(e)}", exc_info=True)
            logger.error(f"  - 数据内容: {data}")

    async def start(self):
        """启动数据收集"""
        self.running = True
        logger.info(f"═══════════════════════════════════════════════")
        logger.info(f"启动OKX K线数据收集器")
        logger.info(f"  - 监控交易对数量: {len(self.watch_pairs)}")
        logger.info(f"  - 监控交易对列表: {', '.join(self.watch_pairs)}")
        logger.info(f"  - K线级别: 1分钟 (candle1m)")
        logger.info(f"═══════════════════════════════════════════════")

        # 预先保存订阅信息（不发送订阅请求，等待连接后自动订阅）
        # 注意：OKX的K线频道名称格式为 candle + 时间单位，如 candle1m, candle5m, candle1H 等
        logger.info(f"→ 预注册订阅信息...")
        for pair in self.watch_pairs:
            key = f"candle1m:{pair}"  # 1分钟K线使用小写m
            self.client.subscriptions[key] = self._candle_callback
            logger.info(f"  - 已注册: {key}")
        
        logger.info(f"✓ 订阅信息已预注册，总计 {len(self.client.subscriptions)} 个频道")
        logger.info(f"→ 启动WebSocket连接...")

        # 启动WebSocket监听（连接成功后会自动触发订阅）
        await self.client.start()

    async def stop(self):
        """停止数据收集"""
        self.running = False
        logger.info("停止OKX K线数据收集器")
        await self.client.disconnect()

    async def add_watch_pair(self, coin_pair: str):
        """添加监控交易对"""
        if coin_pair not in self.watch_pairs:
            logger.info(f"→ 添加监控交易对: {coin_pair}")
            self.watch_pairs.append(coin_pair)
            
            # 订阅新的交易对
            success = await self.client.subscribe(
                [{"channel": "candle1m", "instId": coin_pair}],
                self._candle_callback
            )
            
            if success:
                logger.info(f"✓ 成功添加监控交易对: {coin_pair}")
            else:
                logger.error(f"✗ 添加监控交易对失败: {coin_pair}")
                self.watch_pairs.remove(coin_pair)  # 回滚
        else:
            logger.warning(f"⚠ 交易对已在监控列表中: {coin_pair}")

    async def remove_watch_pair(self, coin_pair: str):
        """移除监控交易对"""
        if coin_pair in self.watch_pairs:
            logger.info(f"→ 移除监控交易对: {coin_pair}")
            
            # 取消订阅
            success = await self.client.unsubscribe(
                [{"channel": "candle1m", "instId": coin_pair}]
            )
            
            if success:
                self.watch_pairs.remove(coin_pair)
                logger.info(f"✓ 成功移除监控交易对: {coin_pair}")
            else:
                logger.error(f"✗ 移除监控交易对失败: {coin_pair}")
        else:
            logger.warning(f"⚠ 交易对不在监控列表中: {coin_pair}")
