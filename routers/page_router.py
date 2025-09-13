from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from pydantic import BaseModel
import logging

from database.page.page_service import get_page_service, PageService
from events.page_events import get_page_event_bus, PageEventBus, PageEvent, PageEventType

logger = logging.getLogger(__name__)

# Request/Response models
class PageTagModel(BaseModel):
    tag_name: str
    tag_id: str

class CreatePageRequest(BaseModel):
    page_id: str
    page_name: str
    token: str
    tags: Optional[List[PageTagModel]] = []

class UpdatePageRequest(BaseModel):
    page_name: Optional[str] = None
    token: Optional[str] = None
    tags: Optional[List[PageTagModel]] = None

class PageResponse(BaseModel):
    page_id: str
    page_name: str
    page_access_token: str
    tags: List[PageTagModel]
    is_active: bool

class AddTagRequest(BaseModel):
    tag_name: str
    tag_id: str

class PageStatusRequest(BaseModel):
    is_active: bool

# Router instance
page_router = APIRouter(
    prefix="/api/v1/pages",
    tags=["pages"],
    responses={404: {"description": "Page not found"}}
)

@page_router.get("/", response_model=List[PageResponse])
async def get_pages(
    page_service: PageService = Depends(get_page_service)
):
    """Lấy danh sách tất cả pages"""
    try:
        pages = await page_service.get_all_pages()
        return [PageResponse(**page) for page in pages]
    except Exception as e:
        logger.error(f"Lỗi khi lấy danh sách pages: {e}")
        raise HTTPException(status_code=500, detail="Lỗi khi lấy danh sách pages")

@page_router.get("/{page_id}", response_model=PageResponse)
async def get_page(
    page_id: str,
    page_service: PageService = Depends(get_page_service)
):
    """Lấy thông tin một page cụ thể"""
    try:
        page = await page_service.get_page_info(page_id)
        if not page:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy page {page_id}")
        
        return PageResponse(**page)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy thông tin page {page_id}: {e}")
        raise HTTPException(status_code=500, detail="Lỗi khi lấy thông tin page")

