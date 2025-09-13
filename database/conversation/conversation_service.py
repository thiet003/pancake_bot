import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, Dict, List

from database.models import ConversationDocument

logger = logging.getLogger(__name__)

class ConversationService:
    """Service để xử lý tất cả operations liên quan đến conversation"""
    
    async def create_or_get_conversation(self, conversation_id: str, page_id: str, customer_id: str, customer_name: str) -> Dict[str, any]:
        """
        Tạo conversation mới nếu chưa tồn tại, trả về thông tin conversation
        Returns: {"is_new": bool, "conversation": ConversationDocument}
        """
        try:
            now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
            result = await ConversationDocument.get_motor_collection().update_one(
                {"conversation_id": conversation_id},
                {
                    "$setOnInsert": {
                        "conversation_id": conversation_id,
                        "page_id": page_id,
                        "customer_id": customer_id,
                        "customer_name": customer_name,
                        "created_at": now,
                        "updated_at": now
                    }
                },
                upsert=True
            )
            is_new = result.upserted_id is not None
            conversation = await ConversationDocument.find_one({"conversation_id": conversation_id})
            return {
                "is_new": is_new,
                "conversation": conversation
            }
            
        except Exception as e:
            return {"is_new": False, "conversation": None}
    
    async def get_conversation(self, conversation_id: str) -> Optional[ConversationDocument]:
        """Lấy conversation theo ID"""
        try:
            return await ConversationDocument.find_one({"conversation_id": conversation_id})
        except Exception as e:
            return None
    
    async def update_conversation_activity(self, conversation_id: str) -> bool:
        """Cập nhật thời gian activity cuối của conversation"""
        try:
            now = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
            result = await ConversationDocument.get_motor_collection().update_one(
                {"conversation_id": conversation_id},
                {"$set": {"updated_at": now}}
            )
            return result.modified_count > 0
        except Exception as e:
            return False
    
    async def get_conversations_by_page(self, page_id: str, limit: int = 50) -> List[ConversationDocument]:
        """Lấy danh sách conversations theo page_id"""
        try:
            return await ConversationDocument.find(
                {"page_id": page_id}
            ).sort([("updated_at", -1)]).limit(limit).to_list()
        except Exception as e:
            return []
    
# Singleton instance
_conversation_service = None

def get_conversation_service() -> ConversationService:
    """Trả về singleton instance của ConversationService"""
    global _conversation_service
    if _conversation_service is None:
        _conversation_service = ConversationService()
    return _conversation_service 