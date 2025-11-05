# -*- coding: utf-8 -*-
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox,
    QComboBox, QProgressBar, QTabWidget, QTreeView, QLineEdit, QFrame, QSplitter,
    QTextEdit, QAbstractItemView, QMessageBox
)
from PySide6.QtGui import (
    QPainter, QColor, QBrush, QAction, QIcon, QStandardItemModel, QStandardItem, QKeySequence
)
from PySide6.QtCore import (
    Qt, QRectF, QPropertyAnimation, QEasingCurve, Property,
    QModelIndex, QSortFilterProxyModel, QTimer, QSize, Signal
)
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle, QHeaderView

# ------------------- Custom Controls -------------------
class ToggleSwitch(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(52, 30)
        self.setCursor(Qt.PointingHandCursor)
        self._checked = False
        self._pos = 0.0
        
    def isChecked(self):
        return self._checked
        
    def setChecked(self, checked):
        self._checked = checked
        self._pos = 1.0 if checked else 0.0
        self.update()
        self.toggled.emit(checked)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setChecked(not self._checked)
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Background track
        track_rect = QRectF(0, 0, 52, 30)
        bg_color = QColor("#4CAF50") if self._checked else QColor("#CCCCCC")
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(bg_color))
        painter.drawRoundedRect(track_rect, 15, 15)
        
        # Thumb circle
        thumb_size = 26
        thumb_x = 2 + (50 - thumb_size) * self._pos
        painter.setBrush(QBrush(Qt.white))
        painter.drawEllipse(QRectF(thumb_x, 2, thumb_size, thumb_size))
        
    toggled = Signal(bool)

class ChipButton(QPushButton):
    def __init__(self, text):
        super().__init__(text)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("""
        QPushButton {
            border: 1px solid #aaaaaa; border-radius: 16px;
            padding: 6px 14px; background: #f5f5f5;
        }
        QPushButton:hover { background: #eaeaea; }
        QPushButton:checked { background: #2196F3; color: white; border-color: #2196F3; }
        """)

class SegmentedControl(QWidget):
    def __init__(self, labels, checked=0, exclusive=True):
        super().__init__()
        l = QHBoxLayout(self); l.setSpacing(0); l.setContentsMargins(0,0,0,0)
        self.group = []
        for i, lab in enumerate(labels):
            b = QPushButton(lab); b.setCheckable(True); b.setCursor(Qt.PointingHandCursor)
            if i == checked: b.setChecked(True)
            b.setStyleSheet("""
            QPushButton { border: 1px solid #c9cdd2; background: #f8f9fb; padding: 6px 14px; }
            QPushButton:checked { background: #2196F3; color: white; }
            """)
            if i == 0:
                b.setStyleSheet(b.styleSheet()+"QPushButton{border-top-left-radius:6px;border-bottom-left-radius:6px;}")
            if i == len(labels)-1:
                b.setStyleSheet(b.styleSheet()+"QPushButton{border-top-right-radius:6px;border-bottom-right-radius:6px;}")
            if exclusive:
                b.toggled.connect(self._exclusive)
            l.addWidget(b); self.group.append(b)

    def _exclusive(self, _):
        # only allow one checked at a time
        sender = self.sender()
        if sender.isChecked():
            for b in self.group:
                if b is not sender:
                    b.setChecked(False)

# ------------------- Tree Helpers & Delegates -------------------
def model_basic():
    m = QStandardItemModel()
    m.setHorizontalHeaderLabels(["Bereich", "Status"])
    r = m.invisibleRootItem()
    def add(parent, a, b="", kids=None):
        A = QStandardItem(a); B = QStandardItem(b)
        if kids:
            for kw in kids:
                add(A, **kw)
        parent.appendRow([A,B])
    add(r, "Windpark Oerzen", kids=[
        dict(a="WEA 1", b="OK", kids=[
            dict(a="Turm", b="geprüft"),
            dict(a="Gondel", b="i.O."),
            dict(a="Rotorblatt A", b="leichter Schaden"),
        ]),
        dict(a="WEA 2", b="OK", kids=[
            dict(a="Turm", b="geprüft"),
            dict(a="Gondel", b="i.O."),
        ]),
        dict(a="Umspannwerk", b="Wartung fällig"),
    ])
    return m

