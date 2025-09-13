import os
from dotenv import load_dotenv
from pydantic import BaseModel

# Load biến môi trường từ file .env
load_dotenv()


class BackendConfig(BaseModel):
    # General settings
    PORT: int = int(os.getenv("PORT",13994))
    
    # MongoDB settings
    MONGO_HOST: str = os.getenv("MONGO_HOST", "localhost")
    MONGO_PORT: int = int(os.getenv("MONGO_PORT", "27017"))
    MONGO_USERNAME: str = os.getenv("MONGO_USERNAME", "")
    MONGO_PASSWORD: str = os.getenv("MONGO_PASSWORD", "")
    MONGO_DB: str = os.getenv("MONGO_DB", "pancake_bot") 

    # Pancake settings
    PANCAKE_ACCESS_TOKEN: str = os.getenv("PANCAKE_ACCESS_TOKEN", "")
    PANCAKE_USER_ID: str = os.getenv("PANCAKE_USER_ID", "")

    # AI settings
    ENDPOINT_AI_URL: str = os.getenv("ENDPOINT_AI_URL", "")