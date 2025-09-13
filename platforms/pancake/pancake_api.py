import os
import json
import aiohttp
import asyncio
import logging
from typing import Dict, List, Tuple, Optional, Any
from dotenv import load_dotenv
from database.page.page_service import get_page_service

logger = logging.getLogger(__name__)
load_dotenv()

class PancakeService:
    BASE_URL_V1 = "https://pages.fm/api/v1"
    BASE_URL_V2 = "https://pages.fm/api/public_api/v2"
    BASE_URL_PUBLIC_V1 = "https://pages.fm/api/public_api/v1"

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.page_configs = {}
        self.page_service = get_page_service()
        self.list_page_names = []
        self._session: Optional[aiohttp.ClientSession] = None

    async def _load_page_configs_from_db(self) -> Dict[str, Dict[str, str]]:
        try:
            # Lấy tất cả pages active từ DB
            all_pages = await self.page_service.get_all_active_pages()
            configs = {}
            for page_info in all_pages:
                page_id = page_info["page_id"]
                configs[page_id] = {
                    "page_access_token": page_info["page_access_token"],
                    "page_name": page_info["page_name"]
                }
                logger.info(f"Loaded config cho page: {page_info['page_name']} ({page_id})")
            
            logger.info(f"Loaded tổng cộng {len(configs)} pages từ DB")
            return configs
        except Exception as e:
            logger.error(f"Lỗi load page configs từ DB: {e}")
            return {}

    async def _get_session(self) -> aiohttp.ClientSession:
        """Khởi tạo hoặc trả về ClientSession đang hoạt động."""
        if self._session is None or self._session.closed:
            # Cấu hình timeout hợp lý cho Pancake API
            timeout = aiohttp.ClientTimeout(
                total=45,      # Tổng thời gian timeout: 45s
                connect=15,    # Thời gian kết nối: 15s
                sock_read=25   # Thời gian đọc response: 25s
            )
            self._session = aiohttp.ClientSession(
                timeout=timeout
            )
        return self._session

    async def close_session(self):
        """Đóng ClientSession khi không cần nữa."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("Closed aiohttp ClientSession for PancakeService.")

    async def _get_page_token(self, page_id: str) -> Optional[str]:
        """Lấy page_access_token từ DB."""
        # Load configs nếu chưa có hoặc cần refresh
        if not self.page_configs:
            self.page_configs = await self._load_page_configs_from_db()
            # Update list_page_names từ DB
            self.list_page_names = [page_info["page_name"] for page_info in self.page_configs.values()]
        
        return self.page_configs.get(page_id, {}).get("page_access_token")

    # Lấy lịch sử hội thoại
    async def load_history(self, list_messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """lấy lịch sử hội thoại"""
        history = []
        for message in list_messages:
            mes = message.get("original_message", "")
            if mes.strip() == "":
                if len(message.get("attachments",[])) > 0:
                    if message.get("attachments", [{}])[0].get("type", "") == "photo":
                        mes_url = message.get("attachments", [{}])[0].get("url", "")
                        mes = f"Ảnh: {mes_url}"
            send_name = message.get("from", {}).get("name", "")
            if send_name in self.list_page_names:
                role = "agent"
            else:
                role = "user"
            time = message.get("inserted_at", "")
            history.append({"role": role, "message": mes, "time": time})
        return history
    # Lấy nguồn quảng cáo hoặc comment
    async def get_source(self, list_messages: List[Dict[str, Any]], post: Dict[str, Any], activities: List[Dict[str, Any]]) -> str:
        source = ""
        logger.warning(f"Post: {post}")
        if post:
            message_post = post.get("message", "")
            logger.warning(f"Message post: {message_post}")
            if message_post:
                return message_post
        for i in range(len(list_messages)-1, -1, -1):
            message = list_messages[i]
            if len(message.get("attachments",[])) > 0:
                first_attachment = message.get("attachments", [{}])[0]
                if first_attachment.get("type",None) == "ad_click":
                    source = first_attachment.get("name","")
                    logger.warning(f"Source ads: {source}")
                    return source
                if first_attachment.get("comment",None) is not None:
                    source = first_attachment.get("name","")
                    logger.warning(f"Source comment: {source}")
                    return source
        for message in list_messages:
            ms = message.get("original_message", "")
            if "AF-FB-MES-DIEU-A3L" in ms or "MES-DIEU-A3L" in ms:
                source = ms + "\nTư vấn áo ba lỗ"
                logger.warning(f"Message source: {source}")
                return source
        if len(activities) > 0:
            first_activity = activities[0]
            if first_activity.get("message") is not None:
                source = first_activity.get("message")
                logger.warning(f"Activity source: {source}")
                return source
        return source
    # Xử lý hội thoại
    async def process_conversation(self, page_id: str, conversation_id: str, customer_id: str) -> Tuple[List[Dict[str, Any]], str]:
        """Lấy lịch sử tin nhắn của cuộc hội thoại."""
        page_token = await self._get_page_token(page_id)
        if not page_token:
            logger.error(f"Không tìm thấy page_access_token cho page_id: {page_id}")
            return [], ""
        
        url = f"{self.BASE_URL_PUBLIC_V1}/pages/{page_id}/conversations/{conversation_id}/messages"
        params = {
            "page_id": page_id,
            "page_access_token": page_token,
            "customer_id": customer_id,
            "conversation_id": conversation_id,
        }
        session = await self._get_session()
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        response_data = await response.json()
                        history = await self.load_history(response_data.get("messages", []))
                        source = await self.get_source(response_data.get("messages", []), response_data.get("post", {}), response_data.get("activities", []))
                        return history, source
                    else:
                        error_text = await response.text()
                        logger.error(f"⚠️ Lỗi khi load history ({conversation_id}) (lần {attempt + 1}): {response.status} - {error_text}")
                        if response.status >= 500 and attempt < max_retries - 1:
                            await asyncio.sleep(1)  # Đợi 1 giây trước khi thử lại
                            continue
                        return [], ""
            except aiohttp.ClientError as e:
                logger.error(f"⚠️ Lỗi mạng khi load history ({conversation_id}) (lần {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                return [], ""
            except Exception as e:
                logger.error(f"⚠️ Lỗi không xác định khi load history ({conversation_id}) (lần {attempt + 1}): {e}", exc_info=True)
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                return [], ""
        return [], ""

    async def load_last_message(self, page_id: str, conversation_id: str, customer_id: str) -> Tuple[str, str]:
        """Lấy tin nhắn cuối cùng và nguồn gốc tin nhắn."""
        page_token = await self._get_page_token(page_id)
        if not page_token:
            logger.error(f"Không tìm thấy page_access_token cho page_id: {page_id}")
            return "", "Error: Missing page token"

        url = f"{self.BASE_URL_PUBLIC_V1}/pages/{page_id}/conversations/{conversation_id}/messages"
        params = {
            "page_id": page_id,
            "page_access_token": page_token,
            "customer_id": customer_id,
            "conversation_id": conversation_id,
        }
        session = await self._get_session()
        try:
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    response_data = await response.json()
                    messages = response_data.get("messages", [])
                    activities = response_data.get("activities", [])

                    if not messages:
                        return "", "" # Không có tin nhắn

                    last_message = messages[-1]
                    user_message = last_message.get("original_message", "")
                    if user_message is None or user_message == "":
                        for attachment in last_message.get("attachments", []):
                             if attachment.get("type") == "photo":
                                 user_message = attachment.get("url", "")
                                 break
                        if not user_message: # Nếu vẫn không có gì thì đặt mặc định
                            user_message = "Ok"
                    for message in messages:
                        ms = message.get("original_message", "")
                        if "AF-FB-MES-HIEU-A3L" in ms:
                            user_message += f"Nguồn: {ms}"
                            break
                    if len(last_message.get("attachments", [])) > 0:
                        # Nguồn quảng cáo của sản phẩm
                        ads_source = last_message.get("attachments", [])[-1].get("name", "")
                        if ads_source:
                            user_message += f" (Nguồn sản phẩm: {ads_source})"
                         
                    source = ""
                    if activities:
                        source = activities[-1].get("message", "")

                    return source, user_message

                else:
                    error_text = await response.text()
                    logger.error(f"⚠️ Lỗi khi load last message ({conversation_id}): {response.status} - {error_text}")
                    return "", ""
        except aiohttp.ClientError as e:
            logger.error(f"⚠️ Lỗi mạng khi load last message ({conversation_id}): {e}")
            return "", f"Error: Network issue"
        except Exception as e:
            logger.error(f"⚠️ Lỗi không xác định khi load last message ({conversation_id}): {e}", exc_info=True)
            return "", f"Error: Unknown"

    
    async def send_message(self, page_id: str, conversation_id: str, message: str, msg_type: str = "text", content_url: str = "") -> bool:
        """Gửi tin nhắn (text hoặc image) đến cuộc hội thoại."""
        if not self.access_token:
            logger.error(f"Thiếu access_token để gửi tin nhắn cho conversation {conversation_id}")
            return False

        url = f"{self.BASE_URL_V1}/pages/{page_id}/conversations/{conversation_id}/messages"
        params = {"access_token": self.access_token}
        headers = {"page_id": page_id, "conversation_id": conversation_id}
        data = {"action": "reply_inbox", "message": message}

        if msg_type == "image" and content_url:
            data["content_url"] = content_url
            if not message:
                data["message"] = " "

        session = await self._get_session()
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with session.post(url, params=params, headers=headers, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"Thông tin tn: {result}")
                        logger.info(f"✅ Gửi tin nhắn thành công đến {conversation_id}: {result.get('id')}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"⚠️ Lỗi gửi tin nhắn đến {conversation_id} (lần {attempt + 1}): {response.status} - {error_text}")
                        if response.status >= 500 and attempt < max_retries - 1:
                            await asyncio.sleep(1)
                            continue
                        return False
            except aiohttp.ClientError as e:
                logger.error(f"⚠️ Lỗi mạng khi gửi tin nhắn đến {conversation_id} (lần {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                return False
            except Exception as e:
                logger.error(f"⚠️ Lỗi không xác định khi gửi tin nhắn đến {conversation_id} (lần {attempt + 1}): {e}", exc_info=True)
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                return False
        return False

    async def _manage_tags(self, action: str, page_id: str, conversation_id: str, tag_id: str) -> bool:
        """Hàm chung để thêm hoặc xóa tag (sử dụng aiohttp)."""
        page_token = await self._get_page_token(page_id)
        if not page_token:
            logger.error(f"Không tìm thấy page_access_token cho page_id: {page_id} khi {action} tag")
            return False

        url = f"{self.BASE_URL_PUBLIC_V1}/pages/{page_id}/conversations/{conversation_id}/tags"
        params = {
            "page_id": page_id,
            "page_access_token": page_token,
            "conversation_id": conversation_id,
        }
        data = {"action": action, "tag_id": tag_id}
        session = await self._get_session()
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with session.post(url, params=params, data=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"✅ {action.capitalize()} tag {tag_id} cho {conversation_id} thành công: {result}")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"⚠️ Lỗi khi {action} tag {tag_id} cho {conversation_id} (lần {attempt + 1}): {response.status} - {error_text}")
                        if response.status >= 500 and attempt < max_retries - 1:
                            await asyncio.sleep(1)
                            continue
                        return False
            except aiohttp.ClientError as e:
                logger.error(f"⚠️ Lỗi mạng khi {action} tag {tag_id} cho {conversation_id} (lần {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                return False
            except Exception as e:
                logger.error(f"⚠️ Lỗi không xác định khi {action} tag {tag_id} cho {conversation_id} (lần {attempt + 1}): {e}", exc_info=True)
                if attempt < max_retries - 1:
                    await asyncio.sleep(1)
                    continue
                return False
        return False

    async def add_tags(self, page_id: str, conversation_id: str, tag_id: str) -> bool:
        """Thêm tag cho hội thoại (async)."""
        return await self._manage_tags("add tag", page_id, conversation_id, tag_id)

    async def remove_tags(self, page_id: str, conversation_id: str, tag_id: str) -> bool:
        """Xóa tag khỏi hội thoại (async)."""
        return await self._manage_tags("remove tag", page_id, conversation_id, tag_id)