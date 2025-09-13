import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional, Dict, List

from database.models import PageDocument, PageTag
from database.page.token_service import get_token_service

logger = logging.getLogger(__name__)

class PageService:
    def __init__(self):
        self.token_service = get_token_service()
    
    async def create_page(self, page_id: str, page_name: str, token: str, tags: Optional[List[Dict]] = None) -> bool:
        """Tạo page mới"""
        try:
            existing = await PageDocument.find_one({"page_id": page_id})
            if existing:
                logger.info(f"Page {page_id} đã tồn tại, bỏ qua tạo mới")
                return True
            
            encrypted_token = self.token_service.encrypt_token(token)
            
            # Chuyển đổi tags từ Dict sang PageTag objects
            page_tags = []
            if tags:
                for tag in tags:
                    page_tags.append(PageTag(
                        tag_name=tag["tag_name"], 
                        tag_id=tag["tag_id"]
                    ))
            
            page = PageDocument(
                page_id=page_id,
                page_name=page_name,
                encrypted_token=encrypted_token,
                tags=page_tags,
                is_active=True,
                created_at=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")),
                updated_at=datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
            )
            
            await page.save()
            logger.info(f"Đã tạo page: {page_name} ({page_id}) với {len(page_tags)} tags")
            return True
            
        except Exception as e:
            logger.error(f"Lỗi tạo page {page_id}: {e}")
            return False
    
    async def get_page_token(self, page_id: str) -> Optional[str]:
        """Lấy token của page"""
        try:
            page = await PageDocument.find_one({"page_id": page_id, "is_active": True})
            if not page:
                logger.warning(f"Không tìm thấy page {page_id}")
                return None
                
            return self.token_service.decrypt_token(page.encrypted_token)
        except Exception as e:
            logger.error(f"Lỗi lấy token page {page_id}: {e}")
            return None
    
    async def get_page_info(self, page_id: str, active_only: bool = False) -> Optional[Dict]:
        """Lấy thông tin page"""
        try:
            if active_only:
                page = await PageDocument.find_one({"page_id": page_id, "is_active": True})
            else:
                page = await PageDocument.find_one({"page_id": page_id})
            
            if not page:
                return None
                
            token = self.token_service.decrypt_token(page.encrypted_token)
            return {
                "page_id": page.page_id,
                "page_name": page.page_name,
                "page_access_token": token,
                "tags": [{"tag_name": tag.tag_name, "tag_id": tag.tag_id} for tag in page.tags] if page.tags else [],
                "is_active": page.is_active
            }
        except Exception as e:
            logger.error(f"Lỗi lấy thông tin page {page_id}: {e}")
            return None

    async def get_all_active_pages(self) -> List[Dict]:
        """Lấy tất cả pages active"""
        try:
            pages = await PageDocument.find({"is_active": True}).to_list()
            result = []
            
            for page in pages:
                token = self.token_service.decrypt_token(page.encrypted_token)
                result.append({
                    "page_id": page.page_id,
                    "page_name": page.page_name,
                    "page_access_token": token,
                    "tags": [{"tag_name": tag.tag_name, "tag_id": tag.tag_id} for tag in page.tags] if page.tags else [],
                    "is_active": page.is_active
                })
            return result
        except Exception as e:
            return []
            
    async def get_all_pages(self) -> List[Dict]:
        """Lấy tất cả pages"""
        try:
            pages = await PageDocument.find({}).to_list()
            result = []
            for page in pages:
                result.append({
                    "page_id": page.page_id,
                    "page_name": page.page_name,
                    "page_access_token": self.token_service.decrypt_token(page.encrypted_token),
                    "tags": [{"tag_name": tag.tag_name, "tag_id": tag.tag_id} for tag in page.tags] if page.tags else [],
                    "is_active": page.is_active
                })
            return result
        except Exception as e:
            return []
    
    async def update_page(self, page_id: str, page_name: Optional[str] = None, token: Optional[str] = None, 
                         tags: Optional[List[Dict]] = None) -> bool:
        """Cập nhật thông tin page"""
        try:
            page = await PageDocument.find_one({"page_id": page_id})
            if not page:
                logger.warning(f"Không tìm thấy page {page_id}")
                return False
            
            # Cập nhật các trường được cung cấp
            if page_name is not None:
                page.page_name = page_name
            if token is not None:
                page.encrypted_token = self.token_service.encrypt_token(token)
            if tags is not None:
                # Chuyển đổi tags từ Dict sang PageTag objects
                page_tags = []
                for tag in tags:
                    page_tags.append(PageTag(
                        tag_name=tag["tag_name"], 
                        tag_id=tag["tag_id"]
                    ))
                page.tags = page_tags
            
            page.updated_at = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
            await page.save()
            
            logger.info(f"Đã cập nhật page: {page_id}")
            return True
            
        except Exception as e:
            logger.error(f"Lỗi cập nhật page {page_id}: {e}")
            return False
    
    async def add_page_tag(self, page_id: str, tag_name: str, tag_id: str) -> bool:
        """Thêm tag mới cho page"""
        try:
            page = await PageDocument.find_one({"page_id": page_id})
            if not page:
                logger.warning(f"Không tìm thấy page {page_id}")
                return False
            
            # Kiểm tra tag đã tồn tại chưa
            if page.tags:
                for existing_tag in page.tags:
                    if existing_tag.tag_id == tag_id or existing_tag.tag_name == tag_name:
                        logger.warning(f"Tag {tag_name} ({tag_id}) đã tồn tại cho page {page_id}")
                        return False
            
            # Thêm tag mới
            new_tag = PageTag(tag_name=tag_name, tag_id=tag_id)
            if page.tags is None:
                page.tags = []
            page.tags.append(new_tag)
            
            page.updated_at = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
            await page.save()
            
            logger.info(f"Đã thêm tag {tag_name} ({tag_id}) cho page {page_id}")
            return True
            
        except Exception as e:
            logger.error(f"Lỗi thêm tag cho page {page_id}: {e}")
            return False
    
    async def remove_page_tag(self, page_id: str, tag_id: str) -> bool:
        """Xóa tag khỏi page"""
        try:
            page = await PageDocument.find_one({"page_id": page_id})
            if not page:
                logger.warning(f"Không tìm thấy page {page_id}")
                return False
            
            if not page.tags:
                logger.warning(f"Page {page_id} không có tag nào")
                return False
            
            # Tìm và xóa tag
            original_count = len(page.tags)
            page.tags = [tag for tag in page.tags if tag.tag_id != tag_id]
            
            if len(page.tags) == original_count:
                logger.warning(f"Không tìm thấy tag với ID {tag_id} trong page {page_id}")
                return False
            
            page.updated_at = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
            await page.save()
            
            logger.info(f"Đã xóa tag ID {tag_id} khỏi page {page_id}")
            return True
            
        except Exception as e:
            logger.error(f"Lỗi xóa tag khỏi page {page_id}: {e}")
            return False
    
    async def get_page_tags(self, page_id: str) -> List[Dict]:
        """Lấy danh sách tags của page"""
        try:
            page = await PageDocument.find_one({"page_id": page_id})
            if not page:
                logger.warning(f"Không tìm thấy page {page_id}")
                return []
            
            if not page.tags:
                return []
            
            return [{"tag_name": tag.tag_name, "tag_id": tag.tag_id} for tag in page.tags]
            
        except Exception as e:
            logger.error(f"Lỗi lấy tags của page {page_id}: {e}")
            return []

    async def update_page_status(self, page_id: str, is_active: bool) -> bool:
        """Cập nhật trạng thái active/inactive của page"""
        try:
            page = await PageDocument.find_one({"page_id": page_id})
            if not page:
                logger.warning(f"Không tìm thấy page {page_id}")
                return False
            
            page.is_active = is_active
            page.updated_at = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
            await page.save()
            
            status_text = "kích hoạt" if is_active else "vô hiệu hóa"
            logger.info(f"Đã {status_text} page: {page_id}")
            return True
            
        except Exception as e:
            logger.error(f"Lỗi cập nhật trạng thái page {page_id}: {e}")
            return False
    
    async def delete_page(self, page_id: str) -> bool:
        """Soft delete page (set is_active = False)"""
        try:
            return await self.update_page_status(page_id, False)
        except Exception as e:
            logger.error(f"Lỗi xóa page {page_id}: {e}")
            return False

