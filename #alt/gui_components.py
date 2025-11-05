#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wiederverwendbare GUI-Komponenten
LoadingScreen und AnalysisWindow
"""

import os
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

from constants import THUMBNAIL_LARGE_WIDTH
from utils_helpers import resource_path


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
            img.thumbnail((THUMBNAIL_LARGE_WIDTH, THUMBNAIL_LARGE_WIDTH), Image.Resampling.LANCZOS)
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
        """Animiert die Lade-Punkte"""
        dots_text = "." * (self.dots + 1)
        self.loading_label.config(text=f"Lade Anwendung{dots_text}")
        self.dots = (self.dots + 1) % 4
        self.animation_job = self.root.after(500, self.animate_loading)

    def update_status(self, status):
        """Aktualisiert den Status-Text"""
        self.status_label.config(text=status)
        self.root.update()

    def close(self):
        """Schließt den Ladebildschirm"""
        self.progress.stop()
        if self.animation_job:
            self.root.after_cancel(self.animation_job)
            self.animation_job = None
        self.root.destroy()


class AnalysisWindow:
    """
    Dediziertes Fenster für OCR-Analyse mit Live-Vorschau und Ergebnis-Bearbeitung
    """
    
    def __init__(self, parent, source_dir, files, valid_kurzel, json_config):
        """
        Initialisiert das Analyse-Fenster
        
        Args:
            parent: Eltern-Widget
            source_dir: Verzeichnis mit Bildern
            files: Liste der zu analysierenden Dateien
            valid_kurzel: Liste gültiger Kürzel
            json_config: Konfigurationsdaten
        """
        self.parent = parent
        self.source_dir = source_dir
        self.files = files
        self.valid_kurzel = valid_kurzel
        self.json_config = json_config
        self.results = []
        self.current_index = 0
        
        self.window = tk.Toplevel(parent)
        self.window.title("OCR-Analyse")
        self.window.geometry("1200x800")
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Haupt-Layout
        self.create_widgets()
        
        # Erstes Bild laden
        if self.files:
            self.load_current_image()
    
    def create_widgets(self):
        """Erstellt die Benutzeroberfläche"""
        # Haupt-Frame
        main_frame = ttk.Frame(self.window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Top-Frame für Steuerung
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Navigation
        nav_frame = ttk.Frame(top_frame)
        nav_frame.pack(side=tk.LEFT)
        
        self.prev_btn = tk.Button(nav_frame, text="◀ Vorheriges", command=self.prev_image)
        self.prev_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.next_btn = tk.Button(nav_frame, text="Nächstes ▶", command=self.next_image)
        self.next_btn.pack(side=tk.LEFT)
        
        # Status
        self.status_var = tk.StringVar(value=f"Bild 1 von {len(self.files)}")
        status_label = ttk.Label(top_frame, textvariable=self.status_var)
        status_label.pack(side=tk.RIGHT)
        
        # Zwei-Spalten-Layout
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Linke Spalte: Bild + OCR-Ergebnis
        left_column = ttk.Frame(content_frame)
        left_column.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        # Canvas für Bild
        self.canvas = tk.Canvas(left_column, bg='white', relief=tk.SUNKEN, bd=1)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<Configure>", lambda e: self.redraw_overlays())
        
        # OCR-Ergebnis-Frame (unter dem Bild)
        result_frame = ttk.LabelFrame(left_column, text="OCR-Ergebnis")
        result_frame.pack(fill=tk.X, pady=(10, 0))
        
        # OCR-Tag
        ttk.Label(result_frame, text="Erkanntes Kürzel:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.ocr_var = tk.StringVar()
        self.ocr_entry = ttk.Entry(result_frame, textvariable=self.ocr_var, width=20)
        self.ocr_entry.grid(row=0, column=1, padx=5, pady=5)
        
        # Buttons
        btn_frame = ttk.Frame(result_frame)
        btn_frame.grid(row=0, column=2, padx=10, pady=5)
        
        self.analyze_btn = tk.Button(btn_frame, text="OCR ausführen", command=self.run_ocr, 
                                   bg='#4CAF50', fg='white', font=('Arial', 10, 'bold'))
        self.analyze_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.save_btn = tk.Button(btn_frame, text="Speichern", command=self.save_result,
                                bg='#2196F3', fg='white', font=('Arial', 10, 'bold'))
        self.save_btn.pack(side=tk.LEFT)

        # Rechte Spalte: Alle Parameter & Aktionen
        right_column = ttk.LabelFrame(content_frame, text="Parameter & Aktionen")
        right_column.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        right_column.configure(width=400)  # Feste Breite für rechte Spalte
        right_column.grid_propagate(False)

        # Parameter (DetectParams) - Optimiert für weiße Kästen
        from constants import DetectParams
        self.dp = DetectParams()
        # Überschreibe mit optimierten Werten für weiße Kästen
        self.dp.min_area_frac = 0.001
        self.dp.max_area_frac = 0.5
        self.dp.min_aspect = 0.8
        self.dp.max_aspect = 4.0
        # Aus Konfiguration laden (falls vorhanden) - aber nur Suchbereich und Padding
        self.load_detect_params_from_config()
        self.pad_vars = {}
        # Parallelität (Standard: Hälfte der Kerne)
        import os as _os
        self._cpu_count = max(1, int(_os.cpu_count() or 1))
        self.max_workers = self.load_max_workers_from_config() or max(1, self._cpu_count // 2)

        def add_param_row(parent, label, var, from_, to_, step=0.01):
            row = ttk.Frame(parent)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=label, width=18).pack(side=tk.LEFT)
            # ttk.Scale besitzt keinen 'value'-Parameter; Initialwert via .set()
            scale = ttk.Scale(row, from_=from_, to=to_, orient=tk.HORIZONTAL,
                              command=lambda v, a=label: self.on_param_change(a, float(v)))
            try:
                init_val = float(var.get()) if hasattr(var, 'get') else float(var)
            except Exception:
                init_val = 0.0
            try:
                scale.set(init_val)
            except Exception:
                pass
            scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
            return scale

        # Parameter-Steuerung (vereinfacht)
        ttk.Label(right_column, text="Suchbereich (Fracs)", font=('Arial', 10, 'bold')).pack(anchor=tk.W, pady=(5, 2))
        # Erweiterte Bereiche bis 0.90 für feine, kleine Suchfenster
        self.scale_top = add_param_row(right_column, "top_frac", self.dp.top_frac, 0.0, 0.90)
        self.scale_bottom = add_param_row(right_column, "bottom_frac", self.dp.bottom_frac, 0.0, 0.90)
        self.scale_left = add_param_row(right_column, "left_frac", self.dp.left_frac, 0.0, 0.90)
        self.scale_right = add_param_row(right_column, "right_frac", self.dp.right_frac, 0.0, 0.90)

        ttk.Label(right_column, text="Padding", font=('Arial', 10, 'bold')).pack(anchor=tk.W, pady=(10, 2))
        # Helper für Padding mit Zahleneingabe + Slider
        def add_padding_row(parent, name, init_val):
            row = ttk.Frame(parent)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=name, width=18).pack(side=tk.LEFT)
            var = tk.IntVar(value=int(init_val))
            spin = tk.Spinbox(row, from_=-100, to=200, width=6, textvariable=var)
            spin.pack(side=tk.RIGHT, padx=(5, 0))
            scale = ttk.Scale(row, from_=-50, to=50, orient=tk.HORIZONTAL,
                              command=lambda v, n=name: self.on_param_change(n, float(v)))
            try:
                scale.set(float(init_val))
            except Exception:
                pass
            scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

            # Events für Spinbox (sofort anwenden)
            def _commit_spin(event=None, n=name, v=var):
                try:
                    self.on_param_change(n, float(v.get()))
                except Exception:
                    pass
            spin.bind("<Return>", _commit_spin)
            spin.bind("<FocusOut>", _commit_spin)

            self.pad_vars[name] = (var, scale, spin)
            return (var, scale, spin)

        self.pad_top = add_padding_row(right_column, "padding_top", self.dp.padding_top)
        self.pad_bottom = add_padding_row(right_column, "padding_bottom", self.dp.padding_bottom)
        self.pad_left = add_padding_row(right_column, "padding_left", self.dp.padding_left)
        self.pad_right = add_padding_row(right_column, "padding_right", self.dp.padding_right)

        # Parallelitäts-Auswahl
        conc_frame = ttk.Frame(right_column)
        conc_frame.pack(fill=tk.X, pady=(6, 4))
        ttk.Label(conc_frame, text="Prozesse:", width=18).pack(side=tk.LEFT)
        self.max_workers_var = tk.IntVar(value=int(self.max_workers))
        self.workers_spin = tk.Spinbox(conc_frame, from_=1, to=self._cpu_count, width=6, textvariable=self.max_workers_var)
        self.workers_spin.pack(side=tk.LEFT)
        def _commit_workers(event=None):
            try:
                self.max_workers = max(1, min(self._cpu_count, int(self.max_workers_var.get())))
                self.save_max_workers_to_config()
            except Exception:
                pass
        self.workers_spin.bind("<Return>", _commit_workers)
        self.workers_spin.bind("<FocusOut>", _commit_workers)

        # Aktionen
        actions = ttk.Frame(right_column)
        actions.pack(fill=tk.X, pady=(10, 0))
        tk.Button(actions, text="Kasten finden", command=self.on_detect, bg="#1565C0", fg="white").pack(fill=tk.X)
        tk.Button(actions, text="OCR ausführen", command=self.on_ocr_single, bg="#2E7D32", fg="white").pack(fill=tk.X, pady=(5, 0))
        tk.Button(actions, text="Alle Bilder analysieren", command=self.on_analyze_all, bg="#F57C00", fg="white").pack(fill=tk.X, pady=(5, 0))

        # Fortschritt
        prog_frame = ttk.LabelFrame(right_column, text="Fortschritt")
        prog_frame.pack(fill=tk.X, pady=(8, 0))
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(prog_frame, variable=self.progress_var, maximum=max(1, len(self.files)))
        self.progress_bar.pack(fill=tk.X, padx=6, pady=(6, 4))
        
        # Fortschritt-Text und Timer
        progress_text_frame = ttk.Frame(prog_frame)
        progress_text_frame.pack(fill=tk.X, padx=6, pady=(0, 6))
        
        self.progress_label = ttk.Label(progress_text_frame, text="Bereit")
        self.progress_label.pack(side=tk.LEFT)
        
        self.timer_label = ttk.Label(progress_text_frame, text="", foreground="gray")
        self.timer_label.pack(side=tk.RIGHT)

        # Post-Processing/Ersetzungen (editierbar)
        char_frame = ttk.LabelFrame(right_column, text="Zeichen-Ersetzungen")
        char_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        columns = ("from", "to")
        self.char_tree = ttk.Treeview(char_frame, columns=columns, show='headings', height=6)
        self.char_tree.heading("from", text="Von")
        self.char_tree.heading("to", text="Nach")
        self.char_tree.column("from", width=40, anchor=tk.CENTER)
        self.char_tree.column("to", width=40, anchor=tk.CENTER)
        self.char_tree.pack(fill=tk.BOTH, expand=True)

        btns = ttk.Frame(char_frame)
        btns.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(btns, text="Hinzufügen", command=self.add_char_mapping).pack(side=tk.LEFT)
        ttk.Button(btns, text="Löschen", command=self.delete_char_mapping).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(btns, text="Standard", command=self.reset_char_mappings).pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(btns, text="Speichern", command=self.save_char_mappings).pack(side=tk.RIGHT)

        self.load_char_mappings()

        # Inline-Editing für Zeichen-Ersetzungen
        self._char_edit = None
        self.char_tree.bind('<Double-1>', self.on_char_mapping_edit)
        
        # Bind Events
        self.canvas.bind("<Button-1>", self.on_canvas_click)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
    
    def load_current_image(self):
        """Lädt das aktuelle Bild"""
        if not self.files or self.current_index >= len(self.files):
            return
        
        try:
            file_path = os.path.join(self.source_dir, self.files[self.current_index])
            
            # Bild laden
            self.current_image = Image.open(file_path)
            
            # Canvas-Größe anpassen
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()
            
            if canvas_width <= 1:
                canvas_width = 800
            if canvas_height <= 1:
                canvas_height = 600
            
            # Bild skalieren
            img_width, img_height = self.current_image.size
            scale = min(canvas_width / img_width, canvas_height / img_height, 1.0)
            new_width = int(img_width * scale)
            new_height = int(img_height * scale)
            # Skalen speichern für Koordinaten-Umrechnung (Original → Anzeige)
            self._orig_width = img_width
            self._orig_height = img_height
            self._disp_width = new_width
            self._disp_height = new_height
            self._scale_x = new_width / max(1.0, float(img_width))
            self._scale_y = new_height / max(1.0, float(img_height))
            
            self.display_image = self.current_image.resize((new_width, new_height), Image.Resampling.LANCZOS)
            self.photo = ImageTk.PhotoImage(self.display_image)
            
            # Canvas konfigurieren
            self.canvas.configure(scrollregion=(0, 0, new_width, new_height))
            
            # Bild anzeigen
            self.canvas.delete("all")
            self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)
            
            # Status aktualisieren
            self.status_var.set(f"Bild {self.current_index + 1} von {len(self.files)}: {self.files[self.current_index]}")

            # Initiale Overlays aktualisieren (Live-Vorschau des Suchbereichs)
            self.redraw_overlays()
            
        except Exception as e:
            self.canvas.delete("all")
            self.canvas.create_text(400, 300, text=f"Fehler beim Laden:\n{str(e)}", fill="red")
    
    def run_ocr(self):
        """Kompatibilität: Delegiert an on_ocr_single"""
        self.on_ocr_single()
    
    def save_result(self):
        """Speichert das OCR-Ergebnis"""
        if not hasattr(self, 'current_image') or not self.ocr_var.get():
            return
        
        try:
            from utils_exif import save_exif_usercomment
            
            file_path = os.path.join(self.source_dir, self.files[self.current_index])
            
            # EXIF-Daten laden oder erstellen
            exif_data = self.json_config.copy()
            exif_data['TAGOCR'] = self.ocr_var.get()
            
            # Speichern
            save_exif_usercomment(file_path, exif_data)
            
            print(f"OCR-Tag '{self.ocr_var.get()}' gespeichert für {self.files[self.current_index]}")
            
        except Exception as e:
            print(f"Speicher-Fehler: {e}")
    
    def prev_image(self):
        """Geht zum vorherigen Bild"""
        if self.current_index > 0:
            self.current_index -= 1
            self.load_current_image()
    
    def next_image(self):
        """Geht zum nächsten Bild"""
        if self.current_index < len(self.files) - 1:
            self.current_index += 1
            self.load_current_image()
    
    def on_canvas_click(self, event):
        """Canvas-Klick Event"""
        pass
    
    def on_canvas_drag(self, event):
        """Canvas-Drag Event"""
        pass
    
    def on_canvas_release(self, event):
        """Canvas-Release Event"""
        pass
    
    def on_close(self):
        """Schließt das Analyse-Fenster"""
        # Einstellungen speichern
        try:
            self.save_detect_params_to_config()
            self.save_max_workers_to_config()
        except Exception:
            pass
        self.window.destroy()

    # ===== Neue Analyse-Funktionen =====
    def on_param_change(self, name, value):
        try:
            if name == "top_frac":
                self.dp.top_frac = float(value)
            elif name == "bottom_frac":
                self.dp.bottom_frac = float(value)
            elif name == "left_frac":
                self.dp.left_frac = float(value)
            elif name == "right_frac":
                self.dp.right_frac = float(value)
            elif name == "min_area_frac":
                self.dp.min_area_frac = float(value)
            elif name == "max_area_frac":
                self.dp.max_area_frac = float(value)
            elif name == "min_aspect":
                self.dp.min_aspect = float(value)
            elif name == "max_aspect":
                self.dp.max_aspect = float(value)
            elif name == "padding_top":
                self.dp.padding_top = int(float(value))
                if "padding_top" in self.pad_vars:
                    self.pad_vars["padding_top"][0].set(self.dp.padding_top)
            elif name == "padding_bottom":
                self.dp.padding_bottom = int(float(value))
                if "padding_bottom" in self.pad_vars:
                    self.pad_vars["padding_bottom"][0].set(self.dp.padding_bottom)
            elif name == "padding_left":
                self.dp.padding_left = int(float(value))
                if "padding_left" in self.pad_vars:
                    self.pad_vars["padding_left"][0].set(self.dp.padding_left)
            elif name == "padding_right":
                self.dp.padding_right = int(float(value))
                if "padding_right" in self.pad_vars:
                    self.pad_vars["padding_right"][0].set(self.dp.padding_right)
            # Nach jeder Änderung speichern
            self.save_detect_params_to_config()
            self.redraw_overlays()
        except Exception:
            pass

    def redraw_overlays(self):
        if not hasattr(self, 'display_image'):
            print("redraw_overlays: Kein display_image vorhanden")
            return
        # Bild neu anzeigen inkl. Overlays
        try:
            self.canvas.delete("all")
            self.photo = ImageTk.PhotoImage(self.display_image)
            self.canvas.create_image(0, 0, anchor=tk.NW, image=self.photo)
            # Live-Suchbereich in Anzeige-Koordinaten aus DetectParams ableiten
            disp_w = getattr(self, '_disp_width', self.display_image.width)
            disp_h = getattr(self, '_disp_height', self.display_image.height)
            x0 = int(disp_w * float(self.dp.left_frac))
            y0 = int(disp_h * float(self.dp.top_frac))
            x1 = int(disp_w * (1.0 - float(self.dp.right_frac)))
            y1 = int(disp_h * (1.0 - float(self.dp.bottom_frac)))
            self.search_rect_display = (x0, y0, max(1, x1 - x0), max(1, y1 - y0))
            sx, sy, sw, sh = self.search_rect_display
            self.canvas.create_rectangle(sx, sy, sx+sw, sy+sh, outline="#1565C0", dash=(4, 2), width=2)
            print(f"redraw_overlays: Suchbereich gezeichnet: {self.search_rect_display}")

            # Gefundene Box (falls vorhanden) in Anzeige-Koordinaten
            if hasattr(self, 'detected_rect_display') and self.detected_rect_display:
                x, y, w, h = self.detected_rect_display
                self.canvas.create_rectangle(x, y, x+w, y+h, outline="#2E7D32", width=2)
                print(f"redraw_overlays: Gefundene Box gezeichnet: {self.detected_rect_display}")
            else:
                print("redraw_overlays: Keine gefundene Box zum Zeichnen")
        except Exception as e:
            import traceback
            print(f"redraw_overlays Fehler: {e}")
            traceback.print_exc()

    def on_detect(self):
        if not hasattr(self, 'current_image'):
            print("on_detect: Kein Bild geladen")
            return
        try:
            import cv2, numpy as np
            from core_ocr import find_text_box_easyocr
            img_cv = cv2.cvtColor(np.array(self.current_image), cv2.COLOR_RGB2BGR)
            print(f"on_detect: Bild geladen, Größe: {img_cv.shape}")

            # Suchrechteck aus DetectParams ableiten
            H, W = img_cv.shape[:2]
            x0 = int(W * self.dp.left_frac)
            y0 = int(H * self.dp.top_frac)
            x1 = int(W * (1.0 - self.dp.right_frac))
            y1 = int(H * (1.0 - self.dp.bottom_frac))
            self.search_rect = (x0, y0, max(1, x1 - x0), max(1, y1 - y0))
            print(f"on_detect: Suchbereich: {self.search_rect}")

            # Normalisierte valid_kurzel
            valid_norm = [str(k).upper().strip() for k in self.valid_kurzel] if self.valid_kurzel else None
            print(f"on_detect: Suche nach Kasten mit {len(valid_norm) if valid_norm else 0} gültigen Kürzeln")

            best = find_text_box_easyocr(img_cv, crop_coords=None, valid_kurzel=valid_norm, detect_params=self.dp)
            print(f"on_detect: Gefundener Kasten: {best}")
            
            self.detected_rect_orig = best
            # In Anzeige-Koordinaten umrechnen
            if best:
                bx, by, bw, bh = best
                sx = int(bx * getattr(self, '_scale_x', 1.0))
                sy = int(by * getattr(self, '_scale_y', 1.0))
                sw = int(bw * getattr(self, '_scale_x', 1.0))
                sh = int(bh * getattr(self, '_scale_y', 1.0))
                self.detected_rect_display = (sx, sy, max(1, sw), max(1, sh))
                print(f"on_detect: Anzeige-Kasten: {self.detected_rect_display}")
            else:
                self.detected_rect_display = None
                print("on_detect: Kein Kasten gefunden")
            self.redraw_overlays()
        except Exception as e:
            import traceback
            print(f"Detect-Fehler: {e}")
            traceback.print_exc()

    def on_ocr_single(self):
        if not hasattr(self, 'current_image'):
            return
        try:
            import cv2, numpy as np
            from core_ocr import run_ocr_easyocr_improved, find_text_box_easyocr
            img_cv = cv2.cvtColor(np.array(self.current_image), cv2.COLOR_RGB2BGR)

            # Sicherstellen, dass wir eine Box haben: ggf. zuerst detektieren
            box = getattr(self, 'detected_rect_orig', None)
            if box is None:
                box = find_text_box_easyocr(img_cv, detect_params=self.dp, valid_kurzel=self.valid_kurzel)
                self.detected_rect_orig = box
                # Anzeige-Box aktualisieren
                if box:
                    bx, by, bw, bh = box
                    sx = int(bx * getattr(self, '_scale_x', 1.0))
                    sy = int(by * getattr(self, '_scale_y', 1.0))
                    sw = int(bw * getattr(self, '_scale_x', 1.0))
                    sh = int(bh * getattr(self, '_scale_y', 1.0))
                    self.detected_rect_display = (sx, sy, max(1, sw), max(1, sh))
                    self.redraw_overlays()

            # Wenn keine Box gefunden wurde: OCR nur im Suchbereich, nicht auf ganzem Bild
            if box is None:
                H, W = img_cv.shape[:2]
                x0 = int(W * self.dp.left_frac)
                y0 = int(H * self.dp.top_frac)
                x1 = int(W * (1.0 - self.dp.right_frac))
                y1 = int(H * (1.0 - self.dp.bottom_frac))
                crop = img_cv[y0:y1, x0:x1]
            else:
                x, y, w, h = box
                crop = img_cv[y:y+h, x:x+w]

            # Char-Mappings aus Editor
            mappings = self.get_char_mappings_dict()
            text, _ = run_ocr_easyocr_improved(crop, enable_post_processing=True, char_mappings=mappings)
            self.ocr_var.set(text)
        except Exception as e:
            print(f"OCR-Fehler: {e}")

    def on_analyze_all(self):
        if not self.files:
            return
        try:
            import os
            from utils_exif import save_exif_usercomment
            from datetime import datetime
            from PIL import Image
            import numpy as np, cv2
            from difflib import get_close_matches
            from gui_dialogs import CorrectionQueueDialog, OCRCorrectionDialog
            from concurrent.futures import ProcessPoolExecutor, as_completed
            from core_ocr import process_single_image_for_batch

            results = []
            out_dir = os.path.join(self.source_dir, "Analyse-Reports")
            os.makedirs(out_dir, exist_ok=True)
            invalid_items = []  # (fname, crop_pil, text, path)

            # Parallel verarbeiten
            dp_dict = self._dp_to_dict()
            mappings = self.get_char_mappings_dict()
            tasks = []
            total = len(self.files)
            # Fortschritt initialisieren
            self.progress_bar.configure(maximum=max(1, total))
            self.progress_var.set(0)
            self.progress_label.config(text=f"Starte Analyse: 0 / {total}")
            self.timer_label.config(text="")
            self.window.update()
            print(f"Starte Batch-Analyse mit {total} Bildern")
            
            # Timer starten
            import time
            start_time = time.time()

            done = 0
            with ProcessPoolExecutor(max_workers=int(self.max_workers)) as ex:
                for fname in self.files:
                    path = os.path.join(self.source_dir, fname)
                    args = {
                        'path': path,
                        'dp': dp_dict,
                        'valid_kurzel': self.valid_kurzel,
                        'enable_post_processing': self.dp.enable_post_processing,
                        'char_mappings': mappings,
                    }
                    tasks.append(ex.submit(process_single_image_for_batch, args))

                for fut in as_completed(tasks):
                    res = fut.result()
                    done += 1
                    # Fortschritt aktualisieren
                    self.progress_var.set(done)
                    self.progress_label.config(text=f"{done} / {total}")
                    
                    # Timer aktualisieren
                    elapsed_time = time.time() - start_time
                    if done > 0:
                        avg_time_per_image = elapsed_time / done
                        remaining_images = total - done
                        estimated_remaining = avg_time_per_image * remaining_images
                        timer_text = f"{elapsed_time:.1f}s | +{estimated_remaining:.1f}s"
                    else:
                        timer_text = f"{elapsed_time:.1f}s"
                    self.timer_label.config(text=timer_text)
                    
                    # GUI sofort aktualisieren
                    self.window.update()
                    print(f"Fortschritt: {done}/{total} - {res.get('filename', 'Unknown')}")
                    
                    fname = res.get('filename')
                    path = res.get('path')
                    text = res.get('text')
                    box = res.get('box')
                    # Crop für Dialog erstellen
                    try:
                        img = Image.open(path)
                        if box:
                            x, y, w, h = box
                            crop_pil = img.crop((x, y, x+w, y+h))
                        else:
                            # Suchbereich aus dp_dict
                            H, W = img.size[1], img.size[0]
                            x0 = int(W * dp_dict['left_frac'])
                            y0 = int(H * dp_dict['top_frac'])
                            x1 = int(W * (1.0 - dp_dict['right_frac']))
                            y1 = int(H * (1.0 - dp_dict['bottom_frac']))
                            crop_pil = img.crop((x0, y0, x1, y1))
                    except Exception:
                        crop_pil = None

                    # EXIF schreiben
                    try:
                        exif_data = self.json_config.copy()
                        exif_data['TAGOCR'] = text
                        save_exif_usercomment(path, exif_data)
                    except Exception:
                        pass

                    # Validierung sammeln (robust normalisiert)
                    valid_set = {str(k).upper().strip() for k in self.valid_kurzel}
                    t_clean = (text or "").upper().strip()
                    
                    if t_clean and t_clean not in valid_set:
                        invalid_items.append((fname, crop_pil, text, path))
                    results.append((fname, text))

            # Analyse abgeschlossen
            total_time = time.time() - start_time
            avg_time_per_image = total_time / total if total > 0 else 0
            self.progress_label.config(text=f"Analyse abgeschlossen: {total} / {total}")
            self.timer_label.config(text=f"Gesamt: {total_time:.1f}s | Ø {avg_time_per_image:.2f}s/Bild")
            self.window.update()
            print(f"Batch-Analyse abgeschlossen: {total} Bilder in {total_time:.1f}s verarbeitet (Ø {avg_time_per_image:.2f}s/Bild)")

            # Am Ende optionaler Korrektur-Dialog mit Warteschlange
            if invalid_items:
                def _done_cb(updated_items):
                    # Nach Korrekturen könnte man Galerie/Status refreshen; hier genügt Abschluss
                    pass
                CorrectionQueueDialog(self.window, invalid_items, self.valid_kurzel, _done_cb)
        except Exception as e:
            print(f"Batch-Analyse-Fehler: {e}")

    # ===== Zeichen-Ersetzungen Editor =====
    def get_char_mappings_dict(self):
        mappings = {}
        try:
            for iid in self.char_tree.get_children():
                vals = self.char_tree.item(iid, 'values')
                if len(vals) != 2:
                    continue
                src = str(vals[0])
                dst = str(vals[1])
                if src:
                    mappings[src] = dst
        except Exception:
            pass
        return mappings

    def add_char_mapping(self):
        try:
            # Leere Zeile hinzufügen, danach per Doppelklick editieren
            self.char_tree.insert('', 'end', values=("", ""))
        except Exception:
            pass

    def delete_char_mapping(self):
        try:
            for iid in self.char_tree.selection():
                self.char_tree.delete(iid)
        except Exception:
            pass

    def reset_char_mappings(self):
        try:
            for iid in self.char_tree.get_children():
                self.char_tree.delete(iid)
            defaults = [("l","1"),("Z","2"),("z","2"),("I","1"),("O","0"),("o","0")]
            for a,b in defaults:
                self.char_tree.insert('', 'end', values=(a,b))
            self.save_char_mappings()
        except Exception:
            pass

    def load_char_mappings(self):
        try:
            cfg = self.json_config.get('ocr_settings', {}).get('char_mappings', {})
            for iid in self.char_tree.get_children():
                self.char_tree.delete(iid)
            if isinstance(cfg, dict) and cfg:
                for a,b in cfg.items():
                    self.char_tree.insert('', 'end', values=(a,b))
            else:
                self.reset_char_mappings()
        except Exception:
            self.reset_char_mappings()

    def save_char_mappings(self):
        try:
            if 'ocr_settings' not in self.json_config:
                self.json_config['ocr_settings'] = {}
            self.json_config['ocr_settings']['char_mappings'] = self.get_char_mappings_dict()
            if hasattr(self.parent, 'config_manager'):
                self.parent.config_manager.save_config()
        except Exception:
            pass

    # Inline-Editierlogik für Treeview-Zellen
    def on_char_mapping_edit(self, event):
        try:
            if self._char_edit is not None:
                return
            region = self.char_tree.identify('region', event.x, event.y)
            if region != 'cell':
                return
            row_id = self.char_tree.identify_row(event.y)
            col_id = self.char_tree.identify_column(event.x)  # '#1' oder '#2'
            if not row_id or col_id not in ('#1', '#2'):
                return
            # Bounding-Box der Zelle
            bbox = self.char_tree.bbox(row_id, col_id)
            if not bbox:
                return
            x, y, w, h = bbox
            # aktuellen Wert holen
            columns = ('from', 'to')
            col_index = 0 if col_id == '#1' else 1
            current_val = self.char_tree.set(row_id, columns[col_index])
            # Editor anlegen
            self._char_edit = tk.Entry(self.char_tree)
            self._char_edit.insert(0, current_val)
            self._char_edit.place(x=x, y=y, width=w, height=h)

            def _commit(event=None):
                try:
                    new_val = self._char_edit.get()
                    # Optional: Beschränkung – 'from' sollte 1 Zeichen sein
                    if col_index == 0 and len(new_val) > 1:
                        new_val = new_val[:1]
                    self.char_tree.set(row_id, columns[col_index], new_val)
                finally:
                    self._char_edit.destroy()
                    self._char_edit = None
                    # Nach Edit automatisch speichern
                    self.save_char_mappings()

            def _cancel(event=None):
                try:
                    self._char_edit.destroy()
                finally:
                    self._char_edit = None

            self._char_edit.bind('<Return>', _commit)
            self._char_edit.bind('<Escape>', _cancel)
            self._char_edit.bind('<FocusOut>', _commit)
            self._char_edit.focus_set()
        except Exception:
            if self._char_edit is not None:
                try:
                    self._char_edit.destroy()
                except Exception:
                    pass
                self._char_edit = None

    # ===== Persistenz für DetectParams =====
    def _dp_to_dict(self):
        return {
            'top_frac': float(self.dp.top_frac),
            'bottom_frac': float(self.dp.bottom_frac),
            'left_frac': float(self.dp.left_frac),
            'right_frac': float(self.dp.right_frac),
            'min_area_frac': float(self.dp.min_area_frac),
            'max_area_frac': float(self.dp.max_area_frac),
            'min_aspect': float(self.dp.min_aspect),
            'max_aspect': float(self.dp.max_aspect),
            'padding_top': int(self.dp.padding_top),
            'padding_bottom': int(self.dp.padding_bottom),
            'padding_left': int(self.dp.padding_left),
            'padding_right': int(self.dp.padding_right),
            'enable_post_processing': bool(self.dp.enable_post_processing),
        }

    def load_detect_params_from_config(self):
        try:
            cfg = self.json_config.get('ocr_settings', {}).get('detect_params', {})
            if not isinstance(cfg, dict):
                return
            # Nur Suchbereich und Padding aus Konfiguration laden, Filter-Werte bleiben optimiert
            allowed_keys = {'top_frac', 'bottom_frac', 'left_frac', 'right_frac', 
                           'padding_top', 'padding_bottom', 'padding_left', 'padding_right',
                           'enable_post_processing'}
            for k, v in cfg.items():
                if k in allowed_keys and hasattr(self.dp, k):
                    try:
                        setattr(self.dp, k, type(getattr(self.dp, k))(v))
                    except Exception:
                        pass
        except Exception:
            pass

    def save_detect_params_to_config(self):
        try:
            if 'ocr_settings' not in self.json_config:
                self.json_config['ocr_settings'] = {}
            self.json_config['ocr_settings']['detect_params'] = self._dp_to_dict()
            # über parent ConfigManager speichern
            if hasattr(self.parent, 'config_manager'):
                self.parent.config_manager.save_config()
        except Exception:
            pass

    # Parallelitäts-Persistenz
    def load_max_workers_from_config(self):
        try:
            val = self.json_config.get('ocr_settings', {}).get('max_workers')
            if val is None:
                return None
            val = int(val)
            if 1 <= val <= self._cpu_count:
                return val
            return None
        except Exception:
            return None

    def save_max_workers_to_config(self):
        try:
            if 'ocr_settings' not in self.json_config:
                self.json_config['ocr_settings'] = {}
            self.json_config['ocr_settings']['max_workers'] = int(self.max_workers)
            if hasattr(self.parent, 'config_manager'):
                self.parent.config_manager.save_config()
        except Exception:
            pass

