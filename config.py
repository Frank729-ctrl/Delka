from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # App
    APP_ENV: str = "development"
    PORT: int = 8000

    # Security
    SECRET_MASTER_KEY: str = "fd-delka-mk-replace-this"

    # Admin UI login
    ADMIN_EMAIL: str = "admin@example.com"
    ADMIN_PASSWORD: str = "change-me"

    # Database
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_NAME: str = "delkaai"
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DATABASE_URL: Optional[str] = None

    # Ollama
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.1"
    OLLAMA_TIMEOUT_SECONDS: int = 120
    OLLAMA_STREAM_TIMEOUT_SECONDS: int = 60

    # Argon2
    ARGON2_TIME_COST: int = 3
    ARGON2_MEMORY_COST: int = 65536
    ARGON2_PARALLELISM: int = 2

    # HMAC
    HMAC_TIMESTAMP_TOLERANCE_SECONDS: int = 300

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 30
    RATE_LIMIT_PER_IP_MINUTE: int = 60
    RATE_LIMIT_BURST_PER_SECOND: int = 5

    # Groq
    GROQ_API_KEY: str = ""

    # CV task
    CV_PRIMARY_PROVIDER: str = "groq"
    CV_PRIMARY_MODEL: str = "llama-3.3-70b-versatile"
    CV_FALLBACK_PROVIDER: str = "ollama"
    CV_FALLBACK_MODEL: str = "llama3.1"

    # Cover letter task
    LETTER_PRIMARY_PROVIDER: str = "groq"
    LETTER_PRIMARY_MODEL: str = "llama-3.3-70b-versatile"
    LETTER_FALLBACK_PROVIDER: str = "ollama"
    LETTER_FALLBACK_MODEL: str = "llama3.1"

    # Support chat task
    SUPPORT_PRIMARY_PROVIDER: str = "groq"
    SUPPORT_PRIMARY_MODEL: str = "llama-3.1-8b-instant"
    SUPPORT_FALLBACK_PROVIDER: str = "ollama"
    SUPPORT_FALLBACK_MODEL: str = "mistral"

    # Visual Search
    VISION_PRIMARY_PROVIDER: str = "groq"
    VISION_PRIMARY_MODEL: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    VISION_FALLBACK_PROVIDER: str = "ollama"
    VISION_FALLBACK_MODEL: str = "llava:13b"
    CHROMA_PERSIST_DIR: str = "./vector_store/chroma"
    EMBEDDING_MODEL: str = "clip-ViT-B-32"
    VISION_DEFAULT_LIMIT: int = 20
    VISION_DEFAULT_MIN_SIMILARITY: float = 0.65
    VISION_MAX_IMAGE_SIZE_MB: int = 10
    VISION_INDEX_BATCH_SIZE: int = 100

    # Resend email
    RESEND_API_KEY: str = ""
    RESEND_FROM_EMAIL: str = "noreply@delkaai.com"

    # Misc
    LLM_MAX_RETRIES: int = 2
    WEBHOOK_TIMEOUT_SECONDS: int = 10
    WEBHOOK_MAX_RETRIES: int = 3
    ALLOWED_ORIGINS: str = "*"
    METRICS_PERSIST_INTERVAL_SECONDS: int = 300

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def docs_url(self) -> Optional[str]:
        return None if self.is_production else "/docs"

    @property
    def redoc_url(self) -> Optional[str]:
        return None if self.is_production else "/redoc"


settings = Settings()
