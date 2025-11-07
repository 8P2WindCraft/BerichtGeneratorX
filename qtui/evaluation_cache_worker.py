# -*- coding: utf-8 -*-
"""
Evaluation Cache Worker
Hintergrund-Worker für asynchrones Schreiben von Bewertungsänderungen in EXIF-Daten.
"""

import time
from PySide6.QtCore import QThread, Signal
from .evaluation_cache_layer import EvaluationCacheLayer


class EvaluationCacheWorker(QThread):
    """Hintergrund-Worker für asynchrones Schreiben von pending changes in EXIF"""
    
    progress = Signal(str)  # Emittiert nach erfolgreichem Schreiben eines Pfads
    error = Signal(str, str)  # Emittiert bei Fehler (path, error_message)
    
    def __init__(self, cache_layer: EvaluationCacheLayer, parent=None):
        super().__init__(parent)
        self.cache_layer = cache_layer
        self._running = False
        self._flush_interval = 3.0  # Sekunden zwischen Flush-Zyklen
        self._batch_size = 5  # Max Anzahl Bilder pro Batch
        self._stop_requested = False
    
    def run(self):
        """Hauptschleife des Workers"""
        self._running = True
        self._stop_requested = False
        
        while not self._stop_requested:
            try:
                # Prüfe auf pending changes
                if self.cache_layer.has_pending_changes():
                    pending_paths = self.cache_layer.get_pending_paths()
                    
                    # Verarbeite in Batches
                    batch = pending_paths[:self._batch_size]
                    for path in batch:
                        if self._stop_requested:
                            break
                        
                        try:
                            # Schreibe in EXIF
                            if self.cache_layer.flush_to_exif(path):
                                self.progress.emit(path)
                            else:
                                self.error.emit(path, "Fehler beim Schreiben in EXIF")
                        except Exception as e:
                            self.error.emit(path, str(e))
                
                # Wenn stop_requested und noch pending changes: Flushe alle
                if self._stop_requested and self.cache_layer.has_pending_changes():
                    try:
                        self.cache_layer.flush_all()
                    except Exception:
                        pass
                    break  # Beende nach finalem Flush
                
                # Warte bis zum nächsten Zyklus
                if not self._stop_requested:
                    time.sleep(self._flush_interval)
                    
            except Exception as e:
                # Bei unerwarteten Fehlern: Log und weiter
                try:
                    from utils_logging import get_logger
                    logger = get_logger('app', {"module": "qtui.evaluation_cache_worker"})
                    logger.error("worker_error", extra={"event": "worker_error", "error": str(e)})
                except Exception:
                    pass
                if not self._stop_requested:
                    time.sleep(self._flush_interval)
        
        self._running = False
    
    def stop(self):
        """Stoppt den Worker (wird beim App-Ende aufgerufen)"""
        self._stop_requested = True
        
        # Warte auf Worker-Thread, der flush_all() im run() aufruft
        # (wird im Worker-Thread ausgeführt, nicht im UI-Thread)
        self.wait(5000)  # Warte max 5 Sekunden auf Beendigung
        
        # Falls Worker nicht mehr läuft und noch pending changes existieren,
        # flushe asynchron im Hintergrund (nicht blockierend für UI)
        if not self.isRunning() and self.cache_layer.has_pending_changes():
            # Asynchron im Hintergrund flushen (nicht blockierend)
            from PySide6.QtCore import QTimer
            def _final_flush():
                try:
                    self.cache_layer.flush_all()
                except Exception:
                    pass
            QTimer.singleShot(0, _final_flush)
    
    def flush_now(self):
        """Fordert sofortiges Flushen aller pending changes an (wird vom UI aufgerufen)"""
        if self.cache_layer.has_pending_changes():
            pending_paths = self.cache_layer.get_pending_paths()
            for path in pending_paths:
                try:
                    if self.cache_layer.flush_to_exif(path):
                        self.progress.emit(path)
                except Exception as e:
                    self.error.emit(path, str(e))