@page_router.post("/", response_model=dict)
async def create_page(
    request: CreatePageRequest,
    page_service: PageService = Depends(get_page_service),
    event_bus: PageEventBus = Depends(get_page_event_bus)
):
    """Tạo page mới"""
    try:
        # Kiểm tra page đã tồn tại chưa
        existing_page = await page_service.get_page_info(request.page_id)
        if existing_page:
            raise HTTPException(status_code=400, detail=f"Page {request.page_id} đã tồn tại")
        
        # Tạo page mới
        tags_dict = [tag.dict() for tag in request.tags] if request.tags else []
        success = await page_service.create_page(
            page_id=request.page_id,
            page_name=request.page_name,
            token=request.token,
            tags=tags_dict
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Không thể tạo page")
        
        # Lấy thông tin page vừa tạo
        page_info = await page_service.get_page_info(request.page_id)
        
        # Emit event
        await event_bus.emit(PageEvent(
            event_type=PageEventType.PAGE_CREATED,
            page_id=page_info.page_id,
            page_data=page_info
        ))
        
        logger.info(f"Đã tạo page mới: {page_info.page_name} ({page_info.page_id})")
        return {
            "status": "success",
            "message": f"Đã tạo page {page_info.page_name} thành công",
            "page": page_info
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi tạo page: {e}")
        raise HTTPException(status_code=500, detail="Lỗi khi tạo page")

@page_router.put("/{page_id}", response_model=dict)
async def update_page(
    page_id: str,
    request: UpdatePageRequest,
    page_service: PageService = Depends(get_page_service),
    event_bus: PageEventBus = Depends(get_page_event_bus)
):
    """Cập nhật thông tin page"""
    try:
        # Kiểm tra page có tồn tại không
        existing_page = await page_service.get_page_info(page_id)
        if not existing_page:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy page {page_id}")
        
        # Cập nhật page
        tags_dict = [tag.dict() for tag in request.tags] if request.tags else None
        success = await page_service.update_page(
            page_id=page_id,
            page_name=request.page_name,
            token=request.token,
            tags=tags_dict
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Không thể cập nhật page")
        
        # Lấy thông tin page sau khi update
        updated_page = await page_service.get_page_info(page_id)
        
        # Emit event
        await event_bus.emit(PageEvent(
            event_type=PageEventType.PAGE_UPDATED,
            page_id=page_id,
            page_data=updated_page
        ))
        
        logger.info(f"Đã cập nhật page: {page_id}")
        return {
            "status": "success",
            "message": f"Đã cập nhật page {page_id} thành công",
            "page": updated_page
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật page {page_id}: {e}")
        raise HTTPException(status_code=500, detail="Lỗi khi cập nhật page")

@page_router.patch("/{page_id}/status", response_model=dict)
async def update_page_status(
    page_id: str,
    request: PageStatusRequest,
    page_service: PageService = Depends(get_page_service),
    event_bus: PageEventBus = Depends(get_page_event_bus)
):
    """Kích hoạt/vô hiệu hóa page"""
    try:
        # Kiểm tra page có tồn tại không
        existing_page = await page_service.get_page_info(page_id)
        if not existing_page:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy page {page_id}")
        
        # Cập nhật trạng thái
        success = await page_service.update_page_status(page_id, request.is_active)
        
        if not success:
            raise HTTPException(status_code=500, detail="Không thể cập nhật trạng thái page")
        
        # Lấy thông tin page sau khi update
        updated_page = await page_service.get_page_info(page_id)
        
        # Emit event tương ứng
        event_type = PageEventType.PAGE_ACTIVATED if request.is_active else PageEventType.PAGE_DEACTIVATED
        await event_bus.emit(PageEvent(
            event_type=event_type,
            page_id=page_id,
            page_data=updated_page
        ))
        
        status_text = "kích hoạt" if request.is_active else "vô hiệu hóa"
        logger.info(f"Đã {status_text} page: {page_id}")
        return {
            "status": "success",
            "message": f"Đã {status_text} page {page_id} thành công",
            "page": updated_page
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi cập nhật trạng thái page {page_id}: {e}")
        raise HTTPException(status_code=500, detail="Lỗi khi cập nhật trạng thái page")

@page_router.delete("/{page_id}", response_model=dict)
async def delete_page(
    page_id: str,
    page_service: PageService = Depends(get_page_service),
    event_bus: PageEventBus = Depends(get_page_event_bus)
):
    """Xóa page (soft delete)"""
    try:
        # Kiểm tra page có tồn tại không
        existing_page = await page_service.get_page_info(page_id)
        if not existing_page:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy page {page_id}")
        
        # Soft delete (set is_active = False)
        success = await page_service.delete_page(page_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="Không thể xóa page")
        
        # Emit event
        await event_bus.emit(PageEvent(
            event_type=PageEventType.PAGE_DELETED,
            page_id=page_id,
            page_data=existing_page
        ))
        
        logger.info(f"Đã xóa page: {page_id}")
        return {
            "status": "success",
            "message": f"Đã xóa page {page_id} thành công"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa page {page_id}: {e}")
        raise HTTPException(status_code=500, detail="Lỗi khi xóa page")

@page_router.post("/reload", response_model=dict)
async def reload_pages(
    page_service: PageService = Depends(get_page_service),
    event_bus: PageEventBus = Depends(get_page_event_bus)
):
    """Trigger reload tất cả pages (force reload WebSocket connections)"""
    try:
        # Emit global reload event
        await event_bus.emit(PageEvent(
            event_type=PageEventType.PAGES_RELOADED,
            page_id="all",
            page_data={"action": "reload_all"}
        ))
        
        logger.info("Đã trigger reload tất cả pages")
        return {
            "status": "success",
            "message": "Đã trigger reload tất cả pages thành công"
        }
        
    except Exception as e:
        logger.error(f"Lỗi khi reload pages: {e}")
        raise HTTPException(status_code=500, detail="Lỗi khi reload pages")

@page_router.post("/{page_id}/tags", response_model=dict)
async def add_page_tag(
    page_id: str,
    request: AddTagRequest,
    page_service: PageService = Depends(get_page_service),
    event_bus: PageEventBus = Depends(get_page_event_bus)
):
    """Thêm tag mới cho page"""
    try:
        # Kiểm tra page có tồn tại không
        existing_page = await page_service.get_page_info(page_id)
        if not existing_page:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy page {page_id}")
        
        # Thêm tag
        success = await page_service.add_page_tag(page_id, request.tag_name, request.tag_id)
        
        if not success:
            raise HTTPException(status_code=400, detail="Không thể thêm tag (có thể đã tồn tại)")
        
        # Lấy thông tin page sau khi thêm tag
        updated_page = await page_service.get_page_info(page_id)
        
        # Emit event
        await event_bus.emit(PageEvent(
            event_type=PageEventType.PAGE_UPDATED,
            page_id=page_id,
            page_data=updated_page
        ))
        
        logger.info(f"Đã thêm tag {request.tag_name} cho page: {page_id}")
        return {
            "status": "success",
            "message": f"Đã thêm tag {request.tag_name} thành công",
            "page": updated_page
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi thêm tag cho page {page_id}: {e}")
        raise HTTPException(status_code=500, detail="Lỗi khi thêm tag")

@page_router.delete("/{page_id}/tags/{tag_id}", response_model=dict)
async def remove_page_tag(
    page_id: str,
    tag_id: str,
    page_service: PageService = Depends(get_page_service),
    event_bus: PageEventBus = Depends(get_page_event_bus)
):
    """Xóa tag khỏi page"""
    try:
        # Kiểm tra page có tồn tại không
        existing_page = await page_service.get_page_info(page_id)
        if not existing_page:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy page {page_id}")
        
        # Xóa tag
        success = await page_service.remove_page_tag(page_id, tag_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Không tìm thấy tag hoặc không thể xóa")
        
        # Lấy thông tin page sau khi xóa tag
        updated_page = await page_service.get_page_info(page_id)
        
        # Emit event
        await event_bus.emit(PageEvent(
            event_type=PageEventType.PAGE_UPDATED,
            page_id=page_id,
            page_data=updated_page
        ))
        
        logger.info(f"Đã xóa tag {tag_id} khỏi page: {page_id}")
        return {
            "status": "success",
            "message": f"Đã xóa tag {tag_id} thành công",
            "page": updated_page
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi xóa tag khỏi page {page_id}: {e}")
        raise HTTPException(status_code=500, detail="Lỗi khi xóa tag")

@page_router.get("/{page_id}/tags", response_model=List[PageTagModel])
async def get_page_tags(
    page_id: str,
    page_service: PageService = Depends(get_page_service)
):
    """Lấy danh sách tags của page"""
    try:
        # Kiểm tra page có tồn tại không
        existing_page = await page_service.get_page_info(page_id)
        if not existing_page:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy page {page_id}")
        
        # Lấy tags
        tags = await page_service.get_page_tags(page_id)
        
        return [PageTagModel(**tag) for tag in tags]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy tags của page {page_id}: {e}")
        raise HTTPException(status_code=500, detail="Lỗi khi lấy tags") 