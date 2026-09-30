# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Форматы координат, как в Google Earth: десятичные градусы,
градусы-минуты-секунды, UTM и MGRS. Запись и разбор строки.

Расчёт без Qt. UTM - поперечная проекция Меркатора на WGS84 рядами
Крюгера шестого порядка (C. F. F. Karney, Transverse Mercator with an
accuracy of a few nanometers, 2011), ошибка меньше миллиметра в зоне.
Зоны Норвегии и Шпицбергена - по правилам UTM. MGRS строится поверх
UTM, полярные области UPS выше 84° и ниже 80° не поддерживаются.
"""
import math
import re

try:  # внутри плагина QGIS
    from .ellipsoid import WGS84_A as A, WGS84_F as F
    from .flight import parse_latlon
except ImportError:  # headless-тесты
    from ellipsoid import WGS84_A as A, WGS84_F as F
    from flight import parse_latlon

FORMATS = ("decimal", "dms", "utm", "mgrs")
K0 = 0.9996
FALSE_EASTING = 500000.0
FALSE_NORTHING = 10000000.0  # южное полушарие
BANDS = "CDEFGHJKLMNPQRSTUVWX"  # полосы широты по 8°, X - 12°
UTM_LIMITS = (-80.0, 84.0)
COLUMNS = ("ABCDEFGH", "JKLMNPQR", "STUVWXYZ")  # 100 км по востоку
ROWS = "ABCDEFGHJKLMNPQRSTUV"  # 100 км по северу, 20 букв

_N = F / (2.0 - F)
_E = math.sqrt(F * (2.0 - F))
_AR = A / (1.0 + _N) * (1.0 + _N ** 2 / 4.0 + _N ** 4 / 64.0
                        + _N ** 6 / 256.0)


def _series(n):
    """Коэффициенты рядов Крюгера: alpha - вперёд, beta - обратно."""
    n2, n3, n4, n5, n6 = n ** 2, n ** 3, n ** 4, n ** 5, n ** 6
    alpha = (
        n / 2 - 2 * n2 / 3 + 5 * n3 / 16 + 41 * n4 / 180
        - 127 * n5 / 288 + 7891 * n6 / 37800,
        13 * n2 / 48 - 3 * n3 / 5 + 557 * n4 / 1440 + 281 * n5 / 630
        - 1983433 * n6 / 1935360,
        61 * n3 / 240 - 103 * n4 / 140 + 15061 * n5 / 26880
        + 167603 * n6 / 181440,
        49561 * n4 / 161280 - 179 * n5 / 168 + 6601661 * n6 / 7257600,
        34729 * n5 / 80640 - 3418889 * n6 / 1995840,
        212378941 * n6 / 319334400)
    beta = (
        n / 2 - 2 * n2 / 3 + 37 * n3 / 96 - n4 / 360 - 81 * n5 / 512
        + 96199 * n6 / 604800,
        n2 / 48 + n3 / 15 - 437 * n4 / 1440 + 46 * n5 / 105
        - 1118711 * n6 / 3870720,
        17 * n3 / 480 - 37 * n4 / 840 - 209 * n5 / 4480
        + 5569 * n6 / 90720,
        4397 * n4 / 161280 - 11 * n5 / 504 - 830251 * n6 / 7257600,
        4583 * n5 / 161280 - 108847 * n6 / 3991680,
        20648693 * n6 / 638668800)
    return alpha, beta


_ALPHA, _BETA = _series(_N)


def utm_zone(lat, lon):
    """Номер зоны UTM с исключениями Норвегии и Шпицбергена."""
    lon = (lon + 180.0) % 360.0 - 180.0
    zone = int((lon + 180.0) // 6.0) + 1
    zone = min(zone, 60)
    if 56.0 <= lat < 64.0 and 3.0 <= lon < 12.0:
        return 32
    if 72.0 <= lat <= 84.0 and 0.0 <= lon < 42.0:
        if lon < 9.0:
            return 31
        if lon < 21.0:
            return 33
        if lon < 33.0:
            return 35
        return 37
    return zone


def band(lat):
    """Буква полосы широты или None вне UTM."""
    if not UTM_LIMITS[0] <= lat <= UTM_LIMITS[1]:
        return None
    return BANDS[min(int((lat + 80.0) // 8.0), len(BANDS) - 1)]


def _tau_prime(tau):
    sigma = math.sinh(_E * math.atanh(_E * tau / math.hypot(1.0, tau)))
    return tau * math.hypot(1.0, sigma) - sigma * math.hypot(1.0, tau)


def to_utm(lat, lon, zone=None):
    """(зона, полоса, восток, север) в метрах или None вне UTM."""
    letter = band(lat)
    if letter is None:
        return None
    zone = zone or utm_zone(lat, lon)
    central = (zone - 1) * 6.0 - 180.0 + 3.0
    dlon = math.radians((lon - central + 180.0) % 360.0 - 180.0)
    tau = math.tan(math.radians(lat))
    tp = _tau_prime(tau)
    xi_p = math.atan2(tp, math.cos(dlon))
    eta_p = math.asinh(math.sin(dlon) / math.hypot(tp, math.cos(dlon)))
    xi, eta = xi_p, eta_p
    for j, a in enumerate(_ALPHA, start=1):
        xi += a * math.sin(2 * j * xi_p) * math.cosh(2 * j * eta_p)
        eta += a * math.cos(2 * j * xi_p) * math.sinh(2 * j * eta_p)
    easting = FALSE_EASTING + K0 * _AR * eta
    northing = K0 * _AR * xi
    if lat < 0.0:
        northing += FALSE_NORTHING
    return zone, letter, easting, northing


def from_utm(zone, south, easting, northing):
    """Широта и долгота из UTM. south - южное полушарие."""
    xi = (northing - (FALSE_NORTHING if south else 0.0)) / (K0 * _AR)
    eta = (easting - FALSE_EASTING) / (K0 * _AR)
    xi_p, eta_p = xi, eta
    for j, b in enumerate(_BETA, start=1):
        xi_p -= b * math.sin(2 * j * xi) * math.cosh(2 * j * eta)
        eta_p -= b * math.cos(2 * j * xi) * math.sinh(2 * j * eta)
    tp = math.sin(xi_p) / math.hypot(math.sinh(eta_p), math.cos(xi_p))
    dlon = math.atan2(math.sinh(eta_p), math.cos(xi_p))
    # Широта из conformal по Ньютону, как у Karney.
    tau = tp
    e2 = _E * _E
    for _ in range(10):
        tpi = _tau_prime(tau)
        delta = (tp - tpi) / math.hypot(1.0, tpi) * (
            1.0 + (1.0 - e2) * tau * tau) / (
            (1.0 - e2) * math.hypot(1.0, tau))
        tau += delta
        if abs(delta) < 1e-14:
            break
    central = (zone - 1) * 6.0 - 180.0 + 3.0
    lon = (central + math.degrees(dlon) + 180.0) % 360.0 - 180.0
    return math.degrees(math.atan(tau)), lon


def to_mgrs(lat, lon, digits=5):
    """Строка MGRS с точностью 10^(5-digits) м или None вне UTM."""
    utm = to_utm(lat, lon)
    if utm is None:
        return None
    zone, letter, easting, northing = utm
    column = COLUMNS[(zone - 1) % 3][int(easting // 100000.0) - 1]
    shift = 5 if zone % 2 == 0 else 0
    row = ROWS[(int(northing // 100000.0) + shift) % 20]
    scale = 10 ** (5 - digits)
    east = int(easting % 100000.0) // scale
    north = int(northing % 100000.0) // scale
    return "{}{} {}{} {:0{d}d} {:0{d}d}".format(
        zone, letter, column, row, east, north, d=digits)


def _band_bottom(letter):
    return -80.0 + 8.0 * BANDS.index(letter)


def from_mgrs(zone, letter, column, row, east, north, digits):
    """Широта и долгота юго-западного угла квадрата MGRS."""
    columns = COLUMNS[(zone - 1) % 3]
    if column not in columns or row not in ROWS or letter not in BANDS:
        return None
    scale = 10 ** (5 - digits)
    easting = (columns.index(column) + 1) * 100000.0 + east * scale
    shift = 5 if zone % 2 == 0 else 0
    north_100 = (ROWS.index(row) - shift) % 20
    northing = north_100 * 100000.0 + north * scale
    south = letter < "N"
    bottom = _band_bottom(letter)
    central = (zone - 1) * 6.0 - 180.0 + 3.0
    lowest = to_utm(bottom, central, zone)[3]
    # Буквы строк повторяются каждые 2000 км. Северная координата -
    # первая с такими буквами не ниже низа полосы широты.
    while northing < lowest - 100000.0:
        northing += 2000000.0
    return from_utm(zone, south, easting, northing)


def dms_parts(value):
    """Градусы, минуты и секунды абсолютного значения."""
    value = abs(value)
    degrees = int(value)
    minutes_all = (value - degrees) * 60.0
    minutes = int(minutes_all)
    seconds = (minutes_all - minutes) * 60.0
    return degrees, minutes, seconds


def dms_text(value, positive, negative, digits=1):
    """Одна координата в градусах, минутах и секундах с полушарием."""
    degrees, minutes, seconds = dms_parts(value)
    seconds = round(seconds, digits)
    if seconds >= 60.0:
        seconds -= 60.0
        minutes += 1
    if minutes >= 60:
        minutes -= 60
        degrees += 1
    return "{}°{:02d}′{:0{w}.{p}f}″ {}".format(
        degrees, minutes, seconds, positive if value >= 0 else negative,
        w=3 + digits if digits else 2, p=digits)


def format_point(lat, lon, fmt="decimal", hemispheres=("N", "S", "E", "W"),
                 digits=5):
    """Точка в выбранном формате. hemispheres - подписи полушарий:
    север, юг, восток, запад. Вне UTM строки UTM и MGRS заменяются
    десятичными градусами."""
    if fmt == "dms":
        north, south, east, west = hemispheres
        return "{}, {}".format(dms_text(lat, north, south),
                               dms_text(lon, east, west))
    if fmt == "utm":
        utm = to_utm(lat, lon)
        if utm is not None:
            zone, letter, easting, northing = utm
            return "{}{} {:.0f} {:.0f}".format(zone, letter, easting,
                                               northing)
    if fmt == "mgrs":
        text = to_mgrs(lat, lon)
        if text is not None:
            return text
    return "{0:.{2}f}, {1:.{2}f}".format(lat, lon, digits)


# Разбор строки поиска.

_HEIGHT = re.compile(r",?\s*(высота|elevation|height)\b.*$", re.I)
_UTM = re.compile(r"^(\d{1,2})\s*([C-HJ-NP-X])\s+(\d+(?:\.\d+)?)\s*[EeВв]?"
                  r"\s*[,;]?\s+(\d+(?:\.\d+)?)\s*[NnСс]?$")
_MGRS = re.compile(r"^(\d{1,2})\s*([C-HJ-NP-X])\s*([A-HJ-NP-Z])\s*"
                   r"([A-HJ-NP-V])\s*(\d*)\s*(\d*)$")
_HEMI = {"N": ("lat", 1), "S": ("lat", -1), "E": ("lon", 1),
         "W": ("lon", -1), "С": ("lat", 1), "Ю": ("lat", -1),
         "В": ("lon", 1), "З": ("lon", -1)}
_RU_HEMI = ((r"с\.?\s*ш\.?", " С "), (r"ю\.?\s*ш\.?", " Ю "),
            (r"в\.?\s*д\.?", " В "), (r"з\.?\s*д\.?", " З "))


def parse_point(text):
    """Широта и долгота из строки поиска или None.

    Понимает десятичные градусы (и строку координат глобуса с высотой),
    градусы-минуты-секунды с полушариями, UTM «40V 513215 6429312»
    и MGRS «40V EL 13215 29312».
    """
    text = text.strip()
    plain = _HEIGHT.sub("", text).strip()
    found = parse_latlon(plain)
    if found is not None:
        return found
    upper = plain.upper()
    utm = _UTM.match(upper)
    if utm:
        zone = int(utm.group(1))
        if 1 <= zone <= 60:
            lat, lon = from_utm(zone, utm.group(2) < "N",
                                float(utm.group(3)), float(utm.group(4)))
            return lat, lon
    mgrs = _MGRS.match(upper)
    if mgrs:
        return _parse_mgrs(mgrs)
    return _parse_dms(plain)


def _parse_mgrs(match):
    zone = int(match.group(1))
    digits_e, digits_n = match.group(5), match.group(6)
    if digits_n == "" and digits_e:
        if len(digits_e) % 2:
            return None
        half = len(digits_e) // 2
        digits_e, digits_n = digits_e[:half], digits_e[half:]
    if len(digits_e) != len(digits_n) or len(digits_e) > 5 \
            or not 1 <= zone <= 60:
        return None
    digits = len(digits_e)
    east = int(digits_e) if digits else 0
    north = int(digits_n) if digits else 0
    return from_mgrs(zone, match.group(2), match.group(3), match.group(4),
                     east, north, digits)


def _parse_dms(text):
    """Градусы, минуты и секунды с полушариями или знаком."""
    if not re.search(r"[°'′\"″NSEWnsewСЮВЗсювз]", text):
        return None
    work = text
    for pattern, letter in _RU_HEMI:
        work = re.sub(pattern, letter, work, flags=re.I)
    work = re.sub(r"(\d),(\d)", r"\1.\2", work)
    # Буква полушария стоит отдельно от слов. Кроме чисел, знаков
    # градусов и букв полушарий в строке ничего нет, иначе это название
    # места, например «Москва».
    token = re.compile(r"[+-]?\d+(?:\.\d+)?|(?<![^\W\d_])[NSEWСЮВЗ]"
                       r"(?![^\W\d_])", re.I)
    if re.sub(r"[\s°'′’\"″”,;]", "", token.sub("", work)):
        return None
    tokens = token.findall(work)
    groups = []
    numbers = []
    for token in tokens:
        if token[-1].isdigit():
            numbers.append(float(token))
        else:
            groups.append((numbers, token.upper()))
            numbers = []
    if numbers:
        if groups:
            return None
        if len(numbers) % 2:
            return None
        half = len(numbers) // 2
        groups = [(numbers[:half], None), (numbers[half:], None)]
    if len(groups) != 2:
        return None
    values = {}
    for index, (parts, letter) in enumerate(groups):
        if not 1 <= len(parts) <= 3:
            return None
        if any(p >= 60.0 for p in parts[1:]) or any(p < 0 for p in parts[1:]):
            return None
        magnitude = abs(parts[0]) + sum(
            p / 60.0 ** k for k, p in enumerate(parts[1:], start=1))
        sign = -1.0 if parts[0] < 0 else 1.0
        axis = "lat" if index == 0 else "lon"
        if letter is not None:
            axis, hemi_sign = _HEMI[letter]
            sign *= hemi_sign
        if axis in values:
            return None
        values[axis] = sign * magnitude
    lat, lon = values.get("lat"), values.get("lon")
    if lat is None or lon is None or not -90.0 <= lat <= 90.0 \
            or not -180.0 <= lon <= 180.0:
        return None
    return lat, lon
