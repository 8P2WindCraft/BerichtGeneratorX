# Modulstruktur - GearGeneGPT

## 📁 Dateiübersicht

```
BerichtGeneratorX/
├── main.py                          # 🚀 Entry Point (90 Zeilen)
├── constants.py                     # 📊 Konstanten (120 Zeilen)
├── utils_helpers.py                 # 🔧 Hilfsfunktionen (38 Zeilen)
├── utils_logging.py                 # 📝 Logging-System (106 Zeilen)
├── utils_csv.py                     # 📋 CSV-Verarbeitung (64 Zeilen)
├── utils_exif.py                    # 📷 EXIF-Verwaltung (96 Zeilen)
├── config_manager.py                # ⚙️ Konfiguration (570 Zeilen)
├── core_kurzel.py                   # 🏷️ Kürzel-Management (198 Zeilen)
├── core_ocr.py                      # 🔍 OCR-Engine (554 Zeilen)
├── gui_dialogs.py                   # 💬 Dialoge (415 Zeilen)
├── gui_components.py                # 🧩 GUI-Komponenten (142 Zeilen)
├── gui_main.py                      # 🖥️ Hauptanwendung (6.367 Zeilen)
│
├── BildAnalysaturEXiff-V3_legacy.py # 📦 Original (Archiv)
└── REFACTORING_README.md            # 📖 Dokumentation
```

## 🔗 Import-Hierarchie

```
main.py
  ├─→ gui_components.LoadingScreen
  └─→ gui_main.OCRReviewApp
       ├─→ constants.*
       ├─→ config_manager.config_manager
       ├─→ core_ocr.ImprovedOCR, get_reader, ...
       ├─→ core_kurzel.KurzelTableManager
       ├─→ utils_exif.get/save_exif_usercomment
       ├─→ utils_logging.logger, write_detailed_log, ...
       ├─→ utils_helpers.resource_path
       ├─→ gui_dialogs.AlternativeKurzelDialog, ExcelGrunddatenDialog
       └─→ gui_components.LoadingScreen, AnalysisWindow
```

## 📦 Modul-Details

### Core Layer (Geschäftslogik)

**config_manager.py**
- `CentralConfigManager` - Zentrale Konfigurationsverwaltung
- `config_manager` - Globale Singleton-Instanz
- `load_json_config()`, `save_json_config()` - Kompatibilitätsfunktionen

**core_kurzel.py**
- `KurzelTableManager` - Erweiterte Kürzel-Verwaltung
- CSV-Import/Export
- Kategorisierung und Suche

**core_ocr.py**
- `ImprovedOCR` - Hauptklasse für OCR-Verarbeitung
- `get_reader()` - Singleton für EasyOCR Reader
- `old_ocr_method()`, `enhanced_old_method()` - Fallback-Methoden
- Hilfsfunktionen für Whitelist und Korrektur

### Utils Layer (Hilfsfunktionen)

**utils_helpers.py**
- `resource_path()` - Pfadauflösung (PyInstaller-kompatibel)
- `normalize_header()` - CSV-Header-Normalisierung

**utils_logging.py**
- `setup_logging()` - Logger-Konfiguration
- `write_detailed_log()` - Detaillierte Logs
- `write_log_entry()` - OCR-Logs
- `logger` - Globaler Logger

**utils_csv.py**
- `detect_csv_encoding()` - Automatische Encoding-Erkennung
- `safe_csv_open()` - Sicheres CSV-Öffnen

**utils_exif.py** ⚠️ **KRITISCH**
- `get_exif_usercomment()` - JSON aus EXIF lesen
- `save_exif_usercomment()` - JSON in EXIF speichern
- **100% kompatibel mit bestehendem Format!**

### Constants Layer

**constants.py**
- `DEFAULT_KURZEL` - Standard-Kürzel-Liste
- `DAMAGE_CATEGORIES`, `IMAGE_TYPES` - Kategorien
- `COLORS`, `FONT_SIZES` - Design-System
- Fenstergrößen und Thumbnails

### GUI Layer

**main.py**
- `main()` - Hauptfunktion
- LoadingScreen-Integration
- Threading für Initialisierung

**gui_components.py**
- `LoadingScreen` - Animierter Ladebildschirm
- `AnalysisWindow` - OCR-Analyse-Fenster (Platzhalter)

**gui_dialogs.py**
- `AlternativeKurzelDialog` - Kürzel-Bearbeitung
- `ExcelGrunddatenDialog` - Excel-Import mit Fortschritt

**gui_main.py** 🖥️ **HAUPTKOMPONENTE**
- `OCRReviewApp` - Hauptanwendungsklasse
- Alle UI-Features:
  - Tab-Navigation (Einzelbild/Galerie)
  - Canvas mit Zoom & Pan
  - Zeichenwerkzeuge (Pfeil, Kreis, Rechteck)
  - Bewertungssystem
  - Fortschrittsanzeige
  - Kürzel-Manager
  - EXIF-Verwaltung
  - Navigation & Shortcuts

## 🎯 Startpunkt

```bash
python main.py
```

## 📝 Hinweise

1. **Kompatibilität**: Alle bestehenden EXIF-Daten und Configs funktionieren weiterhin
2. **Performance**: Keine Verschlechterung durch Modularisierung
3. **Wartbarkeit**: Deutlich verbessert durch klare Trennung
4. **Erweiterbarkeit**: Neue Features können in passenden Modulen ergänzt werden

## 🔮 Zukünftige Optimierungen

`gui_main.py` könnte weiter modularisiert werden in:
- `gui_toolbar.py` - Menüleiste
- `gui_canvas.py` - Bildanzeige
- `gui_zoom.py` - Zoom-Logik
- `gui_drawing.py` - Zeichenwerkzeuge
- `gui_evaluation.py` - Bewertungs-UI
- `gui_navigation.py` - Bildnavigation
- `gui_gallery.py` - Galerie-Ansicht

**Priorität**: Niedrig (aktueller Stand ist bereits sehr gut!)

---

**Erstellt**: 2025-10-12
**Version**: 2.0 (Refactored)


