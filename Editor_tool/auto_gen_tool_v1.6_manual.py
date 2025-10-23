import sys
import math
import json
import random
import os
import time
from collections import deque
from PySide6.QtCore import Qt, QPointF, QRectF, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPolygonF
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QHBoxLayout,
                               QVBoxLayout, QPushButton, QListWidget, QLabel,
                               QSpinBox, QListWidgetItem, QStatusBar,
                               QSpacerItem, QSizePolicy)

from pathlib import Path

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
COLOR_TEXT_DEFAULT = QColor(23, 43, 77)


# --- DATA STRUCTURES ---
class Arrow:

    def __init__(self, points, direction, layer_id, arrow_id, color):
        self.points = points
        self.direction = direction
        self.layer_id = layer_id
        self.id = arrow_id
        self.color = color


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


# --- LOGIC MODULES ---


class Validator:

    def __init__(self):
        self.memo = {}

    def clear_cache(self):
        self.memo.clear()

    def _can_arrow_exit_cleanly(self, arrow_to_check, other_arrows, grid_w,
                                grid_h):
        obstacle_points = {p for arr in other_arrows for p in arr.points}
        self_body_points = set(arrow_to_check.points[1:])
        all_obstacles = obstacle_points.union(self_body_points)
        head = arrow_to_check.points[0]
        direction = arrow_to_check.direction
        current_pos = (head[0] + direction[0], head[1] + direction[1])
        while 0 <= current_pos[0] < grid_w and 0 <= current_pos[1] < grid_h:
            if current_pos in all_obstacles:
                return False
            current_pos = (current_pos[0] + direction[0],
                           current_pos[1] + direction[1])
        return True

    def find_movable_arrows(self, all_arrows, grid_w, grid_h):
        return [
            arr for i, arr in enumerate(all_arrows)
            if self._can_arrow_exit_cleanly(
                arr, all_arrows[:i] + all_arrows[i + 1:], grid_w, grid_h)
        ]

    # === MODIFICATION START: Sử dụng logic "Greedy" (Xóa tất cả) ===
    def is_board_state_solvable(self, arrows, grid_w, grid_h):
        # 1. Tối ưu hóa: Dùng Memoization (vẫn rất quan trọng)
        board_key = frozenset(arr.id for arr in arrows)
        if board_key in self.memo:
            return self.memo[board_key]

        # 2. Trường hợp cơ bản: Bảng trống -> Thành công
        if not arrows:
            self.memo[board_key] = True
            return True

        # 3. Tìm TẤT CẢ các mũi tên giải được ở trạng thái này
        movable_arrows = self.find_movable_arrows(arrows, grid_w, grid_h)

        # 4. Trường hợp bế tắc (Stuck):
        if not movable_arrows:
            self.memo[board_key] = False
            return False

        # 5. LOGIC MỚI: Xóa TẤT CẢ mũi tên giải được cùng lúc
        movable_ids = {arr.id for arr in movable_arrows}
        next_state = [arr for arr in arrows if arr.id not in movable_ids]

        # 6. Đệ quy vào trạng thái tiếp theo
        result = self.is_board_state_solvable(next_state, grid_w, grid_h)

        # 7. Lưu kết quả và trả về
        self.memo[board_key] = result
        return result

    # === MODIFICATION END ===


class LevelGenerator:

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.grid = [[0 for _ in range(width)] for _ in range(height)]
        self.paths = {}
        self.next_path_id = 1

    def _get_grid(self, x, y):
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.grid[y][x]
        return -1

    def _join_paths(self, id_to_keep, id_to_merge):
        if id_to_keep == id_to_merge or id_to_merge not in self.paths:
            return
        path_to_merge = self.paths[id_to_merge]
        self.paths[id_to_keep].extend(path_to_merge)
        del self.paths[id_to_merge]
        for y in range(self.height):
            for x in range(self.width):
                if self.grid[y][x] == id_to_merge:
                    self.grid[y][x] = id_to_keep

    def create_target_map(self):
        for diag in range(self.width + self.height - 1):
            for x in range(self.width):
                y = diag - x
                if not (0 <= y < self.height):
                    continue
                top_id = self._get_grid(x, y - 1)
                left_id = self._get_grid(x - 1, y)
                if top_id <= 0 and left_id <= 0:
                    new_id = self.next_path_id
                    self.grid[y][x] = new_id
                    self.paths[new_id] = [(x, y)]
                    self.next_path_id += 1
                elif top_id > 0 and left_id <= 0:
                    self.grid[y][x] = top_id
                    self.paths[top_id].append((x, y))
                elif left_id > 0 and top_id <= 0:
                    self.grid[y][x] = left_id
                    self.paths[left_id].append((x, y))
                else:
                    if random.random() < 0.5:
                        self.grid[y][x] = top_id
                        self.paths[top_id].append((x, y))
                        if top_id != left_id:
                            self._join_paths(top_id, left_id)
                    else:
                        self.grid[y][x] = left_id
                        self.paths[left_id].append((x, y))
                        if top_id != left_id:
                            self._join_paths(left_id, top_id)
        return list(self.paths.values())


