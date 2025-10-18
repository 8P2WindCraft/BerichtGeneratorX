#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kürzel-Management
"""

from datetime import datetime
from utils_logging import write_detailed_log
from utils_csv import safe_csv_open


class KurzelTableManager:
    """Erweiterte Verwaltung für Kürzel-Tabelle mit Langschreibweise und Kategorien"""
    
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.table_data = self.load_table_data()
        
    def load_table_data(self):
        """Lädt die Kürzel-Tabellendaten"""
        return self.config_manager.get_setting('kurzel_table', {})
    
    def save_table_data(self):
        """Speichert die Kürzel-Tabellendaten"""
        self.config_manager.set_setting('kurzel_table', self.table_data)
        self.config_manager.save_config()
    
    def get_default_kurzel_structure(self):
        """Gibt die Standard-Struktur für ein Kürzel zurück"""
        return {
            'order': 0,
            'kurzel_code': '',
            'name_de': '',
            'name_en': '',
            'category': 'Unbekannt',
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
    
    def add_kurzel(self, kurzel_data):
        """Fügt ein neues Kürzel zur Tabelle hinzu"""
        kurzel_code = kurzel_data.get('kurzel_code', '')
        if not kurzel_code:
            return False
            
        # Setze Standardwerte für fehlende Felder
        default_structure = self.get_default_kurzel_structure()
        default_structure.update(kurzel_data)
        default_structure['created_date'] = datetime.now().isoformat()
        default_structure['last_modified'] = datetime.now().isoformat()
        
        self.table_data[kurzel_code] = default_structure
        self.save_table_data()
        
        # Aktualisiere auch die einfache Liste
        self.update_valid_kurzel_list()
        
        write_detailed_log("info", "Kürzel zur Tabelle hinzugefügt", f"Code: {kurzel_code}")
        return True
    
    def update_kurzel(self, kurzel_code, kurzel_data):
        """Aktualisiert ein bestehendes Kürzel"""
        if kurzel_code in self.table_data:
            self.table_data[kurzel_code].update(kurzel_data)
            self.table_data[kurzel_code]['last_modified'] = datetime.now().isoformat()
            self.save_table_data()
            write_detailed_log("info", "Kürzel aktualisiert", f"Code: {kurzel_code}")
            return True
        return False
    
    def delete_kurzel(self, kurzel_code):
        """Löscht ein Kürzel aus der Tabelle"""
        if kurzel_code in self.table_data:
            del self.table_data[kurzel_code]
            self.save_table_data()
            self.update_valid_kurzel_list()
            write_detailed_log("info", "Kürzel gelöscht", f"Code: {kurzel_code}")
            return True
        return False
    
    def get_kurzel(self, kurzel_code):
        """Holt ein Kürzel aus der Tabelle"""
        return self.table_data.get(kurzel_code, None)
    
    def get_all_kurzel(self):
        """Holt alle Kürzel aus der Tabelle"""
        return self.table_data
    
    def get_kurzel_by_category(self, category):
        """Holt alle Kürzel einer bestimmten Kategorie"""
        return {k: v for k, v in self.table_data.items() if v.get('category') == category}
    
    def get_kurzel_by_image_type(self, image_type):
        """Holt alle Kürzel eines bestimmten Bildtyps"""
        return {k: v for k, v in self.table_data.items() if v.get('image_type') == image_type}
    
    def search_kurzel(self, search_term):
        """Sucht Kürzel nach verschiedenen Kriterien"""
        results = {}
        search_lower = search_term.lower()
        
        for kurzel_code, data in self.table_data.items():
            if (search_lower in kurzel_code.lower() or
                search_lower in data.get('name_de', '').lower() or
                search_lower in data.get('name_en', '').lower() or
                search_lower in data.get('description_de', '').lower() or
                search_lower in data.get('description_en', '').lower()):
                results[kurzel_code] = data
        
        return results
    
    def update_valid_kurzel_list(self):
        """Aktualisiert die einfache Kürzel-Liste basierend auf der Tabelle"""
        valid_kurzel = [k for k, v in self.table_data.items() if v.get('active', True)]
        self.config_manager.set_setting('valid_kurzel', valid_kurzel)
        self.config_manager.save_config()
    
    def export_to_csv(self, filename=None):
        """Exportiert die Kürzel-Tabelle als CSV"""
        if filename is None:
            filename = f"kurzel_table_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        try:
            import csv
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = [
                    'order', 'kurzel_code', 'name_de', 'name_en', 'category', 'subcategory',
                    'description_de', 'description_en', 'priority', 'active',
                    'frequency', 'image_type', 'damage_category', 'created_date', 'last_modified'
                ]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for kurzel_code, data in self.table_data.items():
                    row = {'kurzel_code': kurzel_code, 'order': data.get('order', 0)}
                    row.update(data)
                    writer.writerow(row)
            
            write_detailed_log("info", "Kürzel-Tabelle exportiert", f"Datei: {filename}")
            return filename
        except Exception as e:
            write_detailed_log("error", "Fehler beim CSV-Export", str(e))
            return None
    
    def import_from_csv(self, filename):
        """Importiert Kürzel-Tabelle aus CSV"""
        try:
            import csv
            imported_count = 0
            
            with safe_csv_open(filename, 'r') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    kurzel_code = row.get('kurzel_code', '')
                    if kurzel_code:
                        # Konvertiere String-Werte
                        if 'active' in row:
                            row['active'] = row['active'].lower() == 'true'
                        if 'frequency' in row:
                            try:
                                row['frequency'] = int(row['frequency'])
                            except:
                                row['frequency'] = 0
                        # Reihenfolge (order) optional konvertieren
                        try:
                            row['order'] = int(row.get('order', row.get('Reihenfolge', 0)) or 0)
                        except Exception:
                            row['order'] = 0
                        
                        self.table_data[kurzel_code] = row
                        imported_count += 1
            
            self.save_table_data()
            self.update_valid_kurzel_list()
            
            write_detailed_log("info", "Kürzel-Tabelle importiert", f"Anzahl: {imported_count}")
            return imported_count
        except Exception as e:
            write_detailed_log("error", "Fehler beim CSV-Import", str(e))
            return 0


