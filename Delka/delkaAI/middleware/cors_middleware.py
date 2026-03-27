from config import settings


def get_cors_config() -> dict:
    origins = (
        [o.strip() for o in settings.ALLOWED_ORIGINS.split(",")]
        if settings.ALLOWED_ORIGINS != "*"
        else ["*"]
    )
    return {
        "allow_origins": origins,
        "allow_credentials": True,
        "allow_methods": ["*"],
        "allow_headers": [
            "*",
            "X-DelkaAI-Key",
            "X-DelkaAI-Timestamp",
            "X-DelkaAI-Signature",
            "X-DelkaAI-Master-Key",
        ],
    }
