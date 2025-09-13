from typing import Optional, List
from pydantic import BaseModel
from beanie import Document
from datetime import datetime
from zoneinfo import ZoneInfo
from enum import Enum, IntEnum
import os

class NotifySaleRequest(BaseModel):
    conversation_id: str
    phone: str
    intent: str