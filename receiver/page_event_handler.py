import asyncio
import logging
from typing import TYPE_CHECKING

from events.page_events import PageEvent, PageEventType

if TYPE_CHECKING:
    from receiver.receiver_service import ReceiverService

logger = logging.getLogger(__name__)

class PageEventHandler:
    """Handler để xử lý events thay đổi pages và graceful reload WebSocket"""
    
    def __init__(self, receiver_service: 'ReceiverService'):
        self.receiver_service = receiver_service
        self._reload_lock = asyncio.Lock()
        self._connect_task = None  # Track connect task
        logger.info("PageEventHandler đã được khởi tạo")
    
    async def handle_page_event(self, event: PageEvent):
        """Handle page events và trigger reload khi cần thiết"""
        try:
            logger.info(f"Xử lý page event: {event.event_type.value} cho page: {event.page_id}")
            
            # Các events cần reload WebSocket
            reload_events = {
                PageEventType.PAGE_CREATED,
                PageEventType.PAGE_ACTIVATED,
                PageEventType.PAGE_DEACTIVATED,
                PageEventType.PAGE_DELETED,
                PageEventType.PAGES_RELOADED
            }
            
            if event.event_type in reload_events:
                await self._graceful_reload()
            elif event.event_type == PageEventType.PAGE_UPDATED:
                # Nếu chỉ update thông tin không liên quan đến connection thì không cần reload
                # Nhưng để đảm bảo, vẫn reload
                await self._graceful_reload()
                
        except Exception as e:
            logger.error(f"Lỗi khi xử lý page event {event.event_type.value}: {e}")
    
    async def _graceful_reload(self):
        """Graceful reload WebSocket connections"""
        async with self._reload_lock:
            try:
                logger.info("Bắt đầu graceful reload WebSocket connections...")
                
                # 1. Cancel connect task cũ nếu đang chạy
                if self._connect_task and not self._connect_task.done():
                    logger.info("Đang cancel connect task cũ...")
                    self._connect_task.cancel()
                    try:
                        await self._connect_task
                    except asyncio.CancelledError:
                        logger.info("Đã cancel connect task cũ thành công")
                
                # 2. Đóng WebSocket connection cũ một cách graceful
                if self.receiver_service.ws_client:
                    logger.info("Đang đóng WebSocket connection cũ...")
                    await self.receiver_service.ws_client.close()
                    self.receiver_service.ws_client = None
                
                # 3. Reload page configs từ database
                logger.info("Đang reload page configs từ database...")
                await self.receiver_service._init_page_configs()
                
                # 4. Tạo WebSocket connection mới và connect
                if self.receiver_service.ws_client:
                    logger.info("Đang tạo WebSocket connection mới...")
                    # Tạo task riêng cho WebSocket connection để không block
                    self._connect_task = asyncio.create_task(self.receiver_service.ws_client.connect())
                
                logger.info("Hoàn thành graceful reload WebSocket connections")
                
            except Exception as e:
                logger.error(f"Lỗi trong quá trình graceful reload: {e}")
                # Nếu có lỗi, thử khôi phục lại connection
                try:
                    await self._emergency_recovery()
                except Exception as recovery_error:
                    logger.error(f"Lỗi khi khôi phục connection: {recovery_error}")
    
    async def _emergency_recovery(self):
        """Khôi phục connection trong trường hợp có lỗi"""
        logger.warning("Thực hiện khôi phục khẩn cấp WebSocket connection...")
        
        try:
            # Cleanup mọi thứ
            if self.receiver_service.ws_client:
                await self.receiver_service.ws_client.close()
                self.receiver_service.ws_client = None
            
            # Reload config và tạo lại connection
            await self.receiver_service._init_page_configs()
            
            if self.receiver_service.ws_client:
                self._connect_task = asyncio.create_task(self.receiver_service.ws_client.connect())
                
            logger.info("Khôi phục khẩn cấp thành công")
            
        except Exception as e:
            logger.error(f"Khôi phục khẩn cấp thất bại: {e}")
            raise 