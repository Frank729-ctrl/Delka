PK_ALLOWED_ENDPOINTS: list[str] = [
    "/v1/health",
    "/v1/support/chat",
    "/v1/vision/search",
    "/v1/chat",
    "/v1/feedback",
    # New Phase 8.5 endpoints — public key access
    "/v1/ocr/extract",
    "/v1/speech/transcribe",
    "/v1/tts/synthesize",
    "/v1/translate/",
    "/v1/code/generate",
    "/v1/detect/objects",
]

SK_ALLOWED_ENDPOINTS: list[str] = ["*"]  # all non-admin

ADMIN_ENDPOINTS: list[str] = ["/v1/admin/"]


def check_permission(key_type: str, path: str) -> bool:
    """Returns True if the key type is allowed to access the given path."""
    # Admin endpoints require master key — not a pk/sk concern
    for admin_prefix in ADMIN_ENDPOINTS:
        if path.startswith(admin_prefix):
            return False

    if key_type == "sk":
        return True

    if key_type == "pk":
        return any(path == ep or path.startswith(ep) for ep in PK_ALLOWED_ENDPOINTS)

    return False