def model_icons():
    m = QStandardItemModel(); m.setHorizontalHeaderLabels(["Objekt","Kategorie","Prio"])
    r = m.invisibleRootItem()
    def it(txt, icon=None):
        s = QStandardItem(txt); 
        if icon: s.setIcon(icon)
        s.setEditable(False); return s
    folder = QApplication.style().standardIcon(QStyle.SP_DirIcon)
    warni  = QApplication.style().standardIcon(QStyle.SP_MessageBoxWarning)
    park = it("Windpark Wiesenhagen", folder)
    r.appendRow([park, it("Standort"), it("—")])
    wea1 = it("WEA 1", folder); park.appendRow([wea1, it("WEA"), it("Mittel")])
    wea1.appendRow([it("Rotorblatt A"), it("Blatt"), it("Hoch")])
    wea1.appendRow([it("Rotorblatt B"), it("Blatt"), it("Niedrig")])
    wea1.appendRow([it("Brandmelder", warni), it("Sicherheit"), it("Hoch")])
    wea2 = it("WEA 2", folder); park.appendRow([wea2, it("WEA"), it("Niedrig")])
    wea2.appendRow([it("Gondel"), it("Maschine"), it("Mittel")])
    return m

class ToggleDelegate(QStyledItemDelegate):
    def paint(self, p: QPainter, opt: QStyleOptionViewItem, idx: QModelIndex):
        on = bool(idx.data(Qt.DisplayRole))
        if opt.state & QStyle.State_Selected:
            p.fillRect(opt.rect, opt.palette.highlight())
        r = opt.rect.adjusted(6, 6, -6, -6)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor("#4CAF50") if on else QColor("#B0B0B5")))
        p.drawRoundedRect(QRectF(r), r.height()/2, r.height()/2)
        d = r.height()-6
        x = r.right()-d-3 if on else r.left()+3
        p.setBrush(QBrush(Qt.white))
        p.drawEllipse(QRectF(x, r.top()+3, d, d))

    def editorEvent(self, ev, model, opt, idx):
        if ev.type() == ev.MouseButtonRelease:
            model.setData(idx, not bool(idx.data(Qt.DisplayRole)), Qt.EditRole)
            return True
        return False

class PillDelegate(QStyledItemDelegate):
    def paint(self, p: QPainter, opt: QStyleOptionViewItem, idx: QModelIndex):
        text = (idx.data(Qt.DisplayRole) or "")
        if opt.state & QStyle.State_Selected:
            p.fillRect(opt.rect, opt.palette.highlight())
        tags = [t.strip() for t in text.split(";") if t.strip()]
        x, y = opt.rect.left()+4, opt.rect.top()+4
        p.setRenderHint(QPainter.Antialiasing)
        for t in tags:
            fm = opt.fontMetrics
            w = fm.horizontalAdvance(t) + 16; h = fm.height() + 6
            p.setPen(QColor("#2196F3"))
            p.setBrush(QBrush(QColor(235,244,253)))
            p.drawRoundedRect(QRectF(x, y, w, h), 10, 10)
            p.drawText(QRectF(x+8, y, w-16, h), Qt.AlignVCenter|Qt.AlignLeft, t)
            x += w + 6

def model_delegates():
    m = QStandardItemModel(); m.setHorizontalHeaderLabels(["Objekt","Aktiv","Tags"])
    r = m.invisibleRootItem()
    def row(name, active, tags):
        a = QStandardItem(name); a.setEditable(False)
        b = QStandardItem(); b.setData(bool(active), Qt.DisplayRole)
        c = QStandardItem("; ".join(tags)); c.setEditable(False)
        r.appendRow([a,b,c])
    row("Automatisch speichern", True, ["Sicherheit"])
    row("E-Mail Benachrichtigung", False, ["Elektrik", "Mechanik"])
    row("Live-Refresh", True, ["Monitoring", "Debug"])
    return m

class FilterProxy(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self.setRecursiveFilteringEnabled(True)
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)
    def filterAcceptsRow(self, row, parent):
        if super().filterAcceptsRow(row, parent):
            return True
        idx = self.sourceModel().index(row, 0, parent)
        sm = self.sourceModel()
        for i in range(sm.rowCount(idx)):
            if self.filterAcceptsRow(i, idx):
                return True
        return False

