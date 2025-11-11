"""WebSocket管理器模块"""
import asyncio
import json
import logging
import websockets
from fastapi import WebSocket

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WebSocketManager:
    """WebSocket连接管理器（单例模式）"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """初始化WebSocket管理器"""
        if self._initialized:
            return
        
        self.clients = set()
        self.okx_connection = None
        self.is_running = False
        self._okx_task = None
        self._lock = asyncio.Lock()
        self._initialized = True
        
        # OKX WebSocket配置
        self.okx_url = "wss://ws.okx.com:8443/ws/v5/public"
        self.subscribe_msg = {
            "op": "subscribe",
            "args": [
                {
                    "channel": "tickers",
                    "instId": "BTC-USDT"
                }
            ]
        }
    
    async def connect_client(self, websocket):
        """连接客户端"""
        async with self._lock:
            self.clients.add(websocket)
            logger.info(f"客户端已连接，当前连接数: {len(self.clients)}")
            
            # 如果这是第一个客户端，启动OKX连接
            if len(self.clients) == 1 and not self.is_running:
                await self._connect_to_okx()
    
    async def disconnect_client(self, websocket):
        """断开客户端连接"""
        async with self._lock:
            self.clients.discard(websocket)
            logger.info(f"客户端已断开，当前连接数: {len(self.clients)}")
            
            # 如果没有客户端了，断开OKX连接
            if len(self.clients) == 0 and self.is_running:
                await self._disconnect_from_okx()
    
    async def _connect_to_okx(self):
        """连接到OKX WebSocket"""
        if self.is_running:
            logger.warning("OKX连接已经在运行中")
            return
        
        try:
            logger.info("正在连接到OKX WebSocket...")
            self.is_running = True
            
            # 创建异步任务来处理OKX消息
            self._okx_task = asyncio.create_task(self._okx_message_handler())
            
            logger.info("已启动OKX消息处理任务")
            
        except Exception as e:
            logger.error(f"连接OKX失败: {e}")
            self.is_running = False
            raise
    
    async def _disconnect_from_okx(self):
        """断开OKX WebSocket连接"""
        if not self.is_running:
            logger.warning("OKX连接未运行")
            return
        
        logger.info("正在断开OKX连接...")
        self.is_running = False
        
        # 取消消息处理任务
        if self._okx_task and not self._okx_task.done():
            self._okx_task.cancel()
            try:
                await self._okx_task
            except asyncio.CancelledError:
                logger.info("OKX消息处理任务已取消")
        
        # 关闭OKX连接
        if self.okx_connection and not self.okx_connection.closed:
            await self.okx_connection.close()
            self.okx_connection = None
        
        logger.info("OKX连接已断开")
    
    async def _okx_message_handler(self):
        """OKX消息处理器"""
        retry_count = 0
        max_retries = 5
        
        while self.is_running and retry_count < max_retries:
            try:
                async with websockets.connect(self.okx_url) as websocket:
                    self.okx_connection = websocket
                    logger.info("已连接到OKX WebSocket")
                    
                    # 发送订阅消息
                    await websocket.send(json.dumps(self.subscribe_msg))
                    logger.info("已发送订阅请求")
                    
                    # 重置重试计数
                    retry_count = 0
                    
                    # 持续接收消息
                    while self.is_running:
                        try:
                            response = await asyncio.wait_for(
                                websocket.recv(),
                                timeout=30.0  # 30秒超时
                            )
                            data = json.loads(response)
                            
                            # 只广播ticker数据，过滤订阅确认消息
                            if 'data' in data:
                                await self.broadcast(data)
                            elif 'event' in data:
                                logger.info(f"OKX事件: {data}")
                            
                        except asyncio.TimeoutError:
                            # 发送ping保持连接
                            logger.debug("发送ping消息")
                            await websocket.ping()
                        
            except websockets.exceptions.WebSocketException as e:
                retry_count += 1
                logger.error(f"OKX WebSocket错误 (重试 {retry_count}/{max_retries}): {e}")
                if retry_count < max_retries and self.is_running:
                    await asyncio.sleep(2 ** retry_count)  # 指数退避
            except asyncio.CancelledError:
                logger.info("OKX消息处理被取消")
                break
            except Exception as e:
                logger.error(f"OKX消息处理错误: {e}")
                break
        
        if retry_count >= max_retries:
            logger.error("达到最大重试次数，停止连接OKX")
            self.is_running = False
    
    async def broadcast(self, data):
        """广播数据到所有客户端"""
        if not self.clients:
            return
        
        message = json.dumps(data)
        
        # 移除断开的客户端
        disconnected_clients = set()
        
        for client in self.clients:
            try:
                await client.send_text(message)
            except Exception as e:
                logger.error(f"发送消息到客户端失败: {e}")
                disconnected_clients.add(client)
        
        # 清理断开的客户端
        if disconnected_clients:
            async with self._lock:
                self.clients -= disconnected_clients
                logger.info(f"清理了 {len(disconnected_clients)} 个断开的客户端")
                
                # 如果没有客户端了，断开OKX
                if len(self.clients) == 0 and self.is_running:
                    await self._disconnect_from_okx()


# 全局单例WebSocket管理器实例
ws_manager = WebSocketManager()

