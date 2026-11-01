# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Снимки с дронов и самолётов OpenAerialMap: поиск по рамке вида. Без Qt.

Слово автора от 1 ноября 2026 года - «делай OpenAerialMap» после разбора
данных RustGIS. Служба api.openaerialmap.org/meta отвечает без ключа,
21 487 снимков на 1 ноября 2026 года. Слой проекта - тайлы службы
tiles.openaerialmap.org, файл GeoTIFF из S3 открывался 35 с в главном
потоке, замер того же дня. Шаблон тайлов был у всех 400 проверенных
снимков, у старых адрес начинается с http.

Общая запись ответа называет CC-BY 4.0, но у снимка своя лицензия в поле
properties.license. Из 300 новых снимков 73 - CC BY-NC 4.0, 5 - CC BY-SA
4.0, поэтому показывается и пишется лицензия снимка. Запись лицензии
в данных разная, «CC-BY-NC 4.0» и «CC BY-NC 4.0». Даты бывают с ошибкой
ввода, например год 0206, такая дата не показывается.
"""
import math
from collections import namedtuple
from urllib.parse import urlencode

SEARCH = "https://api.openaerialmap.org/meta"
SITE = "https://openaerialmap.org"
TERMS = "https://openaerialmap.org/legal"
ATTRIBUTION = "OpenAerialMap (Open Imagery Network)"
PAGE = 100  # снимков на страницу ответа
FIRST_YEAR = 1990  # раньше дата считается ошибкой ввода
TILE_HOST = "tiles.openaerialmap.org"  # часть адреса тайлов снимка
MAX_LEVEL = 22  # глубже служба даёт увеличенные пиксели
CIRCLE = 40075016.686  # м, экватор Web Mercator

Image = namedtuple("Image", "title provider day gsd size license box url "
                            "thumbnail tiles")
Image.__doc__ = """Снимок: название, поставщик, день съёмки «ГГГГ-ММ-ДД» или
пусто, пиксель в метрах, байт в файле, лицензия снимка, рамка (запад, юг,
восток, север), адрес файла, адрес картинки или пусто, шаблон тайлов
XYZ или пусто."""


def search_url(box, page=1):
    """Адрес поиска снимков в рамке, новые первыми. Рамка через линию
    перемены дат берётся всеми долготами."""
    west, south, east, north = box
    if west > east:
        west, east = -180.0, 180.0
    return SEARCH + "?" + urlencode({
        "bbox": "{:.5f},{:.5f},{:.5f},{:.5f}".format(west, south, east,
                                                     north),
        "limit": PAGE, "page": page, "order_by": "acquisition_end",
        "sort": "desc"})


def license_text(value):
    """Единая запись лицензии снимка."""
    text = " ".join(str(value or "").split())
    return text.replace("CC-BY", "CC BY")


def day_of(text):
    """День съёмки из записи ISO, пусто при ошибке ввода года."""
    day = str(text or "")[:10]
    return day if day[:4].isdigit() and int(day[:4]) >= FIRST_YEAR else ""


def _image(row):
    url = str(row.get("uuid") or "")
    box = row.get("bbox")
    if not url.startswith("https://") or not isinstance(box, list) \
            or len(box) != 4:
        return None
    extra = row.get("properties")
    extra = extra if isinstance(extra, dict) else {}
    thumbnail = str(extra.get("thumbnail") or "")
    tiles = str(extra.get("tms") or "")
    if tiles.startswith("http://"):
        tiles = "https://" + tiles[len("http://"):]
    return Image(
        " ".join(str(row.get("title") or "").split()),
        " ".join(str(row.get("provider") or "").split()),
        day_of(row.get("acquisition_end")),
        float(row.get("gsd") or 0.0), int(row.get("file_size") or 0),
        license_text(extra.get("license")), tuple(float(v) for v in box),
        url, thumbnail if thumbnail.startswith("https://") else "",
        tiles if tiles.startswith("https://") else "")


def parse(data):
    """Ответ службы словарём: (снимки, найдено всего)."""
    found = data.get("meta", {}).get("found", 0)
    images = []
    for row in data.get("results", ()):
        image = _image(row) if isinstance(row, dict) else None
        if image is not None:
            images.append(image)
    return images, int(found)


def rights(image):
    """Строка прав слоя: у снимка своя лицензия и свой поставщик."""
    parts = [image.provider, image.license,
             "OpenAerialMap, contributors of Open Imagery Network"]
    return ", ".join(p for p in parts if p)


def max_level(image):
    """Уровень тайлов с пикселем не крупнее пикселя снимка."""
    if image.gsd <= 0.0:
        return MAX_LEVEL
    lat = (image.box[1] + image.box[3]) / 2.0
    metres = CIRCLE / 256.0 * max(math.cos(math.radians(lat)), 0.05)
    return min(max(int(math.ceil(math.log2(metres / image.gsd))), 0),
               MAX_LEVEL)


def mercator_box(box):
    """Рамка (запад, юг, восток, север) в метрах EPSG:3857."""
    def y_of(lat):
        phi = math.radians(max(min(lat, 85.0511), -85.0511))
        return math.log(math.tan(math.pi / 4.0 + phi / 2.0)) \
            * CIRCLE / (2.0 * math.pi)
    return (box[0] * CIRCLE / 360.0, y_of(box[1]),
            box[2] * CIRCLE / 360.0, y_of(box[3]))


def is_layer(source):
    """Источник слоя - тайлы снимка OpenAerialMap."""
    return TILE_HOST in str(source)
