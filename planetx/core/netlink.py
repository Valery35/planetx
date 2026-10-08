# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Сетевые ссылки KML (NetworkLink). Расчёт без Qt.

Просьба автора от 9 октября 2026 года. Сетевая ссылка - папка «Моих
меток» с адресом документа KML или KMZ. Окно глобуса загружает
документ и заменяет им содержимое папки, при промежутке обновления -
снова через промежуток. Адрес - http(s) или файл на диске. Адреса
внутри документа (вложенные ссылки, картинки наложений) считаются от
адреса самого документа, как в Google Earth.
"""
import os
from urllib.parse import unquote, urljoin, urlparse

try:  # внутри плагина QGIS
    from .kml import KFolder, KOverlay
except ImportError:  # headless-тесты
    from kml import KFolder, KOverlay

# Промежуток обновления не короче MIN_REFRESH секунд, как у картинок
# по ссылке (core.overlays.MIN_REFRESH): лента с refreshInterval 4
# по умолчанию иначе спрашивалась бы непрерывно.
MIN_REFRESH = 10.0
# Сетевые ссылки внутри загруженных документов - не глубже DEPTH.
DEPTH = 3


def is_web(href):
    """Адрес в сети: http или https."""
    return urlparse(href).scheme.lower() in ("http", "https")


def local_path(href):
    """Путь файла по адресу file:// или пути на диске, иначе None."""
    parsed = urlparse(href)
    if parsed.scheme.lower() == "file":
        path = unquote(parsed.path)
        # file:///C:/x.kml даёт путь /C:/x.kml.
        if len(path) > 2 and path[0] == "/" and path[2] == ":":
            path = path[1:]
        return os.path.normpath(path)
    if parsed.scheme == "" or len(parsed.scheme) == 1:
        # Путь Windows вида C:\x.kml разбирается как схема «c».
        return os.path.normpath(href)
    return None


def resolve(href, base):
    """Адрес href относительно адреса документа base."""
    href = href.strip()
    if not href or is_web(href) or not base:
        return href
    if urlparse(href).scheme.lower() == "file" or os.path.isabs(href):
        return href
    if is_web(base):
        return urljoin(base, href)
    folder = os.path.dirname(local_path(base) or base)
    return os.path.normpath(os.path.join(folder, unquote(href)))


def resolve_tree(tree, base):
    """Адреса вложенных ссылок и картинок наложений дерева core.kml -
    от адреса документа base. Дерево меняется на месте."""
    for child in tree.children:
        if isinstance(child, KFolder):
            if child.link:
                child.link = resolve(child.link, base)
            resolve_tree(child, base)
        elif isinstance(child, KOverlay) and child.href \
                and child.image is None:
            child.href = resolve(child.href, base)
    return tree


def interval(refresh):
    """Промежуток обновления, с: 0 - один раз, иначе не короче
    MIN_REFRESH."""
    return 0.0 if refresh <= 0.0 else max(refresh, MIN_REFRESH)


def due(loaded, refresh, now):
    """Пора ли загружать ссылку: loaded - время прошлой загрузки или
    None, refresh - промежуток из папки."""
    if loaded is None:
        return True
    step = interval(refresh)
    return step > 0.0 and now - loaded >= step
