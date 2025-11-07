# -*- coding: utf-8 -*-
"""
Evaluation Cache Layer
Zwischenspeicher für Bewertungsänderungen, um Datenverlust bei schnellen Bildwechseln zu verhindern.
"""

import os
from typing import Dict, Optional
from threading import Lock
from utils_exif import set_evaluation, set_used_flag, get_evaluation, read_metadata, update_metadata


class EvaluationCacheLayer:
    """Cache-Layer für Bewertungsänderungen mit asynchronem Schreiben in EXIF"""
    
    def __init__(self):
        self._pending_changes: Dict[str, dict] = {}  # {path: {evaluation: {...}, use: bool, timestamp: float}}
        self._lock = Lock()  # Thread-sicherer Zugriff
        self._exif_cache: Dict[str, dict] = {}  # Cache für gelesene EXIF-Daten
        self._max_exif_cache_size = 500  # Maximale Anzahl gecachter EXIF-Daten (verhindert RAM-Überlauf)
        
    def get_evaluation(self, path: str) -> dict:
        """Liest Bewertung aus Cache (falls pending) oder aus EXIF"""
        if not path or not os.path.exists(path):
            return {}
        
        # Prüfe zuerst pending changes (mit Lock)
        with self._lock:
            if path in self._pending_changes:
                pending = self._pending_changes[path]
                if 'evaluation' in pending:
                    # Kopiere pending evaluation
                    pending_eval = pending['evaluation'].copy()
                else:
                    pending_eval = None
            else:
                pending_eval = None
            
            # Prüfe EXIF-Cache
            if path in self._exif_cache:
                cached_eval = self._exif_cache[path].get('evaluation', {})
            else:
                cached_eval = None
        
        # EXIF-Lesevorgang AUSSERHALB des Locks (vermeidet Blockierung)
        # Nur einmal aus EXIF lesen, um doppelte Lesevorgänge zu vermeiden
        if cached_eval is not None:
            # Verwende gecachte Daten
            if pending_eval is not None:
                # Kombiniere gecachte Daten mit pending changes
                result = cached_eval.copy()
                result.update(pending_eval)
                return result
            return cached_eval
        
        # Lese aus EXIF (außerhalb des Locks) - nur einmal
        eval_data = get_evaluation(path)
        
        # Wenn pending changes vorhanden, kombiniere mit EXIF-Daten
        if pending_eval is not None:
            result = eval_data.copy()
            result.update(pending_eval)
            return result
        
        # Cache für zukünftige Zugriffe (mit Lock)
        with self._lock:
            if path not in self._exif_cache:
                self._exif_cache[path] = {}
            self._exif_cache[path]['evaluation'] = eval_data
            
            # Cache-Größe begrenzen (verhindert RAM-Überlauf)
            if len(self._exif_cache) > self._max_exif_cache_size:
                # Entferne älteste Einträge (FIFO)
                keys_to_remove = list(self._exif_cache.keys())[:len(self._exif_cache) - self._max_exif_cache_size + 100]
                for key in keys_to_remove:
                    del self._exif_cache[key]
        
        return eval_data
    
    def get_used_flag(self, path: str) -> Optional[bool]:
        """Liest use_image Flag aus Cache (falls pending) oder aus EXIF"""
        if not path or not os.path.exists(path):
            return None
        
        with self._lock:
            # Prüfe zuerst pending changes
            if path in self._pending_changes:
                pending = self._pending_changes[path]
                if 'use' in pending:
                    return pending['use']
            
            # Prüfe EXIF-Cache
            if path in self._exif_cache:
                return self._exif_cache[path].get('use')
            
            # Lese aus EXIF
            try:
                md = read_metadata(path)
                use_flag = md.get('use_image') or md.get('USE')
                if isinstance(use_flag, bool):
                    use_value = use_flag
                elif isinstance(use_flag, str):
                    use_value = use_flag.lower() in ['ja', 'yes', 'true', '1']
                else:
                    use_value = bool(use_flag) if use_flag is not None else None
                
                # Cache für zukünftige Zugriffe
                if path not in self._exif_cache:
                    self._exif_cache[path] = {}
                self._exif_cache[path]['use'] = use_value
                
                # Cache-Größe begrenzen (verhindert RAM-Überlauf)
                if len(self._exif_cache) > self._max_exif_cache_size:
                    # Entferne älteste Einträge (FIFO)
                    keys_to_remove = list(self._exif_cache.keys())[:len(self._exif_cache) - self._max_exif_cache_size + 100]
                    for key in keys_to_remove:
                        del self._exif_cache[key]
                
                return use_value
            except Exception:
                return None
    
    def set_evaluation(self, path: str, *, categories=None, quality=None, 
                       image_type=None, image_types=None, notes=None, gene=None) -> bool:
        """Speichert Bewertung sofort im Cache (nicht in EXIF)"""
        if not path:
            return False
        
        # Hole aktuelle Bewertung AUSSERHALB des Locks (vermeidet Deadlock)
        current_eval = self.get_evaluation(path)
        
        # Aktualisiere nur geänderte Felder
        if categories is not None:
            current_eval['categories'] = list(categories) if categories else []
        if quality is not None:
            current_eval['quality'] = str(quality) if quality else None
        if image_type is not None:
            current_eval['image_type'] = str(image_type) if image_type else ""
        if image_types is not None:
            current_eval['image_types'] = list(image_types) if image_types else []
        if notes is not None:
            current_eval['notes'] = str(notes) if notes else ""
        if gene is not None:
            current_eval['gene'] = bool(gene)
        
        # Jetzt mit Lock: Speichere im pending changes
        with self._lock:
            # Initialisiere pending changes für diesen Pfad
            if path not in self._pending_changes:
                self._pending_changes[path] = {'evaluation': {}, 'timestamp': 0.0}
            
            # Speichere im pending changes
            self._pending_changes[path]['evaluation'] = current_eval
            import time
            self._pending_changes[path]['timestamp'] = time.time()
            
            # Invalidate EXIF-Cache für diesen Pfad
            if path in self._exif_cache:
                del self._exif_cache[path]
        
        return True
    
    def set_used_flag(self, path: str, used: bool) -> bool:
        """Speichert use_image Flag sofort im Cache (nicht in EXIF)"""
        if not path:
            return False
        
        with self._lock:
            # Initialisiere pending changes für diesen Pfad
            if path not in self._pending_changes:
                self._pending_changes[path] = {'evaluation': {}, 'timestamp': 0.0}
            
            # Speichere im pending changes
            self._pending_changes[path]['use'] = bool(used)
            import time
            self._pending_changes[path]['timestamp'] = time.time()
            
            # Invalidate EXIF-Cache für diesen Pfad
            if path in self._exif_cache:
                del self._exif_cache[path]
            
            return True
    
    def has_pending_changes(self, path: Optional[str] = None) -> bool:
        """Prüft ob es pending changes gibt (für spezifischen Pfad oder insgesamt)"""
        with self._lock:
            if path:
                return path in self._pending_changes
            return len(self._pending_changes) > 0
    
    def get_pending_paths(self) -> list:
        """Gibt Liste aller Pfade mit pending changes zurück"""
        with self._lock:
            return list(self._pending_changes.keys())
    
    def flush_to_exif(self, path: str) -> bool:
        """Schreibt pending changes für einen spezifischen Pfad sofort in EXIF"""
        if not path:
            return False
        
        # Prüfe ob Datei existiert (verhindert Anhäufung von ungültigen Pfaden)
        if not os.path.exists(path):
            # Entferne ungültigen Pfad aus pending changes
            with self._lock:
                if path in self._pending_changes:
                    del self._pending_changes[path]
                if path in self._exif_cache:
                    del self._exif_cache[path]
            return False
        
        # Kopiere pending changes AUSSERHALB des Locks
        with self._lock:
            if path not in self._pending_changes:
                return True  # Nichts zu schreiben - bereits gespeichert oder nie geändert
            
            # Tiefe Kopie der pending changes
            pending = {
                'evaluation': self._pending_changes[path].get('evaluation', {}).copy() if 'evaluation' in self._pending_changes[path] else None,
                'use': self._pending_changes[path].get('use') if 'use' in self._pending_changes[path] else None
            }
        
        # EXIF-Schreibvorgänge AUSSERHALB des Locks (vermeidet Blockierung)
        success = True
        
        # Schreibe Bewertung
        if pending['evaluation'] is not None:
            eval_data = pending['evaluation']
            try:
                result = set_evaluation(
                    path,
                    categories=eval_data.get('categories'),
                    quality=eval_data.get('quality'),
                    image_type=eval_data.get('image_type'),
                    image_types=eval_data.get('image_types'),
                    notes=eval_data.get('notes'),
                    gene=eval_data.get('gene')
                )
                if not result:
                    success = False
            except Exception:
                success = False
        
        # Schreibe use flag
        if pending['use'] is not None:
            try:
                result = set_used_flag(path, pending['use'])
                if not result:
                    success = False
            except Exception:
                success = False
        
        # Entferne aus pending changes nach erfolgreichem Schreiben (mit Lock)
        if success:
            with self._lock:
                if path in self._pending_changes:
                    del self._pending_changes[path]
                # Invalidate EXIF-Cache
                if path in self._exif_cache:
                    del self._exif_cache[path]
        
        return success
    
    def flush_all(self) -> int:
        """Schreibt alle pending changes in EXIF (wird vom Worker aufgerufen)"""
        # Flushe in Schleife, bis keine pending changes mehr vorhanden sind
        # (verhindert Race Condition bei gleichzeitigen Änderungen)
        success_count = 0
        max_iterations = 100  # Verhindert Endlosschleife
        iteration = 0
        failed_paths = []  # Sammle fehlgeschlagene Pfade
        
        while iteration < max_iterations:
            # Hole nächste Batch von Pfaden
            with self._lock:
                if not self._pending_changes:
                    break  # Keine pending changes mehr
                paths_to_flush = list(self._pending_changes.keys())[:10]  # Max 10 pro Iteration
            
            if not paths_to_flush:
                break
            
            # Flushe alle Pfade in diesem Batch
            for path in paths_to_flush:
                if self.flush_to_exif(path):
                    success_count += 1
                else:
                    failed_paths.append(path)
            
            iteration += 1
        
        # Entferne fehlgeschlagene Pfade nach mehreren Versuchen (verhindert Memory Leak)
        # (nur wenn sie nicht mehr existieren)
        if failed_paths:
            with self._lock:
                for path in failed_paths[:]:
                    if path in self._pending_changes:
                        # Prüfe ob Datei noch existiert
                        if not os.path.exists(path):
                            del self._pending_changes[path]
                            failed_paths.remove(path)
        
        return success_count
    
    def clear_cache(self, path: Optional[str] = None):
        """Löscht Cache für einen spezifischen Pfad oder alle"""
        with self._lock:
            if path:
                if path in self._pending_changes:
                    del self._pending_changes[path]
                if path in self._exif_cache:
                    del self._exif_cache[path]
            else:
                self._pending_changes.clear()
                self._exif_cache.clear()

