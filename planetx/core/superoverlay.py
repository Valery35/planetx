# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Суперналожения KML: дерево сетевых ссылок с Region. Расчёт без Qt.

Просьба автора от 20 октября 2026 года, образец - Mountain View DOQQ
Google (mv-doqq.kml, больше 900 тайлов). Суперналожение - большой
снимок, нарезанный тайлами: в документе GroundOverlay тайла и сетевые
ссылки (NetworkLink с viewRefreshMode onRegion) на документы четырёх
подробных тайлов, у каждой ссылки и наложения свой Region. Документ
ссылки загружается, когда её Region активен, наложение видно, когда
активны его Region и Region всех папок и ссылок над ним. Так из сотен
тайлов в памяти держатся десятки у вида.

Region активен, когда его рамка задевает рамку вида и размер рамки на
экране - корень из площади, в пикселях - не меньше minLodPixels и не
больше maxLodPixels. Размер считается по ближайшей к глазу точке рамки
с фокусным расстоянием окна, а не постоянным region.REF_FOCAL: тайл
256 пикселей с minLodPixels 128 заменяется подробными, когда на экране
шире 128 пикселей, как у Google Earth.

Дерево держит документы, не их картинки: картинки берёт окно глобуса
(ui/superoverlay.py) для видимых тайлов. Документов в памяти не больше
MAX_LOADED, лишние давно неактивные уходят вместе с поддеревом.

