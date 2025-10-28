#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zeichenwerkzeuge für QGraphicsView
----------------------------------
Implementiert Pfeil, Kreis, Rechteck, Freihand-Zeichnung mit Undo/Redo
"""

from PySide6.QtCore import Qt, QPointF, QRectF, Signal, QObject
from PySide6.QtGui import QPen, QColor, QPainter, QPainterPath, QPolygonF
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsLineItem, QGraphicsEllipseItem,
                                QGraphicsRectItem, QGraphicsPathItem, QGraphicsPolygonItem)
import math
from typing import List, Optional, Tuple
from utils_logging import get_logger


class DrawingMode:
    """Zeichnungsmodi"""
    NONE = None
    PAN = "pan"
    ARROW = "arrow"
    CIRCLE = "circle"
    RECTANGLE = "rectangle"
    FREEHAND = "freehand"


class DrawingItem:
    """Basis-Klasse für Zeichnungselemente mit Serialisierung"""
    def __init__(self, item_type: str, graphics_item: QGraphicsItem, pen: QPen):
        self.item_type = item_type
        self.graphics_item = graphics_item
        self.pen = pen
    
    def to_dict(self) -> dict:
        """Konvertiert zu Dictionary für EXIF-Speicherung"""
        return {
            'type': self.item_type,
            'color': self.pen.color().name(),
            'width': self.pen.width()
        }
    
    @staticmethod
    def from_dict(data: dict, scene) -> Optional['DrawingItem']:
        """Erstellt DrawingItem aus Dictionary (für EXIF-Laden)"""
        # Implementierung für verschiedene Typen
        pass


class ArrowItem(DrawingItem):
    """Pfeil mit Spitze"""
    def __init__(self, start: QPointF, end: QPointF, pen: QPen, scene):
        # Hauptlinie
        line = QGraphicsLineItem(start.x(), start.y(), end.x(), end.y())
        line.setPen(pen)
        scene.addItem(line)
        
        # Pfeilspitze berechnen
        angle = math.atan2(end.y() - start.y(), end.x() - start.x())
        arrow_size = 15.0
        
        # Zwei Linien für Pfeilspitze
        p1 = QPointF(
            end.x() - arrow_size * math.cos(angle - math.pi / 6),
            end.y() - arrow_size * math.sin(angle - math.pi / 6)
        )
        p2 = QPointF(
            end.x() - arrow_size * math.cos(angle + math.pi / 6),
            end.y() - arrow_size * math.sin(angle + math.pi / 6)
        )
        
        arrow1 = QGraphicsLineItem(end.x(), end.y(), p1.x(), p1.y())
        arrow1.setPen(pen)
        scene.addItem(arrow1)
        
        arrow2 = QGraphicsLineItem(end.x(), end.y(), p2.x(), p2.y())
        arrow2.setPen(pen)
        scene.addItem(arrow2)
        
        # Gruppe für alle Elemente
        self.items = [line, arrow1, arrow2]
        super().__init__('arrow', line, pen)
        self.start = start
        self.end = end
    
    def remove(self, scene):
        """Entfernt alle Pfeil-Elemente"""
        for item in self.items:
            scene.removeItem(item)
    
    def to_dict(self) -> dict:
        """Serialisierung"""
        data = super().to_dict()
        data.update({
            'start': (self.start.x(), self.start.y()),
            'end': (self.end.x(), self.end.y())
        })
        return data


class CircleItem(DrawingItem):
    """Kreis/Ellipse"""
    def __init__(self, rect: QRectF, pen: QPen, scene):
        ellipse = QGraphicsEllipseItem(rect)
        ellipse.setPen(pen)
        ellipse.setBrush(Qt.NoBrush)
        scene.addItem(ellipse)
        super().__init__('circle', ellipse, pen)
        self.rect = rect
    
    def remove(self, scene):
        scene.removeItem(self.graphics_item)
    
    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update({
            'rect': (self.rect.x(), self.rect.y(), self.rect.width(), self.rect.height())
        })
        return data


class RectangleItem(DrawingItem):
    """Rechteck"""
    def __init__(self, rect: QRectF, pen: QPen, scene):
        rectangle = QGraphicsRectItem(rect)
        rectangle.setPen(pen)
        rectangle.setBrush(Qt.NoBrush)
        scene.addItem(rectangle)
        super().__init__('rectangle', rectangle, pen)
        self.rect = rect
    
    def remove(self, scene):
        scene.removeItem(self.graphics_item)
    
    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update({
            'rect': (self.rect.x(), self.rect.y(), self.rect.width(), self.rect.height())
        })
        return data


class FreehandItem(DrawingItem):
    """Freihand-Zeichnung"""
    def __init__(self, points: List[QPointF], pen: QPen, scene):
        path = QPainterPath()
        if points:
            path.moveTo(points[0])
            for point in points[1:]:
                path.lineTo(point)
        
        path_item = QGraphicsPathItem(path)
        path_item.setPen(pen)
        scene.addItem(path_item)
        super().__init__('freehand', path_item, pen)
        self.points = points
    
    def remove(self, scene):
        scene.removeItem(self.graphics_item)
    
    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update({
            'points': [(p.x(), p.y()) for p in self.points]
        })
        return data


class DrawingManager(QObject):
    """Verwaltet Zeichnungen auf einem QGraphicsView"""
    
    # Signals
    drawingChanged = Signal()  # Wird bei Änderungen ausgelöst
    
    def __init__(self, scene):
        super().__init__()
        self.scene = scene
        self._log = get_logger('app', {"module": "qtui.drawing_tools"})
        
        # Zeichnungsmodus
        self.mode = DrawingMode.NONE
        self.pen = QPen(QColor("red"), 3)
        
        # Undo/Redo Stacks
        self.undo_stack: List[DrawingItem] = []
        self.redo_stack: List[DrawingItem] = []
        
        # Aktuelle Zeichnung
        self.current_item: Optional[DrawingItem] = None
        self.temp_item: Optional[QGraphicsItem] = None  # Für Vorschau während Zeichnung
        self.drawing_points: List[QPointF] = []
        self.is_drawing = False
        
        self._log.info("drawing_manager_initialized", extra={"event": "drawing_manager_initialized"})
    
    def set_mode(self, mode: str):
        """Setzt den Zeichnungsmodus"""
        self.mode = mode
        self._log.info("drawing_mode_changed", extra={"mode": mode})
    
    def set_color(self, color: QColor):
        """Setzt die Zeichenfarbe"""
        self.pen.setColor(color)
    
    def set_width(self, width: int):
        """Setzt die Linienbreite"""
        self.pen.setWidth(width)
    
    def start_drawing(self, pos: QPointF):
        """Startet eine neue Zeichnung"""
        if self.mode == DrawingMode.NONE or self.mode == DrawingMode.PAN:
            return
        
        self.is_drawing = True
        self.drawing_points = [pos]
        self._log.debug("drawing_started", extra={"mode": self.mode, "pos": (pos.x(), pos.y())})
    
    def update_drawing(self, pos: QPointF):
        """Aktualisiert die aktuelle Zeichnung (Vorschau)"""
        if not self.is_drawing or self.mode == DrawingMode.NONE:
            return
        
        # Entferne alte Vorschau
        if self.temp_item:
            self.scene.removeItem(self.temp_item)
            self.temp_item = None
        
        if self.mode == DrawingMode.FREEHAND:
            # Freihand: Füge Punkt hinzu und zeichne Linie
            self.drawing_points.append(pos)
            if len(self.drawing_points) >= 2:
                last_point = self.drawing_points[-2]
                line = QGraphicsLineItem(last_point.x(), last_point.y(), pos.x(), pos.y())
                line.setPen(self.pen)
                self.scene.addItem(line)
                # Speichere als Teil der Freihand-Zeichnung
                if not hasattr(self, '_freehand_items'):
                    self._freehand_items = []
                self._freehand_items.append(line)
        else:
            # Andere Modi: Zeige Vorschau
            start = self.drawing_points[0]
            
            if self.mode == DrawingMode.ARROW:
                # Pfeil-Vorschau (nur Hauptlinie)
                self.temp_item = QGraphicsLineItem(start.x(), start.y(), pos.x(), pos.y())
                self.temp_item.setPen(QPen(self.pen.color(), self.pen.width(), Qt.DashLine))
            elif self.mode == DrawingMode.CIRCLE:
                rect = QRectF(start, pos).normalized()
                self.temp_item = QGraphicsEllipseItem(rect)
                self.temp_item.setPen(QPen(self.pen.color(), self.pen.width(), Qt.DashLine))
                self.temp_item.setBrush(Qt.NoBrush)
            elif self.mode == DrawingMode.RECTANGLE:
                rect = QRectF(start, pos).normalized()
                self.temp_item = QGraphicsRectItem(rect)
                self.temp_item.setPen(QPen(self.pen.color(), self.pen.width(), Qt.DashLine))
                self.temp_item.setBrush(Qt.NoBrush)
            
            if self.temp_item:
                self.scene.addItem(self.temp_item)
    
    def finish_drawing(self, pos: QPointF):
        """Beendet die aktuelle Zeichnung"""
        if not self.is_drawing:
            return
        
        self.is_drawing = False
        
        # Entferne Vorschau
        if self.temp_item:
            self.scene.removeItem(self.temp_item)
            self.temp_item = None
        
        # Erstelle finale Zeichnung
        start = self.drawing_points[0] if self.drawing_points else pos
        
        try:
            if self.mode == DrawingMode.ARROW:
                item = ArrowItem(start, pos, self.pen, self.scene)
            elif self.mode == DrawingMode.CIRCLE:
                rect = QRectF(start, pos).normalized()
                item = CircleItem(rect, self.pen, self.scene)
            elif self.mode == DrawingMode.RECTANGLE:
                rect = QRectF(start, pos).normalized()
                item = RectangleItem(rect, self.pen, self.scene)
            elif self.mode == DrawingMode.FREEHAND:
                # Freihand: Sammle alle Punkte
                if hasattr(self, '_freehand_items'):
                    # Entferne temporäre Linien
                    for temp_line in self._freehand_items:
                        self.scene.removeItem(temp_line)
                    self._freehand_items.clear()
                item = FreehandItem(self.drawing_points, self.pen, self.scene)
            else:
                return
            
            # Füge zu Undo-Stack hinzu
            self.undo_stack.append(item)
            self.redo_stack.clear()  # Redo-Stack löschen
            
            self._log.info("drawing_completed", extra={"type": self.mode})
            self.drawingChanged.emit()
            
        except Exception as e:
            self._log.error("drawing_failed", extra={"error": str(e)})
        
        finally:
            self.drawing_points.clear()
    
    def undo(self):
        """Macht die letzte Zeichnung rückgängig"""
        if not self.undo_stack:
            return
        
        item = self.undo_stack.pop()
        item.remove(self.scene)
        self.redo_stack.append(item)
        
        self._log.info("drawing_undone", extra={"type": item.item_type})
        self.drawingChanged.emit()
    
    def redo(self):
        """Stellt die letzte rückgängig gemachte Zeichnung wieder her"""
        if not self.redo_stack:
            return
        
        item = self.redo_stack.pop()
        # Zeichnung wiederherstellen (müsste neu gezeichnet werden)
        # TODO: Implementiere Wiederherstellung
        self.undo_stack.append(item)
        
        self._log.info("drawing_redone", extra={"type": item.item_type})
        self.drawingChanged.emit()
    
    def clear_all(self):
        """Löscht alle Zeichnungen"""
        for item in self.undo_stack:
            item.remove(self.scene)
        self.undo_stack.clear()
        self.redo_stack.clear()
        
        self._log.info("drawings_cleared", extra={"event": "drawings_cleared"})
        self.drawingChanged.emit()
    
    def get_drawings_data(self) -> List[dict]:
        """Gibt alle Zeichnungen als Daten-Liste zurück (für EXIF)"""
        return [item.to_dict() for item in self.undo_stack]
    
    def load_drawings_data(self, data_list: List[dict]):
        """Lädt Zeichnungen aus Daten-Liste (von EXIF)"""
        self.clear_all()
        
        for data in data_list:
            try:
                item_type = data.get('type')
                color = QColor(data.get('color', 'red'))
                width = data.get('width', 3)
                pen = QPen(color, width)
                
                if item_type == 'arrow':
                    start_data = data.get('start', (0, 0))
                    end_data = data.get('end', (0, 0))
                    start = QPointF(start_data[0], start_data[1])
                    end = QPointF(end_data[0], end_data[1])
                    item = ArrowItem(start, end, pen, self.scene)
                    self.undo_stack.append(item)
                    
                elif item_type == 'circle':
                    rect_data = data.get('rect', (0, 0, 0, 0))
                    rect = QRectF(rect_data[0], rect_data[1], rect_data[2], rect_data[3])
                    item = CircleItem(rect, pen, self.scene)
                    self.undo_stack.append(item)
                    
                elif item_type == 'rectangle':
                    rect_data = data.get('rect', (0, 0, 0, 0))
                    rect = QRectF(rect_data[0], rect_data[1], rect_data[2], rect_data[3])
                    item = RectangleItem(rect, pen, self.scene)
                    self.undo_stack.append(item)
                    
                elif item_type == 'freehand':
                    points_data = data.get('points', [])
                    points = [QPointF(p[0], p[1]) for p in points_data]
                    if points:
                        item = FreehandItem(points, pen, self.scene)
                        self.undo_stack.append(item)
                        
            except Exception as e:
                self._log.error("drawing_load_failed", extra={"error": str(e), "data": data})
        
        self._log.info("drawings_loaded", extra={"count": len(data_list)})
        self.drawingChanged.emit()

