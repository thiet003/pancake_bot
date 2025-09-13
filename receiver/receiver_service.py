import os
import asyncio
import time
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from websocket.pancake_websocket import PancakeWebSocketClient
from platforms.pancake.pancake_api import PancakeService
from database.page.page_service import get_page_service
from database.conversation.conversation_service import get_conversation_service
import aiohttp
from notify.smax_notify_service import SmaxNotifyService
from config.settings import BackendConfig
from events.page_events import get_page_event_bus
from receiver.page_event_handler import PageEventHandler
from sender.message_sender import MessageSender
settings:BackendConfig = BackendConfig()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

class ReceiverService:
    """Dịch vụ nhận tin nhắn từ WebSocket và xử lý"""
    def __init__(self):
        self.access_token = settings.PANCAKE_ACCESS_TOKEN
        self.user_id = settings.PANCAKE_USER_ID
        self.page_service = get_page_service()
        self.conversation_service = get_conversation_service()
        self.pancake_service = PancakeService(self.access_token)
        self.smax_notify_service = SmaxNotifyService()
        self.page_configs = {}
        self.ws_client = None
        self.last_processed = {}
        self._connect_task = None 
        # send message 
        self.message_sender = MessageSender(self.access_token)

        self.pending_tasks: Dict[str, asyncio.Task] = {}
        self.event_bus = get_page_event_bus()
        self.page_event_handler = PageEventHandler(self)
        logger.info("Dịch vụ ReceiverService đã được khởi tạo")
    
    async def cleanup(self):
        """Cleanup sessions và connections"""
        try:
            # Cancel connect task if running
            if self._connect_task and not self._connect_task.done():
                self._connect_task.cancel()
                try:
                    await self._connect_task
                except asyncio.CancelledError:
                    logger.info("Đã cancel connect task thành công")
            
            # Cancel tất cả pending tasks
            for conversation_id, task in self.pending_tasks.items():
                if not task.done():
                    task.cancel()
                    logger.info(f"Đã cancel pending task cho conversation {conversation_id}")
            self.pending_tasks.clear()
            
            # Cleanup event subscriptions
            if hasattr(self, 'event_bus') and hasattr(self, 'page_event_handler'):
                # Unsubscribe from events (if needed)
                pass
                
            if self.pancake_service:
                await self.pancake_service.close_session()
            if self.ws_client:
                await self.ws_client.close()
            logger.info("Đã cleanup ReceiverService thành công")
        except Exception as e:
            logger.error(f"Lỗi khi cleanup ReceiverService: {e}")
    
    async def _load_page_configs_from_db(self) -> Dict[str, Dict[str, str]]:
        """Load page configs từ DB"""
        try:
            all_pages = await self.page_service.get_all_active_pages()
            configs = {}
            for page_info in all_pages:
                page_id = page_info["page_id"]
                configs[page_id] = {
                    "page_access_token": page_info["page_access_token"],
                    "page_name": page_info["page_name"],
                    "tags": page_info["tags"]  # Lưu toàn bộ danh sách tags
                }
            return configs
        except Exception as e:
            return {}

    async def _init_page_configs(self):
        self.page_configs = await self._load_page_configs_from_db()
        self.ws_client = PancakeWebSocketClient(
            self.access_token, 
            self.user_id,
            [int(page_id) for page_id in self.page_configs.keys()]
        )
        # Đăng ký xử lý sự kiện WebSocket
        self.ws_client.register_event_handlers(self.handle_conversation_update)

    async def handle_conversation_update(self, payload: Dict[str, Any]) -> None:
        """Xử lý các sự kiện cập nhật cuộc trò chuyện từ WebSocket"""
        try:
            # Trích xuất dữ liệu từ payload
            conversation_data = payload.get("conversation", {})
            conversation_id = conversation_data.get("id")
            page_id = conversation_data.get("page_id")
            
            last_sent_by = conversation_data.get("last_sent_by", {})
            sender_name = last_sent_by.get("name", "No name")
            customer_id = conversation_data.get("customers", [{}])[0].get("id", "")
            customer_name = conversation_data.get("customers", [{}])[0].get("name", "No name")
            type_inbox = conversation_data.get("type", "INBOX")
            time_last_sent = conversation_data.get("updated_at", "")
            # Các tag trong conversation
            tags_int = conversation_data.get("tags", [])
            tags = [str(tag) for tag in tags_int]  # Chuyển đổi sang chuỗi
            logger.info(f"Danh sách tag của hội thoại: {tags}")

            # Lấy nội dung tin nhắn từ snippet
            message_content = conversation_data.get("snippet", "")

            # Kiểm tra trùng lặp
            current_time = time.time()
            last_data = self.last_processed.get(conversation_id)
            if last_data and last_data[0] == message_content and current_time - last_data[1] < 3.0:
                logger.info(f"Bỏ qua tin nhắn trùng lặp: {message_content}")
                return
            
            # Cập nhật tin nhắn đã xử lý gần đây
            self.last_processed[conversation_id] = (message_content, current_time)
            logger.info(f"Nội dung tin nhắn mới: {message_content}")
            logger.info(f"Cussomer ID: {customer_id}, Conversation ID: {conversation_id}, Page ID: {page_id}")
            logger.info(f"Thông tin khách hàng: -Tên: {sender_name}")
            logger.info(f"-----------------------------")

            if type_inbox != "INBOX":
                logger.info(f"Bỏ qua tin nhắn từ {type_inbox}: {conversation_id}")
                return
            # Bỏ qua nếu từ AGENT
            is_poscake_create_order = False
            page_names = [page_info["page_name"] for page_info in self.page_configs.values()]
            if any(bot_name.lower() in sender_name.lower() for bot_name in page_names if bot_name) and not is_poscake_create_order:
                logger.info(f"Bỏ qua tin nhắn từ AGENT: {sender_name}")
                return
            
            # Tìm tag IDs theo tên từ page config
            ai_sale_tag_id = None
            support_tag_id = None
            page_name = None
            page_tags = []
            
            for page_idd, page_info in self.page_configs.items():
                if page_idd == str(page_id):
                    page_name = page_info.get("page_name", None)
                    page_tags = page_info.get("tags", [])
                    
                    # Tìm tag theo tên
                    for tag in page_tags:
                        if tag["tag_name"].lower() == "ai sale":
                            ai_sale_tag_id = tag["tag_id"]
                        elif tag["tag_name"].lower() == "nv hỗ trợ":
                            support_tag_id = tag["tag_id"]
                    break
                    
            # Thêm tag AI sale cho cuộc hội thoại nếu có
            if ai_sale_tag_id:
                await self.pancake_service.add_tags(page_id, conversation_id, str(ai_sale_tag_id))
 
            # Nếu có tag support thì không xử lý
            if support_tag_id and support_tag_id in tags:
                logger.info(f"Bỏ qua tin nhắn có tag support: {conversation_id}")
                return
            
            # Nếu khách hàng gửi ảnh hoặc video thì gọi sale
            if "[Photo]" in message_content or "[Video]" in message_content:
                logger.info(f"Khách hàng gửi ảnh hoặc video: {conversation_id}")
                # Thêm tag support cho conversation nếu có
                if support_tag_id:
                    await self.pancake_service.add_tags(page_id, conversation_id, str(support_tag_id))
            #     # Gửi webhook đến sale
                await self.smax_notify_service.notify_sale_customer_support(
                    customer_name=customer_name,
                    customer_phone="",
                    page_name=page_name,
                    conversation_id=conversation_id,
                    page_id=page_id,
                    intent="Khách hàng gửi ảnh hoặc video"
                )
                return

            # Kiểm tra xem conversation đã tồn tại chưa
            conversation_result = await self.conversation_service.create_or_get_conversation(
                conversation_id, page_id, customer_id, customer_name
            )
            
            if not conversation_result["conversation"]:
                logger.error(f"Không thể tạo/lấy conversation {conversation_id}")
                return
            
            last_message = f"{message_content} - {time_last_sent}"
            await self._schedule_message_with_debounce(conversation_id, page_id, customer_id, customer_name, message_content, last_message)
            
        except Exception as e:
            logger.error(f"Lỗi khi xử lý cập nhật cuộc trò chuyện: {e}", exc_info=True)

    async def _schedule_message_with_debounce(self, conversation_id: str, page_id: str, customer_id: str, customer_name: str, message_content: str, last_message: str) -> None:
        """Lên lịch gửi tin nhắn với debounce 10s - hủy tin cũ nếu có tin mới"""
        try:
            # Hủy task cũ nếu có
            if conversation_id in self.pending_tasks:
                old_task = self.pending_tasks[conversation_id]
                if not old_task.done():
                    old_task.cancel()
                    logger.info(f"Đã hủy tin nhắn cũ cho conversation {conversation_id}")
            
            # Tạo task mới với delay 6s
            async def delayed_process():
                try:
                    await asyncio.sleep(5.0)  # Chờ 5 giây
                    logger.info(f"Gửi tin nhắn sau 5s delay: {conversation_id}")
                    await self._process_single_message(conversation_id, page_id, customer_id, customer_name, message_content, last_message)
                except asyncio.CancelledError:
                    logger.info(f"Tin nhắn đã bị hủy: {conversation_id}")
                    raise
                finally:
                    # Xóa task khỏi pending list
                    if conversation_id in self.pending_tasks:
                        del self.pending_tasks[conversation_id]
            
            # Lưu task mới
            self.pending_tasks[conversation_id] = asyncio.create_task(delayed_process())
            logger.info(f"Đã lên lịch tin nhắn với delay 5s: {conversation_id}")
            
        except Exception as e:
            logger.error(f"Lỗi khi lên lịch tin nhắn: {e}", exc_info=True)

    async def _process_single_message(self, conversation_id: str, page_id: str, customer_id: str, customer_name: str, message_content: str, last_message: str) -> None:
        """Xử lý một tin nhắn đơn lẻ ngay lập tức"""
        try:
            send_result = await self._send_to_ai(conversation_id, page_id, customer_id, customer_name, message_content, last_message)
            if send_result:
                logger.info(f"Đã gửi tin nhắn đến AI: {conversation_id}")
            else:
                logger.error(f"Lỗi khi gửi tin nhắn đến AI: {conversation_id}, {page_id}, {customer_id}, {send_result}")
        except Exception as e:
            logger.error(f"Lỗi khi xử lý tin nhắn: {e}", exc_info=True)
    
    
    # Call API để gửi cho AI xử lý
    async def _send_to_ai(self, conversation_id: str, page_id: str, customer_id: str, customer_name: str, message_content: str, last_message: str) -> None:
        """Gửi tin nhắn đến AI"""
        try:
            
            # Lấy history từ conversation
            history, source = await self.pancake_service.process_conversation(page_id, conversation_id, customer_id)
            
            logger.info(f"Đã lấy history: {history}")
            logger.info(f"Đã lấy source: {source}")
            # Ví dụ về gửi tin nhắn bằng send_message
            answers = [
                "Chào bạn", "Cảm ơn bạn đã liên hệ với chúng tôi. Chúng tôi sẽ phản hồi bạn trong thời gian sớm nhất."
            ]
            images_url = [
                "https://dytbw3ui6vsu6.cloudfront.net/media/catalog/product/resize/800x800/0/0/0091698_513-A01_1_1.webp"
            ]
            response = {
                "answers": answers,
                "images": images_url,
                "action": ""
            }
            await self.message_sender.send_response_with_media(
                page_id, 
                conversation_id, 
                response
            )
            return True
                
        except Exception as e:
            logger.error(f"Lỗi khi gửi tin nhắn đến AI: {e}", exc_info=True)
    
    # Hàm khởi động dịch vụ bot
    async def start(self) -> None:
        """Khởi động dịch vụ bot"""
        try:
            # Subscribe to page events
            self.event_bus.subscribe_all(self.page_event_handler.handle_page_event)
            logger.info("Đã đăng ký lắng nghe page events")
            
            await self._init_page_configs()
            
            # Start WebSocket connection
            if self.ws_client:
                self._connect_task = asyncio.create_task(self.ws_client.connect())
            
            logger.info("Đang khởi động ReceiverService...")
            # Không await connect task để tránh block, để nó chạy background
            if self._connect_task:
                logger.info("WebSocket connection đang chạy trong background")
        except Exception as e:
            logger.error(f"Lỗi khi khởi động dịch vụ: {e}", exc_info=True)
            raise