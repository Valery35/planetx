# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Населённые пункты из векторных тайлов для надписей на глобусе.

Точки берутся из слоя place векторных тайлов схемы OpenMapTiles,
их отдаёт OpenFreeMap. Тайл - сообщение Protocol Buffers формата
Mapbox Vector Tile 2. Здесь раскодируется только слой place, остальные
слои пропускаются по длине, не разбираясь.

Надписи стоят на экране ровно, как в Google Earth. Какие из них видны,
решает select_labels: надписи идут по важности, каждая следующая
ставится, только если не задевает уже поставленные.

Модуль Qt не знает.
"""
import gzip
import math
import re
import struct
import zlib
from collections import namedtuple

LAYER = "place"
EXTENT = 4096  # размер тайла в единицах слоя по умолчанию
MAX_LEVEL = 14  # последний уровень векторных тайлов OpenFreeMap
# Уровень тайла надписей на столько грубее тайла подложки. Тайл схемы
# OpenMapTiles рассчитан на 512 пикселей, тайл подложки - 256. Ещё
# уровень снимает три четверти запросов, а тайл уровня z - 2 несёт
# пункты, которые помещаются на карте этого масштаба.
LEVEL_OFFSET = 2

# Классы пунктов по порядку важности. Внутри класса важнее меньший rank.
# Столица страны идёт перед другими городами. Кроме населённых пунктов
# подписываются воды, заповедники, вершины, аэропорты и номера дорог.
# Класс «search» - временная метка найденного места, она важнее всех.
# Класс «mark» - точечный объект глобуса, свой или из «Моих меток».
# Класс «ruler» - длина отрезка линейки у его середины.
# Класс «layer» - подпись слоя проекта. Классы «circle» и «grid» -
# подписи экватора, тропиков, полярных кругов и линий координатной
# сетки. Класс «plate» - название литосферной плиты, core/plates.py.
# Класс «value» - число поля прогноза погоды, core/weather.py.
# Класс «wiki» - статья Википедии рядом, core/wikipedia.py, после
# пунктов основы: статья подписывается там, где остаётся место.
# Класс «suburb» - район города, «river» - река или канал подписью
# вдоль русла, как у Google Earth, решение автора от 4 ноября 2026 года.
# Класса у каждого стиля render/labels.py требует test_label_kinds.
CLASSES = ("search", "mark", "ruler", "layer", "circle", "grid", "plate",
           "value",
           "country",
           "capital",
           "city", "state",
           "water", "town", "river", "suburb", "park", "peak", "airport",
           "road_ref", "village", "wiki")
KIND = {name: index for index, name in enumerate(CLASSES)}
PLACE_CLASSES = {"country", "capital", "city", "state", "town", "village",
                 "suburb"}

# Подписи основы издалека мельче. Замечание автора от 7 ноября 2026
# года - «подписи на экране слишком крупные на удалении», прежде кегль
# не зависел от высоты. До LABEL_NEAR метров высоты глаза кегль полный,
# к LABEL_FAR уменьшается до доли LABEL_SMALLEST по логарифму высоты,
# ступенями LABEL_STEP - на каждой ступени надписи растрируются заново.
# Свои метки, линейка, подписи слоёв, сетки и погоды не уменьшаются.
# Величины - выбор помощника, утверждает автор.
LABEL_NEAR = 300e3
LABEL_FAR = 6000e3
LABEL_SMALLEST = 0.7
LABEL_STEP = 0.1
SHRINK = {"country", "capital", "city", "state", "water", "town",
          "river", "suburb", "park", "peak", "airport", "road_ref",
          "village", "wiki", "plate"}


def label_scale(altitude):
    """Доля кегля подписей основы при высоте глаза altitude, метры."""
    if not altitude > LABEL_NEAR:
        return 1.0
    share = min(1.0, math.log(altitude / LABEL_NEAR)
                / math.log(LABEL_FAR / LABEL_NEAR))
    value = 1.0 - (1.0 - LABEL_SMALLEST) * share
    return round(round(value / LABEL_STEP) * LABEL_STEP, 2)


# Начала слов в названии нежилого района - промзоны, кампуса, комплекса.
# Признака жилья в тайлах подписей нет, слоя landuse на их уровнях тоже,
# поэтому район без жилья узнаётся по названию. Решение автора от
# 4 ноября 2026 года - в районах только жилые. Состав - выбор помощника.
NOT_LIVING = ("промзон", "промучаст", "промплощад", "промузел",
              "промышленная зона", "комплекс", "кампус", "технопарк",
              "индустриальн", "industrial", "campus", "complex",
              "business park", "technopark")

# Слои векторного тайла с пунктами и нужные атрибуты.
LAYERS = {"place", "mountain_peak", "water_name", "park",
          "aerodrome_label", "transportation_name", "waterway"}
WANTED = {"class", "capital", "rank", "name", "ele", "ref"}
# Слои, где пункт берётся и с линии. В остальных только точки.
LINE_LAYERS = {"water_name", "transportation_name", "waterway"}
# Реки и каналы слоя waterway, ранг по классу. Ручьи не подписываются.
RIVER_RANK = {"river": 1, "canal": 2}
# Направление подписи реки - хорда между вершинами линии на столько
# вершин по обе стороны от места подписи, но не дальше края.
RIVER_SPAN = 3
# Места подписи реки - доли длины каждой линии тайла. Подпись встаёт
# на первое свободное, река одного названия подписывается в кадре один
# раз (render/labels.py). Важнее река, длиннее в кадре вся, по всем
# тайлам (PlaceStore.collect), - так Кама обходит свои притоки.
RIVER_SHARES = (0.5, 0.25, 0.75)
EARTH_KM = 40075.0
# Ранги классов, у которых в тайле ранга нет. Меньше - важнее.
WATER_RANK = {"ocean": 1, "sea": 2, "bay": 4, "strait": 4, "lake": 5}
PARK_CLASSES = {"national_park", "nature_reserve", "protected_area",
                "wildlife_refuge"}
AIRPORT_RANK = {"international": 1, "public": 2, "regional": 3,
                "military": 4}
ROAD_RANK = {"motorway": 1, "trunk": 2, "primary": 3}

# Наименьший уровень тайла пунктов, из которого класс подписывается.
# Области в тайлах уровней 0-2 есть, но из космоса их названия
# заслоняли страны, 26 сентября 2026 года. Тайл уровня 3 нужен виду
# примерно с 5000 км.
MIN_LEVEL = {"state": 3}

# Наибольшая высота глаза над эллипсоидом в метрах, до которой класс
# подписывается. Уровень тайла для этого груб: с 2500 до 4000 км
# в кадре одни и те же уровни 5 и 6. Величины назначил автор
# 27 сентября 2026 года.
MAX_HEIGHT = {"peak": 4.0e5, "airport": 1.0e6, "road_ref": 1.0e6,
              "park": 3.0e6, "suburb": 8.0e4, "river": 4.0e5,
              "village": 3.0e5}


def kinds_at(kinds, height):
    """Классы из kinds, которые подписываются с высоты height, в метрах."""
    return {kind for kind in kinds
            if height <= MAX_HEIGHT.get(kind, height)}

Place = namedtuple("Place", "id name kind rank lat lon info lift base",
                   defaults=(None, 0.0, None))
Place.__doc__ = """Подписываемый пункт: населённый пункт, область, вода,
заповедник, вершина, аэропорт или номер дороги.

