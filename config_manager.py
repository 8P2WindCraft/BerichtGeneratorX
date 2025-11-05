#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Konfigurationsverwaltung
Zen

traler Config-Manager für alle Programm-Einstellungen
"""

import os
import json
from datetime import datetime
from utils_helpers import resource_path
from utils_logging import get_logger
from core_kurzel import KurzelTableManager


# Dateipfade
JSON_CONFIG_FILE = resource_path('GearBoxExiff.json')
CODE_FILE = resource_path('valid_kurzel.txt')


class CentralConfigManager:
    """Zentrale Verwaltung aller Programm-Einstellungen"""
    
    def __init__(self):
        self.config_file = JSON_CONFIG_FILE
        self.config = self.load_config()
        self.kurzel_table_manager = KurzelTableManager(self)
        try:
            get_logger('app', {"module": "config_manager"}).info("module_started", extra={"event": "module_started"})
        except Exception:
            pass
        
    def load_config(self):
        """Lädt die zentrale Konfiguration"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    try:
                        get_logger('app', {"module": "config_manager"}).info("Konfiguration geladen", extra={"event": "config_loaded", "path": self.config_file})
                    except Exception:
                        print(f"Zentrale Konfiguration geladen: {self.config_file}")
                    cfg = self._migrate_config(config)
                    # Sicherstellen, dass kurzel_table vorhanden ist
                    self._ensure_kurzel_table(cfg)
                    return cfg
            except Exception as e:
                try:
                    get_logger('app', {"module": "config_manager"}).exception("Fehler beim Laden der Konfiguration", extra={"event": "config_load_error", "path": self.config_file})
                except Exception:
                    print(f"Fehler beim Laden der Konfiguration {self.config_file}: {e}")
                # Versuche tolerantes Parsen, falls z.B. Zusatzdaten angehängt wurden
                try:
                    with open(self.config_file, 'r', encoding='utf-8') as f:
                        raw = f.read()
                    decoder = json.JSONDecoder()
                    obj, idx = decoder.raw_decode(raw)
                    if isinstance(obj, dict):
                        # Backup der korrupten Datei
                        backup = self.config_file + ".corrupt.bak"
                        try:
                            with open(backup, 'w', encoding='utf-8') as bf:
                                bf.write(raw)
                        except Exception:
                            pass
                        cfg = self._migrate_config(obj)
                        self._ensure_kurzel_table(cfg)
                        # Schreibe bereinigte Konfiguration zurück
                        self.save_config(cfg)
                        return cfg
                except Exception:
                    pass
        
        # Erstelle Standard-Konfiguration
        default_config = self._get_default_config()
        self.save_config(default_config)
        # Falls es eine einfache Kürzelliste gibt, kurzel_table generieren
        self._ensure_kurzel_table(default_config)
        return default_config
    
    def save_config(self, config=None):
        """Speichert die zentrale Konfiguration"""
        if config is None:
            config = self.config
        
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            try:
                get_logger('app', {"module": "config_manager"}).info("Konfiguration gespeichert", extra={"event": "config_saved", "path": self.config_file})
            except Exception:
                print(f"Zentrale Konfiguration gespeichert: {self.config_file}")
            self.config = config
            return True
        except Exception as e:
            try:
                get_logger('app', {"module": "config_manager"}).exception("Fehler beim Speichern der Konfiguration", extra={"event": "config_save_error", "path": self.config_file})
            except Exception:
                print(f"Fehler beim Speichern der Konfiguration {self.config_file}: {e}")
            return False
    
    def _get_default_config(self):
        """Erstellt die Standard-Konfiguration"""
        return {
            "ocr_settings": {
                "active_method": "improved",
                "confidence_threshold": 0.3,
                "fallback_enabled": True,
                "alternative_kurzel_enabled": True
            },
            "valid_kurzel": [
                'HSS', 'HSSR', 'HSSGR', 'HSSGG', 'LSS', 'LSSR', 'LSSGR', 'LSSGG',
                'PLC2GR', 'PLC2GG', 'PLC2R', 'RG2', 'SUN2', 'PL2-1', 'PLB2G-1', 'PLB2R-1',
                'PL2-2', 'PLB2G-2', 'PLB2R-2', 'PL2-3', 'PLB2G-3', 'PLB2R-3',
                'PLC1G', 'PLC1R', 'RG1', 'SUN1', 'PL1-1', 'PLB1G-1', 'PLB1R-1',
                'PL1-2', 'PLB1G-2', 'PLB1R-2', 'PL1-3', 'PLB1G-3', 'PLB1R-3',
                'PL1-4', 'PLB1G-4', 'PLB1R-4'
            ],
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
            "kurzel_details": {},
            "kurzel_categories": {
                "Schmierung": {"description": "Schmierstellen und Schmiersysteme", "color": "#4CAF50", "icon": "🔧", "priority": 1},
                "Planetengetriebe": {"description": "Planetengetriebe-Komponenten", "color": "#2196F3", "icon": "⚙️", "priority": 2},
                "Ritzel": {"description": "Ritzel und Zahnräder", "color": "#FF9800", "icon": "🦷", "priority": 3}
            },
            "kurzel_statistics": {
                "total_count": 0, "active_count": 0, "inactive_count": 0,
                "by_category": {}, "by_priority": {}, "by_frequency": {},
                "last_updated": ""
            },
            "damage_categories": {
                "de": ["Visuell keine Defekte", "Kratzer", "Zykloidische Kratzer", "Stillstandsmarken",
                       "Verschmierung", "Partikeldurchgang", "Überrollmarken", "Pittings", "Sonstige"],
                "en": ["Visually no defects", "Scratches", "Cycloid Scratches", "Standstill marks",
                       "Smearing", "Particle passage", "Overrolling Marks", "Pitting", "Others"]
            },
            "image_types": {
                "de": ["Wälzkörper", "Innenring", "Außenring", "Käfig", "Zahnrad"],
                "en": ["Rolling Element", "Inner ring", "Outer ring", "Cage", "Gear"]
            },
            "image_quality_options": {
                "de": ["Gut", "Normal", "Schlecht", "Verschleiß", "Beschädigt", "Unbekannt"],
                "en": ["Good", "Normal", "Poor", "Traces of wear", "Damage", "Unknown"]
            },
            "use_image_options": {
                "de": ["ja", "nein"],
                "en": ["yes", "no"]
            },
            "localization": {
                "current_language": "en",
                "available_languages": ["de", "en"],
                "auto_detect_language": True
            },
            "display": {
                "window_width": 1080, "window_height": 800,
                "window_x": None, "window_y": None,
                "maximized": False, "save_window_position": True,
                "image_zoom": 1.0, "show_filename": True,
                "show_counter": True, "theme": "default",
                "font_size": 10, "filter_zero_codes": True
            },
            "navigation": {
                "auto_save": True, "confirm_unsaved": True,
                "keyboard_shortcuts": True, "auto_load_last_folder": True,
                "remember_last_image": True
            },
            "project_data": {
                "windpark": "", "windpark_land": "", "sn": "",
                "anlagen_nr": "", "hersteller": "", "getriebe_hersteller": "",
                "hersteller_2": "", "modell": "", "gear_sn": ""
            },
            "custom_data": {
                "field1": "", "field2": "", "field3": "",
                "field4": "", "field5": "", "field6": ""
            },
            "export": {
                "auto_backup": True, "backup_interval": 24,
                "export_format": "json", "include_exif_data": True,
                "include_statistics": True, "report_template": "default"
            },
            "performance": {
                "thumbnail_cache_size": 100, "max_image_size": 2048,
                "lazy_loading": True, "cache_evaluation_data": True,
                "max_cache_size": 1000
            },
            "logging": {
                "log_level": "info", "save_detailed_logs": True,
                "log_rotation": True, "max_log_size": 10,
                "debug_mode": False
            },
            "paths": {
                "last_folder": "", "backup_directory": "Backups",
                "log_directory": "logs", "temp_directory": "temp"
            },
            "last_selections": {
                "open_folder": "", "excel_file": "",
                "analyze_folder": "", "exif_folder": ""
            },
            "tag_management": {
                "auto_update_tags": True, "tag_structure_file": "tag_structure.json",
                "default_tag_structure": {}, "external_ocr_tags": {}
            },
            "metadata": {
                "version": "1.0.0", "last_updated": "",
                "config_version": "1.0", "migration_history": []
            }
        }
    
    def _migrate_config(self, config):
        """Migriert alte Konfigurationen zu neuem Format"""
        default_config = self._get_default_config()
        migrated = False
        
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
                old_value = config[old_key]
                if "." in new_path:
                    section, key = new_path.split(".", 1)
                    if section not in config:
                        config[section] = default_config[section]
                    config[section][key] = old_value
                else:
                    config[new_path] = old_value
                del config[old_key]
                migrated = True
        
        if migrated:
            config["metadata"]["last_updated"] = datetime.now().isoformat()
            config["metadata"]["migration_history"].append({
                "date": datetime.now().isoformat(),
                "type": "migration",
                "description": "Migration von altem Konfigurationsformat"
            })
        
        for section, default_section in default_config.items():
            if section not in config:
                config[section] = default_section.copy()
            elif isinstance(default_section, dict):
                for key, default_value in default_section.items():
                    if key not in config[section]:
                        config[section][key] = default_value
        
        return config

    # Hilfsfunktionen
    def _ensure_kurzel_table(self, config: dict):
        """Stellt sicher, dass eine kurzel_table vorhanden ist. Baut sie notfalls aus valid_kurzel auf."""
        try:
            kurzel_table = config.get('kurzel_table')
            if not isinstance(kurzel_table, dict) or len(kurzel_table) == 0:
                valid = config.get('valid_kurzel', []) or []
                if valid:
                    table = {}
                    for code in valid:
                        table[code] = {
                            'order': 0,
                            'kurzel_code': code,
                            'name_de': '',
                            'name_en': '',
                            'category': self._derive_category_from_code(code),
                            'subcategory': '',
                            'description_de': '',
                            'description_en': '',
                            'priority': 'normal',
                            'active': True,
                            'frequency': 0,
                            'created_date': None,
                            'last_modified': None,
                            'last_used': None,
                            'image_type': 'Unbekannt',
                            'damage_category': 'Unbekannt'
                        }
                    config['kurzel_table'] = table
        except Exception:
            # Bei Fehlern still weitermachen – TreeView zeigt dann ggf. nur 0/0
            pass

    def _derive_category_from_code(self, code: str) -> str:
        """Leitet grobe Kategorien aus dem Kürzel ab (Heuristik)."""
        try:
            c = (code or '').upper()
            if c.startswith('HSS'):
                return 'HSS – High Speed Shaft Stage'
            if c.startswith('LSS'):
                return 'Low Speed Shaft Stage'
            # Planetary Stage 1/2 anhand Ziffern
            if any(c.startswith(p) for p in ['PL1', 'PLB1', 'PLC1', 'PL1-', 'PLB1G', 'PLB1R']) or c in {'RG1', 'SUN1'}:
                return 'Planetary Stage 1'
            if any(c.startswith(p) for p in ['PL2', 'PLB2', 'PLC2', 'PL2-', 'PLB2G', 'PLB2R']) or c in {'RG2', 'SUN2'}:
                return 'Planetary Stage 2'
            return 'Unbekannt'
        except Exception:
            return 'Unbekannt'
    
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
        
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]
        
        config[keys[-1]] = value
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
    
    def get_kurzel_details(self, kurzel_code):
        """Holt detaillierte Informationen zu einem Kürzel"""
        kurzel_details = self.get_setting('kurzel_details', {})
        return kurzel_details.get(kurzel_code, {})
    
    def set_kurzel_details(self, kurzel_code, details):
        """Setzt detaillierte Informationen für ein Kürzel"""
        kurzel_details = self.get_setting('kurzel_details', {})
        kurzel_details[kurzel_code] = details
        self.set_setting('kurzel_details', kurzel_details)
        self.update_kurzel_statistics()
        return True
    
    def add_kurzel(self, kurzel_code, details):
        """Fügt ein neues Kürzel hinzu"""
        valid_kurzel = self.get_setting('valid_kurzel', [])
        if kurzel_code not in valid_kurzel:
            valid_kurzel.append(kurzel_code)
            self.set_setting('valid_kurzel', valid_kurzel)
        
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
        
        details['created_date'] = existing_details.get('created_date', '')
        details['last_modified'] = datetime.now().isoformat()
        self.set_kurzel_details(kurzel_code, details)
        
        print(f"Kürzel aktualisiert: {kurzel_code} - {details.get('name', '')}")
        return True
    
    def delete_kurzel(self, kurzel_code):
        """Löscht ein Kürzel"""
        valid_kurzel = self.get_setting('valid_kurzel', [])
        if kurzel_code in valid_kurzel:
            valid_kurzel.remove(kurzel_code)
            self.set_setting('valid_kurzel', valid_kurzel)
        
        kurzel_details = self.get_setting('kurzel_details', {})
        if kurzel_code in kurzel_details:
            del kurzel_details[kurzel_code]
            self.set_setting('kurzel_details', kurzel_details)
        
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
            if (search_term_lower in code.lower() or
                search_term_lower in details.get('name', '').lower() or
                search_term_lower in details.get('description', '').lower() or
                any(search_term_lower in tag.lower() for tag in details.get('tags', []))):
                results.append(code)
        
        return list(set(results))
    
    def update_kurzel_statistics(self):
        """Aktualisiert die Kürzel-Statistiken"""
        kurzel_details = self.get_setting('kurzel_details', {})
        
        total_count = len(kurzel_details)
        active_count = len([d for d in kurzel_details.values() if d.get('active', True)])
        inactive_count = total_count - active_count
        
        by_category = {}
        for details in kurzel_details.values():
            category = details.get('category', 'Unbekannt')
            by_category[category] = by_category.get(category, 0) + 1
        
        by_priority = {}
        for details in kurzel_details.values():
            priority = details.get('priority', 0)
            by_priority[priority] = by_priority.get(priority, 0) + 1
        
        by_frequency = {}
        for details in kurzel_details.values():
            frequency = details.get('frequency', 'unbekannt')
            by_frequency[frequency] = by_frequency.get(frequency, 0) + 1
        
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
    
    # Kürzel-Tabellen-Methoden (delegiert an KurzelTableManager)
    def get_kurzel_table_data(self):
        return self.kurzel_table_manager.get_all_kurzel()
    
    def get_kurzel_by_code(self, kurzel_code):
        return self.kurzel_table_manager.get_kurzel(kurzel_code)
    
    def add_kurzel_to_table(self, kurzel_data):
        return self.kurzel_table_manager.add_kurzel(kurzel_data)
    
    def update_kurzel_in_table(self, kurzel_code, kurzel_data):
        return self.kurzel_table_manager.update_kurzel(kurzel_code, kurzel_data)
    
    def delete_kurzel_from_table(self, kurzel_code):
        return self.kurzel_table_manager.delete_kurzel(kurzel_code)
    
    def search_kurzel_in_table(self, search_term):
        return self.kurzel_table_manager.search_kurzel(search_term)
    
    def get_kurzel_categories(self):
        kurzel_data = self.get_kurzel_table_data()
        categories = set()
        for data in kurzel_data.values():
            if data.get('category'):
                categories.add(data['category'])
        return sorted(list(categories))
    
    def get_kurzel_image_types(self):
        kurzel_data = self.get_kurzel_table_data()
        image_types = set()
        for data in kurzel_data.values():
            if data.get('image_type'):
                image_types.add(data['image_type'])
        return sorted(list(image_types))
    
    def export_kurzel_table_to_csv(self, filename=None):
        return self.kurzel_table_manager.export_to_csv(filename)
    
    def import_kurzel_table_from_csv(self, filename):
        return self.kurzel_table_manager.import_from_csv(filename)
    
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
            
            if 'kurzel_details' in import_data:
                self.set_setting('kurzel_details', import_data['kurzel_details'])
            if 'kurzel_categories' in import_data:
                self.set_setting('kurzel_categories', import_data['kurzel_categories'])
            if 'valid_kurzel' in import_data:
                self.set_setting('valid_kurzel', import_data['valid_kurzel'])
            
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


