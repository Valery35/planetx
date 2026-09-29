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
import math
import os
import time
import sys
import traceback

ROOT = r"C:\Dev\planetx"
sys.path.insert(0, ROOT)
TEMP = os.environ.get("TEMP", ".")
CRASH = open(os.path.join(TEMP, "planetx_steps_crash.txt"), "w",
             encoding="utf-8")
faulthandler.enable(CRASH, all_threads=True)
# Зависание: стеки всех потоков в тот же файл каждые HANG_DUMP секунд.
# Прогон шагов редко идёт дольше, при зависании видно, где стоит
# главный поток. Переменная PLANETX_HANG_DUMP, 0 - выключено.
HANG_DUMP = int(os.environ.get("PLANETX_HANG_DUMP", "0"))
if HANG_DUMP:
    faulthandler.dump_traceback_later(HANG_DUMP, repeat=True, file=CRASH)

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


GL_TRACE = os.environ.get("PLANETX_GL_TRACE") == "1"
TRACE_PATH = os.path.join(TEMP, "planetx_gl_trace.txt")


def _trace(text):
    """Строка журнала трассировки, сразу на диск: при падении видно
    последнее действие перед ним."""
    with open(TRACE_PATH, "a", encoding="utf-8") as f:
        f.write("{:.3f} {}\n".format(time.monotonic(), text))


def _install_gl_trace():
    """Отладочный контекст OpenGL и журнал действий зданий.

    Контекст с флагом отладки, QOpenGLDebugLogger в синхронном режиме:
    сообщение драйвера приходит внутри вызова, который его вызвал,
    к нему пишется стек Python. Только в проверочном профиле.
    """
    from qgis.PyQt.QtGui import QSurfaceFormat
    import planetx.render.view as rv
    import planetx.render.buildings as rb
    if os.path.exists(TRACE_PATH):
        os.remove(TRACE_PATH)
    plain = rv.surface_format

    def debug_format():
        fmt = plain()
        fmt.setOption(rv.enum(QSurfaceFormat, "FormatOption",
                              "DebugContext"))
        return fmt
    rv.surface_format = debug_format

    upload = rb.Buildings.upload

    def traced_upload(self, count=rb.UPLOADS):
        order = [k for k in self.wanted if k in self.results][:count]
        for key in order:
            mesh, level = self.results[key]
            top = int(mesh.indices.max()) if len(mesh.indices) else -1
            _trace("upload {} v={} i={} max={} level={}".format(
                key, len(mesh.vertices), len(mesh.indices), top, level))
        upload(self, count)
        _trace("uploaded buffers={} vertices={}".format(
            len(self.buffers), self.vertices))
    rb.Buildings.upload = traced_upload

    draw = rb.Buildings.draw

    def traced_draw(self, camera):
        _trace("draw start {}x{} buffers={}".format(
            camera.width, camera.height, len(self.buffers)))
        draw(self, camera)
        _trace("draw end drawn={}".format(self.drawn))
    rb.Buildings.draw = traced_draw

    for name in ("_shot_frame", "_paint_preview", "paintGL"):
        original = getattr(rv.GlobeView, name)

        def wrapped(self, _original=original, _name=name):
            _trace("enter " + _name)
            out = _original(self)
            _trace("leave " + _name)
            return out
        setattr(rv.GlobeView, name, wrapped)


@check(500)
def gl_trace_on():
    """Журнал сообщений драйвера, когда контекст окна уже создан.
    Шаг ставится в PLANETX_STEPS сразу после открытия окна."""
    try:
        from qgis.PyQt.QtOpenGL import QOpenGLDebugLogger
    except ImportError:
        from qgis.PyQt.QtGui import QOpenGLDebugLogger
    view = state["window"].view
    view.makeCurrent()
    logger = QOpenGLDebugLogger(view)
    ok = logger.initialize()

    def logged(message):
        severity = message.severity()
        if getattr(severity, "value", severity) == 8:  # уведомление
            return
        _trace("GL {} {} {}: {}".format(
            int(message.id()), str(message.type()), str(message.severity()),
            message.message()))
        _trace("  stack: " + " | ".join(
            line.strip().replace("\n", " ")
            for line in traceback.format_stack()[-8:-1]))
    logger.messageLogged.connect(logged)
    logger.startLogging(
        QOpenGLDebugLogger.LoggingMode.SynchronousLogging
        if hasattr(QOpenGLDebugLogger, "LoggingMode")
        else QOpenGLDebugLogger.SynchronousLogging)
    view.doneCurrent()
    state["gl_logger"] = logger
    from qgis.PyQt.QtGui import QSurfaceFormat
    import planetx.render.view as rv
    debug = view.context().format().testOption(
        rv.enum(QSurfaceFormat, "FormatOption", "DebugContext"))
    _trace("logger initialized={} debug={}".format(ok, debug))


@check(4000)
def open_globe():
    if GL_TRACE:
        _install_gl_trace()
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
    # «Мои метки» - единственный корень раздела «Метки», есть и пустая.
    # Слои проекта - в своём разделе.
    panel = state["window"].panel
    result["places_folder"] = [
        panel.list.indexOfTopLevelItem(panel.places_group),
        panel.list.topLevelItemCount()]
    result["geo_has_places"] = any(
        panel.geo.topLevelItem(i).text(0) == panel.places_group.text(0)
        for i in range(panel.geo.topLevelItemCount()))

@check(200)
def sidebar():
    window = state["window"]
    view = window.view
    before = view.width()
    if os.environ.get("PLANETX_SIDEBAR_NOOP"):
        # Разбор: только вложенный проход цикла событий, без щелчков.
        QgsApplication.processEvents()
        QgsApplication.processEvents()
        result["sidebar"] = {"noop": True}
        return None
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
    state["frame_at_set"] = view.frame
    # Счёт вызовов страховочного запуска загрузчика подложки.
    pumps = state["pumps"] = []
    if view.loader is not None:
        original = view.loader.pump_if_due
        loader = view.loader

        def counted():
            from planetx.net.loader import Throttle
            pumps.append((Throttle.moving, round(
                Throttle.wait(loader.last_start), 3),
                len(loader.queue.waiting), len(loader.queue.active)))
            original()
        view.loader.pump_if_due = counted
    state["loader_at_set"] = view.loader


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
        "source": state["window"].source.name,
        "frames_since_set": view.frame - state.get("frame_at_set", 0),
        "exposed": view.isVisible() and not view.visibleRegion().isEmpty(),
        "minimized": state["window"].isMinimized(),
        "active_window": QgsApplication.activeWindow() is state["window"],
        "queue": repr(view.loader.queue.__dict__)[:500]
        if view.loader else None,
        "pump_remaining": view.loader.pump_timer.remainingTime()
        if view.loader else None,
        "pump_calls": len(state.get("pumps", [])),
        "pump_samples": state.get("pumps", [])[-6:],
        "heartbeat_active": view._pump_timer.isActive(),
        "loader_same": view.loader is state.get("loader_at_set"),
        "camera_size": [view.camera.width, view.camera.height],
        "view_size": [view.width(), view.height()],
        "pose": [round(view.navigator.pose.lat, 3),
                 round(view.navigator.pose.lon, 3),
                 round(view.navigator.pose.distance)],
        "shot": view.shot is not None}
    if view.loader is not None:
        before = len(view.loader.started)
        view.loader._pump()
        result["labels_state"]["manual_pump_started"] = \
            len(view.loader.started) - before
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
    panel.list.setCurrentItem(None)
    out["button_off_without_choice"] = not panel.tour_button.isEnabled()
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


@check(1000)
def kml_io():
    import zipfile
    window = state["window"]
    store = window.myplaces
    sample = os.path.join(ROOT, "planetx", "tests", "test_kml.py")
    # Образец KML берётся из теста разбора.
    import importlib.util
    spec = importlib.util.spec_from_file_location("test_kml", sample)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, os.path.join(ROOT, "planetx", "core"))
    spec.loader.exec_module(module)
    path = os.path.join(TEMP, "planetx_in.kmz")
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("doc.kml", module.SAMPLE)
    before = len(store.places)
    key = window.import_kml(None, path)
    out = {"folder": store.find(key).name if key else None,
           "added": len(store.places) - before,
           "selected": window.panel.current_folder() == key,
           "flight": window.view.navigator.flight is not None}
    inside = store.places_in(key)
    perm = next((p for p in inside if p.name == "Пермь"), None)
    out["perm_view"] = list(perm.view) if perm and perm.view else None
    out["perm_description"] = perm.description if perm else None
    routes = [f for f in store.folders if f.name == "Маршруты"
              and f.parent == key]
    out["routes_hidden"] = bool(routes) and not routes[0].visible
    out["path_color"] = next((list(p.shape.color) for p in inside
                              if p.name == "Путь"), None)
    exported = os.path.join(TEMP, "planetx_out.kml")
    out["export_ok"] = window.export_kml(key, exported)
    from planetx.core.kml import read_file
    with open(exported, "rb") as fh:
        again = read_file(fh.read())
    out["export_places"] = len(again.places())
    out["export_folders"] = [c.name for c in again.children
                             if hasattr(c, "children")]
    store.remove(key)
    result["kml"] = out


@check(6000)
def extrude():
    from planetx.core.features import Shape
    from planetx.core.navigation import Pose
    from planetx.ui.placeprops import PlaceProperties
    window = state["window"]
    store = window.myplaces
    for place in list(store.places):
        if place.visible:
            store.set_visible(place.key, False)
    # Разбор: PLANETX_EXTRUDE=flat - на земле, lift - поднятые без стен.
    mode = os.environ.get("PLANETX_EXTRUDE", "wall")
    lift = mode != "flat"
    wall = mode == "wall"

    def Shape(*args, **kwargs):  # noqa: N802
        from planetx.core.features import Shape as Base
        if not lift:
            kwargs["height"] = 0.0
        kwargs["extrude"] = kwargs.get("extrude", False) and wall
        return Base(*args, **kwargs)
    keys = [
        store.add(Shape("polygon", [(58.00, 56.20), (58.00, 56.26),
                                    (58.03, 56.26), (58.03, 56.20)],
                        color=(255, 0, 255, 255), fill=(255, 0, 255, 90),
                        name="Коробка", height=500.0, extrude=True)),
        store.add(Shape("line", [(57.98, 56.15), (58.05, 56.30)],
                        color=(0, 255, 255, 255), width=3.0, name="Стена",
                        height=300.0, extrude=True)),
        store.add(Shape("point", [(58.015, 56.17)], name="Мачта",
                        height=200.0, extrude=True))]
    state["extrude_keys"] = keys
    if os.environ.get("PLANETX_NO_SHAPES"):
        # Сравнение: тот же вид без поднятых объектов.
        for key in keys:
            store.set_visible(key, False)
    # Окно свойств: высота стены 300 -> 400.
    dialog = PlaceProperties(store.find(keys[1]), window)
    dialog.height.setValue(400.0)
    store.update(keys[1], dialog.values())
    dialog.deleteLater()
    nav = window.view.navigator
    nav.stop()
    nav.set_pose(Pose(58.015, 56.23, 9000.0, 20.0, 65.0))
    result["extrude"] = {
        "stored": [(round(store.find(k).shape.height), store.find(k)
                    .shape.extrude) for k in keys]}


