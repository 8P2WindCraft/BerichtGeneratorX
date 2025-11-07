# -*- coding: utf-8 -*-
from PySide6.QtCore import QObject, Signal, QSettings
from PySide6.QtWidgets import QApplication
from utils_logging import get_logger
import copy
import json
import os
import ast


class SettingsManager(QObject):
    """Zentraler Settings-Manager für die gesamte App"""
    
    settingsChanged = Signal(dict)  # Signal für Einstellungsänderungen
    
    def __init__(self):
        super().__init__()
        self._log = get_logger('app', {"module": "qtui.settings_manager"})
        self._log.info("module_started", extra={"event": "module_started"})
        
        # QSettings für persistente Speicherung
        self.settings = QSettings("BerichtGeneratorX", "Settings")
        
        # Standard-Einstellungen
        self.defaults = {
            "dark_mode": False,  # Dark Mode standardmäßig aus
            "language": "English",  # Standard: English
            "show_keyboard_shortcuts": True,  # Tastaturkürzel in Buttons anzeigen
            # Zeige im Bild-Overlay nur den reinen OCR-Tag (Standard: False)
            # Wenn True, wird zusätzlich die Überschrift aus der Kürzel-Tabelle angezeigt
            "tag_overlay_heading": False,
            # Reihenfolge der Anzeige: 'below' = Code dann Überschrift, 'above' = Überschrift dann Code
            "tag_heading_order": "below",
            # Which language to normalize metadata to when saving
            # Values: "UI" (follow current UI language), "de", "en"
            "metadata_language": "UI",
            "last_folder": "",
            "auto_save": True,
            "save_interval": 5,
            "ocr_method": "Alte Methode (ohne Box-Suche)",
            "debug_preview": False,
            "gallery_tag_size": 8,
            "single_tag_size": 9,
            "tag_opacity": 200,
            "gallery_overlay_icon_scale": 1.0,  # Skalierungsfaktor für Overlay-Icons in Galerie (0.5 - 2.0)
            "theme": "System",
            "navigation_position": "below",  # "overlay" oder "below"
            "thumb_size": 160,
            "thumb_quality": 85,
            # image_quality ENTFERNT - Einzelansicht zeigt immer Original ohne Kompression
            "zoom_factor": 1.0,
            "crop_x": 100,
            "crop_y": 50,
            "crop_w": 200,
            "crop_h": 100,
            
            # Multi-Threading Einstellungen
            "max_workers": max(1, os.cpu_count() // 4) if os.cpu_count() else 2,
            "ocr_timeout": 30,  # Sekunden
            
            # OCR Auto-Korrektur Einstellungen
            "fuzzy_matching_cutoff": 0.7,  # Wert für get_close_matches
            "enable_char_replacements": True,  # Auto-Korrektur aktivieren
            "char_replacements_text": "I=1\nO=0\n|=1\nl=1\ni=1\nS=5\nG=6\nB=8\nZ=2\nz=2\nD=0\nQ=0\nU=0\nA=4\nE=3\nF=7\nT=7",
            "enable_number_normalization": True,  # Zahlen 5-9→1, 0→1
            
            # OCR ROI Einstellungen
            "ocr_roi_top": 0.0,
            "ocr_roi_bottom": 0.20,
            "ocr_roi_left": 0.0,
            "ocr_roi_right": 0.18,

            # OCR Detection Mode und Padding
            "ocr_detection_mode": "easyocr_box",  # Optionen: easyocr_box | white_box
            "ocr_padding_top": 0,
            "ocr_padding_bottom": 0,
            "ocr_padding_left": 0,
            "ocr_padding_right": 0,
            
            # Kürzel-Tabelle (wie im ursprünglichen Programm)
            "kurzel_table": {
                "HSS": {"kurzel_code": "HSS", "active": True, "frequency": 0, "order": 0},
                "HS5": {"kurzel_code": "HS5", "active": True, "frequency": 0, "order": 1},
                "HS6": {"kurzel_code": "HS6", "active": True, "frequency": 0, "order": 2},
                "HS7": {"kurzel_code": "HS7", "active": True, "frequency": 0, "order": 3},
                "HS8": {"kurzel_code": "HS8", "active": True, "frequency": 0, "order": 4},
                "HS9": {"kurzel_code": "HS9", "active": True, "frequency": 0, "order": 5},
                "HS0": {"kurzel_code": "HS0", "active": True, "frequency": 0, "order": 6},
                "HS1": {"kurzel_code": "HS1", "active": True, "frequency": 0, "order": 7},
                "HS2": {"kurzel_code": "HS2", "active": True, "frequency": 0, "order": 8},
                "HS3": {"kurzel_code": "HS3", "active": True, "frequency": 0, "order": 9},
                "HS4": {"kurzel_code": "HS4", "active": True, "frequency": 0, "order": 10}
            },
            "text_snippets": {
                "tags": {},
                "groups": {}
            },
            
            # Schadenskategorien (Deutsch und Englisch)
            "damage_categories_de": [
                "Visuell keine Defekte", "Kratzer", "Zykloidische Kratzer", "Stillstandsmarken",
                "Verschmierung", "Partikeldurchgang", "Überrollmarken", "Pittings", "Sonstige"
            ],
            "damage_categories_en": [
                "Visually no defects", "Scratches", "Cycloid Scratches", "Standstill marks",
                "Smearing", "Particle passage", "Overrolling Marks", "Pitting", "Others"
            ],
            "damage_categories": [  # Aktuelle Sprache (zur Kompatibilität)
                "Visuell keine Defekte", "Kratzer", "Zykloidische Kratzer", "Stillstandsmarken",
                "Verschmierung", "Partikeldurchgang", "Überrollmarken", "Pittings", "Sonstige"
            ],
            
            # Bildart-Kategorien (Deutsch und Englisch)
            "image_types_de": [
                "Wälzkörper", "Innenring", "Außenring", "Käfig", "Zahnrad"
            ],
            "image_types_en": [
                "Rolling Element", "Inner ring", "Outer ring", "Cage", "Gear"
            ],
            "image_types": [  # Aktuelle Sprache (zur Kompatibilität)
                "Wälzkörper", "Innenring", "Außenring", "Käfig", "Zahnrad"
            ],
            
            # Bildqualitäts-Optionen (Deutsch und Englisch)
            "image_quality_options_de": [
                "Gut", "Normal", "Schlecht", "Verschleiß", "Beschädigt", "Unbekannt"
            ],
            "image_quality_options_en": [
                "Good", "Normal", "Poor", "Traces of wear", "Damage", "Unknown"
            ],
            "image_quality_options": [  # Aktuelle Sprache (zur Kompatibilität)
                "Gut", "Normal", "Schlecht", "Verschleiß", "Beschädigt", "Unbekannt"
            ],
            
            # Bild verwenden Optionen (Deutsch und Englisch)
            "use_image_options_de": ["ja", "nein"],
            "use_image_options_en": ["yes", "no"],
            "use_image_options": ["ja", "nein"],  # Aktuelle Sprache
            
            # Gültige Kürzel (aus dem alten Programm)
            "valid_kurzel": [
                'HSS', 'HSSR', 'HSSGR', 'HSSGG', 'LSS', 'LSSR', 'LSSGR', 'LSSGG',
                'PLC2GR', 'PLC2GG', 'PLC2R', 'RG2', 'SUN2', 'PL2-1', 'PLB2G-1', 'PLB2R-1',
                'PL2-2', 'PLB2G-2', 'PLB2R-2', 'PL2-3', 'PLB2G-3', 'PLB2R-3',
                'PLC1G', 'PLC1R', 'RG1', 'SUN1', 'PL1-1', 'PLB1G-1', 'PLB1R-1',
                'PL1-2', 'PLB1G-2', 'PLB1R-2', 'PL1-3', 'PLB1G-3', 'PLB1R-3',
                'PL1-4', 'PLB1G-4', 'PLB1R-4'
            ],

            # Bereichs-Reihenfolge für die Vorschau/Gliederung
            "section_order": [
                "Planetenstufe 1",
                "Planetenstufe 2",
                "Planetenstufe 3",
                "Low Speed Shaft",
                "High Speed Shaft"
            ],

            # Überschriften zweisprachig (gleiche Reihenfolge wie section_order)
            "section_titles_de": [
                "Planetenstufe 1",
                "Planetenstufe 2",
                "Planetenstufe 3",
                "Niedriggeschwindigkeitswelle",
                "Hochgeschwindigkeitswelle"
            ],
            "section_titles_en": [
                "Planetary Stage 1",
                "Planetary Stage 2",
                "Planetary Stage 3",
                "Low Speed Shaft",
                "High Speed Shaft"
            ],

            # Zuordnung: Bereich -> Liste der zugehörigen Kürzel
            "section_kurzel_map": {
                "Planetenstufe 1": [
                    "PLC1G", "PLC1R", "RG1", "SUN1",
                    "PL1-1", "PLB1G-1", "PLB1R-1",
                    "PL1-2", "PLB1G-2", "PLB1R-2",
                    "PL1-3", "PLB1G-3", "PLB1R-3",
                    "PL1-4", "PLB1G-4", "PLB1R-4"
                ],
                "Planetenstufe 2": [
                    "PLC2GR", "PLC2GG", "PLC2R", "RG2", "SUN2",
                    "PL2-1", "PLB2G-1", "PLB2R-1",
                    "PL2-2", "PLB2G-2", "PLB2R-2",
                    "PL2-3", "PLB2G-3", "PLB2R-3"
                ],
                "Planetenstufe 3": [],
                "Low Speed Shaft": ["LSS", "LSSR", "LSSGR", "LSSGG"],
                "High Speed Shaft": [
                    "HSS", "HSSR", "HSSGR", "HSSGG",
                    "HS0", "HS1", "HS2", "HS3", "HS4",
                    "HS5", "HS6", "HS7", "HS8", "HS9"
                ]
            },
            
            # Alternative Kürzel (aus dem alten Programm)
            "alternative_kurzel": {
                "hss": "HSS", "hssr": "HSSR", "hssgr": "HSSGR", "hssgg": "HSSGG",
                "lss": "LSS", "lssr": "LSSR", "lssgr": "LSSGR", "lssgg": "LSSGG",
                "plc2gr": "PLC2GR", "plc2gg": "PLC2GG", "plc2r": "PLC2R",
                "rg2": "RG2", "sun2": "SUN2",
                "pl2-1": "PL2-1", "plb2g-1": "PLB2G-1", "plb2r-1": "PLB2R-1",
                "pl2-2": "PL2-2", "plb2g-2": "PLB2G-2", "plb2r-2": "PLB2R-2",
                "pl2-3": "PL2-3", "plb2g-3": "PLB2G-3", "plb2r-3": "PLB2R-3",
                "plc1g": "PLC1G", "plc1r": "PLC1R", "rg1": "RG1", "sun1": "SUN1",
                "pl1-1": "PL1-1", "plb1g-1": "PLB1G-1", "plb1r-1": "PLB1R-1",
                "pl1-2": "PL1-2", "plb1g-2": "PLB1G-2", "plb1r-2": "PLB1R-2",
                "pl1-3": "PL1-3", "plb1g-3": "PLB1G-3", "plb1r-3": "PLB1R-3",
                "pl1-4": "PL1-4", "plb1g-4": "PLB1G-4", "plb1r-4": "PLB1R-4"
            },
            
            # Kürzel-Kategorien (aus dem alten Programm)
            "kurzel_categories": {
                "Schmierung": {"description": "Schmierstellen und Schmiersysteme", "color": "#4CAF50", "icon": "🔧", "priority": 1},
                "Planetengetriebe": {"description": "Planetengetriebe-Komponenten", "color": "#2196F3", "icon": "⚙️", "priority": 2},
                "Ritzel": {"description": "Ritzel und Zahnräder", "color": "#FF9800", "icon": "🦷", "priority": 3}
            },
            
            # Kürzel-Details
            "kurzel_details": {},
            
            # Kürzel-Statistiken
            "kurzel_statistics": {
                "total_count": 0, "active_count": 0, "inactive_count": 0,
                "by_category": {}, "by_priority": {}, "by_frequency": {},
                "last_updated": ""
            },
            
            # Lokalisierung
            "localization_current_language": "en",
            "localization_available_languages": ["de", "en"],
            "localization_auto_detect_language": True,
            
            # Display-Einstellungen
            "display_window_width": 1080,
            "display_window_height": 800,
            "display_window_x": None,
            "display_window_y": None,
            "display_maximized": False,
            "display_save_window_position": True,
            "display_image_zoom": 1.0,
            "display_show_filename": True,
            "display_show_counter": True,
            "display_theme": "default",
            "display_font_size": 10,
            "display_filter_zero_codes": True,
            
            # Navigation-Einstellungen
            "navigation_auto_save": True,
            "navigation_confirm_unsaved": True,
            "navigation_keyboard_shortcuts": True,
            "navigation_auto_load_last_folder": True,
            "navigation_remember_last_image": True,
            
            # Projekt-Daten
            "project_windpark": "",
            "project_windpark_land": "",
            "project_sn": "",
            "project_anlagen_nr": "",
            "project_hersteller": "",
            "project_getriebe_hersteller": "",
            "project_hersteller_2": "",
            "project_modell": "",
            "project_gear_sn": "",
            
            # Benutzerdefinierte Felder
            "custom_field1": "",
            "custom_field2": "",
            "custom_field3": "",
            "custom_field4": "",
            "custom_field5": "",
            "custom_field6": "",
            
            # Export-Einstellungen
            "export_auto_backup": True,
            "export_backup_interval": 24,
            "export_format": "json",
            "export_include_exif_data": True,
            "export_include_statistics": True,
            "export_report_template": "default",
            
            # Performance-Einstellungen
            "performance_thumbnail_cache_size": 100,
            "performance_max_image_size": 2048,
            "performance_lazy_loading": True,
            "performance_cache_evaluation_data": True,
            "performance_max_cache_size": 1000,
            
            # Logging-Einstellungen
            "logging_log_level": "info",
            "logging_save_detailed_logs": True,
            "logging_log_rotation": True,
            "logging_max_log_size": 10,
            "logging_debug_mode": False,
            
            # Pfade
            "paths_last_folder": "",
            "paths_backup_directory": "Backups",
            "paths_log_directory": "logs",
            "paths_temp_directory": "temp",
            
            # Letzte Auswahlen
            "last_selections_open_folder": "",
            "last_selections_excel_file": "",
            "last_selections_analyze_folder": "",
            "last_selections_exif_folder": "",

            # Cover-Bildverwaltung
            "cover_tags": [
                "Getriebeansicht",
                "Ölansicht",
                "Ölstabansicht"
            ],
            "cover_images": {},
            "cover_last_folder": "",
            
            # Tag-Management
            "tag_management_auto_update_tags": True,
            "tag_management_tag_structure_file": "tag_structure.json",
            "tag_management_default_tag_structure": {},
            "tag_management_external_ocr_tags": {},
            
            # Metadaten
            "metadata_version": "2.0.0",
            "metadata_last_updated": "",
            "metadata_config_version": "2.0",
            "metadata_migration_history": []
        }
        
        # Cache für aktuelle Einstellungen
        self._cache = {}
        self._load_all_settings()
    
    def _load_all_settings(self):
        """Alle Einstellungen laden"""
        for key, default_value in self.defaults.items():
            # QSettings kann keine komplexen Typen (list, dict) direkt laden
            if isinstance(default_value, (list, dict)):
                raw = self.settings.value(key, default_value)
                self._cache[key] = self._normalize_value(raw, default_value)
            elif isinstance(default_value, bool):
                # Bool muss explizit konvertiert werden
                val = self.settings.value(key, default_value)
                self._cache[key] = val if isinstance(val, bool) else str(val).lower() in ('true', '1', 'yes')
            else:
                try:
                    self._cache[key] = self.settings.value(key, default_value, type(default_value))
                except TypeError:
                    self._cache[key] = default_value
        
        self._log.info("settings_loaded", extra={"event": "settings_loaded", "count": len(self._cache)})
    
    def get(self, key: str, default=None):
        """Einstellung abrufen"""
        if default is None:
            default = self.defaults.get(key)
        return self._cache.get(key, default)
    
    def set(self, key: str, value):
        """Einstellung setzen"""
        old_value = self._cache.get(key)
        self._cache[key] = value
        self.settings.setValue(key, value)
        
        # Signal senden wenn sich etwas geändert hat
        if old_value != value:
            self.settingsChanged.emit({key: value})
            self._log.info("setting_changed", extra={"event": "setting_changed", "key": key, "value": value})
    
    def get_all(self):
        """Alle Einstellungen als Dictionary zurückgeben"""
        return self._cache.copy()
    
    def set_all(self, settings_dict: dict):
        """Mehrere Einstellungen auf einmal setzen"""
        changed_settings = {}
        
        for key, value in settings_dict.items():
            if key in self.defaults:
                old_value = self._cache.get(key)
                self._cache[key] = value
                self.settings.setValue(key, value)
                
                if old_value != value:
                    changed_settings[key] = value
        
        if changed_settings:
            self.settingsChanged.emit(changed_settings)
            self._log.info("settings_bulk_changed", extra={"event": "settings_bulk_changed", "count": len(changed_settings)})
    
    def reset_to_defaults(self):
        """Alle Einstellungen auf Standard zurücksetzen"""
        self.set_all(self.defaults)
        self._log.info("settings_reset", extra={"event": "settings_reset"})
    
    def export_settings(self, file_path: str):
        """Einstellungen in JSON-Datei exportieren"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, indent=2, ensure_ascii=False)
            self._log.info("settings_exported", extra={"event": "settings_exported", "file": file_path})
            return True
        except Exception as e:
            self._log.error("settings_export_failed", extra={"event": "settings_export_failed", "error": str(e)})
            return False
    
    def import_settings(self, file_path: str):
        """Einstellungen aus JSON-Datei importieren"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                imported_settings = json.load(f)
            
            # Nur gültige Einstellungen übernehmen
            valid_settings = {}
            for key, value in imported_settings.items():
                if key in self.defaults:
                    valid_settings[key] = value
            
            self.set_all(valid_settings)
            self._log.info("settings_imported", extra={"event": "settings_imported", "file": file_path, "count": len(valid_settings)})
            return True
        except Exception as e:
            self._log.error("settings_import_failed", extra={"event": "settings_import_failed", "error": str(e)})
            return False
    
    # Convenience-Methoden für häufig verwendete Einstellungen
    def get_language(self):
        return self.get("language")
    
    def get_theme(self):
        return self.get("theme")
    
    def get_gallery_tag_size(self):
        return self.get("gallery_tag_size")
    
    def get_single_tag_size(self):
        return self.get("single_tag_size")
    
    def get_tag_opacity(self):
        return self.get("tag_opacity")
    
    def get_thumb_size(self):
        return self.get("thumb_size")
    
    def get_valid_kurzel(self):
        return self.get("valid_kurzel")
    
    def set_valid_kurzel(self, kurzel_list):
        """Kürzel-Liste setzen und validieren"""
        import re
        valid_kurzel = []
        for kurzel in kurzel_list:
            if isinstance(kurzel, str) and re.match(r'^[A-Z0-9-]+$', kurzel.upper()):
                valid_kurzel.append(kurzel.upper())
        
        self.set("valid_kurzel", valid_kurzel)
        return valid_kurzel
    
    def get_language_specific_list(self, list_type):
        """Holt eine sprachspezifische Liste basierend auf der aktuellen Sprache"""
        language = (self.get("language", "English") or "English").lower()
        suffix = "de" if language.startswith("deutsch") else "en"
        key = f"{list_type}_{suffix}"

        defaults = self._normalize_list_value(self.defaults.get(key, []))
        stored = self._normalize_list_value(self.get(key, []))
        combined = self._merge_defaults(defaults, stored)
        if combined != stored:
            self.set(key, combined)

        # auch generische Liste synchronisieren
        generic_defaults = self._normalize_list_value(self.defaults.get(list_type, []))
        generic_stored = self._normalize_list_value(self.get(list_type, []))
        generic_combined = self._merge_defaults(generic_defaults, combined)
        if generic_combined != generic_stored:
            self.set(list_type, generic_combined)

        return combined

    # Target language for normalizing metadata stored into EXIF JSON
    def get_metadata_target_lang(self) -> str:
        """Returns 'de' or 'en' based on preference/settings."""
        pref = str(self.get("metadata_language", "UI") or "UI").strip().lower()
        if pref in {"ui", "auto"}:
            lang = str(self.get("language", "English") or "English").strip().lower()
            return 'de' if lang.startswith('de') else 'en'
        if pref in {"de", "deutsch", "german"}:
            return 'de'
        return 'en'
    
    def get_damage_categories(self):
        """Holt die Schadenskategorien für die aktuelle Sprache"""
        return self.get_language_specific_list("damage_categories")
    
    def get_image_types(self):
        """Holt die Bildtypen für die aktuelle Sprache"""
        return self.get_language_specific_list("image_types")
    
    def get_image_quality_options(self):
        """Holt die Bildqualitäts-Optionen für die aktuelle Sprache"""
        return self.get_language_specific_list("image_quality_options")
    
    def get_use_image_options(self):
        """Holt die 'Bild verwenden'-Optionen für die aktuelle Sprache"""
        return self.get_language_specific_list("use_image_options")

    # ------------------------------------------------------------------
    # Textbausteine
    def get_text_snippet_config(self):
        raw = self._cache.get('text_snippets', {})
        normalized = self._normalize_text_snippets_config(raw)
        if raw != normalized:
            # Persistiere normalisierte Struktur
            self.set('text_snippets', normalized)
            normalized = self._cache.get('text_snippets', normalized)
        return copy.deepcopy(normalized)

    def set_text_snippet_config(self, config: dict):
        normalized = self._normalize_text_snippets_config(config)
        self.set('text_snippets', normalized)
        return copy.deepcopy(normalized)

    # ------------------------------------------------------------------
    # Normalisierungshilfen
    def _normalize_value(self, value, default):
        if isinstance(default, list):
            return self._normalize_list_value(value if value is not None else default)
        if isinstance(default, dict):
            return self._normalize_dict_value(value if value is not None else default)
        return value if value is not None else default

    def _normalize_list_value(self, value):
        if value is None:
            return []
        if isinstance(value, list):
            return [self._ensure_text(item) for item in value if self._ensure_text(item)]
        if isinstance(value, tuple):
            return self._normalize_list_value(list(value))
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            for parser in (json.loads, ast.literal_eval):
                try:
                    parsed = parser(text)
                    return self._normalize_list_value(parsed)
                except Exception:
                    continue
            if ',' in text:
                return [part.strip() for part in text.split(',') if part.strip()]
            return [text]
        return [self._ensure_text(value)] if self._ensure_text(value) else []

    def _normalize_dict_value(self, value):
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return {}
            for parser in (json.loads, ast.literal_eval):
                try:
                    parsed = parser(text)
                    if isinstance(parsed, dict):
                        return parsed
                except Exception:
                    continue
        return {}

    def _normalize_text_snippets_config(self, value):
        # Backward compatibility: alter default mapping {tag: [snippets]}
        if not isinstance(value, dict):
            value = {}

        tags_section = value.get('tags') if isinstance(value, dict) else {}
        groups_section = value.get('groups') if isinstance(value, dict) else {}

        # Alte Struktur erkennen: dict ohne 'tags'/'groups'
        if not tags_section and not groups_section:
            if all(isinstance(v, (list, tuple, str)) for v in value.values()):
                tags_section = value
                groups_section = {}

        normalized_tags = {}
        if isinstance(tags_section, dict):
            for raw_tag, raw_texts in tags_section.items():
                tag = self._ensure_text(raw_tag)
                if not tag:
                    continue
                tag_key = tag.upper()
                snippets = self._normalize_snippet_list(raw_texts)
                if snippets:
                    normalized_tags[tag_key] = snippets

        normalized_groups = {}
        if isinstance(groups_section, dict):
            iterator = groups_section.items()
        elif isinstance(groups_section, list):
            iterator = []
            for entry in groups_section:
                if isinstance(entry, dict):
                    name = self._ensure_text(entry.get('name') or entry.get('id'))
                    if name:
                        iterator.append((name, entry))
        else:
            iterator = []

        for raw_name, data in iterator:
            name = self._ensure_text(raw_name)
            if not name or not isinstance(data, dict):
                continue
            tags = self._normalize_tag_list(data.get('tags'))
            snippets = self._normalize_snippet_list(data.get('snippets'))
            normalized_groups[name] = {
                'tags': tags,
                'snippets': snippets
            }

        return {
            'tags': normalized_tags,
            'groups': normalized_groups
        }

    def _normalize_tag_list(self, tags):
        if not tags:
            return []
        result = []
        seen = set()
        items = tags
        if isinstance(tags, str):
            items = [tags]
        for tag in items:
            cleaned = self._ensure_text(tag).upper()
            if not cleaned:
                continue
            if cleaned in seen:
                continue
            seen.add(cleaned)
            result.append(cleaned)
        return result

    def _normalize_snippet_list(self, value):
        if value is None:
            return []
        snippets = []
        if isinstance(value, (list, tuple)):
            iterable = value
        elif isinstance(value, str):
            iterable = [value]
        else:
            iterable = [value]
        seen = set()
        for item in iterable:
            text = self._ensure_text(item)
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            snippets.append(text)
        return snippets

    @staticmethod
    def _ensure_text(value):
        if isinstance(value, str):
            return value.strip()
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def _merge_defaults(defaults, current):
        seen = set()
        merged = []
        for source in (current, defaults):
            for item in source:
                if not isinstance(item, str):
                    item = str(item)
                trimmed = item.strip()
                if not trimmed:
                    continue
                key = trimmed.lower()
                if key in seen:
                    continue
                merged.append(trimmed)
                seen.add(key)
        return merged

    # Cover-Bild Convenience
    def get_cover_tags(self):
        tags = self.get("cover_tags", []) or []
        cleaned = []
        seen = set()
        for tag in tags:
            if not isinstance(tag, str):
                continue
            trimmed = tag.strip()
            if not trimmed:
                continue
            if trimmed.lower() in seen:
                continue
            cleaned.append(trimmed)
            seen.add(trimmed.lower())
        if cleaned != tags:
            self.set("cover_tags", cleaned)
        return cleaned

    def set_cover_tags(self, tags):
        cleaned = []
        seen = set()
        for tag in tags or []:
            if not isinstance(tag, str):
                continue
            trimmed = tag.strip()
            if not trimmed:
                continue
            key = trimmed.lower()
            if key in seen:
                continue
            cleaned.append(trimmed)
            seen.add(key)
        self.set("cover_tags", cleaned)
        return cleaned

    def add_cover_tag(self, tag: str):
        tags = self.get_cover_tags()
        if not isinstance(tag, str):
            return tags
        trimmed = tag.strip()
        if not trimmed:
            return tags
        if trimmed.lower() not in {t.lower() for t in tags}:
            tags.append(trimmed)
            self.set("cover_tags", tags)
        return tags

    def remove_cover_tag(self, tag: str):
        if not isinstance(tag, str):
            return self.get_cover_tags()
        tags = [t for t in self.get_cover_tags() if t.lower() != tag.strip().lower()]
        self.set("cover_tags", tags)
        return tags

    def get_cover_images(self):
        data = self.get("cover_images", {}) or {}
        if not isinstance(data, dict):
            return {}
        out = {}
        for path, entry in data.items():
            if not isinstance(path, str) or not isinstance(entry, dict):
                continue
            out[path] = entry.copy()
        if out != data:
            self.set("cover_images", out)
        return out

    def get_cover_image_data(self, image_path: str):
        if not isinstance(image_path, str) or not image_path:
            return {}
        return self.get_cover_images().get(image_path, {}).copy()

    def set_cover_image_data(self, image_path: str, data: dict | None):
        if not isinstance(image_path, str) or not image_path:
            return self.get_cover_images()
        images = self.get_cover_images()
        if data and isinstance(data, dict):
            images[image_path] = data.copy()
        else:
            images.pop(image_path, None)
        self.set("cover_images", images)
        return images

    def clear_cover_image(self, image_path: str):
        if not isinstance(image_path, str) or not image_path:
            return False
        images = self.get_cover_images()
        removed = images.pop(image_path, None) is not None
        if removed:
            self.set("cover_images", images)
        return removed

    def get_cover_last_folder(self):
        return self.get("cover_last_folder", "") or ""

    def set_cover_last_folder(self, folder: str):
        if folder is None:
            folder = ""
        self.set("cover_last_folder", str(folder))
        return folder
    
    def switch_language(self, language: str):
        """Wechselt die Sprache und aktualisiert alle sprachabhängigen Listen"""
        if language not in ["de", "en"]:
            return False
        
        self.set("localization_current_language", language)
        
        # Aktualisiere die aktuellen Listen basierend auf der neuen Sprache
        self.set("damage_categories", self.get(f"damage_categories_{language}", []))
        self.set("image_types", self.get(f"image_types_{language}", []))
        self.set("image_quality_options", self.get(f"image_quality_options_{language}", []))
        self.set("use_image_options", self.get(f"use_image_options_{language}", []))
        
        return True


# Globale Instanz
_settings_manager = None

def get_settings_manager():
    """Singleton-Instanz des Settings-Managers abrufen"""
    global _settings_manager
    if _settings_manager is None:
        _settings_manager = SettingsManager()
    return _settings_manager


def apply_dark_mode(enabled: bool):
    """Dark Mode auf die gesamte Anwendung anwenden"""
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QPalette, QColor
    from PySide6.QtCore import Qt
    
    app = QApplication.instance()
    if not app:
        return
    
    if enabled:
        # Dark Mode aktivieren
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(53, 53, 53))
        palette.setColor(QPalette.WindowText, Qt.white)
        palette.setColor(QPalette.Base, QColor(35, 35, 35))
        palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
        palette.setColor(QPalette.ToolTipBase, QColor(25, 25, 25))
        palette.setColor(QPalette.ToolTipText, Qt.white)
        palette.setColor(QPalette.Text, Qt.white)
        palette.setColor(QPalette.Button, QColor(53, 53, 53))
        palette.setColor(QPalette.ButtonText, Qt.white)
        palette.setColor(QPalette.BrightText, Qt.red)
        palette.setColor(QPalette.Link, QColor(42, 130, 218))
        palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        palette.setColor(QPalette.HighlightedText, Qt.black)
        app.setPalette(palette)
    else:
        # Light Mode aktivieren (Standard-Palette wiederherstellen)
        app.setPalette(QApplication.style().standardPalette())
