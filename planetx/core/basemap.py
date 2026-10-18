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
import math
import re

import numpy as np

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

# Зеркала тайлов: начало адреса - запасные начала с теми же путями.
# Хранилище planetx-terrain отдаёт и CDN jsDelivr, проверено 11 октября
# 2026 года.
MIRRORS = {
    "https://raw.githubusercontent.com/Valery35/planetx-terrain/main/": (
        "https://cdn.jsdelivr.net/gh/Valery35/planetx-terrain@main/",),
}
MIRROR_PAUSE = 30.0  # с, не чаще переходит источник на другое зеркало

_FIELD = re.compile(r"\{([^{}]*)\}")
_KNOWN_FIELDS = {"x", "y", "-y", "z", "q"}


class Source:
    """Источник подложки.

    attribution - пара «текст, ссылка», ссылка может быть пустой.
    headers - дополнительные заголовки запроса. authcfg - код настройки
    проверки подлинности QGIS. login - пара «имя, пароль» из подключения
    или None. missing - коды ответа HTTP, которые значат «тайла нет»:
    вместо такого тайла встаёт увеличенный предок. Хранилище S3 без
    права на список отвечает на отсутствующий файл 403, так отвечает
    сервер снимков Луны на тайл 6/57/39, 1 октября 2026 года. У прочих
    подложек 403 - запрет доступа, это ошибка.

    urls - шаблон адреса и его зеркала (mirror_urls), mirror - номер
    действующего. Отказ сервера уводит источник на следующее зеркало
    (next_mirror), запросы идут туда же.

    Имя и пароль идут одной парой без значения по умолчанию. Параметр
    password="" сканер каталога QGIS (Bandit, правило B107) принял
    за пароль в коде и заблокировал выпуск 0.2.0.
    """

    __slots__ = ("name", "url", "max_level", "attribution", "headers",
                 "authcfg", "username", "password", "parallel", "builtin",
                 "example", "missing", "urls", "mirror", "switched",
                 "ready", "gap")

    def __init__(self, name, url, max_level=MAX_LEVEL, attribution=None,
                 headers=None, authcfg="", login=None, builtin=False,
                 example=False, missing=(404,)):
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
        self.missing = tuple(missing)
        self.parallel = OSM_PARALLEL if is_osm(url) else OTHER_PARALLEL
        self.urls = mirror_urls(url)
        self.mirror = 0
        self.switched = -1e9
        # Ключ готового источника (READY) или пустая строка.
        self.ready = ""
        # Секунд между запросами к источнику, 0 - общий отсчёт загрузчика.
        self.gap = 0.0

    def tile_url(self, z, x, y):
        return tile_url(self.urls[self.mirror], z, x, y)

    def parts(self, z, x, y):
        """Адреса частей тайла, если тайл собирается из нескольких
        картинок источника, иначе None - один адрес tile_url."""
        return None

    def assemble(self, z, x, y, images):
        """Тайл из картинок частей (массивы RGBA по порядку parts)."""
        raise NotImplementedError

    def next_mirror(self, now):
        """Перейти на следующее зеркало после отказа сервера, не чаще
        MIRROR_PAUSE. Истина - перешёл."""
        if len(self.urls) < 2 or now - self.switched < MIRROR_PAUSE:
            return False
        self.mirror = (self.mirror + 1) % len(self.urls)
        self.switched = now
        return True


def mirror_urls(url):
    """Шаблон и его зеркала по MIRRORS, главный - первым."""
    for head, others in MIRRORS.items():
        if url.startswith(head):
            return (url,) + tuple(o + url[len(head):] for o in others)
    return (url,)


def is_osm(url):
    """Сервер тайлов OpenStreetMap или OSM France - не больше двух
    запросов сразу, как по правилам OSM."""
    return any(host in url for host in (
        "tile.openstreetmap.org", "tile.openstreetmap.fr",
        "tile-cyclosm.openstreetmap.fr"))


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
        # Подпись, введённая в окне «Новый источник тайлов».
        credit = str(fields.get("planetx-attribution") or "").strip()
        out.append(Source(
            name, url, top,
            (credit, "") if credit else attribution_for(name, url),
            headers, str(fields.get("authcfg") or ""), login))
    return out


