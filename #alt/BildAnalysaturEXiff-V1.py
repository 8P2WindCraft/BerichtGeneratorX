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
import traceback
import numpy as np
import pandas as pd
import unicodedata
import threading
import time
import sys
import pytesseract

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

# Neue verbesserte OCR-Klasse
class ImprovedOCR:
    def __init__(self, valid_kurzel):
        self.valid_kurzel = valid_kurzel
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
def old_ocr_method(image_path, valid_kurzel):
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
def enhanced_old_method(image_path, valid_kurzel):
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
                
                # 4. Fuzzy Matching mit verschiedenen Cutoffs
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
class CentralConfigManager:
    """Zentrale Verwaltung aller Programm-Einstellungen"""
    
    def __init__(self):
        self.config_file = JSON_CONFIG_FILE
        self.config = self.load_config()
        
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
                "fallback_enabled": True
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
            
            # Bildqualitäts-Optionen (mehrsprachig)
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
                            # Versuche JSON zu parsen
                            parsed_data = json.loads(user_comment.decode('utf-8') if isinstance(user_comment, bytes) else user_comment)
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
            
            # Konvertiere JSON zu String
            json_string = json.dumps(json_data, ensure_ascii=False)
            
            # Finde den UserComment-Tag-ID
            usercomment_tag_id = None
            for tag_id, tag_name in ExifTags.TAGS.items():
                if tag_name == 'UserComment':
                    usercomment_tag_id = tag_id
                    break
            
            if usercomment_tag_id is None:
                # Fallback: verwende einen bekannten Tag-ID für UserComment
                usercomment_tag_id = 37510
            
            exif[usercomment_tag_id] = json_string
            
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
        self.geometry("1080x800")
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
        self.config = config_manager
        self.json_config = self.config.config
        
        # Lade gespeicherte Sprache oder verwende Standard (Englisch)
        saved_language = self.config.get_setting('localization.current_language', 'en')
        if 'localization' not in self.json_config:
            self.json_config['localization'] = {}
        self.json_config['localization']['current_language'] = saved_language
        write_detailed_log("info", "Sprache geladen", f"Sprache: {saved_language}")
        
        # Fenster-Einstellungen aus Konfiguration
        window_width = self.config.get_setting('display.window_width', 1080)
        window_height = self.config.get_setting('display.window_height', 800)
        window_x = self.config.get_setting('display.window_x')
        window_y = self.config.get_setting('display.window_y')
        
        if window_x is not None and window_y is not None:
            self.geometry(f"{window_width}x{window_height}+{window_x}+{window_y}")
        else:
            self.geometry(f"{window_width}x{window_height}")
        
        # Lade gültige Kürzel
        self.valid_kurzel = self.config.get_setting('valid_kurzel', [])

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
        self._damage_save_timer = None
        self._damage_text_changed = False

        write_detailed_log("info", "Anwendung gestartet", f"Fenster-Größe: 1080x800, Gültige Codes: {len(self.valid_kurzel)}")
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
            self.config.update_valid_kurzel(codes)
            
            # Aktualisiere OCR-Klasse falls vorhanden
            if hasattr(self, 'improved_ocr'):
                self.improved_ocr.update_valid_kurzel(codes)
                write_detailed_log("info", "OCR-Klasse mit neuen Codes aktualisiert")
            
            write_detailed_log("info", "Code-Liste aktualisiert", f"Datei: {CODE_FILE}, Anzahl: {len(codes)}")
            messagebox.showinfo("Gespeichert", "Code-Liste aktualisiert und OCR optimiert.")
        except Exception as e:
            write_detailed_log("error", "Fehler beim Speichern der Codes", f"Datei: {CODE_FILE}", e)
            messagebox.showerror("Fehler", f"Fehler beim Speichern der Codes: {e}")

    def create_widgets(self):
        """Erstellt die Benutzeroberfläche"""
        print("Starte create_widgets")
        
        # Status Variable initialisieren
        self.status_var = tk.StringVar(value="Bereit")
        
        # 1. Top Frame mit Buttons
        top_frame = ttk.Frame(self)
        top_frame.pack(fill=tk.X, pady=(0, 5))
        
        # Linke Buttons
        left_buttons = ttk.Frame(top_frame)
        left_buttons.pack(side=tk.LEFT)
        
        ttk.Button(left_buttons, text="Ordner öffnen", command=self.open_folder).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(left_buttons, text="Excel Grunddaten laden", command=self.load_excel_project_data).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(left_buttons, text="Analysieren", command=self.auto_analyze).pack(side=tk.LEFT, padx=(0, 5))
        
        # Fortschrittsbalken (wird nur bei Analyse eingeblendet)
        self.pbar = ttk.Progressbar(left_buttons, length=150, mode='determinate')
        # self.pbar.pack(side=tk.LEFT, padx=(0, 5))  # Wird nur bei Analyse eingeblendet
        
        # Ordner Label
        self.label_folder = ttk.Label(left_buttons, text="Kein Ordner ausgewählt")
        self.label_folder.pack(side=tk.LEFT, padx=(10, 0))
        
        # Rechte Buttons
        self.right_buttons = ttk.Frame(top_frame)
        self.right_buttons.pack(side=tk.RIGHT)
        
        ttk.Button(self.right_buttons, text="OCR Log", command=self.show_ocr_log).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(self.right_buttons, text="Log", command=self.show_detailed_log).pack(side=tk.RIGHT, padx=(5, 0))
        ttk.Button(self.right_buttons, text="Einstellungen", command=self.open_config_editor).pack(side=tk.RIGHT, padx=(5, 0))
        
        # 3. Main Content Area (3 Spalten)
        content_frame = ttk.Frame(self)
        content_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # Konfiguriere die Spaltengewichte
        content_frame.grid_columnconfigure(0, weight=11)  # 55%
        content_frame.grid_columnconfigure(1, weight=4)   # 20%
        content_frame.grid_columnconfigure(2, weight=5)   # 25%
        
        # Linke Spalte (55%) - Bild und Navigation
        left_column = ttk.Frame(content_frame)
        left_column.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        
        # 2. Grunddaten Frame - jetzt in der left_column über dem Bild
        self.grunddaten_frame = ttk.LabelFrame(left_column, text="Excel Grunddaten", padding=5)
        # self.grunddaten_frame.pack(fill=tk.X, pady=(0, 5))  # Initial versteckt
        
        # Combo Frame für Zeilenauswahl
        combo_frame = ttk.Frame(self.grunddaten_frame)
        combo_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(combo_frame, text="Zeile auswählen:").pack(side=tk.LEFT)
        self.excel_row_combo = ttk.Combobox(combo_frame, state="readonly", width=50)
        self.excel_row_combo.pack(side=tk.LEFT, padx=(5, 0))
        self.excel_row_combo.bind("<<ComboboxSelected>>", self.on_excel_row_selected)
        
        # Fields Frame für Grid-Layout
        self.fields_frame = ttk.Frame(self.grunddaten_frame)
        self.fields_frame.pack(fill=tk.X)
        self.grunddaten_fields = {}
        
        # Bildinformationen über dem Bild
        image_info_frame = ttk.Frame(left_column)
        image_info_frame.pack(fill=tk.X, pady=(0, 5))
        
        # OCR-Tag Label (immer sichtbar)
        self.ocr_tag_var = tk.StringVar(value="OCR-Tag: -")
        self.ocr_tag_label = ttk.Label(image_info_frame, textvariable=self.ocr_tag_var, font=("TkDefaultFont", 12, "bold"), foreground="#0077cc")
        self.ocr_tag_label.pack(side=tk.RIGHT, padx=(0, 10))
        
        # Bild-Zähler (Bild X von Y) - anfangs ausgeblendet
        self.image_counter_var = tk.StringVar(value="Bild 0 von 0")
        self.image_counter_label = ttk.Label(image_info_frame, textvariable=self.image_counter_var, font=("TkDefaultFont", 12, "bold"))
        # self.image_counter_label.pack(side=tk.LEFT)  # Wird nur bei Analyse eingeblendet
        
        # Dateiname - anfangs ausgeblendet
        self.filename_var = tk.StringVar(value="Keine Datei geladen")
        self.filename_label = ttk.Label(image_info_frame, textvariable=self.filename_var, font=("TkDefaultFont", 10))
        # self.filename_label.pack(side=tk.RIGHT)  # Wird nur bei Analyse eingeblendet
        
        # Canvas für Bild
        self.canvas = tk.Canvas(left_column, bg='#f0f0f0', relief=tk.SUNKEN, bd=1)
        self.canvas.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        # Navigation Controls direkt unter dem Bild
        nav_frame = ttk.Frame(left_column)
        nav_frame.pack(fill=tk.X, pady=(0, 5))
        
        # Navigation mittig anordnen
        nav_center_frame = ttk.Frame(nav_frame)
        nav_center_frame.pack(expand=True)
        
        # Vorher Button
        ttk.Button(nav_center_frame, text="◀ Vorher", command=self.prev_image, width=12).pack(side=tk.LEFT, padx=(0, 10))
        
        # Zoom Button
        ttk.Button(nav_center_frame, text="Zoom & Markieren", command=self.open_zoom_window).pack(side=tk.LEFT, padx=(0, 10))
        
        # Korrekt Dropdown
        ttk.Label(nav_center_frame, text="Korrekt:").pack(side=tk.LEFT, padx=(0, 2))
        self.correct_var = tk.StringVar()
        self.correct_combo = ttk.Combobox(nav_center_frame, values=self.valid_kurzel, textvariable=self.correct_var, width=10)
        self.correct_combo.pack(side=tk.LEFT, padx=(0, 10))
        self.correct_combo.bind("<<ComboboxSelected>>", self.on_correct_changed)
        
        # Nächste Button
        ttk.Button(nav_center_frame, text="Nächste ▶", command=self.next_image, width=12).pack(side=tk.LEFT)
        
        # Tastatur-Navigation binden
        self.bind('<Left>', lambda e: self.prev_image())
        self.bind('<Right>', lambda e: self.next_image())

        # Damage Description direkt unter der Navigation
        desc_frame = ttk.LabelFrame(left_column, text="Damage Description", padding=5)
        desc_frame.pack(fill=tk.X, pady=(0, 5))
        self.damage_description_text = tk.Text(desc_frame, height=4, font=("TkDefaultFont", 12), wrap=tk.WORD)
        self.damage_description_text.pack(fill=tk.X, pady=2)
        
        # Binding für automatisches Speichern
        self.damage_description_text.bind('<KeyRelease>', self.on_damage_description_change)

        # Status und Progress
        status_frame = ttk.Frame(left_column)
        status_frame.pack(fill=tk.X)
        
        ttk.Label(status_frame, textvariable=self.status_var).pack(side=tk.LEFT)
        
        # Mittlere Spalte (20%) - Bewertung
        center_column = ttk.Frame(content_frame)
        center_column.grid(row=0, column=1, sticky="nsew", padx=5)
        
        # Einheitliche große Schrift für alle Buttons
        einheits_font = ("TkDefaultFont", 12, "bold")
        
        # Bild verwenden
        use_frame = ttk.LabelFrame(center_column, text="Bild verwenden", padding=5)
        use_frame.pack(fill=tk.X, pady=(0, 5))
        # Setze Standardwert für "Bild verwenden" basierend auf aktueller Sprache
        current_options = self.config.get_language_specific_list('use_image_options')
        default_use_image = current_options[0] if current_options else "ja"
        self.use_image_var = tk.StringVar(value=default_use_image)
        for option in self.config.get_language_specific_list('use_image_options'):
            tk.Radiobutton(use_frame, text=option, variable=self.use_image_var, 
                           value=option, command=self.save_current_evaluation, font=einheits_font).pack(anchor=tk.W)
        
        # Schadenskategorien
        damage_frame = ttk.LabelFrame(center_column, text="Schadenskategorien", padding=5)
        damage_frame.pack(fill=tk.X, pady=(0, 5))
        self.damage_vars = {}
        for category in self.config.get_language_specific_list('damage_categories'):
            var = tk.BooleanVar()
            self.damage_vars[category] = var
            tk.Checkbutton(damage_frame, text=category, variable=var, 
                           command=self.save_current_evaluation, font=einheits_font).pack(anchor=tk.W)
        
        # Bildart-Kategorien
        image_type_frame = ttk.LabelFrame(center_column, text="Bildart-Kategorien", padding=5)
        image_type_frame.pack(fill=tk.X, pady=(0, 5))
        self.image_type_vars = {}
        for img_type in self.config.get_language_specific_list('image_types'):
            var = tk.BooleanVar()
            self.image_type_vars[img_type] = var
            tk.Checkbutton(image_type_frame, text=img_type, variable=var, 
                           command=self.save_current_evaluation, font=einheits_font).pack(anchor=tk.W)
        
        # Bildqualitäts-Bewertung
        quality_frame = ttk.LabelFrame(center_column, text="Bildqualität", padding=5)
        quality_frame.pack(fill=tk.X)
        self.image_quality_var = tk.StringVar(value="Unknown")
        for option in self.config.get_language_specific_list('image_quality_options'):
            tk.Radiobutton(quality_frame, text=option, variable=self.image_quality_var, 
                           value=option, command=self.save_current_evaluation, font=einheits_font).pack(anchor=tk.W)
        
        # Rechte Spalte (25%) - Statistik
        right_column = ttk.Frame(content_frame)
        right_column.grid(row=0, column=2, sticky="nsew", padx=(5, 0))
        
        counts_frame = ttk.LabelFrame(right_column, text="Anzahl", padding=5)
        counts_frame.pack(fill=tk.BOTH, expand=True)
        
        # Bewertungsfortschritt
        progress_frame = ttk.Frame(counts_frame)
        progress_frame.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(progress_frame, text="Bewertungsfortschritt:").pack(anchor=tk.W)
        self.evaluation_progress = ttk.Progressbar(progress_frame, mode='determinate')
        self.evaluation_progress.pack(fill=tk.X, pady=(2, 0))
        
        self.evaluation_progress_label = ttk.Label(progress_frame, text="0/0 bewertet")
        self.evaluation_progress_label.pack(anchor=tk.W)
        
        # Filter Checkbox mit größerer Schrift
        filter_value = self.json_config.get('filter_zero_codes', True)  # Standardmäßig True
        self.filter_zero_var = tk.BooleanVar(value=filter_value)
        ttk.Checkbutton(counts_frame, text="Nur Codes mit Anzahl > 0 anzeigen", 
                       variable=self.filter_zero_var, command=self.update_code_listbox).pack(anchor=tk.W, pady=(5, 5))
        
        # Listbox für Codes und Zähler mit größerer Schrift
        self.code_listbox = tk.Listbox(counts_frame, height=25, font=("TkDefaultFont", 12))
        self.code_listbox.pack(fill=tk.BOTH, expand=True)
        self.code_listbox.bind('<<ListboxSelect>>', self.on_code_select)
        self.update_code_listbox()
        
        # Button zum Zurücksetzen der Bewertungen
        ttk.Button(counts_frame, text="Alle Bewertungen zurücksetzen", command=self.reset_all_image_evaluations).pack(fill=tk.X, pady=(10, 0))
        
        print("Fertig mit create_widgets")

    def invalidate_evaluation_cache(self):
        """Markiert den Cache als veraltet"""
        self._cache_dirty = True
        self._evaluation_cache.clear()
        self._tag_evaluation_cache.clear()

    def is_image_evaluated(self, exif_data):
        """Prüft, ob ein Bild als bewertet gilt"""
        if not exif_data:
            return False
            
        # Prüfe "Bild verwenden"
        use_image = exif_data.get('use_image', '')
        if use_image == 'nein':
            return True
            
        # Prüfe Schadenskategorien
        damage_categories = exif_data.get('damage_categories', [])
        
        # Wenn "Visually no defects" in Schadenskategorien ist
        if 'Visually no defects' in damage_categories:
            return True
            
        # Mindestens eine Schadenskategorie UND mindestens eine Bildart-Kategorie
        image_types = exif_data.get('image_types', [])
        return len(damage_categories) > 0 and len(image_types) > 0

    def build_evaluation_cache(self):
        """Baut den Cache für Bewertungsdaten auf"""
        if not self._cache_dirty or not self.files:
            return
            
        self._evaluation_cache.clear()
        self._tag_evaluation_cache.clear()
        
        # Sammle alle Tags und ihre Bilder
        tag_images = {}
        
        for filename in self.files:
            try:
                filepath = os.path.join(self.source_dir, filename)
                exif_data = get_exif_usercomment(filepath)
                
                # Cache Bewertung für dieses Bild
                is_evaluated = self.is_image_evaluated(exif_data)
                self._evaluation_cache[filename] = is_evaluated
                
                # Sammle Bilder pro Tag
                if exif_data and "TAGOCR" in exif_data:
                    tag = exif_data["TAGOCR"]
                    if tag not in tag_images:
                        tag_images[tag] = []
                    tag_images[tag].append(filename)
                    
            except Exception as e:
                print(f"Fehler beim Cache-Aufbau für {filename}: {e}")
                self._evaluation_cache[filename] = False
        
        # Prüfe vollständige Bewertung für jeden Tag
        for tag, images in tag_images.items():
            if not images:
                continue
            # Tag ist vollständig bewertet, wenn alle Bilder des Tags bewertet sind
            self._tag_evaluation_cache[tag] = all(self._evaluation_cache.get(img, False) for img in images)
        
        self._cache_dirty = False

    def update_evaluation_progress(self):
        """Aktualisiert den Bewertungsfortschritt (optimiert mit Cache)"""
        if not self.files:
            self.evaluation_progress['value'] = 0
            self.evaluation_progress['maximum'] = 0
            self.evaluation_progress_label.config(text="0/0 bewertet")
            return
        
        # Baue Cache auf, falls nötig
        self.build_evaluation_cache()
        
        total_images = len(self.files)
        evaluated_count = sum(1 for is_evaluated in self._evaluation_cache.values() if is_evaluated)
        
        self.evaluation_progress['maximum'] = total_images
        self.evaluation_progress['value'] = evaluated_count
        self.evaluation_progress_label.config(text=f"{evaluated_count}/{total_images} bewertet")

    def is_tag_fully_evaluated(self, tag):
        """Prüft, ob alle Bilder eines bestimmten Tags bewertet sind (optimiert mit Cache)"""
        # Baue Cache auf, falls nötig
        self.build_evaluation_cache()
        
        return self._tag_evaluation_cache.get(tag, False)

    def update_code_listbox(self):
        """Aktualisiert die Listbox mit den aktuellen Zählerwerten (optimiert)"""
        self.code_listbox.delete(0, tk.END)
        
        # Bestimme den aktuellen Code des angezeigten Bildes
        current_code = None
        if self.files and 0 <= self.index < len(self.files):
            try:
                current_file = self.files[self.index]
                filepath = os.path.join(self.source_dir, current_file)
                exif_data = get_exif_usercomment(filepath)
                if exif_data and "TAGOCR" in exif_data:
                    current_code = exif_data["TAGOCR"]
            except Exception as e:
                print(f"Fehler beim Bestimmen des aktuellen Codes: {e}")
        
        for code in self.valid_kurzel:
            count = self.counter.get(code, 0)
            if not self.filter_zero_var.get() or count != 0:
                label = f"{code} ({count})"
                self.code_listbox.insert(tk.END, label)
                
                idx = self.code_listbox.size() - 1
                
                # Prüfe, ob alle Bilder dieses Tags bewertet sind (mit Cache)
                if count > 0 and self.is_tag_fully_evaluated(code):
                    # Setze Hintergrundfarbe auf Grün für vollständig bewertete Tags
                    self.code_listbox.itemconfig(idx, {'bg': 'lightgreen'})
                
                # Markiere das aktuelle Bild hellblau
                if code == current_code:
                    self.code_listbox.itemconfig(idx, {'bg': 'lightblue'})
                    # Stelle sicher, dass der Eintrag sichtbar ist
                    self.code_listbox.see(idx)

    def on_code_select(self, event):
        selection = self.code_listbox.curselection()
        if not selection:
            return
        label = self.code_listbox.get(selection[0])
        code = label.split(' ')[0]
        indices = []
        for i, f in enumerate(self.files):
            try:
                exif = get_exif_usercomment(os.path.join(self.source_dir, f))
                if exif and exif.get('TAGOCR') == code:
                    indices.append(i)
            except Exception as e:
                print(f"Fehler beim Listbox-EXIF-Check: {e}")
        if indices:
            self.index = indices[0]
            self.show_image()

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
                self.update_code_listbox()
                
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
            current_options = self.config.get_language_specific_list('use_image_options')
            default_use_image = current_options[0] if current_options else "ja"
            self.use_image_var.set(default_use_image)
            self.image_quality_var.set("Unknown")
            self.damage_description_text.delete("1.0", tk.END)
            return
        
        # Lade Schadenskategorien
        damage_categories = exif_data.get("damage_categories", [])
        for category, var in self.damage_vars.items():
            var.set(category in damage_categories)
        
        # Lade Bildart-Kategorien
        image_types = exif_data.get("image_types", [])
        for img_type, var in self.image_type_vars.items():
            var.set(img_type in image_types)
        
        # Lade Bild verwenden
        use_image = exif_data.get("use_image", "ja")
        # Prüfe ob der Wert in der aktuellen Sprache verfügbar ist
        current_options = self.config.get_language_specific_list('use_image_options')
        if use_image not in current_options and current_options:
            # Fallback auf den ersten verfügbaren Wert
            use_image = current_options[0]
        self.use_image_var.set(use_image)
        
        # Lade Bildqualität
        self.image_quality_var.set(exif_data.get("image_quality", "Unknown"))
        
        # Lade Damage Description
        self.damage_description_text.delete("1.0", tk.END)
        self.damage_description_text.insert("1.0", exif_data.get("damage_description", ""))

    def open_config_editor(self):
        """Öffnet einen Editor für die zentrale JSON-Konfigurationsdatei mit Sprachwahl und OCR-Methoden-Auswahl."""
        win = tk.Toplevel(self)
        win.title("Konfiguration bearbeiten")
        win.geometry("600x700")

        notebook = ttk.Notebook(win)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Tab für OCR-Einstellungen
        ocr_frame = ttk.Frame(notebook)
        notebook.add(ocr_frame, text="OCR-Einstellungen")
        
        ttk.Label(ocr_frame, text="Aktive OCR-Methode:").pack(anchor='w', padx=5, pady=(10,0))
        
        # Nur noch die beiden besten Methoden anbieten
        ocr_method_map = {
            "Feste Koordinaten (schnell)": "feste_koordinaten",
            "Alte Methode": "old"
        }
        
        if 'ocr_settings' not in self.json_config:
            self.json_config['ocr_settings'] = {'active_method': 'feste_koordinaten'}

        current_method = self.json_config.get('ocr_settings', {}).get('active_method', 'feste_koordinaten')
        display_method = next((k for k, v in ocr_method_map.items() if v == current_method), "Feste Koordinaten (schnell)")
        
        ocr_method_var = tk.StringVar(value=display_method)
        ocr_method_combo = ttk.Combobox(ocr_frame, textvariable=ocr_method_var, values=list(ocr_method_map.keys()), state="readonly", width=30)
        ocr_method_combo.pack(anchor='w', padx=5, pady=(0,10))
        
        ttk.Label(ocr_frame, text="Wähle die primäre Methode für die Texterkennung.").pack(anchor='w', padx=5, pady=(0,10))

        # Debug-Checkbox für Vorschau
        debug_var = tk.BooleanVar(value=False)
        debug_check = ttk.Checkbutton(ocr_frame, text="Debug: Vorschau des erkannten Bereichs anzeigen", variable=debug_var)
        debug_check.pack(anchor='w', padx=5, pady=(0,10))
        
        # Dynamische Whitelist anzeigen
        ttk.Label(ocr_frame, text="Dynamische Whitelist (aus gültigen Kürzeln):", font=("TkDefaultFont", 10, "bold")).pack(anchor='w', padx=5, pady=(10, 5))
        
        # Whitelist berechnen und anzeigen
        valid_chars = set(''.join(self.valid_kurzel))
        whitelist = ''.join(sorted(valid_chars))
        whitelist_text = f"Erlaubte Zeichen: {whitelist}"
        whitelist_label = ttk.Label(ocr_frame, text=whitelist_text, font=("Courier", 9), foreground="blue")
        whitelist_label.pack(anchor='w', padx=5, pady=(0, 5))
        
        # Anzahl Zeichen anzeigen
        char_count_text = f"Anzahl verschiedener Zeichen: {len(valid_chars)}"
        char_count_label = ttk.Label(ocr_frame, text=char_count_text, font=("TkDefaultFont", 9), foreground="green")
        char_count_label.pack(anchor='w', padx=5, pady=(0, 10))
        
        # Beispiel-Kürzel anzeigen
        ttk.Label(ocr_frame, text="Beispiel-Kürzel:", font=("TkDefaultFont", 9, "bold")).pack(anchor='w', padx=5, pady=(5, 2))
        example_kurzel = self.valid_kurzel  # Alle Kürzel anzeigen
        example_text = f"Beispiele: {', '.join(example_kurzel)}"
        example_label = ttk.Label(ocr_frame, text=example_text, font=("TkDefaultFont", 9), foreground="gray")
        example_label.pack(anchor='w', padx=5, pady=(0, 10))

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
                display_img.thumbnail((400, 300), Image.Resampling.LANCZOS)
                
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

        # Tab für Kürzel
        kurzel_frame = ttk.Frame(notebook)
        notebook.add(kurzel_frame, text="Gültige Kürzel")
        ttk.Label(kurzel_frame, text="Ein Kürzel pro Zeile:").pack(anchor='w', padx=5, pady=(5,0))
        kurzel_text = tk.Text(kurzel_frame, wrap=tk.WORD, height=10, width=40)
        kurzel_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        kurzel_text.insert('1.0', '\n'.join(self.json_config.get('valid_kurzel', [])))

        # Tab für Kategorien
        kategorien_frame = ttk.Frame(notebook)
        notebook.add(kategorien_frame, text="Kategorien")

        # Sprachwahl für Kategorien
        language_var = tk.StringVar(value=self.json_config.get('current_language', 'de'))
        ttk.Label(kategorien_frame, text="Sprache für Kategorien:").pack(anchor='w', padx=5, pady=(5,0))
        language_combo = ttk.Combobox(kategorien_frame, textvariable=language_var, values=["de", "en"], state="readonly", width=8)
        language_combo.pack(anchor='w', padx=5, pady=(0,5))

        # Schadenskategorien
        ttk.Label(kategorien_frame, text="Schadenskategorien (eine pro Zeile):").pack(anchor='w', padx=5, pady=(5,0))
        damage_text = tk.Text(kategorien_frame, wrap=tk.WORD, height=8)
        damage_text.pack(fill=tk.X, expand=True, padx=5, pady=5)

        # Bildart-Kategorien
        ttk.Label(kategorien_frame, text="Bildart-Kategorien (eine pro Zeile):").pack(anchor='w', padx=5, pady=(5,0))
        imagetype_text = tk.Text(kategorien_frame, wrap=tk.WORD, height=5)
        imagetype_text.pack(fill=tk.X, expand=True, padx=5, pady=5)

        # Bildqualitäts-Kategorien
        ttk.Label(kategorien_frame, text="Bildqualitäts-Kategorien (eine pro Zeile):").pack(anchor='w', padx=5, pady=(5,0))
        imagequality_text = tk.Text(kategorien_frame, wrap=tk.WORD, height=4)
        imagequality_text.pack(fill=tk.X, expand=True, padx=5, pady=5)

        def update_category_fields(*args):
            lang = language_var.get()
            damage = self.json_config.get('damage_categories', {}).get(lang, [])
            imagetypes = self.json_config.get('image_types', {}).get(lang, [])
            imagequality = self.json_config.get('image_quality_options', {}).get(lang, [])
            damage_text.delete('1.0', tk.END)
            damage_text.insert('1.0', '\n'.join(damage))
            imagetype_text.delete('1.0', tk.END)
            imagetype_text.insert('1.0', '\n'.join(imagetypes))
            imagequality_text.delete('1.0', tk.END)
            imagequality_text.insert('1.0', '\n'.join(imagequality))

        update_category_fields()
        language_combo.bind("<<ComboboxSelected>>", update_category_fields)

        def on_save():
            try:
                # OCR-Methode speichern
                selected_display_method = ocr_method_var.get()
                selected_method = ocr_method_map.get(selected_display_method, 'improved')
                self.json_config.setdefault('ocr_settings', {})['active_method'] = selected_method
                self.json_config['ocr_settings']['debug_preview'] = debug_var.get()

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

                # Kürzel speichern
                kurzel_list = [line.strip().upper() for line in kurzel_text.get('1.0', 'end').splitlines() if line.strip()]
                self.json_config['valid_kurzel'] = kurzel_list
                self.valid_kurzel = kurzel_list

                lang = language_var.get()
                # Schadenskategorien
                damage_list = [line.strip() for line in damage_text.get('1.0', 'end').splitlines() if line.strip()]
                self.json_config.setdefault('damage_categories', {})[lang] = damage_list

                # Bildart-Kategorien
                imagetype_list = [line.strip() for line in imagetype_text.get('1.0', 'end').splitlines() if line.strip()]
                self.json_config.setdefault('image_types', {})[lang] = imagetype_list

                # Bildqualitäts-Kategorien
                imagequality_list = [line.strip() for line in imagequality_text.get('1.0', 'end').splitlines() if line.strip()]
                self.json_config.setdefault('image_quality_options', {})[lang] = imagequality_list

                if save_json_config(self.json_config):
                    messagebox.showinfo("Gespeichert", "Konfiguration wurde erfolgreich gespeichert.\nEinige Änderungen erfordern einen Neustart.", parent=win)
                    self.correct_combo['values'] = self.valid_kurzel
                    self.update_code_listbox()
                    win.destroy()
                else:
                    messagebox.showerror("Fehler", "Konfiguration konnte nicht gespeichert werden.", parent=win)

            except Exception as e:
                messagebox.showerror("Fehler", f"Ein Fehler ist aufgetreten: {e}", parent=win)

        button_frame = ttk.Frame(win)
        button_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        ttk.Button(button_frame, text="Speichern", command=on_save).pack(side=tk.RIGHT)
        ttk.Button(button_frame, text="Abbrechen", command=win.destroy).pack(side=tk.RIGHT, padx=5)

    def open_folder(self):
        """Öffnet einen Ordner mit Bildern ohne Analyse zu starten"""
        sel = filedialog.askdirectory(title="Ordner mit Bildern auswählen")
        if not sel:
            return
        
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
        
        # Aktualisiere Bewertungsfortschritt
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
        
        # Aktualisiere Listbox
        self.update_code_listbox()
        
        write_detailed_log("info", "Zähler aus EXIF-Daten aktualisiert", f"Gefundene Tags: {dict(self.counter)}")

    def load_excel_project_data(self):
        """Lädt gezielt nur die benötigten Spalten aus einer Excel-Datei, zeigt alle Zeilen zur Auswahl und füllt die Felder als Eingabefelder im Grid-Layout"""
        print("load_excel_project_data() aufgerufen")
        write_detailed_log("info", "Excel-Dateiauswahl gestartet")
        
        file_path = filedialog.askopenfilename(title="Excel-Datei mit Grunddaten auswählen", filetypes=[("Excel files", "*.xlsx *.xls")])
        print(f"Ausgewählter Dateipfad: {file_path}")
        
        if not file_path:
            write_detailed_log("warning", "Kein Excel-Dateipfad ausgewählt")
            print("Kein Dateipfad ausgewählt, verstecke Excel-Grunddaten")
            # Verstecke Excel-Grunddaten-Frame, wenn keine Datei ausgewählt wurde
            self.hide_excel_grunddaten()
            return
        write_detailed_log("info", "Excel-Dateipfad gewählt", file_path)
        try:
            write_detailed_log("info", "Versuche Excel-Datei zu öffnen", file_path)
            xl = pd.ExcelFile(file_path)
            write_detailed_log("info", "Verfügbare Blätter", str(xl.sheet_names))
            df = pd.read_excel(file_path, header=2)  # Zeile 3 als Überschriftenzeile
            write_detailed_log("info", f"Excel-Datei eingelesen, Zeilen: {df.shape[0]} Spalten: {df.shape[1]}", str(df.columns))
            # Prüfe, ob alle benötigten Spalten vorhanden sind
            fehlende = [col for col in excel_to_json.keys() if col not in df.columns]
            if fehlende:
                write_detailed_log("error", "Fehlende Spalten in Excel", str(fehlende))
                messagebox.showerror("Fehler", f"Folgende Spalten fehlen in der Excel-Datei:\n{fehlende}\nGefunden: {list(df.columns)}")
                # Verstecke Excel-Grunddaten-Frame bei Fehler
                self.hide_excel_grunddaten()
                return
            # Nur die benötigten Spalten behalten
            df = df[list(excel_to_json.keys())]
            self.excel_df = df
            # Erstelle eine Liste von Auswahltexten für die Combobox (z.B. ANlagen_nr + SN)
            auswahl_liste = []
            for idx, row in df.iterrows():
                anlagen_nr = row.get('turbine_id')
                sn = row.get('turbine_sn', '')
                label = f"{anlagen_nr} | {sn}"
                auswahl_liste.append(label)
            self.excel_row_combo['values'] = auswahl_liste
            if auswahl_liste:
                self.excel_row_combo.current(0)
                self.on_excel_row_selected()
            # Felder im GUI als Grid anlegen (vorherige löschen)
            for child in self.grunddaten_fields.values():
                child.destroy()
            self.grunddaten_fields.clear()
            for child in self.fields_frame.winfo_children():
                child.destroy()
            self.grunddaten_vars = {excel_to_json[excel_key]: tk.StringVar() for excel_key in excel_to_json.keys()}
            # Grid-Layout: Labels und Entries untereinander
            for i, excel_key in enumerate(excel_to_json.keys()):
                json_key = excel_to_json[excel_key]
                ttk.Label(self.fields_frame, text=json_key+":").grid(row=i, column=0, sticky='w', padx=2, pady=1)
                entry = ttk.Entry(self.fields_frame, textvariable=self.grunddaten_vars[json_key], width=20)
                entry.grid(row=i, column=1, padx=2, pady=1)
                self.grunddaten_fields[json_key] = entry
            
            print("Excel-Daten erfolgreich verarbeitet, zeige Excel-Grunddaten-Frame an...")
            # Zeige Excel-Grunddaten-Frame an
            self.show_excel_grunddaten()
            
            write_detailed_log("info", "Excel erfolgreich verarbeitet und GUI aktualisiert (Grid-Layout)")
        except Exception as e:
            import traceback
            print(f"Fehler beim Einlesen der Excel-Datei: {e}")
            write_detailed_log("error", "Fehler beim Einlesen der Excel-Datei", f"Pfad: {file_path}", e)
            messagebox.showerror("Fehler", f"Fehler beim Einlesen der Excel-Datei: {e}\n{traceback.format_exc()}")
            # Verstecke Excel-Grunddaten-Frame bei Fehler
            self.hide_excel_grunddaten()

    def on_excel_row_selected(self, event=None):
        idx = self.excel_row_combo.current()
        if self.excel_df is None or idx < 0:
            return
        row = self.excel_df.iloc[idx]
        grunddaten = {}
        for excel_key, json_key in excel_to_json.items():
            value = row.get(excel_key, "")
            self.grunddaten_vars[json_key].set(str(value))
            grunddaten[json_key] = str(value)
        self.project_data_from_excel = grunddaten
        self.excel_row_index = idx

    def auto_analyze(self):
        # Nutze den bereits gewählten Ordner, falls vorhanden
        sel = self.source_dir
        if not sel:
            sel = filedialog.askdirectory(title="Ordner mit Bildern auswählen")
            if not sel:
                return
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

    def show_image(self):
        """Bild anzeigen mit umfassender Fehlerbehandlung (nur Listbox, nie größer als Canvas)"""
        if self._loading_image:
            return
        self._loading_image = True
        
        try:
            if not self.files:
                return
            if self.index >= len(self.files):
                return
                
            fname = self.files[self.index]
            self.current_file = fname  # Setze current_file für Zoom-Button
            path = os.path.join(self.source_dir, fname)
            
            # Prüfe ob Datei existiert
            if not os.path.exists(path):
                return
                
            # Lade Bild
            img = Image.open(path)
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
            # Bild anzeigen
            self.photo = ImageTk.PhotoImage(img)
            x = c_w // 2
            y = c_h // 2
            self.canvas.delete("all")
            self.canvas.create_image(x, y, image=self.photo)
            
            # Zeige OCR-Ergebnis
            exif_data = get_exif_usercomment(path)
            if exif_data and "TAGOCR" in exif_data:
                detected = exif_data["TAGOCR"]
                self.correct_var.set(detected if detected in self.valid_kurzel else '')
                # Listbox-Auswahl setzen
                self.select_code_in_listbox(detected)
                self._current_tagocr = detected
                self.ocr_tag_var.set(f"OCR-Tag: {detected}")
            else:
                self.code_listbox.selection_clear(0, tk.END)
                self._current_tagocr = None
                self.ocr_tag_var.set("OCR-Tag: -")
            
            # Lade Bewertung
            self.load_current_evaluation()
            
            # Update Bildinformationen über dem Bild (nur beim Analysieren)
            if self._analyzing:
                self.image_counter_var.set(f"Bild {self.index + 1} von {len(self.files)}")
                self.filename_var.set(fname)
            
            # Update Status
            self.status_var.set(f"Bild {self.index + 1} von {len(self.files)}: {fname}")
            
            # Aktualisiere Listbox bei Bildwechsel
            self.update_code_listbox()
            
        except Exception as e:
            print(f"Fehler beim Anzeigen des Bildes: {e}")
            import traceback
            traceback.print_exc()
            self.status_var.set(f"Fehler beim Laden des Bildes: {str(e)}")
        finally:
            self._loading_image = False

    def select_code_in_listbox(self, code):
        """Wählt den passenden Code in der Listbox aus"""
        for idx in range(self.code_listbox.size()):
            label = self.code_listbox.get(idx)
            if label.startswith(code + ' '):
                self.code_listbox.selection_clear(0, tk.END)
                self.code_listbox.selection_set(idx)
                self.code_listbox.see(idx)
                break

    def update_code(self):
        new = self.correct_var.get().strip().upper()
        if new not in self.valid_kurzel:
            write_detailed_log("warning", "Ungültiger Code ausgewählt", f"Code: {new}")
            messagebox.showerror("Ungültig", "Wählen Sie einen gültigen Code")
            return
        
        fname = self.files[self.index]
        path = os.path.join(self.source_dir, fname)
        
        # Lade bestehende EXIF-Daten
        exif_data = get_exif_usercomment(path)
        if exif_data is None:
            exif_data = self.json_config.copy()
        
        # Aktualisiere nur das TAGOCR-Feld, behalte alle anderen Daten
        old_code = exif_data.get("TAGOCR", "")
        exif_data["TAGOCR"] = new
        
        write_detailed_log("info", "Code manuell aktualisiert", f"Datei: {fname}, Alt: '{old_code}', Neu: '{new}'")
        
        # Schreibe Log-Eintrag für manuelle Korrektur
        write_log_entry(fname, f"MANUAL_CORRECTION_{old_code}", new)
        
        # Speichere aktualisierte EXIF-Daten
        if save_exif_usercomment(path, exif_data):
            # Update counter
            if old_code in self.valid_kurzel:
                self.counter[old_code] -= 1
            self.counter[new] += 1
            self.code_listbox.delete(0, tk.END)
            self.code_listbox.insert(tk.END, f"{new} ({self.counter[new]})")
            
            # Cache invalidieren, da sich TAGOCR-Daten geändert haben
            self.invalidate_evaluation_cache()
            
            messagebox.showinfo("Aktualisiert", "Code erfolgreich aktualisiert")
            self.next_image()
        else:
            write_detailed_log("error", "Fehler beim Aktualisieren der EXIF-Daten", f"Datei: {fname}")
            messagebox.showerror("Fehler", "Fehler beim Aktualisieren der EXIF-Daten")

    def next_image(self):
        """Nächstes Bild anzeigen mit Fehlerbehandlung"""
        try:
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
                img.thumbnail((32, 32), Image.LANCZOS)
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
                
                # Alle Zeichnungen sammeln
                for item_data in undo_stack:
                    if item_data[0] == 'arrow':
                        x0, y0, x1, y1 = item_data[2], item_data[3], item_data[4], item_data[5]
                        # Skalierung berücksichtigen
                        x0 = int(x0 / zoom_factor)
                        y0 = int(y0 / zoom_factor)
                        x1 = int(x1 / zoom_factor)
                        y1 = int(y1 / zoom_factor)
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
                        x = int(x / zoom_factor)
                        y = int(y / zoom_factor)
                        r = int(r / zoom_factor)
                        draw.ellipse((x-r, y-r, x+r, y+r), outline=draw_color, width=line_width)
                        
                    elif item_data[0] == 'rectangle':
                        x0, y0, x1, y1 = item_data[2], item_data[3], item_data[4], item_data[5]
                        x0 = int(x0 / zoom_factor)
                        y0 = int(y0 / zoom_factor)
                        x1 = int(x1 / zoom_factor)
                        y1 = int(y1 / zoom_factor)
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
                
                self.config.set_setting('display.window_x', x)
                self.config.set_setting('display.window_y', y)
                
                # Fenstergröße extrahieren
                if 'x' in size:
                    width, height = size.split('x')
                    self.config.set_setting('display.window_width', int(width))
                    self.config.set_setting('display.window_height', int(height))
        except Exception as e:
            write_detailed_log("warning", "Fehler beim Speichern der Fensterposition", str(e))
        
        # Ordnerpfad speichern
        try:
            if self.source_dir:
                # Speichere in Konfiguration
                self.config.set_setting('paths.last_folder', self.source_dir)
                
                # Kompatibilität: Auch in separate Datei
                with open(LAST_FOLDER_FILE, 'w', encoding='utf-8') as f:
                    f.write(self.source_dir)
        except Exception as e:
            write_detailed_log("warning", "Fehler beim Speichern des letzten Ordners", str(e))
        
        # Checkbox-Wert speichern
        try:
            if hasattr(self, 'filter_zero_var'):
                self.config.set_setting('display.filter_zero_codes', self.filter_zero_var.get())
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

    def show_excel_grunddaten(self):
        """Zeigt den Excel-Grunddaten-Frame an"""
        try:
            print("Versuche Excel-Grunddaten-Frame anzuzeigen...")
            write_detailed_log("info", "Versuche Excel-Grunddaten-Frame anzuzeigen")
            
            # Prüfe, ob der Frame existiert
            if hasattr(self, 'grunddaten_frame'):
                print(f"grunddaten_frame gefunden: {self.grunddaten_frame}")
                self.grunddaten_frame.pack(fill=tk.X, pady=(0, 5))
                print("grunddaten_frame.pack() ausgeführt")
                write_detailed_log("info", "Excel-Grunddaten-Frame erfolgreich eingeblendet")
            else:
                print("grunddaten_frame nicht gefunden!")
                write_detailed_log("error", "grunddaten_frame Attribut nicht gefunden")
        except Exception as e:
            print(f"Fehler beim Einblenden des Excel-Grunddaten-Frames: {e}")
            write_detailed_log("error", "Fehler beim Einblenden des Excel-Grunddaten-Frames", str(e))
            import traceback
            traceback.print_exc()

    def hide_excel_grunddaten(self):
        """Versteckt den Excel-Grunddaten-Frame"""
        try:
            print("Versuche Excel-Grunddaten-Frame zu verstecken...")
            write_detailed_log("info", "Versuche Excel-Grunddaten-Frame zu verstecken")
            
            if hasattr(self, 'grunddaten_frame'):
                print(f"grunddaten_frame gefunden: {self.grunddaten_frame}")
                self.grunddaten_frame.pack_forget()
                print("grunddaten_frame.pack_forget() ausgeführt")
                write_detailed_log("info", "Excel-Grunddaten-Frame erfolgreich ausgeblendet")
            else:
                print("grunddaten_frame nicht gefunden!")
                write_detailed_log("error", "grunddaten_frame Attribut nicht gefunden")
        except Exception as e:
            print(f"Fehler beim Ausblenden des Excel-Grunddaten-Frames: {e}")
            write_detailed_log("error", "Fehler beim Ausblenden des Excel-Grunddaten-Frames", str(e))
            import traceback
            traceback.print_exc()

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
        self.update_code_listbox()
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
        
        # Fuzzy-Matching gegen gültige Kürzel
        if text:
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
            display_img.thumbnail((300, 200), Image.Resampling.LANCZOS)
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
            crop_display.thumbnail((300, 200), Image.Resampling.LANCZOS)
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
            img.thumbnail((300, 300), Image.LANCZOS)
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
        self.window.geometry("1200x800")
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Variablen
        self.analyzing = False
        self.ocr_settings = json_config.get('ocr_settings', {})
        self.active_method = self.ocr_settings.get('active_method', 'improved')
        self.debug_preview = self.ocr_settings.get('debug_preview', False)
        
        # Cutout-Koordinaten (Standardwerte)
        self.cutout_coords = json_config.get('cutout_coordinates', {'x': 10, 'y': 10, 'w': 60, 'h': 35})
        
        # GUI erstellen
        self.create_widgets()
        
        # Analyse starten
        self.start_analysis()
    
    def create_widgets(self):
        """Erstellt die GUI-Elemente"""
        # Hauptframe
        main_frame = ttk.Frame(self.window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Oberer Bereich: Fortschritt und Status
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Status-Label
        self.status_label = ttk.Label(top_frame, text="Bereite Analyse vor...", font=("TkDefaultFont", 12, "bold"))
        self.status_label.pack(anchor='w')
        
        # Fortschrittsbalken
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(top_frame, variable=self.progress_var, maximum=len(self.files))
        self.progress_bar.pack(fill=tk.X, pady=(5, 0))
        
        # Fortschritts-Text
        self.progress_text = ttk.Label(top_frame, text="0 / " + str(len(self.files)))
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
        
        # Treeview für Ergebnisse
        columns = ('Datei', 'Original', 'Cutout', 'Erkannt', 'Korrigiert', 'Konfidenz', 'Methode')
        self.results_tree = ttk.Treeview(bottom_frame, columns=columns, show='headings', height=10)
        
        # Spalten konfigurieren
        for col in columns:
            self.results_tree.heading(col, text=col)
            self.results_tree.column(col, width=100)
        
        # Scrollbar für Treeview
        tree_scroll = ttk.Scrollbar(bottom_frame, orient=tk.VERTICAL, command=self.results_tree.yview)
        self.results_tree.configure(yscrollcommand=tree_scroll.set)
        
        self.results_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))

        self.stop_button = ttk.Button(button_frame, text="Analyse stoppen", command=self.stop_analysis)
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
        update_coords_button = ttk.Button(coords_inner, text="Koordinaten anwenden", command=self.update_cutout_coordinates)
        update_coords_button.pack(side=tk.RIGHT, padx=(10, 0))
    
    def start_analysis(self):
        """Startet die OCR-Analyse"""
        self.analyzing = True
        self.current_index = 0
        self.results = []
        self.results_tree.delete(*self.results_tree.get_children())
        
        # Initialisiere OCR
        if not hasattr(self.parent, 'improved_ocr'):
            self.parent.improved_ocr = ImprovedOCR(self.valid_kurzel)
        
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
    
    def perform_ocr(self, img, fname):
        """Führt OCR für ein Bild durch"""
        try:
            if self.active_method == 'feste_koordinaten':
                return self.parent.ocr_method_feste_koordinaten(img, debug=False)
            elif self.active_method == 'old':
                src = os.path.join(self.source_dir, fname)
                return old_ocr_method(src, self.valid_kurzel)
            else:
                return {'text': None, 'confidence': 0.0, 'raw_text': 'Unbekannte Methode', 'method': self.active_method}
        except Exception as e:
            return {
                'text': None,
                'confidence': 0.0,
                'raw_text': str(e),
                'method': f'{self.active_method}_error'
            }
    
    def show_images(self, original_img, cutout_img):
        """Zeigt Original- und Cutout-Bild in den Canvas-Elementen an"""
        try:
            # Originalbild skalieren und anzeigen
            original_display = original_img.copy()
            original_display.thumbnail((400, 300), Image.Resampling.LANCZOS)
            original_photo = ImageTk.PhotoImage(original_display)
            
            self.original_canvas.delete("all")
            self.original_canvas.create_image(200, 150, image=original_photo, anchor=tk.CENTER)
            self.original_canvas.image = original_photo  # Referenz halten
            
            # Cutout skalieren und anzeigen
            cutout_display = cutout_img.copy()
            cutout_display.thumbnail((200, 150), Image.Resampling.LANCZOS)
            cutout_photo = ImageTk.PhotoImage(cutout_display)
            
            self.cutout_canvas.delete("all")
            self.cutout_canvas.create_image(100, 75, image=cutout_photo, anchor=tk.CENTER)
            self.cutout_canvas.image = cutout_photo  # Referenz halten
            
        except Exception as e:
            print(f"Fehler beim Anzeigen der Bilder: {e}")
    
    def add_result_to_tree(self, result):
        """Fügt ein Ergebnis zur Treeview hinzu"""
        ocr_result = result['ocr_result']
        values = (
            result['filename'],
            f"{result['original_image'].size[0]}x{result['original_image'].size[1]}",
            f"{result['cutout_image'].size[0]}x{result['cutout_image'].size[1]}",
            ocr_result.get('raw_text', ''),
            ocr_result.get('text', ''),
            f"{ocr_result.get('confidence', 0.0):.2f}",
            ocr_result.get('method', '')
        )
        
        item = self.results_tree.insert('', 'end', values=values)
        # Speichere Referenz auf das Ergebnis (entfernt, da Spalte nicht existiert)
    
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
        dialog.geometry("400x300")
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
        cutout_display.thumbnail((150, 100), Image.Resampling.LANCZOS)
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
    
    def get_cutout_coordinates(self):
        """Gibt die aktuellen Cutout-Koordinaten zurück"""
        try:
            # Verwende Koordinaten aus der Konfiguration
            crop_coords = self.json_config.get('crop_coordinates', {})
            x = crop_coords.get('x', 10)
            y = crop_coords.get('y', 10)
            w = crop_coords.get('w', 60)
            h = crop_coords.get('h', 35)
            return x, y, w, h
        except Exception:
            # Fallback auf Standardwerte
            return 10, 10, 60, 35
    
    def update_cutout_coordinates(self):
        """Aktualisiert die Cutout-Koordinaten"""
        try:
            x = int(self.x_var.get())
            y = int(self.y_var.get())
            w = int(self.w_var.get())
            h = int(self.h_var.get())
            
            # Speichere in Konfiguration
            self.json_config['crop_coordinates'] = {'x': x, 'y': y, 'w': w, 'h': h}
            
            # Speichere Konfiguration
            if save_json_config(self.json_config):
                messagebox.showinfo("Erfolg", f"Koordinaten aktualisiert: X={x}, Y={y}, Breite={w}, Höhe={h}")
            else:
                messagebox.showerror("Fehler", "Koordinaten konnten nicht gespeichert werden!")
            
        except ValueError:
            messagebox.showerror("Fehler", "Bitte geben Sie gültige Zahlen ein!")
    
    def on_close(self):
        """Schließt das Analyse-Fenster"""
        self.analyzing = False
        self.window.destroy()

    def abort_analysis(self):
        """Bricht die Analyse sofort ab und schließt das Analysefenster."""
        self.analyzing = False
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
