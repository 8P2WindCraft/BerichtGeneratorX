# -*- coding: utf-8 -*-
from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class FilterController(QObject):
    """Global synchronisierter Filterzustand für Galerie- und Einzelbildansicht."""

    filterChanged = Signal(str)

    def __init__(self, initial: str = "karte"):
        super().__init__()
        self._mode = initial

    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str):
        mode = str(mode)
        if mode == self._mode:
            return
        self._mode = mode
        self.filterChanged.emit(mode)



