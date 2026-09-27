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
    again = None
    try:
        again = function()
    except (AttributeError, KeyError, RuntimeError, TypeError,
            ValueError, OSError):
        result["errors"].append("%s: %s" % (
            function.__name__, traceback.format_exc().splitlines()[-1]))
    if again:
        # Шаг ждёт: повторяется через again мс.
        QTimer.singleShot(again, lambda: run(index))
        return
    QTimer.singleShot(delay, lambda: run(index + 1))


@check(4000)
def open_globe():
    if os.environ.get("PLANETX_LABELS_FREE"):
        # Сравнение: надписи без ограничений разметки и растровки.
        from planetx.render import labels
        labels.NEW_ROWS_PER_FRAME = 10 ** 6
        labels.RASTER_TIME = 10.0
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

@check(200)
def sidebar():
    window = state["window"]
    view = window.view
    before = view.width()
    window.toolbar.sidebar.click()
    QgsApplication.processEvents()
    out = {"hidden": window.panel.isHidden(), "wider": view.width() - before,
           "tip": window.toolbar.sidebar.toolTip()}
    window.toolbar.sidebar.click()
    QgsApplication.processEvents()
    out["shown_again"] = not window.panel.isHidden()
    out["width_back"] = view.width() - before
    result["sidebar"] = out


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
    from planetx.net.loader import Throttle
    result["labels_state"] = {
        "pending": view.labels.pending, "more": view.labels._more,
        "moving": Throttle.moving, "kinds": sorted(view.label_kinds),
        "place_tiles": len(view.places.tiles),
        "place_busy": view.place_loader.busy()
        if view.place_loader is not None else None,
        "levels": dict(view.drawn_levels),
        "base_busy": view.loader.busy() if view.loader else None,
        "base_started": len(view.loader.started) if view.loader else None,
        "base_active": len(view.loader.replies) if view.loader else None,
        "pump_active": view.loader.pump_timer.isActive()
        if view.loader else None,
        "want": len(view.selection.want) if view.selection else None,
        "errors": {str(k): v for k, v in list(
            state["window"].errors.items())[:5]},
        "source": state["window"].source.name}
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


@check(1000)
def layer_opacity():
    from qgis.core import QgsRasterLayer
    from qgis.PyQt.QtWidgets import QMenu, QSlider
    from osgeo import gdal
    window = state["window"]
    layer = state["layer"]
    menu = QMenu(window)
    action = window.panel._opacity_action(menu, layer)
    slider = action.defaultWidget().findChild(QSlider)
    state["overlay_before"] = window.overlay
    slider.setValue(40)
    out = {"vector_opacity": round(layer.opacity(), 2),
           "refresh_started": window.refresh_timer.isActive()}
    # Растр: прозрачность слоя QGIS доходит до отрисовщика растра.
    path = os.path.join(TEMP, "planetx_raster.tif")
    ds = gdal.GetDriverByName("GTiff").Create(path, 4, 4, 1)
    ds.SetGeoTransform((56.0, 0.1, 0.0, 58.2, 0.0, -0.1))
    ds.GetRasterBand(1).Fill(100)
    ds = None
    raster = QgsRasterLayer(path, "Растр теста")
    QgsProject.instance().addMapLayer(raster)
    raster_slider = window.panel._opacity_action(menu, raster) \
        .defaultWidget().findChild(QSlider)
    raster_slider.setValue(70)
    out["raster_opacity"] = [round(raster.opacity(), 2),
                             round(raster.renderer().opacity(), 2)]
    state["opacity"] = out


@check(200)
def layer_opacity_check():
    window = state["window"]
    out = state["opacity"]
    out["overlay_redrawn"] = window.overlay is not state["overlay_before"]
    out["dirty"] = window.dirty
    result["opacity"] = out


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



SHOT_WAIT = 180.0  # секунд на загрузку тайлов снимка, не больше


def _shot_begin(to_layout, setup):
    import time
    window = state["window"]
    view = window.view
    window._open_snapshot(to_layout)
    dialog = window.shot_dialogs[to_layout]
    setup(dialog)
    done = []
    view.shot_done.connect(
        lambda image, complete: done.append(
            (image.width(), image.height(), complete) if image is not None
            else (0, 0, complete)))
    view.hole_check = True
    view.hole_counts = []
    state["shot"] = {"dialog": dialog, "done": done,
                     "started": time.monotonic()}
    dialog._start()


