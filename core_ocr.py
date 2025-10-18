#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCR-Verarbeitung
Verbesserte OCR-Engine mit dynamischer Anpassung an gültige Kürzel
"""

import re
import os
import cv2
import numpy as np
import easyocr
from PIL import Image, ImageEnhance
from difflib import get_close_matches

from constants import DetectParams
from config_manager import CODE_FILE, load_json_config, save_json_config


# Globaler EasyOCR Reader (Singleton-Pattern für Performance)
_READER = None


# Excel zu JSON Mapping
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


def get_reader():
    """Holt oder erstellt den globalen EasyOCR Reader (Singleton)"""
    global _READER
    if _READER is None:
        _READER = easyocr.Reader(['de', 'en'])
    return _READER


def get_dynamic_whitelist(valid_kurzel):
    """Erstellt eine dynamische Whitelist aus gültigen Kürzeln"""
    valid_chars = set(''.join(valid_kurzel))
    return ''.join(sorted(valid_chars))


def correct_alternative_kurzel(text, alternative_kurzel):
    """Korrigiert Text basierend auf alternativen Kürzeln"""
    if not text or not alternative_kurzel:
        return text
    
    text_lower = text.lower().strip()
    if text_lower in alternative_kurzel:
        return alternative_kurzel[text_lower]
    
    matches = get_close_matches(text_lower, alternative_kurzel.keys(), n=1, cutoff=0.8)
    if matches:
        return alternative_kurzel[matches[0]]
    
    return text


def upscale_crop(crop_img, scale_factor: float = 2.0):
    """Upscales ein Crop-Bild für bessere OCR-Erkennung."""
    if crop_img is None or crop_img.size == 0:
        return crop_img
    
    height, width = crop_img.shape[:2]
    new_width = int(width * scale_factor)
    new_height = int(height * scale_factor)
    
    # INTER_CUBIC für beste Qualität beim Upscaling
    upscaled = cv2.resize(crop_img, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
    return upscaled


def post_process_text(text: str, enabled: bool = True, char_mappings: dict = None):
    """Post-Processing für erkannten Text mit Ersetzungslogik.
    
    Returns:
        tuple: (processed_text, replacements_list)
    """
    if not enabled or not text or text.startswith("[") or text.startswith("Kein"):
        return text, []
    
    # Zeichen-Mapping für häufige OCR-Fehler (überschreibbar)
    default_mappings = {
        'l': '1',  # kleines l → 1
        'Z': '2',  # großes Z → 2
        'z': '2',  # kleines z → 2
        'I': '1',  # großes I → 1
        'O': '0',  # großes O → 0
        'o': '0',  # kleines o → 0
    }
    mappings = char_mappings if isinstance(char_mappings, dict) and char_mappings else default_mappings
    
    processed_text = text
    replacements = []
    
    for old_char, new_char in mappings.items():
        if old_char in processed_text:
            count = processed_text.count(old_char)
            processed_text = processed_text.replace(old_char, new_char)
            replacements.append(f"'{old_char}' → '{new_char}' ({count}x)")
    
    return processed_text, replacements


def find_text_box_easyocr(img_bgr, crop_coords: dict = None, valid_kurzel: list = None, detect_params: DetectParams = None):
    """Verwendet EasyOCR für automatische Text-Box-Findung im wählbaren Bereich.

    - Wenn crop_coords gesetzt: Suche in diesem festen Rechteck (x,y,w,h)
    - Sonst: verwende detect_params (Top/Bottom/Left/Right-Fracs) zur Bereichsbildung
    - Filtere nach Flächenanteil und Seitenverhältnis (detect_params)
    - Polstere Ergebnisbox mit Padding (detect_params)

    Args:
        img_bgr: BGR-Bild (OpenCV Format)
        crop_coords: Optionales Dict {'x','y','w','h'}
        valid_kurzel: Optional - Liste gültiger Kürzel zum Filtern
        detect_params: Optional - Instanz von DetectParams

    Returns:
        tuple: (x, y, w, h) der gefundenen Box oder None
    """
    try:
        # EasyOCR Reader initialisieren (Singleton-Pattern)
        if not hasattr(find_text_box_easyocr, 'reader'):
            find_text_box_easyocr.reader = easyocr.Reader(['en'], gpu=False)
        H, W = img_bgr.shape[:2]

        # Bereich bestimmen
        if crop_coords:
            x0 = int(max(0, crop_coords.get('x', 0)))
            y0 = int(max(0, crop_coords.get('y', 0)))
            w0 = int(max(1, crop_coords.get('w', W)))
            h0 = int(max(1, crop_coords.get('h', H)))
        else:
            dp = detect_params or DetectParams()
            x0 = int(W * dp.left_frac)
            y0 = int(H * dp.top_frac)
            x1f = int(W * (1.0 - dp.right_frac))
            y1f = int(H * (1.0 - dp.bottom_frac))
            w0 = max(1, x1f - x0)
            h0 = max(1, y1f - y0)

        x1 = min(x0 + w0, W)
        y1 = min(y0 + h0, H)

        # ROI ausschneiden
        roi = img_bgr[y0:y1, x0:x1]
        if roi.size == 0:
            return None

        # OCR mit Detection auf ROI ausführen
        result = find_text_box_easyocr.reader.readtext(roi)
        print(f"find_text_box_easyocr: EasyOCR fand {len(result)} Texte im Suchbereich")
        if not result:
            return None
        
        best_box = None
        best_score = -1e9
        roi_area = float(roi.shape[0] * roi.shape[1])
        dp = detect_params or DetectParams()
        valid_norm = None
        if valid_kurzel:
            try:
                valid_norm = [str(k).upper().strip() for k in valid_kurzel]
                print(f"find_text_box_easyocr: Filtere nach {len(valid_norm)} gültigen Kürzeln")
            except Exception:
                valid_norm = [str(k).upper() for k in valid_kurzel]

        for idx, detection in enumerate(result):
            # EasyOCR Format: [[[x1,y1],[x2,y2],[x3,y3],[x4,y4]], text, confidence]
            box_coords = detection[0]
            text = detection[1]
            confidence = detection[2]
            print(f"  Detection {idx+1}: Text='{text}', Confidence={confidence:.2f}")
            
            # Bounding Box berechnen (relativ zum ROI)
            x_coords = [pt[0] for pt in box_coords]
            y_coords = [pt[1] for pt in box_coords]
            x1_rel, x2_rel = min(x_coords), max(x_coords)
            y1_rel, y2_rel = min(y_coords), max(y_coords)
            w = x2_rel - x1_rel
            h = y2_rel - y1_rel
            
            # Filter: Flächenanteil
            box_area = max(1.0, float(w * h))
            area_frac = box_area / max(1.0, roi_area)
            if area_frac < dp.min_area_frac or area_frac > dp.max_area_frac:
                print(f"    -> Abgelehnt: Flächenanteil {area_frac:.4f} nicht in [{dp.min_area_frac}, {dp.max_area_frac}]")
                continue

            # Filter: Seitenverhältnis (Breite/Höhe)
            aspect = (w / max(1.0, h)) if h > 0 else 0.0
            if aspect < dp.min_aspect or aspect > dp.max_aspect:
                print(f"    -> Abgelehnt: Seitenverhältnis {aspect:.2f} nicht in [{dp.min_aspect}, {dp.max_aspect}]")
                continue

            # Koordinaten zurück auf das Gesamtbild umrechnen
            x1_abs = x0 + x1_rel
            y1_abs = y0 + y1_rel
            
            # Filter: nur wenn Text zu gültigen Kürzeln passt
            if valid_norm is not None:
                text_clean = text.upper().strip()
                if not any(k in text_clean for k in valid_norm):
                    print(f"    -> Abgelehnt: Text '{text_clean}' passt zu keinem gültigen Kürzel")
                    continue
            
            # Score basierend auf Confidence
            score = float(confidence) * 100.0
            print(f"    -> Akzeptiert: Score={score:.2f}")
            
            if score > best_score:
                best_score = score
                best_box = (int(x1_abs), int(y1_abs), int(w), int(h))
                print(f"    -> Neuer Bester: Box={best_box}")
        
        if best_box is None:
            return None

        # Padding anwenden
        bx, by, bw, bh = best_box
        bx_pad = max(0, bx + dp.padding_left)
        by_pad = max(0, by + dp.padding_top)
        br_pad = min(W, bx + bw + dp.padding_right)
        bb_pad = min(H, by + bh + dp.padding_bottom)
        bw_pad = max(1, br_pad - bx_pad)
        bh_pad = max(1, bb_pad - by_pad)

        return (int(bx_pad), int(by_pad), int(bw_pad), int(bh_pad))
        
    except Exception as e:
        print(f"EasyOCR Box-Detection Fehler: {e}")
        return None


def run_ocr_easyocr_improved(crop_img, enable_post_processing: bool = True, char_mappings: dict = None):
    """Verbesserte EasyOCR mit Upscaling und Post-Processing.
    
    Args:
        crop_img: Crop-Bild (BGR Format)
        enable_post_processing: Ob Post-Processing aktiviert sein soll
        
    Returns:
        tuple: (processed_text, replacements_list)
    """
    try:
        # EasyOCR Reader initialisieren (Singleton-Pattern)
        if not hasattr(run_ocr_easyocr_improved, 'reader'):
            run_ocr_easyocr_improved.reader = easyocr.Reader(['en'], gpu=False)
        
        # Upscaling für bessere Erkennung
        upscaled_img = upscale_crop(crop_img, scale_factor=2.0)
        
        # OCR ausführen
        result = run_ocr_easyocr_improved.reader.readtext(upscaled_img)
        
        if not result:
            return "[Kein Text erkannt]", []
        
        # Texte zusammenfassen
        texts = []
        for detection in result:
            text = detection[1]
            confidence = detection[2]
            if confidence > 0.3:  # Nur Texte mit guter Confidence
                texts.append(text)
        
        raw_text = " ".join(texts) if texts else "[Kein Text erkannt]"
        
        # Post-Processing
        processed_text, replacements = post_process_text(raw_text, enable_post_processing, char_mappings)
        
        if replacements:
            print(f"OCR Post-Processing: {', '.join(replacements)}")
        
        return processed_text, replacements
        
    except Exception as e:
        print(f"EasyOCR Improved Error: {e}")
        return f"[EasyOCR-Error: {e}]", []


class ImprovedOCR:
    """Verbesserte OCR-Engine mit dynamischer Anpassung an gültige Kürzel"""
    
    def __init__(self, valid_kurzel, alternative_kurzel=None):
        self.valid_kurzel = valid_kurzel
        self.alternative_kurzel = alternative_kurzel or {}
        self.reader = easyocr.Reader(['de', 'en'])
        self._update_optimizations()
        
    def _update_optimizations(self):
        """Aktualisiert die OCR-Optimierungen basierend auf den aktuellen gültigen Kürzeln"""
        self._analyze_valid_codes()
        
        self.char_replacements = {
            'I': '1', 'O': '0', '|': '1', 'l': '1', 'i': '1',
            'S': '5', 'G': '6', 'B': '8', 'Z': '2', 'z': '2',
            'D': '0', 'Q': '0', 'U': '0',
            'A': '4', 'E': '3', 'F': '7', 'T': '7'
        }
        
        self.allowed_chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-'
        self.common_fixes = self._generate_common_fixes()
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
            numbers = re.findall(r'\d', code)
            self.allowed_numbers.update(numbers)
            
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
        
        for code in self.valid_kurzel:
            for i in range(2, len(code) + 1):
                prefix = code[:i]
                if prefix not in self.prefix_patterns:
                    self.prefix_patterns[prefix] = []
                self.prefix_patterns[prefix].append(code)
    
    def _generate_common_fixes(self):
        """Generiert häufige Fehler-Korrekturen basierend auf aktuellen Kürzeln"""
        fixes = {}
        
        for code in self.valid_kurzel:
            if 'Z' in code:
                wrong_code = code.replace('2', 'Z')
                fixes[wrong_code] = code
            if '1' in code:
                wrong_code = code.replace('1', 'I')
                fixes[wrong_code] = code
            if '0' in code:
                wrong_code = code.replace('0', 'O')
                fixes[wrong_code] = code
        
        return fixes
    
    def _generate_special_rules(self):
        """Generiert spezielle Regeln basierend auf aktuellen Kürzeln"""
        rules = {}
        
        pl_codes = [c for c in self.valid_kurzel if c.startswith('PL')]
        if pl_codes:
            rules['PL'] = {
                'base_codes': [c for c in pl_codes if not 'B' in c],
                'b_g_codes': [c for c in pl_codes if 'B' in c and 'G' in c],
                'b_r_codes': [c for c in pl_codes if 'B' in c and 'R' in c]
            }
        
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
            
        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        
        height, width = gray.shape
        upper_left_region = gray[0:height//3, 0:width//3]
        
        regions = []
        
        _, binary = cv2.threshold(upper_left_region, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if 20 < w < 150 and 10 < h < 80:
                regions.append((x, y, w, h))
        
        _, thresh = cv2.threshold(upper_left_region, 200, 255, cv2.THRESH_BINARY)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        dilated = cv2.dilate(thresh, kernel, iterations=1)
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if 30 < w < 120 and 15 < h < 60:
                regions.append((x, y, w, h))
        
        if regions:
            best_region = min(regions, key=lambda r: abs(r[1] - 20) + abs(r[2] * r[3] - 2000))
            return best_region
        
        return (10, 55, 100, 50)
    
    def preprocess_image(self, image, region=None):
        """Verbessertes Preprocessing für bessere OCR-Erkennung"""
        if region:
            image = image.crop(region)
        image = image.convert('L')
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(2.0)
        img_np = np.array(image)
        kernel = np.array([[0, -1, 0], [-1, 5,-1], [0, -1, 0]])
        img_np = cv2.filter2D(img_np, -1, kernel)
        _, img_np = cv2.threshold(img_np, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        image = Image.fromarray(img_np)
        return image
    
    def extract_text_with_confidence(self, image):
        """OCR mit dynamischer Whitelist"""
        preprocessed = self.preprocess_image(image)
        allowlist = get_dynamic_whitelist(self.valid_kurzel)
        reader = easyocr.Reader(['de', 'en'], gpu=False)
        result = reader.readtext(np.array(preprocessed), allowlist=allowlist)
        
        if result:
            best = max(result, key=lambda x: x[2])
            return {'text': best[1], 'confidence': best[2], 'raw_text': best[1], 'method': 'improved'}
        return {'text': None, 'confidence': 0.0, 'raw_text': '', 'method': 'improved'}
    
    def correct_text(self, text):
        """Dynamische Text-Korrektur basierend auf aktuellen gültigen Kürzeln"""
        text = re.sub(r'[^A-Z0-9\-]', '', text)
        
        for old, new in self.char_replacements.items():
            text = text.replace(old, new)
        
        for wrong, correct in self.common_fixes.items():
            if wrong in text:
                text = text.replace(wrong, correct)
        
        text = text.replace('Z', '2')
        for i in range(5, 10):
            text = text.replace(str(i), '1')
        text = text.replace('0', '1')
        
        if text in self.valid_kurzel:
            return text
        
        corrected_text = correct_alternative_kurzel(text, self.alternative_kurzel)
        if corrected_text != text and corrected_text in self.valid_kurzel:
            return corrected_text
        
        matches = get_close_matches(text, self.valid_kurzel, n=1, cutoff=0.8)
        if matches:
            return matches[0]
        
        return None


def sync_valid_codes():
    """Synchronisiert die gültigen Codes zwischen verschiedenen Speicherorten"""
    try:
        text_codes = []
        if os.path.isfile(CODE_FILE):
            with open(CODE_FILE, 'r', encoding='utf-8') as f:
                text_codes = [line.strip() for line in f if line.strip()]
        
        json_config = load_json_config()
        json_codes = json_config.get('valid_kurzel', [])
        
        if text_codes != json_codes:
            if text_codes:
                json_config['valid_kurzel'] = text_codes
                save_json_config(json_config)
                print(f"Codes synchronisiert - Text-Datei: {len(text_codes)}, JSON: {len(json_codes)}")
            elif json_codes:
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
    
    if text in valid_kurzel:
        return True, "Exakte Übereinstimmung"
    
    if not re.match(r'^[A-Z0-9\-]+$', text):
        return False, "Ungültige Zeichen enthalten"
    
    if re.search(r'[5-9]', text):
        return False, "Ungültige Zahlen (nur 1-4 erlaubt)"
    
    if '0' in text:
        return False, "0 nicht in gültigen Kürzeln"
    
    if 'Z' in text:
        return False, "Z wird zu 2 korrigiert"
    
    return True, "Struktur gültig, aber kein exakter Match"


def old_ocr_method(image_path, valid_kurzel, alternative_kurzel=None):
    """Alte OCR-Methode als Fallback"""
    try:
        img = Image.open(image_path)
        cimg = img.crop((10, 55, 110, 105))
        cimg = cimg.convert('L')
        cimg_np = np.array(cimg)
        _, bw = cv2.threshold(cimg_np, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        reader = get_reader()
        allow = get_dynamic_whitelist(valid_kurzel)
        
        char_replacements = {
            'I': '1', 'O': '0', '|': '1', 'l': '1', 'i': '1',
            'S': '5', 'G': '6', 'B': '8', 'Z': '2', 'z': '2',
            'D': '0', 'Q': '0', 'U': '0',
            'A': '4', 'E': '3', 'F': '7', 'T': '7'
        }
        
        res = reader.readtext(bw, detail=0, allowlist=allow)
        text = ''.join(res).upper()
        
        for old, new in char_replacements.items():
            text = text.replace(old, new)
        
        text = text.replace('Z', '2')
        
        for i in range(5, 10):
            text = text.replace(str(i), '1')
        text = text.replace('0', '1')
        
        if alternative_kurzel:
            corrected_text = correct_alternative_kurzel(text, alternative_kurzel)
            if corrected_text != text and corrected_text in valid_kurzel:
                final = corrected_text
            else:
                match = get_close_matches(text, valid_kurzel, n=1, cutoff=0.7)
                final = match[0] if match else text
        else:
            match = get_close_matches(text, valid_kurzel, n=1, cutoff=0.7)
            final = match[0] if match else text
        
        return {
            'text': final,
            'confidence': 0.5,
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


def enhanced_old_method(image_path, valid_kurzel, alternative_kurzel=None):
    """Erweiterte OCR-Methode mit mehreren Preprocessing-Varianten"""
    try:
        img = Image.open(image_path)
        cimg = img.crop((10, 55, 110, 105))
        
        allow = get_dynamic_whitelist(valid_kurzel)
        
        char_replacements = {
            'I': '1', 'O': '0', '|': '1', 'l': '1', 'i': '1',
            'S': '5', 'G': '6', 'B': '8', 'Z': '2', 'z': '2',
            'D': '0', 'Q': '0', 'U': '0',
            'A': '4', 'E': '3', 'F': '7', 'T': '7',
            'H': 'H', 'L': 'L', 'P': 'P', 'R': 'R', 'C': 'C'
        }
        
        preprocessing_variants = []
        
        cimg_gray = cimg.convert('L')
        cimg_np = np.array(cimg_gray)
        _, bw1 = cv2.threshold(cimg_np, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        preprocessing_variants.append(('original', bw1))
        
        enhancer = ImageEnhance.Contrast(cimg_gray)
        cimg_contrast = enhancer.enhance(2.0)
        cimg_contrast_np = np.array(cimg_contrast)
        _, bw2 = cv2.threshold(cimg_contrast_np, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        preprocessing_variants.append(('contrast', bw2))
        
        kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
        cimg_sharp = cv2.filter2D(cimg_np, -1, kernel)
        _, bw3 = cv2.threshold(cimg_sharp, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        preprocessing_variants.append(('sharp', bw3))
        
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        cimg_morph = cv2.morphologyEx(cimg_np, cv2.MORPH_CLOSE, kernel)
        _, bw4 = cv2.threshold(cimg_morph, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        preprocessing_variants.append(('morph', bw4))
        
        reader = get_reader()
        best_result = None
        best_confidence = 0
        best_variant = 'original'
        
        for variant_name, processed_img in preprocessing_variants:
            try:
                res = reader.readtext(processed_img, detail=0, allowlist=allow)
                text = ''.join(res).upper()
                
                for old, new in char_replacements.items():
                    text = text.replace(old, new)
                
                text = text.replace('Z', '2')
                
                for i in range(5, 10):
                    text = text.replace(str(i), '1')
                text = text.replace('0', '1')
                
                if alternative_kurzel:
                    corrected_text = correct_alternative_kurzel(text, alternative_kurzel)
                    if corrected_text != text and corrected_text in valid_kurzel:
                        final = corrected_text
                        confidence = 0.9
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
                
                cutoffs = [0.6, 0.7, 0.8, 0.9]
                for cutoff in cutoffs:
                    match = get_close_matches(text, valid_kurzel, n=1, cutoff=cutoff)
                    if match:
                        final = match[0]
                        confidence = cutoff
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
                
                if not match and text.strip():
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


# --------- Batch-Helfer (für Multicore) ---------
def _dp_from_dict(dp_dict: dict) -> DetectParams:
    try:
        dp = DetectParams()
        for k, v in (dp_dict or {}).items():
            if hasattr(dp, k):
                try:
                    setattr(dp, k, type(getattr(dp, k))(v))
                except Exception:
                    pass
        return dp
    except Exception:
        return DetectParams()


def process_single_image_for_batch(args: dict) -> dict:
    """Verarbeitet ein einzelnes Bild für die Batch-OCR (für ProcessPoolExecutor).

    Args dict keys:
        - path: str
        - dp: dict (DetectParams as dict)
        - valid_kurzel: list[str]
        - enable_post_processing: bool
        - char_mappings: dict

    Returns dict:
        { 'filename': str, 'path': str, 'text': str, 'box': (x,y,w,h) or None,
          'search_rect': (x0,y0,x1,y1) or None, 'error': str or None }
    """
    try:
        path = args.get('path')
        dp = _dp_from_dict(args.get('dp') or {})
        valid_kurzel = args.get('valid_kurzel') or []
        enable_pp = bool(args.get('enable_post_processing', True))
        char_mappings = args.get('char_mappings') or None

        img = Image.open(path)
        import numpy as np, cv2
        img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

        # Box suchen
        box = find_text_box_easyocr(img_cv, detect_params=dp, valid_kurzel=valid_kurzel)

        # Fallback: Suchbereich aus dp
        if box is None:
            H, W = img_cv.shape[:2]
            x0 = int(W * dp.left_frac)
            y0 = int(H * dp.top_frac)
            x1 = int(W * (1.0 - dp.right_frac))
            y1 = int(H * (1.0 - dp.bottom_frac))
            crop = img_cv[y0:y1, x0:x1]
            search_rect = (x0, y0, x1, y1)
        else:
            x, y, w, h = box
            crop = img_cv[y:y+h, x:x+w]
            search_rect = None

        text, _ = run_ocr_easyocr_improved(crop, enable_post_processing=enable_pp, char_mappings=char_mappings)

        return {
            'filename': os.path.basename(path),
            'path': path,
            'text': text,
            'box': box,
            'search_rect': search_rect,
            'error': None
        }
    except Exception as e:
        return {
            'filename': os.path.basename(args.get('path', '')),
            'path': args.get('path', ''),
            'text': None,
            'box': None,
            'search_rect': None,
            'error': str(e)
        }
