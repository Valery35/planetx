# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Сцена глобуса в файл и из файла (шаг 12).

Снимок сцены берёт камеру, промежуток открытой шкалы времени,
отмеченные на глобусе слои проекта, настройки вида и выбранную папку
«Моих меток». Применение сцены ставит настройки, берёт слои из проекта
или добавляет их по источнику, кладёт метки сцены в «Мои метки» новой
папкой, открывает шкалу на промежутке сцены и ведёт камеру в позу
сцены. Время временного контроллера QGIS из прежних сцен становится
промежутком шкалы.

Пароль из источника слоя базы данных при сохранении вырезается, файл
сцены передают другим людям. Ссылка authcfg на настройку подключения
QGIS остаётся.
"""
import math

from qgis.core import (QgsDataSourceUri, QgsProject, QgsRasterLayer,
                       QgsVectorLayer)
from qgis.PyQt.QtCore import QDateTime, Qt

from ..core import when
from ..core.kml import read_kml, write_kml
from ..core.places import LABEL_LANGUAGES, LOCAL, AS_QGIS
from ..core.scene import Scene
from .project import read_insets
from .track import seconds
from ..qt_compat import enum

# Поставщики, в источнике которых бывает пароль.
DATABASES = ("postgres", "mssql", "oracle", "hana", "db2", "spatialite")


def _datetime(text):
    return QDateTime.fromString(text or "", enum(Qt, "DateFormat",
                                                 "ISODate"))


def scene_span(time):
    """Промежуток шкалы времени сцены парой строк KML или None.

    Прежняя сцена хранила временной контроллер QGIS. Выключенный
    контроллер - без времени, анимация - промежуток текущего кадра,
    иначе весь промежуток контроллера.
    """
    if not isinstance(time, dict):
        return None
    if "mode" not in time:
        start, end = time.get("start"), time.get("end")
        if isinstance(start, str) and isinstance(end, str):
            return (start, end)
        return None
    mode = time.get("mode")
    lo = seconds(_datetime(time.get("start")))
    hi = seconds(_datetime(time.get("end")))
    if mode not in (1, 2, 3) or lo is None or hi is None:
        return None
    step, frame = time.get("step"), time.get("frame")
    if mode == 1 and isinstance(step, (int, float)) and step > 0 \
            and isinstance(frame, int):
        lo = lo + frame * step
        hi = lo + step
    return (when.text(lo), when.text(hi))


def clean_uri(provider, source):
    """Источник без пароля: у баз данных пароль вырезается."""
    if provider in DATABASES:
        uri = QgsDataSourceUri(source)
        if uri.password():
            uri.setPassword("")
            source = uri.uri(False)
    return source


def clean_source(layer):
    """Источник слоя без пароля."""
    return clean_uri(layer.providerType(), layer.source())


def capture(window, folder=None, name=""):
    """Сцена с глобуса и текст KML её меток.

    folder - ключ папки «Моих меток», метки и тур сцены, None - без
    меток.
    """
    pose = window.view.navigator.pose
    if window.view.sky_view is not None \
            and getattr(window, "_globe_pose", None) is not None:
        # В небе навигатор ведёт взгляд на небо, камера глобуса -
        # поза до входа в небо.
        pose = window._globe_pose
    project = QgsProject.instance()
    layers = []
    shown = set(window.shown_layers())
    # Растры - рельеф глобуса входят в сцену и без показа на глобусе.
    reliefs = set(read_insets())
    for layer_id in sorted(shown | reliefs):
        layer = project.mapLayer(layer_id)
        if layer is None:
            continue
        layers.append({"name": layer.name(),
                       "provider": layer.providerType(),
                       "source": clean_source(layer),
                       "kind": "raster" if isinstance(layer, QgsRasterLayer)
                       else "vector",
                       "shown": layer_id in shown,
                       "relief": layer_id in reliefs})
    time = None
    span = window._time_range
    if span is not None and all(math.isfinite(v) for v in span):
        time = {"start": when.text(span[0]), "end": when.text(span[1])}
    view = {"basemap": window.sources[window._basemap].name,
            "relief": bool(window._relief), "scale": float(window._scale),
            "groups": sorted(window._groups),
            "language": window._language,
            # Строки раздела «Слои»: сетка, звёзды, облака, температура,
            # 3D-здания.
            "extras": {key: bool(on) for key, on in window.extras.items()},
            # Сцена знает о врезках своего рельефа. В прежних сценах
            # поля нет, врезки проекта при открытии остаются.
            "insets": len(reliefs)}
    wedge = window.view.wedge
    if wedge is not None:
        # Сектор разреза Земли: запад, восток, юг, север, градусы.
        view["wedge"] = [round(float(v), 4) for v in wedge]
    sky = window.view.sky_view
    if sky is not None:
        # Вид неба: взгляд и угол обзора, градусы. Тело под небом
        # остаётся в камере сцены.
        view["sky"] = [math.degrees(sky.ra), math.degrees(sky.dec), sky.fov]
    kml = ""
    places = ""
    if folder:
        tree = window.myplaces.export_tree(folder)
        places = tree.name
        kml = write_kml(tree)
    scene = Scene((pose.lat, pose.lon, pose.distance, pose.heading,
                   pose.tilt), time, layers, view, places, name,
                  body=window.planet.key)
    return scene, kml


def _find_layer(entry):
    for layer in QgsProject.instance().mapLayers().values():
        if layer.providerType() == entry.get("provider") \
                and clean_source(layer) == entry.get("source"):
            return layer
    return None


def _add_layer(entry):
    make = QgsRasterLayer if entry.get("kind") == "raster" \
        else QgsVectorLayer
    layer = make(entry["source"], entry.get("name") or "",
                 entry.get("provider") or "ogr")
    if not layer.isValid():
        return None
    QgsProject.instance().addMapLayer(layer)
    return layer


def apply(window, scene, kml=b""):
    """Поставить сцену на глобус. Возвращает (ключ папки меток или None,
    названия слоёв, которые не нашлись и не открылись)."""
    # Тело - первым: метки сцены ложатся на текущее тело, земные
    # настройки вида на другом теле остаются выключенными.
    window.set_body(scene.body)
    view = scene.view
    names = [source.name for source in window.sources]
    if view.get("basemap") in names:
        window.choose_basemap(names.index(view["basemap"]))
    if "relief" in view:
        window.set_relief(bool(view["relief"]))
    if isinstance(view.get("scale"), (int, float)):
        window.set_relief_scale(float(view["scale"]))
    if isinstance(view.get("groups"), list):
        window.set_line_groups(set(view["groups"]))
    language = view.get("language")
    if language in LABEL_LANGUAGES or language in (LOCAL, AS_QGIS):
        window.set_label_language(language)
    # В прежних сценах строк раздела «Слои» нет, они остаются как есть.
    extras = view.get("extras")
    if isinstance(extras, dict):
        for key, on in extras.items():
            if key in window.extras and bool(on) != window.extras[key]:
                window.set_extra(key, bool(on))
    # Сектор разреза - после строк: включённая строка ставит сектор под
    # прежнюю точку взгляда, сцена заменяет его своим.
    wedge = view.get("wedge")
    if isinstance(wedge, list) and len(wedge) == 4 \
            and all(isinstance(v, (int, float)) for v in wedge):
        window.set_wedge_box(*wedge)
    wanted, reliefs, missing = set(), [], []
    for entry in scene.layers:
        layer = _find_layer(entry) or _add_layer(entry)
        if layer is None:
            missing.append(entry.get("name") or entry.get("source"))
            continue
        if entry.get("shown", True):
            wanted.add(layer.id())
        if entry.get("relief"):
            reliefs.append(layer.id())
    for layer in QgsProject.instance().mapLayers().values():
        window.set_layer_shown(layer.id(), layer.id() in wanted)
    if "insets" in view:
        window.set_insets(reliefs)
    key = None
    if kml:
        # Метки ложатся на тело сцены, в том числе на небо.
        key = window.myplaces.import_tree(read_kml(kml, scene.places),
                                          body=window.body_key())
    window.refresh()
    # Шкала - после слоёв и меток: их время входит в охват шкалы.
    span = scene_span(scene.time)
    if span is not None:
        window._show_time(span)
    lat, lon, distance, heading, tilt = scene.camera
    window._fly_to(lat, lon, distance, heading, tilt)
    sky = view.get("sky")
    if isinstance(sky, list) and len(sky) == 3 \
            and all(isinstance(v, (int, float)) for v in sky):
        window.show_sky(*sky)
    return key, missing
