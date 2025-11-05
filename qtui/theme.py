# -*- coding: utf-8 -*-
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt


# ==================== THEMES ====================

class Theme:
    """Base Theme-Klasse mit allen Farbdefinitionen"""
    
    def __init__(self, name: str):
        self.name = name
        # Basis-Farben
        self.background = "#ffffff"
        self.foreground = "#1f2328"
        self.primary = "#0969da"
        self.secondary = "#f6f8fa"
        self.accent = "#0b57d0"
        self.border = "#d0d7de"
        self.hover = "#f3f4f6"
        self.pressed = "#e1e4e8"
        self.selected = "#e7f0fe"
        self.disabled = "#8c959f"
        # Erweiterte Farben
        self.success = "#1a7f37"
        self.warning = "#bf8700"
        self.error = "#cf222e"
        self.info = "#0969da"
        # Widget-spezifische Farben
        self.header_bg = "#f6f8fa"
        self.header_fg = "#1f2328"
        self.header_border = "#e3e6e8"
        self.input_bg = "#ffffff"
        self.input_fg = "#1f2328"
        self.input_border = "#d0d7de"
        self.button_bg = "#f6f8fa"
        self.button_fg = "#1f2328"
        self.button_border = "#d0d7de"
        
    def to_qss(self) -> str:
        """Generiert QSS-Stylesheet aus Theme-Farben"""
        return f"""
/* ==================== GLOBAL ==================== */
QWidget {{
    background-color: {self.background};
    color: {self.foreground};
    font-family: 'Segoe UI', 'Arial', sans-serif;
    font-size: 14px;
}}

QMainWindow {{
    background-color: {self.background};
}}

/* ==================== BUTTONS ==================== */
QPushButton {{
    background-color: {self.button_bg};
    color: {self.button_fg};
    border: 1px solid {self.button_border};
    padding: 6px 16px;
    border-radius: 6px;
    min-height: 28px;
}}

QPushButton:hover {{
    background-color: {self.hover};
    border-color: {self.primary};
}}

QPushButton:pressed {{
    background-color: {self.pressed};
}}

QPushButton:disabled {{
    background-color: {self.secondary};
    color: {self.disabled};
    border-color: {self.border};
}}

QPushButton:checked {{
    background-color: {self.primary};
    color: {self.background};
    border-color: {self.primary};
}}

/* ==================== INPUT FIELDS ==================== */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {self.input_bg};
    color: {self.input_fg};
    border: 1px solid {self.input_border};
    padding: 6px 12px;
    border-radius: 6px;
    selection-background-color: {self.selected};
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border: 2px solid {self.primary};
    padding: 5px 11px;
}}

QLineEdit:disabled, QTextEdit:disabled {{
    background-color: {self.secondary};
    color: {self.disabled};
}}

/* ==================== COMBOBOX ==================== */
QComboBox {{
    background-color: {self.input_bg};
    color: {self.input_fg};
    border: 1px solid {self.input_border};
    padding: 6px 12px;
    border-radius: 6px;
    min-height: 28px;
}}

QComboBox:hover {{
    border-color: {self.primary};
}}

QComboBox:focus {{
    border: 2px solid {self.primary};
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid {self.foreground};
    margin-right: 6px;
}}

QComboBox QAbstractItemView {{
    background-color: {self.background};
    border: 1px solid {self.border};
    selection-background-color: {self.selected};
    selection-color: {self.accent};
    outline: none;
}}

/* ==================== SPINBOX ==================== */
QSpinBox, QDoubleSpinBox {{
    background-color: {self.input_bg};
    color: {self.input_fg};
    border: 1px solid {self.input_border};
    padding: 6px 12px;
    border-radius: 6px;
}}

QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 2px solid {self.primary};
}}

/* ==================== CHECKBOX & RADIO ==================== */
QCheckBox, QRadioButton {{
    spacing: 8px;
    color: {self.foreground};
}}

QCheckBox::indicator, QRadioButton::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid {self.border};
    background-color: {self.input_bg};
}}

QCheckBox::indicator {{
    border-radius: 4px;
}}

QRadioButton::indicator {{
    border-radius: 9px;
}}

QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {self.primary};
}}

QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background-color: {self.primary};
    border-color: {self.primary};
}}

QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
    background-color: {self.secondary};
    border-color: {self.disabled};
}}

/* ==================== TABS ==================== */
QTabWidget::pane {{
    border: 1px solid {self.border};
    border-radius: 6px;
    background-color: {self.background};
}}

QTabBar::tab {{
    background-color: {self.secondary};
    color: {self.foreground};
    border: 1px solid {self.border};
    padding: 8px 16px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}}

QTabBar::tab:selected {{
    background-color: {self.background};
    border-bottom-color: {self.background};
    font-weight: bold;
}}

QTabBar::tab:hover {{
    background-color: {self.hover};
}}

/* ==================== PROGRESSBAR ==================== */
QProgressBar {{
    border: 1px solid {self.border};
    border-radius: 6px;
    text-align: center;
    background-color: {self.secondary};
    color: {self.foreground};
    min-height: 20px;
}}

QProgressBar::chunk {{
    background-color: {self.primary};
    border-radius: 5px;
}}

/* ==================== SLIDER ==================== */
QSlider::groove:horizontal {{
    border: 1px solid {self.border};
    height: 6px;
    background: {self.secondary};
    border-radius: 3px;
}}

QSlider::handle:horizontal {{
    background: {self.primary};
    border: 1px solid {self.primary};
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}}

QSlider::handle:horizontal:hover {{
    background: {self.accent};
    border-color: {self.accent};
}}

/* ==================== SCROLLBAR ==================== */
QScrollBar:vertical {{
    border: none;
    background-color: {self.secondary};
    width: 12px;
    border-radius: 6px;
}}

QScrollBar::handle:vertical {{
    background-color: {self.border};
    border-radius: 6px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {self.primary};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    border: none;
    background-color: {self.secondary};
    height: 12px;
    border-radius: 6px;
}}

QScrollBar::handle:horizontal {{
    background-color: {self.border};
    border-radius: 6px;
    min-width: 30px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {self.primary};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* ==================== TREEVIEW & LISTVIEW ==================== */
QTreeView, QListView, QTableView {{
    background-color: {self.background};
    alternate-background-color: {self.secondary};
    border: 1px solid {self.border};
    border-radius: 6px;
    color: {self.foreground};
    selection-background-color: {self.selected};
    selection-color: {self.accent};
    outline: none;
}}

QTreeView::item, QListView::item, QTableView::item {{
    padding: 4px;
    border: none;
}}

QTreeView::item:hover, QListView::item:hover, QTableView::item:hover {{
    background-color: {self.hover};
}}

QTreeView::item:selected, QListView::item:selected, QTableView::item:selected {{
    background-color: {self.selected};
    color: {self.accent};
}}

QHeaderView::section {{
    background-color: {self.header_bg};
    color: {self.header_fg};
    border: 1px solid {self.header_border};
    padding: 6px;
    font-weight: bold;
}}

QHeaderView::section:hover {{
    background-color: {self.hover};
}}

/* ==================== MENUBAR & MENU ==================== */
QMenuBar {{
    background-color: {self.background};
    color: {self.foreground};
    border-bottom: 1px solid {self.border};
}}

QMenuBar::item {{
    padding: 6px 12px;
    background-color: transparent;
}}

QMenuBar::item:selected {{
    background-color: {self.hover};
}}

QMenu {{
    background-color: {self.background};
    border: 1px solid {self.border};
    padding: 4px;
}}

QMenu::item {{
    padding: 6px 24px 6px 12px;
    border-radius: 4px;
}}

QMenu::item:selected {{
    background-color: {self.selected};
    color: {self.accent};
}}

QMenu::separator {{
    height: 1px;
    background-color: {self.border};
    margin: 4px 8px;
}}

/* ==================== TOOLBAR ==================== */
QToolBar {{
    background-color: {self.background};
    border: none;
    spacing: 4px;
    padding: 4px;
}}

QToolButton {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 6px;
}}

QToolButton:hover {{
    background-color: {self.hover};
    border-color: {self.border};
}}

QToolButton:pressed {{
    background-color: {self.pressed};
}}

/* ==================== DOCKWIDGET ==================== */
QDockWidget {{
    color: {self.foreground};
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}}

QDockWidget::title {{
    background-color: {self.header_bg};
    padding: 6px;
    border: 1px solid {self.border};
    font-weight: bold;
}}

/* ==================== GROUPBOX ==================== */
QGroupBox {{
    border: 1px solid {self.border};
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 12px;
    font-weight: bold;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 4px 8px;
    background-color: {self.background};
    border-radius: 4px;
}}

/* ==================== TOOLTIP ==================== */
QToolTip {{
    background-color: {self.background};
    color: {self.foreground};
    border: 1px solid {self.border};
    padding: 6px;
    border-radius: 6px;
}}

/* ==================== STATUSBAR ==================== */
QStatusBar {{
    background-color: {self.secondary};
    color: {self.foreground};
    border-top: 1px solid {self.border};
}}

/* ==================== DIALOG ==================== */
QDialog {{
    background-color: {self.background};
}}
"""


