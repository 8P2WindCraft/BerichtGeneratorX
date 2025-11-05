# -*- coding: utf-8 -*-
import sys
import os

# UTF-8 Encoding sicherstellen (Windows)
if sys.platform == 'win32':
    try:
        # Setze UTF-8 als Standard-Encoding für die Konsole
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
        # Setze UTF-8 Environment Variable
        os.environ['PYTHONIOENCODING'] = 'utf-8'
    except Exception:
        pass

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
    from qtui.settings_manager import get_settings_manager
    settings_manager = get_settings_manager()

    # Einmalige Migration der Kurzel-Tabelle aus dem ALT-Programm (GearBoxExiff.json)
    # NUR wenn noch keine kurzel_table existiert oder nur Defaults enthält
    try:
        if not settings_manager.get("kurzel_table_migrated", False):
            import os, json
            from utils_helpers import resource_path
            from qtui.migration_tools import migrate_from_tkinter
            from utils_logging import get_logger

            log = get_logger('app', {"module": "startup.migration"})
            
            # Prüfe ob bereits eine kurzel_table mit mehr als den 11 Defaults existiert
            existing_kurzel = settings_manager.get('kurzel_table', {}) or {}
            has_custom_kurzel = len(existing_kurzel) > 11  # Defaults haben nur 11 Einträge
            
            if has_custom_kurzel:
                # User hat bereits eigene Kürzel importiert - keine Migration
                log.info("migration_skipped_custom_data", extra={"event": "migration_skipped", "reason": "custom_data_exists", "count": len(existing_kurzel)})
                settings_manager.set("kurzel_table_migrated", True)
            else:
                # Nur migrieren wenn noch Default-Daten vorhanden
                alt_config_path = resource_path('GearBoxExiff.json')
                if os.path.exists(alt_config_path):
                    # Versuche Migration der Kurzel-Struktur im selben Format
                    stats = migrate_from_tkinter(alt_config_path, settings_manager)
                    # valid_kurzel aus aktiven Eintraegen der kurzel_table ableiten
                    kurzel_table = settings_manager.get('kurzel_table', {}) or {}
                    valid_kurzel = [k for k, v in kurzel_table.items() if isinstance(v, dict) and v.get('active', True)]
                    if valid_kurzel:
                        settings_manager.set_valid_kurzel(sorted(valid_kurzel))
                    settings_manager.set("kurzel_table_migrated", True)
                    try:
                        log.info("kurzel_table_migrated", extra={"event": "kurzel_table_migrated", "count": len(kurzel_table)})
                    except Exception:
                        pass
                else:
                    # Keine ALT-Konfiguration gefunden; Migration ueberspringen
                    settings_manager.set("kurzel_table_migrated", True)
    except Exception:
        # Migration ist optional; bei Fehlern normal weiter starten
        pass

    # Namen/Beschreibungen fuer Kurzel automatisch ergaenzen (DE/EN), falls leer
    try:
        if not settings_manager.get("kurzel_names_enriched", False):
            import re

            def gen_names(code: str):
                # Defaults
                name_en = code
                name_de = code

                # HSS/LSS Varianten
                m = re.match(r'^(HS|LS)S(GG|GR|R)?$', code)
                if m:
                    base = 'High Speed Shaft Stage' if m.group(1) == 'HS' else 'Low Speed Shaft Stage'
                    base_de = 'Hochgeschwindigkeitswelle (Stufe)' if m.group(1) == 'HS' else 'Niedriggeschwindigkeitswelle (Stufe)'
                    suffix = m.group(2) or ''
                    if suffix:
                        name_en = f"{base} (variant {suffix})"
                        name_de = f"{base_de} (Variante {suffix})"
                    else:
                        name_en = base
                        name_de = base_de
                    return name_de, name_en

                # Planet Carrier Stufe 1/2 (Varianten)
                m = re.match(r'^PLC([12])(GG|GR|G|R)$', code)
                if m:
                    stage = m.group(1)
                    side = m.group(2)
                    side_en = {'G': 'G side', 'R': 'R side'}.get(side, f"variant {side}")
                    side_de = {'G': 'Seite G', 'R': 'Seite R'}.get(side, f"Variante {side}")
                    name_en = f"Planet Carrier Stage {stage} ({side_en})"
                    name_de = f"Planetentraeger Stufe {stage} ({side_de})"
                    return name_de, name_en

                # Ring Gear / Sun Gear Stufe 1/2
                m = re.match(r'^(RG|SUN)([12])$', code)
                if m:
                    kind, stage = m.group(1), m.group(2)
                    if kind == 'RG':
                        name_en = f"Ring Gear Stage {stage}"
                        name_de = f"Hohlrad Stufe {stage}"
                    else:
                        name_en = f"Sun Gear Stage {stage}"
                        name_de = f"Sonnenrad Stufe {stage}"
                    return name_de, name_en

                # Planet n in Stufe 1/2, z.B. PL1-3
                m = re.match(r'^PL([12])-(\d)$', code)
                if m:
                    stage, idx = m.group(1), m.group(2)
                    name_en = f"Planet Stage {stage} → Planet {idx}"
                    name_de = f"Planet Stufe {stage} → Planet {idx}"
                    return name_de, name_en

                # Planet Bearing (G/R) fuer Planet n in Stufe 1/2, z.B. PLB1G-2
                m = re.match(r'^PLB([12])(G|R)-(\d)$', code)
                if m:
                    stage, side, idx = m.group(1), m.group(2), m.group(3)
                    side_en = 'G side' if side == 'G' else 'R side'
                    side_de = 'Seite G' if side == 'G' else 'Seite R'
                    name_en = f"Planet Bearing Stage {stage} ({side_en}) → Planet {idx}"
                    name_de = f"Planetenlager Stufe {stage} ({side_de}) → Planet {idx}"
                    return name_de, name_en

                # HS0..HS9 Fallback
                m = re.match(r'^HS([0-9])$', code)
                if m:
                    d = m.group(1)
                    name_en = f"High Speed code {d}"
                    name_de = f"Hochgeschwindigkeits-Code {d}"
                    return name_de, name_en

                return name_de, name_en

            table = settings_manager.get('kurzel_table', {}) or {}
            changed = False
            for code, data in list(table.items()):
                if not isinstance(data, dict):
                    continue
                name_de = data.get('name_de', '') or ''
                name_en = data.get('name_en', '') or ''
                if not name_de or not name_en:
                    gen_de, gen_en = gen_names(code)
                    if not name_de:
                        data['name_de'] = gen_de
                        changed = True
                    if not name_en:
                        data['name_en'] = gen_en
                        changed = True
                    table[code] = data
            if changed:
                settings_manager.set('kurzel_table', table)
            settings_manager.set('kurzel_names_enriched', True)
    except Exception:
        pass
    
    # Theme laden und anwenden
    from qtui.theme import apply_theme
    theme = settings_manager.get("theme", "Light")
    apply_theme(theme)
    
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
    w.raise_()  # Fenster in den Vordergrund bringen
    w.activateWindow()  # Fenster aktivieren
    splash.finish(w)
    
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
