import sys
import math
import json
import random
import os
from collections import deque
from pathlib import Path

# --- UI LIBRARY IMPORTS ---
from PySide6.QtCore import Qt, QPointF, QRectF, QTimer, QThread, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPolygonF, QCursor, QAction
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout,
                               QVBoxLayout, QPushButton, QListWidget, QLabel,
                               QSpinBox, QListWidgetItem, QStatusBar,
                               QCheckBox, QGroupBox, QFileDialog, QSlider, 
                               QDoubleSpinBox, QComboBox, QDockWidget, QScrollArea, QFrame, QMessageBox, QTextEdit)

# --- CORE LOGIC IMPORTS ---
try:
    from validator import Validator
    from generator import HybridLevelGeneratorTestable
    from helper import Arrow, Args
    from image_tools import ImageTools
    # Import Module Phân Tích Mới
    from core.analysis_manager import AnalysisManager
except ImportError as e:
    print(f"CRITICAL ERROR: Missing modules. Check folder structure.\nDetails: {e}")
    sys.exit(1)


# --- CONFIGURATION ---
GRID_SIZE = 20
COLOR_GRID = QColor(223, 225, 230)
COLOR_CANVAS_BG = QColor(255, 255, 255)
COLOR_BG = QColor(244, 245, 247)
COLOR_SELECTED = QColor(0, 107, 255)
COLOR_SUCCESS = QColor(0, 102, 68)
COLOR_ERROR = QColor(222, 53, 11)
LAYER_COLORS = [
    QColor(0, 82, 204),
    QColor(222, 53, 11),
    QColor(0, 102, 68),
    QColor(107, 70, 193),
    QColor(255, 140, 0),
    QColor(38, 132, 132),
]

# --- STYLE PRESETS ---
STYLE_PRESETS = {
    "Aztec":      {"straight": 1.5, "left": 1.0, "right": 1.0, "max_turns": 5},
    "Snake":      {"straight": 0.5, "left": 2.0, "right": 2.0, "max_turns": 15},
    "Spaghetti":  {"straight": 1.0, "left": 1.0, "right": 1.0, "max_turns": 20},
    "Linear":     {"straight": 5.0, "left": 0.5, "right": 0.5, "max_turns": 2},
    "Right Bias": {"straight": 1.0, "left": 0.2, "right": 3.0, "max_turns": 8},
}

# --- DATA STRUCTURES FOR UI ---

class Layer:
    def __init__(self, layer_id, name, color):
        self.id = layer_id
        self.name = name
        self.color = color
        self.arrows = []
        self.editable_area = set()


class AnimatedArrow:
    def __init__(self, arrow, speed=0.25):
        self.path = deque(arrow.points)
        self.direction = arrow.direction
        self.color = arrow.color
        self.speed = speed
        self.timer = 0

    def update(self, grid_w, grid_h):
        self.timer += 1
        if self.timer >= self.speed:
            self.timer = 0
            head = self.path[0]
            next_head = (head[0] + self.direction[0],
                         head[1] + self.direction[1])
            self.path.appendleft(next_head)
            self.path.pop()
            if not any(0 <= p[0] < grid_w and 0 <= p[1] < grid_h
                       for p in self.path):
                return True
        return False

# --- WORKER THREAD FOR ANALYSIS (Tránh đơ UI) ---
class AnalysisWorker(QThread):
    finished = Signal(str, dict, str) # report_text, summary_data, render_path
    error = Signal(str)

    def __init__(self, manager, level_data, level_id, render_visuals):
        super().__init__()
        self.manager = manager
        self.level_data = level_data
        self.level_id = level_id
        self.render_visuals = render_visuals

    def run(self):
        try:
            report, summary, path = self.manager.run_analysis(
                self.level_data, self.level_id, self.render_visuals
            )
            self.finished.emit(report, summary, str(path))
        except Exception as e:
            self.error.emit(str(e))


# --- CUSTOM CANVAS WIDGET ---

