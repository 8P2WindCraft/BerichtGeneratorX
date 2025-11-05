import re
import os
import json
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ExifTags, ImageDraw, ImageEnhance
import cv2
import easyocr
from difflib import get_close_matches
from collections import Counter
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler
import traceback

import numpy as np
import pandas as pd
import unicodedata
import threading
import time
import sys
import csv


# Default codes list (will be overridden by loaded file)
DEFAULT_KURZEL = [
    'HSS', 'HSSR', 'HSSGR', 'HSSGG',
    'LSS', 'LSSR', 'LSSGR', 'LSSGG',
    'PLC2GR', 'PLC2GG', 'PLC2R', 'RG2', 'SUN2',
    'PL2-1', 'PLB2G-1', 'PLB2R-1',
    'PL2-2', 'PLB2G-2', 'PLB2R-2',
    'PL2-3', 'PLB2G-3', 'PLB2R-3',
    'PLC1G', 'PLC1R', 'RG1', 'SUN1',
    'PL1-1', 'PLB1G-1', 'PLB1R-1',
    'PL1-2', 'PLB1G-2', 'PLB1R-2',
    'PL1-3', 'PLB1G-3', 'PLB1R-3',
    'PL1-4', 'PLB1G-4', 'PLB1R-4',
]

# Schadenskategorien
DAMAGE_CATEGORIES = [
    "Visually no defects",
    "Scratches",
    "Cycloid Scratches",
    "Standstill marks",
    "Smearing",
    "Particle passage",
    "Overrolling Marks",
    "Pitting",
    "Others"
]

# Bildart-Kategorien
IMAGE_TYPES = [
    "Rolling Element",
    "Inner ring",
    "Outer ring",
    "Cage",
    "Gear"
]

# Bild verwenden Optionen
USE_IMAGE_OPTIONS = ["ja", "nein"]

# Konstanten für Magic Numbers
THUMBNAIL_WIDTH = 150
THUMBNAIL_HEIGHT = 100
THUMBNAIL_LARGE_WIDTH = 300
THUMBNAIL_LARGE_HEIGHT = 200
THUMBNAIL_MEDIUM_WIDTH = 200
THUMBNAIL_MEDIUM_HEIGHT = 150
THUMBNAIL_SMALL_WIDTH = 32
THUMBNAIL_SMALL_HEIGHT = 32
THUMBNAIL_DISPLAY_WIDTH = 400
THUMBNAIL_DISPLAY_HEIGHT = 300

# Fenster-Größen
DEBUG_PREVIEW_WIDTH = 800
DEBUG_PREVIEW_HEIGHT = 600
DIALOG_WIDTH = 800
DIALOG_HEIGHT = 600
ANALYSIS_WINDOW_WIDTH = 600
ANALYSIS_WINDOW_HEIGHT = 400
MAIN_WINDOW_WIDTH = 1080
MAIN_WINDOW_HEIGHT = 800
LOG_WINDOW_WIDTH = 1000
LOG_WINDOW_HEIGHT = 700
LOG_WINDOW_SMALL_WIDTH = 800
LOG_WINDOW_SMALL_HEIGHT = 600
JSON_WINDOW_WIDTH = 1000
JSON_WINDOW_HEIGHT = 700
PROGRESS_WINDOW_WIDTH = 400
PROGRESS_WINDOW_HEIGHT = 150
FEEDBACK_WINDOW_WIDTH = 200
FEEDBACK_WINDOW_HEIGHT = 100
INFO_WINDOW_WIDTH = 600
INFO_WINDOW_HEIGHT = 500
LOADING_WINDOW_WIDTH = 500
LOADING_WINDOW_HEIGHT = 400
EDIT_DIALOG_WIDTH = 400
EDIT_DIALOG_HEIGHT = 300

# Andere Konstanten
MAX_CSV_TEST_LINES = 10
MAX_LOG_FILE_SIZE = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5

