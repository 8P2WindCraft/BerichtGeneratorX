# -*- coding: utf-8 -*-
"""Hilfe-Dialog für Tastaturkürzel"""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QPushButton, QHBoxLayout
from PySide6.QtCore import Qt


class ShortcutsHelpDialog(QDialog):
    """Dialog mit Übersicht aller Tastaturkürzel"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tastaturkürzel")
        self.resize(600, 700)
        
        layout = QVBoxLayout(self)
        
        # Text Browser für formatierte Darstellung
        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.setHtml(self._generate_shortcuts_html())
        layout.addWidget(browser)
        
        # Schließen-Button
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        close_btn = QPushButton("Schließen")
        close_btn.clicked.connect(self.accept)
        close_btn.setDefault(True)
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)
    
    def _generate_shortcuts_html(self) -> str:
        """Generiert HTML-Darstellung der Shortcuts"""
        return """
        <html>
        <head>
            <style>
                body {
                    font-family: 'Segoe UI', Arial, sans-serif;
                    margin: 16px;
                }
                h2 {
                    color: #1f6feb;
                    border-bottom: 2px solid #1f6feb;
                    padding-bottom: 8px;
                    margin-top: 24px;
                    margin-bottom: 16px;
                }
                table {
                    width: 100%;
                    border-collapse: collapse;
                    margin-bottom: 20px;
                }
                td {
                    padding: 8px 12px;
                    border-bottom: 1px solid #e0e0e0;
                }
                td:first-child {
                    font-weight: bold;
                    font-family: 'Consolas', 'Courier New', monospace;
                    color: #0969da;
                    width: 120px;
                }
                .section-intro {
                    color: #666;
                    margin-bottom: 12px;
                    font-style: italic;
                }
                .note {
                    background-color: #fff3cd;
                    border-left: 4px solid #ffc107;
                    padding: 12px;
                    margin-top: 16px;
                    border-radius: 4px;
                }
                .note-title {
                    font-weight: bold;
                    margin-bottom: 4px;
                }
            </style>
        </head>
        <body>
            <h1 style="color: #24292f; margin-bottom: 8px;">Tastaturkürzel Übersicht</h1>
            <p style="color: #666; margin-bottom: 24px;">
                Schnelle Bewertung und Navigation mit der Tastatur.<br>
                <strong>Wichtig:</strong> Shortcuts funktionieren nur, wenn das Beschreibungs-Textfeld nicht fokussiert ist.
            </p>
            
            <h2>⌨️ Navigation</h2>
            <p class="section-intro">Schnelle Bildnavigation</p>
            <table>
                <tr>
                    <td>← / →</td>
                    <td>Vorheriges / Nächstes Bild</td>
                </tr>
                <tr>
                    <td>Home / End</td>
                    <td>Erstes / Letztes Bild</td>
                </tr>
                <tr>
                    <td>Leertaste</td>
                    <td>Als "Visuell OK" markieren und zum nächsten Bild</td>
                </tr>
                <tr>
                    <td>X</td>
                    <td>Als "Beschädigt" markieren und zum nächsten Bild</td>
                </tr>
            </table>
            
            <h2>✓ Schnellbewertung</h2>
            <p class="section-intro">Bild schnell bewerten und markieren</p>
            <table>
                <tr>
                    <td>U</td>
                    <td>Toggle "Bild verwenden" (an/aus)</td>
                </tr>
                <tr>
                    <td>V</td>
                    <td>Toggle "Visuell keine Defekte" (an/aus)</td>
                </tr>
            </table>
            
            <h2>🎯 Bildart auswählen</h2>
            <p class="section-intro">Bildart festlegen (nur eine aktiv)</p>
            <table>
                <tr>
                    <td>Q</td>
                    <td>Gear (Zahnrad)</td>
                </tr>
                <tr>
                    <td>W</td>
                    <td>Rolling Element (Wälzkörper)</td>
                </tr>
                <tr>
                    <td>E</td>
                    <td>Inner ring (Innenring)</td>
                </tr>
                <tr>
                    <td>R</td>
                    <td>Outer ring (Außenring)</td>
                </tr>
                <tr>
                    <td>T</td>
                    <td>Cage (Käfig)</td>
                </tr>
            </table>
            
            <h2>🔧 Schadenskategorien</h2>
            <p class="section-intro">Schäden togglen (an/aus) - Mehrfachauswahl möglich</p>
            <table>
                <tr>
                    <td>1</td>
                    <td>Visuell keine Defekte</td>
                </tr>
                <tr>
                    <td>2</td>
                    <td>Scratches (Kratzer)</td>
                </tr>
                <tr>
                    <td>3</td>
                    <td>Cycloid Scratches (Zykloidische Kratzer)</td>
                </tr>
                <tr>
                    <td>4</td>
                    <td>Standstill marks (Stillstandsmarken)</td>
                </tr>
                <tr>
                    <td>5</td>
                    <td>Smearing (Verschmierung)</td>
                </tr>
                <tr>
                    <td>6</td>
                    <td>Particle passage (Partikeldurchgang)</td>
                </tr>
                <tr>
                    <td>7</td>
                    <td>Overrolling Marks (Überrollmarken)</td>
                </tr>
                <tr>
                    <td>8</td>
                    <td>Pitting</td>
                </tr>
                <tr>
                    <td>9</td>
                    <td>Others (Sonstige)</td>
                </tr>
            </table>
            
            <div class="note">
                <div class="note-title">💡 Tipp:</div>
                Die Tastaturkürzel funktionieren sowohl in der Einzelbild- als auch in der Galerie-Ansicht.
                In der Galerie muss ein Bild ausgewählt sein (blauer Rahmen).
            </div>
        </body>
        </html>
        """


