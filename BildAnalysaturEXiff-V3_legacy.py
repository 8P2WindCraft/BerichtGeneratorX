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

# Professionelles Farbschema
COLORS = {
    'primary': '#1565C0',      # Dunkles Blau (Primäraktionen)
    'primary_hover': '#0D47A1', # Noch dunkler für Hover
    'secondary': '#424242',     # Dunkelgrau (Sekundäraktionen)
    'secondary_hover': '#212121',
    'success': '#2E7D32',       # Grün (Erfolg/OK)
    'success_hover': '#1B5E20',
    'warning': '#F57C00',       # Orange (Warnung)
    'warning_hover': '#E65100',
    'danger': '#C62828',        # Rot (Gefahr/Skip)
    'danger_hover': '#B71C1C',
    'info': '#0277BD',          # Info-Blau
    'info_light': '#E3F2FD',    # Helles Info-Blau für Flächen
    'bg_light': '#FAFAFA',      # Heller Hintergrund
    'bg_medium': '#F5F5F5',     # Mittlerer Hintergrund
    'border': '#E0E0E0',        # Rahmenfarbe
    'text_primary': '#212121',  # Haupttext
    'text_secondary': '#757575' # Sekundärtext
}

# Standardisierte Schriftgrößen
FONT_SIZES = {
    'title': 14,
    'heading': 12,
    'body': 10,
    'small': 9,
    'tiny': 8
}

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
        self.config_manager = config_manager
        self.json_config = self.config_manager.config
        
        # Lade gespeicherte Sprache oder verwende Standard (Englisch)
        saved_language = self.config_manager.get_setting('localization.current_language', 'en')
        if 'localization' not in self.json_config:
            self.json_config['localization'] = {}
        self.json_config['localization']['current_language'] = saved_language
        write_detailed_log("info", "Sprache geladen", f"Sprache: {saved_language}")
        
        # Fenster-Einstellungen aus Konfiguration
        window_width = self.config_manager.get_setting('display.window_width', 1080)
        window_height = self.config_manager.get_setting('display.window_height', 800)
        window_x = self.config_manager.get_setting('display.window_x')
        window_y = self.config_manager.get_setting('display.window_y')
        
        if window_x is not None and window_y is not None:
            self.geometry(f"{window_width}x{window_height}+{window_x}+{window_y}")
        else:
            self.geometry(f"{window_width}x{window_height}")
        
        # Lade gültige Kürzel
        self.valid_kurzel = self.config_manager.get_setting('valid_kurzel', [])

        # Event-Handler für Fenstergrößenänderungen
        self.bind('<Configure>', self.on_window_resize)

        # State
        self.source_dir = None
        self.files = []
        self.index = 0
        self.counter = Counter()
        self.photo = None
        self.project_data_from_excel = None
        self.excel_df = None
        self.excel_row_index = None
        self.grunddaten_vars = {json_key: tk.StringVar() for json_key in excel_to_json.values()}
        
        # Flag um rekursive Aufrufe zu verhindern
        self._loading_image = False
        
        # Flag für Analyse-Modus
        self._analyzing = False
        
        # Caching für Bewertungsdaten
        self._evaluation_cache = {}  # {filename: bool} - ob Bild bewertet ist
        self._tag_evaluation_cache = {}  # {tag: bool} - ob Tag vollständig bewertet ist
        self._cache_dirty = True  # Flag für Cache-Invalidierung
        
        # Verzögertes Speichern für Damage-Text
        
        # Zoom und Zeichnen Variablen
        self.zoom_factor = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.is_panning = False
        self.last_pan_x = 0
        self.last_pan_y = 0

        # Zeichnen
        self.draw_mode = None  # None, 'arrow', 'circle', 'rectangle'
        self.draw_color = 'red'
        self.line_width = 3
        self.is_drawing = False
        self.drawing_points = []
        self.temp_drawing_overlay = None

        # Undo/Redo für Zeichnungen
        self.drawing_undo_stack = []
        self.drawing_redo_stack = []
        self._damage_save_timer = None
        self._damage_text_changed = False
        
        # Einstellungsfenster-Instanz
        self._settings_window = None
        
        # Mausrad-Navigation Variable
        self.mousewheel_nav_enabled = tk.BooleanVar(value=False)
        
        # Tab-Navigation Variablen
        self.tab_navigation_widgets = []  # Liste aller navigierbaren Widgets
        self.current_tab_index = 0  # Aktueller Index in der Tab-Navigation
        
        # Tooltip-System
        self.tooltip_window = None
        self.tooltip_text = ""
        
        # Galerie-Ansicht Variablen
        self.view_mode = 'single'  # 'single' oder 'gallery'
        self.gallery_frame = None
        self.gallery_current_tag = None

        write_detailed_log("info", "Anwendung gestartet", f"Fenster-Größe: 1080x800, Gültige Codes: {len(self.valid_kurzel)}")
        
        # Lade letzte Auswahlen
        self.load_last_selections()
        
        self.create_widgets()
        
        # Debug-Menü hinzufügen
        self.add_debug_menu()

        # Nur laden wenn nicht im Loading-Modus
        if not self.loading_mode:
            print("Starte Laden des letzten Ordners...")
            # Ordnerpfad beim Start laden
            if os.path.isfile(LAST_FOLDER_FILE):
                try:
                    print("LAST_FOLDER_FILE gefunden, versuche zu laden...")
                    with open(LAST_FOLDER_FILE, 'r', encoding='utf-8') as f:
                        pfad = f.read().strip()
                        print(f"Gelesener Pfad: {pfad}")
                        if pfad and os.path.isdir(pfad):
                            print(f"Pfad ist gültig, lade Bilder...")
                            self.source_dir = pfad
                            self.label_folder.config(text=pfad)
                            files = [f for f in os.listdir(pfad)
                                     if f.lower().endswith((".png", ".jpg", ".jpeg", ".tif", ".bmp"))]
                            print(f"Gefundene Bilder: {len(files)}")
                            if files:
                                self.files = sorted(files)
                                self.index = 0
                                self.status_var.set(f"Ordner automatisch geladen: {len(files)} Bilder")
                                print("Aktualisiere Zähler...")
                                self.update_counters_from_exif()
                                print("Cache invalidieren...")
                                self.invalidate_evaluation_cache()
                                print("Aktualisiere Bewertungsfortschritt...")
                                self.update_evaluation_progress()
                                print("Zeige erstes Bild...")
                                # Verzögertes Laden des ersten Bildes, damit mainloop nicht blockiert wird
                                self.after(100, self.safe_show_image)
                                print("Erstes Bild angezeigt")
                            else:
                                print("Keine Bilder im Ordner gefunden")
                                self.status_var.set("Ordner geladen, aber keine Bilder gefunden")
                        else:
                            print(f"Pfad ist ungültig oder leer: {pfad}")
                            self.status_var.set("Letzter Ordner nicht mehr verfügbar")
                except Exception as e:
                    print(f"Fehler beim Laden des letzten Ordners: {e}")
                    write_detailed_log("warning", "Fehler beim Laden des letzten Ordners", str(e))
                    self.status_var.set("Fehler beim Laden des letzten Ordners")
            else:
                print("LAST_FOLDER_FILE nicht gefunden")
                self.status_var.set("Bereit - Ordner auswählen")

        print("Fertig mit __init__")

    def finish_initialization(self):
        """Beendet die Initialisierung nach dem Ladebildschirm"""
        self.loading_mode = False
        print("Starte Laden des letzten Ordners...")
        # Ordnerpfad beim Start laden
        if os.path.isfile(LAST_FOLDER_FILE):
            try:
                print("LAST_FOLDER_FILE gefunden, versuche zu laden...")
                with open(LAST_FOLDER_FILE, 'r', encoding='utf-8') as f:
                    pfad = f.read().strip()
                    print(f"Gelesener Pfad: {pfad}")
                    if pfad and os.path.isdir(pfad):
                        print(f"Pfad ist gültig, lade Bilder...")
                        self.source_dir = pfad
                        self.label_folder.config(text=pfad)
                        files = [f for f in os.listdir(pfad)
                                 if f.lower().endswith((".png", ".jpg", ".jpeg", ".tif", ".bmp"))]
                        print(f"Gefundene Bilder: {len(files)}")
                        if files:
                            self.files = sorted(files)
                            self.index = 0
                            self.status_var.set(f"Ordner automatisch geladen: {len(files)} Bilder")
                            print("Aktualisiere Zähler...")
                            self.update_counters_from_exif()
                            print("Cache invalidieren...")
                            self.invalidate_evaluation_cache()
                            print("Aktualisiere Bewertungsfortschritt...")
                            self.update_evaluation_progress()
                            print("Zeige erstes Bild...")
                            # Längere Verzögerung für Bildanzeige, damit das Fenster vollständig bereit ist
                            self.after(500, self.safe_show_image)
                            print("Erstes Bild angezeigt")
                        else:
                            print("Keine Bilder im Ordner gefunden")
                            self.status_var.set("Ordner geladen, aber keine Bilder gefunden")
                    else:
                        print(f"Pfad ist ungültig oder leer: {pfad}")
                        self.status_var.set("Letzter Ordner nicht mehr verfügbar")
            except Exception as e:
                print(f"Fehler beim Laden des letzten Ordners: {e}")
                write_detailed_log("warning", "Fehler beim Laden des letzten Ordners", str(e))
                self.status_var.set("Fehler beim Laden des letzten Ordners")
        else:
            print("LAST_FOLDER_FILE nicht gefunden")
            self.status_var.set("Bereit - Ordner auswählen")

    def load_codes(self):
        # Versuche zuerst Synchronisation
        synced_codes = sync_valid_codes()
        if synced_codes:
            write_detailed_log("info", "Codes nach Synchronisation geladen", f"Anzahl: {len(synced_codes)}")
            return synced_codes
        
        # Fallback auf Standard-Logik
        if os.path.isfile(CODE_FILE):
            try:
                with open(CODE_FILE, 'r', encoding='utf-8') as f:
                    codes = [line.strip() for line in f if line.strip()]
                    write_detailed_log("info", "Codes aus Datei geladen", f"Datei: {CODE_FILE}, Anzahl: {len(codes)}")
                    return codes
            except Exception as e:
                write_detailed_log("warning", "Fehler beim Laden der Codes, verwende Standardwerte", f"Datei: {CODE_FILE}", e)
                messagebox.showwarning("Warnung", "Fehler beim Laden der Codes, verwende Standardwerte.")
        
        # Erstelle Standard-Code-Datei
        with open(CODE_FILE, 'w', encoding='utf-8') as f:
            for code in DEFAULT_KURZEL:
                f.write(code + "\n")
        write_detailed_log("info", "Standard-Code-Datei erstellt", f"Datei: {CODE_FILE}, Anzahl: {len(DEFAULT_KURZEL)}")
        return list(DEFAULT_KURZEL)

    def save_codes(self, codes):
        try:
            with open(CODE_FILE, 'w', encoding='utf-8') as f:
                for code in codes:
                    f.write(code + "\n")
            self.valid_kurzel = codes
            self.correct_combo['values'] = self.valid_kurzel
            
            # Aktualisiere zentrale Konfiguration
            self.config_manager.update_valid_kurzel(codes)
            
            # Aktualisiere OCR-Klasse falls vorhanden
            if hasattr(self, 'improved_ocr'):
                self.improved_ocr.update_valid_kurzel(codes)
                write_detailed_log("info", "OCR-Klasse mit neuen Codes aktualisiert")
            
            write_detailed_log("info", "Code-Liste aktualisiert", f"Datei: {CODE_FILE}, Anzahl: {len(codes)}")
            messagebox.showinfo("Gespeichert", "Code-Liste aktualisiert und OCR optimiert.")
        except Exception as e:
            write_detailed_log("error", "Fehler beim Speichern der Codes", f"Datei: {CODE_FILE}", e)
            messagebox.showerror("Fehler", f"Fehler beim Speichern der Codes: {e}")

    def load_last_selections(self):
        """Lädt die letzten Button-Auswahlen aus der Konfiguration"""
        try:
            last_selections = self.json_config.get('last_selections', {})
            
            # Lade letzten Ordner für "Ordner öffnen"
            last_open_folder = last_selections.get('open_folder', '')
            if last_open_folder and os.path.exists(last_open_folder):
                write_detailed_log("info", "Letzte Auswahl geladen", f"Ordner öffnen: {last_open_folder}")
            
            # Lade letzte Excel-Datei
            last_excel_file = last_selections.get('excel_file', '')
            if last_excel_file and os.path.exists(last_excel_file):
                write_detailed_log("info", "Letzte Auswahl geladen", f"Excel-Datei: {last_excel_file}")
            
            # Lade letzten Analyse-Ordner
            last_analyze_folder = last_selections.get('analyze_folder', '')
            if last_analyze_folder and os.path.exists(last_analyze_folder):
                write_detailed_log("info", "Letzte Auswahl geladen", f"Analyse-Ordner: {last_analyze_folder}")
                
        except Exception as e:
            write_detailed_log("warning", "Fehler beim Laden der letzten Auswahlen", str(e))

    def create_menu_bar(self):
        """Erstellt die Menüleiste - nur mit Funktionen, die NICHT als Buttons in der Toolbar vorhanden sind"""
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        
        # Datei-Menü
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Datei", menu=file_menu)
        file_menu.add_command(label="📊 Excel laden", command=self.show_excel_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Beenden", command=self.quit, accelerator="Ctrl+Q")
        
        # Bearbeiten-Menü
        edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Bearbeiten", menu=edit_menu)
        edit_menu.add_command(label="EXIF anzeigen", command=self.show_exif_info)
        
        # Analyse-Menü
        analysis_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Analyse", menu=analysis_menu)
        analysis_menu.add_command(label="🔍 Analysieren", command=self.auto_analyze)
        analysis_menu.add_command(label="🔄 Aktualisieren", command=self.refresh_images)
        analysis_menu.add_separator()
        analysis_menu.add_command(label="OCR-Methoden testen", command=self.test_ocr_methods)
        
        # Ansicht-Menü
        self.view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Ansicht", menu=self.view_menu)
        
        # Galerie-Ansicht
        self.view_menu.add_command(label="📷 Galerie-Ansicht", command=self.toggle_view_mode, accelerator="Ctrl+G")
        self.view_menu.add_separator()
        
        # Zoom-Funktionen
        self.view_menu.add_command(label="Zoom vergrößern", command=self.zoom_in, accelerator="Ctrl++")
        self.view_menu.add_command(label="Zoom verkleinern", command=self.zoom_out, accelerator="Ctrl+-")
        self.view_menu.add_command(label="Zoom zurücksetzen", command=self.zoom_reset, accelerator="Ctrl+0")
        self.view_menu.add_separator()
        self.view_menu.add_command(label="Vollbild", command=self.toggle_fullscreen, accelerator="F11")
        
        # Extras-Menü
        tools_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Extras", menu=tools_menu)
        tools_menu.add_command(label="📝 Log", command=self.show_detailed_log)
        tools_menu.add_command(label="📋 OCR Log", command=self.show_ocr_log)
        tools_menu.add_command(label="⚙️ Einstellungen", command=self.open_config_editor)
        tools_menu.add_command(label="⚙️ Zeichen-Einstellungen", 
                              command=self.open_drawing_settings)
        tools_menu.add_command(label="💾 Zeichnungen speichern", 
                              command=self.save_drawing_to_file,
                              accelerator="Ctrl+S")
        tools_menu.add_separator()
        tools_menu.add_command(label="Bewertungen zurücksetzen…", command=self.reset_all_image_evaluations)
        tools_menu.add_separator()
        tools_menu.add_command(label="Kürzel-Tabelle verwalten", command=self.open_kurzel_manager)
        tools_menu.add_command(label="Alternative Kürzel verwalten", command=self.open_alternative_kurzel_manager)
        
        # Hilfe-Menü
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Hilfe", menu=help_menu)
        help_menu.add_command(label="Über", command=self.show_about)
        help_menu.add_command(label="Tastenkürzel", command=self.show_shortcuts)
        
        # Tastenkürzel binden
        self.bind('<Control-o>', lambda e: self.open_folder())
        self.bind('<Control-q>', lambda e: self.quit())
        self.bind('<F5>', lambda e: self.refresh_images())
        self.bind('<Control-a>', lambda e: self.auto_analyze())
        self.bind('<Control-plus>', lambda e: self.zoom_in())
        self.bind('<Control-minus>', lambda e: self.zoom_out())
        self.bind('<Control-0>', lambda e: self.zoom_reset())
        self.bind('<F11>', lambda e: self.toggle_fullscreen())
        self.bind('<Control-comma>', lambda e: self.open_config_editor())
        self.bind('<Control-s>', lambda e: self.save_drawing_to_file())
        self.bind('<Control-z>', lambda e: self.drawing_undo())
        self.bind('<Control-y>', lambda e: self.drawing_redo())

    def test_ocr_methods(self):
        """Testet alle OCR-Methoden auf dem aktuellen Bild"""
        if not self.files or not self.source_dir:
            messagebox.showwarning("Warnung", "Bitte wählen Sie zuerst einen Ordner mit Bildern aus!")
            return
        
        # Öffne das Analyse-Fenster
        self.auto_analyze()

    def zoom_in(self):
        """Vergrößert die Ansicht"""
        if hasattr(self, 'zoom_factor'):
            self.zoom_factor *= 1.2
            self.update_image_display()
        else:
            messagebox.showinfo("Info", "Zoom-Funktion nicht verfügbar")

    def zoom_out(self):
        """Verkleinert die Ansicht"""
        if hasattr(self, 'zoom_factor'):
            self.zoom_factor /= 1.2
            self.update_image_display()
        else:
            messagebox.showinfo("Info", "Zoom-Funktion nicht verfügbar")

    def zoom_reset(self):
        """Setzt den Zoom zurück"""
        if hasattr(self, 'zoom_factor'):
            self.zoom_factor = 1.0
            self.update_image_display()
        else:
            messagebox.showinfo("Info", "Zoom-Funktion nicht verfügbar")

    def toggle_fullscreen(self):
        """Schaltet zwischen Vollbild und Fenstermodus um"""
        current_state = self.attributes('-fullscreen')
        self.attributes('-fullscreen', not current_state)

    def open_kurzel_manager(self):
        """Öffnet den Kürzel-Manager"""
        self.open_config_editor()
        # Hier könnte man direkt zum Kürzel-Tab wechseln

    def open_alternative_kurzel_manager(self):
        """Öffnet den Alternative Kürzel-Manager"""
        self.open_config_editor()
        # Hier könnte man direkt zum Alternative Kürzel-Tab wechseln

    def show_about(self):
        """Zeigt das Über-Dialog"""
        about_text = """BerichtGeneratorX - Bilderkennungs- und Analyse-Tool

Version: 3.0
Entwickelt für die automatische OCR-Erkennung von Kürzeln
in technischen Dokumentationen und Bildern.

Features:
• Automatische OCR-Erkennung mit mehreren Methoden
• Alternative Kürzel-Korrektur
• Excel-Integration
• EXIF-Datenverwaltung
• Erweiterte Bildanalyse

© 2024 - Alle Rechte vorbehalten"""
        
        messagebox.showinfo("Über BerichtGeneratorX", about_text)

    def show_shortcuts(self):
        """Zeigt die Tastenkürzel"""
        shortcuts_text = """Tastenkürzel:

Datei:
Ctrl+O    - Ordner öffnen
Ctrl+Q    - Beenden

Bearbeiten:
F5        - Aktualisieren

Analyse:
Ctrl+A    - OCR-Analyse starten

Ansicht:
Ctrl++    - Zoom vergrößern
Ctrl+-    - Zoom verkleinern
Ctrl+0    - Zoom zurücksetzen
F11       - Vollbild umschalten

Extras:
Ctrl+,    - Einstellungen öffnen"""
        
        messagebox.showinfo("Tastenkürzel", shortcuts_text)

    def on_canvas_resize(self, event):
        """Behandelt Canvas-Größenänderungen"""
        try:
            if hasattr(self, 'photo') and self.photo:
                # Zentriere das Bild neu wenn Canvas-Größe sich ändert
                self.center_image()
        except Exception as e:
            # Ignoriere Fehler beim Resize
            pass

    def create_widgets(self):
        """Erstellt die Benutzeroberfläche"""
        print("Starte create_widgets")
        
        # Status Variable initialisieren
        self.status_var = tk.StringVar(value="Bereit")
        
        # TTK Style konfigurieren
        style = ttk.Style()
        style.theme_use('clam')
        
        # Treeview Styling
        style.configure("Treeview",
                       background=COLORS['bg_light'],
                       foreground=COLORS['text_primary'],
                       rowheight=28,
                       fieldbackground=COLORS['bg_light'],
                       font=("Segoe UI", FONT_SIZES['body']))
        
        style.configure("Treeview.Heading",
                       background=COLORS['secondary'],
                       foreground="white",
                       font=("Segoe UI", FONT_SIZES['heading'], "bold"),
                       relief="flat")
        
        style.map("Treeview.Heading",
                 background=[('active', COLORS['secondary_hover'])])
        
        # LabelFrame Styling
        style.configure("TLabelframe",
                       background=COLORS['bg_medium'],
                       borderwidth=1,
                       relief="solid")
        
        style.configure("TLabelframe.Label",
                       font=("Segoe UI", FONT_SIZES['heading'], "bold"),
                       foreground=COLORS['text_primary'])
        
        # Progressbar Styling
        style.configure("TProgressbar",
                       background=COLORS['success'],
                       troughcolor=COLORS['bg_medium'],
                       borderwidth=0,
                       thickness=20)
        
        # 1. Menüleiste erstellen
        self.create_menu_bar()

        # 1a. Tabs (Notebook) für Einzelbild/Galerie ganz oben
        self.tab_container = ttk.Frame(self)
        self.tab_container.pack(fill=tk.X, pady=(0, 5))
        self.notebook = ttk.Notebook(self.tab_container)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        self.single_view_tab = ttk.Frame(self.notebook)
        self.gallery_view_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.single_view_tab, text="📷 Einzelbild")
        self.notebook.add(self.gallery_view_tab, text="🖼️ Galerie")
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_changed)
        
        # 2. Toolbar mit wichtigsten Funktionen
        toolbar_frame = ttk.Frame(self.single_view_tab)
        toolbar_frame.pack(fill=tk.X, pady=(0, 5))
        
        # Linke Seite der Toolbar
        left_toolbar = ttk.Frame(toolbar_frame)
        left_toolbar.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Nur Ordner Button in der Toolbar
        folder_btn = tk.Button(left_toolbar, text="📁 Ordner öffnen", command=self.open_folder,
                              bg=COLORS['primary'], fg="white", 
                              font=("Segoe UI", FONT_SIZES['body'], "bold"),
                              relief="flat", bd=0, padx=15, pady=8, 
                              activebackground=COLORS['primary_hover'],
                              cursor="hand2")
        folder_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # Fortschrittsbalken (wird nur bei Analyse eingeblendet)
        self.pbar = ttk.Progressbar(left_toolbar, length=150, mode='determinate')
        # self.pbar.pack(side=tk.LEFT, padx=(0, 5))  # Wird nur bei Analyse eingeblendet
        
        # Rechte Seite der Toolbar
        right_toolbar = ttk.Frame(toolbar_frame)
        right_toolbar.pack(side=tk.RIGHT, fill=tk.X)
        
        # Rechte Toolbar ist jetzt leer - alle Buttons ins Menü verschoben
        
        # Ordner Label direkt rechts neben dem Button, visuell gruppiert (keine Lücke)
        self.label_folder_container = tk.Frame(toolbar_frame, bg=COLORS['info_light'], bd=0, highlightthickness=1, highlightbackground=COLORS['border'])
        self.label_folder_container.pack(side=tk.LEFT, padx=(0, 0), pady=(0, 0))
        self.label_folder = tk.Label(self.label_folder_container, text="Kein Ordner ausgewählt",
                                     bg=COLORS['info_light'], fg=COLORS['text_primary'],
                                     font=("Segoe UI", FONT_SIZES['body']),
                                     anchor='w')
        self.label_folder.pack(side=tk.LEFT, padx=3, pady=6)
        
        # 3. Main Content Area (4 Spalten: Werkzeuge | Bild | Bewertung | Fortschritt)
        self.content_frame = ttk.Frame(self.single_view_tab)
        self.content_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Konfiguriere die Spaltengewichte (4 Spalten)
        # Spalte 0: Werkzeuge (fix), Spalte 1: Bild (groß), Spalte 2: Bewertung (klein), Spalte 3: Fortschritt (mittel)
        self.content_frame.grid_columnconfigure(0, weight=0, minsize=60)  # Werkzeuge fix
        self.content_frame.grid_columnconfigure(1, weight=15)  # Bild (ca. 65%)
        self.content_frame.grid_columnconfigure(2, weight=3)   # Bewertung (ca. 13%)
        self.content_frame.grid_columnconfigure(3, weight=5)   # Fortschritt (ca. 22%)
        
        # Konfiguriere die Zeilengewichte für vertikales Resizing
        self.content_frame.grid_rowconfigure(0, weight=1)  # Hauptinhalt expandiert vertikal
        
        # Zeichenwerkzeug-Toolbar (vertikal, ganz links - DIREKT in content_frame)
        tools_frame = tk.Frame(self.content_frame, bg=COLORS['bg_medium'], 
                              relief='flat', bd=0, width=60)
        tools_frame.grid(row=0, column=0, sticky='nsew', padx=(0, 5))
        tools_frame.grid_propagate(False)  # Fixe Breite beibehalten
        
        # Werkzeug-Buttons (vertikal)
        tool_buttons_frame = tk.Frame(tools_frame, bg=COLORS['bg_medium'])
        tool_buttons_frame.pack(pady=10)
        
        # Kein Werkzeug (Standard)
        self.tool_none_btn = tk.Button(tool_buttons_frame, text="👆",
                                     command=lambda: self.set_draw_mode(None),
                                     bg=COLORS['bg_light'], fg=COLORS['text_primary'],
                                     font=("Segoe UI", 18),
                                     width=2, height=1,
                                     relief='solid', bd=1,
                                     cursor='hand2')
        self.tool_none_btn.pack(pady=5)
        self.create_tooltip(self.tool_none_btn, "Navigation (Pan)")
        
        # Pfeil
        self.tool_arrow_btn = tk.Button(tool_buttons_frame, text="↗",
                                      command=lambda: self.set_draw_mode('arrow'),
                                      bg='white', fg=COLORS['text_primary'],
                                      font=("Segoe UI", 18),
                                      width=2, height=1,
                                      relief='flat', bd=1,
                                      cursor='hand2')
        self.tool_arrow_btn.pack(pady=5)
        self.create_tooltip(self.tool_arrow_btn, "Pfeil zeichnen")
        
        # Kreis
        self.tool_circle_btn = tk.Button(tool_buttons_frame, text="○",
                                       command=lambda: self.set_draw_mode('circle'),
                                       bg='white', fg=COLORS['text_primary'],
                                       font=("Segoe UI", 18),
                                       width=2, height=1,
                                       relief='flat', bd=1,
                                       cursor='hand2')
        self.tool_circle_btn.pack(pady=5)
        self.create_tooltip(self.tool_circle_btn, "Kreis zeichnen")
        
        # Rechteck
        self.tool_rect_btn = tk.Button(tool_buttons_frame, text="▭",
                                     command=lambda: self.set_draw_mode('rectangle'),
                                     bg='white', fg=COLORS['text_primary'],
                                     font=("Segoe UI", 18),
                                     width=2, height=1,
                                     relief='flat', bd=1,
                                     cursor='hand2')
        self.tool_rect_btn.pack(pady=5)
        self.create_tooltip(self.tool_rect_btn, "Rechteck zeichnen")
        
        # Separator
        ttk.Separator(tool_buttons_frame, orient='horizontal').pack(fill=tk.X, pady=10)
        
        # Undo/Redo
        self.tool_undo_btn = tk.Button(tool_buttons_frame, text="↶",
                                     command=self.drawing_undo,
                                     bg='white', fg=COLORS['secondary'],
                                     font=("Segoe UI", 18),
                                     width=2, height=1,
                                     relief='flat', bd=1,
                                     cursor='hand2')
        self.tool_undo_btn.pack(pady=5)
        self.create_tooltip(self.tool_undo_btn, "Rückgängig")
        
        self.tool_redo_btn = tk.Button(tool_buttons_frame, text="↷",
                                     command=self.drawing_redo,
                                     bg='white', fg=COLORS['secondary'],
                                     font=("Segoe UI", 18),
                                     width=2, height=1,
                                     relief='flat', bd=1,
                                     cursor='hand2')
        self.tool_redo_btn.pack(pady=5)
        self.create_tooltip(self.tool_redo_btn, "Wiederholen")
        
        # Linke Spalte (NUR Bild) - jetzt in Spalte 1 von content_frame
        self.left_column = ttk.Frame(self.content_frame)
        self.left_column.grid(row=0, column=1, sticky="nsew", padx=(0, 5))
        
        # Konfiguriere Spalten- und Zeilengewichte
        self.left_column.grid_columnconfigure(0, weight=1)
        self.left_column.grid_rowconfigure(1, weight=1)  # Bild-Bereich expandiert vertikal
        
        # Bildinformationen über dem Bild
        image_info_frame = ttk.Frame(self.left_column)
        image_info_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        
        # OCR-Tag Label (immer sichtbar) - entfernt, wird jetzt über dem Bild angezeigt
        
        # Bild-Zähler (Bild X von Y) - anfangs ausgeblendet
        self.image_counter_var = tk.StringVar(value="Bild 0 von 0")
        self.image_counter_label = ttk.Label(image_info_frame, textvariable=self.image_counter_var, font=("TkDefaultFont", 12, "bold"))
        # self.image_counter_label.pack(side=tk.LEFT)  # Wird nur bei Analyse eingeblendet
        
        # Dateiname - anfangs ausgeblendet
        self.filename_var = tk.StringVar(value="Keine Datei geladen")
        self.filename_label = ttk.Label(image_info_frame, textvariable=self.filename_var, font=("TkDefaultFont", 10))
        # self.filename_label.pack(side=tk.RIGHT)  # Wird nur bei Analyse eingeblendet
        
        # Canvas für Bild (füllt jetzt die gesamte left_column aus)
        self.canvas = tk.Canvas(self.left_column, bg=COLORS['bg_light'], 
                               relief=tk.FLAT, bd=1, highlightthickness=1,
                               highlightbackground=COLORS['border'])
        self.canvas.grid(row=1, column=0, sticky="nsew", pady=(0, 5))
        
        # Initiale Nachricht im Canvas anzeigen
        self.canvas.create_text(400, 250, 
                               text="Bitte wählen Sie einen Ordner mit Bildern aus",
                               fill=COLORS['text_secondary'], 
                               font=("Segoe UI", FONT_SIZES['heading']))
        
        # Status-Text im Canvas
        self.canvas_status_text = self.canvas.create_text(400, 300, text="Bereit", 
                                                         fill="blue", font=("Arial", 10))
        
        # Canvas-Größe nicht mehr fix setzen - passt sich automatisch an Grid an
        # self.canvas.configure(width=800, height=500)  # Entfernt für besseres Responsive Design
        
        # Event-Binding für Canvas-Resize
        self.canvas.bind('<Configure>', self.on_canvas_resize)
        
        # Mausrad-Zoom
        self.canvas.bind("<MouseWheel>", self.on_canvas_mouse_wheel)
        
        # Strg + Mausrad für Zoom
        self.canvas.bind("<Control-MouseWheel>", self.on_canvas_mouse_wheel)
        
        # Pan und Zeichnen
        self.canvas.bind("<ButtonPress-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        
        # Strg + Zoom Shortcuts
        self.bind("<Control-plus>", lambda e: self.zoom_in_canvas())
        self.bind("<Control-minus>", lambda e: self.zoom_out_canvas())
        self.bind("<Control-0>", lambda e: self.zoom_reset_canvas())
        
        # Zoom-Controls (rechts oben im Canvas)
        # Zoom-Controls entfernt (oben rechts im Bild)
        
        # Zoom-Anzeige Label (im Bild, links unten)
        self.zoom_display = tk.Label(self.canvas, text="100%",
                                    font=("Segoe UI", 10, "bold"),
                                    bg='white', fg=COLORS['text_primary'],
                                    relief='solid', bd=1,
                                    padx=8, pady=4)
        self.zoom_display.place(x=10, rely=1.0, y=-10, anchor='sw')
        
        # OCR-Tag Label über dem Bild (weißes Kästchen, schwarze Schrift)
        self.ocr_tag_var = tk.StringVar(value="-")
        self.ocr_tag_label = tk.Label(self.canvas, textvariable=self.ocr_tag_var, 
                                     font=("Segoe UI", FONT_SIZES['title'], "bold"),
                                     bg="white", fg=COLORS['text_primary'],
                                     relief="solid", bd=1,
                                     padx=12, pady=6)
        # Positioniere das Label in der oberen linken Ecke des Canvas
        self.ocr_tag_label.place(x=10, y=10)

        # Navigation Controls direkt unter dem Bild
        self.nav_frame = ttk.Frame(self.left_column)
        self.nav_frame.grid(row=2, column=0, sticky="ew", pady=(0, 5))
        
        # Navigation mittig anordnen
        nav_center_frame = ttk.Frame(self.nav_frame)
        nav_center_frame.pack(expand=True)
        
        # Vorher Button (größer, blaue Farbe) - Navigation
        prev_button = tk.Button(nav_center_frame, text="◀ Vorher", command=self.prev_image, 
                               bg=COLORS['secondary'], fg="white", 
                               font=("Segoe UI", FONT_SIZES['body'], "bold"),
                               relief="flat", bd=0, padx=20, pady=10,
                               activebackground=COLORS['secondary_hover'],
                               cursor="hand2")
        prev_button.pack(side=tk.LEFT, padx=(0, 10))
        
        # Zoom Button entfernt - Funktionalität jetzt integriert
        
        # Korrekt Dropdown mit verbessertem Styling
        ttk.Label(nav_center_frame, text="Korrekt:", font=("TkDefaultFont", 11, "bold")).pack(side=tk.LEFT, padx=(0, 2))
        self.correct_var = tk.StringVar()
        self.correct_combo = ttk.Combobox(nav_center_frame, values=self.valid_kurzel, textvariable=self.correct_var, 
                                         width=12, font=("TkDefaultFont", 11))
        self.correct_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.correct_combo.bind("<<ComboboxSelected>>", self.on_correct_changed)
        
        # Nächste Button (größer, lila Farbe) - Navigation
        next_button = tk.Button(nav_center_frame, text="Nächste ▶", command=self.next_image, 
                               bg=COLORS['secondary'], fg="white", 
                               font=("Segoe UI", FONT_SIZES['body'], "bold"),
                               relief="flat", bd=0, padx=20, pady=10,
                               activebackground=COLORS['secondary_hover'],
                               cursor="hand2")
        next_button.pack(side=tk.LEFT, padx=(0, 10))
        
        # Grüner OK-Knopf (Inordnung) - Positive Aktion
        ok_button = tk.Button(nav_center_frame, text="✓ In Ordnung", 
                             command=self.mark_as_ok_and_next,
                             bg=COLORS['success'], fg="white", 
                             font=("Segoe UI", FONT_SIZES['body'], "bold"),
                             relief="flat", bd=0, padx=20, pady=10,
                             activebackground=COLORS['success_hover'],
                             cursor="hand2")
        ok_button.pack(side=tk.LEFT)
        
        # Roter Skip-Button (Negative Aktion)
        skip_button = tk.Button(nav_center_frame, text="🚫 Skip", 
                               command=self.mark_as_skip_and_next,
                               bg=COLORS['danger'], fg="white", 
                               font=("Segoe UI", FONT_SIZES['body'], "bold"),
                               relief="flat", bd=0, padx=15, pady=10,
                               activebackground=COLORS['danger_hover'],
                               cursor="hand2")
        skip_button.pack(side=tk.LEFT, padx=(5, 0))
        
        # Mausrad-Navigation Checkbox
        mousewheel_check = ttk.Checkbutton(nav_center_frame, text="🖱️ Mausrad", 
                                          variable=self.mousewheel_nav_enabled,
                                          command=self.toggle_mousewheel_navigation)
        mousewheel_check.pack(side=tk.LEFT, padx=(10, 0))
        
        # Tastatur-Navigation binden
        self.bind('<Left>', lambda e: self.prev_image())
        self.bind('<Right>', lambda e: self.next_image())
        self.bind('<s>', lambda e: self.mark_as_skip_and_next())  # 's' für skip
        
        # Tab-Navigation für Eingabefelder
        self.bind('<Tab>', self.on_tab_navigation)
        self.bind('<Return>', self.on_enter_press)
        
        # Nummerntasten für Schadenskategorien und Bildart-Kategorien
        self.bind('<Key-1>', lambda e: self.toggle_category_by_number(1))
        self.bind('<Key-2>', lambda e: self.toggle_category_by_number(2))
        self.bind('<Key-3>', lambda e: self.toggle_category_by_number(3))
        self.bind('<Key-4>', lambda e: self.toggle_category_by_number(4))
        self.bind('<Key-5>', lambda e: self.toggle_category_by_number(5))
        self.bind('<Key-6>', lambda e: self.toggle_category_by_number(6))
        self.bind('<Key-7>', lambda e: self.toggle_category_by_number(7))
        self.bind('<Key-8>', lambda e: self.toggle_category_by_number(8))
        self.bind('<Key-9>', lambda e: self.toggle_category_by_number(9))
        
        # Galerie-Ansicht Tastenkürzel
        self.bind('<Control-g>', lambda e: self.toggle_view_mode())
        self.bind('<Control-G>', lambda e: self.toggle_view_mode())

        # Damage Description direkt unter der Navigation
        self.desc_frame = ttk.LabelFrame(self.left_column, text="Damage Description", padding=5)
        self.desc_frame.grid(row=3, column=0, sticky="ew", pady=(0, 5))
        self.damage_description_text = tk.Text(self.desc_frame, height=4, font=("TkDefaultFont", 12), wrap=tk.WORD)
        self.damage_description_text.pack(fill=tk.X, pady=2)
        
        # Binding für automatisches Speichern
        self.damage_description_text.bind('<KeyRelease>', self.on_damage_description_change)

        # Status und Progress
        status_frame = ttk.Frame(self.left_column)
        status_frame.grid(row=4, column=0, sticky="ew")
        
        ttk.Label(status_frame, textvariable=self.status_var).pack(side=tk.LEFT)
        
        # Mittlere Spalte (20%) - Bewertung
        self.center_column = ttk.Frame(self.content_frame)
        self.center_column.grid(row=0, column=2, sticky="nsew", padx=5)
        
        # Konfiguriere Spalten- und Zeilengewichte für vertikales Resizing
        self.center_column.grid_columnconfigure(0, weight=1)  # Spalte expandiert horizontal
        self.center_column.grid_rowconfigure(0, weight=1)  # Erste Zeile expandiert vertikal
        
        # Container-Frame für vertikale Zentrierung
        center_container = ttk.Frame(self.center_column)
        center_container.grid(row=0, column=0, sticky="")
        
        # Konfiguriere Container für Zentrierung
        center_container.grid_rowconfigure(0, weight=1)  # Oberer Bereich expandiert
        center_container.grid_rowconfigure(2, weight=1)  # Unterer Bereich expandiert
        
        # Einheitliche große Schrift für alle Buttons
        einheits_font = ("Segoe UI", FONT_SIZES['body'])
        einheits_font_bold = ("Segoe UI", FONT_SIZES['body'], "bold")
        
        # Bild verwenden - Kollapsible
        self.use_frame = self.create_collapsible_frame(center_container, "Bild verwenden", row=1)
        # Setze Standardwert für "Bild verwenden" basierend auf aktueller Sprache
        current_options = self.config_manager.get_language_specific_list('use_image_options')
        default_use_image = current_options[0] if current_options else "ja"
        self.use_image_var = tk.StringVar(value=default_use_image)
        for option in self.config_manager.get_language_specific_list('use_image_options'):
            tk.Radiobutton(self.use_frame['content'], text=option, variable=self.use_image_var, 
                           value=option, command=self.save_current_evaluation, font=einheits_font).pack(anchor=tk.W)
        
        # Schadenskategorien - Kollapsible
        self.damage_frame = self.create_collapsible_frame(center_container, "🔍 Schadenskategorien", row=2)
        self.damage_vars = {}
        for category in self.config_manager.get_language_specific_list('damage_categories'):
            var = tk.BooleanVar()
            self.damage_vars[category] = var
            tk.Checkbutton(self.damage_frame['content'], text=category, variable=var, 
                           command=self.save_current_evaluation, font=einheits_font).pack(anchor=tk.W)
        
        # Bildart-Kategorien - Kollapsible
        self.image_type_frame = self.create_collapsible_frame(center_container, "📸 Bildart-Kategorien", row=3)
        self.image_type_vars = {}
        for img_type in self.config_manager.get_language_specific_list('image_types'):
            var = tk.BooleanVar()
            self.image_type_vars[img_type] = var
            tk.Checkbutton(self.image_type_frame['content'], text=img_type, variable=var, 
                           command=self.save_current_evaluation, font=einheits_font).pack(anchor=tk.W)
        
        # Schadensbewertung - Kollapsible
        self.quality_frame = self.create_collapsible_frame(center_container, "⚖️ Schadensbewertung", row=4)
        self.image_quality_var = tk.StringVar(value="Unknown")
        for option in self.config_manager.get_language_specific_list('image_quality_options'):
            tk.Radiobutton(self.quality_frame['content'], text=option, variable=self.image_quality_var, 
                           value=option, command=self.save_current_evaluation, font=einheits_font).pack(anchor=tk.W)
        
        # Rechte Spalte (25%) - Statistik
        self.right_column = ttk.Frame(self.content_frame)
        self.right_column.grid(row=0, column=3, sticky="nsew", padx=(5, 0))
        
        # Konfiguriere Spalten- und Zeilengewichte für vertikales Resizing
        self.right_column.grid_columnconfigure(0, weight=1)  # Spalte expandiert horizontal
        self.right_column.grid_rowconfigure(0, weight=0)  # Anzahl-Bereich nimmt nur benötigten Platz
        self.right_column.grid_rowconfigure(1, weight=1)  # Treeview-Bereich expandiert vertikal
        
        # Kompakte Bewertungsfortschritt-Anzeige
        counts_frame = ttk.LabelFrame(self.right_column, 
                                     text="Bewertungsfortschritt", 
                                     padding=8)
        counts_frame.grid(row=0, column=0, sticky="ew")
        
        # Fortschrittsbalken (kompakt)
        self.evaluation_progress = ttk.Progressbar(counts_frame, mode='determinate', 
                                                  length=200, style="Custom.Horizontal.TProgressbar")
        self.evaluation_progress.pack(fill=tk.X, pady=(0, 3))
        
        # Fortschritts-Zahlen direkt unter Balken
        self.evaluation_progress_label = ttk.Label(counts_frame, 
                                                  text="0/0",
                                                  font=("Segoe UI", FONT_SIZES['small']),
                                                  foreground=COLORS['text_secondary'])
        self.evaluation_progress_label.pack()
        
        # Zusätzliche Statistiken (entfernt für kompaktere Anzeige auf der rechten Seite)
        
        # Initialisiere Fortschrittsanzeige
        self.update_evaluation_progress()
        
        # Hinweis: "Alle Bewertungen zurücksetzen" wurde ins Menü Extras verschoben
        
        # Kategorien-Treeview für Fortschrittsanzeige
        categories_frame = ttk.LabelFrame(self.right_column, 
                                         text="Kategorien-Fortschritt", 
                                         padding=10)
        categories_frame.grid(row=1, column=0, sticky="nsew", pady=(5, 0))
        categories_frame.grid_rowconfigure(0, weight=1)
        
        # Treeview für Kategorien und Kürzel (maximale Höhe und größere Schrift)
        self.categories_tree = ttk.Treeview(categories_frame, columns=('progress',), show='tree headings', height=25)
        self.categories_tree.heading('#0', text='Kategorie/Kürzel')
        self.categories_tree.heading('progress', text='Fortschritt')
        self.categories_tree.column('#0', width=200)
        self.categories_tree.column('progress', width=100)
        
        # Konfiguriere Schriftgröße (2 Punkte größer)
        style = ttk.Style()
        style.configure("Treeview", font=("TkDefaultFont", 11))  # Standard ist 9, jetzt 11
        style.configure("Treeview.Heading", font=("TkDefaultFont", 13, "bold"))  # Überschriften fett und größer
        
        # Scrollbar für Treeview
        categories_scrollbar = ttk.Scrollbar(categories_frame, orient=tk.VERTICAL, command=self.categories_tree.yview)
        self.categories_tree.configure(yscrollcommand=categories_scrollbar.set)
        
        # Tags für Farben konfigurieren
        self.categories_tree.tag_configure('completed', background='#C8E6C9', foreground='#2E7D32', font=("TkDefaultFont", 11, "bold"))
        
        self.categories_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        categories_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Doppelklick-Event für Navigation
        self.categories_tree.bind('<Double-1>', self.on_treeview_double_click)
        
        # Aktualisiere Kategorien-Treeview
        self.update_categories_treeview()
        
        # Tab-Navigation Setup - sammle alle navigierbaren Widgets
        self.setup_tab_navigation()
        
        # Tooltips zu allen Buttons hinzufügen
        self.after(100, self.add_tooltips_to_buttons)  # Verzögert ausführen, damit alle Widgets geladen sind
        
        print("Fertig mit create_widgets")

    def update_categories_treeview(self):
        """Aktualisiert das Kategorien-Treeview mit Fortschrittsanzeige"""
        try:
            if not hasattr(self, 'categories_tree'):
                print("DEBUG Treeview: categories_tree existiert nicht")
                return
                
            # Lösche alle Einträge
            for item in self.categories_tree.get_children():
                self.categories_tree.delete(item)
            
            # Hole Kürzeltabelle
            kurzel_table = self.json_config.get('kurzel_table', {})
            print(f"DEBUG Treeview: {len(kurzel_table)} Kürzel in kurzel_table gefunden")
            
            # Gruppiere Kürzel nach Kategorien
            categories = {}
            for kurzel_code, kurzel_data in kurzel_table.items():
                if kurzel_data.get('active', True):
                    category = kurzel_data.get('category', 'Unbekannt')
                    if category not in categories:
                        categories[category] = []
                    categories[category].append(kurzel_code)
            
            print(f"DEBUG Treeview: {len(categories)} Kategorien gefunden")
            
            # Füge Kategorien und Kürzel hinzu
            for category, kurzel_list in sorted(categories.items()):
                # Berechne Gesamtfortschritt für die Kategorie
                category_total = 0
                category_evaluated = 0
                all_kurzel_completed = True
                
                for kurzel in sorted(kurzel_list):
                    progress = self.calculate_kurzel_progress(kurzel)
                    if progress != "0/0":
                        evaluated, total = map(int, progress.split('/'))
                        category_total += total
                        category_evaluated += evaluated
                        if evaluated < total:
                            all_kurzel_completed = False
                    else:
                        all_kurzel_completed = False
                
                # Kategorie-Fortschritt berechnen
                if category_total > 0:
                    category_progress = f"{category_evaluated}/{category_total}"
                else:
                    category_progress = "0/0"
                
                # Kategorie als Hauptknoten mit Farbe
                category_item = self.categories_tree.insert('', 'end', text=category, values=(category_progress,))
                
                # Grüne Farbe für abgeschlossene Kategorien
                if all_kurzel_completed and category_total > 0:
                    self.categories_tree.item(category_item, tags=('completed',))
                
                # Kürzel als Unterknoten
                for kurzel in sorted(kurzel_list):
                    progress = self.calculate_kurzel_progress(kurzel)
                    kurzel_item = self.categories_tree.insert(category_item, 'end', text=kurzel, values=(progress,))
                    
                    # Grüne Farbe für abgeschlossene Kürzel
                    if progress != "0/0":
                        evaluated, total = map(int, progress.split('/'))
                        if evaluated == total:
                            self.categories_tree.item(kurzel_item, tags=('completed',))
                
                # Erweitere Kategorie standardmäßig
                self.categories_tree.item(category_item, open=True)
                
        except Exception as e:
            logger.error(f"Fehler beim Aktualisieren des Kategorien-Treeviews: {e}")

    def calculate_kurzel_progress(self, kurzel_code):
        """Berechnet den Fortschritt für ein bestimmtes Kürzel (optimiert mit Cache)"""
        try:
            if not self.files:
                return "0/0"
            
            # Verwende den bestehenden Cache für bessere Performance
            self.build_evaluation_cache()
            
            # Zähle Bilder mit diesem Kürzel aus dem Cache
            total_images = 0
            evaluated_images = 0
            
            for filename in self.files:
                if filename in self._evaluation_cache:
                    cache_entry = self._evaluation_cache[filename]
                    if cache_entry.get('tag_ocr') == kurzel_code:
                        total_images += 1
                        if cache_entry.get('is_evaluated', False):
                            evaluated_images += 1
            
            return f"{evaluated_images}/{total_images}"
            
        except Exception as e:
            logger.error(f"Fehler beim Berechnen des Kürzel-Fortschritts: {e}")
            return "0/0"

    def on_treeview_double_click(self, event):
        """Behandelt Doppelklick im Kategorien-Treeview für Navigation"""
        try:
            # Hole das ausgewählte Element
            selection = self.categories_tree.selection()
            if not selection:
                return
            
            item = selection[0]
            item_text = self.categories_tree.item(item, 'text')
            item_values = self.categories_tree.item(item, 'values')
            
            # Prüfe ob es ein Kürzel (Unterelement) oder eine Kategorie (Hauptelement) ist
            parent = self.categories_tree.parent(item)
            
            if parent:  # Es ist ein Kürzel (Unterelement)
                logger.info(f"Doppelklick auf Kürzel: {item_text}")
                self.navigate_to_kurzel(item_text)
            else:  # Es ist eine Kategorie (Hauptelement)
                logger.info(f"Doppelklick auf Kategorie: {item_text}")
                self.navigate_to_category(item_text)
                
        except Exception as e:
            logger.error(f"Fehler beim Doppelklick-Handler: {e}")

    def navigate_to_kurzel(self, kurzel_code):
        """Navigiert zum ersten Bild mit dem angegebenen Kürzel"""
        try:
            if not self.files:
                return
            
            # Finde das erste Bild mit diesem Kürzel
            for i, filename in enumerate(self.files):
                if filename in self._evaluation_cache:
                    cache_entry = self._evaluation_cache[filename]
                    if cache_entry.get('tag_ocr') == kurzel_code:
                        # Springe zu diesem Bild
                        self.index = i
                        self.show_image()
                        logger.info(f"Zu Bild gesprungen: {filename} (Index: {i})")
                        return
            
            # Kein Bild mit diesem Kürzel gefunden
            messagebox.showinfo("Info", f"Kein Bild mit Kürzel '{kurzel_code}' gefunden")
            
        except Exception as e:
            logger.error(f"Fehler beim Navigieren zu Kürzel {kurzel_code}: {e}")

    def navigate_to_category(self, category_name):
        """Navigiert zum ersten Bild der angegebenen Kategorie"""
        try:
            if not self.files:
                return
            
            # Hole alle Kürzel dieser Kategorie
            kurzel_table = self.json_config.get('kurzel_table', {})
            category_kurzel = []
            
            for kurzel_code, kurzel_data in kurzel_table.items():
                if kurzel_data.get('active', True) and kurzel_data.get('category', '') == category_name:
                    category_kurzel.append(kurzel_code)
            
            if not category_kurzel:
                messagebox.showinfo("Info", f"Keine Kürzel in Kategorie '{category_name}' gefunden")
                return
            
            # Finde das erste Bild mit einem der Kürzel dieser Kategorie
            for i, filename in enumerate(self.files):
                if filename in self._evaluation_cache:
                    cache_entry = self._evaluation_cache[filename]
                    tag_ocr = cache_entry.get('tag_ocr', '')
                    if tag_ocr in category_kurzel:
                        # Springe zu diesem Bild
                        self.index = i
                        self.show_image()
                        logger.info(f"Zu Bild der Kategorie gesprungen: {filename} (Index: {i}, Kürzel: {tag_ocr})")
                        return
            
            # Kein Bild dieser Kategorie gefunden
            messagebox.showinfo("Info", f"Kein Bild in Kategorie '{category_name}' gefunden")
            
        except Exception as e:
            logger.error(f"Fehler beim Navigieren zu Kategorie {category_name}: {e}")

    def invalidate_evaluation_cache(self):
        """Markiert den Cache als veraltet"""
        self._cache_dirty = True
        self._evaluation_cache.clear()
        self._tag_evaluation_cache.clear()

    def is_image_evaluated(self, exif_data, debug=False):
        """Prüft, ob ein Bild als bewertet gilt"""
        if not exif_data:
            if debug:
                print("DEBUG is_evaluated: Keine EXIF-Daten vorhanden")
            return False
            
        # Debug: Zeige verfügbare Keys
        if debug:
            print(f"DEBUG is_evaluated: EXIF-Keys vorhanden: {list(exif_data.keys())}")
            
        # Prüfe "Bild verwenden"
        use_image = exif_data.get('use_image', '')
        if use_image in ['nein', 'no']:
            if debug:
                print(f"DEBUG is_evaluated: Bild übersprungen (use_image={use_image})")
            return True
            
        # Prüfe Schadenskategorien
        damage_categories = exif_data.get('damage_categories', [])
        
        # Prüfe auf "visuell keine Defekte" (mehrsprachig)
        no_defects_variants = ['Visually no defects', 'Visuell keine Defekte']
        if any(variant in damage_categories for variant in no_defects_variants):
            if debug:
                print(f"DEBUG is_evaluated: Bild als bewertet erkannt wegen 'keine Defekte': {damage_categories}")
            return True
            
        # Mindestens eine Schadenskategorie UND mindestens eine Bildart-Kategorie
        image_types = exif_data.get('image_types', [])
        is_evaluated = len(damage_categories) > 0 and len(image_types) > 0
        
        if debug:
            if is_evaluated:
                print(f"DEBUG is_evaluated: Bild als bewertet erkannt wegen Schäden+Bildarten: Schäden={damage_categories}, Bildarten={image_types}")
            else:
                print(f"DEBUG is_evaluated: Bild NICHT bewertet - Schäden={len(damage_categories)}, Bildarten={len(image_types)}")
        
        return is_evaluated

    def build_evaluation_cache(self):
        """Baut den Cache für Bewertungsdaten auf"""
        if not self.files:
            return
            
        # Cache immer aufbauen, wenn keine Daten vorhanden sind
        if not self._cache_dirty and (self._evaluation_cache or self._tag_evaluation_cache):
            return
            
        self._evaluation_cache.clear()
        self._tag_evaluation_cache.clear()
        
        print(f"DEBUG: Baue Cache für {len(self.files)} Bilder auf")
        
        # Sammle alle Tags und ihre Bilder
        tag_images = {}
        
        debug_counter = 0  # Nur erste 5 Bilder im Detail debuggen
        
        for filename in self.files:
            try:
                filepath = os.path.join(self.source_dir, filename)
                exif_data = get_exif_usercomment(filepath)
                
                # Cache Bewertung für dieses Bild (mit Debug für erste 5)
                should_debug = debug_counter < 5
                if should_debug:
                    print(f"\n=== DEBUG Bild #{debug_counter + 1}: {filename} ===")
                is_evaluated = self.is_image_evaluated(exif_data, debug=should_debug)
                tag_ocr = exif_data.get('TAGOCR', '') if exif_data else ''
                debug_counter += 1
                self._evaluation_cache[filename] = {
                    'is_evaluated': is_evaluated,
                    'tag_ocr': tag_ocr
                }
                
                # Debug: nur für erste 5 Bilder
                if is_evaluated and debug_counter <= 5:
                    print(f"DEBUG: {filename} ist bewertet")
                
                # Sammle Bilder pro Tag
                if exif_data and "TAGOCR" in exif_data:
                    tag = exif_data["TAGOCR"]
                    if tag not in tag_images:
                        tag_images[tag] = []
                    tag_images[tag].append(filename)
                    
            except Exception as e:
                print(f"Fehler beim Cache-Aufbau für {filename}: {e}")
                self._evaluation_cache[filename] = {'is_evaluated': False, 'tag_ocr': ''}
        
        # Prüfe vollständige Bewertung für jeden Tag
        for tag, images in tag_images.items():
            if not images:
                continue
            # Tag ist vollständig bewertet, wenn alle Bilder des Tags bewertet sind
            is_tag_evaluated = all(self._evaluation_cache.get(img, False) for img in images)
            self._tag_evaluation_cache[tag] = is_tag_evaluated
            
            if is_tag_evaluated:
                print(f"DEBUG: Tag {tag} ist vollständig bewertet ({len(images)} Bilder)")
        
        self._cache_dirty = False

    def update_evaluation_progress(self):
        """Aktualisiert den Bewertungsfortschritt (optimiert mit Cache, zweisprachig)"""
        if not self.files:
            self.evaluation_progress['value'] = 0
            self.evaluation_progress['maximum'] = 0
            self.evaluation_progress_label.config(text="0/0")
            print("DEBUG: Keine Bilder geladen, Fortschritt auf 0/0 gesetzt")
            return
        
        # Baue Cache auf, falls nötig
        self.build_evaluation_cache()
        
        total_images = len(self.files)
        evaluated_count = sum(1 for cache_entry in self._evaluation_cache.values() 
                             if isinstance(cache_entry, dict) and cache_entry.get('is_evaluated', False))
        
        print(f"DEBUG: Fortschritt aktualisiert - {evaluated_count}/{total_images} bewertet")
        print(f"DEBUG: Cache enthält {len(self._evaluation_cache)} Einträge")
        
        # Aktualisiere Fortschrittsbalken
        self.evaluation_progress['maximum'] = total_images
        self.evaluation_progress['value'] = evaluated_count
        
        # Aktualisiere Labels (nur Zahlen, kompakt)
        if total_images > 0:
            percentage = (evaluated_count / total_images) * 100
            self.evaluation_progress_label.config(text=f"{evaluated_count}/{total_images} ({percentage:.0f}%)")
        else:
            self.evaluation_progress_label.config(text="0/0")
        
        # Aktualisiere auch das Kategorien-Treeview
        self.update_categories_treeview()

    def is_tag_fully_evaluated(self, tag):
        """Prüft, ob alle Bilder eines bestimmten Tags bewertet sind (optimiert mit Cache)"""
        # Baue Cache auf, falls nötig
        self.build_evaluation_cache()
        
        return self._tag_evaluation_cache.get(tag, False)


    def show_detailed_log(self):
        """Zeigt das detaillierte Log in einem neuen Fenster an"""
        if not os.path.exists(DETAILED_LOG_FILE):
            messagebox.showinfo("Info", "Noch kein detailliertes Log vorhanden.")
            return
        
        try:
            with open(DETAILED_LOG_FILE, 'r', encoding='utf-8') as f:
                log_content = f.read()
        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Lesen des detaillierten Logs: {e}")
            return
        
        # Erstelle neues Fenster für Log-Anzeige
        log_window = tk.Toplevel(self)
        log_window.title("Detailliertes Log")
        log_window.geometry("1000x700")
        
        # Erstelle Text-Widget mit Scrollbar
        text_frame = ttk.Frame(log_window)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        text_widget = tk.Text(text_frame, wrap=tk.WORD, font=('Courier', 9))
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Füge Log-Inhalt hinzu
        text_widget.insert('1.0', log_content)
        text_widget.config(state=tk.DISABLED)  # Nur lesbar
        
        # Buttons
        button_frame = ttk.Frame(log_window)
        button_frame.pack(fill=tk.X, pady=5)
        ttk.Button(button_frame, text="Log löschen", command=lambda: self.clear_detailed_log(log_window)).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Schließen", command=log_window.destroy).pack(side=tk.RIGHT, padx=5)

    def clear_detailed_log(self, log_window):
        """Löscht das detaillierte Log"""
        if messagebox.askyesno("Bestätigung", "Möchten Sie das detaillierte Log wirklich löschen?"):
            try:
                os.remove(DETAILED_LOG_FILE)
                messagebox.showinfo("Erfolg", "Detailliertes Log wurde gelöscht.")
                log_window.destroy()
            except Exception as e:
                messagebox.showerror("Fehler", f"Fehler beim Löschen des Logs: {e}")

    def show_ocr_log(self):
        """Zeigt das OCR-Log in einem neuen Fenster an"""
        if not os.path.exists(LOG_FILE):
            messagebox.showinfo("Info", "Noch kein OCR-Log vorhanden.")
            return
        
        try:
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                log_content = f.read()
        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Lesen des OCR-Logs: {e}")
            return
        
        # Erstelle neues Fenster für Log-Anzeige
        log_window = tk.Toplevel(self)
        log_window.title("OCR Log")
        log_window.geometry("800x600")
        
        # Text Widget mit Scrollbar
        text_frame = ttk.Frame(log_window)
        text_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        text_widget = tk.Text(text_frame, wrap=tk.WORD, font=("Consolas", 10))
        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)
        
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Log-Inhalt einfügen
        text_widget.insert(tk.END, log_content)
        text_widget.config(state=tk.DISABLED)
        
        # Button Frame
        button_frame = ttk.Frame(log_window)
        button_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        ttk.Button(button_frame, text="Log löschen", command=lambda: self.clear_log(log_window)).pack(side=tk.LEFT)
        ttk.Button(button_frame, text="Schließen", command=log_window.destroy).pack(side=tk.RIGHT)

    def show_json_data(self):
        """Zeigt alle EXIF-Daten im JSON-Format in einem neuen Fenster an"""
        if not self.files:
            messagebox.showinfo("Info", "Keine Bilder geladen. Bitte öffnen Sie zuerst einen Ordner.")
            return
        
        # Sammle alle EXIF-Daten
        all_json_data = {}
        for i, filename in enumerate(self.files):
            try:
                filepath = os.path.join(self.source_dir, filename)
                exif_data = get_exif_usercomment(filepath)
                if exif_data:
                    all_json_data[filename] = exif_data
                else:
                    all_json_data[filename] = {"status": "Keine EXIF-Daten gefunden"}
            except Exception as e:
                all_json_data[filename] = {"status": f"Fehler beim Lesen: {str(e)}"}
        
        # Erstelle neues Fenster für JSON-Anzeige
        json_window = tk.Toplevel(self)
        json_window.title("Alle EXIF-Daten (JSON)")
        json_window.geometry("1000x700")
        
        # Hauptframe
        main_frame = ttk.Frame(json_window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Datei-Auswahl Frame
        file_frame = ttk.LabelFrame(main_frame, text="Datei auswählen", padding=5)
        file_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Combobox für Dateiauswahl
        self.json_file_combo = ttk.Combobox(file_frame, values=list(all_json_data.keys()), state="readonly", width=80)
        self.json_file_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        
        # Aktualisieren Button
        ttk.Button(file_frame, text="Aktualisieren", command=lambda: self.refresh_json_data(json_window, all_json_data)).pack(side=tk.RIGHT)
        
        # Text Widget mit Scrollbar für JSON-Anzeige
        text_frame = ttk.Frame(main_frame)
        text_frame.pack(fill=tk.BOTH, expand=True)
        
        self.json_text_widget = tk.Text(text_frame, wrap=tk.WORD, font=("Consolas", 10))
        json_scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=self.json_text_widget.yview)
        json_scrollbar_h = ttk.Scrollbar(text_frame, orient=tk.HORIZONTAL, command=self.json_text_widget.xview)
        self.json_text_widget.configure(yscrollcommand=json_scrollbar.set, xscrollcommand=json_scrollbar_h.set)
        
        self.json_text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        json_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        json_scrollbar_h.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Event-Handler für Dateiauswahl
        self.json_file_combo.bind("<<ComboboxSelected>>", lambda e: self.update_json_display(all_json_data))
        
        # Zeige erste Datei an, falls vorhanden
        if all_json_data:
            self.json_file_combo.set(list(all_json_data.keys())[0])
            self.update_json_display(all_json_data)
        
        # Button Frame
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(button_frame, text="Alle Daten exportieren", 
                  command=lambda: self.export_all_json_data(all_json_data)).pack(side=tk.LEFT)
        ttk.Button(button_frame, text="Schließen", command=json_window.destroy).pack(side=tk.RIGHT)

    def update_json_display(self, all_json_data):
        """Aktualisiert die JSON-Anzeige für die ausgewählte Datei"""
        selected_file = self.json_file_combo.get()
        if not selected_file or selected_file not in all_json_data:
            return
        
        json_data = all_json_data[selected_file]
        
        # Text Widget leeren und neue Daten einfügen
        self.json_text_widget.config(state=tk.NORMAL)
        self.json_text_widget.delete(1.0, tk.END)
        
        # JSON formatiert anzeigen
        try:
            formatted_json = json.dumps(json_data, indent=2, ensure_ascii=False)
            self.json_text_widget.insert(tk.END, formatted_json)
        except Exception as e:
            self.json_text_widget.insert(tk.END, f"Fehler beim Formatieren der JSON-Daten: {str(e)}\n\nRohdaten:\n{str(json_data)}")
        
        self.json_text_widget.config(state=tk.DISABLED)

    def refresh_json_data(self, json_window, all_json_data):
        """Aktualisiert alle JSON-Daten neu"""
        # Sammle alle EXIF-Daten erneut
        all_json_data.clear()
        for i, filename in enumerate(self.files):
            try:
                filepath = os.path.join(self.source_dir, filename)
                exif_data = get_exif_usercomment(filepath)
                if exif_data:
                    all_json_data[filename] = exif_data
                else:
                    all_json_data[filename] = {"status": "Keine EXIF-Daten gefunden"}
            except Exception as e:
                all_json_data[filename] = {"status": f"Fehler beim Lesen: {str(e)}"}
        
        # Combobox aktualisieren
        self.json_file_combo['values'] = list(all_json_data.keys())
        if all_json_data:
            self.json_file_combo.set(list(all_json_data.keys())[0])
            self.update_json_display(all_json_data)
        
        messagebox.showinfo("Info", f"JSON-Daten aktualisiert. {len(all_json_data)} Dateien geladen.")

    def export_all_json_data(self, all_json_data):
        """Exportiert alle JSON-Daten in eine Datei"""
        try:
            filename = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                title="Alle JSON-Daten speichern"
            )
            
            if filename:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(all_json_data, f, indent=2, ensure_ascii=False)
                messagebox.showinfo("Erfolg", f"Alle JSON-Daten wurden in {filename} gespeichert.")
        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Speichern der JSON-Daten: {str(e)}")

    def clear_log(self, log_window):
        """Löscht das OCR-Log"""
        if messagebox.askyesno("Bestätigung", "Möchten Sie das OCR-Log wirklich löschen?"):
            try:
                os.remove(LOG_FILE)
                messagebox.showinfo("Erfolg", "OCR-Log wurde gelöscht.")
                log_window.destroy()
            except Exception as e:
                messagebox.showerror("Fehler", f"Fehler beim Löschen des Logs: {e}")
    def save_current_evaluation(self):
        """Speichert die aktuelle Bewertung in EXIF-Daten"""
        if not self.files:
            return
        
        fname = self.files[self.index]
        path = os.path.join(self.source_dir, fname)
        
        # Lade bestehende EXIF-Daten
        exif_data = get_exif_usercomment(path)
        if exif_data is None:
            exif_data = self.json_config.copy()
        
        # Sammle Bewertungsdaten
        damage_categories = [cat for cat, var in self.damage_vars.items() if var.get()]
        image_types = [img_type for img_type, var in self.image_type_vars.items() if var.get()]
        
        # Aktualisiere EXIF-Daten
        exif_data["damage_categories"] = damage_categories
        exif_data["image_types"] = image_types
        exif_data["use_image"] = self.use_image_var.get()
        exif_data["image_quality"] = self.image_quality_var.get()
        exif_data["damage_description"] = self.damage_description_text.get("1.0", tk.END).strip()
        
        # Aktualisiere TAGOCR aus dem Korrekt-Dropdown
        new_tagocr = self.correct_var.get().strip().upper()
        if new_tagocr and new_tagocr in self.valid_kurzel:
            old_tagocr = exif_data.get("TAGOCR", "")
            exif_data["TAGOCR"] = new_tagocr
            
            # Update counter wenn sich TAGOCR geändert hat
            if old_tagocr != new_tagocr:
                if old_tagocr in self.valid_kurzel:
                    self.counter[old_tagocr] -= 1
                self.counter[new_tagocr] += 1
                # Aktualisiere die Kürzel-Tabelle
                if hasattr(self, 'refresh_kurzel_table'):
                    self.refresh_kurzel_table()
                
                write_detailed_log("info", "TAGOCR aktualisiert", f"Datei: {fname}, Alt: '{old_tagocr}', Neu: '{new_tagocr}'")
        
        write_detailed_log("info", "Bewertung gespeichert", f"Datei: {fname}, Schäden: {damage_categories}, Bildarten: {image_types}, Verwenden: {self.use_image_var.get()}, Beschreibung: {self.damage_description_text.get('1.0', tk.END).strip()}, TAGOCR: {new_tagocr}")
        
        # Speichere EXIF-Daten
        if save_exif_usercomment(path, exif_data):
            self.status_var.set(f"Bewertung gespeichert: {fname}")
            # Cache invalidieren, da sich Bewertungsdaten geändert haben
            self.invalidate_evaluation_cache()
            # Aktualisiere Bewertungsfortschritt
            self.update_evaluation_progress()
        else:
            write_detailed_log("error", "Fehler beim Speichern der Bewertung", f"Datei: {fname}")
            self.status_var.set(f"Fehler beim Speichern: {fname}")

    def load_current_evaluation(self):
        """Lädt die Bewertung für das aktuelle Bild"""
        if not self.files:
            return
        
        fname = self.files[self.index]
        path = os.path.join(self.source_dir, fname)
        
        # Lade EXIF-Daten
        exif_data = get_exif_usercomment(path)
        if exif_data is None:
            # Setze Standardwerte
            for var in self.damage_vars.values():
                var.set(False)
            for var in self.image_type_vars.values():
                var.set(False)
            # Setze Standardwert für "Bild verwenden" basierend auf aktueller Sprache
            current_options = self.config_manager.get_language_specific_list('use_image_options')
            default_use_image = current_options[0] if current_options else "ja"
            self.use_image_var.set(default_use_image)
            self.image_quality_var.set("Unknown")
            self.damage_description_text.delete("1.0", tk.END)
            return
        
        # Lade Schadenskategorien
        damage_categories = exif_data.get("damage_categories", [])
        
        # Prüfe ob damage_categories ein dict mit Sprachen ist
        if isinstance(damage_categories, dict):
            # Verwende die aktuelle Sprache oder fallback auf 'de' oder 'en'
            current_lang = self.config_manager.current_language if hasattr(self.config_manager, 'current_language') else 'de'
            damage_categories = damage_categories.get(current_lang, damage_categories.get('de', damage_categories.get('en', [])))
        
        for category, var in self.damage_vars.items():
            var.set(category in damage_categories)
        
        # Lade Bildart-Kategorien
        image_types = exif_data.get("image_types", [])
        
        # Prüfe ob image_types ein dict mit Sprachen ist
        if isinstance(image_types, dict):
            # Verwende die aktuelle Sprache oder fallback auf 'de' oder 'en'
            current_lang = self.config_manager.current_language if hasattr(self.config_manager, 'current_language') else 'de'
            image_types = image_types.get(current_lang, image_types.get('de', image_types.get('en', [])))
        
        # Automatische Vorauswahl basierend auf erkanntem Kürzel
        auto_selected_types = self.get_auto_selected_image_types(exif_data)
        if auto_selected_types and not image_types:  # Nur wenn noch keine Bildarten gesetzt sind
            image_types = auto_selected_types
            logger.info(f"Automatische Bildart-Vorauswahl: {image_types}")
        
        for img_type, var in self.image_type_vars.items():
            var.set(img_type in image_types)
        
        # Lade Bild verwenden
        use_image = exif_data.get("use_image", "ja")
        # Prüfe ob der Wert in der aktuellen Sprache verfügbar ist
        current_options = self.config_manager.get_language_specific_list('use_image_options')
        if use_image not in current_options and current_options:
            # Fallback auf den ersten verfügbaren Wert
            use_image = current_options[0]
        self.use_image_var.set(use_image)
        
        # Lade Schadensbewertung
        self.image_quality_var.set(exif_data.get("image_quality", "Unknown"))
        
        # Lade Damage Description
        self.damage_description_text.delete("1.0", tk.END)
        self.damage_description_text.insert("1.0", exif_data.get("damage_description", ""))

    def get_auto_selected_image_types(self, exif_data):
        """Ermittelt automatisch auszuwählende Bildarten basierend auf dem erkannten Kürzel"""
        try:
            # Hole das erkannte Kürzel
            tag_ocr = exif_data.get('TAGOCR', '')
            if not tag_ocr:
                return []
            
            # Hole die Kürzeltabelle
            kurzel_table = self.json_config.get('kurzel_table', {})
            kurzel_data = kurzel_table.get(tag_ocr, {})
            
            # Hole die Bildart-Zuordnung
            image_type_assignment = kurzel_data.get('image_type_assignment', '')
            if not image_type_assignment or image_type_assignment == 'Nicht zugeordnet':
                return []
            
            # Konvertiere die Zuordnung zu Bildarten-Liste
            # Unterstützt Komma-getrennte Werte
            selected_types = []
            assignments = [a.strip() for a in image_type_assignment.split(',')]
            
            for assignment in assignments:
                if assignment in IMAGE_TYPES:
                    selected_types.append(assignment)
                else:
                    logger.warning(f"Unbekannte Bildart-Zuordnung: {assignment}")
            
            return selected_types
            
        except Exception as e:
            logger.error(f"Fehler bei automatischer Bildart-Vorauswahl: {e}")
            return []

    def migrate_existing_kurzel_to_table(self):
        """Migriert bestehende Kürzel aus valid_kurzel.txt zur neuen Tabellen-Struktur"""
        try:
            # Lade bestehende Kürzel aus der Datei
            existing_kurzel = []
            if os.path.exists(CODE_FILE):
                with open(CODE_FILE, 'r', encoding='utf-8') as f:
                    existing_kurzel = [line.strip() for line in f if line.strip()]
            
            # Lade auch aus der Konfiguration
            config_kurzel = self.config_manager.get_setting('valid_kurzel', [])
            
            # Kombiniere beide Listen
            all_kurzel = list(set(existing_kurzel + config_kurzel))
            
            migrated_count = 0
            
            for kurzel_code in all_kurzel:
                # Prüfe, ob Kürzel bereits in der Tabelle existiert
                if not self.config_manager.kurzel_table_manager.get_kurzel(kurzel_code):
                    # Erstelle Standard-Struktur für das Kürzel
                    kurzel_data = self.config_manager.kurzel_table_manager.get_default_kurzel_structure()
                    kurzel_data['kurzel_code'] = kurzel_code
                    
                    # Versuche eine sinnvolle Kategorie basierend auf dem Kürzel-Code zu bestimmen
                    if 'GEH' in kurzel_code:
                        kurzel_data['category'] = 'Getriebe'
                        kurzel_data['image_type'] = 'Gear'
                    elif 'LSS' in kurzel_code or 'HSS' in kurzel_code:
                        kurzel_data['category'] = 'Lager'
                        kurzel_data['image_type'] = 'Bearing'
                    elif 'PL' in kurzel_code:
                        kurzel_data['category'] = 'Dichtung'
                        kurzel_data['image_type'] = 'Seal'
                    elif 'COOL' in kurzel_code:
                        kurzel_data['category'] = 'Kühlung'
                        kurzel_data['image_type'] = 'Cooling'
                    elif 'ELEC' in kurzel_code:
                        kurzel_data['category'] = 'Elektrik'
                        kurzel_data['image_type'] = 'Electrical'
                    else:
                        kurzel_data['category'] = 'Sonstiges'
                        kurzel_data['image_type'] = 'Other'
                    
                    # Füge das Kürzel zur Tabelle hinzu
                    if self.config_manager.kurzel_table_manager.add_kurzel(kurzel_data):
                        migrated_count += 1
            
            write_detailed_log("info", "Kürzel-Migration abgeschlossen", f"Anzahl migriert: {migrated_count}")
            return migrated_count
            
        except Exception as e:
            write_detailed_log("error", "Fehler bei Kürzel-Migration", str(e))
            return 0

    def open_kurzel_table_manager(self):
        """Öffnet den Kürzel-Tabellen-Manager"""
        win = tk.Toplevel(self)
        win.title("Kürzel-Tabelle verwalten")
        win.geometry("1200x800")
        win.transient(self)
        win.grab_set()
        
        # Hauptframe
        main_frame = ttk.Frame(win)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Toolbar
        toolbar = ttk.Frame(main_frame)
        toolbar.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Button(toolbar, text="Neues Kürzel", command=lambda: self.add_kurzel_to_table(win)).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="Bearbeiten", command=lambda: self.edit_kurzel_in_table(win)).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="Löschen", command=lambda: self.delete_kurzel_from_table(win)).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="Migration", command=lambda: self.run_migration_and_refresh(win)).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="Export CSV", command=lambda: self.export_kurzel_table()).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="Import CSV", command=lambda: self.import_kurzel_table(win)).pack(side=tk.LEFT, padx=(0, 5))
        
        # Suchfeld
        search_frame = ttk.Frame(toolbar)
        search_frame.pack(side=tk.RIGHT)
        ttk.Label(search_frame, text="Suchen:").pack(side=tk.LEFT)
        search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=search_var, width=20)
        search_entry.pack(side=tk.LEFT, padx=(5, 0))
        search_entry.bind('<KeyRelease>', lambda e: self.filter_kurzel_table(search_var.get(), win))
        
        # Treeview für die Tabelle
        columns = ('kurzel_code', 'name_de', 'name_en', 'category', 'image_type_assignment', 'active')
        tree = ttk.Treeview(main_frame, columns=columns, show='headings', height=20)
        
        # Spalten definieren
        tree.heading('kurzel_code', text='Kürzel')
        tree.heading('name_de', text='Name (DE)')
        tree.heading('name_en', text='Name (EN)')
        tree.heading('category', text='Kategorie')
        tree.heading('image_type_assignment', text='Bildart-Zuordnung')
        tree.heading('active', text='Aktiv')
        
        tree.column('kurzel_code', width=100)
        tree.column('name_de', width=200)
        tree.column('name_en', width=200)
        tree.column('category', width=150)
        tree.column('image_type_assignment', width=150)
        tree.column('active', width=80)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Doppelklick zum Bearbeiten
        tree.bind('<Double-1>', lambda e: self.edit_kurzel_in_table(win))
        
        # Speichere Referenzen für andere Funktionen
        win.tree = tree  # type: ignore
        win.search_var = search_var  # type: ignore
        
        # Lade Daten
        self.load_kurzel_table_data(win)
        
        # Prüfe, ob Migration nötig ist
        kurzel_data = self.config_manager.kurzel_table_manager.get_all_kurzel()
        if not kurzel_data:
            # Keine Kürzel in der Tabelle, führe automatische Migration durch
            migrated_count = self.migrate_existing_kurzel_to_table()
            if migrated_count > 0:
                self.load_kurzel_table_data(win)
                messagebox.showinfo("Automatische Migration", f"{migrated_count} bestehende Kürzel wurden automatisch zur Tabelle hinzugefügt.")
        
        # Statusleiste
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=tk.X, pady=(10, 0))
        self.kurzel_status_label = ttk.Label(status_frame, text="")
        self.kurzel_status_label.pack(side=tk.LEFT)
    
    def load_kurzel_table_data(self, win):
        """Lädt die Kürzel-Tabellendaten in die Treeview"""
        tree = win.tree
        tree.delete(*tree.get_children())
        
        kurzel_data = self.config_manager.kurzel_table_manager.get_all_kurzel()
        for kurzel_code, data in kurzel_data.items():
            tree.insert('', 'end', values=(
                kurzel_code,
                data.get('name_de', ''),
                data.get('name_en', ''),
                data.get('category', ''),
                data.get('image_type_assignment', ''),
                'Ja' if data.get('active', True) else 'Nein'
            ))
        
        # Aktualisiere Status
        count = len(kurzel_data)
        self.kurzel_status_label.config(text=f"Anzahl Kürzel: {count}")
    
    def filter_kurzel_table(self, search_term, win):
        """Filtert die Kürzel-Tabelle basierend auf dem Suchbegriff"""
        tree = win.tree
        tree.delete(*tree.get_children())
        
        if not search_term:
            # Zeige alle Kürzel
            kurzel_data = self.config_manager.kurzel_table_manager.get_all_kurzel()
        else:
            # Suche Kürzel
            kurzel_data = self.config_manager.kurzel_table_manager.search_kurzel(search_term)
        
        for kurzel_code, data in kurzel_data.items():
            tree.insert('', 'end', values=(
                kurzel_code,
                data.get('name_de', ''),
                data.get('name_en', ''),
                data.get('category', ''),
                data.get('image_type_assignment', ''),
                'Ja' if data.get('active', True) else 'Nein'
            ))
    
    def add_kurzel_to_table(self, win):
        """Öffnet Dialog zum Hinzufügen eines neuen Kürzels"""
        self.kurzel_edit_dialog(win, None)
    
    def edit_kurzel_in_table(self, win):
        """Öffnet Dialog zum Bearbeiten eines Kürzels"""
        tree = win.tree
        selection = tree.selection()
        if not selection:
            messagebox.showwarning("Warnung", "Bitte wählen Sie ein Kürzel zum Bearbeiten aus.")
            return
        
        item = tree.item(selection[0])
        kurzel_code = item['values'][0]
        self.kurzel_edit_dialog(win, kurzel_code)
    
    def delete_kurzel_from_table(self, win):
        """Löscht ein ausgewähltes Kürzel"""
        tree = win.tree
        selection = tree.selection()
        if not selection:
            messagebox.showwarning("Warnung", "Bitte wählen Sie ein Kürzel zum Löschen aus.")
            return
        
        item = tree.item(selection[0])
        kurzel_code = item['values'][0]
        
        if messagebox.askyesno("Bestätigung", f"Möchten Sie das Kürzel '{kurzel_code}' wirklich löschen?"):
            if self.config_manager.kurzel_table_manager.delete_kurzel(kurzel_code):
                self.load_kurzel_table_data(win)
                messagebox.showinfo("Erfolg", f"Kürzel '{kurzel_code}' wurde gelöscht.")
            else:
                messagebox.showerror("Fehler", "Fehler beim Löschen des Kürzels.")
    
    def kurzel_edit_dialog(self, parent, kurzel_code=None):
        """Dialog zum Bearbeiten/Hinzufügen von Kürzeln"""
        dialog = tk.Toplevel(parent)
        dialog.title("Kürzel bearbeiten" if kurzel_code else "Neues Kürzel")
        dialog.geometry("600x700")
        dialog.transient(parent)
        dialog.grab_set()
        
        # Lade bestehende Daten oder erstelle neue
        if kurzel_code:
            data = self.config_manager.kurzel_table_manager.get_kurzel(kurzel_code)
            if not data:
                messagebox.showerror("Fehler", "Kürzel nicht gefunden.")
                dialog.destroy()
                return
        else:
            data = self.config_manager.kurzel_table_manager.get_default_kurzel_structure()
        
        # Hauptframe mit Scrollbar
        canvas = tk.Canvas(dialog)
        scrollbar = ttk.Scrollbar(dialog, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Eingabefelder
        fields = {}
        
        # Kürzel-Code
        ttk.Label(scrollable_frame, text="Kürzel-Code:").grid(row=0, column=0, sticky='w', padx=5, pady=5)
        fields['kurzel_code'] = tk.StringVar(value=data.get('kurzel_code', ''))
        ttk.Entry(scrollable_frame, textvariable=fields['kurzel_code'], width=30).grid(row=0, column=1, sticky='ew', padx=5, pady=5)
        
        # Name Deutsch
        ttk.Label(scrollable_frame, text="Name (Deutsch):").grid(row=1, column=0, sticky='w', padx=5, pady=5)
        fields['name_de'] = tk.StringVar(value=data.get('name_de', ''))
        ttk.Entry(scrollable_frame, textvariable=fields['name_de'], width=30).grid(row=1, column=1, sticky='ew', padx=5, pady=5)
        
        # Name Englisch
        ttk.Label(scrollable_frame, text="Name (Englisch):").grid(row=2, column=0, sticky='w', padx=5, pady=5)
        fields['name_en'] = tk.StringVar(value=data.get('name_en', ''))
        ttk.Entry(scrollable_frame, textvariable=fields['name_en'], width=30).grid(row=2, column=1, sticky='ew', padx=5, pady=5)
        
        # Kategorie
        ttk.Label(scrollable_frame, text="Kategorie:").grid(row=3, column=0, sticky='w', padx=5, pady=5)
        fields['category'] = tk.StringVar(value=data.get('category', ''))
        category_combo = ttk.Combobox(scrollable_frame, textvariable=fields['category'], width=27)
        category_combo['values'] = ('Getriebe', 'Lager', 'Dichtung', 'Kühlung', 'Elektrik', 'Sonstiges', 'Unbekannt')
        category_combo.grid(row=3, column=1, sticky='ew', padx=5, pady=5)
        
        # Unterkategorie
        ttk.Label(scrollable_frame, text="Unterkategorie:").grid(row=4, column=0, sticky='w', padx=5, pady=5)
        fields['subcategory'] = tk.StringVar(value=data.get('subcategory', ''))
        ttk.Entry(scrollable_frame, textvariable=fields['subcategory'], width=30).grid(row=4, column=1, sticky='ew', padx=5, pady=5)
        
        # Bildtyp
        ttk.Label(scrollable_frame, text="Bildtyp:").grid(row=5, column=0, sticky='w', padx=5, pady=5)
        fields['image_type'] = tk.StringVar(value=data.get('image_type', ''))
        image_type_combo = ttk.Combobox(scrollable_frame, textvariable=fields['image_type'], width=27)
        image_type_combo['values'] = ('Gear', 'Bearing', 'Seal', 'Cooling', 'Electrical', 'Other', 'Unbekannt')
        image_type_combo.grid(row=5, column=1, sticky='ew', padx=5, pady=5)
        
        # Schadenskategorie
        ttk.Label(scrollable_frame, text="Schadenskategorie:").grid(row=6, column=0, sticky='w', padx=5, pady=5)
        fields['damage_category'] = tk.StringVar(value=data.get('damage_category', ''))
        damage_combo = ttk.Combobox(scrollable_frame, textvariable=fields['damage_category'], width=27)
        damage_combo['values'] = ('Normal', 'Verschleiß', 'Schaden', 'Kritisch', 'Unbekannt')
        damage_combo.grid(row=6, column=1, sticky='ew', padx=5, pady=5)
        
        # Priorität
        ttk.Label(scrollable_frame, text="Priorität:").grid(row=7, column=0, sticky='w', padx=5, pady=5)
        fields['priority'] = tk.StringVar(value=data.get('priority', 'normal'))
        priority_combo = ttk.Combobox(scrollable_frame, textvariable=fields['priority'], width=27)
        priority_combo['values'] = ('niedrig', 'normal', 'hoch', 'kritisch')
        priority_combo.grid(row=7, column=1, sticky='ew', padx=5, pady=5)
        
        # Aktiv
        fields['active'] = tk.BooleanVar(value=data.get('active', True))
        ttk.Checkbutton(scrollable_frame, text="Aktiv", variable=fields['active']).grid(row=8, column=0, columnspan=2, sticky='w', padx=5, pady=5)
        
        # Beschreibung Deutsch
        ttk.Label(scrollable_frame, text="Beschreibung (Deutsch):").grid(row=9, column=0, sticky='nw', padx=5, pady=5)
        fields['description_de'] = tk.Text(scrollable_frame, width=40, height=4)
        fields['description_de'].insert('1.0', data.get('description_de', ''))
        fields['description_de'].grid(row=9, column=1, sticky='ew', padx=5, pady=5)
        
        # Beschreibung Englisch
        ttk.Label(scrollable_frame, text="Beschreibung (Englisch):").grid(row=10, column=0, sticky='nw', padx=5, pady=5)
        fields['description_en'] = tk.Text(scrollable_frame, width=40, height=4)
        fields['description_en'].insert('1.0', data.get('description_en', ''))
        fields['description_en'].grid(row=10, column=1, sticky='ew', padx=5, pady=5)
        
        # Buttons
        button_frame = ttk.Frame(scrollable_frame)
        button_frame.grid(row=11, column=0, columnspan=2, pady=20)
        
        def save_kurzel():
            # Sammle alle Daten
            kurzel_data = {}
            for key, var in fields.items():
                if key in ['description_de', 'description_en']:
                    kurzel_data[key] = var.get('1.0', tk.END).strip()
                else:
                    kurzel_data[key] = var.get()
            
            # Validiere Kürzel-Code
            if not kurzel_data['kurzel_code']:
                messagebox.showerror("Fehler", "Kürzel-Code ist erforderlich.")
                return
            
            # Speichere Kürzel
            if kurzel_code:
                # Aktualisiere bestehendes Kürzel
                if self.config_manager.kurzel_table_manager.update_kurzel(kurzel_code, kurzel_data):
                    messagebox.showinfo("Erfolg", f"Kürzel '{kurzel_code}' wurde aktualisiert.")
                else:
                    messagebox.showerror("Fehler", "Fehler beim Aktualisieren des Kürzels.")
            else:
                # Füge neues Kürzel hinzu
                if self.config_manager.kurzel_table_manager.add_kurzel(kurzel_data):
                    messagebox.showinfo("Erfolg", f"Kürzel '{kurzel_data['kurzel_code']}' wurde hinzugefügt.")
                else:
                    messagebox.showerror("Fehler", "Fehler beim Hinzufügen des Kürzels.")
            
            dialog.destroy()
            # Aktualisiere die Haupttabelle
            self.load_kurzel_table_data(parent)
        
        ttk.Button(button_frame, text="Speichern", command=save_kurzel).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Abbrechen", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        
        # Konfiguriere Grid-Gewichtung
        scrollable_frame.columnconfigure(1, weight=1)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    
    def export_kurzel_table(self):
        """Exportiert die Kürzel-Tabelle als CSV"""
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV-Dateien", "*.csv"), ("Alle Dateien", "*.*")],
            title="Kürzel-Tabelle exportieren"
        )
        if filename:
            exported_file = self.config_manager.kurzel_table_manager.export_to_csv(filename)
            if exported_file:
                messagebox.showinfo("Erfolg", f"Kürzel-Tabelle wurde exportiert: {exported_file}")
            else:
                messagebox.showerror("Fehler", "Fehler beim Exportieren der Kürzel-Tabelle.")
    
    def import_kurzel_table(self, parent):
        """Importiert eine Kürzel-Tabelle aus CSV"""
        filename = filedialog.askopenfilename(
            filetypes=[("CSV-Dateien", "*.csv"), ("Alle Dateien", "*.*")],
            title="Kürzel-Tabelle importieren"
        )
        if filename:
            if messagebox.askyesno("Bestätigung", "Möchten Sie die bestehenden Kürzel durch die importierten ersetzen?"):
                imported_count = self.config_manager.kurzel_table_manager.import_from_csv(filename)
                if imported_count > 0:
                    messagebox.showinfo("Erfolg", f"{imported_count} Kürzel wurden importiert.")
                    self.load_kurzel_table_data(parent)
                else:
                    messagebox.showerror("Fehler", "Fehler beim Importieren der Kürzel-Tabelle.")
    
    def run_migration_and_refresh(self, win):
        """Führt die Migration durch und aktualisiert die Tabelle"""
        migrated_count = self.migrate_existing_kurzel_to_table()
        if migrated_count > 0:
            messagebox.showinfo("Migration erfolgreich", f"{migrated_count} Kürzel wurden zur Tabelle hinzugefügt.")
            self.load_kurzel_table_data(win)
        else:
            messagebox.showinfo("Migration", "Keine neuen Kürzel zu migrieren gefunden.")

    def open_config_editor(self):
        """Öffnet einen Editor für die zentrale JSON-Konfigurationsdatei mit Sprachwahl und OCR-Methoden-Auswahl."""
        # Prüfe ob Fenster bereits geöffnet ist
        if self._settings_window is not None and self._settings_window.winfo_exists():
            # Fenster ist bereits geöffnet, bringe es in den Vordergrund
            self._settings_window.lift()
            self._settings_window.focus()
            return
        
        # Erstelle neues Fenster
        win = tk.Toplevel(self)
        win.title("Konfiguration bearbeiten")
        win.geometry("600x700")
        
        # Speichere Referenz auf das Fenster
        self._settings_window = win
        
        # Cleanup-Funktion beim Schließen
        def on_settings_close():
            self._settings_window = None
            win.destroy()
        
        win.protocol("WM_DELETE_WINDOW", on_settings_close)

        notebook = ttk.Notebook(win)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)


        # Tab für Crop-Out Einstellungen
        crop_frame = ttk.Frame(notebook)
        notebook.add(crop_frame, text="Crop-Out Einstellungen")
        
        # Aktuelles Bild für Vorschau laden
        current_image = None
        if hasattr(self, 'source_dir') and hasattr(self, 'files') and hasattr(self, 'index') and self.files:
            try:
                img_path = os.path.join(self.source_dir, self.files[self.index])
                current_image = Image.open(img_path)
            except:
                pass
        
        # Linke Seite: Einstellungen
        settings_frame = ttk.Frame(crop_frame)
        settings_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        ttk.Label(settings_frame, text="Crop-Out Koordinaten:", font=("TkDefaultFont", 10, "bold")).pack(anchor='w', padx=5, pady=(10, 5))
        
        # Koordinaten-Eingabefelder
        coords_frame = ttk.Frame(settings_frame)
        coords_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # X-Koordinate
        x_frame = ttk.Frame(coords_frame)
        x_frame.pack(fill=tk.X, pady=2)
        ttk.Label(x_frame, text="X:", width=8).pack(side=tk.LEFT)
        x_var = tk.StringVar(value=str(self.json_config.get('crop_coordinates', {}).get('x', 18)))
        x_entry = ttk.Entry(x_frame, textvariable=x_var, width=8)
        x_entry.pack(side=tk.LEFT, padx=(5, 0))
        
        # Y-Koordinate
        y_frame = ttk.Frame(coords_frame)
        y_frame.pack(fill=tk.X, pady=2)
        ttk.Label(y_frame, text="Y:", width=8).pack(side=tk.LEFT)
        y_var = tk.StringVar(value=str(self.json_config.get('crop_coordinates', {}).get('y', 65)))
        y_entry = ttk.Entry(y_frame, textvariable=y_var, width=8)
        y_entry.pack(side=tk.LEFT, padx=(5, 0))
        
        # Breite
        w_frame = ttk.Frame(coords_frame)
        w_frame.pack(fill=tk.X, pady=2)
        ttk.Label(w_frame, text="Breite:", width=8).pack(side=tk.LEFT)
        w_var = tk.StringVar(value=str(self.json_config.get('crop_coordinates', {}).get('w', 80)))
        w_entry = ttk.Entry(w_frame, textvariable=w_var, width=8)
        w_entry.pack(side=tk.LEFT, padx=(5, 0))
        
        # Höhe
        h_frame = ttk.Frame(coords_frame)
        h_frame.pack(fill=tk.X, pady=2)
        ttk.Label(h_frame, text="Höhe:", width=8).pack(side=tk.LEFT)
        h_var = tk.StringVar(value=str(self.json_config.get('crop_coordinates', {}).get('h', 40)))
        h_entry = ttk.Entry(h_frame, textvariable=h_var, width=8)
        h_entry.pack(side=tk.LEFT, padx=(5, 0))
        
        # Vorschau-Button
        preview_button = ttk.Button(settings_frame, text="Vorschau aktualisieren")
        preview_button.pack(pady=10)
        
        # Rechte Seite: Vorschau
        preview_frame = ttk.LabelFrame(crop_frame, text="Vorschau")
        preview_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # Canvas für Vorschau
        preview_canvas = tk.Canvas(preview_frame, bg='white', width=400, height=300)
        preview_canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        def update_preview():
            """Aktualisiert die Vorschau mit den aktuellen Koordinaten"""
            if current_image is None:
                preview_canvas.delete("all")
                preview_canvas.create_text(200, 150, text="Kein Bild geladen", fill="gray")
                return
            
            try:
                x = int(x_var.get())
                y = int(y_var.get())
                w = int(w_var.get())
                h = int(h_var.get())
                
                # Bild für Vorschau skalieren
                display_img = current_image.copy()
                display_img.thumbnail((THUMBNAIL_DISPLAY_WIDTH, THUMBNAIL_DISPLAY_HEIGHT), Image.Resampling.LANCZOS)
                
                # Skalierungsfaktor berechnen
                scale_x = display_img.width / current_image.width
                scale_y = display_img.height / current_image.height
                
                # Skalierte Koordinaten
                scaled_x = int(x * scale_x)
                scaled_y = int(y * scale_y)
                scaled_w = int(w * scale_x)
                scaled_h = int(h * scale_y)
                
                # Bild anzeigen
                photo = ImageTk.PhotoImage(display_img)
                preview_canvas.delete("all")
                preview_canvas.create_image(200, 150, image=photo, anchor=tk.CENTER)
                preview_canvas.image = photo  # Referenz halten
                
                # Rechteck für Crop-Bereich zeichnen
                preview_canvas.create_rectangle(
                    scaled_x, scaled_y, 
                    scaled_x + scaled_w, scaled_y + scaled_h,
                    outline="red", width=2
                )
                
                # Koordinaten anzeigen
                preview_canvas.create_text(
                    scaled_x + scaled_w//2, scaled_y - 10,
                    text=f"X:{x}, Y:{y}, W:{w}, H:{h}",
                    fill="red", font=("TkDefaultFont", 8, "bold")
                )
                
            except ValueError:
                preview_canvas.delete("all")
                preview_canvas.create_text(200, 150, text="Ungültige Koordinaten", fill="red")
            except Exception as e:
                preview_canvas.delete("all")
                preview_canvas.create_text(200, 150, text=f"Fehler: {e}", fill="red")
        
        # Initiale Vorschau
        update_preview()
        
        # Vorschau-Button konfigurieren
        preview_button.config(command=update_preview)
        
        # Live-Updates bei Änderungen
        for var in [x_var, y_var, w_var, h_var]:
            var.trace('w', lambda *args: update_preview())

        # Tab für Spracheinstellungen
        sprache_frame = ttk.Frame(notebook)
        notebook.add(sprache_frame, text="Spracheinstellungen")
        ttk.Label(sprache_frame, text="Globale Sprache für die Anwendung:").pack(anchor='w', padx=5, pady=(10,0))
        global_language_var = tk.StringVar(value=self.json_config.get('current_language', 'de'))
        global_language_combo = ttk.Combobox(sprache_frame, textvariable=global_language_var, values=["de", "en"], state="readonly", width=8)
        global_language_combo.pack(anchor='w', padx=5, pady=(0,10))
        ttk.Label(sprache_frame, text="Diese Einstellung bestimmt die Sprache der gesamten Oberfläche und der Kategorien.").pack(anchor='w', padx=5, pady=(0,10))

        # Tab für Kürzel-Tabelle
        kurzel_frame = ttk.Frame(notebook)
        notebook.add(kurzel_frame, text="Kürzel-Tabelle")
        
        # Kürzel-Tabelle erstellen
        self.create_kurzel_table(kurzel_frame)

        # Tab für Schadenskategorien
        damage_frame = ttk.Frame(notebook)
        notebook.add(damage_frame, text="Schadenskategorien")
        self.create_damage_table(damage_frame)
        
        # Tab für Bildart-Kategorien
        imagetype_frame = ttk.Frame(notebook)
        notebook.add(imagetype_frame, text="Bildart-Kategorien")
        self.create_imagetype_table(imagetype_frame)
        
        # Tab für Bildqualitäts-Optionen
        quality_frame = ttk.Frame(notebook)
        notebook.add(quality_frame, text="Bildqualitäts-Optionen")
        self.create_quality_table(quality_frame)
        
        # Tab für Alternative Kürzel
        alternative_frame = ttk.Frame(notebook)
        notebook.add(alternative_frame, text="Alternative Kürzel")
        self.create_alternative_kurzel_table(alternative_frame)


        def on_save():
            try:

                # Crop-Out Koordinaten speichern
                try:
                    crop_coords = {
                        'x': int(x_var.get()),
                        'y': int(y_var.get()),
                        'w': int(w_var.get()),
                        'h': int(h_var.get())
                    }
                    self.json_config['crop_coordinates'] = crop_coords
                except ValueError:
                    messagebox.showwarning("Warnung", "Ungültige Crop-Out Koordinaten. Verwende Standardwerte.", parent=win)
                    self.json_config['crop_coordinates'] = {'x': 10, 'y': 10, 'w': 60, 'h': 35}

                # Globale Sprache speichern
                self.json_config['current_language'] = global_language_var.get()

                # Kürzel speichern (aus der neuen Kürzel-Tabelle)
                kurzel_list = []
                kurzel_table = self.json_config.get('kurzel_table', {})
                for code, data in kurzel_table.items():
                    if data.get('active', True):
                        kurzel_list.append(code)
                self.json_config['valid_kurzel'] = sorted(kurzel_list)
                self.valid_kurzel = kurzel_list

                # Schadenskategorien (aus der neuen Tabelle)
                damage_categories = self.json_config.get('damage_categories', {})
                de_list = damage_categories.get('de', [])
                en_list = damage_categories.get('en', [])
                self.json_config['damage_categories'] = {'de': de_list, 'en': en_list}

                # Bildart-Kategorien (aus der neuen Tabelle)
                image_types = self.json_config.get('image_types', {})
                de_list = image_types.get('de', [])
                en_list = image_types.get('en', [])
                self.json_config['image_types'] = {'de': de_list, 'en': en_list}

                # Bildqualitäts-Optionen (aus der neuen Tabelle)
                image_quality_options = self.json_config.get('image_quality_options', {})
                de_list = image_quality_options.get('de', [])
                en_list = image_quality_options.get('en', [])
                self.json_config['image_quality_options'] = {'de': de_list, 'en': en_list}

                # Alternative Kürzel-Einstellungen speichern
                if hasattr(self, 'alternative_kurzel_enabled_var'):
                    self.json_config['ocr_settings']['alternative_kurzel_enabled'] = self.alternative_kurzel_enabled_var.get()

                if save_json_config(self.json_config):
                    messagebox.showinfo("Gespeichert", "Konfiguration wurde erfolgreich gespeichert.\nEinige Änderungen erfordern einen Neustart.", parent=win)
                    self.correct_combo['values'] = self.valid_kurzel
                    # Aktualisiere die Kürzel-Tabelle
                    if hasattr(self, 'refresh_kurzel_table'):
                        self.refresh_kurzel_table()
                    win.destroy()
                else:
                    messagebox.showerror("Fehler", "Konfiguration konnte nicht gespeichert werden.", parent=win)

            except Exception as e:
                messagebox.showerror("Fehler", f"Ein Fehler ist aufgetreten: {e}", parent=win)

        button_frame = ttk.Frame(win)
        button_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        ttk.Button(button_frame, text="Speichern", command=on_save).pack(side=tk.RIGHT)
        ttk.Button(button_frame, text="Abbrechen", command=win.destroy).pack(side=tk.RIGHT, padx=5)
    
    def create_kurzel_table(self, parent):
        """Erstellt die Kürzel-Tabelle mit zweisprachigen Einstellungen"""
        # Toolbar für Kürzel-Tabelle
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(toolbar, text="Neues Kürzel", command=self.add_new_kurzel).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="Kürzel bearbeiten", command=self.edit_selected_kurzel).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="Kürzel löschen", command=self.delete_selected_kurzel).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="Import CSV", command=self.import_kurzel_csv).pack(side=tk.LEFT, padx=(20, 5))
        ttk.Button(toolbar, text="Export CSV", command=self.export_kurzel_csv).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="Aktualisieren", command=self.refresh_kurzel_table).pack(side=tk.RIGHT)
        
        # Treeview für Kürzel-Tabelle
        columns = ('Kürzel', 'Name (DE)', 'Name (EN)', 'Kategorie', 'Bildart-Zuordnung', 'Beschreibung (DE)', 'Beschreibung (EN)', 'Aktiv')
        self.kurzel_tree = ttk.Treeview(parent, columns=columns, show='headings', height=15)
        
        # Spalten konfigurieren
        for col in columns:
            self.kurzel_tree.heading(col, text=col)
            if col == 'Kürzel':
                self.kurzel_tree.column(col, width=80)
            elif col in ['Name (DE)', 'Name (EN)']:
                self.kurzel_tree.column(col, width=150)
            elif col == 'Kategorie':
                self.kurzel_tree.column(col, width=100)
            elif col == 'Wellen-Zuordnung':
                self.kurzel_tree.column(col, width=120)
            elif col in ['Beschreibung (DE)', 'Beschreibung (EN)']:
                self.kurzel_tree.column(col, width=200)
            elif col == 'Aktiv':
                self.kurzel_tree.column(col, width=60)
        
        # Scrollbar für Treeview
        kurzel_scroll = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.kurzel_tree.yview)
        self.kurzel_tree.configure(yscrollcommand=kurzel_scroll.set)
        
        self.kurzel_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        kurzel_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Event-Binding
        self.kurzel_tree.bind('<Double-1>', self.edit_selected_kurzel)
        
        # Lade initiale Daten
        self.refresh_kurzel_table()
    def create_damage_table(self, parent):
        """Erstellt die Schadenskategorien-Tabelle"""
        # Toolbar
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(toolbar, text="Neue Kategorie", command=self.add_new_damage_category).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="Bearbeiten", command=self.edit_selected_damage_category).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="Löschen", command=self.delete_selected_damage_category).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="Import CSV", command=self.import_damage_csv).pack(side=tk.LEFT, padx=(20, 5))
        ttk.Button(toolbar, text="Export CSV", command=self.export_damage_csv).pack(side=tk.LEFT, padx=(0, 5))
        
        # Treeview für Schadenskategorien (separate DE/EN Spalten wie bei anderen Kategorien)
        columns = ('ID', 'Name (DE)', 'Name (EN)', 'Beschreibung (DE)', 'Beschreibung (EN)', 'Priorität')
        self.damage_tree = ttk.Treeview(parent, columns=columns, show='headings', height=10)
        
        for col in columns:
            self.damage_tree.heading(col, text=col)
            if col == 'ID':
                self.damage_tree.column(col, width=50)
            elif col in ['Name (DE)', 'Name (EN)']:
                self.damage_tree.column(col, width=180)
            elif col in ['Beschreibung (DE)', 'Beschreibung (EN)']:
                self.damage_tree.column(col, width=200)
            elif col == 'Priorität':
                self.damage_tree.column(col, width=80)
        
        damage_scroll = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.damage_tree.yview)
        self.damage_tree.configure(yscrollcommand=damage_scroll.set)
        
        self.damage_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        damage_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.damage_tree.bind('<Double-1>', self.edit_selected_damage_category)
        self.refresh_damage_table()
    
    def create_imagetype_table(self, parent):
        """Erstellt die Bildart-Kategorien-Tabelle"""
        # Toolbar
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(toolbar, text="Neue Bildart", command=self.add_new_imagetype).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="Bearbeiten", command=self.edit_selected_imagetype).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="Löschen", command=self.delete_selected_imagetype).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="Import CSV", command=self.import_imagetype_csv).pack(side=tk.LEFT, padx=(20, 5))
        ttk.Button(toolbar, text="Export CSV", command=self.export_imagetype_csv).pack(side=tk.LEFT, padx=(0, 5))
        
        # Treeview für Bildart-Kategorien (separate DE/EN Spalten)
        columns = ('ID', 'Name (DE)', 'Name (EN)', 'Beschreibung (DE)', 'Beschreibung (EN)', 'Icon')
        self.imagetype_tree = ttk.Treeview(parent, columns=columns, show='headings', height=10)
        
        for col in columns:
            self.imagetype_tree.heading(col, text=col)
            if col == 'ID':
                self.imagetype_tree.column(col, width=50)
            elif col in ['Name (DE)', 'Name (EN)']:
                self.imagetype_tree.column(col, width=180)
            elif col in ['Beschreibung (DE)', 'Beschreibung (EN)']:
                self.imagetype_tree.column(col, width=200)
            elif col == 'Icon':
                self.imagetype_tree.column(col, width=100)
        
        imagetype_scroll = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.imagetype_tree.yview)
        self.imagetype_tree.configure(yscrollcommand=imagetype_scroll.set)
        
        self.imagetype_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        imagetype_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.imagetype_tree.bind('<Double-1>', self.edit_selected_imagetype)
        self.refresh_imagetype_table()
    
    def create_quality_table(self, parent):
        """Erstellt die Bildqualitäts-Optionen-Tabelle"""
        # Toolbar
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(toolbar, text="Neue Qualität", command=self.add_new_quality).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="Bearbeiten", command=self.edit_selected_quality).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="Löschen", command=self.delete_selected_quality).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="Import CSV", command=self.import_quality_csv).pack(side=tk.LEFT, padx=(20, 5))
        ttk.Button(toolbar, text="Export CSV", command=self.export_quality_csv).pack(side=tk.LEFT, padx=(0, 5))
        
        # Treeview für Bildqualitäts-Optionen (separate DE/EN Spalten)
        columns = ('ID', 'Name (DE)', 'Name (EN)', 'Beschreibung (DE)', 'Beschreibung (EN)', 'Wert')
        self.quality_tree = ttk.Treeview(parent, columns=columns, show='headings', height=10)
        
        for col in columns:
            self.quality_tree.heading(col, text=col)
            if col == 'ID':
                self.quality_tree.column(col, width=50)
            elif col in ['Name (DE)', 'Name (EN)']:
                self.quality_tree.column(col, width=180)
            elif col in ['Beschreibung (DE)', 'Beschreibung (EN)']:
                self.quality_tree.column(col, width=200)
            elif col == 'Wert':
                self.quality_tree.column(col, width=80)
        
        quality_scroll = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.quality_tree.yview)
        self.quality_tree.configure(yscrollcommand=quality_scroll.set)
        
        self.quality_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        quality_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.quality_tree.bind('<Double-1>', self.edit_selected_quality)
        self.refresh_quality_table()
    
    def create_alternative_kurzel_table(self, parent):
        """Erstellt die Alternative Kürzel-Tabelle"""
        # Info-Frame
        info_frame = ttk.LabelFrame(parent, text="Information")
        info_frame.pack(fill=tk.X, padx=5, pady=5)
        
        info_text = """Hier können Sie alternative Schreibweisen für Kürzel definieren, die bei der OCR-Erkennung automatisch korrigiert werden.
Beispiele: 'hss' → 'HSS', 'pl2-1' → 'PL2-1', etc.
Die Korrektur funktioniert case-insensitive und unterstützt auch ähnliche Varianten."""
        
        ttk.Label(info_frame, text=info_text, wraplength=600, justify=tk.LEFT).pack(padx=5, pady=5)
        
        # Einstellungen-Frame
        settings_frame = ttk.LabelFrame(parent, text="Einstellungen")
        settings_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Checkbox für Aktivierung
        self.alternative_kurzel_enabled_var = tk.BooleanVar(
            value=self.json_config.get('ocr_settings', {}).get('alternative_kurzel_enabled', True)
        )
        ttk.Checkbutton(settings_frame, text="Alternative Kürzel-Korrektur aktivieren", 
                       variable=self.alternative_kurzel_enabled_var).pack(anchor='w', padx=5, pady=5)
        
        # Toolbar
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(toolbar, text="Neues alternatives Kürzel", command=self.add_alternative_kurzel).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="Bearbeiten", command=self.edit_alternative_kurzel).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="Löschen", command=self.delete_alternative_kurzel).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="Alle aus gültigen Kürzeln generieren", command=self.generate_alternative_kurzel).pack(side=tk.LEFT, padx=(20, 5))
        ttk.Button(toolbar, text="Import CSV", command=self.import_alternative_csv).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(toolbar, text="Export CSV", command=self.export_alternative_csv).pack(side=tk.LEFT, padx=(0, 5))
        
        # Treeview für Alternative Kürzel
        columns = ('Alternatives Kürzel', 'Korrigiertes Kürzel', 'Title Case', 'Ohne Minus', 'Aktiv')
        self.alternative_tree = ttk.Treeview(parent, columns=columns, show='headings', height=15)
        
        for col in columns:
            self.alternative_tree.heading(col, text=col)
            if col == 'Aktiv':
                self.alternative_tree.column(col, width=60)
            else:
                self.alternative_tree.column(col, width=150)
        
        alternative_scroll = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.alternative_tree.yview)
        self.alternative_tree.configure(yscrollcommand=alternative_scroll.set)
        
        self.alternative_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        alternative_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.alternative_tree.bind('<Double-1>', self.edit_alternative_kurzel)
        self.refresh_alternative_kurzel_table()
    
    # Kürzel-Tabelle Methoden
    def refresh_kurzel_table(self):
        """Aktualisiert die Kürzel-Tabelle"""
        try:
            # Überprüfe ob das Fenster noch existiert
            if not hasattr(self, 'kurzel_tree') or self.kurzel_tree is None:
                logger.warning("Kürzel-Tabelle nicht verfügbar - Fenster möglicherweise geschlossen")
                return
            
            # Lösche alle Einträge
            for item in self.kurzel_tree.get_children():
                self.kurzel_tree.delete(item)
            
            # Lade Kürzel aus der Konfiguration
            kurzel_table = self.json_config.get('kurzel_table', {})
            
            logger.info(f"Kürzel-Tabelle wird aktualisiert - Anzahl Einträge: {len(kurzel_table)}")
            
            # Füge alle Kürzel hinzu (nicht nur die aktiven)
            for kurzel_code, kurzel_data in sorted(kurzel_table.items()):
                values = (
                    kurzel_code,
                    kurzel_data.get('name_de', ''),
                    kurzel_data.get('name_en', ''),
                    kurzel_data.get('category', 'Unbekannt'),
                    kurzel_data.get('image_type_assignment', 'Nicht zugeordnet'),
                    kurzel_data.get('description_de', ''),
                    kurzel_data.get('description_en', ''),
                    'Ja' if kurzel_data.get('active', True) else 'Nein'
                )
                
                self.kurzel_tree.insert('', 'end', values=values)
            
            logger.info(f"Kürzel-Tabelle aktualisiert - Einträge in Tabelle: {len(self.kurzel_tree.get_children())}")
            
        except Exception as e:
            logger.error(f"Fehler beim Aktualisieren der Kürzel-Tabelle: {e}")
            messagebox.showerror("Fehler", f"Fehler beim Aktualisieren der Kürzel-Tabelle: {e}")
    
    def add_new_kurzel(self):
        """Öffnet Dialog zum Hinzufügen eines neuen Kürzels"""
        self.edit_kurzel_dialog(None)
    
    def edit_selected_kurzel(self, event=None):
        """Öffnet Dialog zum Bearbeiten des ausgewählten Kürzels"""
        selection = self.kurzel_tree.selection()
        if not selection:
            return
        
        item = selection[0]
        kurzel_code = self.kurzel_tree.item(item)['values'][0]
        self.edit_kurzel_dialog(kurzel_code)
    
    def delete_selected_kurzel(self):
        """Löscht das ausgewählte Kürzel"""
        selection = self.kurzel_tree.selection()
        if not selection:
            return
        
        item = selection[0]
        kurzel_code = self.kurzel_tree.item(item)['values'][0]
        
        if messagebox.askyesno("Bestätigen", f"Möchten Sie das Kürzel '{kurzel_code}' wirklich löschen?"):
            # Entferne aus valid_kurzel Liste
            valid_kurzel = self.json_config.get('valid_kurzel', [])
            if kurzel_code in valid_kurzel:
                valid_kurzel.remove(kurzel_code)
                self.json_config['valid_kurzel'] = valid_kurzel
            
            # Entferne aus Kürzel-Tabelle
            kurzel_table = self.json_config.get('kurzel_table', {})
            if kurzel_code in kurzel_table:
                del kurzel_table[kurzel_code]
                self.json_config['kurzel_table'] = kurzel_table
            
            self.refresh_kurzel_table()
    
    def edit_kurzel_dialog(self, kurzel_code=None):
        """Dialog zum Bearbeiten/Hinzufügen von Kürzeln"""
        dialog = tk.Toplevel(self)
        dialog.title("Kürzel bearbeiten" if kurzel_code else "Neues Kürzel")
        dialog.geometry("500x600")
        dialog.transient(self)
        dialog.grab_set()
        
        # Formular erstellen
        form_frame = ttk.Frame(dialog, padding="10")
        form_frame.pack(fill=tk.BOTH, expand=True)
        
        # Kürzel-Code
        ttk.Label(form_frame, text="Kürzel-Code:").pack(anchor='w')
        code_var = tk.StringVar(value=kurzel_code or '')
        code_entry = ttk.Entry(form_frame, textvariable=code_var, width=20)
        code_entry.pack(fill=tk.X, pady=(0, 10))
        
        # Name (DE)
        ttk.Label(form_frame, text="Name (Deutsch):").pack(anchor='w')
        name_de_var = tk.StringVar()
        name_de_entry = ttk.Entry(form_frame, textvariable=name_de_var, width=50)
        name_de_entry.pack(fill=tk.X, pady=(0, 10))
        
        # Name (EN)
        ttk.Label(form_frame, text="Name (English):").pack(anchor='w')
        name_en_var = tk.StringVar()
        name_en_entry = ttk.Entry(form_frame, textvariable=name_en_var, width=50)
        name_en_entry.pack(fill=tk.X, pady=(0, 10))
        
        # Kategorie
        ttk.Label(form_frame, text="Kategorie:").pack(anchor='w')
        category_var = tk.StringVar()
        category_combo = ttk.Combobox(form_frame, textvariable=category_var, 
                                    values=['Schmierung', 'Getriebe', 'Lager', 'Dichtung', 'Sonstiges'])
        category_combo.pack(fill=tk.X, pady=(0, 10))
        
        # Bildart-Zuordnung
        ttk.Label(form_frame, text="Bildart-Zuordnung (Komma-getrennt):").pack(anchor='w')
        image_type_var = tk.StringVar()
        image_type_combo = ttk.Combobox(form_frame, textvariable=image_type_var, 
                                values=['Nicht zugeordnet'] + IMAGE_TYPES)
        image_type_combo.pack(fill=tk.X, pady=(0, 5))
        
        # Hinweis für Benutzer
        hint_label = ttk.Label(form_frame, text="Verfügbare Optionen: " + ", ".join(IMAGE_TYPES), 
                              font=('Arial', 8), foreground='gray')
        hint_label.pack(anchor='w', pady=(0, 10))
        
        # Beschreibung (DE)
        ttk.Label(form_frame, text="Beschreibung (Deutsch):").pack(anchor='w')
        desc_de_text = tk.Text(form_frame, height=4, wrap=tk.WORD)
        desc_de_text.pack(fill=tk.X, pady=(0, 10))
        
        # Beschreibung (EN)
        ttk.Label(form_frame, text="Beschreibung (English):").pack(anchor='w')
        desc_en_text = tk.Text(form_frame, height=4, wrap=tk.WORD)
        desc_en_text.pack(fill=tk.X, pady=(0, 10))
        
        # Aktiv-Checkbox
        active_var = tk.BooleanVar(value=True)
        active_check = ttk.Checkbutton(form_frame, text="Aktiv", variable=active_var)
        active_check.pack(anchor='w', pady=(0, 10))
        
        # Lade bestehende Daten
        if kurzel_code:
            kurzel_table = self.json_config.get('kurzel_table', {})
            kurzel_data = kurzel_table.get(kurzel_code, {})
            
            name_de_var.set(kurzel_data.get('name_de', ''))
            name_en_var.set(kurzel_data.get('name_en', ''))
            category_var.set(kurzel_data.get('category', ''))
            image_type_var.set(kurzel_data.get('image_type_assignment', 'Nicht zugeordnet'))
            desc_de_text.insert('1.0', kurzel_data.get('description_de', ''))
            desc_en_text.insert('1.0', kurzel_data.get('description_en', ''))
            active_var.set(kurzel_data.get('active', True))
        
        def save_kurzel():
            new_code = code_var.get().strip().upper()
            if not new_code:
                messagebox.showerror("Fehler", "Kürzel-Code darf nicht leer sein!")
                return
            
            # Speichere Kürzel-Daten
            kurzel_table = self.json_config.get('kurzel_table', {})
            kurzel_data = {
                'name_de': name_de_var.get().strip(),
                'name_en': name_en_var.get().strip(),
                'category': category_var.get().strip(),
                'image_type_assignment': image_type_var.get().strip(),
                'description_de': desc_de_text.get('1.0', tk.END).strip(),
                'description_en': desc_en_text.get('1.0', tk.END).strip(),
                'active': active_var.get()
            }
            
            kurzel_table[new_code] = kurzel_data
            self.json_config['kurzel_table'] = kurzel_table
            
            # Füge zu valid_kurzel hinzu, falls nicht vorhanden
            valid_kurzel = self.json_config.get('valid_kurzel', [])
            if new_code not in valid_kurzel and active_var.get():
                valid_kurzel.append(new_code)
                self.json_config['valid_kurzel'] = valid_kurzel
            
            dialog.destroy()
            self.refresh_kurzel_table()
        
        # Buttons
        button_frame = ttk.Frame(form_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(button_frame, text="Speichern", command=save_kurzel).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(button_frame, text="Abbrechen", command=dialog.destroy).pack(side=tk.RIGHT)

    def export_kurzel_csv(self):
        """Exportiert die Kürzel-Tabelle als CSV (deutsches Excel-Format mit Semikolon, UTF-8-BOM)."""
        try:
            file_path = filedialog.asksaveasfilename(
                title="Kürzel-Tabelle exportieren",
                defaultextension=".csv",
                filetypes=[("CSV-Dateien", "*.csv"), ("Alle Dateien", "*.*")],
                initialfile="kurzel_tabelle.csv"
            )
            if not file_path:
                return
            kurzel_table = self.json_config.get('kurzel_table', {})
            fieldnames = [
                'kurzel_code', 'name_de', 'name_en', 'category', 'image_type_assignment',
                'description_de', 'description_en', 'active'
            ]
            with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=';')
                writer.writeheader()
                
                # Exportiere alle Einträge mit Inhalt in der ersten Spalte (kurzel_code)
                for code, data in sorted(kurzel_table.items()):
                    # Nur exportieren wenn kurzel_code (erste Spalte) Inhalt hat
                    if code and code.strip():
                        row = {
                            'kurzel_code': code,
                            'name_de': data.get('name_de', ''),
                            'name_en': data.get('name_en', ''),
                            'category': data.get('category', ''),
                            'image_type_assignment': data.get('image_type_assignment', ''),
                            'description_de': data.get('description_de', ''),
                            'description_en': data.get('description_en', ''),
                            'active': '1' if data.get('active', True) else '0'
                        }
                        writer.writerow(row)
            messagebox.showinfo("Export", f"CSV wurde exportiert:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Fehler", f"CSV-Export fehlgeschlagen: {e}")

    def import_kurzel_csv(self):
        """Importiert die Kürzel-Tabelle aus CSV mit automatischer Format-Erkennung."""
        try:
            file_path = filedialog.askopenfilename(
                title="Kürzel-Tabelle importieren",
                filetypes=[("CSV-Dateien", "*.csv"), ("Alle Dateien", "*.*")]
            )
            if not file_path:
                return
            
            imported_count = 0
            kurzel_table = self.json_config.get('kurzel_table', {})
            valid_kurzel = set(self.json_config.get('valid_kurzel', []))
            
            with safe_csv_open(file_path, 'r') as f:
                # Erste Zeile lesen um Format zu erkennen
                first_line = f.readline().strip()
                f.seek(0)  # Zurück zum Anfang
                
                write_detailed_log("info", "CSV-Format erkannt", f"Erste Zeile: {first_line[:100]}...")
                
                # Prüfe verschiedene Trennzeichen
                delimiter = ';'
                if ',' in first_line and ';' not in first_line:
                    delimiter = ','
                elif '\t' in first_line and ';' not in first_line and ',' not in first_line:
                    delimiter = '\t'
                
                write_detailed_log("info", "Trennzeichen erkannt", f"Verwende: '{delimiter}'")
                
                # Prüfe ob es sich um eine einzige lange Zeile handelt (wie im Bild gezeigt)
                if len(first_line) > 200 and delimiter not in first_line:
                    write_detailed_log("info", "Spezielles Format erkannt", "Verarbeite als einzelne Zeile")
                    self._import_single_line_format(f, kurzel_table, valid_kurzel)
                    imported_count = len(kurzel_table) - len(self.json_config.get('kurzel_table', {}))
                else:
                    reader = csv.DictReader(f, delimiter=delimiter)
                    imported_count = self._import_csv_rows(reader, kurzel_table, valid_kurzel)
                
                self.json_config['kurzel_table'] = kurzel_table
                self.json_config['valid_kurzel'] = sorted(valid_kurzel)
                self.config_manager.save_config()
            
            # Aktualisiere die Tabelle
            try:
                self.refresh_kurzel_table()
                write_detailed_log("info", "Kürzel-Tabelle nach Import aktualisiert", f"Einträge: {imported_count}")
            except Exception as refresh_error:
                write_detailed_log("error", "Fehler beim Aktualisieren der Tabelle nach Import", str(refresh_error))
            
            # Erfolgsmeldung
            messagebox.showinfo("Import erfolgreich", 
                              f"CSV wurde erfolgreich importiert:\n{file_path}\n\n"
                              f"Importierte Einträge: {imported_count}\n"
                              f"Aktive Kürzel: {len([k for k, v in kurzel_table.items() if v.get('active', True)])}")
            
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            write_detailed_log("error", "CSV-Import fehlgeschlagen", f"Datei: {file_path}", str(e))
            messagebox.showerror("Fehler", f"CSV-Import fehlgeschlagen: {e}\n\nDetails:\n{error_details}")
    
    def _extract_field(self, row, possible_names):
        """Extrahiert ein Feld aus einer CSV-Zeile mit verschiedenen möglichen Spaltennamen."""
        for name in possible_names:
            if name in row and row[name]:
                return row[name].strip()
        return ''
    
    def _extract_active_field(self, row):
        """Extrahiert den Active-Status aus einer CSV-Zeile."""
        for field_name in ['active', 'aktiv', 'Active', 'Aktiv']:
            if field_name in row and row[field_name]:
                value = row[field_name].strip().lower()
                return value in ['1', 'true', 'ja', 'yes', 'aktiv', 'active']
        return True  # Standard: aktiv
    
    def _import_csv_rows(self, reader, kurzel_table, valid_kurzel):
        """Importiert CSV-Zeilen im Standard-Format."""
        imported_count = 0
        
        # Debug: Zeige verfügbare Spalten
        available_columns = reader.fieldnames
        write_detailed_log("info", "Verfügbare Spalten", f"Spalten: {available_columns}")
        
        for row_num, row in enumerate(reader, 1):
            # Debug: Zeige erste paar Zeilen
            if row_num <= 3:
                write_detailed_log("info", f"Zeile {row_num}", f"Inhalt: {dict(row)}")
            
            # Versuche verschiedene Spaltennamen für den Code
            code = None
            for code_field in ['kurzel_code', 'code', 'kurzel', 'Kürzel', 'Code']:
                if code_field in row and row[code_field]:
                    code = row[code_field].strip().upper()
                    break
            
                if not code:
                    logger.warning(f"Zeile {row_num} übersprungen - Kein Code gefunden")
                    continue
            
                # Extrahiere Daten mit flexiblen Spaltennamen
                data = {
                    'name_de': self._extract_field(row, ['name_de', 'name_deutsch', 'deutsch', 'Name DE']),
                    'name_en': self._extract_field(row, ['name_en', 'name_english', 'english', 'Name EN']),
                    'category': self._extract_field(row, ['category', 'kategorie', 'Category', 'Kategorie']),
                    'image_type_assignment': self._extract_field(row, ['image_type_assignment', 'image_type', 'bildart', 'Bildart']),
                    'description_de': self._extract_field(row, ['description_de', 'beschreibung_de', 'Beschreibung DE']),
                    'description_en': self._extract_field(row, ['description_en', 'beschreibung_en', 'Beschreibung EN']),
                    'active': self._extract_active_field(row)
                }
                
                kurzel_table[code] = data
                if data['active']:
                    valid_kurzel.add(code)
                elif code in valid_kurzel:
                    valid_kurzel.remove(code)
                imported_count += 1
        
        return imported_count
    
    def _import_single_line_format(self, f, kurzel_table, valid_kurzel):
        """Importiert das spezielle Ein-Zeilen-Format (wie im Bild gezeigt)."""
        try:
            content = f.read()
            write_detailed_log("info", "Ein-Zeilen-Format", f"Inhalt-Länge: {len(content)}")
            
            # Versuche verschiedene Parsing-Strategien
            lines = content.split('\n')
            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line:
                    continue
                
                # Versuche Kürzel zu extrahieren (erste 3-5 Zeichen)
                if len(line) >= 3:
                    # Suche nach Mustern wie "HSS", "LSS", "PLC2", etc.
                    import re
                    patterns = [
                        r'^([A-Z]{2,5}[A-Z0-9]*)',  # HSS, LSS, PLC2GR, etc.
                        r'^([A-Z]+[0-9]+)',          # RG2, SUN2, etc.
                        r'^([A-Z]+[0-9]+-[0-9]+)',   # PL2-1, PLB2G-1, etc.
                    ]
                    
                    code = None
                    for pattern in patterns:
                        match = re.match(pattern, line)
                        if match:
                            code = match.group(1)
                            break
                    
                    if code:
                        # Extrahiere Beschreibung (alles nach dem Code)
                        description = line[len(code):].strip()
                        if description.startswith('–') or description.startswith('-'):
                            description = description[1:].strip()
                        
                        data = {
                            'name_de': description,
                            'name_en': description,
                            'category': 'Unbekannt',
                            'image_type_assignment': 'Nicht zugeordnet',
                            'description_de': description,
                            'description_en': description,
                            'active': True
                        }
                        
                        kurzel_table[code] = data
                        valid_kurzel.add(code)
                        write_detailed_log("info", f"Kürzel extrahiert", f"Code: {code}, Beschreibung: {description[:50]}...")
            
            write_detailed_log("info", "Ein-Zeilen-Format verarbeitet", f"Gefundene Kürzel: {len(kurzel_table)}")
            
        except Exception as e:
            write_detailed_log("error", "Fehler beim Verarbeiten des Ein-Zeilen-Formats", str(e))
    
    # Tabellen-Refresh-Methoden für andere Tabellen
    def refresh_damage_table(self):
        """Aktualisiert die Schadenskategorien-Tabelle"""
        for item in self.damage_tree.get_children():
            self.damage_tree.delete(item)
        
        damage_categories = self.json_config.get('damage_categories', {})
        de_list = damage_categories.get('de', [])
        en_list = damage_categories.get('en', [])
        max_len = max(len(de_list), len(en_list))
        for i in range(max_len):
            name_de = de_list[i] if i < len(de_list) else ''
            name_en = en_list[i] if i < len(en_list) else ''
            values = (
                i + 1,
                name_de,
                name_en,
                '',  # Beschreibung (DE)
                '',  # Beschreibung (EN)
                i + 1  # Priorität
            )
            self.damage_tree.insert('', 'end', values=values)

    # CSV Import/Export für Schadenskategorien
    def export_damage_csv(self):
        try:
            file_path = filedialog.asksaveasfilename(
                title="Schadenskategorien exportieren",
                defaultextension=".csv",
                filetypes=[("CSV-Dateien", "*.csv"), ("Alle Dateien", "*.*")],
                initialfile="schadenskategorien.csv"
            )
            if not file_path:
                return
            damage = self.json_config.get('damage_categories', {})
            de_list = damage.get('de', [])
            en_list = damage.get('en', [])
            with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(['id', 'name_de', 'name_en', 'beschreibung_de', 'beschreibung_en', 'prioritaet'])
                
                # Exportiere alle Zeilen mit Inhalt in der ersten Spalte (name_de)
                max_len = max(len(de_list), len(en_list))
                for i in range(max_len):
                    name_de = de_list[i] if i < len(de_list) else ''
                    name_en = en_list[i] if i < len(en_list) else ''
                    
                    # Nur exportieren wenn name_de (erste Spalte) Inhalt hat
                    if name_de.strip():
                        writer.writerow([i+1,
                                         name_de,
                                         name_en,
                                         '', '',  # Beschreibungen leer lassen
                                         i+1])
            messagebox.showinfo("Export", f"CSV wurde exportiert:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Fehler", f"CSV-Export fehlgeschlagen: {e}")

    def import_damage_csv(self):
        try:
            file_path = filedialog.askopenfilename(
                title="Schadenskategorien importieren",
                filetypes=[("CSV-Dateien", "*.csv"), ("Alle Dateien", "*.*")]
            )
            if not file_path:
                return
            de_list, en_list = [], []
            with safe_csv_open(file_path, 'r') as f:
                reader = csv.DictReader(f, delimiter=';')
                rows = list(reader)
                rows.sort(key=lambda r: int((r.get('id') or '0').strip() or 0))
                for row in rows:
                    de_list.append((row.get('name_de') or '').strip())
                    en_list.append((row.get('name_en') or '').strip())
            self.json_config.setdefault('damage_categories', {})['de'] = de_list
            self.json_config['damage_categories']['en'] = en_list
            self.refresh_damage_table()
            messagebox.showinfo("Import", f"CSV wurde importiert:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Fehler", f"CSV-Import fehlgeschlagen: {e}")
    
    def refresh_imagetype_table(self):
        """Aktualisiert die Bildart-Kategorien-Tabelle"""
        for item in self.imagetype_tree.get_children():
            self.imagetype_tree.delete(item)
        
        image_types = self.json_config.get('image_types', {})
        de_types = image_types.get('de', [])
        en_types = image_types.get('en', [])
        max_len = max(len(de_types), len(en_types))
        for i in range(max_len):
            name_de = de_types[i] if i < len(de_types) else ''
            name_en = en_types[i] if i < len(en_types) else ''
            values = (
                i + 1,
                name_de,
                name_en,
                '',  # Beschreibung DE (optional)
                '',  # Beschreibung EN (optional)
                '📷'
            )
            self.imagetype_tree.insert('', 'end', values=values)

    # CSV Import/Export für Bildart
    def export_imagetype_csv(self):
        try:
            file_path = filedialog.asksaveasfilename(
                title="Bildart-Kategorien exportieren",
                defaultextension=".csv",
                filetypes=[("CSV-Dateien", "*.csv"), ("Alle Dateien", "*.*")],
                initialfile="bildart_kategorien.csv"
            )
            if not file_path:
                return
            image_types = self.json_config.get('image_types', {})
            de_list = image_types.get('de', [])
            en_list = image_types.get('en', [])
            with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(['id', 'name_de', 'name_en', 'beschreibung_de', 'beschreibung_en', 'icon'])
                
                # Exportiere alle Zeilen mit Inhalt in der ersten Spalte (name_de)
                max_len = max(len(de_list), len(en_list))
                for i in range(max_len):
                    name_de = de_list[i] if i < len(de_list) else ''
                    name_en = en_list[i] if i < len(en_list) else ''
                    
                    # Nur exportieren wenn name_de (erste Spalte) Inhalt hat
                    if name_de.strip():
                        writer.writerow([i+1,
                                         name_de,
                                         name_en,
                                         '', '',  # Beschreibungen leer lassen
                                         ''])  # Icon leer lassen
            messagebox.showinfo("Export", f"CSV wurde exportiert:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Fehler", f"CSV-Export fehlgeschlagen: {e}")

    def import_imagetype_csv(self):
        try:
            file_path = filedialog.askopenfilename(
                title="Bildart-Kategorien importieren",
                filetypes=[("CSV-Dateien", "*.csv"), ("Alle Dateien", "*.*")]
            )
            if not file_path:
                return
            de_list, en_list = [], []
            with safe_csv_open(file_path, 'r') as f:
                reader = csv.DictReader(f, delimiter=';')
                rows = list(reader)
                rows.sort(key=lambda r: int((r.get('id') or '0').strip() or 0))
                for row in rows:
                    de_list.append((row.get('name_de') or '').strip())
                    en_list.append((row.get('name_en') or '').strip())
            self.json_config.setdefault('image_types', {})['de'] = de_list
            self.json_config['image_types']['en'] = en_list
            self.refresh_imagetype_table()
            messagebox.showinfo("Import", f"CSV wurde importiert:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Fehler", f"CSV-Import fehlgeschlagen: {e}")
    
    def refresh_quality_table(self):
        """Aktualisiert die Bildqualitäts-Optionen-Tabelle"""
        for item in self.quality_tree.get_children():
            self.quality_tree.delete(item)
        
        quality_options = self.json_config.get('image_quality_options', {})
        de_q = quality_options.get('de', [])
        en_q = quality_options.get('en', [])
        max_len = max(len(de_q), len(en_q))
        for i in range(max_len):
            name_de = de_q[i] if i < len(de_q) else ''
            name_en = en_q[i] if i < len(en_q) else ''
            values = (
                i + 1,
                name_de,
                name_en,
                '',  # Beschreibung DE (optional)
                '',  # Beschreibung EN (optional)
                i + 1
            )
            self.quality_tree.insert('', 'end', values=values)

    # CSV Import/Export für Bildqualitäts-Optionen
    def export_quality_csv(self):
        try:
            file_path = filedialog.asksaveasfilename(
                title="Bildqualitäts-Optionen exportieren",
                defaultextension=".csv",
                filetypes=[("CSV-Dateien", "*.csv"), ("Alle Dateien", "*.*")],
                initialfile="bildqualitaet_optionen.csv"
            )
            if not file_path:
                return
            q = self.json_config.get('image_quality_options', {})
            de_list = q.get('de', [])
            en_list = q.get('en', [])
            with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(['id', 'name_de', 'name_en', 'beschreibung_de', 'beschreibung_en', 'wert'])
                
                # Exportiere alle Zeilen mit Inhalt in der ersten Spalte (name_de)
                max_len = max(len(de_list), len(en_list))
                for i in range(max_len):
                    name_de = de_list[i] if i < len(de_list) else ''
                    name_en = en_list[i] if i < len(en_list) else ''
                    
                    # Nur exportieren wenn name_de (erste Spalte) Inhalt hat
                    if name_de.strip():
                        writer.writerow([i+1,
                                         name_de,
                                         name_en,
                                         '', '',  # Beschreibungen leer lassen
                                         i+1])  # Wert als Index
            messagebox.showinfo("Export", f"CSV wurde exportiert:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Fehler", f"CSV-Export fehlgeschlagen: {e}")
    
    # Alternative Kürzel Methoden
    def refresh_alternative_kurzel_table(self):
        """Aktualisiert die Alternative Kürzel-Tabelle"""
        try:
            if not hasattr(self, 'alternative_tree') or self.alternative_tree is None:
                return
            
            # Lösche alle Einträge
            for item in self.alternative_tree.get_children():
                self.alternative_tree.delete(item)
            
            # Lade alternative Kürzel aus der Konfiguration
            alternative_kurzel = self.json_config.get('alternative_kurzel', {})
            
            # Füge Einträge zur Tabelle hinzu
            for alt_kurzel, korrigiertes_kurzel in alternative_kurzel.items():
                # Erstelle Title Case Variante (erste Buchstaben groß)
                title_case = alt_kurzel.title()
                # Erstelle Variante ohne Minus
                ohne_minus = alt_kurzel.replace('-', '')
                self.alternative_tree.insert('', 'end', values=(alt_kurzel, korrigiertes_kurzel, title_case, ohne_minus, 'Ja'))
                
        except Exception as e:
            print(f"Fehler beim Aktualisieren der Alternative Kürzel-Tabelle: {e}")
    
    def add_alternative_kurzel(self):
        """Fügt ein neues alternatives Kürzel hinzu"""
        dialog = AlternativeKurzelDialog(self, "Neues alternatives Kürzel")
        if dialog.result:
            alt_kurzel, korrigiertes_kurzel = dialog.result
            if alt_kurzel and korrigiertes_kurzel:
                # Prüfe ob alternatives Kürzel bereits existiert
                if alt_kurzel.lower() in self.json_config.get('alternative_kurzel', {}):
                    messagebox.showwarning("Warnung", f"Alternatives Kürzel '{alt_kurzel}' existiert bereits!")
                    return
                
                # Füge zur Konfiguration hinzu
                if 'alternative_kurzel' not in self.json_config:
                    self.json_config['alternative_kurzel'] = {}
                
                self.json_config['alternative_kurzel'][alt_kurzel.lower()] = korrigiertes_kurzel.upper()
                self.refresh_alternative_kurzel_table()
                write_detailed_log("info", "Alternatives Kürzel hinzugefügt", f"Alt: {alt_kurzel} → Korrigiert: {korrigiertes_kurzel}")
    
    def edit_alternative_kurzel(self, event=None):
        """Bearbeitet das ausgewählte alternative Kürzel"""
        selection = self.alternative_tree.selection()
        if not selection:
            messagebox.showwarning("Warnung", "Bitte wählen Sie ein alternatives Kürzel aus!")
            return
        
        item = self.alternative_tree.item(selection[0])
        alt_kurzel, korrigiertes_kurzel, _ = item['values']
        
        dialog = AlternativeKurzelDialog(self, "Alternatives Kürzel bearbeiten", alt_kurzel, korrigiertes_kurzel)
        if dialog.result:
            new_alt_kurzel, new_korrigiertes_kurzel = dialog.result
            if new_alt_kurzel and new_korrigiertes_kurzel:
                # Entferne alten Eintrag
                if alt_kurzel.lower() in self.json_config.get('alternative_kurzel', {}):
                    del self.json_config['alternative_kurzel'][alt_kurzel.lower()]
                
                # Füge neuen Eintrag hinzu
                self.json_config['alternative_kurzel'][new_alt_kurzel.lower()] = new_korrigiertes_kurzel.upper()
                self.refresh_alternative_kurzel_table()
                write_detailed_log("info", "Alternatives Kürzel bearbeitet", f"Alt: {new_alt_kurzel} → Korrigiert: {new_korrigiertes_kurzel}")
    
    def delete_alternative_kurzel(self):
        """Löscht das ausgewählte alternative Kürzel"""
        selection = self.alternative_tree.selection()
        if not selection:
            messagebox.showwarning("Warnung", "Bitte wählen Sie ein alternatives Kürzel aus!")
            return
        
        item = self.alternative_tree.item(selection[0])
        alt_kurzel, korrigiertes_kurzel, _ = item['values']
        
        if messagebox.askyesno("Bestätigung", f"Möchten Sie das alternative Kürzel '{alt_kurzel}' → '{korrigiertes_kurzel}' wirklich löschen?"):
            if alt_kurzel.lower() in self.json_config.get('alternative_kurzel', {}):
                del self.json_config['alternative_kurzel'][alt_kurzel.lower()]
                self.refresh_alternative_kurzel_table()
                write_detailed_log("info", "Alternatives Kürzel gelöscht", f"Alt: {alt_kurzel} → Korrigiert: {korrigiertes_kurzel}")
    
    def generate_alternative_kurzel(self):
        """Generiert automatisch alternative Kürzel aus allen gültigen Kürzeln"""
        if messagebox.askyesno("Bestätigung", "Möchten Sie automatisch alternative Kürzel aus allen gültigen Kürzeln generieren?\n\nDies erstellt verschiedene Varianten:\n- Kleinbuchstaben\n- Title Case (erste Buchstaben groß)\n- Ohne Minus-Zeichen"):
            valid_kurzel = self.json_config.get('valid_kurzel', [])
            alternative_kurzel = self.json_config.get('alternative_kurzel', {})
            
            generated_count = 0
            for kurzel in valid_kurzel:
                # Kleinbuchstaben-Variante
                alt_kurzel_lower = kurzel.lower()
                if alt_kurzel_lower not in alternative_kurzel:
                    alternative_kurzel[alt_kurzel_lower] = kurzel
                    generated_count += 1
                
                # Title Case Variante (erste Buchstaben groß)
                alt_kurzel_title = kurzel.title()
                if alt_kurzel_title not in alternative_kurzel:
                    alternative_kurzel[alt_kurzel_title] = kurzel
                    generated_count += 1
                
                # Variante ohne Minus
                alt_kurzel_no_minus = kurzel.replace('-', '')
                if alt_kurzel_no_minus not in alternative_kurzel:
                    alternative_kurzel[alt_kurzel_no_minus] = kurzel
                    generated_count += 1
                
                # Kleinbuchstaben ohne Minus
                alt_kurzel_lower_no_minus = kurzel.lower().replace('-', '')
                if alt_kurzel_lower_no_minus not in alternative_kurzel:
                    alternative_kurzel[alt_kurzel_lower_no_minus] = kurzel
                    generated_count += 1
            
            self.json_config['alternative_kurzel'] = alternative_kurzel
            self.refresh_alternative_kurzel_table()
            messagebox.showinfo("Erfolg", f"{generated_count} alternative Kürzel wurden generiert!")
            write_detailed_log("info", "Alternative Kürzel generiert", f"Anzahl: {generated_count}")
    
    def import_alternative_csv(self):
        """Importiert alternative Kürzel aus CSV-Datei"""
        try:
            file_path = filedialog.askopenfilename(
                title="Alternative Kürzel importieren",
                filetypes=[("CSV-Dateien", "*.csv"), ("Alle Dateien", "*.*")]
            )
            if not file_path:
                return
            
            imported_count = 0
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.reader(f, delimiter=';')
                next(reader)  # Überspringe Header
                
                for row in reader:
                    if len(row) >= 2 and row[0].strip() and row[1].strip():
                        alt_kurzel = row[0].strip().lower()
                        korrigiertes_kurzel = row[1].strip().upper()
                        
                        if 'alternative_kurzel' not in self.json_config:
                            self.json_config['alternative_kurzel'] = {}
                        
                        self.json_config['alternative_kurzel'][alt_kurzel] = korrigiertes_kurzel
                        imported_count += 1
                        
                        # Importiere auch die zusätzlichen Varianten falls vorhanden
                        if len(row) >= 3 and row[2].strip():
                            title_case = row[2].strip()
                            if title_case not in self.json_config['alternative_kurzel']:
                                self.json_config['alternative_kurzel'][title_case] = korrigiertes_kurzel
                                imported_count += 1
                        
                        if len(row) >= 4 and row[3].strip():
                            ohne_minus = row[3].strip()
                            if ohne_minus not in self.json_config['alternative_kurzel']:
                                self.json_config['alternative_kurzel'][ohne_minus] = korrigiertes_kurzel
                                imported_count += 1
            
            self.refresh_alternative_kurzel_table()
            messagebox.showinfo("Import", f"{imported_count} alternative Kürzel wurden importiert!")
            write_detailed_log("info", "Alternative Kürzel importiert", f"Anzahl: {imported_count}")
            
        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Import: {e}")
    
    def export_alternative_csv(self):
        """Exportiert alternative Kürzel in CSV-Datei"""
        try:
            file_path = filedialog.asksaveasfilename(
                title="Alternative Kürzel exportieren",
                defaultextension=".csv",
                filetypes=[("CSV-Dateien", "*.csv"), ("Alle Dateien", "*.*")],
                initialfile="alternative_kurzel.csv"
            )
            if not file_path:
                return
            
            alternative_kurzel = self.json_config.get('alternative_kurzel', {})
            with open(file_path, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f, delimiter=';')
                writer.writerow(['alternatives_kurzel', 'korrigiertes_kurzel', 'title_case', 'ohne_minus'])
                
                for alt_kurzel, korrigiertes_kurzel in alternative_kurzel.items():
                    title_case = alt_kurzel.title()
                    ohne_minus = alt_kurzel.replace('-', '')
                    writer.writerow([alt_kurzel, korrigiertes_kurzel, title_case, ohne_minus])
            
            messagebox.showinfo("Export", f"CSV wurde exportiert:\n{file_path}")
            write_detailed_log("info", "Alternative Kürzel exportiert", f"Anzahl: {len(alternative_kurzel)}")
            
        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Export: {e}")

    def import_quality_csv(self):
        try:
            file_path = filedialog.askopenfilename(
                title="Bildqualitäts-Optionen importieren",
                filetypes=[("CSV-Dateien", "*.csv"), ("Alle Dateien", "*.*")]
            )
            if not file_path:
                return
            de_list, en_list = [], []
            with safe_csv_open(file_path, 'r') as f:
                reader = csv.DictReader(f, delimiter=';')
                rows = list(reader)
                rows.sort(key=lambda r: int((r.get('id') or '0').strip() or 0))
                for row in rows:
                    de_list.append((row.get('name_de') or '').strip())
                    en_list.append((row.get('name_en') or '').strip())
            self.json_config.setdefault('image_quality_options', {})['de'] = de_list
            self.json_config['image_quality_options']['en'] = en_list
            self.refresh_quality_table()
            messagebox.showinfo("Import", f"CSV wurde importiert:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Fehler", f"CSV-Import fehlgeschlagen: {e}")
    
    # Placeholder-Methoden für andere Tabellen (später implementieren)
    def add_new_damage_category(self): pass
    def edit_selected_damage_category(self, event=None): pass
    def delete_selected_damage_category(self): pass
    def add_new_imagetype(self): pass
    def edit_selected_imagetype(self, event=None): pass
    def delete_selected_imagetype(self): pass
    def add_new_quality(self): pass
    def edit_selected_quality(self, event=None): pass
    def delete_selected_quality(self): pass

    def open_folder(self):
        """Öffnet einen Ordner mit Bildern ohne Analyse zu starten"""
        # Verwende letzten Ordner als Startverzeichnis
        last_folder = self.json_config.get('last_selections', {}).get('open_folder', '')
        initial_dir = last_folder if last_folder and os.path.exists(last_folder) else None
        
        sel = filedialog.askdirectory(title="Ordner mit Bildern auswählen", initialdir=initial_dir)
        if not sel:
            return
        
        # Speichere die Auswahl
        if 'last_selections' not in self.json_config:
            self.json_config['last_selections'] = {}
        self.json_config['last_selections']['open_folder'] = sel
        self.config_manager.save_config()
        
        self.source_dir = sel
        self.label_folder.config(text=sel)
        
        # Lade Bilder
        files = [f for f in os.listdir(sel) 
                 if f.lower().endswith(('.png', '.jpg', '.jpeg', '.tif', '.bmp'))]
        
        if len(files) == 0:
            write_detailed_log("warning", "Keine Bilder im ausgewählten Ordner gefunden", f"Ordner: {sel}")
            messagebox.showinfo("Info", "Keine Bilder im ausgewählten Ordner gefunden.")
            return
        
        self.files = sorted(files)
        self.index = 0
        self.status_var.set(f"Ordner geladen: {len(files)} Bilder")
        
        write_detailed_log("info", "Ordner geöffnet", f"Ordner: {sel}, Bilder: {len(files)}")
        
        # Zeige erstes Bild
        self.show_image()
        
        # Aktualisiere Zähler basierend auf vorhandenen EXIF-Daten
        self.update_counters_from_exif()
        
        # Cache invalidieren, da neue Bilder geladen wurden
        self.invalidate_evaluation_cache()
        
        # Bewertungsfortschritt aktualisieren
        self.update_evaluation_progress()

    def update_counters_from_exif(self):
        """Aktualisiert die Zähler basierend auf vorhandenen EXIF-Daten"""
        self.counter = Counter()
        
        for fname in self.files:
            path = os.path.join(self.source_dir, fname)
            exif_data = get_exif_usercomment(path)
            if exif_data and "TAGOCR" in exif_data:
                tag = exif_data["TAGOCR"]
                if tag in self.valid_kurzel:
                    self.counter[tag] += 1
        
        # (Listbox entfernt)
        
        write_detailed_log("info", "Zähler aus EXIF-Daten aktualisiert", f"Gefundene Tags: {dict(self.counter)}")

    def show_excel_dialog(self):
        """Zeigt den Excel-Grunddaten Dialog"""
        if not hasattr(self, 'excel_dialog'):
            self.excel_dialog = ExcelGrunddatenDialog(self)
        # Setze den aktuellen Ordner für den Dialog
        self.current_folder = self.source_dir
        self.excel_dialog.show_dialog()


    def auto_analyze(self):
        # Nutze den bereits gewählten Ordner, falls vorhanden
        sel = self.source_dir
        if not sel:
            # Verwende letzten Analyse-Ordner als Startverzeichnis
            last_folder = self.json_config.get('last_selections', {}).get('analyze_folder', '')
            initial_dir = last_folder if last_folder and os.path.exists(last_folder) else None
            
            sel = filedialog.askdirectory(title="Ordner mit Bildern auswählen", initialdir=initial_dir)
            if not sel:
                return
            
            # Speichere die Auswahl
            if 'last_selections' not in self.json_config:
                self.json_config['last_selections'] = {}
            self.json_config['last_selections']['analyze_folder'] = sel
            self.config_manager.save_config()
            
            self.source_dir = sel
            self.label_folder.config(text=sel)

        files = [f for f in os.listdir(sel) 
                 if f.lower().endswith(('.png', '.jpg', '.jpeg', '.tif', '.bmp'))]
        total = len(files)
        if total == 0:
            write_detailed_log("warning", "Keine Bilder für Analyse gefunden", f"Ordner: {sel}")
            messagebox.showinfo("Info", "Keine Bilder gefunden.")
            return

        write_detailed_log("info", "OCR-Analyse gestartet", f"Ordner: {sel}, Bilder: {total}")

        # Öffne das neue Analyse-Fenster
        AnalysisWindow(self, sel, files, self.valid_kurzel, self.json_config)

    def refresh_images(self):
        """Aktualisiert die Bilderliste und lädt EXIF-Daten neu"""
        if not self.source_dir:
            messagebox.showwarning("Warnung", "Kein Ordner ausgewählt. Bitte wählen Sie zuerst einen Ordner aus.")
            return
        
        try:
            # Lade Bilderliste neu
            files = [f for f in os.listdir(self.source_dir) 
                     if f.lower().endswith(('.png', '.jpg', '.jpeg', '.tif', '.bmp'))]
            
            if not files:
                messagebox.showinfo("Info", "Keine Bilder im Ordner gefunden.")
                return
            
            # Aktualisiere Dateiliste
            self.files = sorted(files)
            self.index = 0
            
            # Aktualisiere Zähler aus EXIF-Daten
            self.update_counters_from_exif()
            
            # Cache invalidieren
            self.invalidate_evaluation_cache()
            
            # Bewertungsfortschritt aktualisieren
            self.update_evaluation_progress()
            
            # Erstes Bild anzeigen
            self.show_image()
            
            # Status aktualisieren
            self.status_var.set(f"Ordner aktualisiert: {len(files)} Bilder")
            
            write_detailed_log("info", "Bilderliste aktualisiert", f"Ordner: {self.source_dir}, Bilder: {len(files)}")
            messagebox.showinfo("Erfolg", f"Ordner erfolgreich aktualisiert!\n\n{len(files)} Bilder gefunden und EXIF-Daten neu eingelesen.")
            
        except Exception as e:
            error_msg = f"Fehler beim Aktualisieren: {str(e)}"
            write_detailed_log("error", "Fehler beim Aktualisieren der Bilderliste", str(e))
            messagebox.showerror("Fehler", error_msg)
            self.status_var.set("Fehler beim Aktualisieren")

    def show_exif_info(self):
        """Zeigt die EXIF-Informationen des aktuellen Bildes an"""
        if not self.files or self.index >= len(self.files):
            messagebox.showwarning("Warnung", "Kein Bild ausgewählt.")
            return
        
        try:
            fname = self.files[self.index]
            path = os.path.join(self.source_dir, fname)
            
            # Lade EXIF-Daten
            exif_data = get_exif_usercomment(path)
            
            # Erstelle Info-Fenster
            info_window = tk.Toplevel(self)
            info_window.title(f"EXIF-Informationen: {fname}")
            info_window.geometry("600x500")
            info_window.transient(self)
            info_window.grab_set()
            
            # Hauptframe
            main_frame = ttk.Frame(info_window, padding="10")
            main_frame.pack(fill=tk.BOTH, expand=True)
            
            # Titel
            title_label = ttk.Label(main_frame, text=f"EXIF-Daten für: {fname}", font=("TkDefaultFont", 12, "bold"))
            title_label.pack(pady=(0, 10))
            
            # Scrollable Text Widget
            text_frame = ttk.Frame(main_frame)
            text_frame.pack(fill=tk.BOTH, expand=True)
            
            text_widget = tk.Text(text_frame, wrap=tk.WORD, font=("Consolas", 9))
            scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL, command=text_widget.yview)
            text_widget.configure(yscrollcommand=scrollbar.set)
            
            text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            # EXIF-Daten anzeigen
            if exif_data:
                text_widget.insert(tk.END, "=== EXIF-Daten (JSON-Format) ===\n\n")
                
                # Formatiere JSON schön
                import json
                formatted_json = json.dumps(exif_data, indent=2, ensure_ascii=False)
                text_widget.insert(tk.END, formatted_json)
                
                # Zeige wichtige Felder hervorgehoben
                text_widget.insert(tk.END, "\n\n=== Wichtige Felder ===\n\n")
                
                important_fields = [
                    ("TAGOCR", "OCR-Ergebnis"),
                    ("damage_categories", "Schadenskategorien"),
                    ("image_types", "Bildarten"),
                    ("use_image", "Bild verwenden"),
                    ("image_quality", "Schadensbewertung"),
                    ("damage_description", "Schadensbeschreibung"),
                    ("windpark", "Windpark"),
                    ("windpark_land", "Land"),
                    ("sn", "Seriennummer"),
                    ("anlagen_nr", "Anlagen-Nr./Turbinen-ID"),
                    ("hersteller", "Hersteller")
                ]
                
                for field, description in important_fields:
                    value = exif_data.get(field, "Nicht gesetzt")
                    text_widget.insert(tk.END, f"{description}: {value}\n")
                    
            else:
                text_widget.insert(tk.END, "Keine EXIF-Daten gefunden.\n\n")
                text_widget.insert(tk.END, "Das Bild enthält keine UserComment-EXIF-Daten.\n")
                text_widget.insert(tk.END, "Möglicherweise wurde noch keine OCR-Analyse durchgeführt.\n")
            
            # Text nicht editierbar machen
            text_widget.config(state=tk.DISABLED)
            
            # Buttons
            button_frame = ttk.Frame(main_frame)
            button_frame.pack(fill=tk.X, pady=(10, 0))
            
            ttk.Button(button_frame, text="Schließen", command=info_window.destroy).pack(side=tk.RIGHT)
            ttk.Button(button_frame, text="In Datei speichern", command=lambda: self.save_exif_to_file(exif_data, fname)).pack(side=tk.RIGHT, padx=(0, 10))
            
            write_detailed_log("info", "EXIF-Informationen angezeigt", f"Datei: {fname}")
            
        except Exception as e:
            error_msg = f"Fehler beim Anzeigen der EXIF-Daten: {str(e)}"
            write_detailed_log("error", "Fehler beim Anzeigen der EXIF-Daten", str(e))
            messagebox.showerror("Fehler", error_msg)

    def save_exif_to_file(self, exif_data, filename):
        """Speichert EXIF-Daten in eine Textdatei"""
        try:
            from tkinter import filedialog
            import json
            
            # Vorschlag für Dateinamen
            base_name = os.path.splitext(filename)[0]
            suggested_name = f"{base_name}_exif.txt"
            
            # Datei auswählen
            file_path = filedialog.asksaveasfilename(
                title="EXIF-Daten speichern",
                defaultextension=".txt",
                filetypes=[("Textdateien", "*.txt"), ("Alle Dateien", "*.*")],
                initialfile=suggested_name
            )
            
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"EXIF-Daten für: {filename}\n")
                    f.write("=" * 50 + "\n\n")
                    
                    if exif_data:
                        f.write("JSON-Format:\n")
                        f.write(json.dumps(exif_data, indent=2, ensure_ascii=False))
                        f.write("\n\n")
                        
                        f.write("Wichtige Felder:\n")
                        important_fields = [
                            ("TAGOCR", "OCR-Ergebnis"),
                            ("damage_categories", "Schadenskategorien"),
                            ("image_types", "Bildarten"),
                            ("use_image", "Bild verwenden"),
                            ("image_quality", "Schadensbewertung"),
                            ("damage_description", "Schadensbeschreibung")
                        ]
                        
                        for field, description in important_fields:
                            value = exif_data.get(field, "Nicht gesetzt")
                            f.write(f"{description}: {value}\n")
                    else:
                        f.write("Keine EXIF-Daten gefunden.\n")
                
                messagebox.showinfo("Erfolg", f"EXIF-Daten gespeichert in:\n{file_path}")
                write_detailed_log("info", "EXIF-Daten in Datei gespeichert", f"Datei: {file_path}")
                
        except Exception as e:
            error_msg = f"Fehler beim Speichern der EXIF-Daten: {str(e)}"
            write_detailed_log("error", "Fehler beim Speichern der EXIF-Daten", str(e))
            messagebox.showerror("Fehler", error_msg)

    def on_window_resize(self, event):
        """Event-Handler für Fenstergrößenänderungen - zentriert das Bild neu"""
        # Nur auf Hauptfenster-Events reagieren, nicht auf Child-Widgets
        if event.widget == self:
            # Kurze Verzögerung, um sicherzustellen, dass das Layout aktualisiert wurde
            self.after(50, self.center_image_after_resize)
    
    def center_image_after_resize(self):
        """Zentriert das Bild nach einer Größenänderung"""
        try:
            if hasattr(self, 'canvas') and self.canvas and self.photo:
                # Aktualisiere die Canvas-Größe
                self.canvas.update_idletasks()
                
                # Zentriere das Bild neu
                self.center_image()
                
        except Exception as e:
            # Ignoriere Fehler beim Resizing
            pass

    def center_image(self):
        """Zentriert das aktuell angezeigte Bild im Canvas"""
        try:
            if hasattr(self, 'canvas') and self.canvas and self.photo:
                # Aktualisiere die Canvas-Größe
                self.canvas.update_idletasks()
                
                # Hole aktuelle Canvas-Größe
                c_w = self.canvas.winfo_width()
                c_h = self.canvas.winfo_height()
                
                if c_w < 10 or c_h < 10:
                    return  # Canvas noch nicht bereit
                
                # Berechne Zentrum
                x = c_w // 2
                y = c_h // 2
                
                # Lösche NUR das Bild (nicht die Zeichnungen) und zeige Bild links oben
                if hasattr(self, 'canvas_image_id'):
                    self.canvas.delete(self.canvas_image_id)
                self.canvas_image_id = self.canvas.create_image(0, 0, image=self.photo, anchor='nw')
                # Stelle sicher, dass Bild hinter den Zeichnungen ist
                self.canvas.tag_lower(self.canvas_image_id)
                
        except Exception as e:
            # Ignoriere Fehler beim Zentrieren
            pass

    def show_image(self):
        """Bild anzeigen mit umfassender Fehlerbehandlung (nur Listbox, nie größer als Canvas)"""
        if self._loading_image:
            return
        self._loading_image = True
        
        try:
            if not self.files:
                # Zeige Hinweis wenn keine Dateien geladen sind
                self.canvas.delete("all")
                self.canvas.create_text(400, 250, text="Keine Bilder geladen", 
                                       fill="gray", font=("Arial", 14))
                self.canvas.create_text(400, 300, text="Bereit", 
                                       fill="blue", font=("Arial", 10))
                return
            if self.index >= len(self.files):
                return
                
            fname = self.files[self.index]
            self.current_file = fname  # Setze current_file für Zoom-Button
            path = os.path.join(self.source_dir, fname)
            
            # Prüfe ob Datei existiert
            if not os.path.exists(path):
                self.canvas.delete("all")
                self.canvas.create_text(400, 250, text=f"Datei nicht gefunden:\n{fname}", 
                                       fill="red", font=("Arial", 12))
                self.canvas.create_text(400, 300, text="Fehler", 
                                       fill="red", font=("Arial", 10))
                return
                
            # Lade Bild
            img = Image.open(path)
            self.current_image = img.copy()  # Original für Zoom/Pan speichern
            
            w, h = img.size
            # Bild um 20% vergrößern
            w2, h2 = int(w * 1.2), int(h * 1.2)
            img = img.resize((w2, h2), Image.LANCZOS)
            # Canvas-Größe holen
            self.canvas.update_idletasks()
            c_w = self.canvas.winfo_width()
            c_h = self.canvas.winfo_height()
            if c_w < 10 or c_h < 10:
                c_w, c_h = 800, 500
            # Falls das Bild zu groß ist, auf Canvasgröße skalieren
            scale = min(c_w / w2, c_h / h2, 1.0)
            if scale < 1.0:
                img = img.resize((int(w2 * scale), int(h2 * scale)), Image.LANCZOS)
            
            # Zoom/Pan zurücksetzen bei neuem Bild
            self.zoom_factor = 1.0
            self.pan_x = 0
            self.pan_y = 0
            
            # Zeichnungs-History löschen bei neuem Bild
            self.clear_drawing_history()
            
            # Bild anzeigen
            self.photo = ImageTk.PhotoImage(img)
            self.center_image()
            
            # Zeige OCR-Ergebnis
            exif_data = get_exif_usercomment(path)
            if exif_data and "TAGOCR" in exif_data:
                detected = exif_data["TAGOCR"]
                self.correct_var.set(detected if detected in self.valid_kurzel else '')
                self._current_tagocr = detected
                self.ocr_tag_var.set(detected)
            else:
                self._current_tagocr = None
                self.ocr_tag_var.set("-")
            
            # Lade Bewertung
            self.load_current_evaluation()
            
            # Update Bildinformationen über dem Bild (nur beim Analysieren)
            if self._analyzing:
                self.image_counter_var.set(f"Bild {self.index + 1} von {len(self.files)}")
                self.filename_var.set(fname)
            
            # Update Status
            self.status_var.set(f"Bild {self.index + 1} von {len(self.files)}: {fname}")
            
            # (Listbox entfernt) keine Aktualisierung nötig
            
        except Exception as e:
            print(f"Fehler beim Anzeigen des Bildes: {e}")
            import traceback
            traceback.print_exc()
            self.status_var.set(f"Fehler beim Laden des Bildes: {str(e)}")
            # Zeige Fehlermeldung im Canvas
            self.canvas.delete("all")
            self.canvas.create_text(400, 250, text=f"Fehler beim Laden:\n{str(e)}", 
                                   fill="red", font=("Arial", 12))
            self.canvas.create_text(400, 300, text="Fehler", 
                                   fill="red", font=("Arial", 10))
        finally:
            self._loading_image = False
    def check_and_save_drawings(self):
        """Prüft ob Zeichnungen vorhanden sind und fragt ob gespeichert werden soll"""
        # Prüfe ob Zeichnungen vorhanden sind
        drawing_items = self.canvas.find_withtag('permanent_drawing')
        if not drawing_items:
            return True  # Keine Zeichnungen, weiter zum nächsten Bild
        
        # Frage Benutzer
        response = messagebox.askyesnocancel(
            "Zeichnungen speichern?",
            "Sie haben Zeichnungen auf diesem Bild. Möchten Sie diese speichern?",
            icon=messagebox.QUESTION
        )
        
        if response is None:  # Abbrechen
            return False
        elif response:  # Ja, speichern
            self.save_drawing_to_file()
            return True
        else:  # Nein, nicht speichern
            return True
    
    def next_image(self):
        """Nächstes Bild anzeigen mit Fehlerbehandlung"""
        try:
            # Prüfe und speichere Zeichnungen
            if not self.check_and_save_drawings():
                return  # Benutzer hat abgebrochen
            
            # Erzwinge Speichern des Damage-Texts vor dem Bildwechsel
            self._force_save_damage_text()
            
            if not self.files:
                return
            if self.index >= len(self.files) - 1:
                return
            self.index += 1
            self.show_image()
        except Exception as e:
            print(f"Fehler beim nächsten Bild: {e}")
            import traceback
            traceback.print_exc()

    def prev_image(self):
        """Vorheriges Bild anzeigen mit Fehlerbehandlung"""
        try:
            # Prüfe und speichere Zeichnungen
            if not self.check_and_save_drawings():
                return  # Benutzer hat abgebrochen
            
            # Erzwinge Speichern des Damage-Texts vor dem Bildwechsel
            self._force_save_damage_text()
            
            if not self.files:
                return
            if self.index <= 0:
                return
            self.index -= 1
            self.show_image()
        except Exception as e:
            print(f"Fehler beim vorherigen Bild: {e}")
            import traceback
            traceback.print_exc()

    def mark_as_ok_and_next(self):
        """Markiert das aktuelle Bild als 'In Ordnung' und wechselt zum nächsten Bild"""
        try:
            if not self.files:
                return
            
            # Speichere aktuelle Bewertung zuerst
            self.save_current_evaluation()
            
            # Aktiviere die erste Schadenskategorie ("Visuell keine Defekte")
            first_damage_category = self.config_manager.get_language_specific_list('damage_categories')[0]
            print(f"DEBUG: OK-Knopf aktiviert Schadenskategorie: '{first_damage_category}'")
            if first_damage_category in self.damage_vars:
                self.damage_vars[first_damage_category].set(True)
                print(f"DEBUG: Schadenskategorie '{first_damage_category}' wurde aktiviert")
            else:
                print(f"DEBUG: Warnung - Schadenskategorie '{first_damage_category}' nicht in damage_vars gefunden")
                print(f"DEBUG: Verfügbare Schadenskategorien: {list(self.damage_vars.keys())}")
            
            # Speichere die Bewertung erneut mit der neuen Schadenskategorie
            self.save_current_evaluation()
            
            # Visuelles Feedback - kurze grüne Markierung
            self.show_ok_feedback()
            
            # Wechsle zum nächsten Bild
            self.next_image()
            
        except Exception as e:
            print(f"Fehler beim Markieren als OK: {e}")
    
    def toggle_mousewheel_navigation(self):
        """Aktiviert oder deaktiviert die Mausrad-Navigation"""
        if self.mousewheel_nav_enabled.get():
            # Mausrad-Navigation aktivieren
            self.canvas.bind('<MouseWheel>', self.on_mousewheel)
            print("Mausrad-Navigation aktiviert")
        else:
            # Mausrad-Navigation deaktivieren
            self.canvas.unbind('<MouseWheel>')
            print("Mausrad-Navigation deaktiviert")
    
    def on_mousewheel(self, event):
        """Event-Handler für Mausrad-Scroll"""
        if not self.mousewheel_nav_enabled.get():
            return
        
        # Mausrad nach oben gedreht (event.delta > 0) = Vorheriges Bild
        # Mausrad nach unten gedreht (event.delta < 0) = Nächstes Bild
        if event.delta > 0:
            self.prev_image()
        elif event.delta < 0:
            self.next_image()
    
    def setup_tab_navigation(self):
        """Sammelt alle navigierbaren Widgets für Tab-Navigation"""
        self.tab_navigation_widgets = []
        
        # 1. Korrekt-Dropdown
        if hasattr(self, 'correct_combo'):
            self.tab_navigation_widgets.append(self.correct_combo)
        
        # 2. Bild verwenden Radiobuttons
        if hasattr(self, 'use_image_var'):
            # Finde die Radiobuttons für "Bild verwenden"
            for widget in self.winfo_children():
                self._find_radiobuttons_for_var(widget, self.use_image_var)
        
        # 3. Schadenskategorien Checkbuttons
        if hasattr(self, 'damage_vars'):
            for var in self.damage_vars.values():
                self._find_checkbuttons_for_var(var)
        
        # 4. Bildart-Kategorien Checkbuttons
        if hasattr(self, 'image_type_vars'):
            for var in self.image_type_vars.values():
                self._find_checkbuttons_for_var(var)
        
        # 5. Schadensbewertung Radiobuttons
        if hasattr(self, 'image_quality_var'):
            self._find_radiobuttons_for_var(self, self.image_quality_var)
        
        # 6. Damage Description Text
        if hasattr(self, 'damage_description_text'):
            self.tab_navigation_widgets.append(self.damage_description_text)
        
        print(f"Tab-Navigation Setup: {len(self.tab_navigation_widgets)} Widgets gefunden")
        
        # Zeige Nummerierung der Kategorien für Tasten 1-9
        self.show_category_numbering()
    
    def _find_radiobuttons_for_var(self, parent, target_var):
        """Findet Radiobuttons für eine bestimmte Variable"""
        try:
            for widget in parent.winfo_children():
                if isinstance(widget, tk.Radiobutton) and hasattr(widget, 'variable') and widget.variable == target_var:
                    self.tab_navigation_widgets.append(widget)
                elif hasattr(widget, 'winfo_children'):
                    self._find_radiobuttons_for_var(widget, target_var)
        except:
            pass
    
    def _find_checkbuttons_for_var(self, target_var):
        """Findet Checkbuttons für eine bestimmte Variable"""
        try:
            for widget in self.winfo_children():
                if isinstance(widget, tk.Checkbutton) and hasattr(widget, 'variable') and widget.variable == target_var:
                    self.tab_navigation_widgets.append(widget)
                elif hasattr(widget, 'winfo_children'):
                    self._find_checkbuttons_recursive(widget, target_var)
        except:
            pass
    
    def _find_checkbuttons_recursive(self, parent, target_var):
        """Findet Checkbuttons rekursiv"""
        try:
            for widget in parent.winfo_children():
                if isinstance(widget, tk.Checkbutton) and hasattr(widget, 'variable') and widget.variable == target_var:
                    self.tab_navigation_widgets.append(widget)
                elif hasattr(widget, 'winfo_children'):
                    self._find_checkbuttons_recursive(widget, target_var)
        except:
            pass
    
    def on_tab_navigation(self, event):
        """Tab-Navigation Handler"""
        if not self.tab_navigation_widgets:
            return
        
        # Entferne aktuellen Fokus
        current_focus = self.focus_get()
        
        # Finde aktuellen Index
        if current_focus in self.tab_navigation_widgets:
            self.current_tab_index = self.tab_navigation_widgets.index(current_focus)
        else:
            self.current_tab_index = 0
        
        # Nächstes Widget
        self.current_tab_index = (self.current_tab_index + 1) % len(self.tab_navigation_widgets)
        next_widget = self.tab_navigation_widgets[self.current_tab_index]
        
        # Setze Fokus
        next_widget.focus_set()
        
        # Für Text-Widgets: Cursor an Ende setzen
        if isinstance(next_widget, tk.Text):
            next_widget.see(tk.END)
        
        return "break"  # Verhindere Standard-Tab-Verhalten
    
    def on_enter_press(self, event):
        """Enter-Taste Handler für Aktivierung/Deaktivierung"""
        current_focus = self.focus_get()
        
        # Wenn ein Checkbutton oder Radiobutton fokussiert ist
        if isinstance(current_focus, (tk.Checkbutton, tk.Radiobutton)):
            # Simuliere einen Klick
            current_focus.invoke()
            return "break"
        
        # Wenn ein Text-Widget fokussiert ist, füge Zeilenumbruch hinzu
        elif isinstance(current_focus, tk.Text):
            current_focus.insert(tk.INSERT, '\n')
            return "break"
        
        # Standard-Verhalten für andere Widgets
        return None
    
    def toggle_category_by_number(self, number):
        """Aktiviert/Deaktiviert Kategorien basierend auf Nummerntaste (1-9)"""
        try:
            # Liste aller verfügbaren Kategorien (Schadenskategorien + Bildart-Kategorien)
            all_categories = []
            
            # Schadenskategorien hinzufügen
            if hasattr(self, 'damage_vars'):
                damage_categories = list(self.damage_vars.keys())
                all_categories.extend(damage_categories)
            
            # Bildart-Kategorien hinzufügen
            if hasattr(self, 'image_type_vars'):
                image_type_categories = list(self.image_type_vars.keys())
                all_categories.extend(image_type_categories)
            
            # Prüfe ob die Nummer gültig ist
            if number < 1 or number > len(all_categories):
                print(f"Nummer {number} außerhalb des Bereichs (1-{len(all_categories)})")
                return
            
            # Index ist 0-basiert, Nummer ist 1-basiert
            category_index = number - 1
            category_name = all_categories[category_index]
            
            # Bestimme ob es eine Schadenskategorie oder Bildart-Kategorie ist
            if hasattr(self, 'damage_vars') and category_name in self.damage_vars:
                # Schadenskategorie
                var = self.damage_vars[category_name]
                var.set(not var.get())  # Toggle
                print(f"Schadenskategorie '{category_name}' umgeschaltet: {var.get()}")
            elif hasattr(self, 'image_type_vars') and category_name in self.image_type_vars:
                # Bildart-Kategorie
                var = self.image_type_vars[category_name]
                var.set(not var.get())  # Toggle
                print(f"Bildart-Kategorie '{category_name}' umgeschaltet: {var.get()}")
            
            # Speichere die Bewertung
            self.save_current_evaluation()
            
        except Exception as e:
            print(f"Fehler beim Umschalten der Kategorie mit Nummer {number}: {e}")
            import traceback
            traceback.print_exc()
    
    def show_category_numbering(self):
        """Zeigt die Nummerierung der Kategorien für Tasten 1-9 an"""
        try:
            # Liste aller verfügbaren Kategorien
            all_categories = []
            
            # Schadenskategorien hinzufügen
            if hasattr(self, 'damage_vars'):
                damage_categories = list(self.damage_vars.keys())
                all_categories.extend(damage_categories)
            
            # Bildart-Kategorien hinzufügen
            if hasattr(self, 'image_type_vars'):
                image_type_categories = list(self.image_type_vars.keys())
                all_categories.extend(image_type_categories)
            
            print("\n=== Nummerntasten-Zuordnung (1-9) ===")
            for i, category in enumerate(all_categories[:9], 1):
                print(f"Taste {i}: {category}")
            
            if len(all_categories) > 9:
                print(f"... und {len(all_categories) - 9} weitere Kategorien")
            print("=====================================\n")
            
        except Exception as e:
            print(f"Fehler beim Anzeigen der Kategorie-Nummerierung: {e}")
    
    def create_tooltip(self, widget, text):
        """Erstellt einen Tooltip für ein Widget"""
        def show_tooltip(event):
            x, y, _, _ = widget.bbox("insert") if hasattr(widget, 'bbox') else (0, 0, 0, 0)
            x += widget.winfo_rootx() + 25
            y += widget.winfo_rooty() + 25
            
            self.tooltip_window = tk.Toplevel()
            self.tooltip_window.wm_overrideredirect(True)
            self.tooltip_window.wm_geometry(f"+{x}+{y}")
            
            label = tk.Label(self.tooltip_window, text=text, 
                           background="lightyellow", relief="solid", 
                           borderwidth=1, font=("TkDefaultFont", 9),
                           wraplength=300, justify="left")
            label.pack()
        
        def hide_tooltip(event):
            if self.tooltip_window:
                self.tooltip_window.destroy()
                self.tooltip_window = None
        
        widget.bind("<Enter>", show_tooltip)
        widget.bind("<Leave>", hide_tooltip)
    
    def add_tooltips_to_buttons(self):
        """Fügt Tooltips zu allen wichtigen Buttons hinzu"""
        try:
            # Toolbar-Buttons
            for widget in self.winfo_children():
                self._add_tooltips_recursive(widget)
        except Exception as e:
            print(f"Fehler beim Hinzufügen von Tooltips: {e}")
    
    def _add_tooltips_recursive(self, parent):
        """Fügt Tooltips rekursiv zu Widgets hinzu"""
        try:
            for widget in parent.winfo_children():
                # Prüfe Widget-Typ und Text für Tooltip-Zuordnung
                if isinstance(widget, tk.Button):
                    text = widget.cget('text')
                    if text:
                        tooltip_text = self._get_tooltip_for_button(text)
                        if tooltip_text:
                            self.create_tooltip(widget, tooltip_text)
                elif isinstance(widget, ttk.Button):
                    text = widget.cget('text')
                    if text:
                        tooltip_text = self._get_tooltip_for_button(text)
                        if tooltip_text:
                            self.create_tooltip(widget, tooltip_text)
                
                # Rekursiv für alle Kind-Widgets
                if hasattr(widget, 'winfo_children'):
                    self._add_tooltips_recursive(widget)
        except:
            pass
    
    def _get_tooltip_for_button(self, button_text):
        """Gibt den passenden Tooltip-Text für einen Button zurück"""
        tooltips = {
            "📁 Ordner öffnen": "Öffnet einen Ordner mit Bildern zur Analyse\nTastenkürzel: Ctrl+O",
            "📊 Excel laden": "Lädt Excel-Grunddaten für das Projekt\nEnthält Kürzel-Informationen und Metadaten",
            "🔍 Analysieren": "Startet die automatische OCR-Analyse aller Bilder\nTastenkürzel: Ctrl+A",
            "🔄 Aktualisieren": "Aktualisiert die Bildliste und Fortschrittsanzeige\nTastenkürzel: F5",
            "⚙️ Einstellungen": "Öffnet die Einstellungen und Konfiguration\nTastenkürzel: Ctrl+,",
            "📝 Log": "Zeigt das detaillierte Anwendungslog an\nFür Debugging und Fehleranalyse",
            "📋 OCR Log": "Zeigt das OCR-spezifische Log an\nOCR-Erkennungsdetails und Ergebnisse",
            "◀ Vorher": "Zeigt das vorherige Bild an\nTastenkürzel: Pfeil links",
            "Zoom & Markieren": "Öffnet das Zoom-Fenster mit Markierungs-Tools\nFür detaillierte Bildanalyse",
            "Nächste ▶": "Zeigt das nächste Bild an\nTastenkürzel: Pfeil rechts",
            "✓ In Ordnung": "Markiert das Bild als 'In Ordnung' und geht zum nächsten\nAutomatisch aktiviert erste Schadenskategorie",
            "🚫": "Markiert das Bild als 'Nicht verwenden' und geht zum nächsten\nSetzt 'Bild verwenden' auf 'nein'",
            "🖱️ Mausrad": "Aktiviert/Deaktiviert Mausrad-Navigation\nMausrad nach oben = vorheriges Bild\nMausrad nach unten = nächstes Bild"
        }
        return tooltips.get(button_text, "")
    
    def create_collapsible_frame(self, parent, title, row, default_collapsed=False):
        """Erstellt einen kollapsiblen Frame mit Header-Button"""
        # Hauptframe
        main_frame = ttk.Frame(parent)
        main_frame.grid(row=row, column=0, sticky="ew", pady=(0, 5))
        
        # Header-Button mit Pfeil
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X)
        
        # Pfeil-Button (anfangs eingeklappt)
        arrow_text = "▶" if default_collapsed else "▼"
        arrow_button = tk.Button(header_frame, text=f"{arrow_text} {title}", 
                                command=lambda: self.toggle_collapsible_frame(frame_info),
                                bg="#E3F2FD", fg="#1976D2", font=("TkDefaultFont", 10, "bold"),
                                relief="flat", bd=1, padx=5, pady=2)
        arrow_button.pack(fill=tk.X)
        
        # Content-Frame
        content_frame = ttk.Frame(main_frame, relief="sunken", borderwidth=1)
        if not default_collapsed:
            content_frame.pack(fill=tk.X, padx=(10, 0), pady=(0, 5))
        
        # Frame-Informationen
        frame_info = {
            'main_frame': main_frame,
            'header_frame': header_frame,
            'content': content_frame,
            'arrow_button': arrow_button,
            'collapsed': default_collapsed,
            'title': title
        }
        
        return frame_info
    
    def toggle_collapsible_frame(self, frame_info):
        """Schaltet einen kollapsiblen Frame um"""
        if frame_info['collapsed']:
            # Ausklappen
            frame_info['content'].pack(fill=tk.X, padx=(10, 0), pady=(0, 5))
            frame_info['arrow_button'].config(text=f"▼ {frame_info['title']}")
            frame_info['collapsed'] = False
        else:
            # Einklappen
            frame_info['content'].pack_forget()
            frame_info['arrow_button'].config(text=f"▶ {frame_info['title']}")
            frame_info['collapsed'] = True
    
    def mark_as_skip_and_next(self):
        """Markiert das aktuelle Bild als 'nicht verwenden' und wechselt zum nächsten Bild"""
        try:
            if not self.files:
                return
            
            # Speichere aktuelle Bewertung zuerst
            self.save_current_evaluation()
            
            # Setze "Bild verwenden" auf "nein"
            use_image_options = self.config_manager.get_language_specific_list('use_image_options')
            if 'nein' in use_image_options:
                self.use_image_var.set('nein')
            elif 'no' in use_image_options:
                self.use_image_var.set('no')
            else:
                # Fallback auf den letzten Wert in der Liste
                self.use_image_var.set(use_image_options[-1] if use_image_options else 'nein')
            
            # Speichere die Bewertung erneut mit der neuen Einstellung
            self.save_current_evaluation()
            
            # Visuelles Feedback - kurze rote Markierung
            self.show_skip_feedback()
            
            # Wechsle zum nächsten Bild
            self.next_image()
            
        except Exception as e:
            logger.error(f"Fehler beim Markieren als Skip: {e}")
            import traceback
            traceback.print_exc()

    def show_ok_feedback(self):
        """Zeigt kurzes visuelles Feedback für OK-Markierung"""
        try:
            # Erstelle temporäres Overlay-Fenster
            feedback_window = tk.Toplevel(self)
            feedback_window.overrideredirect(True)  # Entfernt Fensterrahmen
            feedback_window.attributes('-topmost', True)  # Immer im Vordergrund
            
            # Positioniere in der Mitte des Hauptfensters
            x = self.winfo_x() + self.winfo_width() // 2 - 100
            y = self.winfo_y() + self.winfo_height() // 2 - 50
            feedback_window.geometry(f"200x100+{x}+{y}")
            
            # Grüner Hintergrund
            feedback_window.configure(bg="#4CAF50")
            
            # Text-Label
            label = tk.Label(feedback_window, text="✓ In Ordnung", 
                           bg="#4CAF50", fg="white", 
                           font=("TkDefaultFont", 16, "bold"))
            label.pack(expand=True)
            
            # Nach 0,3 Sekunden automatisch schließen
            feedback_window.after(300, feedback_window.destroy)
            
        except Exception as e:
            print(f"Fehler beim Anzeigen des OK-Feedbacks: {e}")

    def show_skip_feedback(self):
        """Zeigt kurzes visuelles Feedback für Skip-Markierung"""
        try:
            # Erstelle temporäres Overlay-Fenster
            feedback_window = tk.Toplevel(self)
            feedback_window.overrideredirect(True)  # Entfernt Fensterrahmen
            feedback_window.attributes('-topmost', True)  # Immer im Vordergrund
            
            # Positioniere in der Mitte des Hauptfensters
            x = self.winfo_x() + self.winfo_width() // 2 - 100
            y = self.winfo_y() + self.winfo_height() // 2 - 50
            feedback_window.geometry(f"{FEEDBACK_WINDOW_WIDTH}x{FEEDBACK_WINDOW_HEIGHT}+{x}+{y}")
            
            # Roter Hintergrund
            feedback_window.configure(bg="#f44336")
            
            # Text-Label
            label = tk.Label(feedback_window, text="🚫 Nicht verwenden", 
                           bg="#f44336", fg="white", 
                           font=("TkDefaultFont", 14, "bold"))
            label.pack(expand=True)
            
            # Nach 0,3 Sekunden automatisch schließen
            feedback_window.after(300, feedback_window.destroy)
            
        except Exception as e:
            logger.error(f"Fehler beim Anzeigen des Skip-Feedbacks: {e}")

    def open_zoom_window(self):
        """Erweitertes Zoom- und Markieren-Fenster mit allen gewünschten Features"""
        if not self.current_file:
            messagebox.showwarning("Warnung", "Kein Bild geladen")
            return
            
        fname = os.path.join(self.source_dir, self.current_file)
        
        # Hauptfenster
        win = tk.Toplevel(self)
        win.title(f"Zoom & Markieren - {self.current_file}")
        win.geometry("1200x800")
        
        # Fenster-Icon setzen
        try:
            logo_path = resource_path('82EndoLogo.png')
            if os.path.exists(logo_path):
                img = Image.open(logo_path)
                img = img.convert('RGBA')
                img.thumbnail((THUMBNAIL_SMALL_WIDTH, THUMBNAIL_SMALL_HEIGHT), Image.LANCZOS)
                icon_img = ImageTk.PhotoImage(img)
                win.iconphoto(True, icon_img)
        except:
            pass
        
        # Bild laden
        img = Image.open(fname)
        original_img = img.copy()
        
        # Zoom-Variablen
        zoom_factor = 1.0
        pan_x, pan_y = 0, 0
        is_panning = False
        last_pan_x, last_pan_y = 0, 0
        
        # Zeichen-Variablen
        draw_mode = 'arrow'  # arrow, circle, rectangle, freehand
        draw_color = 'red'
        line_width = 3
        is_drawing = False
        drawing_points = []
        
        # Undo/Redo
        undo_stack = []
        redo_stack = []
        
        # Globale Referenz für das aktuelle Bild
        current_tk_image = None
        
        # Variable für ungespeicherte Änderungen
        has_unsaved_changes = False
        
        # Canvas mit Scrollbars
        canvas_frame = ttk.Frame(win)
        canvas_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Scrollbars
        h_scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL)
        v_scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL)
        
        # Canvas
        canvas = tk.Canvas(canvas_frame, bg='#f0f0f0', 
                          xscrollcommand=h_scrollbar.set,
                          yscrollcommand=v_scrollbar.set)
        
        h_scrollbar.config(command=canvas.xview)
        v_scrollbar.config(command=canvas.yview)
        
        # Grid-Layout für Canvas und Scrollbars
        canvas.grid(row=0, column=0, sticky="nsew")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        
        canvas_frame.grid_rowconfigure(0, weight=1)
        canvas_frame.grid_columnconfigure(0, weight=1)
        
        # Status-Bar
        status_bar = ttk.Label(win, text="Bereit", relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=2)
        
        # Funktionen - MÜSSEN vor den Buttons definiert werden!
        def set_draw_mode(mode):
            nonlocal draw_mode
            draw_mode = mode
            status_bar.config(text=f"Werkzeug: {mode}")
            
        def set_draw_color(color):
            nonlocal draw_color
            draw_color = color
            
        def set_line_width(width):
            nonlocal line_width
            line_width = width
            
        def zoom(factor):
            nonlocal zoom_factor
            zoom_factor *= factor
            zoom_factor = max(0.1, min(10.0, zoom_factor))  # Begrenzen
            zoom_label.config(text=f"{int(zoom_factor * 100)}%")
            update_canvas()
            
        def reset_view():
            nonlocal zoom_factor, pan_x, pan_y
            zoom_factor = 1.0
            pan_x, pan_y = 0, 0
            zoom_label.config(text="100%")
            update_canvas()
            
        def update_canvas():
            nonlocal current_tk_image
            # Canvas-Größe anpassen
            canvas_width = int(img.width * zoom_factor)
            canvas_height = int(img.height * zoom_factor)
            
            # Aktuelle Canvas-Größe ermitteln
            actual_canvas_width = canvas.winfo_width()
            actual_canvas_height = canvas.winfo_height()
            
            # Fallback für Canvas-Größe, falls noch nicht gerendert
            if actual_canvas_width <= 1 or actual_canvas_height <= 1:
                actual_canvas_width = 800
                actual_canvas_height = 600
            
            # Scrollregion setzen (mindestens so groß wie das Canvas)
            scroll_width = max(canvas_width, actual_canvas_width)
            scroll_height = max(canvas_height, actual_canvas_height)
            canvas.configure(scrollregion=(0, 0, scroll_width, scroll_height))
            
            # Bild skalieren
            resized_img = img.resize((canvas_width, canvas_height), Image.Resampling.LANCZOS)
            current_tk_image = ImageTk.PhotoImage(resized_img)
            
            # Altes Bild löschen und neues zentriert zeichnen
            canvas.delete("image")
            
            # X und Y Koordinaten für die Zentrierung berechnen
            x = (scroll_width - canvas_width) // 2
            y = (scroll_height - canvas_height) // 2
            
            # Bild zentriert zeichnen
            canvas.create_image(x, y, image=current_tk_image, anchor="nw", tags="image")
            
            # Scrollbars auf die Mitte setzen, wenn das Bild kleiner als das Canvas ist
            if canvas_width < actual_canvas_width:
                canvas.xview_moveto(0.5 - (canvas_width / (2 * scroll_width)))
            else:
                canvas.xview_moveto(0)
                
            if canvas_height < actual_canvas_height:
                canvas.yview_moveto(0.5 - (canvas_height / (2 * scroll_height)))
            else:
                canvas.yview_moveto(0)
        
        def on_mouse_down(event):
            nonlocal is_panning, is_drawing, last_pan_x, last_pan_y, drawing_points
            
            if event.state & 0x4:  # Strg gedrückt oder rechte Maustaste
                is_panning = True
                last_pan_x, last_pan_y = event.x, event.y
                canvas.config(cursor="fleur")
            else:
                is_drawing = True
                drawing_points = [(event.x, event.y)]
                if draw_mode == 'freehand':
                    canvas.config(cursor="pencil")
                    
        def on_mouse_move(event):
            nonlocal pan_x, pan_y, drawing_points, has_unsaved_changes
            
            if is_panning:
                dx = event.x - last_pan_x
                dy = event.y - last_pan_y
                pan_x += dx
                pan_y += dy
                update_canvas()
                last_pan_x, last_pan_y = event.x, event.y
            elif is_drawing and draw_mode == 'freehand':
                drawing_points.append((event.x, event.y))
                if len(drawing_points) > 1:
                    x1, y1 = drawing_points[-2]
                    x2, y2 = drawing_points[-1]
                    item = canvas.create_line(x1, y1, x2, y2, fill=draw_color, width=line_width, tags="drawing")
                    undo_stack.append(('line', item))
                    redo_stack.clear()
                    has_unsaved_changes = True
                    
        def on_mouse_up(event):
            nonlocal is_panning, is_drawing, has_unsaved_changes
            
            if is_panning:
                is_panning = False
                canvas.config(cursor="")
            elif is_drawing:
                is_drawing = False
                canvas.config(cursor="")
                
                if draw_mode == 'arrow':
                    item = canvas.create_line(drawing_points[0][0], drawing_points[0][1], 
                                           event.x, event.y, arrow=tk.LAST, 
                                           fill=draw_color, width=line_width, tags="drawing")
                    undo_stack.append(('arrow', item, drawing_points[0][0], drawing_points[0][1], event.x, event.y))
                    redo_stack.clear()
                    has_unsaved_changes = True
                    
                elif draw_mode == 'circle':
                    x0, y0 = drawing_points[0]
                    r = ((event.x - x0)**2 + (event.y - y0)**2)**0.5
                    item = canvas.create_oval(x0 - r, y0 - r, x0 + r, y0 + r, 
                                           outline=draw_color, width=line_width, tags="drawing")
                    undo_stack.append(('circle', item, x0, y0, r))
                    redo_stack.clear()
                    has_unsaved_changes = True
                    
                elif draw_mode == 'rectangle':
                    x0, y0 = drawing_points[0]
                    item = canvas.create_rectangle(x0, y0, event.x, event.y, 
                                                outline=draw_color, width=line_width, tags="drawing")
                    undo_stack.append(('rectangle', item, x0, y0, event.x, event.y))
                    redo_stack.clear()
                    has_unsaved_changes = True
            
        def on_mouse_wheel(event):
            if event.state & 0x4:  # Strg gedrückt
                if event.delta > 0:
                    zoom(1.1)
                else:
                    zoom(0.9)
                    
        def undo():
            nonlocal has_unsaved_changes
            if undo_stack:
                item_data = undo_stack.pop()
                redo_stack.append(item_data)
                canvas.delete(item_data[1])  # item_data[1] ist die item_id
                has_unsaved_changes = True
                
        def redo():
            nonlocal has_unsaved_changes
            if redo_stack:
                item_data = redo_stack.pop()
                undo_stack.append(item_data)
                # Item neu erstellen
                if item_data[0] == 'arrow':
                    item = canvas.create_line(item_data[2], item_data[3], item_data[4], item_data[5], 
                                           arrow=tk.LAST, fill=draw_color, width=line_width, tags="drawing")
                elif item_data[0] == 'circle':
                    item = canvas.create_oval(item_data[2] - item_data[4], item_data[3] - item_data[4],
                                           item_data[2] + item_data[4], item_data[3] + item_data[4],
                                           outline=draw_color, width=line_width, tags="drawing")
                elif item_data[0] == 'rectangle':
                    item = canvas.create_rectangle(item_data[2], item_data[3], item_data[4], item_data[5],
                                                outline=draw_color, width=line_width, tags="drawing")
                elif item_data[0] == 'line':
                    # Freihand-Linien werden nicht redo'd, da sie komplex sind
                    pass
                has_unsaved_changes = True
                    
        def save_annotated():
            nonlocal has_unsaved_changes, img
            if not img:
                return
            try:
                # Bild mit Markierungen speichern
                annotated = img.copy()
                draw = ImageDraw.Draw(annotated)
                
                # Bild-Offset berechnen (wie in update_canvas)
                canvas_width = int(img.width * zoom_factor)
                canvas_height = int(img.height * zoom_factor)
                actual_canvas_width = canvas.winfo_width()
                actual_canvas_height = canvas.winfo_height()
                
                if actual_canvas_width <= 1 or actual_canvas_height <= 1:
                    actual_canvas_width = 800
                    actual_canvas_height = 600
                
                scroll_width = max(canvas_width, actual_canvas_width)
                scroll_height = max(canvas_height, actual_canvas_height)
                
                # Bild-Offset (Zentrierung)
                image_offset_x = (scroll_width - canvas_width) // 2
                image_offset_y = (scroll_height - canvas_height) // 2
                
                # Alle Zeichnungen sammeln
                for item_data in undo_stack:
                    if item_data[0] == 'arrow':
                        x0, y0, x1, y1 = item_data[2], item_data[3], item_data[4], item_data[5]
                        # Bild-Offset, Pan-Verschiebung und Zoom berücksichtigen
                        x0 = int((x0 - image_offset_x - pan_x) / zoom_factor)
                        y0 = int((y0 - image_offset_y - pan_y) / zoom_factor)
                        x1 = int((x1 - image_offset_x - pan_x) / zoom_factor)
                        y1 = int((y1 - image_offset_y - pan_y) / zoom_factor)
                        draw.line((x0, y0, x1, y1), fill=draw_color, width=line_width)
                        # Pfeilspitze
                        dx, dy = x1-x0, y1-y0
                        l = (dx**2 + dy**2)**0.5
                        if l > 0:
                            ux, uy = dx/l, dy/l
                            draw.line((x1, y1, x1-30*ux+15*uy, y1-30*uy-15*ux), fill=draw_color, width=line_width)
                            draw.line((x1, y1, x1-30*ux-15*uy, y1-30*uy+15*ux), fill=draw_color, width=line_width)
                            
                    elif item_data[0] == 'circle':
                        x, y, r = item_data[2], item_data[3], item_data[4]
                        # Bild-Offset, Pan-Verschiebung und Zoom berücksichtigen
                        x = int((x - image_offset_x - pan_x) / zoom_factor)
                        y = int((y - image_offset_y - pan_y) / zoom_factor)
                        r = int(r / zoom_factor)
                        draw.ellipse((x-r, y-r, x+r, y+r), outline=draw_color, width=line_width)
                        
                    elif item_data[0] == 'rectangle':
                        x0, y0, x1, y1 = item_data[2], item_data[3], item_data[4], item_data[5]
                        # Bild-Offset, Pan-Verschiebung und Zoom berücksichtigen
                        x0 = int((x0 - image_offset_x - pan_x) / zoom_factor)
                        y0 = int((y0 - image_offset_y - pan_y) / zoom_factor)
                        x1 = int((x1 - image_offset_x - pan_x) / zoom_factor)
                        y1 = int((y1 - image_offset_y - pan_y) / zoom_factor)
                        draw.rectangle((x0, y0, x1, y1), outline=draw_color, width=line_width)
                
                # Aktuelles Verzeichnis des Bildes ermitteln
                current_dir = os.path.dirname(self.files[self.index])
                
                # Original-Ordner als Unterverzeichnis des ausgewählten Bildordners erstellen
                original_dir = os.path.join(self.source_dir, "originale")
                os.makedirs(original_dir, exist_ok=True)
                
                # Pfade für Original und bearbeitete Version
                filename = os.path.basename(self.files[self.index])
                original_save_path = os.path.join(original_dir, filename)
                annotated_save_path = os.path.join(self.source_dir, filename)
                
                # Wenn noch keine Original-Kopie existiert, erstelle sie (mit EXIF)
                if not os.path.exists(original_save_path):
                    if 'exif' in img.info:
                        img.save(original_save_path, quality=95, exif=img.info['exif'])
                    else:
                        img.save(original_save_path, quality=95)
                
                # Bearbeitete Version speichern (mit EXIF)
                try:
                    if 'exif' in img.info:
                        annotated.save(annotated_save_path, quality=95, exif=img.info['exif'])
                    else:
                        annotated.save(annotated_save_path, quality=95)
                except Exception as e:
                    messagebox.showerror("Fehler", f"Bearbeitetes Bild konnte nicht gespeichert werden!\nPfad: {annotated_save_path}\nFehler: {str(e)}")
                    write_detailed_log("error", "Bearbeitetes Bild konnte nicht gespeichert werden", details=str(e))
                    return
                # Prüfe, ob das Bild wirklich überschrieben wurde
                if not os.path.exists(annotated_save_path):
                    messagebox.showerror("Fehler", f"Bearbeitetes Bild wurde nicht gefunden nach dem Speichern!\nPfad: {annotated_save_path}")
                    write_detailed_log("error", "Bearbeitetes Bild nach save() nicht gefunden", details=annotated_save_path)
                    return
                # Optional: Änderungszeit prüfen (Debug)
                mtime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(annotated_save_path)))
                write_detailed_log("info", "Bearbeitetes Bild gespeichert (Prüfung)", f"Pfad: {annotated_save_path}, mtime: {mtime}")
                
                has_unsaved_changes = False  # Änderungen als gespeichert markieren
                
                write_detailed_log("info", "Bearbeitetes Bild gespeichert", 
                               f"Original: {original_save_path}, Bearbeitet: {annotated_save_path}")
                # Nach dem Speichern das Bild im Hauptfenster neu laden
                self.show_image()
            except Exception as e:
                messagebox.showerror("Fehler", f"Fehler beim Speichern: {str(e)}")
                write_detailed_log("error", "Fehler beim Speichern des bearbeiteten Bildes", 
                               details=str(e), exception=e)
        
        def set_pan_mode():
            nonlocal is_panning
            is_panning = not is_panning
            if is_panning:
                canvas.config(cursor="fleur")
                status_bar.config(text="Pan-Modus aktiv (Leertaste zum Beenden)")
            else:
                canvas.config(cursor="")
                status_bar.config(text="Bereit")
        
        def safe_close_window():
            """Sicheres Schließen des Fensters mit Warnung bei ungespeicherten Änderungen"""
            if has_unsaved_changes:
                result = messagebox.askyesnocancel(
                    "Ungespeicherte Änderungen",
                    "Sie haben ungespeicherte Änderungen.\n\n"
                    "Möchten Sie das bearbeitete Bild speichern, bevor Sie das Fenster schließen?",
                    icon=messagebox.WARNING
                )
                if result is True:  # Ja - Speichern
                    save_annotated()
                    win.destroy()
                elif result is False:  # Nein - Schließen ohne Speichern
                    win.destroy()
                # Bei Cancel (None) wird nichts gemacht - Fenster bleibt offen
            else:
                win.destroy()
            # Nach dem Schließen das Bild im Hauptfenster neu laden
            self.show_image()
        
        # Toolbar oben
        toolbar = ttk.Frame(win)
        toolbar.pack(fill=tk.X, padx=5, pady=(5, 0))
        
        # Werkzeug-Buttons mit Tooltips
        ttk.Label(toolbar, text="Werkzeuge:").pack(side=tk.LEFT, padx=(0, 5))
        
        arrow_btn = ttk.Button(toolbar, text="Pfeil", command=lambda: set_draw_mode('arrow'))
        arrow_btn.pack(side=tk.LEFT, padx=2)
        self.create_tooltip(arrow_btn, "Pfeil zeichnen (Pfeil von Start- zu Endpunkt)")
        
        circle_btn = ttk.Button(toolbar, text="Kreis", command=lambda: set_draw_mode('circle'))
        circle_btn.pack(side=tk.LEFT, padx=2)
        self.create_tooltip(circle_btn, "Kreis zeichnen (Radius von Start- zu Endpunkt)")
        
        rect_btn = ttk.Button(toolbar, text="Rechteck", command=lambda: set_draw_mode('rectangle'))
        rect_btn.pack(side=tk.LEFT, padx=2)
        self.create_tooltip(rect_btn, "Rechteck zeichnen (von Ecke zu Ecke)")
        
        freehand_btn = ttk.Button(toolbar, text="Freihand", command=lambda: set_draw_mode('freehand'))
        freehand_btn.pack(side=tk.LEFT, padx=2)
        self.create_tooltip(freehand_btn, "Freihandzeichnen (Maus gedrückt halten)")
        
        # Farbauswahl
        ttk.Label(toolbar, text="Farbe:").pack(side=tk.LEFT, padx=(10, 5))
        color_var = tk.StringVar(value='red')
        color_combo = ttk.Combobox(toolbar, textvariable=color_var, values=['red', 'blue', 'green', 'yellow', 'orange', 'purple', 'black', 'white'], width=8)
        color_combo.pack(side=tk.LEFT, padx=2)
        color_combo.bind('<<ComboboxSelected>>', lambda e: set_draw_color(color_var.get()))
        
        # Linienbreite
        ttk.Label(toolbar, text="Breite:").pack(side=tk.LEFT, padx=(10, 5))
        width_var = tk.StringVar(value='3')
        width_combo = ttk.Combobox(toolbar, textvariable=width_var, values=['1', '2', '3', '5', '8', '12'], width=5)
        width_combo.pack(side=tk.LEFT, padx=2)
        width_combo.bind('<<ComboboxSelected>>', lambda e: set_line_width(int(width_var.get())))
        
        # Zoom-Controls
        ttk.Label(toolbar, text="Zoom:").pack(side=tk.LEFT, padx=(10, 5))
        zoom_label = ttk.Label(toolbar, text="100%")
        zoom_label.pack(side=tk.LEFT, padx=2)
        
        zoom_in_btn = ttk.Button(toolbar, text="+", width=3, command=lambda: zoom(1.2))
        zoom_in_btn.pack(side=tk.LEFT, padx=2)
        
        zoom_out_btn = ttk.Button(toolbar, text="-", width=3, command=lambda: zoom(0.8))
        zoom_out_btn.pack(side=tk.LEFT, padx=2)
        
        reset_btn = ttk.Button(toolbar, text="Reset", command=reset_view)
        reset_btn.pack(side=tk.LEFT, padx=2)
        
        # Undo/Redo
        undo_btn = ttk.Button(toolbar, text="↶", width=3, command=undo)
        undo_btn.pack(side=tk.LEFT, padx=(10, 2))
        self.create_tooltip(undo_btn, "Rückgängig (Strg+Z)")
        
        redo_btn = ttk.Button(toolbar, text="↷", width=3, command=redo)
        redo_btn.pack(side=tk.LEFT, padx=2)
        self.create_tooltip(redo_btn, "Wiederholen (Strg+Y)")
        
        # Speichern-Button
        save_btn = ttk.Button(toolbar, text="Speichern", command=save_annotated)
        save_btn.pack(side=tk.RIGHT, padx=5)
        
        # Event-Bindings
        canvas.bind('<ButtonPress-1>', on_mouse_down)
        canvas.bind('<ButtonPress-3>', on_mouse_down)  # Rechte Maustaste
        canvas.bind('<B1-Motion>', on_mouse_move)
        canvas.bind('<B3-Motion>', on_mouse_move)  # Rechte Maustaste
        canvas.bind('<ButtonRelease-1>', on_mouse_up)
        canvas.bind('<ButtonRelease-3>', on_mouse_up)  # Rechte Maustaste
        canvas.bind('<MouseWheel>', on_mouse_wheel)
        
        # Keyboard-Shortcuts
        win.bind('<Control-z>', lambda e: undo())
        win.bind('<Control-y>', lambda e: redo())
        win.bind('<Control-plus>', lambda e: zoom(1.1))
        win.bind('<Control-minus>', lambda e: zoom(0.9))
        win.bind('<Control-0>', lambda e: reset_view())
        win.bind('<space>', lambda e: set_pan_mode())
        win.bind('<Up>', lambda e: zoom(1.1))  # Pfeiltaste nach oben = Zoomen rein
        win.bind('<Down>', lambda e: zoom(0.9))  # Pfeiltaste nach unten = Zoomen raus
        
        # Initiales Bild anzeigen
        update_canvas()
        
        # Verzögerte Aktualisierung für korrekte Zentrierung beim ersten Laden
        def delayed_center():
            win.update_idletasks()  # Warte bis das Fenster vollständig gezeichnet ist
            update_canvas()  # Aktualisiere mit korrekter Canvas-Größe
        
        win.after(100, delayed_center)  # Führe nach 100ms aus
        
        # Fenster schließen
        win.protocol("WM_DELETE_WINDOW", safe_close_window)
        
    def create_tooltip(self, widget, text):
        """Erstellt einen Tooltip für ein Widget"""
        def show_tooltip(event):
            tooltip = tk.Toplevel()
            tooltip.wm_overrideredirect(True)
            tooltip.wm_geometry(f"+{event.x_root+10}+{event.y_root+10}")
            
            label = tk.Label(tooltip, text=text, justify=tk.LEFT,
                           background="#ffffe0", relief=tk.SOLID, borderwidth=1)
            label.pack()
            
            def hide_tooltip():
                tooltip.destroy()
                
            widget.tooltip = tooltip
            widget.bind('<Leave>', lambda e: hide_tooltip())
            
        widget.bind('<Enter>', show_tooltip)

    def on_close(self):
        # Fensterposition speichern
        try:
            geometry = self.geometry()
            # Parse geometry string "widthxheight+x+y"
            if '+' in geometry:
                size_pos = geometry.split('+')
                size = size_pos[0]
                x = int(size_pos[1])
                y = int(size_pos[2])
                
                self.config_manager.set_setting('display.window_x', x)
                self.config_manager.set_setting('display.window_y', y)
                
                # Fenstergröße extrahieren
                if 'x' in size:
                    width, height = size.split('x')
                    self.config_manager.set_setting('display.window_width', int(width))
                    self.config_manager.set_setting('display.window_height', int(height))
        except Exception as e:
            write_detailed_log("warning", "Fehler beim Speichern der Fensterposition", str(e))
        
        # Ordnerpfad speichern
        try:
            if self.source_dir:
                # Speichere in Konfiguration
                self.config_manager.set_setting('paths.last_folder', self.source_dir)
                
                # Kompatibilität: Auch in separate Datei
                with open(LAST_FOLDER_FILE, 'w', encoding='utf-8') as f:
                    f.write(self.source_dir)
        except Exception as e:
            write_detailed_log("warning", "Fehler beim Speichern des letzten Ordners", str(e))
        
        # Checkbox-Wert speichern
        try:
            if hasattr(self, 'filter_zero_var'):
                self.config_manager.set_setting('display.filter_zero_codes', self.filter_zero_var.get())
        except Exception as e:
            write_detailed_log("warning", "Fehler beim Speichern der Checkbox-Einstellung", str(e))
        
        # Aktuelle Sprache speichern
        try:
            current_language = self.json_config.get('localization', {}).get('current_language', 'en')
            self.config.set_setting('localization.current_language', current_language)
            write_detailed_log("info", "Aktuelle Sprache gespeichert", f"Sprache: {current_language}")
        except Exception as e:
            write_detailed_log("warning", "Fehler beim Speichern der Spracheinstellung", str(e))
        
        # Log-Dateien leeren
        try:
            # OCR-Log leeren
            with open(LOG_FILE, 'w', encoding='utf-8') as f:
                f.write('')
            # Detail-Log leeren
            with open(DETAILED_LOG_FILE, 'w', encoding='utf-8') as f:
                f.write('')
        except Exception as e:
            print(f"Fehler beim Leeren der Log-Dateien: {e}")
        
        self.destroy()

    def safe_show_image(self):
        """Sichere Bildanzeige mit zusätzlichen Prüfungen"""
        try:
            # Prüfe, ob das Fenster bereit ist
            if not self.winfo_exists():
                print("Fenster existiert nicht mehr, überspringe Bildanzeige")
                return
            
            # Warte kurz, damit das Fenster vollständig initialisiert ist
            self.update_idletasks()
            
            # Prüfe, ob der Canvas bereit ist
            if not hasattr(self, 'canvas') or not self.canvas.winfo_exists():
                print("Canvas nicht bereit, versuche erneut in 100ms")
                self.after(100, self.safe_show_image)
                return
            
            # Zusätzliche Prüfung: Warte bis das Fenster vollständig gezeichnet ist
            if not self.winfo_viewable():
                print("Fenster noch nicht sichtbar, versuche erneut in 200ms")
                self.after(200, self.safe_show_image)
                return
            
            print("Fenster bereit, zeige Bild an...")
            self.show_image()
        except Exception as e:
            print(f"Fehler in safe_show_image: {e}")
            import traceback
            traceback.print_exc()
            # Versuche es erneut nach einer kurzen Verzögerung
            self.after(200, self.safe_show_image)

    def on_damage_description_change(self, event):
        """Wird aufgerufen, wenn sich der Text im Damage Description Feld ändert"""
        # Markiere, dass sich der Text geändert hat
        self._damage_text_changed = True
        
        # Verzögertes Speichern (1.5 Sekunden nach dem letzten Tastendruck)
        if self._damage_save_timer:
            self.after_cancel(self._damage_save_timer)
        
        self._damage_save_timer = self.after(1500, self._delayed_save_damage_text)
    
    def _delayed_save_damage_text(self):
        """Speichert den Damage-Text mit Verzögerung"""
        if self._damage_text_changed:
            self._damage_text_changed = False
            self._damage_save_timer = None
            # Nur speichern, wenn sich der Text wirklich geändert hat
            self.save_current_evaluation()
            write_detailed_log("info", "Damage-Text verzögert gespeichert")
    
    def _force_save_damage_text(self):
        """Erzwingt das sofortige Speichern des Damage-Texts"""
        if self._damage_text_changed:
            if self._damage_save_timer:
                self.after_cancel(self._damage_save_timer)
                self._damage_save_timer = None
            self._damage_text_changed = False
            self.save_current_evaluation()
            write_detailed_log("info", "Damage-Text sofort gespeichert")

    def on_correct_changed(self, event):
        """Wird aufgerufen, wenn sich der Korrekt-Dropdown ändert"""
        # Automatisches Speichern bei Änderungen
        self.save_current_evaluation()


    def reset_all_image_evaluations(self):
        """Setzt für alle Bilder im aktuellen Ordner die Felder damage_categories und image_types auf leere Listen (mit Warnung)."""
        if not self.source_dir or not self.files:
            messagebox.showinfo("Info", "Kein Bilderordner geladen.")
            return
        if not messagebox.askyesno(
            "Achtung!",
            "Diese Funktion setzt ALLE Bewertungen (Schadenskategorien und Bildarten) für ALLE Bilder im aktuellen Ordner zurück!\n\nFortfahren?",
            icon=messagebox.WARNING
        ):
            return
        count = 0
        for fname in self.files:
            path = os.path.join(self.source_dir, fname)
            exif_data = get_exif_usercomment(path)
            if exif_data is None:
                continue
            exif_data["damage_categories"] = []
            exif_data["image_types"] = []
            if save_exif_usercomment(path, exif_data):
                count += 1
        self.invalidate_evaluation_cache()
        self.update_evaluation_progress()
        # Aktualisiere die Kürzel-Tabelle
        if hasattr(self, 'refresh_kurzel_table'):
            self.refresh_kurzel_table()
        messagebox.showinfo("Fertig", f"Bewertungen für {count} Bilder wurden zurückgesetzt.")

    def ocr_method_white_box(self, image):
        """Findet eine weiße Box im Bild, schneidet sie aus und wendet OCR darauf an."""
        import cv2
        import numpy as np

        try:
            # Bild für OpenCV vorbereiten
            img_cv = np.array(image.convert('RGB'))
            gray = cv2.cvtColor(img_cv, cv2.COLOR_RGB2GRAY)
            
            # Binarisierung, um helle Bereiche zu finden (das weiße Kästchen)
            # Der Schwellenwert 220 ist ein guter Startpunkt für fast weiße Hintergründe
            _, thresh = cv2.threshold(gray, 220, 255, cv2.THRESH_BINARY)
            
            # Finde Konturen der weißen Flächen
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            best_rect = None
            max_area = 0
            
            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)
                area = w * h
                # Filtere nach sinnvollen Größen, um Rauschen zu vermeiden
                if area > max_area and w > 50 and h > 20 and w < 500 and h < 200:
                    max_area = area
                    best_rect = (x, y, w, h)
            
            if best_rect:
                x, y, w, h = best_rect
                # Schneide die gefundene Box aus dem Originalbild aus
                cropped_image = image.crop((x, y, x + w, y + h))
                
                # Wende die verbesserte OCR-Methode auf den zugeschnittenen Bereich an
                result = self.improved_ocr.extract_text_with_confidence(cropped_image)
                if result:
                    return result
            
            # Wenn keine Box gefunden wurde oder OCR fehlschlägt
            return {'text': None, 'confidence': 0.0, 'raw_text': 'No white box found', 'method': 'white_box'}
        
        except Exception as e:
            write_detailed_log("error", "Fehler in ocr_method_white_box", str(e), exception=e)
            return {'text': None, 'confidence': 0.0, 'raw_text': str(e), 'method': 'white_box_error'}
    def ocr_method_feste_koordinaten(self, image, debug=False):
        """Schnelle OCR nur auf festem Bereich oben links. Optional Debug-Vorschau."""
        import numpy as np
        # Koordinaten aus der Konfiguration
        crop_coords = self.json_config.get('crop_coordinates', {})
        x = crop_coords.get('x', 10)
        y = crop_coords.get('y', 10)
        w = crop_coords.get('w', 60)
        h = crop_coords.get('h', 35)
        roi = image.crop((x, y, x + w, y + h))
        # Optional: Vorschau anzeigen
        if debug:
            try:
                import matplotlib.pyplot as plt
                plt.figure("OCR Debug: Fester Bereich")
                plt.imshow(roi)
                plt.title("Ausgeschnittener Bereich für OCR")
                plt.show()
            except Exception as e:
                print(f"Debug-Vorschau fehlgeschlagen: {e}")
        # OCR auf dem kleinen Bereich
        import easyocr
        reader = easyocr.Reader(['de', 'en'], gpu=False)
        # Dynamische Whitelist aus gültigen Kürzeln
        allowlist = get_dynamic_whitelist(self.valid_kurzel)
        result = reader.readtext(np.array(roi), allowlist=allowlist, detail=0)
        text = ''.join(result).upper() if result else None
        
        # Alternative Kürzel-Korrektur
        if text and self.json_config.get('ocr_settings', {}).get('alternative_kurzel_enabled', True):
            alternative_kurzel = self.json_config.get('alternative_kurzel', {})
            corrected_text = correct_alternative_kurzel(text, alternative_kurzel)
            if corrected_text != text and corrected_text in self.valid_kurzel:
                text = corrected_text
        
        return {'text': text, 'confidence': 1.0 if text else 0.0, 'raw_text': text or '', 'method': 'feste_koordinaten'}

    def ocr_method_tesseract(self, image, debug=False):
        """OCR mit Tesseract auf festem Bereich oben links, Whitelist aus gültigen Kürzeln."""
        import numpy as np
        # Koordinaten aus der Konfiguration
        crop_coords = self.json_config.get('crop_coordinates', {})
        x = crop_coords.get('x', 10)
        y = crop_coords.get('y', 10)
        w = crop_coords.get('w', 60)
        h = crop_coords.get('h', 35)
        roi = image.crop((x, y, x + w, y + h))
        # Optional: Vorschau anzeigen
        if debug:
            try:
                import matplotlib.pyplot as plt
                plt.figure("OCR Debug: Tesseract Bereich")
                plt.imshow(roi)
                plt.title("Ausgeschnittener Bereich für OCR (Tesseract)")
                plt.show()
            except Exception as e:
                print(f"Debug-Vorschau fehlgeschlagen: {e}")
        # Dynamische Whitelist aus gültigen Kürzeln
        whitelist = get_dynamic_whitelist(self.valid_kurzel)
        custom_config = f'-c tessedit_char_whitelist={whitelist} --psm 7'
        # OCR mit Tesseract
        roi_np = np.array(roi)
        import cv2
        if len(roi_np.shape) == 3:
            roi_np = cv2.cvtColor(roi_np, cv2.COLOR_RGB2GRAY)
        # Binarisierung für bessere Ergebnisse
        _, bw = cv2.threshold(roi_np, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        text = pytesseract.image_to_string(bw, config=custom_config)
        text = text.strip().replace("\n", "").upper()
        
        # Alternative Kürzel-Korrektur
        if text and self.json_config.get('ocr_settings', {}).get('alternative_kurzel_enabled', True):
            alternative_kurzel = self.json_config.get('alternative_kurzel', {})
            corrected_text = correct_alternative_kurzel(text, alternative_kurzel)
            if corrected_text != text and corrected_text in self.valid_kurzel:
                final = corrected_text
        else:
            # Fuzzy-Matching gegen gültige Kürzel
            from difflib import get_close_matches
            match = get_close_matches(text, self.valid_kurzel, n=1, cutoff=0.7)
            final = match[0] if match else text
        
        return {'text': final, 'confidence': 1.0 if final in self.valid_kurzel else 0.5, 'raw_text': text, 'method': 'tesseract'}

    def ocr_method_improved_small_text(self, image, debug=False):
        """Verbesserte OCR für kleine Textbereiche mit optimierter Vorverarbeitung"""
        import numpy as np
        import cv2
        from collections import Counter
        
        # Koordinaten aus der Konfiguration
        crop_coords = self.json_config.get('crop_coordinates', {})
        x = crop_coords.get('x', 10)
        y = crop_coords.get('y', 10)
        w = crop_coords.get('w', 60)
        h = crop_coords.get('h', 35)
        roi = image.crop((x, y, x + w, y + h))
        
        # Optional: Vorschau anzeigen
        if debug:
            try:
                import matplotlib.pyplot as plt
                plt.figure("OCR Debug: Verbesserte Methode")
                plt.imshow(roi)
                plt.title("Ausgeschnittener Bereich für OCR (Verbessert)")
                plt.show()
            except Exception as e:
                print(f"Debug-Vorschau fehlgeschlagen: {e}")
        
        # Bildvorverarbeitung für bessere OCR-Ergebnisse
        roi_np = np.array(roi)
        
        # 1. Vergrößerung für bessere Erkennung
        scale_factor = 3
        roi_resized = cv2.resize(roi_np, (w * scale_factor, h * scale_factor), interpolation=cv2.INTER_CUBIC)
        
        # 2. Graustufen-Konvertierung
        if len(roi_resized.shape) == 3:
            gray = cv2.cvtColor(roi_resized, cv2.COLOR_RGB2GRAY)
        else:
            gray = roi_resized
        
        # 3. Kontrastverbesserung
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        enhanced = clahe.apply(gray)
        
        # 4. Rauschreduzierung
        denoised = cv2.medianBlur(enhanced, 3)
        
        # 5. Schärfung
        kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
        sharpened = cv2.filter2D(denoised, -1, kernel)
        
        # 6. Binarisierung mit adaptivem Schwellenwert
        binary = cv2.adaptiveThreshold(sharpened, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        
        # 7. Morphologische Operationen für bessere Textqualität
        kernel = np.ones((2,2), np.uint8)
        cleaned = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        
        # OCR mit EasyOCR auf dem vorverarbeiteten Bild
        import easyocr
        reader = easyocr.Reader(['en'], gpu=False)  # Nur Englisch für bessere Buchstaben-Erkennung
        
        # Dynamische Whitelist aus gültigen Kürzeln
        allowlist = get_dynamic_whitelist(self.valid_kurzel)
        
        # OCR mit verschiedenen Konfigurationen versuchen
        results = []
        
        # Versuch 1: Mit Whitelist
        try:
            result1 = reader.readtext(cleaned, allowlist=allowlist, detail=0)
            if result1:
                results.extend(result1)
        except:
            pass
        
        # Versuch 2: Ohne Whitelist (manchmal besser für Buchstaben)
        try:
            result2 = reader.readtext(cleaned, detail=0)
            if result2:
                results.extend(result2)
        except:
            pass
        
        # Versuch 3: Mit dem ursprünglichen Bild
        try:
            result3 = reader.readtext(roi_np, allowlist=allowlist, detail=0)
            if result3:
                results.extend(result3)
        except:
            pass
        
        # Nur alphanumerische Ergebnisse bereinigen
        cleaned_results = [''.join(c for c in r.upper() if c.isalnum()) for r in results if r]
        
        # Häufigstes Ergebnis nehmen (Voting)
        if cleaned_results:
            text = Counter(cleaned_results).most_common(1)[0][0]
        else:
            text = None
        
        # Alternative Kürzel-Korrektur und Fuzzy-Matching
        if text:
            # Alternative Kürzel-Korrektur
            if self.json_config.get('ocr_settings', {}).get('alternative_kurzel_enabled', True):
                alternative_kurzel = self.json_config.get('alternative_kurzel', {})
                corrected_text = correct_alternative_kurzel(text, alternative_kurzel)
                if corrected_text != text and corrected_text in self.valid_kurzel:
                    final = corrected_text
                else:
                    # Fuzzy-Matching gegen gültige Kürzel
                    from difflib import get_close_matches
                    match = get_close_matches(text, self.valid_kurzel, n=1, cutoff=0.6)
                    final = match[0] if match else text
            else:
                # Fuzzy-Matching gegen gültige Kürzel
                from difflib import get_close_matches
                match = get_close_matches(text, self.valid_kurzel, n=1, cutoff=0.6)
                final = match[0] if match else text
        else:
            final = None
        
        return {
            'text': final, 
            'confidence': 1.0 if final in self.valid_kurzel else 0.5, 
            'raw_text': text or '', 
            'method': 'improved_small_text'
        }

    def debug_ocr_comparison(self, image_path):
        """Debug-Funktion: Vergleicht verschiedene OCR-Methoden auf einem Bild"""
        try:
            img = Image.open(image_path)
            
            # Alle verfügbaren OCR-Methoden testen
            methods = {
                'Verbesserte Methode': lambda: self.improved_ocr.extract_text_with_confidence(img),
                'Weiße-Box-Erkennung': lambda: self.ocr_method_white_box(img),
                'Feste Koordinaten': lambda: self.ocr_method_feste_koordinaten(img, debug=True),
                'Tesseract': lambda: self.ocr_method_tesseract(img, debug=True),
                'Verbesserte kleine Texte': lambda: self.ocr_method_improved_small_text(img, debug=True)
            }
            
            results = {}
            for method_name, method_func in methods.items():
                try:
                    result = method_func()
                    results[method_name] = result
                except Exception as e:
                    results[method_name] = {'text': f'Fehler: {e}', 'confidence': 0.0, 'raw_text': str(e)}
            
            # Debug-Fenster erstellen
            debug_window = tk.Toplevel(self)
            debug_window.title("OCR-Methoden Vergleich")
            debug_window.geometry("800x600")
            
            # Text-Widget für Ergebnisse
            text_widget = tk.Text(debug_window, wrap=tk.WORD, font=("Courier", 10))
            text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            # Ergebnisse anzeigen
            text_widget.insert(tk.END, f"OCR-Vergleich für: {os.path.basename(image_path)}\n")
            text_widget.insert(tk.END, "=" * 60 + "\n\n")
            
            for method_name, result in results.items():
                text_widget.insert(tk.END, f"Methode: {method_name}\n")
                text_widget.insert(tk.END, f"  Roher Text: {result.get('raw_text', 'N/A')}\n")
                text_widget.insert(tk.END, f"  Finaler Text: {result.get('text', 'N/A')}\n")
                text_widget.insert(tk.END, f"  Confidence: {result.get('confidence', 0.0):.2f}\n")
                text_widget.insert(tk.END, f"  Methode: {result.get('method', 'N/A')}\n")
                text_widget.insert(tk.END, "-" * 40 + "\n\n")
            
            # Scrollbar
            scrollbar = ttk.Scrollbar(debug_window, orient=tk.VERTICAL, command=text_widget.yview)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            text_widget.configure(yscrollcommand=scrollbar.set)
            
            # Schließen-Button
            close_button = ttk.Button(debug_window, text="Schließen", command=debug_window.destroy)
            close_button.pack(pady=10)
            
        except Exception as e:
            messagebox.showerror("Fehler", f"Debug-Vergleich fehlgeschlagen: {e}")
    
    def add_debug_menu(self):
        """Fügt Debug-Menü hinzu"""
        if hasattr(self, 'debug_menu'):
            return
            
        # Debug-Menü als Popup-Menü erstellen
        self.debug_menu = tk.Menu(self, tearoff=0)
        
        # OCR-Vergleich für aktuelles Bild
        self.debug_menu.add_command(
            label="OCR-Methoden vergleichen", 
            command=lambda: self.debug_ocr_comparison(os.path.join(self.source_dir, self.files[self.index])) if hasattr(self, 'source_dir') and hasattr(self, 'files') and hasattr(self, 'index') and self.files else messagebox.showwarning("Warnung", "Kein Bild geladen")
        )
        
        # Crop-Bereich anzeigen
        self.debug_menu.add_command(
            label="Crop-Bereich anzeigen",
            command=self.show_crop_debug
        )
        
        # Debug-Button zu den rechten Buttons hinzufügen
        if hasattr(self, 'right_buttons'):
            ttk.Button(self.right_buttons, text="Debug", command=self.show_debug_menu).pack(side=tk.RIGHT, padx=(5, 0))
    
    def show_debug_menu(self):
        """Zeigt das Debug-Menü als Popup an"""
        try:
            self.debug_menu.post(self.winfo_pointerx(), self.winfo_pointery())
        except Exception as e:
            messagebox.showerror("Fehler", f"Debug-Menü konnte nicht angezeigt werden: {e}")
    
    def show_crop_debug(self):
        """Zeigt den aktuellen Crop-Bereich in einem separaten Fenster an"""
        if not hasattr(self, 'source_dir') or not hasattr(self, 'files') or not hasattr(self, 'index') or not self.files:
            messagebox.showwarning("Warnung", "Kein Bild geladen")
            return
            
        try:
            img_path = os.path.join(self.source_dir, self.files[self.index])
            img = Image.open(img_path)
            
            # Crop-Koordinaten
            x, y, w, h = self.get_cutout_coordinates()
            crop_img = img.crop((x, y, x + w, y + h))
            
            # Debug-Fenster
            debug_window = tk.Toplevel(self)
            debug_window.title("Crop-Bereich Debug")
            debug_window.geometry("600x400")
            
            # Frames
            left_frame = ttk.Frame(debug_window)
            left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            right_frame = ttk.Frame(debug_window)
            right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            # Originalbild
            ttk.Label(left_frame, text="Originalbild mit Crop-Bereich:").pack()
            original_canvas = tk.Canvas(left_frame, bg='white', width=300, height=200)
            original_canvas.pack()
            
            # Originalbild skalieren und anzeigen
            display_img = img.copy()
            display_img.thumbnail((THUMBNAIL_LARGE_WIDTH, THUMBNAIL_LARGE_HEIGHT), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(display_img)
            original_canvas.create_image(150, 100, image=photo, anchor=tk.CENTER)
            original_canvas.image = photo
            
            # Crop-Bereich markieren
            scale_x = display_img.width / img.width
            scale_y = display_img.height / img.height
            scaled_x = int(x * scale_x)
            scaled_y = int(y * scale_y)
            scaled_w = int(w * scale_x)
            scaled_h = int(h * scale_y)
            
            original_canvas.create_rectangle(
                scaled_x, scaled_y, scaled_x + scaled_w, scaled_y + scaled_h,
                outline="red", width=2
            )
            
            # Crop-Bild
            ttk.Label(right_frame, text="Ausgeschnittener Bereich:").pack()
            crop_canvas = tk.Canvas(right_frame, bg='white', width=300, height=200)
            crop_canvas.pack()
            
            # Crop-Bild skalieren und anzeigen
            crop_display = crop_img.copy()
            crop_display.thumbnail((THUMBNAIL_LARGE_WIDTH, THUMBNAIL_LARGE_HEIGHT), Image.Resampling.LANCZOS)
            crop_photo = ImageTk.PhotoImage(crop_display)
            crop_canvas.create_image(150, 100, image=crop_photo, anchor=tk.CENTER)
            crop_canvas.image = crop_photo
            
            # Informationen
            info_frame = ttk.Frame(debug_window)
            info_frame.pack(fill=tk.X, padx=10, pady=5)
            
            info_text = f"""
Koordinaten: X={x}, Y={y}, Breite={w}, Höhe={h}
Original-Größe: {img.size[0]}x{img.size[1]}
Crop-Größe: {crop_img.size[0]}x{crop_img.size[1]}
            """
            
            info_label = ttk.Label(info_frame, text=info_text, font=("Courier", 9))
            info_label.pack()
            
        except Exception as e:
            messagebox.showerror("Fehler", f"Crop-Debug fehlgeschlagen: {e}")
    
    # Zoom & Drawing Functions für Hauptfenster
    def main_zoom(self, factor_change):
        """Zoom-Funktion für Hauptfenster"""
        self.main_zoom_factor += factor_change
        self.main_zoom_factor = max(0.1, min(5.0, self.main_zoom_factor))
        self.main_zoom_label.config(text=f"{int(self.main_zoom_factor * 100)}%")
        self.main_update_canvas_zoom()
    
    def main_reset_zoom(self):
        """Reset Zoom für Hauptfenster"""
        self.main_zoom_factor = 1.0
        self.main_pan_x = 0
        self.main_pan_y = 0
        self.main_zoom_label.config(text="100%")
        self.main_update_canvas_zoom()
    
    def main_update_canvas_zoom(self):
        """Aktualisiert das Canvas mit aktuellem Zoom"""
        if not hasattr(self, 'photo') or not self.photo:
            return
        
        try:
            # Original-Bild laden
            if not self.files or self.index >= len(self.files):
                return
            
            filename = self.files[self.index]
            path = os.path.join(self.source_dir, filename)
            original_img = Image.open(path)
            
            # Zoom anwenden
            w, h = original_img.size
            new_w = int(w * self.main_zoom_factor)
            new_h = int(h * self.main_zoom_factor)
            
            if new_w > 0 and new_h > 0:
                zoomed_img = original_img.resize((new_w, new_h), Image.LANCZOS)
                self.main_current_tk_image = ImageTk.PhotoImage(zoomed_img)
                
                # Canvas löschen und neues Bild zeichnen
                self.canvas.delete("all")
                self.canvas.create_image(400 + self.main_pan_x, 250 + self.main_pan_y, 
                                       image=self.main_current_tk_image, anchor=tk.CENTER)
                
                # OCR-Tag Label neu positionieren
                self.ocr_tag_label.place(x=10 + self.main_pan_x, y=10 + self.main_pan_y)
                
        except Exception as e:
            print(f"Fehler beim Zoom-Update: {e}")
    
    def on_tab_changed(self, event):
        """Handler für Tab-Wechsel"""
        current_tab = self.notebook.index(self.notebook.select())
        
        if current_tab == 0:  # Einzelbild
            self.view_mode = 'single'
            # Falls aus Galerie gewechselt, Bild neu laden
            if self.files and self.index < len(self.files):
                self.show_image()
        elif current_tab == 1:  # Galerie
            self.view_mode = 'gallery'
            self.create_gallery_view()
    
    def set_draw_mode(self, mode):
        """Setzt den Zeichenmodus"""
        self.draw_mode = mode
        
        # Button-Highlighting aktualisieren
        for btn in [self.tool_none_btn, self.tool_arrow_btn, 
                    self.tool_circle_btn, self.tool_rect_btn]:
            btn.configure(bg='white', relief='flat')
        
        if mode is None:
            self.tool_none_btn.configure(bg=COLORS['bg_light'], relief='solid')
            self.canvas.config(cursor='arrow')
        elif mode == 'arrow':
            self.tool_arrow_btn.configure(bg=COLORS['primary'], relief='solid')
            self.canvas.config(cursor='crosshair')
        elif mode == 'circle':
            self.tool_circle_btn.configure(bg=COLORS['primary'], relief='solid')
            self.canvas.config(cursor='crosshair')
        elif mode == 'rectangle':
            self.tool_rect_btn.configure(bg=COLORS['primary'], relief='solid')
            self.canvas.config(cursor='crosshair')

    def zoom_in_canvas(self):
        """Zoomt ins Bild hinein"""
        self.zoom_factor = min(self.zoom_factor * 1.2, 5.0)
        self.update_zoom_display()
        self.redraw_image_with_zoom()

    def zoom_out_canvas(self):
        """Zoomt aus dem Bild heraus"""
        self.zoom_factor = max(self.zoom_factor / 1.2, 0.1)
        self.update_zoom_display()
        self.redraw_image_with_zoom()

    def zoom_reset_canvas(self):
        """Setzt Zoom zurück"""
        self.zoom_factor = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.update_zoom_display()
        self.redraw_image_with_zoom()

    def update_zoom_display(self):
        """Aktualisiert die Zoom-Prozent-Anzeige"""
        zoom_percent = int(self.zoom_factor * 100)
        self.zoom_display.config(text=f"{zoom_percent}%")

    def redraw_image_with_zoom(self):
        """Zeichnet Bild mit aktuellem Zoom und Pan neu"""
        if not hasattr(self, 'current_image') or not self.current_image:
            return
        
        try:
            # Original-Bild laden
            img = self.current_image.copy()
            
            # Zoom anwenden
            new_width = int(img.width * self.zoom_factor)
            new_height = int(img.height * self.zoom_factor)
            if new_width > 0 and new_height > 0:
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Canvas aktualisieren
            self.photo = ImageTk.PhotoImage(img)
            
            # Lösche NUR das alte Bild (nicht die Zeichnungen!)
            if hasattr(self, 'canvas_image_id'):
                self.canvas.delete(self.canvas_image_id)
            
            # Bild mit Offset zeichnen
            self.canvas_image_id = self.canvas.create_image(
                self.pan_x, self.pan_y, 
                image=self.photo, 
                anchor='nw'
            )
            
            # Stelle sicher, dass Bild hinter den Zeichnungen ist
            self.canvas.tag_lower(self.canvas_image_id)
            
            # Zoom-Anzeige aktualisieren
            self.update_zoom_display()
            
            # OCR-Tag und Zoom-Label neu positionieren (über allem)
            if hasattr(self, 'ocr_tag_label'):
                self.ocr_tag_label.lift()
            if hasattr(self, 'zoom_display'):
                self.zoom_display.lift()
        except Exception as e:
            print(f"Fehler beim Zoom-Redraw: {e}")

    def on_canvas_mouse_wheel(self, event):
        """Mausrad-Zoom"""
        if event.delta > 0:
            self.zoom_in_canvas()
        else:
            self.zoom_out_canvas()

    def on_canvas_click(self, event):
        """Canvas-Klick für Zeichnen/Pan"""
        if self.draw_mode is None:
            # Pan-Modus
            self.is_panning = True
            self.last_pan_x = event.x
            self.last_pan_y = event.y
        else:
            # Zeichen-Modus
            self.is_drawing = True
            self.drawing_start_x = event.x
            self.drawing_start_y = event.y
            self.drawing_current_x = event.x
            self.drawing_current_y = event.y
            self.temp_drawing_item = None

    def on_canvas_drag(self, event):
        """Canvas-Drag für Zeichnen/Pan"""
        if self.is_panning:
            dx = event.x - self.last_pan_x
            dy = event.y - self.last_pan_y
            self.pan_x += dx
            self.pan_y += dy
            self.last_pan_x = event.x
            self.last_pan_y = event.y
            self.redraw_image_with_zoom()
        elif self.is_drawing:
            self.drawing_current_x = event.x
            self.drawing_current_y = event.y
            self.draw_temp_shape()

    def on_canvas_release(self, event):
        """Canvas-Release für Zeichnen/Pan"""
        if self.is_panning:
            self.is_panning = False
        elif self.is_drawing:
            self.is_drawing = False
            self.finalize_drawing()

    def draw_temp_shape(self):
        """Zeichnet temporäre Form während des Zeichnens"""
        # Lösche vorherige temporäre Form
        if self.temp_drawing_item:
            self.canvas.delete(self.temp_drawing_item)
        
        if not hasattr(self, 'drawing_start_x'):
            return
            
        x1, y1 = self.drawing_start_x, self.drawing_start_y
        x2, y2 = self.drawing_current_x, self.drawing_current_y
        
        # Zeichne temporäre Form basierend auf Modus
        if self.draw_mode == 'arrow':
            # Zeichne Linie mit Pfeilspitze
            self.temp_drawing_item = self.canvas.create_line(
                x1, y1, x2, y2,
                fill=self.draw_color,
                width=self.line_width,
                arrow=tk.LAST,
                arrowshape=(16, 20, 6),
                tags='temp_drawing'
            )
        elif self.draw_mode == 'circle':
            # Zeichne Kreis (Oval mit gleichem Radius)
            radius = ((x2 - x1)**2 + (y2 - y1)**2)**0.5
            self.temp_drawing_item = self.canvas.create_oval(
                x1 - radius, y1 - radius, x1 + radius, y1 + radius,
                outline=self.draw_color,
                width=self.line_width,
                tags='temp_drawing'
            )
        elif self.draw_mode == 'rectangle':
            # Zeichne Rechteck
            self.temp_drawing_item = self.canvas.create_rectangle(
                x1, y1, x2, y2,
                outline=self.draw_color,
                width=self.line_width,
                tags='temp_drawing'
            )

    def finalize_drawing(self):
        """Finalisiert Zeichnung und speichert sie als Canvas-Item"""
        if not hasattr(self, 'drawing_start_x'):
            return
        
        x1 = self.drawing_start_x
        y1 = self.drawing_start_y
        x2 = self.drawing_current_x
        y2 = self.drawing_current_y
        
        # Erstelle permanentes Canvas-Item basierend auf Zeichenmodus
        drawing_item = None
        
        if self.draw_mode == 'arrow':
            drawing_item = self.canvas.create_line(
                x1, y1, x2, y2,
                fill=self.draw_color,
                width=self.line_width,
                arrow=tk.LAST,
                arrowshape=(16, 20, 6),
                tags='permanent_drawing'
            )
        elif self.draw_mode == 'circle':
            radius = ((x2 - x1)**2 + (y2 - y1)**2)**0.5
            drawing_item = self.canvas.create_oval(
                x1 - radius, y1 - radius, x1 + radius, y1 + radius,
                outline=self.draw_color,
                width=self.line_width,
                tags='permanent_drawing'
            )
        elif self.draw_mode == 'rectangle':
            drawing_item = self.canvas.create_rectangle(
                x1, y1, x2, y2,
                outline=self.draw_color,
                width=self.line_width,
                tags='permanent_drawing'
            )
        
        # Speichere für Undo (speichere Canvas-Item ID)
        if drawing_item:
            self.drawing_undo_stack.append(drawing_item)
            self.drawing_redo_stack.clear()
        
        # Lösche temporäre Canvas-Zeichnung
        if self.temp_drawing_item:
            self.canvas.delete(self.temp_drawing_item)
            self.temp_drawing_item = None

    def drawing_undo(self):
        """Macht letzte Zeichnung rückgängig"""
        if self.drawing_undo_stack:
            # Lösche letztes Canvas-Item
            item_id = self.drawing_undo_stack.pop()
            self.canvas.delete(item_id)
            # Speichere für Redo
            self.drawing_redo_stack.append(item_id)

    def drawing_redo(self):
        """Stellt rückgängig gemachte Zeichnung wieder her"""
        # Redo ist schwieriger mit Canvas-Items, da wir das Item nach dem Löschen nicht wiederherstellen können
        # Alternativ könnten wir die Drawing-Parameter speichern statt nur die Item-ID
        pass
    
    def clear_drawing_history(self):
        """Löscht Zeichnungs-History und alle Zeichnungen (z.B. beim Bildwechsel)"""
        self.drawing_undo_stack.clear()
        self.drawing_redo_stack.clear()
        # Lösche alle Zeichnungen vom Canvas
        self.canvas.delete('permanent_drawing')
        self.canvas.delete('temp_drawing')
    
    def save_drawing_to_file(self):
        """Speichert das gezeichnete Bild mit allen Canvas-Zeichnungen zurück zur Datei"""
        if not hasattr(self, 'current_image') or not self.files:
            messagebox.showwarning("Warnung", "Kein Bild geladen")
            return
        
        # Prüfe, ob überhaupt Zeichnungen vorhanden sind
        drawing_items = self.canvas.find_withtag('permanent_drawing')
        if not drawing_items:
            messagebox.showinfo("Info", "Keine Zeichnungen zum Speichern vorhanden")
            return
        
        try:
            from PIL import ImageDraw
            import math
            
            # Kopiere Original-Bild
            img_with_drawings = self.current_image.copy()
            draw = ImageDraw.Draw(img_with_drawings)
            
            # Durchlaufe alle Zeichnungs-Items und übertrage sie aufs Bild
            for item_id in drawing_items:
                item_type = self.canvas.type(item_id)
                coords = self.canvas.coords(item_id)
                color = self.canvas.itemcget(item_id, 'fill') or self.canvas.itemcget(item_id, 'outline')
                width = int(self.canvas.itemcget(item_id, 'width'))
                
                # Konvertiere Canvas-Koordinaten zu Bild-Koordinaten
                img_coords = []
                for i in range(0, len(coords), 2):
                    x_canvas = coords[i]
                    y_canvas = coords[i+1]
                    x_img = int((x_canvas - self.pan_x) / self.zoom_factor)
                    y_img = int((y_canvas - self.pan_y) / self.zoom_factor)
                    img_coords.extend([x_img, y_img])
                
                # Zeichne auf Bild
                if item_type == 'line':
                    # Prüfe ob Pfeil
                    arrow = self.canvas.itemcget(item_id, 'arrow')
                    if arrow and len(img_coords) >= 4:
                        # Zeichne Linie
                        draw.line(img_coords, fill=color, width=width)
                        
                        # Wenn Pfeil, zeichne Pfeilspitze
                        if arrow == 'last':
                            x1, y1, x2, y2 = img_coords[0], img_coords[1], img_coords[2], img_coords[3]
                            angle = math.atan2(y2 - y1, x2 - x1)
                            arrow_length = 15
                            arrow_angle = math.pi / 6
                            
                            x_left = x2 - arrow_length * math.cos(angle - arrow_angle)
                            y_left = y2 - arrow_length * math.sin(angle - arrow_angle)
                            x_right = x2 - arrow_length * math.cos(angle + arrow_angle)
                            y_right = y2 - arrow_length * math.sin(angle + arrow_angle)
                            
                            draw.line([x2, y2, x_left, y_left], fill=color, width=width)
                            draw.line([x2, y2, x_right, y_right], fill=color, width=width)
                    elif len(img_coords) >= 4:
                        draw.line(img_coords, fill=color, width=width)
                
                elif item_type == 'oval' and len(img_coords) >= 4:
                    draw.ellipse(img_coords, outline=color, width=width)
                
                elif item_type == 'rectangle' and len(img_coords) >= 4:
                    draw.rectangle(img_coords, outline=color, width=width)
            
            # Speichere Bild
            current_file = self.files[self.index]
            filepath = os.path.join(self.source_dir, current_file)
            
            # Erstelle Backup-Ordner, falls nicht vorhanden
            backup_dir = os.path.join(self.source_dir, "Originals")
            if not os.path.exists(backup_dir):
                os.makedirs(backup_dir)
                print(f"Backup-Ordner erstellt: {backup_dir}")
            
            # Sichere Original, falls noch nicht vorhanden
            backup_path = os.path.join(backup_dir, current_file)
            if not os.path.exists(backup_path):
                # Kopiere Original ins Backup
                import shutil
                shutil.copy2(filepath, backup_path)
                print(f"Original gesichert: {backup_path}")
            
            # Speichere Bild mit Zeichnungen
            if filepath.lower().endswith(('.jpg', '.jpeg')):
                img_with_drawings.save(filepath, 'JPEG', quality=95)
            else:
                img_with_drawings.save(filepath)
            
            # Aktualisiere current_image mit den Zeichnungen
            self.current_image = img_with_drawings
            
            messagebox.showinfo("Erfolg", f"Zeichnungen gespeichert: {current_file}\n(Original gesichert in: Originals/)")
            print(f"Zeichnungen gespeichert: {filepath}")
            
        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Speichern: {str(e)}")
            print(f"Fehler beim Speichern der Zeichnungen: {e}")
            import traceback
            traceback.print_exc()
    
    def toggle_view_mode(self):
        """Wechselt zwischen Einzelansicht und Galerie"""
        if self.view_mode == 'single':
            self.switch_to_gallery_view()
        else:
            self.switch_to_single_view()

    def on_tab_changed(self, event):
        """Behandelt Tab-Wechsel im Notebook"""
        selected_tab = event.widget.select()
        tab_text = event.widget.tab(selected_tab, "text")
        
        if tab_text == "📷 Einzelansicht":
            self.view_mode = 'single'
            if self.files and 0 <= self.index < len(self.files):
                self.show_image()
        elif tab_text == "🖼️ Galerie":
            self.view_mode = 'gallery'
            if self.files:
                self.create_gallery_view()

    def open_drawing_settings(self):
        """Öffnet Einstellungsdialog für Zeichenparameter"""
        dialog = tk.Toplevel(self)
        dialog.title("Zeichen-Einstellungen")
        dialog.geometry("400x300")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()
        
        # Zentrieren
        dialog.geometry(f"+{self.winfo_rootx() + 100}+{self.winfo_rooty() + 100}")
        
        main_frame = ttk.Frame(dialog, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Farbe
        ttk.Label(main_frame, text="Zeichenfarbe:", 
                 font=("Segoe UI", FONT_SIZES['heading'], "bold")).pack(anchor=tk.W, pady=(0, 5))
        
        color_frame = ttk.Frame(main_frame)
        color_frame.pack(fill=tk.X, pady=(0, 15))
        
        colors = [('Rot', 'red'), ('Blau', 'blue'), ('Grün', 'green'), 
                  ('Gelb', 'yellow'), ('Orange', 'orange'), ('Schwarz', 'black')]
        
        color_var = tk.StringVar(value=self.draw_color)
        for i, (name, color) in enumerate(colors):
            rb = tk.Radiobutton(color_frame, text=name, variable=color_var, 
                               value=color, font=("Segoe UI", FONT_SIZES['body']))
            rb.grid(row=i//3, column=i%3, sticky=tk.W, padx=10, pady=5)
        
        # Linienbreite
        ttk.Label(main_frame, text="Linienbreite:", 
                 font=("Segoe UI", FONT_SIZES['heading'], "bold")).pack(anchor=tk.W, pady=(10, 5))
        
        width_frame = ttk.Frame(main_frame)
        width_frame.pack(fill=tk.X, pady=(0, 15))
        
        width_var = tk.IntVar(value=self.line_width)
        widths = [1, 2, 3, 5, 8, 12]
        for width in widths:
            rb = tk.Radiobutton(width_frame, text=f"{width}px", variable=width_var,
                               value=width, font=("Segoe UI", FONT_SIZES['body']))
            rb.pack(side=tk.LEFT, padx=10)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(20, 0))
        
        def save_settings():
            self.draw_color = color_var.get()
            self.line_width = width_var.get()
            dialog.destroy()
        
        ttk.Button(button_frame, text="Übernehmen", 
                  command=save_settings).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Abbrechen", 
                  command=dialog.destroy).pack(side=tk.RIGHT)
    
    def main_set_draw_mode(self, mode):
        """Setzt den Zeichenmodus"""
        self.main_draw_mode = mode
        print(f"Zeichenmodus: {mode}")
    
    def main_set_draw_color(self, color):
        """Setzt die Zeichenfarbe"""
        self.main_draw_color = color
        print(f"Zeichenfarbe: {color}")
    
    def main_set_line_width(self, width):
        """Setzt die Linienbreite"""
        self.main_line_width = width
        print(f"Linienbreite: {width}")
    
    def main_undo(self):
        """Undo für Zeichnungen"""
        if self.main_undo_stack:
            # Implementierung später
            print("Undo")
    
    def main_redo(self):
        """Redo für Zeichnungen"""
        if self.main_redo_stack:
            # Implementierung später
            print("Redo")
    
    # Canvas Event Handlers
    def main_on_canvas_click(self, event):
        """Canvas Click Handler"""
        if self.main_draw_mode == 'pan':
            self.main_is_panning = True
            self.main_last_pan_x = event.x
            self.main_last_pan_y = event.y
        else:
            # Zeichnen starten
            self.main_is_drawing = True
            self.main_drawing_points = [(event.x, event.y)]
    
    def main_on_canvas_drag(self, event):
        """Canvas Drag Handler"""
        if self.main_is_panning:
            # Pan-Modus
            delta_x = event.x - self.main_last_pan_x
            delta_y = event.y - self.main_last_pan_y
            self.main_pan_x += delta_x
            self.main_pan_y += delta_y
            self.main_last_pan_x = event.x
            self.main_last_pan_y = event.y
            self.main_update_canvas_zoom()
        elif self.main_is_drawing:
            # Zeichnen
            self.main_drawing_points.append((event.x, event.y))
            # Temporäre Linie zeichnen
            if len(self.main_drawing_points) >= 2:
                self.canvas.create_line(self.main_drawing_points[-2], self.main_drawing_points[-1],
                                      fill=self.main_draw_color, width=self.main_line_width)
    
    def main_on_canvas_release(self, event):
        """Canvas Release Handler"""
        if self.main_is_panning:
            self.main_is_panning = False
        elif self.main_is_drawing:
            self.main_is_drawing = False
            # Zeichnung finalisieren
            if len(self.main_drawing_points) >= 2:
                self.main_draw_shape()
            self.main_drawing_points = []
    
    def main_on_canvas_wheel(self, event):
        """Canvas Mouse Wheel Handler"""
        if event.delta > 0:
            self.main_zoom(0.1)
        else:
            self.main_zoom(-0.1)
    
    def main_on_pan_start(self, event):
        """Pan Start Handler"""
        self.main_is_panning = True
        self.main_last_pan_x = event.x
        self.main_last_pan_y = event.y
    
    def main_on_pan_drag(self, event):
        """Pan Drag Handler"""
        if self.main_is_panning:
            delta_x = event.x - self.main_last_pan_x
            delta_y = event.y - self.main_last_pan_y
            self.main_pan_x += delta_x
            self.main_pan_y += delta_y
            self.main_last_pan_x = event.x
            self.main_last_pan_y = event.y
            self.main_update_canvas_zoom()
    
    def main_on_pan_end(self, event):
        """Pan End Handler"""
        self.main_is_panning = False
    
    def main_toggle_pan_mode(self, event):
        """Toggle Pan Mode"""
        if self.main_draw_mode == 'pan':
            self.main_draw_mode = 'arrow'
        else:
            self.main_draw_mode = 'pan'
        print(f"Pan-Modus: {self.main_draw_mode == 'pan'}")
    
    def main_draw_shape(self):
        """Zeichnet eine Form basierend auf dem aktuellen Modus"""
        if len(self.main_drawing_points) < 2:
            return
        
        try:
            if self.main_draw_mode == 'arrow':
                # Pfeil zeichnen
                start = self.main_drawing_points[0]
                end = self.main_drawing_points[-1]
                self.canvas.create_line(start, end, fill=self.main_draw_color, width=self.main_line_width)
            elif self.main_draw_mode == 'circle':
                # Kreis zeichnen
                start = self.main_drawing_points[0]
                end = self.main_drawing_points[-1]
                self.canvas.create_oval(start, end, outline=self.main_draw_color, width=self.main_line_width)
            elif self.main_draw_mode == 'rectangle':
                # Rechteck zeichnen
                start = self.main_drawing_points[0]
                end = self.main_drawing_points[-1]
                self.canvas.create_rectangle(start, end, outline=self.main_draw_color, width=self.main_line_width)
            elif self.main_draw_mode == 'freehand':
                # Freihand bereits gezeichnet
                pass
        except Exception as e:
            print(f"Fehler beim Zeichnen: {e}")
    
    def toggle_view_mode(self):
        """Schaltet zwischen Einzelbild- und Galerie-Ansicht um"""
        if self.view_mode == 'single':
            self.switch_to_gallery_view()
        else:
            self.switch_to_single_view()
    
    def switch_to_single_view(self):
        """Wechselt zur Einzelbild-Ansicht"""
        self.view_mode = 'single'
        # Menü-Text aktualisieren
        if hasattr(self, 'view_menu'):
            self.view_menu.entryconfig("📷 Galerie-Ansicht", label="📷 Galerie-Ansicht")
        
        # Galerie verstecken und zerstören (nur wenn ohne Tabs gearbeitet wird)
        if hasattr(self, 'gallery_frame') and self.gallery_frame and not hasattr(self, 'notebook'):
            self.gallery_frame.destroy()
            self.gallery_frame = None
        
        # Canvas und Navigation zeigen - mit expliziten Grid-Parametern
        self.canvas.grid(row=1, column=0, sticky="nsew", pady=(0, 5))
        self.nav_frame.grid(row=2, column=0, sticky="ew", pady=(0, 5))
        self.desc_frame.grid(row=3, column=0, sticky="ew", pady=(0, 5))
        
        # Bild anzeigen
        if self.files and self.index < len(self.files):
            self.show_image()
    
    def switch_to_gallery_view(self):
        """Wechselt zur Galerie-Ansicht"""
        self.view_mode = 'gallery'
        # Bei Tabs: einfach auf Galerie-Tab wechseln
        if hasattr(self, 'notebook'):
            try:
                self.notebook.select(self.gallery_view_tab)
            except Exception:
                pass
        else:
            # Fallback: alte Logik
            if hasattr(self, 'view_menu'):
                self.view_menu.entryconfig("📷 Galerie-Ansicht", label="🖼️ Einzelbild-Ansicht")
            self.canvas.grid_remove()
            self.nav_frame.grid_remove()
            self.desc_frame.grid_remove()
            self.create_gallery_view()
    
    def create_gallery_view(self):
        """Erstellt die Galerie-Ansicht im Galerie-Tab (Notebook)"""
        # Zielcontainer bestimmen: bei Tabs in gallery_view_tab, sonst left_column
        target_parent = getattr(self, 'gallery_view_tab', None) or self.left_column
        # Vorherige Inhalte entfernen
        for child in target_parent.winfo_children():
            child.destroy()
        
        # Galerie-Frame erstellen
        self.gallery_frame = ttk.Frame(target_parent, style="TFrame")
        if target_parent is self.left_column:
            self.gallery_frame.grid(row=1, column=0, sticky="nsew", pady=(0, 5))
        else:
            self.gallery_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Galerie-Header mit Filter
        header_frame = ttk.Frame(self.gallery_frame)
        header_frame.pack(fill=tk.X, pady=(5, 15), padx=10)
        
        ttk.Label(header_frame, text="🏷️ OCR-Tag Filter:", 
                 font=("Segoe UI", FONT_SIZES['heading'], "bold"),
                 foreground=COLORS['text_primary']).pack(side=tk.LEFT, padx=(0, 10))
        
        # Tag-Dropdown
        available_tags = self.get_available_ocr_tags()
        self.gallery_tag_var = tk.StringVar(value=self.gallery_current_tag or "Alle")
        tag_combo = ttk.Combobox(header_frame, textvariable=self.gallery_tag_var, 
                                values=["Alle"] + available_tags, width=20, state="readonly",
                                font=("Segoe UI", FONT_SIZES['body']))
        tag_combo.pack(side=tk.LEFT, padx=(0, 15))
        tag_combo.bind("<<ComboboxSelected>>", self.on_gallery_tag_changed)
        
        # Auto-Filter: Aktuelles Bild-Tag
        if self.files and self.index < len(self.files):
            current_tag = self.get_current_image_ocr_tag()
            if current_tag and current_tag in available_tags:
                self.gallery_tag_var.set(current_tag)
                self.gallery_current_tag = current_tag
        
        # Scrollable Frame für Thumbnails
        canvas_frame = ttk.Frame(self.gallery_frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        # Canvas mit Scrollbar für Thumbnails
        self.gallery_canvas = tk.Canvas(canvas_frame, bg=COLORS['bg_light'], 
                                       highlightthickness=0, bd=0)
        gallery_scrollbar = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.gallery_canvas.yview)
        self.gallery_scrollable_frame = ttk.Frame(self.gallery_canvas)
        
        self.gallery_scrollable_frame.bind(
            "<Configure>",
            lambda e: self.gallery_canvas.configure(scrollregion=self.gallery_canvas.bbox("all"))
        )
        
        self.gallery_canvas.create_window((0, 0), window=self.gallery_scrollable_frame, anchor="nw")
        self.gallery_canvas.configure(yscrollcommand=gallery_scrollbar.set)
        
        self.gallery_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        gallery_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Thumbnails laden
        self.load_gallery_thumbnails()
    
    def get_available_ocr_tags(self):
        """Gibt alle verfügbaren OCR-Tags zurück"""
        tags = set()
        if not self.files:
            return []
        
        for filename in self.files:
            path = os.path.join(self.source_dir, filename)
            exif_data = get_exif_usercomment(path)
            if exif_data and "TAGOCR" in exif_data:
                tags.add(exif_data["TAGOCR"])
        
        return sorted(list(tags))
    
    def get_current_image_ocr_tag(self):
        """Gibt den OCR-Tag des aktuellen Bildes zurück"""
        if not self.files or self.index >= len(self.files):
            return None
        
        filename = self.files[self.index]
        path = os.path.join(self.source_dir, filename)
        exif_data = get_exif_usercomment(path)
        
        if exif_data and "TAGOCR" in exif_data:
            return exif_data["TAGOCR"]
        return None
    
    def on_gallery_tag_changed(self, event):
        """Event-Handler für Tag-Auswahl in der Galerie"""
        selected_tag = self.gallery_tag_var.get()
        self.gallery_current_tag = selected_tag if selected_tag != "Alle" else None
        self.load_gallery_thumbnails()
    
    def load_gallery_thumbnails(self):
        """Lädt die Thumbnails für die Galerie"""
        # Alte Thumbnails löschen
        for widget in self.gallery_scrollable_frame.winfo_children():
            widget.destroy()
        
        # Bilder filtern
        filtered_files = []
        for filename in self.files:
            if self.gallery_current_tag is None:  # Alle
                filtered_files.append(filename)
            else:
                path = os.path.join(self.source_dir, filename)
                exif_data = get_exif_usercomment(path)
                if exif_data and "TAGOCR" in exif_data and exif_data["TAGOCR"] == self.gallery_current_tag:
                    filtered_files.append(filename)
        
        if not filtered_files:
            ttk.Label(self.gallery_scrollable_frame, text="📭 Keine Bilder für diesen OCR-Tag gefunden", 
                     font=("Segoe UI", FONT_SIZES['heading']),
                     foreground=COLORS['text_secondary']).pack(pady=40)
            return
        
        # Grid-Layout berechnen - mehr Spalten für bessere Übersicht
        total_images = len(filtered_files)
        if total_images <= 2:
            cols = 2
        elif total_images <= 6:
            cols = 3
        elif total_images <= 12:
            cols = 4
        else:
            cols = 5
        
        rows = (total_images + cols - 1) // cols
        
        # Thumbnails erstellen
        for i, filename in enumerate(filtered_files):
            row = i // cols
            col = i % cols
            
            # Thumbnail-Frame mit modernem Look
            thumb_frame = tk.Frame(self.gallery_scrollable_frame, 
                                  bg=COLORS['bg_medium'],
                                  relief="flat", bd=0,
                                  highlightbackground=COLORS['border'],
                                  highlightthickness=1)
            thumb_frame.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
            
            # Thumbnail-Bild laden
            try:
                path = os.path.join(self.source_dir, filename)
                img = Image.open(path)
                img.thumbnail((200, 200), Image.LANCZOS)  # Größere Thumbnails
                photo = ImageTk.PhotoImage(img)
                
                # Thumbnail-Label mit Hover-Effekt
                thumb_label = tk.Label(thumb_frame, image=photo, 
                                     cursor="hand2",
                                     bg=COLORS['bg_medium'],
                                     bd=0)
                thumb_label.image = photo  # Referenz behalten
                thumb_label.pack(pady=(8, 5), padx=8)
                
                # Info-Container
                info_frame = tk.Frame(thumb_frame, bg=COLORS['bg_medium'])
                info_frame.pack(fill=tk.X, padx=8, pady=(0, 8))
                
                # OCR-Tag Label
                exif_data = get_exif_usercomment(path)
                tag = exif_data.get("TAGOCR", "-") if exif_data else "-"
                tag_label = tk.Label(info_frame, text=tag, 
                                   font=("Segoe UI", FONT_SIZES['small'], "bold"),
                                   fg=COLORS['text_primary'],
                                   bg=COLORS['bg_medium'])
                tag_label.pack(side=tk.LEFT)
                
                # Bewertungsstatus
                is_evaluated = self.is_image_evaluated_from_cache(filename)
                status_icon = "✓" if is_evaluated else "○"
                status_color = COLORS['success'] if is_evaluated else COLORS['text_secondary']
                status_label = tk.Label(info_frame, text=status_icon, 
                                      font=("Segoe UI", FONT_SIZES['body'], "bold"),
                                      foreground=status_color,
                                      bg=COLORS['bg_medium'])
                status_label.pack(side=tk.RIGHT)
                
                # Click-Handler für gesamten Frame
                def update_hover_bg(widgets_list, bg_color):
                    for w in widgets_list:
                        try:
                            w.configure(bg=bg_color)
                        except:
                            pass
                
                all_widgets = [thumb_frame, thumb_label, info_frame, tag_label, status_label]
                for widget in all_widgets:
                    widget.bind("<Button-1>", lambda e, f=filename: self.open_image_from_gallery(f))
                    widget.bind("<Enter>", lambda e, wl=all_widgets, tf=thumb_frame: (
                        tf.configure(highlightthickness=2, highlightbackground=COLORS['primary']),
                        update_hover_bg(wl, 'white')
                    ))
                    widget.bind("<Leave>", lambda e, wl=all_widgets, tf=thumb_frame: (
                        tf.configure(highlightthickness=1, highlightbackground=COLORS['border']),
                        update_hover_bg(wl, COLORS['bg_medium'])
                    ))
                
            except Exception as e:
                print(f"Fehler beim Laden des Thumbnails für {filename}: {e}")
        
        # Grid-Gewichte setzen
        for col in range(cols):
            self.gallery_scrollable_frame.grid_columnconfigure(col, weight=1)
        for row in range(rows):
            self.gallery_scrollable_frame.grid_rowconfigure(row, weight=1)
    
    def is_image_evaluated_from_cache(self, filename):
        """Prüft ob ein Bild bereits bewertet wurde (aus Cache)"""
        try:
            if filename in self._evaluation_cache:
                cache_entry = self._evaluation_cache[filename]
                return isinstance(cache_entry, dict) and cache_entry.get('is_evaluated', False)
            return False
        except:
            return False
    
    def open_image_from_gallery(self, filename):
        """Öffnet ein Bild aus der Galerie in der Einzelansicht"""
        # Index des gewählten Bildes finden
        if filename in self.files:
            self.index = self.files.index(filename)
            self.switch_to_single_view()

class LoadingScreen:
    """Ladebildschirm mit Logo auf weißem Hintergrund"""
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("GearGeneGPT - Lade...")
        self.root.geometry("500x400")
        self.root.resizable(False, False)
        self.root.configure(bg='white')

        # Zentriere das Fenster
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (500 // 2)
        y = (self.root.winfo_screenheight() // 2) - (400 // 2)
        self.root.geometry(f"500x400+{x}+{y}")

        # Logo laden
        logo_path = resource_path('82EndoLogo.png')
        if os.path.exists(logo_path):
            img = Image.open(logo_path)
            img = img.convert('RGBA')
            # Maximal 300x300px
            img.thumbnail((THUMBNAIL_LARGE_WIDTH, THUMBNAIL_LARGE_WIDTH), Image.LANCZOS)
            self.logo_img = ImageTk.PhotoImage(img)
            logo_label = tk.Label(self.root, image=self.logo_img, bg='white')
            logo_label.pack(pady=(40, 10))
        else:
            logo_label = tk.Label(self.root, text="8.2 GEARBOX ENDOSCOPY", font=('Arial', 20, 'bold'), fg='#ff8000', bg='white')
            logo_label.pack(pady=(40, 10))

        # Lade-Animation
        self.loading_label = tk.Label(self.root, text="Lade Anwendung...", font=('Arial', 12), fg='#ff8000', bg='white')
        self.loading_label.pack(pady=(10, 10))

        # Fortschrittsbalken
        self.progress = ttk.Progressbar(self.root, mode='indeterminate', length=300)
        self.progress.pack(pady=(0, 20))
        self.progress.start()

        # Status-Text
        self.status_label = tk.Label(self.root, text="Initialisiere...", font=('Arial', 9), fg='#888', bg='white')
        self.status_label.pack()

        # Version
        version_label = tk.Label(self.root, text="Version 2.0", font=('Arial', 8), fg='#aaa', bg='white')
        version_label.pack(side='bottom', pady=(20, 0))

        # Lade-Animation starten
        self.dots = 0
        self.animation_job = None
        self.animate_loading()

        # Fenster schließen verhindern
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)

    def animate_loading(self):
        dots_text = "." * (self.dots + 1)
        self.loading_label.config(text=f"Lade Anwendung{dots_text}")
        self.dots = (self.dots + 1) % 4
        self.animation_job = self.root.after(500, self.animate_loading)

    def update_status(self, status):
        self.status_label.config(text=status)
        self.root.update()

    def close(self):
        self.progress.stop()
        if self.animation_job:
            self.root.after_cancel(self.animation_job)
            self.animation_job = None
        self.root.destroy()
class AnalysisWindow:
    """Dediziertes Fenster für OCR-Analyse mit Live-Vorschau und Ergebnis-Bearbeitung"""
    
    def __init__(self, parent, source_dir, files, valid_kurzel, json_config):
        self.parent = parent
        self.source_dir = source_dir
        self.files = files
        self.valid_kurzel = valid_kurzel
        self.json_config = json_config
        self.results = []
        self.current_index = 0
        
        # Fenster erstellen
        self.window = tk.Toplevel(parent)
        self.window.title("OCR-Analyse")
        self.window.geometry("1920x1080")  # Full HD Auflösung
        self.window.state('zoomed')  # Maximiert auf Windows
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Variablen
        self.analyzing = False
        self.ocr_settings = json_config.get('ocr_settings', {})
        self.active_method = self.ocr_settings.get('active_method', 'improved')
        self.debug_preview = self.ocr_settings.get('debug_preview', False)
        
        # Cutout-Koordinaten aus Konfiguration laden
        saved_coords = json_config.get('cutout_coordinates', {})
        self.cutout_coords = {
            'x': saved_coords.get('x', 10),
            'y': saved_coords.get('y', 10),
            'w': saved_coords.get('w', 60),
            'h': saved_coords.get('h', 35)
        }
        
        # Debug-Ausgabe
        print(f"Geladene Koordinaten: {self.cutout_coords}")
        print(f"JSON-Konfiguration cutout_coordinates: {json_config.get('cutout_coordinates', 'NICHT GEFUNDEN')}")
        
        # GUI erstellen
        self.create_widgets()
        
        # Zeige erstes Bild zur Konfiguration
        self.show_first_image()
    
    def create_widgets(self):
        """Erstellt die GUI-Elemente"""
        # Hauptframe
        main_frame = ttk.Frame(self.window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Oberer Bereich: Fortschritt und Status
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Status-Label (größer für Full HD)
        self.status_label = ttk.Label(top_frame, text="Konfiguriere Analyse-Einstellungen", font=("TkDefaultFont", 14, "bold"))
        self.status_label.pack(anchor='w')
        
        # Fortschrittsbalken
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(top_frame, variable=self.progress_var, maximum=len(self.files))
        self.progress_bar.pack(fill=tk.X, pady=(5, 0))
        
        # Fortschritts-Text (größer für Full HD)
        self.progress_text = ttk.Label(top_frame, text="0 / " + str(len(self.files)), font=("TkDefaultFont", 11))
        self.progress_text.pack(anchor='w', pady=(2, 0))
        
        # Mittlerer Bereich: Live-Vorschau
        middle_frame = ttk.Frame(main_frame)
        middle_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Linke Seite: Originalbild
        left_frame = ttk.LabelFrame(middle_frame, text="Originalbild")
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        self.original_canvas = tk.Canvas(left_frame, bg='white')
        self.original_canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Rechte Seite: Cutout
        right_frame = ttk.LabelFrame(middle_frame, text="Ausgeschnittener Bereich")
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        self.cutout_canvas = tk.Canvas(right_frame, bg='white')
        self.cutout_canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Unterer Bereich: Ergebnisse
        bottom_frame = ttk.LabelFrame(main_frame, text="Analyse-Ergebnisse")
        bottom_frame.pack(fill=tk.BOTH, expand=True)
        
        # Treeview für Ergebnisse mit Bildern
        columns = ('Bild', 'Datei', 'Original', 'Cutout', 'Erkannt', 'Kürzel', 'Gruppe', 'Konfidenz', 'Methode')
        self.results_tree = ttk.Treeview(bottom_frame, columns=columns, show='headings', height=15)
        
        # Spalten konfigurieren für Full HD
        column_widths = {
            'Bild': 120, 'Datei': 200, 'Original': 150, 'Cutout': 150, 
            'Erkannt': 120, 'Kürzel': 120, 'Gruppe': 100, 'Konfidenz': 100, 'Methode': 120
        }
        for col in columns:
            self.results_tree.heading(col, text=col)
            self.results_tree.column(col, width=column_widths.get(col, 120))
        
        # Scrollbar für Treeview
        tree_scroll = ttk.Scrollbar(bottom_frame, orient=tk.VERTICAL, command=self.results_tree.yview)
        self.results_tree.configure(yscrollcommand=tree_scroll.set)
        
        self.results_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))

        # Großer Start-Button
        self.start_button = ttk.Button(button_frame, text="🚀 ANALYSE STARTEN", command=self.start_analysis, style="Accent.TButton")
        self.start_button.pack(side=tk.LEFT, padx=(0, 10))

        self.stop_button = ttk.Button(button_frame, text="Analyse stoppen", command=self.stop_analysis, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=(0, 10))

        self.abort_button = ttk.Button(button_frame, text="Abbrechen", command=self.abort_analysis, style="Danger.TButton")
        self.abort_button.pack(side=tk.LEFT, padx=(0, 10))

        self.save_button = ttk.Button(button_frame, text="Ergebnisse speichern", command=self.save_results, state=tk.DISABLED)
        self.save_button.pack(side=tk.LEFT, padx=(0, 10))

        self.close_button = ttk.Button(button_frame, text="Schließen", command=self.on_close)
        self.close_button.pack(side=tk.RIGHT)
        
        # Event-Binding für Treeview
        self.results_tree.bind('<Double-1>', self.on_result_double_click)
        self.results_tree.bind('<Button-1>', self.on_result_click)
        self.results_tree.bind('<Button-3>', self.on_result_right_click)  # Rechtsklick für Kontextmenü
        
        # Initialisiere Treeview-Widgets für Dropdowns
        self.tree_widgets = {}
        
        # OCR-Einstellungen
        ocr_frame = ttk.LabelFrame(main_frame, text="OCR-Einstellungen")
        ocr_frame.pack(fill=tk.X, pady=(0, 10))
        
        ocr_inner = ttk.Frame(ocr_frame)
        ocr_inner.pack(fill=tk.X, padx=5, pady=5)
        
        # OCR-Methode
        ttk.Label(ocr_inner, text="OCR-Methode:").pack(side=tk.LEFT, padx=(0, 5))
        self.method_var = tk.StringVar(value=self.active_method)
        method_combo = ttk.Combobox(ocr_inner, textvariable=self.method_var, 
                                   values=['improved', 'feste_koordinaten', 'old'], 
                                   state='readonly', width=15)
        method_combo.pack(side=tk.LEFT, padx=(0, 20))
        method_combo.bind('<<ComboboxSelected>>', self.on_method_changed)
        
        # Debug-Vorschau
        self.debug_var = tk.BooleanVar(value=self.debug_preview)
        debug_check = ttk.Checkbutton(ocr_inner, text="Debug-Vorschau", variable=self.debug_var)
        debug_check.pack(side=tk.LEFT, padx=(0, 10))
        
        # Cutout-Koordinaten anzeigen
        coords_frame = ttk.LabelFrame(main_frame, text="Cutout-Koordinaten")
        coords_frame.pack(fill=tk.X, pady=(0, 10))
        
        coords_inner = ttk.Frame(coords_frame)
        coords_inner.pack(fill=tk.X, padx=5, pady=5)
        
        # X-Koordinate
        ttk.Label(coords_inner, text="X:").pack(side=tk.LEFT, padx=(0, 5))
        self.x_var = tk.StringVar(value=str(self.cutout_coords.get('x', 10)))
        x_entry = ttk.Entry(coords_inner, textvariable=self.x_var, width=5)
        x_entry.pack(side=tk.LEFT, padx=(0, 10))
        
        # Y-Koordinate
        ttk.Label(coords_inner, text="Y:").pack(side=tk.LEFT, padx=(0, 5))
        self.y_var = tk.StringVar(value=str(self.cutout_coords.get('y', 10)))
        y_entry = ttk.Entry(coords_inner, textvariable=self.y_var, width=5)
        y_entry.pack(side=tk.LEFT, padx=(0, 10))
        
        # Breite
        ttk.Label(coords_inner, text="Breite:").pack(side=tk.LEFT, padx=(0, 5))
        self.w_var = tk.StringVar(value=str(self.cutout_coords.get('w', 60)))
        w_entry = ttk.Entry(coords_inner, textvariable=self.w_var, width=5)
        w_entry.pack(side=tk.LEFT, padx=(0, 10))
        
        # Höhe
        ttk.Label(coords_inner, text="Höhe:").pack(side=tk.LEFT, padx=(0, 5))
        self.h_var = tk.StringVar(value=str(self.cutout_coords.get('h', 35)))
        h_entry = ttk.Entry(coords_inner, textvariable=self.h_var, width=5)
        h_entry.pack(side=tk.LEFT, padx=(0, 10))
        
        # Aktualisieren-Button
        update_coords_button = ttk.Button(coords_inner, text="Aktualisieren", command=self.update_preview)
        update_coords_button.pack(side=tk.RIGHT, padx=(10, 0))
        
        # Live-Update bei Koordinaten-Änderung
        self.x_var.trace('w', self.on_coords_changed)
        self.y_var.trace('w', self.on_coords_changed)
        self.w_var.trace('w', self.on_coords_changed)
        self.h_var.trace('w', self.on_coords_changed)
    
    
    def show_first_image(self):
        """Zeigt das erste Bild zur Konfiguration an"""
        if self.files:
            try:
                src = os.path.join(self.source_dir, self.files[0])
                img = Image.open(src)
                
                # Cutout erstellen mit aktuellen Einstellungen
                x, y, w, h = self.get_cutout_coordinates()
                cutout = img.crop((x, y, x + w, y + h))
                
                # Bilder anzeigen
                self.show_images(img, cutout)
                self.update_status(f"Bereit zur Analyse - {len(self.files)} Bilder geladen")
                
            except Exception as e:
                self.update_status(f"Fehler beim Laden des ersten Bildes: {e}")

    def on_method_changed(self, event=None):
        """Wird aufgerufen, wenn sich die OCR-Methode ändert"""
        self.active_method = self.method_var.get()
        self.update_preview()

    def on_coords_changed(self, *args):
        """Wird aufgerufen, wenn sich die Koordinaten ändern"""
        # Verzögerte Aktualisierung, um zu viele Updates zu vermeiden
        if hasattr(self, '_coord_timer'):
            self.window.after_cancel(self._coord_timer)
        self._coord_timer = self.window.after(300, self.update_preview)

    def update_preview(self):
        """Aktualisiert die Live-Vorschau"""
        if self.files:
            try:
                src = os.path.join(self.source_dir, self.files[0])
                img = Image.open(src)
                
                # Neue Cutout-Koordinaten
                x, y, w, h = self.get_cutout_coordinates()
                cutout = img.crop((x, y, x + w, y + h))
                
                # Bilder aktualisieren
                self.show_images(img, cutout)
            except Exception as e:
                print(f"Fehler beim Aktualisieren der Vorschau: {e}")

    def start_analysis(self):
        """Startet die OCR-Analyse"""
        self.analyzing = True
        self.current_index = 0
        self.results = []
        self.results_tree.delete(*self.results_tree.get_children())
        
        # Button-Status aktualisieren
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        
        # Initialisiere OCR
        if not hasattr(self.parent, 'improved_ocr'):
            alternative_kurzel = self.json_config.get('alternative_kurzel', {})
            self.parent.improved_ocr = ImprovedOCR(self.valid_kurzel, alternative_kurzel)
        
        # Starte Analyse in separatem Thread
        import threading
        self.analysis_thread = threading.Thread(target=self.run_analysis, daemon=True)
        self.analysis_thread.start()
        
    
    def run_analysis(self):
        """Führt die OCR-Analyse durch"""
        total = len(self.files)
        
        for idx, fname in enumerate(self.files):
            if not self.analyzing:
                break
                
            try:
                # Status aktualisieren
                self.window.after(0, lambda: self.update_status(f"Analysiere {fname} ({idx+1}/{total})"))
                self.window.after(0, lambda: self.progress_var.set(idx+1))
                self.window.after(0, lambda: self.progress_text.config(text=f"{idx+1} / {total}"))
                
                # Bild laden
                src = os.path.join(self.source_dir, fname)
                img = Image.open(src)
                
                # Cutout erstellen (anpassbare Koordinaten)
                # Diese Koordinaten können in den Einstellungen geändert werden
                x, y, w, h = self.get_cutout_coordinates()
                cutout = img.crop((x, y, x + w, y + h))
                
                # Bilder in GUI anzeigen
                self.window.after(0, lambda: self.show_images(img, cutout))
                
                # OCR durchführen
                ocr_result = self.perform_ocr(img, fname)
                
                # Ergebnis speichern
                result = {
                    'filename': fname,
                    'original_image': img,
                    'cutout_image': cutout,
                    'ocr_result': ocr_result,
                    'corrected_kurzel': ocr_result.get('text', '')
                }
                self.results.append(result)
                
                # EXIF-Daten automatisch speichern
                self.save_ocr_to_exif(src, ocr_result)
                
                # Ergebnis in Treeview hinzufügen
                self.window.after(0, lambda r=result: self.add_result_to_tree(r))
                
                # Kurze Pause für bessere Sichtbarkeit
                import time
                time.sleep(0.1)
                
            except Exception as e:
                print(f"Fehler bei {fname}: {e}")
                continue
        
        # Analyse abgeschlossen
        self.window.after(0, self.analysis_finished)
    
    def save_ocr_to_exif(self, image_path, ocr_result):
        """Speichert OCR-Ergebnisse automatisch in EXIF-Daten"""
        try:
            # Erstelle EXIF-Daten-Struktur
            exif_data = {
                "TAGOCR": ocr_result.get('text', ''),
                "ocr_confidence": ocr_result.get('confidence', 0),
                "ocr_method": self.active_method,
                "analysis_timestamp": str(datetime.now()),
                "damage_categories": [],
                "image_types": [],
                "use_image": True,
                "image_quality": "unbekannt",
                "damage_description": ""
            }
            
            # Speichere in EXIF
            success = save_exif_usercomment(image_path, exif_data)
            
            if success:
                write_detailed_log("info", "OCR-Ergebnisse in EXIF gespeichert", f"Bild: {os.path.basename(image_path)}, OCR: {ocr_result.get('text', '')}")
            else:
                write_detailed_log("warning", "Fehler beim Speichern der OCR-Ergebnisse in EXIF", f"Bild: {os.path.basename(image_path)}")
                
        except Exception as e:
            write_detailed_log("error", "Fehler beim Speichern der OCR-Ergebnisse in EXIF", f"Bild: {os.path.basename(image_path)}", e)
            print(f"Fehler beim Speichern der OCR-Ergebnisse in EXIF: {e}")
    
    def perform_ocr(self, img, fname):
        """Führt OCR für ein Bild durch"""
        try:
            if self.active_method == 'feste_koordinaten':
                return self.parent.ocr_method_feste_koordinaten(img, debug=False)
            elif self.active_method == 'old':
                src = os.path.join(self.source_dir, fname)
                alternative_kurzel = self.json_config.get('alternative_kurzel', {})
                return old_ocr_method(src, self.valid_kurzel, alternative_kurzel)
            else:
                return {'text': None, 'confidence': 0.0, 'raw_text': 'Unbekannte Methode', 'method': self.active_method}
        except Exception as e:
            return {
                'text': None,
                'confidence': 0.0,
                'raw_text': str(e),
                'method': f'{self.active_method}_error'
            }
    
    def draw_cropout_overlay(self, img, x, y, w, h):
        """Zeichnet einen roten Rechteck-Overlay für den CropOut-Bereich"""
        # Kopie des Bildes erstellen
        overlay_img = img.copy()
        
        # ImageDraw für das Zeichnen verwenden
        from PIL import ImageDraw
        draw = ImageDraw.Draw(overlay_img)
        
        # Rotes Rechteck zeichnen (2 Pixel breit)
        draw.rectangle([x, y, x + w, y + h], outline='red', width=2)
        
        # Eckpunkte als kleine Kreise markieren
        corner_radius = 3
        corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
        for corner_x, corner_y in corners:
            draw.ellipse([corner_x - corner_radius, corner_y - corner_radius,
                         corner_x + corner_radius, corner_y + corner_radius], 
                        fill='red', outline='darkred')
        
        return overlay_img

    def show_images(self, original_img, cutout_img):
        """Zeigt Original- und Cutout-Bild mit Overlay in den Canvas-Elementen an"""
        try:
            # Originalbild zuerst skalieren
            original_display = original_img.copy()
            original_width, original_height = original_display.size
            
            # Skalierungsfaktor berechnen für max 400x300
            scale_x = 400 / original_width
            scale_y = 300 / original_height
            scale_factor = min(scale_x, scale_y, 1.0)  # Nicht vergrößern
            
            # Neues Bild erstellen
            new_width = int(original_width * scale_factor)
            new_height = int(original_height * scale_factor)
            scaled_img = original_display.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # CropOut-Koordinaten holen und skalieren
            x, y, w, h = self.get_cutout_coordinates()
            scaled_x = int(x * scale_factor)
            scaled_y = int(y * scale_factor)
            scaled_w = int(w * scale_factor)
            scaled_h = int(h * scale_factor)
            
            # Overlay auf das skalierte Bild zeichnen
            overlay_img = self.draw_cropout_overlay(scaled_img, scaled_x, scaled_y, scaled_w, scaled_h)
            
            # PhotoImage erstellen
            original_photo = ImageTk.PhotoImage(overlay_img)
            
            self.original_canvas.delete("all")
            # Bild in der Mitte des Canvas zentrieren
            canvas_center_x = 200
            canvas_center_y = 150
            self.original_canvas.create_image(canvas_center_x, canvas_center_y, image=original_photo, anchor=tk.CENTER)
            self.original_canvas.image = original_photo  # Referenz halten
            
            # Cutout skalieren und anzeigen
            cutout_display = cutout_img.copy()
            cutout_display.thumbnail((THUMBNAIL_MEDIUM_WIDTH, THUMBNAIL_MEDIUM_HEIGHT), Image.Resampling.LANCZOS)
            cutout_photo = ImageTk.PhotoImage(cutout_display)
            
            self.cutout_canvas.delete("all")
            self.cutout_canvas.create_image(100, 75, image=cutout_photo, anchor=tk.CENTER)
            self.cutout_canvas.image = cutout_photo  # Referenz halten
            
        except Exception as e:
            print(f"Fehler beim Anzeigen der Bilder: {e}")
            import traceback
            traceback.print_exc()
    
    def get_cutout_coordinates(self):
        """Gibt die aktuellen Cutout-Koordinaten zurück"""
        try:
            # Verwende Koordinaten aus den Eingabefeldern
            x = int(self.x_var.get())
            y = int(self.y_var.get())
            w = int(self.w_var.get())
            h = int(self.h_var.get())
            return x, y, w, h
        except (ValueError, AttributeError):
            # Fallback auf Standardwerte
            return 10, 10, 60, 35
    
    def update_cutout_coordinates(self):
        """Aktualisiert die Cutout-Koordinaten"""
        try:
            x = int(self.x_var.get())
            y = int(self.y_var.get())
            w = int(self.w_var.get())
            h = int(self.h_var.get())
            
            # Aktualisiere lokale Koordinaten
            self.cutout_coords = {'x': x, 'y': y, 'w': w, 'h': h}
            
            # Speichere in Konfiguration (beide Varianten für Kompatibilität)
            self.json_config['cutout_coordinates'] = {'x': x, 'y': y, 'w': w, 'h': h}
            self.json_config['crop_coordinates'] = {'x': x, 'y': y, 'w': w, 'h': h}
            
            # Speichere Konfiguration
            if save_json_config(self.json_config):
                self.update_status(f"Koordinaten aktualisiert und gespeichert: X={x}, Y={y}, Breite={w}, Höhe={h}")
                print(f"Koordinaten gespeichert: {self.cutout_coords}")
            else:
                self.update_status("Fehler: Koordinaten konnten nicht gespeichert werden!")
            
        except ValueError:
            self.update_status("Fehler: Bitte geben Sie gültige Zahlen ein!")
    
    def update_status(self, message):
        """Aktualisiert den Status-Text"""
        self.status_label.config(text=message)
    
    def stop_analysis(self):
        """Stoppt die laufende Analyse"""
        self.analyzing = False
        self.status_label.config(text="Analyse gestoppt!")
        self.stop_button.config(state=tk.DISABLED)
        self.start_button.config(state=tk.NORMAL)
    
    def analysis_finished(self):
        """Wird aufgerufen, wenn die Analyse abgeschlossen ist"""
        self.analyzing = False
        self.status_label.config(text="Analyse abgeschlossen!")
        self.save_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.start_button.config(state=tk.NORMAL)
        
        # Aktualisiere Treeview
        self.update_results_tree()
    
    
    def add_result_to_tree(self, result):
        """Fügt ein Ergebnis zur Treeview hinzu"""
        ocr_result = result['ocr_result']
        
        # Erstelle Cutout-Thumbnail
        try:
            cutout_img = result.get('cutout_image')
            if cutout_img:
                cutout_img.thumbnail((100, 75), Image.Resampling.LANCZOS)
                cutout_photo = ImageTk.PhotoImage(cutout_img)
            else:
                cutout_photo = None
        except:
            cutout_photo = None
        
        # Bestimme Gruppe basierend auf Kürzel
        detected_text = ocr_result.get('text', '')
        group = self.get_group_for_kurzel(detected_text)
        
        # Erstelle Bild-Text für die erste Spalte
        image_text = "📷" if cutout_photo else "❌"
        
        values = (
            image_text,  # Bild-Indikator
            result['filename'],
            f"{result['original_image'].size[0]}x{result['original_image'].size[1]}",
            f"{result['cutout_image'].size[0]}x{result['cutout_image'].size[1]}",
            ocr_result.get('raw_text', ''),
            detected_text,  # Kürzel
            group,
            f"{ocr_result.get('confidence', 0.0):.2f}",
            ocr_result.get('method', '')
        )
        
        item = self.results_tree.insert('', 'end', values=values)
        
        # Speichere Referenzen für spätere Widget-Erstellung
        if item not in self.tree_widgets:
            self.tree_widgets[item] = {}
        
        self.tree_widgets[item]['result'] = result
        self.tree_widgets[item]['cutout_photo'] = cutout_photo
        
        # Erstelle Dropdown-Widgets nach dem Einfügen
        # self.window.after(100, lambda: self.create_tree_widgets(item))
    
    def get_group_for_kurzel(self, kurzel):
        """Bestimmt die Gruppe für ein Kürzel"""
        if not kurzel:
            return "Unbekannt"
        
        kurzel_upper = kurzel.upper()
        if kurzel_upper.startswith('HSS'):
            return "HSS-Gruppe"
        elif kurzel_upper.startswith('LSS'):
            return "LSS-Gruppe"
        elif kurzel_upper.startswith('PL'):
            return "PL-Gruppe"
        elif kurzel_upper.startswith('RG'):
            return "RG-Gruppe"
        elif kurzel_upper.startswith('SUN'):
            return "SUN-Gruppe"
        else:
            return "Sonstige"
    
    def create_tree_widgets(self, item):
        """Erstellt Dropdown-Widgets in der Treeview"""
        try:
            if item not in self.tree_widgets:
                return
            
            result = self.tree_widgets[item]['result']
            cutout_photo = self.tree_widgets[item]['cutout_photo']
            
            # Hole Spalten-Positionen
            bbox = self.results_tree.bbox(item)
            if not bbox:
                return
            
            x, y, w, h = bbox
            
            # Erstelle Bild-Thumbnail
            if cutout_photo:
                # Erstelle Canvas für Bild
                canvas = tk.Canvas(self.results_tree, width=100, height=75, highlightthickness=0)
                canvas.create_image(50, 37, image=cutout_photo, anchor=tk.CENTER)
                canvas.image = cutout_photo  # Referenz halten
                
                # Platziere Canvas in der ersten Spalte
                self.results_tree.set(item, 0, "")  # Leere den Text
                # Verwende set() statt window_create für Kompatibilität
                
            # Erstelle Kürzel-Dropdown
            kurzel_var = tk.StringVar(value=result['ocr_result'].get('text', ''))
            kurzel_combo = ttk.Combobox(self.results_tree, textvariable=kurzel_var, 
                                       values=self.valid_kurzel, state='readonly', width=12)
            kurzel_combo.bind('<<ComboboxSelected>>', 
                             lambda e, r=result: self.update_kurzel(r, kurzel_var.get()))
            
            # Erstelle Gruppen-Dropdown
            group_var = tk.StringVar(value=self.get_group_for_kurzel(result['ocr_result'].get('text', '')))
            group_options = ["HSS-Gruppe", "LSS-Gruppe", "PL-Gruppe", "RG-Gruppe", "SUN-Gruppe", "Sonstige"]
            group_combo = ttk.Combobox(self.results_tree, textvariable=group_var, 
                                      values=group_options, state='readonly', width=10)
            group_combo.bind('<<ComboboxSelected>>', 
                            lambda e, r=result: self.update_group(r, group_var.get()))
            
            # Speichere Widget-Referenzen
            self.tree_widgets[item]['kurzel_combo'] = kurzel_combo
            self.tree_widgets[item]['group_combo'] = group_combo
            self.tree_widgets[item]['kurzel_var'] = kurzel_var
            self.tree_widgets[item]['group_var'] = group_var
            
        except Exception as e:
            print(f"Fehler beim Erstellen der Treeview-Widgets: {e}")
    
    def update_kurzel(self, result, new_kurzel):
        """Aktualisiert das Kürzel für ein Ergebnis"""
        result['ocr_result']['text'] = new_kurzel
        print(f"Kürzel aktualisiert: {new_kurzel}")
    
    def update_group(self, result, new_group):
        """Aktualisiert die Gruppe für ein Ergebnis"""
        # Hier könnte man die Gruppe in den Ergebnissen speichern
        print(f"Gruppe aktualisiert: {new_group}")
    
    def on_result_right_click(self, event):
        """Behandelt Rechtsklick auf Treeview-Eintrag"""
        item = self.results_tree.selection()[0] if self.results_tree.selection() else None
        if not item:
            return
        
        # Erstelle Kontextmenü
        context_menu = tk.Menu(self.window, tearoff=0)
        context_menu.add_command(label="Kürzel bearbeiten", command=lambda: self.edit_kurzel(item))
        context_menu.add_command(label="Gruppe ändern", command=lambda: self.edit_group(item))
        context_menu.add_separator()
        context_menu.add_command(label="Cutout anzeigen", command=lambda: self.show_cutout(item))
        
        # Zeige Kontextmenü
        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            context_menu.grab_release()
    
    def edit_kurzel(self, item):
        """Öffnet Dialog zum Bearbeiten des Kürzels"""
        if item not in self.tree_widgets:
            return
        
        result = self.tree_widgets[item]['result']
        current_kurzel = result['ocr_result'].get('text', '')
        
        # Erstelle einfachen Dialog
        dialog = tk.Toplevel(self.window)
        dialog.title("Kürzel bearbeiten")
        dialog.geometry("300x150")
        dialog.transient(self.window)
        dialog.grab_set()
        
        # Zentriere Dialog
        dialog.geometry("+%d+%d" % (self.window.winfo_rootx() + 50, self.window.winfo_rooty() + 50))
        
        ttk.Label(dialog, text="Neues Kürzel:").pack(pady=10)
        
        kurzel_var = tk.StringVar(value=current_kurzel)
        kurzel_combo = ttk.Combobox(dialog, textvariable=kurzel_var, values=self.valid_kurzel, state='readonly')
        kurzel_combo.pack(pady=10, padx=20, fill=tk.X)
        
        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=20)
        
        ttk.Button(button_frame, text="OK", command=lambda: self.save_kurzel_edit(item, kurzel_var.get(), dialog)).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Abbrechen", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        
        kurzel_combo.focus()
    
    def save_kurzel_edit(self, item, new_kurzel, dialog):
        """Speichert die Kürzel-Änderung"""
        if item in self.tree_widgets:
            result = self.tree_widgets[item]['result']
            result['ocr_result']['text'] = new_kurzel
            
            # Aktualisiere Treeview
            self.results_tree.set(item, 5, new_kurzel)  # Kürzel-Spalte
            self.results_tree.set(item, 6, self.get_group_for_kurzel(new_kurzel))  # Gruppe-Spalte
            
            print(f"Kürzel aktualisiert: {new_kurzel}")
        
        dialog.destroy()
    
    def edit_group(self, item):
        """Öffnet Dialog zum Ändern der Gruppe"""
        if item not in self.tree_widgets:
            return
        
        result = self.tree_widgets[item]['result']
        current_group = self.get_group_for_kurzel(result['ocr_result'].get('text', ''))
        
        # Erstelle einfachen Dialog
        dialog = tk.Toplevel(self.window)
        dialog.title("Gruppe ändern")
        dialog.geometry("300x150")
        dialog.transient(self.window)
        dialog.grab_set()
        
        # Zentriere Dialog
        dialog.geometry("+%d+%d" % (self.window.winfo_rootx() + 50, self.window.winfo_rooty() + 50))
        
        ttk.Label(dialog, text="Neue Gruppe:").pack(pady=10)
        
        group_var = tk.StringVar(value=current_group)
        group_options = ["HSS-Gruppe", "LSS-Gruppe", "PL-Gruppe", "RG-Gruppe", "SUN-Gruppe", "Sonstige"]
        group_combo = ttk.Combobox(dialog, textvariable=group_var, values=group_options, state='readonly')
        group_combo.pack(pady=10, padx=20, fill=tk.X)
        
        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=20)
        
        ttk.Button(button_frame, text="OK", command=lambda: self.save_group_edit(item, group_var.get(), dialog)).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Abbrechen", command=dialog.destroy).pack(side=tk.LEFT, padx=5)
        
        group_combo.focus()
    
    def save_group_edit(self, item, new_group, dialog):
        """Speichert die Gruppen-Änderung"""
        if item in self.tree_widgets:
            # Aktualisiere Treeview
            self.results_tree.set(item, 6, new_group)  # Gruppe-Spalte
            print(f"Gruppe aktualisiert: {new_group}")
        
        dialog.destroy()
    
    def show_cutout(self, item):
        """Zeigt das Cutout-Bild in einem separaten Fenster"""
        if item not in self.tree_widgets:
            return
        
        cutout_photo = self.tree_widgets[item].get('cutout_photo')
        if not cutout_photo:
            return
        
        # Erstelle neues Fenster
        cutout_window = tk.Toplevel(self.window)
        cutout_window.title("Cutout-Bild")
        cutout_window.transient(self.window)
        
        # Erstelle Canvas für das Bild
        canvas = tk.Canvas(cutout_window, bg='white')
        canvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Zeige das Bild
        canvas.create_image(0, 0, image=cutout_photo, anchor=tk.NW)
        canvas.image = cutout_photo  # Referenz halten
        
        # Passe Fenstergröße an Bild an
        cutout_window.geometry(f"{cutout_photo.width() + 20}x{cutout_photo.height() + 40}")
        
        # Zentriere Fenster
        cutout_window.geometry("+%d+%d" % (self.window.winfo_rootx() + 100, self.window.winfo_rooty() + 100))
    
    def update_results_tree(self):
        """Aktualisiert die Treeview mit aktuellen Ergebnissen"""
        # Lösche alle Einträge
        self.results_tree.delete(*self.results_tree.get_children())
        
        # Füge alle Ergebnisse hinzu
        for result in self.results:
            self.add_result_to_tree(result)
    
    def on_result_double_click(self, event):
        """Öffnet Dialog zum Bearbeiten des Kürzels"""
        selection = self.results_tree.selection()
        if not selection:
            return
            
        item = selection[0]
        result_index = self.results_tree.index(item)
        
        if result_index < len(self.results):
            result = self.results[result_index]
            self.edit_kurzel_dialog(result, item)
    
    def on_result_click(self, event):
        """Zeigt die Bilder der ausgewählten Zeile oben an"""
        selection = self.results_tree.selection()
        if not selection:
            return
            
        item = selection[0]
        result_index = self.results_tree.index(item)
        
        if result_index < len(self.results):
            result = self.results[result_index]
            # Zeige Originalbild und Cutout oben an
            self.show_images(result['original_image'], result['cutout_image'])
            # Aktualisiere Status
            self.update_status(f"Angezeigt: {result['filename']} - Erkannt: {result['ocr_result'].get('text', 'N/A')}")
    
    def edit_kurzel_dialog(self, result, tree_item):
        """Dialog zum Bearbeiten des Kürzels"""
        dialog = tk.Toplevel(self.window)
        dialog.title(f"Kürzel bearbeiten: {result['filename']}")
        dialog.geometry(f"{EDIT_DIALOG_WIDTH}x{EDIT_DIALOG_HEIGHT}")
        dialog.transient(self.window)
        dialog.grab_set()
        
        # Frame
        frame = ttk.Frame(dialog, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Aktuelles Kürzel
        ttk.Label(frame, text="Aktuell erkannt:").pack(anchor='w')
        current_var = tk.StringVar(value=result['ocr_result'].get('text', ''))
        current_entry = ttk.Entry(frame, textvariable=current_var, state='readonly')
        current_entry.pack(fill=tk.X, pady=(0, 10))
        
        # Neues Kürzel
        ttk.Label(frame, text="Neues Kürzel:").pack(anchor='w')
        new_var = tk.StringVar(value=result['corrected_kurzel'])
        
        # Combobox mit gültigen Kürzeln
        combo = ttk.Combobox(frame, textvariable=new_var, values=self.valid_kurzel, state='readonly')
        combo.pack(fill=tk.X, pady=(0, 10))
        
        # Bildvorschau
        preview_frame = ttk.LabelFrame(frame, text="Vorschau")
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Cutout anzeigen
        cutout_display = result['cutout_image'].copy()
        cutout_display.thumbnail((THUMBNAIL_WIDTH, THUMBNAIL_HEIGHT), Image.Resampling.LANCZOS)
        cutout_photo = ImageTk.PhotoImage(cutout_display)
        
        preview_canvas = tk.Canvas(preview_frame, width=150, height=100, bg='white')
        preview_canvas.pack(padx=5, pady=5)
        preview_canvas.create_image(75, 50, image=cutout_photo, anchor=tk.CENTER)
        preview_canvas.image = cutout_photo
        
        # Buttons
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        def save_changes():
            result['corrected_kurzel'] = new_var.get()
            # Treeview aktualisieren
            self.results_tree.set(tree_item, 'Korrigiert', new_var.get())
            dialog.destroy()
        
        def cancel():
            dialog.destroy()
        
        ttk.Button(button_frame, text="Speichern", command=save_changes).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(button_frame, text="Abbrechen", command=cancel).pack(side=tk.LEFT)
    
    def update_status(self, text):
        """Aktualisiert den Status-Text"""
        self.status_label.config(text=text)
    
    def analysis_finished(self):
        """Wird aufgerufen, wenn die Analyse abgeschlossen ist"""
        self.analyzing = False
        self.status_label.config(text="Analyse abgeschlossen!")
        self.save_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
    
    def stop_analysis(self):
        """Stoppt die laufende Analyse"""
        self.analyzing = False
        self.status_label.config(text="Analyse gestoppt!")
        self.stop_button.config(state=tk.DISABLED)
    
    def save_results(self):
        """Speichert die Ergebnisse in EXIF-Daten"""
        saved_count = 0
        
        for result in self.results:
            try:
                fname = result['filename']
                src = os.path.join(self.source_dir, fname)
                
                # Lade bestehende EXIF-Daten
                exif_data = get_exif_usercomment(src)
                if exif_data is None:
                    exif_data = self.json_config.copy()
                
                # Aktualisiere TAGOCR
                corrected_kurzel = result['corrected_kurzel']
                if corrected_kurzel:
                    exif_data["TAGOCR"] = str(corrected_kurzel)
                    
                    # Speichere EXIF-Daten
                    if save_exif_usercomment(src, exif_data):
                        saved_count += 1
                        
            except Exception as e:
                print(f"Fehler beim Speichern von {fname}: {e}")
        
        messagebox.showinfo("Erfolg", f"{saved_count} von {len(self.results)} Dateien gespeichert!")
    
    
    def on_close(self):
        """Schließt das Analyse-Fenster und speichert aktuelle Koordinaten"""
        self.analyzing = False
        
        # Speichere aktuelle Koordinaten automatisch
        try:
            x = int(self.x_var.get())
            y = int(self.y_var.get())
            w = int(self.w_var.get())
            h = int(self.h_var.get())
            
            # Aktualisiere und speichere Koordinaten
            self.cutout_coords = {'x': x, 'y': y, 'w': w, 'h': h}
            self.json_config['cutout_coordinates'] = {'x': x, 'y': y, 'w': w, 'h': h}
            self.json_config['crop_coordinates'] = {'x': x, 'y': y, 'w': w, 'h': h}
            save_json_config(self.json_config)
            print(f"Koordinaten automatisch gespeichert beim Schließen: {self.cutout_coords}")
            
        except (ValueError, AttributeError):
            print("Fehler beim automatischen Speichern der Koordinaten")
        
        self.window.destroy()

    def abort_analysis(self):
        """Bricht die Analyse sofort ab und schließt das Analysefenster."""
        self.analyzing = False
        
        # Speichere aktuelle Koordinaten automatisch
        try:
            x = int(self.x_var.get())
            y = int(self.y_var.get())
            w = int(self.w_var.get())
            h = int(self.h_var.get())
            
            # Aktualisiere und speichere Koordinaten
            self.cutout_coords = {'x': x, 'y': y, 'w': w, 'h': h}
            self.json_config['cutout_coordinates'] = {'x': x, 'y': y, 'w': w, 'h': h}
            self.json_config['crop_coordinates'] = {'x': x, 'y': y, 'w': w, 'h': h}
            save_json_config(self.json_config)
            print(f"Koordinaten automatisch gespeichert beim Abbrechen: {self.cutout_coords}")
            
        except (ValueError, AttributeError):
            print("Fehler beim automatischen Speichern der Koordinaten")
        
        self.window.destroy()

if __name__ == '__main__':
    try:
        print("Starte Ladebildschirm...")
        
        # Ladebildschirm erstellen und anzeigen
        loading_screen = LoadingScreen()
        
        def initialize_app():
            """Initialisiert die Hauptanwendung im Hintergrund"""
            try:
                loading_screen.update_status("Lade Konfiguration...")
                time.sleep(0.5)
                
                loading_screen.update_status("Initialisiere OCR-Engine...")
                time.sleep(0.5)
                
                loading_screen.update_status("Lade Benutzeroberfläche...")
                time.sleep(0.5)
                
                loading_screen.update_status("Erstelle Hauptfenster...")
                time.sleep(0.5)
                
                loading_screen.update_status("Fertig! Starte Anwendung...")
                time.sleep(0.5)
                
                # Hauptanwendung im Hauptthread erstellen
                loading_screen.root.after(0, create_main_app)
                
            except Exception as e:
                print(f"Fehler beim Initialisieren der Anwendung: {e}")
                import traceback
                traceback.print_exc()
                loading_screen.update_status(f"Fehler: {e}")
                loading_screen.root.after(3000, loading_screen.close)
        
        def create_main_app():
            """Erstellt die Hauptanwendung im Hauptthread"""
            try:
                # Ladebildschirm schließen
                loading_screen.close()
                
                # Kurze Pause, damit der Ladebildschirm vollständig geschlossen ist
                time.sleep(0.1)
                
                # Hauptanwendung erstellen (nicht im Loading-Modus)
                app = OCRReviewApp(loading_mode=False)
                
                print("App erstellt, starte mainloop...")
                app.mainloop()
                print("mainloop beendet")
                
            except Exception as e:
                print(f"Fehler beim Erstellen der Hauptanwendung: {e}")
                import traceback
                traceback.print_exc()
                loading_screen.update_status(f"Fehler: {e}")
                loading_screen.root.after(3000, loading_screen.close)
        
        # Initialisierung im Hintergrund starten
        init_thread = threading.Thread(target=initialize_app, daemon=True)
        init_thread.start()
        
        # Ladebildschirm anzeigen
        loading_screen.root.mainloop()
        
    except Exception as e:
        print(f"Fehler beim Starten der Anwendung: {e}")
        import traceback
        traceback.print_exc()