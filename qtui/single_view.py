# -*- coding: utf-8 -*-
from __future__ import annotations
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsView, 
                                QGraphicsScene, QPushButton, QFileDialog, QMenu, QToolBar,
                                QComboBox, QSpinBox, QGroupBox, QButtonGroup, QRadioButton,
                                QDialog, QDialogButtonBox, QPlainTextEdit, QMessageBox, QScrollArea,
                                QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView)
from PySide6.QtGui import QPixmap, QPainter, QKeySequence, QShortcut, QPen, QColor, QAction
from PySide6.QtCore import Qt, Signal, QObject, QThread, QPointF, QTimer, QSize
from utils_logging import get_logger
from utils_exif import (
    set_used_flag,
    set_evaluation,
    read_metadata,
    write_metadata,
    get_used_flag,
    set_ocr_info,
    get_ocr_info,
    get_gene_flag,
    set_gene_flag,
    get_evaluation,
)
# OCR-Erkennung entfernt: keine Abhängigkeit zu core_ocr/DetectParams
from config_manager import config_manager
from .settings_manager import get_settings_manager
from .drawing_tools import DrawingManager, DrawingMode
from .evaluation_panel import EvaluationPanel
from .widgets import ToggleSwitch
import os
import shutil
import tempfile


class DynamicPlainTextEdit(QPlainTextEdit):
    """Dynamisches Textfeld das initial 1 Zeile hoch ist und sich bei Fokus/Text vergrößert"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._expanded = False
        self._min_height = 45  # Größer: 1,5 Zeilen damit Text sichtbar ist
        self._normal_height = 120  # Erweiterte Höhe auch etwas größer
        self.setMinimumHeight(self._min_height)
        self.setMaximumHeight(self._min_height)
        from PySide6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        # Bei Textänderung prüfen
        self.textChanged.connect(self._check_expansion)
    
    def focusInEvent(self, event):
        """Beim Reinklicken vergrößern"""
        super().focusInEvent(event)
        if not self._expanded:
            self._expand()
    
    def focusOutEvent(self, event):
        """Beim Verlassen immer verkleinern"""
        super().focusOutEvent(event)
        # Immer verkleinern beim Verlassen, egal ob Text vorhanden
        if self._expanded:
            self._collapse()
    
    def _check_expansion(self):
        """Prüft ob Text vorhanden ist und expandiert entsprechend"""
        # Nur bei Fokus expandieren, nicht automatisch bei Text
        # Diese Methode wird bei textChanged aufgerufen, aber wir expandieren nur im focusInEvent
        if self._expanded and self.hasFocus():
            # Text vorhanden und bereits expandiert - dynamisch anpassen
            self._adjust_height()
    
    def _expand(self):
        """Vergrößert das Textfeld"""
        self._expanded = True
        self.setMinimumHeight(self._normal_height)
        self.setMaximumHeight(16777215)  # Qt Maximum
        from PySide6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._adjust_height()
    
    def _collapse(self):
        """Verkleinert das Textfeld auf 1 Zeile"""
        self._expanded = False
        self.setMinimumHeight(self._min_height)
        self.setMaximumHeight(self._min_height)
        from PySide6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    
    def _adjust_height(self):
        """Passt die Höhe dynamisch an den Inhalt an"""
        if not self._expanded:
            return
        
        # Kurz warten damit Layout aktualisiert ist
        from PySide6.QtCore import QTimer
        QTimer.singleShot(10, self._do_adjust_height)
    
    def _do_adjust_height(self):
        """Führt die tatsächliche Höhenanpassung durch"""
        if not self._expanded:
            return
        
        # Berechne benötigte Höhe basierend auf Text
        doc = self.document()
        doc.setTextWidth(self.viewport().width())
        height = int(doc.size().height()) + 15  # +15 für Padding/Margins
        
        # Mindesthöhe sicherstellen
        height = max(self._normal_height, height)
        
        # Setze neue Höhe
        self.setMinimumHeight(height)


class SingleView(QWidget):
    progressChanged = Signal(int, int, int)  # current_index(1-based), total, evaluated_count
    folderChanged = Signal(str)
    ocrTagUpdated = Signal(str)  # path
    currentImageChanged = Signal(str)
    def __init__(self):
        super().__init__()
        self._log = get_logger('app', {"module": "qtui.single_view"})
        self._log.info("module_started", extra={"event": "module_started"})
        
        # Settings Manager
        self.settings_manager = get_settings_manager()

        v = QVBoxLayout(self)
        self.setFocusPolicy(Qt.StrongFocus)
        self._image_paths = []
        self._current_index = -1
        self._evaluated = set()
        self._current_folder = ""
        
        # Image Precaching für schnelleren Wechsel
        self._image_cache = {}  # {path: QPixmap}
        self._cache_range = 8  # 8 Bilder vorher + 8 nachher = 16 Bilder gecacht
        self._max_cache_size = 25  # Maximale Cache-Größe
        self._original_backup_paths = set()
        self._pending_drawing_task = None
        self._drawing_flush_scheduled = False
        self._drawing_save_in_progress = False
        
        # Cache für Zeichnungsdaten pro Pfad (bleibt auch bei EXIF-Lesefehlern erhalten)
        self._drawings_cache = {}  # {path: list[dict]}
        
        # Cache-Layer für Bewertungen (wird von MainWindow gesetzt)
        self._cache_layer = None

        # Header: Ordner + Info + Aktionen
        head = QHBoxLayout(); v.addLayout(head)
        self.btn_open = QPushButton("Ordner öffnen…")
        self.btn_open.clicked.connect(self._open_folder)
        self.btn_open.setToolTip("Kein Ordner ausgewählt")
        head.addWidget(self.btn_open)
        self.progress_label = QLabel("Bild 0/0 – Bearbeitet 0/0")
        head.addWidget(self.progress_label)
        
        # Sortierungs-Toggle Button
        self.sort_toggle_btn = QPushButton("ABC")
        self.sort_toggle_btn.setCheckable(True)
        self.sort_toggle_btn.setChecked(True)  # Standard: Alphabetisch
        self.sort_toggle_btn.setFixedWidth(50)
        self.sort_toggle_btn.setToolTip("Grün (ABC): Alphabetisch nach Bildname\nGrau: TreeView-Reihenfolge")
        self.sort_toggle_btn.toggled.connect(self._on_sort_toggle_changed)
        self._update_sort_button_style(True)  # Initial grün
        head.addWidget(self.sort_toggle_btn)
        
        head.addStretch(1)
        use_label = QLabel("Bild verwenden")
        use_label.setStyleSheet("font-weight: bold;")
        head.addWidget(use_label)
        self.use_header_toggle = ToggleSwitch()
        self.use_header_toggle.setChecked(False)
        self.use_header_toggle.toggled.connect(self._set_use_from_header)
        head.addWidget(self.use_header_toggle)
        gene_label = QLabel("Gene")
        gene_label.setStyleSheet("font-weight: bold;")
        head.addWidget(gene_label)
        self.gene_header_toggle = ToggleSwitch(active_color="#FF9800")  # Orange für Gene
        self.gene_header_toggle.setChecked(False)
        self.gene_header_toggle.toggled.connect(self._set_gene_from_header)
        head.addWidget(self.gene_header_toggle)
        
        # OCR-Label als Dummy-Variable (wird nicht angezeigt)
        self.ocr_label = QLabel("—")
        self.ocr_label.hide()  # Verstecken

        # Bildbereich mit Toolbar links
        image_container = QHBoxLayout()
        v.addLayout(image_container, 1)
        
        # Linke Seite: Vertikal kombinierte Toolbars (in ScrollArea, damit dynamisch)
        left_toolbar_container = QWidget()
        left_toolbar_layout = QVBoxLayout(left_toolbar_container)
        left_toolbar_layout.setContentsMargins(0, 0, 0, 0)
        left_toolbar_layout.setSpacing(0)
        
        # Zeichenwerkzeug-Toolbar (vertikal)
        drawing_toolbar = self._create_drawing_toolbar_vertical()
        left_toolbar_layout.addWidget(drawing_toolbar)
        
        # Zoom-Toolbar (vertikal)
        zoom_toolbar = self._create_zoom_toolbar_vertical()
        left_toolbar_layout.addWidget(zoom_toolbar)
        
        # KEIN addStretch - Toolbar soll bis ganz unten reichen, damit Navigation nicht separiert aussieht
        # ScrollArea für dynamische Höhe/kleine Fenster
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QScrollArea.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setWidget(left_toolbar_container)
        image_container.addWidget(left_scroll)

        # Mitte: Bildbereich
        self.view = ImageView(); self.view.setScene(QGraphicsScene())
        self.view.set_context_edit_handler(self._edit_ocr_tag)
        # Drawing Manager an View übergeben
        drawing_manager = DrawingManager(self.view.scene())
        self.view.setup_drawing(drawing_manager)
        # Verbinde drawingChanged Signal mit Timer
        drawing_manager.drawingChanged.connect(self._schedule_drawing_save)
        # Zoom-Label an View übergeben
        self.view.zoom_label = self.zoom_label
        image_container.addWidget(self.view, 1)
        
        # Platzhalter für externes Bewertungs-Panel
        self._evaluation_panel: EvaluationPanel | None = None
        
        # Navigation als Overlay auf dem Canvas oder unter dem Bild
        self.nav_container = self._create_canvas_navigation()
        # WICHTIG: Setze Parent sofort, damit es nicht als separates Fenster erscheint
        self.nav_container.setParent(self.view)
        self.nav_below_wrapper = None  # Wrapper für zentrierte Navigation unter dem Bild
        
        # Initialisiere Navigation-Position basierend auf Settings
        self._update_navigation_position()
        
        # Verbinde Settings-Änderungen
        self.settings_manager.settingsChanged.connect(self._on_settings_changed)

        # Tastatur-Shortcuts (Pfeiltasten)
        QShortcut(QKeySequence(Qt.Key_Left), self, activated=self.prev_image)
        QShortcut(QKeySequence(Qt.Key_Right), self, activated=self.next_image)
        QShortcut(QKeySequence(Qt.Key_Home), self, activated=self.first_image)
        QShortcut(QKeySequence(Qt.Key_End), self, activated=self.last_image)
        QShortcut(QKeySequence(Qt.Key_Space), self, activated=self._mark_as_ok_and_next)
        QShortcut(QKeySequence(Qt.Key_X), self, activated=self._mark_as_reject_and_next)

        # Beschreibung unter dem Bild (damage_description / evaluation.notes)
        desc_group = QGroupBox("Beschreibung")
        desc_layout = QVBoxLayout(desc_group)
        
        # Horizontal: Textfeld links, Button rechts
        desc_row = QHBoxLayout()
        
        # Dynamisches Textfeld (startet mit 1 Zeile)
        self.notes_edit = DynamicPlainTextEdit()
        self.notes_edit.setPlaceholderText("Schadensbeschreibung / Bemerkung")
        desc_row.addWidget(self.notes_edit, 1)  # Stretch factor 1 = nimmt verfügbaren Platz
        
        # Textbausteine-Button rechts daneben
        self.btn_text_snippets = QPushButton("📝")
        self.btn_text_snippets.setToolTip("Textbausteine einfügen")
        self.btn_text_snippets.setFixedWidth(40)
        self.btn_text_snippets.clicked.connect(self._show_text_snippets)
        desc_row.addWidget(self.btn_text_snippets, 0)  # Stretch factor 0 = feste Größe
        
        desc_layout.addLayout(desc_row)
        self.desc_group = desc_group  # Speichere Referenz für Navigation-Positionierung
        v.addWidget(desc_group)

        # Debounced Auto-Save fr die Textbox
        self._notes_timer = QTimer(self)
        self._notes_timer.setSingleShot(True)
        self._notes_timer.timeout.connect(self._save_notes_async)
        self._notes_loading = False
        self.notes_edit.textChanged.connect(self._schedule_notes_save)
        
        # Debounced Auto-Save für Zeichnungen (2 Sekunden nach letzter Änderung)
        self._drawing_timer = QTimer(self)
        self._drawing_timer.setSingleShot(True)
        self._drawing_timer.timeout.connect(self._save_drawings_async)

    def set_evaluation_panel(self, panel: EvaluationPanel | None):
        if self._evaluation_panel is panel:
            return
        if self._evaluation_panel:
            try:
                self._evaluation_panel.evaluationChanged.disconnect(self._on_panel_evaluation)
            except Exception:
                pass
            try:
                self._evaluation_panel.useChanged.disconnect(self._on_panel_use_changed)
            except Exception:
                pass
        self._evaluation_panel = panel
        if panel:
            panel.evaluationChanged.connect(self._on_panel_evaluation)
            try:
                panel.useChanged.connect(self._on_panel_use_changed)
            except Exception:
                pass
            if self._current_path():
                panel.set_path(self._current_path())
            else:
                panel.set_path(None)
            self._refresh_gene_button()
            self._refresh_use_toggle()
        else:
            self.currentImageChanged.emit('')
            self._refresh_gene_button(False)
            self._refresh_use_toggle(False)


    def _on_panel_use_changed(self, path: str, value: bool):
        current = self._current_path()
        if not current or current != path:
            return
        # Aktualisiere Toggle sofort
        self._refresh_use_toggle(value)
        # Aktualisiere auch Gene-Button falls sich etwas geändert hat
        self._refresh_gene_button()
    def _on_panel_evaluation(self, path: str, state: dict):
        current = self._current_path()
        if not current or path != current:
            return
        evaluated = bool(state.get('categories') or state.get('quality') or state.get('image_type'))
        if self._current_index >= 0:
            if evaluated:
                self._evaluated.add(self._current_index)
            else:
                self._evaluated.discard(self._current_index)
        self._update_labels()
        self._refresh_gene_button()
        # Position wird im resizeEvent des ImageView aktualisiert

    def _tag_with_heading(self, tag: str) -> str:
        """Erweitert ein Kürzel optional um eine Überschrift aus der Kürzel-Tabelle.
        Gibt z.B. "Name DE\nCODE" zurück, wenn vorhanden, sonst nur den CODE.
        """
        try:
            code = (tag or "").strip()
            if not code:
                return ""
            show_heading = bool(self.settings_manager.get('tag_overlay_heading', True))
            if show_heading:
                table = self.settings_manager.get('kurzel_table', {}) or {}
                data = table.get(code)
                if isinstance(data, dict):
                    heading = data.get('name_de') or data.get('name_en')
                    if heading:
                        clean = ''.join(ch if ord(ch) >= 32 else ' ' for ch in str(heading))
                        if clean.strip() and clean.strip().upper() != code.upper():
                            order = str(self.settings_manager.get('tag_heading_order', 'below') or 'below').lower()
                            if order == 'below':
                                return f"{code}\n{clean.strip()}"
                            else:
                                return f"{clean.strip()}\n{code}"
        except Exception:
            pass
        return tag or ""

    def _update_ocr_header_display(self, tag: str):
        if not hasattr(self, 'ocr_info_label'):
            return
        tag_clean = (tag or "").strip().upper()
        if not tag_clean or tag_clean in {"—", "NONE"}:
            self.ocr_info_label.setText("OCR: —")
            return
        evaluated = total = 0
        window = self.window()
        if window and hasattr(window, 'evaluation_cache') and window.evaluation_cache:
            try:
                evaluated, total = window.evaluation_cache.get_kurzel_progress(tag_clean)
            except Exception:
                evaluated = total = 0
        self.ocr_info_label.setText(f"OCR: {tag_clean} – bewertet {evaluated}/{total}")

    def _mark_as_ok_and_next(self):
        """Setzt 'Visuell keine Defekte' und verwendet das Bild."""
        current_path = self._current_path()
        if not current_path:
            return

        try:
            if self._evaluation_panel:
                self._evaluation_panel.apply_visual_ok()
                self._evaluation_panel.set_use(True)
            self._refresh_use_toggle(True)
            
            # Sofort zum nächsten Bild springen (Speichern passiert automatisch bei load_image)
            self.next_image()

            self._log.info("marked_as_ok_and_next", extra={"path": current_path})

        except Exception as e:
            self._log.error("mark_as_ok_failed", extra={"error": str(e), "path": current_path})

    def _mark_as_reject_and_next(self):
        """Markiert das Bild als 'nicht verwenden' und springt weiter."""
        current_path = self._current_path()
        if not current_path:
            return

        try:
            if self._evaluation_panel:
                self._evaluation_panel.set_use(False)
            self._refresh_use_toggle(False)
            
            # Sofort zum nächsten Bild springen (Speichern passiert automatisch bei load_image)
            self.next_image()

            self._log.info("marked_as_reject_and_next", extra={"path": current_path})

        except Exception as e:
            self._log.error("mark_as_reject_failed", extra={"error": str(e), "path": current_path})

    def _create_canvas_navigation(self):
        """Erstellt Navigation direkt auf dem Canvas unter dem Bild"""
        # Navigation-Container als Overlay auf dem Canvas
        nav_container = QWidget()
        nav_container.setWindowFlags(Qt.WindowType.Widget)  # WICHTIG: Als Widget, nicht als Window
        nav_container.setFixedHeight(60)
        nav_container.setStyleSheet("""
            QWidget {
                background-color: rgba(40, 40, 40, 200);
                border-radius: 10px;
                padding: 5px;
            }
        """)
        nav_layout = QHBoxLayout(nav_container)
        nav_layout.setContentsMargins(10, 5, 10, 5)
        nav_layout.setSpacing(10)
        
        # Navigation Buttons - kompakter Style für Overlay
        self.btn_prev = QPushButton("◀")
        self.btn_prev.setFixedSize(50, 40)
        self.btn_prev.setStyleSheet("""
            QPushButton {
                background-color: #555;
                color: white;
                border: 1px solid #777;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #666;
            }
            QPushButton:pressed {
                background-color: #444;
            }
        """)
        
        self.btn_next = QPushButton("▶")
        self.btn_next.setFixedSize(50, 40)
        self.btn_next.setStyleSheet("""
            QPushButton {
                background-color: #555;
                color: white;
                border: 1px solid #777;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #666;
            }
            QPushButton:pressed {
                background-color: #444;
            }
        """)
        
        # Grüner Häkchen-Button für "Visuell OK"
        self.btn_ok = QPushButton("✓ Visuell OK")
        self.btn_ok.setFixedSize(120, 40)
        self.btn_ok.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: 2px solid #388E3C;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #45A049;
                border-color: #2E7D32;
            }
            QPushButton:pressed {
                background-color: #3E8E41;
            }
        """)
        
        # Roter Button für "Bild nicht verwenden"
        self.btn_reject = QPushButton("✖ Nicht verwenden")
        self.btn_reject.setFixedSize(150, 40)
        self.btn_reject.setStyleSheet("""
            QPushButton {
                background-color: #F44336;
                color: white;
                border: 2px solid #D32F2F;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #E53935;
                border-color: #C62828;
            }
            QPushButton:pressed {
                background-color: #D32F2F;
            }
        """)
        
        # Verbindungen
        self.btn_prev.clicked.connect(self.prev_image)
        self.btn_next.clicked.connect(self.next_image)
        self.btn_ok.clicked.connect(self._mark_as_ok_and_next)
        self.btn_reject.clicked.connect(self._mark_as_reject_and_next)

        # Fragezeichen-Button für Gene-Zweitmeinung
        self.btn_gene = QPushButton("?")
        self.btn_gene.setCheckable(True)
        self.btn_gene.setFixedSize(40, 40)
        self.btn_gene.setStyleSheet("""
            QPushButton {
                background-color: #3F51B5;
                color: white;
                border: 2px solid #283593;
                border-radius: 20px;
                font-weight: bold;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #5C6BC0;
            }
            QPushButton:checked {
                background-color: #FF9800;
                border-color: #EF6C00;
                color: black;
            }
        """)
        self.btn_gene.clicked.connect(lambda: self._toggle_gene_flag())
        
        # Layout: Kompakt nebeneinander - erst Navigation, dann Bewertung
        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.btn_next)
        nav_layout.addWidget(self.btn_ok)
        nav_layout.addWidget(self.btn_reject)
        nav_layout.addWidget(self.btn_gene)
        
        self._refresh_gene_button()
        self._update_action_tooltips()
        # Gebe den Container zurück, damit er im Hauptlayout eingefügt werden kann
        return nav_container

    def _create_drawing_toolbar_vertical(self):
        """Erstellt die vertikale Toolbar für Zeichenwerkzeuge"""
        group = QGroupBox("Zeichnen")
        layout = QVBoxLayout(group)
        layout.setSpacing(2)
        
        # Button Group für exklusive Auswahl
        mode_group = QButtonGroup(group)
        
        # Pan-Modus (Standard)
        pan_btn = QRadioButton("✋")
        pan_btn.setChecked(True)
        pan_btn.setToolTip("Pan")
        pan_btn.toggled.connect(lambda checked: self.view.set_drawing_mode(DrawingMode.PAN) if checked and hasattr(self.view, 'drawing_manager') else None)
        pan_btn.setFixedHeight(12)
        pan_btn.setMaximumHeight(12)
        pan_btn.setStyleSheet("QRadioButton { font-size: 10pt; }")
        mode_group.addButton(pan_btn)
        layout.addWidget(pan_btn)
        
        # Pfeil
        arrow_btn = QRadioButton("➤")
        arrow_btn.setToolTip("Pfeil")
        arrow_btn.toggled.connect(lambda checked: self.view.set_drawing_mode(DrawingMode.ARROW) if checked and hasattr(self.view, 'drawing_manager') else None)
        arrow_btn.setFixedHeight(20)
        arrow_btn.setMaximumHeight(20)
        arrow_btn.setStyleSheet("QRadioButton { font-size: 12pt; }")
        mode_group.addButton(arrow_btn)
        layout.addWidget(arrow_btn)
        
        # Kreis
        circle_btn = QRadioButton("◯")
        circle_btn.setToolTip("Kreis")
        circle_btn.toggled.connect(lambda checked: self.view.set_drawing_mode(DrawingMode.CIRCLE) if checked and hasattr(self.view, 'drawing_manager') else None)
        circle_btn.setFixedHeight(20)
        circle_btn.setMaximumHeight(20)
        circle_btn.setStyleSheet("QRadioButton { font-size: 12pt; }")
        mode_group.addButton(circle_btn)
        layout.addWidget(circle_btn)
        
        # Rechteck
        rect_btn = QRadioButton("▭")
        rect_btn.setToolTip("Rechteck")
        rect_btn.toggled.connect(lambda checked: self.view.set_drawing_mode(DrawingMode.RECTANGLE) if checked and hasattr(self.view, 'drawing_manager') else None)
        rect_btn.setFixedHeight(20)
        rect_btn.setMaximumHeight(20)
        rect_btn.setStyleSheet("QRadioButton { font-size: 12pt; }")
        mode_group.addButton(rect_btn)
        layout.addWidget(rect_btn)
        
        # Freihand
        freehand_btn = QRadioButton("✎")
        freehand_btn.setToolTip("Freihand")
        freehand_btn.toggled.connect(lambda checked: self.view.set_drawing_mode(DrawingMode.FREEHAND) if checked and hasattr(self.view, 'drawing_manager') else None)
        freehand_btn.setFixedHeight(20)
        freehand_btn.setMaximumHeight(20)
        freehand_btn.setStyleSheet("QRadioButton { font-size: 12pt; }")
        mode_group.addButton(freehand_btn)
        layout.addWidget(freehand_btn)
        
        layout.addSpacing(5)
        
        # Farbe (größer und besser sichtbar)
        color_label = QLabel("Farbe:")
        color_label.setFixedHeight(18)
        color_label.setMaximumHeight(18)
        color_label.setStyleSheet("QLabel { font-size: 10pt; }")
        layout.addWidget(color_label)
        color_combo = QComboBox()
        color_combo.setMaximumWidth(110)
        color_combo.setFixedHeight(22)
        color_combo.setMaximumHeight(22)
        color_combo.setStyleSheet("QComboBox { font-size: 10pt; padding: 2px; } QComboBox::drop-down { height: 20px; width: 20px; }")
        colors = ["red", "blue", "green", "yellow", "orange", "purple", "black", "white"]
        color_combo.addItems(colors)
        color_combo.currentTextChanged.connect(lambda c: self.view.set_drawing_color(QColor(c)) if hasattr(self.view, 'drawing_manager') else None)
        layout.addWidget(color_combo)
        
        # Linienbreite (größer und besser sichtbar)
        width_label = QLabel("Breite:")
        width_label.setFixedHeight(18)
        width_label.setMaximumHeight(18)
        width_label.setStyleSheet("QLabel { font-size: 10pt; }")
        layout.addWidget(width_label)
        width_spin = QSpinBox()
        width_spin.setMaximumWidth(70)
        width_spin.setFixedHeight(22)
        width_spin.setMaximumHeight(22)
        width_spin.setStyleSheet("QSpinBox { font-size: 10pt; padding: 2px; } QSpinBox::up-button, QSpinBox::down-button { height: 10px; }")
        width_spin.setRange(1, 20)
        width_spin.setValue(3)
        width_spin.valueChanged.connect(lambda w: self.view.set_drawing_width(w) if hasattr(self.view, 'drawing_manager') else None)
        layout.addWidget(width_spin)
        
        layout.addSpacing(5)
        
        # Undo/Redo Buttons (kompakter)
        undo_btn = QPushButton("↶")
        undo_btn.setToolTip("Undo")
        undo_btn.setMaximumWidth(110)
        undo_btn.setFixedHeight(12)
        undo_btn.setMaximumHeight(12)
        undo_btn.setStyleSheet("QPushButton { font-size: 8pt; padding: 0px; }")
        undo_btn.clicked.connect(lambda: self.view.undo_drawing() if hasattr(self.view, 'drawing_manager') else None)
        layout.addWidget(undo_btn)
        
        redo_btn = QPushButton("↷")
        redo_btn.setToolTip("Redo")
        redo_btn.setMaximumWidth(110)
        redo_btn.setFixedHeight(12)
        redo_btn.setMaximumHeight(12)
        redo_btn.setStyleSheet("QPushButton { font-size: 8pt; padding: 0px; }")
        redo_btn.clicked.connect(lambda: self.view.redo_drawing() if hasattr(self.view, 'drawing_manager') else None)
        layout.addWidget(redo_btn)
        
        clear_btn = QPushButton("🗑")
        clear_btn.setToolTip("Löschen")
        clear_btn.setMaximumWidth(110)
        clear_btn.setFixedHeight(12)
        clear_btn.setMaximumHeight(12)
        clear_btn.setStyleSheet("QPushButton { font-size: 8pt; padding: 0px; }")
        clear_btn.clicked.connect(lambda: self.view.clear_all_drawings() if hasattr(self.view, 'drawing_manager') else None)
        layout.addWidget(clear_btn)
        
        return group
    
    def _create_zoom_toolbar_vertical(self):
        """Erstellt die vertikale Toolbar für Zoom-Kontrollen"""
        group = QGroupBox("Zoom")
        layout = QVBoxLayout(group)
        layout.setSpacing(2)
        
        # Zoom-Anzeige
        self.zoom_label = QLabel("100%")
        self.zoom_label.setAlignment(Qt.AlignCenter)
        self.zoom_label.setStyleSheet("font-weight: bold; font-size: 8pt;")
        self.zoom_label.setFixedHeight(12)
        self.zoom_label.setMaximumHeight(12)
        layout.addWidget(self.zoom_label)
        
        layout.addSpacing(3)
        
        # Zoom In
        zoom_in_btn = QPushButton("🔍+")
        zoom_in_btn.setToolTip("Vergrößern")
        zoom_in_btn.setMaximumWidth(130)
        zoom_in_btn.setFixedHeight(12)
        zoom_in_btn.setMaximumHeight(12)
        zoom_in_btn.setStyleSheet("QPushButton { font-size: 8pt; padding: 0px; }")
        zoom_in_btn.clicked.connect(lambda: self.view.zoom_in() if self.view else None)
        layout.addWidget(zoom_in_btn)
        
        # Zoom Out
        zoom_out_btn = QPushButton("🔍-")
        zoom_out_btn.setToolTip("Verkleinern")
        zoom_out_btn.setMaximumWidth(130)
        zoom_out_btn.setFixedHeight(12)
        zoom_out_btn.setMaximumHeight(12)
        zoom_out_btn.setStyleSheet("QPushButton { font-size: 8pt; padding: 0px; }")
        zoom_out_btn.clicked.connect(lambda: self.view.zoom_out() if self.view else None)
        layout.addWidget(zoom_out_btn)
        
        # Fit to View
        fit_btn = QPushButton("⤢")
        fit_btn.setToolTip("Anpassen")
        fit_btn.setMaximumWidth(130)
        fit_btn.setFixedHeight(12)
        fit_btn.setMaximumHeight(12)
        fit_btn.setStyleSheet("QPushButton { font-size: 8pt; padding: 0px; }")
        fit_btn.clicked.connect(lambda: self.view.fit_to_view() if self.view else None)
        layout.addWidget(fit_btn)
        
        # Reset Zoom (1:1)
        reset_btn = QPushButton("1:1")
        reset_btn.setToolTip("Reset")
        reset_btn.setMaximumWidth(130)
        reset_btn.setFixedHeight(12)
        reset_btn.setMaximumHeight(12)
        reset_btn.setStyleSheet("QPushButton { font-size: 8pt; padding: 0px; }")
        reset_btn.clicked.connect(lambda: self.view.reset_zoom() if self.view else None)
        layout.addWidget(reset_btn)
        
        return group

    # API
    def load_image(self, path: str):
        self._log.info("image_load", extra={"event": "image_load", "path": path})
        
        # Prüfe ob Datei existiert und nicht leer ist
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            self._log.warning("image_load_skipped_invalid", extra={"event": "image_load_skipped_invalid", "path": path})
            # Verwende leeres Pixmap für defekte Dateien
            pix = QPixmap()
        # Prüfe Cache zuerst (schnellster Weg)
        elif path in self._image_cache:
            pix = self._image_cache[path]
        else:
            # WICHTIG: Einzelbild-Ansicht lädt immer Original-Qualität ohne Kompression!
            pix = QPixmap(path)
            # In Cache speichern (nur wenn gültig)
            if not pix.isNull():
                self._image_cache[path] = pix
        
        # Bild sofort anzeigen (höchste Priorität)
        scene = self.view.scene()
        if scene:
            scene.clear()
            if not pix.isNull():
                self.view.set_pixmap(pix)
        
        # UI sofort aktualisieren (für instant Feedback)
        self.currentImageChanged.emit(path)
        self._update_labels()
        self._update_nav()
        self._update_action_tooltips()
        
        # ALLES andere asynchron laden (nicht blockierend)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: self._load_image_details(path))
        
        # Precaching im Hintergrund starten (niedrigere Priorität)
        QTimer.singleShot(100, self._precache_adjacent_images)
    
    def _load_image_details(self, path: str):
        """Lädt Metadaten und Details asynchron im Hintergrund"""
        # Evaluation Panel laden (macht EXIF-Read)
        if self._evaluation_panel:
            try:
                self._evaluation_panel.set_path(path)
            except Exception:
                pass
        
        # Toggles nach Panel-Load aktualisieren
        self._refresh_gene_button()
        self._refresh_use_toggle()
        
        try:
            md = read_metadata(path) or {}
        except Exception:
            md = {}
        
        # Schadensbeschreibung laden
        try:
            eval_obj = get_evaluation(path) or {}
            notes = eval_obj.get('notes') or md.get('damage_description') or ''
        except Exception:
            notes = ''
        
        self._notes_loading = True
        try:
            self.notes_edit.blockSignals(True)
            self.notes_edit.setPlainText(str(notes) if isinstance(notes, str) else '')
        finally:
            self.notes_edit.blockSignals(False)
            self._notes_loading = False
        
        # OCR-Info laden
        try:
            o = get_ocr_info(path)
        except Exception:
            o = {}
        
        try:
            raw_tag = str(o.get('tag', '')).strip() if isinstance(o, dict) else ''
            if raw_tag:
                display_tag = raw_tag.upper()
                self.ocr_label.setText(display_tag)
                self.view.set_ocr_label(self._tag_with_heading(display_tag))
            else:
                display_tag = "—"
                self.ocr_label.setText(display_tag)
                self.view.set_ocr_label("")
            self._update_ocr_header_display(display_tag)
        except Exception:
            self.ocr_label.setText('—')
            self.view.set_ocr_label("")
            self._update_ocr_header_display("")
        
        # Zeichnungen laden
        try:
            # Versuche zuerst aus Metadaten zu laden
            drawings_data = md.get('drawings', [])
            
            # Falls keine Zeichnungen in Metadaten, versuche Cache
            if not drawings_data and path in self._drawings_cache:
                drawings_data = self._drawings_cache[path]
                self._log.info('drawings_loaded_from_cache', extra={'count': len(drawings_data), 'path': path})
            
            # Lade Zeichnungen in Drawing Manager
            if drawings_data and hasattr(self.view, 'drawing_manager') and self.view.drawing_manager:
                self.view.drawing_manager.load_drawings_data(drawings_data)
                # Aktualisiere Cache mit geladenen Daten
                self._drawings_cache[path] = drawings_data.copy() if isinstance(drawings_data, list) else []
                self._log.info('drawings_loaded', extra={'count': len(drawings_data), 'path': path})
            elif hasattr(self.view, 'drawing_manager') and self.view.drawing_manager:
                # Keine Zeichnungen vorhanden: leere Liste im Cache speichern
                self._drawings_cache[path] = []
        except Exception as e:
            # Bei Fehler: versuche Cache
            try:
                if path in self._drawings_cache and hasattr(self.view, 'drawing_manager') and self.view.drawing_manager:
                    cached_drawings = self._drawings_cache[path]
                    if cached_drawings:
                        self.view.drawing_manager.load_drawings_data(cached_drawings)
                        self._log.info('drawings_loaded_from_cache_after_error', extra={'count': len(cached_drawings), 'path': path, 'error': str(e)})
            except Exception:
                pass

    def select_image(self, path: str):
        # Speichere aktuelles Bild sofort (mit Cache-Layer falls verfügbar)
        current_path = self._current_path()
        if current_path and self._cache_layer:
            # Flushe pending changes für aktuelles Bild asynchron im Hintergrund
            # (vermeidet UI-Blockierung bei langsamem EXIF-Schreiben)
            # WICHTIG: Erstelle lokale Kopie des Pfads, um Race Condition zu vermeiden
            path_to_flush = current_path
            from PySide6.QtCore import QTimer
            def _flush_async():
                try:
                    # Verwende lokale Kopie, nicht self._current_path() (könnte sich geändert haben)
                    self._cache_layer.flush_to_exif(path_to_flush)
                except Exception:
                    pass
            QTimer.singleShot(0, _flush_async)
        else:
            # Fallback: Normales Speichern asynchron im Hintergrund
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._save_current_exif)
        
        # Stelle sicher, dass der Ordner gesetzt ist und der Index stimmt
        folder = os.path.dirname(path)
        if path not in self._image_paths:
            self.set_folder(folder)
        try:
            idx = self._image_paths.index(path)
            self._current_index = idx
        except ValueError:
            pass
        # Bild sofort laden (ohne zu warten)
        self.load_image(path)
    
    def set_cache_layer(self, cache_layer):
        """Setzt den Cache-Layer (wird von MainWindow aufgerufen)"""
        self._cache_layer = cache_layer

    def _edit_ocr_tag(self):
        # Öffnet den Dialog, trägt Änderungen in EXIF ein und aktualisiert Overlay/Label
        path = self._current_path()
        if not path:
            return
        try:
            from .dialogs import OcrEditDialog
            info = get_ocr_info(path)
            dlg = OcrEditDialog(self, tag=info.get('tag', ''))
            if dlg.exec() == QDialog.Accepted:
                tag = dlg.result_tag()
                # Tag normalisieren: Leerstring oder nur Whitespace = None (kein Tag)
                tag_clean = tag.strip() if tag else ""
                tag_value = tag_clean.upper() if tag_clean else None
                
                # Speichere in EXIF (None -> Tag entfernen)
                try:
                    if not set_ocr_info(path, tag=tag_value):
                        raise Exception("set_ocr_info returned False - Tag konnte nicht gespeichert werden")
                    display_tag = tag_value if tag_value else "—"
                    if tag_value:
                        self._log.info("ocr_tag_updated", extra={"path": path, "tag": tag_value})
                    else:
                        self._log.info("ocr_tag_removed", extra={"path": path})
                except Exception as save_error:
                    self._log.error("ocr_tag_save_failed", extra={"error": str(save_error), "path": path, "tag": tag_value})
                    QMessageBox.warning(self, "Fehler", f"OCR-Tag konnte nicht gespeichert werden:\n{save_error}")
                    return
                
                # WICHTIG: Cache invalidierten, damit neuer Tag sofort sichtbar ist
                window = self.window()
                if window and hasattr(window, 'evaluation_cache') and window.evaluation_cache:
                    try:
                        window.evaluation_cache.update_image_tag(path, tag_value if tag_value else '')
                        window.evaluation_cache.invalidate()
                    except Exception:
                        pass
                
                # UI aktualisieren (Label und Overlay)
                if display_tag != "—":
                    self.ocr_label.setText(display_tag)
                    self.view.set_ocr_label(self._tag_with_heading(display_tag))
                else:
                    self.ocr_label.setText("—")
                    self.view.set_ocr_label("")
                
                # Header-Anzeige aktualisieren
                self._update_ocr_header_display(display_tag)
                
                # View und Scene explizit aktualisieren, damit Overlay sofort sichtbar ist
                if hasattr(self.view, 'viewport'):
                    self.view.viewport().update()
                if hasattr(self.view, 'scene') and self.view.scene():
                    self.view.scene().update()
                
                # Galerie informieren
                try:
                    self.ocrTagUpdated.emit(path)
                except Exception:
                    pass
        except Exception as e:
            self._log.error("edit_ocr_tag_failed", extra={"error": str(e), "path": path})

    def _open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Ordner öffnen", "")
        if not folder:
            return
        self.set_folder(folder)

    def set_folder(self, folder: str):
        # Beim Ordnerwechsel ggf. aktuelle Bewertung sichern
        self._save_current_exif()
        
        # Cache leeren bei Ordnerwechsel (verhindert Memory Leak)
        self._image_cache.clear()
        
        # Bereinige auch Cache-Layer für alten Ordner (verhindert RAM-Überlauf)
        if self._cache_layer:
            try:
                # Entferne alle Einträge die nicht mehr existieren
                # (wird automatisch beim nächsten Zugriff bereinigt)
                pass  # clear_cache() würde alle löschen, was zu aggressiv ist
            except Exception:
                pass
        
        exts = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tif', '.tiff'}
        files = [os.path.join(folder, f) for f in os.listdir(folder) if os.path.splitext(f)[1].lower() in exts]
        
        # Sortierung nach aktuellem Modus
        self._sort_files(files)
        
        self._image_paths = files
        self._current_index = 0 if files else -1
        total = len(files)
        self._evaluated.clear()
        
        # Zähle bereits bewertete Bilder
        self._rebuild_evaluated_set()
        
        self._update_labels()
        self._log.info("folder_open", extra={"event": "folder_open", "folder": folder, "count": total})
        # WICHTIG: Lade immer das erste Bild, wenn ein Ordner ausgewählt ist und Bilder vorhanden sind
        if total > 0:
            self.load_image(files[0])
        else:
            if self._evaluation_panel:
                try:
                    self._evaluation_panel.set_path(None)
                except Exception:
                    pass
            self._update_action_tooltips()
            self._refresh_use_toggle(False)
            self._refresh_gene_button(False)
        self._current_folder = folder or ""
        self._update_open_button_tooltip()
        self.progressChanged.emit(1 if total else 0, total, len(self._evaluated))
        self._update_nav()
        self.folderChanged.emit(folder)
    
    def _on_sort_toggle_changed(self, is_alphabetic: bool):
        """Wird aufgerufen wenn Sortierungs-Toggle geändert wird"""
        # Button-Style aktualisieren
        self._update_sort_button_style(is_alphabetic)
        
        if not self._image_paths:
            return
        
        # Aktuelles Bild merken
        current_path = self._current_path()
        
        # Neu sortieren
        self._sort_files(self._image_paths)
        
        # Index des aktuellen Bildes in neuer Sortierung finden
        if current_path:
            try:
                self._current_index = self._image_paths.index(current_path)
            except ValueError:
                self._current_index = 0
        
        # UI aktualisieren
        self._update_labels()
        self._update_nav()
    
    def _update_sort_button_style(self, is_alphabetic: bool):
        """Aktualisiert Button-Style: Grün für ABC, Grau für TreeView"""
        if is_alphabetic:
            # Grün für alphabetische Sortierung
            self.sort_toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #4caf50;
                    color: white;
                    border: 2px solid #388e3c;
                    font-weight: bold;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #66bb6a;
                }
                QPushButton:pressed {
                    background-color: #388e3c;
                }
            """)
            self.sort_toggle_btn.setToolTip("ABC: Alphabetisch nach Bildname (Klick für TreeView-Reihenfolge)")
        else:
            # Grau für TreeView-Reihenfolge
            self.sort_toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #757575;
                    color: white;
                    border: 2px solid #616161;
                    font-weight: bold;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #9e9e9e;
                }
                QPushButton:pressed {
                    background-color: #616161;
                }
            """)
            self.sort_toggle_btn.setToolTip("TreeView-Reihenfolge (Klick für ABC alphabetisch)")
    
    def _sort_files(self, files: list):
        """Sortiert Dateiliste nach aktuellem Modus (in-place)"""
        is_alphabetic = self.sort_toggle_btn.isChecked() if hasattr(self, 'sort_toggle_btn') else True
        
        if is_alphabetic:
            # Alphabetisch nach Bildname
            files.sort()
        else:
            # TreeView-Reihenfolge
            self._sort_by_treeview(files)
    
    def _sort_by_treeview(self, files: list):
        """Sortiert Bilder nach TreeView-Reihenfolge (Kategorien → Kürzel)"""
        from utils_exif import get_ocr_info
        
        # Hole Kürzel-Tabelle mit Kategorien und Reihenfolge
        kurzel_table = self.settings_manager.get('kurzel_table', {}) or {}
        
        # Erstelle Sortier-Schlüssel: (Kategorie-Name, Kürzel-Name)
        # Gruppiere nach Kategorien, dann innerhalb Kategorie nach Kürzeln alphabetisch
        
        def get_sort_key(filepath: str) -> tuple:
            try:
                # Hole OCR-Tag für dieses Bild
                ocr_info = get_ocr_info(filepath)
                tag = ocr_info.get('tag', '') if ocr_info else ''
                
                if tag and tag in kurzel_table:
                    # Hole Kategorie und Order aus Kürzel-Tabelle
                    kurzel_data = kurzel_table[tag]
                    category = kurzel_data.get('category', 'ZZZZ_Unbekannt')  # Unbekannt ans Ende
                    order = kurzel_data.get('order', 9999)
                    
                    # Sortier-Schlüssel: (Kategorie, Order, Kürzel-Name, Dateiname)
                    return (category, order, tag, os.path.basename(filepath))
                else:
                    # Bilder ohne Tag oder unbekanntes Tag ans Ende
                    return ('ZZZZ_Ohne_Tag', 9999, tag or '', os.path.basename(filepath))
            except Exception:
                # Bei Fehler: ans Ende sortieren
                return ('ZZZZ_Fehler', 9999, '', os.path.basename(filepath))
        
        # Sortiere mit dem Schlüssel
        files.sort(key=get_sort_key)

    # --- OCR Integration ---
    def _start_ocr(self, path: str):
        try:
            # Beende ggf. vorherigen Thread sauber
            self._stop_ocr_thread()
            self.ocr_label.setText("…")
            dp = DetectParams()
            args = {
                'path': path,
                'dp': dp.__dict__,
                'valid_kurzel': config_manager.get_setting('valid_kurzel', []),
                'enable_post_processing': True,
                'char_mappings': None,
            }
            # Worker + Thread
            self._ocr_thread = QThread(self)
            self._ocr_worker = _OcrWorker(args, self.settings_manager)
            self._ocr_worker.moveToThread(self._ocr_thread)
            self._ocr_thread.started.connect(self._ocr_worker.run)
            self._ocr_worker.finished.connect(self._ocr_thread.quit)
            self._ocr_worker.finished.connect(self._ocr_worker.deleteLater)
            self._ocr_worker.finished.connect(self._on_ocr_result)
            self._ocr_thread.finished.connect(self._ocr_thread.deleteLater)
            
            # Timeout-Timer
            from PySide6.QtCore import QTimer
            ocr_timeout = self.settings_manager.get('ocr_timeout', 30)
            self._ocr_timer = QTimer()
            self._ocr_timer.setSingleShot(True)
            self._ocr_timer.timeout.connect(self._on_ocr_timeout)
            self._ocr_timer.start(ocr_timeout * 1000)  # Millisekunden
            
            self._ocr_thread.start()
        except Exception:
            self.ocr_label.setText("—")

    def _on_ocr_timeout(self):
        """OCR-Timeout behandeln"""
        self._log.warning("ocr_timeout", extra={"event": "ocr_timeout"})
        self._stop_ocr_thread()
        self.ocr_label.setText("Timeout")
    
    def _on_ocr_result(self, result: dict):
        # Timer stoppen wenn Ergebnis da ist
        if hasattr(self, '_ocr_timer') and self._ocr_timer:
            self._ocr_timer.stop()
        
        # Ignoriere Ergebnisse, wenn inzwischen ein anderes Bild aktiv ist
        if not isinstance(result, dict):
            return
        path_now = self._current_path()
        if result.get('path') != path_now:
            return
        txt = result.get('text') or "—"
        self.ocr_label.setText(str(txt))
        box = result.get('box')
        if box:
            try:
                x, y, w, h = box
                self.view.set_box(x, y, w, h)
            except Exception:
                pass
        # Overlay-Text setzen (mit Überschrift, falls vorhanden)
        try:
            self.view.set_ocr_label(self._tag_with_heading(txt))
        except Exception:
            pass
        # Auto-Speichern in EXIF
        try:
            set_ocr_info(path_now, tag=txt if txt and txt != '—' else None, box=box)
            self._log.info("ocr_tag_saved", extra={"event": "ocr_tag_saved", "path": path_now, "tag": txt})
        except Exception:
            pass

    def _rebuild_evaluated_set(self):
        """Baut das Set der bewerteten Bilder neu auf (für Fortschrittsanzeige)"""
        self._evaluated.clear()
        for idx, path in enumerate(self._image_paths):
            try:
                eval_data = get_evaluation(path)
                if eval_data and self._is_image_evaluated(eval_data):
                    self._evaluated.add(idx)
            except Exception:
                pass
    
    def _is_image_evaluated(self, eval_data: dict) -> bool:
        """Prüft ob ein Bild bewertet wurde"""
        if not eval_data:
            return False
        # Bild gilt als bewertet wenn mind. ein Feld gesetzt ist
        return bool(
            eval_data.get('categories') or 
            eval_data.get('quality') or 
            eval_data.get('image_type') or
            eval_data.get('image_types')
        )
    
    def _update_labels(self):
        total = len(self._image_paths)
        pos = (self._current_index + 1) if self._current_index >= 0 else 0
        done = len(self._evaluated)
        self.progress_label.setText(f"Bild {pos}/{total} – Bearbeitet {done}/{total}")
        self.progressChanged.emit(pos, total, done)

    def _update_nav(self):
        total = len(self._image_paths)
        has = total > 0 and self._current_index >= 0
        
        # Navigation aktiv halten (egal in welcher Position)
        nav_position = self.settings_manager.get("navigation_position", "below") or "below"
        active_container = self.nav_container
        
        if active_container:
            if hasattr(active_container, 'btn_prev'):
                active_container.btn_prev.setEnabled(has and self._current_index > 0)
            if hasattr(active_container, 'btn_next'):
                active_container.btn_next.setEnabled(has and self._current_index < total - 1)
            active_container.setVisible(has)
        if self.nav_below_wrapper:
            self.nav_below_wrapper.setVisible(has and nav_position == "below")
    
    def _on_settings_changed(self, settings_dict):
        """Wird aufgerufen wenn Settings geändert werden"""
        if "navigation_position" in settings_dict:
            self._update_navigation_position()
    
    def _update_navigation_position(self):
        """Aktualisiert die Navigation-Position basierend auf Settings"""
        nav_position = str(self.settings_manager.get("navigation_position", "below") or "below")

        if not self.nav_container:
            return

        # Temporär ausblenden, damit keine Artefakte sichtbar sind
        self.nav_container.hide()

        if nav_position == "overlay":
            # Entferne ggf. vorhandenen Wrapper aus dem Layout
            if self.nav_below_wrapper:
                v = self.layout()
                if v:
                    v.removeWidget(self.nav_below_wrapper)
                self.nav_below_wrapper.deleteLater()
                self.nav_below_wrapper = None

            # Navigation als Overlay in der View platzieren
            if self.view:
                self.nav_container.setParent(self.view)
                self.nav_container.setWindowFlags(Qt.WindowType.Widget)
                self.nav_container.raise_()
                self.nav_container.show()
                self._position_overlay_navigation()

            self._update_nav()
            return

        # Fallback auf "below" für unbekannte Werte
        if nav_position not in ["overlay", "below"]:
            nav_position = "below"
            self.settings_manager.set("navigation_position", "below")

        # Navigation unter dem Bild einfügen (zentriert)
        v = self.layout()
        if v:
            # Entferne bestehenden Wrapper, um ihn frisch aufzubauen
            if self.nav_below_wrapper:
                v.removeWidget(self.nav_below_wrapper)
                self.nav_below_wrapper.deleteLater()
                self.nav_below_wrapper = None

            self.nav_below_wrapper = QWidget()
            nav_wrapper_layout = QHBoxLayout(self.nav_below_wrapper)
            nav_wrapper_layout.setContentsMargins(0, 0, 0, 0)
            nav_wrapper_layout.addStretch()
            nav_wrapper_layout.addWidget(self.nav_container)
            nav_wrapper_layout.addStretch()

            # Parent/Flags setzen, damit Widget normal im Layout geführt wird
            self.nav_container.setParent(self.nav_below_wrapper)
            self.nav_container.setWindowFlags(Qt.WindowType.Widget)

            if hasattr(self, 'desc_group') and self.desc_group is not None:
                desc_group_idx = -1
                for i in range(v.count()):
                    item = v.itemAt(i)
                    if item and item.widget() == self.desc_group:
                        desc_group_idx = i
                        break
                if desc_group_idx >= 0:
                    v.insertWidget(desc_group_idx, self.nav_below_wrapper)
                else:
                    v.addWidget(self.nav_below_wrapper)
            else:
                v.addWidget(self.nav_below_wrapper)

            self.nav_container.show()
            self.nav_below_wrapper.show()

        self._update_nav()

    def next_image(self):
        total = len(self._image_paths)
        if total == 0 or self._current_index >= total - 1:
            return
        # Speichere aktuelle Metadaten asynchron im Hintergrund (nicht blockierend)
        self._save_current_exif_async()
        self._current_index += 1
        self.load_image(self._image_paths[self._current_index])

    def prev_image(self):
        total = len(self._image_paths)
        if total == 0 or self._current_index <= 0:
            return
        # Speichere aktuelle Metadaten asynchron im Hintergrund (nicht blockierend)
        self._save_current_exif_async()
        self._current_index -= 1
        self.load_image(self._image_paths[self._current_index])

    def first_image(self):
        if not self._image_paths:
            return
        # Speichere aktuelle Metadaten asynchron im Hintergrund (nicht blockierend)
        self._save_current_exif_async()
        self._current_index = 0
        self.load_image(self._image_paths[self._current_index])

    def last_image(self):
        if not self._image_paths:
            return
        # Speichere aktuelle Metadaten asynchron im Hintergrund (nicht blockierend)
        self._save_current_exif_async()
        self._current_index = len(self._image_paths) - 1
        self.load_image(self._image_paths[self._current_index])

    def mark_and_next(self):
        if self._current_index >= 0:
            # Speichern in EXIF und Fortschritt markieren
            self._save_current_exif()
            self._update_labels()
            if self._current_index < len(self._image_paths) - 1:
                self.next_image()

    # Hilfsfunktionen
    def _current_path(self):
        if 0 <= self._current_index < len(self._image_paths):
            return self._image_paths[self._current_index]
        return None
    
    def current_path(self) -> str | None:
        return self._current_path()
    
    def _precache_adjacent_images(self):
        """Lädt benachbarte Bilder im Hintergrund vor"""
        if self._current_index < 0 or not self._image_paths:
            return
        
        try:
            # Bestimme Bereich zum Vorladen (konfigurierbar via self._cache_range)
            cache_range = getattr(self, '_cache_range', 8)
            start_idx = max(0, self._current_index - cache_range)
            end_idx = min(len(self._image_paths), self._current_index + cache_range + 1)
            
            # Lade Bilder die noch nicht im Cache sind
            for idx in range(start_idx, end_idx):
                if idx == self._current_index:
                    continue  # Aktuelles Bild ist bereits geladen
                
                path = self._image_paths[idx]
                if path not in self._image_cache:
                    try:
                        pix = QPixmap(path)
                        if not pix.isNull():
                            self._image_cache[path] = pix
                    except Exception:
                        pass
            
            # Cache-Größe begrenzen (entferne alte Einträge)
            max_cache = getattr(self, '_max_cache_size', 25)
            if len(self._image_cache) > max_cache:
                # Entferne Bilder die am weitesten vom aktuellen Index entfernt sind
                current_path = self._current_path()
                paths_to_keep = set(self._image_paths[start_idx:end_idx])
                if current_path:
                    paths_to_keep.add(current_path)
                
                for path in list(self._image_cache.keys()):
                    if path not in paths_to_keep:
                        del self._image_cache[path]
        
        except Exception:
            pass

    def _update_open_button_tooltip(self):
        if hasattr(self, 'btn_open') and self.btn_open:
            folder = self._current_folder or ""
            self.btn_open.setToolTip(folder if folder else "Kein Ordner ausgewählt")

    def _update_action_tooltips(self):
        path = self._current_path()
        tooltip = path if path else "Kein Bild ausgewählt"
        if hasattr(self, 'btn_ok') and self.btn_ok:
            self.btn_ok.setToolTip(tooltip)
        if hasattr(self, 'btn_reject') and self.btn_reject:
            self.btn_reject.setToolTip(tooltip)
        if hasattr(self, 'btn_gene') and self.btn_gene:
            base = "Gene-Zweitmeinung anfordern" if not self.btn_gene.isChecked() else "Gene-Zweitmeinung aktiv"
            if path:
                self.btn_gene.setToolTip(f"{base}\n{path}")
            else:
                self.btn_gene.setToolTip(base)

        if hasattr(self, 'use_header_toggle') and self.use_header_toggle:
            base = "Bild verwenden"
            if path:
                self.use_header_toggle.setToolTip(f"{base}\n{path}")
            else:
                self.use_header_toggle.setToolTip(base)
        if hasattr(self, 'gene_header_toggle') and self.gene_header_toggle:
            base = "Gene"
            if path:
                self.gene_header_toggle.setToolTip(f"{base}\n{path}")
            else:
                self.gene_header_toggle.setToolTip(base)

    def _show_metadata_popup(self):
        path = self._current_path()
        if not path:
            QMessageBox.information(self, "Keine Datei", "Bitte zuerst ein Bild auswählen.")
            return
        try:
            data = read_metadata(path) or {}
        except Exception as exc:
            QMessageBox.warning(self, "Fehler", f"Metadaten konnten nicht gelesen werden:\n{exc}")
            return

        import json
        text = json.dumps(data, indent=2, ensure_ascii=False)

        dialog = QDialog(self)
        dialog.setWindowTitle(f"EXIF-JSON – {os.path.basename(path)}")
        layout = QVBoxLayout(dialog)
        editor = QPlainTextEdit()
        editor.setReadOnly(True)
        editor.setPlainText(text)
        editor.setMinimumSize(520, 400)
        layout.addWidget(editor, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        dialog.exec()

    def show_metadata_popup(self):
        self._show_metadata_popup()

    def _refresh_gene_button(self, value: bool | None = None):
        if not hasattr(self, 'btn_gene') or not self.btn_gene:
            return
        if value is None:
            try:
                if self._evaluation_panel:
                    state = self._evaluation_panel.get_state()
                    value = bool(state.get('gene'))
                elif self._current_path():
                    value = get_gene_flag(self._current_path())
                else:
                    value = False
            except Exception:
                value = False
        state = bool(value)
        self.btn_gene.blockSignals(True)
        self.btn_gene.setChecked(state)
        self.btn_gene.blockSignals(False)
        if hasattr(self, 'gene_header_toggle'):
            self.gene_header_toggle.blockSignals(True)
            self.gene_header_toggle.setChecked(state)
            self.gene_header_toggle.blockSignals(False)
        self._update_action_tooltips()

    def _refresh_use_toggle(self, value: bool | None = None):
        if not hasattr(self, 'use_header_toggle') or not self.use_header_toggle:
            return
        if value is None:
            try:
                if self._evaluation_panel:
                    state = self._evaluation_panel.get_state()
                    value = bool(state.get('use'))
                elif self._current_path():
                    value = get_used_flag(self._current_path())
                else:
                    value = False
            except Exception:
                value = False
        state = bool(value)
        self.use_header_toggle.blockSignals(True)
        self.use_header_toggle.setChecked(state)
        self.use_header_toggle.blockSignals(False)
        self._update_action_tooltips()

    def _set_use_from_header(self, checked: bool):
        self._apply_use_state(bool(checked))
        self._update_action_tooltips()

    def _set_gene_from_header(self, checked: bool):
        self._apply_gene_state(bool(checked))

    def _toggle_gene_flag(self):
        current = False
        try:
            if self._evaluation_panel:
                state = self._evaluation_panel.get_state()
                current = bool(state.get('gene'))
            elif self._current_path():
                current = get_gene_flag(self._current_path())
        except Exception:
            current = False
        self._apply_gene_state(not current)

    def _apply_gene_state(self, new_state: bool):
        handled = False
        if self._evaluation_panel:
            try:
                self._evaluation_panel.set_gene(new_state)
                handled = True
            except Exception:
                handled = False
        if not handled and self._current_path():
            try:
                set_gene_flag(self._current_path(), new_state)
            except Exception:
                pass
        self._refresh_gene_button(new_state)

    def _apply_use_state(self, new_state: bool):
        handled = False
        if self._evaluation_panel:
            try:
                self._evaluation_panel.set_use(new_state)
                handled = True
            except Exception:
                handled = False
        if not handled and self._current_path():
            try:
                set_used_flag(self._current_path(), new_state)
            except Exception:
                pass
        self._refresh_use_toggle(new_state)

    def _save_current_exif_async(self):
        """Speichert aktuelle Metadaten asynchron im Hintergrund (nicht blockierend für Navigation)"""
        path = self._current_path()
        if not path:
            return
        
        # Verwende Cache-Layer falls verfügbar (schneller)
        if self._cache_layer:
            # Flushe pending changes für aktuelles Bild asynchron im Hintergrund
            path_to_flush = path
            from PySide6.QtCore import QTimer
            def _flush_async():
                try:
                    self._cache_layer.flush_to_exif(path_to_flush)
                except Exception:
                    pass
            QTimer.singleShot(0, _flush_async)
        else:
            # Fallback: Normales Speichern asynchron im Hintergrund
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._save_current_exif)
    
    def _save_current_exif(self):
        path = self._current_path()
        if not path:
            return False
        try:
            # Hole Notes aus dem Textfeld
            notes = self.notes_edit.toPlainText().strip() if hasattr(self, 'notes_edit') and self.notes_edit else ''
            
            # EvaluationPanel speichert categories, quality, image_type, gene, use
            # Übergebe notes an _save_state
            if self._evaluation_panel:
                try:
                    # Wenn Timer läuft, stoppen und mit notes speichern
                    if self._evaluation_panel._auto_timer.isActive():
                        self._evaluation_panel._auto_timer.stop()
                        self._evaluation_panel._save_state(notes=notes)
                    else:
                        # Sonst auch speichern (für den Fall dass nichts geändert wurde)
                        self._evaluation_panel._save_state(notes=notes)
                except AttributeError:
                    try:
                        self._evaluation_panel._save_state()
                    except Exception:
                        pass
            
            # Evaluated-Status aktualisieren
            state = self._evaluation_panel.get_state() if self._evaluation_panel else {
                'categories': [],
                'quality': None,
                'image_type': None,
                'use': False,
                'gene': False,
            }
            evaluated = bool(state['categories'] or state['quality'] or state['image_type'])
            if self._current_index >= 0:
                if evaluated:
                    self._evaluated.add(self._current_index)
                else:
                    self._evaluated.discard(self._current_index)

            # Zeichnungen speichern (werden vom EvaluationPanel nicht verwaltet)
            self._save_current_drawings()
            
            self._log.info("exif_saved", extra={"event": "exif_saved", "path": path})
            return True
        except Exception as e:
            self._log.error("exif_save_failed", extra={"error": str(e)})
            return False
    
    def _save_current_drawings(self):
        """Persistiert Zeichnungen, erstellt Sicherung und exportiert annotiertes Bild."""
        path = self._current_path()
        manager = getattr(self.view, 'drawing_manager', None)
        if not path or not manager:
            return

        # Stoppe laufenden Timer (wir speichern jetzt sofort)
        if hasattr(self, '_drawing_timer') and self._drawing_timer.isActive():
            self._drawing_timer.stop()

        try:
            drawings_data = manager.get_drawings_data() or []
            # Deep-Copy der Daten, damit spätere Änderungen den Save nicht beeinflussen
            payload = [dict(item) for item in drawings_data]

            from PySide6.QtCore import QTimer

            # Neuesten Save-Request merken (überschreibt ältere, falls mehrere kurz hintereinander kommen)
            self._pending_drawing_task = (path, payload)

            if not self._drawing_flush_scheduled:
                self._drawing_flush_scheduled = True
                QTimer.singleShot(0, self._flush_pending_drawings)

            self._log.info(
                "drawing_save_scheduled",
                extra={"event": "drawing_save_scheduled", "path": path, "count": len(payload)},
            )
        except Exception as e:
            self._log.error("drawing_save_failed", extra={"error": str(e), "path": path})

    def _flush_pending_drawings(self):
        """Verarbeitet gespeicherte Zeichnungen sequentiell, um Überschneidungen zu vermeiden."""
        self._drawing_flush_scheduled = False
        task = self._pending_drawing_task
        self._pending_drawing_task = None

        if not task:
            return

        path, payload = task
        self._drawing_save_in_progress = True
        try:
            self._persist_drawings(path, payload)
        finally:
            self._drawing_save_in_progress = False
            # Falls während des Speicherns neue Zeichnungen eingegangen sind: sofort erneut flushen
            if self._pending_drawing_task:
                from PySide6.QtCore import QTimer

                if not self._drawing_flush_scheduled:
                    self._drawing_flush_scheduled = True
                    QTimer.singleShot(0, self._flush_pending_drawings)

    def _persist_drawings(self, path: str, drawings: list[dict]):
        if not path:
            return

        # Aktualisiere Cache sofort (auch wenn Speichern später fehlschlägt)
        self._drawings_cache[path] = [dict(item) for item in drawings] if drawings else []

        # Sicherung des Originalbilds (einmalig)
        try:
            backup_path = self._ensure_original_backup(path)
            if backup_path:
                self._log.info(
                    "image_backup_created",
                    extra={"event": "image_backup_created", "original": path, "backup": backup_path},
                )
        except Exception as e:
            self._log.error(
                "image_backup_failed", extra={"error": str(e), "path": path}
            )

        # Aktuelle Metadaten sichern, damit sie nach dem Export wiederhergestellt werden können
        metadata_snapshot = {}
        metadata_read_success = False
        try:
            md = read_metadata(path)
            if isinstance(md, dict):
                metadata_snapshot = md.copy()
                metadata_read_success = True
            else:
                metadata_snapshot = {}
        except Exception as e:
            self._log.error("drawing_metadata_read_failed", extra={"error": str(e), "path": path})
            metadata_snapshot = {}

        if drawings:
            metadata_snapshot["drawings"] = [dict(item) for item in drawings]
        else:
            metadata_snapshot.pop("drawings", None)

        # Annotiertes Bild exportieren und anschließend Metadaten wiederherstellen
        if drawings:
            try:
                panel = getattr(self, '_evaluation_panel', None)
                if panel and hasattr(panel, 'get_state'):
                    state = panel.get_state()
                    if not state.get('use', False) and hasattr(panel, 'set_use'):
                        panel.set_use(True)
            except Exception:
                pass
            temp_path = None
            try:
                _, ext = os.path.splitext(path)
                fd, temp_path = tempfile.mkstemp(suffix=ext or ".jpg", dir=os.path.dirname(path))
                os.close(fd)
            except Exception as e:
                self._log.error("annotated_image_temp_failed", extra={"error": str(e), "path": path})
                return

            annotated_path = self._export_annotated_image(path, target_path=temp_path)
            if annotated_path and os.path.exists(annotated_path):
                self._log.info(
                    "annotated_image_saved",
                    extra={
                        "event": "annotated_image_saved",
                        "original": path,
                        "annotated": annotated_path,
                    },
                )
                metadata_ok = False
                try:
                    metadata_ok = write_metadata(annotated_path, metadata_snapshot)
                except Exception as e:
                    self._log.error("drawing_metadata_write_failed", extra={"error": str(e), "path": path})
                    metadata_ok = False

                if not metadata_ok:
                    try:
                        os.remove(annotated_path)
                    except Exception:
                        pass
                    self._log.error(
                        "drawing_metadata_failed",
                        extra={"event": "drawing_metadata_failed", "path": path},
                    )
                    return

                try:
                    os.replace(annotated_path, path)
                except Exception as e:
                    self._log.error("annotated_image_replace_failed", extra={"error": str(e), "path": path})
                    try:
                        os.remove(annotated_path)
                    except Exception:
                        pass
                    return

                self._log.info(
                    "annotated_image_committed",
                    extra={"event": "annotated_image_committed", "path": path},
                )
                self._refresh_after_image_update(path)
            else:
                self._log.error(
                    "annotated_image_failed",
                    extra={"event": "annotated_image_failed", "path": path},
                )
                if annotated_path and os.path.exists(annotated_path):
                    try:
                        os.remove(annotated_path)
                    except Exception:
                        pass
        else:
            # Keine Zeichnungen: Metadaten ggf. aktualisieren (z. B. Löschen des Drawings-Blocks)
            try:
                if metadata_read_success:
                    write_metadata(path, metadata_snapshot)
            except Exception as e:
                self._log.error("drawing_metadata_write_failed", extra={"error": str(e), "path": path})

    def _ensure_original_backup(self, image_path: str) -> str | None:
        if not image_path:
            return None

        if image_path in self._original_backup_paths:
            return None

        directory = os.path.dirname(image_path)
        filename = os.path.basename(image_path)
        backup_dir_name = self.settings_manager.get("paths_backup_directory", "Backups") or "Backups"
        backup_dir = os.path.join(directory, backup_dir_name)
        os.makedirs(backup_dir, exist_ok=True)

        backup_path = os.path.join(backup_dir, filename)
        if os.path.exists(backup_path):
            self._original_backup_paths.add(image_path)
            return backup_path

        shutil.copy2(image_path, backup_path)
        self._original_backup_paths.add(image_path)
        return backup_path

    def _export_annotated_image(self, original_path: str, *, target_path: str | None = None) -> str | None:
        try:
            from PySide6.QtGui import QImage, QPainter

            scene = self.view.scene()
            if not scene or not scene.items():
                return None

            rect = scene.itemsBoundingRect()
            if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
                return None

            # Overlay (OCR-Tag) temporär ausblenden, damit er nicht eingebrannt wird
            hidden_items = self.view.begin_export_without_overlay()
            try:
                image = QImage(int(rect.width()), int(rect.height()), QImage.Format_RGB32)
                image.fill(Qt.white)

                painter = QPainter(image)
                painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
                scene.render(painter, target=image.rect(), source=rect)
                painter.end()
            finally:
                self.view.end_export_without_overlay(hidden_items)

            destination = target_path or original_path
            ext = os.path.splitext(destination)[1].lower()
            if ext in {".jpg", ".jpeg"}:
                if not image.save(destination, "JPEG", 95):
                    return None
            else:
                if not image.save(destination):
                    return None

            return destination
        except Exception as e:
            self._log.error("annotated_image_exception", extra={"error": str(e), "path": original_path})
            return None

    def _refresh_after_image_update(self, path: str):
        if not path:
            return

        try:
            if path in self._image_cache:
                del self._image_cache[path]
        except Exception:
            pass

        try:
            pix = QPixmap(path)
            if not pix.isNull():
                self._image_cache[path] = pix
                if hasattr(self.view, 'set_pixmap'):
                    self.view.set_pixmap(pix, reset=False)
                    # Overlay nach dem erneuten Laden sicherstellen
                    current_tag = self.ocr_label.text() if hasattr(self, 'ocr_label') else ''
                    if current_tag and current_tag.strip() and current_tag.strip() != "—":
                        self.view.set_ocr_label(self._tag_with_heading(current_tag.strip()))
                    else:
                        self.view.set_ocr_label("")
        except Exception as e:
            self._log.error("image_reload_failed", extra={"error": str(e), "path": path})

        try:
            if hasattr(self.view, 'viewport'):
                self.view.viewport().update()
        except Exception:
            pass

        try:
            window = self.window()
            gallery = getattr(window, 'gallery', None) if window else None
            if gallery and hasattr(gallery, 'refresh_item'):
                gallery.refresh_item(path, emit_signal=False, delay_ms=0)
        except Exception:
            pass
    
    def _stop_ocr_thread(self):
        try:
            if hasattr(self, "_ocr_thread") and self._ocr_thread:
                if self._ocr_thread.isRunning():
                    self._ocr_thread.requestInterruption()
                    self._ocr_thread.quit()
                    self._ocr_thread.wait(2000)
        except Exception:
            pass

    def closeEvent(self, ev):
        # Thread sauber beenden, um Warnungen zu vermeiden
        self._stop_ocr_thread()
        super().closeEvent(ev)

    # --- Notes Autosave ---
    def _schedule_notes_save(self):
        if self._notes_loading:
            return
        self._notes_timer.start(400)

    def _save_notes_async(self):
        path = self._current_path()
        if not path:
            return
        try:
            text = self.notes_edit.toPlainText().strip()
        except Exception:
            text = ''
        try:
            set_evaluation(path, notes=text)
        except Exception:
            pass
    
    def _schedule_drawing_save(self):
        """Startet Timer für verzögertes Zeichnungs-Speichern"""
        if hasattr(self, '_drawing_timer'):
            self._drawing_timer.start(2000)  # 2 Sekunden Debouncing
    
    def _save_drawings_async(self):
        """Speichert Zeichnungen nach Timer-Ablauf"""
        self._save_current_drawings()
    
    def _show_text_snippets(self):
        """Zeigt Dialog mit Textbausteinen für aktuelles OCR-Tag"""
        try:
            current_tag = ""
            path = self._current_path()
            if path:
                ocr_info = get_ocr_info(path)
                current_tag = ocr_info.get('tag', '') if ocr_info else ''

            config = self.settings_manager.get_text_snippet_config()
            tag_map = config.get('tags', {})
            groups_map = config.get('groups', {})

            current_key = current_tag.strip().upper() if current_tag else ''

            entries = []
            if current_key:
                for text in tag_map.get(current_key, []):
                    entries.append({
                        'source': f"Tag {current_key}",
                        'value': text
                    })
                for group_name, data in groups_map.items():
                    tags = [t.upper() for t in data.get('tags', [])]
                    if current_key in tags:
                        for text in data.get('snippets', []):
                            entries.append({
                                'source': f"Gruppe {group_name}",
                                'value': text
                            })

            if not entries:
                for tag_code, texts in tag_map.items():
                    for text in texts:
                        entries.append({
                            'source': f"Tag {tag_code}",
                            'value': text
                        })
                for group_name, data in groups_map.items():
                    for text in data.get('snippets', []):
                        entries.append({
                            'source': f"Gruppe {group_name}",
                            'value': text
                        })

            if not entries:
                QMessageBox.information(
                    self, "Keine Textbausteine",
                    "Keine Textbausteine definiert.\n\n"
                    "Gehen Sie zu Einstellungen → Textbausteine, um Textbausteine zu erstellen."
                )
                return
            
            dialog = TextSnippetPickerDialog(self, current_tag, entries)
            if dialog.exec() == dialog.Accepted:
                snippet = dialog.selected_snippet()
                if not snippet:
                    return
                current_text = self.notes_edit.toPlainText()
                if current_text.strip():
                    # Hänge an bestehenden Text an
                    self.notes_edit.setPlainText(current_text + "\n" + snippet)
                else:
                    # Ersetze leeren Text
                    self.notes_edit.setPlainText(snippet)
                
                # Cursor ans Ende setzen
                cursor = self.notes_edit.textCursor()
                cursor.movePosition(cursor.End)
                self.notes_edit.setTextCursor(cursor)
                
        except Exception as e:
            self._log.error("show_text_snippets_failed", extra={"event": "show_text_snippets_failed", "error": str(e)})

    def keyPressEvent(self, event):
        """Verarbeitet Tastatur-Shortcuts für Bewertung"""
        # Prüfe ob Textfeld fokussiert ist
        from PySide6.QtWidgets import QApplication
        if QApplication.focusWidget() == self.notes_edit:
            # Textfeld hat Fokus -> durchreichen
            super().keyPressEvent(event)
            return
        
        # Kein Evaluation Panel oder kein Bild geladen
        if not self._evaluation_panel or self._current_index < 0:
            super().keyPressEvent(event)
            return
        
        key = event.key()
        
        # Zahlen 1-9: Schadenskategorien togglen
        if Qt.Key_1 <= key <= Qt.Key_9:
            index = key - Qt.Key_1  # 0-basiert
            self._evaluation_panel.toggle_damage_by_index(index)
            event.accept()
            return
        
        # Q/W/E/R/T: Bildarten setzen
        image_type_keys = {
            Qt.Key_Q: 0,  # Gear
            Qt.Key_W: 1,  # Rolling Element
            Qt.Key_E: 2,  # Inner ring
            Qt.Key_R: 3,  # Outer ring
            Qt.Key_T: 4,  # Cage
        }
        if key in image_type_keys:
            self._evaluation_panel.set_image_type_by_index(image_type_keys[key])
            event.accept()
            return
        
        # U: Toggle "Bild verwenden"
        if key == Qt.Key_U:
            if hasattr(self, 'use_toggle') and self.use_toggle:
                self.use_toggle.setChecked(not self.use_toggle.isChecked())
            event.accept()
            return
        
        # V: Toggle "Visuell keine Defekte"
        if key == Qt.Key_V:
            self._evaluation_panel.toggle_visual_ok()
            event.accept()
            return
        
        # Andere Tasten normal verarbeiten
        super().keyPressEvent(event)

    def _position_overlay_navigation(self):
        """Positioniert die Navigation als Overlay zentriert unter dem Bild."""
        if not self.view or not self.nav_container:
            return

        try:
            self.nav_container.adjustSize()
            nav_width = self.nav_container.width()
            x = (self.view.width() - nav_width) / 2
            y = self.view.height() - self.nav_container.height() - 20
            self.nav_container.move(x, y)
            self.nav_container.raise_()
        except Exception:
            pass


