# -*- coding: utf-8 -*-
from PySide6.QtCore import Qt, QRectF, QPropertyAnimation, QEasingCurve, Property, Signal
from PySide6.QtGui import QPainter, QColor, QBrush
from PySide6.QtWidgets import QWidget, QPushButton, QHBoxLayout


class ToggleSwitch(QWidget):
    toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(52, 30)
        self.setCursor(Qt.PointingHandCursor)
        self._checked = False
        self._pos = 0.0
        # Wichtig: nicht "pos" animieren (würde die Widget-Position ändern)
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def isChecked(self):
        return self._checked

    def setChecked(self, checked: bool):
        if self._checked != checked:
            self._checked = checked
            self._anim.stop()
            self._anim.setStartValue(self._pos)
            self._anim.setEndValue(1.0 if checked else 0.0)
            self._anim.start()
            self.toggled.emit(checked)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setChecked(not self._checked)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        track = QRectF(0, 0, 52, 30)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#4CAF50") if self._checked else QColor("#CCCCCC")))
        p.drawRoundedRect(track, 15, 15)
        d = 26
        x = 2 + (50 - d) * self._pos
        p.setBrush(QBrush(Qt.white))
        p.drawEllipse(QRectF(x, 2, d, d))

    def getOffset(self):
        return self._pos

    def setOffset(self, v):
        self._pos = float(v)
        self.update()

    # eigene Animations-Property, nicht mit QWidget.pos kollidieren
    offset = Property(float, getOffset, setOffset)


class ChipButton(QPushButton):
    def __init__(self, text: str):
        super().__init__(text)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        
        # Minimale Breite basierend auf Textlänge (30% kleiner)
        self.setMinimumWidth(84)
        
        self.setStyleSheet(
            """
            QPushButton { 
                border: 1px solid #aaaaaa; 
                border-radius: 16px; 
                padding: 6px 14px; 
                background: #f5f5f5;
                text-align: center;
                min-width: 84px;
                font-weight: normal;
            }
            QPushButton:hover { background: #eaeaea; }
            QPushButton:checked { background: #2196F3; color: white; border-color: #2196F3; }
            """
        )


class SegmentedControl(QWidget):
    def __init__(self, labels, checked=0):
        super().__init__()
        l = QHBoxLayout(self)
        l.setSpacing(0)
        l.setContentsMargins(0, 0, 0, 0)
        self.group = []
        for i, lab in enumerate(labels):
            b = QPushButton(lab)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            if i == checked:
                b.setChecked(True)
            b.setStyleSheet(
                """
                QPushButton { border: 1px solid #c9cdd2; background: #f8f9fb; padding: 6px 14px; }
                QPushButton:checked { background: #2196F3; color: white; }
                """
            )
            if i == 0:
                b.setStyleSheet(b.styleSheet() + "QPushButton{border-top-left-radius:6px;border-bottom-left-radius:6px;}")
            if i == len(labels) - 1:
                b.setStyleSheet(b.styleSheet() + "QPushButton{border-top-right-radius:6px;border-bottom-right-radius:6px;}")
            l.addWidget(b)
            self.group.append(b)

    def selected_text(self) -> str:
        for b in self.group:
            if b.isChecked():
                return b.text()
        return ""

    def set_selected(self, text: str) -> None:
        for b in self.group:
            b.setChecked(b.text() == text)


