# -*- coding: utf-8 -*-
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, 
    QHeaderView, QPushButton, QLineEdit, QComboBox, QTextEdit, QCheckBox,
    QGroupBox, QFormLayout, QLabel, QMessageBox, QFileDialog, QSplitter,
    QTabWidget, QWidget, QScrollArea, QFrame, QSpinBox
)
from PySide6.QtCore import Qt, Signal, QSettings
from PySide6.QtGui import QFont, QColor
from utils_logging import get_logger
from datetime import datetime
import csv
import json
import os


class KurzelManagerDialog(QDialog):
    """Hauptdialog für Kürzel-Management"""
    
    kurzelChanged = Signal()  # Signal für Änderungen
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._log = get_logger('app', {"module": "qtui.kurzel_manager"})
        self._log.info("module_started", extra={"event": "module_started"})
        
        self.setWindowTitle("Kürzel-Manager")
        self.setModal(True)
        self.resize(1000, 700)
        
        # Settings Manager
        from .settings_manager import get_settings_manager
        self.settings_manager = get_settings_manager()
        
        # Kürzel-Daten laden
        self.kurzel_data = self.settings_manager.get('kurzel_table', {})
        
        self._create_ui()
        self._load_kurzel_data()
        
    def _create_ui(self):
        """Erstellt die Benutzeroberfläche"""
        layout = QVBoxLayout(self)
        
        # Haupt-Tabs
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # Tab 1: Kürzel-Tabelle
        self._create_kurzel_table_tab()
        
        # Tab 2: Alternative Kürzel
        self._create_alternative_kurzel_tab()
        
        # Tab 3: Kategorien
        self._create_categories_tab()
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.btn_import_csv = QPushButton("CSV Importieren")
        self.btn_export_csv = QPushButton("CSV Exportieren")
        self.btn_import_json = QPushButton("JSON Importieren")
        self.btn_export_json = QPushButton("JSON Exportieren")
        
        button_layout.addWidget(self.btn_import_csv)
        button_layout.addWidget(self.btn_export_csv)
        button_layout.addWidget(self.btn_import_json)
        button_layout.addWidget(self.btn_export_json)
        button_layout.addStretch()
        
        self.btn_close = QPushButton("Schließen")
        button_layout.addWidget(self.btn_close)
        
        layout.addLayout(button_layout)
        
        # Verbindungen
        self.btn_import_csv.clicked.connect(self._import_csv)
        self.btn_export_csv.clicked.connect(self._export_csv)
        self.btn_import_json.clicked.connect(self._import_json)
        self.btn_export_json.clicked.connect(self._export_json)
        self.btn_close.clicked.connect(self.accept)
        
    def _create_kurzel_table_tab(self):
        """Erstellt den Tab für die Kürzel-Tabelle"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Toolbar
        toolbar_layout = QHBoxLayout()
        
        self.btn_add_kurzel = QPushButton("Neues Kürzel")
        self.btn_edit_kurzel = QPushButton("Bearbeiten")
        self.btn_delete_kurzel = QPushButton("Löschen")
        self.btn_refresh = QPushButton("Aktualisieren")
        
        toolbar_layout.addWidget(self.btn_add_kurzel)
        toolbar_layout.addWidget(self.btn_edit_kurzel)
        toolbar_layout.addWidget(self.btn_delete_kurzel)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.btn_refresh)
        
        layout.addLayout(toolbar_layout)
        
        # Kürzel-Tabelle
        self.kurzel_table = QTableWidget()
        self.kurzel_table.setColumnCount(8)
        self.kurzel_table.setHorizontalHeaderLabels([
            "Kürzel", "Name (DE)", "Name (EN)", "Kategorie", 
            "Bildart", "Beschreibung (DE)", "Beschreibung (EN)", "Aktiv"
        ])
        
        # Spaltenbreiten setzen
        header = self.kurzel_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)  # Kürzel
        header.setSectionResizeMode(1, QHeaderView.Stretch)  # Name DE
        header.setSectionResizeMode(2, QHeaderView.Stretch)  # Name EN
        header.setSectionResizeMode(3, QHeaderView.Fixed)    # Kategorie
        header.setSectionResizeMode(4, QHeaderView.Fixed)   # Bildart
        header.setSectionResizeMode(5, QHeaderView.Stretch) # Beschreibung DE
        header.setSectionResizeMode(6, QHeaderView.Stretch) # Beschreibung EN
        header.setSectionResizeMode(7, QHeaderView.Fixed)   # Aktiv
        
        self.kurzel_table.setColumnWidth(0, 80)   # Kürzel
        self.kurzel_table.setColumnWidth(3, 100)  # Kategorie
        self.kurzel_table.setColumnWidth(4, 120)  # Bildart
        self.kurzel_table.setColumnWidth(7, 60)   # Aktiv
        
        # Doppelklick für Bearbeitung
        self.kurzel_table.itemDoubleClicked.connect(self._edit_selected_kurzel)
        
        layout.addWidget(self.kurzel_table)
        
        # Verbindungen
        self.btn_add_kurzel.clicked.connect(self._add_new_kurzel)
        self.btn_edit_kurzel.clicked.connect(self._edit_selected_kurzel)
        self.btn_delete_kurzel.clicked.connect(self._delete_selected_kurzel)
        self.btn_refresh.clicked.connect(self._load_kurzel_data)
        
        self.tab_widget.addTab(tab, "Kürzel-Tabelle")
        
    def _create_alternative_kurzel_tab(self):
        """Erstellt den Tab für Alternative Kürzel"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Info
        info_label = QLabel("Alternative Kürzel definieren alternative Schreibweisen für bestehende Kürzel.")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Alternative Kürzel-Tabelle
        self.alt_kurzel_table = QTableWidget()
        self.alt_kurzel_table.setColumnCount(2)
        self.alt_kurzel_table.setHorizontalHeaderLabels(["Original Kürzel", "Alternative Schreibweise"])
        
        header = self.alt_kurzel_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        
        layout.addWidget(self.alt_kurzel_table)
        
        # Buttons
        alt_button_layout = QHBoxLayout()
        self.btn_add_alt = QPushButton("Alternative hinzufügen")
        self.btn_remove_alt = QPushButton("Alternative entfernen")
        
        alt_button_layout.addWidget(self.btn_add_alt)
        alt_button_layout.addWidget(self.btn_remove_alt)
        alt_button_layout.addStretch()
        
        layout.addLayout(alt_button_layout)
        
        # Verbindungen
        self.btn_add_alt.clicked.connect(self._add_alternative_kurzel)
        self.btn_remove_alt.clicked.connect(self._remove_alternative_kurzel)
        
        self.tab_widget.addTab(tab, "Alternative Kürzel")
        
    def _create_categories_tab(self):
        """Erstellt den Tab für Kategorien-Verwaltung"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Kategorien-Gruppe
        categories_group = QGroupBox("Kategorien")
        categories_layout = QVBoxLayout(categories_group)
        
        # Kategorien-Liste
        self.categories_list = QTableWidget()
        self.categories_list.setColumnCount(3)
        self.categories_list.setHorizontalHeaderLabels(["Kategorie", "Beschreibung", "Anzahl Kürzel"])
        
        header = self.categories_list.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        self.categories_list.setColumnWidth(2, 100)
        
        categories_layout.addWidget(self.categories_list)
        
        # Kategorie-Buttons
        cat_button_layout = QHBoxLayout()
        self.btn_add_category = QPushButton("Kategorie hinzufügen")
        self.btn_edit_category = QPushButton("Kategorie bearbeiten")
        self.btn_delete_category = QPushButton("Kategorie löschen")
        
        cat_button_layout.addWidget(self.btn_add_category)
        cat_button_layout.addWidget(self.btn_edit_category)
        cat_button_layout.addWidget(self.btn_delete_category)
        cat_button_layout.addStretch()
        
        categories_layout.addLayout(cat_button_layout)
        layout.addWidget(categories_group)
        
        # Verbindungen
        self.btn_add_category.clicked.connect(self._add_category)
        self.btn_edit_category.clicked.connect(self._edit_category)
        self.btn_delete_category.clicked.connect(self._delete_category)
        
        self.tab_widget.addTab(tab, "Kategorien")
        
    def _load_kurzel_data(self):
        """Lädt die Kürzel-Daten in die Tabelle"""
        self.kurzel_data = self.settings_manager.get('kurzel_table', {})
        
        # Tabelle leeren
        self.kurzel_table.setRowCount(0)
        
        # Daten laden
        for kurzel_code, data in self.kurzel_data.items():
            row = self.kurzel_table.rowCount()
            self.kurzel_table.insertRow(row)
            
            # Kürzel-Code
            self.kurzel_table.setItem(row, 0, QTableWidgetItem(kurzel_code))
            
            # Name DE
            self.kurzel_table.setItem(row, 1, QTableWidgetItem(data.get('name_de', '')))
            
            # Name EN
            self.kurzel_table.setItem(row, 2, QTableWidgetItem(data.get('name_en', '')))
            
            # Kategorie
            self.kurzel_table.setItem(row, 3, QTableWidgetItem(data.get('category', '')))
            
            # Bildart
            self.kurzel_table.setItem(row, 4, QTableWidgetItem(data.get('image_type', '')))
            
            # Beschreibung DE
            self.kurzel_table.setItem(row, 5, QTableWidgetItem(data.get('description_de', '')))
            
            # Beschreibung EN
            self.kurzel_table.setItem(row, 6, QTableWidgetItem(data.get('description_en', '')))
            
            # Aktiv (Checkbox)
            active_item = QTableWidgetItem()
            active_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            active_item.setCheckState(Qt.Checked if data.get('active', True) else Qt.Unchecked)
            self.kurzel_table.setItem(row, 7, active_item)
        
        # Alternative Kürzel laden
        self._load_alternative_kurzel()
        
        # Kategorien laden
        self._load_categories()
        
    def _load_alternative_kurzel(self):
        """Lädt die Alternative Kürzel"""
        alt_kurzel = self.settings_manager.get('alternative_kurzel', {})
        
        self.alt_kurzel_table.setRowCount(0)
        
        for original, alternative in alt_kurzel.items():
            row = self.alt_kurzel_table.rowCount()
            self.alt_kurzel_table.insertRow(row)
            
            self.alt_kurzel_table.setItem(row, 0, QTableWidgetItem(original))
            self.alt_kurzel_table.setItem(row, 1, QTableWidgetItem(alternative))
            
    def _load_categories(self):
        """Lädt die Kategorien"""
        categories = self.settings_manager.get('kurzel_categories', {})
        
        self.categories_list.setRowCount(0)
        
        for cat_name, cat_data in categories.items():
            row = self.categories_list.rowCount()
            self.categories_list.insertRow(row)
            
            # Anzahl Kürzel in dieser Kategorie zählen
            count = sum(1 for data in self.kurzel_data.values() 
                       if data.get('category', '') == cat_name)
            
            self.categories_list.setItem(row, 0, QTableWidgetItem(cat_name))
            self.categories_list.setItem(row, 1, QTableWidgetItem(cat_data.get('description', '')))
            self.categories_list.setItem(row, 2, QTableWidgetItem(str(count)))
            
    def _add_new_kurzel(self):
        """Öffnet Dialog für neues Kürzel"""
        dialog = KurzelEditDialog(self)
        if dialog.exec() == QDialog.Accepted:
            kurzel_data = dialog.get_kurzel_data()
            if kurzel_data:
                self.kurzel_data[kurzel_data['kurzel_code']] = kurzel_data
                self.settings_manager.set('kurzel_table', self.kurzel_data)
                self._load_kurzel_data()
                self.kurzelChanged.emit()
                
    def _edit_selected_kurzel(self):
        """Bearbeitet das ausgewählte Kürzel"""
        current_row = self.kurzel_table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "Keine Auswahl", "Bitte wählen Sie ein Kürzel zum Bearbeiten aus.")
            return
            
        kurzel_code = self.kurzel_table.item(current_row, 0).text()
        if kurzel_code in self.kurzel_data:
            dialog = KurzelEditDialog(self, self.kurzel_data[kurzel_code])
            if dialog.exec() == QDialog.Accepted:
                kurzel_data = dialog.get_kurzel_data()
                if kurzel_data:
                    self.kurzel_data[kurzel_code] = kurzel_data
                    self.settings_manager.set('kurzel_table', self.kurzel_data)
                    self._load_kurzel_data()
                    self.kurzelChanged.emit()
                    
    def _delete_selected_kurzel(self):
        """Löscht das ausgewählte Kürzel"""
        current_row = self.kurzel_table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "Keine Auswahl", "Bitte wählen Sie ein Kürzel zum Löschen aus.")
            return
            
        kurzel_code = self.kurzel_table.item(current_row, 0).text()
        
        reply = QMessageBox.question(
            self, "Kürzel löschen", 
            f"Möchten Sie das Kürzel '{kurzel_code}' wirklich löschen?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            if kurzel_code in self.kurzel_data:
                del self.kurzel_data[kurzel_code]
                self.settings_manager.set('kurzel_table', self.kurzel_data)
                self._load_kurzel_data()
                self.kurzelChanged.emit()
                
    def _add_alternative_kurzel(self):
        """Fügt eine Alternative Kürzel hinzu"""
        dialog = AlternativeKurzelDialog(self)
        if dialog.exec() == QDialog.Accepted:
            original, alternative = dialog.get_values()
            if original and alternative:
                alt_kurzel = self.settings_manager.get('alternative_kurzel', {})
                alt_kurzel[original] = alternative
                self.settings_manager.set('alternative_kurzel', alt_kurzel)
                self._load_alternative_kurzel()
                
    def _remove_alternative_kurzel(self):
        """Entfernt eine Alternative Kürzel"""
        current_row = self.alt_kurzel_table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "Keine Auswahl", "Bitte wählen Sie eine Alternative zum Entfernen aus.")
            return
            
        original = self.alt_kurzel_table.item(current_row, 0).text()
        
        reply = QMessageBox.question(
            self, "Alternative entfernen", 
            f"Möchten Sie die Alternative '{original}' wirklich entfernen?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            alt_kurzel = self.settings_manager.get('alternative_kurzel', {})
            if original in alt_kurzel:
                del alt_kurzel[original]
                self.settings_manager.set('alternative_kurzel', alt_kurzel)
                self._load_alternative_kurzel()
                
    def _add_category(self):
        """Fügt eine neue Kategorie hinzu"""
        dialog = CategoryEditDialog(self)
        if dialog.exec() == QDialog.Accepted:
            cat_name, cat_description = dialog.get_values()
            if cat_name:
                categories = self.settings_manager.get('kurzel_categories', {})
                categories[cat_name] = {'description': cat_description}
                self.settings_manager.set('kurzel_categories', categories)
                self._load_categories()
                
    def _edit_category(self):
        """Bearbeitet eine Kategorie"""
        current_row = self.categories_list.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "Keine Auswahl", "Bitte wählen Sie eine Kategorie zum Bearbeiten aus.")
            return
            
        cat_name = self.categories_list.item(current_row, 0).text()
        categories = self.settings_manager.get('kurzel_categories', {})
        
        if cat_name in categories:
            dialog = CategoryEditDialog(self, cat_name, categories[cat_name].get('description', ''))
            if dialog.exec() == QDialog.Accepted:
                new_name, new_description = dialog.get_values()
                if new_name and new_name != cat_name:
                    # Kategorie umbenennen
                    categories[new_name] = {'description': new_description}
                    del categories[cat_name]
                    
                    # Alle Kürzel mit alter Kategorie aktualisieren
                    for kurzel_data in self.kurzel_data.values():
                        if kurzel_data.get('category') == cat_name:
                            kurzel_data['category'] = new_name
                    
                    self.settings_manager.set('kurzel_categories', categories)
                    self.settings_manager.set('kurzel_table', self.kurzel_data)
                    self._load_categories()
                    self._load_kurzel_data()
                    
    def _delete_category(self):
        """Löscht eine Kategorie"""
        current_row = self.categories_list.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "Keine Auswahl", "Bitte wählen Sie eine Kategorie zum Löschen aus.")
            return
            
        cat_name = self.categories_list.item(current_row, 0).text()
        
        # Prüfen ob Kategorie verwendet wird
        count = sum(1 for data in self.kurzel_data.values() 
                   if data.get('category', '') == cat_name)
        
        if count > 0:
            QMessageBox.warning(
                self, "Kategorie in Verwendung", 
                f"Die Kategorie '{cat_name}' wird noch von {count} Kürzel(n) verwendet. "
                "Bitte ändern Sie zuerst die Kategorie der Kürzel."
            )
            return
            
        reply = QMessageBox.question(
            self, "Kategorie löschen", 
            f"Möchten Sie die Kategorie '{cat_name}' wirklich löschen?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            categories = self.settings_manager.get('kurzel_categories', {})
            if cat_name in categories:
                del categories[cat_name]
                self.settings_manager.set('kurzel_categories', categories)
                self._load_categories()
                
    def _import_csv(self):
        """Importiert Kürzel aus CSV-Datei"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "CSV-Datei importieren", "", "CSV-Dateien (*.csv)"
        )
        
        if not file_path:
            return
            
        try:
            imported_count = 0
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if 'kurzel_code' in row and row['kurzel_code']:
                        kurzel_data = {
                            'kurzel_code': row['kurzel_code'],
                            'name_de': row.get('name_de', ''),
                            'name_en': row.get('name_en', ''),
                            'category': row.get('category', ''),
                            'image_type': row.get('image_type', ''),
                            'description_de': row.get('description_de', ''),
                            'description_en': row.get('description_en', ''),
                            'active': row.get('active', 'true').lower() == 'true',
                            'created_date': datetime.now().isoformat(),
                            'last_modified': datetime.now().isoformat()
                        }
                        
                        self.kurzel_data[row['kurzel_code']] = kurzel_data
                        imported_count += 1
                        
            self.settings_manager.set('kurzel_table', self.kurzel_data)
            self._load_kurzel_data()
            
            QMessageBox.information(
                self, "Import erfolgreich", 
                f"{imported_count} Kürzel wurden erfolgreich importiert."
            )
            
        except Exception as e:
            QMessageBox.critical(self, "Import fehlgeschlagen", f"Fehler beim Import: {str(e)}")
            
    def _export_csv(self):
        """Exportiert Kürzel als CSV-Datei"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "CSV-Datei exportieren", "kurzel_export.csv", "CSV-Dateien (*.csv)"
        )
        
        if not file_path:
            return
            
        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                if self.kurzel_data:
                    fieldnames = [
                        'kurzel_code', 'name_de', 'name_en', 'category', 
                        'image_type', 'description_de', 'description_en', 'active'
                    ]
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    
                    for kurzel_data in self.kurzel_data.values():
                        writer.writerow(kurzel_data)
                        
            QMessageBox.information(self, "Export erfolgreich", "Kürzel wurden erfolgreich exportiert.")
            
        except Exception as e:
            QMessageBox.critical(self, "Export fehlgeschlagen", f"Fehler beim Export: {str(e)}")
            
    def _import_json(self):
        """Importiert Kürzel aus JSON-Datei"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "JSON-Datei importieren", "", "JSON-Dateien (*.json)"
        )
        
        if not file_path:
            return
            
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                imported_data = json.load(f)
                
            if isinstance(imported_data, dict):
                self.kurzel_data.update(imported_data)
                self.settings_manager.set('kurzel_table', self.kurzel_data)
                self._load_kurzel_data()
                
                QMessageBox.information(
                    self, "Import erfolgreich", 
                    f"{len(imported_data)} Kürzel wurden erfolgreich importiert."
                )
            else:
                QMessageBox.warning(self, "Ungültiges Format", "Die JSON-Datei hat ein ungültiges Format.")
                
        except Exception as e:
            QMessageBox.critical(self, "Import fehlgeschlagen", f"Fehler beim Import: {str(e)}")
            
    def _export_json(self):
        """Exportiert Kürzel als JSON-Datei"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "JSON-Datei exportieren", "kurzel_export.json", "JSON-Dateien (*.json)"
        )
        
        if not file_path:
            return
            
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.kurzel_data, f, indent=2, ensure_ascii=False)
                
            QMessageBox.information(self, "Export erfolgreich", "Kürzel wurden erfolgreich exportiert.")
            
        except Exception as e:
            QMessageBox.critical(self, "Export fehlgeschlagen", f"Fehler beim Export: {str(e)}")


class KurzelEditDialog(QDialog):
    """Dialog zum Bearbeiten/Hinzufügen von Kürzeln"""
    
    def __init__(self, parent=None, kurzel_data=None):
        super().__init__(parent)
        self.setWindowTitle("Kürzel bearbeiten" if kurzel_data else "Neues Kürzel")
        self.setModal(True)
        self.resize(500, 600)
        
        self.kurzel_data = kurzel_data or self._get_default_structure()
        
        self._create_ui()
        self._load_data()
        
    def _get_default_structure(self):
        """Gibt die Standard-Struktur für ein Kürzel zurück"""
        return {
            'kurzel_code': '',
            'name_de': '',
            'name_en': '',
            'category': '',
            'image_type': '',
            'description_de': '',
            'description_en': '',
            'active': True,
            'created_date': datetime.now().isoformat(),
            'last_modified': datetime.now().isoformat()
        }
        
    def _create_ui(self):
        """Erstellt die Benutzeroberfläche"""
        layout = QVBoxLayout(self)
        
        # Scrollbar für lange Formulare
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        
        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)
        
        # Eingabefelder
        self.kurzel_code_edit = QLineEdit()
        self.name_de_edit = QLineEdit()
        self.name_en_edit = QLineEdit()
        self.category_combo = QComboBox()
        self.image_type_combo = QComboBox()
        self.description_de_edit = QTextEdit()
        self.description_de_edit.setMaximumHeight(80)
        self.description_en_edit = QTextEdit()
        self.description_en_edit.setMaximumHeight(80)
        self.active_checkbox = QCheckBox("Aktiv")
        
        # Kategorien und Bildarten laden
        self._load_categories_and_types()
        
        # Formular zusammenbauen
        form_layout.addRow("Kürzel-Code:", self.kurzel_code_edit)
        form_layout.addRow("Name (Deutsch):", self.name_de_edit)
        form_layout.addRow("Name (Englisch):", self.name_en_edit)
        form_layout.addRow("Kategorie:", self.category_combo)
        form_layout.addRow("Bildart:", self.image_type_combo)
        form_layout.addRow("Beschreibung (Deutsch):", self.description_de_edit)
        form_layout.addRow("Beschreibung (Englisch):", self.description_en_edit)
        form_layout.addRow("", self.active_checkbox)
        
        scroll.setWidget(form_widget)
        layout.addWidget(scroll)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.btn_ok = QPushButton("OK")
        self.btn_cancel = QPushButton("Abbrechen")
        
        button_layout.addStretch()
        button_layout.addWidget(self.btn_ok)
        button_layout.addWidget(self.btn_cancel)
        
        layout.addLayout(button_layout)
        
        # Verbindungen
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        
    def _load_categories_and_types(self):
        """Lädt verfügbare Kategorien und Bildarten"""
        from .settings_manager import get_settings_manager
        settings_manager = get_settings_manager()
        
        # Kategorien laden
        categories = settings_manager.get('kurzel_categories', {})
        self.category_combo.addItems([''] + list(categories.keys()))
        
        # Bildarten laden
        image_types = settings_manager.get('image_types', [])
        self.image_type_combo.addItems([''] + image_types)
        
    def _load_data(self):
        """Lädt die Kürzel-Daten in die Felder"""
        self.kurzel_code_edit.setText(self.kurzel_data.get('kurzel_code', ''))
        self.name_de_edit.setText(self.kurzel_data.get('name_de', ''))
        self.name_en_edit.setText(self.kurzel_data.get('name_en', ''))
        
        category = self.kurzel_data.get('category', '')
        if category:
            index = self.category_combo.findText(category)
            if index >= 0:
                self.category_combo.setCurrentIndex(index)
                
        image_type = self.kurzel_data.get('image_type', '')
        if image_type:
            index = self.image_type_combo.findText(image_type)
            if index >= 0:
                self.image_type_combo.setCurrentIndex(index)
                
        self.description_de_edit.setPlainText(self.kurzel_data.get('description_de', ''))
        self.description_en_edit.setPlainText(self.kurzel_data.get('description_en', ''))
        self.active_checkbox.setChecked(self.kurzel_data.get('active', True))
        
    def get_kurzel_data(self):
        """Gibt die Kürzel-Daten zurück"""
        kurzel_code = self.kurzel_code_edit.text().strip()
        if not kurzel_code:
            QMessageBox.warning(self, "Ungültige Eingabe", "Kürzel-Code darf nicht leer sein.")
            return None
            
        return {
            'kurzel_code': kurzel_code,
            'name_de': self.name_de_edit.text().strip(),
            'name_en': self.name_en_edit.text().strip(),
            'category': self.category_combo.currentText(),
            'image_type': self.image_type_combo.currentText(),
            'description_de': self.description_de_edit.toPlainText().strip(),
            'description_en': self.description_en_edit.toPlainText().strip(),
            'active': self.active_checkbox.isChecked(),
            'created_date': self.kurzel_data.get('created_date', datetime.now().isoformat()),
            'last_modified': datetime.now().isoformat()
        }


class AlternativeKurzelDialog(QDialog):
    """Dialog für Alternative Kürzel"""
    
    def __init__(self, parent=None, original="", alternative=""):
        super().__init__(parent)
        self.setWindowTitle("Alternative Kürzel")
        self.setModal(True)
        self.resize(400, 200)
        
        self._create_ui(original, alternative)
        
    def _create_ui(self, original, alternative):
        """Erstellt die Benutzeroberfläche"""
        layout = QVBoxLayout(self)
        
        form_layout = QFormLayout()
        
        self.original_edit = QLineEdit()
        self.original_edit.setText(original)
        self.alternative_edit = QLineEdit()
        self.alternative_edit.setText(alternative)
        
        form_layout.addRow("Original Kürzel:", self.original_edit)
        form_layout.addRow("Alternative Schreibweise:", self.alternative_edit)
        
        layout.addLayout(form_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.btn_ok = QPushButton("OK")
        self.btn_cancel = QPushButton("Abbrechen")
        
        button_layout.addStretch()
        button_layout.addWidget(self.btn_ok)
        button_layout.addWidget(self.btn_cancel)
        
        layout.addLayout(button_layout)
        
        # Verbindungen
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        
    def get_values(self):
        """Gibt die Werte zurück"""
        return self.original_edit.text().strip(), self.alternative_edit.text().strip()


class CategoryEditDialog(QDialog):
    """Dialog für Kategorie-Bearbeitung"""
    
    def __init__(self, parent=None, name="", description=""):
        super().__init__(parent)
        self.setWindowTitle("Kategorie bearbeiten" if name else "Neue Kategorie")
        self.setModal(True)
        self.resize(400, 200)
        
        self._create_ui(name, description)
        
    def _create_ui(self, name, description):
        """Erstellt die Benutzeroberfläche"""
        layout = QVBoxLayout(self)
        
        form_layout = QFormLayout()
        
        self.name_edit = QLineEdit()
        self.name_edit.setText(name)
        self.description_edit = QTextEdit()
        self.description_edit.setMaximumHeight(80)
        self.description_edit.setPlainText(description)
        
        form_layout.addRow("Kategorie-Name:", self.name_edit)
        form_layout.addRow("Beschreibung:", self.description_edit)
        
        layout.addLayout(form_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.btn_ok = QPushButton("OK")
        self.btn_cancel = QPushButton("Abbrechen")
        
        button_layout.addStretch()
        button_layout.addWidget(self.btn_ok)
        button_layout.addWidget(self.btn_cancel)
        
        layout.addLayout(button_layout)
        
        # Verbindungen
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)
        
    def get_values(self):
        """Gibt die Werte zurück"""
        return self.name_edit.text().strip(), self.description_edit.toPlainText().strip()