# ------------------- Main UI Lab -------------------
LIGHT_QSS = """
QWidget{background:#ffffff;color:#1f2328;font-size:14px;}
QTreeView::item:selected{background:#e7f0fe;color:#0b57d0;}
QHeaderView::section{background:#f6f8fa;border:1px solid #e3e6e8;padding:4px;}
QPushButton{background:#f6f8fa;border:1px solid #d0d7de;padding:6px 12px;border-radius:6px;}
QPushButton:hover{background:#f3f4f6;}
QPushButton:pressed{background:#e1e4e8;}
QComboBox{background:#ffffff;border:1px solid #d0d7de;padding:6px 12px;border-radius:6px;}
QLineEdit{background:#ffffff;border:1px solid #d0d7de;padding:6px 12px;border-radius:6px;}
QProgressBar{border:1px solid #d0d7de;border-radius:6px;text-align:center;}
QProgressBar::chunk{background:#0969da;border-radius:6px;}
"""
DARK_QSS = """
QWidget{background:#0f1419;color:#e6edf3;font-size:14px;}
QTreeView::item:selected{background:#1f2a35;color:#a8c7fa;}
QHeaderView::section{background:#161b22;border:1px solid #30363d;padding:4px;color:#c9d1d9;}
QPushButton{background:#21262d;border:1px solid #30363d;padding:6px 12px;border-radius:6px;color:#e6edf3;}
QPushButton:hover{background:#30363d;}
QPushButton:pressed{background:#484f58;}
QComboBox{background:#0f1419;border:1px solid #30363d;padding:6px 12px;border-radius:6px;color:#e6edf3;}
QLineEdit{background:#0f1419;border:1px solid #30363d;padding:6px 12px;border-radius:6px;color:#e6edf3;}
QProgressBar{border:1px solid #30363d;border-radius:6px;text-align:center;color:#e6edf3;}
QProgressBar::chunk{background:#1f6feb;border-radius:6px;}
"""

