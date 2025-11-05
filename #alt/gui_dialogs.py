#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dialog-Fenster
Verschiedene Dialoge für Benutzerinteraktionen
"""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pandas as pd
import traceback
from PIL import Image, ExifTags
import json

from constants import DIALOG_WIDTH, DIALOG_HEIGHT, PROGRESS_WINDOW_WIDTH, PROGRESS_WINDOW_HEIGHT
from utils_logging import logger


class AlternativeKurzelDialog:
    """Dialog für das Bearbeiten von alternativen Kürzeln"""
    
    def __init__(self, parent, title, alt_kurzel="", korrigiertes_kurzel=""):
        self.parent = parent
        self.result = None
        
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("400x200")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        self.dialog.geometry("+%d+%d" % (parent.winfo_rootx() + 50, parent.winfo_rooty() + 50))
        
        self.alt_kurzel_var = tk.StringVar(value=alt_kurzel)
        self.korrigiertes_kurzel_var = tk.StringVar(value=korrigiertes_kurzel)
        
        self.create_widgets()
        
        self.alt_kurzel_entry.focus()
        self.dialog.wait_window()
    
    def create_widgets(self):
        """Erstellt die Widgets des Dialogs"""
        main_frame = ttk.Frame(self.dialog)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        ttk.Label(main_frame, text="Alternatives Kürzel:").pack(anchor='w', pady=(0, 5))
        self.alt_kurzel_entry = ttk.Entry(main_frame, textvariable=self.alt_kurzel_var, width=30)
        self.alt_kurzel_entry.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(main_frame, text="Korrigiertes Kürzel:").pack(anchor='w', pady=(0, 5))
        self.korrigiertes_kurzel_entry = ttk.Entry(main_frame, textvariable=self.korrigiertes_kurzel_var, width=30)
        self.korrigiertes_kurzel_entry.pack(fill=tk.X, pady=(0, 20))
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X)
        
        ttk.Button(button_frame, text="Abbrechen", command=self.cancel).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(button_frame, text="OK", command=self.ok).pack(side=tk.RIGHT)
        
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
    """Dialog zum Laden von Grunddaten aus Excel-Dateien"""
    
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
        
        columns = ("Zeile", "Windpark", "Land", "Seriennummer", "Turbinen-ID")
        self.tree = ttk.Treeview(data_frame, columns=columns, show="headings", height=15)
        
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=120)
        
        scrollbar = ttk.Scrollbar(data_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
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
            last_file = self.parent.json_config.get('last_selections', {}).get('excel_file', '')
            initial_dir = os.path.dirname(last_file) if last_file and os.path.exists(last_file) else None
            
            file_path = filedialog.askopenfilename(
                title="Excel-Datei mit Grunddaten auswählen",
                filetypes=[("Excel files", "*.xlsx *.xls")],
                initialdir=initial_dir
            )
            
            if file_path:
                logger.info(f"Excel-Datei ausgewählt: {file_path}")
                
                if 'last_selections' not in self.parent.json_config:
                    self.parent.json_config['last_selections'] = {}
                self.parent.json_config['last_selections']['excel_file'] = file_path
                self.parent.config_manager.save_config()
                
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
            
            df = pd.read_excel(file_path, header=2)
            df.columns = df.columns.str.strip()
            
            logger.debug(f"Excel-Datei geladen: {len(df)} Zeilen, Spalten: {list(df.columns)}")
            
            def find_column(possible_names):
                for name in possible_names:
                    for col in df.columns:
                        if name.lower() in col.lower() or col.lower() in name.lower():
                            return col
                return None
            
            windpark_col = find_column(['windpark', 'windfarm', 'park', 'project', 'projekt'])
            land_col = find_column(['land', 'country', 'staat', 'nation'])
            sn_col = find_column(['sn', 'seriennummer', 'serial', 'serial_number', 'turbine_sn'])
            id_col = find_column(['turbine_id', 'id', 'anlagen_nr', 'turbinen_id', 'turbine_number'])
            hersteller_col = find_column(['hersteller', 'manufacturer', 'fabrikant', 'turbine_manufacturer'])
            
            logger.debug(f"Gefundene Spalten: Windpark={windpark_col}, Land={land_col}, "
                        f"Seriennummer={sn_col}, ID={id_col}, Hersteller={hersteller_col}")
            
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
                    
                    self.tree.insert("", "end", values=(
                        index + 1,
                        data_row["windfarm_name"],
                        data_row["windfarm_country"],
                        data_row["turbine_sn"],
                        data_row["turbine_id"]
                    ))
                except Exception as e:
                    logger.warning(f"Fehler beim Verarbeiten von Zeile {index}: {e}")
                    continue
            
            self.load_btn.config(state=tk.NORMAL)
            self.update_btn.config(state=tk.NORMAL)
            
            success_msg = f"Excel-Datei erfolgreich geladen: {len(self.excel_data)} Zeilen\n\nGefundene Spalten:\nWindpark: {windpark_col or 'Nicht gefunden'}\nLand: {land_col or 'Nicht gefunden'}\nSeriennummer: {sn_col or 'Nicht gefunden'}\nID: {id_col or 'Nicht gefunden'}"
            logger.info(f"Excel-Daten erfolgreich geladen: {len(self.excel_data)} Einträge")
            messagebox.showinfo("Erfolg", success_msg)
            
        except Exception as e:
            logger.error(f"Fehler beim Laden der Excel-Datei: {e}")
            logger.debug(f"Traceback: {traceback.format_exc()}")
            messagebox.showerror("Fehler", f"Fehler beim Laden der Excel-Datei:\n{e}")
            
    def on_row_select(self, event):
        """Wird aufgerufen, wenn eine Zeile ausgewählt wird"""
        selection = self.tree.selection()
        if selection:
            item = self.tree.item(selection[0])
            row_index = int(item['values'][0]) - 1
            
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
                    with Image.open(file_path) as img:
                        exif_data = img.getexif()
                        
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
                        
                        if update_existing:
                            if any(key in existing_json for key in ['windpark', 'windpark_land', 'sn', 'anlagen_nr']):
                                existing_json.update({
                                    'windpark': data['windfarm_name'],
                                    'windpark_land': data['windfarm_country'],
                                    'sn': data['turbine_sn'],
                                    'anlagen_nr': data['turbine_id'],
                                    'hersteller': data['turbine_manufacturer']
                                })
                                updated += 1
                            else:
                                skipped += 1
                                continue
                        else:
                            existing_json.update({
                                'windpark': data['windfarm_name'],
                                'windpark_land': data['windfarm_country'],
                                'sn': data['turbine_sn'],
                                'anlagen_nr': data['turbine_id'],
                                'hersteller': data['turbine_manufacturer']
                            })
                            updated += 1
                        
                        new_json_str = json.dumps(existing_json, ensure_ascii=False)
                        new_user_comment = f"ASCII\0\0\0{new_json_str}".encode('utf-8')
                        
                        exif_data[0x9286] = new_user_comment
                        
                        img.save(file_path, exif=exif_data.tobytes())
                        processed += 1
                        
                except Exception as e:
                    print(f"Fehler bei {filename}: {e}")
                    continue
                    
                progress_var.set(i + 1)
                progress_window.update()
                
            progress_window.destroy()
            
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


class OCRCorrectionDialog(tk.Toplevel):
    """Dialog zur Korrektur eines erkannten Kürzels mit Crop-Vorschau"""
    def __init__(self, parent, crop_img_pil, detected_text, valid_kurzel, on_save):
        super().__init__(parent)
        self.title("Kürzel korrigieren")
        self.resizable(False, False)
        self.on_save = on_save
        self.valid_kurzel = valid_kurzel

        preview = ttk.LabelFrame(self, text="Vorschau")
        preview.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        try:
            from PIL import ImageTk, Image
            img = crop_img_pil.copy() if crop_img_pil else Image.new('RGB', (320, 120), 'white')
            img.thumbnail((320, 120), Image.Resampling.LANCZOS)
            self._photo = ImageTk.PhotoImage(img)
            tk.Label(preview, image=self._photo).pack()
        except Exception:
            tk.Label(preview, text="(Keine Vorschau)").pack()

        form = ttk.Frame(self)
        form.pack(fill=tk.X, padx=10)
        ttk.Label(form, text="Erkannt:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.text_var = tk.StringVar(value=str(detected_text or ""))
        ttk.Entry(form, textvariable=self.text_var, width=24).grid(row=0, column=1, padx=5)

        ttk.Label(form, text="Kürzel wählen:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.choice_var = tk.StringVar()
        # Alphabetisch sortierte Auswahl
        try:
            sorted_vals = sorted([str(v) for v in valid_kurzel], key=lambda s: s.upper())
        except Exception:
            sorted_vals = valid_kurzel
        self.choice = ttk.Combobox(form, textvariable=self.choice_var, values=sorted_vals, width=22)
        self.choice.grid(row=1, column=1, padx=5)

        btns = ttk.Frame(self)
        btns.pack(fill=tk.X, padx=10, pady=10)
        ttk.Button(btns, text="Übernehmen", command=self._accept).pack(side=tk.RIGHT)
        ttk.Button(btns, text="Überspringen", command=self._skip).pack(side=tk.RIGHT, padx=(0, 5))

        self.grab_set()

    def _accept(self):
        val = self.choice_var.get().strip() or self.text_var.get().strip()
        if callable(self.on_save):
            self.on_save(val)
        self.destroy()

    def _skip(self):
        self.destroy()


class CorrectionQueueDialog(tk.Toplevel):
    """Dialog zum Durchgehen aller ungültigen OCR-Ergebnisse (Inline-Editor)"""
    def __init__(self, parent, invalid_items, valid_kurzel, on_done):
        super().__init__(parent)
        self.title("Korrekturen prüfen")
        self.resizable(True, True)
        
        # Fenstergröße automatisch anpassen
        self.geometry("1000x600")  # Breite x Höhe
        self.minsize(800, 400)     # Minimale Größe
        
        self.invalid_items = invalid_items  # Liste aus (fname, crop_pil, text, path)
        try:
            self.valid_kurzel = sorted([str(v) for v in valid_kurzel], key=lambda s: s.upper())
        except Exception:
            self.valid_kurzel = valid_kurzel
        self.on_done = on_done

        # Hauptlayout: Links scrollbarer Bereich mit Zeilen, rechts Aktionen
        left = ttk.Frame(self)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=10)
        right = ttk.Frame(self)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)

        # Scrollbarer Bereich
        self.canvas = tk.Canvas(left, borderwidth=0)
        vsb = ttk.Scrollbar(left, orient="vertical", command=self.canvas.yview)
        self.rows_frame = ttk.Frame(self.canvas)
        self.rows_frame.bind(
            "<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self.canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=vsb.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # Zeilen erstellen
        self._thumbs = []
        for idx, (fname, crop_pil, text, path) in enumerate(self.invalid_items):
            row = ttk.Frame(self.rows_frame)
            row.pack(fill=tk.X, pady=4)

            # Thumbnail
            try:
                from PIL import ImageTk, Image
                img = crop_pil.copy() if crop_pil else Image.new('RGB', (320, 120), 'white')
                img.thumbnail((180, 80), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self._thumbs.append(photo)
                tk.Label(row, image=photo).pack(side=tk.LEFT, padx=(0, 8))
            except Exception:
                ttk.Label(row, text="(kein Bild)").pack(side=tk.LEFT, padx=(0, 8))

            # Datei + erkannter Text
            center = ttk.Frame(row)
            center.pack(side=tk.LEFT, fill=tk.X, expand=True)
            ttk.Label(center, text=fname).pack(anchor=tk.W)
            ttk.Label(center, text=f"Erkannt: {text}", foreground="#555").pack(anchor=tk.W)

            # Auswahl (alphabetisch)
            sel_frame = ttk.Frame(row)
            sel_frame.pack(side=tk.RIGHT, padx=(8, 0))
            var = tk.StringVar(value="")
            combo = ttk.Combobox(sel_frame, textvariable=var, values=self.valid_kurzel, width=18)
            combo.pack()

            def make_on_change(_idx=idx, _path=path, _var=var):
                def _on_change(event=None):
                    new_text = _var.get().strip()
                    if not new_text:
                        return
                    try:
                        from utils_exif import save_exif_usercomment
                        exif = {}
                        exif['TAGOCR'] = new_text
                        save_exif_usercomment(_path, exif)
                        # Im Speicher aktualisieren
                        fname, crop_pil, _old, p = self.invalid_items[_idx]
                        self.invalid_items[_idx] = (fname, crop_pil, new_text, p)
                    except Exception:
                        pass
                return _on_change

            combo.bind('<<ComboboxSelected>>', make_on_change())

        # Buttons rechts
        ttk.Button(right, text="Alle akzeptieren", command=self._accept_all).pack(fill=tk.X)
        ttk.Button(right, text="Fertig", command=self._finish).pack(fill=tk.X, pady=(5, 0))

        self.grab_set()

    def _accept_all(self):
        self._finish()

    def _finish(self):
        if callable(self.on_done):
            self.on_done(self.invalid_items)
        self.destroy()