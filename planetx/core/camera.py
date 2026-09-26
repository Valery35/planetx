# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Камера глобуса и матрицы с отсчётом от глаза.

Камера хранит положение глаза в ECEF в float64 и ориентацию матрицей
3×3. Столбцы матрицы - оси камеры в ECEF, это вправо, вверх и назад.
Камера смотрит против оси «назад», как принято в OpenGL.

Мировые координаты в шейдер не попадают. Для каждого тайла матрица
считается в float64 от разности «центр тайла - глаз» и только потом
округляется до float32. Устройство описано в AGENTS.md, раздел
«Координаты».

Экранные координаты - пиксели окна, начало в левом верхнем углу, ось y
вниз, как у событий мыши в Qt.
"""
import math

import numpy as np

try:  # внутри плагина QGIS
    from .ellipsoid import A, B, ecef_to_geodetic, geodetic_to_ecef
except ImportError:  # headless-тесты
    from ellipsoid import A, B, ecef_to_geodetic, geodetic_to_ecef

# Отношение дальней плоскости отсечения к ближней. При 24 битах глубины
# это оставляет различимыми слои на ближней дистанции.
MAX_DEPTH_RATIO = 1e5
MIN_NEAR = 0.5
# Высота Эвереста с запасом. Рельеф за горизонтом эллипсоида виден
# до расстояния горизонта этой высоты.
MAX_TERRAIN = 9000.0
# Ближняя плоскость в доле расстояния до ближайшего рельефа. Запас
# на рельеф между точками опроса и на сетку тайла, собранную
# из высот грубее тех, по которым считается расстояние.
NEAR_SHARE = 0.5


def enu(lat, lon):
    """Оси восток, север, вверх в точке эллипсоида, строки 3×3."""
    la = math.radians(lat)
    lo = math.radians(lon)
    sl, cl = math.sin(la), math.cos(la)
    so, co = math.sin(lo), math.cos(lo)
    return np.array([[-so, co, 0.0],
                     [-sl * co, -sl * so, cl],
                     [cl * co, cl * so, sl]])


def orientation(lat, lon, heading, tilt):
    """Ориентация камеры над точкой.

    heading - азимут верха экрана от севера по часовой стрелке, градусы.
    tilt - отклонение взгляда от отвесного, 0 смотрит вниз, 90 на
    горизонт. Крен нулевой.
    """
    east, north, up = enu(lat, lon)
    psi = math.radians(heading)
    tau = math.radians(tilt)
    screen_up = north * math.cos(psi) + east * math.sin(psi)
    right = east * math.cos(psi) - north * math.sin(psi)
    forward = -up * math.cos(tau) + screen_up * math.sin(tau)
    cam_up = up * math.sin(tau) + screen_up * math.cos(tau)
    return np.stack([right, cam_up, -forward], axis=1)


def perspective(fov_y, aspect, near, far):
    """Матрица проекции OpenGL, по строкам."""
    f = 1.0 / math.tan(math.radians(fov_y) / 2.0)
    return np.array([
        [f / aspect, 0.0, 0.0, 0.0],
        [0.0, f, 0.0, 0.0],
        [0.0, 0.0, (far + near) / (near - far),
         2.0 * far * near / (near - far)],
        [0.0, 0.0, -1.0, 0.0]])


def clip_range(altitude, nearest=None):
    """Ближняя и дальняя плоскости отсечения.

    altitude - высота глаза над эллипсоидом. Дальняя плоскость стоит
    за горизонтом на расстоянии, с которого ещё видна вершина высотой
    MAX_TERRAIN. Без рельефа ближе высоты камеры поверхности нет,
    и ближняя плоскость берётся на 0.8 высоты. С рельефом nearest -
    расстояние до ближайшего рельефа, ближняя плоскость берётся
    на NEAR_SHARE от него. Отношение дальней к ближней не больше
    MAX_DEPTH_RATIO.
    """
    h = max(altitude, 1.0)
    far = math.sqrt(h * (2.0 * A + h)) + math.sqrt(
        MAX_TERRAIN * (2.0 * A + MAX_TERRAIN))
    close = 0.8 * h if nearest is None else NEAR_SHARE * nearest
    near = max(MIN_NEAR, min(close, 0.8 * h), far / MAX_DEPTH_RATIO)
    return near, far


class Camera:
    """Положение и ориентация камеры, размер окна и угол обзора."""

    def __init__(self, eye, rotation, width=1920, height=1080, fov_y=45.0):
        self.eye = np.array(eye, dtype=np.float64)
        self.rotation = np.array(rotation, dtype=np.float64)
        self.width = int(width)
        self.height = int(height)
        self.fov_y = float(fov_y)
        # Расстояние до ближайшего рельефа, от него считается ближняя
        # плоскость. None - рельефа нет.
        self.nearest = None

    @classmethod
    def look_at(cls, lat, lon, distance, heading=0.0, tilt=0.0, h=0.0,
                **kwargs):
        """Камера, которая смотрит на точку с расстояния distance."""
        rotation = orientation(lat, lon, heading, tilt)
        target = geodetic_to_ecef(lat, lon, h)
        eye = target + rotation[:, 2] * distance
        return cls(eye, rotation, **kwargs)

    def set_look_at(self, lat, lon, distance, heading=0.0, tilt=0.0,
                    h=0.0):
        """Поставить камеру так же, как look_at, сохранив размер окна."""
        self.rotation = orientation(lat, lon, heading, tilt)
        self.eye = geodetic_to_ecef(lat, lon, h) + self.rotation[:, 2] \
            * distance

    @property
    def aspect(self):
        return self.width / self.height

    @property
    def forward(self):
        return -self.rotation[:, 2]

    def altitude(self):
        return float(ecef_to_geodetic(self.eye)[2])

    def projection(self):
        near, far = clip_range(self.altitude(), self.nearest)
        return perspective(self.fov_y, self.aspect, near, far)

    def tile_model_view(self, center, scale=1.0):
        """Вид из глаза на тайл с центром center, 4×4, float64.

        Сдвиг «центр - глаз» считается в float64 до поворота. Именно
        здесь исчезают миллионы метров, которые float32 не удержал бы.
        scale сжимает тайл к центру Земли, так рисуется подстилка.
        """
        view = self.rotation.T
        out = np.eye(4)
        out[:3, :3] = view * scale
        out[:3, 3] = view @ (np.asarray(center, dtype=np.float64) * scale
                             - self.eye)
        return out

    def tile_mvp(self, center, projection=None, scale=1.0):
        """Матрица для шейдера тайла, float32, по строкам.

        В OpenGL она передаётся с транспонированием, glUniformMatrix4fv
        с transpose = GL_TRUE.
        """
        if projection is None:
            projection = self.projection()
        return (projection @ self.tile_model_view(center, scale)).astype(
            np.float32)

    def tiles_mvp(self, centers, projection=None, scales=None):
        """Матрицы для набора тайлов одной операцией, (N, 4, 4) float32.

        Даёт то же, что tile_mvp для каждого центра, но без цикла
        Python. Сдвиг «центр - глаз» считается в float64, как в
        tile_model_view.
        """
        if projection is None:
            projection = self.projection()
        centers = np.asarray(centers, dtype=np.float64).reshape(-1, 3)
        n = len(centers)
        scales = np.ones(n) if scales is None else np.asarray(
            scales, dtype=np.float64)
        view = self.rotation.T
        shift = (centers * scales[:, None] - self.eye) @ view.T
        model_view = np.zeros((n, 4, 4))
        model_view[:, :3, :3] = view[None, :, :] * scales[:, None, None]
        model_view[:, :3, 3] = shift
        model_view[:, 3, 3] = 1.0
        return np.ascontiguousarray(
            np.einsum("ij,njk->nik", projection, model_view),
            dtype=np.float32)

    def project(self, points):
        """Точки ECEF в пиксели окна, расчёт в float64.

        Возвращает массив (..., 2) и признак «перед камерой».
        """
        p = np.asarray(points, dtype=np.float64) - self.eye
        cam = p @ self.rotation
        clip = cam @ self.projection()[:3, :3].T
        clip_w = -cam[..., 2]
        ndc = clip[..., :2] / clip_w[..., None]
        return self.ndc_to_pixels(ndc), clip_w > 0.0

    def ndc_to_pixels(self, ndc):
        ndc = np.asarray(ndc)
        x = (ndc[..., 0] + 1.0) * 0.5 * self.width
        y = (1.0 - ndc[..., 1]) * 0.5 * self.height
        return np.stack([x, y], axis=-1)

    def earth_mask(self, erode=0):
        """Пиксели окна, луч через центр которых встречает эллипсоид.

        Массив bool формы (height, width). erode убирает полосу такой
        ширины в пикселях по краю диска. На краю многоугольники тайлов
        лежат внутри эллипсоида, и пиксель там законно остаётся фоном.
        """
        t = math.tan(math.radians(self.fov_y) / 2.0)
        px = (np.arange(self.width) + 0.5) / self.width * 2.0 - 1.0
        py = 1.0 - (np.arange(self.height) + 0.5) / self.height * 2.0
        gx, gy = np.meshgrid(px * t * self.aspect, py * t)
        cam = np.stack([gx, gy, -np.ones_like(gx)], axis=-1)
        d = cam @ self.rotation.T
        scale = np.array([1.0 / A, 1.0 / A, 1.0 / B])
        o = self.eye * scale
        ds = d * scale
        qa = (ds * ds).sum(axis=-1)
        qb = 2.0 * (ds @ o)
        qc = o @ o - 1.0
        disc = qb * qb - 4.0 * qa * qc
        # Снаружи эллипсоида оба корня одного знака, перед камерой они
        # положительны, когда qb < 0.
        mask = (disc >= 0.0) & (qb < 0.0)
        for _ in range(erode):
            inner = mask.copy()
            inner[1:, :] &= mask[:-1, :]
            inner[:-1, :] &= mask[1:, :]
            inner[:, 1:] &= mask[:, :-1]
            inner[:, :-1] &= mask[:, 1:]
            mask = inner
        return mask

    def ray(self, px, py):
        """Луч через точку окна, начало и единичное направление в ECEF."""
        t = math.tan(math.radians(self.fov_y) / 2.0)
        nx = 2.0 * px / self.width - 1.0
        ny = 1.0 - 2.0 * py / self.height
        d = self.rotation @ np.array([nx * t * self.aspect, ny * t, -1.0])
        return self.eye.copy(), d / np.linalg.norm(d)