class LightTheme(Theme):
    """Standard Light Theme (GitHub-inspired)"""
    
    def __init__(self):
        super().__init__("Light")
        # Bereits definierte Standardwerte aus der Base-Klasse


class DarkTheme(Theme):
    """Standard Dark Theme (GitHub Dark)"""
    
    def __init__(self):
        super().__init__("Dark")
        self.background = "#0d1117"
        self.foreground = "#e6edf3"
        self.primary = "#1f6feb"
        self.secondary = "#161b22"
        self.accent = "#58a6ff"
        self.border = "#30363d"
        self.hover = "#252b35"
        self.pressed = "#30363d"
        self.selected = "#1f2a35"
        self.disabled = "#484f58"
        self.success = "#2ea043"
        self.warning = "#d29922"
        self.error = "#f85149"
        self.info = "#58a6ff"
        self.header_bg = "#161b22"
        self.header_fg = "#c9d1d9"
        self.header_border = "#30363d"
        self.input_bg = "#0d1117"
        self.input_fg = "#e6edf3"
        self.input_border = "#30363d"
        # Chiplets dunkler für bessere Integration in Dark Mode
        self.button_bg = "#1c2128"
        self.button_fg = "#c9d1d9"
        self.button_border = "#30363d"


class BlueTheme(Theme):
    """Blue Theme (VS Code inspired)"""
    
    def __init__(self):
        super().__init__("Blue")
        self.background = "#1e1e1e"
        self.foreground = "#d4d4d4"
        self.primary = "#007acc"
        self.secondary = "#252526"
        self.accent = "#0098ff"
        self.border = "#3e3e42"
        self.hover = "#2a2d2e"
        self.pressed = "#094771"
        self.selected = "#264f78"
        self.disabled = "#656565"
        self.success = "#4ec9b0"
        self.warning = "#dcdcaa"
        self.error = "#f48771"
        self.info = "#9cdcfe"
        self.header_bg = "#252526"
        self.header_fg = "#d4d4d4"
        self.header_border = "#3e3e42"
        self.input_bg = "#3c3c3c"
        self.input_fg = "#d4d4d4"
        self.input_border = "#3e3e42"
        self.button_bg = "#0e639c"
        self.button_fg = "#ffffff"
        self.button_border = "#007acc"


