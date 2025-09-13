import json
import asyncio
import logging
import websockets
from typing import Dict, List, Callable, Any
import os
# Cấu hình logging
logger = logging.getLogger(__name__)

class PancakeWebSocketClient:
    """WebSocket client để kết nối với Pancake"""
    
    def __init__(self, access_token: str, user_id: str, page_ids: List[int]) -> None:
        self.access_token = access_token
        self.user_id = user_id
        self.page_ids = page_ids
        self.websocket = None
        self.ref_counter = 0
        self.event_handlers: Dict[str, List[Callable]] = {}
        self.connected = False
        self._should_reconnect = True  # Flag để control reconnection
        logger.info(f"Đã khởi tạo WebSocket client cho người dùng {user_id}")
        
    def register_event_handlers(self, conversation_handler):
        """Đăng ký các event handler cho nhiều loại sự kiện có thể được sử dụng"""
        self.on_event("pages:update_conversation", conversation_handler)
        
    def on_event(self, event_name: str, callback: Callable) -> None:
        """Đăng ký handler cho sự kiện"""
        if event_name not in self.event_handlers:
            self.event_handlers[event_name] = []
        self.event_handlers[event_name].append(callback)
        logger.info(f"✅ Đã đăng ký handler cho sự kiện {event_name}")
    
    def _get_next_ref(self) -> str:
        """Lấy ID tham chiếu tiếp theo cho tin nhắn"""
        self.ref_counter += 1
        return str(self.ref_counter)
    
    async def _send_message(self, channel: str, event: str, payload: dict) -> None:
        """Gửi tin nhắn qua WebSocket"""
        if not self.websocket:
            raise ConnectionError("WebSocket chưa được kết nối")

        ref = self._get_next_ref()
        message = [ref, ref, channel, event, payload]

        try:
            await self.websocket.send(json.dumps(message))
            logger.debug(f"Đã gửi tin nhắn tới kênh {channel}, sự kiện: {event}")
        except Exception as e:
            logger.error(f"Lỗi khi gửi tin nhắn WebSocket: {e}")
            self.connected = False
            raise
    
    async def _handle_message(self, message: str) -> None:
        """Xử lý tin nhắn WebSocket đến"""
        try:
            data = json.loads(message)
            
            # Kiểm tra cấu trúc dữ liệu trước khi truy cập
            if not isinstance(data, list) or len(data) < 4:
                logger.warning(f"Định dạng tin nhắn không hợp lệ: {message[:100]}...")
                return
                
            # Trích xuất thông tin từ tin nhắn
            ref = data[0] if len(data) > 0 else None
            channel = data[2] if len(data) > 2 else None
            event = data[3] if len(data) > 3 else None 
            payload = data[4] if len(data) > 4 else {}
            
            # Log chi tiết về sự kiện nhận được
            logger.info(f"📩 Nhận được sự kiện WebSocket: kênh={channel}, event={event}, payload: {str(payload)}")
            
            # Xử lý dựa trên event
            if event:
                handlers = self.event_handlers.get(event, [])
                
                if handlers:
                    logger.info(f"Tìm thấy {len(handlers)} handler cho sự kiện {event}")
                    for handler in handlers:
                        try:
                            if asyncio.iscoroutinefunction(handler):
                                await handler(payload)
                            else:
                                handler(payload)
                        except Exception as e:
                            logger.error(f"Lỗi trong handler cho sự kiện {event}: {e}", exc_info=True)
                else:
                    logger.debug(f"Không có handler cho sự kiện {event}")
        except json.JSONDecodeError:
            logger.error(f"JSON không hợp lệ trong tin nhắn: {message[:100]}...")
        except Exception as e:
            logger.error(f"Lỗi khi xử lý tin nhắn: {e}", exc_info=True)
    
    async def connect(self) -> None:
        """Kết nối đến WebSocket và duy trì kết nối"""
        uri = "wss://pages.fm/socket/websocket?vsn=2.0.0"
        
        # Vòng lặp kết nối
        while self._should_reconnect:
            try:
                # Kết nối với ping interval và timeout
                async with websockets.connect(
                    uri, 
                    ping_interval=30,
                    ping_timeout=10
                ) as websocket:
                    self.websocket = websocket
                    self.connected = True
                    logger.info("✅ Đã kết nối đến WebSocket")

                    # Tham gia kênh người dùng cho mỗi access token
                    user_channel = f"users:{self.user_id}"
                    await self._send_message(user_channel, "phx_join", {
                        "accessToken": self.access_token,
                        "userId": self.user_id,
                        "platform": "web"
                    })

                    # Cũng đăng ký kênh cho từng trang riêng lẻ
                    for page_id in self.page_ids:
                        page_channel = f"pages:{page_id}"
                        logger.info(f"Tham gia kênh trang {page_channel}")
                        
                        await self._send_message(page_channel, "phx_join", {
                            "accessToken": self.access_token,
                            "userId": self.user_id,
                            "pageId": str(page_id),
                            "platform": "web"
                        })
                    
                    logger.info(f"✅ Đã tham gia các kênh cho người dùng {self.user_id} và các trang {self.page_ids}")

                    # Vòng lặp lắng nghe tin nhắn
                    async for message in websocket:
                        # Non-blocking processing
                        asyncio.create_task(self._safe_handle_message(message))

            except websockets.exceptions.ConnectionClosed as e:
                if self._should_reconnect:
                    logger.warning(f"Kết nối WebSocket đã đóng: {e}")
                else:
                    logger.info("WebSocket đã đóng theo yêu cầu")
                    break
            except Exception as e:
                if self._should_reconnect:
                    logger.error(f"Lỗi kết nối WebSocket: {e}", exc_info=True)
                else:
                    logger.info("Dừng WebSocket theo yêu cầu")
                    break
            finally:
                self.websocket = None
                self.connected = False
                
            # Chỉ đợi khi cần reconnect
            if self._should_reconnect:
                logger.info("Kết nối lại sau 5 giây...")
                await asyncio.sleep(5)
            else:
                logger.info("Dừng reconnection loop")
                break

    async def _safe_handle_message(self, message: str) -> None:
        """Wrapper an toàn cho việc xử lý tin nhắn"""
        try:
            await self._handle_message(message)
        except Exception as e:
            logger.error(f"Lỗi xử lý tin nhắn WebSocket: {e}", exc_info=True)

    async def close(self):
        """Đóng kết nối WebSocket"""
        try:
            # Dừng reconnection loop
            self._should_reconnect = False
            
            if self.websocket and not self.websocket.closed:
                await self.websocket.close()
                logger.info("Đã đóng kết nối WebSocket")
            self.connected = False
        except Exception as e:
            logger.error(f"Lỗi khi đóng WebSocket: {e}") 