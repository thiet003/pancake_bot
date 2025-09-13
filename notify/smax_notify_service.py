import os
import httpx
import asyncio
import logging
import json
import time
from typing import Dict, Any, Optional, List
from urllib.parse import quote

logger = logging.getLogger(__name__)

class SmaxNotifyService:
    """Service để gửi notifications đến sale thông qua SMAX AI API"""
    
    def __init__(self):
        # SMAX AI configuration
        self.smax_base_url = os.getenv("SMAX_BASE_URL")
        self.smax_token = os.getenv("SMAX_TOKEN")

    async def send_to_sale_smax(self, customer_pid: str, page_pid: str, attributes: List[Dict[str, str]] = None, use_post: bool = True) -> bool:
        """
        Gửi tin nhắn đến sale thông qua SMAX AI API
        
        Args:
            customer_pid: ID của khách hàng
            page_pid: ID của page
            attributes: Danh sách attributes [{"name": "key", "value": "value"}]
            use_post: True để dùng POST, False để dùng GET
            
        Returns:
            bool: True nếu gửi thành công, False nếu lỗi
        """
        if attributes is None:
            attributes = []
        pid = "zlw17238474311322837"
        page_id = "zlw130199648610926118"
        try:
            if use_post:
                # Sử dụng POST method với httpx
                headers = {
                    "Authorization": f"Bearer {self.smax_token}"
                }
                
                data = {
                    "customer": {
                        "pid": pid,
                        "page_pid": page_id
                    },
                    "attrs": attributes
                }
                
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.post(self.smax_base_url, json=data, headers=headers)
                    
                    if 200 <= response.status_code < 300:
                        response_text = response.text
                        logger.info(f"✅ Đã gửi tin nhắn đến SMAX AI thành công (POST - status: {response.status_code}): {response_text}")
                        return True
                    else:
                        error_text = response.text
                        logger.error(f"⚠️ Lỗi khi gửi tin nhắn đến SMAX AI (POST): {response.status_code} - {error_text}")
                        return False
            else:
                # Sử dụng GET method với httpx
                customer_data = json.dumps({"pid": customer_pid, "page_pid": page_pid})
                attrs_data = json.dumps(attributes)
                
                # URL encode các parameters
                params = {
                    "customer": customer_data,
                    "attrs": attrs_data,
                    "access_token": self.smax_token
                }
                
                logger.info(f"Gửi tin nhắn đến SMAX AI (GET): customer_pid={customer_pid}, page_pid={page_pid}")
                
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.get(self.smax_base_url, params=params)
                    
                    if 200 <= response.status_code < 300:
                        response_text = response.text
                        logger.info(f"✅ Đã gửi tin nhắn đến SMAX AI thành công (GET - status: {response.status_code}): {response_text}")
                        return True
                    else:
                        error_text = response.text
                        logger.error(f"⚠️ Lỗi khi gửi tin nhắn đến SMAX AI (GET): {response.status_code} - {error_text}")
                        return False
                        
        except httpx.RequestError as e:
            logger.error(f"⚠️ Lỗi mạng khi gửi đến SMAX AI: {e}")
            return False
        except httpx.HTTPStatusError as e:
            logger.error(f"⚠️ SMAX AI trả về lỗi HTTP: {e.response.status_code} - {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"⚠️ Lỗi không xác định khi gửi đến SMAX AI: {e}", exc_info=True)
            return False

    async def notify_sale_customer_support(self, customer_name: str, customer_phone: str, page_name: str, conversation_id: str, page_id: str, intent: str = "Cần hỗ trợ") -> bool:
        """
        Gửi thông báo đến sale khi khách hàng cần hỗ trợ thông qua SMAX AI
        
        Args:
            customer_name: Tên khách hàng
            customer_phone: Số điện thoại khách hàng  
            page_name: Tên page
            conversation_id: ID cuộc trò chuyện
            page_id: ID page
            intent: Mục đích (mặc định: "Cần hỗ trợ")
            
        Returns:
            bool: True nếu gửi thành công
        """
        # Tạo attributes với thông tin khách hàng
        attributes = [
            {"name": "customer_name", "value": customer_name},
            {"name": "customer_phone", "value": customer_phone or ""},
            {"name": "page_name", "value": page_name},
            {"name": "conversation_id", "value": conversation_id},
            {"name": "intent", "value": intent},
            {"name": "pancake_link", "value": f"https://pancake.vn/{page_id}?c_id={conversation_id}"}
        ]
        
        logger.info(f"Thông báo sale hỗ trợ khách hàng {customer_name} - {customer_phone}")
        
        # Sử dụng conversation_id làm customer_pid và page_id làm page_pid
        return await self.send_to_sale_smax(
            customer_pid=conversation_id,
            page_pid=page_id,
            attributes=attributes,
            use_post=True  # Sử dụng POST method
        )

    async def notify_sale_order_created(self, customer_name: str, customer_phone: str, page_name: str, conversation_id: str, page_id: str, order_id: str, order_note: str = "") -> bool:
        """
        Gửi thông báo đến sale khi có đơn hàng mới được tạo
        
        Args:
            customer_name: Tên khách hàng
            customer_phone: Số điện thoại khách hàng
            page_name: Tên page
            conversation_id: ID cuộc trò chuyện
            page_id: ID page
            order_id: ID đơn hàng
            order_note: Ghi chú đơn hàng
            
        Returns:
            bool: True nếu gửi thành công
        """
        # Tạo link đến đơn hàng nhanh.vn
        business_id = os.getenv("NHANH_BUSINESS_ID")
        order_link = f"https://nhanh.vn/order/manage/detail?id={order_id}&businessId={business_id}"
        
        attributes = [
            {"name": "customer_name", "value": customer_name},
            {"name": "customer_phone", "value": customer_phone or ""},
            {"name": "page_name", "value": page_name},
            {"name": "conversation_id", "value": conversation_id},
            {"name": "intent", "value": "Đơn hàng mới được tạo"},
            {"name": "pancake_link", "value": f"https://pancake.vn/{page_id}?c_id={conversation_id}"},
            {"name": "order_id", "value": order_id},
            {"name": "order_link", "value": order_link},
            {"name": "order_note", "value": order_note},
            {"name": "source", "value": "pancake_aisale"}
        ]
        
        logger.info(f"Thông báo sale đơn hàng mới: {order_id} - Khách hàng: {customer_name}")
        
        return await self.send_to_sale_smax(
            customer_pid=conversation_id,
            page_pid=page_id,
            attributes=attributes,
            use_post=True
        )

# Singleton instance
_smax_notify_service = None

def get_smax_notify_service() -> SmaxNotifyService:
    """Trả về singleton instance của SmaxNotifyService"""
    global _smax_notify_service
    if _smax_notify_service is None:
        _smax_notify_service = SmaxNotifyService()
    return _smax_notify_service