@check(200)
def extrude_check():
    window = state["window"]
    view = window.view
    image = view.grabFramebuffer()
    image.save(os.path.join(TEMP, "planetx_extrude.png"))
    from planetx.net.loader import image_to_rgba
    rgba = image_to_rgba(image).astype(int)
    r, g, b = rgba[..., 0], rgba[..., 1], rgba[..., 2]
    out = result["extrude"]
    out["magenta_px"] = int(((r > 150) & (g < 110) & (b > 150)).sum())
    out["cyan_px"] = int(((r < 110) & (g > 150) & (b > 150)).sum())
    out["walls"] = sum(1 for item in view.features.buffers
                       if item is not None and "walls" in item.index)
    out["gl_errors"] = dict(view.gl_errors)
    # Отрисовка объектов вручную: исключение посреди неё оставляло бы
    # кадр с выключенной записью глубины.
    from OpenGL.error import GLError
    view.makeCurrent()
    try:
        view.features.dirty = True
        view.features.draw(view.camera, view.store.heights_at,
                           view.store.version, 1.0)
        out["manual_draw"] = "ok"
    except (GLError, TypeError, ValueError, AttributeError, KeyError,
            IndexError) as error:
        lines = traceback.format_exc().splitlines()
        out["manual_draw"] = [line for line in lines
                              if "File" in line or "err" in line.lower()
                              or "description" in line][:14]
    view.doneCurrent()
    marks = [p for p in view._own_marks() if p.name == "Мачта"]
    out["mark_lift"] = marks[0].lift if marks else None
    from planetx.net.loader import Throttle
    out["state"] = {"levels": dict(view.drawn_levels), "frame": view.frame,
                    "moving": Throttle.moving,
                    "flight": view.navigator.flight is not None,
                    "base_busy": view.loader.busy() if view.loader else None,
                    "base_active": len(view.loader.replies)
                    if view.loader else None,
                    "want": len(view.selection.want)
                    if view.selection else None,
                    "camera": [view.camera.width, view.camera.height],
                    "errors": {str(k): v for k, v in list(
                        window.errors.items())[:4]},
                    "started": len(view.loader.started)
                    if view.loader else None,
                    "queue": repr(view.loader.queue.__dict__)[:600]
                    if view.loader else None}
    if view.loader is not None:
        import time as _time
        loader = view.loader
        out["pump"] = {"timer_active": loader.pump_timer.isActive(),
                       "remaining_ms": loader.pump_timer.remainingTime(),
                       "since_last": round(_time.monotonic()
                                           - loader.last_start, 3),
                       "throttle_since": round(_time.monotonic()
                                               - Throttle.last, 3),
                       "wait": round(Throttle.wait(loader.last_start), 3)}
        loader._pump()
        out["pump"]["active_after_manual"] = len(loader.replies)
    for key in state["extrude_keys"]:
        window.myplaces.remove(key)


@check(300)
def pump_stall():
    # Таймер запуска просрочен, а очередь событий не дала ему сработать.
    # Загрузка вставала совсем, 28 сентября 2026 года. _later обязан
    # запустить запрос без таймера.
    import time as _time
    from planetx.net.loader import Throttle
    loader = state["window"].view.loader
    moving = Throttle.moving
    # Проверяется запуск без таймера, а не общий отсчёт движения.
    Throttle.moving = False
    loader.queue.want((15, 21600, 9800), 5.0, now=_time.monotonic())
    loader.last_start = _time.monotonic() - 1.0
    loader.pump_timer.start(1)
    _time.sleep(0.02)
    # Считаются вызовы запуска: число запросов упирается в предел
    # одновременных, когда загрузчик занят.
    calls = []
    pump = loader._pump
    loader._pump = lambda: calls.append(1) or pump()
    try:
        loader._later()
    finally:
        del loader._pump
    # Показанный кадр запускает ждущий запрос, даже когда таймер
    # запуска не срабатывает.
    loader.queue.want((15, 21601, 9800), 5.0, now=_time.monotonic())
    loader.last_start = _time.monotonic() - 1.0
    loader.pump_timer.start(600000)
    swap = []
    loader._pump = lambda: swap.append(1) or pump()
    try:
        state["window"].view.frameSwapped.emit()
    finally:
        del loader._pump
    Throttle.moving = moving
    result["pump_stall"] = {"pumped": len(calls), "on_swap": len(swap),
                            "moving_before": moving,
                            "view_moving": state["window"].view.navigator
                            .flight is not None}


@check(2500)
def idle_rewant():
    # Вид ждёт тайлы, загрузчик пуст, просьба уже «отправлена» и кадров
    # нет. Так картинка оставалась грубой, 28 сентября 2026 года.
    import time as _time
    from planetx.core.navigation import Pose
    view = state["window"].view
    view.navigator.stop()
    view.navigator.set_pose(Pose(-33.9, 18.4, 30000.0))
    view.repaint()
    want = dict(view.selection.want) if view.selection else {}
    view.loader.retain([])
    view.loader.queue.waiting.clear()
    view._wanted = frozenset(want)
    view._wanted_at = _time.monotonic()
    state["rewant"] = {"want": len(want),
                       "started": len(view.loader.started),
                       "frame": view.frame}


@check(200)
def idle_rewant_check():
    view = state["window"].view
    out = state["rewant"]
    out["started_after"] = len(view.loader.started) - out.pop("started")
    out["frames_after"] = view.frame - out.pop("frame")
    result["idle_rewant"] = out


def _navigation_mode(name):
    """Режим временного контроллера: в QGIS 4 областное имя в Qgis."""
    from qgis.core import Qgis, QgsTemporalNavigationObject
    scoped = getattr(Qgis, "TemporalNavigationMode", None)
    if scoped is not None and hasattr(scoped, name):
        return getattr(scoped, name)
    old = {"Animated": "Animated", "Disabled": "NavigationOff"}[name]
    return getattr(QgsTemporalNavigationObject.NavigationMode, old)


@check(1500)
def tracks():
    from qgis.core import (QgsDateTimeRange, QgsFeature, QgsGeometry,
                           QgsInterval, QgsPointXY, QgsVectorLayer)
    from qgis.PyQt.QtCore import QDateTime
    window = state["window"]
    layer = QgsVectorLayer(
        "Point?crs=EPSG:4326&field=t:datetime&field=obj:string",
        "Трек теста", "memory")
    base = QDateTime.fromString("2026-09-28T10:00:00", "yyyy-MM-ddTHH:mm:ss")
    rows = [("car", 0, 58.00, 56.00), ("car", 600, 58.05, 56.00),
            ("car", 1200, 58.05, 56.10), ("elk", 300, 57.95, 56.20),
            ("elk", 900, 57.95, 56.30)]
    features = []
    for obj, dt, lat, lon in rows:
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
        f["t"] = base.addSecs(dt)
        f["obj"] = obj
        features.append(f)
    layer.dataProvider().addFeatures(features)
    QgsProject.instance().addMapLayer(layer)
    state["track_layer"] = layer
    window.tracks.set_track(layer, {"time": "t", "object": "obj",
                                    "color": [255, 80, 40, 255],
                                    "follow": True})
    controller = window.tracks.controller
    controller.setTemporalExtents(QgsDateTimeRange(base, base.addSecs(1200)))
    controller.setFrameDuration(QgsInterval(60))
    controller.setNavigationMode(_navigation_mode("Animated"))
    controller.setCurrentFrameNumber(4)  # 10:04-10:05
    tracker = window.tracks
    moment = tracker.moment
    shapes = tracker.shapes()
    flight = window.view.navigator.flight
    from planetx.ui.track import seconds
    out = {"moment_min": round((moment - seconds(base))
                               / 60.0, 1) if moment is not None else None,
           "shapes": sorted((s.kind, s.name, len(s.points))
                            for s in shapes),
           "glide": type(flight[1]).__name__ if flight else None,
           "target": [round(flight[1].end.lat, 4), round(flight[1].end.lon,
                                                         4),
                      round(flight[1].end.heading, 1)] if flight else None,
           "on_globe": sum(1 for s in window.view.features.shapes
                           if s.name in ("car", "elk"))}
    # Шаги анимации не должны перечитывать точки треков.
    reloads = []
    reload = tracker.reload
    tracker.reload = lambda: reloads.append(1) or reload()
    for _ in range(3):
        controller.next()
        QgsApplication.processEvents()
    del tracker.reload
    out["reloads_on_steps"] = len(reloads)
    controller.setNavigationMode(_navigation_mode("Disabled"))
    tracker._time_changed()
    out["whole"] = sorted((s.kind, s.name, len(s.points))
                          for s in tracker.shapes())
    result["tracks"] = out


@check(200)
def tracks_off():
    window = state["window"]
    window.tracks.set_track(state["track_layer"], None)
    result["tracks"]["after_remove"] = len(window.tracks.shapes())
    # После close сигнал контроллера в менеджер треков не идёт: шаг
    # времени не меняет его момент.
    tracker = window.tracks
    controller = tracker.controller
    controller.setNavigationMode(_navigation_mode("Animated"))
    controller.setCurrentFrameNumber(2)
    QgsApplication.processEvents()
    tracker.close()
    before = tracker.moment
    controller.setCurrentFrameNumber(7)
    QgsApplication.processEvents()
    result["tracks"]["moment_kept_after_close"] = tracker.moment == before
    controller.setNavigationMode(_navigation_mode("Disabled"))


@check(300)
def load_status():
    # Шаг 14: вставшая загрузка и тяжёлые метки видны в строке
    # состояния, спокойный вид - без хвоста.
    import time as _time
    window = state["window"]
    view = window.view
    window.refresh()
    view._heartbeat()
    out = {"calm": window.status.text().split(chr(10))[0],
           "missing": view.load_missing}
    missing = view._missing
    view._missing = lambda sel: 3
    view.last_arrival = _time.monotonic() - 12.0
    view._heartbeat()
    out["stalled"] = window.status.text().split(chr(10))[0]
    view._missing = missing
    view.last_arrival = _time.monotonic()
    view._heartbeat()
    count = view.object_vertices
    view.object_vertices = lambda: 250000
    window._show_state()
    out["heavy"] = window.status.text().split(chr(10))[0]
    view.object_vertices = count
    window._show_state()
    result["load_status"] = out


