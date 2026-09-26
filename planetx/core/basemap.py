# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Подложки: встроенные и подключения XYZ из настроек QGIS.

Встроенных две. OpenStreetMap - карта. Esri World Imagery - космоснимки,
подложка по умолчанию. В свойствах вида она названа примером подложки:
пользователь может заменить её своими подключениями XYZ. Решение автора
от 26 сентября 2026 года.

Модуль не знает про Qt. Настройки QGIS читает окно и передаёт сюда
словарь «имя подключения - поля подключения», как они лежат
в `connections/xyz/items/<имя>/`.

Подключения рельефа, то есть с непустым полем interpretation,
в список не попадают. Не попадают и подключения, адрес которых нельзя
разобрать, и те, что не дают уровней 0-2: на них держится подстилка.
"""
import re

OSM_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
ESRI_URL = ("https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}")
MAX_LEVEL = 19
DEFAULT_MAX = 18  # zmax подключения, если поле пустое, как в QGIS
START_LEVEL = 2  # уровни 0-START_LEVEL нужны до первого кадра
OSM_PARALLEL = 2  # правила OSM
OTHER_PARALLEL = 4

# Подписи известных источников по части адреса. Остальные подписываются
# именем подключения.
# Подпись Esri World Imagery - как в описании слоя в ArcGIS Online,
# поле accessInformation, сверено 26 сентября 2026 года. Maxar там
# переименован в Vantor. Ссылка ведёт на Esri Master License Agreement,
# по нему слой лицензирован.
KNOWN = (
    ("arcgisonline.com/ArcGIS/rest/services/World_Imagery",
     "Esri, Vantor, Earthstar Geographics, and the GIS User Community",
     "https://www.esri.com/en-us/legal/terms/full-master-agreement"),
)
OSM_ATTRIBUTION = ("© OpenStreetMap contributors",
                   "https://www.openstreetmap.org/copyright")

_FIELD = re.compile(r"\{([^{}]*)\}")
_KNOWN_FIELDS = {"x", "y", "-y", "z", "q"}


class Source:
    """Источник подложки.

    attribution - пара «текст, ссылка», ссылка может быть пустой.
    headers - дополнительные заголовки запроса. authcfg - код настройки
    проверки подлинности QGIS. login - пара «имя, пароль» из подключения
    или None.

    Имя и пароль идут одной парой без значения по умолчанию. Параметр
    password="" сканер каталога QGIS (Bandit, правило B107) принял
    за пароль в коде и заблокировал выпуск 0.2.0.
    """

    __slots__ = ("name", "url", "max_level", "attribution", "headers",
                 "authcfg", "username", "password", "parallel", "builtin",
                 "example")

    def __init__(self, name, url, max_level=MAX_LEVEL, attribution=None,
                 headers=None, authcfg="", login=None, builtin=False,
                 example=False):
        self.name = name
        self.url = url
        self.max_level = max_level
        self.attribution = attribution or (name, "")
        self.headers = dict(headers or {})
        self.authcfg = authcfg
        self.username, self.password = login or (None, None)
        self.builtin = builtin
        # Встроенный пример подложки, в свойствах вида он так и назван.
        self.example = example
        self.parallel = OSM_PARALLEL if is_osm(url) else OTHER_PARALLEL

    def tile_url(self, z, x, y):
        return tile_url(self.url, z, x, y)


def is_osm(url):
    return "tile.openstreetmap.org" in url


def osm():
    return Source("OpenStreetMap", OSM_URL, MAX_LEVEL, OSM_ATTRIBUTION,
                  builtin=True)


def esri_imagery():
    """Космоснимки Esri World Imagery, встроенный пример подложки."""
    return Source("Esri World Imagery", ESRI_URL, MAX_LEVEL,
                  attribution_for("", ESRI_URL), builtin=True,
                  example=True)


def builtins():
    """Встроенные подложки. Первая в списке - подложка по умолчанию."""
    return [esri_imagery(), osm()]


def quadkey(z, x, y):
    """Номер тайла Bing: цифры 0-3 от уровня 1 до z."""
    digits = []
    for level in range(z, 0, -1):
        mask = 1 << (level - 1)
        digits.append(str((1 if x & mask else 0) + (2 if y & mask else 0)))
    return "".join(digits)


def valid_url(url):
    """Адрес разбирается: известные поля, есть z, x, y или только q."""
    fields = set(_FIELD.findall(url))
    if not fields or not fields <= _KNOWN_FIELDS:
        return False
    if "q" in fields:
        return True
    return {"z", "x"} <= fields and bool(fields & {"y", "-y"})


def tile_url(template, z, x, y):
    values = {"z": z, "x": x, "y": y, "-y": (1 << z) - 1 - y,
              "q": quadkey(z, x, y) if "{q}" in template else ""}
    return _FIELD.sub(lambda m: str(values[m.group(1)]), template)


def _level(value, default):
    try:
        return int(str(value).strip())
    except ValueError:
        return default


def attribution_for(name, url):
    for part, text, link in KNOWN:
        if part in url:
            return text, link
    return name, ""


def from_settings(items):
    """Подложки из подключений XYZ QGIS.

    items - словарь «имя - словарь полей». Возвращает список Source
    в порядке имён. Встроенные подложки сюда не входят, подключение
    с тем же адресом пропускается.
    """
    out = []
    for name in sorted(items, key=str.lower):
        fields = items[name]
        url = str(fields.get("url") or "").strip()
        if str(fields.get("interpretation") or "").strip():
            continue
        if not url or url in (OSM_URL, ESRI_URL) or not valid_url(url):
            continue
        if _level(fields.get("zmin", 0), 0) > START_LEVEL:
            continue
        top = min(MAX_LEVEL, _level(fields.get("zmax", DEFAULT_MAX),
                                    DEFAULT_MAX))
        if top < START_LEVEL:
            continue
        headers = {}
        raw = fields.get("http-header")
        if isinstance(raw, dict):
            headers.update({str(k): str(v) for k, v in raw.items() if v})
        referer = str(fields.get("referer") or "").strip()
        if referer:
            headers["Referer"] = referer
        user = str(fields.get("username") or "")
        login = (user, str(fields.get("password") or "")) if user else None
        out.append(Source(
            name, url, top, attribution_for(name, url), headers,
            str(fields.get("authcfg") or ""), login))
    return out