Модуль Qt не знает.
"""
import math
from collections import namedtuple

try:  # внутри плагина QGIS
    from . import region as kml_region
    from .ellipsoid import geodetic_to_ecef
    from .kml import KFolder, KOverlay
except ImportError:  # headless-тесты
    import region as kml_region
    from ellipsoid import geodetic_to_ecef
    from kml import KFolder, KOverlay

MAX_DEPTH = 32  # уровней ссылок, страховка от ссылки на себя
MAX_LOADED = 400  # документов в памяти
# Тайлов на виде не больше: наложение QGIS собирает их растрами.
MAX_SHOWN = 160

Tile = namedtuple("Tile", "key href image corners order color regions")
Tile.__doc__ = """Тайл суперналожения: ключ, адрес картинки или байты
image из KMZ, углы core.overlays, порядок drawOrder, цвет RGBA, цепочка
Region от корня."""


class Node:
    """Документ сетевой ссылки: адрес, цепочка Region от корня, глубина,
    состояние "new", "loading", "ready" или "failed", тайлы и дети."""

    def __init__(self, url, regions, depth):
        self.url = url
        self.regions = tuple(regions)
        self.depth = depth
        self.state = "new"
        self.tiles = []
        self.children = []
        self.used = 0.0  # время, когда документ был активен
        self.size = 0.0  # размер Region на экране в последнем шаге


def _lon_in(lon, west, east):
    """Долгота внутри промежутка, в том числе через линию перемены дат."""
    span = (east - west) % 360.0
    if span == 0.0 and east != west:
        span = 360.0
    return (lon - west) % 360.0 <= span


def overlaps(rect, box):
    """Рамка Region rect задевает рамку вида box (запад, юг, восток,
    север)."""
    west, south, east, north = box
    if rect.north < south or rect.south > north:
        return False
    if east - west >= 360.0 or (west == -180.0 and east == 180.0):
        return True
    return (_lon_in(rect.west, west, east) or _lon_in(rect.east, west, east)
            or _lon_in(west, rect.west, rect.east))


def nearest(rect, lat, lon):
    """Ближайшая к точке (lat, lon) точка рамки Region, градусы."""
    near_lat = min(max(lat, rect.south), rect.north)
    if _lon_in(lon, rect.west, rect.east):
        return near_lat, lon
    to_west = (rect.west - lon) % 360.0
    to_east = (lon - rect.east) % 360.0
    return near_lat, rect.west if to_west < to_east else rect.east


def pixels(rect, eye, eye_geo, focal):
    """Размер рамки на экране в пикселях: корень из её площади на
    расстоянии ближайшей точки рамки от глаза eye (ECEF, метры).
    eye_geo - широта и долгота под глазом."""
    lat, lon = nearest(rect, *eye_geo)
    x, y, z = geodetic_to_ecef(lat, lon, 0.0)
    distance = math.sqrt((eye[0] - x) ** 2 + (eye[1] - y) ** 2
                         + (eye[2] - z) ** 2)
    return kml_region.side(rect) * focal / max(distance, 1.0)


def active(regions, eye, eye_geo, focal, box):
    """Активна ли цепочка Region: каждый задевает вид и проходит Lod.
    Возвращает размер последнего Region на экране или None. Цепочка без
    Region активна всегда, размер - бесконечность."""
    size = math.inf
    for rect in regions:
        if rect is None:
            continue
        if not overlaps(rect, box):
            return None
        size = pixels(rect, eye, eye_geo, focal)
        if size < rect.min_lod:
            return None
        if rect.max_lod >= 0 and size > rect.max_lod:
            return None
    return size


def collect(folder, regions, depth, url):
    """Тайлы и ссылки документа folder (core.kml.KFolder после
    netlink.resolve_tree). regions - цепочка Region над документом."""
    tiles, links = [], []
    chain = tuple(regions) + ((folder.region,) if folder.region else ())

    def walk(node, chain):
        for child in node.children:
            if isinstance(child, KFolder):
                sub = chain + ((child.region,) if child.region else ())
                if child.link:
                    if depth + 1 <= MAX_DEPTH and child.visible:
                        links.append(Node(child.link, sub, depth + 1))
                elif child.visible:
                    walk(child, sub)
            elif isinstance(child, KOverlay) and child.kind == "ground" \
                    and child.visible and child.overlay.corners:
                own = chain + ((child.region,) if child.region else ())
                tiles.append(Tile(
                    "{}#{}".format(url, len(tiles)),
                    child.href, child.image, tuple(child.overlay.corners),
                    child.overlay.order, tuple(child.overlay.color), own))
    walk(folder, chain)
    return tiles, links


class Tree:
    """Дерево суперналожения от одной ссылки «Моих меток»."""

    def __init__(self, url, regions=()):
        self.root = Node(url, regions, 0)

    def nodes(self):
        stack = [self.root]
        while stack:
            node = stack.pop()
            yield node
            stack.extend(node.children)

    def loaded(self, node, folder):
        """Пришёл документ ссылки node: core.kml.KFolder или None при
        ошибке."""
        if folder is None:
            node.state = "failed"
            return
        node.tiles, node.children = collect(folder, node.regions,
                                            node.depth, node.url)
        node.state = "ready"

    def step(self, eye, eye_geo, focal, box, now):
        """Шаг по виду: (ссылки, которые пора загрузить, крупные первыми;
        видимые тайлы, нижние первыми, парами (тайл, закрытие)). eye -
        глаз ECEF, eye_geo - широта и долгота под ним, focal - фокусное
        расстояние окна в пикселях, box - рамка вида core.sync.view_box.

        Закрытие - ключи тайлов детей, которые закрывают тайл на виде,
        или None. Тайл закрыт, когда каждый ребёнок его документа либо
        загружен и активен, либо лежит вне вида: под детьми его не
        видно, окно не рисует его, когда пришли картинки всех детей.
        Иначе под подробными тайлами лежали бы все грубые предки."""
        wanted, shown = [], []
        sizes = {}
        stack = [self.root]
        while stack:
            node = stack.pop()
            size = active(node.regions, eye, eye_geo, focal, box)
            sizes[id(node)] = size
            if size is None:
                continue
            node.used = now
            node.size = size
            if node.state == "new":
                wanted.append(node)
                continue
            if node.state != "ready":
                continue
            stack.extend(node.children)
        for node in self.nodes():
            if sizes.get(id(node)) is None or node.state != "ready":
                continue
            cover = self._cover(node, sizes, box)
            for tile in node.tiles:
                if active(tile.regions, eye, eye_geo, focal, box) \
                        is not None:
                    shown.append((node.depth, tile, cover))
        wanted.sort(key=lambda n: (n.depth, -n.size))
        # Подробные тайлы рисуются поверх грубых: порядок - drawOrder,
        # при равном - глубина ссылки.
        shown.sort(key=lambda item: (item[1].order, item[0]))
        tiles = [(tile, cover) for _, tile, cover in shown]
        if len(tiles) > MAX_SHOWN:
            tiles = tiles[-MAX_SHOWN:]
        return wanted, tiles

    @staticmethod
    def _cover(node, sizes, box):
        """Ключи тайлов детей, закрывающих документ node на виде, или
        None."""
        if not node.children:
            return None
        keys = []
        for child in node.children:
            own = [r for r in child.regions[len(node.regions):]
                   if r is not None]
            if own and not overlaps(own[-1], box):
                continue
            if sizes.get(id(child)) is None or child.state != "ready" \
                    or not child.tiles:
                return None
            keys += [tile.key for tile in child.tiles]
        return tuple(keys) if keys else None

    def trim(self, now):
        """Снять документы сверх MAX_LOADED, давно неактивные первыми,
        вместе с поддеревом. Возвращает снятые узлы."""
        ready = [n for n in self.nodes()
                 if n.state == "ready" and n is not self.root]
        extra = len(ready) - MAX_LOADED
        if extra <= 0:
            return []
        dropped = []
        for node in sorted(ready, key=lambda n: n.used)[:extra]:
            if node.state != "ready" or node.used >= now:
                continue
            for sub in _subtree(node):
                dropped.append(sub)
            node.tiles, node.children = [], []
            node.state = "new"
        return dropped


def _subtree(node):
    stack = [node]
    while stack:
        item = stack.pop()
        yield item
        stack.extend(item.children)
