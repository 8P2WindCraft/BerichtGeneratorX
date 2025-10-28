# -*- coding: utf-8 -*-
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTabWidget, QSplitter, QFrame, QTreeView, QDockWidget, QProgressBar, QPushButton, QMenuBar, QMenu, QDialog, QFileDialog, QMessageBox
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QShortcut, QKeySequence
from utils_logging import get_logger
from .widgets import ToggleSwitch
from .single_view import SingleView
from .gallery_view import GalleryView
from .excel_view import ExcelView
from .theme import apply_theme, apply_theme_from_bool, get_available_themes
from .settings_dialog import SettingsDialog
from .settings_manager import get_settings_manager
from .kurzel_manager import KurzelManagerDialog
from .migration_tools import MigrationDialog
import os


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BerichtGeneratorX – Qt UI")
        self.resize(980, 680)
        self._log = get_logger('app', {"module": "qtui.main_window"})
        self._log.info("module_started", extra={"event": "module_started"})
        
        # Settings Manager
        self.settings_manager = get_settings_manager()
        self.settings_manager.settingsChanged.connect(self._on_settings_changed)

        root = QWidget()
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        
        # Menüleiste erstellen
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
        
        # Theme aus Einstellungen laden
        self._apply_theme_from_settings()

        # Rechte Sidebar als Dock (einklappbar)
        self.side = QDockWidget("Progress/Kategorien", self)
        self.side.setAllowedAreas(Qt.RightDockWidgetArea)
        self.side.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        side_frame = QFrame(); side_frame.setFrameShape(QFrame.NoFrame)
        self.side.setWidget(side_frame)
        self.addDockWidget(Qt.RightDockWidgetArea, self.side)
        # Sidebar-Inhalt (kompakt): Fortschritt + Kategorien-Tree (Platzhalter)
        sv = QVBoxLayout(side_frame)
        sv.addWidget(QLabel("Bewertungsfortschritt"))
        self.progress = QProgressBar(); self.progress.setRange(0, 100); self.progress.setValue(0)
        self.progress_text = QLabel("0/0")
        sv.addWidget(self.progress)
        sv.addWidget(self.progress_text)
        sv.addWidget(QLabel("Kategorien"))
        sv.addWidget(QTreeView())

        # Sidebar Toggle Button entfernt - nur noch im Menü verfügbar

        self._pending_progress = None

        apply_theme(False)

    def _add_tabs(self):
        # Einzelbild
        self.single = SingleView(); self.single.progressChanged.connect(self._on_progress)
        self.tabs.addTab(self.single, "Einzelbild")
        # Galerie
        self.gallery = GalleryView(); self.tabs.addTab(self.gallery, "Galerie")
        self.gallery.imageSelected.connect(self._open_in_single)
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

    def _on_theme_selected(self, theme_name: str):
        """Theme wurde aus dem Menü ausgewählt"""
        # Alle anderen Theme-Actions deaktivieren
        for name, action in self.theme_actions.items():
            action.setChecked(name == theme_name)
        
        # Theme anwenden
        apply_theme(theme_name)
        self.settings_manager.set("theme", theme_name)
        self._log.info("theme_changed", extra={"event": "theme_changed", "theme": theme_name})

    def _open_in_single(self, path: str):
        # Wechsle auf Einzelbild und lade das Bild
        for i in range(self.tabs.count()):
            if self.tabs.tabText(i) == "Einzelbild":
                self.tabs.setCurrentIndex(i)
                w = self.tabs.widget(i)
                try:
                    w.select_image(path)
                except Exception:
                    pass
                break

    def _on_progress(self, pos: int, total: int, done: int):
        if not hasattr(self, 'progress') or self.progress is None:
            self._pending_progress = (pos, total, done)
            return
        self.progress.setRange(0, total if total else 1)
        self.progress.setValue(done)
        self.progress_text.setText(f"{done}/{total}")
        if self._pending_progress:
            self._pending_progress = None

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
        except Exception:
            pass

    # Persistiere und synchronisiere Ordner
    def _sync_last_folder(self, folder: str):
        try:
            with open("last_folder.txt", "w", encoding="utf-8") as f:
                f.write(folder or "")
        except Exception:
            pass
        # Synchronisiere beide Ansichten: Quelle -> Ziel
        sender = self.sender()
        try:
            if sender is self.gallery:
                self.single.set_folder(folder)
            elif sender is self.single:
                # Galerie nur setzen, nicht erneut emitten
                self.gallery.set_folder(folder, emit=False)
            # OCR-Batch entfernt
        except Exception:
            pass

    def _create_menu_bar(self):
        """Menüleiste erstellen"""
        menubar = self.menuBar()
        
        # Datei-Menü
        file_menu = menubar.addMenu("Datei")
        
        open_action = file_menu.addAction("Ordner öffnen...")
        open_action.setShortcut(QKeySequence.Open)
        open_action.triggered.connect(self._open_folder)
        
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
        
        about_action = help_menu.addAction("Über...")
        about_action.triggered.connect(self._show_about)
    
    def _open_folder(self):
        """Ordner öffnen"""
        self.single._open_folder()
    
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
