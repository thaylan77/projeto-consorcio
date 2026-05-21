import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

from config import LOG_FILE, LOG_MAX_MB, LOG_BACKUP_COUNT

_python_logger = logging.getLogger("consorcio")

if not _python_logger.handlers:
    _python_logger.setLevel(logging.DEBUG)
    _handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=LOG_MAX_MB * 1024 * 1024,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    _handler.setFormatter(logging.Formatter("%(message)s"))
    _python_logger.addHandler(_handler)


def log(mensagem: str, level: str = "INFO", modulo: str = "Sistema") -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] [{modulo}] {mensagem}"
    print(line)
    _python_logger.info(line)
