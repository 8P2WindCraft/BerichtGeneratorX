# -*- coding: utf-8 -*-
"""
Evaluation Cache System
Cache für Bewertungsstatus ohne OCR-Abhängigkeit
"""

import os
from typing import Dict, Tuple, Optional, List
from utils_exif import get_exif_usercomment, get_ocr_info


class EvaluationCache:
    """Cache für Bewertungsstatus ohne OCR-Abhängigkeit"""
    
    def __init__(self):
        self._cache: Dict[str, dict] = {}  # {filename: {tag, is_evaluated, ...}}
        self._dirty = True
        self._folder = ""
        
    def build_cache(self, folder: str):
        """Baut Cache aus EXIF-Daten aller Bilder im Ordner"""
        if not folder or not os.path.isdir(folder):
            self._cache.clear()
            self._folder = ""
            return
            
        self._folder = folder
        self._cache.clear()
        
        # Unterstützte Bildformate
        image_extensions = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tif', '.tiff'}
        
        try:
            files = [f for f in os.listdir(folder) 
                    if os.path.splitext(f.lower())[1] in image_extensions]
        except Exception:
            files = []
        
        for filename in files:
            filepath = os.path.join(folder, filename)
            try:
                # Hole EXIF-Daten
                exif_data = get_exif_usercomment(filepath)
                
                # Hole OCR-Tag (manuell vergeben)
                ocr_info = get_ocr_info(filepath)
                tag = ocr_info.get('tag', '') if isinstance(ocr_info, dict) else ''
                
                # Prüfe Bewertungsstatus
                is_evaluated = self._check_is_evaluated(exif_data)
                
                # Hole Gene-Flag
                gene_flag = False
                try:
                    from utils_exif import get_gene_flag
                    gene_flag = get_gene_flag(filepath)
                except Exception:
                    pass
                
                # Speichere im Cache
                self._cache[filename] = {
                    'tag': tag,
                    'is_evaluated': is_evaluated,
                    'filepath': filepath,
                    'damage': exif_data.get('DAMAGE', '') if exif_data else '',
                    'quality': exif_data.get('QUALITY', '') if exif_data else '',
                    'use': exif_data.get('USE') if exif_data else None,
                    'gene': gene_flag
                }
            except Exception:
                # Bei Fehler: Datei im Cache als nicht bewertet markieren
                self._cache[filename] = {
                    'tag': '',
                    'is_evaluated': False,
                    'filepath': filepath,
                    'damage': '',
                    'quality': '',
                    'use': None,
                    'gene': False
                }
        
        self._dirty = False
    
    def _check_is_evaluated(self, exif_data: Optional[dict]) -> bool:
        """Prüft ob Bild bewertet ist basierend auf Regeln"""
        if not exif_data:
            return False
        
        # Hole Regeln aus Settings
        try:
            from qtui.settings_manager import get_settings_manager
            settings = get_settings_manager()
            rules = settings.get('evaluation_rules', None)
        except Exception:
            rules = None
        
        # Wenn keine Regeln definiert: Fallback auf alte Logik
        if not rules:
            return self._check_is_evaluated_legacy(exif_data)
        
        # Stelle sicher, dass rules eine Liste ist
        if not isinstance(rules, list):
            return self._check_is_evaluated_legacy(exif_data)
        
        # Prüfe jede Regel (OR-Verknüpfung zwischen Regeln)
        for rule in rules:
            # AND-Verknüpfung innerhalb der Regel
            conditions_met = True
            
            # use_image = 'nein'
            if rule.get('use_image_no', False):
                use_image = exif_data.get('use_image', '')
                use_flag = exif_data.get('USE')
                if not (use_image in ['nein', 'no'] or use_flag is False):
                    conditions_met = False
            
            # Schadenskategorie vorhanden
            if rule.get('has_damage_cat', False):
                damage_cats = exif_data.get('damage_categories', [])
                no_defects = ['Visually no defects', 'Visuell keine Defekte']
                damage_field = exif_data.get('DAMAGE', '')
                
                has_damage = (len(damage_cats) > 0 or bool(damage_field) or 
                             any(nd in damage_cats for nd in no_defects))
                if not has_damage:
                    conditions_met = False
            
            # GENE markiert
            if rule.get('gene_flagged', False):
                gene = exif_data.get('GENE', False)
                if not gene:
                    conditions_met = False
            
            # Wenn alle Bedingungen dieser Regel erfüllt: Bild ist bewertet
            if conditions_met:
                return True
        
        return False
    
    def _check_is_evaluated_legacy(self, exif_data: dict) -> bool:
        """Alte Bewertungslogik als Fallback"""
        # Prüfe "Bild verwenden" - wenn "nein", dann ist Bewertung abgeschlossen
        use_image = exif_data.get('use_image', '')
        if use_image in ['nein', 'no']:
            return True
        
        # Prüfe USE-Flag (neues System)
        use_flag = exif_data.get('USE')
        if use_flag is False:  # Explizit False = nicht verwenden
            return True
        
        # Prüfe Schadenskategorien
        damage_categories = exif_data.get('damage_categories', [])
        
        # Prüfe auf "visuell keine Defekte" (mehrsprachig)
        no_defects_variants = ['Visually no defects', 'Visuell keine Defekte']
        if any(variant in damage_categories for variant in no_defects_variants):
            return True
        
        # Mindestens eine Schadenskategorie UND mindestens eine Bildart-Kategorie
        image_types = exif_data.get('image_types', [])
        
        # Neues System: DAMAGE und QUALITY Felder
        damage = exif_data.get('DAMAGE', '')
        quality = exif_data.get('QUALITY', '')
        
        # Bewertet wenn: (Schäden + Bildarten) ODER (DAMAGE + QUALITY)
        old_system_evaluated = len(damage_categories) > 0 and len(image_types) > 0
        new_system_evaluated = bool(damage) and bool(quality)
        
        return old_system_evaluated or new_system_evaluated
    
    def invalidate(self):
        """Markiert den Cache als veraltet"""
        self._dirty = True
    
    def is_dirty(self) -> bool:
        """Gibt zurück ob der Cache neu gebaut werden muss"""
        return self._dirty
    
    def refresh_if_needed(self):
        """Baut Cache neu auf wenn er als dirty markiert ist"""
        if self._dirty and self._folder:
            self.build_cache(self._folder)
    
    def is_image_evaluated(self, filename: str) -> bool:
        """Prüft ob Bild bewertet ist (Damage + Quality + Use gesetzt)"""
        self.refresh_if_needed()
        
        if filename in self._cache:
            return self._cache[filename].get('is_evaluated', False)
        return False
    
    def get_tag(self, filename: str) -> str:
        """Gibt das OCR-Tag für ein Bild zurück"""
        self.refresh_if_needed()
        
        if filename in self._cache:
            return self._cache[filename].get('tag', '')
        return ''
    
    def get_kurzel_progress(self, kurzel_code: str) -> Tuple[int, int]:
        """Gibt (bewertete, gesamt) für ein Kürzel zurück"""
        self.refresh_if_needed()
        
        evaluated = 0
        total = 0
        
        for filename, data in self._cache.items():
            if data.get('tag', '') == kurzel_code:
                total += 1
                if data.get('is_evaluated', False):
                    evaluated += 1
        
        return (evaluated, total)
    
    def get_first_image_for_kurzel(self, kurzel_code: str) -> Optional[str]:
        """Gibt den Pfad zum ersten Bild mit diesem Kürzel zurück"""
        self.refresh_if_needed()
        
        for filename, data in self._cache.items():
            if data.get('tag', '') == kurzel_code:
                return data.get('filepath', '')
        return None
    
    def get_all_images_for_kurzel(self, kurzel_code: str) -> List[str]:
        """Gibt Liste aller Bildpfade mit diesem Kürzel zurück"""
        self.refresh_if_needed()
        
        images = []
        for filename, data in self._cache.items():
            if data.get('tag', '') == kurzel_code:
                filepath = data.get('filepath', '')
                if filepath:
                    images.append(filepath)
        
        return images
    
    def get_images_for_category(self, category_name: str, kurzel_table: dict) -> List[str]:
        """Gibt Liste aller Bildpfade in einer Kategorie zurück"""
        self.refresh_if_needed()
        
        # Hole alle Kürzel dieser Kategorie
        category_kurzel = [
            code for code, data in kurzel_table.items()
            if data.get('category', '') == category_name and data.get('active', True)
        ]
        
        # Sammle alle Bilder mit diesen Kürzeln
        images = []
        for kurzel in category_kurzel:
            images.extend(self.get_all_images_for_kurzel(kurzel))
        
        return images
    
    def get_cache_stats(self) -> dict:
        """Gibt Statistiken über den Cache zurück"""
        self.refresh_if_needed()
        
        total_images = len(self._cache)
        evaluated_images = sum(1 for data in self._cache.values() if data.get('is_evaluated', False))
        tagged_images = sum(1 for data in self._cache.values() if data.get('tag', ''))
        
        return {
            'total_images': total_images,
            'evaluated_images': evaluated_images,
            'tagged_images': tagged_images,
            'evaluation_progress': f"{evaluated_images}/{total_images}" if total_images > 0 else "0/0"
        }
    
    def has_gene_flag_for_kurzel(self, kurzel_code: str) -> bool:
        """Prüft ob mindestens ein Bild mit diesem Kürzel das Gene-Flag gesetzt hat"""
        self.refresh_if_needed()
        
        for filename, data in self._cache.items():
            if data.get('tag', '') == kurzel_code and data.get('gene', False):
                return True
        
        return False
    
    def count_gene_flags(self) -> int:
        """Zählt Anzahl der Gene-Flags im Cache"""
        self.refresh_if_needed()
        
        count = 0
        for data in self._cache.values():
            if data.get('gene', False):
                count += 1
        return count
    
    def get_next_gene_image(self, current_path: str | None) -> str | None:
        """Findet nächstes Bild mit Gene-Flag nach current_path (zyklisch)"""
        self.refresh_if_needed()
        
        # Sammle alle Bilder mit Gene-Flag
        gene_images = [
            data['filepath'] 
            for data in self._cache.values() 
            if data.get('gene', False)
        ]
        
        if not gene_images:
            return None
        
        # Sortiere alphabetisch nach Dateinamen
        gene_images.sort(key=lambda p: os.path.basename(p).lower())
        
        if not current_path:
            return gene_images[0]
        
        # Finde Index des aktuellen Bildes
        try:
            current_idx = gene_images.index(current_path)
            # Nächstes Bild (zyklisch)
            next_idx = (current_idx + 1) % len(gene_images)
            return gene_images[next_idx]
        except ValueError:
            # Aktuelles Bild nicht in Gene-Liste - gehe zum ersten
            return gene_images[0]

