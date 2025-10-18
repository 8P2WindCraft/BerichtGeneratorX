#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Logging-Konfiguration und Log-Funktionen
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
import traceback

from constants import MAX_LOG_FILE_SIZE, LOG_BACKUP_COUNT
from utils_helpers import resource_path


# Log-Verzeichnis bestimmen
if getattr(sys, 'frozen', False):
    log_dir = os.path.dirname(sys.executable)
else:
    log_dir = os.path.dirname(os.path.abspath(__file__))

# Log-Datei Pfade
LOG_FILE = os.path.join(log_dir, 'ocr_log.txt')
DETAILED_LOG_FILE = os.path.join(log_dir, 'detailed_log.txt')
LAST_FOLDER_FILE = os.path.join(log_dir, 'last_folder.txt')


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


