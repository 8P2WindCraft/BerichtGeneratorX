# -*- coding: utf-8 -*-
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QLabel,
    QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QLineEdit, QTextEdit,
    QPushButton, QGroupBox, QFormLayout, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QFileDialog, QSlider,
    QRadioButton, QButtonGroup
)
from PySide6.QtCore import Qt, Signal, QSettings, QRegularExpression
from PySide6.QtGui import QFont, QRegularExpressionValidator
from utils_logging import get_logger
import json
import os


class SettingsDialog(QDialog):
    """Kompletter Einstellungsdialog mit allen Optionen aus der alten Version"""
    
    settingsChanged = Signal(dict)  # Signal für Änderungen
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._log = get_logger('app', {"module": "qtui.settings_dialog"})
        self._log.info("module_started", extra={"event": "module_started"})
        
        self.setWindowTitle("Einstellungen")
        self.setModal(True)
        self.resize(700, 600)
        
        # Settings Manager
        self.settings = QSettings("BerichtGeneratorX", "Settings")
        
        # Layout
        layout = QVBoxLayout(self)
        
        # Tab Widget
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.btn_ok = QPushButton("OK")
        self.btn_cancel = QPushButton("Abbrechen")
        self.btn_apply = QPushButton("Übernehmen")
        
        button_layout.addStretch()
        button_layout.addWidget(self.btn_apply)
        button_layout.addWidget(self.btn_cancel)
        button_layout.addWidget(self.btn_ok)
        layout.addLayout(button_layout)
        
        # Verbindungen
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_apply.clicked.connect(self.apply_settings)
        
        # Tabs erstellen
        self._create_general_tab()
        self._create_display_tab()
        self._create_categories_tab()
        self._create_damage_tab()
        self._create_image_types_tab()
        self._create_kurzel_tab()
        
        # Einstellungen laden
        self._load_settings()
    
    def _create_general_tab(self):
        """Allgemeine Einstellungen"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Darstellungs-Einstellungen
        appearance_group = QGroupBox("Darstellung")
        appearance_layout = QFormLayout(appearance_group)
        
        self.dark_mode_check = QCheckBox("Dark Mode aktivieren")
        self.dark_mode_check.stateChanged.connect(self._on_dark_mode_changed)
        appearance_layout.addRow(self.dark_mode_check)
        
        layout.addWidget(appearance_group)
        
        # Spracheinstellungen
        lang_group = QGroupBox("Spracheinstellungen")
        lang_layout = QFormLayout(lang_group)
        
        self.language_combo = QComboBox()
        self.language_combo.addItems(["Deutsch", "English"])
        lang_layout.addRow("Sprache:", self.language_combo)
        
        layout.addWidget(lang_group)
        
        # Verzeichnis-Einstellungen
        dir_group = QGroupBox("Verzeichnis-Einstellungen")
        dir_layout = QFormLayout(dir_group)
        
        self.last_folder_edit = QLineEdit()
        self.last_folder_edit.setReadOnly(True)
        self.btn_browse_folder = QPushButton("Durchsuchen...")
        self.btn_browse_folder.clicked.connect(self._browse_folder)
        
        folder_layout = QHBoxLayout()
        folder_layout.addWidget(self.last_folder_edit)
        folder_layout.addWidget(self.btn_browse_folder)
        dir_layout.addRow("Standard-Ordner:", folder_layout)
        
        layout.addWidget(dir_group)
        
        # Auto-Save Einstellungen
        save_group = QGroupBox("Auto-Save Einstellungen")
        save_layout = QFormLayout(save_group)
        
        self.auto_save_check = QCheckBox("Automatisches Speichern aktivieren")
        save_layout.addRow(self.auto_save_check)
        
        self.save_interval_spin = QSpinBox()
        self.save_interval_spin.setRange(1, 60)
        self.save_interval_spin.setSuffix(" Sekunden")
        save_layout.addRow("Speicher-Intervall:", self.save_interval_spin)
        
        layout.addWidget(save_group)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Allgemein")
    
    def _create_display_tab(self):
        """Anzeige-Einstellungen"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Theme-Einstellungen
        theme_group = QGroupBox("Theme-Einstellungen")
        theme_layout = QFormLayout(theme_group)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Hell", "Dunkel", "System"])
        theme_layout.addRow("Theme:", self.theme_combo)
        
        layout.addWidget(theme_group)
        
        # Thumbnail-Einstellungen
        thumb_group = QGroupBox("Thumbnail-Einstellungen")
        thumb_layout = QFormLayout(thumb_group)
        
        self.thumb_size_spin = QSpinBox()
        self.thumb_size_spin.setRange(80, 300)
        self.thumb_size_spin.setSuffix(" px")
        thumb_layout.addRow("Thumbnail-Größe:", self.thumb_size_spin)
        
        self.thumb_quality_spin = QSpinBox()
        self.thumb_quality_spin.setRange(1, 100)
        self.thumb_quality_spin.setSuffix("%")
        thumb_layout.addRow("Thumbnail-Qualität:", self.thumb_quality_spin)
        
        layout.addWidget(thumb_group)
        
        # Bildanzeige-Einstellungen
        image_group = QGroupBox("Bildanzeige-Einstellungen")
        image_layout = QFormLayout(image_group)
        
        self.image_quality_spin = QSpinBox()
        self.image_quality_spin.setRange(1, 100)
        self.image_quality_spin.setSuffix("%")
        image_layout.addRow("Bildqualität:", self.image_quality_spin)
        
        self.zoom_factor_spin = QDoubleSpinBox()
        self.zoom_factor_spin.setRange(0.1, 5.0)
        self.zoom_factor_spin.setSingleStep(0.1)
        self.zoom_factor_spin.setSuffix("x")
        image_layout.addRow("Standard-Zoom:", self.zoom_factor_spin)
        
        layout.addWidget(image_group)

        # Tag-Anzeige (vorher im OCR-Tab)
        tag_group = QGroupBox("Tag-Anzeige")
        tag_layout = QFormLayout(tag_group)

        self.gallery_tag_size_spin = QSpinBox()
        self.gallery_tag_size_spin.setRange(6, 20)
        self.gallery_tag_size_spin.setSuffix(" pt")
        tag_layout.addRow("Galerie Schriftgröße:", self.gallery_tag_size_spin)

        self.single_tag_size_spin = QSpinBox()
        self.single_tag_size_spin.setRange(8, 24)
        self.single_tag_size_spin.setSuffix(" pt")
        tag_layout.addRow("Einzelbild Schriftgröße:", self.single_tag_size_spin)

        self.tag_opacity_slider = QSlider(Qt.Horizontal)
        self.tag_opacity_slider.setRange(50, 255)
        self.tag_opacity_slider.setValue(200)
        tag_layout.addRow("Transparenz:", self.tag_opacity_slider)

        layout.addWidget(tag_group)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Anzeige")
    
    def _create_crop_tab(self):
        """Crop-Out Einstellungen"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Crop-Koordinaten
        crop_group = QGroupBox("Crop-Out Koordinaten")
        crop_layout = QFormLayout(crop_group)
        
        self.crop_x_spin = QSpinBox()
        self.crop_x_spin.setRange(0, 10000)
        crop_layout.addRow("X-Position:", self.crop_x_spin)
        
        self.crop_y_spin = QSpinBox()
        self.crop_y_spin.setRange(0, 10000)
        crop_layout.addRow("Y-Position:", self.crop_y_spin)
        
        self.crop_w_spin = QSpinBox()
        self.crop_w_spin.setRange(10, 10000)
        crop_layout.addRow("Breite:", self.crop_w_spin)
        
        self.crop_h_spin = QSpinBox()
        self.crop_h_spin.setRange(10, 10000)
        crop_layout.addRow("Höhe:", self.crop_h_spin)
        
        layout.addWidget(crop_group)
        
        # Vorschau
        preview_group = QGroupBox("Vorschau")
        preview_layout = QVBoxLayout(preview_group)
        
        self.preview_label = QLabel("Vorschau wird hier angezeigt")
        self.preview_label.setMinimumHeight(200)
        self.preview_label.setStyleSheet("border: 1px solid gray; background: white;")
        self.preview_label.setAlignment(Qt.AlignCenter)
        preview_layout.addWidget(self.preview_label)
        
        self.btn_update_preview = QPushButton("Vorschau aktualisieren")
        self.btn_update_preview.clicked.connect(self._update_preview)
        preview_layout.addWidget(self.btn_update_preview)
        
        layout.addWidget(preview_group)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Crop-Out")
    
    def _create_categories_tab(self):
        """Schadenskategorien-Einstellungen"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Kategorien-Verwaltung
        cat_group = QGroupBox("Schadenskategorien")
        cat_layout = QVBoxLayout(cat_group)
        
        # Tabelle für Kategorien
        self.categories_table = QTableWidget()
        self.categories_table.setColumnCount(2)
        self.categories_table.setHorizontalHeaderLabels(["Kategorie", "Beschreibung"])
        self.categories_table.horizontalHeader().setStretchLastSection(True)
        cat_layout.addWidget(self.categories_table)
        
        # Buttons für Kategorien
        cat_btn_layout = QHBoxLayout()
        self.btn_add_category = QPushButton("Hinzufügen")
        self.btn_remove_category = QPushButton("Entfernen")
        self.btn_edit_category = QPushButton("Bearbeiten")
        
        cat_btn_layout.addWidget(self.btn_add_category)
        cat_btn_layout.addWidget(self.btn_edit_category)
        cat_btn_layout.addWidget(self.btn_remove_category)
        cat_btn_layout.addStretch()
        
        cat_layout.addLayout(cat_btn_layout)
        layout.addWidget(cat_group)
        
        # Standard-Kategorien laden
        self._load_default_categories()
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Kategorien")
    
    def _load_default_categories(self):
        """Lädt die Standard-Kategorien aus den Einstellungen"""
        try:
            from .settings_manager import get_settings_manager
            settings_manager = get_settings_manager()
            
            # Schadenskategorien laden
            damage_categories = settings_manager.get("damage_categories", [])
            self.categories_table.setRowCount(len(damage_categories))
            
            for i, category in enumerate(damage_categories):
                self.categories_table.setItem(i, 0, QTableWidgetItem(category))
                self.categories_table.setItem(i, 1, QTableWidgetItem(""))
            
            # Bildart-Kategorien laden
            image_types = settings_manager.get("image_types", [])
            start_row = len(damage_categories)
            self.categories_table.setRowCount(start_row + len(image_types))
            
            for i, img_type in enumerate(image_types):
                row = start_row + i
                self.categories_table.setItem(row, 0, QTableWidgetItem(img_type))
                self.categories_table.setItem(row, 1, QTableWidgetItem("Bildart"))
                
        except Exception as e:
            self._log.error("categories_load_failed", extra={"event": "categories_load_failed", "error": str(e)})

    def _create_damage_tab(self):
        """Schadenskategorien: zweisprachige Tabelle (5 Punkte)"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.tbl_damage = QTableWidget(5, 3)
        self.tbl_damage.setHorizontalHeaderLabels(["#", "Deutsch", "Englisch"])
        self.tbl_damage.verticalHeader().setVisible(False)
        self.tbl_damage.horizontalHeader().setStretchLastSection(True)
        for r in range(5):
            self.tbl_damage.setItem(r, 0, QTableWidgetItem(str(r+1)))
            it = self.tbl_damage.item(r, 0)
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        layout.addWidget(self.tbl_damage)

        btns = QHBoxLayout(); layout.addLayout(btns)
        btns.addStretch(1)
        btn_reset = QPushButton("Standardwerte wiederherstellen")
        btn_reset.clicked.connect(self._reset_damage_defaults)
        btns.addWidget(btn_reset)

        layout.addStretch(1)
        self.tab_widget.addTab(tab, "Schadenskategorien")
        self._load_damage_from_settings()

    def _create_image_types_tab(self):
        """Bildarten: zweisprachige Tabelle (5 Punkte)"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.tbl_images = QTableWidget(5, 3)
        self.tbl_images.setHorizontalHeaderLabels(["#", "Deutsch", "Englisch"])
        self.tbl_images.verticalHeader().setVisible(False)
        self.tbl_images.horizontalHeader().setStretchLastSection(True)
        for r in range(5):
            self.tbl_images.setItem(r, 0, QTableWidgetItem(str(r+1)))
            it = self.tbl_images.item(r, 0)
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
        layout.addWidget(self.tbl_images)

        btns = QHBoxLayout(); layout.addLayout(btns)
        btns.addStretch(1)
        btn_reset = QPushButton("Standardwerte wiederherstellen")
        btn_reset.clicked.connect(self._reset_images_defaults)
        btns.addWidget(btn_reset)

        layout.addStretch(1)
        self.tab_widget.addTab(tab, "Bildarten")
        self._load_images_from_settings()

    def _reset_damage_defaults(self):
        """Setzt Schadenskategorien auf zentrale Defaults (gekürzt auf 5)."""
        try:
            from config_manager import config_manager
            cfg = config_manager.config or {}
            dmg = cfg.get('damage_categories', {})
            de = (dmg.get('de') or [])[:5]
            en = (dmg.get('en') or [])[:5]
            for r in range(5):
                self.tbl_damage.setItem(r, 1, QTableWidgetItem(de[r] if r < len(de) else ""))
                self.tbl_damage.setItem(r, 2, QTableWidgetItem(en[r] if r < len(en) else ""))
        except Exception as e:
            self._log.error("reset_damage_failed", extra={"event": "reset_damage_failed", "error": str(e)})

    def _reset_images_defaults(self):
        try:
            from config_manager import config_manager
            cfg = config_manager.config or {}
            img = cfg.get('image_types', {})
            de = (img.get('de') or [])[:5]
            en = (img.get('en') or [])[:5]
            for r in range(5):
                self.tbl_images.setItem(r, 1, QTableWidgetItem(de[r] if r < len(de) else ""))
                self.tbl_images.setItem(r, 2, QTableWidgetItem(en[r] if r < len(en) else ""))
        except Exception as e:
            self._log.error("reset_images_failed", extra={"event": "reset_images_failed", "error": str(e)})

    def _load_damage_from_settings(self):
        try:
            from .settings_manager import get_settings_manager
            sm = get_settings_manager()
            de = sm.get('damage_categories_de', []) or []
            en = sm.get('damage_categories_en', []) or []
            for r in range(5):
                self.tbl_damage.setItem(r, 1, QTableWidgetItem(de[r] if r < len(de) else ""))
                self.tbl_damage.setItem(r, 2, QTableWidgetItem(en[r] if r < len(en) else ""))
        except Exception as e:
            self._log.error("load_damage_failed", extra={"event": "load_damage_failed", "error": str(e)})

    def _load_images_from_settings(self):
        try:
            from .settings_manager import get_settings_manager
            sm = get_settings_manager()
            de = sm.get('image_types_de', []) or []
            en = sm.get('image_types_en', []) or []
            for r in range(5):
                self.tbl_images.setItem(r, 1, QTableWidgetItem(de[r] if r < len(de) else ""))
                self.tbl_images.setItem(r, 2, QTableWidgetItem(en[r] if r < len(en) else ""))
        except Exception as e:
            self._log.error("load_images_failed", extra={"event": "load_images_failed", "error": str(e)})
    
    def _load_default_kurzel(self):
        """Lädt die Standard-Kürzel aus den Einstellungen"""
        try:
            from .settings_manager import get_settings_manager
            settings_manager = get_settings_manager()
            
            # Kürzel-Tabelle laden
            kurzel_table = settings_manager.get("kurzel_table", {})
            if not kurzel_table:
                # Standard-Kürzel erstellen
                default_kurzel = ["HSS", "HS5", "HS6", "HS7", "HS8", "HS9", "HS0", "HS1", "HS2", "HS3", "HS4"]
                kurzel_table = {}
                for i, kurzel in enumerate(default_kurzel):
                    kurzel_table[kurzel] = {
                        'kurzel_code': kurzel,
                        'active': True,
                        'frequency': 0,
                        'order': i
                    }
            
            # Tabelle füllen
            self.kurzel_table.setRowCount(len(kurzel_table))
            row = 0
            for kurzel_code, data in kurzel_table.items():
                self.kurzel_table.setItem(row, 0, QTableWidgetItem(kurzel_code))
                
                # Checkbox für Aktiv
                active_item = QTableWidgetItem()
                active_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                active_item.setCheckState(Qt.Checked if data.get('active', True) else Qt.Unchecked)
                self.kurzel_table.setItem(row, 1, active_item)
                
                # Häufigkeit
                frequency = data.get('frequency', 0)
                self.kurzel_table.setItem(row, 2, QTableWidgetItem(str(frequency)))
                
                # Reihenfolge
                order = data.get('order', row)
                self.kurzel_table.setItem(row, 3, QTableWidgetItem(str(order)))
                
                row += 1
                
        except Exception as e:
            self._log.error("kurzel_load_failed", extra={"event": "kurzel_load_failed", "error": str(e)})
    
    def _add_kurzel(self):
        """Neues Kürzel hinzufügen"""
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(self, 'Kürzel hinzufügen', 'Kürzel eingeben:')
        if ok and text:
            # Validierung
            if not text.isupper() or not text.replace('-', '').isalnum():
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Ungültiges Kürzel", "Nur Großbuchstaben, Zahlen und Bindestriche erlaubt!")
                return
            
            # Prüfen ob bereits vorhanden
            for row in range(self.kurzel_table.rowCount()):
                if self.kurzel_table.item(row, 0).text() == text:
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.warning(self, "Kürzel vorhanden", "Dieses Kürzel existiert bereits!")
                    return
            
            # Hinzufügen
            row = self.kurzel_table.rowCount()
            self.kurzel_table.insertRow(row)
            self.kurzel_table.setItem(row, 0, QTableWidgetItem(text))
            
            # Checkbox für Aktiv
            active_item = QTableWidgetItem()
            active_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            active_item.setCheckState(Qt.Checked)
            self.kurzel_table.setItem(row, 1, active_item)
            
            # Häufigkeit
            self.kurzel_table.setItem(row, 2, QTableWidgetItem("0"))
            
            # Reihenfolge
            self.kurzel_table.setItem(row, 3, QTableWidgetItem(str(row)))
    
    def _remove_kurzel(self):
        """Ausgewähltes Kürzel entfernen"""
        current_row = self.kurzel_table.currentRow()
        if current_row >= 0:
            self.kurzel_table.removeRow(current_row)
    
    def _edit_kurzel(self):
        """Ausgewähltes Kürzel bearbeiten"""
        current_row = self.kurzel_table.currentRow()
        if current_row >= 0:
            current_text = self.kurzel_table.item(current_row, 0).text()
            from PySide6.QtWidgets import QInputDialog
            text, ok = QInputDialog.getText(self, 'Kürzel bearbeiten', 'Kürzel eingeben:', text=current_text)
            if ok and text:
                # Validierung
                if not text.isupper() or not text.replace('-', '').isalnum():
                    from PySide6.QtWidgets import QMessageBox
                    QMessageBox.warning(self, "Ungültiges Kürzel", "Nur Großbuchstaben, Zahlen und Bindestriche erlaubt!")
                    return
                
                self.kurzel_table.setItem(current_row, 0, QTableWidgetItem(text))
    
    def _import_kurzel_csv(self):
        """CSV-Datei importieren"""
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Kürzel-Tabelle importieren", "", "CSV-Dateien (*.csv);;Alle Dateien (*)"
        )
        if file_path:
            try:
                import csv
                imported_count = 0
                
                with open(file_path, 'r', encoding='utf-8') as csvfile:
                    reader = csv.DictReader(csvfile)
                    for row in reader:
                        kurzel_code = row.get('kurzel_code', '').strip()
                        if kurzel_code:
                            # Prüfen ob bereits vorhanden
                            exists = False
                            for table_row in range(self.kurzel_table.rowCount()):
                                if self.kurzel_table.item(table_row, 0).text() == kurzel_code:
                                    exists = True
                                    break
                            
                            if not exists:
                                # Hinzufügen
                                table_row = self.kurzel_table.rowCount()
                                self.kurzel_table.insertRow(table_row)
                                self.kurzel_table.setItem(table_row, 0, QTableWidgetItem(kurzel_code))
                                
                                # Checkbox für Aktiv
                                active_item = QTableWidgetItem()
                                active_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                                active = row.get('active', 'true').lower() == 'true'
                                active_item.setCheckState(Qt.Checked if active else Qt.Unchecked)
                                self.kurzel_table.setItem(table_row, 1, active_item)
                                
                                # Häufigkeit
                                frequency = row.get('frequency', '0')
                                self.kurzel_table.setItem(table_row, 2, QTableWidgetItem(str(frequency)))
                                
                                # Reihenfolge
                                order = row.get('order', str(table_row))
                                self.kurzel_table.setItem(table_row, 3, QTableWidgetItem(str(order)))
                                
                                imported_count += 1
                
                QMessageBox.information(self, "Import erfolgreich", f"{imported_count} Kürzel importiert!")
                
            except Exception as e:
                QMessageBox.critical(self, "Import fehlgeschlagen", f"Fehler beim Import: {str(e)}")
    
    def _export_kurzel_csv(self):
        """CSV-Datei exportieren"""
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Kürzel-Tabelle exportieren", "kurzel_tabelle.csv", "CSV-Dateien (*.csv);;Alle Dateien (*)"
        )
        if file_path:
            try:
                import csv
                
                with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
                    fieldnames = ['kurzel_code', 'active', 'frequency', 'order']
                    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                    
                    writer.writeheader()
                    for row in range(self.kurzel_table.rowCount()):
                        kurzel_code = self.kurzel_table.item(row, 0).text()
                        active_item = self.kurzel_table.item(row, 1)
                        active = active_item.checkState() == Qt.Checked
                        frequency = self.kurzel_table.item(row, 2).text()
                        order = self.kurzel_table.item(row, 3).text()
                        
                        writer.writerow({
                            'kurzel_code': kurzel_code,
                            'active': active,
                            'frequency': frequency,
                            'order': order
                        })
                
                QMessageBox.information(self, "Export erfolgreich", f"Kürzel-Tabelle exportiert nach:\n{file_path}")
                
            except Exception as e:
                QMessageBox.critical(self, "Export fehlgeschlagen", f"Fehler beim Export: {str(e)}")
    
    def _create_kurzel_tab(self):
        """Kürzel-Tabelle mit CSV Import/Export"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Kürzel-Verwaltung
        kurzel_group = QGroupBox("Gültige Kürzel")
        kurzel_layout = QVBoxLayout(kurzel_group)
        
        # Tabelle für Kürzel (wie im ursprünglichen Programm)
        self.kurzel_table = QTableWidget()
        self.kurzel_table.setColumnCount(4)
        self.kurzel_table.setHorizontalHeaderLabels(["Kürzel", "Aktiv", "Häufigkeit", "Reihenfolge"])
        self.kurzel_table.horizontalHeader().setStretchLastSection(True)
        kurzel_layout.addWidget(self.kurzel_table)
        
        # Buttons für Kürzel-Verwaltung
        kurzel_btn_layout = QHBoxLayout()
        self.btn_add_kurzel = QPushButton("Hinzufügen")
        self.btn_remove_kurzel = QPushButton("Entfernen")
        self.btn_edit_kurzel = QPushButton("Bearbeiten")
        
        kurzel_btn_layout.addWidget(self.btn_add_kurzel)
        kurzel_btn_layout.addWidget(self.btn_edit_kurzel)
        kurzel_btn_layout.addWidget(self.btn_remove_kurzel)
        kurzel_btn_layout.addStretch()
        
        kurzel_layout.addLayout(kurzel_btn_layout)
        
        # CSV Import/Export Buttons
        csv_layout = QHBoxLayout()
        self.btn_import_csv = QPushButton("CSV Importieren")
        self.btn_export_csv = QPushButton("CSV Exportieren")
        
        csv_layout.addWidget(self.btn_import_csv)
        csv_layout.addWidget(self.btn_export_csv)
        csv_layout.addStretch()
        
        kurzel_layout.addLayout(csv_layout)
        
        # Info-Label
        info_label = QLabel("Kürzel-Tabelle mit CSV Import/Export. Aktiv = Kürzel wird für OCR verwendet.")
        info_label.setWordWrap(True)
        kurzel_layout.addWidget(info_label)
        
        layout.addWidget(kurzel_group)
        
        # Button-Verbindungen
        self.btn_add_kurzel.clicked.connect(self._add_kurzel)
        self.btn_remove_kurzel.clicked.connect(self._remove_kurzel)
        self.btn_edit_kurzel.clicked.connect(self._edit_kurzel)
        self.btn_import_csv.clicked.connect(self._import_kurzel_csv)
        self.btn_export_csv.clicked.connect(self._export_kurzel_csv)
        
        # Standard-Kürzel laden
        self._load_default_kurzel()
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Kürzel")
    
    def _browse_folder(self):
        """Ordner auswählen"""
        folder = QFileDialog.getExistingDirectory(self, "Standard-Ordner auswählen")
        if folder:
            self.last_folder_edit.setText(folder)
    
    def _update_preview(self):
        """Vorschau der Crop-Koordinaten aktualisieren"""
        x = self.crop_x_spin.value()
        y = self.crop_y_spin.value()
        w = self.crop_w_spin.value()
        h = self.crop_h_spin.value()
        
        # Einfache Text-Vorschau
        preview_text = f"Crop-Bereich:\nX: {x}, Y: {y}\nBreite: {w}, Höhe: {h}"
        self.preview_label.setText(preview_text)
    
    def _load_default_categories(self):
        """Standard-Kategorien laden"""
        default_categories = [
            ("Kratzer", "Oberflächenkratzer"),
            ("Delle", "Dellen im Material"),
            ("Riss", "Risse im Material"),
            ("Korrosion", "Rost und Korrosion"),
            ("Verschmutzung", "Verschmutzungen"),
            ("Abnutzung", "Normale Abnutzung"),
            ("Beschädigung", "Sonstige Beschädigungen")
        ]
        
        self.categories_table.setRowCount(len(default_categories))
        for i, (category, description) in enumerate(default_categories):
            self.categories_table.setItem(i, 0, QTableWidgetItem(category))
            self.categories_table.setItem(i, 1, QTableWidgetItem(description))
    
    def _load_settings(self):
        """Einstellungen aus SettingsManager laden"""
        from .settings_manager import get_settings_manager
        settings_manager = get_settings_manager()
        
        # Allgemeine Einstellungen
        # Dark Mode
        dark_mode = settings_manager.get("dark_mode", False)
        self.dark_mode_check.setChecked(dark_mode)
        
        language = settings_manager.get("language", "Deutsch")
        self.language_combo.setCurrentText(language)
        
        last_folder = settings_manager.get("last_folder", "")
        self.last_folder_edit.setText(last_folder)
        
        auto_save = settings_manager.get("auto_save", True)
        self.auto_save_check.setChecked(auto_save)
        
        save_interval = settings_manager.get("save_interval", 5)
        self.save_interval_spin.setValue(save_interval)
        
        # OCR-bezogene Einstellungen entfernt
        
        gallery_tag_size = settings_manager.get("gallery_tag_size", 8)
        self.gallery_tag_size_spin.setValue(gallery_tag_size)
        
        single_tag_size = settings_manager.get("single_tag_size", 9)
        self.single_tag_size_spin.setValue(single_tag_size)
        
        tag_opacity = settings_manager.get("tag_opacity", 200)
        self.tag_opacity_slider.setValue(tag_opacity)
        
        # Anzeige-Einstellungen
        theme = settings_manager.get("theme", "System")
        self.theme_combo.setCurrentText(theme)
        
        thumb_size = settings_manager.get("thumb_size", 160)
        self.thumb_size_spin.setValue(thumb_size)
        
        thumb_quality = settings_manager.get("thumb_quality", 85)
        self.thumb_quality_spin.setValue(thumb_quality)
        
        image_quality = settings_manager.get("image_quality", 95)
        self.image_quality_spin.setValue(image_quality)
        
        zoom_factor = settings_manager.get("zoom_factor", 1.0)
        self.zoom_factor_spin.setValue(zoom_factor)
        
        # Crop-Einstellungen
        # Crop-Out Einstellungen entfernt
        
        # Kürzel-Tabelle laden
        kurzel_table = settings_manager.get("kurzel_table", {})
        if kurzel_table:
            self.kurzel_table.setRowCount(len(kurzel_table))
            row = 0
            for kurzel_code, data in kurzel_table.items():
                self.kurzel_table.setItem(row, 0, QTableWidgetItem(kurzel_code))
                
                # Checkbox für Aktiv
                active_item = QTableWidgetItem()
                active_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                active_item.setCheckState(Qt.Checked if data.get('active', True) else Qt.Unchecked)
                self.kurzel_table.setItem(row, 1, active_item)
                
                # Häufigkeit
                frequency = data.get('frequency', 0)
                self.kurzel_table.setItem(row, 2, QTableWidgetItem(str(frequency)))
                
                # Reihenfolge
                order = data.get('order', row)
                self.kurzel_table.setItem(row, 3, QTableWidgetItem(str(order)))
                
                row += 1
    
    def _save_settings(self):
        """Einstellungen in SettingsManager speichern"""
        from .settings_manager import get_settings_manager
        settings_manager = get_settings_manager()
        
        # Allgemeine Einstellungen
        settings_manager.set("dark_mode", self.dark_mode_check.isChecked())
        settings_manager.set("language", self.language_combo.currentText())
        settings_manager.set("last_folder", self.last_folder_edit.text())
        settings_manager.set("auto_save", self.auto_save_check.isChecked())
        settings_manager.set("save_interval", self.save_interval_spin.value())
        
        # OCR-bezogene Einstellungen entfernt
        settings_manager.set("gallery_tag_size", self.gallery_tag_size_spin.value())
        settings_manager.set("single_tag_size", self.single_tag_size_spin.value())
        settings_manager.set("tag_opacity", self.tag_opacity_slider.value())
        
        # Anzeige-Einstellungen
        settings_manager.set("theme", self.theme_combo.currentText())
        settings_manager.set("thumb_size", self.thumb_size_spin.value())
        settings_manager.set("thumb_quality", self.thumb_quality_spin.value())
        settings_manager.set("image_quality", self.image_quality_spin.value())
        settings_manager.set("zoom_factor", self.zoom_factor_spin.value())
        
        # Crop-Einstellungen entfernt
        
        # Kürzel-Tabelle speichern
        kurzel_table = {}
        for row in range(self.kurzel_table.rowCount()):
            kurzel_code = self.kurzel_table.item(row, 0).text()
            active_item = self.kurzel_table.item(row, 1)
            active = active_item.checkState() == Qt.Checked
            frequency = int(self.kurzel_table.item(row, 2).text() or 0)
            order = int(self.kurzel_table.item(row, 3).text() or row)
            
            kurzel_table[kurzel_code] = {
                'kurzel_code': kurzel_code,
                'active': active,
                'frequency': frequency,
                'order': order
            }
        
        settings_manager.set("kurzel_table", kurzel_table)
        
        # Nur aktive Kürzel für OCR verwenden
        valid_kurzel = [k for k, data in kurzel_table.items() if data['active']]
        settings_manager.set("valid_kurzel", valid_kurzel)
        
        # Mehrsprachige 5-Punkte-Listen (Schäden/Bildarten) speichern
        try:
            def _collect5_col(table: QTableWidget, col: int):
                vals = []
                for r in range(5):
                    it = table.item(r, col)
                    vals.append(it.text().strip() if it and it.text() else "")
                while vals and not vals[-1]:
                    vals.pop()
                return vals

            dmg_de = _collect5_col(self.tbl_damage, 1)
            dmg_en = _collect5_col(self.tbl_damage, 2)
            img_de = _collect5_col(self.tbl_images, 1)
            img_en = _collect5_col(self.tbl_images, 2)

            if dmg_de:
                settings_manager.set("damage_categories_de", dmg_de)
            if dmg_en:
                settings_manager.set("damage_categories_en", dmg_en)
            if img_de:
                settings_manager.set("image_types_de", img_de)
            if img_en:
                settings_manager.set("image_types_en", img_en)

            # Aktive Listen gem. Sprache (auf 5 begrenzt)
            lang_text = (settings_manager.get("language", "Deutsch") or "").lower()
            if lang_text.startswith("deutsch"):
                settings_manager.set("damage_categories", (dmg_de or settings_manager.get("damage_categories", []))[:5])
                settings_manager.set("image_types", (img_de or settings_manager.get("image_types", []))[:5])
            else:
                settings_manager.set("damage_categories", (dmg_en or settings_manager.get("damage_categories", []))[:5])
                settings_manager.set("image_types", (img_en or settings_manager.get("image_types", []))[:5])
        except Exception as e:
            self._log.error("lists_save_failed", extra={"event": "lists_save_failed", "error": str(e)})
        
        self._log.info("settings_saved", extra={"event": "settings_saved"})
    
    def _on_dark_mode_changed(self, state):
        """Dark Mode sofort umschalten (Vorschau)"""
        from .settings_manager import apply_dark_mode
        apply_dark_mode(state == Qt.Checked)
    
    def _on_whitelist_toggled(self, checked):
        """(entfernt)"""
        pass
    
    def apply_settings(self):
        """Einstellungen übernehmen"""
        self._save_settings()
        
        # Signal für Änderungen senden
        settings_dict = {
            "language": self.language_combo.currentText(),
            "last_folder": self.last_folder_edit.text(),
            "auto_save": self.auto_save_check.isChecked(),
            "save_interval": self.save_interval_spin.value(),
            "gallery_tag_size": self.gallery_tag_size_spin.value(),
            "single_tag_size": self.single_tag_size_spin.value(),
            "tag_opacity": self.tag_opacity_slider.value(),
            "theme": self.theme_combo.currentText(),
            "thumb_size": self.thumb_size_spin.value(),
            "thumb_quality": self.thumb_quality_spin.value(),
            "image_quality": self.image_quality_spin.value(),
            "zoom_factor": self.zoom_factor_spin.value()
        }
        
        self.settingsChanged.emit(settings_dict)
    
    def accept(self):
        """Dialog akzeptieren"""
        self.apply_settings()
        super().accept()
    
    def get_settings(self):
        """Alle Einstellungen als Dictionary zurückgeben"""
        # Kürzel aus Textfeld extrahieren
        kurzel_text = self.kurzel_text.toPlainText().strip()
        valid_kurzel = []
        if kurzel_text:
            lines = kurzel_text.split('\n')
            for line in lines:
                line = line.strip().upper()
                if line and line.replace('-', '').replace('0', '').replace('1', '').replace('2', '').replace('3', '').replace('4', '').isalpha():
                    valid_kurzel.append(line)
        
        return {
            "language": self.language_combo.currentText(),
            "last_folder": self.last_folder_edit.text(),
            "auto_save": self.auto_save_check.isChecked(),
            "save_interval": self.save_interval_spin.value(),
            # OCR-Textkorrektur-Optionen entfernt
            "gallery_tag_size": self.gallery_tag_size_spin.value(),
            "single_tag_size": self.single_tag_size_spin.value(),
            "tag_opacity": self.tag_opacity_slider.value(),
            "theme": self.theme_combo.currentText(),
            "thumb_size": self.thumb_size_spin.value(),
            "thumb_quality": self.thumb_quality_spin.value(),
            "image_quality": self.image_quality_spin.value(),
            "zoom_factor": self.zoom_factor_spin.value(),
            "valid_kurzel": valid_kurzel
        }
