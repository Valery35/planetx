# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Перевод интерфейса.

Устройство взято из Topoliner. Исходный язык русский, английский
перевод лежит в словаре EN. Язык берётся из настройки локали QGIS,
а не системы. Файлы .qm не нужны, для них понадобился бы lrelease.
"""
import os

__all__ = ["tr", "is_russian", "set_language", "EN"]

EN = {
    "Загрузка подложки: {done} из {total}":
        "Loading base map: {done} of {total}",
    "Подложка не загрузилась: {error}":
        "Base map failed to load: {error}",
    "Высота {height}, тайлов в кадре {count}":
        "Altitude {height}, tiles in frame {count}",
    "Для глобуса нужен модуль Python {name}. В этой сборке QGIS его нет.":
        "The globe needs the Python module {name}. This QGIS build "
        "does not have it.",
    "Широта, долгота": "Latitude, longitude",
    "Координаты в градусах, например 58.0105, 56.2294.\n"
    "Enter запускает перелёт. Перелёт прерывается мышью.":
        "Coordinates in degrees, for example 58.0105, 56.2294.\n"
        "Enter starts the flight. The mouse interrupts it.",
    "Лететь": "Fly",
    "О модуле": "About",
    "Слои проекта": "Project layers",
    "Глобус": "Globe",
    "Свойства вида: двойной щелчок": "View properties: double click",
    "Подложка: выбор в меню по правой кнопке, двойной щелчок открывает "
    "свойства вида":
        "Base map: choose it in the right-click menu, a double click opens "
        "the view properties",
    "Подложка · {name}": "Base map · {name}",
    "Подложка": "Base map",
    "{name} · {kind}": "{name} · {kind}",
    "Подлететь: меню по правой кнопке": "Fly to: right-click menu",
    "Подлететь": "Fly to",
    "Свойства вида…": "View properties…",
    "растр": "raster",
    "точки": "points",
    "линии": "lines",
    "полигоны": "polygons",
    "таблица": "table",
    "слой": "layer",
    "Включённые слои проекта поверх подложки, в том же порядке, что на "
    "карте QGIS. Подписей нет. Когда слои меняются, глобус обновляет их "
    "кнопкой «Обновить слои» или сам, если в свойствах вида включено "
    "автоматическое обновление.":
        "The checked project layers over the base map, in the same order "
        "as on the QGIS map. There are no labels. When the layers change, "
        "the globe updates them with the Refresh layers button, or by "
        "itself if automatic update is on in the view properties.",
    "Обновить слои: слои проекта изменились":
        "Refresh layers: the project layers have changed",
    "Обновить слои проекта на глобусе": "Refresh the project layers on the "
                                        "globe",
    "Свойства вида": "View properties",
    "Слои проекта изменились. Нажмите «Обновить слои».":
        "The project layers have changed. Press Refresh layers.",
    "Обновлять автоматически": "Update automatically",
    "Слои проекта на глобусе обычно обновляются кнопкой «Обновить слои». "
    "С этим флажком глобус перерисовывает их сам после каждой правки "
    "данных, стиля, порядка или видимости слоёв. Удобно на лёгких данных, "
    "на тяжёлых глобус будет часто перерисовывать наложение.":
        "The project layers on the globe are usually updated with the "
        "Refresh layers button. With this option the globe redraws them "
        "after every change of data, style, order or visibility. Handy "
        "for light data, with heavy data the globe will redraw often.",
    "Границы и дороги": "Borders and roads",
    "Границы стран и регионов, реки и дороги поверх подложки по векторным "
    "тайлам OpenFreeMap. Линии ложатся на рельеф. Подписей нет.":
        "Country and region borders, rivers and roads over the base map "
        "from OpenFreeMap vector tiles. The lines follow the terrain. "
        "There are no labels.",
    "Границы и дороги не загрузились: {error}":
        "Borders and roads failed to load: {error}",
    "О модуле PlanetX": "About PlanetX",
    "Левая кнопка тянет Землю, после отпускания она вращается "
    "по инерции.":
        "The left button drags the Earth, after release it keeps "
        "rotating by inertia.",
    "Колесо приближает к точке под курсором.":
        "The wheel zooms to the point under the cursor.",
    "Средняя кнопка или левая с Shift поворачивают и наклоняют вид.":
        "The middle button or the left one with Shift turns and tilts "
        "the view.",
    "Координаты в поле внизу окна запускают перелёт.":
        "Coordinates in the field at the bottom of the window start "
        "a flight.",
    "Список внизу окна меняет подложку.":
        "The list at the bottom of the window changes the base map.",
    "Подложка OpenStreetMap: © участники OpenStreetMap.":
        "OpenStreetMap base map: © OpenStreetMap contributors.",
    "Рельеф: Mapzen Terrain Tiles, данные SRTM, GMTED, ETOPO1 и других "
    "источников.":
        "Terrain: Mapzen Terrain Tiles, data from SRTM, GMTED, ETOPO1 "
        "and other sources.",
    "Космоснимки и другие подложки берутся из подключений XYZ Tiles "
    "в QGIS. Условия использования задаёт их владелец.":
        "Satellite imagery and other base maps come from the XYZ Tiles "
        "connections in QGIS. Their owners set the terms of use.",
    "Исходный код": "Source code",
    "Сообщить об ошибке": "Report a bug",
    "Страница в каталоге QGIS": "QGIS plugin page",
    "Трёхмерный глобус внутри QGIS в духе Google Earth. Рельеф, "
    "атмосфера, подложки из подключений QGIS.":
        "A 3D globe inside QGIS in the spirit of Google Earth. Terrain, "
        "atmosphere, base maps from QGIS connections.",
    "Управление": "Controls",
    "Источники данных": "Data sources",
    "Разработка при поддержке": "Developed with the support of",
    "ООО «Информ++»": "Inform++ LLC",
    "Лицензия GNU GPL версии 3.": "License GNU GPL version 3.",
    "Источник картинки на глобусе. В списке OpenStreetMap "
    "и подключения XYZ Tiles из обозревателя QGIS, кроме "
    "подключений рельефа. Новое подключение появляется здесь "
    "при следующем открытии окна.":
        "Source of the globe imagery. The list holds OpenStreetMap "
        "and the XYZ Tiles connections from the QGIS browser, except "
        "terrain connections. A new connection appears here the next "
        "time the window opens.",
    "Не удалось прочитать координаты: {text}":
        "Could not read coordinates: {text}",
    "{value} м": "{value} m",
    "{value} км": "{value} km",
    "Контекст OpenGL 3.3 недоступен: {version}":
        "OpenGL 3.3 context is unavailable: {version}",
}

_language = None


def _detect():
    """Двухбуквенный код языка интерфейса QGIS."""
    value = ""
    try:
        from qgis.core import QgsSettings
    except ImportError:  # headless-тесты, язык берётся из окружения
        QgsSettings = None
    if QgsSettings is not None:
        value = QgsSettings().value("locale/userLocale", "") or ""
    if not value:
        # locale.getdefaultlocale устарел и выдаёт предупреждение Python.
        # Язык берётся из переменных окружения напрямую.
        for name in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
            found = os.environ.get(name)
            if found:
                value = found.split(":")[0].split(".")[0]
                break
    return (value or "en")[:2].lower()


def set_language(code):
    """Задать язык принудительно. Нужно тестам."""
    global _language
    _language = (code or "en")[:2].lower()


def is_russian():
    global _language
    if _language is None:
        _language = _detect()
    return _language == "ru"


def tr(text, **values):
    """Перевод строки и подстановка значений в фигурные скобки."""
    out = text if is_russian() else EN.get(text, text)
    return out.format(**values) if values else out