# Готовые источники меню «Основа». Решение автора от 13 октября 2026
# года - любые карты и снимки, у сервисов без разрешения на такой доступ -
# с предупреждением. Поля: ключ, название по-русски и по-английски,
# адрес, предельный уровень, подпись, ссылка на условия, предупреждать
# ли, вид адреса («xyz» или «ellipsoidal» - эллиптический Меркатор
# EPSG:3395, его тайлы пересчитываются, EllipticSource). Адреса
# проверены тайлом у Перми 13 октября 2026 года, схема Яндекса
# с projection=web_mercator совпала с OpenStreetMap, снимки Яндекса
# этот параметр не принимают.
GOOGLE_TERMS = "https://cloud.google.com/maps-platform/terms"
BING_TERMS = "https://www.microsoft.com/en-us/maps/product/terms"
YANDEX_TERMS = "https://yandex.ru/legal/maps_termsofuse/"
DGIS_TERMS = "https://law.2gis.ru/"
READY = (
    ("google_satellite", "Google Спутник", "Google Satellite",
     "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}", 19,
     "© Google", GOOGLE_TERMS, True, "xyz"),
    ("google_hybrid", "Google Гибрид", "Google Hybrid",
     "https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}", 19,
     "© Google", GOOGLE_TERMS, True, "xyz"),
    ("google_map", "Google Схема", "Google Map",
     "https://mt1.google.com/vt/lyrs=m&x={x}&y={y}&z={z}", 19,
     "© Google", GOOGLE_TERMS, True, "xyz"),
    ("google_terrain", "Google Рельеф", "Google Terrain",
     "https://mt1.google.com/vt/lyrs=p&x={x}&y={y}&z={z}", 19,
     "© Google", GOOGLE_TERMS, True, "xyz"),
    ("bing_aerial", "Bing Спутник", "Bing Aerial",
     "https://ecn.t1.tiles.virtualearth.net/tiles/a{q}.jpeg?g=14000", 19,
     "© Microsoft", BING_TERMS, True, "xyz"),
    ("bing_map", "Bing Схема", "Bing Map",
     "https://ecn.t1.tiles.virtualearth.net/tiles/r{q}.png?g=14000"
     "&mkt=ru-RU&shading=hill", 19, "© Microsoft", BING_TERMS, True, "xyz"),
    ("yandex_satellite", "Яндекс Спутник", "Yandex Satellite",
     "https://core-sat.maps.yandex.net/tiles?l=sat&x={x}&y={y}&z={z}"
     "&lang=ru_RU", 19, "© Яндекс", YANDEX_TERMS, True, "ellipsoidal"),
    ("yandex_map", "Яндекс Схема", "Yandex Map",
     "https://core-renderer-tiles.maps.yandex.net/tiles?l=map&x={x}&y={y}"
     "&z={z}&lang=ru_RU&projection=web_mercator", 19, "© Яндекс",
     YANDEX_TERMS, True, "xyz"),
    ("dgis_map", "2ГИС Схема", "2GIS Map",
     "https://tile2.maps.2gis.com/tiles?x={x}&y={y}&z={z}&v=1", 18,
     "© 2ГИС", DGIS_TERMS, True, "xyz"),
    ("opentopomap", "OpenTopoMap", "OpenTopoMap",
     "https://a.tile.opentopomap.org/{z}/{x}/{y}.png", 17,
     "© OpenStreetMap contributors, SRTM, © OpenTopoMap (CC-BY-SA)",
     "https://opentopomap.org/about", False, "xyz"),
    ("esri_topo", "Esri World Topo Map", "Esri World Topo Map",
     "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/"
     "MapServer/tile/{z}/{y}/{x}", 19, "Esri and the GIS User Community",
     "https://www.esri.com/en-us/legal/terms/full-master-agreement", False,
     "xyz"),
)
# Подложки без ключа по списку модуля basemaps RustGIS, просьба автора
# от 18 октября 2026 года «делай». Адреса проверены тайлом у Перми
# (USGS - у Денвера) 18 октября 2026 года. OSM Germany не взята -
# её правила ограничивают коммерческое и частое использование. Слои
# Esri - на тех же условиях, что World Imagery (doc/SOURCES.md).
ESRI_TILES = ("https://server.arcgisonline.com/ArcGIS/rest/services/"
              "{}/MapServer/tile/{{z}}/{{y}}/{{x}}")
ESRI_TERMS = "https://www.esri.com/en-us/legal/terms/full-master-agreement"
OSMFR_TERMS = "https://www.openstreetmap.fr/fonds-de-carte/"
OSMF_TERMS = "https://operations.osmfoundation.org/policies/tiles/"
GIBS_TERMS = ("https://www.earthdata.nasa.gov/engage/"
              "open-data-services-software-policies")
USGS_TILES = ("https://basemap.nationalmap.gov/arcgis/rest/services/"
              "{}/MapServer/tile/{{z}}/{{y}}/{{x}}")
USGS_TERMS = ("https://www.usgs.gov/information-policies-and-instructions/"
              "copyrights-and-credits")
