#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Label OCR GUI
-------------
PySide6-GUI zum Markieren/Auslesen des weißen Labels oben rechts in Endoskopie-Bildern.
Funktionen:
 - Ordner wählen und Bildliste anzeigen
 - Vorschau mit Suchfenster (oben rechts) und erkannter Box
 - Parameter (ROI-Fractions, Padding, OCR) einstellen
 - OCR auf Einzelbild oder kompletten Ordner ausführen
 - Ergebnisse als CSV + Einzeldateien (boxed, roi, pre_ocr) speichern

Abhängigkeiten:
    pip install PySide6 opencv-python numpy easyocr

Nur EasyOCR wird verwendet - keine zusätzliche Installation erforderlich

# Tesseract-Hinweis entfernt - nur noch EasyOCR
"""
from __future__ import annotations

import sys
import csv
import json
import os
import time
from pathlib import Path
# PIL entfernt - Thermal-Druck nicht mehr benötigt
# win32print und win32api entfernt - Thermal-Druck nicht mehr benötigt
from dataclasses import dataclass
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing

import cv2
import numpy as np
# pytesseract entfernt - nur noch EasyOCR
# PIL import entfernt - Thermal-Druck nicht mehr benötigt
import io
import easyocr

from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QPixmap, QImage, QPainter, QPen, QAction, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFileDialog, QListWidget, QLabel,
    QVBoxLayout, QHBoxLayout, QFormLayout, QDoubleSpinBox, QSpinBox, QPushButton,
    QLineEdit, QMessageBox, QSplitter, QGroupBox, QCheckBox, QTextEdit, QTabWidget,
    QProgressBar
)

# -------------------- Konfiguration --------------------

# Tesseract-Suche entfernt - nur noch EasyOCR

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}

# Konfigurationsdatei für persistente Einstellungen
CONFIG_FILE = Path.home() / ".label_ocr_gui.json"


@dataclass
class DetectParams:
    top_frac: float = 0.0
    bottom_frac: float = 0.20
    left_frac: float = 0.0
    right_frac: float = 0.18
    min_area_frac: float = 0.00
    max_area_frac: float = 0.12
    min_aspect: float = 1.4
    max_aspect: float = 6.5
    padding_top: int = -2
    padding_bottom: int = -2
    padding_left: int = -2
    padding_right: int = -2
    # Tesseract-spezifische Parameter entfernt - nur noch EasyOCR
    ocr_method: str = "easyocr"
    
    # Multi-Core Einstellungen
    use_multicore: bool = True
    num_cores: int = 4


class ImageView(QLabel):
    """Zeigt ein Bild und optional Rechtecke (ROI/Box) als Overlay."""
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(600, 400)
        self._pixmap: QPixmap | None = None
        self.search_rect = None   # (x,y,w,h) in Bildkoordinaten
        self.box_rect = None      # (x,y,w,h) in Bildkoordinaten

    def set_image(self, qpix: QPixmap):
        self._pixmap = qpix
        self.update()

    def set_rects(self, search_rect, box_rect):
        self.search_rect = search_rect
        self.box_rect = box_rect
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._pixmap:
            return
        painter = QPainter(self)
        # Bild einpassen (aspect fit)
        pm = self._pixmap
        avail = self.contentsRect()
        scaled = pm.scaled(avail.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x_off = (avail.width()  - scaled.width())  // 2 + avail.left()
        y_off = (avail.height() - scaled.height()) // 2 + avail.top()
        painter.drawPixmap(x_off, y_off, scaled)

        scale_x = scaled.width() / pm.width()
        scale_y = scaled.height() / pm.height()

        def draw_rect(rect, color, width=2, style=Qt.SolidLine):
            if not rect:
                return
            x,y,w,h = rect
            rx = x_off + x * scale_x
            ry = y_off + y * scale_y
            rw = w * scale_x
            rh = h * scale_y
            pen = QPen(color, width, style)
            painter.setPen(pen)
            painter.drawRect(QRectF(rx, ry, rw, rh))

        # Suchfenster (blau gestrichelt), erkannte Box (grün)
        draw_rect(self.search_rect, Qt.blue, 2, Qt.DashLine)
        draw_rect(self.box_rect, Qt.green, 3, Qt.SolidLine)
        painter.end()


def cv_to_qpix(img_bgr) -> QPixmap:
    if img_bgr is None:
        return QPixmap()
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    bytes_per_line = ch * w
    qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
    return QPixmap.fromImage(qimg)


# ----------------- Bildverarbeitung -----------------

def find_text_box_easyocr(img_bgr, p: DetectParams):
    """Verwendet EasyOCR für automatische Text-Erkennung und Kasten-Findung."""
    try:
        # EasyOCR initialisieren (nur einmal)
        if not hasattr(find_text_box_easyocr, 'reader'):
            find_text_box_easyocr.reader = easyocr.Reader(['en'], gpu=False)

        # Suchbereich definieren (wie bei der alten Methode)
        H, W = img_bgr.shape[:2]
        x0 = int(W * p.left_frac)
        x1 = int(W * p.right_frac)
        y0 = int(H * p.top_frac)
        y1 = int(H * p.bottom_frac)
        x0 = max(0, min(W - 1, x0))
        x1 = max(1, min(W, x1))
        y0 = max(0, min(H - 1, y0))
        y1 = max(1, min(H, y1))

        # ROI ausschneiden
        roi = img_bgr[y0:y1, x0:x1]
        if roi.size == 0:
            return None, (x0, y0, max(1, x1 - x0), max(1, y1 - y0))

        # OCR mit Detection auf ROI ausführen
        result = find_text_box_easyocr.reader.readtext(roi)
        if not result:
            return None, (x0, y0, max(1, x1 - x0), max(1, y1 - y0))

        img_area = H * W

        best_box = None
        best_score = -1e9

        for detection in result:
            # EasyOCR Format: [[[x1,y1],[x2,y2],[x3,y3],[x4,y4]], text, confidence]
            box_coords = detection[0]
            text = detection[1]
            confidence = detection[2]

            # Bounding Box berechnen (relativ zum ROI)
            x_coords = [pt[0] for pt in box_coords]
            y_coords = [pt[1] for pt in box_coords]
            x1_rel, x2_rel = min(x_coords), max(x_coords)
            y1_rel, y2_rel = min(y_coords), max(y_coords)
            w = x2_rel - x1_rel
            h = y2_rel - y1_rel

            # Koordinaten zurück auf das Gesamtbild umrechnen
            x1_abs = x0 + x1_rel
            y1_abs = y0 + y1_rel

            # Filter nach Größe und Seitenverhältnis
            area_frac = (w * h) / max(img_area, 1)
            if area_frac < p.min_area_frac or area_frac > p.max_area_frac:
                continue

            aspect = w / max(h, 1)
            if not (p.min_aspect <= aspect <= p.max_aspect):
                continue

            # Score basierend auf Confidence und Position (oben-rechts bevorzugen)
            dist_penalty = ((y1_abs) / max(H, 1)) * 0.6 + ((x1_abs + w) < W) * 0.4
            score = float(confidence) * 100.0 - 50.0 * float(dist_penalty)

            if score > best_score:
                best_score = score
                best_box = (int(x1_abs), int(y1_abs), int(w), int(h))

        if best_box is None:
            return None, (x0, y0, max(1, x1 - x0), max(1, y1 - y0))

        # Padding anwenden (separat für alle vier Seiten)
        x, y, w, h = best_box
        x = max(0, x - p.padding_left)
        y = max(0, y - p.padding_top)
        w = min(W - x, w + p.padding_left + p.padding_right)
        h = min(H - y, h + p.padding_top + p.padding_bottom)

        return (x, y, w, h), (x0, y0, x1 - x0, y1 - y0)

    except Exception as e:
        print(f"EasyOCR Fehler: {e}")
        return None, None


# Alte find_white_box_top_right Funktion entfernt - nur noch EasyOCR


# preprocess_for_ocr Funktion entfernt - nur noch EasyOCR


# run_simple_ocr Funktion entfernt - nur noch EasyOCR


def upscale_crop(crop_img, scale_factor: float = 2.0):
    """Upscales ein Crop-Bild für bessere OCR-Erkennung."""
    if crop_img is None or crop_img.size == 0:
        return crop_img
    
    # Interpolation-Methode für bessere Qualität
    height, width = crop_img.shape[:2]
    new_width = int(width * scale_factor)
    new_height = int(height * scale_factor)
    
    # INTER_CUBIC für beste Qualität beim Upscaling
    upscaled = cv2.resize(crop_img, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
    
    return upscaled


def post_process_text(text: str, p: DetectParams, enabled: bool = True) -> tuple[str, list[str]]:
    """Post-Processing für erkannten Text mit Ersetzungslogik."""
    if not enabled or not text or text.startswith("[") or text.startswith("Kein"):
        return text, []
    
    # Zeichen-Mapping für häufige OCR-Fehler
    char_mappings = {
        'l': '1',  # kleines l → 1
        'Z': '2',  # großes Z → 2
        'z': '2',  # kleines z → 2
        'I': '1',  # großes I → 1 (falls gewünscht)
        'O': '0',  # großes O → 0 (falls gewünscht)
        'o': '0',  # kleines o → 0 (falls gewünscht)
    }
    
    # Text verarbeiten und Ersetzungen protokollieren
    processed_text = text
    replacements = []
    
    for old_char, new_char in char_mappings.items():
        if old_char in processed_text:
            count = processed_text.count(old_char)
            processed_text = processed_text.replace(old_char, new_char)
            replacements.append(f"'{old_char}' → '{new_char}' ({count}x)")
    
    return processed_text, replacements


def run_ocr_easyocr(img_bgr, p: DetectParams) -> str:
    """Verwendet EasyOCR für Text-Erkennung mit Upscaling."""
    try:
        # EasyOCR initialisieren (nur einmal)
        if not hasattr(run_ocr_easyocr, 'reader'):
            run_ocr_easyocr.reader = easyocr.Reader(['en'], gpu=False)
        
        # Crop-Bild upscalen für bessere OCR-Erkennung
        upscaled_img = upscale_crop(img_bgr, scale_factor=2.0)
        
        # OCR mit Recognition auf upgescaled Bild ausführen
        result = run_ocr_easyocr.reader.readtext(upscaled_img)
        
        if not result:
            return "[Kein Text erkannt]"
        
        # Alle erkannten Texte zusammenfassen
        texts = []
        for detection in result:
            text = detection[1]  # Text ist an Position [1]
            confidence = detection[2]  # Confidence
            if confidence > 0.3:  # Nur Texte mit guter Confidence
                texts.append(text)
        
        raw_text = " ".join(texts) if texts else "[Kein Text erkannt]"
        
        # Post-Processing anwenden
        processed_text, replacements = post_process_text(raw_text, p)
        
        # Ersetzungen loggen
        if replacements:
            print(f"Post-Processing Ersetzungen: {', '.join(replacements)}")
        
        return processed_text
        
    except Exception as e:
        return f"[EasyOCR-Error: {e}]"


def run_ocr(img_bgr, p: DetectParams) -> str:
    """Nur EasyOCR verwenden."""
    return run_ocr_easyocr(img_bgr, p)


def process_single_image(args):
    """Verarbeitet ein einzelnes Bild - für Multi-Core-Verarbeitung."""
    img_path, params_dict, save_parts = args
    
    try:
        # EasyOCR Reader für diesen Prozess initialisieren
        reader = easyocr.Reader(['en'], gpu=False)
        
        # params_dict zu DetectParams-Objekt konvertieren
        params = DetectParams(**params_dict)
        
        # Bild laden
        img = cv2.imread(str(img_path))
        if img is None:
            return img_path, None, "[Bild konnte nicht geladen werden]", "", 0.0
        
        start_time = time.time()
        
        # OCR ausführen (nur EasyOCR)
        box, _ = find_text_box_easyocr(img, params)
        
        if box is None:
            # Kein Text gefunden
            crop_img = None
            text = "[Kein Text erkannt]"
            crop_path = ""
        else:
            # Text-Bereich ausschneiden
            x, y, w, h = box
            crop_img = img[y:y+h, x:x+w]
            
            # OCR-Text erkennen (nur EasyOCR)
            raw_text = run_ocr_easyocr(crop_img, params)
            # Post-Processing anwenden
            text, _ = post_process_text(raw_text, params, True)
            
            # Crop speichern
            crop_filename = f"crop_{img_path.stem}.jpg"
            crop_path = f"crops/{crop_filename}"
        
        processing_time = time.time() - start_time
        
        return img_path, crop_img, text, crop_path, processing_time
        
    except Exception as e:
        return img_path, None, f"[Fehler: {e}]", "", 0.0


# ------------------- GUI -------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Label OCR GUI")
        self.setGeometry(50, 50, 1400, 900)
        self.params = DetectParams()
        self.current_img_path: Path | None = None
        self.current_img_bgr = None
        self.current_box = None
        self.current_search_rect = None
        self.current_crop = None
        self.current_preprocessed = None

        self._build_ui()
        self._connect()
        self._load_config()
        
        # Log-Funktion nach UI-Initialisierung
        self.log("Label OCR GUI gestartet")

    def log(self, message: str):
        """Fügt eine Nachricht zum Live-Log hinzu."""
        timestamp = time.strftime("%H:%M:%S")
        log_message = f"[{timestamp}] {message}"
        self.log_text.append(log_message)
        # Automatisch zum Ende scrollen
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        # Auch in Konsole ausgeben
        print(log_message)
    
    def set_progress(self, value: int, maximum: int = 100, text: str = ""):
        """Setzt den Fortschrittsbalken."""
        self.progress_bar.setMaximum(maximum)
        self.progress_bar.setValue(value)
        if text:
            self.progress_bar.setFormat(f"{text} ({value}/{maximum})")
        else:
            self.progress_bar.setFormat(f"{value}/{maximum}")
        self.progress_bar.setVisible(True)
        # GUI aktualisieren
        QApplication.processEvents()
    
    def hide_progress(self):
        """Versteckt den Fortschrittsbalken."""
        self.progress_bar.setVisible(False)

        # Toolbar: Reset-Defaults
        reset_act = QAction("Standardwerte", self)
        reset_act.triggered.connect(self.set_defaults)
        self.addAction(reset_act)
        self.menuBar().addMenu("Aktion").addAction(reset_act)

    # ---------- UI ----------
    def _build_ui(self):
        self.viewer = ImageView()
        self.viewer.setText("Kein Bild geladen")

        self.folder_edit = QLineEdit()
        self.browse_btn = QPushButton("Ordner wählen…")
        self.list_widget = QListWidget()
        
        # Bildzähler Label
        self.image_counter_label = QLabel("Bilder: 0")
        self.image_counter_label.setStyleSheet("QLabel { font-weight: bold; color: #007bff; }")

        # Parameter-Steuerung
        self.top_spin = QDoubleSpinBox(); self.top_spin.setRange(0,1); self.top_spin.setSingleStep(0.01)
        self.bottom_spin = QDoubleSpinBox(); self.bottom_spin.setRange(0,1); self.bottom_spin.setSingleStep(0.01)
        self.left_spin = QDoubleSpinBox(); self.left_spin.setRange(0,1); self.left_spin.setSingleStep(0.01)
        self.right_spin = QDoubleSpinBox(); self.right_spin.setRange(0,1); self.right_spin.setSingleStep(0.01)

        self.min_area_spin = QDoubleSpinBox(); self.min_area_spin.setRange(0,1); self.min_area_spin.setSingleStep(0.001)
        self.max_area_spin = QDoubleSpinBox(); self.max_area_spin.setRange(0,1); self.max_area_spin.setSingleStep(0.001)
        self.min_asp_spin  = QDoubleSpinBox(); self.min_asp_spin.setRange(0.1, 20); self.min_asp_spin.setSingleStep(0.1)
        self.max_asp_spin  = QDoubleSpinBox(); self.max_asp_spin.setRange(0.1, 20); self.max_asp_spin.setSingleStep(0.1)
        
        # Padding für alle vier Seiten
        self.pad_top_spin = QSpinBox(); self.pad_top_spin.setRange(-10, 50)
        self.pad_bottom_spin = QSpinBox(); self.pad_bottom_spin.setRange(-10, 50)
        self.pad_left_spin = QSpinBox(); self.pad_left_spin.setRange(-10, 50)
        self.pad_right_spin = QSpinBox(); self.pad_right_spin.setRange(-10, 50)

        # Tesseract-Pfad entfernt - nur noch EasyOCR
        
        # Tesseract-spezifische UI-Elemente entfernt - nur noch EasyOCR
        
        # OCR-Methode Auswahl (nur EasyOCR)
        from PySide6.QtWidgets import QComboBox
        self.ocr_method_combo = QComboBox()
        self.ocr_method_combo.addItems(["easyocr"])
        self.ocr_method_combo.setCurrentText("easyocr")
        
        # Post-Processing Einstellungen
        self.post_process_chk = QCheckBox("Post-Processing aktivieren")
        self.post_process_chk.setChecked(True)
        
        # Multi-Core Einstellungen
        self.multicore_chk = QCheckBox("Multi-Core-Verarbeitung")
        self.multicore_chk.setChecked(True)
        
        self.cores_spin = QSpinBox()
        self.cores_spin.setRange(1, multiprocessing.cpu_count())
        self.cores_spin.setValue(multiprocessing.cpu_count())
        
        # Ersetzungsregeln anzeigen
        self.replacements_label = QLabel("Ersetzungsregeln:\n'l' → '1'\n'Z'/'z' → '2'\n'I' → '1'\n'O'/'o' → '0'")
        self.replacements_label.setStyleSheet("QLabel { background-color: #f0f0f0; padding: 5px; border: 1px solid #ccc; }")
        self.replacements_label.setWordWrap(True)

        self.detect_btn = QPushButton("Kasten finden")
        self.ocr_btn = QPushButton("Nur dieses Bild OCR")
        self.process_all_btn = QPushButton("Ordner verarbeiten")
        self.analyze_all_btn = QPushButton("Alle Bilder analysieren")
        self.save_parts_chk = QCheckBox("Crops/Box speichern")
        self.save_parts_chk.setChecked(True)

        self.out_dir_edit = QLineEdit()
        self.out_browse_btn = QPushButton("Ausgabeordner…")
        
        # Log-Anzeige
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(120)
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 8))
        
        # Fortschrittsbalken
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setMinimumHeight(25)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 2px solid #007bff;
                border-radius: 5px;
                text-align: center;
                font-weight: bold;
                background-color: #f0f0f0;
            }
            QProgressBar::chunk {
                background-color: #007bff;
                border-radius: 3px;
            }
        """)
        
        # Vorschau-Bereiche
        self.preprocessed_preview = QLabel("Kein Preprocessed")
        self.preprocessed_preview.setMinimumSize(150, 75)
        self.preprocessed_preview.setAlignment(Qt.AlignCenter)
        self.preprocessed_preview.setStyleSheet("border: 1px solid gray; background-color: #f0f0f0;")

        # Layouts
        # Linke Seite: Ordner und Bildliste
        left_layout = QVBoxLayout()
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(self.browse_btn)
        left_layout.addLayout(folder_row)
        
        # Bildzähler hinzufügen
        left_layout.addWidget(self.image_counter_label)
        
        left_layout.addWidget(self.list_widget, 1)
        
        # Linke Seite begrenzen
        left_widget = QWidget()
        left_widget.setLayout(left_layout)
        left_widget.setMaximumWidth(300)

        # Rechte Seite: Bild und Einstellungen nebeneinander
        right_layout = QHBoxLayout()
        
        # Bild-Container mit Buttons drumherum
        image_container = QWidget()
        image_layout = QVBoxLayout(image_container)
        
        # Menüband mit allen Buttons oben
        menu_bar = QHBoxLayout()
        menu_bar.addWidget(self.detect_btn)
        menu_bar.addWidget(self.ocr_btn)
        menu_bar.addWidget(self.process_all_btn)
        menu_bar.addWidget(self.analyze_all_btn)
        
        # Multi-Core Einstellungen direkt in der Menüleiste
        menu_bar.addWidget(QLabel("CPU-Kerne:"))
        menu_bar.addWidget(self.cores_spin)
        menu_bar.addWidget(self.multicore_chk)
        
        # Speichern-Button hinzufügen
        self.save_settings_btn = QPushButton("Einstellungen speichern")
        menu_bar.addWidget(self.save_settings_btn)
        
        menu_bar.addStretch()  # Füllt den restlichen Platz
        image_layout.addLayout(menu_bar)

        # Bild darunter
        image_layout.addWidget(self.viewer, 1)
        
        # Live-Log direkt unter dem Bild
        log_group = QGroupBox("Live-Log & Fortschritt")
        log_layout = QVBoxLayout(log_group)
        log_layout.addWidget(self.progress_bar)
        log_layout.addWidget(self.log_text)
        image_layout.addWidget(log_group)
        
        # Einstellungen-Container
        settings_container = QWidget()
        settings_layout = QVBoxLayout(settings_container)

        # Parameter-Gruppe (kollabierbar)
        form = QFormLayout()
        form.addRow("Top (0-1)", self.top_spin)
        form.addRow("Bottom (0-1)", self.bottom_spin)
        form.addRow("Left (0-1)", self.left_spin)
        form.addRow("Right (0-1)", self.right_spin)
        form.addRow("Min Area Frac", self.min_area_spin)
        form.addRow("Max Area Frac", self.max_area_spin)
        form.addRow("Min Aspect", self.min_asp_spin)
        form.addRow("Max Aspect", self.max_asp_spin)
        form.addRow("Padding Top [px]", self.pad_top_spin)
        form.addRow("Padding Bottom [px]", self.pad_bottom_spin)
        form.addRow("Padding Left [px]", self.pad_left_spin)
        form.addRow("Padding Right [px]", self.pad_right_spin)

        param_group = QGroupBox("Suchfenster & Filter")
        param_group.setLayout(form)
        param_group.setCheckable(True)  # Macht die Gruppe kollabierbar
        param_group.setChecked(False)   # Standardmäßig eingeklappt

        # OCR-Gruppe (kollabierbar)
        ocr_form = QFormLayout()
        
        # Tesseract-Pfad Zeile
        # Tesseract-Row entfernt - nur noch EasyOCR
        
        ocr_form.addRow("OCR-Methode", self.ocr_method_combo)
        ocr_form.addRow("", self.post_process_chk)
        ocr_form.addRow("", self.replacements_label)
        
        ocr_group = QGroupBox("OCR & Post-Processing")
        ocr_group.setLayout(ocr_form)
        ocr_group.setCheckable(True)  # Macht die Gruppe kollabierbar
        ocr_group.setChecked(False)   # Standardmäßig eingeklappt

        # Ausgabe
        out_row = QHBoxLayout()
        out_row.addWidget(self.out_dir_edit, 1)
        out_row.addWidget(self.out_browse_btn)

        # Vorschau-Gruppe (kollabierbar)
        preview_group = QGroupBox("Vorschau")
        preview_layout = QVBoxLayout()
        preview_layout.addWidget(QLabel("Vorverarbeitet für OCR:"))
        preview_layout.addWidget(self.preprocessed_preview)
        preview_group.setLayout(preview_layout)
        preview_group.setCheckable(True)  # Macht die Gruppe kollabierbar
        preview_group.setChecked(False)   # Standardmäßig eingeklappt

        # Einstellungen zusammenfassen
        settings_layout.addWidget(param_group)
        settings_layout.addWidget(ocr_group)
        settings_layout.addWidget(preview_group)
        settings_layout.addWidget(self.save_parts_chk)
        settings_layout.addLayout(out_row)
        settings_layout.addStretch()  # Füllt den restlichen Platz

        # Bild und Einstellungen nebeneinander
        right_layout.addWidget(image_container, 3)  # Bild bekommt mehr Platz
        right_layout.addWidget(settings_container, 1)  # Einstellungen weniger Platz

        right = QWidget(); right.setLayout(right_layout)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)  # Linke Seite (Ordner/Liste) fest
        splitter.setStretchFactor(1, 1)  # Rechte Seite (Bild/Einstellungen) flexibel
        splitter.setSizes([250, 750])  # Feste Größen für bessere Responsivität

        cw = QWidget()
        main_layout = QVBoxLayout(cw)
        main_layout.addWidget(splitter)
        self.setCentralWidget(cw)

        self.set_defaults()

    def set_defaults(self):
        p = self.params
        self.top_spin.setValue(p.top_frac)
        self.bottom_spin.setValue(p.bottom_frac)
        self.left_spin.setValue(p.left_frac)
        self.right_spin.setValue(p.right_frac)
        self.min_area_spin.setValue(p.min_area_frac)
        self.max_area_spin.setValue(p.max_area_frac)
        self.min_asp_spin.setValue(p.min_aspect)
        self.max_asp_spin.setValue(p.max_aspect)
        self.pad_top_spin.setValue(p.padding_top)
        self.pad_bottom_spin.setValue(p.padding_bottom)
        self.pad_left_spin.setValue(p.padding_left)
        self.pad_right_spin.setValue(p.padding_right)
        # Tesseract-spezifische UI-Elemente entfernt - nur noch EasyOCR
        self.ocr_method_combo.setCurrentText(p.ocr_method)
        
        # Multi-Core UI-Elemente
        self.multicore_chk.setChecked(p.use_multicore)
        self.cores_spin.setValue(p.num_cores)

    # ---------- Connect ----------
    def _connect(self):
        self.browse_btn.clicked.connect(self.choose_folder)
        self.list_widget.currentRowChanged.connect(self.on_select_image)
        self.detect_btn.clicked.connect(self.on_detect)
        self.ocr_btn.clicked.connect(self.on_ocr_single)
        self.process_all_btn.clicked.connect(self.on_process_all)
        self.analyze_all_btn.clicked.connect(self.on_analyze_all)
        self.save_settings_btn.clicked.connect(self.on_save_settings)
        self.out_browse_btn.clicked.connect(self.choose_out_folder)
        # Tesseract-Browse-Button entfernt - nur noch EasyOCR

        for sb in (self.top_spin, self.bottom_spin, self.left_spin, self.right_spin,
                   self.min_area_spin, self.max_area_spin, self.min_asp_spin, self.max_asp_spin,
                   self.pad_top_spin, self.pad_bottom_spin, self.pad_left_spin, self.pad_right_spin):
            sb.valueChanged.connect(self.update_params)
        # Tesseract-spezifische Verbindungen entfernt - nur noch EasyOCR
        self.ocr_method_combo.currentTextChanged.connect(self.update_params)
        self.post_process_chk.toggled.connect(self.update_params)
        self.multicore_chk.toggled.connect(self.update_params)
        self.cores_spin.valueChanged.connect(self.update_params)

    def update_params(self):
        p = self.params
        p.top_frac = self.top_spin.value()
        p.bottom_frac = self.bottom_spin.value()
        p.left_frac = self.left_spin.value()
        p.right_frac = self.right_spin.value()
        p.min_area_frac = self.min_area_spin.value()
        p.max_area_frac = self.max_area_spin.value()
        p.min_aspect = self.min_asp_spin.value()
        p.max_aspect = self.max_asp_spin.value()
        p.padding_top = self.pad_top_spin.value()
        p.padding_bottom = self.pad_bottom_spin.value()
        p.padding_left = self.pad_left_spin.value()
        p.padding_right = self.pad_right_spin.value()
        # Tesseract-spezifische Parameter entfernt - nur noch EasyOCR
        p.ocr_method = self.ocr_method_combo.currentText()
        
        # Multi-Core Einstellungen
        p.use_multicore = self.multicore_chk.isChecked()
        p.num_cores = self.cores_spin.value()

        # Suchfenster neu zeichnen, falls Bild geladen
        if self.current_img_bgr is not None:
            H, W = self.current_img_bgr.shape[:2]
            x0 = int(W * p.left_frac)
            x1 = int(W * p.right_frac)
            y0 = int(H * p.top_frac)
            y1 = int(H * p.bottom_frac)
            self.current_search_rect = (x0, y0, x1-x0, y1-y0)
            self.viewer.set_rects(self.current_search_rect, self.current_box)
        
        # Einstellungen automatisch speichern
        self._save_config()

    # ---------- Datei & Anzeige ----------
    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Bilder-Ordner wählen")
        if folder:
            self.folder_edit.setText(folder)
            self.populate_list(Path(folder))
            self._save_config()  # Speichere sofort nach Auswahl
            self.log(f"Ordner gewählt: {folder}")

    def choose_out_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Ausgabeordner wählen")
        if folder:
            self.out_dir_edit.setText(folder)
            self._save_config()  # Speichere sofort nach Auswahl

    # choose_tesseract_path und update_tesseract_path entfernt - nur noch EasyOCR

    def populate_list(self, folder: Path):
        self.list_widget.clear()
        if not folder.exists():
            self.image_counter_label.setText("Bilder: 0")
            return
        # Case-insensitive Dateisuche ohne Duplikate
        imgs = []
        found_files = set()
        for p in folder.iterdir():
            if p.suffix.lower() in IMG_EXTS:
                found_files.add(p)  # Set verhindert Duplikate
        imgs = sorted(list(found_files))
        
        # Bildzähler aktualisieren
        self.image_counter_label.setText(f"Bilder: {len(imgs)}")
        
        for p in imgs:
            self.list_widget.addItem(str(p.name))
        if imgs:
            self.list_widget.setCurrentRow(0)

    def on_select_image(self, row: int):
        folder = Path(self.folder_edit.text())
        if row < 0 or not folder.exists():
            return
        name = self.list_widget.item(row).text()
        p = folder / name
        self.current_img_path = p
        img = cv2.imread(str(p))
        self.current_img_bgr = img
        self.current_box = None
        self.update_params()  # aktualisiert search_rect
        self.viewer.set_image(cv_to_qpix(img))
        self.viewer.set_rects(self.current_search_rect, None)

    # ---------- Erkennung & OCR ----------
    def on_detect(self):
        if self.current_img_bgr is None:
            self.log("Kein Bild geladen für Erkennung")
            return
        
        self.log("Starte Kasten-Erkennung mit EasyOCR")
        start_time = time.time()
        
        # Nur EasyOCR verwenden
        box, search_rect = find_text_box_easyocr(self.current_img_bgr, self.params)
        
        # Zeit messen
        detection_time = time.time() - start_time
        
        self.current_box = box
        self.current_search_rect = search_rect
        self.viewer.set_rects(self.current_search_rect, self.current_box)
        
        if box:
            self.log(f"Kasten gefunden: {box} (Dauer: {detection_time:.3f}s)")
        else:
            self.log(f"Kein Kasten erkannt (Dauer: {detection_time:.3f}s)")
        
        # Vorschau aktualisieren
        self.update_preview()

    def on_ocr_single(self):
        if self.current_img_bgr is None:
            self.log("Kein Bild geladen für OCR")
            return
        if self.current_box is None:
            self.log("Kein Kasten gefunden, starte Erkennung...")
            self.on_detect()
        if self.current_box is None:
            self.log("Kein Text-Bereich erkannt!")
            QMessageBox.warning(self, "Fehler", "Kein Text-Bereich erkannt!")
            return
        
        self.log("Starte OCR-Erkennung...")
        start_time = time.time()
        
        x,y,w,h = self.current_box
        crop = self.current_img_bgr[y:y+h, x:x+w]
        
        # Nur EasyOCR verwenden
        pre = crop  # Keine Vorverarbeitung für EasyOCR
        text = run_ocr(crop, self.params)  # Direkt das BGR-Bild
        
        # Zeit messen
        ocr_time = time.time() - start_time
        
        self.log(f"OCR-Ergebnis: '{text}' (Dauer: {ocr_time:.3f}s)")
        
        # Vorschau aktualisieren
        self.current_crop = crop
        self.current_preprocessed = pre
        self.update_preview()
        
        # Post-Processing Ersetzungen anzeigen
        post_process_enabled = self.post_process_chk.isChecked()
        processed_text, replacements = post_process_text(text, self.params, post_process_enabled)
        replacement_info = ""
        if replacements:
            replacement_info = f"\n\nErsetzungen:\n" + "\n".join(replacements)
        
        status_text = "Post-Processing: EIN" if post_process_enabled else "Post-Processing: AUS"
        QMessageBox.information(self, "OCR-Ergebnis", f"{status_text}\n\nOriginal: {text}\nKorrigiert: {processed_text}{replacement_info}")

    def on_save_settings(self):
        """Speichert die aktuellen Einstellungen manuell."""
        try:
            self._save_config()
            self.log("Einstellungen erfolgreich gespeichert")
            QMessageBox.information(self, "Einstellungen gespeichert", 
                                  "Alle aktuellen Einstellungen und Werte wurden gespeichert!")
        except Exception as e:
            self.log(f"Fehler beim Speichern: {e}")
            QMessageBox.warning(self, "Speicher-Fehler", f"Einstellungen konnten nicht gespeichert werden:\n{e}")

    def on_analyze_all(self):
        """Analysiert alle Bilder und erstellt eine Übersichtsliste mit Ausschnitten und Texten."""
        folder = Path(self.folder_edit.text())
        if not folder.exists():
            self.log("Kein gültiger Bilderordner gewählt")
            QMessageBox.warning(self, "Hinweis", "Bitte zuerst einen gültigen Bilderordner wählen.")
            return
        
        # Ausgabeordner
        out_dir = Path(self.out_dir_edit.text().strip()) if self.out_dir_edit.text().strip() else (folder / "out")
        out_dir.mkdir(exist_ok=True)
        
        # Alle Bilder finden (case-insensitive)
        imgs = []
        for ext in ("*.jpg", "*.jpeg", "*.png", "*.bmp", "*.tiff", "*.tif"):
            # Sammle alle Varianten (klein, groß, gemischt)
            found_files = set()
            for pattern in [ext, ext.upper(), ext.capitalize()]:
                for file_path in folder.glob(pattern):
                    found_files.add(file_path)  # Set verhindert Duplikate
            imgs.extend(found_files)
        
        if not imgs:
            self.log("Keine Bilder im Ordner gefunden")
            QMessageBox.warning(self, "Hinweis", "Keine Bilder im Ordner gefunden.")
            return
        
        # Timer starten
        analysis_start_time = time.time()
        self.log(f"Starte Analyse von {len(imgs)} Bildern...")
        
        # Multi-Core oder Single-Core Verarbeitung
        if self.params.use_multicore and len(imgs) > 1:
            self.log(f"Multi-Core-Verarbeitung mit {self.params.num_cores} Kernen")
            html_path = out_dir / "analyse_report.html"
            self._create_analysis_report_multicore(imgs, html_path)
        else:
            self.log("Single-Core-Verarbeitung")
            html_path = out_dir / "analyse_report.html"
            self._create_analysis_report(imgs, html_path)
        
        # Timer beenden und Zeit berechnen
        analysis_time = time.time() - analysis_start_time
        avg_time_per_image = analysis_time / len(imgs)
        
        self.hide_progress()
        self.log(f"Analyse abgeschlossen! Report: {html_path}")
        self.log(f"Gesamtzeit: {analysis_time:.2f}s | Durchschnitt: {avg_time_per_image:.3f}s pro Bild")
        QMessageBox.information(self, "Analyse abgeschlossen", 
                               f"Alle {len(imgs)} Bilder analysiert!\n\nGesamtzeit: {analysis_time:.2f}s\nDurchschnitt: {avg_time_per_image:.3f}s pro Bild\n\nReport gespeichert unter:\n{html_path}")

    def _create_analysis_report(self, imgs, html_path):
        """Erstellt einen HTML-Report mit allen analysierten Bildern."""
        html_content = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>OCR Analyse Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .image-row { display: flex; margin: 20px 0; padding: 10px; border: 1px solid #ddd; }
        .image-info { margin-left: 20px; }
        .crop-image { max-width: 200px; max-height: 100px; border: 2px solid #007bff; }
        .text-result { font-size: 18px; font-weight: bold; color: #007bff; }
        .time-info { color: #666; font-size: 12px; }
        .filename { font-weight: bold; color: #333; }
        .error { color: #dc3545; }
    </style>
</head>
<body>
    <h1>OCR Analyse Report</h1>
    <p>Generiert am: """ + time.strftime("%d.%m.%Y %H:%M:%S") + """</p>
"""
        
        total_start_time = time.time()
        
        # Fortschrittsbalken initialisieren
        self.set_progress(0, len(imgs), "Analysiere Bilder")
        
        for i, img_path in enumerate(imgs):
            start_time = time.time()
            
            # Fortschritt aktualisieren
            self.set_progress(i, len(imgs), f"Verarbeite {img_path.name}")
            self.log(f"Verarbeite Bild {i+1}/{len(imgs)}: {img_path.name}")
            
            try:
                # Bild laden
                img = cv2.imread(str(img_path))
                if img is None:
                    continue
                
                # OCR ausführen (nur EasyOCR)
                box, _ = find_text_box_easyocr(img, self.params)
                
                if box is None:
                    # Kein Text gefunden
                    crop_img = None
                    text = "[Kein Text erkannt]"
                    crop_path = ""
                else:
                    # Text-Bereich ausschneiden
                    x, y, w, h = box
                    crop_img = img[y:y+h, x:x+w]
                    
                    # OCR-Text erkennen (nur EasyOCR)
                    raw_text = run_ocr(crop_img, self.params)
                    # Post-Processing anwenden
                    post_process_enabled = self.post_process_chk.isChecked()
                    text, replacements = post_process_text(raw_text, self.params, post_process_enabled)
                    
                    # Crop speichern
                    crop_filename = f"crop_{img_path.stem}.jpg"
                    crop_path = f"crops/{crop_filename}"
                    crop_dir = html_path.parent / "crops"
                    crop_dir.mkdir(exist_ok=True)
                    cv2.imwrite(str(crop_dir / crop_filename), crop_img)
                
                # Zeit messen
                processing_time = time.time() - start_time
                
                # HTML-Zeile hinzufügen
                if crop_img is not None:
                    crop_img_html = f'<img src="{crop_path}" class="crop-image" alt="Crop">'
                else:
                    crop_img_html = '<div class="crop-image" style="background: #f0f0f0; display: flex; align-items: center; justify-content: center;">Kein Crop</div>'
                
                html_content += f"""
    <div class="image-row">
        {crop_img_html}
        <div class="image-info">
            <div class="filename">{img_path.name}</div>
            <div class="text-result">{text}</div>
            <div class="time-info">Verarbeitungszeit: {processing_time:.3f}s</div>
        </div>
    </div>
"""
                
            except Exception as e:
                processing_time = time.time() - start_time
                self.log(f"Fehler bei {img_path.name}: {str(e)}")
                html_content += f"""
    <div class="image-row">
        <div class="crop-image" style="background: #f0f0f0; display: flex; align-items: center; justify-content: center;">Fehler</div>
        <div class="image-info">
            <div class="filename">{img_path.name}</div>
            <div class="text-result error">Fehler: {str(e)}</div>
            <div class="time-info">Verarbeitungszeit: {processing_time:.3f}s</div>
        </div>
    </div>
"""
        
        total_time = time.time() - total_start_time
        
        html_content += f"""
    <hr>
    <p><strong>Gesamtzeit:</strong> {total_time:.3f}s für {len(imgs)} Bilder</p>
    <p><strong>Durchschnitt:</strong> {total_time/len(imgs):.3f}s pro Bild</p>
</body>
</html>
"""
        
        # HTML-Datei speichern
        with html_path.open("w", encoding="utf-8") as f:
            f.write(html_content)
        
        # Finaler Fortschritt
        self.set_progress(len(imgs), len(imgs), "Report erstellt")
        self.log(f"HTML-Report erstellt: {html_path}")
        
        # HTML-Report automatisch öffnen
        try:
            import webbrowser
            webbrowser.open(f"file://{html_path.absolute()}")
            self.log("HTML-Report automatisch geöffnet")
        except Exception as e:
            self.log(f"Fehler beim Öffnen des Reports: {e}")
            QMessageBox.information(self, "Report erstellt", 
                                  f"HTML-Report erstellt:\n{html_path}\n\nBitte manuell öffnen.")

    def _create_analysis_report_multicore(self, imgs, html_path):
        """Erstellt HTML-Report mit Multi-Core-Verarbeitung."""
        self.set_progress(0, len(imgs), "Multi-Core-Verarbeitung...")
        
        # Parameter für Multi-Core-Verarbeitung vorbereiten
        params_dict = {
            'top_frac': self.params.top_frac,
            'bottom_frac': self.params.bottom_frac,
            'left_frac': self.params.left_frac,
            'right_frac': self.params.right_frac,
            'min_area_frac': self.params.min_area_frac,
            'max_area_frac': self.params.max_area_frac,
            'min_aspect': self.params.min_aspect,
            'max_aspect': self.params.max_aspect,
            'padding_top': self.params.padding_top,
            'padding_bottom': self.params.padding_bottom,
            'padding_left': self.params.padding_left,
            'padding_right': self.params.padding_right,
            'ocr_method': self.params.ocr_method,
        }
        
        # Crop-Verzeichnis erstellen
        crop_dir = html_path.parent / "crops"
        crop_dir.mkdir(exist_ok=True)
        
        # Multi-Core-Verarbeitung
        results = []
        completed = 0
        
        with ProcessPoolExecutor(max_workers=self.params.num_cores) as executor:
            # Alle Aufgaben starten
            futures = []
            for img_path in imgs:
                args = (img_path, params_dict, self.save_parts_chk.isChecked())
                future = executor.submit(process_single_image, args)
                futures.append((future, img_path))
            
            # Ergebnisse sammeln
            for future, img_path in futures:
                try:
                    result = future.result(timeout=300)  # 5 Minuten Timeout
                    results.append(result)
                    completed += 1
                    self.set_progress(completed, len(imgs), f"Verarbeitet: {img_path.name}")
                    self.log(f"Verarbeitet ({completed}/{len(imgs)}): {img_path.name}")
                except Exception as e:
                    self.log(f"Fehler bei {img_path.name}: {e}")
                    results.append((img_path, None, f"[Fehler: {e}]", "", 0.0))
                    completed += 1
                    self.set_progress(completed, len(imgs), f"Fehler: {img_path.name}")
        
        # Ergebnisse nach Bildnummer sortieren
        results.sort(key=lambda x: x[0].name)
        
        # HTML-Report erstellen
        self._generate_html_report(results, html_path, crop_dir)
        
        # Finaler Fortschritt
        self.set_progress(len(imgs), len(imgs), "Multi-Core Report erstellt")
        self.log(f"Multi-Core HTML-Report erstellt: {html_path}")
        
        # HTML-Report automatisch öffnen
        try:
            import webbrowser
            webbrowser.open(f"file://{html_path.absolute()}")
            self.log("HTML-Report automatisch geöffnet")
        except Exception as e:
            self.log(f"Fehler beim Öffnen des Reports: {e}")

    def _generate_html_report(self, results, html_path, crop_dir):
        """Generiert den HTML-Report aus den Ergebnissen."""
        total_time = sum(result[4] for result in results if len(result) > 4)
        avg_time = total_time / len(results) if results else 0
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>OCR Analyse Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background-color: #f0f0f0; padding: 20px; border-radius: 5px; }}
                .image-row {{ margin: 20px 0; padding: 10px; border: 1px solid #ddd; border-radius: 5px; }}
                .image-info {{ font-weight: bold; color: #333; }}
                .crop-image {{ max-width: 200px; max-height: 100px; margin: 10px 0; }}
                .text-result {{ font-family: monospace; font-size: 14px; color: #0066cc; }}
                .time-info {{ color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>OCR Analyse Report</h1>
                <p>Verarbeitete Bilder: {len(results)}</p>
                <p>Gesamtzeit: {total_time:.2f} Sekunden</p>
                <p>Durchschnittszeit: {avg_time:.2f} Sekunden pro Bild</p>
            </div>
        """
        
        for i, result in enumerate(results):
            if len(result) >= 5:
                img_path, crop_img, text, crop_path, processing_time = result
            else:
                img_path, crop_img, text, crop_path, processing_time = result[0], None, result[2], "", 0.0
            
            # Crop-Bild speichern falls vorhanden
            if crop_img is not None and self.save_parts_chk.isChecked():
                crop_filename = f"crop_{img_path.stem}.jpg"
                cv2.imwrite(str(crop_dir / crop_filename), crop_img)
                crop_path = f"crops/{crop_filename}"
            
            html_content += f"""
            <div class="image-row">
                <div class="image-info">{img_path.name}</div>
                <div class="text-result">Erkannt: {text}</div>
                <div class="time-info">Verarbeitungszeit: {processing_time:.2f}s</div>
                {f'<img src="{crop_path}" class="crop-image" alt="Crop">' if crop_path else '<p>Kein Crop verfügbar</p>'}
            </div>
            """
        
        html_content += """
        </body>
        </html>
        """
        
        # HTML-Datei speichern
        with html_path.open("w", encoding="utf-8") as f:
            f.write(html_content)

    def on_process_all(self):
        folder = Path(self.folder_edit.text())
        if not folder.exists():
            QMessageBox.warning(self, "Hinweis", "Bitte zuerst einen gültigen Bilderordner wählen.")
            return
        out_dir = Path(self.out_dir_edit.text().strip()) if self.out_dir_edit.text().strip() else (folder / "out")
        out_dir.mkdir(exist_ok=True, parents=True)

        imgs = [p for p in sorted(folder.iterdir()) if p.suffix.lower() in IMG_EXTS]
        if not imgs:
            QMessageBox.information(self, "Info", "Keine Bilder gefunden.")
            return

        # Timer starten
        process_start_time = time.time()
        self.log(f"Starte Verarbeitung von {len(imgs)} Bildern...")

        csv_path = out_dir / "ocr_results.csv"
        with csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(["file","x","y","w","h","text"])

            for p in imgs:
                img = cv2.imread(str(p))
                if img is None:
                    continue
                
                # EasyOCR oder alte Methode verwenden
                # Nur EasyOCR verwenden
                box, _ = find_text_box_easyocr(img, self.params)
                
                if box is None:
                    continue
                    
                x,y,w,h = box
                crop = img[y:y+h, x:x+w]
                
                # Nur EasyOCR verwenden
                pre = crop  # Keine Vorverarbeitung für EasyOCR
                raw_text = run_ocr(crop, self.params)  # Direkt das BGR-Bild
                # Post-Processing anwenden
                post_process_enabled = self.post_process_chk.isChecked()
                text, replacements = post_process_text(raw_text, self.params, post_process_enabled)

                if self.save_parts_chk.isChecked():
                    vis = img.copy()
                    cv2.rectangle(vis, (x,y), (x+w, y+h), (0,255,0), 2)
                    cv2.imwrite(str(out_dir / f"{p.stem}_boxed.jpg"), vis)
                    cv2.imwrite(str(out_dir / f"{p.stem}_roi.jpg"), crop)
                    cv2.imwrite(str(out_dir / f"{p.stem}_roi_pre_ocr.png"), pre)

                writer.writerow([p.name, x, y, w, h, text])

        # Timer beenden und Zeit berechnen
        process_time = time.time() - process_start_time
        avg_time_per_image = process_time / len(imgs)
        
        self.log(f"Verarbeitung abgeschlossen! CSV: {csv_path}")
        self.log(f"Gesamtzeit: {process_time:.2f}s | Durchschnitt: {avg_time_per_image:.3f}s pro Bild")
        QMessageBox.information(self, "Fertig", f"Verarbeitung abgeschlossen.\n\nGesamtzeit: {process_time:.2f}s\nDurchschnitt: {avg_time_per_image:.3f}s pro Bild\n\nCSV: {csv_path}")

    def update_preview(self):
        """Aktualisiert die Vorschau-Bilder."""
        if self.current_preprocessed is not None:
            # Preprocessed-Vorschau (Graustufen)
            if len(self.current_preprocessed.shape) == 2:  # Graustufen
                preprocessed_rgb = cv2.cvtColor(self.current_preprocessed, cv2.COLOR_GRAY2RGB)
            else:
                preprocessed_rgb = self.current_preprocessed
            preprocessed_pixmap = cv_to_qpix(preprocessed_rgb)
            # Skaliere für Vorschau
            scaled_preprocessed = preprocessed_pixmap.scaled(200, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.preprocessed_preview.setPixmap(scaled_preprocessed)
        else:
            self.preprocessed_preview.setText("Kein Preprocessed")

    # ---------- Konfiguration ----------
    def _save_config(self):
        """Speichert aktuelle Einstellungen in Konfigurationsdatei."""
        config = {
            "last_folder": self.folder_edit.text(),
            "last_out_folder": self.out_dir_edit.text(),
            # tesseract_path entfernt - nur noch EasyOCR
            "params": {
                "top_frac": self.params.top_frac,
                "bottom_frac": self.params.bottom_frac,
                "left_frac": self.params.left_frac,
                "right_frac": self.params.right_frac,
                "min_area_frac": self.params.min_area_frac,
                "max_area_frac": self.params.max_area_frac,
                "min_aspect": self.params.min_aspect,
                "max_aspect": self.params.max_aspect,
                "padding_top": self.params.padding_top,
                "padding_bottom": self.params.padding_bottom,
                "padding_left": self.params.padding_left,
                "padding_right": self.params.padding_right,
                # Tesseract-spezifische Parameter entfernt - nur noch EasyOCR
                "ocr_method": self.params.ocr_method,
                "use_multicore": self.params.use_multicore,
                "num_cores": self.params.num_cores,
            },
            "save_parts": self.save_parts_chk.isChecked(),
        }
        try:
            with CONFIG_FILE.open("w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Konfiguration konnte nicht gespeichert werden: {e}")

    def _load_config(self):
        """Lädt gespeicherte Einstellungen aus Konfigurationsdatei."""
        if not CONFIG_FILE.exists():
            return
        
        try:
            with CONFIG_FILE.open("r", encoding="utf-8") as f:
                config = json.load(f)
            
            # Letzten Ordner laden
            if "last_folder" in config and config["last_folder"]:
                folder_path = Path(config["last_folder"])
                if folder_path.exists():
                    self.folder_edit.setText(config["last_folder"])
                    self.populate_list(folder_path)
            
            # Letzten Ausgabeordner laden
            if "last_out_folder" in config and config["last_out_folder"]:
                self.out_dir_edit.setText(config["last_out_folder"])
            
            # Tesseract-Pfad laden
            # tesseract_path entfernt - nur noch EasyOCR
            
            # Parameter laden
            if "params" in config:
                params = config["params"]
                self.params.top_frac = params.get("top_frac", self.params.top_frac)
                self.params.bottom_frac = params.get("bottom_frac", self.params.bottom_frac)
                self.params.left_frac = params.get("left_frac", self.params.left_frac)
                self.params.right_frac = params.get("right_frac", self.params.right_frac)
                self.params.min_area_frac = params.get("min_area_frac", self.params.min_area_frac)
                self.params.max_area_frac = params.get("max_area_frac", self.params.max_area_frac)
                self.params.min_aspect = params.get("min_aspect", self.params.min_aspect)
                self.params.max_aspect = params.get("max_aspect", self.params.max_aspect)
                self.params.padding_top = params.get("padding_top", self.params.padding_top)
                self.params.padding_bottom = params.get("padding_bottom", self.params.padding_bottom)
                self.params.padding_left = params.get("padding_left", self.params.padding_left)
                self.params.padding_right = params.get("padding_right", self.params.padding_right)
                # Tesseract-spezifische Parameter entfernt - nur noch EasyOCR
                self.params.ocr_method = params.get("ocr_method", self.params.ocr_method)
                self.params.use_multicore = params.get("use_multicore", self.params.use_multicore)
                self.params.num_cores = params.get("num_cores", self.params.num_cores)
                
                # UI aktualisieren
                self.set_defaults()
            
            # Checkbox laden
            if "save_parts" in config:
                self.save_parts_chk.setChecked(config["save_parts"])
                
        except Exception as e:
            print(f"Konfiguration konnte nicht geladen werden: {e}")

    def closeEvent(self, event):
        """Speichert Konfiguration beim Schließen der Anwendung."""
        self._save_config()
        event.accept()

# ------------------- main -------------------

def main():
    app = QApplication(sys.argv)
    w = MainWindow()
    w.resize(QSize(1200, 800))
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