@check(7000)
def stall_wait():
    # Пауза дольше STALL_SHOW после idle_rewant.
    return None


@check(200)
def stall_read():
    window = state["window"]
    result["stall_read"] = {"status": window.status.text().split(chr(10))[0],
                            "stalled": window.view.load_stalled}


SCENE_PATH = os.path.join(TEMP, "planetx_check.planetx")
SCENE_EXPECT = os.path.join(TEMP, "planetx_scene_expect.json")


@check(1500)
def scene_save():
    # Шаг 12, первый запуск: сцена в файл. Второй запуск - scene_open.
    from qgis.core import (QgsDateTimeRange, QgsFeature, QgsGeometry,
                           QgsInterval, QgsPointXY, QgsVectorFileWriter,
                           QgsVectorLayer)
    from qgis.PyQt.QtCore import QDateTime
    from planetx.core.features import Shape
    from planetx.core.navigation import Pose
    window = state["window"]
    gpkg = os.path.join(TEMP, "planetx_scene_layer.gpkg")
    memory = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string",
                            "wells", "memory")
    f = QgsFeature(memory.fields())
    f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(56.25, 58.0)))
    f["name"] = "w1"
    memory.dataProvider().addFeatures([f])
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = "wells"
    QgsVectorFileWriter.writeAsVectorFormatV3(
        memory, gpkg, QgsProject.instance().transformContext(), options)
    layer = QgsVectorLayer(gpkg + "|layername=wells", "Скважины сцены",
                           "ogr")
    QgsProject.instance().addMapLayer(layer)
    window.set_layer_shown(layer.id(), True)
    store = window.myplaces
    folder = store.add_folder("Сцена теста")
    store.add(Shape("point", [(58.01, 56.25)], name="Старт"),
              view=(3000.0, 40.0, 50.0), folder=folder)
    store.add(Shape("point", [(58.05, 56.35)], name="Финиш"),
              folder=folder)
    window.panel.select_place(folder)
    controller = window.tracks.controller
    base = QDateTime.fromString("2026-09-28T10:00:00", "yyyy-MM-ddTHH:mm:ss")
    controller.setTemporalExtents(QgsDateTimeRange(base, base.addSecs(3600)))
    controller.setFrameDuration(QgsInterval(300))
    controller.setNavigationMode(_navigation_mode("Animated"))
    controller.setCurrentFrameNumber(3)
    nav = window.view.navigator
    nav.stop()
    nav.set_pose(Pose(58.02, 56.28, 15000.0, 25.0, 60.0))
    ok = window.save_scene(SCENE_PATH)
    expect = {"camera": [58.02, 56.28, 15000.0, 25.0, 60.0],
              "frame": 3, "source": layer.source(),
              "places": ["Старт", "Финиш"]}
    with open(SCENE_EXPECT, "w", encoding="utf-8") as fh:
        json.dump(expect, fh, ensure_ascii=False)
    store.remove(folder)
    result["scene_save"] = {"saved": ok,
                            "size": os.path.getsize(SCENE_PATH)
                            if os.path.exists(SCENE_PATH) else 0}


@check(12000)
def scene_open():
    window = state["window"]
    with open(SCENE_EXPECT, encoding="utf-8") as fh:
        state["scene_expect"] = json.load(fh)
    state["scene_key"] = window.open_scene(SCENE_PATH)


@check(200)
def scene_open_check():
    window = state["window"]
    expect = state["scene_expect"]
    pose = window.view.navigator.pose
    project = QgsProject.instance()
    shown = [project.mapLayer(i) for i in window.shown_layers()]
    key = state["scene_key"]
    places = [p.name for p in window.myplaces.places_in(key)] if key \
        else []
    controller = window.tracks.controller
    window._place_action("tour", key or "")
    stops = [s.name for s in window.tour.stops]
    window.tour.stop()
    got = [round(pose.lat, 4), round(pose.lon, 4), round(pose.distance, 1),
           round(pose.heading, 2), round(pose.tilt, 2)]
    result["scene_open"] = {
        "camera_same": got == [round(v, 4) if i < 2 else round(v, 1)
                               if i == 2 else round(v, 2)
                               for i, v in enumerate(expect["camera"])],
        "camera": got,
        "frame_same": controller.currentFrameNumber() == expect["frame"],
        "layers": [l.source() for l in shown if l is not None],
        "layer_same": any(l is not None and l.source() == expect["source"]
                          for l in shown),
        "places": places, "tour_stops": stops,
        "status": window.status.text().split(chr(10))[0]}
    if key:
        window.myplaces.remove(key)


@check(200)
def scene_password():
    # Пароль базы данных не уходит в файл сцены.
    # Слой не создаётся: он пытался бы подключиться к серверу.
    from planetx.ui.scene import clean_uri
    uri = ("dbname='gis' host=db.example port=5432 user='geo' "
           "password='s3cret' key='id' srid=4326 type=Point "
           "table=\"public\".\"wells\" (geom)")
    cleaned = clean_uri("postgres", uri)
    result["scene_password"] = {"left": "s3cret" in cleaned,
                                "user_kept": "geo" in cleaned,
                                "file_same": clean_uri("ogr", "a.gpkg")
                                == "a.gpkg"}


RECORD_DIRS = [os.path.join(TEMP, "planetx_record_a"),
               os.path.join(TEMP, "planetx_record_b")]
RECORD_LIMIT = 600.0  # с на одну запись


def _record(folder):
    """Шаг 13: тур из двух остановок с растущим треком в папку."""
    import shutil
    import time as _time
    from planetx.core.tour import Stop
    window = state["window"]
    if os.path.isdir(folder):
        shutil.rmtree(folder)
    os.makedirs(folder)
    state["record_done"] = None
    if "record_link" not in state:
        state["record_link"] = window.recorder.done.connect(
            lambda ok, text: state.__setitem__("record_done", (ok, text)))
    window.tour.bar.pause.setValue(0.4)
    window.tour.start([Stop("A", 58.00, 56.02, 9000.0, 10.0, 40.0),
                       Stop("B", 58.03, 56.06, 7000.0, 40.0, 50.0)])
    state["record_started"] = _time.monotonic()
    state["record_began"] = window.record_tour(folder)


@check(500)
def record_setup():
    from qgis.core import (QgsDateTimeRange, QgsFeature, QgsGeometry,
                           QgsInterval, QgsPointXY, QgsVectorLayer)
    from qgis.PyQt.QtCore import QDateTime
    window = state["window"]
    layer = QgsVectorLayer(
        "Point?crs=EPSG:4326&field=t:datetime&field=obj:string",
        "Трек записи", "memory")
    base = QDateTime.fromString("2026-09-28T10:00:00", "yyyy-MM-ddTHH:mm:ss")
    features = []
    for i in range(7):
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromPointXY(
            QgsPointXY(56.02 + 0.007 * i, 58.00 + 0.005 * i)))
        f["t"] = base.addSecs(200 * i)
        f["obj"] = "car"
        features.append(f)
    layer.dataProvider().addFeatures(features)
    QgsProject.instance().addMapLayer(layer)
    state["record_layer"] = layer
    window.tracks.set_track(layer, {"time": "t", "object": "obj",
                                    "color": [255, 80, 40, 255],
                                    "follow": False})
    controller = window.tracks.controller
    controller.setTemporalExtents(QgsDateTimeRange(base, base.addSecs(1200)))
    controller.setFrameDuration(QgsInterval(60))
    controller.setNavigationMode(_navigation_mode("Animated"))
    controller.setCurrentFrameNumber(0)
    _record(RECORD_DIRS[0])


def _record_wait(name):
    import time as _time
    window = state["window"]
    spent = _time.monotonic() - state["record_started"]
    if state["record_done"] is None and spent < RECORD_LIMIT:
        return 1000
    result.setdefault("record", {})[name] = {
        "began": state["record_began"], "done": state["record_done"],
        "seconds": round(spent, 1),
        "status": window.status.text().split(chr(10))[0]}
    return None


@check(500)
def record_wait_a():
    return _record_wait("a")


@check(500)
def record_again():
    _record(RECORD_DIRS[1])


@check(500)
def record_wait_b():
    return _record_wait("b")


@check(200)
def record_check():
    window = state["window"]
    runs = []
    for folder in RECORD_DIRS:
        with open(os.path.join(folder, "frames.json"),
                  encoding="utf-8") as fh:
            data = json.load(fh)
        pngs = sorted(n for n in os.listdir(folder) if n.endswith(".png"))
        runs.append((data, pngs))
    (a, pa), (b, pb) = runs
    diff = max(max(abs(x - y) for x, y in zip(fa["pose"], fb["pose"]))
               for fa, fb in zip(a["frames"], b["frames"]))
    moments = [f["moment"] for f in a["frames"]]
    out = result["record"]
    out.update({
        "fps": a["fps"], "count": [a["count"], b["count"]],
        "png": [len(pa), len(pb)],
        "size": [a["width"], a["height"]],
        "incomplete": [len(a["incomplete"]), len(b["incomplete"])],
        "pose_diff_max": diff,
        "moments_same": moments == [f["moment"] for f in b["frames"]],
        "moment_span_min": round((moments[-1] - moments[0]) / 60.0, 2),
        "first_pose": [round(v, 4) for v in a["frames"][0]["pose"]],
        "tracks_released": not window.tracks.held})
    window.tracks.set_track(state["record_layer"], None)
    window.tracks.controller.setNavigationMode(_navigation_mode("Disabled"))


@check(500)
def place_names():
    # Названия новых меток с номером по виду и значки строк списка.
    from planetx.core.features import Shape
    from planetx.ui.panel import PLACE_ROLE
    window = state["window"]
    store = window.myplaces
    before = {p.key for p in store.places}
    window._open_place()
    dialog = window.place_dialog
    d = window.drawer
    out = {}
    dialog.tabs.setCurrentIndex(0)
    first = dialog.name.text()
    d.add(58.02, 56.2)
    window._save_place()
    out["point"] = [first, dialog.name.text()]
    dialog.tabs.setCurrentIndex(1)
    out["path"] = dialog.name.text()
    dialog.name.setText("Свой путь")
    dialog.tabs.setCurrentIndex(2)
    out["own_kept"] = dialog.name.text()
    dialog.name.clear()
    dialog.tabs.setCurrentIndex(0)
    out["after_clear"] = dialog.name.text()
    window.place_dialog.close()
    store.add(Shape("line", [(58.0, 56.1), (58.01, 56.2)], name="Линия"))
    store.add(Shape("polygon", [(57.97, 56.1), (57.97, 56.2),
                                (57.99, 56.15)], name="Поле"))
    store.add(Shape("point", [(58.0, 56.3)], name="Вид"),
              view=(3000.0, 0.0, 45.0))
    icons = {}
    group = window.panel.places_group

    def look(parent):
        for i in range(parent.childCount()):
            child = parent.child(i)
            key = child.data(0, PLACE_ROLE)
            if key not in before and child.text(0) in (
                    out["point"][0], "Линия", "Поле", "Вид"):
                icons[child.text(0)] = child.icon(0).cacheKey() \
                    if not child.icon(0).isNull() else None
            look(child)
    look(group)
    out["icons_set"] = sum(1 for v in icons.values() if v is not None)
    out["icons_distinct"] = len(set(icons.values()))
    for p in list(store.places):
        if p.key not in before:
            store.remove(p.key)
    result["place_names"] = out


