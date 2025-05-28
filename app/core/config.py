from pydantic_settings import BaseSettings
from typing import Optional
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

# Load environment variables from .env
load_dotenv()

class Settings(BaseSettings):
    # API Settings
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    DEBUG: bool = True
    SECRET_KEY: str = "your-secret-key-here"

    # Neo4j Settings
    NEO4J_URI: str = "bolt://localhost:7687"  # Use 7687, not 7689
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"

    # ElevenLabs API
    ELEVENLABS_API_KEY: Optional[str] = None

    # LinkedIn API
    LINKEDIN_CLIENT_ID: Optional[str] = None
    LINKEDIN_CLIENT_SECRET: Optional[str] = None

    # Vector DB
    VECTOR_DB_HOST: str = "localhost"
    VECTOR_DB_PORT: int = 6333
    VECTOR_DB_NAME: str = "recommendations"

    class Config:
        env_file = ".env"  # ✅ Automatically load .env file
        case_sensitive = True

settings = Settings()

# Log the settings (without password)
logger.info("Loaded settings:")
logger.info(f"NEO4J_URI: {settings.NEO4J_URI}")
logger.info(f"NEO4J_USER: {settings.NEO4J_USER}")
logger.info("NEO4J_PASSWORD: [REDACTED]")
