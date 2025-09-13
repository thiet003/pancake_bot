import os
import logging
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

class TokenService:
    def __init__(self):
        """Khởi tạo service mã hóa token"""
        encryption_key = os.getenv("ENCRYPTION_KEY")
        
        if not encryption_key:
            # Tạo key mới nếu chưa có (chỉ dùng cho development)
            encryption_key = Fernet.generate_key().decode()
            logger.warning(f"Tạo ENCRYPTION_KEY mới: {encryption_key}")
            logger.warning("Vui lòng thêm vào file .env: ENCRYPTION_KEY=" + encryption_key)
        
        try:
            if isinstance(encryption_key, str):
                encryption_key = encryption_key.encode()
            self.cipher = Fernet(encryption_key)
            logger.info("TokenService đã khởi tạo thành công")
        except Exception as e:
            logger.error(f"Lỗi khởi tạo TokenService: {e}")
            raise
    
    def encrypt_token(self, token: str) -> str:
        """Mã hóa token"""
        try:
            if not token:
                return ""
            encrypted = self.cipher.encrypt(token.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error(f"Lỗi mã hóa token: {e}")
            raise
    
    def decrypt_token(self, encrypted_token: str) -> str:
        """Giải mã token"""
        try:
            if not encrypted_token:
                return ""
            decrypted = self.cipher.decrypt(encrypted_token.encode())
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Lỗi giải mã token: {e}")
            raise

# Singleton instance
_token_service = None

def get_token_service() -> TokenService:
    """Trả về singleton instance của TokenService"""
    global _token_service
    if _token_service is None:
        _token_service = TokenService()
    return _token_service 