"""Tests for core.logging_config — setup_logging() and get_logger()."""
from __future__ import annotations

import logging
import os
from unittest.mock import patch

import pytest


def test_get_logger_returns_logger():
    from core.logging_config import get_logger

    logger = get_logger("test")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "smartroute.test"


def test_get_logger_with_prefix():
    from core.logging_config import get_logger

    logger = get_logger("smartroute.api")
    assert logger.name == "smartroute.api"


def test_get_logger_adds_prefix():
    from core.logging_config import get_logger

    logger = get_logger("services.route")
    assert logger.name == "smartroute.services.route"


def test_setup_logging_sets_level():
    from core.logging_config import setup_logging

    setup_logging("DEBUG")
    root = logging.getLogger()
    assert root.level == logging.DEBUG

    # Reset to INFO
    setup_logging("INFO")


def test_setup_logging_defaults_to_info():
    from core.logging_config import setup_logging

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("LOG_LEVEL", None)
        setup_logging()

    root = logging.getLogger()
    assert root.level == logging.INFO


def test_setup_logging_reads_env_var():
    from core.logging_config import setup_logging

    with patch.dict(os.environ, {"LOG_LEVEL": "WARNING"}):
        setup_logging()

    root = logging.getLogger()
    assert root.level == logging.WARNING

    # Reset
    setup_logging("INFO")


def test_setup_logging_quietens_noisy_loggers():
    from core.logging_config import setup_logging

    setup_logging("INFO")

    assert logging.getLogger("urllib3").level == logging.WARNING
    assert logging.getLogger("anyio").level == logging.WARNING
