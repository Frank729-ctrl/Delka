import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from config import settings

_LOGS_DIR = Path("logs")
_LOGS_DIR.mkdir(exist_ok=True)


def _build_logger(
    name: str,
    log_file: str,
    backup_days: int,
) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    file_handler = TimedRotatingFileHandler(
        filename=_LOGS_DIR / log_file,
        when="D",
        interval=1,
        backupCount=backup_days,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if settings.APP_ENV != "production":
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    return logger


request_logger = _build_logger(
    name="delkaai.requests",
    log_file="requests.log",
    backup_days=7,
)

security_logger_instance = _build_logger(
    name="delkaai.security",
    log_file="security.log",
    backup_days=90,
)
