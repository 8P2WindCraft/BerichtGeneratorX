#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hilfsfunktionen und Konstanten für GearGeneGPT
"""

import os
import sys

def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), relative_path)

# Dateipfade
if getattr(sys, 'frozen', False):
    log_dir = os.path.dirname(sys.executable)
else:
    log_dir = os.path.dirname(os.path.abspath(__file__))

CODE_FILE = resource_path('valid_kurzel.txt')
JSON_CONFIG_FILE = resource_path('GearBoxExiff.json')
LOG_FILE = os.path.join(log_dir, 'ocr_log.txt')
DETAILED_LOG_FILE = os.path.join(log_dir, 'detailed_log.txt')
LAST_FOLDER_FILE = os.path.join(log_dir, 'last_folder.txt')

