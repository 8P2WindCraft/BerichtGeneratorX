# -*- coding: utf-8 -*-
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QDialogButtonBox
from .settings_manager import get_settings_manager


class OcrEditDialog(QDialog):
    def __init__(self, parent=None, *, tag: str = ""):
        super().__init__(parent)
        self.setWindowTitle("OCR-Tag bearbeiten")

        v = QVBoxLayout(self)

        # Tag mit Dropdown
        row1 = QHBoxLayout(); v.addLayout(row1)
        row1.addWidget(QLabel("OCR-Tag:"))
        
        # Hole gültige Kürzel aus Settings
        settings_manager = get_settings_manager()
        valid_kurzel = settings_manager.get_valid_kurzel() or []
        
        self._combo = QComboBox()
        self._combo.setEditable(True)  # Erlaube auch manuelle Eingabe
        self._combo.addItems(valid_kurzel)
        if tag:
            # Setze aktuelles Tag, falls vorhanden
            index = self._combo.findText(tag.upper())
            if index >= 0:
                self._combo.setCurrentIndex(index)
            else:
                # Tag nicht in Liste, füge es hinzu
                self._combo.setCurrentText(tag.upper())
        row1.addWidget(self._combo)

        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)

    def _on_accept(self):
        # Erlaube auch leere Eingabe (um Tag zu entfernen)
        self.accept()

    def result_tag(self) -> str:
        return self._combo.currentText().strip().upper()






