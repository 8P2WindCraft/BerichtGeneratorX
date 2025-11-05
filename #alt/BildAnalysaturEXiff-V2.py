#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BildAnalysaturEXiff - Modulare Version
OCR-Bildanalyse mit GUI für Texterkennung und Bewertung
"""

import tkinter as tk
from tkinter import ttk, messagebox
import sys
import os

# Import der neuen Module
from config_manager import ConfigManager
from config_kurzel import KurzelManager
from config_localization import LocalizationManager
from gui_main import OCRReviewApp
from utils_global import *

class LoadingScreen:
    """Ladebildschirm für die Anwendung"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("GearGeneGPT - Ladebildschirm")
        self.root.geometry("400x300")
        self.root.resizable(False, False)
        
        # Zentriere Fenster
        self.root.update_idletasks()
        x = (self.root.winfo_screenwidth() // 2) - (400 // 2)
        y = (self.root.winfo_screenheight() // 2) - (300 // 2)
        self.root.geometry(f"400x300+{x}+{y}")
        
        # Hauptframe
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Logo/Title
        title_label = ttk.Label(main_frame, text="GearGeneGPT", font=("TkDefaultFont", 24, "bold"))
        title_label.pack(pady=(20, 10))
        
        subtitle_label = ttk.Label(main_frame, text="OCR-Bildanalyse", font=("TkDefaultFont", 12))
        subtitle_label.pack(pady=(0, 30))
        
        # Progress-Bar
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(main_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.pack(fill='x', padx=20, pady=10)
        
        # Status-Label
        self.status_var = tk.StringVar(value="Initialisiere Anwendung...")
        status_label = ttk.Label(main_frame, textvariable=self.status_var)
        status_label.pack(pady=10)
        
        # Version-Info
        version_label = ttk.Label(main_frame, text="Version 2.0 - Modulare Architektur", font=("TkDefaultFont", 9))
        version_label.pack(side='bottom', pady=10)
        
        # Animation starten
        self.animate_loading()
    
    def animate_loading(self):
        """Animiert den Ladebildschirm"""
        import time
        
        steps = [
            ("Lade Konfiguration...", 20),
            ("Initialisiere Module...", 40),
            ("Lade GUI-Komponenten...", 60),
            ("Erstelle Hauptfenster...", 80),
            ("Fertig!", 100)
        ]
        
        for status, progress in steps:
            self.status_var.set(status)
            self.progress_var.set(progress)
            self.root.update()
            time.sleep(0.5)
    
    def update_status(self, status):
        """Aktualisiert Status-Text"""
        self.status_var.set(status)
        self.root.update()
    
    def close(self):
        """Schließt Ladebildschirm"""
        self.root.destroy()

def initialize_application():
    """Initialisiert die Anwendung mit modularen Komponenten"""
    try:
        # Erstelle Ladebildschirm
        loading_screen = LoadingScreen()
        
        # Initialisiere Config-Manager
        loading_screen.update_status("Initialisiere Konfiguration...")
        config_manager = ConfigManager()
        
        # Initialisiere Kürzel-Manager
        loading_screen.update_status("Initialisiere Kürzel-Verwaltung...")
        kurzel_manager = KurzelManager(config_manager)
        
        # Initialisiere Lokalisierungs-Manager
        loading_screen.update_status("Initialisiere Lokalisierung...")
        localization_manager = LocalizationManager(config_manager)
        
        # Schließe Ladebildschirm
        loading_screen.close()
        
        # Erstelle Hauptanwendung
        loading_screen.update_status("Erstelle Hauptfenster...")
        app = OCRReviewApp()
        
        # Starte Hauptschleife
        app.mainloop()
        
    except Exception as e:
        write_detailed_log("error", "Fehler bei der Anwendungsinitialisierung", str(e))
        messagebox.showerror("Fehler", f"Fehler beim Starten der Anwendung: {e}")
        sys.exit(1)

def main():
    """Hauptfunktion"""
    try:
        # Prüfe Python-Version
        if sys.version_info < (3, 7):
            messagebox.showerror("Fehler", "Python 3.7 oder höher erforderlich")
            sys.exit(1)
        
        # Prüfe erforderliche Module
        required_modules = ['tkinter', 'PIL', 'cv2', 'easyocr', 'pandas']
        missing_modules = []
        
        for module in required_modules:
            try:
                __import__(module)
            except ImportError:
                missing_modules.append(module)
        
        if missing_modules:
            messagebox.showerror("Fehler", f"Fehlende Module: {', '.join(missing_modules)}")
            sys.exit(1)
        
        # Starte Anwendung
        initialize_application()
        
    except KeyboardInterrupt:
        print("\nAnwendung durch Benutzer abgebrochen")
        sys.exit(0)
    except Exception as e:
        write_detailed_log("error", "Unbehandelter Fehler in main()", str(e))
        messagebox.showerror("Kritischer Fehler", f"Unbehandelter Fehler: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 