def _shot_wait():
    """Ждать снимок. Возвращает мс до повтора или None, когда готов."""
    import time
    shot = state["shot"]
    elapsed = time.monotonic() - shot["started"]
    if not shot["done"] and elapsed < SHOT_WAIT:
        return 1000
    view = state["window"].view
    counts = view.hole_counts[-1] if view.hole_counts else None
    view.hole_check = False
    out = {"done": shot["done"], "seconds": round(elapsed, 1),
           "holes": list(counts[1:]) if counts else None,
           "status": shot["dialog"].status.text(),
           "gl_errors": dict(view.gl_errors),
           "camera_back": [view.camera.width, view.camera.height]}
    if not shot["done"]:
        shot["dialog"].reject()
    return out


@check(500)
def shot_file():
    from planetx.core.navigation import Pose
    import planetx.ui.snapshot as smod
    window = state["window"]
    nav = window.view.navigator
    nav.stop()
    nav.set_pose(Pose(58.0, 56.25, 30000.0, 20.0, 45.0))
    path = os.path.join(TEMP, "planetx_shot.png")
    if os.path.exists(path):
        os.remove(path)
    smod.QFileDialog.getSaveFileName = staticmethod(
        lambda *args, **kwargs: (path, ""))

    def setup(dialog):
        dialog.keep.setChecked(False)
        dialog.width_px.setValue(4000)
        dialog.height_px.setValue(3000)
    _shot_begin(False, setup)


@check(1500)
def shot_file_wait():
    out = _shot_wait()
    if isinstance(out, int):
        return out
    from qgis.PyQt.QtGui import QImage
    path = os.path.join(TEMP, "planetx_shot.png")
    image = QImage(path)
    out["file"] = [image.width(), image.height()]
    result["shot_file"] = out
    return None


@check(500)
def shot_layout():
    def setup(dialog):
        dialog.layouts.setCurrentIndex(dialog.layouts.count() - 1)
        dialog.width_mm.setValue(120.0)
        dialog.dpi.setValue(200)
    _shot_begin(True, setup)


@check(1500)
def shot_layout_wait():
    out = _shot_wait()
    if isinstance(out, int):
        return out
    from qgis.core import QgsLayoutExporter, QgsLayoutItemPicture
    dialog = state["shot"]["dialog"]
    layout = dialog.layout
    if layout is not None:
        pictures = [i for i in layout.items()
                    if isinstance(i, QgsLayoutItemPicture)]
        out["pictures"] = len(pictures)
        out["picture_mm"] = [round(pictures[0].sizeWithUnits().width(), 1),
                             round(pictures[0].sizeWithUnits().height(), 1)] \
            if pictures else None
        pdf = os.path.join(TEMP, "planetx_layout.pdf")
        png = os.path.join(TEMP, "planetx_layout.png")
        exporter = QgsLayoutExporter(layout)
        out["pdf"] = int(exporter.exportToPdf(
            pdf, QgsLayoutExporter.PdfExportSettings()))
        settings = QgsLayoutExporter.ImageExportSettings()
        settings.dpi = 72
        exporter.exportToImage(png, settings)
        out["pdf_bytes"] = os.path.getsize(pdf) if os.path.exists(pdf) \
            else 0
        from planetx.net.loader import image_to_rgba
        from qgis.PyQt.QtGui import QImage
        rgba = image_to_rgba(QImage(png)).astype(int)
        # Лист белый, картинка глобуса - нет.
        out["page_not_white"] = round(float(
            (rgba[..., :3].sum(axis=2) < 700).mean()), 3)
    result["shot_layout"] = out
    return None



