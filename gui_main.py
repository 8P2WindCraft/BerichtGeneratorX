#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hauptanwendungs-Fenster
OCRReviewApp - Die Haupt-GUI-Klasse
"""

import os
import re
import json
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from PIL import Image, ImageTk, ImageDraw
import threading
import time
from datetime import datetime
from collections import Counter
import traceback

from constants import *
from config_manager import config_manager
from core_ocr import (
    ImprovedOCR, get_reader, excel_to_json, old_ocr_method, enhanced_old_method,
    upscale_crop, post_process_text, find_text_box_easyocr, run_ocr_easyocr_improved
)
from core_kurzel import KurzelTableManager
from utils_exif import get_exif_usercomment, save_exif_usercomment
from utils_logging import logger, write_detailed_log, write_log_entry, LOG_FILE, DETAILED_LOG_FILE
from utils_helpers import resource_path, LAST_FOLDER_FILE, CODE_FILE

# Fallback falls Import fehlschlägt
try:
    LAST_FOLDER_FILE
except NameError:
    import os
    LAST_FOLDER_FILE = os.path.join(os.path.dirname(__file__), 'last_folder.txt')
from gui_components import LoadingScreen, AnalysisWindow
from gui_dialogs import AlternativeKurzelDialog, ExcelGrunddatenDialog


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

        # Modernes Theme versuchen (ttkbootstrap), mit Fallback auf Standard
        self._init_theme()

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
        
        # Mindest-Fenstergröße setzen
        self.minsize(800, 600)
        
        # Fenster maximierbar machen
        self.resizable(True, True)
        
        if window_x is not None and window_y is not None:
            self.geometry(f"{window_width}x{window_height}+{window_x}+{window_y}")
        else:
            self.geometry(f"{window_width}x{window_height}")

        # Stelle sicher, dass das Fenster sichtbar ist und nicht hinter der Taskleiste landet
        try:
            self.update_idletasks()
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
            # Verwende Konfig-Werte, falls vorhanden, sonst aktuelle Position
            x = window_x if window_x is not None else self.winfo_x()
            y = window_y if window_y is not None else self.winfo_y()
            w = window_width if window_width else self.winfo_width()
            h = window_height if window_height else self.winfo_height()
            # In sichtbaren Bereich klemmen
            x = max(0, min(int(x), max(0, screen_w - int(w))))
            y = max(0, min(int(y), max(0, screen_h - int(h))))
            self.geometry(f"{int(w)}x{int(h)}+{int(x)}+{int(y)}")
            # Maximiert-Status berücksichtigen
            if self.config_manager.get_setting('display.maximized', False):
                try:
                    self.state('zoomed')
                except Exception:
                    pass
            # In den Vordergrund bringen und Fokus erzwingen
            self.deiconify()
            self.lift()
            try:
                self.focus_force()
            except Exception:
                pass
            try:
                self.attributes('-topmost', True)
                self.after(300, lambda: self.attributes('-topmost', False))
            except Exception:
                pass
        except Exception:
            pass
        
        # Lade gültige Kürzel - nur noch aus der Kürzel-Tabelle
        self.valid_kurzel = []
        self.update_valid_kurzel_from_table()

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
            try:
                last_folder_file = LAST_FOLDER_FILE
            except NameError:
                last_folder_file = os.path.join(os.path.dirname(__file__), 'last_folder.txt')
            
            if os.path.isfile(last_folder_file):
                try:
                    print("LAST_FOLDER_FILE gefunden, versuche zu laden...")
                    with open(last_folder_file, 'r', encoding='utf-8') as f:
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

    def update_valid_kurzel_from_table(self):
        """Aktualisiert die valid_kurzel Liste direkt aus der Kürzel-Tabelle - einzige Wahrheit"""
        try:
            kurzel_list = []
            kurzel_table = self.json_config.get('kurzel_table', {})
            
            # Hole alle aktiven Kürzel aus der Tabelle
            for code, data in kurzel_table.items():
                if data.get('active', True):  # Nur aktive Kürzel
                    kurzel_list.append(code)
            
            # Sortiere alphabetisch
            kurzel_list = sorted(kurzel_list)
            
            # Aktualisiere sowohl die Konfiguration als auch die Instanz-Variable
            self.json_config['valid_kurzel'] = kurzel_list
            self.valid_kurzel = kurzel_list
            
            # Debug-Ausgabe
            print(f"Valid Kürzel aus Kürzel-Tabelle aktualisiert: {len(self.valid_kurzel)} Kürzel")
            print(f"Kürzel: {self.valid_kurzel}")
            
            # Speichere die aktualisierte Konfiguration
            self.config_manager.save_config()
            
        except Exception as e:
            print(f"Fehler beim Aktualisieren der valid_kurzel: {e}")
            # Fallback: leere Liste
            self.valid_kurzel = []
            self.json_config['valid_kurzel'] = []

    def finish_initialization(self):
        """Beendet die Initialisierung nach dem Ladebildschirm"""
        self.loading_mode = False
        print("Starte Laden des letzten Ordners...")
        # Ordnerpfad beim Start laden
        try:
            last_folder_file = LAST_FOLDER_FILE
        except NameError:
            last_folder_file = os.path.join(os.path.dirname(__file__), 'last_folder.txt')
        
        if os.path.isfile(last_folder_file):
            try:
                print("LAST_FOLDER_FILE gefunden, versuche zu laden...")
                with open(last_folder_file, 'r', encoding='utf-8') as f:
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
        
        # Erstelle Standard-Code-Datei aus Kürzel-Tabelle
        active_kurzel = []
        kurzel_table = self.json_config.get('kurzel_table', {})
        for code, data in kurzel_table.items():
            if data.get('active', True):
                active_kurzel.append(code)
        
        with open(CODE_FILE, 'w', encoding='utf-8') as f:
            for code in sorted(active_kurzel):
                f.write(code + "\n")
        write_detailed_log("info", "Standard-Code-Datei erstellt", f"Datei: {CODE_FILE}, Anzahl: {len(active_kurzel)}")
        return active_kurzel

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
        analysis_menu.add_command(label=" Analysieren", command=self.auto_analyze)
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
        tools_menu.add_command(label=" Log", command=self.show_detailed_log)
        tools_menu.add_command(label="📋 OCR Log", command=self.show_ocr_log)
        tools_menu.add_command(label="⚙ Einstellungen", command=self.open_config_editor)
        tools_menu.add_command(label="⚙ Zeichen-Einstellungen", 
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

        # Haupt-Container direkt ohne Tabs (da Fortschritt jetzt eigene Spalte hat)
        self.main_container = ttk.Frame(self)
        self.main_container.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        self.main_container.grid_rowconfigure(0, weight=0)
        self.main_container.grid_rowconfigure(1, weight=1)
        self.main_container.grid_columnconfigure(0, weight=1)
        
        # 2. Toolbar mit wichtigsten Funktionen
        toolbar_frame = ttk.Frame(self.main_container)
        toolbar_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        
        # Linke Seite der Toolbar
        left_toolbar = ttk.Frame(toolbar_frame)
        left_toolbar.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Nur Ordner Button in der Toolbar
        folder_btn = tk.Button(left_toolbar, text=" Ordner öffnen", command=self.open_folder,
                              bg=COLORS['primary'], fg="white", 
                              font=("Segoe UI", FONT_SIZES['body'], "bold"),
                              relief="flat", bd=0, padx=15, pady=8, 
                              activebackground=COLORS['primary_hover'],
                              cursor="hand2")
        folder_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # Ordner Label direkt rechts neben dem Button in der left_toolbar
        self.label_folder_container = tk.Frame(left_toolbar, bg=COLORS['info_light'], bd=0, highlightthickness=1, highlightbackground=COLORS['border'])
        self.label_folder_container.pack(side=tk.LEFT, padx=(0, 10), pady=(0, 0))
        self.label_folder = tk.Label(self.label_folder_container, text="Kein Ordner ausgewählt",
                                     bg=COLORS['info_light'], fg=COLORS['text_primary'],
                                     font=("Segoe UI", FONT_SIZES['body']),
                                     anchor='w')
        self.label_folder.pack(side=tk.LEFT, padx=8, pady=6)
        
        # Fortschrittsbalken (wird nur bei Analyse eingeblendet)
        self.pbar = ttk.Progressbar(left_toolbar, length=150, mode='determinate')
        # self.pbar.pack(side=tk.LEFT, padx=(0, 5))  # Wird nur bei Analyse eingeblendet
        
        # Rechte Seite der Toolbar
        right_toolbar = ttk.Frame(toolbar_frame)
        right_toolbar.pack(side=tk.RIGHT, fill=tk.X)
        
        # Rechte Toolbar ist jetzt leer - alle Buttons ins Menü verschoben
        
        # 3. Main Content Area aufteilen in: Links Content, Rechts Fortschritt (eigene Spalte)
        self.main_split = ttk.Frame(self.main_container)
        self.main_split.grid(row=1, column=0, sticky="nsew", pady=(5, 0))

        # Spaltenkonfiguration: 0 = Content, 1 = Griff, 2 = Progress-Spalte
        self.main_split.grid_columnconfigure(0, weight=4)
        self.main_split.grid_columnconfigure(1, weight=0, minsize=14)
        self.main_split.grid_columnconfigure(2, weight=1)
        self.main_split.grid_rowconfigure(0, weight=1)

        # Linker Inhaltsbereich (Werkzeuge | Bild | Bewertung)
        self.content_frame = ttk.Frame(self.main_split)
        self.content_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        # Schmaler Griff zum Ein-/Ausklappen der rechten Spalte
        self.progress_collapsed = False
        self.progress_handle = tk.Frame(self.main_split, width=14, bg=COLORS['border'])
        self.progress_handle.grid(row=0, column=1, sticky="ns")
        self.progress_handle.grid_propagate(False)
        self.progress_handle_button = tk.Button(self.progress_handle, text="◀", width=2,
                                               command=self.toggle_progress_panel,
                                               relief='flat', bd=0, bg=COLORS['bg_medium'],
                                               fg=COLORS['text_primary'], cursor='hand2')
        self.progress_handle_button.pack(side=tk.TOP, pady=4)

        # Separater Container für Galerie-Ansicht (gleiches Grid-Feld, initial verborgen)
        self.gallery_view_container = ttk.Frame(self.main_split)
        self.gallery_view_container.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self.gallery_view_container.grid_remove()

        # Konfiguriere die Spaltengewichte (3 Spalten)
        # Spalte 0: Werkzeuge (fix), Spalte 1: Bild (groß), Spalte 2: Bewertung (mittel)
        self.content_frame.grid_columnconfigure(0, weight=0, minsize=60)  # Werkzeuge fix
        self.content_frame.grid_columnconfigure(1, weight=12)  # Bild (~60%)
        self.content_frame.grid_columnconfigure(2, weight=4)   # Bewertung (~20%)
        
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
        
        # Speichern-Button
        self.save_btn = tk.Button(tool_buttons_frame, text="💾",
                                command=self.save_current_image_completely,
                                bg=COLORS['success'], fg='white',
                                font=("Segoe UI", 18),
                                width=2, height=1,
                                relief='raised', bd=2,
                                cursor='hand2')
        self.save_btn.pack(pady=5)
        self.create_tooltip(self.save_btn, "Aktuelle Bewertung und Zeichnungen speichern")
        
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
        self.left_column.grid_rowconfigure(0, weight=0)  # Bildinfo (fix)
        self.left_column.grid_rowconfigure(1, weight=1)  # Bild-Bereich expandiert vertikal
        self.left_column.grid_rowconfigure(2, weight=0)  # Navigation (fix)
        self.left_column.grid_rowconfigure(3, weight=0)  # Damage Description (fix)
        self.left_column.grid_rowconfigure(4, weight=0)  # Status (fix)
        
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
        
        # Initiale Nachricht im Canvas anzeigen (wird später gelöscht wenn Bild geladen wird)
        self.canvas_initial_text1 = self.canvas.create_text(400, 250, 
                               text="Bitte wählen Sie einen Ordner mit Bildern aus",
                               fill=COLORS['text_secondary'], 
                               font=("Segoe UI", FONT_SIZES['heading']))
        
        # Status-Text im Canvas (wird später gelöscht wenn Bild geladen wird)
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
        mousewheel_check = ttk.Checkbutton(nav_center_frame, text="🖱 Mausrad", 
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
        
        # Mittlere Spalte (20%) - Bewertung (scrollbar)
        self.center_column = ttk.Frame(self.content_frame)
        self.center_column.grid(row=0, column=2, sticky="nsew", padx=5)
        self.center_column.grid_columnconfigure(0, weight=1)

        # Scrollbarer Container mit Canvas
        center_container = ttk.Frame(self.center_column)
        center_container.grid(row=0, column=0, sticky="nsew")
        center_container.grid_columnconfigure(0, weight=1)
        center_container.grid_rowconfigure(0, weight=1)

        center_canvas = tk.Canvas(center_container, highlightthickness=0, bg=self.cget('bg'))
        center_scroll = ttk.Scrollbar(center_container, orient=tk.VERTICAL, command=center_canvas.yview)
        self.center_inner = ttk.Frame(center_canvas)

        center_canvas.create_window((0, 0), window=self.center_inner, anchor='nw')
        center_canvas.configure(yscrollcommand=center_scroll.set)

        center_canvas.grid(row=0, column=0, sticky='nsew')
        center_scroll.grid(row=0, column=1, sticky='ns')

        def _on_inner_configure(event):
            center_canvas.configure(scrollregion=center_canvas.bbox('all'))
        self.center_inner.bind('<Configure>', _on_inner_configure)

        def _on_container_configure(event):
            try:
                center_canvas.itemconfigure(1, width=event.width - center_scroll.winfo_width())
            except Exception:
                pass
        center_container.bind('<Configure>', _on_container_configure)
        
        # Einheitliche große Schrift für alle Buttons
        einheits_font = ("Segoe UI", FONT_SIZES['body'])
        einheits_font_bold = ("Segoe UI", FONT_SIZES['body'], "bold")
        
        # Bild verwenden - Kollapsible
        self.use_frame = self.create_collapsible_frame(self.center_inner, "Bild verwenden", row=1)
        # Setze Standardwert für "Bild verwenden" basierend auf aktueller Sprache
        current_options = self.config_manager.get_language_specific_list('use_image_options')
        default_use_image = current_options[0] if current_options else "ja"
        self.use_image_var = tk.StringVar(value=default_use_image)
        # Radio-Optionen responsiv anordnen
        _use_widgets = []
        for option in self.config_manager.get_language_specific_list('use_image_options'):
            w = tk.Radiobutton(self.use_frame['content'], text=option, variable=self.use_image_var, 
                               value=option, command=self.save_current_evaluation_delayed, font=einheits_font)
            _use_widgets.append(w)
        use_container = ttk.Frame(self.use_frame['content'])
        use_container.pack(fill=tk.X)
        self._render_options_responsive(use_container, [
            tk.Radiobutton(use_container, text=opt, variable=self.use_image_var, value=opt,
                           command=self.save_current_evaluation_delayed, font=einheits_font)
            for opt in self.config_manager.get_language_specific_list('use_image_options')
        ])
        
        # Schadenskategorien - Kollapsible
        self.damage_frame = self.create_collapsible_frame(self.center_inner, " Schadenskategorien", row=2)
        self.damage_vars = {}
        damage_container = ttk.Frame(self.damage_frame['content'])
        damage_container.pack(fill=tk.X)
        damage_widgets = []
        for category in self.config_manager.get_language_specific_list('damage_categories'):
            var = tk.BooleanVar()
            self.damage_vars[category] = var
            damage_widgets.append(
                tk.Checkbutton(damage_container, text=category, variable=var,
                               command=self.save_current_evaluation_delayed, font=einheits_font)
            )
        self._render_options_responsive(damage_container, damage_widgets)
        
        # Bildart-Kategorien - Kollapsible
        self.image_type_frame = self.create_collapsible_frame(self.center_inner, "📸 Bildart-Kategorien", row=3)
        self.image_type_vars = {}
        image_type_container = ttk.Frame(self.image_type_frame['content'])
        image_type_container.pack(fill=tk.X)
        image_type_widgets = []
        for img_type in self.config_manager.get_language_specific_list('image_types'):
            var = tk.BooleanVar()
            self.image_type_vars[img_type] = var
            image_type_widgets.append(
                tk.Checkbutton(image_type_container, text=img_type, variable=var,
                               command=self.save_current_evaluation_delayed, font=einheits_font)
            )
        self._render_options_responsive(image_type_container, image_type_widgets)
        
        # Schadensbewertung - Kollapsible
        self.quality_frame = self.create_collapsible_frame(self.center_inner, "⚖ Schadensbewertung", row=4)
        self.image_quality_var = tk.StringVar(value="Unknown")
        quality_container = ttk.Frame(self.quality_frame['content'])
        quality_container.pack(fill=tk.X)
        quality_widgets = []
        for option in self.config_manager.get_language_specific_list('image_quality_options'):
            quality_widgets.append(
                tk.Radiobutton(quality_container, text=option, variable=self.image_quality_var,
                               value=option, command=self.save_current_evaluation_delayed, font=einheits_font)
            )
        self._render_options_responsive(quality_container, quality_widgets)
        
        # Rechte Spalte (eigene Spalte) - Fortschritt und Kategorien-Tree (Spalte 2)
        self.progress_column = ttk.Frame(self.main_split)
        self.progress_column.grid(row=0, column=2, sticky="nsew")
        
        # Konfiguriere Spalten- und Zeilengewichte für vertikales Resizing
        self.progress_column.grid_columnconfigure(0, weight=1)  # Spalte expandiert horizontal
        self.progress_column.grid_rowconfigure(0, weight=0)  # Fortschrittsbalken nimmt nur benötigten Platz
        self.progress_column.grid_rowconfigure(1, weight=1)  # Treeview-Bereich expandiert vertikal
        
        # Kompakte Bewertungsfortschritt-Anzeige (ohne LabelFrame-Rand)
        counts_frame = ttk.Frame(self.progress_column, padding=4)
        counts_frame.grid(row=0, column=0, sticky="ew")
        
        # Fortschrittsbalken (kompakt)
        self.evaluation_progress = ttk.Progressbar(counts_frame, mode='determinate', 
                                                  length=200, style="Custom.Horizontal.TProgressbar")
        self.evaluation_progress.pack(fill=tk.X, pady=(0, 2))
        
        # Fortschritts-Zahlen direkt unter Balken
        self.evaluation_progress_label = ttk.Label(counts_frame, 
                                                  text="Bearbeitet 0 von 0",
                                                  font=("Segoe UI", FONT_SIZES['tiny']),
                                                  foreground=COLORS['text_secondary'])
        self.evaluation_progress_label.pack()
        
        # Zusätzliche Statistiken (entfernt für kompaktere Anzeige auf der rechten Seite)
        
        # Initialisiere Fortschrittsanzeige
        self.update_evaluation_progress()
        
        # Hinweis: "Alle Bewertungen zurücksetzen" wurde ins Menü Extras verschoben
        
        # Kategorien-Treeview für Fortschrittsanzeige (ohne Rahmen/Überschrift)
        categories_frame = ttk.Frame(self.progress_column, padding=5)
        categories_frame.grid(row=1, column=0, sticky="nsew", pady=(5, 0))
        categories_frame.grid_rowconfigure(0, weight=1)
        
        # Treeview für Kategorien und Kürzel (maximale Höhe und größere Schrift)
        self.categories_tree = ttk.Treeview(categories_frame, columns=('progress',), show='tree headings', height=25)
        self.categories_tree.heading('#0', text='Kategorie/Kürzel')
        self.categories_tree.heading('progress', text='Fortschritt')
        self.categories_tree.column('#0', width=200)
        self.categories_tree.column('progress', width=100)
        
        # Konfiguriere Schriftgröße (kompakt)
        style = ttk.Style()
        style.configure("Treeview", font=("TkDefaultFont", 10), rowheight=18)  # Kompaktere Schrift und Zeilenhöhe
        style.configure("Treeview.Heading", font=("TkDefaultFont", 11, "bold"))  # Kleinere Überschriften
        
        # Scrollbar für Treeview
        categories_scrollbar = ttk.Scrollbar(categories_frame, orient=tk.VERTICAL, command=self.categories_tree.yview)
        self.categories_tree.configure(yscrollcommand=categories_scrollbar.set)
        
        # Tags für Farben konfigurieren
        self.categories_tree.tag_configure('completed', background='#C8E6C9', foreground='#2E7D32', font=("TkDefaultFont", 10, "bold"))
        
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

    def toggle_progress_panel(self):
        """Klappt die rechte Fortschrittsspalte ein/aus und passt Griff-Pfeil an."""
        try:
            if not hasattr(self, 'progress_collapsed'):
                self.progress_collapsed = False
            self.progress_collapsed = not self.progress_collapsed
            if self.progress_collapsed:
                # Rechte Spalte ausblenden und Griffpfeil nach rechts zeigen
                if hasattr(self, 'progress_column'):
                    self.progress_column.grid_remove()
                if hasattr(self, 'progress_handle_button'):
                    self.progress_handle_button.config(text="▶")
                # Content-Spalte bekommt mehr Platz (Gewichte anpassen)
                try:
                    self.main_split.grid_columnconfigure(0, weight=1)
                    self.main_split.grid_columnconfigure(2, weight=0)
                except Exception:
                    pass
            else:
                # Rechte Spalte einblenden und Griffpfeil nach links zeigen
                if hasattr(self, 'progress_column'):
                    self.progress_column.grid(row=0, column=2, sticky="nsew")
                if hasattr(self, 'progress_handle_button'):
                    self.progress_handle_button.config(text="◀")
                try:
                    self.main_split.grid_columnconfigure(0, weight=4)
                    self.main_split.grid_columnconfigure(2, weight=1)
                except Exception:
                    pass
        except Exception:
            pass

    # ------------------------ Responsive Options Rendering ------------------------
    def _render_options_responsive(self, container, widgets, min_two_col_width=320):
        """Ordnet eine Liste von Widgets in 1–2 Spalten an, abhängig von der Breite des Containers."""
        if not hasattr(container, '_responsive_widgets'):
            container._responsive_widgets = widgets

            def _relayout(event=None):
                try:
                    width = container.winfo_width()
                    cols = 2 if width >= min_two_col_width else 1
                    for i, w in enumerate(container._responsive_widgets):
                        r = i // cols
                        c = i % cols
                        w.grid(row=r, column=c, sticky='w', padx=(0, 8), pady=2)
                    for c in range(2):
                        container.grid_columnconfigure(c, weight=1 if cols == 2 else 0)
                except Exception:
                    pass
            container.bind('<Configure>', _relayout)
            # Initiales Layout
            container.after(0, _relayout)

    def _init_theme(self):
        """Initialisiert ein modernes Theme, falls verfügbar, und setzt kompakte Abstände."""
        try:
            # Optionales modernes Theme via ttkbootstrap
            from ttkbootstrap import Style  # type: ignore
            try:
                self.style = Style(theme="flatly")
            except Exception:
                self.style = Style()
            try:
                self.style.master = self  # type: ignore[attr-defined]
            except Exception:
                pass
            self.style.configure("TCheckbutton", padding=(2, 2))
            self.style.configure("TRadiobutton", padding=(2, 2))
            self.style.configure("TLabelframe", padding=6)
            self.style.configure("TLabelframe.Label", font=("Segoe UI", 10, "bold"))
        except Exception:
            # Fallback: Standard-ttk leicht verdichten
            try:
                style = ttk.Style()
                style.configure("TCheckbutton", padding=(2, 2))
                style.configure("TRadiobutton", padding=(2, 2))
                style.configure("TLabelframe", padding=6)
                style.configure("TLabelframe.Label", font=("Segoe UI", 10, "bold"))
            except Exception:
                pass

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
        """Speichert die aktuelle Bewertung in EXIF-Daten (sofort)"""
        self._save_evaluation_immediate()
    
    def save_current_image_completely(self):
        """Speichert sowohl Bewertungsdaten als auch Zeichnungen"""
        # 1. Bewertungsdaten speichern
        self._save_evaluation_immediate()
        
        # 2. Zeichnungen speichern (falls vorhanden) - ohne Popups
        drawing_items = self.canvas.find_withtag('permanent_drawing')
        if drawing_items:
            success = self.save_drawing_to_file(show_popups=False)
            if success:
                # Markiere, dass Zeichnungen gespeichert wurden
                self._drawings_saved_for_current_image = True
                # Zeige nur eine kurze Bestätigung in der Statusleiste
                self.status_var.set("Bild und Zeichnungen gespeichert")
            else:
                self.status_var.set("Fehler beim Speichern der Zeichnungen")
        else:
            self.status_var.set("Bild gespeichert")
    
    def save_current_evaluation_delayed(self):
        """Speichert die aktuelle Bewertung verzögert (für bessere UI-Responsivität)"""
        # Cancel previous timer if exists
        if hasattr(self, '_save_timer') and self._save_timer:
            self.after_cancel(self._save_timer)
        
        # Schedule save after 100ms delay
        self._save_timer = self.after(100, self._save_evaluation_immediate)
    
    def _save_evaluation_immediate(self):
        """Interne Funktion zum sofortigen Speichern der Bewertung"""
        if not self.files:
            return
        
        fname = self.files[self.index]
        path = os.path.join(self.source_dir, fname)
        
        # Lade bestehende EXIF-Daten
        exif_data = get_exif_usercomment(path)
        if exif_data is None:
            # WICHTIG: Keine globale Konfiguration in das Bild schreiben!
            # Neu angelegte Bewertungen starten mit leerem JSON.
            exif_data = {}
        
        # Sammle Bewertungsdaten
        damage_categories = [cat for cat, var in self.damage_vars.items() if var.get()]
        image_types = [img_type for img_type, var in self.image_type_vars.items() if var.get()]
        
        # Aktualisiere EXIF-Daten
        exif_data["damage_categories"] = damage_categories
        # Zusätzlich pro Kategorie boolean für Galerie-Status schreiben
        try:
            for cat in self.config_manager.get_language_specific_list('damage_categories'):
                exif_data[cat] = (cat in damage_categories)
        except Exception:
            pass
        exif_data["image_types"] = image_types
        # Vereinheitlichung: Schlüssel groß wie im restlichen Code
        exif_data["UseImage"] = self.use_image_var.get()
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
        
        # Lade Schadenskategorien - robust zu verschiedenen Formaten
        damage_categories = exif_data.get("damage_categories", [])
        
        # Prüfe ob damage_categories ein dict mit Sprachen ist
        if isinstance(damage_categories, dict):
            # Verwende die aktuelle Sprache oder fallback auf 'de' oder 'en'
            current_lang = self.config_manager.current_language if hasattr(self.config_manager, 'current_language') else 'de'
            damage_categories = damage_categories.get(current_lang, damage_categories.get('de', damage_categories.get('en', [])))
        
        for category, var in self.damage_vars.items():
            # Erlaube beides: Liste in damage_categories ODER einzelne True/False-Flags
            in_list = category in damage_categories
            flag = bool(exif_data.get(category, False))
            var.set(in_list or flag)
        
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
        use_image = exif_data.get("UseImage", exif_data.get("use_image", "ja"))
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
        columns = ('order', 'kurzel_code', 'name_de', 'name_en', 'category', 'image_type_assignment', 'active')
        tree = ttk.Treeview(main_frame, columns=columns, show='headings', height=24)
        
        # Spalten definieren
        tree.heading('order', text='Reihenfolge')
        tree.heading('kurzel_code', text='Kürzel')
        tree.heading('name_de', text='Name (DE)')
        tree.heading('name_en', text='Name (EN)')
        tree.heading('category', text='Kategorie')
        tree.heading('image_type_assignment', text='Bildart-Zuordnung')
        tree.heading('active', text='Aktiv')
        
        tree.column('order', width=100, anchor='center')
        tree.column('kurzel_code', width=100)
        tree.column('name_de', width=200)
        tree.column('name_en', width=200)
        tree.column('category', width=150)
        tree.column('image_type_assignment', width=150)
        tree.column('active', width=80)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        
        # Reduzierte Zeilenhöhe für mehr Einträge sichtbar
        try:
            style = ttk.Style(tree)
            style.configure('Treeview', rowheight=18)
        except Exception:
            pass
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
        # Sortierung: zuerst nach Reihenfolge (order), dann nach Kürzel
        def _sort_key(item):
            code, d = item
            try:
                order_val = int(d.get('order', 0))
            except Exception:
                order_val = 0
            return (order_val, code)
        for kurzel_code, data in sorted(kurzel_data.items(), key=_sort_key):
            tree.insert('', 'end', values=(
                int(data.get('order', 0) or 0),
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
        
        def _sort_key(item):
            code, d = item
            try:
                order_val = int(d.get('order', 0))
            except Exception:
                order_val = 0
            return (order_val, code)
        for kurzel_code, data in sorted(kurzel_data.items(), key=_sort_key):
            tree.insert('', 'end', values=(
                int(data.get('order', 0) or 0),
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

        def on_save():
            try:
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

                self.config_manager.save_config()
                
                # Aktualisiere valid_kurzel aus der Kürzel-Tabelle (einzige Wahrheit)
                self.update_valid_kurzel_from_table()

                messagebox.showinfo("Gespeichert", "Konfiguration wurde erfolgreich gespeichert.\nEinige Änderungen erfordern einen Neustart.", parent=win)
                self.correct_combo['values'] = self.valid_kurzel

                # Aktualisiere die Kürzel-Tabelle
                if hasattr(self, 'refresh_kurzel_table'):
                    self.refresh_kurzel_table()
                win.destroy()

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
        columns = ('Reihenfolge', 'Kürzel', 'Name (DE)', 'Name (EN)', 'Kategorie', 'Bildart-Zuordnung', 'Beschreibung (DE)', 'Beschreibung (EN)', 'Aktiv')
        self.kurzel_tree = ttk.Treeview(parent, columns=columns, show='headings', height=15)
        
        # Spalten konfigurieren
        for col in columns:
            self.kurzel_tree.heading(col, text=col)
            if col == 'Reihenfolge':
                self.kurzel_tree.column(col, width=90, anchor='center')
            elif col == 'Kürzel':
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
        
        # Reduziere Zeilenhöhe über Style
        try:
            style = ttk.Style(self.kurzel_tree)
            style.configure('Treeview', rowheight=18)
        except Exception:
            pass
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
            # Sortiere nach 'order' (Reihenfolge), dann nach Kürzel
            def _sort_key(item):
                code, data = item
                try:
                    order_val = int(data.get('order', 0))
                except Exception:
                    order_val = 0
                return (order_val, code)
            for kurzel_code, kurzel_data in sorted(kurzel_table.items(), key=_sort_key):
                values = (
                    int(kurzel_data.get('order', 0) or 0),
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
            
            # Aktualisiere valid_kurzel aus der Kürzel-Tabelle (einzige Wahrheit)
            self.update_valid_kurzel_from_table()
            
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
                self.config_manager.save_config()
                
                # Aktualisiere valid_kurzel aus der Kürzel-Tabelle (einzige Wahrheit)
                self.update_valid_kurzel_from_table()
            
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
        """Event-Handler für Fenstergrößenänderungen - zentriert das Bild neu und speichert Größe"""
        # Nur auf Hauptfenster-Events reagieren, nicht auf Child-Widgets
        if event.widget == self:
            # Speichere neue Fenstergröße in der Konfiguration
            self.config_manager.set_setting('display.window_width', event.width)
            self.config_manager.set_setting('display.window_height', event.height)
            self.config_manager.set_setting('display.window_x', event.x)
            self.config_manager.set_setting('display.window_y', event.y)
            
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
                
                # Berechne Zentrum mit Pan-Offset
                center_x = c_w // 2 + self.pan_x
                center_y = c_h // 2 + self.pan_y
                
                # Lösche NUR das Bild (nicht die Zeichnungen)
                if hasattr(self, 'canvas_image_id'):
                    self.canvas.delete(self.canvas_image_id)
                
                # Zeige Bild zentriert im Canvas
                self.canvas_image_id = self.canvas.create_image(center_x, center_y, image=self.photo, anchor='center')
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
        
        # Reset das Flag für gespeicherte Zeichnungen beim Wechseln zu einem neuen Bild
        if hasattr(self, '_drawings_saved_for_current_image'):
            self._drawings_saved_for_current_image = False
        
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
            
            # Canvas-Größe holen
            self.canvas.update_idletasks()
            c_w = self.canvas.winfo_width()
            c_h = self.canvas.winfo_height()
            if c_w < 10 or c_h < 10:
                c_w, c_h = 800, 500
            
            # Berechne optimale Bildgröße - passt sich an Canvas an, aber nicht größer als Original
            scale = min(c_w / w, c_h / h, 1.0)
            new_w = int(w * scale)
            new_h = int(h * scale)
            
            # Skaliere Bild auf optimale Größe
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
            # Zoom/Pan zurücksetzen bei neuem Bild
            self.zoom_factor = 1.0
            self.pan_x = 0
            self.pan_y = 0
            
            # Zeichnungs-History löschen bei neuem Bild
            self.clear_drawing_history()
            
            # Lösche alle Canvas-Inhalte (auch die initialen Texte)
            self.canvas.delete("all")
            
            
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
            
            # Lade gespeicherte Zeichnungen aus EXIF-Daten
            self.load_drawings_from_exif()
            
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
        # Prüfe ob Zeichnungen bereits gespeichert wurden
        if hasattr(self, '_drawings_saved_for_current_image') and self._drawings_saved_for_current_image:
            # Zeichnungen wurden bereits gespeichert, Flag zurücksetzen
            self._drawings_saved_for_current_image = False
            return True  # Weiter zum nächsten Bild
        
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
            " Ordner öffnen": "Öffnet einen Ordner mit Bildern zur Analyse\nTastenkürzel: Ctrl+O",
            "📊 Excel laden": "Lädt Excel-Grunddaten für das Projekt\nEnthält Kürzel-Informationen und Metadaten",
            " Analysieren": "Startet die automatische OCR-Analyse aller Bilder\nTastenkürzel: Ctrl+A",
            "🔄 Aktualisieren": "Aktualisiert die Bildliste und Fortschrittsanzeige\nTastenkürzel: F5",
            "⚙ Einstellungen": "Öffnet die Einstellungen und Konfiguration\nTastenkürzel: Ctrl+,",
            " Log": "Zeigt das detaillierte Anwendungslog an\nFür Debugging und Fehleranalyse",
            "📋 OCR Log": "Zeigt das OCR-spezifische Log an\nOCR-Erkennungsdetails und Ergebnisse",
            "◀ Vorher": "Zeigt das vorherige Bild an\nTastenkürzel: Pfeil links",
            "Zoom & Markieren": "Öffnet das Zoom-Fenster mit Markierungs-Tools\nFür detaillierte Bildanalyse",
            "Nächste ▶": "Zeigt das nächste Bild an\nTastenkürzel: Pfeil rechts",
            "✓ In Ordnung": "Markiert das Bild als 'In Ordnung' und geht zum nächsten\nAutomatisch aktiviert erste Schadenskategorie",
            "🚫": "Markiert das Bild als 'Nicht verwenden' und geht zum nächsten\nSetzt 'Bild verwenden' auf 'nein'",
            "🖱 Mausrad": "Aktiviert/Deaktiviert Mausrad-Navigation\nMausrad nach oben = vorheriges Bild\nMausrad nach unten = nächstes Bild"
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
                                relief="flat", bd=0, padx=4, pady=2, highlightthickness=0)
        arrow_button.pack(fill=tk.X)
        
        # Content-Frame
        content_frame = ttk.Frame(main_frame)
        if not default_collapsed:
            content_frame.pack(fill=tk.X, padx=(6, 0), pady=(0, 4))
        
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
                                           fill=draw_color, width=line_width, tags="permanent_drawing")
                    undo_stack.append(('arrow', item, drawing_points[0][0], drawing_points[0][1], event.x, event.y))
                    redo_stack.clear()
                    has_unsaved_changes = True
                    
                elif draw_mode == 'circle':
                    x0, y0 = drawing_points[0]
                    r = ((event.x - x0)**2 + (event.y - y0)**2)**0.5
                    item = canvas.create_oval(x0 - r, y0 - r, x0 + r, y0 + r, 
                                           outline=draw_color, width=line_width, tags="permanent_drawing")
                    undo_stack.append(('circle', item, x0, y0, r))
                    redo_stack.clear()
                    has_unsaved_changes = True
                    
                elif draw_mode == 'rectangle':
                    x0, y0 = drawing_points[0]
                    item = canvas.create_rectangle(x0, y0, event.x, event.y, 
                                                outline=draw_color, width=line_width, tags="permanent_drawing")
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
                                           arrow=tk.LAST, fill=draw_color, width=line_width, tags="permanent_drawing")
                elif item_data[0] == 'circle':
                    item = canvas.create_oval(item_data[2] - item_data[4], item_data[3] - item_data[4],
                                           item_data[2] + item_data[4], item_data[3] + item_data[4],
                                           outline=draw_color, width=line_width, tags="permanent_drawing")
                elif item_data[0] == 'rectangle':
                    item = canvas.create_rectangle(item_data[2], item_data[3], item_data[4], item_data[5],
                                                outline=draw_color, width=line_width, tags="permanent_drawing")
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
                try:
                    last_folder_file = LAST_FOLDER_FILE
                except NameError:
                    last_folder_file = os.path.join(os.path.dirname(__file__), 'last_folder.txt')
                
                with open(last_folder_file, 'w', encoding='utf-8') as f:
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
    def ocr_method_feste_koordinaten(self, image, debug=False, enable_post_processing=True):
        """Verbesserte OCR mit automatischer Box-Detection, Upscaling und Post-Processing."""
        import numpy as np
        import cv2
        
        try:
            # Bild für OpenCV vorbereiten (PIL -> OpenCV BGR)
            if isinstance(image, Image.Image):
                img_bgr = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
            else:
                img_bgr = image

            # Koordinaten aus der Konfiguration
            crop_coords = self.json_config.get('crop_coordinates', {})

            # Versuch 1: Automatische Box-Detection mit EasyOCR
            detected_box = find_text_box_easyocr(img_bgr, crop_coords, self.valid_kurzel)

            if detected_box:
                # Box gefunden - verwende diese für OCR
                x, y, w, h = detected_box
                roi_bgr = img_bgr[y:y+h, x:x+w]
                if debug:
                    print(f"Auto-detected Box: x={x}, y={y}, w={w}, h={h}")
            else:
                # Fallback: Verwende feste Koordinaten
                x = crop_coords.get('x', 10)
                y = crop_coords.get('y', 10)
                w = crop_coords.get('w', 60)
                h = crop_coords.get('h', 35)
                roi_bgr = img_bgr[y:y+h, x:x+w]
                if debug:
                    print(f"Using fixed coordinates: x={x}, y={y}, w={w}, h={h}")

            # Optional: Debug-Vorschau
            if debug:
                try:
                    import matplotlib.pyplot as plt
                    plt.figure("OCR Debug: Erkannter Bereich")
                    plt.imshow(cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2RGB))
                    plt.title("Bereich für OCR (Auto-Detection oder Fix)")
                    plt.show()
                except Exception as e:
                    print(f"Debug-Vorschau fehlgeschlagen: {e}")

            # Verbesserte OCR mit Upscaling und Post-Processing
            text, replacements = run_ocr_easyocr_improved(roi_bgr, enable_post_processing)

            # Alternative Kürzel-Korrektur
            if text and not text.startswith("[") and self.json_config.get('ocr_settings', {}).get('alternative_kurzel_enabled', True):
                from core_ocr import correct_alternative_kurzel
                alternative_kurzel = self.json_config.get('alternative_kurzel', {})
                corrected_text = correct_alternative_kurzel(text, alternative_kurzel)
                if corrected_text != text and corrected_text in self.valid_kurzel:
                    if debug:
                        print(f"Alternative Kürzel-Korrektur: {text} -> {corrected_text}")
                    text = corrected_text

            # Fuzzy-Matching gegen gültige Kürzel
            if text and not text.startswith("["):
                from difflib import get_close_matches
                text_clean = text.upper().strip()
                matches = get_close_matches(text_clean, self.valid_kurzel, n=1, cutoff=0.7)
                if matches:
                    if debug:
                        print(f"Fuzzy-Match: {text_clean} -> {matches[0]}")
                    text = matches[0]

            return {
                'text': text,
                'confidence': 1.0 if text and not text.startswith("[") else 0.0,
                'raw_text': text or '',
                'method': 'improved_easyocr',
                'replacements': replacements if enable_post_processing else []
            }
            
        except Exception as e:
            write_detailed_log("error", "Fehler in ocr_method_feste_koordinaten", str(e), exception=e)
            return {
                'text': None,
                'confidence': 0.0,
                'raw_text': f'[Error: {str(e)}]',
                'method': 'improved_easyocr_error',
                'replacements': []
            }

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
        """Setzt Zoom zurück und zentriert das Bild"""
        self.zoom_factor = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.update_zoom_display()
        self.center_image()  # Verwende center_image für perfekte Zentrierung

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
            
            # Berechne Canvas-Zentrum
            self.canvas.update_idletasks()
            c_w = self.canvas.winfo_width()
            c_h = self.canvas.winfo_height()
            
            if c_w < 10 or c_h < 10:
                return  # Canvas noch nicht bereit
            
            # Bild zentriert mit Pan-Offset zeichnen
            center_x = c_w // 2 + self.pan_x
            center_y = c_h // 2 + self.pan_y
            
            self.canvas_image_id = self.canvas.create_image(
                center_x, center_y, 
                image=self.photo, 
                anchor='center'
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
    
    def save_drawing_to_file(self, show_popups=True):
        """Speichert Zeichnungsdaten in EXIF-Daten (nicht direkt ins Bild)"""
        if not hasattr(self, 'current_image') or not self.files:
            if show_popups:
                messagebox.showwarning("Warnung", "Kein Bild geladen")
            return False
        
        # Prüfe, ob überhaupt Zeichnungen vorhanden sind
        drawing_items = self.canvas.find_withtag('permanent_drawing')
        if not drawing_items:
            if show_popups:
                messagebox.showinfo("Info", "Keine Zeichnungen zum Speichern vorhanden")
            return False
        
        try:
            from utils_exif import get_exif_usercomment, save_exif_usercomment
            
            current_file = self.files[self.index]
            filepath = os.path.join(self.source_dir, current_file)
            
            # Lade bestehende EXIF-Daten
            exif_data = get_exif_usercomment(filepath) or {}
            
            # Konvertiere Canvas-Zeichnungen zu Bild-Koordinaten und speichere sie
            drawing_data = []
            for item_id in drawing_items:
                item_type = self.canvas.type(item_id)
                coords = self.canvas.coords(item_id)
                color = self.canvas.itemcget(item_id, 'fill') or self.canvas.itemcget(item_id, 'outline')
                width = int(float(self.canvas.itemcget(item_id, 'width')))
                arrow = self.canvas.itemcget(item_id, 'arrow')
                
                # Konvertiere Canvas-Koordinaten zu Bild-Koordinaten
                img_coords = []
                for i in range(0, len(coords), 2):
                    x_canvas = float(coords[i])
                    y_canvas = float(coords[i+1])
                    
                    # Korrekte Koordinaten-Konvertierung: Canvas -> Bild
                    # Berücksichtige Pan-Verschiebung und Zoomfaktor
                    x_img = int((x_canvas - self.pan_x) / self.zoom_factor)
                    y_img = int((y_canvas - self.pan_y) / self.zoom_factor)
                    
                    # Stelle sicher, dass Koordinaten innerhalb des Bildes liegen
                    img_width, img_height = self.current_image.size
                    x_img = max(0, min(img_width - 1, x_img))
                    y_img = max(0, min(img_height - 1, y_img))
                    
                    img_coords.extend([x_img, y_img])
                
                # Speichere Zeichnungsdaten
                drawing_item = {
                    'type': item_type,
                    'coords': img_coords,
                    'color': color,
                    'width': width,
                    'arrow': arrow if arrow else None
                }
                drawing_data.append(drawing_item)
            
            # Speichere Zeichnungsdaten in EXIF
            exif_data['drawings'] = drawing_data
            
            # Speichere EXIF-Daten
            success = save_exif_usercomment(filepath, exif_data)
            
            if success:
                if show_popups:
                    messagebox.showinfo("Erfolg", f"Zeichnungen gespeichert: {current_file}")
                print(f"Zeichnungen gespeichert in EXIF: {filepath}")
                return True
            else:
                if show_popups:
                    messagebox.showerror("Fehler", "Fehler beim Speichern der Zeichnungen")
                return False
            
        except Exception as e:
            if show_popups:
                messagebox.showerror("Fehler", f"Fehler beim Speichern: {str(e)}")
            print(f"Fehler beim Speichern der Zeichnungen: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def load_drawings_from_exif(self):
        """Lädt gespeicherte Zeichnungen aus EXIF-Daten und stellt sie auf dem Canvas wieder her"""
        if not hasattr(self, 'current_image') or not self.files:
            return False
        
        try:
            from utils_exif import get_exif_usercomment
            
            current_file = self.files[self.index]
            filepath = os.path.join(self.source_dir, current_file)
            
            # Lade EXIF-Daten
            exif_data = get_exif_usercomment(filepath)
            if not exif_data or 'drawings' not in exif_data:
                return False
            
            drawing_data = exif_data['drawings']
            if not drawing_data:
                return False
            
            # Lösche alle bestehenden Zeichnungen
            self.canvas.delete('permanent_drawing')
            
            # Stelle Zeichnungen wieder her
            for drawing_item in drawing_data:
                item_type = drawing_item['type']
                img_coords = drawing_item['coords']
                color = drawing_item['color']
                width = drawing_item['width']
                arrow = drawing_item.get('arrow')
                
                # Konvertiere Bild-Koordinaten zu Canvas-Koordinaten
                canvas_coords = []
                for i in range(0, len(img_coords), 2):
                    x_img = float(img_coords[i])
                    y_img = float(img_coords[i+1])
                    
                    # Korrekte Koordinaten-Konvertierung: Bild -> Canvas
                    # Berücksichtige Pan-Verschiebung und Zoomfaktor
                    x_canvas = x_img * self.zoom_factor + self.pan_x
                    y_canvas = y_img * self.zoom_factor + self.pan_y
                    
                    canvas_coords.extend([x_canvas, y_canvas])
                
                # Erstelle Canvas-Item
                if item_type == 'line':
                    if arrow and len(canvas_coords) >= 4:
                        # Pfeil
                        item = self.canvas.create_line(
                            canvas_coords,
                            fill=color,
                            width=width,
                            arrow=tk.LAST,
                            tags='permanent_drawing'
                        )
                    else:
                        # Normale Linie
                        item = self.canvas.create_line(
                            canvas_coords,
                            fill=color,
                            width=width,
                            tags='permanent_drawing'
                        )
                elif item_type == 'oval' and len(canvas_coords) >= 4:
                    item = self.canvas.create_oval(
                        canvas_coords,
                        outline=color,
                        width=width,
                        tags='permanent_drawing'
                    )
                
                elif item_type == 'rectangle' and len(canvas_coords) >= 4:
                    item = self.canvas.create_rectangle(
                        canvas_coords,
                        outline=color,
                        width=width,
                        tags='permanent_drawing'
                    )
            
            print(f"Zeichnungen geladen aus EXIF: {len(drawing_data)} Elemente")
            return True
            
        except Exception as e:
            print(f"Fehler beim Laden der Zeichnungen: {e}")
            import traceback
            traceback.print_exc()
            return False
    
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
        elif tab_text == "🖼 Galerie":
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
        
        # Galerie-Container ausblenden, Einzelbild-Container zeigen
        if hasattr(self, 'gallery_view_container'):
            for child in self.gallery_view_container.winfo_children():
                child.destroy()
            self.gallery_view_container.grid_remove()
        if hasattr(self, 'content_frame'):
            self.content_frame.grid()
        
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
                # Thumbnails neu laden wenn Galerie bereits existiert
                if hasattr(self, 'gallery_scrollable_frame'):
                    self.load_gallery_thumbnails()
            except Exception:
                pass
        else:
            # Fallback: getrennte Container ohne Tabs
            if hasattr(self, 'view_menu'):
                self.view_menu.entryconfig("📷 Galerie-Ansicht", label="🖼 Einzelbild-Ansicht")
            if hasattr(self, 'content_frame'):
                self.content_frame.grid_remove()
            if hasattr(self, 'gallery_view_container'):
                self.gallery_view_container.grid()
            self.create_gallery_view()
    
    def create_gallery_view(self):
        """Erstellt die Galerie-Ansicht im Galerie-Tab (Notebook) mit Split-View"""
        # Zielcontainer bestimmen: bei Tabs in gallery_view_tab, sonst eigener Galerie-Container
        target_parent = getattr(self, 'gallery_view_tab', None) or self.gallery_view_container
        # Vorherige Inhalte entfernen
        for child in target_parent.winfo_children():
            child.destroy()
        
        # Galerie-Frame erstellen
        self.gallery_frame = ttk.Frame(target_parent, style="TFrame")
        # Im separaten Container vollflächig packen
        self.gallery_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Grid-Layout für 3-Spalten-View konfigurieren
        self.gallery_frame.grid_columnconfigure(0, weight=0)  # Spalte 0: Schadensbewertung (feste Breite)
        self.gallery_frame.grid_columnconfigure(1, weight=1)  # Spalte 1: Galerie (expandiert)
        self.gallery_frame.grid_columnconfigure(2, weight=0)  # Spalte 2: Großes Bild (feste Breite)
        self.gallery_frame.grid_rowconfigure(1, weight=1)  # Hauptinhalt expandiert vertikal
        
        # Galerie-Header mit Filter (über alle drei Spalten)
        header_frame = ttk.Frame(self.gallery_frame)
        header_frame.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(5, 15), padx=10)
        
        ttk.Label(header_frame, text=" OCR-Tag Filter:", 
                 font=("Segoe UI", FONT_SIZES['heading'], "bold"),
                 foreground=COLORS['text_primary']).pack(side=tk.LEFT, padx=(0, 10))
        
        # Tag-Dropdown mit Navigation-Pfeilen
        tag_frame = tk.Frame(header_frame)
        tag_frame.pack(side=tk.LEFT, padx=(0, 15))
        
        # Vorheriger Tag Button
        prev_btn = tk.Button(tag_frame, text="◀", font=("Segoe UI", 12, "bold"),
                           command=self.previous_gallery_tag,
                           bg=COLORS['bg_medium'], fg=COLORS['text_primary'],
                           relief="flat", bd=0, padx=5)
        prev_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # Tag-Dropdown
        available_tags = self.get_available_ocr_tags()
        self.gallery_tag_var = tk.StringVar(value=self.gallery_current_tag or "Alle")
        tag_combo = ttk.Combobox(tag_frame, textvariable=self.gallery_tag_var, 
                                values=["Alle"] + available_tags, width=15, state="readonly",
                                font=("Segoe UI", FONT_SIZES['body']))
        tag_combo.pack(side=tk.LEFT, padx=5)
        tag_combo.bind("<<ComboboxSelected>>", self.on_gallery_tag_changed)
        
        # Nächster Tag Button
        next_btn = tk.Button(tag_frame, text="▶", font=("Segoe UI", 12, "bold"),
                           command=self.next_gallery_tag,
                           bg=COLORS['bg_medium'], fg=COLORS['text_primary'],
                           relief="flat", bd=0, padx=5)
        next_btn.pack(side=tk.LEFT, padx=(5, 0))
        
        # Thumbnail-Größe-Buttons
        size_frame = tk.Frame(header_frame)
        size_frame.pack(side=tk.LEFT, padx=(20, 0))
        
        ttk.Label(size_frame, text=" Größe:", 
                 font=("Segoe UI", FONT_SIZES['body']),
                 foreground=COLORS['text_primary']).pack(side=tk.LEFT, padx=(0, 5))
        
        # Kleine Thumbnails (125 * 1.30 = 163)
        small_btn = tk.Button(size_frame, text="S", font=("Segoe UI", 10, "bold"),
                            command=lambda: self.set_thumbnail_size(163),
                            bg=COLORS['bg_medium'], fg=COLORS['text_primary'],
                            relief="flat", bd=0, padx=8, pady=2)
        small_btn.pack(side=tk.LEFT, padx=(0, 3))
        
        # Mittlere Thumbnails (188 * 1.30 = 244)
        medium_btn = tk.Button(size_frame, text="M", font=("Segoe UI", 10, "bold"),
                             command=lambda: self.set_thumbnail_size(244),
                             bg=COLORS['bg_medium'], fg=COLORS['text_primary'],
                             relief="flat", bd=0, padx=8, pady=2)
        medium_btn.pack(side=tk.LEFT, padx=(0, 3))
        
        # Große Thumbnails (250 * 1.30 = 325)
        large_btn = tk.Button(size_frame, text="L", font=("Segoe UI", 10, "bold"),
                            command=lambda: self.set_thumbnail_size(325),
                            bg=COLORS['bg_medium'], fg=COLORS['text_primary'],
                            relief="flat", bd=0, padx=8, pady=2)
        large_btn.pack(side=tk.LEFT, padx=(0, 3))
        
        # Extra große Thumbnails (313 * 1.30 = 407)
        xlarge_btn = tk.Button(size_frame, text="XL", font=("Segoe UI", 10, "bold"),
                             command=lambda: self.set_thumbnail_size(407),
                             bg=COLORS['bg_medium'], fg=COLORS['text_primary'],
                             relief="flat", bd=0, padx=8, pady=2)
        xlarge_btn.pack(side=tk.LEFT, padx=(0, 15))
        
        # Bildanzahl-Auswahl
        count_frame = tk.Frame(header_frame)
        count_frame.pack(side=tk.LEFT, padx=(10, 0))
        
        ttk.Label(count_frame, text="📊 Anzeige:", 
                 font=("Segoe UI", FONT_SIZES['body']),
                 foreground=COLORS['text_primary']).pack(side=tk.LEFT, padx=(0, 5))
        
        # 1 Bild (1x1)
        one_btn = tk.Button(count_frame, text="1", font=("Segoe UI", 10, "bold"),
                           command=lambda: self.set_gallery_images_per_page(1),
                           bg=COLORS['bg_medium'], fg=COLORS['text_primary'],
                           relief="flat", bd=0, padx=8, pady=2)
        one_btn.pack(side=tk.LEFT, padx=(0, 3))
        
        # 4 Bilder (2x2)
        four_btn = tk.Button(count_frame, text="4", font=("Segoe UI", 10, "bold"),
                            command=lambda: self.set_gallery_images_per_page(4),
                            bg=COLORS['bg_medium'], fg=COLORS['text_primary'],
                            relief="flat", bd=0, padx=8, pady=2)
        four_btn.pack(side=tk.LEFT, padx=(0, 3))
        
        # 9 Bilder (3x3)
        nine_btn = tk.Button(count_frame, text="9", font=("Segoe UI", 10, "bold"),
                            command=lambda: self.set_gallery_images_per_page(9),
                            bg=COLORS['bg_medium'], fg=COLORS['text_primary'],
                            relief="flat", bd=0, padx=8, pady=2)
        nine_btn.pack(side=tk.LEFT, padx=(0, 3))
        
        # 12 Bilder (4x3)
        twelve_btn = tk.Button(count_frame, text="12", font=("Segoe UI", 10, "bold"),
                              command=lambda: self.set_gallery_images_per_page(12),
                              bg=COLORS['bg_medium'], fg=COLORS['text_primary'],
                              relief="flat", bd=0, padx=8, pady=2)
        twelve_btn.pack(side=tk.LEFT)
        
        # Auto-Filter: Aktuelles Bild-Tag
        if self.files and self.index < len(self.files):
            current_tag = self.get_current_image_ocr_tag()
            if current_tag and current_tag in available_tags:
                self.gallery_tag_var.set(current_tag)
                self.gallery_current_tag = current_tag
        
        # Spalte 0: Schadensbewertung (immer sichtbar, nur so viel Platz wie nötig)
        self.gallery_damage_panel = ttk.Frame(self.gallery_frame, style="TFrame")
        self.gallery_damage_panel.grid(row=1, column=0, sticky="nsew", padx=(10, 5), pady=(0, 0))
        # Keine feste Breite - passt sich dem Inhalt an, aber nimmt vertikalen Platz ein
        
        # Spalte 1: Scrollable Frame für Thumbnails
        canvas_frame = ttk.Frame(self.gallery_frame)
        canvas_frame.grid(row=1, column=1, sticky="nsew", padx=5, pady=(0, 0))
        
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
        
        # Paginierungs-Controls unter der Galerie
        pagination_frame = tk.Frame(self.gallery_frame, bg=COLORS['bg_light'], height=50)
        pagination_frame.grid(row=2, column=1, sticky="ew", padx=10, pady=(0, 10))
        pagination_frame.pack_propagate(False)
        
        # Vorherige Seite Button
        prev_page_btn = tk.Button(pagination_frame, text="◀ Vorherige", 
                                  font=("Segoe UI", 10, "bold"),
                                  command=self.gallery_previous_page,
                                  bg=COLORS['bg_medium'], fg=COLORS['text_primary'],
                                  relief="flat", bd=0, padx=15, pady=8)
        prev_page_btn.pack(side=tk.LEFT, padx=(10, 5))
        
        # Seiten-Anzeige (wird dynamisch aktualisiert)
        self.gallery_page_label = tk.Label(pagination_frame, text="Seite 1 von 1",
                                          font=("Segoe UI", 10),
                                          bg=COLORS['bg_light'], fg=COLORS['text_primary'])
        self.gallery_page_label.pack(side=tk.LEFT, padx=20)
        
        # Nächste Seite Button
        next_page_btn = tk.Button(pagination_frame, text="Nächste ▶", 
                                 font=("Segoe UI", 10, "bold"),
                                 command=self.gallery_next_page,
                                 bg=COLORS['bg_medium'], fg=COLORS['text_primary'],
                                 relief="flat", bd=0, padx=15, pady=8)
        next_page_btn.pack(side=tk.LEFT, padx=(5, 10))
        
        # Rechte Spalte: Großes Bild (feste Breite = 400px)
        # Spalte 2: Großes Bild (resizable)
        self.gallery_large_image_panel = ttk.Frame(self.gallery_frame, style="TFrame")
        self.gallery_large_image_panel.grid(row=1, column=2, sticky="nsew", padx=(5, 10), pady=(0, 10))
        self.gallery_large_image_panel.configure(width=400)
        self.gallery_large_image_panel.grid_propagate(False)
        
        # Schadensbewertung wird beim ersten Bild automatisch geladen
        
        ttk.Label(self.gallery_large_image_panel, 
                 text="🖼 Großes Bild\n\nBild auswählen\num große Ansicht anzuzeigen",
                 font=("Segoe UI", FONT_SIZES['body']),
                 foreground=COLORS['text_secondary'],
                 justify=tk.CENTER).pack(expand=True, pady=50)
        
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
    
    def previous_gallery_tag(self):
        """Wechselt zum vorherigen OCR-Tag"""
        available_tags = self.get_available_ocr_tags()
        if not available_tags:
            return
            
        current_index = 0
        if self.gallery_current_tag and self.gallery_current_tag in available_tags:
            current_index = available_tags.index(self.gallery_current_tag)
        
        # Vorheriger Tag
        if current_index > 0:
            self.gallery_current_tag = available_tags[current_index - 1]
        else:
            self.gallery_current_tag = available_tags[-1]  # Zum letzten springen
            
        self.gallery_tag_var.set(self.gallery_current_tag)
        self.load_gallery_thumbnails()
    
    def next_gallery_tag(self):
        """Wechselt zum nächsten OCR-Tag"""
        available_tags = self.get_available_ocr_tags()
        if not available_tags:
            return
            
        current_index = 0
        if self.gallery_current_tag and self.gallery_current_tag in available_tags:
            current_index = available_tags.index(self.gallery_current_tag)
        
        # Nächster Tag
        if current_index < len(available_tags) - 1:
            self.gallery_current_tag = available_tags[current_index + 1]
        else:
            self.gallery_current_tag = available_tags[0]  # Zum ersten springen
            
        self.gallery_tag_var.set(self.gallery_current_tag)
        self.load_gallery_thumbnails()
    
    def set_thumbnail_size(self, size):
        """Setzt die Thumbnail-Größe und lädt die Galerie neu"""
        self.thumbnail_size = size
        self.load_gallery_thumbnails()
    
    def set_gallery_images_per_page(self, count):
        """Setzt die Anzahl der Bilder pro Seite und lädt die Galerie neu"""
        self.gallery_images_per_page = count
        self.gallery_current_page = 0  # Zurück zur ersten Seite
        self.load_gallery_thumbnails()
    
    def get_damage_list_for_gallery(self, filename):
        """Gibt Liste der Schäden zurück (ohne 'Visually no defects')"""
        try:
            path = os.path.join(self.source_dir, filename)
            exif_data = get_exif_usercomment(path)
            if not exif_data:
                return []
            damage_categories = self.config_manager.get_language_specific_list('damage_categories')
            damages = []
            for cat in damage_categories:
                if cat == "Visually no defects":
                    continue
                if cat in exif_data and exif_data[cat]:
                    damages.append(cat)
            return damages
        except:
            return []
    
    def get_image_type_list_for_gallery(self, filename):
        """Gibt Liste der Bildarten/Orte zurück"""
        try:
            path = os.path.join(self.source_dir, filename)
            exif_data = get_exif_usercomment(path)
            if not exif_data:
                return []
            image_types = exif_data.get('image_types', [])
            if isinstance(image_types, list):
                return image_types
            return []
        except:
            return []
    
    def get_ocr_tag(self, filename):
        """Gibt den OCR-Tag für ein Bild zurück"""
        try:
            path = os.path.join(self.source_dir, filename)
            exif_data = get_exif_usercomment(path)
            if exif_data and "TAGOCR" in exif_data:
                return exif_data["TAGOCR"]
            return "-"
        except Exception as e:
            print(f"DEBUG get_ocr_tag Fehler für {filename}: {e}")
            return "-"
    
    def get_use_image_status(self, filename):
        """Gibt zurück, ob ein Bild verwendet wird"""
        try:
            path = os.path.join(self.source_dir, filename)
            exif_data = get_exif_usercomment(path)
            if exif_data and "UseImage" in exif_data:
                return exif_data["UseImage"] == "ja"
            return True  # Standard: Bild wird verwendet
        except Exception as e:
            print(f"DEBUG get_use_image_status Fehler für {filename}: {e}")
            return True
    
    def gallery_previous_page(self):
        """Geht zur vorherigen Seite in der Galerie"""
        if hasattr(self, 'gallery_current_page') and self.gallery_current_page > 0:
            self.gallery_current_page -= 1
            self.load_gallery_thumbnails()
    
    def gallery_next_page(self):
        """Geht zur nächsten Seite in der Galerie"""
        if not hasattr(self, 'gallery_current_page'):
            return
        
        # Berechne maximale Seitenanzahl
        if not self.files:
            return
        
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
        
        total_images = len(filtered_files)
        images_per_page = self.gallery_images_per_page if hasattr(self, 'gallery_images_per_page') else 9
        total_pages = (total_images + images_per_page - 1) // images_per_page
        
        # Nur weiter, wenn nicht letzte Seite erreicht
        if self.gallery_current_page < total_pages - 1:
            self.gallery_current_page += 1
            self.load_gallery_thumbnails()
    
    def show_damage_overlay_dialog(self, filename):
        """Zeigt ein Overlay-Dialog für Schadenskategorien-Auswahl"""
        # Neues Fenster erstellen
        damage_window = tk.Toplevel(self)
        damage_window.title(f"Schadenskategorien - {filename}")
        damage_window.geometry("400x500")
        damage_window.resizable(True, True)
        damage_window.transient(self)
        damage_window.grab_set()
        
        # Zentriere das Fenster
        damage_window.geometry("+%d+%d" % (self.winfo_rootx() + 50, self.winfo_rooty() + 50))
        
        # Header
        header_frame = tk.Frame(damage_window, bg=COLORS['bg_medium'], height=60)
        header_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        header_frame.pack_propagate(False)
        
        tk.Label(header_frame, text=f"🔧 Schadenskategorien", 
                font=("Segoe UI", 16, "bold"), 
                fg=COLORS['text_primary'], 
                bg=COLORS['bg_medium']).pack(pady=15)
        
        # Bildvorschau
        preview_frame = tk.Frame(damage_window, bg=COLORS['bg_light'], height=120)
        preview_frame.pack(fill=tk.X, padx=10, pady=5)
        preview_frame.pack_propagate(False)
        
        try:
            path = os.path.join(self.source_dir, filename)
            if os.path.exists(path):
                img = Image.open(path)
                img.thumbnail((100, 100), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                img_label = tk.Label(preview_frame, image=photo, bg=COLORS['bg_light'])
                img_label.image = photo  # Referenz halten
                img_label.pack(side=tk.LEFT, padx=10, pady=10)
        except Exception as e:
            tk.Label(preview_frame, text=" Bild nicht verfügbar", 
                    bg=COLORS['bg_light'], fg=COLORS['danger']).pack(pady=40)
        
        # Dateiname
        tk.Label(preview_frame, text=filename, 
                font=("Segoe UI", 10), 
                fg=COLORS['text_secondary'], 
                bg=COLORS['bg_light']).pack(side=tk.LEFT, padx=10, pady=40)
        
        # Schadenskategorien-Frame
        categories_frame = tk.Frame(damage_window, bg=COLORS['bg_light'])
        categories_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        # Aktuelle Bewertung laden
        path = os.path.join(self.source_dir, filename)
        exif_data = get_exif_usercomment(path)
        damage_categories = self.config_manager.get_language_specific_list('damage_categories')
        
        # Checkboxen für Schadenskategorien
        self.damage_checkboxes = {}
        for i, category in enumerate(damage_categories):
            var = tk.BooleanVar()
            if exif_data and category in exif_data and exif_data[category]:
                var.set(True)
            
            cb = tk.Checkbutton(categories_frame, text=category, variable=var,
                               font=("Segoe UI", 10), bg=COLORS['bg_light'],
                               fg=COLORS['text_primary'], selectcolor=COLORS['success'],
                               activebackground=COLORS['bg_light'], activeforeground=COLORS['text_primary'])
            cb.pack(anchor=tk.W, padx=20, pady=5)
            self.damage_checkboxes[category] = var
        
        # Button-Frame
        button_frame = tk.Frame(damage_window, bg=COLORS['bg_light'], height=60)
        button_frame.pack(fill=tk.X, padx=10, pady=(5, 10))
        button_frame.pack_propagate(False)
        
        # Speichern-Button
        save_btn = tk.Button(button_frame, text="💾 Speichern", 
                           command=lambda: self.save_damage_categories(filename, damage_window),
                           font=("Segoe UI", 12, "bold"), bg=COLORS['success'], 
                           fg='white', relief="flat", bd=0, padx=20, pady=10)
        save_btn.pack(side=tk.LEFT, padx=(10, 5))
        
        # Abbrechen-Button
        cancel_btn = tk.Button(button_frame, text=" Abbrechen", 
                             command=damage_window.destroy,
                             font=("Segoe UI", 12, "bold"), bg=COLORS['danger'], 
                             fg='white', relief="flat", bd=0, padx=20, pady=10)
        cancel_btn.pack(side=tk.LEFT, padx=5)
        
        # Alle zurücksetzen-Button
        reset_btn = tk.Button(button_frame, text="🔄 Zurücksetzen", 
                             command=lambda: self.reset_damage_checkboxes(),
                             font=("Segoe UI", 12, "bold"), bg=COLORS['warning'], 
                             fg='white', relief="flat", bd=0, padx=20, pady=10)
        reset_btn.pack(side=tk.RIGHT, padx=(5, 10))
    
    def reset_damage_checkboxes(self):
        """Setzt alle Schadenskategorie-Checkboxen zurück"""
        for var in self.damage_checkboxes.values():
            var.set(False)
    
    def save_damage_categories(self, filename, window):
        """Speichert die ausgewählten Schadenskategorien"""
        try:
            path = os.path.join(self.source_dir, filename)
            exif_data = get_exif_usercomment(path)
            if not exif_data:
                exif_data = {}
            
            # Schadenskategorien aktualisieren
            for category, var in self.damage_checkboxes.items():
                exif_data[category] = var.get()
            
            # Speichern
            save_exif_usercomment(path, exif_data)
            
            # Fenster schließen und Galerie aktualisieren
            window.destroy()
            self.load_gallery_thumbnails()
            
            # Erfolgsmeldung
            messagebox.showinfo("Erfolg", f"Schadenskategorien für {filename} gespeichert!")
            
        except Exception as e:
            messagebox.showerror("Fehler", f"Fehler beim Speichern: {str(e)}")
    
    def load_gallery_thumbnails(self):
        """Lädt die Thumbnails für die Galerie"""
        # Alte Thumbnails löschen
        for widget in self.gallery_scrollable_frame.winfo_children():
            widget.destroy()
        
        # Thumbnail-Größe festlegen (Standard: 244px = 188 * 1.30)
        if not hasattr(self, 'thumbnail_size'):
            self.thumbnail_size = 244
        
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
        
        # Paginierung: Anzahl Bilder pro Seite
        total_images = len(filtered_files)
        if not hasattr(self, 'gallery_images_per_page'):
            self.gallery_images_per_page = 9  # Standard: 3x3 Grid
        
        if not hasattr(self, 'gallery_current_page'):
            self.gallery_current_page = 0
        
        # Bilder für aktuelle Seite auswählen
        images_per_page = self.gallery_images_per_page
        start_idx = self.gallery_current_page * images_per_page
        end_idx = min(start_idx + images_per_page, total_images)
        page_files = filtered_files[start_idx:end_idx]
        
        
        # Anzahl Seiten berechnen
        total_pages = (total_images + images_per_page - 1) // images_per_page
        
        # Grid-Layout berechnen basierend auf gewählter Bildanzahl
        if self.gallery_images_per_page == 1:
            cols = 1
        elif self.gallery_images_per_page == 4:
            cols = 2  # 2x2
        elif self.gallery_images_per_page == 9:
            cols = 3  # 3x3
        elif self.gallery_images_per_page == 12:
            cols = 4  # 4x3
        else:
            # Fallback: automatisch basierend auf Gesamtanzahl
            if total_images <= 2:
                cols = 2
            elif total_images <= 6:
                cols = 3
            elif total_images <= 12:
                cols = 4
            else:
                cols = 5
        
        rows = (len(page_files) + cols - 1) // cols
        
        # Thumbnails erstellen (nur für aktuelle Seite)
        for i, filename in enumerate(page_files):
            row = i // cols
            col = i % cols
            
            # Rahmenfarbe basierend auf Bildstatus ermitteln
            border_color = self.get_thumbnail_border_color(filename)
            border_width = 3  # Deutlich sichtbare Rahmendicke
            
            # Hintergrundfarbe der Karte basierend auf Status
            bg_color = self.get_thumbnail_background_color(filename)
            
            # Aktive Kachel mit hellblauem Hintergrund hervorheben
            if hasattr(self, 'current_gallery_filename') and self.current_gallery_filename == filename:
                bg_color = '#E3F2FD'  # Hellblau für aktive Kachel
                border_color = '#1976D2'  # Dunkleres Blau für Rahmen
                border_width = 4  # Dickerer Rahmen für aktive Kachel

            # Thumbnail-Frame erstellen mit farbigem Rahmen
            thumb_frame = tk.Frame(self.gallery_scrollable_frame, 
                                  bg=bg_color,
                                  relief="solid", bd=0,
                                  highlightbackground=border_color,
                                  highlightcolor=border_color,
                                  highlightthickness=border_width)
            thumb_frame.grid(row=row, column=col, padx=4, pady=4, sticky="nsew")
            
            # Versuche Thumbnail-Bild zu laden
            thumb_label = None
            try:
                path = os.path.join(self.source_dir, filename)
                
                if os.path.exists(path):
                    img = Image.open(path)
                    img.thumbnail((self.thumbnail_size, self.thumbnail_size), Image.Resampling.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    # Canvas: Bild + Overlays (OCR-Badge, Hover-Buttons, optional X)
                    cw, ch = photo.width(), photo.height()
                    canvas = tk.Canvas(thumb_frame, width=cw, height=ch,
                                       bg=bg_color, highlightthickness=0, bd=0, cursor="hand2")
                    canvas.pack(pady=(8, 0), padx=8)
                    canvas.create_image(0, 0, image=photo, anchor='nw', tags=('bg_image',))
                    canvas.image = photo

                    # OCR-Badge oben rechts (weiße Box)
                    try:
                        tag_value = self.get_ocr_tag(filename)
                    except Exception:
                        tag_value = "-"
                    badge_w, badge_h = 46, 18
                    bx2, by1 = cw - 5, 5
                    bx1, by2 = bx2 - badge_w, by1 + badge_h
                    canvas.create_rectangle(bx1, by1, bx2, by2, fill='white', outline='black', width=1, tags=('ocr_badge',))
                    canvas.create_text((bx1+bx2)//2, (by1+by2)//2, text=str(tag_value), font=("Segoe UI", 9, "bold"), fill='black', tags=('ocr_badge',))

                    # X-Overlay falls nicht verwendet
                    try:
                        is_used = self.get_use_image_status(filename)
                    except Exception:
                        is_used = True
                    if not is_used:
                        lw = max(6, int(min(cw, ch) * 0.06))
                        pad = max(8, int(min(cw, ch) * 0.08))
                        canvas.create_line(pad, pad, cw-pad, ch-pad, fill=COLORS['danger'], width=lw, tags=('not_used_x',))
                        canvas.create_line(cw-pad, pad, pad, ch-pad, fill=COLORS['danger'], width=lw, tags=('not_used_x',))

                    # Hover-Buttons unten (größer und besser sichtbar)
                    btn_y = ch - 50
                    btn_h = 35
                    btn_w = max(50, (cw - 40) // 3)
                    # Hintergrund für alle Buttons
                    canvas.create_rectangle(5, btn_y, cw-5, ch-5, fill='gray', outline='', tags=('btn_overlay',), state='hidden')
                    x1 = 10
                    canvas.create_rectangle(x1, btn_y+5, x1+btn_w, btn_y+btn_h, fill=COLORS['success'], outline='white', width=2, tags=('btn_overlay','btn_ok'), state='hidden')
                    canvas.create_text(x1+btn_w//2, btn_y+btn_h//2+5, text='✓ i.O.', font=("Segoe UI", 10, "bold"), fill='white', tags=('btn_overlay','btn_ok_text'), state='hidden')
                    x2 = x1 + btn_w + 8
                    canvas.create_rectangle(x2, btn_y+5, x2+btn_w, btn_y+btn_h, fill=COLORS['danger'], outline='white', width=2, tags=('btn_overlay','btn_not_use'), state='hidden')
                    canvas.create_text(x2+btn_w//2, btn_y+btn_h//2+5, text='✗ Nein', font=("Segoe UI", 10, "bold"), fill='white', tags=('btn_overlay','btn_not_use_text'), state='hidden')
                    x3 = x2 + btn_w + 8
                    canvas.create_rectangle(x3, btn_y+5, x3+btn_w, btn_y+btn_h, fill=COLORS['warning'], outline='white', width=2, tags=('btn_overlay','btn_damage'), state='hidden')
                    canvas.create_text(x3+btn_w//2, btn_y+btn_h//2+5, text='⚠ Schaden', font=("Segoe UI", 9, "bold"), fill='white', tags=('btn_overlay','btn_damage_text'), state='hidden')

                    def show_buttons(event, c=canvas):
                        for it in c.find_withtag('btn_overlay'):
                            c.itemconfig(it, state='normal')
                    def hide_buttons(event, c=canvas):
                        for it in c.find_withtag('btn_overlay'):
                            c.itemconfig(it, state='hidden')
                    canvas.bind('<Enter>', show_buttons)
                    canvas.bind('<Leave>', hide_buttons)
                    def on_canvas_click(event, c=canvas, f=filename):
                        x, y = event.x, event.y
                        items = c.find_overlapping(x, y, x, y)
                        for it in items:
                            tg = c.gettags(it)
                            if 'btn_ok' in tg:
                                self.quick_action_all_ok(f)
                                self.load_gallery_thumbnails()  # Aktualisiere Galerie
                                return
                            if 'btn_not_use' in tg:
                                self.quick_action_toggle_use(f)
                                self.load_gallery_thumbnails()  # Aktualisiere Galerie
                                return
                            if 'btn_damage' in tg:
                                self.show_damage_overlay_dialog(f)
                                return
                        self.show_evaluation_in_gallery(f)
                    canvas.bind('<Button-1>', on_canvas_click)
                    thumb_label = canvas
                else:
                    raise FileNotFoundError(f"Datei nicht gefunden: {path}")
                    
            except Exception as e:
                print(f"Fehler beim Laden des Thumbnails für {filename}: {e}")
                # Fallback: Platzhalter-Label
                thumb_label = tk.Label(thumb_frame, text=f"\n{filename[:20]}...", 
                                     cursor="hand2",
                                       bg=bg_color,
                                       bd=0,
                                       font=("Segoe UI", FONT_SIZES['small']),
                                       fg=COLORS['danger'])
                thumb_label.pack(pady=(8, 5), padx=8)
                
            # Info-Container zweispaltig (Schäden | Bildart)
            info_table = tk.Frame(thumb_frame, bg=bg_color)
            info_table.pack(fill=tk.X, padx=4, pady=(5, 8))

            # Linke Spalte: Schäden
            damage_frame = tk.Frame(info_table, bg=bg_color)
            damage_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            damages = self.get_damage_list_for_gallery(filename)
            if damages:
                damage_text = ", ".join(damages[:2])
                if len(damages) > 2:
                    damage_text += "..."
            else:
                damage_text = "i.O."
            tk.Label(damage_frame, text=damage_text,
                     font=("Segoe UI", FONT_SIZES['small']),
                     fg=COLORS['text_secondary'], bg=bg_color,
                     anchor='w').pack(fill=tk.X, padx=2)

            # Trennlinie
            tk.Frame(info_table, width=1, bg=COLORS['border']).pack(side=tk.LEFT, fill=tk.Y, padx=2)

            # Rechte Spalte: Bildart/Ort
            image_type_frame = tk.Frame(info_table, bg=bg_color)
            image_type_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
            image_types = self.get_image_type_list_for_gallery(filename)
            if image_types:
                type_text = ", ".join(image_types[:2])
                if len(image_types) > 2:
                    type_text += "..."
            else:
                type_text = "-"
            tk.Label(image_type_frame, text=type_text,
                     font=("Segoe UI", FONT_SIZES['small']),
                     fg=COLORS['text_secondary'], bg=bg_color,
                     anchor='e').pack(fill=tk.X, padx=2)

            # Kompakte Mängel-Zeile (nur wenn Mängel vorhanden)
            try:
                damage_summary = self.get_damage_summary_compact(filename, tag)
                damage_label = None
                if damage_summary:
                    damage_label = tk.Label(thumb_frame, text=damage_summary,
                                          font=("Segoe UI", FONT_SIZES['small']),
                                          fg=COLORS['text_secondary'],
                                          bg=bg_color,
                                          wraplength=self.thumbnail_size-16,
                                          justify=tk.LEFT, anchor='w')
                    damage_label.pack(fill=tk.X, padx=8, pady=(0, 3))
            except:
                damage_label = None

            # Aktionsbuttons entfallen (liegen jetzt als Hover-Overlay im Canvas)
            action_frame = tk.Frame(thumb_frame, bg=bg_color)
            action_frame.pack(fill=tk.X, padx=8, pady=(0, 6))
                
            # Click-Handler für gesamten Frame (Mouse-Over vereinfacht)
                
            all_widgets = [thumb_frame, thumb_label, action_frame]
            if damage_label:
                all_widgets.append(damage_label)
                
                for widget in all_widgets:
                widget.bind("<Button-1>", lambda e, f=filename: self.show_evaluation_in_gallery(f))
                # Hover: Nur Rahmen dicker machen, keine Farbwechsel (verhindert Wackeln)
                widget.bind("<Enter>", lambda e, tf=thumb_frame, bc=border_color: 
                    tf.configure(highlightthickness=5, highlightbackground=bc))
                widget.bind("<Leave>", lambda e, tf=thumb_frame, bc=border_color, bw=border_width: 
                    tf.configure(highlightthickness=bw, highlightbackground=bc))
        
        # Grid-Gewichte setzen
        for col in range(cols):
            self.gallery_scrollable_frame.grid_columnconfigure(col, weight=1)
        for row in range(rows):
            self.gallery_scrollable_frame.grid_rowconfigure(row, weight=1)
        
        # Seiten-Anzeige aktualisieren
        if hasattr(self, 'gallery_page_label'):
            current_page_display = self.gallery_current_page + 1  # 1-basiert für Anzeige
            self.gallery_page_label.config(text=f"Seite {current_page_display} von {total_pages} ({len(page_files)} von {total_images} Bildern)")
        
        # Automatisch das erste Bild für die Schadensbewertung laden (nur beim ersten Laden)
        if not hasattr(self, 'current_gallery_filename') and page_files:
            self.show_evaluation_in_gallery(page_files[0])
    
    def is_image_evaluated_from_cache(self, filename):
        """Prüft ob ein Bild bereits bewertet wurde (aus Cache)"""
        try:
            if filename in self._evaluation_cache:
                cache_entry = self._evaluation_cache[filename]
                return isinstance(cache_entry, dict) and cache_entry.get('is_evaluated', False)
            return False
        except:
            return False
    
    def get_use_image_status(self, filename):
        """Gibt True zurück wenn Bild verwendet wird (ja/yes), sonst False"""
        try:
            path = os.path.join(self.source_dir, filename)
            exif_data = get_exif_usercomment(path)
            if exif_data and "UseImage" in exif_data:
                use_value = str(exif_data["UseImage"]).lower()
                return use_value in ['ja', 'yes']
            return False  # Default: nicht verwendet
        except Exception as e:
            print(f"Fehler in get_use_image_status für {filename}: {e}")
            return False
    
    def get_thumbnail_border_color(self, filename):
        """Bestimmt die Rahmenfarbe für Galerie-Thumbnails basierend auf Bildstatus
        
        Priorität:
        1. ROT: Bild wird nicht verwendet (UseImage == 'nein')
        2. ORANGE: Bild hat Schadenskategorien (außer "Visually no defects")
        3. GRÜN: Bild ist in Ordnung (nur "Visually no defects")
        4. GRAU: Unvollständig bewertet (default)
        """
        try:
            path = os.path.join(self.source_dir, filename)
            exif_data = get_exif_usercomment(path)
            if not exif_data:
                return COLORS['border']  # Grau - keine Daten
            
            # PRIORITÄT 1: Nicht verwendet = ROT
            use_image = exif_data.get('UseImage', '').lower()
            if use_image == 'nein' or use_image == 'no':
                return COLORS['danger']  # Rot
            
            # PRIORITÄT 2: Schaden vorhanden = ORANGE
            damage_categories = self.config_manager.get_language_specific_list('damage_categories')
            has_damage = False
            visually_ok_key = "Visuell keine Defekte"  # Deutsche Version
            for cat in damage_categories:
                if cat != visually_ok_key and cat in exif_data and exif_data[cat]:
                    has_damage = True
                    break
            
            if has_damage:
                return COLORS['warning']  # Orange
            
            # PRIORITÄT 3: In Ordnung (nur "Visually no defects") = GRÜN
            visually_ok_key = "Visuell keine Defekte"  # Deutsche Version
            if exif_data.get(visually_ok_key):
                # Sicherstellen, dass keine anderen Schäden aktiv sind
                for cat in damage_categories:
                    if cat != visually_ok_key and cat in exif_data and exif_data[cat]:
                        return COLORS['border']
                return COLORS['success']  # Grün
            
            return COLORS['border']  # Grau - default
        except Exception as e:
            print(f"Fehler in get_thumbnail_border_color für {filename}: {e}")
            return COLORS['border']

    def get_thumbnail_background_color(self, filename):
        """Bestimmt Hintergrundfarbe der Karte: Einheitlich weiß"""
        return 'white'
    
    def get_damage_summary(self, filename):
        """Gibt eine Zusammenfassung der ausgewählten Schadenskategorien zurück"""
        try:
            path = os.path.join(self.source_dir, filename)
            exif_data = get_exif_usercomment(path)
            if not exif_data:
                return ""
            
            # Lade alle verfügbaren Kategorien
            damage_categories = self.config_manager.get_language_specific_list('damage_categories')
            
            selected_categories = []
            
            # Prüfe welche Kategorien ausgewählt sind - FIX: Korrekte EXIF-Key-Prüfung
            for category in damage_categories:
                if category in exif_data and exif_data[category]:  # Key existiert UND ist truthy
                    selected_categories.append(category)
            
            # Maximal 2 Kategorien anzeigen, dann "..." 
            if len(selected_categories) == 0:
                return ""
            elif len(selected_categories) <= 2:
                return ", ".join(selected_categories)
            else:
                return ", ".join(selected_categories[:2]) + "..."
        except Exception as e:
            print(f"Fehler in get_damage_summary für {filename}: {e}")
            return ""

    def get_damage_summary_compact(self, filename, ocr_tag):
        """Gibt kompakte Mängel-Liste zurück: 'OCR: Mangel1, Mangel2' (ohne 'Visually no defects')"""
        try:
            path = os.path.join(self.source_dir, filename)
            exif_data = get_exif_usercomment(path)
            if not exif_data:
                return ""
            damage_categories = self.config_manager.get_language_specific_list('damage_categories')
            damages = []
            for cat in damage_categories:
                if cat == "Visually no defects":
                    continue
                if cat in exif_data and exif_data[cat]:
                    damages.append(cat)
            if not damages:
                return ""
            return f"{ocr_tag}: {', '.join(damages)}"
        except Exception:
            return ""
    
    def show_evaluation_in_gallery(self, filename):
        """Zeigt die Bewertung des gewählten Bildes in den neuen Panels der Galerie"""
        try:
            print(f"DEBUG: show_evaluation_in_gallery aufgerufen für {filename}")
            # Index des gewählten Bildes setzen
            if filename in self.files:
                self.index = self.files.index(filename)
                # Aktives Bild merken
                self.current_gallery_filename = filename
                # Galerie neu laden um aktive Kachel hervorzuheben
                self.load_gallery_thumbnails()
                # Panels aktualisieren
                self.update_gallery_damage_panel(filename)
                self.update_gallery_large_image_panel(filename)
                print(f"DEBUG: Beide Panels aktualisiert für {filename}")
            else:
                print(f"DEBUG: Dateiname {filename} nicht in self.files gefunden")
        except Exception as e:
            print(f"Fehler beim Anzeigen der Bewertung: {e}")
            import traceback
            traceback.print_exc()
    
    def update_gallery_damage_panel(self, filename):
        """Aktualisiert das Schadensbewertungs-Panel (links)"""
        try:
            # Alle alten Inhalte löschen
            for widget in self.gallery_damage_panel.winfo_children():
                widget.destroy()
            
            # Direktes Frame ohne Scrollbar - kompakter
            eval_frame = ttk.Frame(self.gallery_damage_panel)
            eval_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            # Dateiname
            tk.Label(eval_frame, text=filename, 
                    font=("Segoe UI", 11, "bold"), 
                    bg='white', fg='black').pack(pady=(5, 2))
            
            # OCR-Tag
            try:
                ocr_tag = self.get_ocr_tag(filename)
                tk.Label(eval_frame, text=f"OCR: {ocr_tag}", 
                        font=("Segoe UI", 9), 
                        bg='white', fg='gray').pack(pady=(0, 8))
            except:
                pass
            
            # Bild verwenden
            use_frame = tk.Frame(eval_frame, bg='white')
            use_frame.pack(fill=tk.X, padx=5, pady=(0, 8))
            tk.Label(use_frame, text="Bild verwenden:", 
                    font=("Segoe UI", 9, "bold"), 
                    bg='white', fg='black').pack(anchor=tk.W)
            
            use_var = tk.StringVar()
            try:
                path = os.path.join(self.source_dir, filename)
                exif_data = get_exif_usercomment(path)
                if exif_data and "UseImage" in exif_data:
                    use_var.set(exif_data["UseImage"])
                else:
                    use_var.set("ja")
            except:
                use_var.set("ja")
            
            tk.Radiobutton(use_frame, text="ja", variable=use_var, value="ja",
                          command=lambda: self.save_use_image_status(filename, "ja"),
                          font=("Segoe UI", 10), bg='white', 
                          fg='black', selectcolor='white').pack(anchor=tk.W, padx=15, pady=1)
            tk.Radiobutton(use_frame, text="nein", variable=use_var, value="nein",
                          command=lambda: self.save_use_image_status(filename, "nein"),
                          font=("Segoe UI", 10), bg='white', 
                          fg='black', selectcolor='white').pack(anchor=tk.W, padx=15, pady=1)
            
            # Schadenskategorien
            damage_frame = tk.Frame(eval_frame, bg='white')
            damage_frame.pack(fill=tk.X, padx=5, pady=(0, 8))
            tk.Label(damage_frame, text="Schadenskategorien:", 
                    font=("Segoe UI", 9, "bold"), 
                    bg='white', fg='black').pack(anchor=tk.W)
            
            damage_categories = self.config_manager.get_language_specific_list('damage_categories')
            for category in damage_categories:
                var = tk.BooleanVar()
                try:
                    path = os.path.join(self.source_dir, filename)
                    exif_data = get_exif_usercomment(path)
                    if exif_data and category in exif_data and exif_data[category]:
                        var.set(True)
                except:
                    pass
                
                cb = tk.Checkbutton(damage_frame, text=category, variable=var,
                                   command=lambda c=category, v=var: self.save_damage_category(filename, c, v.get()),
                                   font=("Segoe UI", 10), bg='white',
                                   fg='black', selectcolor='white',
                                   activebackground='white', activeforeground='black')
                cb.pack(anchor=tk.W, padx=15, pady=2)
            
        except Exception as e:
            print(f"Fehler beim Aktualisieren des Schadensbewertungs-Panels: {e}")
    
    def update_gallery_large_image_panel(self, filename):
        """Aktualisiert das große Bild-Panel (rechts)"""
        try:
            # Alte Inhalte löschen
            for widget in self.gallery_large_image_panel.winfo_children():
                widget.destroy()
            
            # Scrollable Frame für das rechte Panel
            right_canvas = tk.Canvas(self.gallery_large_image_panel, bg='white', highlightthickness=0, bd=0)
            right_scrollbar = ttk.Scrollbar(self.gallery_large_image_panel, orient=tk.VERTICAL, command=right_canvas.yview)
            right_frame = ttk.Frame(right_canvas)
            
            right_frame.bind(
                "<Configure>",
                lambda e: right_canvas.configure(scrollregion=right_canvas.bbox("all"))
            )
            
            right_canvas.create_window((0, 0), window=right_frame, anchor="nw")
            right_canvas.configure(yscrollcommand=right_scrollbar.set)
            
            right_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            right_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            # Großes Bild anzeigen
            try:
                path = os.path.join(self.source_dir, filename)
                img = Image.open(path)
                # Maximale Größe für das Panel
                max_size = 300
                img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                
                img_label = tk.Label(right_frame, image=photo, bg='white')
                img_label.image = photo  # Referenz behalten
                img_label.pack(pady=10)
                
                # Dateiname unter dem Bild
                tk.Label(right_frame, text=filename, 
                        font=("Segoe UI", 12, "bold"), 
                        bg='white', fg='black').pack(pady=(5, 10))
                
                # OCR-Tag
                try:
                    ocr_tag = self.get_ocr_tag(filename)
                    tk.Label(right_frame, text=f"OCR: {ocr_tag}", 
                        font=("Segoe UI", 10), 
                            bg='white', fg='gray').pack(pady=(0, 15))
                except:
                    pass
                
                # Lade alle EXIF-Daten wie in der Hauptansicht
                exif_data = get_exif_usercomment(path)
                
                # Bild verwenden (vergrößerte Auswahlfelder)
                use_frame = tk.Frame(right_frame, bg='white')
                use_frame.pack(fill=tk.X, padx=10, pady=(0, 15))
                tk.Label(use_frame, text="Bild verwenden:", 
                        font=("Segoe UI", 12, "bold"), 
                        bg='white', fg='black').pack(anchor=tk.W, pady=(0, 5))
                
                use_var = tk.StringVar()
                if exif_data:
                    # Prüfe verschiedene mögliche Keys für "Bild verwenden"
                    use_value = None
                    if "UseImage" in exif_data:
                        use_value = exif_data["UseImage"]
                    elif "use_image" in exif_data:
                        use_value = exif_data["use_image"]
                    elif "useImage" in exif_data:
                        use_value = exif_data["useImage"]
                    
                    if use_value:
                        use_var.set(use_value)
                        print(f"DEBUG: UseImage für {filename}: {use_value}")
                    else:
                        # Fallback: Standard auf "ja" setzen
                        use_var.set("ja")
                        print(f"DEBUG: Kein UseImage gefunden für {filename}, setze auf 'ja'")
                else:
                    # Keine EXIF-Daten: Standard auf "ja" setzen
                    use_var.set("ja")
                    print(f"DEBUG: Keine EXIF-Daten für {filename}, setze UseImage auf 'ja'")
                
                # Vergrößerte Radio-Buttons
                tk.Radiobutton(use_frame, text="ja", variable=use_var, value="ja",
                              command=lambda: self.save_use_image_status(filename, "ja"),
                              font=("Segoe UI", 12), bg='white', 
                              fg='black', selectcolor='white').pack(anchor=tk.W, padx=20, pady=2)
                tk.Radiobutton(use_frame, text="nein", variable=use_var, value="nein",
                              command=lambda: self.save_use_image_status(filename, "nein"),
                              font=("Segoe UI", 12), bg='white', 
                              fg='black', selectcolor='white').pack(anchor=tk.W, padx=20, pady=2)
                
                # Schadenskategorien (wie in Hauptansicht)
                damage_frame = tk.Frame(right_frame, bg='white')
                damage_frame.pack(fill=tk.X, padx=10, pady=(0, 15))
                tk.Label(damage_frame, text="Schadenskategorien:", 
                        font=("Segoe UI", 12, "bold"), 
                        bg='white', fg='black').pack(anchor=tk.W, pady=(0, 5))
                
                damage_categories = self.config_manager.get_language_specific_list('damage_categories')
                for category in damage_categories:
                    var = tk.BooleanVar()
                    if exif_data:
                        # Prüfe sowohl Liste als auch einzelne Flags (wie in Hauptansicht)
                        damage_list = exif_data.get("damage_categories", [])
                        if isinstance(damage_list, dict):
                            current_lang = getattr(self.config_manager, 'current_language', 'de')
                            damage_list = damage_list.get(current_lang, damage_list.get('de', damage_list.get('en', [])))
                        in_list = category in damage_list
                        flag = bool(exif_data.get(category, False))
                        var.set(in_list or flag)
                    
                    cb = tk.Checkbutton(damage_frame, text=category, variable=var,
                                       command=lambda c=category, v=var: self.save_damage_category(filename, c, v.get()),
                                       font=("Segoe UI", 10), bg='white',
                                       fg='black', selectcolor='white',
                                       activebackground='white', activeforeground='black')
                    cb.pack(anchor=tk.W, padx=20, pady=2)
                
                # Bildart-Kategorien (wie in Hauptansicht)
                image_type_frame = tk.Frame(right_frame, bg='white')
                image_type_frame.pack(fill=tk.X, padx=10, pady=(0, 15))
                tk.Label(image_type_frame, text="Bildart-Kategorien:", 
                        font=("Segoe UI", 12, "bold"), 
                        bg='white', fg='black').pack(anchor=tk.W, pady=(0, 5))
                
                image_types = self.config_manager.get_language_specific_list('image_types')
                for img_type in image_types:
                    var = tk.BooleanVar()
                    if exif_data:
                        # Prüfe sowohl Liste als auch einzelne Flags (wie in Hauptansicht)
                        image_list = exif_data.get("image_types", [])
                        if isinstance(image_list, dict):
                            current_lang = getattr(self.config_manager, 'current_language', 'de')
                            image_list = image_list.get(current_lang, image_list.get('de', image_list.get('en', [])))
                        in_list = img_type in image_list
                        flag = bool(exif_data.get(img_type, False))
                        var.set(in_list or flag)
                    
                    cb = tk.Checkbutton(image_type_frame, text=img_type, variable=var,
                                       command=lambda c=img_type, v=var: self.save_image_type_category(filename, c, v.get()),
                                       font=("Segoe UI", 10), bg='white',
                                       fg='black', selectcolor='white',
                                       activebackground='white', activeforeground='black')
                    cb.pack(anchor=tk.W, padx=20, pady=2)
                
                # Schadensbewertung (wie in Hauptansicht)
                quality_frame = tk.Frame(right_frame, bg='white')
                quality_frame.pack(fill=tk.X, padx=10, pady=(0, 15))
                tk.Label(quality_frame, text="Schadensbewertung:", 
                        font=("Segoe UI", 12, "bold"), 
                        bg='white', fg='black').pack(anchor=tk.W, pady=(0, 5))
                
                quality_var = tk.StringVar()
                if exif_data and "image_quality" in exif_data:
                    quality_var.set(exif_data["image_quality"])
                else:
                    quality_var.set("Unknown")
                
                quality_options = self.config_manager.get_language_specific_list('image_quality_options')
                for option in quality_options:
                    tk.Radiobutton(quality_frame, text=option, variable=quality_var, value=option,
                                  command=lambda o=option: self.save_image_quality(filename, o),
                                  font=("Segoe UI", 10), bg='white', 
                                  fg='black', selectcolor='white').pack(anchor=tk.W, padx=20, pady=2)
                
            except Exception as e:
                tk.Label(self.gallery_large_image_panel, text=f" Bild nicht verfügbar\n{str(e)}", 
                        bg=COLORS['bg_light'], fg=COLORS['danger']).pack(pady=50)
                
        except Exception as e:
            print(f"Fehler beim Aktualisieren des großen Bild-Panels: {e}")
    
    def save_use_image_status(self, filename, status):
        """Speichert den UseImage-Status"""
        try:
            path = os.path.join(self.source_dir, filename)
            exif_data = get_exif_usercomment(path)
            if not exif_data:
                exif_data = {}
            exif_data["UseImage"] = status
            save_exif_usercomment(path, exif_data)
            self.load_gallery_thumbnails()  # Aktualisiere Galerie
        except Exception as e:
            print(f"Fehler beim Speichern des UseImage-Status: {e}")
    
    def save_damage_category(self, filename, category, value):
        """Speichert eine Schadenskategorie"""
        try:
            path = os.path.join(self.source_dir, filename)
            exif_data = get_exif_usercomment(path)
            if not exif_data:
                exif_data = {}
            exif_data[category] = value
            save_exif_usercomment(path, exif_data)
            self.load_gallery_thumbnails()  # Aktualisiere Galerie
        except Exception as e:
            print(f"Fehler beim Speichern der Schadenskategorie: {e}")
    
    def save_image_type_category(self, filename, category, value):
        """Speichert eine Bildart-Kategorie"""
        try:
            path = os.path.join(self.source_dir, filename)
            exif_data = get_exif_usercomment(path)
            if not exif_data:
                exif_data = {}
            exif_data[category] = value
            save_exif_usercomment(path, exif_data)
            self.load_gallery_thumbnails()  # Aktualisiere Galerie
        except Exception as e:
            print(f"Fehler beim Speichern der Bildart-Kategorie: {e}")
    
    def save_image_quality(self, filename, quality):
        """Speichert die Schadensbewertung"""
        try:
            path = os.path.join(self.source_dir, filename)
            exif_data = get_exif_usercomment(path)
            if not exif_data:
                exif_data = {}
            exif_data["image_quality"] = quality
            save_exif_usercomment(path, exif_data)
            self.load_gallery_thumbnails()  # Aktualisiere Galerie
        except Exception as e:
            print(f"Fehler beim Speichern der Schadensbewertung: {e}")
    
    def create_gallery_evaluation_panel(self, parent, filename):
        """Erstellt das Bewertungs-Panel im rechten Bereich der Galerie"""
        try:
            path = os.path.join(self.source_dir, filename)
            
            # Scrollable Frame für das Panel
            eval_canvas = tk.Canvas(parent, bg=COLORS['bg_light'], highlightthickness=0, bd=0)
            eval_scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=eval_canvas.yview)
            eval_frame = ttk.Frame(eval_canvas)
            
            eval_frame.bind(
                "<Configure>",
                lambda e: eval_canvas.configure(scrollregion=eval_canvas.bbox("all"))
            )
            
            eval_canvas.create_window((0, 0), window=eval_frame, anchor="nw")
            eval_canvas.configure(yscrollcommand=eval_scrollbar.set)
            
            eval_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            eval_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            
            # Thumbnail des Bildes (XL-Größe im rechten Panel)
            try:
                img = Image.open(path)
                # XL Breite nutzen (z. B. 407)
                xl_size = max(getattr(self, 'thumbnail_size', 407), 407)
                img.thumbnail((xl_size, xl_size), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                thumb_label = tk.Label(eval_frame, image=photo, bg=COLORS['bg_light'])
                thumb_label.image = photo  # Referenz behalten
                thumb_label.pack(pady=(10, 5))
            except:
                pass
            
            # Dateiname
            ttk.Label(eval_frame, text=filename, 
                     font=("Segoe UI", FONT_SIZES['small'], "bold"),
                     foreground=COLORS['text_primary']).pack(pady=(0, 5))
            
            # OCR-Tag
            exif_data = get_exif_usercomment(path)
            tag = exif_data.get("TAGOCR", "-") if exif_data else "-"
            ttk.Label(eval_frame, text=f"OCR: {tag}", 
                     font=("Segoe UI", FONT_SIZES['body']),
                     foreground=COLORS['text_secondary']).pack(pady=(0, 15))
            
            # Trennlinie
            ttk.Separator(eval_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=10, pady=10)
            
            # Lade aktuelle Bewertung
            self.load_current_evaluation()
            
            # Bild verwenden
            use_frame = ttk.LabelFrame(eval_frame, text="Bild verwenden", padding=10)
            use_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
            
            # Temporäre Variable für diese Galerie-Ansicht
            self.gallery_use_image_var = tk.StringVar(value=self.use_image_var.get())
            for option in self.config_manager.get_language_specific_list('use_image_options'):
                tk.Radiobutton(use_frame, text=option, variable=self.gallery_use_image_var, 
                              value=option, 
                              command=lambda: self.save_gallery_evaluation(filename),
                              font=("Segoe UI", FONT_SIZES['body'])).pack(anchor=tk.W, pady=2)
            
            # Schadenskategorien
            damage_frame = ttk.LabelFrame(eval_frame, text="Schadenskategorien", padding=10)
            damage_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
            
            self.gallery_damage_vars = {}
            for category in self.config_manager.get_language_specific_list('damage_categories'):
                var = tk.BooleanVar(value=self.damage_vars.get(category, tk.BooleanVar()).get())
                self.gallery_damage_vars[category] = var
                tk.Checkbutton(damage_frame, text=category, variable=var,
                              command=lambda: self.save_gallery_evaluation(filename),
                              font=("Segoe UI", FONT_SIZES['body'])).pack(anchor=tk.W, pady=2)
            
            # Bildart-Kategorien
            image_type_frame = ttk.LabelFrame(eval_frame, text="Bildart-Kategorien", padding=10)
            image_type_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
            
            self.gallery_image_type_vars = {}
            for img_type in self.config_manager.get_language_specific_list('image_types'):
                var = tk.BooleanVar(value=self.image_type_vars.get(img_type, tk.BooleanVar()).get())
                self.gallery_image_type_vars[img_type] = var
                tk.Checkbutton(image_type_frame, text=img_type, variable=var,
                              command=lambda: self.save_gallery_evaluation(filename),
                              font=("Segoe UI", FONT_SIZES['body'])).pack(anchor=tk.W, pady=2)
            
            # Schadensbewertung
            evaluation_frame = ttk.LabelFrame(eval_frame, text="Schadensbewertung", padding=10)
            evaluation_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
            
            self.gallery_evaluation_vars = {}
            for eval_option in self.config_manager.get_language_specific_list('evaluation_options'):
                var = tk.BooleanVar(value=self.evaluation_vars.get(eval_option, tk.BooleanVar()).get())
                self.gallery_evaluation_vars[eval_option] = var
                tk.Checkbutton(evaluation_frame, text=eval_option, variable=var,
                              command=lambda: self.save_gallery_evaluation(filename),
                              font=("Segoe UI", FONT_SIZES['body'])).pack(anchor=tk.W, pady=2)
            
        except Exception as e:
            print(f"Fehler beim Erstellen des Bewertungs-Panels: {e}")
            import traceback
            traceback.print_exc()

    def update_gallery_evaluation_panel(self, filename):
        """Aktualisiert Inhalte des Bewertungs-Panels ohne kompletten Neuaufbau der Galerie"""
        # Panel komplett neu aufbauen ist am stabilsten hier, aber ausgelagert in eigene Methode
        for widget in self.gallery_evaluation_container.winfo_children():
            widget.destroy()
        self.create_gallery_evaluation_panel(self.gallery_evaluation_container, filename)
    
    def save_gallery_evaluation(self, filename):
        """Speichert die Bewertung aus dem Galerie-Panel"""
        try:
            # Übertrage Werte von Galerie-Variablen zu Haupt-Variablen
            self.use_image_var.set(self.gallery_use_image_var.get())
            
            for category, var in self.gallery_damage_vars.items():
                if category in self.damage_vars:
                    self.damage_vars[category].set(var.get())
            
            for img_type, var in self.gallery_image_type_vars.items():
                if img_type in self.image_type_vars:
                    self.image_type_vars[img_type].set(var.get())
            
            for eval_option, var in self.gallery_evaluation_vars.items():
                if eval_option in self.evaluation_vars:
                    self.evaluation_vars[eval_option].set(var.get())
            
            # Speichere die Bewertung
            self.save_current_evaluation()
            
            # Aktualisiere Thumbnails um Status-Icon zu refreshen
            self.load_gallery_thumbnails()

            # Panel aktualisieren, damit XL-Vorschau und Radiobuttons konsistent sind
            if hasattr(self, 'current_gallery_filename') and self.current_gallery_filename == filename:
                self.update_gallery_evaluation_panel(filename)
            
        except Exception as e:
            print(f"Fehler beim Speichern der Galerie-Bewertung: {e}")

    def quick_action_all_ok(self, filename):
        """Setzt 'Visually no defects' auf True, alle anderen Schäden False und UseImage='ja'"""
        try:
            path = os.path.join(self.source_dir, filename)
            exif_data = get_exif_usercomment(path) or {}
            # UseImage
            exif_data['UseImage'] = 'ja'
            # Schäden setzen
            damage_categories = self.config_manager.get_language_specific_list('damage_categories')
            selected = []
            for cat in damage_categories:
                if cat == 'Visually no defects':
                    exif_data[cat] = True
                    selected.append(cat)
                else:
                    exif_data[cat] = False
            exif_data['damage_categories'] = selected
            save_exif_usercomment(path, exif_data)
            # Refresh
            self.load_gallery_thumbnails()
            if hasattr(self, 'current_gallery_filename') and self.current_gallery_filename == filename:
                self.update_gallery_evaluation_panel(filename)
        except Exception as e:
            print(f"Fehler quick_action_all_ok: {e}")

    def quick_action_toggle_use(self, filename):
        """Toggelt UseImage ja/nein (nur Anzeige in Galerie)"""
        try:
            path = os.path.join(self.source_dir, filename)
            exif_data = get_exif_usercomment(path) or {}
            current = str(exif_data.get('UseImage', 'nein')).lower()
            exif_data['UseImage'] = 'nein' if current in ['ja', 'yes'] else 'ja'
            save_exif_usercomment(path, exif_data)
            self.load_gallery_thumbnails()
            if hasattr(self, 'current_gallery_filename') and self.current_gallery_filename == filename:
                self.update_gallery_evaluation_panel(filename)
        except Exception as e:
            print(f"Fehler quick_action_toggle_use: {e}")
    
    def open_image_from_gallery(self, filename):
        """Öffnet ein Bild aus der Galerie in der Einzelansicht"""
        # Index des gewählten Bildes finden
        if filename in self.files:
            self.index = self.files.index(filename)
            self.switch_to_single_view()