class TextSnippetPickerDialog(QDialog):
    def __init__(self, parent, current_tag: str, entries: list[dict]):
        super().__init__(parent)
        self.setWindowTitle("Textbaustein einfügen")
        self._entries = entries

        layout = QVBoxLayout(self)

        label_tag = current_tag if current_tag else "—"
        description = QLabel(f"Textbausteine für '{label_tag}' auswählen:")
        description.setWordWrap(True)
        layout.addWidget(description)

        self.table = QTableWidget(len(entries), 2)
        self.table.setHorizontalHeaderLabels(["Quelle", "Text"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)

        for row, entry in enumerate(entries):
            source_item = QTableWidgetItem(entry.get('source', ''))
            text_item = QTableWidgetItem(entry.get('value', ''))
            self.table.setItem(row, 0, source_item)
            self.table.setItem(row, 1, text_item)

        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumWidth(420)
        self.table.setMinimumHeight(240)
        layout.addWidget(self.table)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.table.itemDoubleClicked.connect(lambda *_: self.accept())
        if entries:
            self.table.selectRow(0)

    def selected_snippet(self) -> str | None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self._entries):
            return None
        return self._entries[row].get('value')


class ImageView(QGraphicsView):
    def __init__(self):
        super().__init__()
        # QPainter-Flags verwenden (nicht self.RenderHint)
        self.setRenderHints(self.renderHints() | QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.NoDrag)  # Drag Mode wird vom Drawing Manager gesteuert
        self._pix = None
        self._rect_item = None
        self._tag_item = None
        self._tag_bg_item = None
        self._context_edit_callback = None
        self._pix_item = None
        
        # SettingsManager für Tag-Größe und Transparenz
        from .settings_manager import get_settings_manager
        self.settings_manager = get_settings_manager()
        
        # Zeichenwerkzeuge
        self.drawing_manager = None
        self._is_panning = False
        self._last_pan_pos = QPointF()
        
        # Zoom-Tracking
        self._zoom_factor = 1.0
        self.zoom_label = None  # Wird von außen gesetzt
        self._manual_zoom_active = False  # Flag: Wurde manuell gezoomt (nicht durch fit_to_view)
        self._zoom_mode = "fit_to_view"  # "fit_to_view", "1:1", oder "manual"

    def set_pixmap(self, pix: QPixmap, *, reset: bool = True):
        self._pix = pix
        sc = self.scene()
        if not sc:
            return

        if reset or self._pix_item is None:
            sc.clear()
            self._pix_item = sc.addPixmap(pix)
            if self._pix_item:
                self._pix_item.setZValue(-100)
        else:
            try:
                if self._pix_item:
                    self._pix_item.setPixmap(pix)
            except Exception:
                # Fallback: vollständiger Reset
                sc.clear()
                self._pix_item = sc.addPixmap(pix)
                if self._pix_item:
                    self._pix_item.setZValue(-100)
        
        # Zoom-Modus beibehalten beim Wechseln der Bilder
        if self._zoom_mode == "1:1":
            # 1:1 Zoom beibehalten - verwende die gleiche Logik wie reset_zoom()
            self.resetTransform()
            # Verwende fit_to_view() als Basis (wie in reset_zoom())
            rect = sc.itemsBoundingRect()
            if rect.isValid():
                self.fitInView(rect, Qt.KeepAspectRatio)
                view_rect = self.viewport().rect()
                scene_rect = self.sceneRect()
                if scene_rect.width() > 0 and scene_rect.height() > 0:
                    scale_x = view_rect.width() / scene_rect.width()
                    scale_y = view_rect.height() / scene_rect.height()
                    fit_scale = min(scale_x, scale_y) * 0.95  # 95% für Margin (wie in reset_zoom())
                    # Für 1:1: Wir müssen relativ zu fit_scale skalieren
                    # 1:1 bedeutet: zoom_to_original / fit_scale
                    target_relative_zoom = 1.0 / fit_scale if fit_scale > 0 else 1.0
                    self.scale(target_relative_zoom, target_relative_zoom)
                    self._zoom_factor = target_relative_zoom
                    self._update_zoom_label()
                    # Zentriere das Bild
                    if self._pix:
                        self.centerOn(self._pix.width() / 2, self._pix.height() / 2)
                    # Zoom-Modus bleibt "1:1" (nicht zurücksetzen)
        elif self._zoom_mode == "manual" and self._zoom_factor != 1.0:
            # Manueller Zoom beibehalten
            self.resetTransform()
            rect = sc.itemsBoundingRect()
            if rect.isValid():
                self.fitInView(rect, Qt.KeepAspectRatio)
                view_rect = self.viewport().rect()
                scene_rect = self.sceneRect()
                if scene_rect.width() > 0 and scene_rect.height() > 0:
                    scale_x = view_rect.width() / scene_rect.width()
                    scale_y = view_rect.height() / scene_rect.height()
                    fit_scale = min(scale_x, scale_y) * 0.95
                    target_scale = self._zoom_factor / fit_scale if fit_scale > 0 else self._zoom_factor
                    self.scale(target_scale, target_scale)
                    self._update_zoom_label()
        else:
            # Standard: fit_to_view beim Laden eines neuen Bildes
            self._zoom_mode = "fit_to_view"
            self._manual_zoom_active = False
            self.fit_to_view()

    def set_box(self, x: int, y: int, w: int, h: int):
        sc = self.scene()
        try:
            if self._rect_item is not None:
                sc.removeItem(self._rect_item)
        except Exception:
            pass
        pen = QPen(QColor(220, 0, 0))
        pen.setWidth(3)
        self._rect_item = sc.addRect(x, y, w, h, pen)
        # reposition tag label wenn vorhanden
        if self._tag_item is not None:
            self._tag_item.setPos(x + 4, y + 4)

    def set_ocr_label(self, text: str):
        sc = self.scene()
        if not sc:
            # Keine Scene vorhanden, kann Overlay nicht anzeigen
            return
            
        try:
            if self._tag_item is not None:
                sc.removeItem(self._tag_item)
                self._tag_item = None
            if self._tag_bg_item is not None:
                sc.removeItem(self._tag_bg_item)
                self._tag_bg_item = None
        except Exception:
            pass
            
        if not text or not text.strip():
            self._tag_item = None
            self._tag_bg_item = None
            # View aktualisieren, damit entferntes Overlay verschwindet
            if hasattr(self, 'viewport'):
                self.viewport().update()
            return
        
        from PySide6.QtGui import QFont, QBrush
        from PySide6.QtWidgets import QGraphicsTextItem, QGraphicsRectItem
        from PySide6.QtCore import QRectF
        
        # Text-Item erstellen
        self._tag_item = QGraphicsTextItem(str(text))
        f = QFont()
        f.setPointSize(self.settings_manager.get_single_tag_size())
        f.setBold(True)  # Text fett machen
        self._tag_item.setFont(f)
        self._tag_item.setDefaultTextColor(QColor(0, 0, 0))  # Schwarze Schrift
        
        # Text zentrieren
        self._tag_item.setTextWidth(-1)  # Automatische Breite
        self._tag_item.setDefaultTextColor(QColor(0, 0, 0))
        
        # Hintergrund-Kasten erstellen
        text_rect = self._tag_item.boundingRect()
        padding = 4
        bg_rect = QRectF(text_rect.x() - padding, text_rect.y() - padding, 
                        text_rect.width() + 2*padding, text_rect.height() + 2*padding)
        
        self._tag_bg_item = QGraphicsRectItem(bg_rect)
        opacity = self.settings_manager.get_tag_opacity()
        self._tag_bg_item.setBrush(QBrush(QColor(255, 255, 255, opacity)))  # Weißer, halbtransparenter Hintergrund
        self._tag_bg_item.setPen(QPen(QColor(0, 0, 0, 100), 1))  # Dünner schwarzer Rand
        
        # Position: oben in der Mitte des Bildes
        if self._pix:
            pix_width = self._pix.width()
            
            # Text zentrieren im Hintergrund-Kasten
            text_width = text_rect.width()
            bg_width = bg_rect.width()
            text_x_offset = (bg_width - text_width) / 2
            
            x_pos = (pix_width - bg_rect.width()) / 2
            y_pos = 10  # 10px vom oberen Rand
            
            self._tag_bg_item.setPos(x_pos, y_pos)
            self._tag_item.setPos(x_pos + text_x_offset, y_pos + padding)
        else:
            # Fallback: Position oben links, wenn kein Bild geladen
            self._tag_bg_item.setPos(10, 10)
            self._tag_item.setPos(14, 14)
        
        # Z-Order: Hintergrund unten, Text oben
        self._tag_bg_item.setZValue(9)
        self._tag_item.setZValue(10)
        
        # Items zur Scene hinzufügen
        sc.addItem(self._tag_bg_item)
        sc.addItem(self._tag_item)
        
        # View sofort aktualisieren, damit Overlay sichtbar wird
        if hasattr(self, 'viewport'):
            self.viewport().update()

    def begin_export_without_overlay(self):
        hidden = []
        for item in (self._tag_item, self._tag_bg_item):
            try:
                if item is not None and item.isVisible():
                    item.setVisible(False)
                    hidden.append(item)
            except Exception:
                pass
        return hidden

    def end_export_without_overlay(self, hidden_items):
        if not hidden_items:
            return
        for item in hidden_items:
            try:
                item.setVisible(True)
            except Exception:
                pass
        if hasattr(self, 'viewport'):
            self.viewport().update()

    def set_context_edit_handler(self, cb):
        self._context_edit_callback = cb

    def contextMenuEvent(self, ev):
        menu = QMenu(self)
        act = menu.addAction("OCR-Tag bearbeiten…")
        act.triggered.connect(lambda: self._context_edit_callback() if self._context_edit_callback else None)
        menu.exec(ev.globalPos())

    def fit_to_view(self):
        if not self.scene() or not self.scene().items():
            return
        rect = self.scene().itemsBoundingRect()
        if rect.isValid():
            self.fitInView(rect, Qt.KeepAspectRatio)
            # Berechne Zoom-Faktor nach fit_to_view
            view_rect = self.viewport().rect()
            scene_rect = self.sceneRect()
            if scene_rect.width() > 0 and scene_rect.height() > 0:
                scale_x = view_rect.width() / scene_rect.width()
                scale_y = view_rect.height() / scene_rect.height()
                fit_scale = min(scale_x, scale_y) * 0.95  # 95% für Margin
                self._zoom_factor = fit_scale
                self._update_zoom_label()
            self._manual_zoom_active = False  # Reset: Automatische Anpassung
            self._zoom_mode = "fit_to_view"  # Zoom-Modus setzen

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        # Nur fit_to_view aufrufen, wenn nicht manuell gezoomt wurde
        if not self._manual_zoom_active:
            self.fit_to_view()
        else:
            # Wenn manuell gezoomt: Zoom-Faktor beibehalten
            # Berechne neue Basis-Skalierung
            if self._pix and self.scene() and self.scene().items():
                self.resetTransform()
                rect = self.scene().itemsBoundingRect()
                if rect.isValid():
                    self.fitInView(rect, Qt.KeepAspectRatio)
                    # Skaliere auf gespeicherten Zoom-Faktor
                    view_rect = self.viewport().rect()
                    scene_rect = self.sceneRect()
                    if scene_rect.width() > 0 and scene_rect.height() > 0:
                        scale_x = view_rect.width() / scene_rect.width()
                        scale_y = view_rect.height() / scene_rect.height()
                        fit_scale = min(scale_x, scale_y) * 0.95
                        # Skaliere relativ zu fit_scale auf den gewünschten Zoom
                        target_scale = self._zoom_factor / fit_scale if fit_scale > 0 else self._zoom_factor
                        self.scale(target_scale, target_scale)
                        # Zentriere das Bild
                        if self._pix:
                            self.centerOn(self._pix.width() / 2, self._pix.height() / 2)
        
        # Positioniere Navigation-Overlay am unteren Rand (nur wenn "overlay" aktiv)
        nav_position = self.settings_manager.get("navigation_position", "below") or "below"
        if nav_position == "overlay":
            self._position_overlay_navigation()

    def wheelEvent(self, ev):
        # Strg+Mausrad = zoomen, sonst normal scrollen
        if ev.modifiers() & Qt.ControlModifier:
            factor = 1.15 if ev.angleDelta().y() > 0 else 1/1.15
            self.scale(factor, factor)
            self._zoom_factor *= factor
            self._manual_zoom_active = True  # Manueller Zoom aktiv
            self._zoom_mode = "manual"  # Zoom-Modus setzen
            self._update_zoom_label()
        else:
            super().wheelEvent(ev)
    
    def _update_zoom_label(self):
        """Aktualisiert das Zoom-Label"""
        if self.zoom_label:
            self.zoom_label.setText(f"{int(self._zoom_factor * 100)}%")
    
    def zoom_in(self):
        """Vergrößert die Ansicht"""
        factor = 1.25
        self.scale(factor, factor)
        self._zoom_factor *= factor
        self._manual_zoom_active = True  # Manueller Zoom aktiv
        self._zoom_mode = "manual"  # Zoom-Modus setzen
        self._update_zoom_label()
    
    def zoom_out(self):
        """Verkleinert die Ansicht"""
        factor = 0.8
        self.scale(factor, factor)
        self._zoom_factor *= factor
        self._manual_zoom_active = True  # Manueller Zoom aktiv
        self._zoom_mode = "manual"  # Zoom-Modus setzen
        self._update_zoom_label()
    
    def reset_zoom(self):
        """Setzt Zoom auf 1:1 zurück"""
        if not self._pix:
            return
        self.resetTransform()
        # Berechne Zoom-Faktor für 1:1 (Originalgröße)
        # 1:1 bedeutet: 1 Pixel Bild = 1 Pixel Bildschirm
        # Aber wir müssen sicherstellen, dass das Bild sichtbar ist
        # Daher verwenden wir fit_to_view() als Basis und dann skalieren wir auf 1:1
        self.fit_to_view()
        # Jetzt haben wir fit_to_view als Basis, berechne den Faktor für 1:1
        view_rect = self.viewport().rect()
        scene_rect = self.sceneRect()
        if scene_rect.width() > 0 and scene_rect.height() > 0:
            scale_x = view_rect.width() / scene_rect.width()
            scale_y = view_rect.height() / scene_rect.height()
            fit_scale = min(scale_x, scale_y) * 0.95  # 95% für Margin
            # Für 1:1: Wir müssen relativ zu fit_scale skalieren
            # 1:1 bedeutet: zoom_to_original / fit_scale
            target_relative_zoom = 1.0 / fit_scale if fit_scale > 0 else 1.0
            self.scale(target_relative_zoom, target_relative_zoom)
            self._zoom_factor = target_relative_zoom
        else:
            self._zoom_factor = 1.0
        self._update_zoom_label()
        # Zentriere das Bild
        if self._pix:
            self.centerOn(self._pix.width() / 2, self._pix.height() / 2)
        # 1:1 Zoom-Modus setzen
        self._manual_zoom_active = False
        self._zoom_mode = "1:1"
    
    # Zeichenwerkzeug-Integration
    def setup_drawing(self, manager: DrawingManager):
        """Initialisiert den Drawing Manager"""
        self.drawing_manager = manager
    
    def set_drawing_mode(self, mode: str):
        """Setzt den Zeichnungsmodus"""
        if self.drawing_manager:
            self.drawing_manager.set_mode(mode)
            # Drag Mode anpassen
            if mode == DrawingMode.PAN:
                self.setDragMode(QGraphicsView.ScrollHandDrag)
            else:
                self.setDragMode(QGraphicsView.NoDrag)
    
    def set_drawing_color(self, color: QColor):
        """Setzt die Zeichenfarbe"""
        if self.drawing_manager:
            self.drawing_manager.set_color(color)
    
    def set_drawing_width(self, width: int):
        """Setzt die Linienbreite"""
        if self.drawing_manager:
            self.drawing_manager.set_width(width)
    
    def undo_drawing(self):
        """Macht die letzte Zeichnung rückgängig"""
        if self.drawing_manager:
            self.drawing_manager.undo()
    
    def redo_drawing(self):
        """Stellt die letzte rückgängig gemachte Zeichnung wieder her"""
        if self.drawing_manager:
            self.drawing_manager.redo()
    
    def clear_all_drawings(self):
        """Löscht alle Zeichnungen"""
        if self.drawing_manager:
            self.drawing_manager.clear_all()
    
    def mousePressEvent(self, event):
        """Maus-Klick für Zeichnen oder Pan"""
        if not self.drawing_manager:
            super().mousePressEvent(event)
            return
        
        # Szenen-Position berechnen
        scene_pos = self.mapToScene(event.pos())
        
        if self.drawing_manager.mode == DrawingMode.PAN:
            # Pan-Modus: Qt's eingebautes Drag-System nutzen
            super().mousePressEvent(event)
        elif self.drawing_manager.mode != DrawingMode.NONE:
            # Zeichnen-Modus
            self.drawing_manager.start_drawing(scene_pos)
        else:
            super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Maus-Bewegung für Zeichnen-Vorschau oder Pan"""
        if not self.drawing_manager:
            super().mouseMoveEvent(event)
            return
        
        scene_pos = self.mapToScene(event.pos())
        
        if self.drawing_manager.mode == DrawingMode.PAN:
            # Pan-Modus
            super().mouseMoveEvent(event)
        elif self.drawing_manager.is_drawing:
            # Zeichnen-Vorschau
            self.drawing_manager.update_drawing(scene_pos)
        else:
            super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Maus-Release für Zeichnen beenden"""
        if not self.drawing_manager:
            super().mouseReleaseEvent(event)
            return
        
        scene_pos = self.mapToScene(event.pos())
        
        if self.drawing_manager.mode == DrawingMode.PAN:
            # Pan-Modus
            super().mouseReleaseEvent(event)
        elif self.drawing_manager.is_drawing:
            # Zeichnung beenden
            self.drawing_manager.finish_drawing(scene_pos)
        else:
            super().mouseReleaseEvent(event)




# OCR-Worker entfernt
