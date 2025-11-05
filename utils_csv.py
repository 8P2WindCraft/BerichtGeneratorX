#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSV-bezogene Funktionen
"""

import os
from constants import MAX_CSV_TEST_LINES
from utils_logging import get_logger
logger = get_logger('app', {"module": "utils_csv"})


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


