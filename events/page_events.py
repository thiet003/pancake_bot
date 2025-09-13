import asyncio
import logging
from typing import Dict, Any, Callable, List
from enum import Enum
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

class PageEventType(Enum):
    """Các loại events của page"""
    PAGE_CREATED = "page_created"
    PAGE_UPDATED = "page_updated" 
    PAGE_DELETED = "page_deleted"
    PAGE_ACTIVATED = "page_activated"
    PAGE_DEACTIVATED = "page_deactivated"
    PAGES_RELOADED = "pages_reloaded"

@dataclass
class PageEvent:
    """Event data structure"""
    event_type: PageEventType
    page_id: str
    page_data: Dict[str, Any] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

class PageEventBus:
    """Event Bus để quản lý và dispatch events liên quan đến pages"""
    
    def __init__(self):
        self._subscribers: Dict[PageEventType, List[Callable]] = {}
        self._global_subscribers: List[Callable] = []
        logger.info("PageEventBus đã được khởi tạo")
    
    def subscribe(self, event_type: PageEventType, callback: Callable[[PageEvent], None]):
        """Đăng ký lắng nghe một loại event cụ thể"""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(callback)
        logger.info(f"Đã đăng ký callback cho event: {event_type.value}")
    
    def subscribe_all(self, callback: Callable[[PageEvent], None]):
        """Đăng ký lắng nghe tất cả events"""
        self._global_subscribers.append(callback)
        logger.info("Đã đăng ký callback cho tất cả events")
    
    def unsubscribe(self, event_type: PageEventType, callback: Callable):
        """Hủy đăng ký lắng nghe event"""
        if event_type in self._subscribers:
            try:
                self._subscribers[event_type].remove(callback)
                logger.info(f"Đã hủy đăng ký callback cho event: {event_type.value}")
            except ValueError:
                pass
    
    async def emit(self, event: PageEvent):
        """Phát sự kiện đến tất cả subscribers"""
        logger.info(f"Emitting event: {event.event_type.value} for page: {event.page_id}")
        
        # Gửi đến subscribers của loại event cụ thể
        specific_subscribers = self._subscribers.get(event.event_type, [])
        
        # Gửi đến global subscribers
        all_subscribers = specific_subscribers + self._global_subscribers
        
        # Chạy tất cả callbacks async
        tasks = []
        for callback in all_subscribers:
            try:
                if asyncio.iscoroutinefunction(callback):
                    tasks.append(callback(event))
                else:
                    # Wrap sync function in async
                    tasks.append(asyncio.create_task(asyncio.to_thread(callback, event)))
            except Exception as e:
                logger.error(f"Lỗi khi chuẩn bị callback cho event {event.event_type.value}: {e}")
        
        # Chạy tất cả callbacks concurrently
        if tasks:
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
                logger.info(f"Đã gửi event {event.event_type.value} đến {len(tasks)} subscribers")
            except Exception as e:
                logger.error(f"Lỗi khi gửi event {event.event_type.value}: {e}")

# Singleton instance
_page_event_bus = None

def get_page_event_bus() -> PageEventBus:
    """Trả về singleton instance của PageEventBus"""
    global _page_event_bus
    if _page_event_bus is None:
        _page_event_bus = PageEventBus()
    return _page_event_bus 