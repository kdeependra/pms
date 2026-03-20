from pydantic_settings import BaseSettings
from typing import List, Optional

class Settings(BaseSettings):
    # App Configuration
    APP_NAME: str = "AI-PMS"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"
    
    # Database Configuration  
    DATABASE_URL: str = "sqlite:////D:/deependra/codenticai/pms/pms_dev.db"
    MONGODB_URL: Optional[str] = None
    REDIS_URL: Optional[str] = None
    ELASTICSEARCH_URL: Optional[str] = None
    
    # Security
    SECRET_KEY: str = "dev-secret-key-change-in-production-min-32-characters-long"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:19006"
    
    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
    
    # AI Configuration
    AI_MODEL_PATH: str = "./models"
    AI_SERVICE_URL: Optional[str] = None
    
    # External APIs
    TABLEAU_API_URL: Optional[str] = None
    HRMS_API_URL: Optional[str] = None
    FMIS_API_URL: Optional[str] = None
    IVALUA_API_URL: Optional[str] = None
    BMC_REMEDY_API_URL: Optional[str] = None
    
    # Email
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    
    # File Storage
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE: int = 10485760  # 10MB
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
