from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import StreamingResponse
from models.bot import HistoryRequest, SendMessageRequest
from models.nhanh import NotifySaleRequest
from platforms.pancake.pancake_api import PancakeService
from database.conversation.conversation_service import get_conversation_service
from sender.message_sender import MessageSender
from notify.smax_notify_service import get_smax_notify_service
from database.page.page_service import get_page_service
import base64
import logging
import os
import json
from uuid import uuid4
from config.settings import BackendConfig
import asyncio

settings: BackendConfig = BackendConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logger.info(f"Router logger initialized: {__name__}")

# Singleton instances
_pancake_service = None
_nhanh_service = None
_message_sender = None

routes = APIRouter(
    prefix="",
    tags=["bot"],
    responses={404: {"description": "API not found"}}
)

# Dependency injection functions
def get_pancake_service() -> PancakeService:
    """Get PancakeService singleton instance"""
    global _pancake_service
    if _pancake_service is None:
        _pancake_service = PancakeService(settings.PANCAKE_ACCESS_TOKEN)
    return _pancake_service

def get_message_sender() -> MessageSender:
    """Get MessageSender singleton instance"""
    global _message_sender
    if _message_sender is None:
        _message_sender = MessageSender(settings.PANCAKE_ACCESS_TOKEN)
    return _message_sender

async def cleanup_services():
    """Cleanup all singleton services and close their sessions"""
    global _pancake_service, _nhanh_service, _message_sender
    
    tasks = []
    if _pancake_service:
        tasks.append(_pancake_service.close_session())
    if _message_sender and hasattr(_message_sender, 'close_session'):
        tasks.append(_message_sender.close_session())
    
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Đã đóng tất cả aiohttp sessions")

# API lấy history chat, có param chỉ có conversation_id
@routes.post("/api/v1/history-chat")
async def get_history_chat(
    request: Request, 
    conversation_id: str,
    pancake_service: PancakeService = Depends(get_pancake_service),
    conversation_service = Depends(get_conversation_service)
):
    logger.info(f"[HISTORY_CHAT] Bắt đầu lấy history chat: conversation_id={conversation_id}")
    conversation = await conversation_service.get_conversation(conversation_id)
    if not conversation:
        logger.warning(f"[HISTORY_CHAT] Không tìm thấy conversation: {conversation_id}")
        return {
            "history": "",
            "conversation_id": conversation_id,
            "resource": {
                "product_content": ""
            }
        }
    page_id = conversation.page_id
    customer_id = conversation.customer_id
    logger.info(f"[HISTORY_CHAT] Conversation tìm thấy - page_id: {page_id}, customer_id: {customer_id}")
    # Lấy history từ pancake
    history, source = await pancake_service.process_conversation(page_id, conversation_id, customer_id)
    logger.info(f"[HISTORY_CHAT] Đã lấy được {len(history)} tin nhắn từ Pancake")
    
    return {
        "history": history,
        "conversation_id": conversation_id,
    }

# API gửi tin nhắn đến pancake
@routes.post("/api/v1/send-message")
async def send_message(
    send_message_request: SendMessageRequest,
    sender: MessageSender = Depends(get_message_sender),
    conversation_service = Depends(get_conversation_service)
):
    logger.info(f"[SEND_MESSAGE] Bắt đầu xử lý gửi tin nhắn: conversation_id={send_message_request.conversation_id}")
    conversation = await conversation_service.get_conversation(send_message_request.conversation_id)
    if not conversation:
        logger.warning(f"[SEND_MESSAGE] Không tìm thấy conversation: {send_message_request.conversation_id}")
        return {
            "status": "error",
            "message": "Không tìm thấy conversation",
            "conversation_id": send_message_request.conversation_id
        }
    page_id = conversation.page_id
    logger.info(f"[SEND_MESSAGE] Conversation tìm thấy - page_id: {page_id}")
    try:
        response_dict = send_message_request.response.model_dump()
        # Gửi tin nhắn đến pancake
        result = await sender.send_response_with_media(
            page_id, 
            send_message_request.conversation_id, 
            response_dict
        )
        
        if result:
            logger.info(f"[SEND_MESSAGE] Gửi tin nhắn thành công: conversation_id={send_message_request.conversation_id}")
            return {
                "status": "success",
                "message": "Tin nhắn đã được gửi thành công",
                "conversation_id": send_message_request.conversation_id
            }
            
        logger.warning(f"[SEND_MESSAGE] Gửi tin nhắn thất bại: conversation_id={send_message_request.conversation_id}")
        return {
            "status": "error",
            "message": "Không thể gửi tin nhắn",
            "conversation_id": send_message_request.conversation_id
        }
    except Exception as e:
        logger.error(f"[SEND_MESSAGE] Lỗi khi xử lý yêu cầu gửi tin nhắn: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "message": "Lỗi khi gửi tin nhắn",
            "conversation_id": send_message_request.conversation_id
        }

