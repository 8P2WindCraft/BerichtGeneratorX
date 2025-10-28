# -*- coding: utf-8 -*-
"""
Excel-Ansicht für das Laden und Schreiben von Grunddaten in EXIF
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QFileDialog, QMessageBox, QProgressBar, QCheckBox
)
from PySide6.QtCore import Qt, Signal
from utils_logging import get_logger
from utils_exif import update_metadata, read_metadata
import pandas as pd
import os
from pathlib import Path


class ExcelView(QWidget):
    """Excel-Daten-Management für Grunddaten"""
    
    dataLoaded = Signal(dict)  # Signal wenn Daten geladen wurden
    
    def __init__(self):
        super().__init__()
        self._log = get_logger('app', {"module": "qtui.excel_view"})
        self._log.info("module_started", extra={"event": "module_started"})
        
        self.excel_data = None
        self.excel_df = None
        self.current_folder = None
        
        self._create_ui()
        
    def _create_ui(self):
        """Erstellt die Benutzeroberfläche"""
        layout = QVBoxLayout(self)
        
        # Info-Label
        info_label = QLabel(
            "Laden Sie Excel-Daten mit Turbinen-Grunddaten und schreiben Sie diese in die EXIF-Metadaten der Bilder."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # 1. Excel-Datei laden
        file_group = QGroupBox("1. Excel-Datei laden")
        file_layout = QVBoxLayout(file_group)
        
        file_button_layout = QHBoxLayout()
        self.btn_load_excel = QPushButton("Excel-Datei auswählen...")
        self.btn_load_excel.clicked.connect(self._load_excel)
        file_button_layout.addWidget(self.btn_load_excel)
        
        self.lbl_excel_file = QLabel("Keine Datei geladen")
        file_button_layout.addWidget(self.lbl_excel_file, 1)
        
        file_layout.addLayout(file_button_layout)
        layout.addWidget(file_group)
        
        # 2. Daten anzeigen und Zeile auswählen
        data_group = QGroupBox("2. Daten anzeigen und Zeile auswählen")
        data_layout = QVBoxLayout(data_group)
        
        self.excel_table = QTableWidget()
        self.excel_table.setColumnCount(6)
        self.excel_table.setHorizontalHeaderLabels([
            "Zeile", "Windpark", "Land", "Seriennummer", "Turbinen-ID", "Hersteller"
        ])
        
        header = self.excel_table.horizontalHeader()
        for i in range(6):
            header.setSectionResizeMode(i, QHeaderView.Stretch)
            
        self.excel_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.excel_table.setSelectionMode(QTableWidget.SingleSelection)
        self.excel_table.itemSelectionChanged.connect(self._on_row_selected)
        
        data_layout.addWidget(self.excel_table)
        layout.addWidget(data_group)
        
        # 3. Aktionen
        actions_group = QGroupBox("3. Grunddaten in Bilder schreiben")
        actions_layout = QVBoxLayout(actions_group)
        
        # Ordner-Auswahl
        folder_layout = QHBoxLayout()
        folder_layout.addWidget(QLabel("Ziel-Ordner:"))
        self.lbl_folder = QLabel("Kein Ordner ausgewählt")
        folder_layout.addWidget(self.lbl_folder, 1)
        
        self.btn_select_folder = QPushButton("Ordner auswählen...")
        self.btn_select_folder.clicked.connect(self._select_folder)
        folder_layout.addWidget(self.btn_select_folder)
        
        actions_layout.addLayout(folder_layout)
        
        # Optionen
        self.check_update_only = QCheckBox("Nur vorhandene Grunddaten aktualisieren")
        self.check_update_only.setToolTip(
            "Wenn aktiviert, werden nur Bilder aktualisiert, die bereits Grunddaten haben. "
            "Wenn deaktiviert, werden alle Bilder mit Grunddaten versehen."
        )
        actions_layout.addWidget(self.check_update_only)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.btn_write_to_all = QPushButton("Grunddaten in ALLE Bilder schreiben")
        self.btn_write_to_all.clicked.connect(self._write_to_all_images)
        self.btn_write_to_all.setEnabled(False)
        button_layout.addWidget(self.btn_write_to_all)
        
        self.btn_write_to_current = QPushButton("Grunddaten in AKTUELLES Bild schreiben")
        self.btn_write_to_current.clicked.connect(self._write_to_current_image)
        self.btn_write_to_current.setEnabled(False)
        button_layout.addWidget(self.btn_write_to_current)
        
        actions_layout.addLayout(button_layout)
        
        # Fortschritt
        progress_layout = QHBoxLayout()
        progress_layout.addWidget(QLabel("Fortschritt:"))
        self.progress_bar = QProgressBar()
        progress_layout.addWidget(self.progress_bar, 1)
        actions_layout.addLayout(progress_layout)
        
        layout.addWidget(actions_group)
        
        layout.addStretch()
        
    def set_folder(self, folder: str):
        """Setzt den aktuellen Ordner"""
        self.current_folder = folder
        self.lbl_folder.setText(folder if folder else "Kein Ordner ausgewählt")
        self._update_buttons()
        
    def _load_excel(self):
        """Lädt Excel-Datei"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Excel-Datei laden", "", "Excel-Dateien (*.xlsx *.xls)"
        )
        
        if not file_path:
            return
            
        try:
            self._log.info("excel_loading", extra={"event": "excel_loading", "path": file_path})
            
            # Excel-Datei laden
            self.excel_df = pd.read_excel(file_path)
            
            # Spalten finden (flexibel)
            column_mapping = self._find_columns(self.excel_df.columns)
            
            if not column_mapping:
                QMessageBox.warning(
                    self, "Spalten nicht gefunden",
                    "Konnte keine passenden Spalten in der Excel-Datei finden.\n\n"
                    "Benötigte Spalten: Windpark/Windfarm, Land/Country, "
                    "Seriennummer/SN, Turbinen-ID/ID, Hersteller/Manufacturer"
                )
                return
                
            # Tabelle füllen
            self.excel_table.setRowCount(0)
            self.excel_data = []
            
            for index, row in self.excel_df.iterrows():
                data_row = {
                    "row_index": index,
                    "windfarm_name": str(row.get(column_mapping.get('windpark', ''), '')),
                    "windfarm_country": str(row.get(column_mapping.get('land', ''), '')),
                    "turbine_sn": str(row.get(column_mapping.get('sn', ''), '')),
                    "turbine_id": str(row.get(column_mapping.get('id', ''), '')),
                    "turbine_manufacturer": str(row.get(column_mapping.get('hersteller', ''), ''))
                }
                
                self.excel_data.append(data_row)
                
                # In Tabelle einfügen
                row_position = self.excel_table.rowCount()
                self.excel_table.insertRow(row_position)
                
                self.excel_table.setItem(row_position, 0, QTableWidgetItem(str(index + 1)))
                self.excel_table.setItem(row_position, 1, QTableWidgetItem(data_row['windfarm_name']))
                self.excel_table.setItem(row_position, 2, QTableWidgetItem(data_row['windfarm_country']))
                self.excel_table.setItem(row_position, 3, QTableWidgetItem(data_row['turbine_sn']))
                self.excel_table.setItem(row_position, 4, QTableWidgetItem(data_row['turbine_id']))
                self.excel_table.setItem(row_position, 5, QTableWidgetItem(data_row['turbine_manufacturer']))
                
            self.lbl_excel_file.setText(f"{os.path.basename(file_path)} ({len(self.excel_data)} Zeilen)")
            
            self._log.info("excel_loaded", extra={
                "event": "excel_loaded",
                "rows": len(self.excel_data),
                "columns": column_mapping
            })
            
            QMessageBox.information(
                self, "Excel geladen",
                f"Excel-Datei erfolgreich geladen: {len(self.excel_data)} Zeilen\n\n"
                f"Gefundene Spalten:\n"
                f"• Windpark: {column_mapping.get('windpark', 'Nicht gefunden')}\n"
                f"• Land: {column_mapping.get('land', 'Nicht gefunden')}\n"
                f"• Seriennummer: {column_mapping.get('sn', 'Nicht gefunden')}\n"
                f"• ID: {column_mapping.get('id', 'Nicht gefunden')}\n"
                f"• Hersteller: {column_mapping.get('hersteller', 'Nicht gefunden')}"
            )
            
            self._update_buttons()
            
        except Exception as e:
            self._log.error("excel_load_failed", extra={"event": "excel_load_failed", "error": str(e)})
            QMessageBox.critical(self, "Fehler", f"Fehler beim Laden der Excel-Datei:\n{str(e)}")
            
    def _find_columns(self, columns):
        """Findet die passenden Spalten in der Excel-Datei"""
        mapping = {}
        columns_lower = [str(col).lower() for col in columns]
        
        # Windpark
        for pattern in ['windpark', 'windfarm', 'wind farm', 'park']:
            for i, col in enumerate(columns_lower):
                if pattern in col:
                    mapping['windpark'] = columns[i]
                    break
            if 'windpark' in mapping:
                break
                
        # Land
        for pattern in ['land', 'country', 'staat']:
            for i, col in enumerate(columns_lower):
                if pattern in col:
                    mapping['land'] = columns[i]
                    break
            if 'land' in mapping:
                break
                
        # Seriennummer
        for pattern in ['seriennummer', 'sn', 'serial', 'nummer']:
            for i, col in enumerate(columns_lower):
                if pattern in col and 'turb' not in col:
                    mapping['sn'] = columns[i]
                    break
            if 'sn' in mapping:
                break
                
        # Turbinen-ID
        for pattern in ['turbinen-id', 'turbine_id', 'id', 'anlagen_nr', 'anlagennr']:
            for i, col in enumerate(columns_lower):
                if 'turb' in col and ('id' in col or 'nr' in col or 'nummer' in col):
                    mapping['id'] = columns[i]
                    break
            if 'id' in mapping:
                break
                
        # Hersteller
        for pattern in ['hersteller', 'manufacturer', 'maker', 'brand']:
            for i, col in enumerate(columns_lower):
                if pattern in col:
                    mapping['hersteller'] = columns[i]
                    break
            if 'hersteller' in mapping:
                break
                
        return mapping if mapping else None
        
    def _select_folder(self):
        """Wählt Ziel-Ordner aus"""
        folder = QFileDialog.getExistingDirectory(self, "Ziel-Ordner auswählen", "")
        if folder:
            self.set_folder(folder)
            
    def _on_row_selected(self):
        """Wird aufgerufen wenn eine Zeile ausgewählt wird"""
        self._update_buttons()
        
    def _update_buttons(self):
        """Aktualisiert den Enabled-Status der Buttons"""
        has_data = self.excel_data is not None and len(self.excel_data) > 0
        has_folder = self.current_folder is not None and os.path.exists(self.current_folder)
        has_selection = len(self.excel_table.selectedItems()) > 0
        
        self.btn_write_to_all.setEnabled(has_data and has_folder and has_selection)
        self.btn_write_to_current.setEnabled(has_data and has_folder and has_selection)
        
    def _write_to_all_images(self):
        """Schreibt Grunddaten in alle Bilder des Ordners"""
        selected_row = self.excel_table.currentRow()
        if selected_row < 0 or selected_row >= len(self.excel_data):
            QMessageBox.warning(self, "Keine Auswahl", "Bitte wählen Sie eine Zeile aus der Tabelle aus.")
            return
            
        data = self.excel_data[selected_row]
        
        reply = QMessageBox.question(
            self, "Bestätigung",
            f"Möchten Sie folgende Grunddaten in ALLE Bilder im Ordner schreiben?\n\n"
            f"Windpark: {data['windfarm_name']}\n"
            f"Land: {data['windfarm_country']}\n"
            f"Seriennummer: {data['turbine_sn']}\n"
            f"Turbinen-ID: {data['turbine_id']}\n"
            f"Hersteller: {data['turbine_manufacturer']}\n\n"
            f"Ordner: {self.current_folder}",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
            
        self._process_images(data, update_only=self.check_update_only.isChecked())
        
    def _write_to_current_image(self):
        """Schreibt Grunddaten nur in das aktuell angezeigte Bild"""
        # TODO: Integration mit SingleView um aktuelles Bild zu bekommen
        QMessageBox.information(
            self, "In Entwicklung",
            "Diese Funktion wird mit der SingleView integriert."
        )
        
    def _process_images(self, data, update_only=False):
        """Verarbeitet alle Bilder im Ordner"""
        if not self.current_folder or not os.path.exists(self.current_folder):
            QMessageBox.warning(self, "Fehler", "Kein gültiger Ordner ausgewählt.")
            return
            
        try:
            # Alle Bilder im Ordner finden
            image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff'}
            image_files = [
                f for f in os.listdir(self.current_folder)
                if os.path.splitext(f)[1].lower() in image_extensions
            ]
            
            if not image_files:
                QMessageBox.information(self, "Keine Bilder", "Keine Bilder im ausgewählten Ordner gefunden.")
                return
                
            total = len(image_files)
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(0)
            
            updated = 0
            skipped = 0
            errors = []
            
            for i, filename in enumerate(image_files):
                file_path = os.path.join(self.current_folder, filename)
                
                try:
                    # Aktuelle Metadaten lesen
                    metadata = read_metadata(file_path)
                    
                    # Prüfen ob schon Grunddaten vorhanden sind
                    if update_only:
                        has_grunddaten = any(key in metadata for key in [
                            'windpark', 'windfarm_name', 'windpark_land', 'sn', 'anlagen_nr'
                        ])
                        
                        if not has_grunddaten:
                            skipped += 1
                            continue
                            
                    # Grunddaten hinzufügen/aktualisieren
                    metadata['windpark'] = data['windfarm_name']
                    metadata['windfarm_name'] = data['windfarm_name']
                    metadata['windpark_land'] = data['windfarm_country']
                    metadata['windfarm_country'] = data['windfarm_country']
                    metadata['sn'] = data['turbine_sn']
                    metadata['turbine_sn'] = data['turbine_sn']
                    metadata['anlagen_nr'] = data['turbine_id']
                    metadata['turbine_id'] = data['turbine_id']
                    metadata['hersteller'] = data['turbine_manufacturer']
                    metadata['turbine_manufacturer'] = data['turbine_manufacturer']
                    
                    # Metadaten speichern
                    if update_metadata(file_path, metadata):
                        updated += 1
                    else:
                        errors.append(filename)
                        
                except Exception as e:
                    self._log.error("image_process_failed", extra={
                        "event": "image_process_failed",
                        "file": filename,
                        "error": str(e)
                    })
                    errors.append(f"{filename}: {str(e)}")
                    
                self.progress_bar.setValue(i + 1)
                
            # Ergebnis anzeigen
            message = f"Verarbeitung abgeschlossen:\n\n"
            message += f"• {updated} Bilder aktualisiert\n"
            
            if skipped > 0:
                message += f"• {skipped} Bilder übersprungen (keine Grunddaten vorhanden)\n"
                
            if errors:
                message += f"\n⚠️ {len(errors)} Fehler aufgetreten"
                
            if errors:
                QMessageBox.warning(self, "Mit Fehlern abgeschlossen", message)
            else:
                QMessageBox.information(self, "Erfolgreich", message)
                
            self._log.info("images_processed", extra={
                "event": "images_processed",
                "total": total,
                "updated": updated,
                "skipped": skipped,
                "errors": len(errors)
            })
            
        except Exception as e:
            self._log.error("process_images_failed", extra={"event": "process_images_failed", "error": str(e)})
            QMessageBox.critical(self, "Fehler", f"Fehler beim Verarbeiten der Bilder:\n{str(e)}")