@check(500)
def tour_start():
    from planetx.core.features import Shape
    window = state["window"]
    store = window.myplaces
    for place in list(store.places):
        if place.visible:
            store.set_visible(place.key, False)
    a = store.add(Shape("point", [(58.0, 56.25)], name="Тур 1"))
    b = store.add(Shape("point", [(57.43, 56.94)], name="Тур 2"),
                  view=(5000.0, 90.0, 50.0))
    c = store.add(Shape("polygon", [(57.9, 56.0), (57.9, 56.2),
                                    (58.0, 56.1)], name="Тур 3"))
    # Перетаскивание «Тур 3» перед «Тур 2», как мышью в списке.
    order = [p.key for p in store.places]
    window.panel.place_moved.emit(c, "", order.index(b))
    state["tour_keys"] = (a, b, c)
    player = window.tour
    player.bar.pause.setValue(0.5)
    window._place_action("tour", "")
    state["tour_seen"] = []
    state["tour_paused"] = None
    result["tour"] = {
        "stops": [s.name for s in player.stops],
        "bar_shown": player.bar.isVisible(),
        "info": player.bar.info.text()}


@check(500)
def tour_wait():
    import time
    window = state["window"]
    player = window.tour
    seen = state["tour_seen"]
    began = state.setdefault("tour_began", time.monotonic())
    if player.tour is not None and player.playing:
        if not seen or seen[-1] != player.index:
            seen.append(player.index)
    paused = state["tour_paused"]
    if paused is None and player.index == 1 and player.playing:
        player.toggle()  # пауза в полёте ко второй остановке
        state["tour_paused"] = {"t": round(player.t, 2),
                                "playing": player.playing,
                                "flight": window.view.navigator.flight
                                is not None, "at": time.monotonic()}
        return 500
    if paused and "resumed" not in paused \
            and time.monotonic() - paused["at"] > 1.0:
        paused["still"] = window.view.navigator.flight is None
        player.toggle()
        paused["resumed"] = player.playing
        return 500
    if (player.playing or paused is None or "resumed" not in paused) \
            and time.monotonic() - began < 90:
        return 500
    pose = window.view.navigator.pose
    out = result["tour"]
    out["seen"] = seen
    out["paused"] = {k: v for k, v in paused.items() if k != "at"} \
        if paused else None
    out["end_pose"] = [round(pose.lat, 3), round(pose.lon, 3),
                       round(pose.distance), round(pose.heading, 1),
                       round(pose.tilt, 1)]
    out["seconds"] = round(time.monotonic() - began, 1)
    out["ended_playing"] = player.playing
    out["info_end"] = player.bar.info.text()
    player.stop()
    out["bar_after_stop"] = player.bar.isVisible()
    for key in state["tour_keys"]:
        window.myplaces.remove(key)
    return None



@check(500)
def tour_path():
    from planetx.core.features import Shape
    window = state["window"]
    store = window.myplaces
    key = store.add(Shape("line", [(58.0, 56.0), (58.18, 56.0),
                                   (58.18, 56.34)], name="Путь тура"))
    panel = window.panel
    group = panel.places_group
    item = next(group.child(i) for i in range(group.childCount())
                if group.child(i).data(0, panel_role()) == key)
    panel.list.setCurrentItem(item)
    out = {"button_on": panel.tour_button.isEnabled()}
    panel.list.setCurrentItem(panel.head)
    out["button_off_on_globe"] = not panel.tour_button.isEnabled()
    panel.list.setCurrentItem(item)
    panel.tour_button.click()
    player = window.tour
    out["stops"] = [type(s).__name__ for s in player.stops]
    state["path_key"] = key
    state["path_samples"] = []
    result["tour_path"] = out


def panel_role():
    from planetx.ui.panel import PLACE_ROLE
    return PLACE_ROLE


@check(500)
def tour_path_wait():
    player = state["window"].tour
    tour = player.tour
    samples = state["path_samples"]
    if tour is not None and player.playing \
            and player.t > tour.glides[0] + 1.0:
        pose = state["window"].view.navigator.pose
        samples.append([round(player.t, 1), round(pose.lat, 4),
                        round(pose.lon, 4), round(pose.heading, 1),
                        round(pose.tilt, 1), round(pose.distance)])
    if player.playing and len(samples) < 8:
        return 1000
    out = result["tour_path"]
    out["samples"] = samples
    close = [b for b in player.bar.findChildren(type(player.bar.play))
             if b.text() == "✕"]
    out["close_button"] = len(close)
    if close:
        close[0].click()
    out["bar_after_close"] = player.bar.isVisible()
    out["flight_after_close"] = state["window"].view.navigator.flight \
        is not None
    state["window"].myplaces.remove(state["path_key"])
    return None