# --- Custom Canvas Widget ---


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
    def effective_grid_size(self):
        return self.base_grid_size * self.zoom_level

    @property
    def pixel_offset_x(self): return self.view_padding * \
        self.effective_grid_size + self.pan_x

    @property
    def pixel_offset_y(self): return self.view_padding * \
        self.effective_grid_size + self.pan_y

    def grid_to_pixel(self, grid_pos):
        x = grid_pos[0] * self.effective_grid_size + self.pixel_offset_x
        y = grid_pos[1] * self.effective_grid_size + self.pixel_offset_y
        return QPointF(x, y)

    def pixel_to_grid(self, pixel_pos, do_round=True):
        egs = self.effective_grid_size
        if egs == 0:
            return (0, 0)
        x = (pixel_pos.x() - self.pixel_offset_x) / egs
        y = (pixel_pos.y() - self.pixel_offset_y) / egs
        if do_round:
            return (round(x), round(y))
        return (x, y)

    @property
    def grid_w(self):
        return self.level_grid_w

    @property
    def grid_h(self):
        return self.level_grid_h

    def get_grid_pos(self, pos):
        return self.pixel_to_grid(pos, do_round=True)

    def set_mode(self, mode):
        self.mode = mode
        if mode != "PLAYTEST":
            self.animating_arrows.clear()
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
            while x_start > 0:
                x_start -= egs
            while y_start > 0:
                y_start -= egs
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
                        p1, p2 = self.temp_arrow_path[
                            -2], self.temp_arrow_path[-1]
                        temp_dir = (p2[0] - p1[0], p2[1] - p1[1])
                        thickness = max(1.0, 5.0 * self.zoom_level)
                        pen = QPen(QColor(color), thickness, Qt.SolidLine,
                                   Qt.RoundCap, Qt.RoundJoin)
                        painter.setPen(pen)
                        path = QPolygonF()
                        for p in self.temp_arrow_path:
                            path.append(self.grid_to_pixel(p))
                        painter.drawPolyline(path)
                        head_center = self.grid_to_pixel(
                            self.temp_arrow_path[-1])
                        dx, dy = temp_dir[0], temp_dir[1]
                        s = max(3.0, 8.0 * self.zoom_level)
                        hp1 = head_center + \
                            QPointF(-dy * s - dx * s, dx * s - dy * s)
                        hp2 = head_center + \
                            QPointF(dy * s - dx * s, -dx * s - dy * s)
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
                self.draw_arrow(painter, arrow.points, arrow.direction,
                                arrow.color)
            for anim in self.animating_arrows:
                self.draw_arrow(painter, list(anim.path), anim.direction,
                                anim.color)
        painter.end()

    def draw_arrow(self, painter, points, direction, color):
        if not points:
            return
        thickness = max(1.0, 5.0 * self.zoom_level)
        pen = QPen(QColor(color), thickness, Qt.SolidLine, Qt.RoundCap,
                   Qt.RoundJoin)
        painter.setPen(pen)
        path = QPolygonF()
        for p in points:
            path.append(self.grid_to_pixel(p))
        painter.drawPolyline(path)
        if len(points) > 1:
            head_center = self.grid_to_pixel(points[0])
            dx, dy = direction[0], direction[1]
            s = max(3.0, 8.0 * self.zoom_level)
            p1 = head_center + QPointF(-dy * s - dx * s, dx * s - dy * s)
            p2 = head_center + QPointF(dy * s - dx * s, -dx * s - dy * s)
            p3 = head_center + QPointF(dx * s, dy * s)
            painter.setBrush(QBrush(QColor(color)))
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
                movable_arrows = self.validator.find_movable_arrows(
                    self.playtest_arrows, self.grid_w, self.grid_h)
                for arrow in movable_arrows:
                    if self.current_pos_grid in arrow.points:
                        self.animating_arrows.append(AnimatedArrow(arrow))
                        self.playtest_arrows = [
                            a for a in self.playtest_arrows if a.id != arrow.id
                        ]
                        break
            return
        if event.button() == Qt.LeftButton:
            self.is_drawing = True
            self.start_pos_grid = self.current_pos_grid
            if self.mode == "MANUAL_ARROW" and self.active_layer:
                if self.current_pos_grid in self.active_layer.editable_area:
                    self.temp_arrow_path = [self.current_pos_grid]
                else:
                    self.is_drawing = False
                    self.status_bar.showMessage(
                        "Cannot draw outside painted area!", 2000)
            elif self.mode == "PAINT_AREA" and self.active_layer:
                pass
        self.update()

        # Right-click to remove arrow
        if event.button() == Qt.RightButton:
            # Check all layers for arrows at the clicked position
            for layer in self.layers:
                for arrow in layer.arrows:
                    if self.current_pos_grid in arrow.points:
                        # Remove the arrow from its layer
                        layer.arrows.remove(arrow)
                        self.validator.clear_cache()
                        self.status_bar.showMessage(
                            f"Arrow removed from {layer.name}!", 2000)
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
            return
        mouse_buttons = event.buttons()
        if self.mode == "PAINT_AREA" and self.active_layer:
            if self.paint_sub_mode == "BRUSH":
                if mouse_buttons & Qt.LeftButton:
                    self.active_layer.editable_area.add(self.current_pos_grid)
                elif mouse_buttons & Qt.RightButton:
                    self.active_layer.editable_area.discard(
                        self.current_pos_grid)
        elif self.mode == "MANUAL_ARROW" and self.is_drawing and self.temp_arrow_path:
            if self.current_pos_grid != self.temp_arrow_path[
                    -1] and self.current_pos_grid in self.active_layer.editable_area:
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
        if self.mode == "PLAYTEST" or not self.is_drawing:
            if self.mode == "PLAYTEST":
                return
            if not self.is_drawing:
                return
        self.is_drawing = False
        end_pos_grid = self.get_grid_pos(event.position())
        if self.mode == "MANUAL_ARROW" and self.active_layer and len(
                self.temp_arrow_path) > 1:
            p1, p2 = self.temp_arrow_path[-2], self.temp_arrow_path[-1]
            direction = (p2[0] - p1[0], p2[1] - p1[1])
            path_to_save = list(reversed(self.temp_arrow_path))
            if not self.get_all_occupied_points().isdisjoint(
                    set(path_to_save)):
                self.status_bar.showMessage("Invalid: Arrows cannot overlap!",
                                            3000)
            else:
                hypo_arrow = Arrow(path_to_save, direction,
                                   self.active_layer.id, -1,
                                   self.active_layer.color)
                self.validator.clear_cache()
                if self.validator.is_board_state_solvable(
                        self.get_all_arrows() + [hypo_arrow], self.grid_w,
                        self.grid_h):
                    hypo_arrow.id = self.arrow_id_counter
                    self.active_layer.arrows.append(hypo_arrow)
                    self.arrow_id_counter += 1
                    self.status_bar.showMessage("Arrow added!", 2000)
                else:
                    self.status_bar.showMessage(
                        "Invalid: Creates an unsolvable state!", 3000)
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
        if delta > 0:
            self.zoom_level = min(self.zoom_level * 1.15, 8.0)
        elif delta < 0:
            self.zoom_level = max(self.zoom_level / 1.15, 0.1)
        if old_zoom == self.zoom_level:
            return
        new_egs = self.effective_grid_size
        base_origin_x = self.view_padding * new_egs
        base_origin_y = self.view_padding * new_egs
        new_px_x_no_pan = grid_pos_before_zoom[0] * new_egs + base_origin_x
        new_px_y_no_pan = grid_pos_before_zoom[1] * new_egs + base_origin_y
        self.pan_x = mouse_pos.x() - new_px_x_no_pan
        self.pan_y = mouse_pos.y() - new_px_y_no_pan
        self.update()
        event.accept()


