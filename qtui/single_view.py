# -*- coding: utf-8 -*-
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsView, 
                                QGraphicsScene, QPushButton, QFileDialog, QMenu, QToolBar,
                                QComboBox, QSpinBox, QGroupBox, QButtonGroup, QRadioButton)
from PySide6.QtGui import QPixmap, QPainter, QKeySequence, QShortcut, QPen, QColor, QAction
from PySide6.QtCore import Qt, Signal, QObject, QThread, QPointF
from utils_logging import get_logger
from .widgets import ToggleSwitch, ChipButton, SegmentedControl
from utils_exif import set_used_flag, set_evaluation, read_metadata, get_used_flag, set_ocr_info, get_ocr_info
# OCR-Erkennung entfernt: keine Abhängigkeit zu core_ocr/DetectParams
from config_manager import config_manager
from .settings_manager import get_settings_manager
from .drawing_tools import DrawingManager, DrawingMode
import os


class SingleView(QWidget):
    progressChanged = Signal(int, int, int)  # current_index(1-based), total, evaluated_count
    folderChanged = Signal(str)
    ocrTagUpdated = Signal(str)  # path
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

        # Header: Fortschritt + "Bild verwenden" Toggle
        head = QHBoxLayout(); v.addLayout(head)
        self.btn_open = QPushButton("Ordner öffnen…")
        self.btn_open.clicked.connect(self._open_folder)
        head.addWidget(self.btn_open)
        self.progress_label = QLabel("Bild 0/0 — Bearbeitet 0/0")
        head.addWidget(self.progress_label)
        head.addStretch(1)
        head.addWidget(QLabel("Bild verwenden"))
        self.use_toggle = ToggleSwitch();         head.addWidget(self.use_toggle)
        
        # OCR-Label als Dummy-Variable (wird nicht angezeigt)
        self.ocr_label = QLabel("—")
        self.ocr_label.hide()  # Verstecken

        # Bildbereich mit Toolbar links
        image_container = QHBoxLayout()
        v.addLayout(image_container, 1)
        
        # Linke Seite: Vertikal kombinierte Toolbars
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
        
        left_toolbar_layout.addStretch(1)
        image_container.addWidget(left_toolbar_container)

        # Mitte: Bildbereich
        self.view = ImageView(); self.view.setScene(QGraphicsScene())
        self.view.set_context_edit_handler(self._edit_ocr_tag)
        # Drawing Manager an View übergeben
        self.view.setup_drawing(DrawingManager(self.view.scene()))
        # Zoom-Label an View übergeben
        self.view.zoom_label = self.zoom_label
        image_container.addWidget(self.view, 1)
        
        # Rechte Seite: Bewertungs-Panel
        right_panel = self._create_evaluation_panel()
        image_container.addWidget(right_panel)
        
        # Navigation als Overlay auf dem Canvas unter dem Bild
        self.nav_container = self._create_canvas_navigation()
        self.nav_container.setParent(self.view)
        self.nav_container.raise_()
        # Position wird im resizeEvent des ImageView aktualisiert

        # Tastatur-Shortcuts (Pfeiltasten)
        QShortcut(QKeySequence(Qt.Key_Left), self, activated=self.prev_image)
        QShortcut(QKeySequence(Qt.Key_Right), self, activated=self.next_image)
        QShortcut(QKeySequence(Qt.Key_Home), self, activated=self.first_image)
        QShortcut(QKeySequence(Qt.Key_End), self, activated=self.last_image)
        # Leertaste für "Visuell OK und Weiter"
        QShortcut(QKeySequence(Qt.Key_Space), self, activated=self._mark_as_ok_and_next)
        # X-Taste für "Bild nicht verwenden und Weiter"
        QShortcut(QKeySequence(Qt.Key_X), self, activated=self._mark_as_reject_and_next)

    def _mark_as_ok_and_next(self):
        """Setzt nur 'Visuell keine Defekte' auf aktiv, setzt 'Bild verwenden' auf ja und geht zum nächsten Bild"""
        current_path = self._current_path()
        if not current_path:
            return
        
        try:
            # Alle anderen Schäden deaktivieren
            for chip in self.chip_buttons:
                chip.setChecked(False)
            
            # Nur "Visuell keine Defekte" aktivieren
            for chip in self.chip_buttons:
                if "Visuell" in chip.text() and "keine" in chip.text() and "Defekte" in chip.text():
                    chip.setChecked(True)
                    break
            
            # Setze "Bild verwenden" auf ja (falls nicht gesetzt)
            from utils_exif import set_used_flag
            set_used_flag(current_path, True)
            
            # Speichere die Bewertung
            self._save_current_exif()
            
            # Gehe zum nächsten Bild
            self.next_image()
            
            self._log.info("marked_as_ok_and_next", extra={"path": current_path})
            
        except Exception as e:
            self._log.error("mark_as_ok_failed", extra={"error": str(e), "path": current_path})

    def _mark_as_reject_and_next(self):
        """Markiert das Bild als 'nicht verwenden' und geht zum nächsten Bild"""
        current_path = self._current_path()
        if not current_path:
            return
        
        try:
            # Setze "use_image" auf False
            from utils_exif import set_used_flag
            set_used_flag(current_path, False)
            
            # Speichere die Bewertung
            self._save_current_exif()
            
            # Gehe zum nächsten Bild
            self.next_image()
            
            self._log.info("marked_as_reject_and_next", extra={"path": current_path})
            
        except Exception as e:
            self._log.error("mark_as_reject_failed", extra={"error": str(e), "path": current_path})

    def _create_canvas_navigation(self):
        """Erstellt Navigation direkt auf dem Canvas unter dem Bild"""
        # Navigation-Container als Overlay auf dem Canvas
        nav_container = QWidget()
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
        self.btn_reject = QPushButton("✗ Nicht verwenden")
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
        
        # Layout: Kompakt nebeneinander - erst Navigation, dann Bewertung
        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.btn_next)
        nav_layout.addWidget(self.btn_ok)
        nav_layout.addWidget(self.btn_reject)
        
        # Gebe den Container zurück, damit er im Hauptlayout eingefügt werden kann
        return nav_container

    def _create_evaluation_panel(self):
        """Erstellt das rechte Bewertungs-Panel"""
        from PySide6.QtWidgets import QScrollArea, QFrame
        
        # Scroll-Container für das Panel
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(224)  # 30% kleiner (320 * 0.7)
        scroll.setMaximumWidth(280)  # 30% kleiner (400 * 0.7)
        
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setSpacing(10)
        
        settings_manager = get_settings_manager()
        
        # Bildart (Chips, exklusiv)
        bildart_group = QGroupBox("Bildart")
        bildart_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                color: #333;
                border: 1px solid #ccc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        bildart_layout = QVBoxLayout(bildart_group)
        self.image_type_chips = []
        image_types = (settings_manager.get('image_types', []) or ["Wälzkörper", "Innenring", "Außenring", "Käfig", "Zahnrad"])[:5]
        
        for txt in image_types:
            b = ChipButton(txt)
            b.setCheckable(True)
            # Exklusive Auswahl: Beim Klick andere deaktivieren
            b.toggled.connect(lambda checked, button=b: self._on_image_type_selected(button) if checked else None)
            self.image_type_chips.append(b)
            bildart_layout.addWidget(b)
        
        layout.addWidget(bildart_group)
        
        # Schadenskategorien (Chips, multi)
        schaden_group = QGroupBox("Schadenskategorien")
        schaden_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                color: #333;
                border: 1px solid #ccc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        schaden_layout = QVBoxLayout(schaden_group)
        self.chip_buttons = []
        damage_categories = (settings_manager.get('damage_categories', []) or ["Visuell keine Defekte", "Kratzer", "Zykloidische Kratzer", "Stillstandsmarken", "Verschmierung", "Partikeldurchgang", "Überrollmarken", "Pittings", "Sonstige"])[:5]
        
        for txt in damage_categories:
            b = ChipButton(txt)
            
            # "Visuell keine Defekte" grün färben NUR wenn aktiviert
            if "Visuell" in txt and "keine" in txt and "Defekte" in txt:
                b.setStyleSheet("""
                    ChipButton:checked {
                        background-color: #4caf50;
                        color: white;
                        border: 2px solid #388e3c;
                        font-weight: bold;
                    }
                """)
            
            self.chip_buttons.append(b)
            schaden_layout.addWidget(b)
        
        layout.addWidget(schaden_group)
        
        # Bewertung (Chips, exklusiv)
        bewertung_group = QGroupBox("Bewertung")
        bewertung_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 12px;
                color: #333;
                border: 1px solid #ccc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        bewertung_layout = QVBoxLayout(bewertung_group)
        self.quality_chips = []
        qualities = ["Low", "Medium", "High"]
        
        for txt in qualities:
            b = ChipButton(txt)
            b.setCheckable(True)
            # Exklusive Auswahl
            b.toggled.connect(lambda checked, button=b: self._on_quality_selected(button) if checked else None)
            self.quality_chips.append(b)
            bewertung_layout.addWidget(b)
        
        # Medium standardmäßig ausgewählt
        if len(self.quality_chips) > 1:
            self.quality_chips[1].setChecked(True)
        
        layout.addWidget(bewertung_group)
        
        layout.addStretch(1)
        
        scroll.setWidget(container)
        return scroll
    
    def _on_image_type_selected(self, selected_button):
        """Stellt sicher, dass nur ein Bildart-Chip ausgewählt ist (exklusiv)"""
        for btn in self.image_type_chips:
            if btn != selected_button and btn.isChecked():
                btn.setChecked(False)
    
    def _on_quality_selected(self, selected_button):
        """Stellt sicher, dass nur ein Bewertungs-Chip ausgewählt ist (exklusiv)"""
        for btn in self.quality_chips:
            if btn != selected_button and btn.isChecked():
                btn.setChecked(False)
    
    def _create_drawing_toolbar_vertical(self):
        """Erstellt die vertikale Toolbar für Zeichenwerkzeuge"""
        group = QGroupBox("Zeichnen")
        layout = QVBoxLayout(group)
        layout.setSpacing(4)
        
        # Button Group für exklusive Auswahl
        mode_group = QButtonGroup(group)
        
        # Pan-Modus (Standard)
        pan_btn = QRadioButton("✋ Pan")
        pan_btn.setChecked(True)
        pan_btn.toggled.connect(lambda checked: self.view.set_drawing_mode(DrawingMode.PAN) if checked and hasattr(self.view, 'drawing_manager') else None)
        mode_group.addButton(pan_btn)
        layout.addWidget(pan_btn)
        
        # Pfeil
        arrow_btn = QRadioButton("➤ Pfeil")
        arrow_btn.toggled.connect(lambda checked: self.view.set_drawing_mode(DrawingMode.ARROW) if checked and hasattr(self.view, 'drawing_manager') else None)
        mode_group.addButton(arrow_btn)
        layout.addWidget(arrow_btn)
        
        # Kreis
        circle_btn = QRadioButton("○ Kreis")
        circle_btn.toggled.connect(lambda checked: self.view.set_drawing_mode(DrawingMode.CIRCLE) if checked and hasattr(self.view, 'drawing_manager') else None)
        mode_group.addButton(circle_btn)
        layout.addWidget(circle_btn)
        
        # Rechteck
        rect_btn = QRadioButton("▭ Rechteck")
        rect_btn.toggled.connect(lambda checked: self.view.set_drawing_mode(DrawingMode.RECTANGLE) if checked and hasattr(self.view, 'drawing_manager') else None)
        mode_group.addButton(rect_btn)
        layout.addWidget(rect_btn)
        
        # Freihand
        freehand_btn = QRadioButton("✏ Freihand")
        freehand_btn.toggled.connect(lambda checked: self.view.set_drawing_mode(DrawingMode.FREEHAND) if checked and hasattr(self.view, 'drawing_manager') else None)
        mode_group.addButton(freehand_btn)
        layout.addWidget(freehand_btn)
        
        layout.addSpacing(10)
        
        # Farbe
        layout.addWidget(QLabel("Farbe:"))
        color_combo = QComboBox()
        colors = ["red", "blue", "green", "yellow", "orange", "purple", "black", "white"]
        color_combo.addItems(colors)
        color_combo.currentTextChanged.connect(lambda c: self.view.set_drawing_color(QColor(c)) if hasattr(self.view, 'drawing_manager') else None)
        layout.addWidget(color_combo)
        
        # Linienbreite
        layout.addWidget(QLabel("Breite:"))
        width_spin = QSpinBox()
        width_spin.setRange(1, 20)
        width_spin.setValue(3)
        width_spin.valueChanged.connect(lambda w: self.view.set_drawing_width(w) if hasattr(self.view, 'drawing_manager') else None)
        layout.addWidget(width_spin)
        
        layout.addSpacing(10)
        
        # Undo/Redo Buttons
        undo_btn = QPushButton("↶ Undo")
        undo_btn.clicked.connect(lambda: self.view.undo_drawing() if hasattr(self.view, 'drawing_manager') else None)
        layout.addWidget(undo_btn)
        
        redo_btn = QPushButton("↷ Redo")
        redo_btn.clicked.connect(lambda: self.view.redo_drawing() if hasattr(self.view, 'drawing_manager') else None)
        layout.addWidget(redo_btn)
        
        clear_btn = QPushButton("🗑 Löschen")
        clear_btn.clicked.connect(lambda: self.view.clear_all_drawings() if hasattr(self.view, 'drawing_manager') else None)
        layout.addWidget(clear_btn)
        
        return group
    
    def _create_zoom_toolbar_vertical(self):
        """Erstellt die vertikale Toolbar für Zoom-Kontrollen"""
        group = QGroupBox("Zoom")
        layout = QVBoxLayout(group)
        layout.setSpacing(4)
        
        # Zoom-Anzeige
        self.zoom_label = QLabel("100%")
        self.zoom_label.setAlignment(Qt.AlignCenter)
        self.zoom_label.setStyleSheet("font-weight: bold; font-size: 14pt;")
        layout.addWidget(self.zoom_label)
        
        layout.addSpacing(5)
        
        # Zoom In
        zoom_in_btn = QPushButton("🔍+ Vergrößern")
        zoom_in_btn.clicked.connect(lambda: self.view.zoom_in() if self.view else None)
        layout.addWidget(zoom_in_btn)
        
        # Zoom Out
        zoom_out_btn = QPushButton("🔍- Verkleinern")
        zoom_out_btn.clicked.connect(lambda: self.view.zoom_out() if self.view else None)
        layout.addWidget(zoom_out_btn)
        
        # Fit to View
        fit_btn = QPushButton("⬜ Anpassen")
        fit_btn.clicked.connect(lambda: self.view.fit_to_view() if self.view else None)
        layout.addWidget(fit_btn)
        
        # Reset Zoom (1:1)
        reset_btn = QPushButton("1:1 Reset")
        reset_btn.clicked.connect(lambda: self.view.reset_zoom() if self.view else None)
        layout.addWidget(reset_btn)
        
        return group

    # API
    def load_image(self, path: str):
        self._log.info("image_load", extra={"event": "image_load", "path": path})
        pix = QPixmap(path)
        scene = self.view.scene()
        scene.clear()
        if not pix.isNull():
            self.view.set_pixmap(pix)
            # Automatische OCR entfernt - nur manuelle Bearbeitung erlaubt
        # Vorbelegung aus EXIF
        try:
            md = read_metadata(path) or {}
            ev = md.get('evaluation') or {}
            
            # Bildart aus EXIF laden
            img_type = ev.get('image_type')
            if img_type and hasattr(self, 'image_type_chips'):
                for b in self.image_type_chips:
                    b.setChecked(b.text() == img_type)
            
            # Schadenskategorien aus EXIF laden
            cats = set(ev.get('categories') or [])
            for b in self.chip_buttons:
                b.setChecked(b.text() in cats)
            
            # Bewertung aus EXIF laden
            quality = ev.get('quality')
            if quality and hasattr(self, 'quality_chips'):
                for b in self.quality_chips:
                    b.setChecked(b.text() == quality)
            # "Bild verwenden" aus EXIF holen
            try:
                self.use_toggle.setChecked(bool(get_used_flag(path)))
            except Exception:
                pass
            # OCR Tag aus EXIF (falls bereits gespeichert) - ohne Box-Anzeige
            try:
                o = get_ocr_info(path)
                if 'tag' in o:
                    if 'confidence' in o:
                        self.ocr_label.setText(f"{o['tag']} ({o.get('confidence', 0):.2f})")
                    else:
                        self.ocr_label.setText(o['tag'])
                    # Overlay im Bild anzeigen
                    self.view.set_ocr_label(o['tag'])
                else:
                    # Kein gespeichertes Tag -> Label zurücksetzen
                    self.ocr_label.setText("—")
                    # Overlay entfernen
                    self.view.set_ocr_label("")
            except Exception:
                self.ocr_label.setText("—")
                self.view.set_ocr_label("")
            
            # Zeichnungen aus EXIF laden
            drawings_data = md.get('drawings', [])
            if drawings_data and hasattr(self.view, 'drawing_manager') and self.view.drawing_manager:
                self.view.drawing_manager.load_drawings_data(drawings_data)
                self._log.info("drawings_loaded", extra={"count": len(drawings_data), "path": path})
        except Exception:
            pass
        # Label aktualisieren (Position/Progress)
        self._update_labels()
        self._update_nav()

    def select_image(self, path: str):
        # Vor Wechsel: aktuelle Bewertung speichern
        self._save_current_exif()
        # Stelle sicher, dass der Ordner gesetzt ist und der Index stimmt
        folder = os.path.dirname(path)
        if path not in self._image_paths:
            self.set_folder(folder)
        try:
            idx = self._image_paths.index(path)
            self._current_index = idx
        except ValueError:
            pass
        self.load_image(path)

    def _edit_ocr_tag(self):
        # Öffnet den Dialog, trägt Änderungen in EXIF ein und aktualisiert Overlay/Label
        path = self._current_path()
        if not path:
            return
        try:
            from .dialogs import OcrEditDialog
            info = get_ocr_info(path)
            dlg = OcrEditDialog(self, tag=info.get('tag', ''), confidence=info.get('confidence'))
            if dlg.exec() == dlg.Accepted:
                tag = dlg.result_tag()
                conf = dlg.result_confidence()
                set_ocr_info(path, tag=tag, confidence=conf)
                # UI aktualisieren (Label und Overlay)
                self.ocr_label.setText(f"{tag} ({conf:.2f})")
                self.view.set_ocr_label(tag)
                # Galerie informieren
                try:
                    self.ocrTagUpdated.emit(path)
                except Exception:
                    pass
        except Exception:
            pass

    def _open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Ordner öffnen", "")
        if not folder:
            return
        self.set_folder(folder)

    def set_folder(self, folder: str):
        # Beim Ordnerwechsel ggf. aktuelle Bewertung sichern
        self._save_current_exif()
        exts = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tif', '.tiff'}
        files = [os.path.join(folder, f) for f in os.listdir(folder) if os.path.splitext(f)[1].lower() in exts]
        files.sort()
        self._image_paths = files
        self._current_index = 0 if files else -1
        total = len(files)
        self._evaluated.clear()
        self._update_labels()
        self._log.info("folder_open", extra={"event": "folder_open", "folder": folder, "count": total})
        if total:
            self.load_image(files[0])
        self.progressChanged.emit(1 if total else 0, total, len(self._evaluated))
        self._update_nav()
        self.folderChanged.emit(folder)

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
        conf = result.get('confidence')
        if conf is not None:
            self.ocr_label.setText(f"{txt} ({conf:.2f})")
        else:
            self.ocr_label.setText(str(txt))
        box = result.get('box')
        if box:
            try:
                x, y, w, h = box
                self.view.set_box(x, y, w, h)
            except Exception:
                pass
        # Auto-Speichern in EXIF
        try:
            set_ocr_info(path_now, tag=txt if txt and txt != '—' else None, confidence=conf, box=box)
            self._log.info("ocr_tag_saved", extra={"event": "ocr_tag_saved", "path": path_now, "tag": txt, "conf": conf})
        except Exception:
            pass

    def _update_labels(self):
        total = len(self._image_paths)
        pos = (self._current_index + 1) if self._current_index >= 0 else 0
        done = len(self._evaluated)
        self.progress_label.setText(f"Bild {pos}/{total} — Bearbeitet {done}/{total}")
        self.progressChanged.emit(pos, total, done)

    def _update_nav(self):
        total = len(self._image_paths)
        has = total > 0 and self._current_index >= 0
        self.btn_prev.setEnabled(has and self._current_index > 0)
        self.btn_next.setEnabled(has and self._current_index < total - 1)

    def next_image(self):
        total = len(self._image_paths)
        if total == 0 or self._current_index >= total - 1:
            return
        # Speichere aktuelle Metadaten vor dem Wechsel
        self._save_current_exif()
        self._current_index += 1
        self.load_image(self._image_paths[self._current_index])

    def prev_image(self):
        total = len(self._image_paths)
        if total == 0 or self._current_index <= 0:
            return
        self._save_current_exif()
        self._current_index -= 1
        self.load_image(self._image_paths[self._current_index])

    def first_image(self):
        if not self._image_paths:
            return
        self._save_current_exif()
        self._current_index = 0
        self.load_image(self._image_paths[self._current_index])

    def last_image(self):
        if not self._image_paths:
            return
        self._save_current_exif()
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

    def _save_current_exif(self):
        path = self._current_path()
        if not path:
            return False
        try:
            # Markiere als bewertet
            if self._current_index >= 0:
                self._evaluated.add(self._current_index)
            # Schreibe EXIF aus aktueller UI
            set_used_flag(path, self.use_toggle.isChecked())
            
            # Schadenskategorien sammeln
            cats = [b.text() for b in self.chip_buttons if b.isChecked()]
            
            # Bildart sammeln (exklusiv)
            image_type = None
            if hasattr(self, 'image_type_chips'):
                for b in self.image_type_chips:
                    if b.isChecked():
                        image_type = b.text()
                        break
            
            # Bewertung sammeln (exklusiv)
            quality = None
            if hasattr(self, 'quality_chips'):
                for b in self.quality_chips:
                    if b.isChecked():
                        quality = b.text()
                        break
            
            set_evaluation(
                path,
                categories=cats,
                quality=quality,
                image_type=image_type,
            )
            
            # Zeichnungen speichern
            if hasattr(self.view, 'drawing_manager') and self.view.drawing_manager:
                drawings_data = self.view.drawing_manager.get_drawings_data()
                if drawings_data:
                    # Speichere Zeichnungen in EXIF
                    from utils_exif import update_metadata
                    update_metadata(path, {'drawings': drawings_data})
                    
                    # Erstelle Backup-Bild mit Zeichnungen
                    self._save_drawing_backup(path)
            
            self._log.info("exif_saved", extra={"event": "exif_saved", "path": path})
            return True
        except Exception as e:
            self._log.error("exif_save_failed", extra={"error": str(e)})
            return False

    def _save_drawing_backup(self, original_path: str):
        """Erstellt ein Backup-Bild mit eingezeichneten Elementen"""
        try:
            import os
            from PySide6.QtGui import QImage, QPainter
            from datetime import datetime
            
            # Backup-Verzeichnis erstellen
            backup_dir = os.path.join(os.path.dirname(original_path), "Annotiert")
            os.makedirs(backup_dir, exist_ok=True)
            
            # Backup-Dateiname mit Zeitstempel
            base_name = os.path.basename(original_path)
            name_without_ext = os.path.splitext(base_name)[0]
            ext = os.path.splitext(base_name)[1]
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{name_without_ext}_annotiert_{timestamp}{ext}"
            backup_path = os.path.join(backup_dir, backup_name)
            
            # Scene als Bild rendern
            scene = self.view.scene()
            if scene and scene.items():
                # Bounding Rect der Scene
                rect = scene.itemsBoundingRect()
                
                # QImage erstellen
                image = QImage(int(rect.width()), int(rect.height()), QImage.Format_RGB32)
                image.fill(Qt.white)
                
                # Scene auf Image rendern
                painter = QPainter(image)
                painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
                scene.render(painter, target=image.rect(), source=rect)
                painter.end()
                
                # Bild speichern
                if image.save(backup_path):
                    self._log.info("drawing_backup_saved", extra={
                        "event": "drawing_backup_saved",
                        "original": original_path,
                        "backup": backup_path
                    })
                    return backup_path
            
            return None
        except Exception as e:
            self._log.error("drawing_backup_failed", extra={"error": str(e), "path": original_path})
            return None
    
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

    def set_pixmap(self, pix: QPixmap):
        self._pix = pix
        sc = self.scene()
        sc.clear()
        sc.addPixmap(pix)
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
        try:
            if self._tag_item is not None:
                sc.removeItem(self._tag_item)
            if self._tag_bg_item is not None:
                sc.removeItem(self._tag_bg_item)
        except Exception:
            pass
        if not text:
            self._tag_item = None
            self._tag_bg_item = None
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
        
        # Z-Order: Hintergrund unten, Text oben
        self._tag_bg_item.setZValue(9)
        self._tag_item.setZValue(10)
        
        sc.addItem(self._tag_bg_item)
        sc.addItem(self._tag_item)

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

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self.fit_to_view()
        
        # Positioniere Navigation-Overlay am unteren Rand zentriert
        if hasattr(self.parent(), 'nav_container'):
            nav = self.parent().nav_container
            if nav:
                # Zentriere horizontal, positioniere am unteren Rand
                nav_width = nav.sizeHint().width()
                x = (self.width() - nav_width) // 2
                y = self.height() - nav.height() - 20  # 20px vom unteren Rand
                nav.move(x, y)
                nav.show()

    def wheelEvent(self, ev):
        # Strg+Mausrad = zoomen, sonst normal scrollen
        if ev.modifiers() & Qt.ControlModifier:
            factor = 1.15 if ev.angleDelta().y() > 0 else 1/1.15
            self.scale(factor, factor)
            self._zoom_factor *= factor
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
        self._update_zoom_label()
    
    def zoom_out(self):
        """Verkleinert die Ansicht"""
        factor = 0.8
        self.scale(factor, factor)
        self._zoom_factor *= factor
        self._update_zoom_label()
    
    def reset_zoom(self):
        """Setzt Zoom auf 1:1 zurück"""
        self.resetTransform()
        self._zoom_factor = 1.0
        self._update_zoom_label()
    
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
