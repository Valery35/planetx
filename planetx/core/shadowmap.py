# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тени в кадре при строке «Солнце» - карта глубины со стороны солнца.
Расчёт без Qt.

Задача автора от 28 октября 2026 года, вторая часть теней. Карта
глубины - ортогональная проекция вдоль лучей солнца на квадрат со
стороной 2·radius вокруг точки взгляда center. Тени - только вблизи
камеры: radius - доля SHARE расстояния до точки взгляда, от NEAR до
REACH, дальше FROM теней нет. Глубина вдоль лучей - столько, сколько
под низким солнцем занимает полоса земли, накрытая квадратом.

Мировые координаты в видеокарту не попадают. Матрица света тайла -
поворот в оси света и сдвиг «центр тайла - центр карты», посчитанный
в float64, как у матриц камеры. Центр карты привязан к сетке текселей
карты в осях света: при сдвиге вида тень не дрожит.
"""
import math

import numpy as np

MAP_SIZE = 2048  # текселей карты на сторону
SHARE = 1.2  # радиус карты в долях расстояния до точки взгляда
NEAR = 300.0  # м, наименьший радиус
REACH = 5000.0  # м, наибольший радиус
FROM = 40000.0  # м, дальше этого расстояния до точки взгляда теней нет
MIN_SUN = math.sin(math.radians(1.0))  # солнце ниже - теней нет
LOW_SUN = 0.08  # синус высоты солнца, с которой считается глубина
DEPTH_MAX = 80000.0  # м, наибольшая полуглубина вдоль лучей
FADE = 0.8  # доля радиуса, с которой тени гаснут к краю
OFFSET_TEXELS = 1.5  # сдвиг точки по нормали перед сравнением, текселей
BIAS_TEXELS = 0.5  # запас глубины при сравнении, в размерах текселя
RADIUS_STEPS = 4  # ступеней радиуса на удвоение - карта не дрожит


def radius_for(distance):
    """Радиус карты по расстоянию до точки взгляда или None - далеко.
    Радиус идёт ступенями 2^(1/RADIUS_STEPS), так приближение колесом
    не меняет масштаб карты каждый кадр."""
    if not distance or distance > FROM:
        return None
    raw = min(max(distance * SHARE, NEAR), REACH)
    step = 2.0 ** (math.ceil(math.log2(raw) * RADIUS_STEPS) / RADIUS_STEPS)
    return min(step, REACH)


class LightFrame:
    """Оси света и матрицы карты теней.

    center - точка взгляда в ECEF (м), sun - направление на солнце
    в ECEF, radius - полусторона квадрата карты, м."""

    def __init__(self, center, sun, radius, size=MAP_SIZE):
        center = np.asarray(center, dtype=np.float64)
        sun = np.asarray(sun, dtype=np.float64)
        sun = sun / np.linalg.norm(sun)
        up_hint = center / np.linalg.norm(center)
        forward = -sun  # от солнца к земле
        # Оси света - только от направления солнца, не от центра карты:
        # иначе при сдвиге вида они поворачивались, и проекция центра
        # Земли уходила на текселы - сетка карты и тени дрожали.
        right = np.cross(forward, np.array([0.0, 0.0, 1.0]))
        if np.linalg.norm(right) < 1e-6:
            right = np.array([1.0, 0.0, 0.0])
        right /= np.linalg.norm(right)
        up = np.cross(right, forward)
        self.sin_sun = float(np.dot(sun, up_hint))
        self.radius = float(radius)
        self.size = int(size)
        self.texel = 2.0 * self.radius / self.size
        # Привязка центра к сетке текселей в осях света.
        a = float(np.dot(center, right))
        b = float(np.dot(center, up))
        center = center + (round(a / self.texel) * self.texel - a) * right \
            + (round(b / self.texel) * self.texel - b) * up
        self.center = center
        self.depth = min(self.radius / max(self.sin_sun, LOW_SUN),
                         DEPTH_MAX) + self.radius
        self.axes = np.stack([right / self.radius, up / self.radius,
                              forward / self.depth])  # строки 3×3

    @property
    def active(self):
        """Солнце над горизонтом точки взгляда."""
        return self.sin_sun > MIN_SUN

    def matrices(self, centers, scales=None):
        """Матрицы света для набора центров (N, 4, 4) float64 по строкам:
        точка от центра тайла в координаты отсечения карты."""
        centers = np.asarray(centers, dtype=np.float64).reshape(-1, 3)
        n = len(centers)
        scales = np.ones(n) if scales is None else np.asarray(
            scales, dtype=np.float64)
        shift = (centers * scales[:, None] - self.center) @ self.axes.T
        out = np.zeros((n, 4, 4))
        out[:, :3, :3] = self.axes[None, :, :] * scales[:, None, None]
        out[:, :3, 3] = shift
        out[:, 3, 3] = 1.0
        return out

    def project(self, points):
        """Точки ECEF в координаты отсечения карты (..., 3)."""
        p = np.asarray(points, dtype=np.float64) - self.center
        return p @ self.axes.T

    @property
    def offset(self):
        """Сдвиг точки по нормали перед сравнением, м."""
        return OFFSET_TEXELS * self.texel

    @property
    def bias(self):
        """Запас глубины при сравнении в долях глубины карты 0-1."""
        return BIAS_TEXELS * self.texel / (2.0 * self.depth)


class LightCamera:
    """Камера для прохода карты теней: то, что зданиям и моделям нужно
    от камеры вида, - глаз и матрицы набора центров."""

    def __init__(self, frame):
        self.frame = frame
        self.eye = frame.center

    def tiles_mvp(self, centers, projection=None, scales=None):
        return np.ascontiguousarray(self.frame.matrices(centers, scales),
                                    dtype=np.float32)
