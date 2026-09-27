# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Проверка новых шагов в отдельном QGIS 4. Запускается при старте QGIS.

    qgis.bat --profiles-path %TEMP%\\planetx_stress --code
        tools\\qgis_check_steps.py

QGIS пользователя не трогается, проект пустой и не сохраняется.
Итог пишется в %TEMP%\\planetx_steps.json,
стек при падении - в %TEMP%\\planetx_steps_crash.txt. В конце QGIS
закрывается.
"""
import faulthandler
import json
import os
import sys
import traceback

ROOT = r"C:\Dev\planetx"
sys.path.insert(0, ROOT)
TEMP = os.environ.get("TEMP", ".")
CRASH = open(os.path.join(TEMP, "planetx_steps_crash.txt"), "w",
             encoding="utf-8")
faulthandler.enable(CRASH, all_threads=True)

from qgis.core import QgsApplication, QgsProject  # noqa: E402
from qgis.PyQt.QtCore import QTimer  # noqa: E402
from qgis.utils import iface  # noqa: E402

OUT = os.path.join(TEMP, "planetx_steps.json")
result = {"errors": []}
state = {}
CHECKS = []


def check(delay):
    """Шаг проверки: функция и пауза перед следующим шагом, мс."""
    def wrap(function):
        CHECKS.append((function, delay))
        return function
    return wrap


def finish():
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1, default=str)
    if "plugin" in state:
        state["plugin"].unload()
    # С загруженными слоями QGIS падает на exit(0), и на экране автора
    # всплывает окно отчёта. Проект очищается заранее.
    QgsProject.instance().clear()
    QgsApplication.instance().exit(0)


def run(index=0):
    if index >= len(CHECKS):
        finish()
        return
    function, delay = CHECKS[index]
    CRASH.write("step %s\n" % function.__name__)
    CRASH.flush()
    try:
        function()
    except (AttributeError, KeyError, RuntimeError, TypeError,
            ValueError):
        result["errors"].append("%s: %s" % (
            function.__name__, traceback.format_exc().splitlines()[-1]))
    QTimer.singleShot(delay, lambda: run(index + 1))


@check(4000)
def open_globe():
    from planetx.plugin import PlanetXPlugin
    plugin = PlanetXPlugin(iface)
    plugin.initGui()
    plugin.run()
    state["plugin"] = plugin
    state["window"] = plugin.window
    plugin.window.showNormal()


@check(200)
def places_folder():
    # «Мои метки» - папка сразу под «Глобусом», есть и пустая.
    panel = state["window"].panel
    result["places_folder"] = [
        panel.list.indexOfTopLevelItem(panel.head),
        panel.list.indexOfTopLevelItem(panel.places_group)]
    result["geo_has_places"] = any(
        panel.geo.topLevelItem(i).text(0) == panel.places_group.text(0)
        for i in range(panel.geo.topLevelItemCount()))

@check(8000)
def shapes_set():
    from planetx.core.features import Shape
    from planetx.core.navigation import Pose
    view = state["window"].view
    view.navigator.stop()
    view.navigator.set_pose(Pose(58.0, 56.25, 40000.0, 0.0, 30.0))
    view.set_shapes([
        Shape("polygon", [(57.95, 56.1), (57.95, 56.4), (58.06, 56.4),
                          (58.06, 56.1)], color=(255, 0, 255, 255),
              width=4.0, fill=(255, 0, 255, 60), name="Квадрат"),
        Shape("line", [(57.9, 56.0), (58.1, 56.5)],
              color=(255, 255, 0, 255), width=3.0),
        Shape("point", [(58.01, 56.25)], name="Точка"),
    ])
    result["gl_before"] = dict(view.gl_errors)


@check(100)
def shapes_check():
    view = state["window"].view
    image = view.grabFramebuffer()
    image.save(os.path.join(TEMP, "planetx_steps_shapes.png"))
    from planetx.net.loader import image_to_rgba
    rgba = image_to_rgba(image).astype(int)
    r, g, b = rgba[..., 0], rgba[..., 1], rgba[..., 2]
    result["magenta_px"] = int(((r > 200) & (g < 60) & (b > 200)).sum())
    result["yellow_px"] = int(((r > 200) & (g > 200) & (b < 60)).sum())
    result["gl_errors"] = dict(view.gl_errors)
    result["labels"] = view.labels.count
    result["features_built"] = sum(1 for x in view.features.buffers if x)


@check(2000)
def places():
    from planetx.core.features import Shape
    from planetx.ui.myplaces import MyPlaces
    window = state["window"]
    store = window.myplaces
    result["places_path"] = store.path
    before = len(store.places)
    keys = [store.add(Shape("point", [(58.01, 56.25)], name="Пермь, центр")),
            store.add(Shape("line", [(57.9, 56.0), (58.1, 56.5)],
                            name="Путь")),
            store.add(Shape("polygon", [(57.95, 56.1), (57.95, 56.4),
                                        (58.06, 56.4)],
                            fill=(255, 255, 255, 60), name="Треугольник"),
                      measure="Площадь 1 км²")]
    result["places_added"] = [k is not None for k in keys]
    result["places_count"] = len(store.places) - before
    group = window.panel.places_group
    result["panel_rows"] = group.childCount()
    result["view_shapes"] = len(window.view.features.shapes)
    state["places_shown"] = result["view_shapes"]
    # Флажок папки прячет все метки, запись после обхода строк.
    from qgis.PyQt.QtCore import Qt
    group.setCheckState(0, Qt.CheckState.Unchecked)
    state["place_keys"] = keys


@check(200)
def places_after_folder():
    from planetx.ui.myplaces import MyPlaces
    from qgis.PyQt.QtCore import Qt
    window = state["window"]
    store = window.myplaces
    keys = state["place_keys"]
    result["folder_hidden"] = [len(window.view.features.shapes),
                               sum(p.visible for p in store.places)]
    window.panel.places_group.setCheckState(0, Qt.CheckState.Checked)
    QgsApplication.processEvents()
    QgsApplication.processEvents()
    result["folder_shown"] = len(window.view.features.shapes)
    store.set_visible(keys[1], False)
    result["after_hide"] = len(window.view.features.shapes)
    store.rename(keys[0], "Центр Перми")
    store.remove(keys[2])
    again = MyPlaces(store.path)
    again.load()
    result["reread"] = sorted((p.shape.name, p.visible)
                              for p in again.places)
    window.fly_to_place(store.find(keys[1]))
    flight = window.view.navigator.flight
    result["place_flight"] = [round(v, 3) for v in (
        flight[1].end.lat, flight[1].end.lon)] if flight else None


@check(3000)
def ruler():
    from planetx.core.measure import destination
    from planetx.core.navigation import Pose
    window = state["window"]
    window._open_ruler()
    r = window.ruler
    dialog = window.ruler_dialog
    out = {}
    r.set_mode("line")
    r.add(58.0, 56.0)
    r.add(59.0, 56.0)
    out["meridian_km"] = round(r.values(False)["length"] / 1000.0, 3)
    r.set_mode("circle")
    r.add(58.0, 56.0)
    r.add(*destination(58.0, 56.0, 90.0, 1000.0))
    v = r.values(False)
    out["circle"] = [round(v["radius"], 1), round(v["area"] / 1e6, 4)]
    r.set_mode("polygon")
    for p in ((58.0, 56.0), (58.0, 56.1), (58.1, 56.1), (58.1, 56.0)):
        r.add(*p)
    v = r.values(False)
    out["square"] = [round(v["perimeter"] / 1000.0, 3),
                     round(v["area"] / 1e6, 3)]
    out["summary"] = dialog.summary()
    # Щелчок по виду ставит точку пути, резинка тянется к курсору.
    r.set_mode("path")
    view = window.view
    view.navigator.stop()
    view.navigator.set_pose(Pose(58.0, 56.25, 30000.0))
    cam = view.camera
    view.clicked.emit(cam.width * 0.4, cam.height * 0.5)
    view.clicked.emit(cam.width * 0.6, cam.height * 0.5)
    r.set_cursor((58.05, 56.3))
    out["path_points"] = len(r.points)
    out["rubber"] = len(r.shape().points)
    out["shapes_on_globe"] = len(view.features.shapes)
    before = len(window.myplaces.places)
    window.myplaces.add(r.shape(rubber=False, name="Путь линейки"),
                        measure=dialog.summary())
    out["saved"] = len(window.myplaces.places) - before
    out["saved_measure"] = window.myplaces.places[-1].measure \
        if window.myplaces.places else None
    result["ruler"] = out


@check(200)
def ruler_frame():
    view = state["window"].view
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_steps_ruler.png"))
    result["gl_errors_end"] = dict(view.gl_errors)


@check(1500)
def draw():
    from qgis.PyQt.QtGui import QColor
    window = state["window"]
    store = window.myplaces
    before = len(store.places)
    window._open_place()
    dialog = window.place_dialog
    d = window.drawer
    out = {"ruler_closed": not window._ruler_open()}
    dialog.tabs.setCurrentIndex(0)
    dialog.name.setText("Метка теста")
    d.add(58.02, 56.2)
    d.add(58.03, 56.21)  # новый щелчок переносит метку
    out["point_points"] = len(d.points)
    window._save_place()
    dialog.tabs.setCurrentIndex(1)
    dialog.name.setText("Путь теста")
    dialog.color.setColor(QColor(0, 120, 255, 255))
    dialog.width.setValue(4.0)
    for p in ((58.0, 56.1), (58.02, 56.2), (58.0, 56.3)):
        d.add(*p)
    window._save_place()
    dialog.tabs.setCurrentIndex(2)
    dialog.name.setText("Многоугольник теста")
    for p in ((57.97, 56.1), (57.97, 56.2), (57.99, 56.15)):
        d.add(*p)
    window._save_place()
    out["added"] = len(store.places) - before
    saved = {p.shape.name: p.shape for p in store.places}
    path = saved.get("Путь теста")
    out["path_style"] = [list(path.color), path.width] if path else None
    point = saved.get("Метка теста")
    out["point_at"] = list(point.points[0]) if point else None
    poly = saved.get("Многоугольник теста")
    out["polygon_fill"] = list(poly.fill) if poly and poly.fill else None
    window._open_ruler()
    out["place_closed_by_ruler"] = not window._place_open()
    window.ruler_dialog.close()
    result["draw"] = out


@check(1500)
def link_setup():
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsVectorLayer
    from planetx.core.navigation import Pose
    window = state["window"]
    layer = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string",
                           "Точки теста", "memory")
    features = []
    for n, (lat, lon) in enumerate(((58.0, 56.25), (58.01, 56.26))):
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
        f["name"] = "т%d" % n
        features.append(f)
    layer.dataProvider().addFeatures(features)
    QgsProject.instance().addMapLayer(layer)
    state["layer"] = layer
    window.set_layer_shown(layer.id(), True)
    window.refresh()
    window.view.navigator.stop()
    window.view.navigator.set_pose(Pose(58.0, 56.25, 20000.0))


@check(1000)
def link_selection():
    window = state["window"]
    layer = state["layer"]
    overlay = window.overlay
    window.dirty = False
    layer.selectByIds([next(layer.getFeatures()).id()])
    state["overlay_before"] = overlay


@check(200)
def link_selection_check():
    window = state["window"]
    layer = state["layer"]
    out = {"overlay_redrawn": window.overlay is not state["overlay_before"],
           "dirty_after_select": window.dirty}
    layer.removeSelection()
    # Опрос в точке первого объекта и «Выделить на карте».
    from planetx.ui.identify import IdentifyDialog, identify
    found = identify([layer], 58.0, 56.25, 50.0)
    dialog = IdentifyDialog(window)
    dialog.show_result("", found)
    dialog._select_on_map()
    out["selected_from_globe"] = len(layer.selectedFeatureIds())
    dialog.close()
    # Как на карте QGIS: глобус следует дереву слоёв и меняет его.
    from planetx.ui.project import visible_on_map
    window.set_follow(True)
    out["follow_shown"] = layer.id() in window.shown_layers()
    window.set_layer_shown(layer.id(), False)
    out["legend_after_uncheck"] = visible_on_map(layer)
    out["follow_shown_after"] = layer.id() in window.shown_layers()
    window.set_layer_shown(layer.id(), True)
    window.set_follow(False)
    # Новые слои сразу на глобус.
    from qgis.core import QgsVectorLayer
    window.set_new_shown(True)
    extra = QgsVectorLayer("Point?crs=EPSG:4326", "Новый слой", "memory")
    QgsProject.instance().addMapLayer(extra)
    out["new_layer_shown"] = extra.id() in window.shown_layers()
    window.set_new_shown(False)
    result["link"] = out


@check(200)
def save_view_check():
    from planetx.core.features import Shape
    from planetx.core.navigation import Pose
    from planetx.ui import myplaces
    import planetx.ui.window as wmod
    window = state["window"]
    nav = window.view.navigator
    nav.stop()
    nav.set_pose(Pose(58.0, 56.25, 15000.0, 35.0, 50.0))
    original = wmod.QInputDialog.getText
    wmod.QInputDialog.getText = staticmethod(
        lambda *args, **kwargs: ("Вид теста", True))
    try:
        window.save_view()
    finally:
        wmod.QInputDialog.getText = original
    views = [p for p in window.myplaces.places
             if p.shape.name == "Вид теста"]
    out = {"places": len(views),
           "view": [round(v, 1) for v in views[-1].view]
           if views and views[-1].view else None,
           "bookmarks": len(QgsProject.instance().bookmarkManager()
                            .bookmarks())}
    nav.set_pose(Pose(50.0, 40.0, 3.0e6))
    if views:
        window.fly_to_place(views[-1])
        end = nav.flight[1].end if nav.flight else None
        out["pose"] = [round(end.lat, 4), round(end.lon, 4),
                       round(end.distance), round(end.heading, 1),
                       round(end.tilt, 1)] if end else None
        window.myplaces.remove(views[-1].key)
    # Файл 0.4.1 без поля view: поле добавляется при открытии.
    old = os.path.join(TEMP, "planetx_old_places.gpkg")
    if os.path.exists(old):
        os.remove(old)
    fields = myplaces.FIELDS
    myplaces.FIELDS = tuple(f for f in fields if f[0] != "view")
    try:
        store = myplaces.MyPlaces(old)
        store.load()
        store.add(Shape("point", [(58.0, 56.0)], name="Старая"))
        out["old_has_view"] = store.layers["point"].fields() \
            .indexOf("view") >= 0
    finally:
        myplaces.FIELDS = fields
    store = myplaces.MyPlaces(old)
    store.load()
    key = store.add(Shape("point", [(58.1, 56.1)], name="Новая"),
                    view=(1000.0, 10.0, 20.0))
    out["migrated_has_view"] = store.layers["point"].fields() \
        .indexOf("view") >= 0
    out["migrated"] = sorted((p.shape.name, p.view) for p in store.places)
    out["migrated_key"] = key is not None
    store.layers = {}
    result["save_view"] = out

@check(500)
def big_polygon():
    import time
    from qgis.PyQt.QtCore import Qt
    window = state["window"]
    view = window.view
    arrow = Qt.CursorShape.ArrowCursor
    cross = Qt.CursorShape.CrossCursor
    out = {"cursor_idle": int(view.cursor().shape() == arrow)}
    window._open_place()
    out["cursor_tool"] = int(view.cursor().shape() == cross)
    dialog = window.place_dialog
    dialog.tabs.setCurrentIndex(2)
    d = window.drawer
    for p in ((57.5, 55.5), (57.5, 57.0), (58.5, 57.0)):
        d.add(*p)
    start = time.perf_counter()
    for i in range(10):
        d.set_cursor((58.5, 55.5 + 0.01 * i))
        view.repaint()
    out["ten_moves_s"] = round(time.perf_counter() - start, 2)
    window._save_place()
    dialog.close()
    out["cursor_after"] = int(view.cursor().shape() == arrow)
    result["big_polygon"] = out


QTimer.singleShot(3000, run)