# Singleton instance
_page_service = None

def get_page_service() -> PageService:
    """Trả về singleton instance của PageService"""
    global _page_service
    if _page_service is None:
        _page_service = PageService()
    return _page_service

async def init_default_pages():
    page_service = get_page_service()
    # Định nghĩa các pages mặc định ở đây hoặc lấy từ biến môi trường
    # default_pages = [
    #     {
    #         "page_id":  "<ID page của bạn>",
    #         "page_name": "<Tên page của bạn>",
    #         "token": "<Token của bạn>",
    #         "active": True
    #     }
    # ]
    default_pages = []

    for page_data in default_pages:
        if not page_data["token"]:
            logger.warning(f"Không có token cho page {page_data['page_name']}")
            continue
        # Kiểm tra xem page đã tồn tại chưa bằng hàm có sẵn
        existing_pages = await page_service.get_page_info(page_data["page_id"])
        if existing_pages:
            logger.info(f"Page {page_data['page_name']} đã tồn tại, bỏ qua tạo mới")
            continue

        success = await page_service.create_page(
            page_id=page_data["page_id"],
            page_name=page_data["page_name"], 
            token=page_data["token"],
            tags=page_data.get("tags", [])
        )
        
        if success:
            logger.info(f"✅ Page {page_data['page_name']} khởi tạo thành công")
        else:
            logger.error(f"❌ Lỗi khởi tạo page {page_data['page_name']}")
    
    logger.info("Hoàn thành khởi tạo pages mặc định") 