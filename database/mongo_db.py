import logging
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from functools import lru_cache
import asyncio
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError, OperationFailure

from database.models import (
    ConversationDocument, 
    PageDocument
)
from config.settings import BackendConfig

# Cấu hình logging
logger = logging.getLogger(__name__)

# Khởi tạo cấu hình từ biến môi trường
settings = BackendConfig()

class MongoClient:
    def __init__(self):
        """Khởi tạo kết nối MongoDB với thông số tối ưu cho pooling"""
        self._client = None
        self._initialized = False
        self._connection_lock = asyncio.Lock()

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        retry=retry_if_exception_type((ConnectionFailure, ServerSelectionTimeoutError)),
        before_sleep=lambda retry_state: logger.warning(
            f"Thử kết nối MongoDB lần {retry_state.attempt_number}, "
            f"chờ {retry_state.retry_object.wait(retry_state.attempt_number)} giây..."
        )
    )
    async def _create_client(self):
        """Tạo kết nối MongoDB với retry pattern"""
        
        connection_string = "mongodb://{username}:{password}@{host}:{port}/{database}?authSource=admin".format(
            username=settings.MONGO_USERNAME,
            password=settings.MONGO_PASSWORD,
            host=settings.MONGO_HOST,
            port=settings.MONGO_PORT,
            database=settings.MONGO_DB
        )
        
        log_conn_string = f"mongodb://{settings.MONGO_USERNAME}:****@{settings.MONGO_HOST}:{settings.MONGO_PORT}/{settings.MONGO_DB}?authSource=admin"
        logger.info(f"Đang kết nối đến MongoDB: {log_conn_string}")
        
        try:
            # Cấu hình connection pool
            self._client = AsyncIOMotorClient(
                connection_string,
                maxPoolSize=50,               
                minPoolSize=5,                
                maxIdleTimeMS=60000,          
                connectTimeoutMS=5000,        
                serverSelectionTimeoutMS=5000, 
                retryWrites=True,             
                retryReads=True,              
            )
            logger.info(f"Đã kết nối thành công đến MongoDB tại {settings.MONGO_HOST}:{settings.MONGO_PORT}")
            return self._client
        except (ConnectionFailure, ServerSelectionTimeoutError, OperationFailure) as e:
            logger.error(f"Lỗi kết nối MongoDB: {e}")
            raise
        except Exception as e:
            logger.error(f"Lỗi không xác định khi kết nối MongoDB: {e}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((ConnectionFailure, ServerSelectionTimeoutError, OperationFailure))
    )
    async def init(self):
        """Khởi tạo Beanie ODM với database và models"""
        async with self._connection_lock:
            if self._initialized:
                return
            if self._client is None:
                self._client = await self._create_client()
            try:
                await init_beanie(
                    database=self._client[settings.MONGO_DB], 
                    document_models=[
                        ConversationDocument, 
                        PageDocument
                    ]
                )
                # Đánh dấu đã khởi tạo thành công
                self._initialized = True
                logger.info(f"Đã khởi tạo Beanie với database {settings.MONGO_DB}")
                
            except Exception as e:
                logger.error(f"Không thể khởi tạo Beanie: {e}")
                self._client = None
                self._initialized = False
                raise

    @property
    def client(self):
        """Trả về MongoDB client nếu đã khởi tạo"""
        if self._client is None:
            raise RuntimeError("MongoDB client chưa được khởi tạo. Hãy gọi init() trước.")
        return self._client
        
    @property
    def is_connected(self):
        """Kiểm tra xem đã kết nối thành công chưa"""
        return self._initialized and self._client is not None
        
# Singleton instance
mongo_client = MongoClient()

@lru_cache(maxsize=1)
def get_mongo_client() -> MongoClient:
    """Trả về singleton instance của MongoDB client, với cache"""
    return mongo_client

async def init_mongo():
    """Khởi tạo kết nối MongoDB và Beanie với retry pattern"""
    try:
        await mongo_client.init()
        logger.info("MongoDB client đã được khởi tạo thành công")
        
        # Khởi tạo pages mặc định
        from database.page.page_service import init_default_pages
        await init_default_pages()
        
        return True
    except Exception as e:
        logger.error(f"Lỗi khởi tạo MongoDB: {e}")
        return False
