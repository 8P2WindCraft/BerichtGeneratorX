#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GearGeneGPT - Haupteinstiegspunkt
OCR-Bildanalyse für Getriebe-Endoskopie
"""

import time
import threading

from gui_components import LoadingScreen
from gui_main import OCRReviewApp


def main():
    """Hauptfunktion - Startet die Anwendung mit Ladebildschirm"""
    try:
        # Erstelle Ladebildschirm
        loading_screen = LoadingScreen()
        
        def initialize_app():
            """Initialisiert die Anwendung im Hintergrund"""
            try:
                loading_screen.update_status("Lade Konfiguration...")
                time.sleep(0.5)
                
                loading_screen.update_status("Initialisiere OCR-Engine...")
                time.sleep(0.5)
                
                loading_screen.update_status("Lade Benutzeroberfläche...")
                time.sleep(0.5)
                
                loading_screen.update_status("Erstelle Hauptfenster...")
                time.sleep(0.5)
                
                loading_screen.update_status("Fertig! Starte Anwendung...")
                time.sleep(0.5)
                
                # Hauptanwendung im Hauptthread erstellen
                loading_screen.root.after(0, create_main_app)
                
            except Exception as e:
                print(f"Fehler beim Initialisieren der Anwendung: {e}")
                import traceback
                traceback.print_exc()
                loading_screen.update_status(f"Fehler: {e}")
                loading_screen.root.after(3000, loading_screen.close)
        
        def create_main_app():
            """Erstellt die Hauptanwendung im Hauptthread"""
            try:
                # Ladebildschirm schließen
                loading_screen.close()
                
                # Kurze Pause, damit der Ladebildschirm vollständig geschlossen ist
                time.sleep(0.1)
                
                # Hauptanwendung erstellen
                print("Starte GearGeneGPT...")
                app = OCRReviewApp(loading_mode=False)
                
                # Sicherstellen, dass das Hauptfenster sichtbar und fokussiert ist
                try:
                    app.deiconify()
                    app.lift()
                    app.focus_force()
                    app.attributes('-topmost', True)
                    app.after(300, lambda: app.attributes('-topmost', False))
                except Exception:
                    pass
                
                print("App erstellt, starte mainloop...")
                app.mainloop()
                print("mainloop beendet")
                
            except Exception as e:
                print(f"Fehler beim Erstellen der Hauptanwendung: {e}")
                import traceback
                traceback.print_exc()
        
        # Initialisierung im Hintergrund starten
        init_thread = threading.Thread(target=initialize_app, daemon=True)
        init_thread.start()
        
        # Ladebildschirm anzeigen
        loading_screen.root.mainloop()
        
    except Exception as e:
        print(f"Fehler beim Starten der Anwendung: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()

