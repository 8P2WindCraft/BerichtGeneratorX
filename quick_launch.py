from qtui.app import create_app
from qtui.main_window import MainWindow
from PySide6.QtCore import QTimer
app = create_app()
w = MainWindow()
w.show()
QTimer.singleShot(5000, app.quit)
app.exec()
