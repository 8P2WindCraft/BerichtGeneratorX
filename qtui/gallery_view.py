# -*- coding: utf-8 -*-
from __future__ import annotations
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame,
    QPushButton, QFileDialog, QGridLayout, QComboBox, QLineEdit,
    QGroupBox, QCheckBox, QSpinBox, QTreeView
)
from PySide6.QtCore import Signal, Qt, QTimer, QEvent
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QStandardItemModel, QStandardItem, QPen, QBrush, QPainterPath
from utils_logging import get_logger
from utils_exif import get_ocr_info, get_evaluation, get_used_flag
from .settings_manager import get_settings_manager
from .evaluation_panel import EvaluationPanel
import os


class ClickableLabel(QLabel):
    clicked = Signal(str)
    doubleClicked = Signal(str)

    def __init__(self, path: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._path = path
        self._is_selected = False
        self.setCursor(Qt.PointingHandCursor)
        self._update_border_style()

    def _update_border_style(self):
        """Aktualisiert Border-Style basierend auf Auswahl"""
        if self._is_selected:
            self.setStyleSheet("""
                QLabel {
                    border: 3px solid #2196F3;
                    border-radius: 8px;
                    background-color: rgba(33, 150, 243, 0.1);
                }
            """)
        else:
            self.setStyleSheet("""
                QLabel {
                    border: 2px solid transparent;
                    border-radius: 8px;
                }
                QLabel:hover {
                    border-color: #2196F3;
                }
            """)
    
    def set_selected(self, selected: bool):
        """Setzt Auswahl-Status"""
        self._is_selected = selected
        self._update_border_style()

    def mousePressEvent(self, ev):
        # Einfacher Klick aktiviert Bild (für Bewertung)
        if ev.button() == Qt.LeftButton:
            self.clicked.emit(self._path)
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
    imageSelectedWithTabSwitch = Signal(str)  # Für Doppelklick mit Tab-Wechsel
    folderChanged = Signal(str)
    def __init__(self):
        super().__init__()
        self._log = get_logger('app', {"module": "qtui.gallery_view"})
        self._log.info("module_started", extra={"event": "module_started"})

        self._evaluation_panel: EvaluationPanel | None = None
        # Settings Manager
        self.settings_manager = get_settings_manager()

        # Hauptlayout
        main_layout = QVBoxLayout(self)
        
        # Galerie-Container
        gallery_widget = QWidget()
        gallery_layout = QVBoxLayout(gallery_widget)
        main_layout.addWidget(gallery_widget)

        # OCR-Tag Anzeige (über der Toolbar)
        ocr_info_layout = QHBoxLayout()
        
        self.ocr_tag_display = QLabel("—")
        self.ocr_tag_display.setStyleSheet("""
            QLabel {
                font-size: 12pt;
                font-weight: bold;
                color: #2196F3;
                padding: 4px 12px;
                background-color: rgba(33, 150, 243, 0.1);
                border: 2px solid #2196F3;
                border-radius: 6px;
            }
        """)
        ocr_info_layout.addWidget(self.ocr_tag_display)
        ocr_info_layout.addStretch()
        gallery_layout.addLayout(ocr_info_layout)

        # Toolbar mit Filter und Suchfunktionen
        toolbar = QHBoxLayout()
        gallery_layout.addLayout(toolbar)
        
        self.btn_open = QPushButton("Ordner öffnen…")
        self.btn_open.setToolTip("Kein Ordner ausgewählt")
        toolbar.addWidget(self.btn_open)
        
        # Ehemalige Filter werden versteckt; stattdessen Sortierung anbieten
        # (Objekte anlegen, damit übriger Code nicht bricht)
        self.ocr_filter = QComboBox(); self.ocr_filter.hide()
        self.status_filter = QComboBox(); self.status_filter.hide()
        self.search_field = QLineEdit(); self.search_field.hide()

        # Neue Sortierungsauswahl
        toolbar.addWidget(QLabel("Sortierung:"))
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["ABC", "OCR-Tag"])
        self.sort_combo.setCurrentText("OCR-Tag")  # Standard: OCR-Tag
        self.sort_combo.currentTextChanged.connect(self._apply_sort)
        toolbar.addWidget(self.sort_combo)
        toolbar.addStretch()
        
        # Toggle-Buttons für "Bild verwenden" und "Gene" mit Abstand nach oben
        from .widgets import ToggleSwitch
        toolbar.addSpacing(8)  # Zusätzlicher Abstand
        use_label = QLabel("Bild")
        use_label.setStyleSheet("font-weight: bold; margin-top: 5px;")
        toolbar.addWidget(use_label)
        self.use_toggle = ToggleSwitch()
        self.use_toggle.setChecked(False)
        self.use_toggle.toggled.connect(self._on_use_toggle)
        toolbar.addWidget(self.use_toggle)
        
        gene_label = QLabel("Gene")
        gene_label.setStyleSheet("font-weight: bold; margin-top: 5px;")
        toolbar.addWidget(gene_label)
        self.gene_toggle = ToggleSwitch(active_color="#FF9800")  # Orange für Gene
        self.gene_toggle.setChecked(False)
        self.gene_toggle.toggled.connect(self._on_gene_toggle)
        toolbar.addWidget(self.gene_toggle)


        # Layout-Auswahl (erweitert mit 2x3, 3x2, etc.)
        toolbar.addWidget(QLabel("Layout:"))
        self.grid_mode_combo = QComboBox()
        self.grid_mode_combo.addItems([
            "Auto-Fit", "2 x 2", "2 x 3", "2 x 4", 
            "3 x 2", "3 x 3", "3 x 4",
            "4 x 2", "4 x 3", "4 x 4",
            "5 x 3", "5 x 4"
        ])
        self.grid_mode_combo.currentTextChanged.connect(self._on_grid_mode_changed)
        toolbar.addWidget(self.grid_mode_combo)
        
        # Standard-Raster aus Einstellungen laden
        default_grid = self.settings_manager.get('gallery_grid_mode', 'Auto-Fit')
        idx = self.grid_mode_combo.findText(default_grid)
        if idx >= 0:
            self.grid_mode_combo.setCurrentIndex(idx)
        
        # Pagination mit Links/Rechts-Pfeilen
        self.btn_prev_page = QPushButton("◀")
        self.btn_prev_page.setFixedWidth(30)
        self.btn_prev_page.clicked.connect(self._prev_page)
        toolbar.addWidget(self.btn_prev_page)
        
        self.page_label = QLabel("Seite 1 von 1")
        self.page_label.setStyleSheet("font-weight: bold; padding: 0 8px;")
        self.page_label.setMinimumWidth(100)
        self.page_label.setAlignment(Qt.AlignCenter)
        toolbar.addWidget(self.page_label)
        
        self.btn_next_page = QPushButton("▶")
        self.btn_next_page.setFixedWidth(30)
        self.btn_next_page.clicked.connect(self._next_page)
        toolbar.addWidget(self.btn_next_page)
        
        # SpinBox für Kompatibilität behalten (versteckt)
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(1)
        self.page_spin.hide()
        
        # Kürzel-Filter entfernt (wird nur noch über TreeView gesteuert)
        # Objekte behalten für Kompatibilität, aber versteckt
        self.code_filter_combo = QComboBox()
        self.code_filter_combo.hide()

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
        self._debug_label = QLabel(self.area.viewport())
        self._debug_label.setStyleSheet("background-color: rgba(0,0,0,140); color: white;padding: 6px; border-radius: 6px; font-family: Consolas, monospace; font-size: 9pt;")
        self._debug_label.setVisible(False)

        # Resize-Handling für Auto-Layout
        self.area.viewport().installEventFilter(self)
        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self._handle_viewport_resize)
        self._thumb_size = (160, 120)
        self._paths = []
        self._filtered_paths = []
        self._current_selected_path = None
        self.sort_mode = "Dateiname (A-Z)"
        self._labels = []
        self._cache = {}
        self._path_to_label = {}
        self._pending_idx = 0
        self._loader = QTimer(self)
        self._loader.timeout.connect(self._load_chunk)
        self._current_page = 1
        self._items_per_page = 20
        self._grid_mode = 'auto'  # 'auto' oder (rows, cols)
        self._rows = 0
        self._cols = 5
        self._current_folder = ""
        self._code_filter = None  # Set[str] (uppercase) der gefilterten Kürzel oder None
        
        # Verbindungen
        self.btn_open.clicked.connect(self._open_folder)
        # Erste Layout-Berechnung
        self._recalculate_layout()
        self._update_debug_overlay()
        # Erste Sortierung anwenden
        self._apply_sort()
        # Tree initial befüllen
        self._rebuild_code_tree()
    # ---------------- Tree (Bereiche/Kürzel) ----------------
    def _create_code_tree(self):
        self.code_model = QStandardItemModel()
        self._section_items = []
        self._code_items = {}

    def _on_code_filter_changed(self, index: int):
        try:
            if index < 0 or not hasattr(self, 'code_filter_combo'):
                return
            data = self.code_filter_combo.itemData(index, Qt.UserRole)
            if data:
                self._code_filter = {str(data).upper()}
            else:
                self._code_filter = None
            self._apply_filters()
            self._refresh_code_tree_status()
        except Exception:
            pass

    def _clear_code_filter(self):
        try:
            self._code_filter = None
            if hasattr(self, 'code_filter_combo'):
                self.code_filter_combo.blockSignals(True)
                self.code_filter_combo.setCurrentIndex(0)
                self.code_filter_combo.blockSignals(False)
            self._apply_filters()
            self._refresh_code_tree_status()
        except Exception:
            pass
    
    def filter_by_tag(self, tag: str):
        """Filtert Galerie nach OCR-Tag"""
        try:
            if tag:
                tag_upper = str(tag).upper()
                self._code_filter = {tag_upper}
                
                # OCR-Tag-Anzeige aktualisieren
                if hasattr(self, 'ocr_tag_display'):
                    self.ocr_tag_display.setText(tag_upper)
            else:
                self._code_filter = None
                
                # OCR-Tag-Anzeige zurücksetzen
                if hasattr(self, 'ocr_tag_display'):
                    self.ocr_tag_display.setText("—")
            
            # ComboBox aktualisieren, damit Filter sichtbar bleibt
            if hasattr(self, 'code_filter_combo'):
                self.code_filter_combo.blockSignals(True)
                if tag:
                    # Finde das entsprechende Item in der ComboBox
                    idx = self.code_filter_combo.findData(tag_upper, Qt.UserRole)
                    if idx >= 0:
                        self.code_filter_combo.setCurrentIndex(idx)
                    else:
                        # Falls nicht gefunden, auf "Alle Kürzel" setzen
                        self.code_filter_combo.setCurrentIndex(0)
                else:
                    self.code_filter_combo.setCurrentIndex(0)
                self.code_filter_combo.blockSignals(False)
            
            # Filter anwenden
            self._apply_filters()
            self._refresh_code_tree_status()
            
            # Button sichtbar machen wenn gefiltert
            if hasattr(self, 'btn_reset_filter'):
                self.btn_reset_filter.setVisible(bool(self._code_filter))
        except Exception as e:
            self._log.error("filter_by_tag_failed", extra={"event": "filter_by_tag_failed", "error": str(e)})
    
    def _rebuild_code_tree(self):
        try:
            from .settings_manager import get_settings_manager
            sm = get_settings_manager()
            order = sm.get('section_order', []) or []
            titles_de = sm.get('section_titles_de', []) or []
            titles_en = sm.get('section_titles_en', []) or []
            mapping = sm.get('section_kurzel_map', {}) or {}
            lang = (sm.get('language', 'Deutsch') or 'Deutsch').lower()
            use_de = lang.startswith('de')

            self.code_model.clear()
            self._section_items = []
            self._code_items = {}

            for idx, sec in enumerate(order):
                title = titles_de[idx] if use_de and idx < len(titles_de) else (titles_en[idx] if idx < len(titles_en) else sec)
                sec_item = QStandardItem(title)
                f = sec_item.font(); f.setBold(True); sec_item.setFont(f)
                sec_item.setEditable(False)
                sec_item.setData(sec, Qt.UserRole + 1)
                self.code_model.appendRow(sec_item)
                self._section_items.append(sec_item)

                for code in mapping.get(sec, []) or []:
                    it = QStandardItem(code)
                    it.setEditable(False)
                    it.setData(code.upper(), Qt.UserRole + 1)
                    sec_item.appendRow(it)
                    self._code_items[code.upper()] = it

            self._rebuild_code_combo()
        except Exception:
            pass

    def _rebuild_code_combo(self):
        try:
            if not hasattr(self, 'code_filter_combo'):
                return
            self.code_filter_combo.blockSignals(True)
            # Aktuellen Filter aus _code_filter oder ComboBox holen
            current_from_combo = self.code_filter_combo.currentData(Qt.UserRole) if self.code_filter_combo.count() else None
            current_from_filter = None
            if hasattr(self, '_code_filter') and self._code_filter:
                # Nehme das erste Element aus dem Filter-Set
                current_from_filter = list(self._code_filter)[0] if len(self._code_filter) == 1 else None
            current = current_from_filter or current_from_combo
            self.code_filter_combo.clear()
            self.code_filter_combo.addItem("Alle Kürzel", userData=None)
            for section_item in self._section_items:
                section_name = section_item.text()
                section_data = section_item.data(Qt.UserRole + 1)
                children = [section_item.child(i) for i in range(section_item.rowCount())]
                if not children:
                    self.code_filter_combo.addItem(section_name, userData=section_data)
                else:
                    if section_name:
                        self.code_filter_combo.addItem(f"[{section_name}]", userData=section_data)
                    for child in children:
                        code = child.text()
                        self.code_filter_combo.addItem(code, userData=child.data(Qt.UserRole + 1))
            # Filter wiederherstellen
            if current:
                idx = self.code_filter_combo.findData(current, Qt.UserRole)
                if idx >= 0:
                    self.code_filter_combo.setCurrentIndex(idx)
                else:
                    # Falls nicht gefunden, Filter zurücksetzen
                    self._code_filter = None
                    self.code_filter_combo.setCurrentIndex(0)
            else:
                # Kein Filter gesetzt
                self.code_filter_combo.setCurrentIndex(0)
            self.code_filter_combo.blockSignals(False)
        except Exception:
            pass

    def _refresh_code_tree_status(self):
        try:
            status = self._compute_code_status()
            default_color = QColor(Qt.black)
            green = QColor(0, 150, 0)
            if hasattr(self, 'code_filter_combo'):
                for idx in range(1, self.code_filter_combo.count()):
                    code = self.code_filter_combo.itemData(idx, Qt.UserRole)
                    if not code or len(str(code)) == 0:
                        continue
                    ok = status.get(str(code).upper(), False)
                    color = green if ok else default_color
                    self.code_filter_combo.setItemData(idx, color, Qt.TextColorRole)
            for code_u, item in self._code_items.items():
                ok = status.get(code_u, False)
                item.setForeground(green if ok else default_color)
        except Exception:
            pass

    def _compute_code_status(self) -> dict:
        """Aggregiert pro Kürzel: grün nur, wenn ALLE Bilder mit diesem Kürzel bewertet sind."""
        stats = {}  # code -> [total, evaluated]
        paths = list(self._paths or [])
        for p in paths:
            try:
                info = get_ocr_info(p)
                tag = str(info.get('tag') or '').upper().strip()
                if not tag:
                    continue
                total, done = stats.get(tag, [0, 0])
                total += 1
                if self._is_evaluated(p):
                    done += 1
                stats[tag] = [total, done]
            except Exception:
                continue
        out = {}
        for code, (total, done) in stats.items():
            out[code] = (total > 0 and done == total)
        return out

    def _on_tree_clicked(self, index):
        try:
            if not index.isValid():
                return
            item = self.code_model.itemFromIndex(index)
            parent = item.parent()
            if parent is not None:
                code = (item.data(Qt.UserRole + 1) or item.text() or '').upper().strip()
                new_filter = {code} if code else None
                if self._code_filter == new_filter:
                    self._code_filter = None
                else:
                    self._code_filter = new_filter
            else:
                sec_key = item.data(Qt.UserRole + 1) or ''
                from .settings_manager import get_settings_manager
                sm = get_settings_manager()
                mapping = sm.get('section_kurzel_map', {}) or {}
                codes = [c.upper() for c in mapping.get(sec_key, []) or []]
                new_filter = set(codes) if codes else None
                if self._code_filter == new_filter:
                    self._code_filter = None
                else:
                    self._code_filter = new_filter
            self._apply_filters()
            self._refresh_code_tree_status()
        except Exception:
            pass
    def _reset_code_filter(self):
        """Setzt den Tree-Filter zurück und aktualisiert die Galerie."""
        try:
            self._code_filter = None
            if hasattr(self, 'code_filter_combo'):
                self.code_filter_combo.blockSignals(True)
                self.code_filter_combo.setCurrentIndex(0)
                self.code_filter_combo.blockSignals(False)
            self._apply_filters()
            self._refresh_code_tree_status()
            
            # Button verstecken wenn Filter zurückgesetzt
            if hasattr(self, 'btn_reset_filter'):
                self.btn_reset_filter.setVisible(False)
        except Exception:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Bei Größenänderung: Auto-Fit oder feste Raster neu berechnen
        self._recalculate_layout()
        self._update_pagination()
        self._render_grid()

    def _on_grid_mode_changed(self, text: str):
        t = text.strip()
        
        # Parse "X x Y" Format
        if 'x' in t.lower() and not t.lower().startswith('auto'):
            try:
                parts = t.lower().split('x')
                rows = int(parts[0].strip())
                cols = int(parts[1].strip())
                self._grid_mode = (rows, cols)
            except:
                self._grid_mode = 'auto'
        else:
            self._grid_mode = 'auto'
        
        # In Einstellungen speichern
        self.settings_manager.set('gallery_grid_mode', text)
        
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
        self._current_folder = folder or ""
        self._update_open_button_tooltip()
        self._current_selected_path = None
        if self._evaluation_panel:
            try:
                self._evaluation_panel.set_path(None)
            except Exception:
                pass
        self._apply_filters()
        # Baum aktualisieren
        self._rebuild_code_tree()
        self._log.info("gallery_folder_open", extra={"event": "gallery_folder_open", "folder": folder, "count": len(files)})
        if emit:
            self.folderChanged.emit(folder)

    def _apply_filters(self):
        """Filter: optional nach Kürzel(n) + Sortierung anwenden."""
        if not self._paths:
            return
        paths = list(self._paths)
        if getattr(self, "_code_filter", None):
            want = set(self._code_filter)
            def _m(p):
                try:
                    info = get_ocr_info(p)
                    return (str(info.get('tag') or '').upper().strip() in want)
                except Exception:
                    return False
            paths = [p for p in paths if _m(p)]
        self._filtered_paths = paths
        self._apply_sort()

    def _apply_sort(self):
        """Sortiert nach Dateiname (ABC) oder OCR-Tag (gruppiert)."""
        try:
            mode = self.sort_combo.currentText()
        except Exception:
            mode = "OCR-Tag"
        paths = list(self._filtered_paths or self._paths)
        
        if mode == "OCR-Tag":
            # Sortiere nach OCR-Tag (gruppiert)
            def key_func(p):
                try:
                    info = get_ocr_info(p)
                    tag = str(info.get('tag') or '')
                except Exception:
                    tag = ''
                return (tag == '', tag.upper())
            paths.sort(key=key_func)
            self._filtered_paths = paths
            # Gruppierter Modus: Tag-basierte Pagination
            self._update_tag_pagination()
        else:  # ABC
            # Sortiere nach Dateiname
            paths.sort(key=lambda p: os.path.basename(p).upper())
            self._filtered_paths = paths
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
        
        self._update_page_display()
    
    def _update_page_display(self):
        """Aktualisiert die Seitenanzeige und Button-Status"""
        max_page = self.page_spin.maximum()
        
        # Label aktualisieren
        if hasattr(self, 'page_label'):
            self.page_label.setText(f"Seite {self._current_page} von {max_page}")
        
        # Button-Status aktualisieren
        if hasattr(self, 'btn_prev_page'):
            self.btn_prev_page.setEnabled(self._current_page > 1)
        if hasattr(self, 'btn_next_page'):
            self.btn_next_page.setEnabled(self._current_page < max_page)
    
    def _update_tag_pagination(self):
        """Aktualisiert Pagination für Tag-gruppierte Ansicht"""
        # Gruppiere Bilder nach Tags
        from collections import OrderedDict
        tag_groups = OrderedDict()
        for path in self._filtered_paths:
            try:
                info = get_ocr_info(path)
                tag = str(info.get('tag') or '(Kein Tag)').strip()
            except Exception:
                tag = '(Kein Tag)'
            if tag not in tag_groups:
                tag_groups[tag] = []
            tag_groups[tag].append(path)
        
        # Speichere Tag-Gruppen
        self._tag_groups = list(tag_groups.values())
        total_groups = len(self._tag_groups)
        
        # Pagination: 1 Seite = 1 Tag-Gruppe
        self.page_spin.setMaximum(max(1, total_groups))
        if self._current_page > total_groups:
            self._current_page = 1
            self.page_spin.setValue(1)
        
        self._update_page_display()

    def _change_page(self, page: int):
        """Wechselt zur angegebenen Seite"""
        self._current_page = page
        self._render_grid()
    
    def _prev_page(self):
        """Wechselt zur vorherigen Seite"""
        if self._current_page > 1:
            self._current_page -= 1
            self._update_page_display()
            self._render_grid()
    
    def _next_page(self):
        """Wechselt zur nächsten Seite"""
        max_page = self.page_spin.maximum()
        if self._current_page < max_page:
            self._current_page += 1
            self._update_page_display()
            self._render_grid()

    def _update_open_button_tooltip(self):
        try:
            folder = getattr(self, "_current_folder", "") or ""
            tip = folder if folder else "Kein Ordner ausgewählt"
            if hasattr(self, "btn_open") and self.btn_open:
                self.btn_open.setToolTip(tip)
        except Exception:
            pass


    def _toggle_debug_overlay(self, enabled: bool):
        self._debug_label.setVisible(bool(enabled))
        if enabled:
            self._update_debug_overlay()


    def _update_ocr_tag_display(self, path: str):
        """Aktualisiert die OCR-Tag Anzeige basierend auf dem ausgewählten Bild"""
        try:
            if not path or not hasattr(self, 'ocr_tag_display'):
                return
            
            ocr_info = get_ocr_info(path)
            tag = str(ocr_info.get('tag', '')).strip() if ocr_info else ''
            
            if tag:
                self.ocr_tag_display.setText(tag)
            else:
                self.ocr_tag_display.setText("—")
        except Exception:
            if hasattr(self, 'ocr_tag_display'):
                self.ocr_tag_display.setText("—")
    
    def _on_use_toggle(self, checked: bool):
        """Handler für 'Bild verwenden' Toggle"""
        if not self._current_selected_path:
            return
        
        if self._evaluation_panel:
            try:
                self._evaluation_panel.set_use(checked)
                # Sofort Thumbnail aktualisieren um Grau-Filter zu entfernen/hinzufügen
                self.refresh_item(self._current_selected_path, emit_signal=False)
            except Exception:
                pass
        else:
            # Fallback ohne Panel
            try:
                from utils_exif import set_used_flag
                set_used_flag(self._current_selected_path, checked)
                self.refresh_item(self._current_selected_path, emit_signal=False)
            except Exception:
                pass
    
    def _on_gene_toggle(self, checked: bool):
        """Handler für 'Gene' Toggle"""
        if not self._current_selected_path:
            return
        
        if self._evaluation_panel:
            try:
                self._evaluation_panel.set_gene(checked)
            except Exception:
                pass
        else:
            # Fallback ohne Panel
            try:
                from utils_exif import set_gene_flag
                set_gene_flag(self._current_selected_path, checked)
            except Exception:
                pass
    
    def _update_toggles_for_current_image(self):
        """Aktualisiert Toggle-Status basierend auf aktuellem Bild"""
        if not self._current_selected_path:
            if hasattr(self, 'use_toggle'):
                self.use_toggle.blockSignals(True)
                self.use_toggle.setChecked(False)
                self.use_toggle.blockSignals(False)
            if hasattr(self, 'gene_toggle'):
                self.gene_toggle.blockSignals(True)
                self.gene_toggle.setChecked(False)
                self.gene_toggle.blockSignals(False)
            return
        
        try:
            # Nutze Panel-State wenn verfügbar (schneller als EXIF-Read)
            if self._evaluation_panel:
                state = self._evaluation_panel.get_state()
                use_flag = bool(state.get('use', False))
                gene_flag = bool(state.get('gene', False))
            else:
                # Fallback: EXIF lesen
                from utils_exif import get_used_flag, get_gene_flag
                use_flag = get_used_flag(self._current_selected_path)
                gene_flag = get_gene_flag(self._current_selected_path)
            
            if hasattr(self, 'use_toggle'):
                self.use_toggle.blockSignals(True)
                self.use_toggle.setChecked(use_flag)
                self.use_toggle.blockSignals(False)
            
            if hasattr(self, 'gene_toggle'):
                self.gene_toggle.blockSignals(True)
                self.gene_toggle.setChecked(gene_flag)
                self.gene_toggle.blockSignals(False)
        except Exception:
            pass
    
    def _on_image_clicked(self, path: str):
        """Wird bei Einfach-Klick aufgerufen - Auswahl und Bewertung laden"""
        # Alte Auswahl deselektieren
        if self._current_selected_path and self._current_selected_path in self._path_to_label:
            old_label = self._path_to_label[self._current_selected_path]
            if hasattr(old_label, 'set_selected'):
                old_label.set_selected(False)
        
        # Neue Auswahl setzen
        self._current_selected_path = path
        if path in self._path_to_label:
            new_label = self._path_to_label[path]
            if hasattr(new_label, 'set_selected'):
                new_label.set_selected(True)
        
        # OCR-Tag Anzeige aktualisieren
        self._update_ocr_tag_display(path)
        
        # Bewertung und Toggle-Buttons laden
        self._load_image_data(path)
    
    def _load_image_data(self, path: str):
        """Lädt Panel und Toggle-Daten im Hintergrund"""
        try:
            # Bewertungs-Panel aktualisieren
            if self._evaluation_panel:
                self._evaluation_panel.set_path(path)
                # Toggle-Buttons nach Panel-Load aktualisieren
                self._update_toggles_for_current_image()
            else:
                # Ohne Panel: Toggles aktualisieren
                self._update_toggles_for_current_image()
        except Exception:
            pass
    
    def highlight_current_image(self, path: str):
        """Markiert ein Bild in der Galerie (für Sync mit Single View)"""
        try:
            if not path:
                return

            # Vorherige Auswahl zurücksetzen
            if self._current_selected_path and self._current_selected_path in self._path_to_label:
                old_label = self._path_to_label[self._current_selected_path]
                if hasattr(old_label, 'set_selected'):
                    old_label.set_selected(False)

            self._current_selected_path = path

            # Prüfen ob Bild auf aktueller Seite ist, sonst Seite wechseln
            if path in self._filtered_paths:
                img_index = self._filtered_paths.index(path)
                needed_page = (img_index // self._items_per_page) + 1
                if needed_page != self._current_page:
                    # Seite wechseln ohne Neurendern zu triggern
                    self._current_page = needed_page
                    self.page_spin.blockSignals(True)
                    self.page_spin.setValue(needed_page)
                    self.page_spin.blockSignals(False)
                    # Seitenanzeige aktualisieren
                    self._update_page_display()
                    # Grid neu rendern für neue Seite
                    self._render_grid()

            # Neue Auswahl markieren, sofern vorhanden
            label = self._path_to_label.get(path)
            if label and hasattr(label, 'set_selected'):
                label.set_selected(True)
            
            # OCR-Tag Anzeige aktualisieren
            self._update_ocr_tag_display(path)
            
            # Toggle-Buttons aktualisieren
            self._update_toggles_for_current_image()

            # Bewertungspanel synchron halten, ohne Signalschleife auszulösen
            if self._evaluation_panel:
                try:
                    self._evaluation_panel.commit_pending()
                    self._evaluation_panel.set_path(path)
                except Exception:
                    pass
        except Exception:
            pass
    
    def _emit_and_autosave(self, path: str):
        """Wird bei Doppel-Klick aufgerufen - wechselt zu Einzelansicht"""
        # Speichere aktuelles Bild im Panel falls vorhanden
        if self._evaluation_panel:
            try:
                self._evaluation_panel.commit_pending()
            except AttributeError:
                try:
                    self._evaluation_panel._save_state()
                except Exception:
                    pass
        
        # Setze Auswahl und lade Panel-Daten für das neue Bild
        self._current_selected_path = path
        
        # Panel und Toggles laden
        self._load_image_data(path)
        
        # OCR-Tag aktualisieren
        self._update_ocr_tag_display(path)
        
        # Signal für Sync mit Single View emittieren
        self.imageSelected.emit(path)
        
        # Bei Doppelklick: Signal mit Tab-Wechsel emittieren
        self.imageSelectedWithTabSwitch.emit(path)

    def _update_debug_overlay(self):
        if not self._debug_label.isVisible():
            return
        try:
            vp = self.area.viewport().size()
            wv, hv = max(1, vp.width()), max(1, vp.height())
            tw, th = self._thumb_size
            mode_str = "auto" if self._grid_mode == "auto" else str(self._grid_mode)
            txt = (f"Grid: {self._rows} x {self._cols}\n"
                   f"Thumb: {tw} x {th}px\n"
                   f"Viewport: {wv} x {hv}px\n"
                   f"Items/Page: {self._items_per_page}  Page: {self._current_page}/{self.page_spin.maximum()}\n"
                   f"Mode: {mode_str}")
            self._debug_label.setText(txt)
            self._debug_label.adjustSize()
            x = max(0, self.area.viewport().width() - self._debug_label.width() - 8)
            y = max(0, self.area.viewport().height() - self._debug_label.height() - 8)
            self._debug_label.move(x, y)
        except Exception:
            pass

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
        
        # Prüfe ob wir im Tag-gruppierten Modus sind
        try:
            mode = self.sort_combo.currentText()
            is_tag_grouped = isinstance(mode, str) and "gruppiert" in mode.lower()
        except Exception:
            is_tag_grouped = False
        
        # Wähle Pfade basierend auf Modus
        if is_tag_grouped and hasattr(self, '_tag_groups') and self._tag_groups:
            # Zeige nur Bilder der aktuellen Tag-Gruppe
            group_idx = self._current_page - 1
            if 0 <= group_idx < len(self._tag_groups):
                current_paths = self._tag_groups[group_idx]
            else:
                current_paths = []
        else:
            # Normale Pagination
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
            lbl.setToolTip(os.path.basename(path))
            lbl.clicked.connect(self._on_image_clicked)  # Einfach-Klick für Auswahl
            lbl.doubleClicked.connect(self._emit_and_autosave)  # Doppel-Klick für Einzelansicht
            self.grid.addWidget(lbl, r, c)
            self._labels.append(lbl)
            self._path_to_label[path] = lbl

        # Start incremental loader
        self._loader.start(10)  # alle 10ms ein Chunk\n        self._update_debug_overlay()\n

    def refresh_layout_from_settings(self):
        """Wendet geanderte Anzeige-/Thumbnail-Settings an (z. B. thumb_size)."""
        self._cache.clear()
        self._recalculate_layout()
        self._update_pagination()
        self._render_grid()

    def eventFilter(self, obj, event):
        if obj is self.area.viewport() and event.type() == QEvent.Resize:
            self._resize_timer.start(80)
            return False
        return super().eventFilter(obj, event)

    def _handle_viewport_resize(self):
        try:
            prev_items_per_page = getattr(self, '_items_per_page', 0)
            self._recalculate_layout()
            if self._items_per_page != prev_items_per_page:
                self._update_pagination()
            self._render_grid()
        except Exception:
            pass

    def set_evaluation_panel(self, panel: EvaluationPanel | None):
        if self._evaluation_panel is panel:
            return
        if self._evaluation_panel:
            try:
                self._evaluation_panel.evaluationChanged.disconnect(self._on_panel_evaluation)
            except Exception:
                pass
        self._evaluation_panel = panel
        if panel:
            panel.evaluationChanged.connect(self._on_panel_evaluation)
            if getattr(self, '_current_selected_path', None):
                try:
                    panel.set_path(self._current_selected_path)
                except Exception:
                    pass

    def _on_panel_evaluation(self, path: str, state: dict):
        if path in getattr(self, '_path_to_label', {}):
            self.refresh_item(path, emit_signal=False)

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
            cache_key = (path, self._thumb_size)
            pix = self._cache.get(cache_key)
            if pix is None:
                p = QPixmap(path)
                if not p.isNull():
                    pix = p.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    self._cache[cache_key] = pix
            if pix is not None:
                try:
                    info = get_ocr_info(path)
                except Exception:
                    info = {}
                use_flag = False
                try:
                    use_flag = get_used_flag(path)
                except Exception:
                    pass

                final_pixmap = QPixmap(pix)
                painter = QPainter(final_pixmap)
                painter.setRenderHints(painter.renderHints() | QPainter.Antialiasing | QPainter.TextAntialiasing)

                if not use_flag:
                    painter.fillRect(final_pixmap.rect(), QColor(255, 255, 255, 140))

                if info.get('tag'):
                    code = str(info['tag']).strip()
                    lines = [code]

                    f = QFont(); f.setPointSize(self.settings_manager.get_gallery_tag_size())
                    painter.setFont(f)
                    fm = painter.fontMetrics()
                    text_width = max((fm.horizontalAdvance(s) for s in lines), default=0)
                    line_height = fm.height()

                    padding = 4
                    badge_width = text_width + 2 * padding
                    badge_height = line_height * len(lines) + 2 * padding

                    x_pos = (final_pixmap.width() - badge_width) / 2
                    y_pos = 5

                    opacity = self.settings_manager.get_tag_opacity()
                    painter.fillRect(int(x_pos), int(y_pos), int(badge_width), int(badge_height),
                                     QColor(255, 255, 255, opacity))
                    painter.setPen(QColor(0, 0, 0, 100))
                    painter.drawRect(int(x_pos), int(y_pos), int(badge_width), int(badge_height))

                    painter.setPen(QColor(0, 0, 0))
                    painter.drawText(int(x_pos + padding), int(y_pos + padding + line_height - fm.descent()), code)

                self._add_status_icons2(painter, path, final_pixmap, use_flag)

                painter.end()
                lbl.setPixmap(final_pixmap)

                tooltip_lines = [os.path.basename(path)]
                if info.get('tag'):
                    tooltip_lines.append(f"Tag: {info.get('tag')}")
                eval_data = {}
                try:
                    eval_data = get_evaluation(path)
                except Exception:
                    pass
                if eval_data.get('image_type'):
                    tooltip_lines.append(f"Bildart: {eval_data.get('image_type')}")
                if eval_data.get('quality'):
                    tooltip_lines.append(f"Qualität: {eval_data.get('quality')}")
                if eval_data.get('categories'):
                    tooltip_lines.append(f"Schäden: {', '.join(eval_data.get('categories'))}")
                tooltip_lines.append("Verwenden: Ja" if use_flag else "Verwenden: Nein")
                lbl.setToolTip("\n".join(tooltip_lines))
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

    def refresh_item(self, path: str, emit_signal: bool = False):
        try:
            lbl = self._path_to_label.get(path)
        except Exception:
            lbl = None
        if not lbl:
            return
        try:
            keys_to_del = [k for k in self._cache if k[0] == path]
            for key in keys_to_del:
                del self._cache[key]
            w, h = self._thumb_size
            p = QPixmap(path)
            if not p.isNull():
                self._cache[(path, self._thumb_size)] = p.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self._pending_idx = 0
                self._load_chunk()
        except Exception:
            pass

        if emit_signal:
            self.imageSelected.emit(path)

    # Neue, skalierende Badges (✓/X, Gene-?, Schadens-Chips, Typ-Icon)
    def _add_status_icons2(self, painter: QPainter, path: str, pixmap: QPixmap, used: bool):
        try:
            # Keine Symbole, wenn Bild nicht verwendet
            if not used:
                return

            w, h = pixmap.width(), pixmap.height()
            base = min(w, h)
            m = self._overlay_metrics(base)

            # Bewertung lesen
            try:
                eval_data = get_evaluation(path) or {}
            except Exception:
                eval_data = {}

            categories = [str(c).strip() for c in (eval_data.get('categories') or []) if str(c).strip()]
            quality = (eval_data.get('quality') or '').strip()
            gene_flag = bool(eval_data.get('gene'))
            image_type = (eval_data.get('image_type') or '').strip()

            # Logik: OK vs. Schaden
            no_defect = {"Visually no defects", "Visuell keine Defekte"}
            has_no_defect = any(c in no_defect for c in categories)
            other_damages = [c for c in categories if c and c not in no_defect]
            quality_damage = quality.lower() in {"damage", "beschädigt"}
            has_damage = bool(other_damages) or quality_damage

            if has_damage or has_no_defect:
                self._draw_main_status_badge(painter, ok=(has_no_defect and not has_damage), m=m)
            if gene_flag:
                self._draw_gene_badge(painter, m)
            if other_damages:
                self._draw_damage_chips(painter, other_damages, m, w, h)
            if image_type:
                self._draw_type_icon(painter, image_type, m, w)
        except Exception:
            pass

    # -------- Overlay-Helfer --------
    def _overlay_metrics(self, base: int) -> dict:
        def clamp(v, lo, hi):
            return max(lo, min(hi, int(round(v))))
        margin = clamp(base * 0.05, 3, 12)
        main_badge = clamp(base * 0.22, 14, 36)
        gene_badge = clamp(base * 0.16, 12, 28)
        type_icon = clamp(base * 0.15, 10, 25)  # 15-20% kleiner (war 0.18, 12-30)
        chip_h = clamp(base * 0.16, 12, 28)
        chip_gap = clamp(chip_h * 0.2, 2, 8)
        font_px = clamp(chip_h * 0.58, 8, 18)
        return {
            'margin': margin,
            'main_badge': main_badge,
            'gene_badge': gene_badge,
            'type_icon': type_icon,
            'chip_h': chip_h,
            'chip_gap': chip_gap,
            'chip_font_px': font_px,
        }

    def _draw_main_status_badge(self, painter: QPainter, ok: bool, m: dict):
        size = m['main_badge']
        r = size // 2
        x = m['margin'] + r
        y = painter.viewport().height() - m['margin'] - r
        painter.save()
        color = QColor(46, 204, 113, 230) if ok else QColor(231, 76, 60, 230)
        pen = QPen(QColor(255, 255, 255), max(1, size // 12))
        painter.setPen(pen)
        painter.setBrush(QBrush(color))
        painter.drawEllipse(int(x - r), int(y - r), int(size), int(size))
        painter.setPen(QPen(QColor(255, 255, 255), max(2, size // 8)))
        if ok:
            sx, sy = x - r * 0.5, y
            mx, my = x - r * 0.1, y + r * 0.35
            ex, ey = x + r * 0.5, y - r * 0.45
            painter.drawLine(int(sx), int(sy), int(mx), int(my))
            painter.drawLine(int(mx), int(my), int(ex), int(ey))
        else:
            off = r * 0.5
            painter.drawLine(int(x - off), int(y - off), int(x + off), int(y + off))
            painter.drawLine(int(x - off), int(y + off), int(x + off), int(y - off))
        painter.restore()

    def _draw_gene_badge(self, painter: QPainter, m: dict):
        size = m['gene_badge']
        r = size // 2
        x = m['margin'] + r
        # 15% weiter nach unten verschieben
        y = m['margin'] + r + int(r * 0.15)
        painter.save()
        color = QColor(241, 196, 15, 230)
        painter.setPen(QPen(QColor(255, 255, 255), max(1, size // 12)))
        painter.setBrush(QBrush(color))
        painter.drawEllipse(int(x - r), int(y - r), int(size), int(size))
        painter.setPen(QPen(QColor(80, 80, 80), max(2, size // 10)))
        cx, cy = x, y - r * 0.2
        painter.drawArc(int(cx - r * 0.6), int(cy - r * 0.6), int(r * 1.2), int(r * 1.2), 30 * 16, 240 * 16)
        painter.drawPoint(int(x), int(y + r * 0.45))
        painter.restore()

    def _draw_damage_chips(self, painter: QPainter, categories: list[str], m: dict, w: int, h: int):
        abbrevs = []
        for c in categories:
            ab = self._damage_abbrev_en(c)
            if ab:
                abbrevs.append(ab)
        max_show = 3
        shown = abbrevs[:max_show]
        rest = len(abbrevs) - len(shown)
        if rest > 0:
            shown.append(f"+{rest}")
        if not shown:
            return
        painter.save()
        f = QFont()
        f.setPixelSize(m['chip_font_px'])
        painter.setFont(f)
        fm = painter.fontMetrics()
        x_right = w - m['margin']
        y_bottom = h - m['margin']
        chip_h = m['chip_h']
        gap = m['chip_gap']
        for text in shown[::-1]:
            tw = fm.horizontalAdvance(text)
            pad_x = max(6, chip_h // 3)
            chip_w = tw + pad_x * 2
            x = x_right - chip_w
            y = y_bottom - chip_h
            painter.setBrush(QColor(30, 30, 30, 200))
            painter.setPen(QPen(QColor(255, 255, 255, 220), 1))
            radius = max(4, chip_h // 3)
            painter.drawRoundedRect(int(x), int(y), int(chip_w), int(chip_h), radius, radius)
            painter.setPen(QColor(255, 255, 255))
            tx = x + pad_x
            ty = y + (chip_h + fm.ascent() - fm.descent()) / 2 - 1
            painter.drawText(int(tx), int(ty), text)
            x_right = x - gap
        painter.restore()

    def _draw_type_icon(self, painter: QPainter, image_type: str, m: dict, w: int):
        t = (image_type or '').strip().lower()
        if t in {"gear", "zahnrad"}:
            kind = 'gear'
        elif t in {"rolling element", "wälzkörper", "waelzkoerper", "bowling", "ball"}:
            kind = 'bowling'
        elif t in {"inner ring", "innenring", "innering"}:
            kind = 'inner_ring'
        elif t in {"outer ring", "außenring", "aussenring"}:
            kind = 'outer_ring'
        elif t in {"cage", "käfig", "kaefig"}:
            kind = 'cage'
        else:
            kind = 'gear'
        size = m['type_icon']
        x = w - m['margin'] - size
        y = m['margin']
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        pen = QPen(QColor(255, 255, 255), max(1, size // 14))
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(230, 230, 230, 220)))
        if kind == 'gear':
            self._draw_icon_gear(painter, x, y, size)
        elif kind == 'bowling':
            self._draw_icon_bowling(painter, x, y, size)
        elif kind == 'inner_ring':
            self._draw_icon_ring(painter, x, y, size, inner_ratio=0.45)
        elif kind == 'outer_ring':
            self._draw_icon_ring(painter, x, y, size, inner_ratio=0.65)
        elif kind == 'cage':
            self._draw_icon_cage(painter, x, y, size)
        painter.restore()

    def _draw_icon_gear(self, painter: QPainter, x: int, y: int, size: int):
        painter.save()
        r = size / 2
        cx, cy = x + r, y + r
        outer = r
        inner = r * 0.65
        teeth = 8
        for i in range(teeth):
            angle = (i / teeth) * 360
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(angle)
            w = r * 0.18
            h = r * 0.28
            painter.drawRect(int(inner), int(-w / 2), int(h), int(w))
            painter.restore()
        painter.drawEllipse(int(cx - outer), int(cy - outer), int(size), int(size))
        painter.setBrush(QBrush(QColor(255, 255, 255, 255)))
        painter.drawEllipse(int(cx - inner), int(cy - inner), int(inner * 2), int(inner * 2))
        hole = r * 0.18
        painter.setBrush(QBrush(QColor(230, 230, 230, 230)))
        painter.drawEllipse(int(cx - hole), int(cy - hole), int(hole * 2), int(hole * 2))
        painter.restore()

    def _draw_icon_bowling(self, painter: QPainter, x: int, y: int, size: int):
        painter.save()
        r = size / 2
        cx, cy = x + r, y + r
        painter.drawEllipse(int(x), int(y), int(size), int(size))
        hole = r * 0.12
        off = r * 0.28
        for dx, dy in [(-off, -off * 0.7), (0, -off), (off, -off * 0.7)]:
            painter.drawEllipse(int(cx + dx - hole), int(cy + dy - hole), int(hole * 2), int(hole * 2))
        painter.restore()

    def _draw_icon_ring(self, painter: QPainter, x: int, y: int, size: int, inner_ratio: float = 0.55):
        painter.save()
        r = size / 2
        cx, cy = x + r, y + r
        painter.drawEllipse(int(x), int(y), int(size), int(size))
        inner = r * inner_ratio
        painter.setBrush(QBrush(QColor(255, 255, 255, 255)))
        painter.drawEllipse(int(cx - inner), int(cy - inner), int(inner * 2), int(inner * 2))
        painter.restore()

    def _draw_icon_cage(self, painter: QPainter, x: int, y: int, size: int):
        painter.save()
        radius = max(3, size // 6)
        painter.drawRoundedRect(int(x), int(y), int(size), int(size), radius, radius)
        step = max(3, size // 4)
        for i in range(1, 3):
            painter.drawLine(int(x + i * step), int(y + 2), int(x + i * step), int(y + size - 2))
        for j in range(1, 3):
            painter.drawLine(int(x + 2), int(y + j * step), int(x + size - 2), int(y + j * step))
        painter.restore()

    def _damage_abbrev_en(self, name: str) -> str:
        n = (name or '').strip()
        if not n:
            return ''
        mapping = {
            'Visually no defects': '',
            'Scratches': 'SCR',
            'Cycloid Scratches': 'CYC',
            'Standstill marks': 'SSM',
            'Smearing': 'SMR',
            'Particle passage': 'PP',
            'Overrolling Marks': 'ORM',
            'Pitting': 'PIT',
            'Others': 'OTH',
            'Visuell keine Defekte': '',
            'Kratzer': 'SCR',
            'Zykloidische Kratzer': 'CYC',
            'Stillstandsmarken': 'SSM',
            'Verschmierung': 'SMR',
            'Partikeldurchgang': 'PP',
            'Überrollmarken': 'ORM',
            'Ueberrollmarken': 'ORM',
            'Pittings': 'PIT',
            'Pittings (Pitting)': 'PIT',
            'Sonstige': 'OTH',
        }
        if n in mapping:
            return mapping[n]
        import re
        letters = re.findall(r"[A-Za-z0-9]+", n)
        if not letters:
            return ''
        if len(letters) == 1 and len(letters[0]) >= 3:
            return letters[0][:3].upper()
        return ''.join(w[0] for w in letters)[:3].upper()

    def keyPressEvent(self, event):
        """Verarbeitet Tastatur-Shortcuts für Bewertung"""
        # Nur aktiv wenn Bild ausgewählt ist
        if not self._current_selected_path or not self._evaluation_panel:
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
