# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Поезда Финляндии вживую по данным Digitraffic. Просьба автора от
18 октября 2026 года - «начинай с модели по треку и финских поездов».

Расчёт без Qt. Положения поездов - открытый ответ Digitraffic
(Fintraffic) train-locations/latest, точка GPS, время и скорость
каждого поезда, раз в 10 с. Вид и категория поезда - запрос GraphQL
currentlyRunningTrains. Условия - CC BY 4.0, заголовок
Digitraffic-User без личных данных, сжатие обязательно (Qt просит
gzip сам), сверено 18 октября 2026 года.

Между обновлениями поезд едет со своей скоростью по своему курсу не
дольше EXTRAPOLATE_MAX секунд. Вблизи точка GPS притягивается к рельсам
OSM из векторной основы (Rails), и поезд едет по линии рельсов, через
стрелки - в ту ветку, что ближе по направлению. Пришло новое положение -
поезд переходит к нему за BLEND секунд, без скачка.

Модель - условный состав в цвет категории: вагонов по категории
(CARS), каждый вагон стоит на рельсах на своём отступе назад от головы
(Fleet.place, back), на кривой состав изгибается по пути. Длина вагона
вдоль оси Y модели (train_parts), поэтому азимут модели - курс.
"""
import calendar
import math
import time

import numpy as np

try:  # внутри плагина QGIS
    from . import ellipsoid
    from .models import Part
    from .routing import to_grid, to_latlon, unit_metres
    from .tour import bearing
except ImportError:  # headless-тесты
    import ellipsoid
    from models import Part
    from routing import to_grid, to_latlon, unit_metres
    from tour import bearing

LATEST_URL = "https://rata.digitraffic.fi/api/v1/train-locations/latest/"
GRAPHQL_URL = "https://rata.digitraffic.fi/api/v2/graphql/graphql"
# Вид одного поезда. Прибывшие поезда служба снимает с «в пути»
# (runningCurrently), GraphQL их не отдаёт, а положения GPS ещё идут -
# 18 октября 2026 года вечером 21 поезд из 125.
TRAIN_URL = "https://rata.digitraffic.fi/api/v1/trains/{date}/{number}"
TYPES_EACH = 8  # поездов без вида спрашивается за опрос, не больше
TYPES_QUERY = ("{ currentlyRunningTrains { trainNumber departureDate "
               "commuterLineid trainType { name trainCategory { name } } "
               "operator { shortCode } } }")
# Digitraffic-User - программа, без личных данных, условие Digitraffic.
USER = "PlanetX"
ATTRIBUTION = ("Trains: Fintraffic / digitraffic.fi, CC BY 4.0",
               "https://www.digitraffic.fi/en/railway-traffic/")
PAGE = "https://www.digitraffic.fi/en/railway-traffic/"
POLL = 10.0  # с между запросами положений, с таким шагом их обновляет служба
TYPES_POLL = 300.0  # с между запросами видов поездов
# Ход по своей скорости после последнего положения - не дольше, с.
EXTRAPOLATE_MAX = 30.0
BLEND = 2.0  # с перехода к новому положению
MOVED = 3.0  # м, сдвиг между положениями, по которому берётся курс
# Точка GPS притягивается к рельсам не дальше, м.
SNAP_REACH = 40.0
# Ветка за стрелкой годится, если её направление отличается от хода
# не больше чем на это значение косинуса (около 60°).
BRANCH_COS = 0.5
# Положение старше этого времени - поезд не показывается, с.
STALE = 600.0
# Цвета категорий 0-1 и порядок шкалы - выбор помощника.
CATEGORIES = (("Long-distance", (0.82, 0.18, 0.18)),
              ("Commuter", (0.56, 0.24, 0.70)),
              ("Cargo", (0.20, 0.45, 0.78)),
              ("Locomotive", (0.96, 0.62, 0.12)),
              ("Shunting", (0.55, 0.55, 0.55)),
              ("On-track machines", (0.95, 0.85, 0.20)))
OTHER = (0.85, 0.85, 0.85)
DARK = (0.16, 0.17, 0.19)
GLASS = (0.10, 0.14, 0.20)
# Условный вагон, метры: длина, ширина, высота. Выбор помощника.
CAR_LENGTH = 25.0
CAR_WIDTH = 3.2
CAR_HEIGHT = 4.2
CAR_STEP = 26.0  # м между началами соседних вагонов
# Вагонов в составе по категории. Настоящий состав служба даёт
# отдельным запросом, здесь - типичная длина. Выбор помощника.
CARS = {"Long-distance": 6, "Commuter": 4, "Cargo": 12, "Locomotive": 1,
        "Shunting": 1, "On-track machines": 1}
CARS_OTHER = 3


def cars(category):
    """Вагонов в составе категории."""
    return CARS.get(category, CARS_OTHER)


def category_color(category):
    """Цвет категории 0-1, неизвестной - OTHER."""
    for name, color in CATEGORIES:
        if name == category:
            return color
    return OTHER


def epoch(text):
    """Время ISO 8601 вида 2026-10-18T17:31:33.000Z в секунды UTC от
    1970 года или None."""
    if not isinstance(text, str) or len(text) < 19:
        return None
    try:
        parts = time.strptime(text[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None
    seconds = float(calendar.timegm(parts))
    rest = text[19:]
    if rest.startswith("."):
        digits = ""
        for ch in rest[1:]:
            if not ch.isdigit():
                break
            digits += ch
        if digits:
            seconds += float("0." + digits)
    return seconds


class Sample:
    """Положение поезда: ключ (номер, дата отправления), время, точка,
    скорость в м/с."""

    def __init__(self, key, t, lat, lon, speed):
        self.key = key
        self.t = t
        self.lat = lat
        self.lon = lon
        self.speed = speed


def parse_latest(data):
    """Положения из ответа train-locations/latest: список Sample.
    Записи без точки или времени пропускаются."""
    out = []
    for item in data if isinstance(data, list) else ():
        if not isinstance(item, dict):
            continue
        location = item.get("location") or {}
        coords = location.get("coordinates") if isinstance(location,
                                                            dict) else None
        t = epoch(item.get("timestamp"))
        number = item.get("trainNumber")
        if not coords or len(coords) < 2 or t is None or number is None:
            continue
        lon, lat = _number(coords[0]), _number(coords[1])
        speed = _number(item.get("speed") or 0.0)
        if lat is None or lon is None or speed is None \
                or not (-90.0 <= lat <= 90.0) or not math.isfinite(lon):
            continue
        out.append(Sample((int(number), str(item.get("departureDate", ""))),
                          t, lat, lon, max(speed / 3.6, 0.0)))
    return out


def _number(value):
    """Число из значения ответа или None."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class Info:
    """Сведения о поезде: вид (IC, S, HL…), категория, линия пригородного
    поезда, оператор."""

    def __init__(self, kind="", category="", line="", operator=""):
        self.kind = kind
        self.category = category
        self.line = line
        self.operator = operator


