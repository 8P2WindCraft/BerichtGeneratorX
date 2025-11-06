#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EXIF-Daten-Verwaltung (JSON in UserComment)
KRITISCH: Kompatibilität mit bestehenden Bildern wahren!
"""

import json
from PIL import Image, ExifTags
from utils_logging import write_detailed_log, get_logger

_log = get_logger('app', {"module": "utils_exif"})


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


# -------------------- Komfort-API für Metadaten --------------------
def read_metadata(image_path: str) -> dict:
    """Liest JSON-Metadaten aus EXIF UserComment. Liefert {} bei Fehlern/keinen Daten."""
    try:
        data = get_exif_usercomment(image_path)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        write_detailed_log("error", "read_metadata fehlgeschlagen", f"Bild: {image_path}", e)
        return {}


def write_metadata(image_path: str, metadata: dict) -> bool:
    """Schreibt vollständige Metadaten (DICT) in EXIF UserComment."""
    try:
        if not isinstance(metadata, dict):
            metadata = {}
        ok = save_exif_usercomment(image_path, metadata)
        if ok:
            _log.info("exif_write", extra={"event": "exif_write", "path": image_path})
        return ok
    except Exception as e:
        write_detailed_log("error", "write_metadata fehlgeschlagen", f"Bild: {image_path}", e)
        return False


def update_metadata(image_path: str, patch: dict) -> bool:
    """Merged vorhandene Metadaten mit 'patch' und speichert sie."""
    try:
        base = read_metadata(image_path)
        base = base.copy() if isinstance(base, dict) else {}
        if isinstance(patch, dict):
            base.update(patch)
        return write_metadata(image_path, base)
    except Exception as e:
        write_detailed_log("error", "update_metadata fehlgeschlagen", f"Bild: {image_path}", e)
        return False


def get_used_flag(image_path: str) -> bool:
    """Gibt zurück, ob das Bild verwendet werden soll (use_image/used).
    Standard: True wenn noch kein Eintrag vorhanden ist."""
    md = read_metadata(image_path)
    if not isinstance(md, dict):
        return True  # Standard: verwenden
    
    # Prüfe ob überhaupt JSON-Daten vorhanden sind
    has_any_data = bool(md.get('evaluation') or md.get('ocr_info') or md.get('use_image') is not None or md.get('used') is not None)
    
    if isinstance(md.get('use_image'), bool):
        return md['use_image']
    if isinstance(md.get('used'), bool):
        return md['used']
    text = md.get('use_image_str')
    if isinstance(text, str):
        txt = text.strip().lower()
        if txt in {'ja', 'yes', 'true', '1'}:
            return True
        if txt in {'nein', 'no', 'false', '0'}:
            return False
    if isinstance(md.get('use_image_bool'), bool):
        return md['use_image_bool']
    
    # Kein expliziter Wert gesetzt: Standard ist True (verwenden)
    return True


def set_used_flag(image_path: str, used: bool) -> bool:
    """Setzt das use_image-Flag im EXIF-JSON."""
    patch = {
        "use_image": bool(used),
        "use_image_str": "ja" if used else "nein",
        "use_image_bool": bool(used),
    }
    return update_metadata(image_path, patch)


def get_evaluation(image_path: str) -> dict:
    """Liest die Bewertung aus den Metadaten."""
    try:
        md = read_metadata(image_path)
        eval_obj = md.get('evaluation', {})
        if isinstance(eval_obj, dict):
            eval_obj = eval_obj.copy()
        else:
            eval_obj = {}

        if not eval_obj.get('categories') and isinstance(md.get('damage_categories'), list):
            eval_obj['categories'] = [str(c).strip() for c in md.get('damage_categories') if str(c).strip()]
        # Bildarten: sowohl Liste als auch Einzelwert bereitstellen
        if not eval_obj.get('image_types') and isinstance(md.get('image_types'), list):
            eval_obj['image_types'] = [str(x).strip() for x in md.get('image_types') if str(x).strip()]
        if not eval_obj.get('image_type'):
            imgs = eval_obj.get('image_types') or md.get('image_types')
            if isinstance(imgs, list) and imgs:
                eval_obj['image_type'] = str(imgs[0]).strip()
        if not eval_obj.get('quality') and md.get('image_quality'):
            eval_obj['quality'] = str(md.get('image_quality')).strip()
        if not eval_obj.get('notes') and md.get('damage_description'):
            eval_obj['notes'] = str(md.get('damage_description')).strip()
        if 'gene' not in eval_obj and isinstance(md.get('gene_flag'), bool):
            eval_obj['gene'] = bool(md.get('gene_flag'))

        return eval_obj
    except Exception as e:
        write_detailed_log("error", "get_evaluation fehlgeschlagen", f"Bild: {image_path}", e)
        return {}

def set_evaluation(image_path: str, *, categories=None, quality=None, image_type=None, image_types=None, notes=None, gene=None) -> bool:
    """Write evaluation into EXIF JSON and mirror simple fields.
    Optionally normalizes strings to a target language (de/en) based on
    settings value 'metadata_language' (UI/de/en).
    """
    try:
        # Helper: map DE/EN terms to selected language using SettingsManager lists
        def _normalize_values(cats, qual, img, imgs):
            try:
                from qtui.settings_manager import get_settings_manager
                sm = get_settings_manager()
                target = sm.get_metadata_target_lang()
                de_c = [str(x) for x in (sm.get('damage_categories_de', []) or [])]
                en_c = [str(x) for x in (sm.get('damage_categories_en', []) or [])]
                de_i = [str(x) for x in (sm.get('image_types_de', []) or [])]
                en_i = [str(x) for x in (sm.get('image_types_en', []) or [])]
                de_q = [str(x) for x in (sm.get('image_quality_options_de', []) or [])]
                en_q = [str(x) for x in (sm.get('image_quality_options_en', []) or [])]

                def _map_one(val: str, de_list: list[str], en_list: list[str]) -> str:
                    if not isinstance(val, str):
                        return val
                    v = val.strip()
                    if not v:
                        return v
                    vlow = v.lower()
                    de_low = [s.strip().lower() for s in de_list]
                    en_low = [s.strip().lower() for s in en_list]
                    idx = -1
                    if vlow in de_low:
                        idx = de_low.index(vlow)
                    elif vlow in en_low:
                        idx = en_low.index(vlow)
                    if idx >= 0:
                        return (de_list if target == 'de' else en_list)[idx]
                    return v

                # Categories
                out_cats = None
                if cats is not None:
                    out_cats = []
                    for c in cats:
                        out_cats.append(_map_one(str(c), de_c, en_c))
                # Image type
                out_img = None
                if img is not None:
                    out_img = _map_one(str(img), de_i, en_i)
                out_imgs = None
                if imgs is not None:
                    out_list = []
                    for it in (imgs or []):
                        if isinstance(it, str) and it.strip():
                            out_list.append(_map_one(it, de_i, en_i))
                    out_imgs = out_list
                # Quality
                out_q = None
                if qual is not None:
                    out_q = _map_one(str(qual), de_q, en_q)
                return out_cats, out_q, out_img, out_imgs
            except Exception:
                return cats, qual, img, imgs

        md = read_metadata(image_path)
        eval_obj = md.get('evaluation') if isinstance(md.get('evaluation'), dict) else {}

        # Normalize before saving
        categories, quality, image_type, image_types = _normalize_values(categories, quality, image_type, image_types)

        if categories is not None:
            eval_obj['categories'] = list(categories)
        if quality is not None:
            eval_obj['quality'] = str(quality)
        if image_types is not None:
            try:
                eval_obj['image_types'] = list(image_types)
            except Exception:
                eval_obj['image_types'] = []
            if image_types and not image_type:
                image_type = image_types[0]
        if image_type is not None:
            eval_obj['image_type'] = str(image_type) if image_type else ""
        if notes is not None:
            eval_obj['notes'] = str(notes)
        if gene is not None:
            eval_obj['gene'] = bool(gene)
        md['evaluation'] = eval_obj

        # Mirror simplified fields
        if categories is not None:
            md['damage_categories'] = list(categories)
        if image_types is not None:
            md['image_types'] = [str(x) for x in (image_types or [])]
        elif image_type is not None:
            md['image_types'] = [str(image_type)] if image_type else []
        if quality is not None:
            md['image_quality'] = str(quality) if quality is not None else ""
        if notes is not None:
            md['damage_description'] = str(notes)
        if gene is not None:
            md['gene_flag'] = bool(gene)

        return write_metadata(image_path, md)
    except Exception as e:
        write_detailed_log("error", "set_evaluation fehlgeschlagen", f"Bild: {image_path}", e)
        return False


# -------- OCR-Helfer --------
def get_ocr_info(image_path: str) -> dict:
    """Liest OCR-Infos aus Metadaten und bietet Abwärtskompatibilität.
    Gibt ein Dict mit optionalen Keys: tag, confidence, box.
    Berücksichtigt neben md['ocr'] auch historische Felder wie 'TAGOCR' und 'ocr_result'.
    """
    md = read_metadata(image_path)
    out = {}

    # Primär: moderner 'ocr'-Block
    o = md.get('ocr')
    if isinstance(o, dict):
        if isinstance(o.get('tag'), str):
            out['tag'] = o['tag']
        if isinstance(o.get('confidence'), (int, float)):
            out['confidence'] = float(o['confidence'])
        if isinstance(o.get('box'), (list, tuple)) and len(o['box']) == 4:
            out['box'] = tuple(int(v) for v in o['box'])
    elif isinstance(o, str) and o.strip():
        # Ganz alte Variante: 'ocr' direkt als String = Tag
        out['tag'] = o.strip()

    # Fallbacks: historische Felder
    if 'tag' not in out:
        if isinstance(md.get('TAGOCR'), str) and md.get('TAGOCR').strip():
            out['tag'] = md.get('TAGOCR').strip()
        elif isinstance(md.get('ocr_result'), str) and md.get('ocr_result').strip():
            out['tag'] = md.get('ocr_result').strip()
    if 'confidence' not in out and isinstance(md.get('ocr_confidence'), (int, float)):
        try:
            out['confidence'] = float(md.get('ocr_confidence'))
        except Exception:
            pass

    return out


def set_ocr_info(image_path: str, *, tag: str = None, confidence: float = None, box: tuple | list = None) -> bool:
    """Schreibt OCR-Infos unter 'ocr' und hält Kompatibilitätsfelder aktuell (TAGOCR/ocr_result)."""
    try:
        md = read_metadata(image_path)
        o = md.get('ocr') if isinstance(md.get('ocr'), dict) else {}
        if not isinstance(o, dict):
            o = {}
        if tag is not None:
            o['tag'] = str(tag)
            # Kompatibilität: Top-Level Spiegel
            if str(tag).strip():
                md['TAGOCR'] = str(tag).strip()
                md['ocr_result'] = str(tag).strip()
            else:
                # leeren Tag entfernen
                md.pop('TAGOCR', None)
                md.pop('ocr_result', None)
        if confidence is not None:
            try:
                o['confidence'] = float(confidence)
            except Exception:
                pass
        if box is not None and isinstance(box, (list, tuple)) and len(box) == 4:
            o['box'] = [int(v) for v in box]
        md['ocr'] = o
        return write_metadata(image_path, md)
    except Exception:
        return False


def get_gene_flag(image_path: str) -> bool:
    try:
        eval_obj = get_evaluation(image_path)
        if isinstance(eval_obj, dict) and isinstance(eval_obj.get('gene'), bool):
            return eval_obj['gene']
    except Exception:
        pass
    return False


def set_gene_flag(image_path: str, flagged: bool) -> bool:
    try:
        md = read_metadata(image_path)
        eval_obj = md.get('evaluation') if isinstance(md.get('evaluation'), dict) else {}
        eval_obj = eval_obj.copy()
        eval_obj['gene'] = bool(flagged)
        md['evaluation'] = eval_obj
        return write_metadata(image_path, md)
    except Exception as e:
        write_detailed_log("error", "set_gene_flag fehlgeschlagen", f"Bild: {image_path}", e)
        return False


def get_cover_info(image_path: str) -> dict:
    """Liest Cover-spezifische Informationen (Tag, Beschreibung etc.)."""
    try:
        md = read_metadata(image_path)
        cover = md.get('cover') if isinstance(md.get('cover'), dict) else {}
        tag = cover.get('tag') if isinstance(cover, dict) else None
        description = cover.get('description') if isinstance(cover, dict) else None
        defect = cover.get('defect_description') if isinstance(cover, dict) else None
        use = cover.get('use') if isinstance(cover, dict) else None

        if not tag:
            tag = md.get('excel_footer_tag')
        if not description:
            description = md.get('excel_footer_comment')
        if not defect:
            defect = md.get('excel_footer_issue') or md.get('excel_footer_defect')

        return {
            'tag': str(tag).strip() if isinstance(tag, str) else '',
            'description': str(description).strip() if isinstance(description, str) else '',
            'defect_description': str(defect).strip() if isinstance(defect, str) else '',
            'use': bool(use) if isinstance(use, bool) else False,
        }
    except Exception as e:
        write_detailed_log("error", "get_cover_info fehlgeschlagen", f"Bild: {image_path}", e)
        return {
            'tag': '',
            'description': '',
            'defect_description': '',
            'use': True,
        }


def set_cover_info(
    image_path: str,
    *,
    tag: str | None = None,
    description: str | None = None,
    defect_description: str | None = None,
    use: bool | None = None,
) -> bool:
    """Aktualisiert Cover-Daten und spiegelt Tag/Beschreibung in Excel-Footer-Feldern."""
    try:
        md = read_metadata(image_path)
        cover = md.get('cover') if isinstance(md.get('cover'), dict) else {}
        cover = cover.copy() if isinstance(cover, dict) else {}

        def _clean_text(value):
            if isinstance(value, str):
                return value.strip()
            return ''

        if tag is not None:
            cleaned = _clean_text(tag)
            if cleaned:
                cover['tag'] = cleaned
            else:
                cover.pop('tag', None)
            if cleaned:
                md['excel_footer_tag'] = cleaned
            else:
                md.pop('excel_footer_tag', None)

        if description is not None:
            cleaned = _clean_text(description)
            if cleaned:
                cover['description'] = cleaned
                md['excel_footer_comment'] = cleaned
            else:
                cover.pop('description', None)
                md.pop('excel_footer_comment', None)

        if defect_description is not None:
            cleaned = _clean_text(defect_description)
            if cleaned:
                cover['defect_description'] = cleaned
                md['excel_footer_issue'] = cleaned
            else:
                cover.pop('defect_description', None)
                md.pop('excel_footer_issue', None)
                md.pop('excel_footer_defect', None)

        if use is not None:
            cover['use'] = bool(use)

        # Entferne Cover-Block falls leer
        if cover:
            md['cover'] = cover
        else:
            md.pop('cover', None)

        return write_metadata(image_path, md)
    except Exception as e:
        write_detailed_log("error", "set_cover_info fehlgeschlagen", f"Bild: {image_path}", e)
        return False


def is_image_evaluated(exif_data: dict) -> bool:
    """Prüft ob ein Bild vollständig bewertet ist
    
    Args:
        exif_data: EXIF-Daten dict von get_exif_usercomment()
    
    Returns:
        True wenn alle Bewertungsfelder gesetzt sind
    """
    if not exif_data:
        return False
    
    # Prüfe ob alle Bewertungsfelder gesetzt sind
    has_damage = bool(exif_data.get('DAMAGE'))
    has_quality = bool(exif_data.get('QUALITY'))
    has_use = exif_data.get('USE') is not None
    
    return has_damage and has_quality and has_use