@check(500)
def multi_select():
    # Несколько выделенных строк «Моих меток»: перенос, скрытие,
    # удаление клавишей Del. Корень выделен жирным шрифтом.
    from qgis.PyQt.QtCore import QEvent, Qt
    from qgis.PyQt.QtGui import QKeyEvent
    from qgis.PyQt.QtWidgets import QMessageBox
    from planetx.core.features import Shape
    from planetx.ui import window as window_module
    window = state["window"]
    store = window.myplaces
    panel = window.panel
    tree = panel.list
    count0 = len(store.places)
    folder = store.add_folder("Выбор теста")
    keys = []
    for i in range(3):
        store.add(Shape("point", [(58.0 + 0.01 * i, 56.2)],
                        name="Выбор %d" % i))
        keys.append([p.key for p in store.places
                     if p.name == "Выбор %d" % i][0])
    store.add(Shape("point", [(58.1, 56.3)], name="Внутри"), folder=folder)
    out = {"root_bold": panel.places_group.font(0).bold(),
           "root_icon": not panel.places_group.icon(0).isNull()}

    from planetx.ui.panel import PLACE_ROLE

    def select_role(chosen):
        tree.clearSelection()

        def look(parent):
            for i in range(parent.childCount()):
                child = parent.child(i)
                if child.data(0, PLACE_ROLE) in chosen:
                    child.setSelected(True)
                look(child)
        look(panel.places_group)
    select_role([keys[2], keys[0]])
    out["selected"] = tree.selected_keys() == [keys[0], keys[2]]
    panel.places_moved.emit([keys[0], keys[2]], folder, 0)
    inside = [p.name for p in store.places_in(folder)]
    out["moved_into_folder"] = inside
    panel.places_action.emit("hide", [folder])
    out["hidden"] = sorted(p.name for p in store.places_in(folder)
                           if not p.visible)
    panel.places_action.emit("show", [folder])
    asked = []
    old = window_module.QMessageBox.question
    window_module.QMessageBox.question = staticmethod(
        lambda *a: asked.append(a[2]) or QMessageBox.StandardButton.Yes
        if hasattr(QMessageBox, "StandardButton") else QMessageBox.Yes)
    try:
        select_role([folder, keys[1]])
        tree.setFocus()
        QgsApplication.sendEvent(tree, QKeyEvent(
            QEvent.Type.KeyPress if hasattr(QEvent, "Type")
            else QEvent.KeyPress, Qt.Key.Key_Delete if hasattr(Qt, "Key")
            else Qt.Key_Delete, Qt.KeyboardModifier.NoModifier
            if hasattr(Qt, "KeyboardModifier") else Qt.NoModifier))
    finally:
        window_module.QMessageBox.question = old
    out["asked"] = len(asked)
    out["left"] = len(store.places) - count0
    out["folder_gone"] = store.find(folder) is None
    result["multi_select"] = out


@check(300)
def accordion():
    # Разделы панели сворачиваются, место отходит открытым разделам.
    # Слои проекта лежат в своём списке, не в дереве меток.
    from qgis.core import QgsVectorLayer
    window = state["window"]
    panel = window.panel
    layer = QgsVectorLayer("Point?crs=EPSG:4326", "Слой раздела", "memory")
    QgsProject.instance().addMapLayer(layer)
    QgsApplication.processEvents()
    places, project, base = panel.sections
    out = {"titles": [s.header.text() for s in panel.sections],
           "layer_in_own_list": any(
               panel.layers.topLevelItem(i).text(0).startswith(
                   "Слой раздела")
               for i in range(panel.layers.topLevelItemCount())),
           "tree_tops": panel.list.topLevelItemCount()}
    before = [s.height() for s in panel.sections]
    project.set_open(False)
    QgsApplication.processEvents()
    after = [s.height() for s in panel.sections]
    out["heights_open"] = before
    out["heights_project_closed"] = after
    out["closed_is_header"] = after[1] <= project.header.sizeHint().height()
    out["others_grew"] = after[0] + after[2] > before[0] + before[2]
    project.set_open(True)
    QgsApplication.processEvents()
    out["reopened"] = project.height() > project.header.sizeHint().height()
    asked = []
    window.properties = None
    window._show_properties = lambda: asked.append(1)
    window.toolbar.properties_clicked.disconnect()
    window.toolbar.properties_clicked.connect(window._show_properties)
    window.toolbar.properties.click()
    out["header_buttons"] = base.row.count()
    out["properties_button"] = len(asked)
    flown = []
    panel.fly_to_layer.connect(lambda layer: flown.append(layer.name()))
    row = next(panel.layers.topLevelItem(i)
               for i in range(panel.layers.topLevelItemCount())
               if panel.layers.topLevelItem(i).text(0).startswith(
                   "Слой раздела"))
    panel.layers.itemDoubleClicked.emit(row, 0)
    out["double_click_flies"] = flown
    panel.grab().save(os.path.join(TEMP, "planetx_panel.png"))
    QgsProject.instance().removeMapLayer(layer.id())
    result["accordion"] = out


def _qt(owner, scope, name):
    return getattr(getattr(owner, scope, owner), name)


def _send_mouse(view, kind, x, y, button, buttons, mods=None):
    from qgis.PyQt.QtCore import QEvent, QPoint, QPointF, Qt
    from qgis.PyQt.QtGui import QMouseEvent
    mods = mods if mods is not None else _qt(Qt, "KeyboardModifier",
                                             "NoModifier")
    event = QMouseEvent(_qt(QEvent, "Type", kind), QPointF(x, y),
                        QPointF(view.mapToGlobal(QPoint(int(x), int(y)))),
                        button, buttons, mods)
    QgsApplication.sendEvent(view, event)


def _send_key(view, name, mods=None):
    from qgis.PyQt.QtCore import QEvent, Qt
    from qgis.PyQt.QtGui import QKeyEvent
    mods = mods if mods is not None else _qt(Qt, "KeyboardModifier",
                                             "NoModifier")
    QgsApplication.sendEvent(view, QKeyEvent(
        _qt(QEvent, "Type", "KeyPress"), _qt(Qt, "Key", name), mods))


@check(3000)
def ge_nav():
    # Навигация Google Earth: двойные щелчки, правая кнопка, Ctrl,
    # клавиши. Вид - неподвижная поза над Пермью.
    from qgis.PyQt.QtCore import Qt
    from planetx.core.navigation import Pose, ground_under
    from planetx.core.ellipsoid import ecef_to_geodetic
    view = state["window"].view
    nav = view.navigator
    left = _qt(Qt, "MouseButton", "LeftButton")
    right = _qt(Qt, "MouseButton", "RightButton")
    none = _qt(Qt, "MouseButton", "NoButton")
    ctrl = _qt(Qt, "KeyboardModifier", "ControlModifier")
    shift = _qt(Qt, "KeyboardModifier", "ShiftModifier")
    ratio = view.devicePixelRatioF()
    cx, cy = view.width() / 2.0, view.height() / 2.0

    def reset():
        nav.stop()
        nav.set_pose(Pose(58.0105, 56.2294, 20000.0, 30.0, 40.0))
        view._fit_camera()
        nav.pose.apply(view.camera)

    out = {}
    reset()
    x, y = cx + 150, cy - 60
    point = ground_under(view.camera, x * ratio, y * ratio)
    lat, lon, _ = ecef_to_geodetic(point)
    _send_mouse(view, "MouseButtonDblClick", x, y, left, left)
    flight = nav.flight[1] if nav.flight else None
    out["double_left"] = None if flight is None else {
        "distance": round(flight.end.distance, 1),
        "to_point_m": round(math.hypot(
            (flight.end.lat - float(lat)) * 111320.0,
            (flight.end.lon - float(lon)) * 111320.0
            * math.cos(math.radians(float(lat)))), 3),
        "heading": flight.end.heading, "tilt": flight.end.tilt}
    reset()
    _send_mouse(view, "MouseButtonDblClick", x, y, right, right)
    flight = nav.flight[1] if nav.flight else None
    out["double_right"] = round(flight.end.distance, 1) if flight else None
    reset()
    _send_mouse(view, "MouseButtonPress", cx, cy, right, right)
    _send_mouse(view, "MouseMove", cx, cy - 100, none, right)
    _send_mouse(view, "MouseButtonRelease", cx, cy - 100, right, none)
    out["right_drag_up"] = round(nav.pose.distance, 1)
    reset()
    eye0, _ = nav.pose.eye_rotation()
    _send_mouse(view, "MouseButtonPress", cx, cy, left, left, ctrl)
    _send_mouse(view, "MouseMove", cx + 50, cy - 20, none, left, ctrl)
    _send_mouse(view, "MouseButtonRelease", cx + 50, cy - 20, left, none,
                ctrl)
    eye1, _ = nav.pose.eye_rotation()
    out["ctrl_look"] = {"heading": round(nav.pose.heading, 3),
                        "tilt": round(nav.pose.tilt, 3),
                        "eye_moved_m": round(float(
                            ((eye1 - eye0) ** 2).sum() ** 0.5), 3)}
    reset()
    view.setFocus()
    _send_key(view, "Key_Up")
    out["arrow_up_m"] = round(math.hypot(
        (nav.pose.lat - 58.0105) * 111320.0,
        (nav.pose.lon - 56.2294) * 111320.0
        * math.cos(math.radians(58.0105))), 1)
    reset()
    _send_key(view, "Key_Left", shift)
    out["shift_left_heading"] = round(nav.pose.heading, 3)
    reset()
    _send_key(view, "Key_R")
    flight = nav.flight[1] if nav.flight else None
    out["key_r"] = [flight.end.heading, flight.end.tilt] if flight else None
    _send_key(view, "Key_Space")
    out["space_stops"] = nav.flight is None
    reset()
    _send_key(view, "Key_PageUp")
    out["page_up_zooming"] = nav.zooming is not None
    nav.stop()
    result["ge_nav"] = out


