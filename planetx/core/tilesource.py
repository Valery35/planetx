# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Разбор адреса нового источника тайлов. Модуль не знает про Qt.

Окно «Новый источник тайлов» (ui/tilesource.py) принимает адрес в том
виде, в каком его копируют из браузера или чужих настроек, и приводит
к шаблону подключения XYZ QGIS с полями {z}, {x}, {y}, {-y} или {q}:

- шаблон с полями - как есть, поля {s} (поддомен) и {r} (размер для
  экранов высокой плотности) заменяются значениями по умолчанию;
- поля в фигурных скобках, закодированные как %7B и %7D, раскодируются;
- поля вида ${z} из OpenLayers приводятся к {z};
- адрес конкретного тайла, например .../12/2589/1290.png, - последние
  три числа пути считаются уровнем, столбцом и рядом, у серверов ArcGIS
  MapServer - уровнем, рядом и столбцом;
- параметры запроса z=, x=, y= (или zoom=, col=, row=) получают поля.

Шаблон без полей, который не удалось разобрать, - ошибка, окно
показывает её текстом.
"""
import re
from urllib.parse import unquote, urlsplit

try:  # внутри плагина QGIS
    from .basemap import valid_url
except ImportError:  # headless-тесты
    from basemap import valid_url

SUBDOMAIN = "a"  # {s} у Leaflet - поддомены a, b, c
_TILE_PATH = re.compile(r"/(\d{1,2})/(\d+)/(\d+)(\.[A-Za-z]{3,4})?$")
_QUERY_KEYS = (("z", ("z", "zoom", "level", "l", "tilematrix")),
               ("x", ("x", "col", "tilecol")),
               ("y", ("y", "row", "tilerow")))


class ParseError(ValueError):
    """Адрес не удалось привести к шаблону тайлов."""


def _fields(url):
    """Привести разные записи полей к {поле}."""
    url = url.strip()
    if "%7B" in url.upper():
        url = unquote(url)
    url = re.sub(r"\$\{(-?[a-z]+)\}", r"{\1}", url)
    url = url.replace("{s}", SUBDOMAIN).replace("{r}", "")
    url = re.sub(r"\{switch:([^,}]+)[^}]*\}", r"\1", url)
    return url


def _from_tile_path(url):
    """Адрес одного тайла с z/x/y в конце пути."""
    parts = urlsplit(url)
    m = _TILE_PATH.search(parts.path)
    if not m:
        return None
    z, a, b = (int(v) for v in m.group(1, 2, 3))
    n = 1 << z
    if z > 24 or a >= n or b >= n:
        return None
    # ArcGIS MapServer: .../tile/{z}/{y}/{x}.
    order = "{z}/{y}/{x}" if "/mapserver/tile/" in parts.path.lower() \
        else "{z}/{x}/{y}"
    path = parts.path[:m.start()] + "/" + order + (m.group(4) or "")
    return url.replace(parts.path, path, 1)


def _from_query(url):
    """Адрес с уровнем, столбцом и рядом в параметрах запроса."""
    parts = urlsplit(url)
    if not parts.query:
        return None
    pairs = [p.split("=", 1) for p in parts.query.split("&") if "=" in p]
    found = {}
    for field, names in _QUERY_KEYS:
        for i, (key, value) in enumerate(pairs):
            if key.lower() in names and value.isdigit():
                found[field] = i
                break
    if len(found) != 3:
        return None
    for field, i in found.items():
        pairs[i][1] = "{%s}" % field
    query = "&".join("=".join(p) for p in pairs)
    return url.replace(parts.query, query, 1)


def template(text):
    """Шаблон подключения XYZ по введённому адресу или ParseError."""
    url = _fields(text)
    if not url:
        raise ParseError("empty")
    if not re.match(r"^(https?|file)://", url, re.I):
        raise ParseError("scheme")
    if valid_url(url):
        return url
    if "{" not in url:
        for guess in (_from_tile_path, _from_query):
            out = guess(url)
            if out and valid_url(out):
                return out
    raise ParseError("fields")


def flip_rows(url):
    """Ряды сверху вниз и снизу вверх: {y} на {-y} и обратно."""
    if "{-y}" in url:
        return url.replace("{-y}", "{y}")
    return url.replace("{y}", "{-y}")


def name_for(url):
    """Название источника по адресу: имя сервера без www и tile."""
    host = urlsplit(url).hostname or ""
    parts = [p for p in host.split(".")
             if p not in ("www", "tile", "tiles", SUBDOMAIN)]
    if len(parts) >= 2:
        parts = parts[-2:-1] if parts[-1] in ("com", "org", "net", "ru",
                                              "io", "gov") else parts[-2:]
    return ".".join(parts) or "XYZ"


def preview_keys(level=1):
    """Тайлы мозаики предпросмотра: весь мир уровнем level."""
    n = 1 << level
    return [(level, x, y) for y in range(n) for x in range(n)]
