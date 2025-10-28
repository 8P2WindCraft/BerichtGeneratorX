# -*- coding: utf-8 -*-
from PySide6.QtWidgets import QSplashScreen, QVBoxLayout, QLabel, QProgressBar, QWidget
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont
import os


class LoadingScreen(QSplashScreen):
    """Professioneller Loading Screen für die Anwendung"""
    
    def __init__(self):
        # Erstelle ein leeres Pixmap als Hintergrund
        self._pixmap = QPixmap(500, 300)
        self._pixmap.fill(QColor(45, 45, 48))  # Dunkler Hintergrund
        
        # Zeichne den Inhalt BEVOR wir das Pixmap an QSplashScreen übergeben
        self._draw_content()
        
        super().__init__(self._pixmap, Qt.WindowStaysOnTopHint)
        
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        
        # Fortschritt
        self._progress = 0
        self._max_steps = 10
        
    def _draw_content(self):
        """Zeichnet den Inhalt des Loading Screens"""
        painter = QPainter(self._pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Titel
        font = QFont("Segoe UI", 24, QFont.Bold)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(0, 0, 500, 120, Qt.AlignCenter, "BerichtGeneratorX")
        
        # Untertitel
        font = QFont("Segoe UI", 12)
        painter.setFont(font)
        painter.setPen(QColor(200, 200, 200))
        painter.drawText(0, 120, 500, 40, Qt.AlignCenter, "Wird geladen...")
        
        # Version
        font = QFont("Segoe UI", 9)
        painter.setFont(font)
        painter.setPen(QColor(150, 150, 150))
        painter.drawText(0, 260, 500, 30, Qt.AlignCenter, "Version 2.0 (PySide6)")
        
        painter.end()
    
    def update_progress(self, step: int, message: str = ""):
        """Aktualisiert den Fortschritt"""
        self._progress = step
        percent = int((step / self._max_steps) * 100)
        
        # Aktualisiere die Nachricht
        if message:
            self.showMessage(
                f"{message}\n{percent}%",
                Qt.AlignBottom | Qt.AlignHCenter,
                QColor(255, 255, 255)
            )
        else:
            self.showMessage(
                f"Laden... {percent}%",
                Qt.AlignBottom | Qt.AlignHCenter,
                QColor(255, 255, 255)
            )
        
        # Verarbeite Events, damit der Screen aktualisiert wird
        from PySide6.QtWidgets import QApplication
        QApplication.processEvents()
    
    def set_max_steps(self, max_steps: int):
        """Setzt die maximale Anzahl der Schritte"""
        self._max_steps = max_steps

