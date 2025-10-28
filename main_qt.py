# -*- coding: utf-8 -*-
from qtui.app import create_app
from qtui.main_window import MainWindow
from qtui.loading_screen import LoadingScreen
from PySide6.QtCore import QTimer


def main():
    app = create_app()
    
    # Loading Screen anzeigen
    splash = LoadingScreen()
    splash.show()
    app.processEvents()
    
    # Komponenten laden mit Fortschrittsanzeige
    splash.update_progress(1, "Initialisiere Anwendung...")
    
    splash.update_progress(2, "Lade Einstellungen...")
    from qtui.settings_manager import get_settings_manager, apply_dark_mode
    settings_manager = get_settings_manager()
    
    # Dark Mode anwenden falls aktiviert
    dark_mode = settings_manager.get("dark_mode", False)
    if dark_mode:
        apply_dark_mode(True)
    
    splash.update_progress(3, "Lade Logger...")
    from utils_logging import get_logger
    
    splash.update_progress(4, "Lade EXIF-Utilities...")
    import utils_exif
    
    splash.update_progress(5, "Lade Widgets...")
    from qtui import widgets
    
    splash.update_progress(6, "Erstelle Hauptfenster...")
    w = MainWindow()
    
    splash.update_progress(7, "Lade Views...")
    # Views werden automatisch beim MainWindow-Init geladen
    
    splash.update_progress(8, "Finalisiere...")
    
    # Warte kurz, damit der Benutzer den fertigen Loading Screen sieht
    import time
    time.sleep(0.3)
    
    splash.update_progress(9, "Fertig!")
    time.sleep(0.2)
    
    # Hauptfenster anzeigen und Loading Screen schließen
    w.show()
    splash.finish(w)
    
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