def _pad_reset():
    from planetx.core.navigation import Pose
    view = state["window"].view
    view.navigator.stop()
    view.navigator.set_pose(Pose(58.0105, 56.2294, 20000.0, 40.0, 30.0))
    view._fit_camera()
    view.navigator.pose.apply(view.camera)


def _pad_press(name, x, y):
    from qgis.PyQt.QtCore import Qt
    pad = state["window"].navpad
    left = _qt(Qt, "MouseButton", "LeftButton")
    _send_mouse(pad, "MouseButtonPress", x, y, left, left)
    state["pad_" + name] = state["window"].view.navigator.pose.copy()


def _pad_release(x, y):
    from qgis.PyQt.QtCore import Qt
    pad = state["window"].navpad
    _send_mouse(pad, "MouseButtonRelease", x, y,
                _qt(Qt, "MouseButton", "LeftButton"),
                _qt(Qt, "MouseButton", "NoButton"))


@check(600)
def navpad_plus():
    from planetx.ui import navpad as ui
    window = state["window"]
    pad = window.navpad
    view = window.view
    result["navpad"] = {
        "visible": pad.isVisible(),
        "top_right": [view.width() - pad.x() - pad.width(), pad.y()]}
    pad.grab().save(os.path.join(TEMP, "planetx_navpad.png"))
    _pad_reset()
    _pad_press("plus", *ui.PLUS)


@check(600)
def navpad_move():
    from planetx.ui import navpad as ui
    _pad_release(*ui.PLUS)
    pose = state["window"].view.navigator.pose
    result["navpad"]["plus_ratio"] = round(
        pose.distance / state["pad_plus"].distance, 3)
    _pad_reset()
    _pad_press("move", ui.MOVE[0], ui.MOVE[1] - 20)


@check(600)
def navpad_look():
    from planetx.ui import navpad as ui
    _pad_release(ui.MOVE[0], ui.MOVE[1] - 20)
    pose = state["window"].view.navigator.pose
    start = state["pad_move"]
    result["navpad"]["move_m"] = round(math.hypot(
        (pose.lat - start.lat) * 111320.0,
        (pose.lon - start.lon) * 111320.0
        * math.cos(math.radians(start.lat))), 1)
    _pad_reset()
    _pad_press("look", ui.RING[0] + 12, ui.RING[1])


@check(300)
def navpad_ring():
    from qgis.PyQt.QtCore import Qt
    from planetx.ui import navpad as ui
    _pad_release(ui.RING[0] + 12, ui.RING[1])
    view = state["window"].view
    nav = view.navigator
    pad = state["window"].navpad
    out = result["navpad"]
    out["look_heading"] = round(nav.pose.heading - state["pad_look"].heading,
                                2)
    # Кольцо: от 90° (справа) к 120° по часовой.
    _pad_reset()
    left = _qt(Qt, "MouseButton", "LeftButton")
    r = (ui.R_IN + ui.R_OUT) / 2.0
    x0, y0 = ui.RING[0] + r, ui.RING[1]
    a = math.radians(120.0)
    x1, y1 = ui.RING[0] + r * math.sin(a), ui.RING[1] - r * math.cos(a)
    _send_mouse(pad, "MouseButtonPress", x0, y0, left, left)
    _send_mouse(pad, "MouseMove", x1, y1, _qt(Qt, "MouseButton", "NoButton"),
                left)
    _pad_release(x1, y1)
    out["ring_heading"] = round(nav.pose.heading, 2)
    # Буква N: азимут 40°, щелчок по ней - перелёт к северу.
    _pad_reset()
    n = math.radians(-40.0)
    nx = ui.RING[0] + ui.R_NORTH * math.sin(n)
    ny = ui.RING[1] - ui.R_NORTH * math.cos(n)
    _send_mouse(pad, "MouseButtonPress", nx, ny, left, left)
    _pad_release(nx, ny)
    flight = nav.flight[1] if nav.flight else None
    out["north_flight"] = flight.end.heading if flight else None
    nav.stop()
    # Ползунок: середина дорожки - расстояние slider_distance(0.5).
    _pad_reset()
    mid = (ui.TRACK[0] + ui.TRACK[1]) / 2.0
    _send_mouse(pad, "MouseButtonPress", ui.CX, mid, left, left)
    _pad_release(ui.CX, mid)
    out["slider_distance"] = round(nav.pose.distance)
    # Показ: органы видны всегда, у угла проявлены, вдали - контур.
    ratio = view.devicePixelRatioF()
    view.hovered.emit(100 * ratio, (view.height() - 100) * ratio)
    QgsApplication.processEvents()
    out["far"] = [pad.isVisible(), pad.near]
    state["window"].grab().save(os.path.join(TEMP, "planetx_navpad_far.png"))
    view.hovered.emit((view.width() - 30) * ratio, 30 * ratio)
    QgsApplication.processEvents()
    out["near"] = [pad.isVisible(), pad.near]
    state["window"].grab().save(os.path.join(TEMP, "planetx_navpad_near.png"))
    view.hovered.emit(-1, -1)
    out["gone"] = [pad.isVisible(), pad.near]
    _pad_reset()
    view.update()


@check(300)
def place_props_live():
    # Окно свойств метки немодальное, правки видны на глобусе сразу,
    # «Отмена» возвращает вид, «OK» пишет в файл. Ползунок высоты.
    from planetx.core.features import Shape
    window = state["window"]
    store = window.myplaces
    store.add(Shape("point", [(58.0, 56.2)], name="Свойства теста"))
    place = [p for p in store.places if p.name == "Свойства теста"][0]
    key = place.key

    def on_globe():
        return [s.height for s in window.view.features.shapes
                if s.name in ("Свойства теста", "Свойства теста 2")]
    out = {}
    window._place_action("properties", key)
    dialog = window.prop_dialogs[key]
    out["modal"] = dialog.isModal()
    out["visible"] = dialog.isVisible()
    dialog.slider.setValue(500)
    out["slider_height"] = dialog.height.value()
    out["preview_height"] = on_globe()
    dialog.name.setText("Свойства теста 2")
    out["preview_names"] = sorted(s.name for s in window.view.features.shapes
                                  if s.name.startswith("Свойства теста"))
    dialog.reject()
    QgsApplication.processEvents()
    out["after_cancel"] = on_globe()
    out["file_after_cancel"] = store.find(key).shape.height
    window._place_action("properties", key)
    dialog = window.prop_dialogs[key]
    dialog.height.setValue(3600.0)
    out["slider_for_3600"] = dialog.slider.value()
    dialog.accept()
    QgsApplication.processEvents()
    saved = [p for p in store.places if p.name == "Свойства теста"][0]
    out["file_after_ok"] = saved.shape.height
    out["globe_after_ok"] = on_globe()
    out["dialogs_left"] = len(window.prop_dialogs)
    store.remove(saved.key)
    result["place_props_live"] = out


@check(300)
def copy_paste():
    # Копировать и вставить: KML в буфере обмена, правка текста как
    # в блокноте, вставка в другую папку без обёртки, клавиши.
    from qgis.PyQt.QtCore import QEvent, Qt
    from qgis.PyQt.QtGui import QKeyEvent
    from qgis.PyQt.QtWidgets import QApplication
    from planetx.core.features import Shape
    from planetx.ui.panel import PLACE_ROLE
    window = state["window"]
    store = window.myplaces
    panel = window.panel
    source = store.add_folder("Копия исходник")
    store.add(Shape("point", [(58.0, 56.2)], name="Копия А"),
              folder=source)
    store.add(Shape("line", [(58.0, 56.2), (58.1, 56.3)], name="Копия Б",
                    height=120.0, extrude=True), folder=source)
    store.add(Shape("point", [(58.2, 56.4)], name="Копия В"))
    single = [p.key for p in store.places if p.name == "Копия В"][0]
    target = store.add_folder("Копия цель")
    out = {}
    panel.places_action.emit("copy", [source, single])
    clip = QApplication.clipboard().text()
    out["clip_is_kml"] = clip.startswith("<?xml") and "<kml" in clip
    out["clip_names"] = [n for n in ("Копия исходник", "Копия А", "Копия Б",
                                     "Копия В") if n in clip]
    # Правка в блокноте: переименование и только текст в буфере.
    QApplication.clipboard().setText(clip.replace("Копия А", "Правка А"))
    panel.place_action.emit("paste", target)
    inside = [p.name for p in store.places_in(target)]
    out["pasted_names"] = sorted(inside)
    out["pasted_folder"] = [f.name for f in store.folders
                            if f.name == "Копия исходник"]
    line = [p for p in store.places_in(target) if p.name == "Копия Б"]
    out["line_kept"] = [line[0].shape.height, bool(line[0].shape.extrude)] \
        if line else None
    # Мусор в буфере - сообщение и ничего не вставлено.
    count = len(store.places)
    QApplication.clipboard().setText("не KML")
    out["garbage_pasted"] = window.paste_places(None)
    out["garbage_same_count"] = len(store.places) == count
    # Ctrl+C по выделенной строке.
    tree = panel.list
    tree.clearSelection()

    def look(parent):
        for i in range(parent.childCount()):
            child = parent.child(i)
            if child.data(0, PLACE_ROLE) == single:
                child.setSelected(True)
            look(child)
    look(panel.places_group)
    mods = _qt(Qt, "KeyboardModifier", "ControlModifier")
    QgsApplication.sendEvent(tree, QKeyEvent(
        _qt(QEvent, "Type", "KeyPress"), _qt(Qt, "Key", "Key_C"), mods))
    out["ctrl_c"] = "Копия В" in QApplication.clipboard().text() and \
        "Копия А" not in QApplication.clipboard().text()
    for key in (source, target, single):
        if store.find(key) is not None:
            store.remove(key)
    for f in [f for f in store.folders if f.name == "Копия исходник"]:
        store.remove(f.key)
    result["copy_paste"] = out


@check(6000)
def grid_space():
    # Координатная сетка: из космоса шаг 30°, линии и подписи на глобусе.
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    view.navigator.stop()
    view.navigator.set_pose(Pose(40.0, 60.0, 1.5e7, 0.0, 0.0))
    window.set_extra("grid", True)
    view.update()
    result["grid"] = {
        "space_lines": len(window.grid_shapes),
        "space_labels": sorted(m.name for m in view.grid_marks)[:6],
        "circles": [m.name for m in view.grid_marks
                    if m.kind == "circle"]}


@check(8000)
def grid_near():
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    window.grab().save(os.path.join(TEMP, "planetx_grid_space.png"))
    view.navigator.set_pose(Pose(58.0105, 56.2294, 25000.0, 20.0, 45.0))
    view.update()
    QgsApplication.processEvents()
    result["grid"]["near_lines"] = len(window.grid_shapes)
    result["grid"]["near_labels"] = sorted(
        m.name for m in view.grid_marks)[:6]


