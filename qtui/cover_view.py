# -*- coding: utf-8 -*-
"""Titelbild-Verwaltung: Auswahl, Tagging und Beschreibung von Cover-Bildern."""

from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import Qt, QSize, Signal, QTimer
from PySide6.QtGui import QPixmap, QIcon, QImage, QColor, QPainter
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFileDialog,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QPlainTextEdit,
    QComboBox,
    QMessageBox,
    QFrame,
    QGridLayout,
    QRadioButton,
    QButtonGroup,
)

from utils_logging import get_logger
from utils_exif import get_cover_info, set_cover_info
from .settings_manager import get_settings_manager
from .widgets import ChipButton


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}


class CoverView(QWidget):
    """Verwaltet Bilder für Titelseiten inklusive Tag- und Beschreibungspflege."""

    folderChanged = Signal(str)
    imageSelected = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._log = get_logger('app', {"module": "qtui.cover_view"})
        self._log.info("module_started", extra={"event": "module_started"})

        self.settings_manager = get_settings_manager()
        self.settings_manager.settingsChanged.connect(self._on_settings_changed)

        self._current_folder: str = ""
        self._current_path: str = ""
        self._preview_original: Optional[QPixmap] = None
        self._thumb_cache: dict[tuple[str, bool], QIcon] = {}
        self._item_by_path: dict[str, QListWidgetItem] = {}
        self._suspend_settings_events = False
        self._loading_fields = False
        self._current_tag: str = ""
        self.tag_buttons: list[tuple[ChipButton, str]] = []
        self._nav_prev_btn = None
        self._nav_next_btn = None

        self._auto_save_timer = QTimer(self)
        self._auto_save_timer.setSingleShot(True)
        self._auto_save_timer.timeout.connect(self._auto_save_now)

        self._create_ui()

    # ---- UI Aufbau -------------------------------------------------
    def _create_ui(self):
        layout = QVBoxLayout(self)

        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter, 1)

        # Linke Seite: Ordner und Bildliste
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setSpacing(8)
        left_layout.setContentsMargins(0, 0, 0, 0)

        controls = QHBoxLayout()
        self.btn_select_folder = QPushButton("Ordner auswählen…")
        self.btn_select_folder.clicked.connect(self._select_folder)
        controls.addWidget(self.btn_select_folder)

        self.btn_refresh = QPushButton("Aktualisieren")
        self.btn_refresh.clicked.connect(self._refresh_folder)
        controls.addWidget(self.btn_refresh)
        controls.addStretch(1)

        left_layout.addLayout(controls)

        self.folder_label = QLabel("Kein Ordner gewählt")
        self.folder_label.setObjectName("coverFolderLabel")
        self.folder_label.setWordWrap(True)
        left_layout.addWidget(self.folder_label)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filter:"))
        self.filter_combo = QComboBox()
        self.filter_combo.addItem("Alle Tags", userData=None)
        self.filter_combo.currentIndexChanged.connect(self._apply_filter)
        filter_row.addWidget(self.filter_combo, 1)
        left_layout.addLayout(filter_row)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SingleSelection)
        self.list_widget.setIconSize(QSize(128, 96))
        self.list_widget.currentItemChanged.connect(self._on_item_changed)
        left_layout.addWidget(self.list_widget, 1)

        splitter.addWidget(left)

        # Rechte Seite
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setSpacing(8)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Titelbild verwenden Radio Buttons (oberhalb)
        use_row = QHBoxLayout()
        use_row.setContentsMargins(0, 0, 0, 0)
        use_row.setSpacing(12)
        use_row.addWidget(QLabel("Titelbild verwenden:"))
        self.use_yes_radio = QRadioButton("Ja")
        self.use_no_radio = QRadioButton("Nein")
        self.use_no_radio.setChecked(True)
        self.use_radio_group = QButtonGroup(self)
        self.use_radio_group.addButton(self.use_yes_radio)
        self.use_radio_group.addButton(self.use_no_radio)
        self.use_yes_radio.toggled.connect(lambda checked: self._on_use_radio_toggled(True, checked))
        self.use_no_radio.toggled.connect(lambda checked: self._on_use_radio_toggled(False, checked))
        use_row.addWidget(self.use_yes_radio)
        use_row.addWidget(self.use_no_radio)
        use_row.addStretch(1)
        right_layout.addLayout(use_row)

        # Bild + Overlay
        image_container = QFrame()
        image_container.setFrameShape(QFrame.NoFrame)
        grid = QGridLayout(image_container)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)

        self.preview_label = QLabel("Kein Bild ausgewählt")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setFrameShape(QFrame.StyledPanel)
        self.preview_label.setMinimumHeight(240)
        grid.addWidget(self.preview_label, 0, 0)

        self.nav_overlay = self._create_nav_overlay()
        grid.addWidget(self.nav_overlay, 0, 0, Qt.AlignBottom)

        right_layout.addWidget(image_container, 1)

        # Mangelbeschreibung direkt unter dem Bild
        self.defect_edit = QPlainTextEdit()
        self.defect_edit.setPlaceholderText("Optionale Mangelbeschreibung…")
        self.defect_edit.setMinimumHeight(80)
        self.defect_edit.textChanged.connect(self._on_defect_text_changed)
        right_layout.addWidget(self.defect_edit)

        # Tag-Auswahl darunter
        tag_group = QVBoxLayout()
        tag_group.setContentsMargins(0, 0, 0, 0)
        tag_group.setSpacing(6)

        info_label = QLabel("Tags bearbeitest du im Einstellungsreiter 'Titelbild-Tags'.")
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: #4a4a4a; font-size: 11px;")
        tag_group.addWidget(info_label)

        self.tag_button_panel = QWidget()
        self.tag_button_layout = QVBoxLayout(self.tag_button_panel)
        self.tag_button_layout.setContentsMargins(0, 0, 0, 0)
        self.tag_button_layout.setSpacing(6)
        tag_group.addWidget(self.tag_button_panel)

        tag_wrapper = QWidget()
        tag_wrapper.setLayout(tag_group)
        right_layout.addWidget(tag_wrapper)

        self.status_label = QLabel("")
        self.status_label.setObjectName("coverStatusLabel")
        right_layout.addWidget(self.status_label)

        splitter.addWidget(right)
        splitter.setSizes([360, 620])

        self._refresh_tag_sources()

    def _create_nav_overlay(self) -> QWidget:
        container = QWidget()
        container.setFixedHeight(52)
        container.setStyleSheet(
            "QWidget {"
            "background-color: rgba(35, 35, 35, 190);"
            "border-radius: 10px;"
            "padding: 6px;"
            "}"
        )
        layout = QHBoxLayout(container)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(12)

        self._nav_prev_btn = QPushButton("◀")
        self._nav_prev_btn.setFixedSize(48, 36)
        self._nav_prev_btn.setStyleSheet(
            "QPushButton { background-color: #555; color: white; border: 1px solid #777; border-radius: 6px; }"
            "QPushButton:hover { background-color: #666; }"
            "QPushButton:pressed { background-color: #444; }"
        )
        self._nav_prev_btn.clicked.connect(self._show_prev_image)

        self._nav_next_btn = QPushButton("▶")
        self._nav_next_btn.setFixedSize(48, 36)
        self._nav_next_btn.setStyleSheet(
            "QPushButton { background-color: #555; color: white; border: 1px solid #777; border-radius: 6px; }"
            "QPushButton:hover { background-color: #666; }"
            "QPushButton:pressed { background-color: #444; }"
        )
        self._nav_next_btn.clicked.connect(self._show_next_image)

        layout.addStretch(1)
        layout.addWidget(self._nav_prev_btn)
        layout.addWidget(self._nav_next_btn)
        layout.addStretch(1)
        return container

    # ---- Ordner / Listenhandling -----------------------------------
    def _select_folder(self):
        start_dir = self._current_folder or self.settings_manager.get_cover_last_folder() or os.getcwd()
        folder = QFileDialog.getExistingDirectory(self, "Bildordner auswählen", start_dir)
        if folder:
            self.set_folder(folder)

    def _refresh_folder(self):
        if not self._current_folder:
            QMessageBox.information(self, "Kein Ordner", "Bitte wählen Sie zuerst einen Ordner aus.")
            return
        self.set_folder(self._current_folder, emit_signal=False)

    def set_folder(self, folder: str, *, emit_signal: bool = True):
        folder = folder or ""
        if folder and not os.path.isdir(folder):
            QMessageBox.warning(self, "Ordner nicht gefunden", f"Der Ordner existiert nicht:\n{folder}")
            return

        if folder == self._current_folder:
            self._reload_list()
            return

        self._current_folder = folder
        self.settings_manager.set_cover_last_folder(folder)
        self.folder_label.setText(folder if folder else "Kein Ordner gewählt")
        self._reload_list()

        if emit_signal:
            self.folderChanged.emit(self._current_folder)

    def _reload_list(self):
        previous_path = self._current_path

        # Cache leeren, damit geänderte Use-States neue Icons erhalten
        self._thumb_cache.clear()

        self.list_widget.clear()
        self._item_by_path.clear()

        if not self._current_folder:
            return

        try:
            entries = []
            for name in sorted(os.listdir(self._current_folder)):
                ext = os.path.splitext(name)[1].lower()
                if ext in IMAGE_EXTENSIONS:
                    entries.append(os.path.join(self._current_folder, name))
        except Exception as exc:
            self._log.error("cover_list_load_failed", extra={"error": str(exc), "folder": self._current_folder})
            QMessageBox.critical(self, "Fehler", f"Bilder konnten nicht geladen werden:\n{exc}")
            return

        settings_map = self.settings_manager.get_cover_images()

        for path in entries:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, path)
            settings_entry = settings_map.get(path)
            if settings_entry is None:
                rel_path = os.path.relpath(path, self._current_folder)
                settings_entry = settings_map.get(rel_path)
            info = self._combine_cover_info(path, settings_entry)
            self._apply_item_metadata(item, info)
            self.list_widget.addItem(item)
            self._item_by_path[path] = item

        if previous_path and previous_path in self._item_by_path:
            self.list_widget.setCurrentItem(self._item_by_path[previous_path])
        elif entries:
            self.list_widget.setCurrentRow(0)

        self._refresh_filter_items()
        self._apply_filter()
        self._update_nav_buttons()

    def _apply_item_metadata(self, item: QListWidgetItem, info: dict):
        path = item.data(Qt.UserRole)
        filename = os.path.basename(path)
        tag = info.get('tag', '') if isinstance(info, dict) else ''
        item.setText(tag)
        item.setData(Qt.UserRole + 1, tag)
        tooltip_parts = [filename]
        if tag:
            tooltip_parts.append(f"Tag: {tag}")
        defect = info.get('defect_description', '') if isinstance(info, dict) else ''
        if defect:
            tooltip_parts.append(f"Mangel: {defect}")
        use_flag = bool(info.get('use', False))
        tooltip_parts.append("Verwenden: Ja" if use_flag else "Verwenden: Nein")
        item.setToolTip("\n".join(tooltip_parts))
        item.setData(Qt.UserRole + 2, use_flag)
        item.setIcon(self._icon_for_path(path, use_flag))

    def _icon_for_path(self, path: str, used: bool = True) -> QIcon:
        key = (path, bool(used))
        icon = self._thumb_cache.get(key)
        if icon:
            return icon
        pix = QPixmap(path)
        if pix.isNull():
            icon = self.style().standardIcon(self.style().SP_FileIcon)
        else:
            scaled = pix.scaled(128, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            if not used:
                scaled = self._create_unused_pixmap(scaled)
            icon = QIcon(scaled)
        self._thumb_cache[key] = icon
        return icon

    def _create_unused_pixmap(self, pix: QPixmap) -> QPixmap:
        img = pix.toImage().convertToFormat(QImage.Format_ARGB32)
        width = img.width()
        height = img.height()
        for y in range(height):
            for x in range(width):
                color = QColor(img.pixelColor(x, y))
                gray = int(0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue())
                blended = int(gray * 0.65 + 255 * 0.35)
                alpha = int(color.alpha() * 0.75)
                img.setPixelColor(x, y, QColor(blended, blended, blended, alpha))
        dull = QPixmap.fromImage(img)
        painter = QPainter(dull)
        painter.fillRect(dull.rect(), QColor(255, 255, 255, 35))
        painter.end()
        return dull

    # ---- Datensynchronisation --------------------------------------
    def _combine_cover_info(self, path: str, settings_entry: Optional[dict]) -> dict:
        file_info = get_cover_info(path)
        entry = settings_entry or {}
        if isinstance(entry, dict):
            for key in ("tag", "defect_description"):
                value = entry.get(key)
                if isinstance(value, str) and value.strip():
                    file_info[key] = value.strip()
            if 'use' in entry:
                file_info['use'] = bool(entry.get('use'))
        # Beschreibung wird nicht mehr verwendet
        file_info.pop('description', None)
        if 'use' not in file_info:
            file_info['use'] = False
        return file_info

    def _save_current_entry(self):
        if not self._current_path:
            return
        if self._loading_fields:
            return
        self._auto_save_timer.stop()

        tag = (self._current_tag or '').strip()
        defect = self.defect_edit.toPlainText().strip()
        use = self.use_yes_radio.isChecked()

        data = {}
        if tag:
            data['tag'] = tag
        if defect:
            data['defect_description'] = defect
        data['use'] = use

        empty_payload = not tag and not defect and not use

        try:
            self._suspend_settings_events = True
            if empty_payload:
                self.settings_manager.clear_cover_image(self._current_path)
            else:
                self.settings_manager.set_cover_image_data(self._current_path, data)
            if self._current_folder:
                rel_key = os.path.relpath(self._current_path, self._current_folder)
                if rel_key != self._current_path:
                    self.settings_manager.clear_cover_image(rel_key)
            set_cover_info(
                self._current_path,
                tag=tag,
                description="",
                defect_description=defect,
                use=use,
            )
            self.status_label.setText("Gespeichert")
            item = self._item_by_path.get(self._current_path)
            if item:
                info = data if not empty_payload else get_cover_info(self._current_path)
                self._apply_item_metadata(item, info)
            self._refresh_filter_items()
            self._apply_filter()
        except Exception as exc:
            self._log.error("cover_save_failed", extra={"error": str(exc), "path": self._current_path})
            QMessageBox.critical(self, "Fehler", f"Speichern fehlgeschlagen:\n{exc}")
        finally:
            self._suspend_settings_events = False

    def _schedule_auto_save(self, *_, delay_ms: int = 400):
        if self._loading_fields or not self._current_path:
            return
        self._auto_save_timer.start(delay_ms)

    def _auto_save_now(self):
        if self._loading_fields or not self._current_path:
            return
        self._save_current_entry()

    # ---- Auswahl / Formular ----------------------------------------
    def _on_item_changed(self, current: Optional[QListWidgetItem], previous: Optional[QListWidgetItem]):
        if previous and self._current_path:
            self._save_current_entry()

        if not current:
            self._current_path = ""
            self.preview_label.setText("Kein Bild ausgewählt")
            self._preview_original = None
            return

        path = current.data(Qt.UserRole)
        self._current_path = path
        self.imageSelected.emit(path)

        info = self._combine_cover_info(path, self.settings_manager.get_cover_image_data(path))

        self._loading_fields = True
        self._set_selected_tag(info.get('tag', ''))
        self.defect_edit.setPlainText(info.get('defect_description', ''))
        self._set_use_flag(bool(info.get('use', False)), schedule=False)
        self._loading_fields = False
        self._preview_item_update()

        self._update_preview(path)
        self.status_label.setText("")
        self._update_nav_buttons()

    def _update_preview(self, path: str):
        pix = QPixmap(path)
        if pix.isNull():
            self.preview_label.setText("Vorschau nicht verfügbar")
            self.preview_label.setPixmap(QPixmap())
            self._preview_original = None
            return
        self._preview_original = pix
        self._apply_preview_scale()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_preview_scale()

    def _apply_preview_scale(self):
        if not self._preview_original:
            return
        target = self.preview_label.size() - QSize(12, 12)
        if target.width() <= 0 or target.height() <= 0:
            target = self.preview_label.size()
        if target.width() <= 0 or target.height() <= 0:
            return
        scaled = self._preview_original.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview_label.setPixmap(scaled)

    # ---- Tag-Verwaltung --------------------------------------------
    def _refresh_tag_sources(self):
        tags = self.settings_manager.get_cover_tags()
        self._build_tag_buttons(tags)
        self._refresh_filter_items(tags)
        self._apply_filter()

    def _build_tag_buttons(self, tags: list[str]):
        selected = self._current_tag
        # Layout leeren
        while self.tag_button_layout.count():
            item = self.tag_button_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.tag_buttons = []

        # "Kein Tag" Option
        none_button = ChipButton("Kein Tag")
        none_button.setCheckable(True)
        none_button.toggled.connect(lambda checked: self._on_tag_selected('') if checked else None)
        self.tag_buttons.append((none_button, ''))
        self.tag_button_layout.addWidget(none_button)

        for tag in tags:
            btn = ChipButton(tag)
            btn.setCheckable(True)
            btn.toggled.connect(lambda checked, value=tag: self._on_tag_selected(value) if checked else None)
            self.tag_buttons.append((btn, tag))
            self.tag_button_layout.addWidget(btn)

        if selected and all(value != selected for _, value in self.tag_buttons if value):
            orphan_btn = ChipButton(selected)
            orphan_btn.setCheckable(True)
            orphan_btn.setStyleSheet("ChipButton { background-color: #ffc107; color: black; }")
            orphan_btn.toggled.connect(lambda checked, value=selected: self._on_tag_selected(value) if checked else None)
            self.tag_buttons.append((orphan_btn, selected))
            self.tag_button_layout.addWidget(orphan_btn)

        self.tag_button_layout.addStretch(1)
        self._set_selected_tag(selected)
        self._update_nav_buttons()
        self._preview_item_update()

    def _set_selected_tag(self, tag: str):
        self._current_tag = tag or ''
        found = False
        for btn, value in self.tag_buttons:
            btn.blockSignals(True)
            should_check = (value == self._current_tag) if value else self._current_tag == ''
            btn.setChecked(should_check)
            btn.blockSignals(False)
            if should_check:
                found = True
        if not found and self.tag_buttons:
            # Fallback auf "Kein Tag"
            self._current_tag = ''
            for btn, value in self.tag_buttons:
                btn.blockSignals(True)
                btn.setChecked(value == '')
                btn.blockSignals(False)

    def _on_tag_selected(self, tag: str):
        if self._loading_fields:
            self._current_tag = tag or ''
            return
        self._set_selected_tag(tag)
        self._set_use_flag(bool(tag), schedule=False)
        self.status_label.setText("")
        self._preview_item_update(tag=self._current_tag)
        self._schedule_auto_save()
        self._update_nav_buttons()

    def _set_use_flag(self, value: bool, schedule: bool = True):
        current = self.use_yes_radio.isChecked()
        if current == value and self.use_no_radio.isChecked() == (not value):
            if schedule and not self._loading_fields:
                self._schedule_auto_save()
            return
        for btn in (self.use_yes_radio, self.use_no_radio):
            btn.blockSignals(True)
        self.use_yes_radio.setChecked(value)
        self.use_no_radio.setChecked(not value)
        for btn in (self.use_yes_radio, self.use_no_radio):
            btn.blockSignals(False)
        if not self._loading_fields:
            self._preview_item_update(use=value)
            if schedule:
                self._schedule_auto_save()

    def _on_use_radio_toggled(self, value: bool, checked: bool):
        if not checked or self._loading_fields:
            return
        self._preview_item_update(use=value)
        self._schedule_auto_save()

    def _preview_item_update(self, tag: Optional[str] = None, use: Optional[bool] = None):
        if not self._current_path:
            return
        item = self._item_by_path.get(self._current_path)
        if not item:
            return
        info = {
            'tag': tag if tag is not None else self._current_tag,
            'defect_description': self.defect_edit.toPlainText().strip(),
            'use': use if use is not None else self.use_yes_radio.isChecked(),
        }
        self._apply_item_metadata(item, info)

    def _on_defect_text_changed(self):
        self._preview_item_update()
        self._schedule_auto_save(delay_ms=800)

    # ---- Filter ----------------------------------------------------
    def _refresh_filter_items(self, tags: Optional[list[str]] = None):
        tags = tags if tags is not None else self.settings_manager.get_cover_tags()
        current_value = self.filter_combo.currentData()
        current_text = self.filter_combo.currentText()
        self.filter_combo.blockSignals(True)
        self.filter_combo.clear()
        self.filter_combo.addItem("Alle Tags", userData=None)
        for tag in tags or []:
            self.filter_combo.addItem(tag, userData=tag)
        if current_value and current_value in tags:
            index = self.filter_combo.findData(current_value)
            if index >= 0:
                self.filter_combo.setCurrentIndex(index)
        elif current_text and current_text in tags:
            index = self.filter_combo.findText(current_text)
            if index >= 0:
                self.filter_combo.setCurrentIndex(index)
        else:
            self.filter_combo.setCurrentIndex(0)
        self.filter_combo.blockSignals(False)

    def _apply_filter(self):
        selected_tag = self.filter_combo.currentData()
        for row in range(self.list_widget.count()):
            item = self.list_widget.item(row)
            item_tag = item.data(Qt.UserRole + 1)
            hidden = bool(selected_tag) and (item_tag != selected_tag)
            item.setHidden(hidden)
        visible = self._visible_indices()
        if visible:
            current_row = self.list_widget.currentRow()
            if current_row not in visible:
                self.list_widget.setCurrentRow(visible[0])
        self._update_nav_buttons()

    # ---- Settings-Listener -----------------------------------------
    def _on_settings_changed(self, changes: dict):
        if self._suspend_settings_events:
            return
        if 'cover_tags' in changes:
            self._refresh_tag_sources()
        if 'cover_images' in changes:
            self._reload_list()

    # ---- Navigation -------------------------------------------------
    def _visible_indices(self) -> list[int]:
        return [i for i in range(self.list_widget.count()) if not self.list_widget.item(i).isHidden()]

    def _current_visible_index(self) -> int:
        current_row = self.list_widget.currentRow()
        visible = self._visible_indices()
        try:
            return visible.index(current_row)
        except ValueError:
            return -1

    def _move_selection(self, step: int):
        visible = self._visible_indices()
        if not visible:
            return
        current_idx = self._current_visible_index()
        if current_idx == -1:
            target_row = visible[0]
        else:
            new_idx = current_idx + step
            new_idx = max(0, min(len(visible) - 1, new_idx))
            target_row = visible[new_idx]
        if 0 <= target_row < self.list_widget.count():
            self.list_widget.setCurrentRow(target_row)

    def _show_prev_image(self):
        self._move_selection(-1)

    def _show_next_image(self):
        self._move_selection(1)

    def _update_nav_buttons(self):
        if not self._nav_prev_btn or not self._nav_next_btn:
            return
        visible = self._visible_indices()
        if not visible:
            self._nav_prev_btn.setEnabled(False)
            self._nav_next_btn.setEnabled(False)
            return
        current_idx = self._current_visible_index()
        if current_idx == -1:
            self._nav_prev_btn.setEnabled(False)
            self._nav_next_btn.setEnabled(len(visible) > 1)
            return
        self._nav_prev_btn.setEnabled(current_idx > 0)
        self._nav_next_btn.setEnabled(current_idx < len(visible) - 1)
