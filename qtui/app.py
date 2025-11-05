# -*- coding: utf-8 -*-
import sys
import locale
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from utils_logging import init_logging, get_logger


def create_app() -> QApplication:
    # UTF-8 Encoding sicherstellen
    if sys.platform == 'win32':
        try:
            # Konsolen-Encoding auf UTF-8 setzen
            if sys.stdout:
                sys.stdout.reconfigure(encoding='utf-8')
            if sys.stderr:
                sys.stderr.reconfigure(encoding='utf-8')
        except Exception:
            pass
    
    init_logging()
    app = QApplication.instance() or QApplication([])
    try:
        app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    except Exception:
        pass
    get_logger('app', {"module": "qtui.app"}).info("module_started", extra={"event": "module_started"})
    return app






