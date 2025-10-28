# -*- coding: utf-8 -*-
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from utils_logging import init_logging, get_logger


def create_app() -> QApplication:
    init_logging()
    app = QApplication.instance() or QApplication([])
    try:
        app.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    except Exception:
        pass
    get_logger('app', {"module": "qtui.app"}).info("module_started", extra={"event": "module_started"})
    return app






