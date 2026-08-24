from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


def setup_logging(level: str | None = None) -> None:
    """Configure structured logging for SmartRoute."""
    log_level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    numeric_level = getattr(logging, log_level, logging.INFO)

    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)

    # Quiet noisy loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("anyio").setLevel(logging.WARNING)

    # Set SmartRoute loggers
    for name in ["smartroute", "smartroute.api", "smartroute.agents", "smartroute.services"]:
        logger = logging.getLogger(name)
        logger.setLevel(numeric_level)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the smartroute prefix."""
    if not name.startswith("smartroute"):
        name = f"smartroute.{name}"
    return logging.getLogger(name)
