"""Centralized full diagnostics logging utilities."""

import json
import logging
import platform
import socket
import sys
import threading
import traceback
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
LOG_DIR = PROJECT_ROOT / "logs"
LOG_PATH = LOG_DIR / "full_diagnostics.log"
LOGGER_NAME = "tish.full_diagnostics"

_logger_lock = threading.Lock()
_logger = None
_hooks_installed = False


def _sanitize(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_sanitize(v) for v in value]
    try:
        return str(value)
    except Exception:
        return repr(value)


def _get_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger

    with _logger_lock:
        if _logger is not None:
            return _logger

        LOG_DIR.mkdir(exist_ok=True)
        logger = logging.getLogger(LOGGER_NAME)
        logger.setLevel(logging.INFO)
        logger.propagate = False

        if not logger.handlers:
            handler = RotatingFileHandler(
                str(LOG_PATH),
                maxBytes=20 * 1024 * 1024,
                backupCount=10,
                encoding="utf-8",
            )
            handler.setFormatter(logging.Formatter("%(message)s"))
            logger.addHandler(handler)

        _logger = logger
        return logger


def diagnostics_log_path() -> Path:
    return LOG_PATH


def log_event(event: str, level: str = "info", **fields: Any) -> None:
    level_map = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warn": logging.WARNING,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL,
    }
    payload = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "event": event,
    }
    for key, value in fields.items():
        payload[key] = _sanitize(value)

    try:
        logger = _get_logger()
        logger.log(level_map.get(level, logging.INFO), json.dumps(payload, ensure_ascii=False))
    except Exception:
        # Диагностика не должна ломать рабочий процесс
        pass


def install_exception_hooks() -> None:
    global _hooks_installed
    if _hooks_installed:
        return
    _hooks_installed = True

    previous_excepthook = sys.excepthook

    def _excepthook(exc_type, exc_value, exc_tb):
        log_event(
            "uncaught_exception",
            level="error",
            exc_type=getattr(exc_type, "__name__", str(exc_type)),
            error=str(exc_value),
            traceback="".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
        )
        if previous_excepthook:
            previous_excepthook(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook

    if hasattr(threading, "excepthook"):
        previous_thread_excepthook = threading.excepthook

        def _thread_excepthook(args):
            log_event(
                "thread_uncaught_exception",
                level="error",
                thread_name=getattr(args.thread, "name", ""),
                exc_type=getattr(args.exc_type, "__name__", str(args.exc_type)),
                error=str(args.exc_value),
                traceback="".join(
                    traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)
                ),
            )
            if previous_thread_excepthook:
                previous_thread_excepthook(args)

        threading.excepthook = _thread_excepthook


def setup_full_diagnostics(source: str = "app_start") -> Path:
    _get_logger()
    install_exception_hooks()
    log_event(
        "diagnostics_initialized",
        source=source,
        log_path=str(LOG_PATH),
        hostname=socket.gethostname(),
        platform=platform.platform(),
        python=sys.version,
    )
    return LOG_PATH

