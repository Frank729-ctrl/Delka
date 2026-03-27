from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # App
    APP_ENV: str = "development"
    PORT: int = 8000

    # Security
    SECRET_MASTER_KEY: str = "fd-delka-mk-replace-this"

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
