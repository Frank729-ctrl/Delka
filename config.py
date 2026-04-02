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

    # Google Gemini (OpenAI-compatible endpoint)
    GOOGLE_API_KEY: str = ""
    GEMINI_CHAT_MODEL: str = "gemini-2.5-pro"

    # Cerebras (OpenAI-compatible, free tier)
    CEREBRAS_API_KEY: str = ""
    CEREBRAS_CHAT_MODEL: str = "llama-3.3-70b"
    CEREBRAS_CODE_MODEL: str = "qwen3-235b"

    # Cohere (embeddings)
    COHERE_API_KEY: str = ""
    COHERE_EMBED_MODEL: str = "embed-v4.0"

    # NVIDIA NIM
    NVIDIA_API_KEY: str = ""
    NVIDIA_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    NVIDIA_CHAT_MODEL: str = "meta/llama-3.1-70b-instruct"
    NVIDIA_OCR_MODEL: str = "nvidia/neva-22b"
    NVIDIA_STT_MODEL: str = "nvidia/parakeet-ctc-1.1b-asr"
    NVIDIA_TTS_MODEL: str = "nvidia/fastpitch-hifigan-tts"
    NVIDIA_EMBED_MODEL: str = "nvidia/nv-embedqa-e5-v5"
    NVIDIA_RERANK_MODEL: str = "nvidia/nv-rerankqa-mistral-4b-v3"
    NVIDIA_TRANSLATE_MODEL: str = "meta/nllb-200-1.3b"
    NVIDIA_CODE_MODEL: str = "nvidia/starcoder2-15b"
    NVIDIA_DETECTION_MODEL: str = "nvidia/nemoguard-8b-content-safety"
    NVIDIA_IMAGE_GEN_MODEL: str = "stabilityai/stable-diffusion-xl-base-1.0"
    NVIDIA_SAFETY_MODEL: str = "nvidia/llama-3.1-nemoguard-8b-content-safety"

    # Plugin API keys
    YOUTUBE_API_KEY: str = ""
    GNEWS_API_KEY: str = ""

    # Tavily web search
    TAVILY_API_KEY: str = ""
    TAVILY_SEARCH_DEPTH: str = "basic"
    TAVILY_MAX_RESULTS: int = 5
    SEARCH_ENABLED: bool = True
    USE_AUTOMATIC_TOOL_SEARCH: bool = False

    # CV task — Gemini → Groq → NVIDIA → Ollama
    CV_PRIMARY_PROVIDER: str = "gemini"
    CV_PRIMARY_MODEL: str = "gemini-2.5-pro"
    CV_SECONDARY_PROVIDER: str = "groq"
    CV_SECONDARY_MODEL: str = "llama-3.3-70b-versatile"
    CV_TERTIARY_PROVIDER: str = "nvidia"
    CV_TERTIARY_MODEL: str = "meta/llama-3.1-70b-instruct"
    CV_FALLBACK_PROVIDER: str = "ollama"
    CV_FALLBACK_MODEL: str = "llama3.1"

    # Cover letter task — Gemini → Groq → NVIDIA → Ollama
    LETTER_PRIMARY_PROVIDER: str = "gemini"
    LETTER_PRIMARY_MODEL: str = "gemini-2.5-pro"
    LETTER_SECONDARY_PROVIDER: str = "groq"
    LETTER_SECONDARY_MODEL: str = "llama-3.3-70b-versatile"
    LETTER_TERTIARY_PROVIDER: str = "nvidia"
    LETTER_TERTIARY_MODEL: str = "meta/llama-3.1-70b-instruct"
    LETTER_FALLBACK_PROVIDER: str = "ollama"
    LETTER_FALLBACK_MODEL: str = "llama3.1"

    # Support / chat task — Groq → Cerebras → Ollama
    SUPPORT_PRIMARY_PROVIDER: str = "groq"
    SUPPORT_PRIMARY_MODEL: str = "llama-3.1-8b-instant"
    SUPPORT_SECONDARY_PROVIDER: str = "cerebras"
    SUPPORT_SECONDARY_MODEL: str = "llama-3.3-70b"
    SUPPORT_FALLBACK_PROVIDER: str = "ollama"
    SUPPORT_FALLBACK_MODEL: str = "mistral"

    # Code generation — Cerebras → Groq → Ollama
    CODE_PRIMARY_PROVIDER: str = "cerebras"
    CODE_PRIMARY_MODEL: str = "qwen3-235b"
    CODE_SECONDARY_PROVIDER: str = "groq"
    CODE_SECONDARY_MODEL: str = "llama-3.3-70b-versatile"
    CODE_FALLBACK_PROVIDER: str = "ollama"
    CODE_FALLBACK_MODEL: str = "codellama"

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
    RESEND_FROM_EMAIL: str = "support@snafrate.com"

    # A/B Testing
    AB_TEST_ENABLED: bool = False
    AB_TEST_SERVICE: str = "cv"
    AB_TEST_MODEL_A_PROVIDER: str = "groq"
    AB_TEST_MODEL_A_MODEL: str = "llama-3.3-70b-versatile"
    AB_TEST_MODEL_A_WEIGHT: float = 0.5
    AB_TEST_MODEL_B_PROVIDER: str = "ollama"
    AB_TEST_MODEL_B_MODEL: str = "delkaai-cv-v1"
    AB_TEST_MODEL_B_WEIGHT: float = 0.5

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
