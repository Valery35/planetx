# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Вид неба: взгляд из центра небесной сферы, без Qt.

Направление взгляда - прямое восхождение и склонение J2000, север
мира вверху экрана. Изнутри сферы восток слева, как на звёздной карте.
Перетаскивание тянет небо за курсором, колесо меняет угол обзора.
Звёзды, Млечный путь, созвездия и планеты стоят в экваториальной
системе J2000, поворот на звёздное время здесь не нужен.
"""
import math

import numpy as np

FOV_MIN = 2.0  # угол обзора по вертикали, градусы
FOV_MAX = 110.0
DEC_LIMIT = math.radians(89.5)  # у самого полюса север вверху не задан
# Начальный вид: Орион и Телец, угол обзора 70°. Выбор помощника.
HOME = (85.0, 10.0, 70.0)


class SkyView:
    """Направление взгляда и угол обзора."""

    def __init__(self, ra=HOME[0], dec=HOME[1], fov=HOME[2]):
        self.ra = math.radians(ra)
        self.dec = math.radians(dec)
        self.fov = float(fov)

    def set(self, ra, dec, fov=None):
        """Взгляд на точку неба, градусы."""
        self.ra = math.radians(ra) % (2.0 * math.pi)
        self.dec = max(-DEC_LIMIT, min(DEC_LIMIT, math.radians(dec)))
        if fov is not None:
            self.fov = max(FOV_MIN, min(FOV_MAX, float(fov)))

    def forward(self):
        cd = math.cos(self.dec)
        return np.array([cd * math.cos(self.ra), cd * math.sin(self.ra),
                         math.sin(self.dec)])

    def rotation(self):
        """Оси камеры по столбцам - вправо, вверх, назад, как у
        core.camera. Правая ось смотрит на запад."""
        f = self.forward()
        right = np.cross(f, (0.0, 0.0, 1.0))
        right /= np.linalg.norm(right)
        up = np.cross(right, f)
        return np.stack([right, up, -f], axis=1)

    def radians_per_pixel(self, height):
        """Угол на пиксель кадра в середине вида."""
        return 2.0 * math.tan(math.radians(self.fov) / 2.0) / max(height, 1)

    def drag(self, dx, dy, height):
        """Небо тянется за курсором на dx, dy пикселей кадра, y вниз."""
        step = self.radians_per_pixel(height)
        self.ra = (self.ra + dx * step / max(math.cos(self.dec), 0.05)) \
            % (2.0 * math.pi)
        self.dec = max(-DEC_LIMIT, min(DEC_LIMIT, self.dec + dy * step))

    def zoom(self, factor):
        """Угол обзора умножается на factor, меньше 1 - ближе."""
        self.fov = max(FOV_MIN, min(FOV_MAX, self.fov * factor))

    def project(self, directions, width, height):
        """Пиксели кадра для направлений (N, 3) и маска точек перед
        взглядом."""
        d = np.asarray(directions, dtype=np.float64) @ self.rotation()
        front = d[:, 2] < -1e-9
        depth = np.where(front, -d[:, 2], 1.0)
        t = math.tan(math.radians(self.fov) / 2.0)
        aspect = width / max(height, 1)
        x = (d[:, 0] / depth / (t * aspect) + 1.0) * width / 2.0
        y = (1.0 - d[:, 1] / depth / t) * height / 2.0
        return np.stack([x, y], axis=1), front

    def direction_at(self, px, py, width, height):
        """Направление на небо под пикселем кадра, J2000."""
        t = math.tan(math.radians(self.fov) / 2.0)
        aspect = width / max(height, 1)
        local = np.array([(2.0 * px / width - 1.0) * t * aspect,
                          (1.0 - 2.0 * py / height) * t, -1.0])
        v = self.rotation() @ local
        return v / np.linalg.norm(v)


def ra_dec_of(vector):
    """Прямое восхождение от 0 до 360° и склонение направления."""
    x, y, z = vector
    return (math.degrees(math.atan2(y, x)) % 360.0,
            math.degrees(math.asin(max(-1.0, min(1.0, z)))))


def ra_dec_text(vector):
    """Запись направления в астрономической нотации J2000:
    α в часах, минутах и секундах, δ в градусах и минутах."""
    ra, dec = ra_dec_of(vector)
    seconds = int(round(ra / 15.0 * 3600.0)) % 86400
    arcmin = int(round(abs(dec) * 60.0))
    return "α {:02d}h {:02d}m {:02d}s  δ {}{:02d}° {:02d}′".format(
        seconds // 3600, seconds // 60 % 60, seconds % 60,
        "-" if dec < 0 else "+", arcmin // 60, arcmin % 60)
