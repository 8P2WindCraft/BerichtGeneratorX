#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OCR-Verarbeitung - Vereinfachte Version
Nur eine OCR-Methode: Feste Koordinaten + EasyOCR mit Upscaling
"""

import os
import cv2
import numpy as np
import easyocr
from PIL import Image
from difflib import get_close_matches

from utils_logging import get_logger

log_app = get_logger('app', {"module": "core_ocr"})
log_ocr = get_logger('ocr', {"module": "core_ocr"})

# Globaler EasyOCR Reader (Singleton-Pattern für Performance)
_READER = None


def get_reader():
    """Holt oder erstellt den globalen EasyOCR Reader (Singleton)"""
    global _READER
    if _READER is None:
        _READER = easyocr.Reader(['de', 'en'], gpu=False)
        log_ocr.info("easyocr.Reader initialisiert", extra={"lang": ["de","en"], "event": "ocr_reader"})
    return _READER


def get_dynamic_whitelist(valid_kurzel):
    """Erstellt eine dynamische Whitelist aus gültigen Kürzeln"""
    if not valid_kurzel:
        return None
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


def run_ocr_simple(image_path, valid_kurzel, alternative_kurzel=None, 
                   enable_char_replacements=True, enable_number_normalization=True, 
                   fuzzy_cutoff=0.7):
    """
    Einzige OCR-Methode - basierend auf label_ocr_gui.py
    
    Workflow:
    1. Feste Koordinaten (10, 55, 110, 105) ausschneiden
    2. Graustufenkonvertierung
    3. OTSU Threshold
    4. Upscaling (2x) für bessere Erkennung
    5. EasyOCR mit dynamic whitelist
    6. Character Replacements (optional)
    7. Zahlen-Normalisierung (optional)
    8. Fuzzy Matching gegen valid_kurzel
    """
    try:
        # 1. Bild laden und Crop ausschneiden
        img = Image.open(image_path)
        cimg = img.crop((10, 55, 110, 105))
        
        # 2. Graustufenkonvertierung
        cimg = cimg.convert('L')
        cimg_np = np.array(cimg)
        
        # 3. OTSU Threshold
        _, bw = cv2.threshold(cimg_np, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # 4. Upscaling für bessere Erkennung
        upscaled = upscale_crop(bw, scale_factor=2.0)
        
        # 5. EasyOCR Reader initialisieren
        reader = get_reader()
        allow = get_dynamic_whitelist(valid_kurzel)
        
        # 6. OCR ausführen
        res = reader.readtext(upscaled, detail=0, allowlist=allow)
        text = ''.join(res).upper()
        
        log_ocr.info("ocr_raw_text", extra={"text": text, "path": os.path.basename(image_path)})
        
        # 7. Character Replacements (optional)
        if enable_char_replacements:
            char_replacements = {
                'I': '1', 'O': '0', '|': '1', 'l': '1', 'i': '1',
                'S': '5', 'G': '6', 'B': '8', 'Z': '2', 'z': '2',
                'D': '0', 'Q': '0', 'U': '0',
                'A': '4', 'E': '3', 'F': '7', 'T': '7'
            }
            
            for old, new in char_replacements.items():
                text = text.replace(old, new)
            
            text = text.replace('Z', '2')
        
        # 8. Zahlen-Normalisierung (optional)
        if enable_number_normalization:
            for i in range(5, 10):
                text = text.replace(str(i), '1')
            text = text.replace('0', '1')
        
        # 9. Alternative Kürzel-Korrektur
        if alternative_kurzel:
            corrected_text = correct_alternative_kurzel(text, alternative_kurzel)
            if corrected_text != text and corrected_text in valid_kurzel:
                final = corrected_text
                log_ocr.info("alternative_kurzel_match", extra={"original": text, "corrected": final})
            else:
                match = get_close_matches(text, valid_kurzel, n=1, cutoff=fuzzy_cutoff)
                final = match[0] if match else text
                if match:
                    log_ocr.info("fuzzy_match", extra={"original": text, "matched": final, "cutoff": fuzzy_cutoff})
        else:
            match = get_close_matches(text, valid_kurzel, n=1, cutoff=fuzzy_cutoff)
            final = match[0] if match else text
            if match:
                log_ocr.info("fuzzy_match", extra={"original": text, "matched": final, "cutoff": fuzzy_cutoff})
        
        return {
            'text': final,
            'confidence': 0.75,  # Höhere Confidence wegen Upscaling
            'method': 'simple_upscaled',
            'raw_text': text
        }
    except Exception as e:
        log_ocr.error("ocr_error", extra={"error": str(e), "path": os.path.basename(image_path)})
        return {
            'text': None,
            'confidence': 0.0,
            'method': 'error',
            'raw_text': str(e)
        }


def process_single_image_for_batch(args: dict) -> dict:
    """
    Verarbeitet ein einzelnes Bild für die Batch-OCR.
    Verwendet die vereinfachte OCR-Methode.
    """
    try:
        path = args.get('path')
        valid_kurzel = args.get('valid_kurzel') or []
        alternative_kurzel = args.get('alternative_kurzel') or {}
        enable_char_replacements = args.get('enable_char_replacements', True)
        enable_number_normalization = args.get('enable_number_normalization', True)
        fuzzy_cutoff = args.get('fuzzy_cutoff', 0.7)

        # Vereinfachte OCR-Methode verwenden
        ocr_result = run_ocr_simple(
            path, 
            valid_kurzel,
            alternative_kurzel=alternative_kurzel,
            enable_char_replacements=enable_char_replacements,
            enable_number_normalization=enable_number_normalization,
            fuzzy_cutoff=fuzzy_cutoff
        )
        
        result = {
            'filename': os.path.basename(path),
            'path': path,
            'text': ocr_result.get('text', ''),
            'box': None,  # Keine Box-Suche
            'search_rect': None,
            'confidence': ocr_result.get('confidence', 0.0),
            'replacements': [],
            'error': None
        }
        
        # Auto in EXIF speichern, wenn sinnvoller Text vorhanden
        try:
            if result['text'] and not result['text'].startswith('['):
                from utils_exif import set_ocr_info
                set_ocr_info(path, tag=result['text'], confidence=result['confidence'], box=None)
        except Exception:
            pass
        
        return result
    except Exception as e:
        log_ocr.error("batch_process_error", extra={"error": str(e), "path": args.get('path', '')})
        return {
            'filename': os.path.basename(args.get('path', '')),
            'path': args.get('path', ''),
            'text': None,
            'box': None,
            'search_rect': None,
            'confidence': 0.0,
            'replacements': [],
            'error': str(e)
        }