def parse_types(data):
    """{ключ: Info} из ответа GraphQL currentlyRunningTrains."""
    out = {}
    trains = ((data or {}).get("data") or {}).get("currentlyRunningTrains")
    for item in trains if isinstance(trains, list) else ():
        if not isinstance(item, dict) or item.get("trainNumber") is None:
            continue
        kind = item.get("trainType") or {}
        category = (kind.get("trainCategory") or {}).get("name") or ""
        operator = (item.get("operator") or {}).get("shortCode") or ""
        key = (int(item["trainNumber"]), str(item.get("departureDate", "")))
        out[key] = Info(kind.get("name") or "", category,
                        item.get("commuterLineid") or "", operator)
    return out


def train_url(key):
    """Адрес сведений одного поезда."""
    return TRAIN_URL.format(date=key[1], number=key[0])


def parse_train(data):
    """{ключ: Info} из ответа trains/{дата}/{номер}."""
    out = {}
    for item in data if isinstance(data, list) else ():
        if not isinstance(item, dict) or item.get("trainNumber") is None:
            continue
        key = (int(item["trainNumber"]), str(item.get("departureDate", "")))
        out[key] = Info(item.get("trainType") or "",
                        item.get("trainCategory") or "",
                        item.get("commuterLineID") or "",
                        item.get("operatorShortCode") or "")
    return out


def label(key, info):
    """Подпись поезда: «IC 9», у пригородного «R 9123»."""
    number = key[0]
    if info is not None and info.line:
        return "{} {}".format(info.line, number)
    if info is not None and info.kind:
        return "{} {}".format(info.kind, number)
    return str(number)