@check(300)
def grid_off():
    window = state["window"]
    window.grab().save(os.path.join(TEMP, "planetx_grid_near.png"))
    window.set_extra("grid", False)
    result["grid"]["off_lines"] = len(window.grid_shapes)
    result["grid"]["off_on_globe"] = len(window.view.features.shapes)


def _sky_points(view):
    """Светлых пикселей в верхней пятой части кадра, где нет Земли."""
    from planetx.net.loader import image_to_rgba
    rgba = image_to_rgba(view.grabFramebuffer()).astype(int)
    top = rgba[:rgba.shape[0] // 5, :, :3]
    return int((top.max(axis=2) > 50).sum())


@check(15000)
def stars_on():
    # Звёзды: из космоса вокруг Земли светлые точки, выключены - нет.
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    view.navigator.stop()
    view.navigator.set_pose(Pose(20.0, 60.0, 3.0e7, 0.0, 0.0))
    window.set_extra("stars", True)
    view.update()


@check(1500)
def stars_off():
    window = state["window"]
    view = window.view
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_stars.png"))
    result["stars"] = {"drawn": view.stars.drawn,
                       "sky_px_on": _sky_points(view),
                       "milky_way": view.sky.drawn,
                       "sky_texture": view.sky.texture is not None}
    window.set_extra("stars", False)
    view.update()


@check(1500)
def stars_low():
    window = state["window"]
    view = window.view
    result["stars"]["drawn_off"] = view.stars.drawn
    result["stars"]["sky_px_off"] = _sky_points(view)
    from planetx.core.navigation import Pose
    window.set_extra("stars", True)
    view.navigator.set_pose(Pose(58.0, 56.2, 5000.0, 0.0, 80.0))
    view.update()


@check(300)
def stars_low_check():
    view = state["window"].view
    result["stars"]["drawn_low"] = view.stars.drawn
    result["stars"]["gl_errors"] = dict(view.gl_errors)


def _gibs_report(window, name):
    """Картинки, недостающие тайлы и уровни слоя GIBS вида."""
    layer = window.view.gibs[name]
    loader = window.gibs_loaders.get(name)
    return {"textures": len(layer.textures), "missing": layer.missing,
            "levels": sorted({k[0] for k in layer.textures}),
            "started": len(loader.started) if loader else None}


@check(2000)
def clouds_on():
    # Облака NASA GIBS: картинки приходят, лежат на тайлах, подпись есть.
    # В отдельном профиле ответы GIBS после первых 2 с встают, запросы
    # висят без данных. В QGIS автора те же запросы идут ровно, 72 ответа
    # за 14 с, 29 сентября 2026 года. Причина не найдена.
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    window.set_extra("stars", False)
    view.navigator.set_pose(Pose(50.0, 30.0, 8.0e6, 0.0, 0.0))
    window.set_extra("clouds", True)
    view.update()


@check(12000)
def clouds_wait():
    window = state["window"]
    view = window.view
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_clouds.png"))
    result["clouds"] = _gibs_report(window, "clouds")
    result["clouds"]["attribution"] = \
        "NASA GIBS, VIIRS" in window.attribution.text()
    window.set_extra("clouds", False)
    view.update()


@check(1000)
def clouds_off():
    window = state["window"]
    view = window.view
    result["clouds"]["off_textures"] = len(view.gibs["clouds"].textures)
    result["clouds"]["off_loader"] = "clouds" not in window.gibs_loaders
    result["clouds"]["off_attribution"] = \
        "NASA GIBS, VIIRS" in window.attribution.text()
    result["clouds"]["gl_errors"] = dict(view.gl_errors)
    window.set_extra("stars", True)


@check(2000)
def temperature_on():
    # Температура суши и моря NASA GIBS со шкалой в углу вида.
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    view.navigator.set_pose(Pose(40.0, 20.0, 8.0e6, 0.0, 0.0))
    window.set_extra("temperature", True)
    view.update()


@check(12000)
def temperature_wait():
    window = state["window"]
    view = window.view
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_temperature.png"))
    window.grab().save(os.path.join(TEMP, "planetx_temperature_win.png"))
    result["temperature"] = {
        "sea": _gibs_report(window, "sea"),
        "land": _gibs_report(window, "land"),
        "legend": window.legend.isVisible(),
        "attribution": "GHRSST" in window.attribution.text()}
    window.set_extra("temperature", False)
    view.update()


@check(1000)
def temperature_off():
    window = state["window"]
    view = window.view
    out = result["temperature"]
    out["off_textures"] = sum(len(view.gibs[n].textures)
                              for n in ("sea", "land"))
    out["off_legend"] = window.legend.isVisible()
    out["off_loaders"] = sorted(window.gibs_loaders)
    out["gl_errors"] = dict(view.gl_errors)

@check(3000)
def layer_labels_on():
    # Подписи слоёв проекта: точки со своими подписями и многоугольник
    # с подписью по правилу тёмным цветом. Слои временные, в памяти.
    from qgis.core import (QgsFeature, QgsGeometry, QgsPalLayerSettings,
                           QgsPointXY, QgsRuleBasedLabeling,
                           QgsTextFormat, QgsVectorLayer,
                           QgsVectorLayerSimpleLabeling)
    from qgis.PyQt.QtGui import QColor
    from planetx.core.navigation import Pose
    window = state["window"]
    points = QgsVectorLayer("Point?crs=EPSG:4326&field=name:string",
                            "Подписи точек", "memory")
    feats = []
    for n, (lat, lon) in enumerate(((58.01, 56.23), (58.03, 56.30),
                                    (57.99, 56.15))):
        f = QgsFeature(points.fields())
        f.setAttribute("name", "Скважина %d" % (n + 1))
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
        feats.append(f)
    points.dataProvider().addFeatures(feats)
    settings = QgsPalLayerSettings()
    settings.fieldName = "name"
    fmt = QgsTextFormat()
    fmt.setColor(QColor(255, 220, 0))
    fmt.setSize(10)
    settings.setFormat(fmt)
    points.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    points.setLabelsEnabled(True)
    area = QgsVectorLayer("Polygon?crs=EPSG:4326&field=title:string",
                          "Подписи участков", "memory")
    f = QgsFeature(area.fields())
    f.setAttribute("title", "Участок")
    f.setGeometry(QgsGeometry.fromWkt(
        "POLYGON((56.18 57.96, 56.28 57.96, 56.28 58.00, 56.18 58.00, "
        "56.18 57.96))"))
    area.dataProvider().addFeatures([f])
    rule_settings = QgsPalLayerSettings()
    rule_settings.fieldName = "'Участок: ' || title"
    rule_settings.isExpression = True
    dark_fmt = QgsTextFormat()
    dark_fmt.setColor(QColor(20, 20, 20))
    rule_settings.setFormat(dark_fmt)
    root = QgsRuleBasedLabeling.Rule(None)
    root.appendChild(QgsRuleBasedLabeling.Rule(rule_settings, 0, 0,
                                               "title IS NOT NULL"))
    area.setLabeling(QgsRuleBasedLabeling(root))
    area.setLabelsEnabled(True)
    QgsProject.instance().addMapLayers([points, area])
    state["label_layers"] = [points.id(), area.id()]
    for layer_id in state["label_layers"]:
        window.set_layer_shown(layer_id, True)
    window.refresh()
    window.view.navigator.set_pose(Pose(58.0, 56.23, 30000.0, 0.0, 30.0))
    window.view.update()


@check(4000)
def layer_labels_check():
    window = state["window"]
    view = window.view
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_layer_labels.png"))
    marks = view.layer_marks
    shown = view.labels.shown
    result["layer_labels"] = {
        "marks": sorted(m.name for m in marks),
        "kinds": sorted({m.kind for m in marks}),
        "shown": sorted(m.name for m in marks
                        if (m.id, m.name) in shown),
        "gl_errors": dict(view.gl_errors)}
    for layer_id in state["label_layers"]:
        window.set_layer_shown(layer_id, False)
    window.refresh()


@check(1500)
def layer_labels_off():
    view = state["window"].view
    result["layer_labels"]["off"] = len(view.layer_marks)
    QgsProject.instance().removeMapLayers(state["label_layers"])

@check(8000)
def layer_labels_real():
    # Подписи настоящего слоя автора: путь к слою, поле подписи и proj
    # его системы координат - в PLANETX_LABEL_LAYER через «;;», в пути
    # GeoPackage уже есть «|». Слой открывается только на чтение.
    from qgis.core import (QgsCoordinateReferenceSystem, QgsPalLayerSettings,
                           QgsVectorLayer, QgsVectorLayerSimpleLabeling)
    from planetx.core.ellipsoid import ecef_to_geodetic
    from planetx.core.navigation import Pose
    spec = os.environ.get("PLANETX_LABEL_LAYER")
    if not spec:
        result["layer_labels_real"] = "PLANETX_LABEL_LAYER не задан"
        return
    source, field, proj = spec.split(";;", 2)
    layer = QgsVectorLayer(source, "Слой автора", "ogr")
    layer.setCrs(QgsCoordinateReferenceSystem.fromProj(proj))
    settings = QgsPalLayerSettings()
    settings.fieldName = field
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)
    QgsProject.instance().addMapLayer(layer)
    state["real_layer"] = layer.id()
    window = state["window"]
    window.set_layer_shown(layer.id(), True)
    window.refresh()
    # Точка взгляда - середина охвата слоя.
    from qgis.core import QgsCoordinateTransform
    to_wgs = QgsCoordinateTransform(
        layer.crs(), QgsCoordinateReferenceSystem("EPSG:4326"),
        QgsProject.instance().transformContext())
    c = to_wgs.transform(layer.extent().center())
    window.view.navigator.set_pose(Pose(c.y(), c.x(), 15000.0, 0.0, 0.0))
    window.view.update()
    state["real_center"] = (round(c.y(), 4), round(c.x(), 4))


@check(6000)
def layer_labels_real_check():
    if "real_layer" not in state:
        return
    view = state["window"].view
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_layer_labels_real.png"))
    marks = view.layer_marks
    result["layer_labels_real"] = {
        "center": state["real_center"],
        "marks": len(marks),
        "sample": [m.name for m in marks[:5]],
        "shown": sum(1 for m in marks
                     if (m.id, m.name) in view.labels.shown),
        "labels": view.labels.count,
        "gl_errors": dict(view.gl_errors)}