id - номер объекта в тайле или 0. kind - класс из CLASSES. rank - ранг
OpenMapTiles, меньше - важнее, без ранга 99. lat, lon в градусах.
info - высота вершины в метрах, у реки - направление русла (широта,
долгота до, широта, долгота после) и длина реки этого названия в тайле,
км, у остальных None. lift - подъём
надписи над рельефом в метрах, у своих поднятых меток. base - от чего
отсчитан подъём своей метки: None - поверхность, "floor" - рельеф
с дном моря, "abs" - уровень моря (подъём уже с масштабом рельефа).
"""


class DecodeError(ValueError):
    """Тайл не разбирается как Mapbox Vector Tile."""


def _varint(data, pos):
    result = 0
    shift = 0
    while True:
        if pos >= len(data):
            raise DecodeError("varint")
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7


def _fields(data):
    """Поля сообщения: номер, тип, значение.

    Значение - число для типов 0, 1, 5 и срез байтов для типа 2.
    """
    pos = 0
    end = len(data)
    while pos < end:
        # Ключ поля и длина значения почти всегда в один-два байта.
        # Короткий путь без вызова _varint втрое быстрее на слое
        # с тысячами значений.
        key = data[pos]
        if key < 0x80:
            pos += 1
        else:
            key, pos = _varint(data, pos)
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, pos = _varint(data, pos)
        elif wire == 2:
            if pos >= end:
                raise DecodeError("length")
            size = data[pos]
            if size < 0x80:
                pos += 1
            else:
                size, pos = _varint(data, pos)
            if pos + size > end:
                raise DecodeError("length")
            value = data[pos:pos + size]
            pos += size
        elif wire == 1:
            value = data[pos:pos + 8]
            pos += 8
        elif wire == 5:
            value = data[pos:pos + 4]
            pos += 4
        else:
            raise DecodeError("wire type {}".format(wire))
        yield number, wire, value


def _packed(data):
    """Упакованные числа varint, один проход по байтам."""
    out = []
    append = out.append
    result = 0
    shift = 0
    for byte in data:
        result |= (byte & 0x7F) << shift
        if byte & 0x80:
            shift += 7
        else:
            append(result)
            result = 0
            shift = 0
    return out


def _zigzag(value):
    return (value >> 1) ^ -(value & 1)


def _value(data):
    """Значение атрибута: строка, число или признак."""
    for number, wire, value in _fields(data):
        if number == 1:
            return bytes(value).decode("utf-8", errors="replace")
        if number in (2, 3):
            try:
                return struct.unpack("<f" if number == 2 else "<d",
                                     bytes(value))[0]
            except struct.error as error:
                raise DecodeError(str(error)) from error
        if number in (4, 5):
            return value
        if number == 6:
            return _zigzag(value)
        if number == 7:
            return bool(value)
    return None


def _points(geometry, every=False):
    """Точки геометрии в единицах слоя.

    every=False - только начала частей, это точки объекта-точки.
    every=True - все вершины, для линии.
    """
    out = []
    x = y = 0
    i = 0
    while i < len(geometry):
        command = geometry[i]
        i += 1
        kind, count = command & 7, command >> 3
        if kind == 1 or kind == 2:
            for _ in range(count):
                if i + 1 >= len(geometry):
                    return out
                x += _zigzag(geometry[i])
                y += _zigzag(geometry[i + 1])
                i += 2
                if kind == 1 or every:
                    out.append((x, y))
        elif kind != 7:
            return out
    return out


def _unpack(data):
    data = bytes(data)
    if data[:2] == b"\x1f\x8b":
        try:
            data = gzip.decompress(data)
        except (OSError, EOFError, zlib.error) as error:
            raise DecodeError(str(error)) from error
    return memoryview(data)


def decode_layers(data, names, wanted=None):
    """Объекты слоёв names за один проход по тайлу.

    Возвращает словарь «имя слоя - (объекты, extent)». Объект - четвёрка
    (номер, тип геометрии, атрибуты, точки): 1 точка, 2 линия,
    3 полигон. У точки в списке точки объекта, у линии все вершины,
    у полигона пусто. wanted - имена нужных атрибутов, None - все.
    Сжатый gzip тайл распаковывается.
    """
    out = {}
    for number, wire, layer in _fields(_unpack(data)):
        if number != 3 or wire != 2:
            continue
        # Имя слоя ищется без разбора его объектов. Слои дорог и зданий
        # в тайле уровня 4 занимают сотни килобайт.
        title = None
        for n, w, v in _fields(layer):
            if n == 1 and w == 2:
                title = bytes(v).decode("utf-8", errors="replace")
                break
        if title not in names:
            continue
        fields = list(_fields(layer))
        keys = [bytes(v).decode("utf-8", errors="replace")
                for n, w, v in fields if n == 3 and w == 2]
        # Значений в слое place тайла уровня 4 около 10 тысяч, это
        # названия стран на всех языках. Раскодируются только значения
        # нужных атрибутов, 56 мс против 3 мс на тайл.
        raw = [v for n, w, v in fields if n == 4 and w == 2]
        decoded = {}
        extent = next((v for n, w, v in fields if n == 5 and w == 0),
                      EXTENT)
        features = []
        for n, w, feature in fields:
            if n != 2 or w != 2:
                continue
            fid = 0
            tags = []
            geometry = []
            kind = 0
            for fn, fw, fv in _fields(feature):
                if fn == 1 and fw == 0:
                    fid = fv
                elif fn == 2 and fw == 2:
                    tags = _packed(fv)
                elif fn == 3 and fw == 0:
                    kind = fv
                elif fn == 4 and fw == 2:
                    geometry = _packed(fv)
            if kind not in (1, 2):
                continue
            attrs = {}
            for k, v in zip(tags[0::2], tags[1::2]):
                if k >= len(keys) or v >= len(raw):
                    continue
                name_k = keys[k]
                if wanted is not None and name_k not in wanted:
                    continue
                if v not in decoded:
                    decoded[v] = _value(raw[v])
                attrs[name_k] = decoded[v]
            features.append((fid, kind, attrs,
                             _points(geometry, every=kind == 2)))
        out[title] = (features, extent)
    return out


def decode_layer(data, name=LAYER, wanted=None):
    """Точечные объекты слоя name: список троек (номер, атрибуты, точки).

    Точки - пары в единицах слоя, extent возвращается вторым значением.
    """
    features, extent = decode_layers(data, {name}, wanted).get(
        name, ([], EXTENT))
    return [(fid, attrs, points) for fid, kind, attrs, points in features
            if kind == 1], extent


def living(*names):
    """Жилой ли район с такими названиями - ни одно слово названий
    не начинается с NOT_LIVING."""
    for name in names:
        text = " ".join(re.findall(r"\w+", str(name or "").lower()))
        words = text.split()
        for start in NOT_LIVING:
            if " " in start:
                if start in text:
                    return False
            elif any(word.startswith(start) for word in words):
                return False
    return True


def place_kind(attrs):
    """Класс пункта из CLASSES или None, если пункт не показывается."""
    kind = attrs.get("class")
    if kind == "city" and attrs.get("capital") in (2, "2"):
        return "capital"
    if kind == "province":
        return "state"
    return kind if kind in PLACE_CLASSES else None


# Языки подписей в свойствах вида, коды полей name:xx OpenMapTiles.
# Состав назначил автор 27 сентября 2026 года.
LABEL_LANGUAGES = ("ru", "en", "de", "fr", "es", "it", "pt", "pl", "uk",
                   "kk", "tr", "ar", "zh", "ja", "ko")
# Выбор в свойствах вида: язык QGIS или местные названия.
AS_QGIS = ""
LOCAL = "local"
# Языки на латинице. Без названия на выбранном языке у них ставится
# название латиницей, у остальных - местное.
LATIN_SCRIPT = {"en", "de", "fr", "es", "it", "pt", "pl", "tr"}


def name_languages(choice, ui_language):
    """Языки названий по порядку поиска для place_name.

    choice - код из LABEL_LANGUAGES, AS_QGIS или LOCAL. ui_language -
    код языка интерфейса QGIS. Язык QGIS не из списка даёт английский.
    Пустой набор - местные названия.
    """
    if choice == LOCAL:
        return ()
    code = choice or ui_language
    if code not in LABEL_LANGUAGES:
        code = "en"
    return (code, "latin") if code in LATIN_SCRIPT else (code,)


def place_name(attrs, languages):
    """Название на первом найденном языке из languages или основное."""
    for language in languages:
        for field in ("name:" + language, "name_" + language):
            value = attrs.get(field)
            if value:
                return str(value)
    value = attrs.get("name")
    return str(value) if value else None


def tile_point(z, x, y, px, py, extent):
    """Широта и долгота точки тайла в единицах слоя."""
    n = 1 << z
    u = (x + px / extent) / n
    v = (y + py / extent) / n
    lon = u * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * v))))
    return lat, lon


def _rank(attrs, default=99):
    rank = attrs.get("rank")
    return int(rank) if isinstance(rank, (int, float)) else default


def _read_place(layer, attrs, languages):
    """Класс, название, ранг и сведения пункта из объекта слоя.

    None - объект не подписывается.
    """
    if layer == "place":
        kind = place_kind(attrs)
        name = place_name(attrs, languages)
        if kind == "suburb" and not living(name, attrs.get("name")):
            return None
        return kind and (kind, name, _rank(attrs), None)
    if layer == "mountain_peak":
        ele = attrs.get("ele")
        ele = int(ele) if isinstance(ele, (int, float)) else None
        return ("peak", place_name(attrs, languages), _rank(attrs), ele)
    if layer == "water_name":
        rank = WATER_RANK.get(attrs.get("class"))
        return rank and ("water", place_name(attrs, languages), rank, None)
    if layer == "park":
        if attrs.get("class") not in PARK_CLASSES:
            return None
        return ("park", place_name(attrs, languages), _rank(attrs), None)
    if layer == "aerodrome_label":
        rank = AIRPORT_RANK.get(attrs.get("class"), 5)
        return ("airport", place_name(attrs, languages), rank, None)
    if layer == "waterway":
        rank = RIVER_RANK.get(attrs.get("class"))
        return rank and ("river", place_name(attrs, languages), rank, None)
    if layer == "transportation_name":
        ref = str(attrs.get("ref") or "").split(";")[0].strip()
        rank = ROAD_RANK.get(attrs.get("class"))
        return ref and rank and ("road_ref", ref, rank, None)
    return None


def decode_places(key, data, languages=("en",)):
    """Пункты векторного тайла key = (z, x, y), список Place.

    Точки берутся из слоёв LAYERS. У линии, например номера дороги
    или названия водохранилища, пункт стоит на средней вершине.
    """
    z, x, y = key
    wanted = set(WANTED)
    for language in languages:
        wanted |= {"name:" + language, "name_" + language}
    out = []
    rivers = {}
    for layer, (features, extent) in decode_layers(
            data, LAYERS, wanted).items():
        for fid, kind, attrs, points in features:
            if kind == 2 and layer not in LINE_LAYERS:
                continue
            found = _read_place(layer, attrs, languages)
            if not found or not found[1] or not points:
                continue
            if found[0] == "river":
                rivers.setdefault(found[1], []).append(
                    (fid, found[2], points, extent))
                continue
            px, py = points[len(points) // 2] if kind == 2 else points[0]
            # Точки в полосе за краем тайла повторяют соседей.
            if not (0 <= px < extent and 0 <= py < extent):
                continue
            lat, lon = tile_point(z, x, y, px, py, extent)
            place_class, name, rank, info = found
            out.append(Place(fid, name, place_class, rank, lat, lon, info))
    for name, lines in rivers.items():
        out += river_places(key, name, lines)
    return out


def river_places(key, name, lines):
    """Места подписи реки name в тайле key по её линиям lines - кортежам
    (номер, ранг класса, вершины, размер тайла)."""
    z, x, y = key
    km = EARTH_KM / (1 << z)
    total = sum(_length(points) / extent for _, _, points, extent in lines)
    out = []
    for fid, rank, points, extent in lines:
        for k, share in enumerate(RIVER_SHARES):
            n = _vertex_at(points, share)
            px, py = points[n]
            if not (0 <= px < extent and 0 <= py < extent):
                continue
            course = river_course(z, x, y, points, extent, n)
            if course is None:
                continue
            lat, lon = tile_point(z, x, y, px, py, extent)
            # Номер места свой у тайла, линии и доли: одна линия OSM
            # идёт через соседние тайлы, места каждого нужны.
            ident = hash((z, x, y, fid, k)) & 0x7fffffff or 1
            out.append(Place(ident, name, "river", rank, lat, lon,
                             course + (total * km,)))
    return out


def _length(points):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1])
               for a, b in zip(points, points[1:]))


def _vertex_at(points, share):
    """Номер вершины линии на доле share её длины."""
    goal = share * _length(points)
    run = 0.0
    for n, (a, b) in enumerate(zip(points, points[1:])):
        run += math.hypot(b[0] - a[0], b[1] - a[1])
        if run >= goal:
            return n + 1 if run - goal < goal - run + math.hypot(
                b[0] - a[0], b[1] - a[1]) else n
    return len(points) // 2


def river_course(z, x, y, points, extent, middle=None):
    """Направление русла у вершины middle линии (по умолчанию средней):
    (широта, долгота до, широта, долгота после) или None, если линия -
    точка."""
    if middle is None:
        middle = len(points) // 2
    a = points[max(0, middle - RIVER_SPAN)]
    b = points[min(len(points) - 1, middle + RIVER_SPAN)]
    if a == b:
        return None
    return tile_point(z, x, y, a[0], a[1], extent) \
        + tile_point(z, x, y, b[0], b[1], extent)


def river_rank(place, total):
    """Пункт реки с рангом по длине total, км, всей реки в кадре: ранг
    класса впереди, длиннее - важнее."""
    return place._replace(
        rank=place.rank * 100000 + 99999 - min(99999, int(total)))


def label_level(z, max_level=MAX_LEVEL):
    """Уровень тайла надписей для тайла подложки уровня z."""
    return max(0, min(z - LEVEL_OFFSET, max_level))


def importance(place):
    """Ключ сортировки: сначала важные."""
    return (KIND[place.kind], place.rank, place.name)


def identity(place):
    """Один и тот же пункт в тайлах разных уровней.

    Номер объекта в OpenMapTiles - номер точки OSM, он один на всех
    уровнях. Координаты на грубых уровнях округлены сеткой тайла.
    """
    return (place.id, place.name) if place.id else (0, place.name)


class PlaceStore:
    """Загруженные тайлы пунктов и пункты для кадра."""

    def __init__(self, max_level=MAX_LEVEL):
        self.max_level = max_level
        self.tiles = {}
        self._collected = (None, [])

    def add(self, key, places):
        self.tiles[key] = list(places)

    def wanted(self, draw):
        """Ключи тайлов пунктов для тайлов подложки draw."""
        return {self._key(key) for key in draw}

    def _key(self, key):
        z, x, y = key
        level = label_level(z, self.max_level)
        shift = z - level
        return (level, x >> shift, y >> shift)

    def source(self, key):
        """Готовый тайл пунктов для тайла подложки key или его предок."""
        z, x, y = self._key(key)
        while z >= 0:
            if (z, x, y) in self.tiles:
                return (z, x, y)
            z, x, y = z - 1, x >> 1, y >> 1
        return None

    def collect(self, draw, kinds=None):
        """Пункты для тайлов draw по порядку важности, без повторов.

        kinds - нужные классы из CLASSES, None - все. Из тайлов разных
        уровней пункт берётся из самого точного. Список помнится, пока
        набор тайлов пунктов и классы те же.
        """
        sources = {self.source(key) for key in draw}
        sources.discard(None)
        memo = (frozenset(sources), None if kinds is None
                else frozenset(kinds))
        if memo == self._collected[0]:
            return self._collected[1]
        seen = {}
        totals = {}
        for key in sorted(memo[0], reverse=True):
            counted = set()
            for place in self.tiles[key]:
                if key[0] < MIN_LEVEL.get(place.kind, 0):
                    continue
                if kinds is not None and place.kind not in kinds:
                    continue
                if place.kind == "river" and place.name not in counted:
                    counted.add(place.name)
                    totals[place.name] = \
                        totals.get(place.name, 0.0) + place.info[4]
                seen.setdefault(identity(place), place)
        out = sorted((river_rank(p, totals[p.name]) if p.kind == "river"
                      else p for p in seen.values()), key=importance)
        self._collected = (memo, out)
        return out

    def trim(self, keep, limit=2000):
        """Забыть тайлы вне keep, если их больше limit."""
        if len(self.tiles) > limit:
            self.tiles = {k: v for k, v in self.tiles.items() if k in keep}
            self._collected = (None, [])


def select_labels(boxes, tiers, previous=(), cell=64.0):
    """Надписи без наложений, жадно по порядку boxes.

    boxes - прямоугольники (x0, y0, x1, y1) в пикселях, уже по порядку
    важности. tiers - класс каждой надписи, номер из KIND. previous -
    номера надписей, видных в прошлом кадре. Внутри класса они ставятся
    первыми. Так надпись не мигает, когда соседняя того же класса
    сдвигается на пиксель. Возвращает номера поставленных надписей
    в порядке постановки.

    Проверка идёт по сетке ячеек cell пикселей, каждая надпись
    сравнивается только с надписями своих ячеек.
    """
    previous = set(previous)
    order = sorted(range(len(boxes)),
                   key=lambda i: (tiers[i], i not in previous, i))
    grid = {}
    placed = []
    for i in order:
        x0, y0, x1, y1 = boxes[i]
        cells = [(cx, cy)
                 for cx in range(int(x0 // cell), int(x1 // cell) + 1)
                 for cy in range(int(y0 // cell), int(y1 // cell) + 1)]
        clash = False
        for c in cells:
            for j in grid.get(c, ()):
                a0, b0, a1, b1 = boxes[j]
                if x0 < a1 and a0 < x1 and y0 < b1 and b0 < y1:
                    clash = True
                    break
            if clash:
                break
        if clash:
            continue
        placed.append(i)
        for c in cells:
            grid.setdefault(c, []).append(i)
    return placed