class CanvasWidget(QWidget):

    def __init__(self, status_bar, parent=None):
        super().__init__(parent)
        self.setMinimumSize(800, 720)
        self.setMouseTracking(True)
        self.status_bar = status_bar
        self.level_grid_w = 20
        self.level_grid_h = 25
        self.layers = [Layer(0, "Layer 0", LAYER_COLORS[0])]
        self.active_layer = self.layers[0]
        self.arrow_id_counter = 0
        self.mode = "SELECT"
        self.paint_sub_mode = "BRUSH"
        self.show_areas = True
        self.is_drawing = False
        self.start_pos_grid = (0, 0)
        self.current_pos_grid = (0, 0)
        self.temp_arrow_path = []
        
        self.playtest_arrows = []
        self.animating_arrows = []
        self.movable_arrows_cache = [] 
        self.hovered_arrow = None      
        
        self.validator = Validator()
        
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.update_animations)
        self.animation_timer.start(1000 // 60)
        self.base_grid_size = GRID_SIZE
        self.zoom_level = 1.0
        self.view_padding = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0
        self._is_panning = False
        self._last_pan_pos = QPointF(0, 0)

    @property
    def effective_grid_size(self): return self.base_grid_size * self.zoom_level

    @property
    def pixel_offset_x(self): return self.view_padding * self.effective_grid_size + self.pan_x

    @property
    def pixel_offset_y(self): return self.view_padding * self.effective_grid_size + self.pan_y

    def grid_to_pixel(self, grid_pos):
        x = grid_pos[0] * self.effective_grid_size + self.pixel_offset_x
        y = grid_pos[1] * self.effective_grid_size + self.pixel_offset_y
        return QPointF(x, y)

    def pixel_to_grid(self, pixel_pos, do_round=True):
        egs = self.effective_grid_size
        if egs == 0: return (0, 0)
        x = (pixel_pos.x() - self.pixel_offset_x) / egs
        y = (pixel_pos.y() - self.pixel_offset_y) / egs
        if do_round: return (round(x), round(y))
        return (x, y)

    @property
    def grid_w(self): return self.level_grid_w

    @property
    def grid_h(self): return self.level_grid_h

    def get_grid_pos(self, pos): return self.pixel_to_grid(pos, do_round=True)

    def set_mode(self, mode):
        self.mode = mode
        if mode != "PLAYTEST":
            self.animating_arrows.clear()
            self.hovered_arrow = None
            self.setCursor(Qt.ArrowCursor)
        self.status_bar.showMessage(f"Mode: {mode}")
        self.update()

    def set_paint_sub_mode(self, sub_mode):
        self.paint_sub_mode = sub_mode
        self.status_bar.showMessage(f"Paint Tool: {sub_mode}")
        self.update()

    def get_all_arrows(self):
        return [arrow for layer in self.layers for arrow in layer.arrows]

    def get_all_occupied_points(self):
        return {p for arrow in self.get_all_arrows() for p in arrow.points}

    def clear_all(self):
        self.layers = [Layer(0, "Layer 0", LAYER_COLORS[0])]
        self.active_layer = self.layers[0]
        self.arrow_id_counter = 0
        self.level_grid_w = 20
        self.level_grid_h = 25
        self.validator.clear_cache()
        self.status_bar.showMessage("Board cleared!", 2000)
        self.update()

    def refresh_playtest_logic(self):
        if self.mode == "PLAYTEST":
            self.movable_arrows_cache = self.validator.find_movable_arrows(
                self.playtest_arrows, self.grid_w, self.grid_h)
            self.hovered_arrow = None

    def update_animations(self):
        if self.mode == "PLAYTEST" and self.animating_arrows:
            self.animating_arrows[:] = [
                anim for anim in self.animating_arrows
                if not anim.update(self.grid_w, self.grid_h)
            ]
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), COLOR_CANVAS_BG)
        pen = QPen(COLOR_GRID, 1, Qt.SolidLine)
        painter.setPen(pen)
        egs = self.effective_grid_size
        
        if egs > 0.5:
            origin_px = self.grid_to_pixel((0, 0))
            x_start = origin_px.x()
            y_start = origin_px.y()
            while x_start > 0: x_start -= egs
            while y_start > 0: y_start -= egs
            x = x_start
            while x < self.width():
                painter.drawLine(int(x), 0, int(x), self.height())
                x += egs
            y = y_start
            while y < self.height():
                painter.drawLine(0, int(y), self.width(), int(y))
                y += egs
        
        if self.mode != "PLAYTEST":
            if self.show_areas:
                half_egs = self.effective_grid_size / 2.0
                for layer in self.layers:
                    color = QColor(layer.color)
                    color.setAlpha(50)
                    painter.setBrush(QBrush(color))
                    painter.setPen(Qt.NoPen)
                    for p in layer.editable_area:
                        p_pos = self.grid_to_pixel(p)
                        painter.drawRect(
                            QRectF(p_pos.x() - half_egs,
                                   p_pos.y() - half_egs, egs, egs))
            for layer in self.layers:
                for arrow in layer.arrows:
                    self.draw_arrow(painter, arrow.points, arrow.direction,
                                    arrow.color)
            
            color = self.active_layer.color if self.active_layer else COLOR_SELECTED
            if self.is_drawing:
                if self.mode == "MANUAL_ARROW" and self.temp_arrow_path:
                    if len(self.temp_arrow_path) > 1:
                        p1, p2 = self.temp_arrow_path[-2], self.temp_arrow_path[-1]
                        temp_dir = (p2[0] - p1[0], p2[1] - p1[1])
                        thickness = max(1.0, 5.0 * self.zoom_level)
                        pen = QPen(QColor(color), thickness, Qt.SolidLine,
                                   Qt.RoundCap, Qt.RoundJoin)
                        painter.setPen(pen)
                        path = QPolygonF()
                        for p in self.temp_arrow_path:
                            path.append(self.grid_to_pixel(p))
                        painter.drawPolyline(path)
                        head_center = self.grid_to_pixel(self.temp_arrow_path[-1])
                        dx, dy = temp_dir[0], temp_dir[1]
                        s = max(3.0, 8.0 * self.zoom_level)
                        hp1 = head_center + QPointF(-dy * s - dx * s, dx * s - dy * s)
                        hp2 = head_center + QPointF(dy * s - dx * s, -dx * s - dy * s)
                        hp3 = head_center + QPointF(dx * s, dy * s)
                        painter.setBrush(QBrush(QColor(color)))
                        painter.setPen(Qt.NoPen)
                        painter.drawPolygon(QPolygonF([hp1, hp2, hp3]))
                    elif self.temp_arrow_path:
                        p_pos = self.grid_to_pixel(self.temp_arrow_path[0])
                        radius = max(2.0, 3.0 * self.zoom_level)
                        painter.setBrush(QBrush(color))
                        painter.setPen(Qt.NoPen)
                        painter.drawEllipse(p_pos.x() - radius,
                                            p_pos.y() - radius, radius * 2,
                                            radius * 2)
                elif self.mode == "PAINT_AREA":
                    pen = QPen(color, 3, Qt.DotLine)
                    painter.setPen(pen)
                    painter.setBrush(Qt.NoBrush)
                    start_p = self.grid_to_pixel(self.start_pos_grid)
                    current_p = self.grid_to_pixel(self.current_pos_grid)
                    if self.paint_sub_mode == "RECT":
                        rect = QRectF(start_p, current_p)
                        painter.drawRect(rect.normalized())
                    elif self.paint_sub_mode == "CIRCLE":
                        radius_pixels = math.hypot(current_p.x() - start_p.x(),
                                                   current_p.y() - start_p.y())
                        painter.drawEllipse(start_p, radius_pixels,
                                            radius_pixels)
        else:
            for arrow in self.playtest_arrows:
                is_highlighted = (self.hovered_arrow and arrow.id == self.hovered_arrow.id)
                self.draw_arrow(painter, arrow.points, arrow.direction,
                                arrow.color, is_highlighted)
            
            for anim in self.animating_arrows:
                self.draw_arrow(painter, list(anim.path), anim.direction,
                                anim.color)
        painter.end()

    def draw_arrow(self, painter, points, direction, color, is_highlighted=False):
        if not points: return
        thickness = max(1.0, 5.0 * self.zoom_level)
        
        draw_color = QColor(color)
        if is_highlighted:
            draw_color = draw_color.lighter(150)
            thickness *= 1.2
            
        pen = QPen(draw_color, thickness, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        path = QPolygonF()
        for p in points:
            path.append(self.grid_to_pixel(p))
        painter.drawPolyline(path)
        if len(points) > 1:
            head_center = self.grid_to_pixel(points[0])
            dx, dy = direction[0], direction[1]
            s = max(3.0, 8.0 * self.zoom_level)
            if is_highlighted: s *= 1.2
            
            p1 = head_center + QPointF(-dy * s - dx * s, dx * s - dy * s)
            p2 = head_center + QPointF(dy * s - dx * s, -dx * s - dy * s)
            p3 = head_center + QPointF(dx * s, dy * s)
            painter.setBrush(QBrush(draw_color))
            painter.setPen(Qt.NoPen)
            painter.drawPolygon(QPolygonF([p1, p2, p3]))

    def mousePressEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._is_panning = True
            self._last_pan_pos = event.position()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        self.current_pos_grid = self.get_grid_pos(event.position())
        
        if self.mode == "PLAYTEST":
            if event.button() == Qt.LeftButton:
                if self.hovered_arrow:
                    arrow = self.hovered_arrow
                    self.animating_arrows.append(AnimatedArrow(arrow))
                    self.playtest_arrows = [
                        a for a in self.playtest_arrows if a.id != arrow.id
                    ]
                    self.refresh_playtest_logic()
                    self.update()
            return
            
        if event.button() == Qt.LeftButton:
            self.is_drawing = True
            self.start_pos_grid = self.current_pos_grid
            if self.mode == "MANUAL_ARROW" and self.active_layer:
                if self.current_pos_grid in self.active_layer.editable_area:
                    self.temp_arrow_path = [self.current_pos_grid]
                else:
                    self.is_drawing = False
                    self.status_bar.showMessage("Cannot draw outside painted area!", 2000)
            elif self.mode == "PAINT_AREA" and self.active_layer:
                pass
        self.update()

        if event.button() == Qt.RightButton:
            for layer in self.layers:
                for arrow in layer.arrows:
                    if self.current_pos_grid in arrow.points:
                        layer.arrows.remove(arrow)
                        self.validator.clear_cache()
                        self.status_bar.showMessage(f"Arrow removed from {layer.name}!", 2000)
                        self.update()
                        return
            self.status_bar.showMessage("No arrow at this position.", 2000)
            return

    def mouseMoveEvent(self, event):
        if self._is_panning:
            delta = event.position() - self._last_pan_pos
            self.pan_x += delta.x()
            self.pan_y += delta.y()
            self._last_pan_pos = event.position()
            self.update()
            event.accept()
            return
        self.current_pos_grid = self.get_grid_pos(event.position())
        
        if self.mode == "PLAYTEST":
            prev_hover = self.hovered_arrow
            self.hovered_arrow = None
            for arrow in self.movable_arrows_cache:
                if self.current_pos_grid in arrow.points:
                    self.hovered_arrow = arrow
                    break
            if self.hovered_arrow: self.setCursor(Qt.PointingHandCursor)
            else: self.setCursor(Qt.ArrowCursor)
            if prev_hover != self.hovered_arrow: self.update()
            return
        
        mouse_buttons = event.buttons()
        if self.mode == "PAINT_AREA" and self.active_layer:
            if self.paint_sub_mode == "BRUSH":
                if mouse_buttons & Qt.LeftButton:
                    self.active_layer.editable_area.add(self.current_pos_grid)
                elif mouse_buttons & Qt.RightButton:
                    self.active_layer.editable_area.discard(self.current_pos_grid)
        elif self.mode == "MANUAL_ARROW" and self.is_drawing and self.temp_arrow_path:
            if self.current_pos_grid != self.temp_arrow_path[-1] and self.current_pos_grid in self.active_layer.editable_area:
                if self.current_pos_grid in self.temp_arrow_path:
                    idx = self.temp_arrow_path.index(self.current_pos_grid)
                    self.temp_arrow_path = self.temp_arrow_path[:idx + 1]
                else:
                    last_pos = self.temp_arrow_path[-1]
                    dx = abs(self.current_pos_grid[0] - last_pos[0])
                    dy = abs(self.current_pos_grid[1] - last_pos[1])
                    if dx + dy == 1:
                        self.temp_arrow_path.append(self.current_pos_grid)
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MiddleButton:
            self._is_panning = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        if self.mode == "PLAYTEST" or not self.is_drawing: return
        self.is_drawing = False
        end_pos_grid = self.get_grid_pos(event.position())
        
        if self.mode == "MANUAL_ARROW" and self.active_layer and len(self.temp_arrow_path) > 1:
            p1, p2 = self.temp_arrow_path[-2], self.temp_arrow_path[-1]
            direction = (p2[0] - p1[0], p2[1] - p1[1])
            path_to_save = list(reversed(self.temp_arrow_path))
            
            if not self.get_all_occupied_points().isdisjoint(set(path_to_save)):
                self.status_bar.showMessage("Invalid: Arrows cannot overlap!", 3000)
            else:
                hypo_arrow = Arrow(path_to_save, direction,
                                   self.active_layer.id, -1,
                                   self.active_layer.color)
                self.validator.clear_cache()
                all_existing_arrows = self.get_all_arrows()
                
                if self.validator.is_board_state_solvable(
                        all_existing_arrows + [hypo_arrow], self.grid_w, self.grid_h):
                    hypo_arrow.id = self.arrow_id_counter
                    self.active_layer.arrows.append(hypo_arrow)
                    self.arrow_id_counter += 1
                    self.status_bar.showMessage("Arrow added!", 2000)
                else:
                    self.status_bar.showMessage("Invalid: Creates an unsolvable state!", 3000)
            self.temp_arrow_path = []
            
        elif self.mode == "PAINT_AREA" and self.active_layer:
            start_pos_grid = self.start_pos_grid
            if self.paint_sub_mode == "RECT":
                sx, ex = sorted((start_pos_grid[0], end_pos_grid[0]))
                sy, ey = sorted((start_pos_grid[1], end_pos_grid[1]))
                for x in range(int(sx), int(ex) + 1):
                    for y in range(int(sy), int(ey) + 1):
                        self.active_layer.editable_area.add((x, y))
            elif self.paint_sub_mode == "CIRCLE":
                radius = math.hypot(end_pos_grid[0] - start_pos_grid[0],
                                    end_pos_grid[1] - start_pos_grid[1])
                cx, cy = start_pos_grid[0], start_pos_grid[1]
                min_x = int(cx - radius) - 1
                max_x = int(cx + radius) + 2
                min_y = int(cy - radius) - 1
                max_y = int(cy + radius) + 2
                for x in range(min_x, max_x):
                    for y in range(min_y, max_y):
                        if math.hypot(x - cx, y - cy) <= radius:
                            self.active_layer.editable_area.add((x, y))
        self.update()

    def wheelEvent(self, event):
        if not event.modifiers() & Qt.ControlModifier:
            super().wheelEvent(event)
            return
        mouse_pos = event.position()
        grid_pos_before_zoom = self.pixel_to_grid(mouse_pos, do_round=False)
        old_zoom = self.zoom_level
        delta = event.angleDelta().y()
        if delta > 0: self.zoom_level = min(self.zoom_level * 1.15, 8.0)
        elif delta < 0: self.zoom_level = max(self.zoom_level / 1.15, 0.1)
        if old_zoom == self.zoom_level: return
        new_egs = self.effective_grid_size
        base_origin_x = self.view_padding * new_egs
        base_origin_y = self.view_padding * new_egs
        new_px_x_no_pan = grid_pos_before_zoom[0] * new_egs + base_origin_x
        new_px_y_no_pan = grid_pos_before_zoom[1] * new_egs + base_origin_y
        self.pan_x = mouse_pos.x() - new_px_x_no_pan
        self.pan_y = mouse_pos.y() - new_px_y_no_pan
        self.update()
        event.accept()


# --- MAIN WINDOW ---

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Level Editor - Pro Layout v3.0 (With Analysis)")
        self.setGeometry(100, 100, 1280, 720)
        self.setStatusBar(QStatusBar())
        
        # Tools
        self.image_tools = ImageTools()
        self.analysis_manager = AnalysisManager("analysis_output") # Thư mục output

        # --- CENTER CANVAS ---
        self.canvas = CanvasWidget(self.statusBar())
        self.setCentralWidget(self.canvas)
        
        self.exit_playtest_button = QPushButton("Exit Playtest", self.canvas)
        self.exit_playtest_button.hide()
        
        # --- DOCK 1: CONTROL PANEL (LEFT) ---
        self.dock_controls = QDockWidget("Tools & Settings", self)
        self.dock_controls.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        
        control_container = QWidget()
        toolbar_layout = QVBoxLayout(control_container)
        toolbar_layout.setAlignment(Qt.AlignTop)
        
        # 1. FILE
        toolbar_layout.addWidget(QLabel("<h3>FILE</h3>"))
        self.level_id_spinbox = QSpinBox()
        self.level_id_spinbox.setRange(1, 999)
        file_id_layout = QHBoxLayout()
        file_id_layout.addWidget(QLabel("Level ID:"))
        file_id_layout.addWidget(self.level_id_spinbox)
        toolbar_layout.addLayout(file_id_layout)
        
        file_btn_layout = QHBoxLayout()
        self.btn_save = QPushButton("Save (S)")
        self.btn_load = QPushButton("Load (L)")
        file_btn_layout.addWidget(self.btn_save)
        file_btn_layout.addWidget(self.btn_load)
        toolbar_layout.addLayout(file_btn_layout)
        
        self.btn_clear = QPushButton("Clear All (C)")
        toolbar_layout.addWidget(self.btn_clear)
        toolbar_layout.addSpacing(10)
        
        self.btn_analyze = QPushButton("Quick Check (D)")
        toolbar_layout.addWidget(self.btn_analyze)
        self.btn_playtest = QPushButton("Playtest (P)")
        toolbar_layout.addWidget(self.btn_playtest)
        toolbar_layout.addSpacing(15)

        # 2. IMAGE IMPORT
        img_group = QGroupBox("Image Import")
        img_layout = QVBoxLayout()
        size_layout = QHBoxLayout()
        size_layout.addWidget(QLabel("Size:"))
        self.img_w_spinbox = QSpinBox()
        self.img_w_spinbox.setRange(5, 100)
        self.img_w_spinbox.setValue(20)
        size_layout.addWidget(self.img_w_spinbox)
        size_layout.addWidget(QLabel("x"))
        self.img_h_spinbox = QSpinBox()
        self.img_h_spinbox.setRange(5, 100)
        self.img_h_spinbox.setValue(20)
        size_layout.addWidget(self.img_h_spinbox)
        img_layout.addLayout(size_layout)
        thresh_layout = QHBoxLayout()
        thresh_layout.addWidget(QLabel("Alpha:"))
        self.img_thresh_spinbox = QSpinBox()
        self.img_thresh_spinbox.setRange(0, 255)
        self.img_thresh_spinbox.setValue(128)
        thresh_layout.addWidget(self.img_thresh_spinbox)
        img_layout.addLayout(thresh_layout)
        self.btn_import_img = QPushButton("Select Image")
        img_layout.addWidget(self.btn_import_img)
        img_group.setLayout(img_layout)
        toolbar_layout.addWidget(img_group)
        toolbar_layout.addSpacing(15)

        # 3. TOOLS
        toolbar_layout.addWidget(QLabel("<h3>TOOLS</h3>"))
        self.btn_select = QPushButton("Select (Q)")
        self.btn_paint = QPushButton("Paint Area (W)")
        self.btn_draw = QPushButton("Draw Arrow (E)")
        toolbar_layout.addWidget(self.btn_select)
        toolbar_layout.addWidget(self.btn_paint)
        
        self.paint_tools_widget = QWidget()
        paint_tools_layout = QHBoxLayout(self.paint_tools_widget)
        paint_tools_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_brush = QPushButton("Brush")
        self.btn_rect = QPushButton("Rect")
        self.btn_circle = QPushButton("Circ")
        paint_tools_layout.addWidget(self.btn_brush)
        paint_tools_layout.addWidget(self.btn_rect)
        paint_tools_layout.addWidget(self.btn_circle)
        toolbar_layout.addWidget(self.paint_tools_widget)
        self.paint_tools_widget.hide()
        toolbar_layout.addWidget(self.btn_draw)
        toolbar_layout.addSpacing(20)

        # 4. AUTO-GENERATION
        gen_group = QGroupBox("Auto-Generation")
        gen_layout_main = QVBoxLayout()
        self.chk_smart_fill = QCheckBox("Smart Fill (Loop)")
        self.chk_smart_fill.setChecked(True)
        gen_layout_main.addWidget(self.chk_smart_fill)
        self.chk_advanced_mode = QCheckBox("Advanced Mode")
        self.chk_advanced_mode.toggled.connect(self.toggle_advanced_ui)
        gen_layout_main.addWidget(self.chk_advanced_mode)

        form_layout = QVBoxLayout()
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Len:"))
        self.gen_avg_len_spinbox = QSpinBox()
        self.gen_avg_len_spinbox.setRange(3, 100)
        self.gen_avg_len_spinbox.setValue(15)
        row1.addWidget(self.gen_avg_len_spinbox)
        form_layout.addLayout(row1)
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("W-Min:"))
        self.gen_min_width_spinbox = QSpinBox()
        self.gen_min_width_spinbox.setRange(1, 10)
        self.gen_min_width_spinbox.setValue(3)
        row2.addWidget(self.gen_min_width_spinbox)
        form_layout.addLayout(row2)
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("W-Max:"))
        self.gen_max_width_spinbox = QSpinBox()
        self.gen_max_width_spinbox.setRange(1, 20)
        self.gen_max_width_spinbox.setValue(8)
        row3.addWidget(self.gen_max_width_spinbox)
        form_layout.addLayout(row3)
        row4 = QHBoxLayout()
        row4.addWidget(QLabel("Count:"))
        self.gen_arrow_count_spinbox = QSpinBox()
        self.gen_arrow_count_spinbox.setRange(1, 999)
        self.gen_arrow_count_spinbox.setValue(50)
        row4.addWidget(self.gen_arrow_count_spinbox)
        form_layout.addLayout(row4)

        self.adv_params_widget = QWidget()
        adv_layout = QVBoxLayout(self.adv_params_widget)
        adv_layout.setContentsMargins(0, 0, 0, 0)
        row_preset = QHBoxLayout()
        row_preset.addWidget(QLabel("Preset:"))
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(list(STYLE_PRESETS.keys()))
        self.preset_combo.currentTextChanged.connect(self.apply_style_preset)
        row_preset.addWidget(self.preset_combo)
        adv_layout.addLayout(row_preset)
        row_w1 = QHBoxLayout()
        row_w1.addWidget(QLabel("Str:"))
        self.spin_straight = QDoubleSpinBox()
        self.spin_straight.setRange(0.1, 10.0)
        self.spin_straight.setSingleStep(0.1)
        self.spin_straight.setValue(1.5)
        row_w1.addWidget(self.spin_straight)
        adv_layout.addLayout(row_w1)
        row_w2 = QHBoxLayout()
        row_w2.addWidget(QLabel("L:"))
        self.spin_left = QDoubleSpinBox()
        self.spin_left.setRange(0.1, 10.0)
        self.spin_left.setValue(1.0)
        row_w2.addWidget(self.spin_left)
        row_w2.addWidget(QLabel("R:"))
        self.spin_right = QDoubleSpinBox()
        self.spin_right.setRange(0.1, 10.0)
        self.spin_right.setValue(1.0)
        row_w2.addWidget(self.spin_right)
        adv_layout.addLayout(row_w2)
        row_t = QHBoxLayout()
        row_t.addWidget(QLabel("Max Turns:"))
        self.spin_max_turns = QSpinBox()
        self.spin_max_turns.setRange(0, 50)
        self.spin_max_turns.setValue(5)
        row_t.addWidget(self.spin_max_turns)
        adv_layout.addLayout(row_t)
        
        self.adv_params_widget.setVisible(False)
        gen_layout_main.addWidget(self.adv_params_widget)
        gen_layout_main.addLayout(form_layout)

        self.btn_suggest_count = QPushButton("Suggest Count")
        gen_layout_main.addWidget(self.btn_suggest_count)
        self.btn_generate_level = QPushButton("GENERATE (G)")
        self.btn_generate_level.setStyleSheet("font-weight: bold; color: blue;")
        self.btn_generate_level.setShortcut(Qt.Key_G)
        gen_layout_main.addWidget(self.btn_generate_level)
        gen_group.setLayout(gen_layout_main)
        toolbar_layout.addWidget(gen_group)
        
        scroll_control = QScrollArea()
        scroll_control.setWidget(control_container)
        scroll_control.setWidgetResizable(True)
        self.dock_controls.setWidget(scroll_control)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.dock_controls)

        # --- DOCK 2: LAYERS (RIGHT) ---
        self.dock_layers = QDockWidget("Layers", self)
        self.dock_layers.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        layers_panel_widget = QWidget()
        layers_panel_widget.setFixedWidth(200)
        layers_panel_layout = QVBoxLayout(layers_panel_widget)
        layers_panel_layout.setAlignment(Qt.AlignTop)
        self.layer_list_widget = QListWidget()
        self.update_layer_list()
        layers_panel_layout.addWidget(self.layer_list_widget)
        self.add_layer_button = QPushButton("Add New Layer")
        layers_panel_layout.addWidget(self.add_layer_button)
        self.dock_layers.setWidget(layers_panel_widget)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_layers)

        # --- DOCK 3: ANALYSIS (NEW - BOTTOM or TAB) ---
        self.dock_analysis = QDockWidget("Analysis Pipeline", self)
        self.dock_analysis.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea | Qt.BottomDockWidgetArea)
        analysis_widget = QWidget()
        analysis_layout = QVBoxLayout(analysis_widget)
        
        self.chk_render_visuals = QCheckBox("Render Visuals (Slower)")
        self.chk_render_visuals.setToolTip("Create images for each state")
        analysis_layout.addWidget(self.chk_render_visuals)
        
        self.btn_run_analysis = QPushButton("Run Full Analysis")
        self.btn_run_analysis.setStyleSheet("font-weight: bold; color: darkgreen;")
        analysis_layout.addWidget(self.btn_run_analysis)
        
        self.txt_analysis_report = QTextEdit()
        self.txt_analysis_report.setReadOnly(True)
        self.txt_analysis_report.setPlaceholderText("Analysis results will appear here...")
        analysis_layout.addWidget(self.txt_analysis_report)
        
        self.dock_analysis.setWidget(analysis_widget)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_analysis)
        # Tabify with layers if needed
        self.tabifyDockWidget(self.dock_layers, self.dock_analysis)


        # --- CONNECTIONS ---
        self.btn_select.clicked.connect(lambda: self.set_active_mode("SELECT"))
        self.btn_paint.clicked.connect(lambda: self.set_active_mode("PAINT_AREA"))
        self.btn_draw.clicked.connect(lambda: self.set_active_mode("MANUAL_ARROW"))
        self.btn_brush.clicked.connect(lambda: (self.set_active_mode("PAINT_AREA"), self.canvas.set_paint_sub_mode("BRUSH")))
        self.btn_rect.clicked.connect(lambda: (self.set_active_mode("PAINT_AREA"), self.canvas.set_paint_sub_mode("RECT")))
        self.btn_circle.clicked.connect(lambda: (self.set_active_mode("PAINT_AREA"), self.canvas.set_paint_sub_mode("CIRCLE")))
        self.add_layer_button.clicked.connect(self.add_new_layer)
        self.layer_list_widget.currentRowChanged.connect(self.change_active_layer)
        self.btn_clear.clicked.connect(self.canvas.clear_all)
        self.btn_save.clicked.connect(self.save_level)
        self.btn_load.clicked.connect(self.load_level)
        self.btn_analyze.clicked.connect(self.analyze_level)
        self.btn_playtest.clicked.connect(self.start_playtest)
        self.exit_playtest_button.clicked.connect(self.exit_playtest)
        self.btn_suggest_count.clicked.connect(self.suggest_arrow_count)
        self.btn_generate_level.clicked.connect(self.generate_level_smart)
        self.btn_import_img.clicked.connect(self.process_image_import)
        
        # New Connection for Analysis
        self.btn_run_analysis.clicked.connect(self.start_full_analysis)

        self.canvas.resizeEvent = self.on_canvas_resize
        self.set_active_mode("SELECT")
        self.update_layer_list()
        self.layer_list_widget.setCurrentRow(0)

    def on_canvas_resize(self, event):
        self.exit_playtest_button.setGeometry(
            self.canvas.width() // 2 - 100,
            self.canvas.height() - 60, 200, 40)

    def set_active_mode(self, mode):
        is_playtest = (mode == "PLAYTEST")
        self.canvas.set_mode(mode)
        self.paint_tools_widget.setVisible(mode == "PAINT_AREA")
        if mode == "PAINT_AREA":
            self.canvas.set_paint_sub_mode("BRUSH")
        
        if is_playtest:
            self.dock_controls.hide()
            self.dock_layers.hide()
            self.dock_analysis.hide()
        else:
            self.dock_controls.show()
            self.dock_layers.show()
            self.dock_analysis.show()
            
        self.exit_playtest_button.setVisible(is_playtest)

    def add_new_layer(self):
        new_id = len(self.canvas.layers)
        color = LAYER_COLORS[new_id % len(LAYER_COLORS)]
        new_layer = Layer(new_id, f"Layer {new_id}", color)
        self.canvas.layers.append(new_layer)
        self.update_layer_list()
        self.layer_list_widget.setCurrentRow(new_id)

    def update_layer_list(self):
        self.layer_list_widget.clear()
        for layer in self.canvas.layers:
            self.layer_list_widget.addItem(QListWidgetItem(layer.name))

    def change_active_layer(self, index):
        if 0 <= index < len(self.canvas.layers):
            self.canvas.active_layer = self.canvas.layers[index]
            self.canvas.update()

    # --- HELPER: GET CURRENT LEVEL DATA ---
    def get_current_level_data(self):
        all_arrows = self.canvas.get_all_arrows()
        all_painted_points = set()
        for layer in self.canvas.layers:
            all_painted_points.update(layer.editable_area)
        
        all_arrow_points = {p for arr in all_arrows for p in arr.points}
        all_relevant_points = all_painted_points.union(all_arrow_points)
        
        if not all_relevant_points:
            return None

        min_x = min(p[0] for p in all_relevant_points)
        min_y = min(p[1] for p in all_relevant_points)
        max_x = max(p[0] for p in all_relevant_points)
        max_y = max(p[1] for p in all_relevant_points)
        
        offset_x = -min_x
        offset_y = -min_y
        new_x_size = max_x - min_x + 1
        new_y_size = max_y - min_y + 1
        
        output_data = {"XSize": new_x_size, "YSize": new_y_size, "Arrows": []}
        
        for arrow in all_arrows:
            if not arrow.points: continue
            new_points = [(p[0] + offset_x, p[1] + offset_y) for p in arrow.points]
            indices = [y * new_x_size + x for x, y in new_points]
            tail_x = new_points[0][0]
            tail_y = new_points[0][1]
            bend_count = 0
            if len(arrow.points) >= 3:
                for k in range(len(arrow.points) - 2):
                    p1, p2, p3 = arrow.points[k], arrow.points[k+1], arrow.points[k+2]
                    dir1 = (p2[0] - p1[0], p2[1] - p1[1])
                    dir2 = (p3[0] - p2[0], p3[1] - p2[1])
                    if dir1 != dir2: bend_count += 1
            arrow_dict = {
                "Dx": arrow.direction[0], "Dy": arrow.direction[1],
                "X": tail_x, "Y": tail_y,
                "Indices": indices, "BendCount": bend_count
            }
            output_data["Arrows"].append(arrow_dict)
        return output_data

    # --- SAVE / LOAD LOGIC ---
    def save_level(self):
        level_id = self.level_id_spinbox.value()
        if not os.path.exists("levels"): os.makedirs("levels")
        filename = Path(f"levels/{int(level_id):04d}.json")
        output_data = self.get_current_level_data()
        if not output_data:
            self.statusBar().showMessage("Canvas empty. Saved 1x1.", 3000)
            output_data = {"XSize": 1, "YSize": 1, "Arrows": []}
        
        try:
            with open(filename, 'w') as f:
                json.dump(output_data, f, separators=(',', ':'))
            self.statusBar().showMessage(f"Saved {filename}!", 3000)
        except Exception as e:
            self.statusBar().showMessage(f"Error saving: {e}", 5000)

    def load_level(self):
        level_id = self.level_id_spinbox.value()
        filename = Path(f"levels/{int(level_id):04d}.json")
        try:
            with open(filename, 'r') as f: data = json.load(f)
            x_size = data.get("XSize")
            y_size = data.get("YSize")
            if x_size is None: return
            
            self.canvas.level_grid_w = x_size
            self.canvas.level_grid_h = y_size
            new_layers = []
            layer_color = LAYER_COLORS[0]
            layer = Layer(0, "Imported", layer_color)
            arrow_id_counter = 0
            for i, arrow_data in enumerate(data.get("Arrows", [])):
                dx, dy = arrow_data.get("Dx", 0), arrow_data.get("Dy", 0)
                indices = arrow_data.get("Indices", [])
                points = []
                for index in indices:
                    x = index % x_size
                    y = index // x_size
                    points.append((x, y))
                if not points: continue
                arrow = Arrow(points, (dx, dy), layer.id, i, layer_color)
                layer.arrows.append(arrow)
                layer.editable_area.update(points)
                arrow_id_counter = i + 1
            new_layers.append(layer)
            self.canvas.layers = new_layers
            self.canvas.active_layer = new_layers[0]
            self.canvas.arrow_id_counter = arrow_id_counter
            self.canvas.validator.clear_cache()
            self.update_layer_list()
            self.canvas.update()
            self.statusBar().showMessage(f"Loaded {filename}!", 3000)
        except Exception as e:
            self.statusBar().showMessage(f"Error loading: {e}", 5000)

    def analyze_level(self):
        self.statusBar().showMessage("Analyzing...")
        QApplication.processEvents()
        self.canvas.validator.clear_cache()
        is_solvable = self.canvas.validator.is_board_state_solvable(
            self.canvas.get_all_arrows(), self.canvas.grid_w, self.canvas.grid_h)
        msg = "SOLVABLE!" if is_solvable else "UNSOLVABLE!"
        self.statusBar().showMessage(f"Analysis: {msg}", 5000)

    def start_playtest(self):
        all_arrows = self.canvas.get_all_arrows()
        if not all_arrows: return
        all_pts = {p for arr in all_arrows for p in arr.points}
        min_x = min(p[0] for p in all_pts)
        min_y = min(p[1] for p in all_pts)
        max_x = max(p[0] for p in all_pts)
        max_y = max(p[1] for p in all_pts)
        offset_x = -min_x
        offset_y = -min_y
        self.canvas.level_grid_w = max_x - min_x + 1
        self.canvas.level_grid_h = max_y - min_y + 1
        playtest_arrows = []
        for arrow in all_arrows:
            new_points = [(p[0] + offset_x, p[1] + offset_y) for p in arrow.points]
            shifted = Arrow(new_points, arrow.direction, arrow.layer_id, arrow.id, arrow.color)
            playtest_arrows.append(shifted)
        self.set_active_mode("PLAYTEST")
        self.canvas.playtest_arrows = playtest_arrows
        self.canvas.animating_arrows = []
        self.canvas.refresh_playtest_logic()

    def exit_playtest(self):
        self.set_active_mode("SELECT")

    def suggest_arrow_count(self, total_cells=None, avg_len=None):
        active_layer = self.canvas.active_layer
        if total_cells is None:
            if not active_layer: return
            total_cells = len(active_layer.editable_area)
        if avg_len is None:
            avg_len = self.gen_avg_len_spinbox.value()
        if avg_len == 0 or total_cells == 0: return
        suggested = round(total_cells / avg_len)
        if suggested == 0: suggested = 1
        self.gen_arrow_count_spinbox.setValue(suggested)
        self.statusBar().showMessage(f"Suggested {suggested} arrows.", 3000)
        return suggested

    def process_image_import(self):
        if not self.canvas.active_layer:
            self.statusBar().showMessage("Vui lòng chọn hoặc tạo Layer trước.", 4000)
            return
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Image", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if not file_path: return
        w = self.img_w_spinbox.value()
        h = self.img_h_spinbox.value()
        thresh = self.img_thresh_spinbox.value()
        self.statusBar().showMessage(f"Đang xử lý {os.path.basename(file_path)}...")
        QApplication.processEvents()
        result = self.image_tools.process_image_to_points(input_path=file_path, target_width=w, target_height=h, alpha_threshold=thresh)
        if result["success"]:
            self.canvas.active_layer.arrows.clear()
            self.canvas.active_layer.editable_area = result["points"]
            self.canvas.level_grid_w = result["width"]
            self.canvas.level_grid_h = result["height"]
            self.canvas.update()
            self.statusBar().showMessage(result["message"], 5000)
            self.suggest_arrow_count()
        else:
            self.statusBar().showMessage(result["message"], 5000)

    def toggle_advanced_ui(self, checked):
        self.adv_params_widget.setVisible(checked)

    def apply_style_preset(self, preset_name):
        if preset_name in STYLE_PRESETS:
            config = STYLE_PRESETS[preset_name]
            self.spin_straight.setValue(config["straight"])
            self.spin_left.setValue(config["left"])
            self.spin_right.setValue(config["right"])
            self.spin_max_turns.setValue(config["max_turns"])

    def generate_level_smart(self):
        self.statusBar().showMessage("Initializing Generator...")
        QApplication.processEvents()
        active_layer = self.canvas.active_layer
        if not active_layer or not active_layer.editable_area:
            self.statusBar().showMessage("Error: No painted area to generate in.", 4000)
            return
        current_len = self.gen_avg_len_spinbox.value()
        min_len = 3
        fake_args = Args(alter_item_name=f"Manual_L{active_layer.id}", min_width=self.gen_min_width_spinbox.value(), max_width=self.gen_max_width_spinbox.value())
        validator = Validator()
        generator = HybridLevelGeneratorTestable(fake_args)
        start_arrow_id = self.canvas.arrow_id_counter
        all_arrows = self.canvas.get_all_arrows()
        is_loop = self.chk_smart_fill.isChecked()
        max_limit = self.gen_arrow_count_spinbox.value()
        generated_count = 0
        while current_len >= min_len:
            occupied = {p for arr in all_arrows for p in arr.points}
            available = active_layer.editable_area.difference(occupied)
            if not available: break
            num_to_gen = self.suggest_arrow_count(len(available), current_len)
            remaining_quota = max_limit - generated_count
            if num_to_gen > remaining_quota and not is_loop: num_to_gen = remaining_quota
            if num_to_gen <= 0: break
            self.statusBar().showMessage(f"Gen Length {current_len}: Trying to add {num_to_gen} arrows...")
            QApplication.processEvents()
            
            if self.chk_advanced_mode.isChecked():
                new_arrows, new_id_counter, msg = generator.generate_hybrid_level_advanced(
                    validator=validator, active_layer=active_layer, all_arrows_on_board=all_arrows,
                    start_arrow_id=start_arrow_id, num_to_gen=num_to_gen, avg_length=current_len,
                    straight_weight=self.spin_straight.value(), left_weight=self.spin_left.value(),
                    right_weight=self.spin_right.value(), max_turns=self.spin_max_turns.value())
            else:
                new_arrows, new_id_counter, msg = generator.generate_hybrid_level(
                    validator=validator, active_layer=active_layer, all_arrows_on_board=all_arrows,
                    start_arrow_id=start_arrow_id, num_to_gen=num_to_gen, avg_length=current_len)
            
            if new_arrows:
                self.canvas.validator.clear_cache()
                hypothetical_global_board = self.canvas.get_all_arrows() + new_arrows
                is_globally_solvable = self.canvas.validator.is_board_state_solvable(
                    hypothetical_global_board, self.canvas.grid_w, self.canvas.grid_h)
                if is_globally_solvable:
                    all_arrows.extend(new_arrows)
                    active_layer.arrows.extend(new_arrows)
                    start_arrow_id = new_id_counter
                    generated_count += len(new_arrows)
                    self.canvas.update()
                    if is_loop and current_len > min_len:
                        current_len -= 2
                        if current_len < min_len: current_len = min_len
                else:
                    print(f"Gen WARNING: Discarded {len(new_arrows)} arrows at len={current_len} due to GLOBAL conflict.")
                    self.statusBar().showMessage(f"Conflict detected! Skipped arrows at len {current_len}.", 2000)
                    if current_len == min_len: break
                    current_len -= 2
                    if current_len < min_len: current_len = min_len
            else:
                if current_len == min_len: break
                current_len -= 2
                if current_len < min_len: current_len = min_len
            if not is_loop: break
        self.canvas.arrow_id_counter = start_arrow_id
        self.canvas.update()
        self.statusBar().showMessage(f"Generation Done. Added {generated_count} arrows.", 5000)

    # --- ANALYSIS METHODS ---
    def start_full_analysis(self):
        data = self.get_current_level_data()
        if not data:
            QMessageBox.warning(self, "Warning", "Board is empty. Draw something first!")
            return
        
        self.btn_run_analysis.setEnabled(False)
        self.txt_analysis_report.setText("Running Analysis Pipeline...\nPlease wait...")
        self.statusBar().showMessage("Running Analysis...")
        
        render_visuals = self.chk_render_visuals.isChecked()
        level_id = self.level_id_spinbox.value()
        
        # Start Worker Thread
        self.analysis_thread = AnalysisWorker(self.analysis_manager, data, level_id, render_visuals)
        self.analysis_thread.finished.connect(self.on_analysis_finished)
        self.analysis_thread.error.connect(self.on_analysis_error)
        self.analysis_thread.start()

    def on_analysis_finished(self, report, summary, path):
        self.btn_run_analysis.setEnabled(True)
        self.txt_analysis_report.setText(report)
        self.statusBar().showMessage("Analysis Complete!", 5000)
        
        # Color code logic
        if summary.get("solvable_ratio", 0) > 0:
            self.txt_analysis_report.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.txt_analysis_report.setStyleSheet("color: red; font-weight: bold;")

    def on_analysis_error(self, error_msg):
        self.btn_run_analysis.setEnabled(True)
        self.txt_analysis_report.setText(f"Error:\n{error_msg}")
        self.statusBar().showMessage("Analysis Failed.", 5000)


# --- Application Entry Point ---
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())