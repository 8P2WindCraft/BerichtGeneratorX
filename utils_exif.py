#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EXIF-Daten-Verwaltung (JSON in UserComment)
KRITISCH: Kompatibilität mit bestehenden Bildern wahren!
"""

import json
from PIL import Image, ExifTags
from utils_logging import write_detailed_log


def get_exif_usercomment(image_path):
    """Liest das EXIF UserComment-Feld aus einem Bild"""
    try:
        with Image.open(image_path) as img:
            exif = img.getexif()
            if exif is None:
                write_detailed_log("info", "Keine EXIF-Daten gefunden", f"Bild: {image_path}")
                return None
            
            # Finde den UserComment-Tag
            for tag_id in exif:
                tag = ExifTags.TAGS.get(tag_id, tag_id)
                if tag == 'UserComment':
                    user_comment = exif.get(tag_id)
                    if user_comment:
                        try:
                            # Behandle sowohl String als auch Bytes mit Prefixen
                            if isinstance(user_comment, bytes):
                                # Entferne mögliche Prefixe
                                prefixes = [b'ASCII\x00\x00\x00', b'UNICODE\x00', b'JIS\x00\x00\x00', b'\x00\x00\x00\x00']
                                data = user_comment
                                for prefix in prefixes:
                                    if data.startswith(prefix):
                                        data = data[len(prefix):]
                                        break
                                data = data.decode('utf-8', errors='ignore')
                            else:
                                data = str(user_comment)
                            
                            # Versuche JSON zu parsen
                            parsed_data = json.loads(data)
                            write_detailed_log("info", "EXIF-Daten erfolgreich gelesen", f"Bild: {image_path}, Größe: {len(str(parsed_data))} Zeichen")
                            return parsed_data
                        except (json.JSONDecodeError, UnicodeDecodeError) as e:
                            write_detailed_log("warning", "EXIF-Daten konnten nicht als JSON geparst werden", f"Bild: {image_path}", e)
                            return None
            write_detailed_log("info", "Kein UserComment-Tag in EXIF-Daten gefunden", f"Bild: {image_path}")
            return None
    except Exception as e:
        write_detailed_log("error", "Fehler beim Lesen der EXIF-Daten", f"Bild: {image_path}", e)
        print(f"Fehler beim Lesen der EXIF-Daten: {e}")
        return None


def save_exif_usercomment(image_path, json_data):
    """Speichert JSON-Daten im EXIF UserComment-Feld"""
    try:
        with Image.open(image_path) as img:
            exif = img.getexif()
            if exif is None:
                exif = {}
            
            # Konvertiere JSON zu Bytes mit Standard-Prefix
            json_string = json.dumps(json_data, ensure_ascii=False)
            json_bytes = json_string.encode('utf-8')
            user_comment = b'ASCII\x00\x00\x00' + json_bytes
            
            # Finde den UserComment-Tag-ID
            usercomment_tag_id = None
            for tag_id, tag_name in ExifTags.TAGS.items():
                if tag_name == 'UserComment':
                    usercomment_tag_id = tag_id
                    break
            
            if usercomment_tag_id is None:
                # Fallback: verwende einen bekannten Tag-ID für UserComment
                usercomment_tag_id = 37510
            
            exif[usercomment_tag_id] = user_comment
            
            # Speichere das Bild mit neuen EXIF-Daten
            img.save(image_path, exif=exif)
            write_detailed_log("info", "EXIF-Daten erfolgreich gespeichert", f"Bild: {image_path}, Größe: {len(json_string)} Zeichen")
            return True
    except Exception as e:
        write_detailed_log("error", "Fehler beim Speichern der EXIF-Daten", f"Bild: {image_path}", e)
        print(f"Fehler beim Speichern der EXIF-Daten: {e}")
        return False