class UILab(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PySide6 UI Lab – moderne Elemente & Tests")
        main = QVBoxLayout(self)
        # top bar
        bar = QHBoxLayout(); main.addLayout(bar)
        self.theme_switch = ToggleSwitch(); self.theme_switch.setToolTip("Dark Mode")
        bar.addWidget(QLabel("Dark Mode")); bar.addWidget(self.theme_switch)
        bar.addStretch(1)
        self.run_btn = QPushButton("Run Tests"); bar.addWidget(self.run_btn)

        # splitter: tabs + console
        split = QSplitter(Qt.Vertical); main.addWidget(split, 1)
        tabs = QTabWidget(); split.addWidget(tabs)
        self.console = QTextEdit(); self.console.setReadOnly(True); split.addWidget(self.console)
        split.setSizes([520, 160])

        # --- Tab Controls
        t_controls = QWidget(); l1 = QVBoxLayout(t_controls)
        # Toggles
        row1 = QHBoxLayout(); l1.addLayout(row1)
        self.t1 = ToggleSwitch(); self.t1.setChecked(True)
        self.t2 = ToggleSwitch()
        row1.addWidget(QLabel("Toggle A")); row1.addWidget(self.t1)
        row1.addWidget(QLabel("Toggle B")); row1.addWidget(self.t2); row1.addStretch(1)

        # Chips
        row2 = QHBoxLayout(); l1.addLayout(row2)
        row2.addWidget(QLabel("Chips:"))
        self.c1 = ChipButton("Sicherheit"); self.c1.setChecked(True)
        self.c2 = ChipButton("Elektrik")
        self.c3 = ChipButton("Mechanik"); self.c3.setChecked(True)
        for b in (self.c1, self.c2, self.c3): row2.addWidget(b)
        row2.addStretch(1)

        # Segment
        l1.addWidget(QLabel("Segmented:"))
        self.segment = SegmentedControl(["Low","Medium","High"], checked=1)
        l1.addWidget(self.segment)

        # Extras
        row3 = QHBoxLayout(); l1.addLayout(row3)
        self.combo = QComboBox(); self.combo.addItems(["—", "Option 1", "Option 2", "Option 3"])
        self.progress = QProgressBar(); self.progress.setRange(0,100); self.progress.setValue(20)
        self.msg_btn = QPushButton("Toast/Info")
        row3.addWidget(QLabel("Combo:")); row3.addWidget(self.combo)
        row3.addWidget(QLabel("Progress:")); row3.addWidget(self.progress)
        row3.addStretch(1); row3.addWidget(self.msg_btn)

        tabs.addTab(t_controls, "Controls")

        # --- Tab Tree Basic
        t_basic = QWidget(); l2 = QVBoxLayout(t_basic)
        self.tree_basic = QTreeView(); self.tree_basic.setModel(model_basic()); self.tree_basic.expandAll()
        self.tree_basic.setAlternatingRowColors(True)
        l2.addWidget(QLabel("Basic Tree (2 Spalten)")); l2.addWidget(self.tree_basic)
        tabs.addTab(t_basic, "Tree – Basic")

        # --- Tab Icons + Filter
        t_filter = QWidget(); l3 = QVBoxLayout(t_filter)
        src = model_icons(); self.proxy = FilterProxy(); self.proxy.setSourceModel(src)
        self.search = QLineEdit(); self.search.setPlaceholderText("Suche…"); self.search.textChanged.connect(self.proxy.setFilterFixedString)
        self.tree_icons = QTreeView(); self.tree_icons.setModel(self.proxy); self.tree_icons.expandAll()
        self.tree_icons.setAlternatingRowColors(True); self.tree_icons.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tree_icons.header().setStretchLastSection(False)
        hv = self.tree_icons.header()
        hv.setSectionResizeMode(0, QHeaderView.Stretch)
        hv.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hv.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        l3.addWidget(QLabel("Icons + Mehrspaltig + rekursiver Suchfilter")); l3.addWidget(self.search); l3.addWidget(self.tree_icons)
        tabs.addTab(t_filter, "Tree – Filter")

        # --- Tab Delegates
        t_del = QWidget(); l4 = QVBoxLayout(t_del)
        self.tree_del = QTreeView(); self.tree_del.setModel(model_delegates())
        self.tree_del.setItemDelegateForColumn(1, ToggleDelegate())
        self.tree_del.setItemDelegateForColumn(2, PillDelegate())
        self.tree_del.setAlternatingRowColors(True); self.tree_del.setRootIsDecorated(False)
        hd = self.tree_del.header()
        hd.setStretchLastSection(True)
        hd.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hd.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        l4.addWidget(QLabel("Custom Delegates (Toggle + Pill-Tags)")); l4.addWidget(self.tree_del)
        tabs.addTab(t_del, "Tree – Delegates")

        # --- Tab Toggle Tests
        t_toggle = QWidget(); l5 = QVBoxLayout(t_toggle)
        
        # Test ToggleSwitches
        toggle_row1 = QHBoxLayout(); l5.addLayout(toggle_row1)
        self.test_t1 = ToggleSwitch(); self.test_t1.setChecked(True)
        self.test_t2 = ToggleSwitch(); self.test_t2.setChecked(False)
        self.test_t3 = ToggleSwitch(); self.test_t3.setChecked(True)
        toggle_row1.addWidget(QLabel("Test Toggle 1:")); toggle_row1.addWidget(self.test_t1)
        toggle_row1.addWidget(QLabel("Test Toggle 2:")); toggle_row1.addWidget(self.test_t2)
        toggle_row1.addWidget(QLabel("Test Toggle 3:")); toggle_row1.addWidget(self.test_t3)
        toggle_row1.addStretch(1)
        
        # Status Labels
        status_row = QHBoxLayout(); l5.addLayout(status_row)
        self.status_t1 = QLabel("Toggle 1: OFF"); self.status_t1.setStyleSheet("color: red; font-weight: bold;")
        self.status_t2 = QLabel("Toggle 2: OFF"); self.status_t2.setStyleSheet("color: red; font-weight: bold;")
        self.status_t3 = QLabel("Toggle 3: OFF"); self.status_t3.setStyleSheet("color: red; font-weight: bold;")
        status_row.addWidget(self.status_t1)
        status_row.addWidget(self.status_t2)
        status_row.addWidget(self.status_t3)
        status_row.addStretch(1)
        
        # Test Buttons
        button_row = QHBoxLayout(); l5.addLayout(button_row)
        self.test_all_btn = QPushButton("Alle umschalten")
        self.reset_all_btn = QPushButton("Alle zurücksetzen")
        button_row.addWidget(self.test_all_btn)
        button_row.addWidget(self.reset_all_btn)
        button_row.addStretch(1)
        
        l5.addStretch(1)
        tabs.addTab(t_toggle, "Toggle Tests")

        # Signals -> console
        self._wire_signals()

        # keyboard shortcut: Ctrl+R run tests
        act = QAction(self); act.setShortcut(QKeySequence("Ctrl+R")); act.triggered.connect(self._run_tests)
        self.addAction(act)

        # theme switch
        self.theme_switch.toggled.connect(self._apply_theme)
        # Apply initial theme - start with light theme
        self._apply_theme(False)

        self.run_btn.clicked.connect(self._run_tests)
        self.msg_btn.clicked.connect(lambda: QMessageBox.information(self, "Info", "Alles gut – nur ein Test."))

    def _wire_signals(self):
        self.t1.toggled.connect(lambda v: self.log(f"Toggle A -> {v}"))
        self.t2.toggled.connect(lambda v: self.log(f"Toggle B -> {v}"))
        self.c1.toggled.connect(lambda v: self.log(f"Chip Sicherheit -> {v}"))
        self.c2.toggled.connect(lambda v: self.log(f"Chip Elektrik -> {v}"))
        self.c3.toggled.connect(lambda v: self.log(f"Chip Mechanik -> {v}"))
        for b in self.segment.group:
            b.toggled.connect(lambda v, btn=b: v and self.log(f"Segment -> {btn.text()}"))
        self.combo.currentTextChanged.connect(lambda t: self.log(f"Combo -> {t}"))
        self.search.textChanged.connect(lambda t: self.log(f"Search -> '{t}'"))
        self.tree_del.model().dataChanged.connect(lambda *_: self.log("Delegates: Toggle geändert"))
        
        # Test Toggle Signals
        self.test_t1.toggled.connect(lambda v: self._update_toggle_status(1, v))
        self.test_t2.toggled.connect(lambda v: self._update_toggle_status(2, v))
        self.test_t3.toggled.connect(lambda v: self._update_toggle_status(3, v))
        
        # Test Buttons
        self.test_all_btn.clicked.connect(self._toggle_all_test)
        self.reset_all_btn.clicked.connect(self._reset_all_test)

    def _apply_theme(self, dark):
        self.setStyleSheet(DARK_QSS if dark else LIGHT_QSS)
        self.log(f"Theme -> {'Dark' if dark else 'Light'}")

    def _run_tests(self):
        self.log("== Starte UI-Tests ==")
        # Toggle flip
        self.t1.setChecked(not self.t1.isChecked())
        self.t2.setChecked(True)
        # Chips
        self.c2.setChecked(True)
        # Segment -> High
        for b in self.segment.group:
            b.setChecked(b.text()=="High")
        # Combo -> Option 2
        self.combo.setCurrentIndex(2)
        # Progress advance
        v = (self.progress.value()+30) % 101
        self.progress.setValue(v)
        # Search -> 'Blatt'
        self.search.setText("Blatt")
        # Toggle delegate first row
        idx = self.tree_del.model().index(0,1)
        cur = bool(self.tree_del.model().data(idx, Qt.DisplayRole))
        self.tree_del.model().setData(idx, not cur, Qt.EditRole)
        self.log("== Tests abgeschlossen ==")

    def _update_toggle_status(self, toggle_num, checked):
        status_label = getattr(self, f"status_t{toggle_num}")
        if checked:
            status_label.setText(f"Toggle {toggle_num}: ON")
            status_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            status_label.setText(f"Toggle {toggle_num}: OFF")
            status_label.setStyleSheet("color: red; font-weight: bold;")
        self.log(f"Test Toggle {toggle_num} -> {checked}")

    def _toggle_all_test(self):
        self.test_t1.setChecked(not self.test_t1.isChecked())
        self.test_t2.setChecked(not self.test_t2.isChecked())
        self.test_t3.setChecked(not self.test_t3.isChecked())
        self.log("Alle Test-Toggles umgeschaltet")

    def _reset_all_test(self):
        self.test_t1.setChecked(False)
        self.test_t2.setChecked(False)
        self.test_t3.setChecked(False)
        self.log("Alle Test-Toggles zurückgesetzt")

    def log(self, msg):
        self.console.append(msg)

if __name__ == "__main__":
    import sys
    try:
        app = QApplication(sys.argv)
    except Exception as e:
        print("Fehler beim Starten von QApplication:", e)
        sys.exit(1)
    w = UILab()
    w.resize(980, 680)
    w.show()
    sys.exit(app.exec())


