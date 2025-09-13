from typing import Optional, List
from pydantic import BaseModel
from beanie import Document
from datetime import datetime
from zoneinfo import ZoneInfo

class HistoryRequest(BaseModel):
    conversation_id: str
    page_id: str
    customer_id: str

class MessageResponse(BaseModel):
    answers: List[str]
    images: List[str]
    sub_answers: List[str]

class SendMessageRequest(BaseModel):
    conversation_id: str
    response: MessageResponse

class ResourceRequest(BaseModel):
    conversation_id: str
    page_id: str
    customer_id: str
    customer_name: str
    source: str
    
class AIRequest(BaseModel):
    history: str
    resource: ResourceRequest