USGS_CREDIT = "USGS The National Map"
READY = READY + (
    ("osm_hot", "OSM Гуманитарная", "OSM Humanitarian",
     "https://a.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png", 19,
     "© OpenStreetMap contributors, HOT, OpenStreetMap France",
     OSMFR_TERMS, False, "xyz"),
    ("osm_fr", "OSM Франция", "OSM France",
     "https://a.tile.openstreetmap.fr/osmfr/{z}/{x}/{y}.png", 19,
     "© OpenStreetMap France, © OpenStreetMap contributors", OSMFR_TERMS,
     False, "xyz"),
    ("cyclosm", "CyclOSM", "CyclOSM",
     "https://a.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png", 19,
     "CyclOSM, © OpenStreetMap contributors", OSMF_TERMS, False, "xyz"),
    ("esri_street", "Esri Улицы", "Esri World Street Map",
     ESRI_TILES.format("World_Street_Map"), 19,
     "Esri and its data partners", ESRI_TERMS, False, "xyz"),
    ("esri_light_gray", "Esri Светло-серая", "Esri Light Gray Canvas",
     ESRI_TILES.format("Canvas/World_Light_Gray_Base"), 16,
     "Esri, HERE, Garmin, © OpenStreetMap contributors", ESRI_TERMS, False,
     "xyz"),
    ("esri_dark_gray", "Esri Тёмно-серая", "Esri Dark Gray Canvas",
     ESRI_TILES.format("Canvas/World_Dark_Gray_Base"), 16,
     "Esri, HERE, Garmin, © OpenStreetMap contributors", ESRI_TERMS, False,
     "xyz"),
    ("esri_natgeo", "Esri National Geographic", "Esri National Geographic",
     ESRI_TILES.format("NatGeo_World_Map"), 16,
     "National Geographic, Esri, GEBCO, NOAA, iPC", ESRI_TERMS, False,
     "xyz"),
    ("esri_ocean", "Esri Океаны", "Esri Ocean",
     ESRI_TILES.format("Ocean/World_Ocean_Base"), 13,
     "Esri, GEBCO, NOAA, National Geographic", ESRI_TERMS, False, "xyz"),
    ("esri_terrain", "Esri Рельеф", "Esri World Terrain",
     ESRI_TILES.format("World_Terrain_Base"), 13,
     "Esri, USGS, NPS", ESRI_TERMS, False, "xyz"),
    ("esri_shaded", "Esri Отмывка", "Esri Shaded Relief",
     ESRI_TILES.format("World_Shaded_Relief"), 13, "Esri", ESRI_TERMS,
     False, "xyz"),
    ("esri_physical", "Esri Физическая", "Esri Physical",
     ESRI_TILES.format("World_Physical_Map"), 8,
     "Esri, US National Park Service", ESRI_TERMS, False, "xyz"),
    ("esri_hillshade", "Esri Отмывка подробная", "Esri World Hillshade",
     ESRI_TILES.format("Elevation/World_Hillshade"), 16,
     "Esri, Airbus DS, USGS, NGA, NASA, CGIAR", ESRI_TERMS, False, "xyz"),
    ("nasa_blue_marble", "NASA Blue Marble", "NASA Blue Marble",
     "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/"
     "BlueMarble_ShadedRelief_Bathymetry/default/"
     "GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg", 8,
     "NASA Blue Marble, NASA GIBS", GIBS_TERMS, False, "xyz"),
    ("usgs_imagery", "USGS Снимки (США)", "USGS Imagery (USA)",
     USGS_TILES.format("USGSImageryOnly"), 16, USGS_CREDIT, USGS_TERMS,
     False, "xyz"),
    ("usgs_imagery_topo", "USGS Снимки с картой (США)",
     "USGS Imagery Topo (USA)", USGS_TILES.format("USGSImageryTopo"), 16,
     USGS_CREDIT, USGS_TERMS, False, "xyz"),
    ("usgs_topo", "USGS Топокарта (США)", "USGS Topo (USA)",
     USGS_TILES.format("USGSTopo"), 16, USGS_CREDIT, USGS_TERMS, False,
     "xyz"),
    ("usgs_relief", "USGS Отмывка (США)", "USGS Shaded Relief (USA)",
     USGS_TILES.format("USGSShadedReliefOnly"), 16, USGS_CREDIT,
     USGS_TERMS, False, "xyz"),
)
READY_KEYS = tuple(r[0] for r in READY)
# Подменю «Готовых источников»: ключ группы и ключи источников по
# порядку. Названия групп даёт окно (перевод).
READY_GROUPS = (
    ("osm", ("opentopomap", "osm_hot", "osm_fr", "cyclosm")),
    ("esri", ("esri_topo", "esri_street", "esri_light_gray",
              "esri_dark_gray", "esri_natgeo", "esri_ocean", "esri_terrain",
              "esri_shaded", "esri_physical", "esri_hillshade")),
    ("nasa_usgs", ("nasa_blue_marble", "usgs_imagery", "usgs_imagery_topo",
                   "usgs_topo", "usgs_relief")),
    ("warned", ("google_satellite", "google_hybrid", "google_map",
                "google_terrain", "bing_aerial", "bing_map",
                "yandex_satellite", "yandex_map", "dgis_map")),
)


