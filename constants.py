#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Konstanten und Konfigurationswerte für BildAnalysaturEXiff
"""

from dataclasses import dataclass

# Kürzel-Listen - Alle Kürzel kommen jetzt nur noch aus der Kürzel-Tabelle
# DEFAULT_KURZEL wurde entfernt - nur noch Kürzel-Tabelle wird verwendet

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

# Konstanten für Magic Numbers
THUMBNAIL_WIDTH = 150
THUMBNAIL_HEIGHT = 100
THUMBNAIL_LARGE_WIDTH = 300
THUMBNAIL_LARGE_HEIGHT = 200
THUMBNAIL_MEDIUM_WIDTH = 200
THUMBNAIL_MEDIUM_HEIGHT = 150
THUMBNAIL_SMALL_WIDTH = 32
THUMBNAIL_SMALL_HEIGHT = 32
THUMBNAIL_DISPLAY_WIDTH = 400
THUMBNAIL_DISPLAY_HEIGHT = 300

# Fenster-Größen
DEBUG_PREVIEW_WIDTH = 800
DEBUG_PREVIEW_HEIGHT = 600
DIALOG_WIDTH = 800
DIALOG_HEIGHT = 600
ANALYSIS_WINDOW_WIDTH = 600
ANALYSIS_WINDOW_HEIGHT = 400
MAIN_WINDOW_WIDTH = 1080
MAIN_WINDOW_HEIGHT = 800
LOG_WINDOW_WIDTH = 1000
LOG_WINDOW_HEIGHT = 700
LOG_WINDOW_SMALL_WIDTH = 800
LOG_WINDOW_SMALL_HEIGHT = 600
JSON_WINDOW_WIDTH = 1000
JSON_WINDOW_HEIGHT = 700
PROGRESS_WINDOW_WIDTH = 400
PROGRESS_WINDOW_HEIGHT = 150
FEEDBACK_WINDOW_WIDTH = 200
FEEDBACK_WINDOW_HEIGHT = 100
INFO_WINDOW_WIDTH = 600
INFO_WINDOW_HEIGHT = 500
LOADING_WINDOW_WIDTH = 500
LOADING_WINDOW_HEIGHT = 400
EDIT_DIALOG_WIDTH = 400
EDIT_DIALOG_HEIGHT = 300

# Andere Konstanten
MAX_CSV_TEST_LINES = 10
MAX_LOG_FILE_SIZE = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5

# Professionelles Farbschema
COLORS = {
    'primary': '#1565C0',      # Dunkles Blau (Primäraktionen)
    'primary_hover': '#0D47A1', # Noch dunkler für Hover
    'secondary': '#424242',     # Dunkelgrau (Sekundäraktionen)
    'secondary_hover': '#212121',
    'success': '#2E7D32',       # Grün (Erfolg/OK)
    'success_hover': '#1B5E20',
    'warning': '#F57C00',       # Orange (Warnung)
    'warning_hover': '#E65100',
    'danger': '#C62828',        # Rot (Gefahr/Skip)
    'danger_hover': '#B71C1C',
    'info': '#0277BD',          # Info-Blau
    'info_light': '#E3F2FD',    # Helles Info-Blau für Flächen
    'bg_light': '#FAFAFA',      # Heller Hintergrund
    'bg_medium': '#F5F5F5',     # Mittlerer Hintergrund
    'border': '#E0E0E0',        # Rahmenfarbe
    'text_primary': '#212121',  # Haupttext
    'text_secondary': '#757575' # Sekundärtext
}

# Standardisierte Schriftgrößen
FONT_SIZES = {
    'title': 14,
    'heading': 12,
    'body': 10,
    'small': 9,
    'tiny': 8
}


# Parameter für die automatische Box-Detektion (Analyse-Fenster)
@dataclass
class DetectParams:
    top_frac: float = 0.0
    bottom_frac: float = 0.20
    left_frac: float = 0.0
    right_frac: float = 0.18

    min_area_frac: float = 0.001  # Optimiert für kleine Kürzel auf weißem Hintergrund
    max_area_frac: float = 0.5    # Erlaubt größere weiße Kästen (bis 50% des Bildes)

    min_aspect: float = 0.8       # Etwas breiter als hoch erlaubt
    max_aspect: float = 4.0       # Bis zu 4x breiter als hoch

    padding_top: int = -2
    padding_bottom: int = -2
    padding_left: int = -2
    padding_right: int = -2

    enable_post_processing: bool = True

