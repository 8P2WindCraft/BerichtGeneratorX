# -*- coding: utf-8 -*-
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame,
    QPushButton, QFileDialog, QGridLayout, QComboBox, QLineEdit,
    QGroupBox, QCheckBox, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem,
    QHeaderView, QProgressBar
)
from PySide6.QtCore import Signal, Qt, QTimer, QSize
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QIcon
from utils_logging import get_logger
from utils_exif import get_ocr_info, get_evaluation
from .settings_manager import get_settings_manager
from .widgets import ChipButton
import os


class ClickableLabel(QLabel):
    clicked = Signal(str)
    doubleClicked = Signal(str)

    def __init__(self, path: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._path = path
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
            QLabel {
                border: 2px solid transparent;
                border-radius: 8px;
            }
            QLabel:hover {
                border-color: #2196F3;
            }
        """)

    def mousePressEvent(self, ev):
        # Einfacher Klick wird ignoriert - nur Doppelklick wechselt zur Einzelbildansicht
        return super().mousePressEvent(ev)
    
    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.doubleClicked.emit(self._path)
        return super().mouseDoubleClickEvent(ev)
    
    def set_status_icons(self, has_ocr: bool, is_evaluated: bool, quality: str = None):
        """Setzt Status-Icons für OCR und Bewertung"""
        # Status-Icons werden in _load_chunk() hinzugefügt
        pass


class GalleryView(QWidget):
    imageSelected = Signal(str)
    folderChanged = Signal(str)
    def __init__(self):
        super().__init__()
        self._log = get_logger('app', {"module": "qtui.gallery_view"})
        self._log.info("module_started", extra={"event": "module_started"})
        
        # Settings Manager
        self.settings_manager = get_settings_manager()

        # Hauptlayout mit Splitter
        main_layout = QVBoxLayout(self)
        
        # Splitter für Galerie und rechte Sidebar
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # Linke Seite: Galerie
        gallery_widget = QWidget()
        gallery_layout = QVBoxLayout(gallery_widget)
        splitter.addWidget(gallery_widget)

        # Toolbar mit Filter und Suchfunktionen
        toolbar = QHBoxLayout()
        gallery_layout.addLayout(toolbar)
        
        self.btn_open = QPushButton("Ordner öffnen…")
        toolbar.addWidget(self.btn_open)
        
        toolbar.addWidget(QLabel("Filter:"))
        
        # OCR-Filter
        self.ocr_filter = QComboBox()
        self.ocr_filter.addItems(["Alle", "Mit OCR-Tag", "Ohne OCR-Tag"])
        self.ocr_filter.currentTextChanged.connect(self._apply_filters)
        toolbar.addWidget(self.ocr_filter)
        
        toolbar.addWidget(QLabel("Status:"))
        
        # Status-Filter
        self.status_filter = QComboBox()
        self.status_filter.addItems(["Alle", "Bewertet", "Unbewertet", "High Quality", "Medium Quality", "Low Quality"])
        self.status_filter.currentTextChanged.connect(self._apply_filters)
        toolbar.addWidget(self.status_filter)
        
        # Suchfeld
        toolbar.addWidget(QLabel("Suche:"))
        self.search_field = QLineEdit()
        self.search_field.setPlaceholderText("Dateiname oder OCR-Tag...")
        self.search_field.textChanged.connect(self._apply_filters)
        toolbar.addWidget(self.search_field)
        
        toolbar.addStretch()

        # Layout-Auswahl (2x2, 3x3, 4x4, Auto-Fit)
        toolbar.addWidget(QLabel("Layout:"))
        self.grid_mode_combo = QComboBox()
        self.grid_mode_combo.addItems(["Auto-Fit", "2 x 2", "3 x 3", "4 x 4"])
        self.grid_mode_combo.currentTextChanged.connect(self._on_grid_mode_changed)
        toolbar.addWidget(self.grid_mode_combo)
        
        # Pagination
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(1)
        self.page_spin.valueChanged.connect(self._change_page)
        toolbar.addWidget(QLabel("Seite:"))
        toolbar.addWidget(self.page_spin)
        
        # Scroll-Grid
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.wrapper = QFrame()
        self.area.setWidget(self.wrapper)
        self.grid = QGridLayout(self.wrapper)
        self.grid.setContentsMargins(8, 8, 8, 8)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(8)
        gallery_layout.addWidget(self.area, 1)

        # Rechte Sidebar: Bewertungs-Panel
        self._create_evaluation_sidebar()
        splitter.addWidget(self.evaluation_panel)
        
        # Splitter-Verhältnis (30% kleiner für rechte Seite)
        splitter.setSizes([700, 210])

        self._thumb_size = (160, 120)
        self._paths = []
        self._filtered_paths = []
        self._labels = []
        self._cache = {}
        self._pending_idx = 0
        self._loader = QTimer(self)
        self._loader.timeout.connect(self._load_chunk)
        self._current_page = 1
        self._items_per_page = 20
        self._grid_mode = 'auto'  # 'auto' oder (rows, cols)
        self._rows = 0
        self._cols = 5
        self._current_folder = ""
        
        # Verbindungen
        self.btn_open.clicked.connect(self._open_folder)
        # Erste Layout-Berechnung
        self._recalculate_layout()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Bei Größenänderung: Auto-Fit oder feste Raster neu berechnen
        self._recalculate_layout()
        self._update_pagination()
        self._render_grid()

    def _on_grid_mode_changed(self, text: str):
        t = text.strip().lower()
        if t.startswith('2'):
            self._grid_mode = (2, 2)
        elif t.startswith('3'):
            self._grid_mode = (3, 3)
        elif t.startswith('4'):
            self._grid_mode = (4, 4)
        else:
            self._grid_mode = 'auto'
        self._recalculate_layout()
        self._update_pagination()
        self._render_grid()

    def _recalculate_layout(self):
        """Berechnet Raster (Zeilen/Spalten) und Thumb-Größe aus Modus + verfügbarer Fläche."""
        try:
            vp = self.area.viewport().size()
            avail_w = max(100, vp.width())
            avail_h = max(100, vp.height())
            m = self.grid.contentsMargins()
            spacing_h = self.grid.horizontalSpacing() or 0
            spacing_v = self.grid.verticalSpacing() or 0
            pad_w = (m.left() if hasattr(m, 'left') else 8) + (m.right() if hasattr(m, 'right') else 8)
            pad_h = (m.top() if hasattr(m, 'top') else 8) + (m.bottom() if hasattr(m, 'bottom') else 8)
            inner_w = max(50, avail_w - pad_w)
            inner_h = max(50, avail_h - pad_h)

            # Basisgröße aus Settings (Seitenverhältnis ~ 4:3)
            base_w = int(self.settings_manager.get('thumb_size', 160) or 160)
            base_h = int(base_w * 0.75)

            if self._grid_mode == 'auto':
                cols = max(1, inner_w // (base_w + spacing_h))
                rows = max(1, inner_h // (base_h + spacing_v))
            else:
                rows, cols = self._grid_mode

            # Zellen-Größe passend verteilen
            cell_w = max(32, int((inner_w - spacing_h * max(0, cols - 1)) / cols))
            cell_h = max(32, int((inner_h - spacing_v * max(0, rows - 1)) / rows))
            self._thumb_size = (cell_w, cell_h)
            self._rows = rows
            self._cols = cols
            self._items_per_page = max(1, rows * cols)
        except Exception:
            # Fallback auf frühere Defaults
            self._rows, self._cols = (4, 5)
            self._items_per_page = self._rows * self._cols
            self._thumb_size = (160, 120)

    def _create_evaluation_sidebar(self):
        """Erstellt das rechte Bewertungs-Panel"""
        self.evaluation_panel = QWidget()
        self.evaluation_panel.setMaximumWidth(245)  # 30% kleiner (350 * 0.7)
        layout = QVBoxLayout(self.evaluation_panel)
        
        # Aktuell ausgewähltes Bild
        self.current_image_label = QLabel("Kein Bild ausgewählt")
        self.current_image_label.setWordWrap(True)
        layout.addWidget(self.current_image_label)
        
        # Schnellbewertung
        quick_eval_group = QGroupBox("Schnellbewertung")
        quick_eval_layout = QVBoxLayout(quick_eval_group)
        
        # Bildart
        bildart_group = QGroupBox("Bildart")
        bildart_layout = QVBoxLayout(bildart_group)
        self.quick_image_type_chips = []
        image_types = self.settings_manager.get('image_types', []) or ["Wälzkörper", "Innenring", "Außenring", "Käfig", "Zahnrad"]
        
        for txt in image_types:
            b = ChipButton(txt)
            b.setCheckable(True)
            b.toggled.connect(lambda checked, button=b: self._on_quick_image_type_selected(button) if checked else None)
            self.quick_image_type_chips.append(b)
            bildart_layout.addWidget(b)
        
        quick_eval_layout.addWidget(bildart_group)
        
        # Schadenskategorien
        schaden_group = QGroupBox("Schadenskategorien")
        schaden_layout = QVBoxLayout(schaden_group)
        self.quick_chip_buttons = []
        damage_categories = self.settings_manager.get('damage_categories', []) or ["Visuell keine Defekte", "Kratzer", "Zykloidische Kratzer", "Stillstandsmarken", "Verschmierung", "Partikeldurchgang", "Überrollmarken", "Pittings", "Sonstige"]
        
        for txt in damage_categories:
            b = ChipButton(txt)
            if "Visuell" in txt and "keine" in txt and "Defekte" in txt:
                b.setStyleSheet("""
                    ChipButton:checked {
                        background-color: #4caf50;
                        color: white;
                        border: 2px solid #388e3c;
                        font-weight: bold;
                    }
                """)
            self.quick_chip_buttons.append(b)
            schaden_layout.addWidget(b)
        
        quick_eval_layout.addWidget(schaden_group)
        
        # Bewertung
        bewertung_group = QGroupBox("Bewertung")
        bewertung_layout = QVBoxLayout(bewertung_group)
        self.quick_quality_chips = []
        qualities = ["Low", "Medium", "High"]
        
        for txt in qualities:
            b = ChipButton(txt)
            b.setCheckable(True)
            b.toggled.connect(lambda checked, button=b: self._on_quick_quality_selected(button) if checked else None)
            self.quick_quality_chips.append(b)
            bewertung_layout.addWidget(b)
        
        # Medium standardmäßig ausgewählt
        if len(self.quick_quality_chips) > 1:
            self.quick_quality_chips[1].setChecked(True)
        
        quick_eval_layout.addWidget(bewertung_group)
        layout.addWidget(quick_eval_group)
        
        # Speichern Button
        self.save_eval_btn = QPushButton("Bewertung speichern")
        self.save_eval_btn.clicked.connect(self._save_quick_evaluation)
        layout.addWidget(self.save_eval_btn)
        
        layout.addStretch()

    def _open_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Ordner öffnen", "")
        if not folder:
            return
        self.set_folder(folder, emit=True)

    def set_folder(self, folder: str, emit: bool = False):
        exts = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tif', '.tiff'}
        files = [os.path.join(folder, f) for f in os.listdir(folder) if os.path.splitext(f)[1].lower() in exts]
        files.sort()
        self._paths = files
        self._current_folder = folder
        self._apply_filters()
        self._log.info("gallery_folder_open", extra={"event": "gallery_folder_open", "folder": folder, "count": len(files)})
        if emit:
            self.folderChanged.emit(folder)

    def _apply_filters(self):
        """Wendet alle aktiven Filter an"""
        if not self._paths:
            return
            
        filtered = self._paths.copy()
        
        # OCR-Filter
        ocr_filter = self.ocr_filter.currentText()
        if ocr_filter == "Mit OCR-Tag":
            filtered = [p for p in filtered if self._has_ocr_tag(p)]
        elif ocr_filter == "Ohne OCR-Tag":
            filtered = [p for p in filtered if not self._has_ocr_tag(p)]
        
        # Status-Filter
        status_filter = self.status_filter.currentText()
        if status_filter == "Bewertet":
            filtered = [p for p in filtered if self._is_evaluated(p)]
        elif status_filter == "Unbewertet":
            filtered = [p for p in filtered if not self._is_evaluated(p)]
        elif status_filter in ["High Quality", "Medium Quality", "Low Quality"]:
            quality = status_filter.split()[0]  # "High", "Medium", "Low"
            filtered = [p for p in filtered if self._has_quality(p, quality)]
        
        # Suchfilter
        search_text = self.search_field.text().lower()
        if search_text:
            filtered = [p for p in filtered if self._matches_search(p, search_text)]
        
        self._filtered_paths = filtered
        self._update_pagination()
        self._render_grid()

    def _has_ocr_tag(self, path: str) -> bool:
        """Prüft ob das Bild ein OCR-Tag hat"""
        try:
            info = get_ocr_info(path)
            return bool(info.get('tag'))
        except:
            return False

    def _is_evaluated(self, path: str) -> bool:
        """Prüft ob das Bild bewertet wurde"""
        try:
            eval_data = get_evaluation(path)
            return bool(eval_data.get('categories') or eval_data.get('quality') or eval_data.get('image_type'))
        except:
            return False

    def _has_quality(self, path: str, quality: str) -> bool:
        """Prüft ob das Bild die angegebene Qualität hat"""
        try:
            eval_data = get_evaluation(path)
            return eval_data.get('quality') == quality
        except:
            return False

    def _matches_search(self, path: str, search_text: str) -> bool:
        """Prüft ob das Bild dem Suchtext entspricht"""
        filename = os.path.basename(path).lower()
        if search_text in filename:
            return True
        try:
            info = get_ocr_info(path)
            tag = str(info.get('tag', '')).lower()
            return search_text in tag
        except:
            return False

    def _update_pagination(self):
        """Aktualisiert die Pagination"""
        total_items = len(self._filtered_paths)
        total_pages = max(1, (total_items + self._items_per_page - 1) // self._items_per_page)
        
        self.page_spin.setMaximum(total_pages)
        if self._current_page > total_pages:
            self._current_page = 1
            self.page_spin.setValue(1)

    def _change_page(self, page: int):
        """Wechselt zur angegebenen Seite"""
        self._current_page = page
        self._render_grid()

    def _on_quick_image_type_selected(self, selected_button):
        """Stellt sicher, dass nur ein Bildart-Chip ausgewählt ist"""
        for btn in self.quick_image_type_chips:
            if btn != selected_button and btn.isChecked():
                btn.setChecked(False)

    def _on_quick_quality_selected(self, selected_button):
        """Stellt sicher, dass nur ein Bewertungs-Chip ausgewählt ist"""
        for btn in self.quick_quality_chips:
            if btn != selected_button and btn.isChecked():
                btn.setChecked(False)

    def _save_quick_evaluation(self):
        """Speichert die Schnellbewertung für das aktuell ausgewählte Bild"""
        if not hasattr(self, '_current_selected_path') or not self._current_selected_path:
            return
        
        from utils_exif import set_evaluation
        
        # Bewertung sammeln
        categories = []
        for b in self.quick_chip_buttons:
            if b.isChecked():
                categories.append(b.text())
        
        image_type = None
        for b in self.quick_image_type_chips:
            if b.isChecked():
                image_type = b.text()
                break
        
        quality = None
        for b in self.quick_quality_chips:
            if b.isChecked():
                quality = b.text()
                break
        
        # Speichern
        set_evaluation(
            self._current_selected_path,
            categories=categories,
            quality=quality,
            image_type=image_type,
        )
        
        # Galerie aktualisieren
        self.refresh_item(self._current_selected_path)
        self._log.info("quick_evaluation_saved", extra={"path": self._current_selected_path})

    def _render_grid(self):
        # clear
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
        self._labels.clear()
        self._path_to_label = {}
        self._pending_idx = 0
        
        # Pagination: Nur die aktuellen Items anzeigen
        start_idx = (self._current_page - 1) * self._items_per_page
        end_idx = min(start_idx + self._items_per_page, len(self._filtered_paths))
        current_paths = self._filtered_paths[start_idx:end_idx]
        
        cols = max(1, self._cols or 5)
        w, h = self._thumb_size
        for idx, path in enumerate(current_paths):
            r, c = divmod(idx, cols)
            lbl = ClickableLabel(path)
            # Placeholder bis geladen
            lbl.setFixedSize(w, h)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setText("…")
            lbl.setToolTip(f"{os.path.basename(path)}\n(Doppelklick für Einzelbildansicht)")
            lbl.doubleClicked.connect(self._emit_and_autosave)
            self.grid.addWidget(lbl, r, c)
            self._labels.append(lbl)
            self._path_to_label[path] = lbl

        # Start incremental loader
        self._loader.start(10)  # alle 10ms ein Chunk


    def refresh_layout_from_settings(self):
        """Wendet ge�nderte Anzeige-/Thumbnail-Settings an (z. B. thumb_size)."""
        self._recalculate_layout()
        self._update_pagination()
        self._render_grid()

    def _load_chunk(self):
        if self._pending_idx >= len(self._labels):
            self._loader.stop()
            return
        chunk = 10
        w, h = self._thumb_size
        end = min(self._pending_idx + chunk, len(self._labels))
        for i in range(self._pending_idx, end):
            lbl = self._labels[i]
            path = lbl._path
            pix = self._cache.get(path)
            if pix is None:
                p = QPixmap(path)
                if not p.isNull():
                    pix = p.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self._cache[path] = pix
            if pix is not None:
                # Badge mit OCR-Tag (falls vorhanden)
                try:
                    info = get_ocr_info(path)
                except Exception:
                    info = {}
                # Erstelle Status-Icons
                final_pixmap = QPixmap(pix)
                painter = QPainter(final_pixmap)
                painter.setRenderHints(painter.renderHints() | QPainter.Antialiasing | QPainter.TextAntialiasing)
                
                # OCR-Badge (falls vorhanden)
                if info.get('tag'):
                    tag_text = str(info['tag'])
                    f = QFont(); f.setPointSize(self.settings_manager.get_gallery_tag_size())
                    painter.setFont(f)
                    fm = painter.fontMetrics()
                    text_width = fm.horizontalAdvance(tag_text)
                    text_height = fm.height()
                    
                    # Badge-Größe mit Padding
                    padding = 4
                    badge_width = text_width + 2 * padding
                    badge_height = text_height + 2 * padding
                    
                    # STATUS-ICONS hinzufügen
                    icon_size = 16
                    icon_spacing = 20
                    
                    # Position: oben in der Mitte
                    x_pos = (final_pixmap.width() - badge_width) / 2
                    y_pos = 5
                    
                    # Hintergrund-Kasten (weiß, halbtransparent)
                    opacity = self.settings_manager.get_tag_opacity()
                    painter.fillRect(int(x_pos), int(y_pos), int(badge_width), int(badge_height), 
                                   QColor(255, 255, 255, opacity))
                    painter.setPen(QColor(0, 0, 0, 100))
                    painter.drawRect(int(x_pos), int(y_pos), int(badge_width), int(badge_height))
                    
                    # Text (schwarz)
                    painter.setPen(QColor(0, 0, 0))
                    painter.drawText(int(x_pos + padding), int(y_pos + padding + text_height - fm.descent()), tag_text)
                
                # Status-Icons hinzufügen
                self._add_status_icons(painter, path, final_pixmap)
                
                painter.end()
                lbl.setPixmap(final_pixmap)
                
                # Tooltip mit Status-Informationen
                tooltip = f"{os.path.basename(path)}\n(Doppelklick für Einzelbildansicht)"
                if info.get('tag'):
                    tooltip += f"\nOCR: {info['tag']}{(' ('+str(round(info.get('confidence',0),2))+')') if 'confidence' in info else ''}"
                
                # Bewertungs-Status
                eval_data = get_evaluation(path)
                if eval_data.get('categories') or eval_data.get('quality') or eval_data.get('image_type'):
                    tooltip += f"\nBewertet: {eval_data.get('quality', 'N/A')}"
                else:
                    tooltip += "\nUnbewertet"
                
                lbl.setToolTip(tooltip)
                lbl.setText("")
        self._pending_idx = end

    def _add_status_icons(self, painter: QPainter, path: str, pixmap: QPixmap):
        """Fügt Status-Icons zu einem Thumbnail hinzu"""
        icon_size = 16
        margin = 5
        
        # Position: unten rechts
        x_start = pixmap.width() - margin - icon_size
        y_start = pixmap.height() - margin - icon_size
        
        # OCR-Status Icon (grün = hat OCR, rot = kein OCR)
        has_ocr = self._has_ocr_tag(path)
        ocr_color = QColor(0, 255, 0, 180) if has_ocr else QColor(255, 0, 0, 180)
        painter.fillRect(x_start, y_start, icon_size, icon_size, ocr_color)
        painter.setPen(QColor(0, 0, 0))
        painter.drawRect(x_start, y_start, icon_size, icon_size)
        
        # Bewertungs-Status Icon (blau = bewertet, grau = unbewertet)
        is_evaluated = self._is_evaluated(path)
        eval_color = QColor(0, 0, 255, 180) if is_evaluated else QColor(128, 128, 128, 180)
        painter.fillRect(x_start - icon_size - 2, y_start, icon_size, icon_size, eval_color)
        painter.setPen(QColor(0, 0, 0))
        painter.drawRect(x_start - icon_size - 2, y_start, icon_size, icon_size)

    def refresh_item(self, path: str):
        # Thumbnail neu zeichnen (inkl. OCR-Badge)
        try:
            lbl = self._path_to_label.get(path)
        except Exception:
            lbl = None
        if not lbl:
            return
        # Cache invalidieren und neu setzen
        try:
            if path in self._cache:
                del self._cache[path]
            w, h = self._thumb_size
            p = QPixmap(path)
            if not p.isNull():
                pix = p.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self._cache[path] = pix
                # Badge ggf. anbringen (wie im Loader)
                info = {}
                try:
                    info = get_ocr_info(path)
                except Exception:
                    pass
                if info.get('tag'):
                    q = QPixmap(pix)
                    painter = QPainter(q)
                    painter.setRenderHints(painter.renderHints() | QPainter.Antialiasing | QPainter.TextAntialiasing)
                    
                    # OCR-Badge oben in der Mitte
                    tag_text = str(info['tag'])
                    f = QFont(); f.setPointSize(self.settings_manager.get_gallery_tag_size())
                    painter.setFont(f)
                    fm = painter.fontMetrics()
                    text_width = fm.horizontalAdvance(tag_text)
                    text_height = fm.height()
                    
                    # Badge-Größe mit Padding
                    padding = 4
                    badge_width = text_width + 2 * padding
                    badge_height = text_height + 2 * padding
                    
                    # Position: oben in der Mitte
                    x_pos = (q.width() - badge_width) / 2
                    y_pos = 5
                    
                    # Hintergrund-Kasten (weiß, halbtransparent)
                    opacity = self.settings_manager.get_tag_opacity()
                    painter.fillRect(int(x_pos), int(y_pos), int(badge_width), int(badge_height), 
                                   QColor(255, 255, 255, opacity))
                    painter.setPen(QColor(0, 0, 0, 100))
                    painter.drawRect(int(x_pos), int(y_pos), int(badge_width), int(badge_height))
                    
                    # Text (schwarz)
                    painter.setPen(QColor(0, 0, 0))
                    painter.drawText(int(x_pos + padding), int(y_pos + padding + text_height - fm.descent()), tag_text)
                    
                    painter.end()
                    lbl.setPixmap(q)
                    lbl.setToolTip(f"{os.path.basename(path)}\nOCR: {info['tag']}{(' ('+str(round(info.get('confidence',0),2))+')') if 'confidence' in info else ''}")
                else:
                    lbl.setPixmap(pix)
                    lbl.setToolTip(os.path.basename(path))
        except Exception:
            pass

    def _emit_and_autosave(self, path: str):
        # Aktuell ausgewähltes Bild speichern für Schnellbewertung
        self._current_selected_path = path
        self.current_image_label.setText(f"Gewählt: {os.path.basename(path)}")
        
        # Bewertung aus EXIF laden und in Schnellbewertung anzeigen
        try:
            eval_data = get_evaluation(path)
            
            # Bildart laden
            img_type = eval_data.get('image_type')
            if img_type:
                for b in self.quick_image_type_chips:
                    b.setChecked(b.text() == img_type)
            
            # Schadenskategorien laden
            cats = set(eval_data.get('categories') or [])
            for b in self.quick_chip_buttons:
                b.setChecked(b.text() in cats)
            
            # Bewertung laden
            quality = eval_data.get('quality')
            if quality:
                for b in self.quick_quality_chips:
                    b.setChecked(b.text() == quality)
        except Exception:
            pass
        
        # Optionaler Auto-Save: frage den MainWindow-SingleView, ob er speichern soll
        try:
            # Elternhierarchie hochlaufen und SingleView suchen
            from .single_view import SingleView
            w = self.parent()
            while w and not isinstance(w, SingleView):
                w = w.parent()
            # Wenn gefunden, speichere vorher den aktuellen Zustand
            if isinstance(w, SingleView):
                try:
                    w._save_current_exif()
                except Exception:
                    pass
        except Exception:
            pass
        self.imageSelected.emit(path)

