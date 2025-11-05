#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Erzeugt eine verschlankte Version von GearBoxExiff.json:
- Reduziert kurzel_table auf: kurzel_code, ocr_tag, active, order, name_de, name_en, description_de, description_en
- Übernimmt nur die notwendigen Blöcke: ocr_settings (Kernfelder), valid_kurzel,
  kurzel_table (reduziert), damage_categories, image_types, metadata (Basis)
- Schreibt nach GearBoxExiff.slim.json
"""

from __future__ import annotations
import json
from pathlib import Path

SRC = Path("GearBoxExiff.json")
DST = Path("GearBoxExiff.slim.json")

def _as_bool(v, default=False):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in {"true", "1", "yes", "y"}
    return default

def _as_int(v, default=0):
    try:
        return int(v)
    except Exception:
        return default

def main():
    if not SRC.exists():
        raise SystemExit(f"Quelle nicht gefunden: {SRC}")
    with SRC.open("r", encoding="utf-8") as f:
        src = json.load(f)

    slim = {}

    # ocr_settings: nur Kernfelder übernehmen
    ocr_src = src.get("ocr_settings", {}) or {}
    slim["ocr_settings"] = {
        k: ocr_src[k]
        for k in ("active_method", "confidence_threshold")
        if k in ocr_src
    }

    # valid_kurzel 1:1
    slim["valid_kurzel"] = list(src.get("valid_kurzel", []) or [])

    # kurzel_table reduziert + Felder für OCR-Tag und Freitext-Beschreibung
    reduced_table = {}
    for code, data in (src.get("kurzel_table", {}) or {}).items():
        if not isinstance(data, dict):
            continue
        kurzel_code = (data.get("kurzel_code") or code or "").strip()
        active = _as_bool(data.get("active", True), True)
        order = _as_int(data.get("order", 0), 0)
        name_de = (data.get("name_de") or "").strip()
        name_en = (data.get("name_en") or "").strip()
        desc_de = (data.get("description_de") or "").strip()
        desc_en = (data.get("description_en") or "").strip()
        ocr_tag = (data.get("ocr_tag") or kurzel_code or "").strip()
        reduced_table[code] = {
            "kurzel_code": kurzel_code,
            "ocr_tag": ocr_tag,
            "active": active,
            "order": order,
            "name_de": name_de,
            "name_en": name_en,
            "description_de": desc_de,
            "description_en": desc_en,
        }
    if reduced_table:
        slim["kurzel_table"] = reduced_table

    # Schadenskategorien / Bildarten (zweisprachig)
    if isinstance(src.get("damage_categories"), dict):
        slim["damage_categories"] = src["damage_categories"]
    if isinstance(src.get("image_types"), dict):
        slim["image_types"] = src["image_types"]

    # Metadaten minimiert
    meta = src.get("metadata", {}) or {}
    meta_out = {}
    for k in ("version", "config_version"):
        if k in meta:
            meta_out[k] = meta[k]
    if meta_out:
        slim["metadata"] = meta_out

    with DST.open("w", encoding="utf-8") as f:
        json.dump(slim, f, indent=2, ensure_ascii=False)

    print(f"Erstellt: {DST} (Felder reduziert, Größe gestrafft)")

if __name__ == "__main__":
    main()
