# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Палеогеография: берега материков в прошлом по веб-службе GPlates.

Служба отдаёт GeoJSON с многоугольниками берегов на заданный возраст
в миллионах лет (URL). Модель движения плит MODEL охватывает последний
миллиард лет. Источник выбран автором 3 октября 2026 года. Расчёт без Qt:
адрес запроса, разбор ответа, прореживание контуров, название периода.

Суша рисуется заливкой на гладкой основе цвета OCEAN: нынешний снимок,
границы и подписи на это время убраны. Контуры ложатся в маску суши,
картинку всей Земли, её красит шейдер тайла. Линиями контуры
не рисуются: модель режет берега по плитам, швы шли бы по материкам.
"""
try:  # внутри плагина QGIS
    from .features import Shape
except ImportError:  # headless-тесты
    from features import Shape

SERVICE = "https://gws.gplates.org/reconstruct/coastlines/"
MODEL = "MERDITH2021"
MAX_AGE = 1000  # млн лет, охват модели
STEP = 5  # млн лет, шаг ползунка
ATTRIBUTION = ("Paleogeography: GPlates Web Service, Merdith et al. 2021",
               "https://gwsdoc.gplates.org/")
COLOR = (255, 236, 150, 255)
OCEAN = (0.10, 0.22, 0.40)  # цвет гладкой основы, океан
LAND = (0.66, 0.60, 0.42)  # цвет суши на ней
MASK_WIDTH = 2048  # пикселей в маске суши по долготе
WIDTH = 1.5
RING_POINTS = 120  # вершин на контур, не больше
MIN_SPAN = 1.5  # градусов, контур мельче не рисуется
# Контуров на возраст, не больше, остаются самые крупные. Модель режет
# берега по плитам на 1379 кусков, все вместе они давали 1.07 млн
# вершин линий, 3 октября 2026 года.
MAX_RINGS = 500
# Нижние границы периодов, млн лет, шкала ICS.
PERIODS = ((2.58, "quaternary"), (23.03, "neogene"), (66.0, "paleogene"),
           (145.0, "cretaceous"), (201.4, "jurassic"), (251.9, "triassic"),
           (298.9, "permian"), (358.9, "carboniferous"),
           (419.2, "devonian"), (443.8, "silurian"), (485.4, "ordovician"),
           (538.8, "cambrian"))
PRECAMBRIAN = "precambrian"


def url(age, model=MODEL):
    """Адрес берегов на возраст age млн лет."""
    return "{}?time={:g}&model={}".format(SERVICE, float(age), model)


def period(age):
    """Ключ периода для возраста age млн лет."""
    for base, key in PERIODS:
        if age < base:
            return key
    return PRECAMBRIAN


def thin(ring, limit=RING_POINTS):
    """Контур не больше чем из limit вершин, вершины через равный шаг."""
    if len(ring) <= limit:
        return list(ring)
    step = len(ring) / float(limit)
    return [ring[int(i * step)] for i in range(limit)]


def _rings(geometry):
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates") or []
    if kind == "Polygon":
        return coordinates[:1]
    if kind == "MultiPolygon":
        return [part[0] for part in coordinates if part]
    return []


def parse(data, limit=RING_POINTS, min_span=MIN_SPAN, count=MAX_RINGS):
    """Внешние контуры берегов из ответа службы: списки (широта,
    долгота) без повтора первой точки, от крупных к мелким. Мелкие
    контуры пропускаются."""
    out = []
    for feature in (data or {}).get("features") or []:
        for ring in _rings(feature.get("geometry") or {}):
            points = []
            for pair in ring:
                if len(pair) >= 2:
                    points.append((float(pair[1]), float(pair[0])))
            if len(points) > 1 and points[0] == points[-1]:
                points.pop()
            if len(points) < 3:
                continue
            lats = [p[0] for p in points]
            lons = [p[1] for p in points]
            span = max(max(lats) - min(lats), max(lons) - min(lons))
            if span < min_span:
                continue
            out.append((span, thin(points, limit)))
    out.sort(key=lambda item: -item[0])
    return [ring for _, ring in out[:count]]


def unwrapped(ring):
    """Контур для маски суши: долгота идёт без скачка на 180°, может
    выходить за ±180. Контур вокруг полюса дополнен до него, иначе
    заливка не закрывает полярную шапку."""
    out = [tuple(ring[0])]
    lon = raw = ring[0][1]
    for lat, value in list(ring[1:]) + [ring[0]]:
        lon += (value - raw + 180.0) % 360.0 - 180.0
        raw = value
        out.append((lat, lon))
    turn = lon - ring[0][1]
    if abs(turn) < 180.0:
        return out[:-1]
    pole = 90.0 if sum(p[0] for p in ring) > 0.0 else -90.0
    return out + [(pole, lon), (pole, ring[0][1])]


def shapes(rings):
    """Контуры линиями для глобуса."""
    return [Shape("line", list(ring) + [ring[0]], COLOR, WIDTH)
            for ring in rings]
