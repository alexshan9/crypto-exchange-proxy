import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=9100,
        reload=True,  # 开发模式，代码变更自动重载
        log_level="debug"
    )