def ready_entry(key):
    """Строка READY по ключу или None."""
    for row in READY:
        if row[0] == key:
            return row
    return None


def ready_source(key, russian=True):
    """Готовый источник по ключу. Название - на языке интерфейса."""
    row = ready_entry(key)
    if row is None:
        raise KeyError(key)
    key, ru, en, url, top, credit, terms, _, kind = row
    cls = EllipticSource if kind == "ellipsoidal" else Source
    source = cls(ru if russian else en, url, top, (credit, terms))
    source.ready = key
    return source


# Эксцентриситет эллипсоида WGS84 - эллиптический Меркатор EPSG:3395.
ECCENTRICITY = 0.0818191908426215


def elliptic_rows(z, y, size=256):
    """Строки тайла Web Mercator (z, y) в тайлах эллиптического
    Меркатора того же уровня: (первый тайл, последний тайл, положения
    середин строк в картинке, сложенной из тайлов первый-последний,
    в пикселях от её верха). Столбцы у обеих проекций одни."""
    count = 1 << z
    v = (y + (np.arange(size) + 0.5) / size) / count
    lat = np.arctan(np.sinh(np.pi * (1.0 - 2.0 * v)))
    s = np.sin(lat)
    north = np.arctanh(s) - ECCENTRICITY * np.arctanh(ECCENTRICITY * s)
    rows = (0.5 - north / (2.0 * np.pi)) * count
    first = int(min(max(math.floor(rows.min()), 0), count - 1))
    last = int(min(max(math.floor(rows.max()), 0), count - 1))
    return first, last, (rows - first) * size - 0.5


def elliptic_tile(z, y, images, size=256):
    """Тайл Web Mercator из картинок тайлов EPSG:3395 одного столбца,
    сверху вниз (elliptic_rows). Строки берутся линейным смешением
    соседних строк сложенной картинки."""
    first, last, at = elliptic_rows(z, y, size)
    stack = np.concatenate([np.asarray(i, dtype=np.float32)
                            for i in images], axis=0)
    at = np.clip(at, 0.0, stack.shape[0] - 1.0)
    low = np.floor(at).astype(int)
    high = np.minimum(low + 1, stack.shape[0] - 1)
    share = (at - low)[:, None, None]
    out = stack[low] * (1.0 - share) + stack[high] * share
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


class EllipticSource(Source):
    """Источник в эллиптическом Меркаторе EPSG:3395 (снимки Яндекса):
    тайл глобуса собирается из одного-двух тайлов источника того же
    столбца и пересчитывается по широте. У Перми сдвиг между проекциями -
    около 36 км, без пересчёта снимок лёг бы мимо места."""

    __slots__ = ()

    def parts(self, z, x, y):
        first, last, _ = elliptic_rows(z, y)
        return [tile_url(self.urls[self.mirror], z, x, row)
                for row in range(first, last + 1)]

    def assemble(self, z, x, y, images):
        return elliptic_tile(z, y, images, images[0].shape[1])


# Земной шар в метрах Web Mercator, половина ширины.
MERCATOR_HALF = 20037508.342789244


def tile_bbox(z, x, y):
    """Рамка тайла в метрах EPSG:3857: запад, юг, восток, север."""
    side = 2.0 * MERCATOR_HALF / (1 << z)
    west = -MERCATOR_HALF + x * side
    north = MERCATOR_HALF - y * side
    return west, north - side, west + side, north


class SplitSource(Source):
    """Источник из двух шаблонов: мельче уровня split - coarse, глубже -
    url. Так у карты WorldCover мелкие уровни из planetx-terrain, а
    подробные - из службы, которая мельче уровня 6 тайлов не отдаёт."""

    __slots__ = ("coarse", "split")

    def __init__(self, name, url, coarse, split, *args, **kwargs):
        super().__init__(name, url, *args, **kwargs)
        self.coarse = coarse
        self.split = split

    def tile_url(self, z, x, y):
        if z < self.split:
            return tile_url(self.coarse, z, x, y)
        return super().tile_url(z, x, y)


class WmsSource(Source):
    """Источник WMS: место {bbox} адреса - рамка тайла в EPSG:3857."""

    __slots__ = ()

    def tile_url(self, z, x, y):
        box = ",".join("{:.2f}".format(v) for v in tile_bbox(z, x, y))
        return self.urls[self.mirror].replace("{bbox}", box)
