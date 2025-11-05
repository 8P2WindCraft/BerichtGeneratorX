# -*- coding: utf-8 -*-
from __future__ import annotations
"""Gemeinsames Bewertungs-Panel für Einzelbild- und Galerie-Ansichten."""


from typing import Iterable

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QToolButton,
    QScrollArea,
)

from utils_exif import (
    get_evaluation,
    set_evaluation,
    get_used_flag,
    set_used_flag,
    get_ocr_info,
)
from .settings_manager import get_settings_manager
from .widgets import ChipButton, ToggleSwitch


def _normalize_list(values: Iterable[str], fallback: list[str], limit: int | None = None) -> list[str]:
    out: list[str] = []
    for v in values or []:
        if isinstance(v, str):
            text = v.strip()
            if text and text not in out:
                out.append(text)
        if limit and len(out) >= limit:
            break
    if not out:
        out = list(fallback)
    if limit:
        out = out[:limit]
    return out


class EvaluationPanel(QWidget):
    """Bewertungssteuerung mit gemeinsamen Logik für Bilder."""

    evaluationChanged = Signal(str, dict)
    useChanged = Signal(str, bool)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.settings_manager = get_settings_manager()
        self.settings_manager.settingsChanged.connect(self._on_settings_changed)

        self._path: str | None = None
        self._loading = False
        self._damage_buttons: list[ChipButton] = []
        self._quality_buttons: list[ChipButton] = []
        self._image_type_buttons: list[ChipButton] = []
        self._damage_section_body: QWidget | None = None
        self._quality_section_body: QWidget | None = None
        self._image_section_body: QWidget | None = None
        self._visual_ok_texts: set[str] = set()

        self._auto_timer = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.timeout.connect(self._save_state)

        self._build_ui()
        self.refresh_options()
        self.setEnabled(False)

    # ------------------------------------------------------------------
    # UI Aufbau
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(8)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)

        # Interne ToggleSwitches (nicht sichtbar) werden für die Logik benötigt
        self.use_toggle = ToggleSwitch()
        self.use_toggle.setChecked(False)
        self.use_toggle.toggled.connect(self._on_use_toggled)
        self.use_toggle.hide()

        self.gene_toggle = ToggleSwitch()
        self.gene_toggle.setChecked(False)
        self.gene_toggle.toggled.connect(self._schedule_save)
        self.gene_toggle.hide()

        self._image_section_body = self._create_section(layout, "Bildart")
        self._damage_section_body = self._create_section(layout, "Schadenskategorien", collapsible=True)
        self._quality_section_body = self._create_section(layout, "Bewertung", collapsible=True)

        layout.addStretch(1)

    def _create_section(self, parent_layout: QVBoxLayout, title: str, collapsible: bool = True) -> QWidget:
        frame = QFrame()
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(4)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)
        lbl = QLabel(title)
        lbl.setStyleSheet("font-weight: bold;")
        header.addWidget(lbl)
        header.addStretch(1)
        if collapsible:
            toggle_btn = QToolButton()
            toggle_btn.setCheckable(True)
            toggle_btn.setChecked(True)
            toggle_btn.setArrowType(Qt.DownArrow)

            def _toggle(checked: bool, body=None, btn=None):
                if body is not None:
                    body.setVisible(checked)
                if btn is not None:
                    btn.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)

            body = QWidget()
            body_layout = QVBoxLayout(body)
            body_layout.setContentsMargins(0, 0, 0, 0)
            body_layout.setSpacing(4)
            toggle_btn.toggled.connect(lambda checked, b=body, t=toggle_btn: _toggle(checked, b, t))
            header.addWidget(toggle_btn)
            frame_layout.addLayout(header)
            frame_layout.addWidget(body)
            parent_layout.addWidget(frame)
            return body
        else:
            frame_layout.addLayout(header)
            body = QWidget()
            body_layout = QVBoxLayout(body)
            body_layout.setContentsMargins(0, 0, 0, 0)
            body_layout.setSpacing(4)
            frame_layout.addWidget(body)
            parent_layout.addWidget(frame)
            return body

    # ------------------------------------------------------------------
    def refresh_options(self):
        image_types = _normalize_list(self.settings_manager.get_image_types(), [
            "Wälzkörper", "Innenring", "Außenring", "Käfig", "Zahnrad"
        ])
        damage_categories = _normalize_list(self.settings_manager.get_damage_categories(), [
            "Visuell keine Defekte", "Kratzer", "Zykloidische Kratzer", "Stillstandsmarken", "Verschmierung"
        ])
        quality_options = _normalize_list(self.settings_manager.get_image_quality_options(), [
            "Low", "Medium", "High"
        ], limit=5)

        self._rebuild_image_type_buttons(image_types)
        self._rebuild_damage_buttons(damage_categories)
        self._rebuild_quality_buttons(quality_options)

    def _rebuild_image_type_buttons(self, options: list[str]):
        self._image_types = options
        layout = self._image_section_body.layout() if self._image_section_body else None
        if not isinstance(layout, QVBoxLayout):
            return
        self._clear_layout(layout)
        self._image_type_buttons = []
        for text in options:
            btn = ChipButton(text)
            btn.setCheckable(True)
            # Mehrfachauswahl möglich - speichern bei jeder Änderung
            btn.toggled.connect(lambda checked, b=btn: self._on_image_type_toggled(b, checked))
            layout.addWidget(btn)
            self._image_type_buttons.append(btn)
    
    def _on_image_type_toggled(self, button: ChipButton, checked: bool):
        """Wird aufgerufen wenn Bildart geändert wird"""
        if self._loading:
            return
        
        # Wenn Bildart gesetzt wird: automatisch "Bild verwenden" aktivieren
        if checked:
            self.set_use(True)
        
        # Mehrfachauswahl erlaubt - nur speichern
        self._schedule_save()
    
    def _on_visual_ok_toggled(self, button: ChipButton, checked: bool):
        """Wird aufgerufen wenn 'Visuell in Ordnung' aktiviert wird"""
        if self._loading:
            return
        
        if checked:
            # Alle anderen Schadenskategorien deaktivieren
            for btn in self._damage_buttons:
                if btn is not button and btn.isChecked():
                    btn.blockSignals(True)
                    btn.setChecked(False)
                    btn.blockSignals(False)
        
        self._schedule_save()
    
    def _on_damage_toggled(self, button: ChipButton, checked: bool):
        """Wird aufgerufen wenn eine Schadenskategorie (außer Visuell OK) aktiviert wird"""
        if self._loading:
            return
        
        if checked:
            # Wenn Schaden gesetzt wird: automatisch "Bild verwenden" aktivieren
            self.set_use(True)
            
            # Wenn ein Schaden aktiviert wird: "Visuell keine Defekte" deaktivieren
            for btn in self._damage_buttons:
                if btn.text() in self._visual_ok_texts and btn.isChecked():
                    btn.blockSignals(True)
                    btn.setChecked(False)
                    btn.blockSignals(False)
        
        self._schedule_save()
    
    def _filter_damage_categories_by_image_type(self, image_type: str):
        """Filtert Schadenskategorien basierend auf gewählter Bildart"""
        # Hole Mapping aus Settings
        mapping = self.settings_manager.get('image_type_damage_mapping', {}) or {}
        
        if image_type in mapping:
            # Zeige nur zugeordnete Schadenskategorien
            allowed_damages = set(mapping[image_type])
            
            for btn in self._damage_buttons:
                # Buttons ausblenden die nicht zur Bildart passen
                btn.setVisible(btn.text() in allowed_damages or btn.text() in self._visual_ok_texts)
        else:
            # Keine Zuordnung: Zeige alle
            for btn in self._damage_buttons:
                btn.setVisible(True)

    def _rebuild_damage_buttons(self, options: list[str]):
        self._damage = options
        layout = self._damage_section_body.layout() if self._damage_section_body else None
        if not isinstance(layout, QVBoxLayout):
            return
        self._clear_layout(layout)
        self._damage_buttons = []
        # Erkenne "keine Defekte" in Deutsch und Englisch
        self._visual_ok_texts = {
            t for t in options 
            if ("visuell" in t.lower() and "keine" in t.lower()) or 
               ("visually" in t.lower() and "no" in t.lower() and "defect" in t.lower())
        }
        for text in options:
            btn = ChipButton(text)
            if text in self._visual_ok_texts:
                # Nur grün wenn aktiv (checked)
                btn.setStyleSheet("""
                    ChipButton {
                        background-color: #f5f5f5;
                        color: #333;
                        border: 2px solid #ccc;
                        font-weight: normal;
                    }
                    ChipButton:checked {
                        background-color: #4caf50;
                        color: white;
                        border: 2px solid #388e3c;
                        font-weight: bold;
                    }
                    ChipButton:hover {
                        background-color: #e0e0e0;
                        border: 2px solid #999;
                    }
                """)
            btn.setCheckable(True)
            # Spezielle Logik für "Visuell in Ordnung"
            if text in self._visual_ok_texts:
                btn.toggled.connect(lambda checked, b=btn: self._on_visual_ok_toggled(b, checked))
            else:
                btn.toggled.connect(lambda checked, b=btn: self._on_damage_toggled(b, checked))
            layout.addWidget(btn)
            self._damage_buttons.append(btn)

    def _rebuild_quality_buttons(self, options: list[str]):
        self._quality = options
        layout = self._quality_section_body.layout() if self._quality_section_body else None
        if not isinstance(layout, QVBoxLayout):
            return
        self._clear_layout(layout)
        self._quality_buttons = []
        for text in options:
            btn = ChipButton(text)
            btn.setCheckable(True)
            btn.toggled.connect(lambda checked, b=btn: self._on_quality_toggled(b) if checked else None)
            layout.addWidget(btn)
            self._quality_buttons.append(btn)

    @staticmethod
    def _clear_layout(layout: QVBoxLayout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    # ------------------------------------------------------------------
    def set_path(self, path: str | None):
        self._path = path
        self._loading = True
        try:
            if not path:
                self.setEnabled(False)
                self.use_toggle.setChecked(False)
                self.gene_toggle.setChecked(False)
                for btn in self._damage_buttons + self._quality_buttons + self._image_type_buttons:
                    btn.setChecked(False)
                return

            self.setEnabled(True)
            eval_obj = get_evaluation(path) or {}
            
            # Auto-Bildart: Wenn keine Bildart vorhanden, aber Kürzel-Manager eine vorgibt
            if not eval_obj.get('image_type') and not eval_obj.get('image_types'):
                try:
                    ocr_info = get_ocr_info(path)
                    tag = ocr_info.get('tag', '').strip() if ocr_info else ''
                    if tag:
                        kurzel_table = self.settings_manager.get('kurzel_table', {}) or {}
                        kurzel_data = kurzel_table.get(tag, {})
                        predefined_image_type = kurzel_data.get('image_type', '').strip()
                        
                        if predefined_image_type:
                            # Setze vordefinierte Bildart
                            eval_obj['image_type'] = predefined_image_type
                            # Sofort speichern
                            set_evaluation(path, eval_obj)
                except Exception:
                    pass
            
            # Sprach-/Synonym-Normalisierung: Werte aus den EXIFs
            # (z.B. Deutsch) auf die aktuell sichtbaren Optionen abbilden.
            use_flag = get_used_flag(path)
            self.use_toggle.setChecked(bool(use_flag))
            self.gene_toggle.setChecked(bool(eval_obj.get('gene')))

            def _map_value_to_current(value: str, kind: str) -> str | None:
                if not isinstance(value, str):
                    return None
                value_norm = value.strip().lower()
                if not value_norm:
                    return None
                # Aktuelle Optionen (sichtbare Sprache)
                current = self._damage if kind == 'damage' else self._image_types
                current_lower = [s.strip().lower() for s in current]
                # Direkter Treffer in aktueller Sprache
                try:
                    idx = current_lower.index(value_norm)
                    return current[idx]
                except ValueError:
                    pass
                # Alternativ-Listen (DE/EN) positionsbasiert abgleichen
                de_key = 'damage_categories_de' if kind == 'damage' else 'image_types_de'
                en_key = 'damage_categories_en' if kind == 'damage' else 'image_types_en'
                de_list = [str(x) for x in (self.settings_manager.get(de_key, []) or [])]
                en_list = [str(x) for x in (self.settings_manager.get(en_key, []) or [])]
                de_lower = [s.strip().lower() for s in de_list]
                en_lower = [s.strip().lower() for s in en_list]
                # In DE suchen
                if value_norm in de_lower:
                    i = de_lower.index(value_norm)
                    if 0 <= i < len(current):
                        return current[i]
                # In EN suchen
                if value_norm in en_lower:
                    i = en_lower.index(value_norm)
                    if 0 <= i < len(current):
                        return current[i]
                # Kein Mapping m6glich
                return None

            # Kategorien mappen
            raw_categories = [c for c in (eval_obj.get('categories') or []) if isinstance(c, str)]
            mapped_categories = set()
            for c in raw_categories:
                mapped = _map_value_to_current(c, 'damage')
                mapped_categories.add(mapped if mapped else c)
            for btn in self._damage_buttons:
                btn.setChecked(btn.text() in mapped_categories)

            # Bildart mappen (Mehrfachauswahl)
            img_type = eval_obj.get('image_type')
            mapped_img_type = _map_value_to_current(img_type, 'image') if isinstance(img_type, str) else None
            raw_list = eval_obj.get('image_types') if isinstance(eval_obj.get('image_types'), list) else []
            
            # Debug deaktiviert für Performance
            # print(f"DEBUG: Image type buttons count: {len(self._image_type_buttons)}")
            # for btn in self._image_type_buttons:
            #     print(f"  - {btn.text()}: checkable={btn.isCheckable()}, enabled={btn.isEnabled()}")
            
            if not raw_list:
                single = mapped_img_type or eval_obj.get('image_type')
                raw_list = [single] if isinstance(single, str) and single else []
            selected = {str(x).strip() for x in raw_list}
            for btn in self._image_type_buttons:
                btn.setChecked(btn.text() in selected)

            # Quality mapping
            quality = eval_obj.get('quality')
            if isinstance(quality, str):
                q_cur = [s.strip().lower() for s in getattr(self, '_quality', [])]
                q_map = None
                q_val = quality.strip().lower()
                try:
                    # direct match in current language
                    qi = q_cur.index(q_val)
                    q_map = self._quality[qi]
                except ValueError:
                    de_list = [str(x) for x in (self.settings_manager.get('image_quality_options_de', []) or [])]
                    en_list = [str(x) for x in (self.settings_manager.get('image_quality_options_en', []) or [])]
                    de_lower = [s.strip().lower() for s in de_list]
                    en_lower = [s.strip().lower() for s in en_list]
                    if q_val in de_lower:
                        idx = de_lower.index(q_val)
                        if 0 <= idx < len(self._quality):
                            q_map = self._quality[idx]
                    elif q_val in en_lower:
                        idx = en_lower.index(q_val)
                        if 0 <= idx < len(self._quality):
                            q_map = self._quality[idx]
            else:
                q_map = None
            quality_found = False
            for btn in self._quality_buttons:
                btn.setChecked(btn.text() == (q_map or quality))
                if btn.isChecked():
                    quality_found = True
            if not quality_found:
                for btn in self._quality_buttons:
                    btn.setChecked(False)
        finally:
            self._loading = False

    def clear(self):
        self.set_path(None)

    # Helpers

    def _on_quality_toggled(self, selected_button: ChipButton):
        if self._loading:
            return
        for btn in self._quality_buttons:
            if btn is not selected_button and btn.isChecked():
                btn.blockSignals(True)
                btn.setChecked(False)
                btn.blockSignals(False)
        self._schedule_save()

    def _on_use_toggled(self, checked: bool):
        if self._loading:
            return
        self._schedule_save()
        if self._path:
            self.useChanged.emit(self._path, checked)

    def _schedule_save(self):
        if self._loading or not self._path:
            return
        self._auto_timer.start(2000)  # 2 Sekunden Debouncing für bessere Performance

    def commit_pending(self):
        """Speichert sofort, falls noch ein Auto-Save ansteht."""
        if not self._auto_timer.isActive():
            return
        self._auto_timer.stop()
        self._save_state()

    def _save_state(self, notes: str = None):
        if self._loading or not self._path:
            return
        path = self._path
        state = self.get_state()
        try:
            set_evaluation(
                path,
                categories=state['categories'],
                quality=state['quality'],
                image_type=state.get('image_type'),
                image_types=state.get('image_types'),
                notes=notes,  # Notes können optional von außen übergeben werden
                gene=state['gene'],
            )
            set_used_flag(path, state['use'])
            self.evaluationChanged.emit(path, state)
        except Exception:
            pass

    def get_state(self) -> dict:
        categories = [btn.text() for btn in self._damage_buttons if btn.isChecked()]
        image_types = [btn.text() for btn in self._image_type_buttons if btn.isChecked()]
        image_type = image_types[0] if image_types else None
        quality = next((btn.text() for btn in self._quality_buttons if btn.isChecked()), None)
        state = {
            'categories': categories,
            'image_type': image_type,
            'image_types': image_types,
            'quality': quality,
            'use': self.use_toggle.isChecked(),
            'gene': self.gene_toggle.isChecked(),
        }
        return state

    def apply_visual_ok(self):
        """Setzt "Visuell keine Defekte" und aktiviert Verwendung."""
        if self._loading:
            return
        self._loading = True
        try:
            any_set = False
            for btn in self._damage_buttons:
                mark = btn.text() in self._visual_ok_texts
                btn.setChecked(mark)
                if mark:
                    any_set = True
            if any_set:
                self._set_use(True)
        finally:
            self._loading = False
        self._schedule_save()

    def _set_use(self, value: bool):
        self.use_toggle.blockSignals(True)
        self.use_toggle.setChecked(value)
        self.use_toggle.blockSignals(False)

    def set_use(self, value: bool):
        if self._loading:
            return
        self._set_use(value)
        # Emittiere sofort Signal für Synchronisation, auch wenn Save verzögert ist
        if self._path:
            self.useChanged.emit(self._path, value)
        self._schedule_save()

    def set_gene(self, value: bool):
        if self._loading:
            return
        self.gene_toggle.blockSignals(True)
        self.gene_toggle.setChecked(value)
        self.gene_toggle.blockSignals(False)
        # Emittiere sofort evaluationChanged Signal
        if self._path:
            state = self.get_state()
            self.evaluationChanged.emit(self._path, state)
        self._schedule_save()

    def _on_settings_changed(self, changes: dict):
        keys = {'image_types', 'damage_categories', 'damage_categories_de', 'damage_categories_en',
                'image_types_de', 'image_types_en', 'image_quality_options'}
        if keys.intersection(changes.keys()):
            current_state = self.get_state() if self._path else None
            self._loading = True
            try:
                self.refresh_options()
                if current_state:
                    self._restore_state(current_state)
            finally:
                self._loading = False

    def _restore_state(self, state: dict):
        cats = set(state.get('categories') or [])
        for btn in self._damage_buttons:
            btn.setChecked(btn.text() in cats)
        imgs = set(state.get('image_types') or ([] if not state.get('image_type') else [state.get('image_type')]))
        for btn in self._image_type_buttons:
            btn.setChecked(btn.text() in imgs)
        qual = state.get('quality')
        for btn in self._quality_buttons:
            btn.setChecked(btn.text() == qual)
        self._set_use(bool(state.get('use')))
        self.gene_toggle.setChecked(bool(state.get('gene')))

    # ------------------------------------------------------------------
    # Keyboard Shortcuts Support
    
    def get_damage_categories(self) -> list[str]:
        """Gibt Liste der Schadenskategorien zurück für Index-Zugriff"""
        return [btn.text() for btn in self._damage_buttons]
    
    def get_image_types(self) -> list[str]:
        """Gibt Liste der Bildarten zurück für Index-Zugriff"""
        return [btn.text() for btn in self._image_type_buttons]
    
    def toggle_damage_by_index(self, index: int):
        """Toggle Schadenskategorie per Index (0-basiert)"""
        if self._loading or not self._path:
            return
        if 0 <= index < len(self._damage_buttons):
            btn = self._damage_buttons[index]
            btn.setChecked(not btn.isChecked())
    
    def set_image_type_by_index(self, index: int):
        """Setzt Bildart per Index (0-basiert), exklusiv"""
        if self._loading or not self._path:
            return
        if 0 <= index < len(self._image_type_buttons):
            target_btn = self._image_type_buttons[index]
            # Deaktiviere alle anderen
            for btn in self._image_type_buttons:
                if btn is not target_btn and btn.isChecked():
                    btn.setChecked(False)
            # Toggle den gewählten
            target_btn.setChecked(not target_btn.isChecked())
    
    def toggle_visual_ok(self):
        """Toggle 'Visuell keine Defekte' Kategorie"""
        if self._loading or not self._path:
            return
        # Finde "Visuell keine Defekte" Button
        for btn in self._damage_buttons:
            if btn.text() in self._visual_ok_texts:
                btn.setChecked(not btn.isChecked())
                break
