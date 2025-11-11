"""FastAPI主应用"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import candlestick, websocket
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 创建FastAPI应用实例
app = FastAPI(
    title="Crypto Exchange Proxy",
    description="加密货币交易所代理服务，提供历史K线数据和实时ticker数据转发",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
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


@app.get("/", tags=["root"])
async def root():
    """根路径"""
    return {
        "service": "Crypto Exchange Proxy",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "candlestick": "/candlestick/historical",
            "websocket": "/ws/ticker",
            "docs": "/docs"
        }
    }


@app.get("/health", tags=["health"])
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "service": "crypto-exchange-proxy"
    }


@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    logger.info("=" * 50)
    logger.info("Crypto Exchange Proxy 正在启动...")
    logger.info("服务端口: 9100")
    logger.info("API文档: http://localhost:9100/docs")
    logger.info("=" * 50)


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    logger.info("=" * 50)
    logger.info("Crypto Exchange Proxy 正在关闭...")
    logger.info("=" * 50)


if __name__ == "__main__":
    import uvicorn
    from app.config import config
    
    uvicorn.run(
        "app.main:app",
        host=config.get_server_host(),
        port=config.get_server_port(),
        reload=True,
        log_level="info"
    )