@check(1500)
def place_view():
    # Вид метки, как в Google Earth: «Снимок вида метки» в меню, перелёт
    # и тур по виду, значок, KML, окно свойств, прежний вид из трёх
    # чисел. Метки - в «Моих метках» отдельного профиля.
    from planetx.core.features import Shape
    from planetx.core.kml import write_kml
    from planetx.core.navigation import Pose
    from planetx.ui.panel import place_icon
    from qgis.core import QgsApplication as App
    window = state["window"]
    places = window.myplaces
    key = places.add(Shape("polygon", [(58.0, 56.2), (58.0, 56.3),
                                       (58.1, 56.3)], name="Участок вида"))
    old = places.add(Shape("point", [(57.5, 55.5)], name="Прежний вид"),
                     view=(1500.0, 20.0, 30.0))
    view = window.view
    view.navigator.stop()
    view.navigator.set_pose(Pose(58.2, 56.5, 12000.0, 40.0, 55.0))
    window._place_action("snapshot", key)
    place = places.find(key)
    stop = window.place_stop(place)
    old_place = places.find(old)
    tree = places.export_keys([key])
    text = write_kml(tree)
    from planetx.ui.placeprops import PlaceProperties
    dialog = PlaceProperties(place, window, current_view=window.current_view)
    dialog_view = dialog.view()
    view.navigator.set_pose(Pose(50.0, 30.0, 8000.0, 0.0, 0.0))
    dialog._snapshot()
    snapped = dialog.view()
    dialog._reset_view()
    reset = dialog.view()
    dialog.close()
    result["place_view"] = {
        "view": [round(v, 4) for v in place.view],
        "stop": [round(v, 4) for v in (stop.lat, stop.lon, stop.distance,
                                       stop.heading, stop.tilt)],
        "icon_is_polygon": place_icon(place).cacheKey()
        == App.getThemeIcon("/mIconPolygonLayer.svg").cacheKey(),
        "old_view": [round(v, 4) for v in old_place.view],
        "old_icon_camera": place_icon(old_place).cacheKey()
        == App.getThemeIcon("/mIconCamera.svg").cacheKey(),
        "kml_lookat": "<latitude>58.20000000</latitude>" in text,
        "dialog_view": [round(v, 4) for v in dialog_view],
        "dialog_snapshot": [round(v, 4) for v in snapped],
        "dialog_reset": [round(v, 4) for v in reset]}
    places.remove_many([key, old])


BUILDINGS_POSE = (58.0105, 56.2294, 1500.0, 30.0, 60.0)


def _buildings_report(window):
    view = window.view
    b = view.buildings
    loader = window.buildings_loader
    return {"wanted": len(b.wanted), "footprints": len(b.footprints),
            "buffers": len(b.buffers), "drawn": b.drawn,
            "vertices": b.vertices, "missing": b.missing(),
            "started": len(loader.started) if loader else None,
            "active": len(loader.replies) if loader else None,
            "queued": len(loader.queue) if loader else None,
            "decoding": len(loader.decoding) if loader else None,
            "failed": state.get("buildings_failed", []),
            "building": len(b.building), "results": len(b.results),
            "gl_errors": dict(view.gl_errors),
            "outside_errors": dict(view.outside_errors)}


@check(1500)
def buildings_on():
    # 3D-здания над центром Перми: тайлы приходят, сетки в видеокарте,
    # кадр со зданиями отличается от кадра без них, подпись есть.
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    view.navigator.stop()
    view.navigator.set_pose(Pose(*BUILDINGS_POSE))
    window.set_extra("buildings", True)
    state["buildings_failed"] = []
    window.buildings_loader.failed.connect(
        lambda key, text: state["buildings_failed"].append(
            [list(key), str(text)]))
    view.update()


def _changed_pixels(a, b, step=4):
    if a.size() != b.size():
        return -1
    count = 0
    for y in range(0, a.height(), step):
        for x in range(0, a.width(), step):
            if a.pixel(x, y) != b.pixel(x, y):
                count += 1
    return count


