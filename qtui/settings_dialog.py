# -*- coding: utf-8 -*-
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QLabel,
    QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox, QLineEdit, QTextEdit,
    QPushButton, QGroupBox, QFormLayout, QScrollArea, QTableWidget,
    QTableWidgetItem, QHeaderView, QMessageBox, QFileDialog, QSlider,
    QRadioButton, QButtonGroup, QSizePolicy, QListWidgetItem
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
        from .settings_manager import get_settings_manager
        self.settings_manager = get_settings_manager()
        
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
        # Kürzel-Tab entfernt - wird nun über Extra → Kürzel-Manager verwaltet
        self._create_cover_tags_tab()
        self._create_text_snippets_tab()
        self._create_evaluation_logic_tab()
        
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
        
        # Bildqualität-Einstellung ENTFERNT - Einzelbild-Ansicht zeigt immer Original-Qualität!
        
        self.zoom_factor_spin = QDoubleSpinBox()
        self.zoom_factor_spin.setRange(0.1, 5.0)
        self.zoom_factor_spin.setSingleStep(0.1)
        self.zoom_factor_spin.setSuffix("x")
        image_layout.addRow("Standard-Zoom:", self.zoom_factor_spin)
        
        # Galerie Overlay-Icon-Größe
        self.gallery_overlay_icon_scale_spin = QDoubleSpinBox()
        self.gallery_overlay_icon_scale_spin.setRange(50, 200)
        self.gallery_overlay_icon_scale_spin.setSingleStep(10)
        self.gallery_overlay_icon_scale_spin.setSuffix("%")
        self.gallery_overlay_icon_scale_spin.setValue(100)  # Standard: 100%
        image_layout.addRow("Galerie Overlay-Icon-Größe:", self.gallery_overlay_icon_scale_spin)
        
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

        # Neue Optionen: Überschrift anzeigen und Reihenfolge
        self.tag_heading_check = QCheckBox("Überschrift aus Kürzel-Tabelle anzeigen")
        tag_layout.addRow(self.tag_heading_check)

        self.tag_heading_order_combo = QComboBox()
        self.tag_heading_order_combo.addItems(["Überschrift unter Tag", "Überschrift über Tag"]) 
        tag_layout.addRow("Reihenfolge:", self.tag_heading_order_combo)

        layout.addWidget(tag_group)
        
        # Tastaturkürzel anzeigen
        shortcuts_group = QGroupBox("Tastaturkürzel")
        shortcuts_layout = QFormLayout(shortcuts_group)
        
        self.show_shortcuts_check = QCheckBox("Tastaturkürzel in Buttons anzeigen")
        shortcuts_layout.addRow(self.show_shortcuts_check)
        
        layout.addWidget(shortcuts_group)
        
        # Galerie-Raster Einstellungen
        grid_group = QGroupBox("Galerie-Raster")
        grid_layout = QFormLayout(grid_group)
        
        self.gallery_grid_combo = QComboBox()
        self.gallery_grid_combo.addItems([
            "Auto-Fit", "2 x 2", "2 x 3", "2 x 4",
            "3 x 2", "3 x 3", "3 x 4",
            "4 x 2", "4 x 3", "4 x 4",
            "5 x 3", "5 x 4"
        ])
        grid_layout.addRow("Standard-Raster:", self.gallery_grid_combo)
        
        layout.addWidget(grid_group)
        
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
        self.categories_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.categories_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        cat_layout.addWidget(self.categories_table, 1)
        
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
        layout.addWidget(cat_group, 1)
        
        # Standard-Kategorien laden
        self._load_default_categories()
        
        # Kategorie-Überschriften für TreeView
        headings_group = QGroupBox("TreeView-Überschriften")
        headings_layout = QVBoxLayout(headings_group)
        
        info_headings = QLabel("Definieren Sie Überschriften und Reihenfolge für die TreeView-Anzeige.")
        info_headings.setWordWrap(True)
        headings_layout.addWidget(info_headings)
        
        self.category_headings_table = QTableWidget()
        self.category_headings_table.setColumnCount(4)
        self.category_headings_table.setHorizontalHeaderLabels([
            "Kategorie", "Reihenfolge", "Überschrift (DE)", "Überschrift (EN)"
        ])
        
        header_h = self.category_headings_table.horizontalHeader()
        header_h.setSectionResizeMode(QHeaderView.Interactive)
        self.category_headings_table.setColumnWidth(1, 100)
        
        headings_layout.addWidget(self.category_headings_table)
        
        # Buttons für Überschriften
        headings_btn_layout = QHBoxLayout()
        btn_refresh_headings = QPushButton("Aus Kürzel-Tabelle laden")
        btn_refresh_headings.setToolTip("Lädt alle verwendeten Kategorien aus der Kürzel-Tabelle")
        btn_refresh_headings.clicked.connect(self._load_categories_from_kurzel_table)
        headings_btn_layout.addWidget(btn_refresh_headings)
        headings_btn_layout.addStretch()
        headings_layout.addLayout(headings_btn_layout)
        
        layout.addWidget(headings_group)
        
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
        """Schadenskategorien: frei wachsende zweisprachige Tabelle."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.tbl_damage = QTableWidget(0, 3)
        self.tbl_damage.setHorizontalHeaderLabels(["#", "Deutsch", "Englisch"])
        self.tbl_damage.verticalHeader().setVisible(False)
        self.tbl_damage.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.tbl_damage.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.tbl_damage, 1)

        btns = QHBoxLayout()
        self.btn_damage_add = QPushButton("Hinzufügen")
        self.btn_damage_remove = QPushButton("Entfernen")
        btn_reset = QPushButton("Standardwerte wiederherstellen")
        self.btn_damage_add.clicked.connect(self._add_damage_row)
        self.btn_damage_remove.clicked.connect(self._remove_damage_row)
        btn_reset.clicked.connect(self._reset_damage_defaults)
        btns.addWidget(self.btn_damage_add)
        btns.addWidget(self.btn_damage_remove)
        btns.addStretch(1)
        btns.addWidget(btn_reset)
        layout.addLayout(btns)

        self.tab_widget.addTab(tab, "Schadenskategorien")
        self._load_damage_from_settings()

    def _create_image_types_tab(self):
        """Bildarten: frei wachsende zweisprachige Tabelle."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.tbl_images = QTableWidget(0, 3)
        self.tbl_images.setHorizontalHeaderLabels(["#", "Deutsch", "Englisch"])
        self.tbl_images.verticalHeader().setVisible(False)
        self.tbl_images.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.tbl_images.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.tbl_images, 1)

        btns = QHBoxLayout()
        self.btn_images_add = QPushButton("Hinzufügen")
        self.btn_images_remove = QPushButton("Entfernen")
        btn_reset = QPushButton("Standardwerte wiederherstellen")
        self.btn_images_add.clicked.connect(self._add_image_type_row)
        self.btn_images_remove.clicked.connect(self._remove_image_type_row)
        btn_reset.clicked.connect(self._reset_images_defaults)
        btns.addWidget(self.btn_images_add)
        btns.addWidget(self.btn_images_remove)
        btns.addStretch(1)
        btns.addWidget(btn_reset)
        layout.addLayout(btns)
        
        # Bildart → Schadenskategorien Zuordnung
        mapping_group = QGroupBox("Bildart-spezifische Schadenskategorien")
        mapping_layout = QVBoxLayout(mapping_group)
        
        info_mapping = QLabel(
            "Ordnen Sie jeder Bildart relevante Schadenskategorien zu.\n"
            "Bei der Bewertung werden nur die zur Bildart passenden Schäden angezeigt."
        )
        info_mapping.setWordWrap(True)
        mapping_layout.addWidget(info_mapping)
        
        # Splitter: Links Bildarten-Liste, Rechts Schadenskategorien-Auswahl
        from PySide6.QtWidgets import QSplitter, QListWidget
        mapping_splitter = QSplitter(Qt.Horizontal)
        
        # Links: Bildarten
        left_mapping = QWidget()
        left_mapping_layout = QVBoxLayout(left_mapping)
        left_mapping_layout.addWidget(QLabel("Bildart auswählen:"))
        
        self.mapping_imagetype_list = QListWidget()
        self.mapping_imagetype_list.currentItemChanged.connect(self._on_damage_mapping_imagetype_selected)
        left_mapping_layout.addWidget(self.mapping_imagetype_list)
        
        mapping_splitter.addWidget(left_mapping)
        
        # Rechts: Zugeordnete Schadenskategorien (Checkboxen)
        right_mapping = QWidget()
        right_mapping_layout = QVBoxLayout(right_mapping)
        
        self.mapping_label = QLabel("Schadenskategorien für: (Keine Bildart gewählt)")
        self.mapping_label.setStyleSheet("font-weight: bold;")
        right_mapping_layout.addWidget(self.mapping_label)
        
        # Scroll-Area für Checkboxen
        scroll_damage = QScrollArea()
        scroll_damage.setWidgetResizable(True)
        self.damage_checkboxes_widget = QWidget()
        self.damage_checkboxes_layout = QVBoxLayout(self.damage_checkboxes_widget)
        scroll_damage.setWidget(self.damage_checkboxes_widget)
        right_mapping_layout.addWidget(scroll_damage)
        
        mapping_splitter.addWidget(right_mapping)
        mapping_splitter.setStretchFactor(0, 1)
        mapping_splitter.setStretchFactor(1, 2)
        
        mapping_layout.addWidget(mapping_splitter)
        
        layout.addWidget(mapping_group)

        self.tab_widget.addTab(tab, "Bildarten")
        self._load_images_from_settings()
        self._load_damage_mapping()

    def _reset_damage_defaults(self):
        """Setzt Schadenskategorien auf zentrale Defaults."""
        try:
            defaults = self._get_default_damage_lists()
            self._populate_damage_table(defaults['de'], defaults['en'])
        except Exception as e:
            self._log.error("reset_damage_failed", extra={"event": "reset_damage_failed", "error": str(e)})

    def _reset_images_defaults(self):
        try:
            defaults = self._get_default_image_lists()
            self._populate_image_table(defaults['de'], defaults['en'])
        except Exception as e:
            self._log.error("reset_images_failed", extra={"event": "reset_images_failed", "error": str(e)})

    def _load_damage_from_settings(self):
        try:
            from .settings_manager import get_settings_manager
            sm = get_settings_manager()
            defaults = self._get_default_damage_lists()
            de = self._merge_defaults(defaults['de'], sm.get('damage_categories_de', []) or [])
            en = self._merge_defaults(defaults['en'], sm.get('damage_categories_en', []) or [])
            self._populate_damage_table(de, en)
        except Exception as e:
            self._log.error("load_damage_failed", extra={"event": "load_damage_failed", "error": str(e)})

    def _load_images_from_settings(self):
        try:
            from .settings_manager import get_settings_manager
            sm = get_settings_manager()
            defaults = self._get_default_image_lists()
            de = self._merge_defaults(defaults['de'], sm.get('image_types_de', []) or [])
            en = self._merge_defaults(defaults['en'], sm.get('image_types_en', []) or [])
            self._populate_image_table(de, en)
        except Exception as e:
            self._log.error("load_images_failed", extra={"event": "load_images_failed", "error": str(e)})

    # ------------------------------------------------------------------
    # Tabellen-Helfer
    def _populate_damage_table(self, de_list, en_list):
        self.tbl_damage.setRowCount(0)
        rows = max(len(de_list), len(en_list))
        if rows == 0:
            self._insert_table_row(self.tbl_damage)
        else:
            for idx in range(rows):
                de = de_list[idx] if idx < len(de_list) else ""
                en = en_list[idx] if idx < len(en_list) else ""
                self._insert_table_row(self.tbl_damage, de, en)
        self._renumber_table(self.tbl_damage)

    def _populate_image_table(self, de_list, en_list):
        self.tbl_images.setRowCount(0)
        rows = max(len(de_list), len(en_list))
        if rows == 0:
            self._insert_table_row(self.tbl_images)
        else:
            for idx in range(rows):
                de = de_list[idx] if idx < len(de_list) else ""
                en = en_list[idx] if idx < len(en_list) else ""
                self._insert_table_row(self.tbl_images, de, en)
        self._renumber_table(self.tbl_images)

    def _insert_table_row(self, table: QTableWidget, de_text: str = "", en_text: str = ""):
        row = table.rowCount()
        table.insertRow(row)
        index_item = QTableWidgetItem(str(row + 1))
        index_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        table.setItem(row, 0, index_item)
        table.setItem(row, 1, QTableWidgetItem(de_text))
        table.setItem(row, 2, QTableWidgetItem(en_text))

    def _renumber_table(self, table: QTableWidget):
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item is None:
                item = QTableWidgetItem()
                table.setItem(row, 0, item)
            item.setText(str(row + 1))
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

    def _add_damage_row(self):
        self._insert_table_row(self.tbl_damage)
        self._renumber_table(self.tbl_damage)

    def _remove_damage_row(self):
        row = self.tbl_damage.currentRow()
        if row < 0:
            row = self.tbl_damage.rowCount() - 1
        if row >= 0:
            self.tbl_damage.removeRow(row)
        if self.tbl_damage.rowCount() == 0:
            self._insert_table_row(self.tbl_damage)
        self._renumber_table(self.tbl_damage)

    def _add_image_type_row(self):
        self._insert_table_row(self.tbl_images)
        self._renumber_table(self.tbl_images)

    def _remove_image_type_row(self):
        row = self.tbl_images.currentRow()
        if row < 0:
            row = self.tbl_images.rowCount() - 1
        if row >= 0:
            self.tbl_images.removeRow(row)
        if self.tbl_images.rowCount() == 0:
            self._insert_table_row(self.tbl_images)
        self._renumber_table(self.tbl_images)

    # ------------------------------------------------------------------
    # Default-Helpers
    def _get_default_damage_lists(self):
        try:
            from config_manager import config_manager
            cfg = config_manager.config or {}
            dmg = cfg.get('damage_categories', {}) or {}
        except Exception:
            dmg = {}
        if not dmg:
            dmg = {
                'de': [
                    "Visuell keine Defekte", "Kratzer", "Zykloidische Kratzer",
                    "Stillstandsmarken", "Verschmierung", "Partikeldurchgang",
                    "Überrollmarken", "Pittings", "Sonstige"
                ],
                'en': [
                    "Visually no defects", "Scratches", "Cycloid Scratches",
                    "Standstill marks", "Smearing", "Particle passage",
                    "Overrolling Marks", "Pitting", "Others"
                ]
            }
        return dmg

    def _get_default_image_lists(self):
        try:
            from config_manager import config_manager
            cfg = config_manager.config or {}
            img = cfg.get('image_types', {}) or {}
        except Exception:
            img = {}
        if not img:
            img = {
                'de': ["Wälzkörper", "Innenring", "Außenring", "Käfig", "Zahnrad"],
                'en': ["Rolling Element", "Inner ring", "Outer ring", "Cage", "Gear"]
            }
        return img

    @staticmethod
    def _merge_defaults(defaults: list[str], current: list[str]) -> list[str]:
        seen = set()
        merged = []
        for src in (current, defaults):
            for item in src:
                if not isinstance(item, str):
                    continue
                trimmed = item.strip()
                if not trimmed or trimmed.lower() in seen:
                    continue
                merged.append(trimmed)
                seen.add(trimmed.lower())
        return merged
    
    # Kürzel-Verwaltung entfernt - wird nun über Extra → Kürzel-Manager verwaltet
    
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
    
    def _create_cover_tags_tab(self):
        """Titelbild-Tags verwalten"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        info_box = QLabel(
            "Titelbild-Tags definieren die Auswahl im Titelbilder-Tab."
            "\nPasse die Liste hier an, um neue Optionen hinzuzufügen oder nicht mehr benötigte Tags zu entfernen."
        )
        info_box.setWordWrap(True)
        info_box.setStyleSheet("color: #4a4a4a; margin-bottom: 6px;")
        layout.addWidget(info_box)

        self.cover_tags_table = QTableWidget(0, 1)
        self.cover_tags_table.setHorizontalHeaderLabels(["Tag"])
        self.cover_tags_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.cover_tags_table.verticalHeader().setVisible(False)
        layout.addWidget(self.cover_tags_table, 1)

        controls = QHBoxLayout()
        self.cover_tag_input = QLineEdit()
        self.cover_tag_input.setPlaceholderText("Neuer Tagâ€¦")
        self.cover_tag_input.returnPressed.connect(self._add_cover_tag)
        controls.addWidget(self.cover_tag_input, 1)

        self.btn_add_cover_tag = QPushButton("Hinzufügen")
        self.btn_add_cover_tag.clicked.connect(self._add_cover_tag)
        controls.addWidget(self.btn_add_cover_tag)

        self.btn_remove_cover_tag = QPushButton("Entfernen")
        self.btn_remove_cover_tag.clicked.connect(self._remove_selected_cover_tag)
        controls.addWidget(self.btn_remove_cover_tag)
        controls.addStretch(1)

        layout.addLayout(controls)
        layout.addStretch()
        self.tab_widget.addTab(tab, "Titelbild-Tags")
    
    def _create_text_snippets_tab(self):
        """Textbausteine verwalten (OCR-Tag-spezifisch)"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        info_box = QLabel(
            "Textbausteine definieren vorgefertigte Texte, die beim Beschreiben von Schäden "
            "eingefügt werden können.\nVerknüpfen Sie Textbausteine direkt mit OCR-Tags oder bündeln Sie mehrere Kürzel in Gruppen."
        )
        info_box.setWordWrap(True)
        info_box.setStyleSheet("color: #4a4a4a; margin-bottom: 6px;")
        layout.addWidget(info_box)
        
        self.snippet_tabs = QTabWidget()
        layout.addWidget(self.snippet_tabs)

        self._build_snippet_tag_tab()
        self._build_snippet_group_tab()

        self.tab_widget.addTab(tab, "Textbausteine")

        # Initiale Daten laden
        self._load_snippet_kurzel_list()
        self._load_snippet_group_list()

    def _build_snippet_tag_tab(self):
        from PySide6.QtWidgets import QSplitter, QListWidget

        tag_tab = QWidget()
        tag_layout = QVBoxLayout(tag_tab)

        splitter = QSplitter(Qt.Horizontal)

        # Links: Kürzel-Liste
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(QLabel("OCR-Tag auswählen:"))

        self.snippets_kurzel_list = QListWidget()
        self.snippets_kurzel_list.currentItemChanged.connect(self._on_snippet_kurzel_selected)
        left_layout.addWidget(self.snippets_kurzel_list)

        splitter.addWidget(left_widget)

        # Rechts: Textbausteine für gewähltes Kürzel
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        self.snippet_tag_label = QLabel("Textbausteine für: (Kein Tag gewählt)")
        self.snippet_tag_label.setStyleSheet("font-weight: bold;")
        right_layout.addWidget(self.snippet_tag_label)

        self.snippets_table = QTableWidget()
        self.snippets_table.setColumnCount(1)
        self.snippets_table.setHorizontalHeaderLabels(["Textbaustein"])
        self.snippets_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        right_layout.addWidget(self.snippets_table)

        snippets_controls = QHBoxLayout()

        self.snippet_input = QLineEdit()
        self.snippet_input.setPlaceholderText("Neuer Textbaustein...")
        self.snippet_input.returnPressed.connect(self._add_text_snippet)
        snippets_controls.addWidget(self.snippet_input, 1)

        btn_add_snippet = QPushButton("Hinzufügen")
        btn_add_snippet.clicked.connect(self._add_text_snippet)
        snippets_controls.addWidget(btn_add_snippet)

        btn_remove_snippet = QPushButton("Entfernen")
        btn_remove_snippet.clicked.connect(self._remove_text_snippet)
        snippets_controls.addWidget(btn_remove_snippet)

        btn_edit_snippet = QPushButton("Bearbeiten")
        btn_edit_snippet.clicked.connect(self._edit_text_snippet)
        snippets_controls.addWidget(btn_edit_snippet)

        right_layout.addLayout(snippets_controls)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        tag_layout.addWidget(splitter)

        self.snippet_tabs.addTab(tag_tab, "Tags")

    def _build_snippet_group_tab(self):
        from PySide6.QtWidgets import QListWidget

        group_tab = QWidget()
        layout = QHBoxLayout(group_tab)

        left_panel = QVBoxLayout()
        left_panel.addWidget(QLabel("Gruppe auswählen:"))

        self.snippet_group_list = QListWidget()
        self.snippet_group_list.currentItemChanged.connect(self._on_snippet_group_selected)
        left_panel.addWidget(self.snippet_group_list)

        group_buttons = QHBoxLayout()
        btn_add_group = QPushButton("Neue Gruppe")
        btn_add_group.clicked.connect(self._add_snippet_group)
        group_buttons.addWidget(btn_add_group)

        btn_rename_group = QPushButton("Umbenennen")
        btn_rename_group.clicked.connect(self._rename_snippet_group)
        group_buttons.addWidget(btn_rename_group)

        btn_remove_group = QPushButton("Löschen")
        btn_remove_group.clicked.connect(self._remove_snippet_group)
        group_buttons.addWidget(btn_remove_group)

        left_panel.addLayout(group_buttons)

        left_container = QWidget()
        left_container.setLayout(left_panel)
        layout.addWidget(left_container, 1)

        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)

        self.snippet_group_label = QLabel("Gruppe: (Keine Gruppe gewählt)")
        self.snippet_group_label.setStyleSheet("font-weight: bold;")
        right_layout.addWidget(self.snippet_group_label)

        self.group_tags_list = QListWidget()
        self.group_tags_list.itemChanged.connect(self._on_group_tag_item_changed)
        right_layout.addWidget(self.group_tags_list)

        # Snippet Tabelle für Gruppen
        self.group_snippets_table = QTableWidget()
        self.group_snippets_table.setColumnCount(1)
        self.group_snippets_table.setHorizontalHeaderLabels(["Textbaustein"])
        self.group_snippets_table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        right_layout.addWidget(self.group_snippets_table)

        group_snippet_controls = QHBoxLayout()

        self.group_snippet_input = QLineEdit()
        self.group_snippet_input.setPlaceholderText("Neuer Gruppen-Textbaustein...")
        self.group_snippet_input.returnPressed.connect(self._add_group_text_snippet)
        group_snippet_controls.addWidget(self.group_snippet_input, 1)

        btn_add_group_snippet = QPushButton("Hinzufügen")
        btn_add_group_snippet.clicked.connect(self._add_group_text_snippet)
        group_snippet_controls.addWidget(btn_add_group_snippet)

        btn_remove_group_snippet = QPushButton("Entfernen")
        btn_remove_group_snippet.clicked.connect(self._remove_group_text_snippet)
        group_snippet_controls.addWidget(btn_remove_group_snippet)

        btn_edit_group_snippet = QPushButton("Bearbeiten")
        btn_edit_group_snippet.clicked.connect(self._edit_group_text_snippet)
        group_snippet_controls.addWidget(btn_edit_group_snippet)

        right_layout.addLayout(group_snippet_controls)

        layout.addWidget(right_container, 2)

        self._group_tag_loading = False
        self.snippet_tabs.addTab(group_tab, "Gruppen")

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

    def _set_cover_tags(self, tags):
        tags = tags or []
        self.cover_tags_table.setRowCount(0)
        for tag in tags:
            if not isinstance(tag, str):
                continue
            trimmed = tag.strip()
            if not trimmed:
                continue
            row = self.cover_tags_table.rowCount()
            self.cover_tags_table.insertRow(row)
            self.cover_tags_table.setItem(row, 0, QTableWidgetItem(trimmed))

    def _collect_cover_tags(self):
        tags = []
        seen = set()
        for row in range(self.cover_tags_table.rowCount()):
            item = self.cover_tags_table.item(row, 0)
            if not item:
                continue
            tag = item.text().strip()
            if not tag:
                continue
            key = tag.lower()
            if key in seen:
                continue
            seen.add(key)
            tags.append(tag)
        return tags

    def _add_cover_tag(self):
        tag = self.cover_tag_input.text().strip()
        if not tag:
            return
        existing = {t.lower() for t in self._collect_cover_tags()}
        if tag.lower() in existing:
            self.cover_tag_input.clear()
            return
        row = self.cover_tags_table.rowCount()
        self.cover_tags_table.insertRow(row)
        self.cover_tags_table.setItem(row, 0, QTableWidgetItem(tag))
        self.cover_tag_input.clear()

    def _remove_selected_cover_tag(self):
        rows = {index.row() for index in self.cover_tags_table.selectedIndexes()}
        for row in sorted(rows, reverse=True):
            self.cover_tags_table.removeRow(row)
    
    def _on_snippet_kurzel_selected(self, current, previous):
        """Wird aufgerufen wenn ein Kürzel in der Textbausteine-Liste gewählt wird"""
        if not current:
            return
        
        tag = current.text().strip().upper()
        self.snippet_tag_label.setText(f"Textbausteine für: {tag}")
        
        config = self.settings_manager.get_text_snippet_config()
        tag_snippets = config.get('tags', {}).get(tag, [])
        
        # Tabelle füllen
        self.snippets_table.setRowCount(0)
        for snippet in tag_snippets:
            row = self.snippets_table.rowCount()
            self.snippets_table.insertRow(row)
            self.snippets_table.setItem(row, 0, QTableWidgetItem(snippet))
    
    def _add_text_snippet(self):
        """Fügt einen neuen Textbaustein hinzu"""
        current_item = self.snippets_kurzel_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Kein Tag gewählt", "Bitte wählen Sie zuerst ein OCR-Tag aus.")
            return
        
        tag = current_item.text().strip().upper()
        snippet_text = self.snippet_input.text().strip()
        
        if not snippet_text:
            return
        
        # Füge zur Tabelle hinzu
        row = self.snippets_table.rowCount()
        self.snippets_table.insertRow(row)
        self.snippets_table.setItem(row, 0, QTableWidgetItem(snippet_text))
        
        self.snippet_input.clear()
        
        # Speichere sofort
        self._save_text_snippets_for_tag(tag)
    
    def _remove_text_snippet(self):
        """Entfernt ausgewählten Textbaustein"""
        current_row = self.snippets_table.currentRow()
        if current_row < 0:
            return
        
        current_item = self.snippets_kurzel_list.currentItem()
        if not current_item:
            return
        
        tag = current_item.text().strip().upper()
        self.snippets_table.removeRow(current_row)
        
        # Speichere sofort
        self._save_text_snippets_for_tag(tag)
    
    def _edit_text_snippet(self):
        """Bearbeitet ausgewählten Textbaustein"""
        current_row = self.snippets_table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "Keine Auswahl", "Bitte wählen Sie einen Textbaustein zum Bearbeiten aus.")
            return
        
        current_item = self.snippets_kurzel_list.currentItem()
        if not current_item:
            return
        
        tag = current_item.text().strip().upper()
        old_text = self.snippets_table.item(current_row, 0).text()
        
        from PySide6.QtWidgets import QInputDialog
        new_text, ok = QInputDialog.getText(
            self, "Textbaustein bearbeiten",
            "Textbaustein bearbeiten:",
            text=old_text
        )
        
        if ok and new_text.strip():
            self.snippets_table.setItem(current_row, 0, QTableWidgetItem(new_text.strip()))
            self._save_text_snippets_for_tag(tag)
    
    def _save_text_snippets_for_tag(self, tag: str):
        """Speichert Textbausteine für ein Tag"""
        snippets = []
        for row in range(self.snippets_table.rowCount()):
            item = self.snippets_table.item(row, 0)
            if item:
                text = item.text().strip()
                if text:
                    snippets.append(text)
        
        config = self.settings_manager.get_text_snippet_config()
        if snippets:
            config.setdefault('tags', {})[tag] = snippets
        else:
            config.get('tags', {}).pop(tag, None)

        self.settings_manager.set_text_snippet_config(config)
    
    def _load_snippet_kurzel_list(self):
        """Lädt die Kürzel-Liste für Textbausteine"""
        try:
            codes = self._collect_all_kurzel_codes()
            self.snippets_kurzel_list.clear()
            for code in codes:
                self.snippets_kurzel_list.addItem(code)
            if self.snippets_kurzel_list.count() > 0:
                self.snippets_kurzel_list.setCurrentRow(0)
        except Exception as e:
            self._log.error("load_snippet_kurzel_list_failed", extra={"event": "load_snippet_kurzel_list_failed", "error": str(e)})

    def _collect_all_kurzel_codes(self):
        kurzel_table = self.settings_manager.get('kurzel_table', {}) or {}
        codes = {
            str(code).strip().upper()
            for code, data in kurzel_table.items()
            if str(code).strip() and data.get('active', True)
        }
        config = self.settings_manager.get_text_snippet_config()
        codes.update(config.get('tags', {}).keys())
        for group in config.get('groups', {}).values():
            for tag in group.get('tags', []):
                if tag:
                    codes.add(tag.upper())
        return sorted(codes)

    # ------------------------------------------------------------------
    # Gruppenspezifische Textbausteine
    def _load_snippet_group_list(self):
        try:
            config = self.settings_manager.get_text_snippet_config()
            groups = config.get('groups', {})
            self.snippet_group_list.clear()
            for name in sorted(groups.keys()):
                self.snippet_group_list.addItem(name)
            if self.snippet_group_list.count() > 0:
                self.snippet_group_list.setCurrentRow(0)
            self._refresh_group_tag_list()
        except Exception as e:
            self._log.error("load_snippet_group_list_failed", extra={"event": "load_snippet_group_list_failed", "error": str(e)})

    def _refresh_group_tag_list(self):
        tags = self._collect_all_kurzel_codes()
        self._group_tag_loading = True
        self.group_tags_list.blockSignals(True)
        self.group_tags_list.clear()
        for tag in tags:
            item = QListWidgetItem(tag)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.group_tags_list.addItem(item)
        self.group_tags_list.blockSignals(False)
        self._group_tag_loading = False

    def _on_snippet_group_selected(self, current, previous):
        if not current:
            self.snippet_group_label.setText("Gruppe: (Keine Gruppe gewählt)")
            self.group_snippets_table.setRowCount(0)
            return

        group_name = current.text().strip()
        self.snippet_group_label.setText(f"Gruppe: {group_name}")
        config = self.settings_manager.get_text_snippet_config()
        group_data = config.get('groups', {}).get(group_name, {'tags': [], 'snippets': []})

        self._apply_group_tag_selection(group_data.get('tags', []))
        self._set_group_snippets_table(group_data.get('snippets', []))

    def _add_snippet_group(self):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Neue Gruppe", "Name der Textbaustein-Gruppe:")
        if not ok:
            return
        cleaned = name.strip()
        if not cleaned:
            return

        config = self.settings_manager.get_text_snippet_config()
        groups = config.setdefault('groups', {})
        if cleaned in groups:
            QMessageBox.warning(self, "Gruppe existiert", "Es existiert bereits eine Gruppe mit diesem Namen.")
            return

        groups[cleaned] = {'tags': [], 'snippets': []}
        self.settings_manager.set_text_snippet_config(config)
        self._load_snippet_group_list()
        items = self.snippet_group_list.findItems(cleaned, Qt.MatchExactly)
        if items:
            self.snippet_group_list.setCurrentItem(items[0])

    def _rename_snippet_group(self):
        from PySide6.QtWidgets import QInputDialog
        current_item = self.snippet_group_list.currentItem()
        if not current_item:
            return
        old_name = current_item.text()
        new_name, ok = QInputDialog.getText(self, "Gruppe umbenennen", "Neuer Name:", text=old_name)
        if not ok:
            return
        cleaned = new_name.strip()
        if not cleaned or cleaned == old_name:
            return

        config = self.settings_manager.get_text_snippet_config()
        groups = config.setdefault('groups', {})
        if cleaned in groups:
            QMessageBox.warning(self, "Gruppe existiert", "Es existiert bereits eine Gruppe mit diesem Namen.")
            return

        data = groups.pop(old_name, {'tags': [], 'snippets': []})
        groups[cleaned] = data
        self.settings_manager.set_text_snippet_config(config)
        current_item.setText(cleaned)
        self.snippet_group_label.setText(f"Gruppe: {cleaned}")

    def _remove_snippet_group(self):
        current_item = self.snippet_group_list.currentItem()
        if not current_item:
            return
        name = current_item.text()
        confirm = QMessageBox.question(
            self,
            "Gruppe löschen",
            f"Soll die Gruppe '{name}' mit allen Textbausteinen gelöscht werden?"
        )
        if confirm != QMessageBox.Yes:
            return

        config = self.settings_manager.get_text_snippet_config()
        groups = config.setdefault('groups', {})
        if name in groups:
            del groups[name]
            self.settings_manager.set_text_snippet_config(config)
        self._load_snippet_group_list()

    def _apply_group_tag_selection(self, selected_tags):
        selected_set = {tag.upper() for tag in selected_tags or []}
        self._group_tag_loading = True
        self.group_tags_list.blockSignals(True)
        for index in range(self.group_tags_list.count()):
            item = self.group_tags_list.item(index)
            tag_code = item.text().strip().upper()
            item.setCheckState(Qt.Checked if tag_code in selected_set else Qt.Unchecked)
        self.group_tags_list.blockSignals(False)
        self._group_tag_loading = False

    def _on_group_tag_item_changed(self, item):
        if self._group_tag_loading:
            return
        current_item = self.snippet_group_list.currentItem()
        if not current_item:
            return
        group_name = current_item.text()
        self._save_current_group_tags(group_name)

    def _save_current_group_tags(self, group_name):
        selected_tags = []
        for index in range(self.group_tags_list.count()):
            item = self.group_tags_list.item(index)
            if item.checkState() == Qt.Checked:
                selected_tags.append(item.text().strip().upper())

        config = self.settings_manager.get_text_snippet_config()
        groups = config.setdefault('groups', {})
        group = groups.setdefault(group_name, {'tags': [], 'snippets': []})
        group['tags'] = selected_tags
        self.settings_manager.set_text_snippet_config(config)

    def _set_group_snippets_table(self, snippets):
        self.group_snippets_table.setRowCount(0)
        for snippet in snippets or []:
            row = self.group_snippets_table.rowCount()
            self.group_snippets_table.insertRow(row)
            self.group_snippets_table.setItem(row, 0, QTableWidgetItem(snippet))

    def _add_group_text_snippet(self):
        current_group = self.snippet_group_list.currentItem()
        if not current_group:
            QMessageBox.warning(self, "Keine Gruppe", "Bitte wählen Sie zuerst eine Gruppe aus.")
            return

        snippet_text = self.group_snippet_input.text().strip()
        if not snippet_text:
            return

        row = self.group_snippets_table.rowCount()
        self.group_snippets_table.insertRow(row)
        self.group_snippets_table.setItem(row, 0, QTableWidgetItem(snippet_text))
        self.group_snippet_input.clear()

        self._save_group_snippets(current_group.text(), self._collect_group_snippets())

    def _remove_group_text_snippet(self):
        current_group = self.snippet_group_list.currentItem()
        if not current_group:
            return
        current_row = self.group_snippets_table.currentRow()
        if current_row < 0:
            return
        self.group_snippets_table.removeRow(current_row)
        self._save_group_snippets(current_group.text(), self._collect_group_snippets())

    def _edit_group_text_snippet(self):
        from PySide6.QtWidgets import QInputDialog
        current_group = self.snippet_group_list.currentItem()
        if not current_group:
            return
        current_row = self.group_snippets_table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "Keine Auswahl", "Bitte wählen Sie einen Textbaustein zum Bearbeiten aus.")
            return
        old_text = self.group_snippets_table.item(current_row, 0).text()
        new_text, ok = QInputDialog.getText(
            self, "Gruppen-Textbaustein bearbeiten",
            "Textbaustein bearbeiten:",
            text=old_text
        )
        if ok and new_text.strip():
            self.group_snippets_table.setItem(current_row, 0, QTableWidgetItem(new_text.strip()))
            self._save_group_snippets(current_group.text(), self._collect_group_snippets())

    def _collect_group_snippets(self):
        snippets = []
        for row in range(self.group_snippets_table.rowCount()):
            item = self.group_snippets_table.item(row, 0)
            if not item:
                continue
            text = item.text().strip()
            if text:
                snippets.append(text)
        return snippets

    def _save_group_snippets(self, group_name, snippets):
        config = self.settings_manager.get_text_snippet_config()
        groups = config.setdefault('groups', {})
        group = groups.setdefault(group_name, {'tags': [], 'snippets': []})
        group['snippets'] = snippets
        self.settings_manager.set_text_snippet_config(config)

    def _load_settings(self):
        """Einstellungen aus SettingsManager laden"""
        from .settings_manager import get_settings_manager
        settings_manager = get_settings_manager()
        
        # Allgemeine Einstellungen
        # Dark Mode
        dark_mode = settings_manager.get("dark_mode", False)
        self.dark_mode_check.setChecked(dark_mode)
        
        language = settings_manager.get("language", "English")
        self.language_combo.setCurrentText(language)
        
        last_folder = settings_manager.get("last_folder", "")
        self.last_folder_edit.setText(last_folder)

        self._set_cover_tags(settings_manager.get_cover_tags())
        
        auto_save = settings_manager.get("auto_save", True)
        self.auto_save_check.setChecked(auto_save)
        
        save_interval = settings_manager.get("save_interval", 5)
        self.save_interval_spin.setValue(save_interval)
        
        # OCR-bezogene Einstellungen entfernt
        
        gallery_tag_size = settings_manager.get("gallery_tag_size", 8)
        self.gallery_tag_size_spin.setValue(gallery_tag_size)
        
        single_tag_size = settings_manager.get("single_tag_size", 9)
        self.single_tag_size_spin.setValue(single_tag_size)
        
        # Galerie-Raster laden
        gallery_grid = settings_manager.get("gallery_grid_mode", "Auto-Fit")
        idx = self.gallery_grid_combo.findText(gallery_grid)
        if idx >= 0:
            self.gallery_grid_combo.setCurrentIndex(idx)
        
        tag_opacity = settings_manager.get("tag_opacity", 200)
        self.tag_opacity_slider.setValue(tag_opacity)
        
        # Anzeige-Einstellungen
        theme = settings_manager.get("theme", "System")
        self.theme_combo.setCurrentText(theme)
        
        thumb_size = settings_manager.get("thumb_size", 160)
        self.thumb_size_spin.setValue(thumb_size)
        
        thumb_quality = settings_manager.get("thumb_quality", 85)
        self.thumb_quality_spin.setValue(thumb_quality)
        
        # image_quality ENTFERNT - Einzelbild-Ansicht zeigt immer Original-Qualität!
        
        zoom_factor = settings_manager.get("zoom_factor", 1.0)
        self.zoom_factor_spin.setValue(zoom_factor)
        
        gallery_overlay_icon_scale = settings_manager.get("gallery_overlay_icon_scale", 1.0)
        # Konvertiere von Faktor (1.0 = 100%) zu Prozent
        self.gallery_overlay_icon_scale_spin.setValue(gallery_overlay_icon_scale * 100)
        
        # Tastaturkürzel anzeigen
        show_shortcuts = settings_manager.get("show_keyboard_shortcuts", True)
        self.show_shortcuts_check.setChecked(show_shortcuts)
        # Tag Overlay Optionen laden
        tag_heading = settings_manager.get("tag_overlay_heading", True)
        self.tag_heading_check.setChecked(bool(tag_heading))
        order = str(settings_manager.get("tag_heading_order", "below") or "below").lower()
        self.tag_heading_order_combo.setCurrentIndex(0 if order=="below" else 1)
        
        # Crop-Einstellungen
        # Crop-Out Einstellungen entfernt
        
        # Kürzel-Tabelle laden - ENTFERNT (jetzt im KürzelManager)
        # Die Kürzel-Verwaltung erfolgt jetzt über den separaten Kürzel-Manager Dialog
        pass
        
        # Bewertungsregeln laden
        self._load_evaluation_rules()
    
    def _save_settings(self):
        """Einstellungen in SettingsManager speichern"""
        from .settings_manager import get_settings_manager
        settings_manager = get_settings_manager()
        
        # Allgemeine Einstellungen
        settings_manager.set("dark_mode", self.dark_mode_check.isChecked())
        settings_manager.set("language", self.language_combo.currentText())
        settings_manager.set("last_folder", self.last_folder_edit.text())
        settings_manager.set_cover_tags(self._collect_cover_tags())
        settings_manager.set("auto_save", self.auto_save_check.isChecked())
        settings_manager.set("save_interval", self.save_interval_spin.value())
        
        # OCR-bezogene Einstellungen entfernt
        settings_manager.set("gallery_tag_size", self.gallery_tag_size_spin.value())
        settings_manager.set("single_tag_size", self.single_tag_size_spin.value())
        settings_manager.set("tag_opacity", self.tag_opacity_slider.value())
        settings_manager.set("gallery_grid_mode", self.gallery_grid_combo.currentText())
        
        # Anzeige-Einstellungen
        settings_manager.set("theme", self.theme_combo.currentText())
        settings_manager.set("thumb_size", self.thumb_size_spin.value())
        settings_manager.set("thumb_quality", self.thumb_quality_spin.value())
        # image_quality ENTFERNT - Einzelbild-Ansicht zeigt immer Original-Qualität!
        settings_manager.set("zoom_factor", self.zoom_factor_spin.value())
        # Konvertiere von Prozent zu Faktor (100% = 1.0)
        settings_manager.set("gallery_overlay_icon_scale", self.gallery_overlay_icon_scale_spin.value() / 100.0)
        
        # Tastaturkürzel anzeigen
        settings_manager.set("show_keyboard_shortcuts", self.show_shortcuts_check.isChecked())
        
        # Crop-Einstellungen entfernt
        
        # Kürzel-Tabelle speichern - ENTFERNT (jetzt im KürzelManager)
        # Die Kürzel-Verwaltung erfolgt jetzt über den separaten Kürzel-Manager Dialog
        # Kürzel-Daten werden direkt im KürzelManager gespeichert
        
        # Mehrsprachige 5-Punkte-Listen (Schäden/Bildarten) speichern
        try:
            def _collect_column(table: QTableWidget, col: int):
                vals = []
                for r in range(table.rowCount()):
                    item = table.item(r, col)
                    txt = item.text().strip() if item and item.text() else ""
                    if txt:
                        vals.append(txt)
                return vals

            dmg_de = _collect_column(self.tbl_damage, 1)
            dmg_en = _collect_column(self.tbl_damage, 2)
            img_de = _collect_column(self.tbl_images, 1)
            img_en = _collect_column(self.tbl_images, 2)

            if dmg_de:
                settings_manager.set("damage_categories_de", dmg_de)
            if dmg_en:
                settings_manager.set("damage_categories_en", dmg_en)
            if img_de:
                settings_manager.set("image_types_de", img_de)
            if img_en:
                settings_manager.set("image_types_en", img_en)

            # Aktive Listen gem. Sprache
            lang_text = (settings_manager.get("language", "English") or "").lower()
            if lang_text.startswith("deutsch"):
                settings_manager.set("damage_categories", dmg_de or settings_manager.get("damage_categories", []))
                settings_manager.set("image_types", img_de or settings_manager.get("image_types", []))
            else:
                settings_manager.set("damage_categories", dmg_en or settings_manager.get("damage_categories", []))
                settings_manager.set("image_types", img_en or settings_manager.get("image_types", []))
        except Exception as e:
            self._log.error("lists_save_failed", extra={"event": "lists_save_failed", "error": str(e)})
        
        # Überschriften (DE/EN) speichern
        self._save_headings_to_settings()
        
        # Bewertungsregeln speichern
        self._save_evaluation_rules()
        
        # Kategorie-Überschriften speichern
        self._save_category_headings()
        
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
        cover_tags = self._collect_cover_tags()
        
        # Signal für Änderungen senden
        settings_dict = {
            "tag_overlay_heading": self.tag_heading_check.isChecked(),
            "tag_heading_order": ("below" if self.tag_heading_order_combo.currentIndex()==0 else "above"),
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
            # image_quality ENTFERNT - Einzelbild-Ansicht zeigt immer Original-Qualität!
            "zoom_factor": self.zoom_factor_spin.value(),
            "gallery_overlay_icon_scale": self.gallery_overlay_icon_scale_spin.value(),
            "show_keyboard_shortcuts": self.show_shortcuts_check.isChecked(),
            "cover_tags": cover_tags
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
            # image_quality ENTFERNT - Einzelbild-Ansicht zeigt immer Original-Qualität!
            "zoom_factor": self.zoom_factor_spin.value(),
            "gallery_overlay_icon_scale": self.gallery_overlay_icon_scale_spin.value(),
            "valid_kurzel": valid_kurzel
        }

    # --- Überschriften (DE/EN) ---
    def _create_headings_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        grp = QGroupBox("Überschriften")
        gl = QVBoxLayout(grp)
        self.tbl_headings = QTableWidget(0, 2)
        self.tbl_headings.setHorizontalHeaderLabels(["Deutsch", "Englisch"])
        self.tbl_headings.verticalHeader().setVisible(False)
        self.tbl_headings.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        gl.addWidget(self.tbl_headings)
        layout.addWidget(grp)
        layout.addStretch(1)
        self.tab_widget.addTab(tab, "Überschriften")

    def _load_headings_from_settings(self):
        from .settings_manager import get_settings_manager
        sm = get_settings_manager()
        order = sm.get('section_order', []) or []
        de = sm.get('section_titles_de', []) or []
        en = sm.get('section_titles_en', []) or []
        n = len(order)
        self.tbl_headings.setRowCount(n)
        for i in range(n):
            txt_de = de[i] if i < len(de) else (order[i] if i < len(order) else "")
            txt_en = en[i] if i < len(en) else ""
            self.tbl_headings.setItem(i, 0, QTableWidgetItem(txt_de))
            self.tbl_headings.setItem(i, 1, QTableWidgetItem(txt_en))

    def _save_headings_to_settings(self):
        try:
            from .settings_manager import get_settings_manager
            sm = get_settings_manager()
            if not hasattr(self, 'tbl_headings'):
                return
            rows = self.tbl_headings.rowCount()
            de_list, en_list = [], []
            for r in range(rows):
                it_de = self.tbl_headings.item(r, 0)
                it_en = self.tbl_headings.item(r, 1)
                de_list.append(it_de.text().strip() if it_de and it_de.text() else "")
                en_list.append(it_en.text().strip() if it_en and it_en.text() else "")
            sm.set('section_titles_de', de_list)
            sm.set('section_titles_en', en_list)
        except Exception:
            pass
    
    def _create_evaluation_logic_tab(self):
        """Logik-Editor für Bewertungskriterien"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Info-Text
        info = QLabel(
            "Definieren Sie Regeln, wann ein Bild als bewertet (grün) gilt.\n"
            "Eine Regel ist erfüllt wenn ALLE aktivierten Checkboxen zutreffen (AND).\n"
            "Ein Bild ist bewertet wenn MINDESTENS EINE Regel erfüllt ist (OR)."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #4a4a4a; margin-bottom: 10px; padding: 10px; background: #f0f0f0; border-radius: 5px;")
        layout.addWidget(info)
        
        # Matrix-Tabelle
        self.eval_rules_table = QTableWidget()
        self.eval_rules_table.setColumnCount(5)
        self.eval_rules_table.setHorizontalHeaderLabels([
            "Regelname",
            "use_image = 'nein'",
            "Schadenskategorie gesetzt",
            "GENE markiert",
            "Aktionen"
        ])
        
        # Spaltenbreiten
        header = self.eval_rules_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        
        self.eval_rules_table.setColumnWidth(1, 140)
        self.eval_rules_table.setColumnWidth(2, 180)
        self.eval_rules_table.setColumnWidth(3, 120)
        self.eval_rules_table.setColumnWidth(4, 80)
        
        layout.addWidget(self.eval_rules_table)
        
        # Buttons
        btn_layout = QHBoxLayout()
        btn_add_rule = QPushButton("Regel hinzufügen")
        btn_add_rule.clicked.connect(self._add_evaluation_rule)
        btn_layout.addWidget(btn_add_rule)
        btn_layout.addStretch()
        
        btn_reset = QPushButton("Auf Standard zurücksetzen")
        btn_reset.clicked.connect(self._reset_evaluation_rules)
        btn_layout.addWidget(btn_reset)
        
        layout.addLayout(btn_layout)
        
        self.tab_widget.addTab(tab, "Bewertungslogik")
    
    def _load_evaluation_rules(self):
        """Lädt Bewertungsregeln in die Tabelle"""
        rules = self.settings_manager.get('evaluation_rules', None)
        
        if not rules:
            # Standard-Regeln erstellen
            rules = [
                {
                    'name': 'Nicht verwenden markiert',
                    'use_image_no': True,
                    'has_damage_cat': False,
                    'gene_flagged': False
                },
                {
                    'name': 'Visuell keine Defekte',
                    'use_image_no': False,
                    'has_damage_cat': True,
                    'gene_flagged': False
                },
                {
                    'name': 'Gene markiert (Zweitmeinung)',
                    'use_image_no': False,
                    'has_damage_cat': False,
                    'gene_flagged': True
                }
            ]
        
        self.eval_rules_table.setRowCount(len(rules))
        
        for row, rule in enumerate(rules):
            # Regelname
            self.eval_rules_table.setItem(row, 0, QTableWidgetItem(rule.get('name', '')))
            
            # Checkboxen für Bedingungen
            for col, key in enumerate(['use_image_no', 'has_damage_cat', 'gene_flagged'], start=1):
                item = QTableWidgetItem()
                item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                item.setCheckState(Qt.Checked if rule.get(key, False) else Qt.Unchecked)
                self.eval_rules_table.setItem(row, col, item)
            
            # Löschen-Button
            btn_delete = QPushButton("Löschen")
            btn_delete.clicked.connect(lambda checked, r=row: self._delete_evaluation_rule(r))
            self.eval_rules_table.setCellWidget(row, 4, btn_delete)
    
    def _save_evaluation_rules(self):
        """Speichert Bewertungsregeln"""
        rules = []
        
        for row in range(self.eval_rules_table.rowCount()):
            name_item = self.eval_rules_table.item(row, 0)
            if not name_item:
                continue
            
            use_item = self.eval_rules_table.item(row, 1)
            damage_item = self.eval_rules_table.item(row, 2)
            gene_item = self.eval_rules_table.item(row, 3)
            
            rule = {
                'name': name_item.text(),
                'use_image_no': use_item.checkState() == Qt.Checked if use_item else False,
                'has_damage_cat': damage_item.checkState() == Qt.Checked if damage_item else False,
                'gene_flagged': gene_item.checkState() == Qt.Checked if gene_item else False
            }
            rules.append(rule)
        
        self.settings_manager.set('evaluation_rules', rules)
    
    def _add_evaluation_rule(self):
        """Fügt neue leere Regel hinzu"""
        row = self.eval_rules_table.rowCount()
        self.eval_rules_table.insertRow(row)
        
        # Regelname
        self.eval_rules_table.setItem(row, 0, QTableWidgetItem("Neue Regel"))
        
        # Checkboxen
        for col in range(1, 4):
            item = QTableWidgetItem()
            item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            item.setCheckState(Qt.Unchecked)
            self.eval_rules_table.setItem(row, col, item)
        
        # Löschen-Button
        btn_delete = QPushButton("Löschen")
        btn_delete.clicked.connect(lambda checked, r=row: self._delete_evaluation_rule(r))
        self.eval_rules_table.setCellWidget(row, 4, btn_delete)
    
    def _delete_evaluation_rule(self, row: int):
        """Löscht eine Regel"""
        if row < self.eval_rules_table.rowCount():
            self.eval_rules_table.removeRow(row)
            # Buttons neu verknüpfen nach dem Löschen
            self._refresh_delete_buttons()
    
    def _refresh_delete_buttons(self):
        """Aktualisiert die Löschen-Buttons nach Zeilen-Änderungen"""
        for row in range(self.eval_rules_table.rowCount()):
            btn_delete = QPushButton("Löschen")
            btn_delete.clicked.connect(lambda checked, r=row: self._delete_evaluation_rule(r))
            self.eval_rules_table.setCellWidget(row, 4, btn_delete)
    
    def _reset_evaluation_rules(self):
        """Setzt Regeln auf Standard zurück"""
        reply = QMessageBox.question(
            self, "Zurücksetzen",
            "Möchten Sie die Bewertungsregeln auf Standard zurücksetzen?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.settings_manager.set('evaluation_rules', None)
            self._load_evaluation_rules()
    
    def _load_categories_from_kurzel_table(self):
        """Lädt alle verwendeten Kategorien aus der Kürzel-Tabelle"""
        kurzel_table = self.settings_manager.get('kurzel_table', {}) or {}
        
        # Sammle alle eindeutigen Kategorien
        categories = {}
        for kurzel_code, data in kurzel_table.items():
            cat = data.get('category', '')
            if cat and cat not in categories:
                categories[cat] = {
                    'order': data.get('order', 999),
                    'heading_de': cat,  # Standard: Kategoriename
                    'heading_en': cat
                }
        
        # Bestehende Überschriften laden und mergen
        existing = self.settings_manager.get('category_headings', {}) or {}
        for cat, data in existing.items():
            if cat in categories:
                categories[cat] = data
        
        # Tabelle füllen
        self.category_headings_table.setRowCount(len(categories))
        row = 0
        for cat, data in sorted(categories.items(), key=lambda x: (x[1].get('order', 999), x[0])):
            self.category_headings_table.setItem(row, 0, QTableWidgetItem(cat))
            self.category_headings_table.setItem(row, 1, QTableWidgetItem(str(data.get('order', 0))))
            self.category_headings_table.setItem(row, 2, QTableWidgetItem(data.get('heading_de', cat)))
            self.category_headings_table.setItem(row, 3, QTableWidgetItem(data.get('heading_en', cat)))
            row += 1
    
    def _load_category_headings(self):
        """Lädt Kategorie-Überschriften in die Tabelle"""
        headings = self.settings_manager.get('category_headings', {}) or {}
        
        if not headings:
            # Beim ersten Mal: Aus Kürzel-Tabelle laden
            self._load_categories_from_kurzel_table()
            return
        
        self.category_headings_table.setRowCount(len(headings))
        row = 0
        for cat, data in sorted(headings.items(), key=lambda x: (x[1].get('order', 999), x[0])):
            self.category_headings_table.setItem(row, 0, QTableWidgetItem(cat))
            self.category_headings_table.setItem(row, 1, QTableWidgetItem(str(data.get('order', 0))))
            self.category_headings_table.setItem(row, 2, QTableWidgetItem(data.get('heading_de', cat)))
            self.category_headings_table.setItem(row, 3, QTableWidgetItem(data.get('heading_en', cat)))
            row += 1
    
    def _save_category_headings(self):
        """Speichert Kategorie-Überschriften"""
        headings = {}
        
        for row in range(self.category_headings_table.rowCount()):
            cat_item = self.category_headings_table.item(row, 0)
            order_item = self.category_headings_table.item(row, 1)
            de_item = self.category_headings_table.item(row, 2)
            en_item = self.category_headings_table.item(row, 3)
            
            if not cat_item:
                continue
            
            cat = cat_item.text()
            headings[cat] = {
                'order': int(order_item.text()) if order_item and order_item.text().isdigit() else 0,
                'heading_de': de_item.text() if de_item else cat,
                'heading_en': en_item.text() if en_item else cat
            }
        
        self.settings_manager.set('category_headings', headings)
    
    def _on_damage_mapping_imagetype_selected(self, current, previous):
        """Wird aufgerufen wenn Bildart in Mapping-Liste gewählt wird"""
        if not current:
            return
        
        image_type = current.text()
        self.mapping_label.setText(f"Schadenskategorien für: {image_type}")
        
        # Lade zugeordnete Schadenskategorien
        mapping = self.settings_manager.get('image_type_damage_mapping', {}) or {}
        assigned_damages = mapping.get(image_type, [])
        
        # Hole alle verfügbaren Schadenskategorien
        all_damages = self.settings_manager.get_damage_categories()
        
        # Lösche alte Checkboxen
        while self.damage_checkboxes_layout.count():
            item = self.damage_checkboxes_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Erstelle Checkboxen für alle Schadenskategorien
        for damage in all_damages:
            checkbox = QCheckBox(damage)
            checkbox.setChecked(damage in assigned_damages)
            checkbox.toggled.connect(lambda checked, img=image_type: self._save_damage_mapping_for_type(img))
            self.damage_checkboxes_layout.addWidget(checkbox)
        
        self.damage_checkboxes_layout.addStretch()
    
    def _save_damage_mapping_for_type(self, image_type: str):
        """Speichert Schadenskategorien-Zuordnung für eine Bildart"""
        # Sammle alle markierten Checkboxen
        assigned_damages = []
        for i in range(self.damage_checkboxes_layout.count()):
            widget = self.damage_checkboxes_layout.itemAt(i).widget()
            if isinstance(widget, QCheckBox) and widget.isChecked():
                assigned_damages.append(widget.text())
        
        # Speichere Mapping
        mapping = self.settings_manager.get('image_type_damage_mapping', {}) or {}
        if assigned_damages:
            mapping[image_type] = assigned_damages
        elif image_type in mapping:
            del mapping[image_type]
        
        self.settings_manager.set('image_type_damage_mapping', mapping)
    
    def _load_damage_mapping(self):
        """Lädt Bildart-Liste für Damage-Mapping"""
        # Lade alle Bildarten
        image_types = self.settings_manager.get_image_types()
        
        self.mapping_imagetype_list.clear()
        for img_type in image_types:
            self.mapping_imagetype_list.addItem(img_type)
        
        # Wähle ersten Eintrag
        if self.mapping_imagetype_list.count() > 0:
            self.mapping_imagetype_list.setCurrentRow(0)
