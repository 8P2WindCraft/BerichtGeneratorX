# -*- coding: utf-8 -*-
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QDoubleSpinBox, QDialogButtonBox
from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator


class OcrEditDialog(QDialog):
    def __init__(self, parent=None, *, tag: str = "", confidence: float | None = None):
        super().__init__(parent)
        self.setWindowTitle("OCR-Tag bearbeiten")

        v = QVBoxLayout(self)

        # Tag
        row1 = QHBoxLayout(); v.addLayout(row1)
        row1.addWidget(QLabel("OCR-Tag:"))
        self._line = QLineEdit(tag or "")
        rx = QRegularExpression("^[A-Z0-9-]+$")
        self._line.setValidator(QRegularExpressionValidator(rx))
        self._line.textEdited.connect(lambda s: self._line.setText(s.upper()))
        row1.addWidget(self._line)

        # Confidence
        row2 = QHBoxLayout(); v.addLayout(row2)
        row2.addWidget(QLabel("Confidence:"))
        self._conf = QDoubleSpinBox()
        self._conf.setRange(0.0, 1.0)
        self._conf.setDecimals(2)
        self._conf.setSingleStep(0.01)
        self._conf.setValue(confidence if isinstance(confidence, (int, float)) else 1.0)
        row2.addWidget(self._conf)

        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)

    def _on_accept(self):
        if not self._line.text():
            # Leere Eingabe nicht zulassen
            return
        self.accept()

    def result_tag(self) -> str:
        return self._line.text().strip().upper()

    def result_confidence(self) -> float:
        return float(self._conf.value())