def destination(lat, lon, heading, metres):
    """Точка на шаре на расстоянии metres по азимуту heading, градусы."""
    radius = ellipsoid.A
    d = metres / radius
    p1, l1, h = math.radians(lat), math.radians(lon), math.radians(heading)
    p2 = math.asin(math.sin(p1) * math.cos(d)
                   + math.cos(p1) * math.sin(d) * math.cos(h))
    l2 = l1 + math.atan2(math.sin(h) * math.sin(d) * math.cos(p1),
                         math.cos(d) - math.sin(p1) * math.sin(p2))
    return math.degrees(p2), (math.degrees(l2) + 540.0) % 360.0 - 180.0


def _metres(lat1, lon1, lat2, lon2):
    """Расстояние по шару среднего радиуса, метры."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    a = math.sin((p2 - p1) / 2) ** 2 \
        + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2.0 * ellipsoid.A * math.asin(min(1.0, math.sqrt(a)))


# Рельсы.

class RailPos:
    """Место на рельсах: линия, расстояние от её начала в единицах
    сетки, направление хода по линии ±1."""

    def __init__(self, line, s, direction):
        self.line = line
        self.s = s
        self.direction = direction


class Rails:
    """Линии рельсов в единицах мировой сетки core.routing.

    lines - массивы вершин (n, 2). Стрелки - общие вершины линий:
    у соседних тайлов уровня 14 вершины совпадают точно.
    """

    def __init__(self, lines):
        self.lines = [np.asarray(points, dtype=np.float64)
                      for points in lines if len(points) >= 2]
        self.lengths = []
        starts, ends, owners = [], [], []
        self.vertices = {}
        for n, points in enumerate(self.lines):
            steps = np.hypot(*np.diff(points, axis=0).T)
            self.lengths.append(np.concatenate([[0.0], np.cumsum(steps)]))
            starts.append(points[:-1])
            ends.append(points[1:])
            owners.append(np.stack([np.full(len(steps), n),
                                    np.arange(len(steps))], axis=1))
            for k, (x, y) in enumerate(points):
                self.vertices.setdefault((round(x), round(y)), []).append(
                    (n, k))
        if self.lines:
            self.a = np.concatenate(starts)
            self.b = np.concatenate(ends)
            self.owner = np.concatenate(owners)
        else:
            self.a = self.b = np.zeros((0, 2))
            self.owner = np.zeros((0, 2), dtype=np.int64)

    def __len__(self):
        return len(self.lines)

    def snap(self, x, y, reach):
        """Ближайшее место на рельсах к точке сетки (x, y) не дальше
        reach единиц: (номер линии, s) или None."""
        if not len(self.a):
            return None
        p = np.array([x, y], dtype=np.float64)
        ab = self.b - self.a
        length2 = np.maximum((ab * ab).sum(axis=1), 1e-12)
        t = np.clip(((p - self.a) * ab).sum(axis=1) / length2, 0.0, 1.0)
        near = self.a + t[:, None] * ab
        gap = np.hypot(*(near - p).T)
        i = int(np.argmin(gap))
        if gap[i] > reach:
            return None
        line, seg = (int(v) for v in self.owner[i])
        lengths = self.lengths[line]
        s = lengths[seg] + t[i] * (lengths[seg + 1] - lengths[seg])
        return line, float(s)

    def point(self, line, s):
        """Точка сетки и единичная касательная по ходу линии в месте s."""
        points, lengths = self.lines[line], self.lengths[line]
        s = min(max(s, 0.0), lengths[-1])
        k = int(np.searchsorted(lengths, s, side="right")) - 1
        k = min(max(k, 0), len(points) - 2)
        span = lengths[k + 1] - lengths[k]
        f = (s - lengths[k]) / span if span > 0 else 0.0
        a, b = points[k], points[k + 1]
        tangent = b - a
        norm = math.hypot(*tangent)
        tangent = tangent / norm if norm > 0 else np.array([0.0, -1.0])
        return a + f * (b - a), tangent

    def walk(self, pos, units):
        """Новое RailPos после units единиц сетки хода от pos. В конце
        линии ход идёт на линию с общей вершиной, направление которой
        ближе к ходу. Нет такой - поезд стоит в конце."""
        line, s, direction = pos.line, pos.s, pos.direction
        left = max(units, 0.0)
        for _ in range(32):
            length = self.lengths[line][-1]
            target = s + direction * left
            if 0.0 <= target <= length:
                return RailPos(line, target, direction)
            end = length if direction > 0 else 0.0
            left -= abs(end - s)
            _, tangent = self.point(line, end)
            heading = tangent * direction
            nxt = self._branch(line, end, heading)
            if nxt is None:
                return RailPos(line, end, direction)
            line, s, direction = nxt
        return RailPos(line, s, direction)

    def move(self, pos, units):
        """walk с ходом обоих знаков: меньше нуля - назад от pos, по
        направлению pos."""
        if units >= 0.0:
            return self.walk(pos, units)
        back = self.walk(RailPos(pos.line, pos.s, -pos.direction), -units)
        return RailPos(back.line, back.s, -back.direction)

    def _branch(self, line, s, heading):
        """Продолжение хода в конце линии: (линия, s, направление) или
        None."""
        x, y = self.point(line, s)[0]
        best, best_cos = None, BRANCH_COS
        for other, k in self.vertices.get((round(x), round(y)), ()):
            if other == line:
                continue
            points = self.lines[other]
            s_other = self.lengths[other][k]
            for direction, neighbour in ((1, k + 1), (-1, k - 1)):
                if not 0 <= neighbour < len(points):
                    continue
                step = points[neighbour] - points[k]
                norm = math.hypot(*step)
                if norm <= 0:
                    continue
                cos = float(step @ heading) / norm
                if cos > best_cos:
                    best, best_cos = (other, s_other, direction), cos
        return best


def grid_heading(tangent):
    """Азимут по касательной в единицах сетки: x - восток, y - юг."""
    return math.degrees(math.atan2(tangent[0], -tangent[1])) % 360.0


# Поезда.

class Train:
    """Поезд: последнее положение, курс, место на рельсах и переход."""

    def __init__(self, sample):
        self.key = sample.key
        self.sample = sample
        self.heading = math.nan
        self.rail = None  # RailPos последнего положения или None
        self.rail_version = None
        self.blend_from = None  # (широта, долгота, азимут) или None
        self.blend_at = 0.0

    def update(self, sample, shown, now):
        """Новое положение. shown - (широта, долгота, азимут) на экране
        в момент прихода, от него идёт переход."""
        if sample.t <= self.sample.t:
            return
        gap = _metres(self.sample.lat, self.sample.lon, sample.lat,
                      sample.lon)
        if gap >= MOVED:
            self.heading = bearing(self.sample.lat, self.sample.lon,
                                   sample.lat, sample.lon)
        self.sample = sample
        self.rail = None
        self.rail_version = None
        self.blend_from = shown
        self.blend_at = now


class Fleet:
    """Поезда на глобусе: положения, рельсы, точка и курс на момент."""

    def __init__(self):
        self.trains = {}
        self.info = {}
        self.rails = None
        self.rails_version = 0

    def set_rails(self, rails):
        """Рельсы у вида или None."""
        self.rails = rails if rails is not None and len(rails) else None
        self.rails_version += 1

    def update(self, samples, now, clock=None):
        """Новые положения из ответа службы. now - time.monotonic для
        перехода, clock - секунды UTC для хода по скорости. Поездов,
        которых нет в ответе или чьё положение старше STALE, нет."""
        clock = time.time() if clock is None else clock
        seen = set()
        for sample in samples:
            if clock - sample.t > STALE:
                continue
            seen.add(sample.key)
            train = self.trains.get(sample.key)
            if train is None:
                self.trains[sample.key] = Train(sample)
                continue
            shown = self.place(train, now, clock)
            train.update(sample, shown, now)
        for key in list(self.trains):
            if key not in seen:
                del self.trains[key]

    def _rail(self, train):
        """Место последнего положения на рельсах или None."""
        if self.rails is None:
            return None
        if train.rail_version == self.rails_version:
            return train.rail
        train.rail_version = self.rails_version
        train.rail = None
        sample = train.sample
        x, y = to_grid(sample.lat, sample.lon)
        found = self.rails.snap(x, y,
                                SNAP_REACH / unit_metres(sample.lat))
        if found is None:
            return None
        line, s = found
        _, tangent = self.rails.point(line, s)
        direction = 1
        if train.heading == train.heading:
            along = grid_heading(tangent)
            turn = (train.heading - along + 180.0) % 360.0 - 180.0
            direction = 1 if abs(turn) <= 90.0 else -1
        train.rail = RailPos(line, s, direction)
        return train.rail

    def _ahead(self, train, clock, back=0.0):
        """Точка и азимут на back метров позади головы без перехода."""
        sample = train.sample
        elapsed = min(max(clock - sample.t, 0.0), EXTRAPOLATE_MAX)
        moving = train.heading == train.heading
        metres = (sample.speed * elapsed if moving else 0.0) - back
        rail = self._rail(train)
        if rail is not None:
            pos = self.rails.move(rail, metres / unit_metres(sample.lat))
            xy, tangent = self.rails.point(pos.line, pos.s)
            lat, lon = to_latlon(xy)
            return (float(lat), float(lon),
                    grid_heading(tangent * pos.direction))
        heading = train.heading if moving else 0.0
        if metres != 0.0:
            lat, lon = destination(sample.lat, sample.lon, heading, metres)
            return lat, lon, train.heading
        return sample.lat, sample.lon, train.heading

    def place(self, train, now, clock, back=0.0):
        """(широта, долгота, азимут) на экране точки поезда back метров
        позади головы - вагона состава."""
        here = self._ahead(train, clock, back)
        if train.blend_from is not None:
            k = (now - train.blend_at) / BLEND
            if k >= 1.0:
                train.blend_from = None
            else:
                k = max(k, 0.0)
                head = here if back == 0.0 else self._ahead(train, clock)
                # Весь состав сдвинут на остаток пути головы от прежнего
                # места на экране.
                moved = _blend(train.blend_from, head, k)
                here = (here[0] + moved[0] - head[0],
                        here[1] + (moved[1] - head[1] + 180.0) % 360.0
                        - 180.0, moved[2] if back == 0.0 else here[2])
        return here

    def positions(self, now, clock=None):
        """[(ключ, широта, долгота, азимут)] на момент. Азимут NaN -
        курс ещё неизвестен."""
        clock = time.time() if clock is None else clock
        out = []
        for key, train in self.trains.items():
            lat, lon, heading = self.place(train, now, clock)
            out.append((key, lat, lon, heading))
        return out


def _blend(a, b, k):
    """Точка и азимут между a и b по доле k."""
    lat = a[0] + k * (b[0] - a[0])
    dlon = (b[1] - a[1] + 180.0) % 360.0 - 180.0
    lon = (a[1] + k * dlon + 180.0) % 360.0 - 180.0
    if a[2] != a[2]:
        heading = b[2]
    elif b[2] != b[2]:
        heading = a[2]
    else:
        turn = (b[2] - a[2] + 180.0) % 360.0 - 180.0
        heading = (a[2] + k * turn) % 360.0
    return lat, lon, heading


# Модель.

def _box(x0, x1, y0, y1, z0, z1):
    """Треугольники коробки подряд, гранями наружу."""
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    faces = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6),
             (1, 2, 6, 5), (3, 0, 4, 7))
    out = []
    for a, b, c, d in faces:
        out += [v[a], v[b], v[c], v[a], v[c], v[d]]
    return out


def train_parts(color, front=True):
    """Условный вагон для core.models: тележки, кузов цвета категории,
    полоса окон, у головного front - лобовое стекло. Перёд смотрит по
    оси +Y."""
    half_l, half_w = CAR_LENGTH / 2.0, CAR_WIDTH / 2.0
    under = _box(-half_w + 0.3, half_w - 0.3, -half_l + 1.0, half_l - 1.0,
                 0.0, 1.2)
    body = _box(-half_w, half_w, -half_l, half_l - 1.2, 1.2, CAR_HEIGHT)
    nose = _box(-half_w, half_w, half_l - 1.2, half_l, 1.2,
                CAR_HEIGHT - 1.2)
    band = _box(-half_w - 0.02, half_w + 0.02, -half_l + 1.5,
                half_l - 2.0, 2.5, 3.4)
    glass = _box(-half_w + 0.2, half_w - 0.2, half_l - 1.2,
                 half_l + 0.02, CAR_HEIGHT - 1.2, CAR_HEIGHT - 0.2)
    out = []
    if not front:
        body = _box(-half_w, half_w, -half_l, half_l, 1.2, CAR_HEIGHT)
        nose, glass = [], []
    for points, rgba in ((under, DARK), (body + nose, color),
                         (band + glass, GLASS)):
        positions = np.asarray(points, dtype=np.float64)
        out.append(Part(positions, None, None, None, tuple(rgba) + (1.0,)))
    return out
