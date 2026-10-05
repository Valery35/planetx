# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Наложения картинок, как в Google Earth: на поверхности, на экране
и фото с камерой. Просьба автора от 5 октября 2026 года.

Расчёт без Qt: свойства наложения, углы картинки на поверхности по
рамке KML и повороту, место картинки на экране, углы фото в ECEF по
камере и полю зрения, поза глобуса для перелёта к фото.

Наложение на поверхности - четыре угла (широта, долгота) в порядке
gx:LatLonQuad: левый нижний, правый нижний, правый верхний, левый
верхний. LatLonBox с поворотом переводится в те же углы, поворот -
против часовой стрелки вокруг середины в местной плоскости.

Камера фото - как Camera в KML: широта, долгота, высота над уровнем
моря, азимут, наклон (0 - взгляд вниз, 90 - на горизонт), крен. Поле
зрения - ViewVolume: левый, правый, нижний, верхний углы в градусах
от оси взгляда, near - расстояние до плоскости фото в метрах.
"""
import json
import math

import numpy as np

try:  # внутри плагина QGIS
    from . import ellipsoid
    from .camera import enu
    from .measure import destination
except ImportError:  # headless-тесты
    import ellipsoid
    from camera import enu
    from measure import destination

KINDS = ("ground", "screen", "photo")
WHITE = (255, 255, 255, 255)
# Новая картинка на поверхности - доля ширины видимой полосы.
NEW_SHARE = 0.5
# Плоскость нового фото - доля расстояния до точки взгляда.
NEAR_SHARE = 0.2
MIN_NEAR = 10.0  # метров
MAX_TILT = 85.0  # градусов, круче точка взгляда не берётся по лучу
# Наименьший промежуток обновления картинки по ссылке, секунд. Чаще
# запросы к чужому серверу не уходят.
MIN_REFRESH = 10.0


def refresh_interval(value):
    """Промежуток обновления картинки по ссылке в секундах: 0 - картинка
    не обновляется, иначе не меньше MIN_REFRESH."""
    try:
        value = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(value) or value <= 0.0:
        return 0.0
    return max(value, MIN_REFRESH)


class Overlay:
    """Свойства наложения без картинки.

    kind - "ground", "screen" или "photo". corners - углы картинки на
    поверхности. color - RGBA 0-255, альфа - непрозрачность. order -
    порядок рисования. У картинки на экране overlay_xy, screen_xy - пары
    (x, y, единицы x, единицы y), единицы fraction, pixels или
    insetPixels, size - так же, -1 - размер картинки, 0 - по пропорции,
    rotation - градусы. У фото camera и fov, near. box - рамка
    LatLonBox (север, юг, восток, запад, поворот) или None - четыре
    свободных угла gx:LatLonQuad. С рамкой углы считаются по ней.
    refresh - промежуток обновления картинки по ссылке в секундах,
    0 - не обновляется, как refreshMode onInterval в Icon KML.
    """

    def __init__(self, kind, corners=None, color=WHITE, order=0,
                 overlay_xy=(0.0, 0.0, "fraction", "fraction"),
                 screen_xy=(0.0, 0.0, "fraction", "fraction"),
                 size=(-1.0, -1.0, "fraction", "fraction"), rotation=0.0,
                 camera=None, fov=(-30.0, 30.0, -20.0, 20.0), near=100.0,
                 box=None, refresh=0.0):
        self.kind = kind
        self.refresh = refresh_interval(refresh)
        self.box = tuple(float(v) for v in box) if box else None
        if self.box is not None:
            corners = box_corners(*self.box)
        self.corners = [tuple(c) for c in corners] if corners else []
        self.color = tuple(color)
        self.order = int(order)
        self.overlay_xy = tuple(overlay_xy)
        self.screen_xy = tuple(screen_xy)
        self.size = tuple(size)
        self.rotation = float(rotation)
        self.camera = tuple(camera) if camera else None
        self.fov = tuple(fov)
        self.near = float(near)

    def set_box(self, box):
        """Новая рамка, углы - по ней."""
        self.box = tuple(float(v) for v in box)
        self.corners = box_corners(*self.box)

    def set_corners(self, corners):
        """Четыре свободных угла, рамки больше нет."""
        self.box = None
        self.corners = [tuple(c) for c in corners]

    def params(self):
        """Свойства для поля файла, JSON."""
        data = {"color": list(self.color), "order": self.order}
        if self.refresh:
            data["refresh"] = self.refresh
        if self.kind == "ground":
            data["corners"] = [list(c) for c in self.corners]
            if self.box is not None:
                data["box"] = list(self.box)
        elif self.kind == "screen":
            data.update(overlay_xy=list(self.overlay_xy),
                        screen_xy=list(self.screen_xy),
                        size=list(self.size), rotation=self.rotation)
        else:
            data.update(camera=list(self.camera or ()), fov=list(self.fov),
                        near=self.near)
        return json.dumps(data)


def from_params(kind, text, corners=None):
    """Наложение из поля файла. corners - углы из геометрии, они главнее
    углов в тексте."""
    try:
        data = json.loads(text or "{}")
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}

    def pair(name, default):
        value = data.get(name)
        if isinstance(value, list) and len(value) == 4:
            return (float(value[0]), float(value[1]), str(value[2]),
                    str(value[3]))
        return default

    base = Overlay(kind)
    color = data.get("color")
    box = data.get("box")
    return Overlay(
        kind, corners or data.get("corners"),
        box=box if isinstance(box, list) and len(box) == 5 else None,
        color=tuple(int(v) for v in color) if isinstance(color, list)
        and len(color) == 4 else WHITE,
        order=int(data.get("order", 0) or 0),
        overlay_xy=pair("overlay_xy", base.overlay_xy),
        screen_xy=pair("screen_xy", base.screen_xy),
        size=pair("size", base.size),
        rotation=float(data.get("rotation", 0.0) or 0.0),
        camera=data.get("camera") or None,
        fov=tuple(data.get("fov") or base.fov),
        near=float(data.get("near", base.near) or base.near),
        refresh=data.get("refresh", 0.0))


def _metres_per_degree(lat):
    """Метров в градусе широты и долготы на широте lat, шар."""
    radius = ellipsoid.A
    north = math.pi * radius / 180.0
    return north, north * max(math.cos(math.radians(lat)), 1e-6)


def box_corners(north, south, east, west, rotation=0.0):
    """Углы LatLonBox с поворотом rotation градусов против часовой
    стрелки вокруг середины."""
    if east < west:
        east += 360.0
    lat0 = (north + south) / 2.0
    lon0 = (east + west) / 2.0
    my, mx = _metres_per_degree(lat0)
    angle = math.radians(rotation)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    out = []
    for lat, lon in ((south, west), (south, east), (north, east),
                     (north, west)):
        x = (lon - lon0) * mx
        y = (lat - lat0) * my
        xr = x * cos_a - y * sin_a
        yr = x * sin_a + y * cos_a
        lon_r = lon0 + xr / mx
        out.append((lat0 + yr / my, (lon_r + 180.0) % 360.0 - 180.0))
    return out


# Рамка картинки на поверхности, как у Google Earth: середина, полуширина
# и полувысота в метрах местной плоскости, поворот против часовой стрелки.

def box_frame(box):
    """(широта и долгота середины, полуширина и полувысота в метрах,
    поворот в радианах) рамки (север, юг, восток, запад, поворот)."""
    north, south, east, west, rotation = box
    if east < west:
        east += 360.0
    lat0 = (north + south) / 2.0
    lon0 = (east + west) / 2.0
    my, mx = _metres_per_degree(lat0)
    return (lat0, lon0, (east - west) / 2.0 * mx,
            (north - south) / 2.0 * my, math.radians(rotation))


def frame_box(lat0, lon0, half_x, half_y, angle, scale_lat=None):
    """Рамка (север, юг, восток, запад, поворот) по середине, полуразмерам
    в метрах и повороту в радианах. scale_lat - широта, по которой метры
    переводятся в градусы, без неё - широта середины. Правка рамки
    берёт широту прежней середины, иначе края по долготе уплывали бы
    при растяжении по широте."""
    my, mx = _metres_per_degree(lat0 if scale_lat is None else scale_lat)
    half_x = max(abs(half_x), 1e-3)
    half_y = max(abs(half_y), 1e-3)
    east = lon0 + half_x / mx
    west = lon0 - half_x / mx
    wrap = lambda lon: (lon + 180.0) % 360.0 - 180.0  # noqa: E731
    return (min(lat0 + half_y / my, 89.9), max(lat0 - half_y / my, -89.9),
            wrap(east), wrap(west), math.degrees(angle))


def _local(lat0, lon0, lat, lon):
    my, mx = _metres_per_degree(lat0)
    dlon = (lon - lon0 + 180.0) % 360.0 - 180.0
    return dlon * mx, (lat - lat0) * my


def _turn(x, y, angle):
    c, s = math.cos(angle), math.sin(angle)
    return x * c - y * s, x * s + y * c


# Ручки рамки: углы в порядке углов, середины сторон (юг, восток, север,
# запад), середина и ромб поворота над северной стороной.
SIGNS = ((-1, -1), (1, -1), (1, 1), (-1, 1))
SIDES = ((0, -1), (1, 0), (0, 1), (-1, 0))
ROTATE_REACH = 1.25  # ромб - на столько полувысот от середины


def box_handles(box):
    """Ручки рамки (широта, долгота): (углы, середины сторон, середина,
    ромб поворота)."""
    lat0, lon0, hx, hy, angle = box_frame(box)
    my, mx = _metres_per_degree(lat0)

    def point(u, v):
        x, y = _turn(u, v, angle)
        return lat0 + y / my, (lon0 + x / mx + 180.0) % 360.0 - 180.0
    corners = [point(sx * hx, sy * hy) for sx, sy in SIGNS]
    sides = [point(sx * hx, sy * hy) for sx, sy in SIDES]
    return corners, sides, (lat0, (lon0 + 180.0) % 360.0 - 180.0), \
        point(0.0, ROTATE_REACH * hy)


def box_drag(box, handle, index, lat, lon, centred=False):
    """Новая рамка, когда ручку handle ("corner", "side", "center",
    "rotate") номер index тянут в точку (lat, lon). Угол и сторона
    растягивают рамку от противоположного угла или стороны, centred -
    от середины, как с Shift у Google Earth."""
    lat0, lon0, hx, hy, angle = box_frame(box)
    if handle == "center":
        return frame_box(lat, lon, hx, hy, angle, lat0)
    x, y = _local(lat0, lon0, lat, lon)
    if handle == "rotate":
        return frame_box(lat0, lon0, hx, hy, math.atan2(-x, y))
    u, v = _turn(x, y, -angle)
    if handle == "corner":
        sx, sy = SIGNS[index]
        if centred:
            return frame_box(lat0, lon0, abs(u), abs(v), angle, lat0)
        ox, oy = -sx * hx, -sy * hy
        cu, cv = (u + ox) / 2.0, (v + oy) / 2.0
        nhx, nhy = abs(u - ox) / 2.0, abs(v - oy) / 2.0
    else:
        sx, sy = SIDES[index]
        cu, cv, nhx, nhy = 0.0, 0.0, hx, hy
        if sx:
            if centred:
                nhx = abs(u)
            else:
                cu, nhx = (u - sx * hx) / 2.0, abs(u + sx * hx) / 2.0
        else:
            if centred:
                nhy = abs(v)
            else:
                cv, nhy = (v - sy * hy) / 2.0, abs(v + sy * hy) / 2.0
    cx, cy = _turn(cu, cv, angle)
    my, mx = _metres_per_degree(lat0)
    return frame_box(lat0 + cy / my, lon0 + cx / mx, nhx, nhy, angle, lat0)


def corners_box(corners):
    """Рамка LatLonBox без поворота, если углы - такая рамка: (север,
    юг, восток, запад), иначе None."""
    if len(corners) != 4:
        return None
    (s1, w1), (s2, e1), (n1, e2), (n2, w2) = corners
    close = 1e-9
    if abs(s1 - s2) < close and abs(n1 - n2) < close \
            and abs(w1 - w2) < close and abs(e1 - e2) < close \
            and n1 > s1:
        return n1, s1, e1, w1
    return None


def fit_box(lat, lon, width, aspect):
    """Рамка новой картинки на поверхности: середина (lat, lon), ширина
    width метров, высота - по пропорции aspect = ширина / высота."""
    return frame_box(lat, lon, width / 2.0,
                     width / max(aspect, 1e-6) / 2.0, 0.0)


def fit_corners(lat, lon, width, aspect):
    """Углы новой картинки на поверхности: середина (lat, lon), ширина
    width метров, высота - по пропорции aspect = ширина / высота."""
    my, mx = _metres_per_degree(lat)
    half_x = width / 2.0 / mx
    half_y = width / max(aspect, 1e-6) / 2.0 / my
    north = min(lat + half_y, 89.0)
    south = max(lat - half_y, -89.0)
    return box_corners(north, south, lon + half_x, lon - half_x)


def affine(corners):
    """Геопривязка картинки размером 1 × 1 по углам, если они -
    параллелограмм: (x0, dx по столбцу, dx по строке, y0, dy по столбцу,
    dy по строке) в градусах, как геопреобразование GDAL на картинку
    width × height после деления на размеры. Иначе None."""
    if len(corners) != 4:
        return None
    (y_ll, x_ll), (y_lr, x_lr), (y_ur, x_ur), (y_ul, x_ul) = corners
    # Параллелограмм: верхний правый угол - сумма сторон от левого
    # нижнего.
    if abs(x_ul + x_lr - x_ll - x_ur) > 1e-7 \
            or abs(y_ul + y_lr - y_ll - y_ur) > 1e-7:
        return None
    return (x_ul, x_ur - x_ul, x_ll - x_ul, y_ul, y_ur - y_ul, y_ll - y_ul)


def _length(value, units, total, own):
    if units == "pixels":
        return value
    if units == "insetPixels":
        return total - value
    return value * total if units == "fraction" else value * own


def screen_rect(overlay, view_w, view_h, image_w, image_h):
    """Место картинки на экране: (x, y, ширина, высота) в пикселях от
    левого верхнего угла вида. Отсчёт KML - от левого нижнего угла."""
    sx, sy, sxu, syu = overlay.size
    width = image_w if sx < 0 else (None if sx == 0 else
                                    _length(sx, sxu, view_w, image_w))
    height = image_h if sy < 0 else (None if sy == 0 else
                                     _length(sy, syu, view_h, image_h))
    ratio = image_w / float(max(image_h, 1))
    if width is None and height is None:
        width, height = image_w, image_h
    elif width is None:
        width = height * ratio
    elif height is None:
        height = width / ratio
    ox, oy, oxu, oyu = overlay.overlay_xy
    px, py, pxu, pyu = overlay.screen_xy
    anchor_x = _length(ox, oxu, width, width)
    anchor_y = _length(oy, oyu, height, height)
    at_x = _length(px, pxu, view_w, view_w)
    at_y = _length(py, pyu, view_h, view_h)
    left = at_x - anchor_x
    bottom = at_y - anchor_y
    return (left, view_h - bottom - height, width, height)


def _frame(camera):
    """Оси фото в ECEF: глаз, вперёд, вправо, вверх."""
    lat, lon, alt, heading, tilt, roll = camera
    east, north, up = enu(lat, lon)
    h = math.radians(heading)
    t = math.radians(tilt)
    forward = [math.sin(h) * math.sin(t) * e + math.cos(h) * math.sin(t) * n
               - math.cos(t) * u for e, n, u in zip(east, north, up)]
    right = [math.cos(h) * e - math.sin(h) * n for e, n in zip(east, north)]
    top = [right[1] * forward[2] - right[2] * forward[1],
           right[2] * forward[0] - right[0] * forward[2],
           right[0] * forward[1] - right[1] * forward[0]]
    r = math.radians(roll)
    cos_r, sin_r = math.cos(r), math.sin(r)
    right, top = ([cos_r * a + sin_r * b for a, b in zip(right, top)],
                  [-sin_r * a + cos_r * b for a, b in zip(right, top)])
    eye = [float(v) for v in ellipsoid.geodetic_to_ecef(lat, lon, alt)]
    return eye, forward, right, top


def photo_corners(camera, fov, near):
    """Углы плоскости фото в ECEF в порядке левый нижний, правый нижний,
    правый верхний, левый верхний."""
    eye, forward, right, top = _frame(camera)
    left, right_fov, bottom, top_fov = (math.radians(v) for v in fov)
    out = []
    for x, y in ((left, bottom), (right_fov, bottom), (right_fov, top_fov),
                 (left, top_fov)):
        a = near * math.tan(x)
        b = near * math.tan(y)
        out.append(tuple(e + near * f + a * r + b * t for e, f, r, t
                         in zip(eye, forward, right, top)))
    return out


def photo_mesh(camera, fov, near):
    """Плоскость фото для видеокарты: (центр в ECEF, вершины
    core.subsurface.IMAGE_VERTEX, индексы). Верх картинки - вверху
    плоскости."""
    corners = np.array(photo_corners(camera, fov, near), dtype=np.float64)
    center = corners.mean(axis=0)
    vertices = np.zeros(4, dtype=[("position", np.float32, 3),
                                  ("uv", np.float32, 2)])
    vertices["position"] = (corners - center).astype(np.float32)
    vertices["uv"] = [(0.0, 1.0), (1.0, 1.0), (1.0, 0.0), (0.0, 0.0)]
    indices = np.array([0, 1, 2, 0, 2, 3], dtype=np.uint32)
    return center, vertices, indices


def photo_pose(camera, near):
    """Поза глобуса для перелёта к фото: (широта, долгота точки
    взгляда, расстояние, азимут, наклон), глаз - в точке камеры.
    Точка взгляда - там, где взгляд встречает землю. Взгляд выше
    MAX_TILT упирается в точку на 10 расстояний near."""
    lat, lon, alt, heading, tilt, _ = camera
    tilt = min(max(tilt, 0.0), MAX_TILT)
    height = max(alt, 1.0)
    if tilt < MAX_TILT:
        distance = height / math.cos(math.radians(tilt))
    else:
        distance = max(10.0 * near, height / math.cos(math.radians(tilt)))
    ground = distance * math.sin(math.radians(tilt))
    if ground < 0.01:
        return lat, lon, distance, heading, tilt
    look_lat, look_lon = destination(lat, lon, heading, ground)
    return look_lat, look_lon, distance, heading, tilt


def view_camera(eye_lat, eye_lon, eye_alt, heading, tilt, vfov, aspect,
                distance):
    """Камера, поле зрения и near нового фото по нынешнему виду: глаз,
    азимут и наклон камеры глобуса, вертикальное поле vfov градусов,
    пропорция картинки aspect = ширина / высота, distance - расстояние
    до точки взгляда."""
    half_v = vfov / 2.0
    half_h = math.degrees(math.atan(math.tan(math.radians(half_v))
                                    * aspect))
    near = max(MIN_NEAR, NEAR_SHARE * distance)
    return ((eye_lat, eye_lon, eye_alt, heading, tilt, 0.0),
            (-half_h, half_h, -half_v, half_v), near)
