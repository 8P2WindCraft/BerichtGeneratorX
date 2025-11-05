#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zentrale Logging-Infrastruktur

Ziele (1c, 2b):
- Konsole: menschenlesbar
- Dateien: JSON-Lines, getrennt nach Bereichen (app, ocr, detailed) mit Rotation 10MB×5
"""

import os
import sys
import json
import time
import logging
import threading
import traceback
from typing import Any, Dict, Optional
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone

from constants import MAX_LOG_FILE_SIZE, LOG_BACKUP_COUNT
from utils_helpers import resource_path

# Pfade
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_LOG = os.path.join(_BASE_DIR, 'app.log')
_OCR_LOG = os.path.join(_BASE_DIR, 'ocr_log.txt')
_DETAILED_LOG = os.path.join(_BASE_DIR, 'detailed_log.txt')


class JsonFormatter(logging.Formatter):
    """Emit je Logeintrag eine JSON-Zeile (UTF-8)."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
            "msg": record.getMessage(),
            "pid": os.getpid(),
            "thread": record.threadName,
        }
        # Zusätzliche Kontextfelder aus LoggerAdapter
        extra = getattr(record, 'extra_ctx', None)
        if isinstance(extra, dict):
            payload.update(extra)

        # Exceptions/Stack
        if record.exc_info:
            payload["stack"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


class ContextAdapter(logging.LoggerAdapter):
    """LoggerAdapter, der Kontextfelder unter 'extra_ctx' injiziert."""

    def process(self, msg, kwargs):
        extra = kwargs.pop('extra', {}) or {}
        # Mische Standard-Kontext mit pro-Call-Extra
        merged = dict(self.extra)
        if isinstance(extra, dict):
            merged.update(extra)
        kwargs['extra'] = {"extra_ctx": merged}
        return msg, kwargs


_INITIALIZED = False


def init_logging(config: Optional[dict] = None) -> None:
    """Richtet alle Logger/Handler ein. Idempotent.

    - app → Konsole (human) + app.log (JSON)
    - ocr → ocr_log.txt (JSON)
    - detailed → detailed_log.txt (JSON)
    """
    global _INITIALIZED
    if _INITIALIZED:
        return

    os.makedirs(os.path.dirname(_APP_LOG), exist_ok=True)

    logging.captureWarnings(True)
    logging.getLogger().setLevel(logging.DEBUG)

    # Formatter
    human = logging.Formatter('[%(asctime)s] %(levelname)s %(name)s %(module)s: %(message)s',
                               datefmt='%H:%M:%S')
    jf = JsonFormatter()

    # Console → nur app
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(human)

    # Datei-Handler JSON
    def _rot(file_path: str, level: int) -> RotatingFileHandler:
        h = RotatingFileHandler(file_path, maxBytes=MAX_LOG_FILE_SIZE,
                                backupCount=LOG_BACKUP_COUNT, encoding='utf-8')
        h.setLevel(level)
        h.setFormatter(jf)
        return h

    # Logger app
    app_logger = logging.getLogger('app')
    app_logger.setLevel(logging.DEBUG)
    app_logger.addHandler(ch)
    app_logger.addHandler(_rot(_APP_LOG, logging.DEBUG))
    app_logger.propagate = False

    # Logger ocr
    ocr_logger = logging.getLogger('ocr')
    ocr_logger.setLevel(logging.DEBUG)
    ocr_logger.addHandler(_rot(_OCR_LOG, logging.DEBUG))
    ocr_logger.propagate = False

    # Logger detailed
    det_logger = logging.getLogger('detailed')
    det_logger.setLevel(logging.DEBUG)
    det_logger.addHandler(_rot(_DETAILED_LOG, logging.DEBUG))
    det_logger.propagate = False

    _INITIALIZED = True


def get_logger(name: str = 'app', context: Optional[Dict[str, Any]] = None) -> ContextAdapter:
    """Gibt einen LoggerAdapter mit optionalem Kontext zurück."""
    base = logging.getLogger(name or 'app')
    return ContextAdapter(base, context or {})


# Exception-Hooks
def _log_unhandled(exc_type, exc, tb):
    lg = logging.getLogger('app')
    lg.error('Unhandled exception', exc_info=(exc_type, exc, tb), extra={"extra_ctx": {"event": "unhandled_exception"}})


def install_exception_hooks(tk_root=None) -> None:
    """Installiert sys/thread/Tk Hooks für zentrales Logging."""
    sys.excepthook = _log_unhandled

    def _thread_hook(args):
        _log_unhandled(args.exc_type, args.exc_value, args.exc_traceback)

    try:
        threading.excepthook = _thread_hook
    except Exception:
        pass

    if tk_root is not None:
        try:
            def _tk_hook(exc, val, tb):
                _log_unhandled(exc, val, tb)
            tk_root.report_callback_exception = _tk_hook
        except Exception:
            pass


# Kompatibilitätsfunktionen (bestehender Code nutzt diese bereits)
def write_detailed_log(level, message, details=None, exception=None):
    lg = get_logger('detailed')
    extra = {}
    if details:
        extra['details'] = details
    if exception:
        lg.log(getattr(logging, (level or 'INFO').upper(), logging.INFO), message, extra=extra, exc_info=exception)
    else:
        lg.log(getattr(logging, (level or 'INFO').upper(), logging.INFO), message, extra=extra)


def write_log_entry(filename, raw_text, final_result, confidence=None):
    lg = get_logger('ocr')
    extra = {"file_path": filename}
    if confidence is not None:
        extra['confidence'] = confidence
    lg.info(f"OCR result: {final_result}", extra=extra)


