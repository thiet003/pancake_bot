import logging
from typing import Dict, Any
import asyncio
import aiohttp
from typing import Union
from typing import List
from typing import Optional
from pydantic_core.core_schema import str_schema
from platforms.pancake.pancake_api import PancakeService
# Cấu hình logging
logger = logging.getLogger(__name__)


class MessageSender:
    """Lớp phụ trách gửi thông tin cho bên khác"""
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.pancake_service = PancakeService(self.access_token)
        logger.info("Đã khởi tạo bộ gửi tin nhắn")
    
    async def close_session(self):
        """Đóng aiohttp session của PancakeService"""
        if self.pancake_service:
            await self.pancake_service.close_session()
            logger.info("Đã đóng session cho MessageSender")
    
    async def send_message(self, page_id: str, conversation_id: str, 
                           message: str) -> bool:
        """Gửi tin nhắn text trở lại cuộc trò chuyện"""
        try:
            # Gọi phương thức async của PancakeService
            result = await self.pancake_service.send_message(
                page_id=page_id,
                conversation_id=conversation_id,
                message=message
            )
            if result:
                logger.info(f"Đã gửi tin nhắn đến cuộc trò chuyện {conversation_id}: {message[:50]}...")
                return True
            else:
                logger.warning(f"Không thể gửi tin nhắn đến {conversation_id}: API trả về False")
                return False
                
        except Exception as e:
            logger.error(f"Không thể gửi tin nhắn đến {conversation_id}: {e}")
            return False
    
    async def send_image(self, page_id: str, conversation_id: str, 
                        image_url: str, caption: str = "") -> bool:
        """Gửi hình ảnh trở lại cuộc trò chuyện"""
        try:
            # Gọi phương thức async của PancakeService
            result = await self.pancake_service.send_message(
                page_id=page_id,
                conversation_id=conversation_id,
                message="",
                msg_type="image",
                content_url=image_url
            )
            
            if result:
                logger.info(f"Đã gửi hình ảnh đến cuộc trò chuyện {conversation_id}: {image_url}")
                return True
            else:
                logger.warning(f"Không thể gửi hình ảnh đến {conversation_id}: API trả về False")
                return False
                
        except Exception as e:
            logger.error(f"Không thể gửi hình ảnh đến {conversation_id}: {e}")
            return False
    # Gửi tin nhắn tổng hợp
    async def send_response_with_media(
        self, 
        page_id: Union[str, int], 
        conversation_id: str, 
        response: Dict[str, List[str]]
    ) -> bool:
        try:
            logger.info(f"Đang gửi tin nhắn đến cuộc trò chuyện {conversation_id}")
            # Lấy dữ liệu từ response
            messages = response.get("answers", [])
            images = response.get("images", [])
            action = response.get("action", "")
            logger.info(f"Action template: {action}")
            
            # Gửi các tin nhắn chính lần lượt
            previous_message = None
            for i, message in enumerate(messages, start=1):
                try:
                    logger.info(f"Đang gửi tin nhắn thứ {i}: {message}...")



                    # Bỏ qua nếu trùng với tin nhắn trước đó
                    if previous_message and message.lower() == previous_message.lower():
                        logger.info("Tin nhắn bị trùng lặp, bỏ qua.")
                        continue

                    await self.send_message(page_id, conversation_id, message)
                    previous_message = message
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"⚠️ Lỗi khi gửi tin nhắn thứ {i}: {e}")
            
            # Gửi các hình ảnh lần lượt
            for i, image in enumerate(images):
                try:
                    logger.info(f"Đang gửi hình ảnh thứ {i+1}: {image}")
                    await self.send_image(
                        page_id, 
                        conversation_id, 
                        image_url=image,
                        caption=""
                    )
                    await asyncio.sleep(1)
                except Exception as e:
                    logger.error(f"⚠️ Lỗi khi gửi hình ảnh thứ {i+1}: {str(e)}")
            logger.info(f"✅ Đã gửi thành công: {len(messages)} tin nhắn chính, {len(images)} hình ảnh")

            return True
        except Exception as e:
            logger.error(f"❌ Lỗi khi gửi phản hồi đa phương tiện: {e}", exc_info=True)
            return False