# API thông báo cho Sale
@routes.post("/api/v1/notify-sale")
async def notify_sale(
    notify_sale_request: NotifySaleRequest,
    smax_notify_service = Depends(get_smax_notify_service),
    conversation_service = Depends(get_conversation_service),
    page_service = Depends(get_page_service),
    pancake_service = Depends(get_pancake_service)
):
    logger.info(f"[NOTIFY_SALE] Bắt đầu thông báo Sale: conversation_id={notify_sale_request.conversation_id}")
    try:
        # Kiểm tra conversation tồn tại
        conversation = await conversation_service.get_conversation(notify_sale_request.conversation_id)
        if not conversation:
            logger.warning(f"[NOTIFY_SALE] Không tìm thấy conversation: {notify_sale_request.conversation_id}")
            return {
                "status": "error",
                "message": "Không tìm thấy conversation",
                "conversation_id": notify_sale_request.conversation_id
            }
        
        # Kiểm tra page tồn tại
        page_id = conversation.page_id
        page_info = await page_service.get_page_info(page_id)
        page_name = page_info["page_name"]
        logger.info(f"[NOTIFY_SALE] Page info: {page_name} (ID: {page_id})")
        
        # Tìm support tag ID theo tên từ page info
        support_tag_id = None
        if page_info and page_info.get("tags"):
            for tag in page_info["tags"]:
                if tag["tag_name"].lower() == "nv hỗ trợ":
                    support_tag_id = tag["tag_id"]
                    break
        
        # Gửi tin nhắn đến pancake
        # await pancake_service.send_message(
        #     page_id,
        #     notify_sale_request.conversation_id,
        #     "Dạ anh đợi chút ạ"
        # )
        # logger.info(f"[NOTIFY_SALE] Đã gửi tin nhắn 'Dạ anh đợi chút ạ' cho customer")
        
        # Gắn tag hỗ trợ nếu có
        if support_tag_id:
            await pancake_service.add_tags(
                page_id,
                notify_sale_request.conversation_id,
                support_tag_id
            )
            logger.info(f"[NOTIFY_SALE] Đã gắn tag support cho conversation")
        # Gửi notification và chờ kết quả
        result = await smax_notify_service.notify_sale_customer_support(
            customer_name=conversation.customer_name or "Khách hàng",
            customer_phone=notify_sale_request.phone,
            page_name=page_name,
            conversation_id=notify_sale_request.conversation_id,
            page_id=page_id,
            intent=notify_sale_request.intent
        )
        logger.info(f"[NOTIFY_SALE] Webhook result: {result}")
        if result:
            logger.info(f"[NOTIFY_SALE] Đã gửi notification cho Sale thành công: conversation_id={notify_sale_request.conversation_id}")
            return {
                "status": "success",
                "message": "Đã gửi thông báo cho Sale thành công",
                "conversation_id": notify_sale_request.conversation_id
            }
        else:
            logger.warning(f"[NOTIFY_SALE] Gửi notification cho Sale thất bại: conversation_id={notify_sale_request.conversation_id}")
            return {
                "status": "error",
                "message": "Không thể gửi thông báo cho Sale",
                "conversation_id": notify_sale_request.conversation_id
            }
        
    except Exception as e:
        logger.error(f"[NOTIFY_SALE] Lỗi khi gửi thông báo cho Sale: {str(e)}", exc_info=True)
        return {
                "status": "error",
                "message": "Lỗi hệ thống khi gửi thông báo",
                "conversation_id": getattr(notify_sale_request, 'conversation_id', 'unknown')
            }
