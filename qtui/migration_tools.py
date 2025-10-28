# -*- coding: utf-8 -*-
"""
Migration-Tools für Kürzel und Konfiguration
Unterstützt Migration von Tkinter zu Qt und zwischen verschiedenen Versionen
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QProgressBar, QTextEdit, QFileDialog, QMessageBox, QGroupBox
)
from PySide6.QtCore import Qt, Signal
from utils_logging import get_logger
from datetime import datetime
import json
import os


class MigrationDialog(QDialog):
    """Dialog für Migrations-Tools"""
    
    migrationComplete = Signal(dict)  # Signal nach erfolgreicher Migration
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._log = get_logger('app', {"module": "qtui.migration_tools"})
        self._log.info("module_started", extra={"event": "module_started"})
        
        self.setWindowTitle("Migrations-Tools")
        self.setModal(True)
        self.resize(700, 500)
        
        # Settings Manager
        from .settings_manager import get_settings_manager
        self.settings_manager = get_settings_manager()
        
        self._create_ui()
        
    def _create_ui(self):
        """Erstellt die Benutzeroberfläche"""
        layout = QVBoxLayout(self)
        
        # Info-Label
        info_label = QLabel(
            "Migrations-Tools ermöglichen den Import von Einstellungen und Daten "
            "aus älteren Versionen oder der Tkinter-Anwendung."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Kürzel-Migration
        kurzel_group = self._create_kurzel_migration_group()
        layout.addWidget(kurzel_group)
        
        # Konfigurations-Migration
        config_group = self._create_config_migration_group()
        layout.addWidget(config_group)
        
        # Fortschrittsanzeige
        progress_group = QGroupBox("Fortschritt")
        progress_layout = QVBoxLayout(progress_group)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        progress_layout.addWidget(self.log_text)
        
        layout.addWidget(progress_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.btn_close = QPushButton("Schließen")
        button_layout.addStretch()
        button_layout.addWidget(self.btn_close)
        
        layout.addLayout(button_layout)
        
        # Verbindungen
        self.btn_close.clicked.connect(self.accept)
        
    def _create_kurzel_migration_group(self):
        """Erstellt die Kürzel-Migrations-Gruppe"""
        group = QGroupBox("Kürzel-Migration")
        layout = QVBoxLayout(group)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        self.btn_import_tkinter_kurzel = QPushButton("Tkinter Kürzel importieren...")
        self.btn_import_tkinter_kurzel.clicked.connect(self._import_tkinter_kurzel)
        btn_layout.addWidget(self.btn_import_tkinter_kurzel)
        
        self.btn_migrate_kurzel = QPushButton("Kürzel-Format aktualisieren")
        self.btn_migrate_kurzel.clicked.connect(self._migrate_kurzel_format)
        btn_layout.addWidget(self.btn_migrate_kurzel)
        
        layout.addLayout(btn_layout)
        
        return group
        
    def _create_config_migration_group(self):
        """Erstellt die Konfigurations-Migrations-Gruppe"""
        group = QGroupBox("Konfigurations-Migration")
        layout = QVBoxLayout(group)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        self.btn_import_tkinter_config = QPushButton("Tkinter Config importieren...")
        self.btn_import_tkinter_config.clicked.connect(self._import_tkinter_config)
        btn_layout.addWidget(self.btn_import_tkinter_config)
        
        self.btn_export_config = QPushButton("Config exportieren...")
        self.btn_export_config.clicked.connect(self._export_config)
        btn_layout.addWidget(self.btn_export_config)
        
        layout.addLayout(btn_layout)
        
        return group
        
    def _log_message(self, message: str):
        """Fügt eine Nachricht zum Log hinzu"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        
    def _import_tkinter_kurzel(self):
        """Importiert Kürzel aus Tkinter-Konfiguration"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Tkinter Config.json laden", "", "JSON-Dateien (*.json)"
        )
        
        if not file_path:
            return
            
        try:
            self._log_message("Starte Kürzel-Import...")
            self.progress_bar.setValue(10)
            
            with open(file_path, 'r', encoding='utf-8') as f:
                tkinter_config = json.load(f)
                
            self.progress_bar.setValue(30)
            
            # Kürzel-Tabelle extrahieren
            kurzel_table = tkinter_config.get('kurzel_table', {})
            alternative_kurzel = tkinter_config.get('alternative_kurzel', {})
            kurzel_categories = tkinter_config.get('kurzel_categories', {})
            
            self._log_message(f"Gefunden: {len(kurzel_table)} Kürzel, {len(alternative_kurzel)} Alternativen, {len(kurzel_categories)} Kategorien")
            
            self.progress_bar.setValue(50)
            
            # In aktuelle Konfiguration übernehmen
            if kurzel_table:
                self.settings_manager.set('kurzel_table', kurzel_table)
                self._log_message(f"✓ {len(kurzel_table)} Kürzel importiert")
                
            if alternative_kurzel:
                self.settings_manager.set('alternative_kurzel', alternative_kurzel)
                self._log_message(f"✓ {len(alternative_kurzel)} Alternative Kürzel importiert")
                
            if kurzel_categories:
                self.settings_manager.set('kurzel_categories', kurzel_categories)
                self._log_message(f"✓ {len(kurzel_categories)} Kategorien importiert")
                
            self.progress_bar.setValue(100)
            self._log_message("✅ Kürzel-Import erfolgreich abgeschlossen")
            
            QMessageBox.information(
                self, "Import erfolgreich", 
                f"Es wurden {len(kurzel_table)} Kürzel erfolgreich importiert."
            )
            
        except Exception as e:
            self._log_message(f"❌ Fehler beim Import: {str(e)}")
            QMessageBox.critical(self, "Import fehlgeschlagen", f"Fehler: {str(e)}")
            self.progress_bar.setValue(0)
            
    def _migrate_kurzel_format(self):
        """Migriert Kürzel-Format auf neueste Version"""
        try:
            self._log_message("Starte Kürzel-Format-Migration...")
            self.progress_bar.setValue(10)
            
            kurzel_table = self.settings_manager.get('kurzel_table', {})
            
            if not kurzel_table:
                QMessageBox.information(self, "Keine Daten", "Keine Kürzel zum Migrieren gefunden.")
                return
                
            self._log_message(f"Prüfe {len(kurzel_table)} Kürzel...")
            self.progress_bar.setValue(30)
            
            migrated_count = 0
            updated_count = 0
            
            # Standard-Felder für aktuelles Format
            required_fields = [
                'kurzel_code', 'name_de', 'name_en', 'category', 'image_type',
                'description_de', 'description_en', 'active', 'created_date', 
                'last_modified'
            ]
            
            for kurzel_code, data in kurzel_table.items():
                updated = False
                
                # Prüfe ob alle Felder vorhanden sind
                for field in required_fields:
                    if field not in data:
                        if field == 'active':
                            data[field] = True
                        elif field in ['created_date', 'last_modified']:
                            data[field] = datetime.now().isoformat()
                        else:
                            data[field] = ''
                        updated = True
                        
                if updated:
                    updated_count += 1
                    kurzel_table[kurzel_code] = data
                    
                migrated_count += 1
                
            self.progress_bar.setValue(70)
            
            # Aktualisierte Kürzel speichern
            self.settings_manager.set('kurzel_table', kurzel_table)
            
            self.progress_bar.setValue(100)
            self._log_message(f"✅ Migration abgeschlossen: {migrated_count} Kürzel geprüft, {updated_count} aktualisiert")
            
            QMessageBox.information(
                self, "Migration erfolgreich", 
                f"{migrated_count} Kürzel wurden geprüft.\n{updated_count} Kürzel wurden aktualisiert."
            )
            
        except Exception as e:
            self._log_message(f"❌ Fehler bei Migration: {str(e)}")
            QMessageBox.critical(self, "Migration fehlgeschlagen", f"Fehler: {str(e)}")
            self.progress_bar.setValue(0)
            
    def _import_tkinter_config(self):
        """Importiert vollständige Konfiguration aus Tkinter"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Tkinter Config.json laden", "", "JSON-Dateien (*.json)"
        )
        
        if not file_path:
            return
            
        reply = QMessageBox.question(
            self, "Warnung", 
            "Dies wird ALLE aktuellen Einstellungen überschreiben!\n"
            "Möchten Sie fortfahren?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
            
        try:
            self._log_message("Starte vollständigen Config-Import...")
            self.progress_bar.setValue(10)
            
            with open(file_path, 'r', encoding='utf-8') as f:
                tkinter_config = json.load(f)
                
            self.progress_bar.setValue(30)
            
            imported_count = 0
            
            # Mapping von Tkinter-Keys zu Qt-Keys (wo unterschiedlich)
            key_mapping = {
                'damage_categories': 'damage_categories',
                'image_types': 'image_types',
                'image_quality_options': 'image_quality_options',
                'use_image_options': 'use_image_options',
                'kurzel_table': 'kurzel_table',
                'alternative_kurzel': 'alternative_kurzel',
                'kurzel_categories': 'kurzel_categories',
                'kurzel_details': 'kurzel_details',
                'kurzel_statistics': 'kurzel_statistics',
                'valid_kurzel': 'valid_kurzel',
                'ocr_roi_top': 'ocr_roi_top',
                'ocr_roi_bottom': 'ocr_roi_bottom',
                'ocr_roi_left': 'ocr_roi_left',
                'ocr_roi_right': 'ocr_roi_right',
                'max_workers': 'max_workers',
                'ocr_timeout': 'ocr_timeout',
                'enable_char_replacements': 'enable_char_replacements',
                'enable_number_normalization': 'enable_number_normalization',
                'fuzzy_matching_cutoff': 'fuzzy_matching_cutoff',
            }
            
            total_keys = len(key_mapping)
            for i, (tk_key, qt_key) in enumerate(key_mapping.items()):
                if tk_key in tkinter_config:
                    self.settings_manager.set(qt_key, tkinter_config[tk_key])
                    imported_count += 1
                    
                progress = 30 + int((i / total_keys) * 60)
                self.progress_bar.setValue(progress)
                
            self.progress_bar.setValue(100)
            self._log_message(f"✅ Config-Import erfolgreich: {imported_count} Einstellungen importiert")
            
            QMessageBox.information(
                self, "Import erfolgreich", 
                f"{imported_count} Einstellungen wurden erfolgreich importiert.\n"
                "Bitte starten Sie die Anwendung neu, um alle Änderungen zu übernehmen."
            )
            
        except Exception as e:
            self._log_message(f"❌ Fehler beim Import: {str(e)}")
            QMessageBox.critical(self, "Import fehlgeschlagen", f"Fehler: {str(e)}")
            self.progress_bar.setValue(0)
            
    def _export_config(self):
        """Exportiert aktuelle Konfiguration"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Konfiguration exportieren", "config_export.json", "JSON-Dateien (*.json)"
        )
        
        if not file_path:
            return
            
        try:
            self._log_message("Starte Config-Export...")
            self.progress_bar.setValue(10)
            
            # Alle wichtigen Einstellungen sammeln
            export_data = {
                'export_date': datetime.now().isoformat(),
                'export_version': '2.0',
                'kurzel_table': self.settings_manager.get('kurzel_table', {}),
                'alternative_kurzel': self.settings_manager.get('alternative_kurzel', {}),
                'kurzel_categories': self.settings_manager.get('kurzel_categories', {}),
                'damage_categories': self.settings_manager.get('damage_categories', []),
                'image_types': self.settings_manager.get('image_types', []),
                'image_quality_options': self.settings_manager.get('image_quality_options', []),
                'use_image_options': self.settings_manager.get('use_image_options', []),
                'ocr_roi_top': self.settings_manager.get('ocr_roi_top', 0.0),
                'ocr_roi_bottom': self.settings_manager.get('ocr_roi_bottom', 0.20),
                'ocr_roi_left': self.settings_manager.get('ocr_roi_left', 0.0),
                'ocr_roi_right': self.settings_manager.get('ocr_roi_right', 0.18),
                'max_workers': self.settings_manager.get('max_workers', 2),
                'ocr_timeout': self.settings_manager.get('ocr_timeout', 30),
                'theme': self.settings_manager.get('theme', 'Light'),
            }
            
            self.progress_bar.setValue(50)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
                
            self.progress_bar.setValue(100)
            self._log_message(f"✅ Config-Export erfolgreich nach: {file_path}")
            
            QMessageBox.information(
                self, "Export erfolgreich", 
                f"Konfiguration wurde erfolgreich exportiert nach:\n{file_path}"
            )
            
        except Exception as e:
            self._log_message(f"❌ Fehler beim Export: {str(e)}")
            QMessageBox.critical(self, "Export fehlgeschlagen", f"Fehler: {str(e)}")
            self.progress_bar.setValue(0)


def migrate_from_tkinter(tkinter_config_path: str, settings_manager) -> dict:
    """
    Standalone-Funktion für Migration von Tkinter-Konfiguration
    
    Args:
        tkinter_config_path: Pfad zur Tkinter config.json
        settings_manager: Qt Settings Manager Instance
        
    Returns:
        dict: Migration-Statistiken
    """
    stats = {
        'success': False,
        'imported_kurzel': 0,
        'imported_settings': 0,
        'errors': []
    }
    
    try:
        if not os.path.exists(tkinter_config_path):
            stats['errors'].append(f"Datei nicht gefunden: {tkinter_config_path}")
            return stats
            
        with open(tkinter_config_path, 'r', encoding='utf-8') as f:
            tkinter_config = json.load(f)
            
        # Kürzel importieren
        if 'kurzel_table' in tkinter_config:
            kurzel_table = tkinter_config['kurzel_table']
            settings_manager.set('kurzel_table', kurzel_table)
            stats['imported_kurzel'] = len(kurzel_table)
            
        # Weitere Einstellungen importieren
        settings_to_import = [
            'alternative_kurzel', 'kurzel_categories', 'damage_categories',
            'image_types', 'image_quality_options', 'use_image_options',
            'ocr_roi_top', 'ocr_roi_bottom', 'ocr_roi_left', 'ocr_roi_right',
            'max_workers', 'ocr_timeout'
        ]
        
        for setting in settings_to_import:
            if setting in tkinter_config:
                settings_manager.set(setting, tkinter_config[setting])
                stats['imported_settings'] += 1
                
        stats['success'] = True
        
    except Exception as e:
        stats['errors'].append(str(e))
        
    return stats




