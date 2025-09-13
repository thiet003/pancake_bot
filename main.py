from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, HTTPException, status
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json
import os
import asyncio
import time
import logging
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv
from receiver.receiver_service import ReceiverService
from routers.main_router import routes, cleanup_services
from routers.page_router import page_router
from database.mongo_db import init_mongo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
from config.settings import BackendConfig
settings:BackendConfig = BackendConfig()

# Port
port = settings.PORT
logger.info(f"Port: {port}")

receiver_service: Optional[ReceiverService] = None

async def lifespan(app: FastAPI):
    global receiver_service
    logger.info("Đang khởi động ứng dụng...")
    # Khởi tạo MongoDB
    await init_mongo()
    # Khởi tạo receiver service
    try:
        receiver_service = ReceiverService()
        asyncio.create_task(receiver_service.start())
        logger.info("Receiver service đã được khởi động và đang chạy ngầm")
    except Exception as e:
        logger.error(f"Lỗi khi khởi động receiver service: {e}")
    
    yield
    
    logger.info("Đang dừng ứng dụng...")
    try:
        if receiver_service:
            await receiver_service.cleanup()
        await cleanup_services()
        logger.info("Đã cleanup services thành công")
    except Exception as e:
        logger.error(f"Lỗi khi cleanup services: {e}")


app: FastAPI = FastAPI(
    title="Bot Pancake API",
    description="API cho Bot Pancake với WebSocket chạy ngầm",
    version="1.0",
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Router
app.include_router(page_router)
app.include_router(routes)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=port)
