import logging
import os
import sys


class _Formatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record.levelname = f" {record.levelname} "
        return super().format(record)


def setup_logging() -> None:
    """Configure logging for the entire application.

    Set LOG_LEVEL env var to DEBUG, INFO, WARNING, ERROR, or CRITICAL.
    Defaults to INFO.
    """
    # Import here to avoid circular dependency (config imports os, not logging)
    from config import cfg

    level = getattr(logging, cfg.log_level, logging.INFO)

    formatter = _Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)
    root.addHandler(handler)

    # Reduce noise from third-party libraries
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("langchain").setLevel(logging.WARNING)
    logging.getLogger("langsmith").setLevel(logging.WARNING)