@check(15000)
def buildings_wait():
    window = state["window"]
    view = window.view
    image = view.grabFramebuffer()
    image.save(os.path.join(TEMP, "planetx_buildings.png"))
    # Тот же кадр без зданий сразу следом: разница - сами здания.
    view.buildings.shown = False
    bare = view.grabFramebuffer()
    view.buildings.shown = True
    again = view.grabFramebuffer()
    result["buildings"] = _buildings_report(window)
    result["buildings"]["changed_px_sampled"] = _changed_pixels(image, bare)
    result["buildings"]["same_px_check"] = _changed_pixels(image, again)
    result["buildings"]["attribution"] = \
        "OpenFreeMap" in window.attribution.text()
    result["buildings"]["frame_ms"] = round(
        1000.0 * sorted(view.frame_times)[len(view.frame_times) // 2], 2)
    window.set_extra("buildings", False)
    view.update()


@check(2000)
def buildings_off():
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    result["buildings"]["off"] = {
        "loader": window.buildings_loader is None,
        "drawn": view.buildings.drawn}
    window.set_extra("buildings", True)
    lat, lon = BUILDINGS_POSE[:2]
    view.navigator.set_pose(Pose(lat, lon, 20000.0, 0.0, 0.0))
    view.update()


@check(3000)
def buildings_range():
    window = state["window"]
    report = _buildings_report(window)
    result["buildings"]["high"] = report
    window.set_extra("buildings", False)
    window.view.update()


@check(500)
def buildings_shot():
    # Снимок вида ждёт здания: после него все тайлы зданий кадра
    # в видеокарте.
    from planetx.core.navigation import Pose
    import planetx.ui.snapshot as smod
    window = state["window"]
    nav = window.view.navigator
    nav.stop()
    nav.set_pose(Pose(*BUILDINGS_POSE))
    # PLANETX_SHOT_BARE=1 - тот же снимок без зданий, для сравнения.
    window.set_extra("buildings",
                     os.environ.get("PLANETX_SHOT_BARE") != "1")
    path = os.path.join(TEMP, "planetx_buildings_shot.png")
    if os.path.exists(path):
        os.remove(path)
    smod.QFileDialog.getSaveFileName = staticmethod(
        lambda *args, **kwargs: (path, ""))

    def setup(dialog):
        dialog.keep.setChecked(False)
        dialog.width_px.setValue(2000)
        dialog.height_px.setValue(1500)
    _shot_begin(False, setup)


@check(1500)
def buildings_shot_wait():
    out = _shot_wait()
    if isinstance(out, int):
        return out
    window = state["window"]
    b = window.view.buildings
    out["wanted"] = len(b.wanted)
    out["buffers"] = len([k for k in b.wanted if k in b.buffers])
    out["empty"] = len([k for k in b.wanted
                        if b.footprints.get(k) == "empty"])
    out["missing_after"] = b.missing()
    out["rejected"] = b.rejected
    result["buildings_shot"] = out
    return None


@check(500)
def buildings_scene():
    # Строка «3D-здания» уходит в сцену и возвращается из неё.
    from planetx.ui.scene import apply, capture
    window = state["window"]
    scene, _ = capture(window)
    saved = scene.view.get("extras", {}).get("buildings")
    window.set_extra("buildings", False)
    apply(window, scene)
    result["buildings_scene"] = {
        "saved": saved, "restored": window.extras.get("buildings"),
        "loader": window.buildings_loader is not None}
    window.set_extra("buildings", False)


@check(1500)
def coords_search():
    # Поиск понимает все форматы координат и строку глобуса с высотой.
    from planetx.core.coords import FORMATS, format_point
    from planetx.ui.identify import hemispheres
    window = state["window"]
    found = {}
    for fmt in FORMATS:
        text = format_point(58.0105, 56.2294, fmt, hemispheres())
        window.fly(text)
        mark = window.view.search_mark
        found[fmt] = [text, round(mark.lat, 5), round(mark.lon, 5)] \
            if mark is not None else [text, None]
        window.set_coords(fmt)
        found[fmt].append(window.coords)
    window.fly("59.593416, 56.806003, высота 207 м")
    mark = window.view.search_mark
    found["with_height"] = [round(mark.lat, 6), round(mark.lon, 6)]
    window.set_coords("decimal")
    result["coords_search"] = found


# Путь линейки через вершину Эльбруса, 5642 м.
ELBRUS = (43.3499, 42.4453)


@check(1500)
def ruler_path():
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    view.navigator.stop()
    view.navigator.set_pose(Pose(ELBRUS[0], ELBRUS[1], 25000.0, 0.0, 0.0))
    window._open_ruler()
    window.ruler_dialog.tabs.setCurrentIndex(1)  # путь
    ruler = window.ruler
    ruler.add(43.31, 42.40)
    ruler.add(*ELBRUS)
    ruler.add(43.39, 42.49)
    view.update()


@check(1000)
def ruler_wait():
    """Ждать высоты вдоль пути, не дольше 90 с."""
    import time
    window = state["window"]
    started = state.setdefault("ruler_started", time.monotonic())
    values = window.ruler.values(rubber=False)
    elapsed = time.monotonic() - started
    if not values["ground_ready"] and elapsed < 90.0:
        return 1000
    state["ruler_ready_s"] = round(elapsed, 1)
    return None


@check(500)
def ruler_path_check():
    window = state["window"]
    view = window.view
    ruler = window.ruler
    values = ruler.values(rubber=False)
    window._ruler_profile()
    dialog = window.profile_dialog
    p = dialog.chart.profile
    out = {"length_m": round(values["length"], 1),
           "ground_m": round(values["ground"], 1),
           "ground_ready": values["ground_ready"],
           "ready_after_s": state.get("ruler_ready_s"),
           "tool_heights_left": len(view.tool_heights),
           "profile_high": round(p.high, 1) if p else None,
           "profile_gain": round(p.gain, 1) if p else None,
           "profile_title": dialog.windowTitle(),
           "stats": dialog.stats.text(),
           "segment_labels": len([m for m in view.tool_marks
                                  if m.kind == "ruler"]),
           "summary": window.ruler_dialog.summary()}
    # Перетаскивание последней точки через vertex_tool вида.
    import numpy as np
    from planetx.core.ellipsoid import geodetic_to_ecef
    lat, lon = ruler.points[2]
    xyz = geodetic_to_ecef(lat, lon, view.store.heights_at(
        np.array([lat]), np.array([lon]))[0])
    (px, py), front = view.camera.project(xyz[None])[0][0], True
    tool = view.vertex_tool
    grabbed = tool.grab(px, py)
    tool.move(px + 60.0, py)
    tool.drop()
    out["grabbed"] = bool(grabbed)
    out["moved"] = ruler.points[2] != (lat, lon)
    view.undo_point.emit()
    out["after_backspace"] = len(ruler.points)
    # Профиль пути из «Моих меток».
    from planetx.core.features import Shape
    key = window.myplaces.add(Shape("line", [(43.31, 42.40), ELBRUS],
                                    name="Путь на Эльбрус"))
    window._place_action("profile", key)
    out["place_profile_title"] = dialog.windowTitle()
    window.myplaces.remove(key)
    out["gl_errors"] = dict(view.gl_errors)
    result["ruler_path"] = out
    dialog.close()
    window.ruler_dialog.close()


@check(1500)
def icons_time():
    # Значки меток и шкала времени: охват, скрытие меток вне промежутка,
    # перелёт к метке с датой вида, KML туда и обратно, окно свойств.
    from planetx.core.features import Shape
    from planetx.core.kml import read_kml, write_kml
    from planetx.core.navigation import Pose
    from planetx.ui.placeprops import PlaceProperties
    window = state["window"]
    view = window.view
    store = window.myplaces
    folder = store.add_folder("Значки и время")
    keys = [
        store.add(Shape("point", [(58.0105, 56.2294)], (255, 80, 0, 255),
                        name="Флаг", icon="flag"), folder=folder,
                  period=("2026-09-01", "2026-09-01")),
        store.add(Shape("point", [(58.02, 56.25)], (0, 160, 255, 255),
                        name="Музей", icon="museum"), folder=folder,
                  period=("2026-09-10", "2026-09-20"),
                  view=(58.02, 56.25, 1500.0, 0.0, 45.0),
                  view_period=("2026-09-15", "2026-09-15")),
        store.add(Shape("point", [(58.03, 56.27)], name="Без времени",
                        icon="camera"), folder=folder)]
    state["icons_keys"] = keys
    state["icons_folder"] = folder
    view.navigator.stop()
    view.navigator.set_pose(Pose(58.02, 56.25, 6000.0, 0.0, 30.0))
    # Шкала закрыта, пока её не откроют: кнопка доступна, метки все.
    button = window.toolbar.time
    out = {"bar_shown": window.timebar.isVisible(),
           "button": [button.isEnabled(), button.isChecked()],
           "extent": [round(v) for v in window.timebar.extent()],
           "shapes_all": len([s for s in view.features.shapes
                              if s.kind == "point"])}
    # Кнопка открывает шкалу. Промежуток после 5 сентября: флаг скрыт,
    # музей и метка без времени видны.
    button.setChecked(True)
    out["bar_by_button"] = window.timebar.isVisible()
    import calendar
    lo = calendar.timegm((2026, 9, 5, 0, 0, 0))
    window.timebar.set_range(lo, window.timebar.extent()[1])
    out["names_after_5th"] = sorted(s.name for s in view.features.shapes
                                    if s.kind == "point")
    # Закрытая шкала метки не скрывает.
    button.setChecked(False)
    out["names_closed"] = sorted(s.name for s in view.features.shapes
                                 if s.kind == "point")
    # Перелёт к виду с датой сам открывает шкалу.
    window.fly_to_place(store.find(keys[1]))
    out["bar_after_fly"] = [window.timebar.isVisible(), button.isChecked()]
    out["range_after_fly"] = [round(v) for v in window.timebar.range()]
    tree = store.export_tree(folder)
    back = {p.name: p for p in read_kml(write_kml(tree).encode()).places()}
    out["kml"] = {name: [p.icon, list(p.time) if p.time else None,
                         list(p.view_time) if p.view_time else None]
                  for name, p in back.items()}
    dialog = PlaceProperties(store.find(keys[1]), window,
                             current_view=window.current_view)
    values = dialog.values()
    out["dialog"] = {k: values[k] for k in ("icon", "time", "view_time")}
    dialog.close()
    out["marks"] = sorted(m.kind for m in view._own_marks())
    result["icons_time"] = out
    view.update()


@check(3000)
def icons_time_check():
    window = state["window"]
    view = window.view
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_icons.png"))
    result["icons_time"]["labels"] = view.labels.count
    result["icons_time"]["gl_errors"] = dict(view.gl_errors)
    window.myplaces.remove(state["icons_folder"])
    result["icons_time"]["bar_after_remove"] = [
        window.timebar.isVisible(), window.toolbar.time.isEnabled()]


@check(300)
def record_screen():
    # Запись тура с экрана: кнопка записи, камера проходит десять поз.
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    view.navigator.stop()
    view.navigator.set_pose(Pose(58.0, 56.2, 8000.0, 0.0, 20.0))
    window.toolbar.record.setChecked(True)
    state["record_k"] = 0


@check(300)
def record_screen_move():
    from planetx.core.navigation import Pose
    window = state["window"]
    k = state["record_k"]
    if k < 10:
        window.view.navigator.set_pose(Pose(
            58.0 + 0.005 * k, 56.2 + 0.01 * k, 8000.0 - 400.0 * k,
            10.0 * k, 20.0 + 3.0 * k))
        state["record_k"] = k + 1
        return 300
    return None


@check(500)
def record_screen_stop():
    import planetx.ui.window as wmod
    window = state["window"]
    wmod.QInputDialog.getText = staticmethod(
        lambda *args, **kwargs: ("Тур теста", True))
    window.toolbar.record.setChecked(False)
    place = next(p for p in window.myplaces.places if p.tour
                 and p.name == "Тур теста")
    state["record_key"] = place.key
    from planetx.core.kml import read_kml, write_kml
    back = read_kml(write_kml(window.myplaces.export_keys(
        [place.key])).encode()).places()[0]
    result["record_screen"] = {
        "samples": len(place.tour),
        "duration": round(place.tour[-1][0], 2),
        "last": [round(v, 4) for v in place.tour[-1][1:]],
        "kml_samples": len(back.tour),
        "drawn": any(s.name == "Тур теста" for s in
                     window.view.features.shapes)}
    window._place_action("tour", place.key)


@check(12000)
def record_screen_play():
    window = state["window"]
    pose = window.view.navigator.pose
    out = result["record_screen"]
    tour = window.tour.tour
    out["tour_duration"] = round(tour.duration, 2) if tour else None
    if tour is not None:
        # Поза тура в конце - без зависимости от кадров окна.
        end = tour.pose_at(tour.duration)
        out["tour_end"] = [round(end.lat, 4), round(end.lon, 4),
                           round(end.distance, 1), round(end.heading, 2),
                           round(end.tilt, 2)]
        out["stop_kind"] = type(tour.stops[0]).__name__
    out["end_pose"] = [round(pose.lat, 4), round(pose.lon, 4),
                       round(pose.distance, 1), round(pose.heading, 2),
                       round(pose.tilt, 2)]
    window.tour.stop()
    window.myplaces.remove(state["record_key"])


@check(1500)
def demo_open():
    # Демо «Пермь» из меню «Сцена»: метки со значками и временем, тур,
    # шкала времени, 3D-здания.
    window = state["window"]
    nav = window.view.navigator
    starts = []
    original = nav.start_flight

    def counted(flight, now):
        import traceback as tb
        starts.append(" < ".join(
            "%s:%d %s" % (os.path.basename(f.filename), f.lineno, f.name)
            for f in tb.extract_stack()[-5:-1]))
        return original(flight, now)
    nav.start_flight = counted
    state["demo_starts"] = starts
    # Исключения кадра: кадр с ошибкой не заказывает следующий.
    failures = []
    view = window.view
    render = view._render

    def guarded_render(*args, **kwargs):
        try:
            return render(*args, **kwargs)
        except (AttributeError, IndexError, KeyError, RuntimeError,
                TypeError, ValueError):
            failures.append(traceback.format_exc().splitlines()[-6:])
            raise
    view._render = guarded_render
    state["demo_failures"] = failures
    # Счёт кадров по секундам и состояние вида.
    from qgis.PyQt.QtCore import QTimer as _Timer
    samples = []
    ticker = _Timer()
    ticker.setInterval(1000)
    ticker.timeout.connect(lambda: samples.append(
        [view.frame, view.isVisible(), view.updatesEnabled(),
         view.navigator.flight is not None, view.shot is not None,
         window.isMinimized(), round(view.navigator.pose.distance)]))
    ticker.start()
    state["demo_ticker"] = ticker
    state["demo_samples"] = samples
    part = os.environ.get("PLANETX_DEMO_PART", "")
    if part:
        # Разбор по частям: какое действие демо держит главный поток.
        from planetx.core.kml import read_kml
        from planetx.core.scene import read_scene
        with open(os.path.join(ROOT, "planetx", "demo", "perm.planetx"),
                  "rb") as fh:
            scene, kml = read_scene(fh.read())
        key = None
        if part == "places":
            key = window.myplaces.import_tree(read_kml(kml, scene.places))
        elif part == "extras":
            for name, on in scene.view["extras"].items():
                window.set_extra(name, on)
        elif part == "groups":
            window.set_line_groups(set(scene.view["groups"]))
        elif part == "fly":
            window._fly_to(*scene.camera)
        state["demo_key"] = key
        result["demo"] = {"part": part}
        return
    key = window.open_demo()
    state["demo_key"] = key
    places = window.myplaces.places_in(key) if key else []
    result["demo"] = {
        "folder": key is not None,
        "places": len(places),
        "icons": sorted({p.shape.icon for p in places
                         if p.kind == "point"}),
        "timed": len([p for p in places if p.time]),
        "tours": len([p for p in places if p.tour]),
        "extruded": len([p for p in places if p.shape.extrude]),
        "bar": window.timebar.isVisible(),
        "buildings": window.extras.get("buildings")}
    window.view.update()


@check(45000)
def demo_check():
    window = state["window"]
    view = window.view
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_demo.png"))
    out = result["demo"]
    out["labels"] = view.labels.count
    out["buildings_drawn"] = view.buildings.drawn
    out["gl_errors"] = dict(view.gl_errors)
    pose = view.navigator.pose
    out["pose"] = [round(pose.lat, 4), round(pose.lon, 4),
                   round(pose.distance), round(pose.heading, 1),
                   round(pose.tilt, 1)]
    out["flight"] = view.navigator.flight is not None
    out["frames"] = view.frame
    starts = state.get("demo_starts", [])
    out["flight_starts"] = len(starts)
    out["flight_callers"] = sorted(set(starts))[:6]
    failures = state.get("demo_failures", [])
    out["render_failures"] = len(failures)
    state["demo_ticker"].stop()
    out["per_second"] = state.get("demo_samples", [])
    out["first_failure"] = failures[0] if failures else None
    if state.get("demo_key"):
        window.myplaces.remove(state["demo_key"])
    window.set_extra("buildings", False)

# Выбор шагов: PLANETX_STEPS=tour_start,tour_wait. Окно открывается
# всегда. Без переменной идут все шаги.
ONLY = os.environ.get("PLANETX_STEPS")
if ONLY:
    CHECKS[:] = [c for c in CHECKS if c[0].__name__ == "open_globe"
                 or c[0].__name__ in ONLY.split(",")]
QTimer.singleShot(3000, run)
