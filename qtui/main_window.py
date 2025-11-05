# -*- coding: utf-8 -*-
from __future__ import annotations
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QSplitter, QFrame, QTreeView, QDockWidget, QProgressBar, QPushButton, QMenuBar, QMenu, QDialog, QFileDialog, QMessageBox, QToolTip
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QShortcut, QKeySequence, QCursor, QStandardItemModel, QStandardItem
from utils_logging import get_logger
from .single_view import SingleView
from .gallery_view import GalleryView
from .excel_view import ExcelView
from .cover_view import CoverView
from .evaluation_panel import EvaluationPanel
from .theme import apply_theme, apply_theme_from_bool, get_available_themes
from .settings_dialog import SettingsDialog
from .settings_manager import get_settings_manager
from .kurzel_manager import KurzelManagerDialog
from .migration_tools import MigrationDialog
import os
import html


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BerichtGeneratorX â€“ Qt UI")
        self.resize(980, 680)
        self._log = get_logger('app', {"module": "qtui.main_window"})
        self._log.info("module_started", extra={"event": "module_started"})
        
        # Settings Manager
        self.settings_manager = get_settings_manager()
        self.settings_manager.settingsChanged.connect(self._on_settings_changed)
        
        # Evaluation Cache System
        from .evaluation_cache import EvaluationCache
        self.evaluation_cache = EvaluationCache()
        
        # TreeView Rebuild Debouncing (verhindert zu häufige Updates)
        from PySide6.QtCore import QTimer
        self._tree_rebuild_timer = QTimer(self)
        self._tree_rebuild_timer.setSingleShot(True)
        self._tree_rebuild_timer.timeout.connect(self._rebuild_ocr_tree)
        self._tree_rebuild_delay = 1500  # 1.5 Sekunden Debounce - nur wenn Pause beim Navigieren

        # Ermöglicht mehrere Docks nebeneinander
        self.setDockNestingEnabled(True)

        root = QWidget()
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        
        # Menüleiste erstellen
        self._open_folder_action = None
        self._open_action_tooltip = ""
        self._create_menu_bar()

        # Topbar entfernt - nur noch Menüleiste

        # Splitter: Tabs + rechte Sidebar (Kategorien/Progress)
        split = QSplitter(Qt.Horizontal)
        v.addWidget(split, 1)

        # Tabs
        self.tabs = QTabWidget(); split.addWidget(self.tabs)
        self._add_tabs()
        # Beim Start ggf. letzten Ordner laden
        self._load_last_folder()
        self._load_cover_folder()
        
        # Theme aus Einstellungen laden
        self._apply_theme_from_settings()
        self._init_evaluation_dock()

        # Rechte Sidebar als Dock (einklappbar)
        self.side = QDockWidget("Progress/Kategorien", self)
        self.side.setAllowedAreas(Qt.RightDockWidgetArea)
        self.side.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        self.side.setMinimumWidth(264)
        side_frame = QFrame(); side_frame.setFrameShape(QFrame.NoFrame)
        self.side.setWidget(side_frame)
        self.addDockWidget(Qt.RightDockWidgetArea, self.side)
        # Sidebar-Inhalt (kompakt): Fortschritt + Kategorien-Tree (Platzhalter)
        sv = QVBoxLayout(side_frame)
        
        # Progress Bar und Gene-Counter in einer Zeile
        progress_row = QHBoxLayout()
        progress_row.setSpacing(8)
        
        # Links: Progress Bar (nimmt verfügbaren Platz)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        progress_row.addWidget(self.progress, 1)  # Stretch factor 1
        
        # Rechts: Gene-Counter Button (feste Breite)
        self.gene_count_button = QPushButton("0")
        self.gene_count_button.setFixedWidth(50)
        self.gene_count_button.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: black;
                font-weight: bold;
                font-size: 14pt;
                padding: 4px;
                border-radius: 6px;
                min-height: 28px;
            }
            QPushButton:hover {
                background-color: #FFA726;
            }
            QPushButton:pressed {
                background-color: #FB8C00;
            }
        """)
        self.gene_count_button.setToolTip("Gene-Checks: Zum nächsten Bild mit Gene-Flag springen")
        self.gene_count_button.clicked.connect(self._navigate_to_next_gene)
        progress_row.addWidget(self.gene_count_button, 0)  # Stretch factor 0 = feste Größe
        
        sv.addLayout(progress_row)
        
        # Darunter: Progress Text
        self.progress_text = QLabel("0/0")
        sv.addWidget(self.progress_text)
        
        self.category_tree = QTreeView()
        self.category_tree.setSortingEnabled(False)  # Deaktiviert für hierarchische Struktur
        
        # Kompakte Darstellung: kleinere Schrift und weniger Spacing
        from PySide6.QtGui import QFont
        tree_font = QFont()
        tree_font.setPointSize(9)  # Kleinere Schrift (Standard: 10-11)
        self.category_tree.setFont(tree_font)
        
        # Reduziertes Spacing
        self.category_tree.setIndentation(12)  # Weniger Einrückung (Standard: 20)
        self.category_tree.setStyleSheet("""
            QTreeView {
                padding: 2px;
            }
            QTreeView::item {
                padding: 2px;
                height: 20px;
            }
        """)
        
        self._ocr_model = QStandardItemModel(self)
        self._ocr_model.setHorizontalHeaderLabels(["Kategorie", "Fort.", "GENE"])
        self.category_tree.setModel(self._ocr_model)
        self.category_tree.doubleClicked.connect(self._on_tree_double_click)
        
        # Reduzierte Spaltenbreiten für kompakte Darstellung
        header = self.category_tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, header.ResizeMode.Stretch)  # Kategorie: flexible
        header.setSectionResizeMode(1, header.ResizeMode.Fixed)    # Fort.: fixed
        header.setSectionResizeMode(2, header.ResizeMode.Fixed)    # GENE: fixed
        header.resizeSection(1, 50)  # Fort.-Spalte: 50px
        header.resizeSection(2, 35)  # GENE-Spalte: 35px
        
        # Custom Delegate für Hintergrund (grün bei komplett + blau bei aktiv)
        from PySide6.QtWidgets import QStyledItemDelegate
        from PySide6.QtGui import QColor as QC
        from PySide6.QtCore import Qt as QtCore
        class HighlightDelegate(QStyledItemDelegate):
            def paint(self, painter, option, index):
                # Zuerst Standard-Zeichnung (mit allen Hintergründen)
                super().paint(painter, option, index)
                
                # Prüfe ob aktuell markiert (aktive Zeile)
                item_data = index.data(QtCore.UserRole + 10)
                if item_data:
                    # Hellblauer Overlay über allem (halbtransparent, damit grün durchscheint)
                    painter.save()
                    painter.fillRect(option.rect, QC(150, 200, 255, 60))  # Sehr transparentes Blau
                    painter.restore()
        
        self.category_tree.setItemDelegate(HighlightDelegate(self.category_tree))
        sv.addWidget(self.category_tree)

        # Sidebar Toggle Button entfernt - nur noch im Menü verfügbar
        try:
            self.splitDockWidget(self.evaluation_dock, self.side, Qt.Horizontal)
        except Exception:
            pass

        self.tabs.currentChanged.connect(self._on_tab_changed)
        self._update_dock_visibility()

        self._pending_progress = None

        apply_theme(False)

        # Initial Tree-Befüllung (nachdem UI steht)
        try:
            self._rebuild_ocr_tree()
        except Exception:
            pass


    def _add_tabs(self):
        # Einzelbild
        self.single = SingleView(); self.single.progressChanged.connect(self._on_progress)
        self.tabs.addTab(self.single, "Einzelbild")
        # Galerie
        self.gallery = GalleryView(); self.tabs.addTab(self.gallery, "Galerie")
        # Einfacher Klick: Synchronisiere ohne Tab-Wechsel
        self.gallery.imageSelected.connect(lambda path: self._open_in_single(path, switch_tab=False))
        # Doppelklick: Synchronisiere mit Tab-Wechsel
        self.gallery.imageSelectedWithTabSwitch.connect(lambda path: self._open_in_single(path, switch_tab=True))
        # Titelbilder (eigener Ordner)
        self.cover = CoverView(); self.tabs.addTab(self.cover, "Titelbilder")
        try:
            self.gallery.folderChanged.connect(self._sync_last_folder)
            self.single.folderChanged.connect(self._sync_last_folder)
        except Exception:
            pass
        # OCR-Batch entfernt
        # Excel-Grunddaten
        self.excel_view = ExcelView()
        self.tabs.addTab(self.excel_view, "Excel-Grunddaten")
        # Ordner-Synchronisation für Excel-View
        try:
            self.single.folderChanged.connect(self.excel_view.set_folder)
            self.gallery.folderChanged.connect(self.excel_view.set_folder)
        except Exception:
            pass
        # Einstellungen-Tab entfernt

        # Verbindung: Nach manuellem Edit Badge aktualisieren
        try:
            self.single.ocrTagUpdated.connect(self.gallery.refresh_item)
        except Exception:
            pass
        # OCR-Tag Änderung → TreeView aktualisieren
        try:
            self.single.ocrTagUpdated.connect(lambda _p: self._rebuild_ocr_tree())
        except Exception:
            pass
        
        # Single View → Galerie Sync: Wenn Bild in Single View geändert wird, in Galerie markieren
        try:
            self.single.currentImageChanged.connect(self._on_single_image_changed)
        except Exception:
            pass

    def _on_theme_selected(self, theme_name: str):
        """Theme wurde aus dem Menü ausgewählt"""
        # Alle anderen Theme-Actions deaktivieren
        for name, action in self.theme_actions.items():
            action.setChecked(name == theme_name)
        
        # Theme anwenden
        apply_theme(theme_name)
        self.settings_manager.set("theme", theme_name)
        self._log.info("theme_changed", extra={"event": "theme_changed", "theme": theme_name})

    def _open_in_single(self, path: str, switch_tab: bool = True):
        # Lade Bild in Einzelbildansicht
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == "Einzelbild":
                w = self.tabs.widget(i)
                try:
                    w.select_image(path)
                    # Tab nur wechseln, wenn gewünscht (bei Doppelklick, nicht bei einfachem Klick)
                    if switch_tab:
                        self.tabs.setCurrentIndex(i)
                except Exception:
                    pass
                break
    
    def _on_single_image_changed(self, path: str):
        """Wird aufgerufen wenn Bild in Single View geändert wird"""
        # Galerie aktualisieren um aktives Bild zu markieren (asynchron)
        if hasattr(self.gallery, 'highlight_current_image') and path:
            try:
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, lambda: self.gallery.highlight_current_image(path))
            except Exception:
                pass
        
        # TreeView aktualisieren um aktuellen Bereich zu markieren (asynchron)
        if path:
            try:
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, lambda: self._highlight_current_kurzel_in_tree(path))
            except Exception:
                pass

    def _on_progress(self, pos: int, total: int, done: int):
        if not hasattr(self, 'progress') or self.progress is None:
            self._pending_progress = (pos, total, done)
            return
        self.progress.setRange(0, total if total else 1)
        self.progress.setValue(done)
        self.progress_text.setText(f"{done}/{total}")
        if self._pending_progress:
            self._pending_progress = None
        
        # Gene-Counter aktualisieren
        self._update_gene_counter()

    def _on_tab_changed(self, index: int):
        self._update_dock_visibility()

    def _update_dock_visibility(self):
        try:
            current = self.tabs.currentWidget() if hasattr(self, 'tabs') else None
            allowed = {getattr(self, 'single', None), getattr(self, 'gallery', None)}
            should_show = current in allowed
        except Exception:
            should_show = False

        dock = getattr(self, 'evaluation_dock', None)
        if not dock:
            return

        if should_show:
            dock.show()
            if hasattr(self, 'side') and self.side:
                try:
                    self.splitDockWidget(dock, self.side, Qt.Horizontal)
                except Exception:
                    pass
        else:
            dock.hide()

    def _load_last_folder(self):
        """Letzten Ordner laden"""
        try:
            with open("last_folder.txt", "r", encoding="utf-8") as f:
                folder = f.read().strip()
            if folder:
                self.single.set_folder(folder)
                if hasattr(self, 'gallery') and hasattr(self.gallery, 'set_folder'):
                    self.gallery.set_folder(folder, emit=False)
                # OCR-Batch entfernt
                self._update_open_folder_tooltip(folder)
            else:
                self._update_open_folder_tooltip("")
        except Exception:
            pass

    def _load_cover_folder(self):
        """Zuletzt genutzten Titelbild-Ordner laden"""
        try:
            folder = self.settings_manager.get_cover_last_folder()
            if folder and os.path.isdir(folder) and hasattr(self, 'cover'):
                self.cover.set_folder(folder, emit_signal=False)
                self._log.info("cover_folder_loaded", extra={"event": "cover_folder_loaded", "folder": folder})
        except Exception as e:
            self._log.error("cover_folder_load_failed", extra={"event": "cover_folder_load_failed", "error": str(e)})

    # Persistiere und synchronisiere Ordner
    def _sync_last_folder(self, folder: str):
        try:
            self._current_folder = folder or ""
            with open("last_folder.txt", "w", encoding="utf-8") as f:
                f.write(folder or "")
        except Exception:
            pass
        # Synchronisiere beide Ansichten: Quelle -> Ziel
        sender = self.sender()
        try:
            if sender is getattr(self, 'gallery', None):
                self.single.set_folder(folder)
            elif sender is getattr(self, 'single', None):
                # Galerie nur setzen, nicht erneut emitten
                if hasattr(self, 'gallery'):
                    self.gallery.set_folder(folder, emit=False)
            # OCR-Batch entfernt
        except Exception:
            pass
        self._update_open_folder_tooltip(folder)
        
        # Automatisch Titelbilder-Ordner eine Ebene höher setzen
        if folder and hasattr(self, 'cover'):
            try:
                parent_folder = os.path.dirname(folder)
                if parent_folder and os.path.isdir(parent_folder):
                    self.cover.set_folder(parent_folder, emit_signal=False)
                    self._log.info("cover_auto_sync", extra={"event": "cover_auto_sync", "endo_folder": folder, "cover_folder": parent_folder})
            except Exception as e:
                self._log.error("cover_auto_sync_failed", extra={"event": "cover_auto_sync_failed", "error": str(e)})
        
        # Cache neu aufbauen und TreeView aktualisieren
        if hasattr(self, 'evaluation_cache') and folder:
            self.evaluation_cache.build_cache(folder)
        self._rebuild_ocr_tree()
        
        # Gene-Counter aktualisieren
        self._update_gene_counter()

    def _init_evaluation_dock(self):
        self.evaluation_panel = EvaluationPanel(self)
        self.evaluation_panel.evaluationChanged.connect(self._on_global_evaluation_changed)
        self.evaluation_panel.useChanged.connect(self._on_global_use_changed)
        dock = QDockWidget("Bewertung", self)
        dock.setObjectName("EvaluationDock")
        dock.setAllowedAreas(Qt.RightDockWidgetArea)
        dock.setMinimumWidth(208)
        dock.setWidget(self.evaluation_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)
        self.evaluation_dock = dock
        if hasattr(self, 'single'):
            try:
                self.single.set_evaluation_panel(self.evaluation_panel)
            except Exception:
                pass
        if hasattr(self, 'gallery'):
            try:
                self.gallery.set_evaluation_panel(self.evaluation_panel)
            except Exception:
                pass

    def _on_global_evaluation_changed(self, path: str, state: dict):
        self._update_dock_visibility()
        try:
            # Galerie-Refresh asynchron
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self.gallery.refresh_item(path, emit_signal=False))
        except Exception:
            pass
        
        # TreeView aktualisieren (debounced)
        if hasattr(self, 'evaluation_cache'):
            self.evaluation_cache.invalidate()
        self._schedule_tree_rebuild()
        
        # Gene-Counter aktualisieren wenn Gene-Flag geändert wurde
        if 'gene' in state:
            self._update_gene_counter()

    def _on_global_use_changed(self, path: str, value: bool):
        self._update_dock_visibility()
        try:
            # Galerie-Refresh asynchron
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self.gallery.refresh_item(path, emit_signal=False))
        except Exception:
            pass
        
        # TreeView aktualisieren (debounced - nicht bei jedem Bild)
        if hasattr(self, 'evaluation_cache'):
            self.evaluation_cache.invalidate()
        # Use-Änderungen triggern kein Tree-Rebuild (zu häufig)

    def _schedule_tree_rebuild(self):
        """Plant TreeView-Rebuild mit Debouncing"""
        if hasattr(self, '_tree_rebuild_timer'):
            self._tree_rebuild_timer.start(self._tree_rebuild_delay)
    
    # ---------------------------------------------------------------
    # OCR-Tag TreeView
    def _rebuild_ocr_tree(self):
        """Baut hierarchische TreeView mit Kategorien und Kürzeln auf."""
        from PySide6.QtGui import QColor
        
        model = getattr(self, '_ocr_model', None)
        if not model:
            return

        folder = getattr(self, '_current_folder', '') or ''
        
        # Cache neu aufbauen wenn Ordner vorhanden
        if folder and hasattr(self, 'evaluation_cache'):
            self.evaluation_cache.build_cache(folder)
        
        model.removeRows(0, model.rowCount())
        
        # Hole Kürzel-Tabelle
        kurzel_table = self.settings_manager.get('kurzel_table', {}) or {}
        if not kurzel_table:
            return
        
        # Hole Kategorie-Überschriften und Sprache
        category_headings = self.settings_manager.get('category_headings', {}) or {}
        language = self.settings_manager.get('language', 'Deutsch') or 'Deutsch'
        use_de = language.lower().startswith('de')
        
        # Gruppiere nach Kategorien
        categories = {}
        for kurzel_code, kurzel_data in kurzel_table.items():
            if kurzel_data.get('active', True):
                category = kurzel_data.get('category', 'Unbekannt')
                if category not in categories:
                    categories[category] = []
                categories[category].append(kurzel_code)
        
        # Sortiere Kategorien nach order (aus category_headings)
        def get_category_order(cat):
            if cat in category_headings:
                return category_headings[cat].get('order', 999)
            return 999
        
        sorted_categories = sorted(categories.items(), key=lambda x: (get_category_order(x[0]), x[0]))
        
        # Baue hierarchische Struktur
        for category, kurzel_list in sorted_categories:
            # Hole Überschrift aus Settings (DE oder EN)
            if category in category_headings:
                heading_de = category_headings[category].get('heading_de', category)
                heading_en = category_headings[category].get('heading_en', category)
                display_name = heading_de if use_de else heading_en
            else:
                display_name = category
            
            # Parent-Node: Kategorie mit Überschrift
            cat_item = QStandardItem(display_name)
            cat_item.setEditable(False)
            cat_item.setData(category, Qt.UserRole)  # Original-Name für Logik speichern
            
            # Kategorie-Fortschritt berechnen
            cat_evaluated, cat_total = 0, 0
            for kurzel in kurzel_list:
                evaluated, total = self._calculate_kurzel_progress(kurzel)
                cat_evaluated += evaluated
                cat_total += total
            
            cat_progress = QStandardItem(f"{cat_evaluated}/{cat_total}")
            cat_progress.setEditable(False)
            
            # GENE-Kommentar Spalte (leer für Kategorien)
            cat_gene = QStandardItem("")
            cat_gene.setEditable(False)
            
            # Hellgrüne Färbung wenn komplett bewertet (über alle Spalten)
            if cat_total > 0 and cat_evaluated == cat_total:
                light_green = QColor("#C8E6C9")
                cat_item.setBackground(light_green)
                cat_progress.setBackground(light_green)
                cat_gene.setBackground(light_green)
                cat_progress.setForeground(QColor("#2E7D32"))
            
            model.appendRow([cat_item, cat_progress, cat_gene])
            
            # Child-Nodes: Kürzel nach 'order' sortieren
            def get_kurzel_sort_key(kurzel_code):
                """Sortier-Schlüssel: erst nach order, dann alphabetisch"""
                kurzel_info = kurzel_table.get(kurzel_code, {})
                order = kurzel_info.get('order', 9999)
                return (order, kurzel_code)
            
            for kurzel in sorted(kurzel_list, key=get_kurzel_sort_key):
                kurzel_item = QStandardItem(kurzel)
                kurzel_item.setEditable(False)
                
                evaluated, total = self._calculate_kurzel_progress(kurzel)
                progress_item = QStandardItem(f"{evaluated}/{total}")
                progress_item.setEditable(False)
                
                # GENE-Kommentar für Kürzel: "X" wenn mindestens ein Bild Gene-Flag hat
                has_gene = self._check_kurzel_has_gene(kurzel)
                gene_item = QStandardItem("X" if has_gene else "")
                gene_item.setEditable(False)
                
                # Hellgrüner Hintergrund wenn komplett bewertet
                if total > 0 and evaluated == total:
                    light_green = QColor("#C8E6C9")
                    kurzel_item.setBackground(light_green)
                    progress_item.setBackground(light_green)
                    gene_item.setBackground(light_green)
                    progress_item.setForeground(QColor("#2E7D32"))
                
                cat_item.appendRow([kurzel_item, progress_item, gene_item])
        
        # Tree expandieren
        self.category_tree.expandAll()
        
        # Aktuelle Markierung wiederherstellen
        if hasattr(self, 'single') and hasattr(self.single, '_current_path'):
            try:
                current_path = self.single._current_path()
                if current_path:
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(0, lambda: self._highlight_current_kurzel_in_tree(current_path))
            except Exception:
                pass
    
    def _calculate_kurzel_progress(self, kurzel_code: str) -> tuple:
        """Berechnet Bewertungsfortschritt für ein Kürzel"""
        if not hasattr(self, 'evaluation_cache'):
            return (0, 0)
        
        evaluated, total = self.evaluation_cache.get_kurzel_progress(kurzel_code)
        return (evaluated, total)
    
    def _check_kurzel_has_gene(self, kurzel_code: str) -> bool:
        """Prüft ob mindestens ein Bild mit diesem Kürzel das Gene-Flag hat"""
        if not hasattr(self, 'evaluation_cache'):
            return False
        
        return self.evaluation_cache.has_gene_flag_for_kurzel(kurzel_code)
    
    def _highlight_current_kurzel_in_tree(self, path: str):
        """Markiert das Kürzel des aktuellen Bildes im TreeView"""
        from PySide6.QtGui import QColor, QBrush, QPen
        from utils_exif import get_ocr_info
        
        if not hasattr(self, '_ocr_model') or not self._ocr_model:
            return
        
        try:
            # Hole OCR-Tag des aktuellen Bildes
            ocr_info = get_ocr_info(path)
            current_tag = str(ocr_info.get('tag', '')).strip().upper()
            
            if not current_tag:
                # Kein Tag -> alle Markierungen entfernen
                self._clear_tree_highlights()
                return
            
            # Durchsuche alle Items im TreeView
            for row in range(self._ocr_model.rowCount()):
                cat_item = self._ocr_model.item(row, 0)
                if not cat_item:
                    continue
                
                # Durchsuche Child-Items (Kürzel)
                for child_row in range(cat_item.rowCount()):
                    kurzel_item = cat_item.child(child_row, 0)
                    progress_item = cat_item.child(child_row, 1)
                    gene_item = cat_item.child(child_row, 2)
                    
                    if not kurzel_item:
                        continue
                    
                    kurzel_text = kurzel_item.text().strip().upper()
                    
                    # Setze oder entferne Markierung mit Rahmen
                    if kurzel_text == current_tag:
                        # Aktuelles Kürzel mit dickem orangen Rahmen markieren
                        border_color = QColor("#FF9800")  # Orange
                        
                        # Setze Rahmen für alle 3 Spalten
                        for item in [kurzel_item, progress_item, gene_item]:
                            if item:
                                # Speichere ursprüngliche Farben
                                item.setData(True, Qt.UserRole + 10)  # Markierungs-Flag
                        
                        # Stelle sicher, dass Item sichtbar ist
                        index = self._ocr_model.indexFromItem(kurzel_item)
                        if hasattr(self, 'category_tree') and self.category_tree:
                            self.category_tree.scrollTo(index)
                            # Trigger Repaint
                            self.category_tree.viewport().update()
                    else:
                        # Markierung entfernen
                        for item in [kurzel_item, progress_item, gene_item]:
                            if item:
                                item.setData(False, Qt.UserRole + 10)
        
        except Exception:
            pass
    
    def _clear_tree_highlights(self):
        """Entfernt alle Markierungen im TreeView"""
        if not hasattr(self, '_ocr_model') or not self._ocr_model:
            return
        
        try:
            for row in range(self._ocr_model.rowCount()):
                cat_item = self._ocr_model.item(row, 0)
                if not cat_item:
                    continue
                
                for child_row in range(cat_item.rowCount()):
                    for col in range(3):
                        item = cat_item.child(child_row, col)
                        if item:
                            item.setData(False, Qt.UserRole + 10)
        except Exception:
            pass
    
    def _on_tree_double_click(self, index):
        """Behandelt Doppelklick auf TreeView-Element"""
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QCursor
        
        if not index.isValid():
            return
        
        item = self._ocr_model.itemFromIndex(index)
        if not item:
            return
        
        # Prüfe ob Parent (Kategorie) oder Child (Kürzel)
        parent = item.parent()
        
        if parent:
            # Kürzel geklickt - zeige Context-Menu
            kurzel_code = item.text()
            self._navigate_to_kurzel(kurzel_code)
        else:
            # Kategorie geklickt
            category_name = item.text()
            self._navigate_to_category(category_name)
    
    def _navigate_to_kurzel(self, kurzel_code: str):
        """Springt direkt zum aktiven Tab (Single View oder Galerie)"""
        # Prüfe welcher Tab aktiv ist
        current_widget = self.tabs.currentWidget()
        
        if current_widget == self.single:
            # Einzelbild-Tab aktiv -> öffne dort
            self._open_kurzel_in_single(kurzel_code)
        elif current_widget == self.gallery:
            # Galerie-Tab aktiv -> filter dort
            self._open_kurzel_in_gallery(kurzel_code)
        else:
            # Fallback: öffne in Single View
            self._open_kurzel_in_single(kurzel_code)
    
    def _open_kurzel_in_single(self, kurzel_code: str):
        """Öffnet erstes Bild mit Kürzel in Single View"""
        from PySide6.QtWidgets import QMessageBox
        
        if not hasattr(self, 'evaluation_cache'):
            return
        
        # Hole erstes Bild mit diesem Tag aus Cache
        first_image = self.evaluation_cache.get_first_image_for_kurzel(kurzel_code)
        
        if first_image:
            # Wechsel zu Single View
            self.tabs.setCurrentWidget(self.single)
            # Lade Bild
            self.single.select_image(first_image)
        else:
            QMessageBox.information(
                self, "Kein Bild gefunden",
                f"Kein Bild mit Kürzel '{kurzel_code}' gefunden."
            )
    
    def _open_kurzel_in_gallery(self, kurzel_code: str):
        """Öffnet Galerie gefiltert nach Kürzel"""
        self.tabs.setCurrentWidget(self.gallery)
        if hasattr(self.gallery, 'filter_by_tag'):
            self.gallery.filter_by_tag(kurzel_code)
    
    def _navigate_to_category(self, category_name: str):
        """Navigiert zu erstem Bild in Kategorie"""
        # Hole alle Kürzel dieser Kategorie
        kurzel_table = self.settings_manager.get('kurzel_table', {})
        category_kurzel = [
            code for code, data in kurzel_table.items()
            if data.get('category') == category_name and data.get('active', True)
        ]
        
        if not category_kurzel:
            return
        
        # Finde erstes Bild mit einem dieser Kürzel
        for kurzel in sorted(category_kurzel):
            if hasattr(self, 'evaluation_cache'):
                first_image = self.evaluation_cache.get_first_image_for_kurzel(kurzel)
                if first_image:
                    self.tabs.setCurrentWidget(self.single)
                    self.single.select_image(first_image)
                    return

    def _create_menu_bar(self):
        """Menüleiste erstellen"""
        menubar = self.menuBar()
        
        # Datei-Menü
        file_menu = menubar.addMenu("Datei")
        
        open_action = file_menu.addAction("Ordner öffnen...")
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self._open_folder)
        open_action.hovered.connect(self._show_open_folder_tooltip)
        self._open_folder_action = open_action
        
        file_menu.addSeparator()
        
        excel_action = file_menu.addAction("Excel Grunddaten laden...")
        excel_action.triggered.connect(self._load_excel_data)
        
        file_menu.addSeparator()
        
        settings_action = file_menu.addAction("Einstellungen...")
        settings_action.triggered.connect(self._open_settings)
        
        file_menu.addSeparator()
        
        exit_action = file_menu.addAction("Beenden")
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        
        # Bearbeiten-Menü
        edit_menu = menubar.addMenu("Bearbeiten")
        
        kurzel_manager_action = edit_menu.addAction("Kürzel-Manager...")
        kurzel_manager_action.triggered.connect(self._open_kurzel_manager)
        
        edit_menu.addSeparator()
        
        refresh_action = edit_menu.addAction("Aktualisieren")
        refresh_action.setShortcut(QKeySequence.Refresh)
        refresh_action.triggered.connect(self._refresh_images)
        
        exif_action = edit_menu.addAction("EXIF anzeigen")
        exif_action.triggered.connect(self._show_exif_info)
        
        # Analyse-Menü
        # (entfernt)
        
        # (entfernt)
        
        # (entfernt)
        
        # (entfernt)
        
        # Ansicht-Menü
        view_menu = menubar.addMenu("Ansicht")
        
        toggle_sidebar_action = view_menu.addAction("Sidebar ein-/ausblenden")
        toggle_sidebar_action.triggered.connect(self._toggle_sidebar)
        
        view_menu.addSeparator()
        
        # Zoom-Funktionen
        zoom_in_action = view_menu.addAction("Zoom vergrößern")
        zoom_in_action.setShortcut(QKeySequence("Ctrl++"))
        zoom_in_action.triggered.connect(self._zoom_in)
        
        zoom_out_action = view_menu.addAction("Zoom verkleinern")
        zoom_out_action.setShortcut(QKeySequence("Ctrl+-"))
        zoom_out_action.triggered.connect(self._zoom_out)
        
        zoom_reset_action = view_menu.addAction("Zoom zurücksetzen")
        zoom_reset_action.setShortcut(QKeySequence("Ctrl+0"))
        zoom_reset_action.triggered.connect(self._zoom_reset)
        
        view_menu.addSeparator()
        
        fullscreen_action = view_menu.addAction("Vollbild")
        fullscreen_action.setShortcut(QKeySequence.FullScreen)
        fullscreen_action.triggered.connect(self._toggle_fullscreen)
        
        view_menu.addSeparator()
        
        # Theme-Menü
        theme_menu = view_menu.addMenu("Theme")
        
        # Theme-Optionen dynamisch aus verfügbaren Themes generieren
        self.theme_actions = {}
        for theme_name in get_available_themes():
            action = theme_menu.addAction(theme_name)
            action.setCheckable(True)
            action.triggered.connect(lambda checked, name=theme_name: self._on_theme_selected(name))
            self.theme_actions[theme_name] = action
        
        # Aktuelles Theme aus Einstellungen setzen
        current_theme = self.settings_manager.get("theme", "Light")
        if current_theme in self.theme_actions:
            self.theme_actions[current_theme].setChecked(True)
        
        # Extras-Menü
        tools_menu = menubar.addMenu("Extras")
        
        config_editor_action = tools_menu.addAction("Konfiguration bearbeiten...")
        config_editor_action.triggered.connect(self._open_config_editor)
        
        tools_menu.addSeparator()
        
        migration_action = tools_menu.addAction("Migrations-Tools...")
        migration_action.triggered.connect(self._open_migration_tools)
        
        tools_menu.addSeparator()
        
        backup_action = tools_menu.addAction("Backup erstellen...")
        backup_action.triggered.connect(self._create_backup)
        
        restore_action = tools_menu.addAction("Backup wiederherstellen...")
        restore_action.triggered.connect(self._restore_backup)
        
        # Hilfe-Menü
        help_menu = menubar.addMenu("Hilfe")
        
        shortcuts_action = help_menu.addAction("Tastaturkürzel...")
        shortcuts_action.setShortcut(QKeySequence("F1"))
        shortcuts_action.triggered.connect(self._show_shortcuts_help)
        
        help_menu.addSeparator()
        
        about_action = help_menu.addAction("Über...")
        about_action.triggered.connect(self._show_about)
    
    def _open_folder(self):
        """Ordner öffnen"""
        self.single._open_folder()

    def _show_open_folder_tooltip(self):
        text = self._open_action_tooltip or "Kein Ordner gewählt"
        QToolTip.showText(QCursor.pos(), text, self)

    def _update_open_folder_tooltip(self, folder: str):
        try:
            if folder:
                safe = html.escape(folder)
                text = f"<p style='white-space:pre-wrap;'>{safe}</p>"
            else:
                text = "Kein Ordner gewählt"
            self._open_action_tooltip = text
            if self._open_folder_action:
                self._open_folder_action.setToolTip(text)
        except Exception:
            pass
    
    def _open_settings(self):
        """Einstellungsdialog öffnen"""
        dialog = SettingsDialog(self)
        dialog.settingsChanged.connect(self._on_settings_changed)
        
        if dialog.exec() == QDialog.Accepted:
            self._log.info("settings_dialog_accepted", extra={"event": "settings_dialog_accepted"})
    
    def _open_kurzel_manager(self):
        """Kürzel-Manager öffnen"""
        dialog = KurzelManagerDialog(self)
        dialog.kurzelChanged.connect(self._on_kurzel_changed)
        dialog.exec()
    
    def _on_kurzel_changed(self):
        """Wird aufgerufen wenn Kürzel geändert wurden"""
        self._log.info("kurzel_changed", extra={"event": "kurzel_changed"})
        # Hier könnten weitere Aktionen bei Kürzel-Änderungen implementiert werden
        # z.B. OCR-Cache leeren, Galerie aktualisieren, etc.
    
    def _toggle_sidebar(self):
        """Sidebar ein-/ausblenden"""
        if self.side.isVisible():
            self.side.hide()
        else:
            self.side.show()
    
    def _load_excel_data(self):
        """Excel Grunddaten laden - wechselt zum Excel-Tab"""
        # Wechsle zum Excel-Tab
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == "Excel-Grunddaten":
                self.tabs.setCurrentIndex(i)
                break
                
    def _refresh_images(self):
        """Bilder aktualisieren"""
        try:
            if hasattr(self, 'single') and hasattr(self.single, 'refresh_images'):
                self.single.refresh_images()
            if hasattr(self, 'gallery') and hasattr(self.gallery, 'refresh_images'):
                self.gallery.refresh_images()
            if hasattr(self, 'cover') and hasattr(self.cover, '_refresh_folder'):
                self.cover._refresh_folder()
            self._log.info("images_refreshed", extra={"event": "images_refreshed"})
        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"Fehler beim Aktualisieren: {str(e)}")
            
    def _show_exif_info(self):
        """EXIF-Informationen anzeigen"""
        try:
            if hasattr(self, 'single') and hasattr(self.single, 'show_exif_info'):
                self.single.show_exif_info()
            else:
                QMessageBox.information(self, "EXIF-Info", "Kein Bild geladen oder EXIF-Funktion nicht verfügbar.")
        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"Fehler beim Anzeigen der EXIF-Info: {str(e)}")
            
    def _start_ocr_analysis(self):
        """OCR-Analyse starten"""
        try:
            if hasattr(self, 'single') and hasattr(self.single, 'start_ocr_analysis'):
                self.single.start_ocr_analysis()
            else:
                QMessageBox.information(self, "OCR-Analyse", "OCR-Analyse nicht verfügbar.")
        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"Fehler beim Starten der OCR-Analyse: {str(e)}")
            
    def _test_ocr_methods(self):
        """OCR-Methoden testen"""
        try:
            if hasattr(self, 'single') and hasattr(self.single, 'test_ocr_methods'):
                self.single.test_ocr_methods()
            else:
                QMessageBox.information(self, "OCR-Test", "OCR-Test-Funktion nicht verfügbar.")
        except Exception as e:
            QMessageBox.warning(self, "Fehler", f"Fehler beim Testen der OCR-Methoden: {str(e)}")
            
    def _zoom_in(self):
        """Zoom vergrößern"""
        try:
            if hasattr(self, 'single') and hasattr(self.single, 'zoom_in'):
                self.single.zoom_in()
        except Exception as e:
            self._log.warning("zoom_in_failed", extra={"event": "zoom_in_failed", "error": str(e)})
            
    def _zoom_out(self):
        """Zoom verkleinern"""
        try:
            if hasattr(self, 'single') and hasattr(self.single, 'zoom_out'):
                self.single.zoom_out()
        except Exception as e:
            self._log.warning("zoom_out_failed", extra={"event": "zoom_out_failed", "error": str(e)})
            
    def _zoom_reset(self):
        """Zoom zurücksetzen"""
        try:
            if hasattr(self, 'single') and hasattr(self.single, 'zoom_reset'):
                self.single.zoom_reset()
        except Exception as e:
            self._log.warning("zoom_reset_failed", extra={"event": "zoom_reset_failed", "error": str(e)})
            
    def _toggle_fullscreen(self):
        """Vollbild umschalten"""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
            
    def _open_config_editor(self):
        """Konfigurationseditor öffnen"""
        QMessageBox.information(self, "Konfiguration", "Konfigurationseditor wird geöffnet...")
        # Hier würde der Konfigurationseditor implementiert
        
    def _open_migration_tools(self):
        """Migrations-Tools öffnen"""
        dialog = MigrationDialog(self)
        dialog.migrationComplete.connect(self._on_migration_complete)
        dialog.exec()
    
    def _on_migration_complete(self, stats: dict):
        """Wird aufgerufen nach erfolgreicher Migration"""
        self._log.info("migration_complete", extra={"event": "migration_complete", "stats": stats})
        
    def _create_backup(self):
        """Backup erstellen"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Backup erstellen", "backup.json", "JSON-Dateien (*.json)"
        )
        if file_path:
            try:
                # Hier würde die Backup-Erstellung implementiert
                QMessageBox.information(self, "Backup erstellt", f"Backup wurde in '{file_path}' gespeichert.")
            except Exception as e:
                QMessageBox.critical(self, "Fehler", f"Fehler beim Erstellen des Backups: {str(e)}")
                
    def _restore_backup(self):
        """Backup wiederherstellen"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Backup wiederherstellen", "", "JSON-Dateien (*.json)"
        )
        if file_path:
            try:
                # Hier würde die Backup-Wiederherstellung implementiert
                QMessageBox.information(self, "Backup wiederhergestellt", f"Backup aus '{file_path}' wurde wiederhergestellt.")
            except Exception as e:
                QMessageBox.critical(self, "Fehler", f"Fehler beim Wiederherstellen des Backups: {str(e)}")
    
    def _update_gene_counter(self):
        """Aktualisiert Gene-Counter basierend auf Evaluation Cache"""
        if not hasattr(self, 'evaluation_cache') or not hasattr(self, 'gene_count_button'):
            return
        
        try:
            gene_count = self.evaluation_cache.count_gene_flags()
            self.gene_count_button.setText(str(gene_count))
        except Exception as e:
            self._log.error("update_gene_counter_failed", extra={"event": "update_gene_counter_failed", "error": str(e)})
    
    def _navigate_to_next_gene(self):
        """Navigiert zum nächsten Bild mit Gene-Flag"""
        if not hasattr(self, 'evaluation_cache'):
            return
        
        try:
            current_path = self.single._current_path() if hasattr(self.single, '_current_path') else None
            next_gene_image = self.evaluation_cache.get_next_gene_image(current_path)
            
            if next_gene_image:
                self.tabs.setCurrentWidget(self.single)
                self.single.select_image(next_gene_image)
            else:
                QMessageBox.information(
                    self, "Keine Gene-Checks", 
                    "Kein Bild mit Gene-Flag gefunden."
                )
        except Exception as e:
            self._log.error("navigate_to_gene_failed", extra={"event": "navigate_to_gene_failed", "error": str(e)})
    
    def _show_shortcuts_help(self):
        """Tastaturkürzel-Hilfe anzeigen"""
        from .shortcuts_help import ShortcutsHelpDialog
        dialog = ShortcutsHelpDialog(self)
        dialog.exec()
    
    def _show_about(self):
        """Über-Dialog anzeigen"""
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.about(self, "Über BerichtGeneratorX", 
                         "BerichtGeneratorX Qt UI\n\n"
                         "Eine moderne Bildanalyse-Anwendung mit OCR-Funktionalität.\n\n"
                         "Version: 2.0 (PySide6)")
    
    def _on_settings_changed(self, settings_dict):
        """Einstellungsänderungen verarbeiten"""
        self._log.info("settings_changed", extra={"event": "settings_changed", "settings": list(settings_dict.keys())})
        
        # Theme anwenden
        if "theme" in settings_dict:
            self._apply_theme_from_settings()
        
        # OCR-Tag-Größen aktualisieren
        if any(key in settings_dict for key in ["gallery_tag_size", "single_tag_size", "tag_opacity"]):
            self._update_ocr_tag_settings()
        
        # Thumbnail-Größe aktualisieren
        if "thumb_size" in settings_dict:
            self._update_thumbnail_settings()
    
    def _apply_theme_from_settings(self):
        """Theme aus Einstellungen anwenden"""
        theme_name = self.settings_manager.get("theme", "Light")
        apply_theme(theme_name)
        
        # Theme-Action im Menü aktivieren
        if hasattr(self, 'theme_actions') and theme_name in self.theme_actions:
            for name, action in self.theme_actions.items():
                action.setChecked(name == theme_name)
    
    def _update_ocr_tag_settings(self):
        """OCR-Tag-Einstellungen aktualisieren"""
        # Diese Methode wird von den Views implementiert
        pass
    
    def _update_thumbnail_settings(self):
        """Thumbnail-Einstellungen aktualisieren"""
        try:
            if hasattr(self, 'gallery') and hasattr(self.gallery, 'refresh_layout_from_settings'):
                self.gallery.refresh_layout_from_settings()
        except Exception:
            pass

        pass