class HighContrastTheme(Theme):
    """High Contrast Theme (Barrierefreiheit)"""
    
    def __init__(self):
        super().__init__("High Contrast")
        self.background = "#000000"
        self.foreground = "#ffffff"
        self.primary = "#ffff00"
        self.secondary = "#1a1a1a"
        self.accent = "#00ff00"
        self.border = "#ffffff"
        self.hover = "#333333"
        self.pressed = "#666666"
        self.selected = "#0000ff"
        self.disabled = "#808080"
        self.success = "#00ff00"
        self.warning = "#ffff00"
        self.error = "#ff0000"
        self.info = "#00ffff"
        self.header_bg = "#1a1a1a"
        self.header_fg = "#ffffff"
        self.header_border = "#ffffff"
        self.input_bg = "#000000"
        self.input_fg = "#ffffff"
        self.input_border = "#ffffff"
        self.button_bg = "#1a1a1a"
        self.button_fg = "#ffffff"
        self.button_border = "#ffffff"


# Verfügbare Themes
THEMES = {
    "Light": LightTheme(),
    "Dark": DarkTheme(),
    "Blue": BlueTheme(),
    "High Contrast": HighContrastTheme()
}


# ==================== THEME FUNCTIONS ====================

def apply_theme(theme_name: str = "Light") -> None:
    """Wendet ein Theme an"""
    app = QApplication.instance()
    if not app:
        return
        
    theme = THEMES.get(theme_name, THEMES["Light"])
    app.setStyleSheet(theme.to_qss())


def apply_theme_from_bool(dark: bool) -> None:
    """Legacy-Funktion für Kompatibilität"""
    apply_theme("Dark" if dark else "Light")


def get_available_themes() -> list:
    """Gibt Liste aller verfügbaren Themes zurück"""
    return list(THEMES.keys())



