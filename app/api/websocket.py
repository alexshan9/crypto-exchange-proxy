"""WebSocket转发API模块"""
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.websocket_manager import ws_manager

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建路由
router = APIRouter(tags=["websocket"])


@router.websocket("/ws/ticker")
async def websocket_ticker_endpoint(websocket: WebSocket):
    """WebSocket ticker数据转发端点
    
    客户端连接到此端点后，会自动接收来自OKX的实时ticker数据。
    当第一个客户端连接时，会自动建立到OKX的WebSocket连接。
    当最后一个客户端断开时，会自动断开OKX连接以节省资源。
    
    Args:
        websocket: FastAPI WebSocket连接对象
    """
    # 接受WebSocket连接
    await websocket.accept()
    logger.info(f"新的WebSocket连接: {websocket.client}")
    
    try:
        # 将客户端添加到管理器
        await ws_manager.connect_client(websocket)
        
        # 发送欢迎消息
        await websocket.send_json({
            "event": "connected",
            "message": "已连接到crypto-exchange-proxy，正在接收OKX BTC-USDT ticker数据"
        })
        
        # 保持连接，等待客户端断开
        # WebSocket管理器会自动广播数据到所有连接的客户端
        while True:
            # 接收客户端消息（如果有的话）
            # 这里我们不处理客户端发送的消息，只是保持连接活跃
            data = await websocket.receive_text()
            
            # 可以在这里处理客户端发送的消息
            # 例如：切换交易对、订阅不同的频道等
            logger.debug(f"收到客户端消息: {data}")
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket连接断开: {websocket.client}")
    except Exception as e:
        logger.error(f"WebSocket错误: {e}")
    finally:
        # 从管理器移除客户端
        await ws_manager.disconnect_client(websocket)

