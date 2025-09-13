from typing import List, Optional
from datetime import datetime
from zoneinfo import ZoneInfo
from pydantic import BaseModel
from beanie import Document


class Message(BaseModel):
    role: str
    content: str


class PageTag(BaseModel):
    """Model cho tag của page"""
    tag_name: str  # Tên tag (vd: "AI Sale", "Order", "Support")
    tag_id: str    # ID của tag

# Page
class PageDocument(Document):
    page_id: str
    page_name: str
    encrypted_token: str
    tags: Optional[List[PageTag]] = []  # Danh sách các tag linh hoạt
    is_active: bool = True
    created_at: datetime = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    updated_at: datetime = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    
    class Settings:
        name = "pages"
        indexes = ["page_id"]

# Conversation
class ConversationDocument(Document):
    conversation_id: str
    page_id: str
    customer_id: str
    customer_name: str
    created_at: datetime = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    updated_at: datetime = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    
    class Settings:
        name = "conversations"
        indexes = [
            "conversation_id",
            "page_id",
            "customer_id"
        ]