# Logging-Setup
def setup_logging():
    """Konfiguriert das Logging-System"""
    # Logger erstellen
    logger = logging.getLogger('BildAnalysator')
    logger.setLevel(logging.DEBUG)
    
    # Verhindere doppelte Handler
    if logger.handlers:
        return logger
    
    # Log-Format
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
    )
    
    # File Handler mit Rotation
    log_file = os.path.join(os.path.dirname(__file__), 'app.log')
    file_handler = RotatingFileHandler(
        log_file, 
        maxBytes=MAX_LOG_FILE_SIZE, 
        backupCount=LOG_BACKUP_COUNT,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    
    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # Handler hinzufügen
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# Globaler Logger
logger = setup_logging()

def detect_csv_encoding(file_path):
    """Erkennt die Kodierung einer CSV-Datei automatisch"""
    logger.debug(f"Erkenne Kodierung für Datei: {file_path}")
    encodings_to_try = ['utf-8-sig', 'utf-8', 'windows-1252', 'latin-1', 'cp1252']
    
    if not os.path.exists(file_path):
        logger.error(f"Datei existiert nicht: {file_path}")
        raise FileNotFoundError(f"Datei nicht gefunden: {file_path}")
    
    for encoding in encodings_to_try:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                # Versuche die ersten paar Zeilen zu lesen
                for i, line in enumerate(f):
                    if i > MAX_CSV_TEST_LINES:  # Nur erste Zeilen testen
                        break
                logger.info(f"Erfolgreich Kodierung erkannt: {encoding}")
                return encoding
        except UnicodeDecodeError as e:
            logger.debug(f"Kodierung {encoding} fehlgeschlagen: {e}")
            continue
        except PermissionError as e:
            logger.error(f"Keine Berechtigung für Datei: {file_path}")
            raise PermissionError(f"Keine Berechtigung: {file_path}") from e
        except OSError as e:
            logger.error(f"OS-Fehler beim Lesen der Datei: {file_path}")
            raise OSError(f"Fehler beim Lesen: {file_path}") from e
    
    logger.warning(f"Keine passende Kodierung gefunden, verwende Fallback: utf-8-sig")
    return 'utf-8-sig'

def safe_csv_open(file_path, mode='r'):
    """Öffnet eine CSV-Datei mit automatischer Kodierungserkennung"""
    logger.debug(f"Öffne CSV-Datei: {file_path} (Mode: {mode})")
    
    try:
        if mode == 'r':
            encoding = detect_csv_encoding(file_path)
            return open(file_path, mode, encoding=encoding, newline='')
        else:
            return open(file_path, mode, encoding='utf-8-sig', newline='')
    except FileNotFoundError as e:
        logger.error(f"Datei nicht gefunden: {file_path}")
        raise
    except PermissionError as e:
        logger.error(f"Keine Berechtigung für Datei: {file_path}")
        raise
    except Exception as e:
        logger.error(f"Unerwarteter Fehler beim Öffnen der Datei {file_path}: {e}")
        raise

# Excel-Grunddaten Dialog Klasse
class AlternativeKurzelDialog:
    """Dialog für das Bearbeiten von alternativen Kürzeln"""
    
    def __init__(self, parent, title, alt_kurzel="", korrigiertes_kurzel=""):
        self.parent = parent
        self.result = None
        
        # Dialog-Fenster erstellen
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("400x200")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Zentriere das Fenster
        self.dialog.geometry("+%d+%d" % (parent.winfo_rootx() + 50, parent.winfo_rooty() + 50))
        
        # Variablen
        self.alt_kurzel_var = tk.StringVar(value=alt_kurzel)
        self.korrigiertes_kurzel_var = tk.StringVar(value=korrigiertes_kurzel)
        
        self.create_widgets()
        
        # Fokus auf erstes Eingabefeld
        self.alt_kurzel_entry.focus()
        
        # Warte auf Schließen
        self.dialog.wait_window()
    
    def create_widgets(self):
        """Erstellt die Widgets des Dialogs"""
        main_frame = ttk.Frame(self.dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Alternatives Kürzel
        ttk.Label(main_frame, text="Alternatives Kürzel:").pack(anchor='w', pady=(0, 5))
        self.alt_kurzel_entry = ttk.Entry(main_frame, textvariable=self.alt_kurzel_var, width=30)
        self.alt_kurzel_entry.pack(fill=tk.X, pady=(0, 15))
        
        # Korrigiertes Kürzel
        ttk.Label(main_frame, text="Korrigiertes Kürzel:").pack(anchor='w', pady=(0, 5))
        self.korrigiertes_kurzel_entry = ttk.Entry(main_frame, textvariable=self.korrigiertes_kurzel_var, width=30)
        self.korrigiertes_kurzel_entry.pack(fill=tk.X, pady=(0, 20))
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="Abbrechen", command=self.cancel).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(button_frame, text="OK", command=self.ok).pack(side=tk.RIGHT)
        
        # Enter-Taste für OK
        self.dialog.bind('<Return>', lambda e: self.ok())
        self.dialog.bind('<Escape>', lambda e: self.cancel())
    
    def ok(self):
        """Bestätigt die Eingabe"""
        alt_kurzel = self.alt_kurzel_var.get().strip()
        korrigiertes_kurzel = self.korrigiertes_kurzel_var.get().strip()
        
        if not alt_kurzel or not korrigiertes_kurzel:
            messagebox.showwarning("Warnung", "Bitte füllen Sie beide Felder aus!")
            return
        
        self.result = (alt_kurzel, korrigiertes_kurzel)
        self.dialog.destroy()
    
    def cancel(self):
        """Bricht den Dialog ab"""
        self.result = None
        self.dialog.destroy()

class ExcelGrunddatenDialog:
    def __init__(self, parent):
        self.parent = parent
        self.dialog = None
        self.excel_data = None
        self.selected_row = None
        
    def show_dialog(self):
        """Zeigt den Excel-Grunddaten Dialog"""
        self.dialog = tk.Toplevel(self.parent)
        self.dialog.title("Excel-Grunddaten laden")
        self.dialog.geometry(f"{DIALOG_WIDTH}x{DIALOG_HEIGHT}")
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        logger.info("Excel-Grunddaten Dialog geöffnet")
        
        # Hauptframe
        main_frame = ttk.Frame(self.dialog, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 1. Excel-Datei auswählen
        file_frame = ttk.LabelFrame(main_frame, text="1. Excel-Datei auswählen", padding="10")
        file_frame.pack(fill=tk.X, pady=(0, 10))
        
        file_layout = ttk.Frame(file_frame)
        file_layout.pack(fill=tk.X)
        
        self.file_path_var = tk.StringVar()
        file_entry = ttk.Entry(file_layout, textvariable=self.file_path_var, state="readonly")
        file_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        browse_btn = ttk.Button(file_layout, text="Durchsuchen...", command=self.browse_excel_file)
        browse_btn.pack(side=tk.RIGHT)
        
        # 2. Daten anzeigen
        data_frame = ttk.LabelFrame(main_frame, text="2. Daten anzeigen und Zeile auswählen", padding="10")
        data_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Treeview für Excel-Daten
        columns = ("Zeile", "Windpark", "Land", "Seriennummer", "Turbinen-ID")
        self.tree = ttk.Treeview(data_frame, columns=columns, show="headings", height=15)
        
        # Spalten konfigurieren
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=120)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(data_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Auswahl-Info
        self.selection_label = ttk.Label(data_frame, text="Keine Zeile ausgewählt")
        self.selection_label.pack(pady=(10, 0))
        
        # 3. Aktionen
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.load_btn = ttk.Button(action_frame, text="Grunddaten in alle Bilder schreiben", 
                                 command=self.write_to_images, state="disabled")
        self.load_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.update_btn = ttk.Button(action_frame, text="Bestehende Grunddaten aktualisieren", 
                                   command=self.update_existing_data, state="disabled")
        self.update_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        close_btn = ttk.Button(action_frame, text="Schließen", command=self.dialog.destroy)
        close_btn.pack(side=tk.RIGHT)
        
        # Event-Bindings
        self.tree.bind("<<TreeviewSelect>>", self.on_row_select)
        
        # Zentrieren
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (self.dialog.winfo_width() // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (self.dialog.winfo_height() // 2)
        self.dialog.geometry(f"+{x}+{y}")
        
    def browse_excel_file(self):
        """Öffnet Dateidialog für Excel-Auswahl"""
        logger.debug("Excel-Datei Browser geöffnet")
        
        try:
            # Verwende letzte Excel-Datei als Startverzeichnis
            last_file = self.parent.json_config.get('last_selections', {}).get('excel_file', '')
            initial_dir = os.path.dirname(last_file) if last_file and os.path.exists(last_file) else None
            
            file_path = filedialog.askopenfilename(
                title="Excel-Datei mit Grunddaten auswählen",
                filetypes=[("Excel files", "*.xlsx *.xls")],
                initialdir=initial_dir
            )
            
            if file_path:
                logger.info(f"Excel-Datei ausgewählt: {file_path}")
                
                # Speichere die Auswahl
                if 'last_selections' not in self.parent.json_config:
                    self.parent.json_config['last_selections'] = {}
                self.parent.json_config['last_selections']['excel_file'] = file_path
                self.parent.config.save_config()
                
                self.file_path_var.set(file_path)
                self.load_excel_data(file_path)
            else:
                logger.debug("Keine Excel-Datei ausgewählt")
                
        except Exception as e:
            logger.error(f"Fehler beim Öffnen des Excel-Datei-Dialogs: {e}")
            messagebox.showerror("Fehler", f"Fehler beim Auswählen der Excel-Datei: {e}")
            
    def load_excel_data(self, file_path):
        """Lädt Excel-Daten und zeigt sie in der Tabelle"""
        logger.info(f"Lade Excel-Daten aus: {file_path}")
        
        try:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Excel-Datei nicht gefunden: {file_path}")
            
            # Excel-Datei einlesen (Header in Zeile 3)
            df = pd.read_excel(file_path, header=2)
            df.columns = df.columns.str.strip()
            
            logger.debug(f"Excel-Datei geladen: {len(df)} Zeilen, Spalten: {list(df.columns)}")
            
            # Flexible Spalten-Suche
            def find_column(possible_names):
                for name in possible_names:
                    for col in df.columns:
                        if name.lower() in col.lower() or col.lower() in name.lower():
                            return col
                return None
            
            # Suche nach Spalten mit verschiedenen möglichen Namen
            windpark_col = find_column(['windpark', 'windfarm', 'park', 'project', 'projekt'])
            land_col = find_column(['land', 'country', 'staat', 'nation'])
            sn_col = find_column(['sn', 'seriennummer', 'serial', 'serial_number', 'turbine_sn'])
            id_col = find_column(['turbine_id', 'id', 'anlagen_nr', 'turbinen_id', 'turbine_number'])
            hersteller_col = find_column(['hersteller', 'manufacturer', 'fabrikant', 'turbine_manufacturer'])
            
            logger.debug(f"Gefundene Spalten: Windpark={windpark_col}, Land={land_col}, "
                        f"Seriennummer={sn_col}, ID={id_col}, Hersteller={hersteller_col}")
            
            # Daten für Anzeige vorbereiten
            self.excel_data = []
            for index, row in df.iterrows():
                try:
                    data_row = {
                        "row_index": index,
                        "turbine_id": str(row.get(id_col, "")) if id_col else "",
                        "turbine_manufacturer": str(row.get(hersteller_col, "")) if hersteller_col else "",
                        "windfarm_name": str(row.get(windpark_col, "")) if windpark_col else "",
                        "windfarm_country": str(row.get(land_col, "")) if land_col else "",
                        "turbine_sn": str(row.get(sn_col, "")) if sn_col else ""
                    }
                    self.excel_data.append(data_row)
                    
                    # In Treeview einfügen
                    self.tree.insert("", "end", values=(
                        index + 1,  # Zeilennummer für Anzeige
                        data_row["windfarm_name"],
                        data_row["windfarm_country"],
                        data_row["turbine_sn"],
                        data_row["turbine_id"]
                    ))
                except Exception as e:
                    logger.warning(f"Fehler beim Verarbeiten von Zeile {index}: {e}")
                    continue
            
            # Buttons aktivieren
            self.load_btn.config(state=tk.NORMAL)
            self.update_btn.config(state=tk.NORMAL)
            
            success_msg = f"Excel-Datei erfolgreich geladen: {len(self.excel_data)} Zeilen\n\nGefundene Spalten:\nWindpark: {windpark_col or 'Nicht gefunden'}\nLand: {land_col or 'Nicht gefunden'}\nSeriennummer: {sn_col or 'Nicht gefunden'}\nID: {id_col or 'Nicht gefunden'}"
            logger.info(f"Excel-Daten erfolgreich geladen: {len(self.excel_data)} Einträge")
            messagebox.showinfo("Erfolg", success_msg)
            
        except FileNotFoundError as e:
            logger.error(f"Excel-Datei nicht gefunden: {e}")
            messagebox.showerror("Fehler", f"Excel-Datei nicht gefunden:\n{e}")
        except PermissionError as e:
            logger.error(f"Keine Berechtigung für Excel-Datei: {e}")
            messagebox.showerror("Fehler", f"Keine Berechtigung für Excel-Datei:\n{e}")
        except pd.errors.EmptyDataError as e:
            logger.error(f"Excel-Datei ist leer: {e}")
            messagebox.showerror("Fehler", "Excel-Datei ist leer oder ungültig")
        except pd.errors.ExcelFileError as e:
            logger.error(f"Ungültige Excel-Datei: {e}")
            messagebox.showerror("Fehler", f"Ungültige Excel-Datei:\n{e}")
        except Exception as e:
            logger.error(f"Unerwarteter Fehler beim Laden der Excel-Datei: {e}")
            logger.debug(f"Traceback: {traceback.format_exc()}")
            messagebox.showerror("Fehler", f"Fehler beim Laden der Excel-Datei:\n{e}")
            
    def on_row_select(self, event):
        """Wird aufgerufen, wenn eine Zeile ausgewählt wird"""
        selection = self.tree.selection()
        if selection:
            item = self.tree.item(selection[0])
            row_index = int(item['values'][0]) - 1  # 0-basiert
            
            if 0 <= row_index < len(self.excel_data):
                self.selected_row = self.excel_data[row_index]
                self.selection_label.config(text=f"Zeile {row_index + 1} ausgewählt")
                self.load_btn.config(state="normal")
                self.update_btn.config(state="normal")
            else:
                self.selected_row = None
                self.selection_label.config(text="Keine Zeile ausgewählt")
                self.load_btn.config(state="disabled")
                self.update_btn.config(state="disabled")
                
    def write_to_images(self):
        """Schreibt Grunddaten in alle Bilder"""
        if not self.selected_row:
            messagebox.showwarning("Warnung", "Bitte wählen Sie zuerst eine Zeile aus.")
            return
            
        if not hasattr(self.parent, 'current_folder') or not self.parent.current_folder:
            messagebox.showwarning("Warnung", "Bitte wählen Sie zuerst einen Bildordner aus.")
            return
            
        # Bestätigung
        result = messagebox.askyesno(
            "Bestätigung", 
            f"Möchten Sie die Grunddaten aus Zeile {self.tree.selection()[0]} in alle Bilder schreiben?\n\n"
            f"Windpark: {self.selected_row['windfarm_name']}\n"
            f"Land: {self.selected_row['windfarm_country']}\n"
            f"Seriennummer: {self.selected_row['turbine_sn']}\n"
            f"Turbinen-ID: {self.selected_row['turbine_id']}"
        )
        
        if result:
            self._process_images(self.selected_row, update_existing=False)
            
    def update_existing_data(self):
        """Aktualisiert bestehende Grunddaten in Bildern"""
        if not self.selected_row:
            messagebox.showwarning("Warnung", "Bitte wählen Sie zuerst eine Zeile aus.")
            return
            
        if not hasattr(self.parent, 'current_folder') or not self.parent.current_folder:
            messagebox.showwarning("Warnung", "Bitte wählen Sie zuerst einen Bildordner aus.")
            return
            
        # Bestätigung
        result = messagebox.askyesno(
            "Bestätigung", 
            f"Möchten Sie die bestehenden Grunddaten in allen Bildern aktualisieren?\n\n"
            f"Neue Daten:\n"
            f"Windpark: {self.selected_row['windfarm_name']}\n"
            f"Land: {self.selected_row['windfarm_country']}\n"
            f"Seriennummer: {self.selected_row['turbine_sn']}\n"
            f"Turbinen-ID: {self.selected_row['turbine_id']}"
        )
        
        if result:
            self._process_images(self.selected_row, update_existing=True)
            
    def _process_images(self, data, update_existing=False):
        """Verarbeitet alle Bilder im aktuellen Ordner"""
        try:
            image_files = [f for f in os.listdir(self.parent.current_folder) 
                          if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
            
            if not image_files:
                messagebox.showwarning("Warnung", "Keine Bilddateien im aktuellen Ordner gefunden.")
                return
                
            # Fortschrittsdialog
            progress_window = tk.Toplevel(self.dialog)
            progress_window.title("Verarbeitung...")
            progress_window.geometry(f"{PROGRESS_WINDOW_WIDTH}x{PROGRESS_WINDOW_HEIGHT}")
            progress_window.transient(self.dialog)
            progress_window.grab_set()
            
            progress_frame = ttk.Frame(progress_window, padding="20")
            progress_frame.pack(fill=tk.BOTH, expand=True)
            
            progress_label = ttk.Label(progress_frame, text="Bilder werden verarbeitet...")
            progress_label.pack(pady=(0, 10))
            
            progress_var = tk.DoubleVar()
            progress_bar = ttk.Progressbar(progress_frame, variable=progress_var, maximum=len(image_files))
            progress_bar.pack(fill=tk.X, pady=(0, 10))
            
            status_label = ttk.Label(progress_frame, text="")
            status_label.pack()
            
            # Zentrieren
            progress_window.update_idletasks()
            x = (progress_window.winfo_screenwidth() // 2) - (progress_window.winfo_width() // 2)
            y = (progress_window.winfo_screenheight() // 2) - (progress_window.winfo_height() // 2)
            progress_window.geometry(f"+{x}+{y}")
            
            processed = 0
            updated = 0
            skipped = 0
            
            for i, filename in enumerate(image_files):
                file_path = os.path.join(self.parent.current_folder, filename)
                status_label.config(text=f"Verarbeite: {filename}")
                progress_window.update()
                
                try:
                    # Bild öffnen
                    with Image.open(file_path) as img:
                        exif_data = img.getexif()
                        
                        # Bestehende UserComment lesen
                        existing_json = {}
                        existing_raw = ""
                        
                        for tag_id, value in exif_data.items():
                            if ExifTags.TAGS.get(tag_id) == 'UserComment':
                                try:
                                    if isinstance(value, bytes):
                                        if value.startswith(b"ASCII\0\0\0"):
                                            existing_raw = value[8:].decode("utf-8", errors="ignore")
                                        elif value.startswith(b"UNICODE\0"):
                                            existing_raw = value[8:].decode("utf-16", errors="ignore")
                                        else:
                                            existing_raw = value.decode("utf-8", errors="ignore")
                                    else:
                                        existing_raw = str(value)
                                        
                                    if existing_raw:
                                        existing_json = json.loads(existing_raw)
                                except (json.JSONDecodeError, TypeError):
                                    existing_json = {}
                        
                        # Grunddaten hinzufügen/aktualisieren
                        if update_existing:
                            # Nur aktualisieren, wenn bereits Grunddaten vorhanden
                            if any(key in existing_json for key in ['windpark', 'windpark_land', 'sn', 'anlagen_nr']):
                                existing_json.update({
                                    'windpark': data['windfarm_name'],
                                    'windpark_land': data['windfarm_country'],
                                    'sn': data['turbine_sn'],
                                    'anlagen_nr': data['turbine_id'],
                                    'hersteller': data['turbine_manufacturer']
                                })
                                updated += 1
                                print(f"DEBUG: Aktualisiert {filename} mit Grunddaten: {existing_json}")
                            else:
                                skipped += 1
                                print(f"DEBUG: Übersprungen {filename} - keine Grunddaten vorhanden")
                                continue
                        else:
                            # Neue Grunddaten hinzufügen
                            existing_json.update({
                                'windpark': data['windfarm_name'],
                                'windpark_land': data['windfarm_country'],
                                'sn': data['turbine_sn'],
                                'anlagen_nr': data['turbine_id'],
                                'hersteller': data['turbine_manufacturer']
                            })
                            updated += 1
                            print(f"DEBUG: Hinzugefügt {filename} mit Grunddaten: {existing_json}")
                        
                        # JSON in UserComment schreiben (mit ASCII-Prefix wie die Lesefunktion erwartet)
                        new_json_str = json.dumps(existing_json, ensure_ascii=False)
                        new_user_comment = f"ASCII\0\0\0{new_json_str}".encode('utf-8')
                        
                        print(f"DEBUG: JSON-String für {filename}: {new_json_str}")
                        print(f"DEBUG: UserComment-Länge: {len(new_user_comment)} bytes")
                        
                        # Exif-Daten aktualisieren (Exif-Objekt beibehalten)
                        exif_data[0x9286] = new_user_comment  # UserComment Tag
                        
                        # Bild mit neuen Exif-Daten speichern (als Bytes)
                        img.save(file_path, exif=exif_data.tobytes())
                        processed += 1
                        print(f"DEBUG: {filename} erfolgreich gespeichert")
                        
                except Exception as e:
                    print(f"Fehler bei {filename}: {e}")
                    continue
                    
                # Fortschritt aktualisieren
                progress_var.set(i + 1)
                progress_window.update()
                
            progress_window.destroy()
            
            # Ergebnis anzeigen
            if update_existing:
                messagebox.showinfo(
                    "Erfolg", 
                    f"Grunddaten aktualisiert:\n"
                    f"• {updated} Bilder aktualisiert\n"
                    f"• {skipped} Bilder übersprungen (keine Grunddaten vorhanden)\n"
                    f"• {processed} Bilder verarbeitet"
                )
            else:
                messagebox.showinfo(
                    "Erfolg", 
                    f"Grunddaten hinzugefügt:\n"
                    f"• {updated} Bilder aktualisiert\n"
                    f"• {processed} Bilder verarbeitet"
                )
                
        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Verarbeiten der Bilder:\n{e}")

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), relative_path)

if getattr(sys, 'frozen', False):
    log_dir = os.path.dirname(sys.executable)
else:
    log_dir = os.path.dirname(os.path.abspath(__file__))

CODE_FILE = resource_path('valid_kurzel.txt')
JSON_CONFIG_FILE = resource_path('GearBoxExiff.json')
LOG_FILE = os.path.join(log_dir, 'ocr_log.txt')
DETAILED_LOG_FILE = os.path.join(log_dir, 'detailed_log.txt')
LAST_FOLDER_FILE = os.path.join(log_dir, 'last_folder.txt')
_READER = None

excel_to_json = {
    "turbine_id": "anlagen_nr",
    "turbine_manufacturer": "hersteller",
    "windfarm_name": "windpark",
    "windfarm_country": "windpark_land",
    "turbine_sn": "sn",
    "gear_manufacturer": "getriebe_hersteller",
    "gear_model": "modell",
    "gear_sn": "gear_sn"
}

# Globale Funktion für dynamische Whitelist
def get_dynamic_whitelist(valid_kurzel):
    """Erstellt eine dynamische Whitelist aus gültigen Kürzeln"""
    valid_chars = set(''.join(valid_kurzel))
    return ''.join(sorted(valid_chars))

# Funktion für alternative Kürzel-Korrektur
def correct_alternative_kurzel(text, alternative_kurzel):
    """Korrigiert Text basierend auf alternativen Kürzeln"""
    if not text or not alternative_kurzel:
        return text
    
    # Direkte Übereinstimmung (case-insensitive)
    text_lower = text.lower().strip()
    if text_lower in alternative_kurzel:
        return alternative_kurzel[text_lower]
    
    # Fuzzy-Matching für ähnliche Varianten
    from difflib import get_close_matches
    matches = get_close_matches(text_lower, alternative_kurzel.keys(), n=1, cutoff=0.8)
    if matches:
        return alternative_kurzel[matches[0]]
    
    return text

# Neue verbesserte OCR-Klasse
class ImprovedOCR:
    def __init__(self, valid_kurzel, alternative_kurzel=None):
        self.valid_kurzel = valid_kurzel
        self.alternative_kurzel = alternative_kurzel or {}
        self.reader = easyocr.Reader(['de', 'en'])
        self._update_optimizations()
        
    def _update_optimizations(self):
        """Aktualisiert die OCR-Optimierungen basierend auf den aktuellen gültigen Kürzeln"""
        # Analysiere die aktuellen gültigen Kürzel
        self._analyze_valid_codes()
        
        # Optimierte Ersetzungen basierend auf den gültigen Kürzeln
        self.char_replacements = {
            'I': '1', 'O': '0', '|': '1', 'l': '1', 'i': '1',
            'S': '5', 'G': '6', 'B': '8', 'Z': '2', 'z': '2',
            'D': '0', 'Q': '0', 'U': '0',
            'A': '4', 'E': '3', 'F': '7', 'T': '7'
        }
        
        # Erlaubte Zeichen basierend auf gültigen Kürzeln
        self.allowed_chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-'
        
        # Häufige Fehler-Korrekturen basierend auf aktuellen Kürzeln
        self.common_fixes = self._generate_common_fixes()
        
        # Spezielle Regeln basierend auf aktuellen Kürzeln
        self.special_rules = self._generate_special_rules()
        
        print(f"OCR-Optimierungen aktualisiert - Anzahl gültige Kürzel: {len(self.valid_kurzel)}, "
              f"Erlaubte Zahlen: {self.allowed_numbers}, "
              f"Code-Muster: {list(self.code_patterns.keys())}")
    
    def _analyze_valid_codes(self):
        """Analysiert die gültigen Kürzel für optimierte Erkennung"""
        self.allowed_numbers = set()
        self.code_patterns = {}
        self.prefix_patterns = {}
        
        for code in self.valid_kurzel:
            # Extrahiere Zahlen aus dem Code
            numbers = re.findall(r'\d', code)
            self.allowed_numbers.update(numbers)
            
            # Analysiere Code-Muster
            if code.startswith('PL'):
                if 'B' in code:
                    if 'G' in code:
                        self.code_patterns['PLB_G'] = code
                    elif 'R' in code:
                        self.code_patterns['PLB_R'] = code
                else:
                    self.code_patterns['PL'] = code
            elif code.startswith('HSS'):
                self.code_patterns['HSS'] = code
            elif code.startswith('LSS'):
                self.code_patterns['LSS'] = code
            elif code.startswith('PLC'):
                self.code_patterns['PLC'] = code
            elif code.startswith('RG'):
                self.code_patterns['RG'] = code
            elif code.startswith('SUN'):
                self.code_patterns['SUN'] = code
            elif code.startswith('CONN'):
                self.code_patterns['CONN'] = code
            elif code.startswith('GEH'):
                self.code_patterns['GEH'] = code
        
        # Erstelle Präfix-Muster für bessere Erkennung
        for code in self.valid_kurzel:
            for i in range(2, len(code) + 1):
                prefix = code[:i]
                if prefix not in self.prefix_patterns:
                    self.prefix_patterns[prefix] = []
                self.prefix_patterns[prefix].append(code)
    
    def _generate_common_fixes(self):
        """Generiert häufige Fehler-Korrekturen basierend auf aktuellen Kürzeln"""
        fixes = {}
        
        # Z wird immer zu 2
        for code in self.valid_kurzel:
            if 'Z' in code:
                wrong_code = code.replace('2', 'Z')
                fixes[wrong_code] = code
        
        # Häufige Verwechslungen basierend auf aktuellen Kürzeln
        for code in self.valid_kurzel:
            # I -> 1
            if '1' in code:
                wrong_code = code.replace('1', 'I')
                fixes[wrong_code] = code
            # O -> 0
            if '0' in code:
                wrong_code = code.replace('0', 'O')
                fixes[wrong_code] = code
        
        return fixes
    
    def _generate_special_rules(self):
        """Generiert spezielle Regeln basierend auf aktuellen Kürzeln"""
        rules = {}
        
        # PL-Serien Regeln
        pl_codes = [c for c in self.valid_kurzel if c.startswith('PL')]
        if pl_codes:
            rules['PL'] = {
                'base_codes': [c for c in pl_codes if not 'B' in c],
                'b_g_codes': [c for c in pl_codes if 'B' in c and 'G' in c],
                'b_r_codes': [c for c in pl_codes if 'B' in c and 'R' in c]
            }
        
        # HSS/LSS Regeln
        hss_codes = [c for c in self.valid_kurzel if c.startswith('HSS')]
        lss_codes = [c for c in self.valid_kurzel if c.startswith('LSS')]
        
        if hss_codes:
            rules['HSS'] = {
                'base': 'HSS',
                'suffixes': [c[3:] for c in hss_codes if len(c) > 3]
            }
        
        if lss_codes:
            rules['LSS'] = {
                'base': 'LSS',
                'suffixes': [c[3:] for c in lss_codes if len(c) > 3]
            }
        
        return rules
    
    def update_valid_kurzel(self, new_valid_kurzel):
        """Aktualisiert die gültigen Kürzel und optimiert die OCR entsprechend"""
        self.valid_kurzel = new_valid_kurzel
        self._update_optimizations()
        print(f"OCR-Klasse aktualisiert - Neue Anzahl gültige Kürzel: {len(self.valid_kurzel)}")
    
    def detect_text_region_upper_left(self, image):
        """Erkennt Textbereich nur im oberen linken Drittel des Bildes"""
        if isinstance(image, Image.Image):
            img_cv = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        else:
            img_cv = image
            
        # Graustufen
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        
        # Definiere oberes linkes Drittel
        height, width = gray.shape
        upper_left_region = gray[0:height//3, 0:width//3]
        
        # Verschiedene Methoden zur ROI-Erkennung im oberen linken Bereich
        regions = []
        
        # Methode 1: Konturerkennung
        _, binary = cv2.threshold(upper_left_region, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if 20 < w < 150 and 10 < h < 80:  # Realistische Textgröße
                regions.append((x, y, w, h))
        
        # Methode 2: Template-basierte Erkennung
        _, thresh = cv2.threshold(upper_left_region, 200, 255, cv2.THRESH_BINARY)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        dilated = cv2.dilate(thresh, kernel, iterations=1)
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if 30 < w < 120 and 15 < h < 60:
                regions.append((x, y, w, h))
        
        # Wähle die beste Region basierend auf Position (bevorzuge obere Bereiche)
        if regions:
            # Bevorzuge Regionen in der oberen Hälfte des oberen linken Bereichs
            best_region = min(regions, key=lambda r: abs(r[1] - 20) + abs(r[2] * r[3] - 2000))
            return best_region
        
        # Fallback: Standard-Bereich im oberen linken Drittel
        return (10, 55, 100, 50)
    
    def preprocess_image(self, image, region=None):
        """Verbessertes Preprocessing: Schärfen, Kontrast erhöhen, Binarisierung für bessere OCR-Erkennung von SS/11"""
        import cv2
        import numpy as np
        from PIL import ImageEnhance
        # Region zuschneiden, falls angegeben
        if region:
            image = image.crop(region)
        # In Graustufen umwandeln
        image = image.convert('L')
        # Kontrast erhöhen
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(2.0)  # Kontrastfaktor ggf. anpassen
        # In NumPy-Array für OpenCV
        img_np = np.array(image)
        # Schärfen (Kernel)
        kernel = np.array([[0, -1, 0], [-1, 5,-1], [0, -1, 0]])
        img_np = cv2.filter2D(img_np, -1, kernel)
        # Binarisierung (Otsu)
        _, img_np = cv2.threshold(img_np, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        # Zurück zu PIL
        image = Image.fromarray(img_np)
        return image
    
    def extract_text_with_confidence(self, image):
        """OCR mit dynamischer Whitelist: Nur erlaubte Zeichen werden erkannt"""
        import easyocr
        # Preprocessing wie gehabt
        preprocessed = self.preprocess_image(image)
        # Dynamische Whitelist aus gültigen Kürzeln
        allowlist = get_dynamic_whitelist(self.valid_kurzel)
        reader = easyocr.Reader(['de', 'en'], gpu=False)
        # EasyOCR unterstützt allowlist als Parameter (nur in neueren Versionen)
        result = reader.readtext(np.array(preprocessed), allowlist=allowlist)
        # Fallback, falls allowlist nicht unterstützt wird:
        # result = reader.readtext(np.array(preprocessed))
        # Extrahiere bestes Ergebnis
        if result:
            best = max(result, key=lambda x: x[2])
            return {'text': best[1], 'confidence': best[2], 'raw_text': best[1], 'method': 'improved'}
        return {'text': None, 'confidence': 0.0, 'raw_text': '', 'method': 'improved'}
    
    def correct_text(self, text):
        """Dynamische Text-Korrektur basierend auf aktuellen gültigen Kürzeln. Gibt garantiert nur ein gültiges Kürzel zurück oder None."""
        # Entferne unerwünschte Zeichen
        text = re.sub(r'[^A-Z0-9\-]', '', text)
        
        # Ersetze häufige Fehler basierend auf den gültigen Kürzeln
        for old, new in self.char_replacements.items():
            text = text.replace(old, new)
        
        # Prüfe auf häufige Fehler-Korrekturen
        for wrong, correct in self.common_fixes.items():
            if wrong in text:
                text = text.replace(wrong, correct)
        
        # Spezielle Regeln für die gültigen Kürzel
        text = text.replace('Z', '2')
        for i in range(5, 10):
            text = text.replace(str(i), '1')
        text = text.replace('0', '1')
        
        # Exakte Übereinstimmung
        if text in self.valid_kurzel:
            return text
        
        # Alternative Kürzel-Korrektur
        corrected_text = correct_alternative_kurzel(text, self.alternative_kurzel)
        if corrected_text != text and corrected_text in self.valid_kurzel:
            return corrected_text
        
        # Fuzzy-Matching, aber nur gegen gültige Kürzel
        from difflib import get_close_matches
        matches = get_close_matches(text, self.valid_kurzel, n=1, cutoff=0.8)
        if matches:
            return matches[0]
        
        # Keine gültige Zuordnung gefunden
        return None  # oder z.B. 'UNGÜLTIG'

def sync_valid_codes():
    """Synchronisiert die gültigen Codes zwischen verschiedenen Speicherorten"""
    try:
        # Lade Codes aus Text-Datei
        text_codes = []
        if os.path.isfile(CODE_FILE):
            with open(CODE_FILE, 'r', encoding='utf-8') as f:
                text_codes = [line.strip() for line in f if line.strip()]
        
        # Lade Codes aus JSON-Konfiguration
        json_config = load_json_config()
        json_codes = json_config.get('valid_kurzel', [])
        
        # Vergleiche und synchronisiere
        if text_codes != json_codes:
            # Verwende die neueren Codes (Text-Datei hat Vorrang)
            if text_codes:
                # Aktualisiere JSON-Konfiguration
                json_config['valid_kurzel'] = text_codes
                save_json_config(json_config)
                print(f"Codes synchronisiert - Text-Datei: {len(text_codes)}, JSON: {len(json_codes)}")
            elif json_codes:
                # Aktualisiere Text-Datei
                with open(CODE_FILE, 'w', encoding='utf-8') as f:
                    for code in json_codes:
                        f.write(code + "\n")
                print(f"Codes synchronisiert - JSON: {len(json_codes)}, Text-Datei aktualisiert")
        
        return text_codes if text_codes else json_codes
        
    except Exception as e:
        print(f"Fehler bei Code-Synchronisation: {e}")
        return []

def validate_ocr_result(text, valid_kurzel):
    """Validiert OCR-Ergebnisse basierend auf gültigen Kürzeln"""
    if not text:
        return False, "Leerer Text"
    
    # Prüfe ob Text in gültigen Kürzeln enthalten ist
    if text in valid_kurzel:
        return True, "Exakte Übereinstimmung"
    
    # Prüfe auf gültige Struktur
    # Alle gültigen Kürzel bestehen nur aus Großbuchstaben, Zahlen 1-4 und Bindestrichen
    if not re.match(r'^[A-Z0-9\-]+$', text):
        return False, "Ungültige Zeichen enthalten"
    
    # Prüfe auf Zahlen außer 1-4
    if re.search(r'[5-9]', text):
        return False, "Ungültige Zahlen (nur 1-4 erlaubt)"
    
    # Prüfe auf 0 (nicht in gültigen Kürzeln)
    if '0' in text:
        return False, "0 nicht in gültigen Kürzeln"
    
    # Prüfe auf Z (wird zu 2)
    if 'Z' in text:
        return False, "Z wird zu 2 korrigiert"
    
    return True, "Struktur gültig, aber kein exakter Match"
# Alte OCR-Methode als Fallback
def old_ocr_method(image_path, valid_kurzel, alternative_kurzel=None):
    """Alte OCR-Methode als Fallback mit verbesserter Textkorrektur und dynamischer Whitelist"""
    try:
        img = Image.open(image_path)
        cimg = img.crop((10, 55, 110, 105))  # Bereich wie ursprünglich gewünscht
        cimg = cimg.convert('L')  # Graustufen
        cimg_np = np.array(cimg)
        _, bw = cv2.threshold(cimg_np, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        reader = get_reader()
        
        # Dynamische Whitelist aus gültigen Kürzeln
        allow = get_dynamic_whitelist(valid_kurzel)
        
        # Verbesserte Ersetzungen basierend auf gültigen Kürzeln
        char_replacements = {
            'I': '1', 'O': '0', '|': '1', 'l': '1', 'i': '1',
            'S': '5', 'G': '6', 'B': '8', 'Z': '2', 'z': '2',
            'D': '0', 'Q': '0', 'U': '0',
            'A': '4', 'E': '3', 'F': '7', 'T': '7'
        }
        
        res = reader.readtext(bw, detail=0, allowlist=allow)
        text = ''.join(res).upper()
        
        # Verbesserte Textkorrektur
        # 1. Ersetze häufige Fehler
        for old, new in char_replacements.items():
            text = text.replace(old, new)
        
        # 2. Z wird immer zu 2
        text = text.replace('Z', '2')
        
        # 3. Zahlen sind nur 1-4, ersetze andere
        for i in range(5, 10):
            text = text.replace(str(i), '1')
        text = text.replace('0', '1')  # 0 wird zu 1
        
        # 4. Alternative Kürzel-Korrektur
        if alternative_kurzel:
            corrected_text = correct_alternative_kurzel(text, alternative_kurzel)
            if corrected_text != text and corrected_text in valid_kurzel:
                final = corrected_text
            else:
                # 5. Fuzzy Matching mit höherem Cutoff
                match = get_close_matches(text, valid_kurzel, n=1, cutoff=0.7)
                final = match[0] if match else text
        else:
            # 4. Fuzzy Matching mit höherem Cutoff
            match = get_close_matches(text, valid_kurzel, n=1, cutoff=0.7)
            final = match[0] if match else text
        
        return {
            'text': final,
            'confidence': 0.5,  # Standard-Konfidenz für alte Methode
            'method': 'old_method',
            'raw_text': text
        }
    except Exception as e:
        print(f"Fehler in alter OCR-Methode: {e}")
        return {
            'text': None,
            'confidence': 0.0,
            'method': 'old_method_error',
            'raw_text': str(e)
        }

# Erweiterte alte OCR-Methode
def enhanced_old_method(image_path, valid_kurzel, alternative_kurzel=None):
    """Erweiterte OCR-Methode basierend auf der alten Methode mit verbesserten Features"""
    try:
        img = Image.open(image_path)
        cimg = img.crop((10, 55, 110, 105))  # Bereich wie ursprünglich gewünscht
        
        # Dynamische Whitelist aus gültigen Kürzeln
        allow = get_dynamic_whitelist(valid_kurzel)
        
        # Erweiterte Zeichenersetzungen basierend auf gültigen Kürzeln
        char_replacements = {
            'I': '1', 'O': '0', '|': '1', 'l': '1', 'i': '1',
            'S': '5', 'G': '6', 'B': '8', 'Z': '2', 'z': '2',
            'D': '0', 'Q': '0', 'U': '0',
            'A': '4', 'E': '3', 'F': '7', 'T': '7',
            'H': 'H', 'L': 'L', 'P': 'P', 'R': 'R', 'C': 'C'
        }
        
        # Mehrere Preprocessing-Varianten testen
        preprocessing_variants = []
        
        # Variante 1: Original (wie alte Methode)
        cimg_gray = cimg.convert('L')
        cimg_np = np.array(cimg_gray)
        _, bw1 = cv2.threshold(cimg_np, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        preprocessing_variants.append(('original', bw1))
        
        # Variante 2: Kontrast erhöht
        from PIL import ImageEnhance
        enhancer = ImageEnhance.Contrast(cimg_gray)
        cimg_contrast = enhancer.enhance(2.0)
        cimg_contrast_np = np.array(cimg_contrast)
        _, bw2 = cv2.threshold(cimg_contrast_np, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        preprocessing_variants.append(('contrast', bw2))
        
        # Variante 3: Schärfung
        kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
        cimg_sharp = cv2.filter2D(cimg_np, -1, kernel)
        _, bw3 = cv2.threshold(cimg_sharp, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        preprocessing_variants.append(('sharp', bw3))
        
        # Variante 4: Morphologische Operationen
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        cimg_morph = cv2.morphologyEx(cimg_np, cv2.MORPH_CLOSE, kernel)
        _, bw4 = cv2.threshold(cimg_morph, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        preprocessing_variants.append(('morph', bw4))
        
        reader = get_reader()
        best_result = None
        best_confidence = 0
        best_variant = 'original'
        
        # Teste alle Preprocessing-Varianten
        for variant_name, processed_img in preprocessing_variants:
            try:
                res = reader.readtext(processed_img, detail=0, allowlist=allow)
                text = ''.join(res).upper()
                
                # Erweiterte Textkorrektur
                # 1. Ersetze häufige Fehler
                for old, new in char_replacements.items():
                    text = text.replace(old, new)
                
                # 2. Z wird immer zu 2
                text = text.replace('Z', '2')
                
                # 3. Zahlen sind nur 1-4, ersetze andere
                for i in range(5, 10):
                    text = text.replace(str(i), '1')
                text = text.replace('0', '1')  # 0 wird zu 1
                
                # 4. Alternative Kürzel-Korrektur
                if alternative_kurzel:
                    corrected_text = correct_alternative_kurzel(text, alternative_kurzel)
                    if corrected_text != text and corrected_text in valid_kurzel:
                        final = corrected_text
                        confidence = 0.9  # Hohe Konfidenz für alternative Korrektur
                        if confidence > best_confidence:
                            best_result = {
                                'text': final,
                                'confidence': confidence,
                                'method': 'enhanced_old_alternative',
                                'raw_text': text,
                                'variant': 'alternative_correction',
                                'cutoff': confidence
                            }
                            best_confidence = confidence
                
                # 5. Fuzzy Matching mit verschiedenen Cutoffs
                cutoffs = [0.6, 0.7, 0.8, 0.9]
                for cutoff in cutoffs:
                    match = get_close_matches(text, valid_kurzel, n=1, cutoff=cutoff)
                    if match:
                        final = match[0]
                        confidence = cutoff  # Höherer Cutoff = höhere Konfidenz
                        if confidence > best_confidence:
                            best_result = {
                                'text': final,
                                'confidence': confidence,
                                'method': f'enhanced_old_{variant_name}',
                                'raw_text': text,
                                'variant': variant_name,
                                'cutoff': cutoff
                            }
                            best_confidence = confidence
                            best_variant = variant_name
                        break
                
                # Wenn kein Match gefunden, aber Text vorhanden
                if not match and text.strip():
                    # Prüfe, ob der Text bereits ein gültiges Kürzel ist
                    if text in valid_kurzel:
                        confidence = 0.9
                        if confidence > best_confidence:
                            best_result = {
                                'text': text,
                                'confidence': confidence,
                                'method': f'enhanced_old_{variant_name}_exact',
                                'raw_text': text,
                                'variant': variant_name,
                                'cutoff': 'exact'
                            }
                            best_confidence = confidence
                            best_variant = variant_name
                    else:
                        # Niedrige Konfidenz für nicht erkannten Text
                        confidence = 0.3
                        if confidence > best_confidence:
                            best_result = {
                                'text': text,
                                'confidence': confidence,
                                'method': f'enhanced_old_{variant_name}_unknown',
                                'raw_text': text,
                                'variant': variant_name,
                                'cutoff': 'unknown'
                            }
                            best_confidence = confidence
                            best_variant = variant_name
                            
            except Exception as e:
                print(f"Fehler in Variante {variant_name}: {e}")
                continue
        
        # Fallback, falls alle Varianten fehlschlagen
        if best_result is None:
            return {
                'text': None,
                'confidence': 0.0,
                'method': 'enhanced_old_failed',
                'raw_text': 'Keine Variante erfolgreich',
                'variant': 'none',
                'cutoff': 0.0
            }
        
        return best_result
        
    except Exception as e:
        print(f"Fehler in erweiterter OCR-Methode: {e}")
        return {
            'text': None,
            'confidence': 0.0,
            'method': 'enhanced_old_error',
            'raw_text': str(e),
            'variant': 'error',
            'cutoff': 0.0
        }

# Zentrale Konfigurationsverwaltung
class KurzelTableManager:
    """Erweiterte Verwaltung für Kürzel-Tabelle mit Langschreibweise und Kategorien"""
    
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.table_data = self.load_table_data()
        
    def load_table_data(self):
        """Lädt die Kürzel-Tabellendaten"""
        return self.config_manager.get_setting('kurzel_table', {})
    
    def save_table_data(self):
        """Speichert die Kürzel-Tabellendaten"""
        self.config_manager.set_setting('kurzel_table', self.table_data)
        self.config_manager.save_config()
    
    def get_default_kurzel_structure(self):
        """Gibt die Standard-Struktur für ein Kürzel zurück"""
        return {
            'kurzel_code': '',
            'name_de': '',
            'name_en': '',
            'category': 'Unbekannt',
            'subcategory': '',
            'description_de': '',
            'description_en': '',
            'priority': 'normal',
            'active': True,
            'frequency': 0,
            'created_date': None,
            'last_modified': None,
            'last_used': None,
            'image_type': 'Unbekannt',
            'damage_category': 'Unbekannt'
        }
    
    def add_kurzel(self, kurzel_data):
        """Fügt ein neues Kürzel zur Tabelle hinzu"""
        kurzel_code = kurzel_data.get('kurzel_code', '')
        if not kurzel_code:
            return False
            
        # Setze Standardwerte für fehlende Felder
        default_structure = self.get_default_kurzel_structure()
        default_structure.update(kurzel_data)
        default_structure['created_date'] = datetime.now().isoformat()
        default_structure['last_modified'] = datetime.now().isoformat()
        
        self.table_data[kurzel_code] = default_structure
        self.save_table_data()
        
        # Aktualisiere auch die einfache Liste
        self.update_valid_kurzel_list()
        
        write_detailed_log("info", "Kürzel zur Tabelle hinzugefügt", f"Code: {kurzel_code}")
        return True
    
    def update_kurzel(self, kurzel_code, kurzel_data):
        """Aktualisiert ein bestehendes Kürzel"""
        if kurzel_code in self.table_data:
            self.table_data[kurzel_code].update(kurzel_data)
            self.table_data[kurzel_code]['last_modified'] = datetime.now().isoformat()
            self.save_table_data()
            write_detailed_log("info", "Kürzel aktualisiert", f"Code: {kurzel_code}")
            return True
        return False
    
    def delete_kurzel(self, kurzel_code):
        """Löscht ein Kürzel aus der Tabelle"""
        if kurzel_code in self.table_data:
            del self.table_data[kurzel_code]
            self.save_table_data()
            self.update_valid_kurzel_list()
            write_detailed_log("info", "Kürzel gelöscht", f"Code: {kurzel_code}")
            return True
        return False
    
    def get_kurzel(self, kurzel_code):
        """Holt ein Kürzel aus der Tabelle"""
        return self.table_data.get(kurzel_code, None)
    
    def get_all_kurzel(self):
        """Holt alle Kürzel aus der Tabelle"""
        return self.table_data
    
    def get_kurzel_by_category(self, category):
        """Holt alle Kürzel einer bestimmten Kategorie"""
        return {k: v for k, v in self.table_data.items() if v.get('category') == category}
    
    def get_kurzel_by_image_type(self, image_type):
        """Holt alle Kürzel eines bestimmten Bildtyps"""
        return {k: v for k, v in self.table_data.items() if v.get('image_type') == image_type}
    
    def search_kurzel(self, search_term):
        """Sucht Kürzel nach verschiedenen Kriterien"""
        results = {}
        search_lower = search_term.lower()
        
        for kurzel_code, data in self.table_data.items():
            if (search_lower in kurzel_code.lower() or
                search_lower in data.get('name_de', '').lower() or
                search_lower in data.get('name_en', '').lower() or
                search_lower in data.get('description_de', '').lower() or
                search_lower in data.get('description_en', '').lower()):
                results[kurzel_code] = data
        
        return results
    
    def update_valid_kurzel_list(self):
        """Aktualisiert die einfache Kürzel-Liste basierend auf der Tabelle"""
        valid_kurzel = [k for k, v in self.table_data.items() if v.get('active', True)]
        self.config_manager.set_setting('valid_kurzel', valid_kurzel)
        self.config_manager.save_config()
    
    def export_to_csv(self, filename=None):
        """Exportiert die Kürzel-Tabelle als CSV"""
        if filename is None:
            filename = f"kurzel_table_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        try:
            import csv
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'kurzel_code', 'name_de', 'name_en', 'category', 'subcategory',
                    'description_de', 'description_en', 'priority', 'active',
                    'frequency', 'image_type', 'damage_category', 'created_date', 'last_modified'
                ]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for kurzel_code, data in self.table_data.items():
                    row = {'kurzel_code': kurzel_code}
                    row.update(data)
                    writer.writerow(row)
            
            write_detailed_log("info", "Kürzel-Tabelle exportiert", f"Datei: {filename}")
            return filename
        except Exception as e:
            write_detailed_log("error", "Fehler beim CSV-Export", str(e))
            return None
    
    def import_from_csv(self, filename):
        """Importiert Kürzel-Tabelle aus CSV"""
        try:
            import csv
            imported_count = 0
            
            with safe_csv_open(filename, 'r') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    kurzel_code = row.get('kurzel_code', '')
                    if kurzel_code:
                        # Konvertiere String-Werte
                        if 'active' in row:
                            row['active'] = row['active'].lower() == 'true'
                        if 'frequency' in row:
                            try:
                                row['frequency'] = int(row['frequency'])
                            except:
                                row['frequency'] = 0
                        
                        self.table_data[kurzel_code] = row
                        imported_count += 1
            
            self.save_table_data()
            self.update_valid_kurzel_list()
            
            write_detailed_log("info", "Kürzel-Tabelle importiert", f"Anzahl: {imported_count}")
            return imported_count
        except Exception as e:
            write_detailed_log("error", "Fehler beim CSV-Import", str(e))
            return 0
class CentralConfigManager:
    """Zentrale Verwaltung aller Programm-Einstellungen"""
    
    def __init__(self):
        self.config_file = JSON_CONFIG_FILE
        self.config = self.load_config()
        self.kurzel_table_manager = KurzelTableManager(self)
        
    def load_config(self):
        """Lädt die zentrale Konfiguration"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    print(f"Zentrale Konfiguration geladen: {self.config_file}")
                    return self._migrate_config(config)
            except Exception as e:
                print(f"Fehler beim Laden der Konfiguration {self.config_file}: {e}")
        
        # Erstelle Standard-Konfiguration
        default_config = self._get_default_config()
        self.save_config(default_config)
        return default_config
    
    def save_config(self, config=None):
        """Speichert die zentrale Konfiguration"""
        if config is None:
            config = self.config
        
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            print(f"Zentrale Konfiguration gespeichert: {self.config_file}")
            self.config = config
            return True
        except Exception as e:
            print(f"Fehler beim Speichern der Konfiguration {self.config_file}: {e}")
            return False
    
    def _get_default_config(self):
        """Erstellt die Standard-Konfiguration"""
        return {
            "ocr_settings": {
                "active_method": "improved",  # "improved", "white_box", "old"
                "confidence_threshold": 0.3,
                "fallback_enabled": True,
                "alternative_kurzel_enabled": True
            },
            # Gültige Kürzel mit erweiterten Informationen
            "valid_kurzel": [
                'HSS', 'HSSR', 'HSSGR', 'HSSGG', 'LSS', 'LSSR', 'LSSGR', 'LSSGG',
                'PLC2GR', 'PLC2GG', 'PLC2R', 'RG2', 'SUN2', 'PL2-1', 'PLB2G-1', 'PLB2R-1',
                'PL2-2', 'PLB2G-2', 'PLB2R-2', 'PL2-3', 'PLB2G-3', 'PLB2R-3',
                'PLC1G', 'PLC1R', 'RG1', 'SUN1', 'PL1-1', 'PLB1G-1', 'PLB1R-1',
                'PL1-2', 'PLB1G-2', 'PLB1R-2', 'PL1-3', 'PLB1G-3', 'PLB1R-3',
                'PL1-4', 'PLB1G-4', 'PLB1R-4'
            ],
            
            # Alternative Kürzel für OCR-Korrektur
            "alternative_kurzel": {
                "hss": "HSS",
                "hssr": "HSSR", 
                "hssgr": "HSSGR",
                "hssgg": "HSSGG",
                "lss": "LSS",
                "lssr": "LSSR",
                "lssgr": "LSSGR", 
                "lssgg": "LSSGG",
                "plc2gr": "PLC2GR",
                "plc2gg": "PLC2GG",
                "plc2r": "PLC2R",
                "rg2": "RG2",
                "sun2": "SUN2",
                "pl2-1": "PL2-1",
                "plb2g-1": "PLB2G-1",
                "plb2r-1": "PLB2R-1",
                "pl2-2": "PL2-2",
                "plb2g-2": "PLB2G-2",
                "plb2r-2": "PLB2R-2",
                "pl2-3": "PL2-3",
                "plb2g-3": "PLB2G-3",
                "plb2r-3": "PLB2R-3",
                "plc1g": "PLC1G",
                "plc1r": "PLC1R",
                "rg1": "RG1",
                "sun1": "SUN1",
                "pl1-1": "PL1-1",
                "plb1g-1": "PLB1G-1",
                "plb1r-1": "PLB1R-1",
                "pl1-2": "PL1-2",
                "plb1g-2": "PLB1G-2",
                "plb1r-2": "PLB1R-2",
                "pl1-3": "PL1-3",
                "plb1g-3": "PLB1G-3",
                "plb1r-3": "PLB1R-3",
                "pl1-4": "PL1-4",
                "plb1g-4": "PLB1G-4",
                "plb1r-4": "PLB1R-4"
            },
            
            # Erweiterte Kürzel-Informationen
            "kurzel_details": {
                "HSS": {
                    "name": "Hauptschmierstelle",
                    "description": "Hauptschmierstelle für Getriebe",
                    "category": "Schmierung",
                    "priority": 1,
                    "frequency": "häufig",
                    "location": "Getriebe",
                    "components": ["Schmierpumpe", "Schmierleitungen"],
                    "tags": ["schmierung", "haupt", "getriebe"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "HSSR": {
                    "name": "Hauptschmierstelle Reserve",
                    "description": "Reserve-Hauptschmierstelle",
                    "category": "Schmierung",
                    "priority": 2,
                    "frequency": "mittel",
                    "location": "Getriebe",
                    "components": ["Reserve-Schmierpumpe"],
                    "tags": ["schmierung", "reserve", "backup"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "HSSGR": {
                    "name": "Hauptschmierstelle Getriebe Reserve",
                    "description": "Getriebe-Hauptschmierstelle Reserve",
                    "category": "Schmierung",
                    "priority": 2,
                    "frequency": "mittel",
                    "location": "Getriebe",
                    "components": ["Getriebe-Schmierpumpe"],
                    "tags": ["schmierung", "getriebe", "reserve"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "HSSGG": {
                    "name": "Hauptschmierstelle Getriebe Grund",
                    "description": "Getriebe-Hauptschmierstelle Grund",
                    "category": "Schmierung",
                    "priority": 1,
                    "frequency": "häufig",
                    "location": "Getriebe",
                    "components": ["Grund-Schmierpumpe"],
                    "tags": ["schmierung", "getriebe", "grund"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "LSS": {
                    "name": "Lagerschmierstelle",
                    "description": "Schmierstelle für Lager",
                    "category": "Schmierung",
                    "priority": 1,
                    "frequency": "häufig",
                    "location": "Lager",
                    "components": ["Lager-Schmierpumpe"],
                    "tags": ["schmierung", "lager"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "LSSR": {
                    "name": "Lagerschmierstelle Reserve",
                    "description": "Reserve-Lagerschmierstelle",
                    "category": "Schmierung",
                    "priority": 2,
                    "frequency": "mittel",
                    "location": "Lager",
                    "components": ["Reserve-Lager-Schmierpumpe"],
                    "tags": ["schmierung", "lager", "reserve"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "LSSGR": {
                    "name": "Lagerschmierstelle Getriebe Reserve",
                    "description": "Getriebe-Lagerschmierstelle Reserve",
                    "category": "Schmierung",
                    "priority": 2,
                    "frequency": "mittel",
                    "location": "Lager",
                    "components": ["Getriebe-Lager-Schmierpumpe"],
                    "tags": ["schmierung", "lager", "getriebe", "reserve"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "LSSGG": {
                    "name": "Lagerschmierstelle Getriebe Grund",
                    "description": "Getriebe-Lagerschmierstelle Grund",
                    "category": "Schmierung",
                    "priority": 1,
                    "frequency": "häufig",
                    "location": "Lager",
                    "components": ["Grund-Lager-Schmierpumpe"],
                    "tags": ["schmierung", "lager", "getriebe", "grund"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "PLC2GR": {
                    "name": "Planetenstufe 2 Getriebe Reserve",
                    "description": "Reserve-Planetenstufe 2 Getriebe",
                    "category": "Planetengetriebe",
                    "priority": 2,
                    "frequency": "mittel",
                    "location": "Planetenstufe 2",
                    "components": ["Planetenräder", "Sonnenrad", "Hohlrad"],
                    "tags": ["planeten", "stufe2", "getriebe", "reserve"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "PLC2GG": {
                    "name": "Planetenstufe 2 Getriebe Grund",
                    "description": "Grund-Planetenstufe 2 Getriebe",
                    "category": "Planetengetriebe",
                    "priority": 1,
                    "frequency": "häufig",
                    "location": "Planetenstufe 2",
                    "components": ["Planetenräder", "Sonnenrad", "Hohlrad"],
                    "tags": ["planeten", "stufe2", "getriebe", "grund"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "PLC2R": {
                    "name": "Planetenstufe 2 Reserve",
                    "description": "Reserve-Planetenstufe 2",
                    "category": "Planetengetriebe",
                    "priority": 2,
                    "frequency": "mittel",
                    "location": "Planetenstufe 2",
                    "components": ["Planetenräder", "Sonnenrad", "Hohlrad"],
                    "tags": ["planeten", "stufe2", "reserve"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "RG2": {
                    "name": "Ritzel Getriebe 2",
                    "description": "Ritzel für Getriebe Stufe 2",
                    "category": "Ritzel",
                    "priority": 1,
                    "frequency": "häufig",
                    "location": "Getriebe Stufe 2",
                    "components": ["Ritzel", "Zahnrad"],
                    "tags": ["ritzel", "getriebe", "stufe2"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "SUN2": {
                    "name": "Sonnenrad 2",
                    "description": "Sonnenrad für Stufe 2",
                    "category": "Planetengetriebe",
                    "priority": 1,
                    "frequency": "häufig",
                    "location": "Planetenstufe 2",
                    "components": ["Sonnenrad"],
                    "tags": ["sonnenrad", "stufe2", "planeten"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "PL2-1": {
                    "name": "Planetenstufe 2 Position 1",
                    "description": "Planetenstufe 2 an Position 1",
                    "category": "Planetengetriebe",
                    "priority": 1,
                    "frequency": "häufig",
                    "location": "Planetenstufe 2",
                    "components": ["Planetenräder"],
                    "tags": ["planeten", "stufe2", "position1"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "PL2-2": {
                    "name": "Planetenstufe 2 Position 2",
                    "description": "Planetenstufe 2 an Position 2",
                    "category": "Planetengetriebe",
                    "priority": 1,
                    "frequency": "häufig",
                    "location": "Planetenstufe 2",
                    "components": ["Planetenräder"],
                    "tags": ["planeten", "stufe2", "position2"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "PL2-3": {
                    "name": "Planetenstufe 2 Position 3",
                    "description": "Planetenstufe 2 an Position 3",
                    "category": "Planetengetriebe",
                    "priority": 1,
                    "frequency": "häufig",
                    "location": "Planetenstufe 2",
                    "components": ["Planetenräder"],
                    "tags": ["planeten", "stufe2", "position3"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "PLB2G-1": {
                    "name": "Planetenstufe 2 Getriebe Position 1",
                    "description": "Planetenstufe 2 Getriebe an Position 1",
                    "category": "Planetengetriebe",
                    "priority": 1,
                    "frequency": "häufig",
                    "location": "Planetenstufe 2",
                    "components": ["Planetenräder", "Getriebe"],
                    "tags": ["planeten", "stufe2", "getriebe", "position1"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "PLB2G-2": {
                    "name": "Planetenstufe 2 Getriebe Position 2",
                    "description": "Planetenstufe 2 Getriebe an Position 2",
                    "category": "Planetengetriebe",
                    "priority": 1,
                    "frequency": "häufig",
                    "location": "Planetenstufe 2",
                    "components": ["Planetenräder", "Getriebe"],
                    "tags": ["planeten", "stufe2", "getriebe", "position2"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "PLB2G-3": {
                    "name": "Planetenstufe 2 Getriebe Position 3",
                    "description": "Planetenstufe 2 Getriebe an Position 3",
                    "category": "Planetengetriebe",
                    "priority": 1,
                    "frequency": "häufig",
                    "location": "Planetenstufe 2",
                    "components": ["Planetenräder", "Getriebe"],
                    "tags": ["planeten", "stufe2", "getriebe", "position3"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "PLB2R-1": {
                    "name": "Planetenstufe 2 Reserve Position 1",
                    "description": "Planetenstufe 2 Reserve an Position 1",
                    "category": "Planetengetriebe",
                    "priority": 2,
                    "frequency": "mittel",
                    "location": "Planetenstufe 2",
                    "components": ["Planetenräder", "Reserve"],
                    "tags": ["planeten", "stufe2", "reserve", "position1"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "PLB2R-2": {
                    "name": "Planetenstufe 2 Reserve Position 2",
                    "description": "Planetenstufe 2 Reserve an Position 2",
                    "category": "Planetengetriebe",
                    "priority": 2,
                    "frequency": "mittel",
                    "location": "Planetenstufe 2",
                    "components": ["Planetenräder", "Reserve"],
                    "tags": ["planeten", "stufe2", "reserve", "position2"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "PLB2R-3": {
                    "name": "Planetenstufe 2 Reserve Position 3",
                    "description": "Planetenstufe 2 Reserve an Position 3",
                    "category": "Planetengetriebe",
                    "priority": 2,
                    "frequency": "mittel",
                    "location": "Planetenstufe 2",
                    "components": ["Planetenräder", "Reserve"],
                    "tags": ["planeten", "stufe2", "reserve", "position3"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "PLC1G": {
                    "name": "Planetenstufe 1 Getriebe",
                    "description": "Planetenstufe 1 Getriebe",
                    "category": "Planetengetriebe",
                    "priority": 1,
                    "frequency": "häufig",
                    "location": "Planetenstufe 1",
                    "components": ["Planetenräder", "Sonnenrad", "Hohlrad"],
                    "tags": ["planeten", "stufe1", "getriebe"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "PLC1R": {
                    "name": "Planetenstufe 1 Reserve",
                    "description": "Planetenstufe 1 Reserve",
                    "category": "Planetengetriebe",
                    "priority": 2,
                    "frequency": "mittel",
                    "location": "Planetenstufe 1",
                    "components": ["Planetenräder", "Sonnenrad", "Hohlrad"],
                    "tags": ["planeten", "stufe1", "reserve"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "RG1": {
                    "name": "Ritzel Getriebe 1",
                    "description": "Ritzel für Getriebe Stufe 1",
                    "category": "Ritzel",
                    "priority": 1,
                    "frequency": "häufig",
                    "location": "Getriebe Stufe 1",
                    "components": ["Ritzel", "Zahnrad"],
                    "tags": ["ritzel", "getriebe", "stufe1"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "SUN1": {
                    "name": "Sonnenrad 1",
                    "description": "Sonnenrad für Stufe 1",
                    "category": "Planetengetriebe",
                    "priority": 1,
                    "frequency": "häufig",
                    "location": "Planetenstufe 1",
                    "components": ["Sonnenrad"],
                    "tags": ["sonnenrad", "stufe1", "planeten"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "PL1-1": {
                    "name": "Planetenstufe 1 Position 1",
                    "description": "Planetenstufe 1 an Position 1",
                    "category": "Planetengetriebe",
                    "priority": 1,
                    "frequency": "häufig",
                    "location": "Planetenstufe 1",
                    "components": ["Planetenräder"],
                    "tags": ["planeten", "stufe1", "position1"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "PL1-2": {
                    "name": "Planetenstufe 1 Position 2",
                    "description": "Planetenstufe 1 an Position 2",
                    "category": "Planetengetriebe",
                    "priority": 1,
                    "frequency": "häufig",
                    "location": "Planetenstufe 1",
                    "components": ["Planetenräder"],
                    "tags": ["planeten", "stufe1", "position2"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "PL1-3": {
                    "name": "Planetenstufe 1 Position 3",
                    "description": "Planetenstufe 1 an Position 3",
                    "category": "Planetengetriebe",
                    "priority": 1,
                    "frequency": "häufig",
                    "location": "Planetenstufe 1",
                    "components": ["Planetenräder"],
                    "tags": ["planeten", "stufe1", "position3"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "PL1-4": {
                    "name": "Planetenstufe 1 Position 4",
                    "description": "Planetenstufe 1 an Position 4",
                    "category": "Planetengetriebe",
                    "priority": 1,
                    "frequency": "häufig",
                    "location": "Planetenstufe 1",
                    "components": ["Planetenräder"],
                    "tags": ["planeten", "stufe1", "position4"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "PLB1G-1": {
                    "name": "Planetenstufe 1 Getriebe Position 1",
                    "description": "Planetenstufe 1 Getriebe an Position 1",
                    "category": "Planetengetriebe",
                    "priority": 1,
                    "frequency": "häufig",
                    "location": "Planetenstufe 1",
                    "components": ["Planetenräder", "Getriebe"],
                    "tags": ["planeten", "stufe1", "getriebe", "position1"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "PLB1G-2": {
                    "name": "Planetenstufe 1 Getriebe Position 2",
                    "description": "Planetenstufe 1 Getriebe an Position 2",
                    "category": "Planetengetriebe",
                    "priority": 1,
                    "frequency": "häufig",
                    "location": "Planetenstufe 1",
                    "components": ["Planetenräder", "Getriebe"],
                    "tags": ["planeten", "stufe1", "getriebe", "position2"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "PLB1G-3": {
                    "name": "Planetenstufe 1 Getriebe Position 3",
                    "description": "Planetenstufe 1 Getriebe an Position 3",
                    "category": "Planetengetriebe",
                    "priority": 1,
                    "frequency": "häufig",
                    "location": "Planetenstufe 1",
                    "components": ["Planetenräder", "Getriebe"],
                    "tags": ["planeten", "stufe1", "getriebe", "position3"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "PLB1G-4": {
                    "name": "Planetenstufe 1 Getriebe Position 4",
                    "description": "Planetenstufe 1 Getriebe an Position 4",
                    "category": "Planetengetriebe",
                    "priority": 1,
                    "frequency": "häufig",
                    "location": "Planetenstufe 1",
                    "components": ["Planetenräder", "Getriebe"],
                    "tags": ["planeten", "stufe1", "getriebe", "position4"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "PLB1R-1": {
                    "name": "Planetenstufe 1 Reserve Position 1",
                    "description": "Planetenstufe 1 Reserve an Position 1",
                    "category": "Planetengetriebe",
                    "priority": 2,
                    "frequency": "mittel",
                    "location": "Planetenstufe 1",
                    "components": ["Planetenräder", "Reserve"],
                    "tags": ["planeten", "stufe1", "reserve", "position1"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "PLB1R-2": {
                    "name": "Planetenstufe 1 Reserve Position 2",
                    "description": "Planetenstufe 1 Reserve an Position 2",
                    "category": "Planetengetriebe",
                    "priority": 2,
                    "frequency": "mittel",
                    "location": "Planetenstufe 1",
                    "components": ["Planetenräder", "Reserve"],
                    "tags": ["planeten", "stufe1", "reserve", "position2"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "PLB1R-3": {
                    "name": "Planetenstufe 1 Reserve Position 3",
                    "description": "Planetenstufe 1 Reserve an Position 3",
                    "category": "Planetengetriebe",
                    "priority": 2,
                    "frequency": "mittel",
                    "location": "Planetenstufe 1",
                    "components": ["Planetenräder", "Reserve"],
                    "tags": ["planeten", "stufe1", "reserve", "position3"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                },
                "PLB1R-4": {
                    "name": "Planetenstufe 1 Reserve Position 4",
                    "description": "Planetenstufe 1 Reserve an Position 4",
                    "category": "Planetengetriebe",
                    "priority": 2,
                    "frequency": "mittel",
                    "location": "Planetenstufe 1",
                    "components": ["Planetenräder", "Reserve"],
                    "tags": ["planeten", "stufe1", "reserve", "position4"],
                    "created_date": "",
                    "last_modified": "",
                    "notes": "",
                    "active": True
                }
            },
            
            # Kürzel-Kategorien
            "kurzel_categories": {
                "Schmierung": {
                    "description": "Schmierstellen und Schmiersysteme",
                    "color": "#4CAF50",
                    "icon": "🔧",
                    "priority": 1
                },
                "Planetengetriebe": {
                    "description": "Planetengetriebe-Komponenten",
                    "color": "#2196F3",
                    "icon": "⚙️",
                    "priority": 2
                },
                "Ritzel": {
                    "description": "Ritzel und Zahnräder",
                    "color": "#FF9800",
                    "icon": "🦷",
                    "priority": 3
                }
            },
            
            # Kürzel-Statistiken
            "kurzel_statistics": {
                "total_count": 0,
                "active_count": 0,
                "inactive_count": 0,
                "by_category": {},
                "by_priority": {},
                "by_frequency": {},
                "last_updated": ""
            },
            
            # Schadenskategorien (mehrsprachig)
            "damage_categories": {
                "de": [
                    "Visuell keine Defekte", "Kratzer", "Zykloidische Kratzer", "Stillstandsmarken",
                    "Verschmierung", "Partikeldurchgang", "Überrollmarken", "Pittings", "Sonstige"
                ],
                "en": [
                    "Visually no defects", "Scratches", "Cycloid Scratches", "Standstill marks",
                    "Smearing", "Particle passage", "Overrolling Marks", "Pitting", "Others"
                ]
            },
            
            # Bildart-Kategorien (mehrsprachig)
            "image_types": {
                "de": ["Wälzkörper", "Innenring", "Außenring", "Käfig", "Zahnrad"],
                "en": ["Rolling Element", "Inner ring", "Outer ring", "Cage", "Gear"]
            },
            
            # Schadensbewertungs-Optionen (mehrsprachig)
            "image_quality_options": {
                "de": ["Gut", "Normal", "Schlecht", "Verschleiß", "Beschädigt", "Unbekannt"],
                "en": ["Good", "Normal", "Poor", "Traces of wear", "Damage", "Unknown"]
            },
            
            # Bild verwenden Optionen (mehrsprachig)
            "use_image_options": {
                "de": ["ja", "nein"],
                "en": ["yes", "no"]
            },
            
            # Sprache und Lokalisierung
            "localization": {
                "current_language": "en",
                "available_languages": ["de", "en"],
                "auto_detect_language": True
            },
            
            # Anzeige-Einstellungen
            "display": {
                "window_width": 1080,
                "window_height": 800,
                "window_x": None,
                "window_y": None,
                "maximized": False,
                "save_window_position": True,
                "image_zoom": 1.0,
                "show_filename": True,
                "show_counter": True,
                "theme": "default",
                "font_size": 10,
                "filter_zero_codes": True
            },
            
            # Navigation und Benutzerfreundlichkeit
            "navigation": {
                "auto_save": True,
                "confirm_unsaved": True,
                "keyboard_shortcuts": True,
                "auto_load_last_folder": True,
                "remember_last_image": True
            },
            
            # Projekt-Daten
            "project_data": {
                "windpark": "",
                "windpark_land": "",
                "sn": "",
                "anlagen_nr": "",
                "hersteller": "",
                "getriebe_hersteller": "",
                "hersteller_2": "",
                "modell": "",
                "gear_sn": ""
            },
            
            # Benutzerdefinierte Felder
            "custom_data": {
                "field1": "",
                "field2": "",
                "field3": "",
                "field4": "",
                "field5": "",
                "field6": ""
            },
            
            # Export und Berichte
            "export": {
                "auto_backup": True,
                "backup_interval": 24,
                "export_format": "json",
                "include_exif_data": True,
                "include_statistics": True,
                "report_template": "default"
            },
            
            # Performance und Cache
            "performance": {
                "thumbnail_cache_size": 100,
                "max_image_size": 2048,
                "lazy_loading": True,
                "cache_evaluation_data": True,
                "max_cache_size": 1000
            },
            
            # Logging und Debugging
            "logging": {
                "log_level": "info",
                "save_detailed_logs": True,
                "log_rotation": True,
                "max_log_size": 10,
                "debug_mode": False
            },
            
            # Datei-Pfade und Verzeichnisse
            "paths": {
                "last_folder": "",
                "backup_directory": "Backups",
                "log_directory": "logs",
                "temp_directory": "temp"
            },
            
            # Letzte Button-Auswahlen
            "last_selections": {
                "open_folder": "",
                "excel_file": "",
                "analyze_folder": "",
                "exif_folder": ""
            },
            
            # Tag-Management
            "tag_management": {
                "auto_update_tags": True,
                "tag_structure_file": "tag_structure.json",
                "default_tag_structure": {},
                "external_ocr_tags": {}
            },
            
            # Version und Metadaten
            "metadata": {
                "version": "1.0.0",
                "last_updated": "",
                "config_version": "1.0",
                "migration_history": []
            }
        }
    def _migrate_config(self, config):
        """Migriert alte Konfigurationen zu neuem Format"""
        default_config = self._get_default_config()
        migrated = False
        
        # Migration von alten Top-Level-Keys
        old_keys = {
            "damage_categories": "damage_categories.de",
            "image_types": "image_types.de", 
            "use_image_options": "use_image_options.de",
            "image_quality_options": "image_quality_options.de",
            "filter_zero_codes": "display.filter_zero_codes",
            "current_language": "localization.current_language",
            "project_data": "project_data",
            "custom_data": "custom_data",
            "valid_kurzel": "valid_kurzel"
        }
        
        for old_key, new_path in old_keys.items():
            if old_key in config:
                # Speichere alten Wert
                old_value = config[old_key]
                
                # Setze neuen Wert basierend auf Pfad
                if "." in new_path:
                    section, key = new_path.split(".", 1)
                    if section not in config:
                        config[section] = default_config[section]
                    config[section][key] = old_value
                else:
                    config[new_path] = old_value
                
                # Entferne alten Key
                del config[old_key]
                migrated = True
        
        # Aktualisiere Metadaten
        if migrated:
            config["metadata"]["last_updated"] = datetime.now().isoformat()
            config["metadata"]["migration_history"].append({
                "date": datetime.now().isoformat(),
                "type": "migration",
                "description": "Migration von altem Konfigurationsformat"
            })
        
        # Stelle sicher, dass alle erforderlichen Sektionen existieren
        for section, default_section in default_config.items():
            if section not in config:
                config[section] = default_section.copy()
            elif isinstance(default_section, dict):
                for key, default_value in default_section.items():
                    if key not in config[section]:
                        config[section][key] = default_value
        
        return config
    
    def get_setting(self, path, default=None):
        """Holt eine Einstellung über Pfad-Notation (z.B. 'display.window_width')"""
        keys = path.split('.')
        value = self.config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def set_setting(self, path, value):
        """Setzt eine Einstellung über Pfad-Notation"""
        keys = path.split('.')
        config = self.config
        
        # Navigiere zu der Sektion
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]
        
        # Setze den Wert
        config[keys[-1]] = value
        
        # Speichere Konfiguration
        return self.save_config()
    
    def get_language_specific_list(self, list_type, language=None):
        """Holt eine sprachspezifische Liste"""
        if language is None:
            language = self.get_setting('localization.current_language', 'de')
        
        return self.get_setting(f'{list_type}.{language}', [])
    
    def update_valid_kurzel(self, new_kurzel):
        """Aktualisiert die gültigen Kürzel"""
        self.config['valid_kurzel'] = new_kurzel
        return self.save_config()
    
    def get_current_language_config(self):
        """Holt die aktuelle Sprachkonfiguration"""
        current_lang = self.get_setting('localization.current_language', 'de')
        return {
            'damage_categories': self.get_language_specific_list('damage_categories', current_lang),
            'image_types': self.get_language_specific_list('image_types', current_lang),
            'image_quality_options': self.get_language_specific_list('image_quality_options', current_lang),
            'use_image_options': self.get_language_specific_list('use_image_options', current_lang)
        }
    
    # Erweiterte Kürzel-Verwaltung
    def get_kurzel_details(self, kurzel_code):
        """Holt detaillierte Informationen zu einem Kürzel"""
        kurzel_details = self.get_setting('kurzel_details', {})
        return kurzel_details.get(kurzel_code, {})
    
    def set_kurzel_details(self, kurzel_code, details):
        """Setzt detaillierte Informationen für ein Kürzel"""
        kurzel_details = self.get_setting('kurzel_details', {})
        kurzel_details[kurzel_code] = details
        self.set_setting('kurzel_details', kurzel_details)
        
        # Aktualisiere Statistiken
        self.update_kurzel_statistics()
        
        return True
    
    def add_kurzel(self, kurzel_code, details):
        """Fügt ein neues Kürzel hinzu"""
        # Füge zur Liste hinzu
        valid_kurzel = self.get_setting('valid_kurzel', [])
        if kurzel_code not in valid_kurzel:
            valid_kurzel.append(kurzel_code)
            self.set_setting('valid_kurzel', valid_kurzel)
        
        # Setze Details
        details['created_date'] = datetime.now().isoformat()
        details['last_modified'] = datetime.now().isoformat()
        self.set_kurzel_details(kurzel_code, details)
        
        print(f"Neues Kürzel hinzugefügt: {kurzel_code} - {details.get('name', '')}")
        return True
    
    def update_kurzel(self, kurzel_code, details):
        """Aktualisiert ein bestehendes Kürzel"""
        existing_details = self.get_kurzel_details(kurzel_code)
        if not existing_details:
            return False
        
        # Behalte created_date bei
        details['created_date'] = existing_details.get('created_date', '')
        details['last_modified'] = datetime.now().isoformat()
        
        self.set_kurzel_details(kurzel_code, details)
        
        print(f"Kürzel aktualisiert: {kurzel_code} - {details.get('name', '')}")
        return True
    
    def delete_kurzel(self, kurzel_code):
        """Löscht ein Kürzel"""
        # Entferne aus Liste
        valid_kurzel = self.get_setting('valid_kurzel', [])
        if kurzel_code in valid_kurzel:
            valid_kurzel.remove(kurzel_code)
            self.set_setting('valid_kurzel', valid_kurzel)
        
        # Entferne Details
        kurzel_details = self.get_setting('kurzel_details', {})
        if kurzel_code in kurzel_details:
            del kurzel_details[kurzel_code]
            self.set_setting('kurzel_details', kurzel_details)
        
        # Aktualisiere Statistiken
        self.update_kurzel_statistics()
        
        print(f"Kürzel gelöscht: {kurzel_code}")
        return True
    
    def get_kurzel_by_category(self, category):
        """Holt alle Kürzel einer Kategorie"""
        kurzel_details = self.get_setting('kurzel_details', {})
        return [code for code, details in kurzel_details.items() 
                if details.get('category') == category]
    
    def get_kurzel_by_priority(self, priority):
        """Holt alle Kürzel einer Priorität"""
        kurzel_details = self.get_setting('kurzel_details', {})
        return [code for code, details in kurzel_details.items() 
                if details.get('priority') == priority]
    
    def get_kurzel_by_frequency(self, frequency):
        """Holt alle Kürzel einer Häufigkeit"""
        kurzel_details = self.get_setting('kurzel_details', {})
        return [code for code, details in kurzel_details.items() 
                if details.get('frequency') == frequency]
    
    def get_active_kurzel(self):
        """Holt alle aktiven Kürzel"""
        kurzel_details = self.get_setting('kurzel_details', {})
        return [code for code, details in kurzel_details.items() 
                if details.get('active', True)]
    
    def get_inactive_kurzel(self):
        """Holt alle inaktiven Kürzel"""
        kurzel_details = self.get_setting('kurzel_details', {})
        return [code for code, details in kurzel_details.items() 
                if not details.get('active', True)]
    
    def search_kurzel(self, search_term):
        """Sucht Kürzel nach verschiedenen Kriterien"""
        kurzel_details = self.get_setting('kurzel_details', {})
        results = []
        
        search_term_lower = search_term.lower()
        
        for code, details in kurzel_details.items():
            # Suche in Code
            if search_term_lower in code.lower():
                results.append(code)
                continue
            
            # Suche in Name
            name = details.get('name', '').lower()
            if search_term_lower in name:
                results.append(code)
                continue
            
            # Suche in Beschreibung
            description = details.get('description', '').lower()
            if search_term_lower in description:
                results.append(code)
                continue
            
            # Suche in Tags
            tags = details.get('tags', [])
            for tag in tags:
                if search_term_lower in tag.lower():
                    results.append(code)
                    break
        
        return list(set(results))  # Entferne Duplikate
    
    def update_kurzel_statistics(self):
        """Aktualisiert die Kürzel-Statistiken"""
        kurzel_details = self.get_setting('kurzel_details', {})
        
        # Basis-Statistiken
        total_count = len(kurzel_details)
        active_count = len([d for d in kurzel_details.values() if d.get('active', True)])
        inactive_count = total_count - active_count
        
        # Statistiken nach Kategorie
        by_category = {}
        for details in kurzel_details.values():
            category = details.get('category', 'Unbekannt')
            by_category[category] = by_category.get(category, 0) + 1
        
        # Statistiken nach Priorität
        by_priority = {}
        for details in kurzel_details.values():
            priority = details.get('priority', 0)
            by_priority[priority] = by_priority.get(priority, 0) + 1
        
        # Statistiken nach Häufigkeit
        by_frequency = {}
        for details in kurzel_details.values():
            frequency = details.get('frequency', 'unbekannt')
            by_frequency[frequency] = by_frequency.get(frequency, 0) + 1
        
        # Speichere Statistiken
        statistics = {
            "total_count": total_count,
            "active_count": active_count,
            "inactive_count": inactive_count,
            "by_category": by_category,
            "by_priority": by_priority,
            "by_frequency": by_frequency,
            "last_updated": datetime.now().isoformat()
        }
        
        self.set_setting('kurzel_statistics', statistics)
    
    def get_kurzel_statistics(self):
        """Holt die aktuellen Kürzel-Statistiken"""
        return self.get_setting('kurzel_statistics', {})
    
    # Neue Methoden für die erweiterte Kürzel-Tabelle
    def get_kurzel_table_data(self):
        """Holt alle Kürzel-Tabellendaten"""
        return self.kurzel_table_manager.get_all_kurzel()
    
    def get_kurzel_by_code(self, kurzel_code):
        """Holt ein spezifisches Kürzel aus der Tabelle"""
        return self.kurzel_table_manager.get_kurzel(kurzel_code)
    
    def add_kurzel_to_table(self, kurzel_data):
        """Fügt ein neues Kürzel zur Tabelle hinzu"""
        return self.kurzel_table_manager.add_kurzel(kurzel_data)
    
    def update_kurzel_in_table(self, kurzel_code, kurzel_data):
        """Aktualisiert ein Kürzel in der Tabelle"""
        return self.kurzel_table_manager.update_kurzel(kurzel_code, kurzel_data)
    
    def delete_kurzel_from_table(self, kurzel_code):
        """Löscht ein Kürzel aus der Tabelle"""
        return self.kurzel_table_manager.delete_kurzel(kurzel_code)
    
    def search_kurzel_in_table(self, search_term):
        """Sucht Kürzel in der Tabelle"""
        return self.kurzel_table_manager.search_kurzel(search_term)
    
    def get_kurzel_categories(self):
        """Holt alle verfügbaren Kategorien"""
        kurzel_data = self.get_kurzel_table_data()
        categories = set()
        for data in kurzel_data.values():
            if data.get('category'):
                categories.add(data['category'])
        return sorted(list(categories))
    
    def get_kurzel_image_types(self):
        """Holt alle verfügbaren Bildtypen"""
        kurzel_data = self.get_kurzel_table_data()
        image_types = set()
        for data in kurzel_data.values():
            if data.get('image_type'):
                image_types.add(data['image_type'])
        return sorted(list(image_types))
    
    def export_kurzel_table_to_csv(self, filename=None):
        """Exportiert die Kürzel-Tabelle als CSV"""
        return self.kurzel_table_manager.export_to_csv(filename)
    
    def import_kurzel_table_from_csv(self, filename):
        """Importiert eine Kürzel-Tabelle aus CSV"""
        return self.kurzel_table_manager.import_from_csv(filename)
    
    def export_kurzel_details(self, filename=None):
        """Exportiert alle Kürzel-Details in eine JSON-Datei"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"kurzel_details_{timestamp}.json"
        
        export_data = {
            "export_date": datetime.now().isoformat(),
            "kurzel_details": self.get_setting('kurzel_details', {}),
            "kurzel_categories": self.get_setting('kurzel_categories', {}),
            "kurzel_statistics": self.get_kurzel_statistics(),
            "valid_kurzel": self.get_setting('valid_kurzel', [])
        }
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            print(f"Kürzel-Details exportiert: {filename}")
            return True
        except Exception as e:
            print(f"Fehler beim Exportieren der Kürzel-Details {filename}: {e}")
            return False
    
    def import_kurzel_details(self, filename):
        """Importiert Kürzel-Details aus einer JSON-Datei"""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                import_data = json.load(f)
            
            # Importiere Details
            if 'kurzel_details' in import_data:
                self.set_setting('kurzel_details', import_data['kurzel_details'])
            
            # Importiere Kategorien
            if 'kurzel_categories' in import_data:
                self.set_setting('kurzel_categories', import_data['kurzel_categories'])
            
            # Importiere gültige Kürzel
            if 'valid_kurzel' in import_data:
                self.set_setting('valid_kurzel', import_data['valid_kurzel'])
            
            # Aktualisiere Statistiken
            self.update_kurzel_statistics()
            
            print(f"Kürzel-Details importiert: {filename}")
            return True
        except Exception as e:
            print(f"Fehler beim Importieren der Kürzel-Details {filename}: {e}")
            return False

# Globale Instanz des Config-Managers
config_manager = CentralConfigManager()

# Kompatibilitätsfunktionen für bestehenden Code
def load_json_config():
    """Lädt die JSON-Konfiguration (Kompatibilität)"""
    return config_manager.config

def save_json_config(config):
    """Speichert die JSON-Konfiguration (Kompatibilität)"""
    config_manager.config = config
    return config_manager.save_config()

def get_default_config():
    """Gibt die Standard-Konfiguration zurück (Kompatibilität)"""
    return config_manager._get_default_config()

def get_reader():
    global _READER
    if _READER is None:
        _READER = easyocr.Reader(['de', 'en'])
    return _READER

def write_detailed_log(level, message, details=None, exception=None):
    """Schreibt einen detaillierten Log-Eintrag"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    log_entry = f"[{timestamp}] [{level.upper()}] {message}\n"
    
    if details:
        log_entry += f"    Details: {details}\n"
    
    if exception:
        log_entry += f"    Exception: {str(exception)}\n"
        log_entry += f"    Traceback: {traceback.format_exc()}\n"
    
    log_entry += "\n"
    
    try:
        with open(DETAILED_LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    except Exception as e:
        print(f"Fehler beim Schreiben des detaillierten Logs: {e}")

def write_log_entry(filename, raw_text, final_result, confidence=None):
    """Schreibt einen Log-Eintrag für OCR-Ergebnisse"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {filename}: Raw='{raw_text}' -> Final='{final_result}'"
    if confidence:
        log_entry += f" (Confidence: {confidence:.2f})"
    log_entry += "\n"
    
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_entry)
    except Exception as e:
        print(f"Fehler beim Schreiben des Logs: {e}")

def get_exif_usercomment(image_path):
    """Liest das EXIF UserComment-Feld aus einem Bild"""
    try:
        with Image.open(image_path) as img:
            exif = img.getexif()
            if exif is None:
                write_detailed_log("info", "Keine EXIF-Daten gefunden", f"Bild: {image_path}")
                return None
            
            # Finde den UserComment-Tag
            for tag_id in exif:
                tag = ExifTags.TAGS.get(tag_id, tag_id)
                if tag == 'UserComment':
                    user_comment = exif.get(tag_id)
                    if user_comment:
                        try:
                            # Behandle sowohl String als auch Bytes mit Prefixen
                            if isinstance(user_comment, bytes):
                                # Entferne mögliche Prefixe
                                prefixes = [b'ASCII\x00\x00\x00', b'UNICODE\x00', b'JIS\x00\x00\x00', b'\x00\x00\x00\x00']
                                data = user_comment
                                for prefix in prefixes:
                                    if data.startswith(prefix):
                                        data = data[len(prefix):]
                                        break
                                data = data.decode('utf-8', errors='ignore')
                            else:
                                data = str(user_comment)
                            
                            # Versuche JSON zu parsen
                            parsed_data = json.loads(data)
                            write_detailed_log("info", "EXIF-Daten erfolgreich gelesen", f"Bild: {image_path}, Größe: {len(str(parsed_data))} Zeichen")
                            return parsed_data
                        except (json.JSONDecodeError, UnicodeDecodeError) as e:
                            write_detailed_log("warning", "EXIF-Daten konnten nicht als JSON geparst werden", f"Bild: {image_path}", e)
                            return None
            write_detailed_log("info", "Kein UserComment-Tag in EXIF-Daten gefunden", f"Bild: {image_path}")
            return None
    except Exception as e:
        write_detailed_log("error", "Fehler beim Lesen der EXIF-Daten", f"Bild: {image_path}", e)
        print(f"Fehler beim Lesen der EXIF-Daten: {e}")
        return None

def save_exif_usercomment(image_path, json_data):
    """Speichert JSON-Daten im EXIF UserComment-Feld"""
    try:
        with Image.open(image_path) as img:
            exif = img.getexif()
            if exif is None:
                exif = {}
            
            # Konvertiere JSON zu Bytes mit Standard-Prefix
            json_string = json.dumps(json_data, ensure_ascii=False)
            json_bytes = json_string.encode('utf-8')
            user_comment = b'ASCII\x00\x00\x00' + json_bytes
            
            # Finde den UserComment-Tag-ID
            usercomment_tag_id = None
            for tag_id, tag_name in ExifTags.TAGS.items():
                if tag_name == 'UserComment':
                    usercomment_tag_id = tag_id
                    break
            
            if usercomment_tag_id is None:
                # Fallback: verwende einen bekannten Tag-ID für UserComment
                usercomment_tag_id = 37510
            
            exif[usercomment_tag_id] = user_comment
            
            # Speichere das Bild mit neuen EXIF-Daten
            img.save(image_path, exif=exif)
            write_detailed_log("info", "EXIF-Daten erfolgreich gespeichert", f"Bild: {image_path}, Größe: {len(json_string)} Zeichen")
            return True
    except Exception as e:
        write_detailed_log("error", "Fehler beim Speichern der EXIF-Daten", f"Bild: {image_path}", e)
        print(f"Fehler beim Speichern der EXIF-Daten: {e}")
        return False

def normalize_header(header):
    # Umlaute ersetzen
    header = header.replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue').replace('ß', 'ss')
    header = header.replace('Ä', 'Ae').replace('Ö', 'Oe').replace('Ü', 'Ue')
    # Unicode-Normalisierung (z.B. für Akzente)
    header = unicodedata.normalize('NFKD', header)
    # Kleinbuchstaben
    header = header.lower()
    # Sonderzeichen/Leerzeichen zu Unterstrich
    header = re.sub(r'[^a-z0-9]+', '_', header)
    # Mehrfache Unterstriche zu einem
    header = re.sub(r'_+', '_', header)
    # Am Anfang/Ende Unterstriche entfernen
    header = header.strip('_')
    return header
class OCRReviewApp(tk.Tk):
    def __init__(self, loading_mode=False):
        super().__init__()
        
        # Programm-Icon setzen
        try:
            icon_path = resource_path("82EndoLogo.png")
            if os.path.exists(icon_path):
                self.iconphoto(True, ImageTk.PhotoImage(Image.open(icon_path)))
        except Exception as e:
            write_detailed_log("warning", "Konnte Programm-Icon nicht laden", str(e))
            
        self.title("GearGeneGPT")
        self.geometry(f"{MAIN_WINDOW_WIDTH}x{MAIN_WINDOW_HEIGHT}")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Fenster-Icon setzen
        icon_path = resource_path('Logo.png')
        if os.path.exists(icon_path):
            try:
                icon_img = Image.open(icon_path)
                icon_img = icon_img.convert('RGBA')
                icon_img = icon_img.resize((64, 64), Image.LANCZOS)
                self.icon_imgtk = ImageTk.PhotoImage(icon_img)
                self.iconphoto(False, self.icon_imgtk)
            except Exception as e:
                print(f"Fehler beim Laden des Icons: {e}")

        # Loading mode flag
        self.loading_mode = loading_mode

        # Lade Konfiguration
