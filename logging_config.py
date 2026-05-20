from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
MAX_LOG_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 3
TOKEN_URL_PATTERN = re.compile(r"/bot[^/\s?]+")


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact_sensitive_values(super().format(record))


def redact_sensitive_values(text: str) -> str:
    return TOKEN_URL_PATTERN.sub("/bot<redacted>", text)


def setup_logging(level: str, log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    formatter = RedactingFormatter(LOG_FORMAT, DATE_FORMAT)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=MAX_LOG_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(numeric_level)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("telebot").setLevel(logging.INFO)