# --- Main Application Window ---


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Level Editor - PySide6")
        self.setGeometry(100, 100, 1280, 720)
        self.setStatusBar(QStatusBar())
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        toolbar_widget = QWidget()
        toolbar_widget.setFixedWidth(240)
        toolbar_layout = QVBoxLayout(toolbar_widget)
        toolbar_layout.setAlignment(Qt.AlignTop)

        toolbar_layout.addWidget(QLabel("<h3>FILE</h3>"))
        self.level_id_spinbox = QSpinBox()
        self.level_id_spinbox.setMinimum(1)
        self.level_id_spinbox.setMaximum(999)
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
        toolbar_layout.addSpacing(15)
        self.btn_analyze = QPushButton("Deep Analysis (D)")
        toolbar_layout.addWidget(self.btn_analyze)
        self.btn_playtest = QPushButton("Playtest (P)")
        toolbar_layout.addWidget(self.btn_playtest)
        toolbar_layout.addSpacing(15)
        toolbar_layout.addWidget(QLabel("<h3>TOOLS</h3>"))
        self.btn_select = QPushButton("Select (Q)")
        self.btn_paint = QPushButton("Paint Area (W)")
        self.btn_draw = QPushButton("Draw Arrow (E)")
        toolbar_layout.addWidget(self.btn_select)
        toolbar_layout.addWidget(self.btn_paint)
        self.paint_tools_widget = QWidget()
        paint_tools_layout = QHBoxLayout(self.paint_tools_widget)
        paint_tools_layout.setContentsMargins(0, 5, 0, 5)
        self.btn_brush = QPushButton("Brush")
        self.btn_rect = QPushButton("Rect")
        self.btn_circle = QPushButton("Circle")
        paint_tools_layout.addWidget(self.btn_brush)
        paint_tools_layout.addWidget(self.btn_rect)
        paint_tools_layout.addWidget(self.btn_circle)
        toolbar_layout.addWidget(self.paint_tools_widget)
        self.paint_tools_widget.hide()
        toolbar_layout.addWidget(self.btn_draw)
        toolbar_layout.addSpacing(20)

        # === MODIFICATION START: Cập nhật Auto-Gen UI ===
        toolbar_layout.addWidget(QLabel("<h3>AUTO-GENERATION</h3>"))

        # --- UI cho "Desired Avg. Length" ---
        avg_len_layout = QHBoxLayout()
        avg_len_layout.addWidget(QLabel("Desired Avg. Length:"))
        self.gen_avg_len_spinbox = QSpinBox()
        self.gen_avg_len_spinbox.setMinimum(5)
        self.gen_avg_len_spinbox.setMaximum(100)
        self.gen_avg_len_spinbox.setValue(15)
        avg_len_layout.addWidget(self.gen_avg_len_spinbox)
        toolbar_layout.addLayout(avg_len_layout)

        # --- UI cho "Arrows" (Count) ---
        gen_layout = QHBoxLayout()
        gen_layout.addWidget(QLabel("Arrows:"))
        self.gen_arrow_count_spinbox = QSpinBox()
        self.gen_arrow_count_spinbox.setMinimum(1)
        self.gen_arrow_count_spinbox.setMaximum(500)  # Tăng giới hạn
        self.gen_arrow_count_spinbox.setValue(10)
        gen_layout.addWidget(self.gen_arrow_count_spinbox)

        # --- Nút "Suggest Count" ---
        self.btn_suggest_count = QPushButton("Suggest")
        gen_layout.addWidget(self.btn_suggest_count)
        toolbar_layout.addLayout(gen_layout)

        self.btn_generate_level = QPushButton("Generate Hybrid Level (G)")
        self.btn_generate_level.setShortcut(Qt.Key_G)
        toolbar_layout.addWidget(self.btn_generate_level)
        # === MODIFICATION END ===

        self.canvas = CanvasWidget(self.statusBar())
        self.exit_playtest_button = QPushButton("Exit Playtest", self.canvas)
        self.exit_playtest_button.setGeometry(self.canvas.width() // 2 - 100,
                                              self.canvas.height() - 60, 200,
                                              40)
        self.exit_playtest_button.hide()
        self.canvas.resizeEvent = lambda event: self.exit_playtest_button.setGeometry(
            self.canvas.width() // 2 - 100,
            self.canvas.height() - 60, 200, 40)
        layers_panel_widget = QWidget()
        layers_panel_widget.setFixedWidth(240)
        layers_panel_layout = QVBoxLayout(layers_panel_widget)
        layers_panel_layout.setAlignment(Qt.AlignTop)
        layers_panel_layout.addWidget(QLabel("<h3>LAYERS</h3>"))
        self.layer_list_widget = QListWidget()
        self.update_layer_list()
        layers_panel_layout.addWidget(self.layer_list_widget)
        self.add_layer_button = QPushButton("Add New Layer")
        layers_panel_layout.addWidget(self.add_layer_button)
        main_layout.addWidget(toolbar_widget)
        main_layout.addWidget(self.canvas)
        main_layout.addWidget(layers_panel_widget)

        self.btn_select.clicked.connect(lambda: self.set_active_mode("SELECT"))
        self.btn_paint.clicked.connect(
            lambda: self.set_active_mode("PAINT_AREA"))
        self.btn_draw.clicked.connect(
            lambda: self.set_active_mode("MANUAL_ARROW"))
        self.btn_brush.clicked.connect(
            lambda: (self.set_active_mode("PAINT_AREA"), self.canvas.set_paint_sub_mode("BRUSH")))
        self.btn_rect.clicked.connect(
            lambda: (self.set_active_mode("PAINT_AREA"), self.canvas.set_paint_sub_mode("RECT")))
        self.btn_circle.clicked.connect(
            lambda: (self.set_active_mode("PAINT_AREA"), self.canvas.set_paint_sub_mode("CIRCLE")))
        self.add_layer_button.clicked.connect(self.add_new_layer)
        self.layer_list_widget.currentRowChanged.connect(
            self.change_active_layer)
        self.btn_clear.clicked.connect(self.canvas.clear_all)
        self.btn_save.clicked.connect(self.save_level)
        self.btn_load.clicked.connect(self.load_level)
        self.btn_analyze.clicked.connect(self.analyze_level)
        self.btn_playtest.clicked.connect(self.start_playtest)
        self.exit_playtest_button.clicked.connect(self.exit_playtest)

        # === MODIFICATION START: Connect Gen Buttons ===
        self.btn_suggest_count.clicked.connect(
            self.suggest_arrow_count)  # Nút mới
        self.btn_generate_level.clicked.connect(self.generate_hybrid_level)
        # === MODIFICATION END ===

        self.set_active_mode("SELECT")
        self.update_layer_list()
        self.layer_list_widget.setCurrentRow(0)

    def set_active_mode(self, mode):
        is_playtest = (mode == "PLAYTEST")
        self.canvas.set_mode(mode)
        self.paint_tools_widget.setVisible(mode == "PAINT_AREA")
        if mode == "PAINT_AREA":
            self.canvas.set_paint_sub_mode("BRUSH")
        for child in self.centralWidget().layout().itemAt(
                0).widget().children():
            if isinstance(child, QWidget):
                child.setVisible(not is_playtest)
        self.centralWidget().layout().itemAt(2).widget().setVisible(
            not is_playtest)
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

    def save_level(self):
        level_id = self.level_id_spinbox.value()
        # filename = f"level_{level_id}.json"
        filename = Path(f"levels/level_{level_id}.json")
        all_arrows = self.canvas.get_all_arrows()
        all_painted_points = set()
        for layer in self.canvas.layers:
            all_painted_points.update(layer.editable_area)
        all_arrow_points = {p for arr in all_arrows for p in arr.points}
        all_relevant_points = all_painted_points.union(all_arrow_points)
        if not all_relevant_points:
            output_data = {"XSize": 1, "YSize": 1, "Arrows": []}
            self.statusBar().showMessage("Canvas is empty. Saved 1x1 file.",
                                         3000)
        else:
            min_x = min(p[0] for p in all_relevant_points)
            min_y = min(p[1] for p in all_relevant_points)
            max_x = max(p[0] for p in all_relevant_points)
            max_y = max(p[1] for p in all_relevant_points)
            offset_x = -min_x
            offset_y = -min_y
            new_x_size = max_x - min_x + 1
            new_y_size = max_y - min_y + 1
            output_data = {
                "XSize": new_x_size,
                "YSize": new_y_size,
                "Arrows": []
            }
            for arrow in all_arrows:
                if not arrow.points:
                    continue
                new_points = [(p[0] + offset_x, p[1] + offset_y)
                              for p in arrow.points]
                indices = [y * new_x_size + x for x, y in new_points]
                tail_x = new_points[0][0]
                tail_y = new_points[0][1]
                bend_count = 0
                if len(arrow.points) >= 3:
                    for k in range(len(arrow.points) - 2):
                        p1, p2, p3 = arrow.points[k], arrow.points[
                            k + 1], arrow.points[k + 2]
                        dir1 = (p2[0] - p1[0], p2[1] - p1[1])
                        dir2 = (p3[0] - p2[0], p3[1] - p2[1])
                        if dir1 != dir2:
                            bend_count += 1
                arrow_dict = {
                    "Dx": arrow.direction[0],
                    "Dy": arrow.direction[1],
                    "X": tail_x,
                    "Y": tail_y,
                    "Indices": indices,
                    "BendCount": bend_count
                }
                output_data["Arrows"].append(arrow_dict)
        try:
            with open(filename, 'w') as f:
                json.dump(output_data, f, separators=(',', ':'))
            size_msg = f"{output_data['XSize']}x{output_data['YSize']}"
            self.statusBar().showMessage(
                f"Level {level_id} saved (Dynamic Size: {size_msg})!", 3000)
            self.canvas.level_grid_w = output_data['XSize']
            self.canvas.level_grid_h = output_data['YSize']
        except Exception as e:
            self.statusBar().showMessage(f"Error saving: {e}", 5000)

    def load_level(self):
        level_id = self.level_id_spinbox.value()
        # filename = f"level_{level_id}.json"
        filename = Path(f"levels/level_{level_id}.json")
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
            x_size = data.get("XSize")
            y_size = data.get("YSize")
            if x_size is None or y_size is None:
                self.statusBar().showMessage(
                    f"File {filename} missing XSize or YSize", 3000)
                return
            self.canvas.level_grid_w = x_size
            self.canvas.level_grid_h = y_size
            new_layers = []
            layer_color = LAYER_COLORS[0]
            layer = Layer(0, "Imported Level", layer_color)
            arrow_id_counter = 0
            for i, arrow_data in enumerate(data.get("Arrows", [])):
                direction = (arrow_data.get("Dx", 0), arrow_data.get("Dy", 0))
                indices = arrow_data.get("Indices", [])
                points = []
                for index in indices:
                    x = index % x_size
                    y = index // x_size
                    points.append((x, y))
                if not points:
                    continue
                arrow_id = i
                arrow = Arrow(points, direction, layer.id, arrow_id,
                              layer_color)
                layer.arrows.append(arrow)
                arrow_id_counter = i + 1
            new_layers.append(layer)
            self.canvas.layers = new_layers
            self.canvas.active_layer = new_layers[0] if new_layers else None
            self.canvas.arrow_id_counter = arrow_id_counter
            self.canvas.validator.clear_cache()
            self.update_layer_list()
            if new_layers:
                self.layer_list_widget.setCurrentRow(0)
            self.canvas.update()
            self.statusBar().showMessage(
                f"Level {level_id} (game format) loaded!", 3000)
        except FileNotFoundError:
            self.statusBar().showMessage(f"File {filename} not found", 3000)
        except json.JSONDecodeError:
            self.statusBar().showMessage(f"File {filename} is not valid JSON",
                                         3000)
        except Exception as e:
            self.statusBar().showMessage(f"Error loading: {e}", 5000)

    def analyze_level(self):
        self.statusBar().showMessage("Analyzing...")
        QApplication.processEvents()
        self.canvas.validator.clear_cache()
        is_solvable = self.canvas.validator.is_board_state_solvable(
            self.canvas.get_all_arrows(), self.canvas.grid_w,
            self.canvas.grid_h)
        if is_solvable:
            self.statusBar().showMessage("Analysis: Level is SOLVABLE!", 5000)
        else:
            self.statusBar().showMessage("Analysis: Level is UNSOLVABLE!",
                                         5000)

    def start_playtest(self):
        all_arrows = self.canvas.get_all_arrows()
        all_arrow_points = {p for arr in all_arrows for p in arr.points}
        if not all_arrow_points:
            self.set_active_mode("PLAYTEST")
            self.canvas.playtest_arrows = []
            self.canvas.animating_arrows = []
            self.canvas.level_grid_w = 1
            self.canvas.level_grid_h = 1
            return
        min_x = min(p[0] for p in all_arrow_points)
        min_y = min(p[1] for p in all_arrow_points)
        max_x = max(p[0] for p in all_arrow_points)
        max_y = max(p[1] for p in all_arrow_points)
        offset_x = -min_x
        offset_y = -min_y
        playtest_grid_w = max_x - min_x + 1
        playtest_grid_h = max_y - min_y + 1
        self.canvas.level_grid_w = playtest_grid_w
        self.canvas.level_grid_h = playtest_grid_h
        playtest_arrows_shifted = []
        for arrow in all_arrows:
            new_points = [(p[0] + offset_x, p[1] + offset_y)
                          for p in arrow.points]
            shifted_arrow = Arrow(new_points, arrow.direction, arrow.layer_id,
                                  arrow.id, arrow.color)
            playtest_arrows_shifted.append(shifted_arrow)
        self.set_active_mode("PLAYTEST")
        self.canvas.playtest_arrows = playtest_arrows_shifted
        self.canvas.animating_arrows = []

    def exit_playtest(self):
        self.set_active_mode("SELECT")

    # === MODIFICATION START: Thêm hàm suggest_arrow_count ===
    def suggest_arrow_count(self):
        active_layer = self.canvas.active_layer
        if not active_layer:
            self.statusBar().showMessage("No active layer selected.", 4000)
            return

        total_cells = len(active_layer.editable_area)
        if total_cells == 0:
            self.statusBar().showMessage("Painted area is empty.", 4000)
            return

        avg_length = self.gen_avg_len_spinbox.value()
        if avg_length == 0:
            self.statusBar().showMessage("Average length cannot be zero.",
                                         4000)
            return

        suggested_count = round(total_cells / avg_length)
        if suggested_count == 0:
            suggested_count = 1

        self.gen_arrow_count_spinbox.setValue(suggested_count)
        self.statusBar().showMessage(
            f"Suggested {suggested_count} arrows (for {total_cells} cells).",
            3000)

    # === MODIFICATION END ===

    def _perform_random_walk(self,
                             start_pos,
                             all_occupied_points,
                             editable_area,
                             gen_grid_w,
                             gen_grid_h,
                             max_len=30):
        path = [start_pos]
        visited = {start_pos}
        current_pos = start_pos
        for _ in range(int(max_len) - 1):
            x, y = current_pos
            neighbors = []
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = x + dx, y + dy
                neighbor = (nx, ny)
                if not (0 <= nx < gen_grid_w and 0 <= ny < gen_grid_h):
                    continue
                if neighbor not in editable_area:
                    continue
                if neighbor not in all_occupied_points and neighbor not in visited:
                    neighbors.append(neighbor)
            if not neighbors:
                break
            next_pos = random.choice(neighbors)
            path.append(next_pos)
            visited.add(next_pos)
            current_pos = next_pos
        return path

    def generate_hybrid_level(self):
        self.statusBar().showMessage(
            "Generating level in painted area... (This will be slow)")
        QApplication.processEvents()
        num_to_gen = self.gen_arrow_count_spinbox.value()
        max_retries_per_arrow = 100
        active_layer = self.canvas.active_layer
        if not active_layer:
            self.statusBar().showMessage("No active layer selected.", 4000)
            return
        editable_area = active_layer.editable_area
        if not editable_area:
            self.statusBar().showMessage(
                "Active layer has no painted area to generate in.", 4000)
            return
        all_arrows_on_board = self.canvas.get_all_arrows()

        # 3. Tính toán ranh giới và độ lệch (offset) CỦA editable_area
        min_x = min(p[0] for p in editable_area)
        min_y = min(p[1] for p in editable_area)
        max_x = max(p[0] for p in editable_area)
        max_y = max(p[1] for p in editable_area)
        gen_offset_x = -min_x
        gen_offset_y = -min_y
        gen_grid_w = max_x - min_x + 1
        gen_grid_h = max_y - min_y + 1

        # 4. Dịch chuyển (shift) các đối tượng vào "Thế giới ảo"
        gen_editable_area = {(p[0] + gen_offset_x, p[1] + gen_offset_y)
                             for p in editable_area}
        gen_arrows_on_board = []
        gen_occupied_points = set()
        for arrow in all_arrows_on_board:
            is_in_area = False
            shifted_points = []
            for p in arrow.points:
                if p in editable_area:
                    is_in_area = True
                shifted_points.append(
                    (p[0] + gen_offset_x, p[1] + gen_offset_y))
            if is_in_area:
                virtual_arrow = Arrow(shifted_points, arrow.direction,
                                      arrow.layer_id, arrow.id, arrow.color)
                gen_arrows_on_board.append(virtual_arrow)
                for p_shifted, p_original in zip(shifted_points, arrow.points):
                    if p_original in editable_area:
                        gen_occupied_points.add(p_shifted)

        newly_generated_arrows = []
        arrow_id_counter = self.canvas.arrow_id_counter
        default_color = active_layer.color

        # === MODIFICATION START: Sử dụng Avg. Length từ UI ===
        # Lấy giá trị từ spinbox mới
        avg_length = self.gen_avg_len_spinbox.value()
        # Đặt min_len tối thiểu là 2 (head + 1 body)
        min_len = max(2, int(avg_length * 0.5))
        max_len = int(avg_length * 1.5)
        # Sử dụng max_len này cho random walk
        max_walk_len = max_len
        # (Xóa bỏ logic tính total_cells, avg_len, max_arrow_len cũ)
        # === MODIFICATION END ===

        for i in range(num_to_gen):
            self.statusBar().showMessage(
                f"Trying to generate arrow {i+1}/{num_to_gen}...")
            QApplication.processEvents()
            found_arrow = False
            for retry in range(max_retries_per_arrow):
                p2_candidates = []
                for pos in gen_editable_area:
                    if pos not in gen_occupied_points:
                        p2_candidates.append(pos)
                if not p2_candidates:
                    break
                random.shuffle(p2_candidates)
                start_p2 = None
                p1 = None
                found_start_pair = False
                for p2_cand in p2_candidates:
                    p1_candidates = []
                    for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                        p1_cand = (p2_cand[0] + dx, p2_cand[1] + dy)
                        if p1_cand in gen_editable_area and p1_cand not in gen_occupied_points:
                            p1_candidates.append(p1_cand)
                    if p1_candidates:
                        p1 = random.choice(p1_candidates)
                        start_p2 = p2_cand
                        found_start_pair = True
                        break
                if not found_start_pair:
                    break

                temp_occupied = gen_occupied_points.union({p1})
                path_body = self._perform_random_walk(
                    start_p2,
                    temp_occupied,
                    gen_editable_area,
                    gen_grid_w,
                    gen_grid_h,
                    max_len=max_walk_len - 1  # <-- Sử dụng max_walk_len mới
                )

                path = [p1] + path_body

                # === MODIFICATION START: Lọc độ dài ===
                if not (min_len <= len(path) <= max_len):
                    continue  # Path quá ngắn hoặc quá dài -> Hủy, thử lại
                # === MODIFICATION END ===

                direction = (p1[0] - start_p2[0], p1[1] - start_p2[1])
                temp_arrow = Arrow(path, direction, active_layer.id,
                                   arrow_id_counter, default_color)

                hypothetical_board = gen_arrows_on_board + \
                    newly_generated_arrows + [temp_arrow]
                self.canvas.validator.clear_cache()

                is_solvable = self.canvas.validator.is_board_state_solvable(
                    hypothetical_board, gen_grid_w, gen_grid_h)
                if is_solvable:
                    newly_generated_arrows.append(temp_arrow)
                    gen_occupied_points.update(path)
                    arrow_id_counter += 1
                    found_arrow = True
                    break

            if not found_arrow:
                self.statusBar().showMessage(
                    f"Could not find valid arrow {i+1}. Stopping.", 4000)
                break

        if not newly_generated_arrows:
            self.statusBar().showMessage(
                "Generation complete, but 0 valid arrows found. Try again.",
                5000)
            return

        final_arrows_to_add = []
        for arrow in newly_generated_arrows:
            original_points = [(p[0] - gen_offset_x, p[1] - gen_offset_y)
                               for p in arrow.points]
            real_arrow = Arrow(original_points, arrow.direction,
                               active_layer.id, arrow.id, arrow.color)
            final_arrows_to_add.append(real_arrow)

        self.canvas.active_layer.arrows.extend(final_arrows_to_add)
        self.canvas.arrow_id_counter = arrow_id_counter
        self.canvas.update()
        self.statusBar().showMessage(
            f"Successfully generated {len(final_arrows_to_add)} arrows!", 5000)


# --- Application Entry Point ---
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
