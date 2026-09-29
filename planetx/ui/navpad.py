# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Экранные органы навигации в правом верхнем углу вида.

Как в Google Earth: кольцо компаса с буквой N, внутри него джойстик
взгляда, ниже джойстик сдвига и ползунок высоты с кнопками плюс
и минус. Кольцо тянется мышью и поворачивает вид, щелчок по N ставит
север вверху. Джойстики и кнопки действуют, пока нажата кнопка мыши,
скорость растёт с отклонением. Бегунок ползунка стоит по высоте
камеры, перетаскивание задаёт новую.

Органы видны всегда. Пока курсор далеко, они стоят слабым контуром
без заливки и не мешают виду. Когда курсор подходит к углу вида,
органы рисуются целиком. Расчёт лежит в core/navpad.py.
"""
import math
import time

from qgis.PyQt.QtCore import QEvent, QPointF, QRect, QRectF, Qt, QTimer
from qgis.PyQt.QtGui import QColor, QFont, QPainter, QPen, QPolygonF, QRegion
from qgis.PyQt.QtWidgets import QWidget

from ..core.navigation import clamp_distance, lifted
from ..core.navpad import (FAINT, angle_delta, look_step, move_step,
                           north_angle, ring_angle, ring_turn,
                           slider_distance, slider_share, stick,
                           zoom_factor)
from ..i18n import tr
from ..qt_compat import enum

MARGIN = 8  # логических пикселей от края вида
NEAR_ZONE = 48  # столько пикселей вокруг органов курсор их проявляет
TICK = 16  # мс между шагами, пока кнопка мыши нажата
# Раскладка в логических пикселях.
WIDTH, HEIGHT = 84, 288
CX = WIDTH / 2.0
RING = (CX, 42.0)
R_OUT, R_IN = 38.0, 26.0
R_NORTH = 32.0  # радиус буквы N на кольце
LOOK_R = 18.0
MOVE = (CX, 120.0)
MOVE_R = 24.0
PLUS = (CX, 166.0)
MINUS = (CX, 274.0)
BUTTON_R = 10.0
TRACK = (184.0, 256.0)  # верх и низ дорожки ползунка
TRACK_HALF = 8.0


def _dist(x, y, centre):
    return math.hypot(x - centre[0], y - centre[1])


class NavPad(QWidget):
    """Органы навигации поверх вида view (render/view.py)."""

    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.setFixedSize(WIDTH, HEIGHT)
        self.setMouseTracking(True)
        self.setToolTip(tr(
            "Кольцо поворачивает вид, буква N ставит север вверху. "
            "Джойстик в кольце поворачивает взгляд, нижний сдвигает вид. "
            "Ползунок задаёт высоту, плюс и минус приближают и отдаляют."))
        self.part = None  # что нажато: ring, north, look, move, plus...
        self.stick = (0.0, 0.0)
        self.ring_last = 0.0
        self.moved = False
        self.hot = False  # курсор над органами
        self.near = False  # курсор у угла вида, органы проявлены
        self.last = time.monotonic()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.setMask(self._shape())
        view.installEventFilter(self)
        view.hovered.connect(self._view_hover)
        view.changed.connect(self._view_changed)
        self._place()

    # Показ.

    def _shape(self):
        ellipse = enum(QRegion, "RegionType", "Ellipse")

        def circle(centre, radius):
            r = int(math.ceil(radius)) + 1
            return QRegion(QRect(int(centre[0]) - r, int(centre[1]) - r,
                                 2 * r, 2 * r), ellipse)
        region = circle(RING, R_OUT).united(circle(MOVE, MOVE_R))
        region = region.united(circle(PLUS, BUTTON_R))
        region = region.united(circle(MINUS, BUTTON_R))
        return region.united(QRegion(QRect(
            int(CX - TRACK_HALF) - 1, int(TRACK[0]) - 2,
            int(2 * TRACK_HALF) + 2, int(TRACK[1] - TRACK[0]) + 4)))

    def _place(self):
        parent = self.parentWidget()
        self.move(parent.width() - WIDTH - MARGIN, MARGIN)

    def eventFilter(self, watched, event):
        if event.type() == enum(QEvent, "Type", "Resize"):
            self._place()
        return False

    def _view_hover(self, px, py):
        """Курсор над видом в пикселях кадра, (-1, -1) - ушёл."""
        if self.part is not None:
            return
        near = False
        if px >= 0:
            ratio = self.view.devicePixelRatioF()
            zone = self.geometry().adjusted(-NEAR_ZONE, -NEAR_ZONE,
                                            NEAR_ZONE, NEAR_ZONE)
            near = zone.contains(int(px / ratio), int(py / ratio))
        if near != self.near:
            self.near = near
            self.update()

    def _view_changed(self):
        if self.isVisible():
            self.update()

    def enterEvent(self, event):
        self.hot = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hot = False
        self.update()
        super().leaveEvent(event)

    # Мышь.

    def _hit(self, x, y):
        nav = self.view.navigator
        a = math.radians(north_angle(nav.pose.heading))
        north = (RING[0] + R_NORTH * math.sin(a),
                 RING[1] - R_NORTH * math.cos(a))
        d = _dist(x, y, RING)
        if _dist(x, y, north) <= 9.0:
            return "north"
        if R_IN <= d <= R_OUT:
            return "ring"
        if d < R_IN:
            return "look"
        if _dist(x, y, MOVE) <= MOVE_R:
            return "move"
        if _dist(x, y, PLUS) <= BUTTON_R:
            return "plus"
        if _dist(x, y, MINUS) <= BUTTON_R:
            return "minus"
        if abs(x - CX) <= TRACK_HALF and TRACK[0] - 2 <= y <= TRACK[1] + 2:
            return "slider"
        return None

    def _pos(self, event):
        pos = event.position() if hasattr(event, "position") else event.pos()
        return pos.x(), pos.y()

    def mousePressEvent(self, event):
        if self.view.shot is not None or event.button() != enum(
                Qt, "MouseButton", "LeftButton"):
            return
        x, y = self._pos(event)
        self.part = self._hit(x, y)
        self.moved = False
        self.view.navigator.stop()
        if self.part in ("ring", "north"):
            self.ring_last = ring_angle(x - RING[0], y - RING[1])
        elif self.part == "slider":
            self._slide(y)
        self._aim(x, y)
        if self.part in ("look", "move", "plus", "minus"):
            self.last = time.monotonic()
            self.timer.start(TICK)
        self.update()

    def mouseMoveEvent(self, event):
        x, y = self._pos(event)
        if self.part in ("ring", "north"):
            angle = ring_angle(x - RING[0], y - RING[1])
            delta = angle_delta(self.ring_last, angle)
            if abs(delta) > 0.5 or self.moved:
                self.moved = True
                self.part = "ring"
                self.ring_last = angle
                self.view.navigator.turn(ring_turn(0.0, delta), 0.0)
                self.view.update()
        elif self.part == "slider":
            self._slide(y)
        else:
            self._aim(x, y)

    def mouseReleaseEvent(self, event):
        if self.part == "north" and not self.moved:
            pose = self.view.navigator.pose
            self.view.fly_pose(pose.lat, pose.lon, pose.distance, 0.0,
                               pose.tilt)
        self.part = None
        self.stick = (0.0, 0.0)
        self.timer.stop()
        self.update()

    def _aim(self, x, y):
        if self.part == "look":
            self.stick = stick(x - RING[0], y - RING[1], LOOK_R)
        elif self.part == "move":
            self.stick = stick(x - MOVE[0], y - MOVE[1], MOVE_R)

    def _slide(self, y):
        share = (y - TRACK[0]) / (TRACK[1] - TRACK[0])
        self._zoom_to(slider_distance(share))
        self.update()

    def _zoom_to(self, distance):
        """Расстояние камеры distance, точка в середине вида на месте.
        Если в середине вида небо, расстояние ставится как есть."""
        view = self.view
        nav = view.navigator
        view._fit_camera()
        factor = distance / nav.pose.distance
        if not nav.zoom_now(view.camera.width / 2.0,
                            view.camera.height / 2.0, factor):
            pose = nav.pose.copy()
            pose.distance = clamp_distance(pose, distance)
            nav.set_pose(lifted(pose))
        view.update()

    def _tick(self):
        now = time.monotonic()
        dt = min(now - self.last, 0.1)
        self.last = now
        nav = self.view.navigator
        sx, sy = self.stick
        if self.part == "look" and (sx or sy):
            nav.look_around(*look_step(sx, sy, dt))
        elif self.part == "move" and (sx or sy):
            width = 2.0 * nav.pose.distance * math.tan(
                math.radians(self.view.camera.fov_y) / 2.0)
            nav.pan_by(*move_step(sx, sy, dt, width))
        elif self.part in ("plus", "minus"):
            direction = 1 if self.part == "plus" else -1
            self._zoom_to(nav.pose.distance * zoom_factor(direction, dt))
        self.view.update()
        self.update()

    # Рисование.

    def paintEvent(self, event):
        faint = not (self.hot or self.near or self.part)
        alpha = FAINT if faint else 1.0 if (self.hot or self.part) else 0.65
        p = QPainter(self)
        try:
            p.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
            # Вдали от курсора остаётся контур без заливки.
            fill = QColor(24, 24, 24, 0 if faint else int(150 * alpha))
            line = QColor(255, 255, 255, int(210 * alpha))
            accent = QColor(120, 190, 255, int(230 * alpha))
            p.setPen(QPen(line, 1.2))
            p.setBrush(fill)
            self._circle(p, RING, R_OUT - 0.5)
            p.setBrush(QColor(0, 0, 0, 0))
            self._circle(p, RING, R_IN)
            self._north(p, line, alpha)
            p.setBrush(fill)
            self._stick(p, RING, LOOK_R - 2, line, accent,
                        self.part == "look")
            p.setPen(QPen(line, 1.2))
            p.setBrush(fill)
            self._circle(p, MOVE, MOVE_R - 0.5)
            self._stick(p, MOVE, MOVE_R - 4, line, accent,
                        self.part == "move")
            for centre, sign in ((PLUS, "+"), (MINUS, "-")):
                p.setPen(QPen(line, 1.2))
                p.setBrush(accent if self.part == ("plus" if sign == "+"
                                                   else "minus") else fill)
                self._circle(p, centre, BUTTON_R - 0.5)
                self._sign(p, centre, sign, line)
            self._slider(p, fill, line, accent)
        finally:
            p.end()

    def _circle(self, p, centre, radius):
        p.drawEllipse(QPointF(*centre), radius, radius)

    def _north(self, p, line, alpha):
        a = math.radians(north_angle(self.view.navigator.pose.heading))
        x = RING[0] + R_NORTH * math.sin(a)
        y = RING[1] - R_NORTH * math.cos(a)
        # Светлый кружок с тёмной буквой, как в Google Earth.
        p.setPen(enum(Qt, "PenStyle", "NoPen"))
        p.setBrush(QColor(240, 240, 240, int(235 * alpha)))
        p.drawEllipse(QPointF(x, y), 7.0, 7.0)
        font = QFont(p.font())
        font.setPixelSize(10)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor(30, 30, 30, int(255 * alpha)))
        p.drawText(QRectF(x - 7, y - 7, 14, 14),
                   enum(Qt, "AlignmentFlag", "AlignCenter"), "N")

    def _stick(self, p, centre, reach, line, accent, active):
        """Четыре стрелки и шарик джойстика, сдвинутый при нажатии."""
        p.setPen(enum(Qt, "PenStyle", "NoPen"))
        p.setBrush(line)
        cx, cy = centre
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            tip = QPointF(cx + dx * reach, cy + dy * reach)
            base = reach - 6.0
            left = QPointF(cx + dx * base - dy * 4.0,
                           cy + dy * base + dx * 4.0)
            right = QPointF(cx + dx * base + dy * 4.0,
                            cy + dy * base - dx * 4.0)
            p.drawPolygon(QPolygonF([tip, left, right]))
        sx, sy = self.stick if active else (0.0, 0.0)
        p.setBrush(accent if active else line)
        p.drawEllipse(QPointF(cx + sx * (reach - 8), cy + sy * (reach - 8)),
                      4.0, 4.0)

    def _sign(self, p, centre, sign, line):
        p.setPen(QPen(line, 2.0))
        x, y = centre
        p.drawLine(QPointF(x - 5, y), QPointF(x + 5, y))
        if sign == "+":
            p.drawLine(QPointF(x, y - 5), QPointF(x, y + 5))

    def _slider(self, p, fill, line, accent):
        top, bottom = TRACK
        p.setPen(QPen(line, 1.2))
        p.setBrush(fill)
        p.drawRoundedRect(QRectF(CX - 3, top, 6, bottom - top), 3, 3)
        share = slider_share(self.view.navigator.pose.distance)
        y = top + share * (bottom - top)
        p.setBrush(accent if self.part == "slider" else line)
        p.drawRoundedRect(QRectF(CX - TRACK_HALF, y - 4, 2 * TRACK_HALF, 8),
                          3, 3)