@check(300)
def folders():
    from planetx.core.features import Shape
    from qgis.PyQt.QtCore import Qt
    window = state["window"]
    store = window.myplaces
    panel = window.panel
    out = {"table": store.folder_layer is not None
           and store.folder_layer.isValid()}
    f = store.add_folder("Папка F")
    g = store.add_folder("Папка G", f)
    p1 = store.add(Shape("point", [(58.0, 56.2)], name="p1"), folder=f)
    p2 = store.add(Shape("point", [(58.1, 56.3)], name="p2"), folder=g)
    p3 = store.add(Shape("line", [(58.0, 56.0), (58.1, 56.1)], name="p3"),
                   folder=g)
    state["folders"] = (f, g, p1, p2, p3)
    out["in_g"] = [p.name for p in store.places_in(g)]
    # Перетаскивание p1 в начало G и попытка положить F внутрь G.
    panel.place_moved.emit(p1, g, 0)
    out["in_g_after"] = [p.name for p in store.places_in(g)]
    panel.place_moved.emit(f, g, 0)
    out["f_parent"] = store.find(f).parent
    # Строки панели: F в корне, в F - G, в G - три метки.
    item_f = next(panel.places_group.child(i)
                  for i in range(panel.places_group.childCount())
                  if panel.places_group.child(i).text(0) == "Папка F")
    out["panel_f"] = [item_f.child(i).text(0)
                      for i in range(item_f.childCount())]
    item_g = item_f.child(0)
    out["panel_g"] = [item_g.child(i).text(0)
                      for i in range(item_g.childCount())]
    # Выбранная папка - папка новой метки.
    panel.list.setCurrentItem(item_g.child(1))
    out["current_folder"] = panel.current_folder() == g
    out["tour_button_on_folder"] = None
    panel.list.setCurrentItem(item_f)
    out["tour_button_on_folder"] = panel.tour_button.isEnabled()
    window._place_action("tour", f)
    out["tour_stops"] = [type(s).__name__ + ":" + s.name
                         for s in window.tour.stops]
    window.tour.stop()
    # Флажок папки F снимает все метки внутри, запись после обхода.
    item_f.setCheckState(0, Qt.CheckState.Unchecked)
    item_f.setExpanded(False)
    result["folders"] = out


@check(300)
def folders_check():
    from planetx.ui.myplaces import MyPlaces
    window = state["window"]
    store = window.myplaces
    f, g, p1, p2, p3 = state["folders"]
    out = result["folders"]
    out["visible_after_uncheck"] = [store.find(k).visible
                                    for k in (p1, p2, p3)]
    again = MyPlaces(store.path)
    again.load()
    out["reread_expanded_f"] = again.find(f).expanded
    out["reread_parent_g"] = again.find(g).parent == f
    again.layers, again.folder_layer = {}, None
    before = len(store.places)
    store.remove(f)
    out["removed_places"] = before - len(store.places)
    out["folders_left"] = [x.key for x in store.folders if x.key in (f, g)]


@check(300)
def new_folder():
    from planetx.core import placetree
    from planetx.core.features import Shape
    window = state["window"]
    store = window.myplaces
    p = store.add(Shape("point", [(58.0, 56.2)], name="под папкой"))
    q = store.add(Shape("point", [(58.0, 56.3)], name="после"))
    store.move(q, None, 0)
    store.move(p, None, 0)  # p первая, q вторая
    window._place_action("new_folder_after", p)
    roots = [n.key for n in placetree.children(store.nodes(), None)]
    new = window.panel.current_folder()
    out = {"after_place": roots[:3] == [p, new, q],
           "name": store.find(new).name if new else None}
    window._place_action("new_folder", new)
    inner = window.panel.current_folder()
    out["inside_folder"] = store.find(inner).parent == new
    for key in (new, p, q):
        store.remove(key)
    result["new_folder"] = out

# Выбор шагов: PLANETX_STEPS=tour_start,tour_wait. Окно открывается
# всегда. Без переменной идут все шаги.
ONLY = os.environ.get("PLANETX_STEPS")
if ONLY:
    CHECKS[:] = [c for c in CHECKS if c[0].__name__ == "open_globe"
                 or c[0].__name__ in ONLY.split(",")]
QTimer.singleShot(3000, run)
