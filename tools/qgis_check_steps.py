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

# Корень модуля: рабочая копия или другая копия, например ветки,
# через переменную PLANETX_ROOT.
ROOT = os.environ.get("PLANETX_ROOT", r"C:\Dev\planetx")
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
MANUAL = set()  # отладочные шаги, только по имени


def check(delay, manual=False):
    """Шаг проверки: функция и пауза перед следующим шагом, мс.
    manual - отладочный шаг, он идёт только по имени в PLANETX_STEPS,
    в полный прогон не входит."""
    def wrap(function):
        CHECKS.append((function, delay))
        if manual:
            MANUAL.add(function.__name__)
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
            ValueError, OSError, ImportError, IndexError):
        result["errors"].append("%s: %s" % (
            function.__name__, traceback.format_exc().splitlines()[-1]))
        # Полная трассировка - для разбора, в отчёте отдельно.
        result.setdefault("traces", {})[function.__name__] = \
            traceback.format_exc()
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


# Отладочный вывод драйвера повесил QGIS (AGENTS, «Сбой снимка со
# зданиями»), в QGIS 4 класс лежит не там, где его ищет шаг. В полный
# прогон шаг не входит, 2 октября 2026 года он остановил его окном
# ошибки.
@check(500, manual=True)
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
    store.update(keys[0], {"name": "Центр Перми"})
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
def tour_loop():
    # Кнопка ⟳: тур после последней остановки идёт с первой.
    from planetx.core.features import Shape
    window = state["window"]
    store = window.myplaces
    for place in list(store.places):
        if place.visible:
            store.set_visible(place.key, False)
    state["loop_keys"] = [
        store.add(Shape("point", [(58.0, 56.25)], name="Круг 1")),
        store.add(Shape("point", [(58.02, 56.27)], name="Круг 2"))]
    player = window.tour
    player.bar.pause.setValue(0.2)
    player.bar.loop.setChecked(True)
    player.laps = 0
    window._place_action("tour", "")
    state["loop_began"] = None
    result["tour_loop"] = {"stops": len(player.stops),
                           "loop_shown": player.bar.loop.isVisible()}


@check(500)
def tour_loop_wait():
    import time
    from qgis.core import QgsSettings
    player = state["window"].tour
    began = state["loop_began"] or time.monotonic()
    state["loop_began"] = began
    if player.laps < 2 and time.monotonic() - began < 90:
        return 500
    out = result["tour_loop"]
    out["laps"] = player.laps
    out["playing"] = player.playing
    out["setting"] = QgsSettings().value("PlanetX/tour_loop", False,
                                         type=bool)
    player.bar.grab().save(os.path.join(TEMP, "planetx_tour_bar.png"))
    # Шкала времени в том же виде, что панель тура.
    bar = state["window"].timebar
    bar.set_extent((0.0, 86400.0 * 30))
    bar.open_bar()
    bar.grab().save(os.path.join(TEMP, "planetx_time_bar.png"))
    bar.close_bar()
    # Без круга тур встаёт в конце.
    player.bar.loop.setChecked(False)
    state["loop_off"] = time.monotonic()
    return None


@check(500)
def tour_loop_off():
    import time
    window = state["window"]
    player = window.tour
    laps = player.laps
    if player.playing and time.monotonic() - state["loop_off"] < 60:
        return 500
    out = result["tour_loop"]
    out["stopped_at_end"] = not player.playing
    out["laps_after_off"] = laps
    player.stop()
    for key in state["loop_keys"]:
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


def _open_time(lo, hi):
    """Открыть шкалу времени глобуса на промежутке, секунды."""
    from planetx.core import when
    state["window"]._show_time((when.text(lo), when.text(hi)))


@check(1500)
def tracks():
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsVectorLayer
    from qgis.PyQt.QtCore import QDateTime
    from planetx.ui.track import seconds
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
    t0 = seconds(base)
    state["track_base"] = t0
    # Охват шкалы - время трека.
    extent = window.timebar.track.extent if window.timebar.known else None
    _open_time(t0 + 240, t0 + 300)  # 10:04-10:05
    tracker = window.tracks
    moment = tracker.moment
    shapes = tracker.shapes()
    flight = window.view.navigator.flight
    out = {"moment_min": round((moment - t0) / 60.0, 1)
           if moment is not None else None,
           "bar_known": window.timebar.known,
           "extent": [round((v - t0) / 60.0, 1) for v in extent]
           if extent else None,
           "shapes": sorted((s.kind, s.name, len(s.points))
                            for s in shapes),
           "glide": type(flight[1]).__name__ if flight else None,
           "target": [round(flight[1].end.lat, 4), round(flight[1].end.lon,
                                                         4),
                      round(flight[1].end.heading, 1)] if flight else None,
           "on_globe": sum(1 for s in window.view.features.shapes
                           if s.name in ("car", "elk"))}
    # Шаги шкалы не должны перечитывать точки треков.
    reloads = []
    reload = tracker.reload
    tracker.reload = lambda: reloads.append(1) or reload()
    for k in range(3):
        window.timebar.set_range(t0 + 300 + 60 * k, t0 + 360 + 60 * k)
        QgsApplication.processEvents()
    del tracker.reload
    out["reloads_on_steps"] = len(reloads)
    out["moment_after_steps"] = round((tracker.moment - t0) / 60.0, 1) \
        if tracker.moment is not None else None
    window._time_toggled(False)
    window.toolbar.set_time_shown(False)
    out["whole"] = sorted((s.kind, s.name, len(s.points))
                          for s in tracker.shapes())
    result["tracks"] = out


@check(200)
def tracks_off():
    from qgis.utils import iface
    window = state["window"]
    tracker = window.tracks
    # Временной контроллер QGIS трек не двигает: глобус слушает только
    # свою шкалу.
    _open_time(state["track_base"] + 240, state["track_base"] + 300)
    before = tracker.moment
    controller = iface.mapCanvas().temporalController()
    from qgis.core import QgsDateTimeRange
    from planetx.ui.track import clock
    controller.setTemporalExtents(QgsDateTimeRange(
        clock(state["track_base"]), clock(state["track_base"] + 1200)))
    controller.updateTemporalRange.emit(QgsDateTimeRange(
        clock(state["track_base"]), clock(state["track_base"] + 1200)))
    QgsApplication.processEvents()
    result["tracks"]["controller_ignored"] = tracker.moment == before
    window._time_toggled(False)
    window.toolbar.set_time_shown(False)
    window.tracks.set_track(state["track_layer"], None)
    result["tracks"]["after_remove"] = len(window.tracks.shapes())


@check(1500)
def layer_time():
    """Слой проекта со временем рисуется в промежутке шкалы глобуса."""
    from qgis.core import (Qgis, QgsFeature, QgsGeometry, QgsPalLayerSettings,
                           QgsPointXY, QgsVectorLayer,
                           QgsVectorLayerSimpleLabeling)
    from qgis.PyQt.QtCore import QDateTime
    from planetx.core.navigation import Pose
    from planetx.ui.track import seconds
    window = state["window"]
    layer = QgsVectorLayer(
        "Point?crs=EPSG:4326&field=t:datetime&field=name:string",
        "Слой со временем", "memory")
    base = QDateTime.fromString("2026-09-28T10:00:00", "yyyy-MM-ddTHH:mm:ss")
    features = []
    for k in range(6):
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromPointXY(
            QgsPointXY(56.20 + 0.02 * k, 58.00)))
        f["t"] = base.addSecs(3600 * k)
        f["name"] = "p%d" % k
        features.append(f)
    layer.dataProvider().addFeatures(features)
    props = layer.temporalProperties()
    mode = getattr(Qgis, "VectorTemporalMode", None)
    props.setMode(mode.FeatureDateTimeInstantFromField if mode is not None
                  else props.ModeFeatureDateTimeInstantFromField)
    props.setStartField("t")
    props.setIsActive(True)
    settings = QgsPalLayerSettings()
    settings.fieldName = "name"
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)
    QgsProject.instance().addMapLayer(layer)
    state["time_layer"] = layer
    window.set_layer_shown(layer.id(), True)
    window.refresh()
    nav = window.view.navigator
    nav.stop()
    nav.show(Pose(58.0, 56.25, 30000.0, 0.0, 0.0))
    t0 = seconds(base)
    state["time_layer_base"] = t0
    out = {"temporal": [l.name() for l in window._temporal_layers()],
           "marks": len(window._data_marks),
           "bar_known": window.timebar.known}
    # Два часа из пяти: 11:00-13:00, видны p1, p2, p3.
    _open_time(t0 + 3600, t0 + 3 * 3600)
    window._layer_time_timer.stop()
    window._apply_layer_time()
    span = window.overlay.time_range if window.overlay is not None \
        else None
    out["overlay_range"] = [span.begin().toString("HH:mm"),
                            span.end().toString("HH:mm")] if span else None
    out["labels_filter"] = window.layer_labels._time_filter(layer)
    out["drawn"] = _drawn_points(window, layer)
    result["layer_time"] = out


def _drawn_points(window, layer):
    """Нарисованы ли точки p0-p5 слоя со временем на картинке
    с настройками наложения глобуса."""
    from qgis.core import (QgsCoordinateReferenceSystem,
                           QgsCoordinateTransform, QgsMapRendererSequentialJob,
                           QgsPointXY, QgsRectangle)
    from qgis.PyQt.QtCore import QSize
    if window.overlay is None:
        return None
    settings = window.overlay._settings((12, 0, 0))
    settings.setLayers([layer])
    to_map = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:4326"),
        QgsCoordinateReferenceSystem("EPSG:3857"), QgsProject.instance())
    a = to_map.transform(QgsPointXY(56.18, 57.99))
    b = to_map.transform(QgsPointXY(56.32, 58.01))
    settings.setExtent(QgsRectangle(a.x(), a.y(), b.x(), b.y()))
    settings.setOutputSize(QSize(700, 200))
    job = QgsMapRendererSequentialJob(settings)
    job.start()
    job.waitForFinished()
    image = job.renderedImage()
    pixels = settings.mapToPixel()
    drawn = []
    for k in range(6):
        p = to_map.transform(QgsPointXY(56.20 + 0.02 * k, 58.00))
        c = pixels.transform(p.x(), p.y())
        x, y = int(c.x()), int(c.y())
        drawn.append(any(image.pixelColor(i, j).alpha() > 0
                         for i in range(x - 3, x + 4)
                         for j in range(y - 3, y + 4)
                         if 0 <= i < image.width()
                         and 0 <= j < image.height()))
    return drawn


@check(3000)
def layer_time_check():
    window = state["window"]
    out = result["layer_time"]
    out["labels"] = sorted(m.name for m in window.layer_labels.marks
                           if m.name.startswith("p"))
    # Шкала закрыта - слой целиком, наложение без промежутка.
    window._time_toggled(False)
    window.toolbar.set_time_shown(False)
    window._layer_time_timer.stop()
    window._apply_layer_time()
    out["closed_range"] = window.overlay.time_range is None \
        if window.overlay is not None else None
    out["closed_drawn"] = _drawn_points(window, state["time_layer"])
    QgsProject.instance().removeMapLayer(state.pop("time_layer"))
    window.refresh()
    out["marks_after_remove"] = len(window._data_marks)


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
    from qgis.core import (QgsFeature, QgsGeometry, QgsPointXY,
                           QgsVectorFileWriter, QgsVectorLayer)
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
              folder=folder,
              period=("2026-09-28T10:00:00Z", "2026-09-28T11:00:00Z"))
    window.panel.select_place(folder)
    # Шкала времени на 10:15-10:20 по времени метки «Финиш».
    window._show_time(("2026-09-28T10:15:00Z", "2026-09-28T10:20:00Z"))
    nav = window.view.navigator
    nav.stop()
    nav.set_pose(Pose(58.02, 56.28, 15000.0, 25.0, 60.0))
    ok = window.save_scene(SCENE_PATH)
    expect = {"camera": [58.02, 56.28, 15000.0, 25.0, 60.0],
              "time": ["2026-09-28T10:15:00Z", "2026-09-28T10:20:00Z"],
              "source": layer.source(),
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
    from planetx.core import when
    span = window._time_range
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
        "time": [when.text(v) for v in span] if span else None,
        "time_same": span is not None
        and [when.text(v) for v in span] == expect["time"],
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
    # Время прежней сцены - временной контроллер QGIS - становится
    # промежутком шкалы: кадр 3 по 300 с от 10:00.
    from planetx.ui.scene import scene_span
    result["scene_old_time"] = {
        "animated": scene_span({"mode": 1, "start": "2026-09-28T10:00:00",
                                "end": "2026-09-28T11:00:00", "frame": 3,
                                "step": 300.0}),
        "off": scene_span({"mode": 0, "start": "2026-09-28T10:00:00",
                           "end": "2026-09-28T11:00:00"})}
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
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsVectorLayer
    from qgis.PyQt.QtCore import QDateTime
    from planetx.ui.track import seconds
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
    # Шкала на весь трек, 10:00-10:20: запись ведёт трек по ней.
    _open_time(seconds(base), seconds(base) + 1200)
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
    window._time_toggled(False)
    window.toolbar.set_time_shown(False)


VIDEO_PATH = os.path.join(TEMP, "planetx_tour.mp4")
HIRES_DIR = os.path.join(TEMP, "planetx_record_hires")


def _record_mode(target, mode, size=(0, 0)):
    """Тур из двух остановок без трека: видео MP4 или кадры размера
    size."""
    import shutil
    import time as _time
    from planetx.core.tour import Stop
    window = state["window"]
    if mode == "video":
        if os.path.exists(target):
            os.remove(target)
    else:
        if os.path.isdir(target):
            shutil.rmtree(target)
        os.makedirs(target)
    state["record_done"] = None
    if "record_link" not in state:
        state["record_link"] = window.recorder.done.connect(
            lambda ok, text: state.__setitem__("record_done", (ok, text)))
    window.tour.bar.pause.setValue(0.4)
    window.tour.start([Stop("A", 58.00, 56.02, 9000.0, 10.0, 40.0),
                       Stop("B", 58.03, 56.06, 7000.0, 40.0, 50.0)])
    state["record_started"] = _time.monotonic()
    state["record_began"] = window.record_tour(target, mode, size)


@check(500)
def record_video():
    _record_mode(VIDEO_PATH, "video")


@check(500)
def record_video_wait():
    return _record_wait("video")


@check(500)
def record_hires():
    _record_mode(HIRES_DIR, "frames", (1920, 1080))


@check(500)
def record_hires_wait():
    return _record_wait("hires")


@check(200)
def record_modes_check():
    from qgis.PyQt.QtGui import QImage
    window = state["window"]
    out = result["record"]
    with open(VIDEO_PATH, "rb") as fh:
        head = fh.read(12)
    out["video_file"] = {"bytes": os.path.getsize(VIDEO_PATH),
                         "ftyp": head[4:8] == b"ftyp",
                         "window": [window.view.width(),
                                    window.view.height()],
                         "ratio": window.view.devicePixelRatioF()}
    with open(os.path.join(HIRES_DIR, "frames.json"),
              encoding="utf-8") as fh:
        data = json.load(fh)
    pngs = sorted(n for n in os.listdir(HIRES_DIR) if n.endswith(".png"))
    image = QImage(os.path.join(HIRES_DIR, pngs[0]))
    out["hires"] = {"count": data["count"], "png": len(pngs),
                    "size": [data["width"], data["height"]],
                    "png_size": [image.width(), image.height()],
                    "incomplete": len(data["incomplete"])}
    out["gl"] = dict(window.view.gl_errors)


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


SUN_TIME = 1790748000.0  # 30 сентября 2026 года, 06:00 UTC


@check(300)
def sun_on():
    # Солнце: камера над линией дня и ночи, солнце на западе кадра.
    # Дневная половина кадра светлее ночной, воздух ночью гаснет.
    from planetx.core import sun
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    window.set_extra("stars", False)
    window.set_extra("sun", True)
    window.sun_timer.stop()
    view.sun = sun.direction(SUN_TIME)
    lat, lon = sun.subsolar(SUN_TIME)
    view.navigator.stop()
    view.navigator.set_pose(Pose(0.0, lon + 90.0, 2.0e7, 0.0, 0.0))
    result["sun"] = {"subsolar": [round(lat, 3), round(lon, 3)],
                     "timer": window.sun_timer.isActive()}
    view.update()


@check(15000)
def sun_terminator():
    from planetx.net.loader import image_to_rgba
    view = state["window"].view
    image = view.grabFramebuffer()
    image.save(os.path.join(TEMP, "planetx_sun.png"))
    rgba = image_to_rgba(image).astype(float)
    h, w = rgba.shape[:2]
    # Диск в середине кадра, левая треть - день, правая - ночь.
    band = rgba[h // 3:2 * h // 3, :, :3].sum(axis=2) / 3.0
    out = result["sun"]
    out["day"] = round(float(band[:, w // 4:5 * w // 12].mean()), 1)
    out["night"] = round(float(band[:, 7 * w // 12:3 * w // 4].mean()), 1)
    out["gl_errors"] = dict(view.gl_errors)
    # Над Пермью в 06:00 UTC (11:00 местного) - день.
    from planetx.core import sun
    out["perm_elevation"] = round(sun.elevation(58.01, 56.23, SUN_TIME), 2)
    window = state["window"]
    window.set_extra("sun", False)
    out["off"] = [view.sun is None, window.sun_timer.isActive()]
    view.update()


@check(300)
def sun_city():
    # Здания и рельеф центра Перми под вечерним солнцем, 17:30 местного.
    from planetx.core import sun
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    window.set_extra("buildings", True)
    window.set_extra("sun", True)
    window.sun_timer.stop()
    t = SUN_TIME + 6.5 * 3600.0
    view.sun = sun.direction(t)
    view.navigator.stop()
    view.navigator.set_pose(Pose(58.0105, 56.2294, 1500.0, 90.0, 60.0))
    result["sun_city"] = {"elevation": round(sun.elevation(58.01, 56.23, t),
                                             2)}
    view.update()


@check(40000)
def sun_city_check():
    window = state["window"]
    view = window.view
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_sun_city.png"))
    result["sun_city"]["buildings"] = view.buildings.drawn
    result["sun_city"]["gl_errors"] = dict(view.gl_errors)
    window.set_extra("sun", False)
    window.set_extra("buildings", False)


@check(300)
def tiles_deep():
    # Подложка грузится до подробных уровней над Пермью с 5 км.
    from planetx.core.navigation import Pose
    view = state["window"].view
    view.navigator.stop()
    view.navigator.set_pose(Pose(58.0105, 56.2294, 5000.0, 0.0, 30.0))
    view.update()


@check(40000)
def tiles_deep_check():
    view = state["window"].view
    view._heartbeat()
    levels = [key[0] for key in view.textures]
    result["tiles_deep"] = {"max_level": max(levels) if levels else None,
                            "textures": len(levels),
                            "missing": view.load_missing,
                            "errors": {str(k): str(v) for k, v in
                                       list(state["window"].errors.items())
                                       [:3]},
                            "gl_errors": dict(view.gl_errors)}
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_tiles.png"))


def _body_state(name):
    from planetx.core import ellipsoid
    window = state["window"]
    view = window.view
    levels = [key[0] for key in view.textures]
    pose = view.navigator.pose
    view.grabFramebuffer().save(
        os.path.join(TEMP, "planetx_body_%s.png" % name))
    return {"body": ellipsoid.BODY.key, "a": ellipsoid.A,
            "planet": window.planet.key,
            "textures": len(levels),
            "max_level": max(levels) if levels else None,
            "missing": view.load_missing,
            "source": window.source.name,
            "air": list(view.air_tint) if view.air_tint else None,
            "relief": view.store.scale,
            "pose": [round(pose.lat, 3), round(pose.lon, 3),
                     round(pose.distance)],
            "geo_enabled": not window.panel.geo_items["relief"].isDisabled(),
            "errors": {str(k): str(v) for k, v in
                       list(window.errors.items())[:3]},
            "started": len(window.loader.started),
            "gl_errors": dict(view.gl_errors)}


# Пауза шага - время после него, поэтому смена тела стоит в шаге
# с паузой 20 с, а замер - в следующем.

@check(20000)
def body_mars():
    state["window"].set_body("mars")


@check(20000)
def body_mars_check():
    result["bodies"] = {"mars": _body_state("mars")}
    state["window"].set_body("moon")


@check(20000)
def body_moon_check():
    result["bodies"]["moon"] = _body_state("moon")
    state["window"].set_body("earth")


@check(300)
def body_earth_check():
    result["bodies"]["earth"] = _body_state("earth")


@check(4000)
def body_tools():
    # Инструменты на Марсе: сетка, линейка по экватору, снимок вида.
    from planetx.core.navigation import Pose
    import planetx.ui.snapshot as smod
    window = state["window"]
    window.set_body("mars")
    window.set_extra("grid", True)
    nav = window.view.navigator
    nav.stop()
    nav.set_pose(Pose(0.0, 0.5, 400000.0, 0.0, 0.0))
    window._open_ruler()
    window.ruler_dialog.tabs.setCurrentIndex(0)  # линия
    window.ruler.add(0.0, 0.0)
    window.ruler.add(0.0, 1.0)
    state["terrain_before"] = len(window.view.terrain_loader.started) \
        if window.view.terrain_loader is not None else 0
    path = os.path.join(TEMP, "planetx_body_shot.png")
    if os.path.exists(path):
        os.remove(path)
    smod.QFileDialog.getSaveFileName = staticmethod(
        lambda *args, **kwargs: (path, ""))

    def setup(dialog):
        dialog.keep.setChecked(False)
        dialog.width_px.setValue(1600)
        dialog.height_px.setValue(1200)
    _shot_begin(False, setup)


@check(1500)
def body_tools_check():
    out = _shot_wait()
    if isinstance(out, int):
        return out
    import math
    from qgis.PyQt.QtGui import QImage
    window = state["window"]
    values = window.ruler.values(rubber=False)
    image = QImage(os.path.join(TEMP, "planetx_body_shot.png"))
    view = window.view
    out.update({
        "file": [image.width(), image.height()],
        "grid_shapes": len(window.grid_shapes),
        "length_m": round(values["length"], 1),
        "expect_m": round(2 * math.pi * 3396190.0 / 360.0, 1),
        "ground_m": round(values.get("ground") or 0.0, 1),
        "ground_ready": values.get("ground_ready"),
        "terrain_requests": (len(view.terrain_loader.started)
                             if view.terrain_loader is not None else 0)
        - state["terrain_before"],
        "tool_heights": len(view.tool_heights)})
    result["body_tools"] = out
    window.ruler.clear()
    window.ruler_dialog.close()
    window.set_extra("grid", False)
    window.set_body("earth")
    return None


@check(15000)
def sky_on():
    # Вид неба: Орион. Картинка Млечного пути приходит из кэша QGIS.
    window = state["window"]
    window.set_extra("stars", True)
    window.set_body("sky")
    window.show_sky(85.0, 5.0, 70.0)


def _sky_state(name):
    window = state["window"]
    view = window.view
    view.repaint()
    window.sky_labels.repaint()
    window.grab().save(os.path.join(TEMP, "planetx_sky_%s.png" % name))
    shown = window.sky_labels.shown
    cam = view.camera
    window._hover = (cam.width / 2.0, cam.height / 2.0)
    window._update_cursor()
    return {"sky": view.sky_view is not None,
            "milky_way": view.sky.drawn, "stars": view.stars.drawn,
            "lines": view.constellations.drawn, "bodies": view.bodies.drawn,
            "labels": len(shown),
            "names": [t for k, t, _, _ in shown][:12],
            "navpad": window.navpad.isVisible(),
            "ruler_enabled": window.toolbar.ruler_button.isEnabled(),
            "cursor": window._cursor_text,
            "status": window.status.text().split(chr(10))[0],
            "spinner": window.spinner.isVisible(),
            "attribution": window.attribution.text()[:60],
            "gl_errors": dict(view.gl_errors)}


@check(1500)
def sky_check():
    result["sky"] = {"orion": _sky_state("orion")}
    # Юпитер и Марс осенью 2026 года - в Раке и Льве.
    state["window"].show_sky(135.0, 18.0, 50.0)


@check(300)
def sky_planets():
    window = state["window"]
    result["sky"]["planets"] = _sky_state("planets")
    view = window.view
    view.sky_view.drag(100.0, 0.0, view.camera.height)
    view.sky_view.zoom(0.5)
    result["sky"]["after_drag"] = [round(math.degrees(view.sky_view.ra), 2),
                                   round(view.sky_view.fov, 1)]
    window.set_body("earth")
    result["sky"]["earth"] = {
        "sky": view.sky_view is not None,
        "navpad": window.navpad.isVisible(),
        "ruler_enabled": window.toolbar.ruler_button.isEnabled(),
        "labels_visible": window.sky_labels.isVisible()}


@check(1500)
def sky_toggle():
    # Пункт «Созвездия»: без линий и названий, потом снимок с подписями.
    import planetx.ui.snapshot as smod
    window = state["window"]
    window.set_body("sky")
    window.show_sky(85.0, 5.0, 70.0)
    window.set_constellations(False)
    window.view.repaint()
    window.sky_labels.repaint()
    off = {"lines": window.view.constellations.drawn,
           "names": sum(1 for k, _, _, _ in window.sky_labels.shown
                        if k == "constellation"),
           "stars": sum(1 for k, _, _, _ in window.sky_labels.shown
                        if k == "star")}
    window.set_constellations(True)
    result["sky_toggle"] = {"off": off}
    path = os.path.join(TEMP, "planetx_sky_shot.png")
    if os.path.exists(path):
        os.remove(path)
    smod.QFileDialog.getSaveFileName = staticmethod(
        lambda *args, **kwargs: (path, ""))

    def setup(dialog):
        dialog.keep.setChecked(False)
        dialog.width_px.setValue(2400)
        dialog.height_px.setValue(1600)
    _shot_begin(False, setup)


@check(500)
def sky_toggle_check():
    out = _shot_wait()
    if isinstance(out, int):
        return out
    from qgis.PyQt.QtGui import QImage
    window = state["window"]
    image = QImage(os.path.join(TEMP, "planetx_sky_shot.png"))
    shown = window.sky_labels.shot_shown
    result["sky_toggle"].update({
        "file": [image.width(), image.height()],
        "shot_labels": len(shown),
        "shot_names": [t for _, t, _, _ in shown][:8],
        "lines_on": window.view.constellations.drawn,
        "gl_errors": out.get("gl_errors")})
    window.set_body("earth")
    return None


@check(10000)
def moon_missing():
    # Тайл Луны 6/57/39 в разметке TMS сервер отдаёт кодом 403, его
    # ключ XYZ - (6, 57, 24). Он должен встать вырезкой из предка.
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("moon")
    nav = window.view.navigator
    nav.stop()
    nav.set_pose(Pose(36.6, 143.4, 250000.0, 0.0, 0.0))
    window.view.update()


@check(300)
def moon_missing_check():
    window = state["window"]
    loader = window.loader
    result["moon_missing"] = {
        "url": window.source.tile_url(6, 57, 24),
        "missing": (6, 57, 24) in loader.missing,
        "filled": loader.filled,
        "errors": {str(k): str(v) for k, v in window.errors.items()},
        "attribution": window.attribution.text()}
    window.set_body("earth")


@check(2000)
def moon_tour():
    # Тур по трём меткам на Луне, как из меню «Мои метки».
    from planetx.core.features import Shape
    window = state["window"]
    window.set_body("moon")
    store = window.myplaces
    folder = store.add_folder("Тур по Луне")
    for i, (lat, lon) in enumerate(((0.67, 23.47), (-8.9, 15.5),
                                    (26.1, 3.6))):
        store.add(Shape("point", [(lat, lon)], name="Л%d" % i),
                  folder=folder)
    state["moon_folder"] = folder
    stops = window._tour_stops(None)
    # Выделена метка, а не папка: кнопка ▶ ведёт тур по её папке.
    first = window.myplaces.places_in(folder)[0]
    window.panel.select_place(first.key)
    button = window.panel.tour_button
    result["moon_tour_button"] = {
        "enabled": button.isEnabled(), "tip": button.toolTip(),
        "key_is_folder": window.panel._tour_key(
            window.panel.list.currentItem()) == folder}
    button.click()
    tour = window.tour
    result["moon_tour"] = {
        "stops": len(stops),
        "stop_points": [[round(s.lat, 2), round(s.lon, 2),
                         round(s.distance)] for s in stops],
        "player_stops": len(getattr(tour, "stops", []) or []),
        "playing": bool(getattr(tour, "playing", None)
                        or getattr(tour, "active", None))}


@check(300)
def moon_tour_check():
    window = state["window"]
    tour = window.tour
    pose = window.view.navigator.pose
    result["moon_tour"].update({
        "after": {k: str(getattr(tour, k)) for k in dir(tour)
                  if k in ("playing", "active", "index", "stops")},
        "pose": [round(pose.lat, 2), round(pose.lon, 2),
                 round(pose.distance)],
        "status": window.status.text().split(chr(10))[0]})
    tour.stop()
    window.myplaces.remove(state["moon_folder"])
    window.set_body("earth")


@check(1500)
def sky_tour():
    # Метки неба «Сохранить видом» и тур по ним кнопкой ▶.
    from planetx.core.navigation import Pose
    window = state["window"]
    nav = window.view.navigator
    nav.stop()
    nav.set_pose(Pose(58.0, 56.2, 2.0e7, 0.0, 0.0))
    window.set_body("sky")
    store = window.myplaces
    folder = store.add_folder("Небо")
    state["sky_folder"] = folder
    window.panel.select_place(folder)
    import planetx.ui.window as wmod
    for name, (ra, dec, fov) in (("Орион", (84.0, 0.0, 40.0)),
                                 ("Плеяды", (56.9, 24.1, 8.0)),
                                 ("Вега", (279.2, 38.8, 20.0))):
        window.show_sky(ra, dec, fov)
        wmod.QInputDialog.getText = staticmethod(
            lambda *a, n=name, **k: (n, True))
        window.panel.select_place(folder)
        window.save_view()
    places = store.places_in(folder)
    result["sky_tour"] = {
        "places": [(p.shape.name, p.body,
                    [round(v, 2) for v in p.shape.points[0]])
                   for p in places],
        "stops": len(window._tour_stops(folder)),
        "labels": sorted(t for k, t, _, _ in window.sky_labels.shown
                         if k == "place")}
    window.show_sky(0.0, 0.0, 90.0)
    window.panel.select_place(places[0].key)
    window.panel.tour_button.click()
    state["sky_track"] = []
    view = window.view

    def sample():
        sky = view.sky_view
        if sky is not None:
            state["sky_track"].append((round(math.degrees(sky.ra), 1),
                                       round(math.degrees(sky.dec), 1),
                                       round(sky.fov, 1)))
    timer = QTimer(window)
    timer.timeout.connect(sample)
    timer.start(500)
    state["sky_timer"] = timer


@check(25000)
def sky_tour_wait():
    pass


@check(300)
def sky_tour_check():
    window = state["window"]
    state["sky_timer"].stop()
    track = state["sky_track"]
    window.view.repaint()
    window.sky_labels.repaint()
    result["sky_tour"].update({
        "samples": len(track), "track": track[::6],
        "max_fov": max((t[2] for t in track), default=None),
        "playing": bool(window.tour.playing),
        "labels": sorted(t for k, t, _, _ in window.sky_labels.shown
                         if k == "place")})
    window.grab().save(os.path.join(TEMP, "planetx_sky_tour.png"))
    window.tour.stop()
    # Перелёт к метке неба с Земли включает небо.
    window.set_body("earth")
    globe = window.view.navigator.pose
    place = window.myplaces.places_in(state["sky_folder"])[2]
    window.fly_to_place(place)
    result["sky_tour"]["fly"] = {"sky": window.view.sky_view is not None}
    window.set_body("earth")
    back = window.view.navigator.pose
    result["sky_tour"]["globe_back"] = [
        round(globe.lat, 3) == round(back.lat, 3),
        round(globe.distance) == round(back.distance)]
    window.myplaces.remove(state["sky_folder"])


@check(4000)
def sky_record():
    # Новая метка щелчком по небу и запись тура с экрана на небе.
    import planetx.ui.window as wmod
    window = state["window"]
    window.set_body("sky")
    window.show_sky(84.0, 0.0, 60.0)
    view = window.view
    window._open_place()
    cam = view.camera
    window._clicked(cam.width / 2.0, cam.height / 2.0)
    window._refresh_shapes()
    preview = [n for _, n in view.sky_places]
    window._save_place()
    window.place_dialog.close()
    state["sky_new"] = [p for p in window.myplaces.places
                        if p.body == "sky"][-1]
    result["sky_record"] = {
        "tools": {"place": window.toolbar.place_button.isEnabled(),
                  "record": window.toolbar.record.isEnabled(),
                  "save": window.toolbar.save_button.isEnabled()},
        "preview": preview,
        "new": [state["sky_new"].shape.name, state["sky_new"].body,
                [round(v, 2) for v in state["sky_new"].shape.points[0]]]}
    wmod.QInputDialog.getText = staticmethod(
        lambda *a, **k: ("Тур по небу", True))
    window.toolbar.record.setChecked(True)
    steps = iter(range(12))

    def move():
        if next(steps, None) is None:
            state["sky_move"].stop()
            return
        view.sky_view.drag(40.0, -10.0, cam.height)
        view.sync_sky_pose()
        view.update()
    timer = QTimer(window)
    timer.timeout.connect(move)
    timer.start(250)
    state["sky_move"] = timer


@check(6000)
def sky_record_stop():
    window = state["window"]
    window.toolbar.record.setChecked(False)
    tours = [p for p in window.myplaces.places
             if p.body == "sky" and p.tour]
    result["sky_record"]["tour"] = [(p.shape.name, len(p.tour))
                                    for p in tours]
    state["sky_rec"] = tours[-1] if tours else None
    window.show_sky(0.0, 60.0, 60.0)
    if state["sky_rec"] is not None:
        window._place_action("tour", state["sky_rec"].key)
    state["sky_rec_track"] = []

    def sample():
        sky = window.view.sky_view
        if sky is not None:
            state["sky_rec_track"].append(round(math.degrees(sky.ra), 1))
    timer = QTimer(window)
    timer.timeout.connect(sample)
    timer.start(300)
    state["sky_rec_timer"] = timer


@check(300)
def sky_record_check():
    window = state["window"]
    state["sky_rec_timer"].stop()
    track = state["sky_rec_track"]
    result["sky_record"]["replay_ra"] = [track[0], track[-1]] \
        if track else None
    window.tour.stop()
    window.show_sky(279.2, 38.8, 20.0)
    window.view.repaint()
    window.sky_labels.repaint()
    for place in (state["sky_new"], state["sky_rec"]):
        if place is not None:
            window.myplaces.remove(place.key)
    window.set_body("earth")


SITE_SHOTS = os.path.join(ROOT, "doc", "images")


@check(25000)
def site_mars():
    # Снимки для сайта: Марс над Фарсидой и долинами Маринер.
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("mars")
    nav = window.view.navigator
    nav.stop()
    nav.set_pose(Pose(-2.0, -85.0, 8.5e6, 0.0, 0.0))
    window.view.update()


@check(25000)
def site_moon():
    from planetx.core.navigation import Pose
    window = state["window"]
    window.view.grabFramebuffer().save(
        os.path.join(SITE_SHOTS, "mars.jpg"), "JPG", 92)
    window.set_body("moon")
    nav = window.view.navigator
    nav.stop()
    nav.set_pose(Pose(8.0, 12.0, 4.6e6, 0.0, 0.0))
    window.view.update()


@check(15000)
def site_sky():
    window = state["window"]
    window.view.grabFramebuffer().save(
        os.path.join(SITE_SHOTS, "moon.jpg"), "JPG", 92)
    window.set_extra("stars", True)
    window.set_body("sky")
    window.show_sky(88.0, 8.0, 75.0)


@check(300)
def site_sky_save():
    from qgis.PyQt.QtGui import QPainter
    window = state["window"]
    view = window.view
    view.repaint()
    image = view.grabFramebuffer()
    # Картинка с масштабом экрана 2 рисуется в логических пикселях,
    # подписи уехали бы вдвое. Подписи считаются в пикселях кадра.
    image.setDevicePixelRatio(1.0)
    painter = QPainter(image)
    try:
        window.sky_labels.draw(painter, image.width(), image.height(),
                               view.devicePixelRatioF())
    finally:
        painter.end()
    image.save(os.path.join(SITE_SHOTS, "sky.jpg"), "JPG", 92)
    window.set_body("earth")
    result["site_shots"] = {name: os.path.getsize(
        os.path.join(SITE_SHOTS, name)) for name in
        ("mars.jpg", "moon.jpg", "sky.jpg")}


@check(25000)
def moon_holes():
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("moon")
    nav = window.view.navigator
    nav.stop()
    nav.set_pose(Pose(8.0, 12.0, 4.6e6, 0.0, 0.0))
    window.view.update()


@check(300)
def moon_holes_check():
    # Сторож: смешивание, оставленное включённым до кадра, не белит
    # перекрытые поверхности Луны. Белых пикселей - только шапки.
    import numpy as np
    from OpenGL import GL
    from qgis.PyQt.QtGui import QImage
    window = state["window"]
    view = window.view

    def white():
        img = view.grabFramebuffer().convertToFormat(
            QImage.Format.Format_RGB888)
        ptr = img.constBits()
        ptr.setsize(img.sizeInBytes())
        a = np.frombuffer(ptr, np.uint8).reshape(
            img.height(), img.bytesPerLine())[:, :img.width() * 3]
        a = a.reshape(img.height(), img.width(), 3)
        return int((a.min(axis=2) > 200).sum())
    clean = white()
    view.makeCurrent()
    GL.glEnable(GL.GL_BLEND)
    GL.glBlendFunc(GL.GL_ONE, GL.GL_ONE)
    view.doneCurrent()
    forced = white()
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_moon_a.png"))
    result["moon_holes"] = {"white": clean, "white_after_blend": forced,
                            "levels": sorted({k[0] for k in
                                              view.selection.draw})}
    window.set_body("earth")

DEMOS = ("perm", "bocachica", "mars", "jezero", "moon", "sky")


def _demo_open(name):
    window = state["window"]
    state.setdefault("demo_keys", []).append(window.open_demo(name))


def _demo_check(name):
    window = state["window"]
    folder = window.myplaces.folders[-1].key \
        if window.myplaces.folders else None
    places = window.myplaces.places_in(folder) if folder else []
    result.setdefault("demos", {})[name] = {
        "body": window.body_key(),
        "places": len(places),
        "bodies": sorted({p.body for p in places}),
        "stops": len(window._tour_stops(folder)),
        "status": window.status.text().split(chr(10))[0]}
    if folder:
        window.myplaces.remove(folder)


def _demo_steps():
    for i, name in enumerate(DEMOS):
        prev = DEMOS[i - 1] if i else None

        def step(name=name, prev=prev):
            if prev is not None:
                _demo_check(prev)
            _demo_open(name)
        step.__name__ = "demo_" + name
        check(8000)(step)

    def demo_done():
        _demo_check(DEMOS[-1])
        state["window"].set_body("earth")
    check(300)(demo_done)


_demo_steps()


def _cursor_at_center(window):
    """Строка под курсором в середине вида: широта, долгота, высота
    или глубина."""
    view = window.view
    from planetx.core.ellipsoid import ecef_to_geodetic
    from planetx.core.navigation import ground_under
    window._hover = (view.width() / 2.0, view.height() / 2.0)
    window._update_cursor()
    point = ground_under(view.camera, *window._hover,
                         view.navigator.pose.terrain)
    lat, lon, h = (float(v) for v in ecef_to_geodetic(point))
    terrain = view.navigator.pose.terrain
    return {"text": window._cursor_text,
            "store_m": round(view.store.height_at(lat, lon)
                             / (view.store.scale or 1.0)),
            "terrain": terrain is not None}


@check(25000)
def seafloor_on():
    # Дно океана: Марианский жёлоб с 600 км, строка «Дно океана».
    from planetx.core.features import Shape
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    nav = window.view.navigator
    nav.stop()
    # show, а не set_pose: поза с рельефом, по нему ищется точка
    # под курсором.
    nav.show(Pose(11.35, 142.4, 600000.0, 0.0, 30.0))
    window.set_sea_depths(True)
    key = window.myplaces.add(Shape("line", [(10.6, 142.5), (12.2, 142.5)],
                                    name="Через жёлоб"))
    state["sf_key"] = key
    window._place_action("profile", key)
    result["seafloor"] = {"flag": window.view.sea_floor}


@check(15000)
def seafloor_check():
    import numpy as np
    window = state["window"]
    view = window.view
    out = result["seafloor"]
    store = view.store
    trench = store.heights_at(np.array([11.35]), np.array([142.2]),
                              scaled=False)
    out["trench_m"] = round(float(trench[0]))
    out["store_low"] = round(store.low)
    window.profile_dialog.refresh()
    p = window.profile_dialog.chart.profile
    out["profile_low"] = round(float(p.low)) if p is not None else None
    out["profile_high"] = round(float(p.high)) if p is not None else None
    out["gl"] = dict(view.gl_errors)
    out["cursor"] = _cursor_at_center(window)
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_seafloor.png"))
    window.profile_dialog.grab().save(os.path.join(
        TEMP, "planetx_seafloor_profile.png"))
    # Чёрное море: середина западной котловины.
    from planetx.core.navigation import Pose
    view.navigator.stop()
    view.navigator.show(Pose(43.2, 31.5, 400000.0, 0.0, 20.0))


@check(15000)
def seafloor_black_sea():
    import numpy as np
    window = state["window"]
    view = window.view
    out = result["seafloor"]
    h = view.store.heights_at(np.array([43.2]), np.array([31.5]),
                              scaled=False)
    out["black_sea_m"] = round(float(h[0]))
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_seafloor_black.png"))
    window.set_sea_depths(False)


@check(10000)
def seafloor_off():
    import numpy as np
    window = state["window"]
    view = window.view
    out = result["seafloor"]
    h = view.store.heights_at(np.array([43.2]), np.array([31.5]),
                              scaled=False)
    out["off_black_sea_m"] = round(float(h[0]))
    out["off_flag"] = view.sea_floor
    out["off_cursor"] = _cursor_at_center(window)
    out["gl_after"] = dict(view.gl_errors)
    view.grabFramebuffer().save(os.path.join(
        TEMP, "planetx_seafloor_black_off.png"))
    # Флажок окна свойств вида и автообновление - умолчания.
    window._show_properties()
    out["properties_sea"] = window.properties.sea.isChecked()
    window.properties.sea.setChecked(True)
    out["after_checkbox"] = view.sea_floor
    out["auto_refresh"] = window.auto_refresh
    out["panel_row"] = "seafloor" in window.panel.extra_items
    window.properties.close()
    window.profile_dialog.close()
    window.myplaces.remove(state["sf_key"])


@check(15000)
def quakes_on():
    # Землетрясения: сводка USGS, вид на Японию и Курилы с наклоном.
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    nav = window.view.navigator
    nav.stop()
    nav.set_pose(Pose(38.0, 142.0, 3000000.0, 0.0, 45.0))
    window.set_extra("quakes", True)
    result["quakes"] = {"legend": window.quake_legend.isVisible()}


@check(3000)
def quakes_check():
    window = state["window"]
    view = window.view
    out = result["quakes"]
    out["events"] = len(window.quake_events)
    out["error"] = window.quake_error
    out["depths"] = sorted(round(q.depth) for q in window.quake_events)[-3:]
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_quakes.png"))
    out["drawn"] = view.quakes.drawn
    out["usgs_credit"] = "USGS" in window.attribution.text()
    out["gl"] = dict(view.gl_errors)
    # Шкала времени: последние 7 суток сводки.
    out["time_known"] = window.timebar.known
    window.toolbar.set_time_shown(True)
    window._time_toggled(True)
    lo, hi = window.timebar.extent()
    out["extent_days"] = round((hi - lo) / 86400.0, 1)
    window.timebar.set_range(hi - 7 * 86400.0, hi)
    out["window_days"] = round((view.quakes.window[1]
                                - view.quakes.window[0]) / 86400.0, 1)
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_quakes_week.png"))
    out["drawn_week"] = view.quakes.drawn
    window.toolbar.set_time_shown(False)
    window._time_toggled(False)
    view.grabFramebuffer()
    out["drawn_closed"] = view.quakes.drawn
    window.set_extra("quakes", False)


def _land_share(view):
    """Доля пикселей кадра цвета суши палеогеографии: красный заметно
    больше синего. Океан и небо синие."""
    import numpy as np
    image = view.grabFramebuffer()
    bits = image.constBits()
    if hasattr(bits, "setsize"):
        bits.setsize(image.sizeInBytes())
    a = np.frombuffer(bits, dtype=np.uint8).reshape(
        image.height(), image.width(), 4).astype(int)
    # Формат ARGB32: в памяти синий, зелёный, красный, альфа. Суша
    # карт возраста зелёная и бурая, море синее.
    land = (a[..., 2] + a[..., 1]) // 2 > a[..., 0] + 15
    return round(float(land.mean()), 4)


def _fake_model():
    """Поддельный сервер модели на 127.0.0.1 в потоке: на вопрос
    отвечает вызовом инструмента, на ответ инструмента - текстом.
    Понимает Anthropic Messages (/v1/messages) и Responses (/responses).
    Запросы складываются в список для проверки."""
    import http.server
    import threading
    seen = []
    kml = ('<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
           '<name>Проба помощника</name><Placemark><name>Токио</name>'
           '<Point><coordinates>139.69,35.69,0</coordinates></Point>'
           '</Placemark></Document></kml>')

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            return None

        def do_POST(self):
            body = json.loads(self.rfile.read(
                int(self.headers["Content-Length"])))
            seen.append((self.path, body,
                         self.headers.get("x-api-key")
                         or self.headers.get("Authorization")))
            if self.path.endswith("/messages"):
                last = body["messages"][-1]["content"]
                if isinstance(last, str):
                    answer = {"content": [
                        {"type": "text", "text": "Лечу к Японии."},
                        {"type": "tool_use", "id": "t1", "name": "fly_to",
                         "input": {"lat": 36.0, "lon": 138.0,
                                   "distance_km": 1500}}]}
                else:
                    answer = {"content": [{"type": "text",
                                           "text": "Готово."}]}
            elif self.path.endswith("/chat/completions"):
                last = body["messages"][-1]
                if "tools" not in body:
                    # Создание меток: KML текстом, в ограде Markdown,
                    # с датой события до нашей эры.
                    made = kml.replace(
                        "</Point>", "</Point><TimeStamp><when>-0263-06"
                        "</when></TimeStamp>")
                    if body.get("stream"):
                        self.stream(made, "медленно" in last["content"])
                        return
                    answer = {"choices": [{"message": {
                        "role": "assistant",
                        "content": "Вот:\n```xml\n" + made + "\n```"}}]}
                elif last["role"] == "user":
                    answer = {"choices": [{"message": {
                        "role": "assistant", "content": None,
                        "tool_calls": [{"id": "k1", "type": "function",
                                        "function": {
                                            "name": "fly_to",
                                            "arguments": json.dumps(
                                                {"lat": -33.9,
                                                 "lon": 151.2})}}]}}]}
                else:
                    answer = {"choices": [{"message": {
                        "role": "assistant", "content": "Сидней."}}]}
            else:
                last = body["input"][-1]
                if last.get("role") == "user":
                    answer = {"output": [{
                        "type": "function_call", "call_id": "c1",
                        "name": "add_kml",
                        "arguments": json.dumps({"kml": kml})}]}
                else:
                    answer = {"output": [{"type": "message", "content": [
                        {"type": "output_text", "text": "Предложил."}]}]}
            data = json.dumps(answer).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def stream(self, made, slow):
            """Ответ потоком событий SSE формата Chat. Быстрый - документ
            made шестью кусками. Медленный - 12 меток, по одной в 0.3 с,
            его останавливает шаг assistant_stop_check."""
            if slow:
                mark = made[made.index("<Placemark>"):
                            made.index("</Placemark>") + len("</Placemark>")]
                head = made[:made.index("<Placemark>")]
                parts = [head] + [mark.replace("Токио", "Токио %d" % n)
                                  for n in range(12)] + ["</Document></kml>"]
                pause = 0.3
            else:
                text = "Вот:\n```xml\n" + made + "\n```"
                size = max(1, len(text) // 6)
                parts = [text[i:i + size] for i in range(0, len(text), size)]
                pause = 0.05
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            try:
                self.wfile.write(b": PROCESSING\n\n")
                for part in parts:
                    event = {"choices": [{"delta": {"content": part}}]}
                    self.wfile.write(("data: " + json.dumps(
                        event, ensure_ascii=False) + "\n\n").encode("utf-8"))
                    self.wfile.flush()
                    time.sleep(pause)
                self.wfile.write(b"data: [DONE]\n\n")
            except OSError:
                # Клиент оборвал поток - шаг остановки.
                seen.append(("stream aborted", {}, None))

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, seen


def _use_service(dialog, provider, base):
    """Сервис и адрес помощника через окно «Настройки помощника»."""
    dialog.open_settings()
    settings = dialog.settings
    settings.provider.setCurrentIndex(settings.provider.findData(provider))
    settings.base.setText(base)
    settings._remember()
    return settings


@check(4000)
def assistant_on():
    # Помощник через поддельный сервер: Anthropic - перелёт к Японии.
    from planetx.core import assistant as ai
    from planetx.ui import assistant as ui_ai
    window = state["window"]
    window.set_body("earth")
    server, seen = _fake_model()
    state["fake_model"] = (server, seen)
    state.setdefault("real_load_key", ui_ai.load_key)
    ui_ai.load_key = lambda provider: "test-key"
    window.open_assistant()
    dialog = window.assistant_dialog
    _use_service(dialog, ai.ANTHROPIC,
                 "http://127.0.0.1:%d" % server.server_port)
    dialog.input.setText("Покажи Японию")
    dialog.send()
    result["assistant"] = {}


@check(2000)
def assistant_anthropic_check():
    from planetx.core import assistant as ai
    window = state["window"]
    dialog = window.assistant_dialog
    server, seen = state["fake_model"]
    out = result["assistant"]
    out["requests"] = [p for p, _, _ in seen]
    out["key_header"] = seen[0][2] if seen else None
    second = seen[1][1]["messages"][-1]["content"][0] if len(seen) > 1 \
        else None
    out["tool_result"] = second
    out["history"] = dialog.history.toPlainText()
    pose = window.view.navigator.pose
    out["pose"] = [round(pose.lat, 1), round(pose.lon, 1)]
    # Responses: предложение KML и запись в «Мои метки».
    del seen[:]
    _use_service(dialog, ai.RESPONSES,
                 "http://127.0.0.1:%d" % server.server_port)
    dialog.input.setText("Поставь метку в Токио")
    dialog.send()
    state["places_before"] = len(window.myplaces.places)


@check(1000)
def assistant_responses_check():
    window = state["window"]
    dialog = window.assistant_dialog
    server, seen = state["fake_model"]
    out = result["assistant"]
    out["responses_requests"] = [p for p, _, _ in seen]
    out["responses_key"] = seen[0][2] if seen else None
    out["function_output"] = seen[1][1]["input"][-1] if len(seen) > 1 \
        else None
    out["proposal_shown"] = dialog.proposal.isVisible()
    out["proposal_text"] = dialog.proposal_text.text()
    dialog._accept_place()
    out["places_added"] = len(window.myplaces.places) \
        - state["places_before"]
    tokyo = [p for p in window.myplaces.places if p.name == "Токио"]
    out["tokyo"] = [list(p.shape.points[0]) for p in tokyo]
    out["folder"] = getattr(window, "assistant_folder", None)
    if out["folder"]:
        window.myplaces.remove(out["folder"])
    out["places_after_cleanup"] = len(window.myplaces.places) \
        - state["places_before"]
    dialog.grab().save(os.path.join(TEMP, "planetx_assistant.png"))
    out["context"] = window.assistant_context()
    dialog.close()
    server.shutdown()
    out["gl"] = dict(window.view.gl_errors)


@check(1000)
def assistant_tools():
    # Остальные инструменты помощника - напрямую через исполнитель окна.
    from planetx.core.assistant import Call
    window = state["window"]
    # Глубины - умолчание модуля, прерванный прогон мог их выключить.
    window.set_sea_depths(True)
    window._want_crust()
    window.set_extra("quakes", True)
    state["tools_started"] = time.monotonic()


@check(1000)
def assistant_tools_check():
    from planetx.core.assistant import Call
    window = state["window"]
    if ((window.crust is None or not window.quake_events)
            and time.monotonic() - state["tools_started"] < 60.0):
        return 1000
    out = result.setdefault("assistant", {})

    def run(name, **args):
        return window.assistant_tool(Call("x", name, args))
    out["point_info"] = run("point_info", lat=38.5, lon=142.0)
    out["quakes_summary"] = run("quakes_summary", south=30, north=46,
                                west=128, east=150)[:300]
    out["set_layer"] = run("set_layer", key="grid", on=True)
    out["set_layer_bad"] = run("set_layer", key="nope", on=True)
    out["cutaway"] = run("earth_cutaway", west=100, east=150, south=0,
                         north=60)
    out["cutaway_off"] = run("earth_cutaway", off=True)
    out["section"] = run("section_down", points=[[38.5, 146], [38.5, 132]],
                         depth_km=700)
    out["get_kml"] = run("get_kml")[:160]
    out["bad_args"] = run("fly_to", lat="x")
    out["unknown"] = run("teleport")
    run("set_layer", key="grid", on=False)
    window.set_extra("quakes", False)
    if window.section_dialog is not None:
        window.section_dialog.close()
    out["tools_gl"] = dict(window.view.gl_errors)


@check(3000)
def assistant_search():
    # Просьба словами в строке «Поиск» уходит помощнику в скрытом окне,
    # ответ - под строкой. Сервер модели поддельный.
    from qgis.core import QgsSettings
    from planetx.core import assistant as ai
    from planetx.ui import assistant as ui_ai
    window = state["window"]
    window.set_body("earth")
    server, seen = _fake_model()
    state["fake_search"] = (server, seen)
    state.setdefault("real_load_key", ui_ai.load_key)
    ui_ai.load_key = lambda provider: "test-key"
    QgsSettings().setValue(ui_ai.SEARCH_KEY, True)
    dialog = window._assistant()
    dialog.hide()
    _use_service(dialog, ai.ANTHROPIC,
                 "http://127.0.0.1:%d" % server.server_port)
    window.view.navigator.stop()
    window.place.setText("Покажи Японию")
    window.fly()
    result["assistant_search"] = {
        "busy_text": window.panel.answer.text(),
        "busy_shown": window.panel.answer.isVisible()}


@check(1000)
def assistant_search_check():
    from qgis.core import QgsSettings
    from planetx.ui import assistant as ui_ai
    window = state["window"]
    dialog = window.assistant_dialog
    server, seen = state["fake_search"]
    out = result["assistant_search"]
    out["requests"] = [p for p, _, _ in seen]
    out["question"] = seen[0][1]["messages"][-1]["content"] if seen \
        else None
    out["answer"] = window.panel.answer.text()
    out["dialog_shown"] = dialog.isVisible()
    pose = window.view.navigator.pose
    out["pose"] = [round(pose.lat, 1), round(pose.lon, 1)]
    # Флажок окна снят - строка поиска помощнику ничего не шлёт.
    dialog.settings.search.setChecked(False)
    out["setting_off"] = QgsSettings().value(ui_ai.SEARCH_KEY, True,
                                             type=bool)
    before = len(seen)
    out["asked_when_off"] = window.ask_assistant("покажи Марс")
    out["requests_when_off"] = len(seen) - before
    dialog.settings.search.setChecked(True)
    # Пустая строка прячет ответ.
    window.place.setText("")
    out["answer_after_clear"] = window.panel.answer.isVisible()
    # Свой сервис формата OpenAI Chat на этом компьютере: без ключа.
    from planetx.core import assistant as ai
    ui_ai.load_key = lambda provider: ""
    del seen[:]
    _use_service(dialog, ai.LOCAL,
                 "http://127.0.0.1:%d" % server.server_port)
    out["chat_asked"] = dialog.ask("Покажи Сидней")


@check(1000)
def assistant_chat_check():
    window = state["window"]
    dialog = window.assistant_dialog
    server, seen = state["fake_search"]
    out = result["assistant_search"]
    out["chat_requests"] = [p for p, _, _ in seen]
    out["chat_auth"] = [k for _, _, k in seen]
    out["chat_tool_answer"] = seen[1][1]["messages"][-1] \
        if len(seen) > 1 else None
    out["chat_answer"] = window.panel.answer.text()
    pose = window.view.navigator.pose
    out["chat_pose"] = [round(pose.lat, 1), round(pose.lon, 1)]
    # Удалённому сервису без ключа вопрос не уходит.
    from planetx.core import assistant as ai
    del seen[:]
    _use_service(dialog, ai.OPENROUTER, ai.DEFAULTS[ai.OPENROUTER][0])
    out["remote_without_key"] = dialog.ask("Покажи Сидней")
    out["remote_requests"] = len(seen)
    # Ключ без мастер-пароля: открытым текстом в настройках профиля,
    # менеджер паролей не трогается.
    from qgis.core import QgsSettings
    from planetx.ui import assistant as ui_ai
    ui_ai.load_key = state["real_load_key"]
    settings = QgsSettings()
    dialog.settings.plain.setChecked(True)
    out["plain_setting"] = settings.value(ui_ai.PLAIN_KEY, False, type=bool)
    dialog.settings.key.setText("plain-test-key")
    dialog.settings._save_key()
    out["plain_note"] = dialog.settings.status.text()
    out["plain_loaded"] = ui_ai.load_key(ai.OPENROUTER) == "plain-test-key"
    out["plain_ready"] = ui_ai.ready(ai.OPENROUTER)
    out["plain_authcfg"] = settings.value(
        ui_ai.SETTINGS + ai.OPENROUTER + "/authcfg", "")
    settings.remove(ui_ai.SETTINGS + ai.OPENROUTER + "/key")
    dialog.settings.plain.setChecked(True)
    out["plain_after_cleanup"] = ui_ai.load_key(ai.OPENROUTER)
    # Окно помощника - сервис и модель видны строкой сверху.
    out["service_line"] = dialog.service.text()
    out["placeholder"] = bool(dialog.history.placeholderText())
    # Свой сервис не запущен: порт закрыт, ответа нет вовсе.
    import socket
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    closed = probe.getsockname()[1]
    probe.close()
    ui_ai.load_key = lambda provider: ""
    _use_service(dialog, ai.LOCAL, "http://127.0.0.1:%d" % closed)
    out["down_asked"] = dialog.ask("Покажи Сидней")
    ui_ai.load_key = state["real_load_key"]
    state["down_settings"] = settings
    state["down_started"] = time.monotonic()


@check(5000)
def assistant_down_check():
    from planetx.core import assistant as ai
    from planetx.ui import assistant as ui_ai
    window = state["window"]
    dialog = window.assistant_dialog
    out = result["assistant_search"]
    waited = time.monotonic() - state["down_started"]
    if dialog.busy() and waited < 30.0:
        return 1000
    out["down_wait"] = round(waited, 1)
    out["down_busy"] = dialog.busy()
    lines = dialog.history.toPlainText().splitlines()
    out["down_notes"] = [x for x in lines[-4:] if x.startswith("Модуль")]
    settings = state["down_settings"]
    # Адреса поддельного сервера не остаются в настройках профиля.
    for provider in ai.PROVIDERS:
        settings.remove(ui_ai.SETTINGS + provider + "/base")
    settings.remove(ui_ai.SETTINGS + "provider")
    dialog.close()
    state["fake_search"][0].shutdown()
    out["gl"] = dict(window.view.gl_errors)


@check(3000)
def assistant_make():
    # Метки по описанию одним запросом: кнопка у строки «Поиск».
    from qgis.core import QgsSettings
    from planetx.core import assistant as ai
    from planetx.ui import assistant as ui_ai
    window = state["window"]
    window.set_body("earth")
    server, seen = _fake_model()
    state["fake_make"] = (server, seen)
    state.setdefault("real_load_key", ui_ai.load_key)
    ui_ai.load_key = lambda provider: "test-key"
    dialog = window._assistant()
    dialog.hide()
    _use_service(dialog, ai.OPENROUTER,
                 "http://127.0.0.1:%d" % server.server_port)
    dialog.settings.close()
    state["make_before"] = len(window.myplaces.places)
    state["make_progress"] = []
    dialog.progress.connect(state["make_progress"].append)
    window.view.navigator.stop()
    window.place.setText("Токио")
    # Кнопки помощника у строки нет с 5 октября 2026 года, Ctrl+Enter.
    window.panel._make()
    result["assistant_make"] = {"busy": dialog.busy()}


@check(1000)
def assistant_make_check():
    from qgis.core import QgsSettings
    from planetx.core import assistant as ai
    from planetx.ui import assistant as ui_ai
    from planetx.core.when import text as when_text
    window = state["window"]
    dialog = window.assistant_dialog
    server, seen = state["fake_make"]
    out = result["assistant_make"]
    out["requests"] = [p for p, _, _ in seen]
    out["tools_sent"] = "tools" in seen[0][1] if seen else None
    out["max_tokens"] = seen[0][1].get("max_tokens") if seen else None
    out["stream_asked"] = seen[0][1].get("stream") if seen else None
    out["progress"] = list(state["make_progress"])
    out["busy_after"] = dialog.busy()
    out["places_added"] = len(window.myplaces.places) - state["make_before"]
    key = getattr(window, "made_folder", None)
    made = window.myplaces.places_in(key) if key else []
    out["names"] = [p.name for p in made]
    out["times"] = [p.time for p in made]
    out["timed_in_answer"] = "со временем 1" in window.panel.answer.text()
    out["timebar_shown"] = window.timebar.shown()
    out["time_range"] = [when_text(v) for v in window.timebar.range()] \
        if window.timebar.shown() else None
    out["answer"] = window.panel.answer.text()
    out["dialog_shown"] = dialog.isVisible()
    pose = window.view.navigator.target if hasattr(
        window.view.navigator, "target") else None
    # Ссылка «Отменить» удаляет созданную папку.
    window.panel._answer_link("undo")
    out["places_after_undo"] = len(window.myplaces.places) \
        - state["make_before"]
    out["answer_after_undo"] = window.panel.answer.text()
    if window.timebar.shown():
        window._time_bar_closed()
        window.timebar.close_bar()
    # Пустая строка - запроса нет.
    del seen[:]
    window.place.setText("")
    out["empty_asked"] = window.make_places("")
    out["empty_requests"] = len(seen)
    settings = QgsSettings()
    for provider in ai.PROVIDERS:
        settings.remove(ui_ai.SETTINGS + provider + "/base")
    settings.remove(ui_ai.SETTINGS + "provider")
    ui_ai.load_key = state["real_load_key"]
    dialog.close()
    server.shutdown()
    out["gl"] = dict(window.view.gl_errors)


@check(1500)
def assistant_stop():
    # Медленный поток из 12 меток останавливается ссылкой «Остановить»:
    # метки, пришедшие целиком, записываются.
    from planetx.core import assistant as ai
    from planetx.ui import assistant as ui_ai
    window = state["window"]
    window.set_body("earth")
    server, seen = _fake_model()
    state["fake_stop"] = (server, seen)
    state.setdefault("real_load_key", ui_ai.load_key)
    ui_ai.load_key = lambda provider: "test-key"
    dialog = window._assistant()
    dialog.hide()
    _use_service(dialog, ai.OPENROUTER,
                 "http://127.0.0.1:%d" % server.server_port)
    dialog.settings.close()
    state["stop_before"] = len(window.myplaces.places)
    window.place.setText("Токио медленно")
    result["assistant_stop"] = {"asked": window.make_places(
        "Токио медленно")}


@check(1000)
def assistant_stop_check():
    window = state["window"]
    out = result["assistant_stop"]
    out["busy_before"] = window.assistant_dialog.busy()
    out["answer_before"] = window.panel.answer.text()
    out["stop_link"] = 'href="stop"' in out["answer_before"]
    # Значок ожидания у строки поиска крутится, пока идёт ответ.
    out["spinner_busy"] = [window.panel.busy.busy(),
                           window.panel.busy.isVisible(),
                           window.panel.busy.toolTip()]
    window.panel._answer_link("stop")


@check(1000)
def assistant_stop_done():
    from qgis.core import QgsSettings
    from planetx.core import assistant as ai
    from planetx.ui import assistant as ui_ai
    window = state["window"]
    dialog = window.assistant_dialog
    server, seen = state["fake_stop"]
    out = result["assistant_stop"]
    out["busy_after"] = dialog.busy()
    out["spinner_after"] = [window.panel.busy.busy(),
                            window.panel.busy.isVisible()]
    out["places_added"] = len(window.myplaces.places) - state["stop_before"]
    out["answer"] = window.panel.answer.text()
    out["aborted_on_server"] = any(p == "stream aborted" for p, _, _ in seen)
    window.undo_made_places()
    if window.timebar.shown():
        window._time_bar_closed()
        window.timebar.close_bar()
    window.place.setText("")
    settings = QgsSettings()
    for provider in ai.PROVIDERS:
        settings.remove(ui_ai.SETTINGS + provider + "/base")
    settings.remove(ui_ai.SETTINGS + "provider")
    settings.remove("PlanetX/search_history")
    ui_ai.load_key = state["real_load_key"]
    dialog.close()
    server.shutdown()
    out["gl"] = dict(window.view.gl_errors)


# Падение с повреждением кучи 4 октября 2026 года: стек автора -
# QgsVectorTileLoader::downloadBlocking в потоке QgsMapRendererParallelJob,
# проверочный QGIS - нарушение доступа на get() главного потока. Шаг
# перелетает по новым местам с основой OpenFreeMap. PLANETX_STRESS_JOBS -
# отрисовок наложения одновременно, по умолчанию как в модуле.
STRESS_SECONDS = 60.0
STRESS_PERIOD = 250  # плавное движение, как в падении шага odd_text_wait
STRESS_JUMP = 3.0  # скачок в новое место, с


@check(1000)
def vt_stress():
    import random
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.set_relief(True)
    seed = int(time.time())
    state["stress_rnd"] = random.Random(seed)
    state["stress_started"] = time.monotonic()
    jobs = os.environ.get("PLANETX_STRESS_JOBS")
    state["stress_jobs"] = int(jobs) if jobs else None
    result["vt_stress"] = {"seed": seed, "jobs_limit": state["stress_jobs"],
                           "flights": 0, "max_jobs": 0, "groups":
                           sorted(window._groups)}
    window.view.navigator.stop()
    window.view.navigator.show(Pose(50.0, 10.0, 80000.0, 0.0, 40.0))


@check(STRESS_PERIOD)
def vt_stress_run():
    from planetx.core.navigation import Pose
    window = state["window"]
    out = result["vt_stress"]
    overlay = window.overlay
    if overlay is not None:
        if state["stress_jobs"]:
            overlay.queue.max_active = state["stress_jobs"]
        if os.environ.get("PLANETX_STRESS_NOCANCEL") \
                and not getattr(overlay, "_stress_patched", False):
            # Опыт: ушедший из кадра тайл не отменяется, задание
            # дорисовывается, картинка выбрасывается.
            def retain(keys, overlay=overlay):
                for key in overlay.queue.retain(keys):
                    job = overlay.jobs.pop(key, None)
                    if job is not None:
                        job.finished.disconnect()
                        job.finished.connect(
                            lambda job=job: overlay._retire(job))
                        overlay.retired.add(job)
                    overlay.queue.done(key, ok=True)
                overlay._later()
            overlay.retain = retain
            overlay._stress_patched = True
        out["max_retired"] = max(out.get("max_retired", 0),
                                 len(overlay.retired))
        out["max_jobs"] = max(out["max_jobs"], len(overlay.jobs))
    now = time.monotonic()
    if now - state["stress_started"] < STRESS_SECONDS:
        rnd = state["stress_rnd"]
        if now - state.get("stress_jump", 0.0) >= STRESS_JUMP:
            # Суша умеренных широт: Европа, Азия, Америки.
            state["stress_jump"] = now
            lat = rnd.uniform(25.0, 60.0)
            lon = rnd.choice((rnd.uniform(-10.0, 60.0),
                              rnd.uniform(60.0, 135.0),
                              rnd.uniform(-120.0, -75.0)))
            window.view.navigator.show(Pose(
                lat, lon, rnd.uniform(60000.0, 400000.0),
                rnd.uniform(0.0, 360.0), 30.0))
            out["flights"] += 1
        else:
            pose = window.view.navigator.pose
            window.view.navigator.show(Pose(
                pose.lat, pose.lon + 0.05, pose.distance * 0.97,
                pose.heading, pose.tilt))
        return STRESS_PERIOD
    out["gl"] = dict(window.view.gl_errors)
    out["seconds"] = round(time.monotonic() - state["stress_started"], 1)


# Строки, какие бесплатная модель кладёт в названия 4 октября 2026
# года: флаг Англии из символов-тегов, ⚔️ с селектором вида, иврит
# внутри русского слова, плюс сочетания, опасные для отрисовки текста.
ODD_NAMES = (
    "🏴\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f "
    "Английские владения к 1429 г. (после Азиנקур)",
    "⚔️ Ланкастерская фаза (1415–1453)",
    "🏰 Ключевые города и столицы",
    "Татары 🇷🇺🇹🇷 👨‍👩‍👧‍👦 мечеть ☪️",
    "Казань́̈̃ ‮обратно‬ ‌ ‍",
    "عربي 中文 日本語 한국어 ไทย",
    "Длинное " * 40,
)


def _odd_kml():
    import random
    rnd = random.Random(4)
    marks = []
    for n in range(40):
        name = ODD_NAMES[n % len(ODD_NAMES)] + " %d" % n
        lat = 57.0 + rnd.uniform(0.0, 3.0)
        lon = 54.0 + rnd.uniform(0.0, 5.0)
        if n % 5 == 4:
            geom = ("<LineString><coordinates>{:.4f},{:.4f},0 {:.4f},{:.4f},0"
                    "</coordinates></LineString>").format(
                        lon, lat, lon + 0.5, lat + 0.3)
        else:
            geom = ("<Point><coordinates>{:.4f},{:.4f},0</coordinates>"
                    "</Point>").format(lon, lat)
        marks.append(
            "<Placemark><name>{}</name><description>{}</description>"
            "<TimeStamp><when>{}</when></TimeStamp>{}</Placemark>".format(
                name, ODD_NAMES[(n + 3) % len(ODD_NAMES)],
                1550 + 10 * n, geom))
    return ('<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
            "<name>{}</name><Folder><name>{}</name>{}</Folder></Document>"
            "</kml>").format(ODD_NAMES[3], ODD_NAMES[0], "".join(marks))


@check(1000)
def odd_text():
    # Названия из странных символов всеми путями: метки по кнопке,
    # история разговора, ответ под строкой, надписи на глобусе.
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    out = result.setdefault("odd_text", {"rounds": 0})
    dialog = window._assistant()
    for name in ODD_NAMES:
        dialog._say("assistant", name)
        dialog._say("tool", name)
    window._places_made(_odd_kml())
    window.view.navigator.stop()
    window.view.navigator.show(Pose(58.5, 56.5, 400000.0, 0.0, 30.0))
    window.panel.set_answer(" ".join(ODD_NAMES), undo=True)
    state["odd_started"] = time.monotonic()


@check(1000)
def odd_text_wait():
    window = state["window"]
    out = result["odd_text"]
    # Кадры с надписями меток в течение 15 с, камера понемногу едет.
    from planetx.core.navigation import Pose
    t = time.monotonic() - state["odd_started"]
    if t < 15.0:
        pose = window.view.navigator.pose
        window.view.navigator.show(Pose(pose.lat, pose.lon + 0.05,
                                        pose.distance * 0.97, pose.heading,
                                        30.0))
        out["frames"] = out.get("frames", 0) + 1
        return 250
    window.view.grabFramebuffer().save(
        os.path.join(TEMP, "planetx_odd.png"))
    out["places"] = len(window.myplaces.places_in(window.made_folder)) \
        if window.made_folder else 0
    out["labels"] = len(getattr(window.view.labels, "items", []) or []) \
        if hasattr(window.view, "labels") else None
    window.undo_made_places()
    window.assistant_dialog.close()
    out["gl"] = dict(window.view.gl_errors)


@check(3000)
def topic_link():
    # Поиск по названию нашёл места - под строкой ссылка на метки
    # помощника по теме. Щелчок по ней - один запрос, метки в папку.
    from planetx.core import assistant as ai
    from planetx.core.geocode import Place
    from planetx.ui import assistant as ui_ai
    window = state["window"]
    window.set_body("earth")
    server, seen = _fake_model()
    state["fake_topic"] = (server, seen)
    state.setdefault("real_load_key", ui_ai.load_key)
    ui_ai.load_key = lambda provider: "test-key"
    dialog = window._assistant()
    _use_service(dialog, ai.OPENROUTER,
                 "http://127.0.0.1:%d" % server.server_port)
    dialog.settings.close()
    topic = "Первая мировая война"
    window.place.setText(topic)
    window._show_found((topic, None), [Place(
        "Немецкий ДОТ (Первая мировая война)", "", 55.2, 26.9, None)])
    out = result["topic_link"] = {"answer": window.panel.answer.text()}
    state["topic_before"] = len(window.myplaces.places)
    window.panel._answer_link("make")
    out["requests_sent"] = len(seen)


@check(1000)
def topic_link_check():
    from qgis.core import QgsSettings
    from planetx.core import assistant as ai
    from planetx.ui import assistant as ui_ai
    window = state["window"]
    server, seen = state["fake_topic"]
    out = result["topic_link"]
    out["requests"] = [p for p, _, _ in seen]
    out["no_tools"] = all("tools" not in b for _, b, _ in seen)
    out["places_added"] = len(window.myplaces.places) - state["topic_before"]
    out["answer_after"] = window.panel.answer.text()
    window.undo_made_places()
    if window.timebar.shown():
        window._time_bar_closed()
    settings = QgsSettings()
    for provider in ai.PROVIDERS:
        settings.remove(ui_ai.SETTINGS + provider + "/base")
    settings.remove(ui_ai.SETTINGS + "provider")
    ui_ai.load_key = state["real_load_key"]
    window.assistant_dialog.close()
    server.shutdown()
    out["gl"] = dict(window.view.gl_errors)


@check(3000)
def topic_empty():
    # Nominatim ничего не нашёл. Тема - сразу метки одним запросом без
    # инструментов, а не разговор: 4 октября 2026 года «Путешествия
    # Колумба» ушли в разговор, бесплатная модель описала документ
    # текстом, меток не было.
    from planetx.core import assistant as ai
    from planetx.ui import assistant as ui_ai
    window = state["window"]
    window.set_body("earth")
    server, seen = _fake_model()
    state["fake_empty"] = (server, seen)
    state.setdefault("real_load_key", ui_ai.load_key)
    ui_ai.load_key = lambda provider: "test-key"
    dialog = window._assistant()
    _use_service(dialog, ai.OPENROUTER,
                 "http://127.0.0.1:%d" % server.server_port)
    dialog.settings.close()
    topic = "Путешествия Колумба"
    window.place.setText(topic)
    state["empty_before"] = len(window.myplaces.places)
    window._show_found((topic, None), [])
    result["topic_empty"] = {"answer_start": window.panel.answer.text()}


@check(1000)
def topic_empty_check():
    from planetx.core import assistant as ai
    window = state["window"]
    server, seen = state["fake_empty"]
    out = result["topic_empty"]
    out["requests"] = len(seen)
    out["no_tools"] = all("tools" not in b for _, b, _ in seen)
    out["places_added"] = len(window.myplaces.places) - state["empty_before"]
    window.undo_made_places()
    if window.timebar.shown():
        window._time_bar_closed()
    # Вопрос без найденных мест - разговор с инструментами. Поддельный
    # сервер формата Responses отвечает вызовом add_kml.
    state["fake_question"] = len(seen)
    _use_service(window.assistant_dialog, ai.RESPONSES,
                 "http://127.0.0.1:%d" % server.server_port)
    window.assistant_dialog.settings.close()
    window._show_found(("где похоронен Колумб?", None), [])


@check(1000)
def topic_empty_done():
    from qgis.core import QgsSettings
    from planetx.core import assistant as ai
    from planetx.ui import assistant as ui_ai
    window = state["window"]
    dialog = window.assistant_dialog
    server, seen = state["fake_empty"]
    out = result["topic_empty"]
    asked = seen[state["fake_question"]:]
    out["question_requests"] = len(asked)
    out["question_tools"] = any("tools" in b for _, b, _ in asked)
    out["answer"] = window.panel.answer.text()
    out["accept_link"] = 'href="accept"' in out["answer"]
    out["dialog_popped"] = dialog.isVisible()
    before = len(window.myplaces.places)
    window.panel._answer_link("accept")
    out["accepted_places"] = len(window.myplaces.places) - before
    out["answer_after"] = window.panel.answer.text()
    window.undo_made_places()
    if window.timebar.shown():
        window._time_bar_closed()
    settings = QgsSettings()
    for provider in ai.PROVIDERS:
        settings.remove(ui_ai.SETTINGS + provider + "/base")
    settings.remove(ui_ai.SETTINGS + "provider")
    ui_ai.load_key = state["real_load_key"]
    window.assistant_dialog.close()
    server.shutdown()
    out["gl"] = dict(window.view.gl_errors)


@check(3000)
def props_vertices():
    # Окно «Свойства…» многоугольника: вершины тянутся мышью на глобусе,
    # «OK» записывает форму, «Отмена» - нет. Просьба автора от 4 октября
    # 2026 года.
    from planetx.core.features import Shape
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.view.navigator.stop()
    window.view.navigator.set_pose(Pose(58.1, 56.2, 60000.0, 0.0, 0.0))
    key = window.myplaces.add(Shape(
        "polygon", [(58.0, 56.0), (58.0, 56.4), (58.2, 56.2)],
        name="Проба вершин"))
    state["props_key"] = key
    result["props_vertices"] = {}


@check(1000)
def props_vertices_drag():
    window = state["window"]
    view = window.view
    key = state["props_key"]
    out = result["props_vertices"]
    window._open_place_properties(window.myplaces.find(key))
    tool = window.handles.tool
    out["tool"] = type(tool).__name__
    out["active"] = tool.active()
    vertices, front, middles, _ = tool.screen()
    out["handles"] = [len(vertices), len(middles)]
    x0, y0 = vertices[0]
    out["grabbed"] = view.vertex_tool.grab(float(x0), float(y0))
    view.vertex_tool.move(float(x0) + 80.0, float(y0) + 60.0)
    view.vertex_tool.drop()
    # Кружок середины первого отрезка - новая вершина. Середина
    # сдвинулась вместе с вершиной, место берётся заново.
    mx, my = tool.screen()[2][0]
    out["middle_grabbed"] = view.vertex_tool.grab(float(mx), float(my))
    view.vertex_tool.move(float(mx), float(my) + 50.0)
    view.vertex_tool.drop()
    dialog = window.prop_dialogs[key]
    out["dialog_points"] = len(dialog.points)
    out["preview_points"] = len(window.previews[key].points)
    state["props_moved"] = dialog.points[0]
    dialog.accept()


@check(1000)
def props_vertices_check():
    window = state["window"]
    key = state["props_key"]
    out = result["props_vertices"]
    place = window.myplaces.find(key)
    out["saved_points"] = len(place.shape.points)
    out["saved_moved"] = [round(v, 4) for v in place.shape.points[0]]
    out["moved"] = [round(v, 4) for v in state["props_moved"]]
    out["tool_after"] = type(window.handles.tool).__name__
    out["vertex_tool_after"] = type(window.view.vertex_tool).__name__
    # «Отмена» форму не меняет.
    window._open_place_properties(place)
    dialog = window.prop_dialogs[key]
    dialog.set_points([(57.0, 55.0), (57.0, 55.5), (57.3, 55.2)])
    dialog.reject()
    out["after_cancel"] = [round(v, 4) for v in
                           window.myplaces.find(key).shape.points[0]]
    window.myplaces.remove(key)
    out["gl"] = dict(window.view.gl_errors)


@check(1000)
def plates_on():
    # Строка «Границы плит»: слой в наложении, названия плит, окно
    # «Объекты» у Японского жёлоба.
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.view.navigator.stop()
    window.view.navigator.show(Pose(30.0, 150.0, 9000000.0, 0.0, 0.0))
    window.set_extra("plates", True)
    state["plates_started"] = time.monotonic()
    result["plates"] = {}


@check(1000)
def plates_wait():
    window = state["window"]
    if (window.view.load_missing
            and time.monotonic() - state["plates_started"] < 40.0):
        return 1000


@check(1000)
def plates_check():
    window = state["window"]
    out = result["plates"]
    overlay = window.overlay
    out["lines"] = len(window.plates_data.boundaries) \
        if window.plates_data else None
    out["layer_features"] = window.plate_layer.featureCount() \
        if window.plate_layer is not None else None
    out["in_overlay"] = overlay is not None \
        and window.plate_layer in overlay.layers
    out["marks"] = len(window.view.plate_marks)
    out["attribution"] = "Bird" in window.attribution.text()
    found = window._identify_plates(38.3, 143.9, 80000.0)
    out["identify"] = [(g.name if hasattr(g, "name") else str(g),
                        [(name, values) for name, values, _ in items])
                       for g, items in found]
    window.view.grabFramebuffer().save(
        os.path.join(TEMP, "planetx_plates.png"))
    window.set_extra("plates", False)
    out["off_in_overlay"] = window.overlay is not None \
        and window.plate_layer in window.overlay.layers
    out["off_marks"] = len(window.view.plate_marks)
    out["gl"] = dict(window.view.gl_errors)


@check(1000)
def compact_clear():
    # Помощник - кнопка у строки «Поиск» с меню, значка на панели нет.
    # «Очистить «Мои метки»» удаляет все метки и папки. Только
    # в проверочном профиле.
    from qgis.PyQt.QtWidgets import QPushButton, QToolButton
    from planetx.core.features import Shape
    window = state["window"]
    out = result.setdefault("compact", {})
    # Кнопки помощника у строки поиска нет, решение автора от 5 октября
    # 2026 года. Помощник - группа окна «Свойства вида».
    out["make_button"] = hasattr(window.panel, "make")
    out["placeholder"] = window.place.placeholderText()
    window._show_properties()
    out["properties_assistant"] = [
        b.text() for b in window.properties.findChildren(QPushButton)]
    window.properties.close()
    out["toolbar_assistant"] = [
        b.toolTip()[:40] for b in window.toolbar.findChildren(QToolButton)
        if "Помощник" in b.toolTip()]
    folder = window.myplaces.add_folder("Проба очистки")
    window.myplaces.add(Shape("point", [(55.0, 37.0)], name="Внутри"),
                        folder=folder)
    window.myplaces.add(Shape("point", [(56.0, 38.0)], name="В корне"))
    out["before"] = len(window.myplaces.places)
    out["cleared"] = window.clear_places(confirm=False)
    out["after_places"] = len(window.myplaces.places)
    out["after_folders"] = len(window.myplaces.folders)
    out["again"] = window.clear_places(confirm=False)
    out["gl"] = dict(window.view.gl_errors)


@check(1000)
def search_bar():
    # Строка «Поиск»: подсказки из «Моих меток» и прежних запросов,
    # клавиши списка подсказок, выбор подсказки, точное название своей
    # метки по Enter без запроса к Nominatim, история в профиле, звезда
    # в виде неба. Шаг без сети.
    from qgis.PyQt.QtCore import QEvent, Qt
    from qgis.PyQt.QtGui import QKeyEvent
    from qgis.PyQt.QtWidgets import QApplication
    from planetx.core.features import Shape
    from planetx.core.navigation import Pose
    from planetx.i18n import ui_language
    from planetx.qt_compat import enum, enum_int
    window = state["window"]
    panel = window.panel
    nav = window.view.navigator
    window.set_body("earth")
    state["search_sidebar"] = not panel.isHidden()
    window.set_sidebar(True)
    window.place.setText("")
    window.clear_search_history()
    nav.show(Pose(20.0, 0.0, 9000000.0, 0.0, 0.0))
    names = (("Проба поиска Вокзал", 58.02, 56.25),
             ("Проба поиска Университет", 58.0, 56.18),
             ("Вокзал пробы поиска", 55.75, 37.62))
    keys = [window.myplaces.add(Shape("point", [(lat, lon)], name=name))
            for name, lat, lon in names]
    state["search_keys"] = keys
    out = result["search_bar"] = {"keys": keys}
    # Запрос к Nominatim подменён списком до конца search_bar_check:
    # шаг в сеть не ходит и при ошибке разбора строки.
    out["nominatim"] = []
    window._search = out["nominatim"].append

    def press(widget, name):
        # Клавиша через фильтр событий панели, как с клавиатуры.
        QApplication.sendEvent(widget, QKeyEvent(
            enum(QEvent, "Type", "KeyPress"),
            enum_int(enum(Qt, "Key", name)),
            enum(Qt, "KeyboardModifier", "NoModifier")))

    def rows():
        return [panel.hints.item(i).text()
                for i in range(panel.hints.count())]

    def edit(text):
        # Правка пользователем: текст строки и сигнал textEdited.
        window.place.setText(text)
        window.place.textEdited.emit(text)

    def target():
        # Цель перелёта навигатора: широта и долгота.
        if nav.flight is None:
            return None
        end = nav.flight[1].end
        return [round(end.lat, 2), round(end.lon, 2)]

    # Поставщик: начало названия выше начала слова.
    out["source"] = [(s.kind, s.text)
                     for s in window.search_suggestions("вокзал")]
    # Текст, поставленный программой, подсказок не показывает.
    window.place.setText("вокзал")
    out["rows_set_text"] = rows()
    edit("вокзал")
    out["rows"] = rows()
    out["shown"] = not panel.hints.isHidden()
    # «Вниз» - в список, «вверх» с первой строки - в строку, Escape
    # прячет список.
    press(window.place, "Key_Down")
    out["down"] = [panel.hints.currentRow(),
                   panel.focusWidget() is panel.hints]
    press(panel.hints, "Key_Up")
    out["up"] = [panel.hints.currentRow(),
                 panel.focusWidget() is window.place]
    press(window.place, "Key_Escape")
    out["escape_rows"] = rows()
    # Выбор подсказки клавишами: перелёт к метке, она выделена в списке.
    edit("универ")
    press(window.place, "Key_Down")
    press(panel.hints, "Key_Return")
    out["chosen"] = {"target": target(), "text": window.place.text(),
                     "rows": rows(),
                     "selected": panel.list.selected_keys() == [keys[1]]}
    # Enter с точным названием своей метки в другом регистре: перелёт
    # к ней, запроса к Nominatim нет, запрос в истории.
    nav.stop()
    window.place.setText("")
    reply = window._search_reply
    name = names[0][0].upper()
    edit(name)
    window.place.returnPressed.emit()
    out["exact"] = {"target": target(), "rows": rows(),
                    "search_key": window._search_key,
                    "timer": window._search_timer.isActive(),
                    "same_reply": window._search_reply is reply,
                    "history": window.search_history()}
    # Прежний запрос с названием метки второй строкой не идёт.
    out["repeat"] = [(s.kind, s.text)
                     for s in window.search_suggestions("проба")]
    # Поиск помощника в историю не идёт.
    window.fly("10.0, 20.0", assistant=False)
    out["tool_history"] = window.search_history()
    # «Вниз» в пустой строке - прежние запросы, Enter по строке списка -
    # запрос заново.
    nav.stop()
    window.place.setText("")
    press(window.place, "Key_Down")
    out["empty_down"] = rows()
    press(panel.hints, "Key_Return")
    out["history_chosen"] = {"target": target(),
                             "text": window.place.text(),
                             "timer": window._search_timer.isActive()}
    # Историю стирает кнопка группы «Помощник» окна «Свойства вида».
    window._show_properties()
    window.properties.history_clear_requested.emit()
    window.properties.close()
    out["cleared"] = window.search_history()
    # Небо: подсказка звезды, выбор ведёт взгляд к ней.
    nav.stop()
    window.show_sky(85.0, 5.0, 70.0)
    star = "Сириус" if ui_language() == "ru" else "Sirius"
    edit(star[:4].lower())
    out["sky_rows"] = rows()
    found = [s for s in panel._hints
             if s.kind == "star" and s.text == star]
    out["sky_star"] = list(found[0][3:]) if found else None
    if found:
        panel._choose_hint(panel._hints.index(found[0]))
    out["sky_target"] = target()
    state["search_started"] = time.monotonic()


@check(500)
def search_bar_check():
    from planetx.i18n import ui_language
    window = state["window"]
    nav = window.view.navigator
    out = result.setdefault("search_bar", {})
    started = state.get("search_started")
    if nav.flight is not None and started is not None \
            and time.monotonic() - started < 20.0:
        return 500
    # Взгляд после перелёта: прямое восхождение, склонение, поле зрения.
    sky = window.view.sky_view
    out["sky_view"] = [round(math.degrees(sky.ra), 1),
                       round(math.degrees(sky.dec), 1),
                       round(sky.fov, 1)] if sky is not None else None
    # Enter с точным названием созвездия: перелёт взгляда без Nominatim.
    if sky is not None:
        window.place.setText("Орион" if ui_language() == "ru" else "Orion")
        window.place.returnPressed.emit()
        end = nav.flight[1].end if nav.flight is not None else None
        out["sky_exact"] = {
            "target": [round(end.lat, 2), round(end.lon, 2)]
            if end is not None else None,
            "search_key": window._search_key,
            "timer": window._search_timer.isActive()}
    # Уборка и после сбоя первого шага: подмена поиска, метки шага,
    # небо, строка, история, панель.
    if "_search" in window.__dict__:
        del window._search
    nav.stop()
    for key in state.get("search_keys", ()):
        if key:
            window.myplaces.remove(key)
    window.set_body("earth")
    window.place.setText("")
    window.clear_search_history()
    window.set_sidebar(state.get("search_sidebar", True))
    out["places_left"] = [p.name for p in window.myplaces.places
                          if "поиска" in p.name.lower()]
    out["history_left"] = window.search_history()
    out["gl"] = dict(window.view.gl_errors)


@check(2000)
def japan_open():
    # Демо «Японский жёлоб»: сектор из сцены, землетрясения, окно «Разрез».
    window = state["window"]
    window.set_body("earth")
    window.set_sea_depths(True)
    # Строка разреза включена заранее: сектор встанет под прежнюю точку,
    # сцена обязана заменить его своим.
    window.set_extra("cutaway", True)
    window.view.navigator.stop()
    state["japan_key"] = window.open_demo("japan")
    result["japan"] = {"started": time.monotonic()}


@check(1000)
def japan_wait():
    import numpy as np
    window = state["window"]
    out = result["japan"]
    dialog = window.section_dialog
    s = dialog.chart.section if dialog is not None else None
    ready = (window.crust is not None and window.quake_events
             and s is not None and np.isfinite(s.slab_top).any()
             and not window.view.load_missing)
    if not ready and time.monotonic() - out["started"] < 90.0:
        return 1000
    out["waited"] = round(time.monotonic() - out["started"], 1)


@check(1000)
def japan_check():
    import numpy as np
    from planetx.ui.scene import capture
    window = state["window"]
    out = result["japan"]
    out["wedge"] = [round(float(v), 2) for v in window.view.wedge] \
        if window.view.wedge is not None else None
    out["extras"] = {k: window.extras.get(k) for k in ("quakes", "cutaway")}
    out["slab_zones"] = sorted(window.slab_zones)
    out["events"] = len(window.quake_events)
    pose = window.view.navigator.pose
    out["pose"] = [round(pose.lat, 1), round(pose.lon, 1),
                   round(pose.distance / 1000.0)]
    dialog = window.section_dialog
    out["section_open"] = dialog is not None and dialog.isVisible()
    s = dialog.chart.section if dialog is not None else None
    if s is not None:
        slab = np.isfinite(s.slab_top)
        out["section_km"] = round(float(s.distance[-1]))
        out["slab_points"] = int(slab.sum())
        out["slab_depth_km"] = round(float(np.nanmax(s.slab_top)), 1) \
            if slab.any() else None
        out["crust"] = s.bounds is not None
        out["band_km"] = dialog.band.value()
        out["section_quakes"] = len(s.quakes)
        dialog.grab().save(os.path.join(TEMP, "planetx_japan_section.png"))
    out["places"] = len(window.myplaces.places_in(state["japan_key"])) \
        if state.get("japan_key") else 0
    # Сцена с глобуса хранит сектор.
    scene, _ = capture(window)
    out["scene_wedge"] = scene.view.get("wedge")
    window.view.grabFramebuffer().save(
        os.path.join(TEMP, "planetx_japan.png"))
    out["gl"] = dict(window.view.gl_errors)
    if dialog is not None:
        dialog.close()
    if state.get("japan_key"):
        window.myplaces.remove(state["japan_key"])
    window.set_extra("quakes", False)
    window.set_extra("cutaway", False)


@check(2000)
def identify_on():
    # Окно «Объекты»: метка «Моих меток», очаги землетрясений, место.
    from planetx.core.features import Shape
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    # Глубины - умолчание модуля, прерванный прогон мог их выключить.
    window.set_sea_depths(True)
    window.view.navigator.stop()
    window.view.navigator.show(Pose(38.5, 142.0, 3000000.0, 0.0, 0.0))
    state["identify_key"] = window.myplaces.add(
        Shape("point", [(38.5, 142.0)], name="Проба определения"))
    window.set_extra("quakes", True)
    window._want_crust()
    window.toolbar.identify.setChecked(True)
    result["identify"] = {"started": time.monotonic(),
                          "identifying": window.identifying}


@check(1000)
def identify_wait():
    window = state["window"]
    out = result["identify"]
    if (not window.quake_events or window.crust is None) \
            and time.monotonic() - out["started"] < 60.0:
        return 1000
    out["wait_s"] = round(time.monotonic() - out["started"], 1)


def _identified_tree(window):
    """Дерево окна «Объекты»: {группа: {объект: {поле: значение}}}."""
    tree = window.identified.tree
    out = {}
    for i in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(i)
        objects = {}
        for j in range(top.childCount()):
            item = top.child(j)
            objects[item.text(0)] = {item.child(k).text(0):
                                     item.child(k).text(1)
                                     for k in range(item.childCount())}
        out[top.text(0)] = objects
    return out


@check(1000)
def identify_check():
    import numpy as np
    from planetx.core import quakes as qk
    from planetx.core.ellipsoid import geodetic_to_ecef
    window = state["window"]
    view = window.view
    out = result["identify"]
    view.grabFramebuffer()
    xyz = geodetic_to_ecef(np.array([38.5]), np.array([142.0]),
                           np.zeros(1))
    pixels, _ = view.camera.project(xyz)
    window._clicked(*pixels[0])
    out["at_place"] = _identified_tree(window)
    # Щелчок по видимому очагу.
    layer = view.quakes
    eye = np.asarray(view.camera.eye)
    shown = qk.facing(eye, layer.epicenter, layer.lats, layer.lons)
    pixels, front = view.camera.project(layer.focus)
    inside = shown & front & (pixels[:, 0] > 0) & (pixels[:, 1] > 0) \
        & (pixels[:, 0] < view.width()) & (pixels[:, 1] < view.height())
    if np.any(inside):
        n = int(np.nonzero(inside)[0][0])
        window._clicked(*pixels[n])
        tree = _identified_tree(window)
        out["quake_groups"] = list(tree)
        out["quake_sample"] = next(iter(tree.get("Землетрясения", {})
                                        .items()), None)
    window.identified.grab().save(os.path.join(TEMP,
                                               "planetx_identify.png"))
    window.toolbar.identify.setChecked(False)
    window.identified.close()
    window.set_extra("quakes", False)
    window.myplaces.remove(state["identify_key"])
    out["gl"] = dict(view.gl_errors)


@check(15000)
def paleo_startup():
    # Палеогеография включена до первого кадра нового окна, как при
    # открытии окна с сохранённым флажком 2 октября 2026 года у автора.
    from planetx.core.navigation import Pose
    plugin = state["plugin"]
    old = plugin.window
    old.close()
    plugin.run()
    window = plugin.window
    state["window"] = window
    _paleo_local(window)
    window.set_extra("paleo", True)
    window.view.navigator.set_pose(Pose(5.0, 20.0, 20000000.0, 0.0, 0.0))
    result["paleo_startup"] = {"new_window": window is not old}


@check(1000)
def paleo_startup_check():
    window = state["window"]
    out = result["paleo_startup"]
    out["source"] = window.source.url
    out["ready"] = window._paleo_ready()
    out["land"] = _land_share(window.view)
    window.view.grabFramebuffer().save(
        os.path.join(TEMP, "planetx_paleo_startup.png"))
    window.set_extra("paleo", False)
    out["source_off"] = window.source.url


def _paleo_local(window):
    """Карты возрастов - с локальной копии planetx-terrain, если её
    указывает PLANETX_TERRAIN_DIR, иначе из хранилища."""
    folder = os.environ.get("PLANETX_TERRAIN_DIR")
    if folder:
        from qgis.PyQt.QtCore import QUrl
        window.paleo_url = QUrl.fromLocalFile(os.path.join(
            folder, "paleo", "paleomap")).toString() \
            + "/{age}/{z}/{x}/{y}.jpg"


@check(3000)
def paleo_on():
    # Палеогеография на возраст 0 над Африкой.
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    _paleo_local(window)
    window.view.navigator.stop()
    window.view.navigator.set_pose(Pose(5.0, 20.0, 20000000.0, 0.0, 0.0))
    window.set_extra("paleo", True)
    result["paleo"] = {"started": time.monotonic()}


@check(1000)
def paleo_wait():
    window = state["window"]
    out = result["paleo"]
    if not window._paleo_ready() \
            and time.monotonic() - out["started"] < 60.0:
        return 1000
    out["wait_s"] = round(time.monotonic() - out["started"], 1)


@check(10000)
def paleo_check():
    # Смена контекста OpenGL: тайлы карты возраста грузятся заново, как
    # при открытии окна. Снимок - в следующем шаге.
    window = state["window"]
    view = window.view
    out = result["paleo"]
    out["land_before"] = _land_share(view)
    old = view.context()
    splitter = window.splitter
    index = splitter.indexOf(view)
    view.setParent(None)
    splitter.insertWidget(index, view)
    view.show()
    view.grabFramebuffer()
    out["context_changed"] = view.context() is not old
    view.update()


@check(1000)
def paleo_after():
    window = state["window"]
    view = window.view
    out = result["paleo"]
    out["land_after_context"] = _land_share(view)
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_paleo.png"))
    window.set_extra("paleo", False)
    out["gl"] = dict(view.gl_errors)


# Палеогеография глазами пользователя: показ возрастов кнопкой, пока
# камера ходит, паузы цикла событий и время прихода каждого возраста.
# Жалоба автора от 5 октября 2026 года - «тормозит, дёргается».
PALEO_FROM = 100  # млн лет, начало показа


@check(1000)
def paleo_tour():
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    _paleo_local(window)
    window.view.navigator.stop()
    window.view.navigator.set_pose(Pose(20.0, 20.0, 20000000.0, 0.0, 0.0))
    relief_before = window.view.store.scale
    window.set_extra("paleo", True)
    window.paleo_bar.set_age(PALEO_FROM)
    window._paleo_age(PALEO_FROM)
    result["paleo_tour"] = {"started": time.monotonic(),
                            "relief_before": relief_before,
                            "relief_on": window.view.store.scale,
                            "seen": []}


@check(500)
def paleo_tour_run():
    # Ждёт возраст начала, потом показ кнопкой с качанием камеры.
    window = state["window"]
    out = result["paleo_tour"]
    waited = time.monotonic() - out["started"]
    if "playing" not in out:
        if not window._paleo_ready() and waited < 60.0:
            return 500
        out["first_s"] = round(waited, 1)
        image = window.view.grabFramebuffer()
        image.save(os.path.join(TEMP, "planetx_paleo_%d.png" % PALEO_FROM))
        state["paleo_first"] = _frame_array(image)
        out["playing"] = time.monotonic()
        _swing_start("paleo")
        window.paleo_bar.toggle()
        return 300
    seen = out["seen"]
    if not seen or seen[-1][0] != window.paleo_age:
        seen.append((window.paleo_age,
                     round(time.monotonic() - out["playing"], 2)))
    if window.paleo_bar.timer.isActive() \
            and time.monotonic() - out["playing"] < 90.0:
        return 300
    out["swing"] = _swing_report("paleo")
    out["play_s"] = round(time.monotonic() - out["playing"], 1)
    out["ages_seen"] = len(seen)
    out["label"] = window.paleo_bar.label.text()
    out["source"] = window.source.url
    image = window.view.grabFramebuffer()
    image.save(os.path.join(TEMP, "planetx_paleo_0.png"))
    # Кадр возраста PALEO_FROM отличается от кадра настоящего. На коде
    # до правки TileLoader._decoded в кадре стояла карта возраста 0.
    first = state.pop("paleo_first")
    out["frame_diff"] = round(float(abs(
        first.astype(int) - _frame_array(image).astype(int)).mean()), 1)
    return None


def _frame_array(image):
    import numpy as np
    bits = image.constBits()
    if hasattr(bits, "setsize"):
        bits.setsize(image.sizeInBytes())
    return np.frombuffer(bits, dtype=np.uint8).reshape(
        image.height(), image.width(), 4)[..., :3].copy()


@check(500)
def loader_stopped():
    # Ответ рабочего потока после abort не доходит до окна: снятие
    # связи не отменяет вызова, уже поставленного в очередь.
    import numpy as np
    from planetx.net.loader import TileLoader
    from planetx.core import basemap
    loader = TileLoader(basemap.osm())
    seen = []
    loader.loaded.connect(lambda *args: seen.append(args[0]))
    loader.abort()
    loader._decoded((3, 1, 1), np.zeros((256, 256, 4), np.uint8), None)
    result["loader_stopped"] = {"delivered_after_abort": len(seen)}
    loader.deleteLater()


@check(4000)
def paleo_close_view():
    # Берег вблизи на возрасте 0: Гибралтар с 600 км - подробность
    # карты 0.1°.
    from planetx.core.navigation import Pose
    window = state["window"]
    window.paleo_bar.set_age(0)
    window._paleo_age(0)
    window.view.navigator.stop()
    window.view.navigator.set_pose(Pose(36.0, -5.5, 600000.0, 0.0, 0.0))


@check(1000)
def paleo_close_check():
    window = state["window"]
    out = result["paleo_tour"]
    window.view.grabFramebuffer().save(
        os.path.join(TEMP, "planetx_paleo_close.png"))
    out["message"] = window.message[0]
    window.set_extra("paleo", False)
    out["relief_off"] = window.view.store.scale
    out["source_off"] = window.source.url
    out["gl"] = dict(window.view.gl_errors)


# Темы NASA GIBS: каждая тема даёт картинки тайлов, день по шкале
# времени, шкала в углу. Просьба автора от 5 октября 2026 года.
@check(1000)
def themes_open():
    from planetx.core import themes
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.set_extra("paleo", False)
    window.view.navigator.stop()
    window.view.navigator.set_pose(Pose(20.0, 30.0, 15000000.0, 0.0, 0.0))
    # PLANETX_THEMES - ключи тем через запятую, обход только их.
    only = [k for k in os.environ.get("PLANETX_THEMES", "").split(",") if k]
    result["themes"] = {"keys": [t.key for t in themes.THEMES
                                 if not only or t.key in only],
                        "index": 0, "each": {}, "started": None}


@check(500)
def themes_bar():
    # Одно время вида: тема без событий - шкала одним бегунком на
    # последнем дне ряда. Вопрос автора от 5 октября 2026 года - «слоёв
    # и легенд две, движок времени один».
    window = state["window"]
    out = result["themes"]
    if window.theme_key != "ozone":
        # Метки со временем - события, на время шага они скрыты.
        timed = {p.key: p.visible for p in window.myplaces.places
                 if p.time and p.visible}
        state["timed_places"] = timed
        window.myplaces.set_visible_many({k: False for k in timed})
        window.set_extra("quakes", False)
        window.timebar.close_bar()
        window._time_toggled(False)
        window.set_theme("")
        window.set_theme("ozone")
        out["bar_started"] = time.monotonic()
    if ("ozone" not in window._theme_domains or window.theme_day is None) \
            and time.monotonic() - out["bar_started"] < 30.0:
        return 500
    from planetx.core import themes
    bar = window.timebar
    lo, hi = bar.range()
    out["bar_shown"] = bar.shown()
    out["bar_point"] = bar.track.point and lo == hi
    out["bar_day"] = window.theme_day
    out["bar_last"] = themes.pick_day(window._theme_domains["ozone"])
    out["steps_shown"] = [b.isVisible() for b in bar.steps]
    # Шаг назад по ряду - на предыдущий день.
    bar.step(-1)
    window._apply_theme()
    out["day_after_step"] = window.theme_day
    out["legend_panel"] = window.legend_panel.isVisible()
    return None

@check(500)
def themes_cycle():
    # Темы по очереди: ряд дат, день, картинки в видеокарте, шкала.
    window = state["window"]
    out = result["themes"]
    keys = out["keys"]
    if out["index"] >= len(keys):
        return None
    key = keys[out["index"]]
    if window.theme_key != key:
        window.set_theme(key)
        out["started"] = time.monotonic()
        return 500
    waited = time.monotonic() - out["started"]
    layer = window.view.gibs["theme"]
    if (not layer.textures or layer.missing) and waited < 25.0:
        return 500
    out["each"][key] = {
        "day": window.theme_day, "textures": len(layer.textures),
        "missing": layer.missing, "wait_s": round(waited, 1),
        "legend": window.theme_legend.isVisible(),
        "scale": (window._theme_scales.get(key) or {}).get("kind")}
    window.view.grabFramebuffer().save(
        os.path.join(TEMP, "planetx_theme_%s.png" % key))
    out["index"] += 1
    return 500


@check(500)
def snow_winter():
    """Снежные темы на 15 января 2026 года над Западной Сибирью: доля
    кадра, раскрашенная темой, по снимку с темой и без неё."""
    import numpy as np
    from planetx.core.navigation import Pose
    window = state["window"]
    out = result.setdefault("snow_winter", {"index": 0})
    keys = ("snow", "snow_8day", "snow_mass")
    if out["index"] >= len(keys):
        window.set_theme("")
        return None
    key = keys[out["index"]]
    view = window.view
    if window.theme_key != key:
        view.navigator.stop()
        view.navigator.set_pose(Pose(60.0, 70.0, 4500000.0, 0.0, 0.0))
        window.set_theme(key)
        out["started"] = time.monotonic()
        return 500
    if key not in window._theme_domains and \
            time.monotonic() - out["started"] < 30.0:
        return 500
    moment = 1768435200.0  # 15 января 2026 года
    if not window.timebar.shown():
        window._time_toggled(True)
    window.timebar.set_range(moment, moment)
    window._apply_theme()
    layer = view.gibs["theme"]
    waited = time.monotonic() - out["started"]
    if (not layer.textures or layer.missing) and waited < 40.0:
        return 500
    image = view.grabFramebuffer()
    image.save(os.path.join(TEMP, "planetx_snow_%s.png" % key))
    window.set_theme("")
    view.grabFramebuffer()
    plain = view.grabFramebuffer()
    window.set_theme(key)

    def array(img):
        img = img.convertToFormat(img.Format.Format_RGBA8888)
        ptr = img.constBits()
        ptr.setsize(img.sizeInBytes())
        return np.frombuffer(ptr, np.uint8).reshape(
            img.height(), img.width(), 4)[..., :3].astype(int)

    diff = np.abs(array(image) - array(plain)).sum(axis=2) > 30
    out[key] = {"day": window.theme_day, "textures": len(layer.textures),
                "coloured_share": round(float(diff.mean()), 3),
                "legend": (window._theme_scales.get(key) or {}).get("kind")}
    out["index"] += 1
    return 500


@check(500)
def themes_time():
    # День по шкале времени: осадки на 15 июля 2020 года.
    import calendar
    import datetime
    window = state["window"]
    out = result["themes"]
    if window.theme_key != "rain":
        window.set_theme("rain")
        out["time_started"] = time.monotonic()
    if "rain" not in window._theme_domains \
            and time.monotonic() - out["time_started"] < 30.0:
        return 500
    day = float(calendar.timegm(datetime.date(2020, 7, 15).timetuple()))
    window.timebar.set_range(day + 3600.0, day + 3600.0)
    return None


@check(1500)
def themes_time_check():
    # Растительность и землетрясения вместе: шкала - промежуток для
    # очагов, тема берёт правый бегунок. Шкалы - одной панелью.
    window = state["window"]
    out = result["themes"]
    out["day_by_timebar"] = window.theme_day
    window.set_theme("ndvi")
    out["day_after_switch"] = window.theme_day
    window.set_extra("quakes", True)
    out["quakes_started"] = time.monotonic()
    geo = window.panel.geo
    for group in window.panel.theme_groups:
        group.setExpanded(True)
    geo.scrollToItem(window.panel.theme_items["rain"])
    geo.grab().save(os.path.join(TEMP, "planetx_theme_panel.png"))


@check(1000)
def themes_events():
    window = state["window"]
    out = result["themes"]
    if not window.view.quakes.events \
            and time.monotonic() - out["quakes_started"] < 30.0:
        return 1000
    bar = window.timebar
    lo, hi = bar.range()
    out["with_quakes_point"] = bar.track.point
    out["with_quakes_range"] = lo < hi
    out["panel_legends"] = [type(l).__name__ for l in
                            window.legend_panel.legends if not l.isHidden()]
    window.grab().save(os.path.join(TEMP, "planetx_theme_window.png"))
    window.set_extra("quakes", False)
    out["point_after_quakes"] = bar.track.point
    return None

@check(3000)
def themes_off():
    window = state["window"]
    out = result["themes"]
    out["day_after_close"] = window.theme_day
    window.set_body("mars")
    out["on_mars"] = {"legend": window.theme_legend.isVisible(),
                      "shown": window.view.gibs["theme"].shown}
    window.set_body("earth")
    out["back_on_earth"] = window.view.gibs["theme"].shown
    # Галка группы: снята - тема выключена, поставлена - прежняя тема
    # группы снова. Замечание автора от 5 октября 2026 года.
    from planetx.core import themes
    from planetx.ui.panel import CHECKED, THEME_GROUP_ROLE, UNCHECKED
    panel = window.panel
    current = themes.BY_KEY[window.theme_key].group
    water = next(g for g in panel.theme_groups
                 if g.data(0, THEME_GROUP_ROLE) == current)
    out["group_checked"] = water.checkState(0) == CHECKED
    water.setCheckState(0, UNCHECKED)
    out["group_off"] = (window.theme_key, window.view.gibs["theme"].shown)
    water.setCheckState(0, CHECKED)
    out["group_on"] = window.theme_key
    window.set_theme("")
    out["bar_after_off"] = window.timebar.track.point
    window.myplaces.set_visible_many(state.pop("timed_places", {}))
    out["group_after_off"] = water.checkState(0) == CHECKED
    out["off"] = {"legend": window.theme_legend.isVisible(),
                  "shown": window.view.gibs["theme"].shown,
                  "loader": "theme" in window.gibs_loaders}
    out["gl"] = dict(window.view.gl_errors)


# Наложения картинок: на поверхности, фото, на экране. Просьба автора
# от 5 октября 2026 года, «растры в KML, как в GE».
def _overlay_png(name, color, size=(400, 200)):
    from qgis.PyQt.QtGui import QColor, QImage
    image = QImage(size[0], size[1], QImage.Format.Format_ARGB32
                   if hasattr(QImage, "Format") else QImage.Format_ARGB32)
    image.fill(QColor(*color))
    path = os.path.join(TEMP, name)
    image.save(path, "PNG")
    return path


def _centre_pixel(view):
    image = view.grabFramebuffer()
    c = image.pixelColor(image.width() // 2, image.height() // 2)
    return [c.red(), c.green(), c.blue()]


@check(1000)
def overlays_open():
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.set_extra("paleo", False)
    window.set_theme("")
    window.view.navigator.stop()
    window.view.navigator.set_pose(Pose(20.0, 30.0, 400000.0, 0.0, 0.0))
    result["overlays"] = {"before": len(window.myplaces.overlays)}


@check(3000)
def overlays_add():
    window = state["window"]
    out = result["overlays"]
    out["centre_before"] = _centre_pixel(window.view)
    red = _overlay_png("planetx_ov_red.png", (230, 20, 20, 255))
    blue = _overlay_png("planetx_ov_blue.png", (20, 20, 230, 255),
                        (300, 200))
    green = _overlay_png("planetx_ov_green.png", (20, 200, 20, 255),
                         (120, 60))
    keys = [window.add_overlay("ground", path=red),
            window.add_overlay("photo", path=blue),
            window.add_overlay("screen", path=green)]
    state["overlay_keys"] = keys
    out["keys"] = keys
    out["dialogs"] = len(window.overlay_dialogs)
    for dialog in list(window.overlay_dialogs.values()):
        dialog.reject()


@check(1500)
def overlays_check():
    window = state["window"]
    out = result["overlays"]
    view = window.view
    out["count"] = len(window.myplaces.overlays) - out["before"]
    out["ground_layers"] = len(window._ground_rasters)
    out["ground_errors"] = window.ground_layers.errors
    out["in_overlay"] = bool(window.overlay) and any(
        layer in window.overlay.layers for layer in window._ground_rasters) \
        if hasattr(window.overlay, "layers") else None
    out["centre_after"] = _centre_pixel(view)
    out["photos_drawn"] = view.photos.drawn
    labels = window.screen_overlays.labels
    out["screen"] = [(l.x(), l.y(), l.width(), l.height(), l.isVisible())
                     for l in labels]
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_ov_ground.png"))
    window.grab().save(os.path.join(TEMP, "planetx_ov_window.png"))
    # Перелёт к фото: глаз в точке камеры фото.
    photo = window.myplaces.find(state["overlay_keys"][1])
    window._place_action("fly", photo.key)
    out["photo_camera"] = list(photo.overlay.camera[:3])


@check(6000)
def overlays_photo_check():
    from planetx.core.ellipsoid import ecef_to_geodetic
    window = state["window"]
    out = result["overlays"]
    view = window.view
    eye = [float(v) for v in ecef_to_geodetic(view.camera.eye)]
    out["eye_after_fly"] = [round(v, 4) for v in eye]
    out["photos_drawn_close"] = view.photos.drawn
    out["centre_photo"] = _centre_pixel(view)
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_ov_photo.png"))


@check(1500)
def overlays_edit():
    # Рамка картинки на поверхности: поворот полем, растяжение ручкой
    # угла. Два способа привязки, как у Google Earth.
    from planetx.core import overlays
    from planetx.core.navigation import Pose
    window = state["window"]
    out = result["overlays"]
    key = state["overlay_keys"][0]
    item = window.myplaces.find(key)
    out["new_box"] = item.overlay.box is not None
    window.view.navigator.stop()
    window.view.navigator.set_pose(Pose(20.0, 30.0, 400000.0, 0.0, 0.0))
    window._open_overlay_properties(item)
    dialog = window.overlay_dialogs[key]
    out["box_tool"] = type(window.handles.tool).__name__
    dialog.edges["rotation"].setValue(30.0)
    north, south, east, west, _ = dialog.overlay.box
    dialog.set_box(overlays.box_drag(dialog.overlay.box, "corner", 2,
                                     north + 0.3, east + 0.3))
    out["box_after"] = [round(v, 4) for v in dialog.overlay.box]
    # Ручки на глобусе: углы, середина и ромб, середины сторон.
    window.handles.sync()
    window.handles.grab()
    out["handles_shown"] = list(window.handles.shown[:2])
    out["ids_before"] = list(window._ground_ids)


@check(1500)
def overlays_edit_check():
    # Четыре угла, непрозрачность и картинка ссылкой на файл, «OK».
    window = state["window"]
    out = result["overlays"]
    key = state["overlay_keys"][0]
    out["ids_after_drag"] = list(window._ground_ids)
    dialog = window.overlay_dialogs[key]
    dialog._to_corners()
    out["quad_tool"] = type(window.handles.tool).__name__
    points = dialog.points
    lat, lon = points[2]
    points[2] = (lat + 0.2, lon + 0.2)
    dialog.set_points(points)
    dialog.opacity.setValue(50)
    dialog.store.setCurrentIndex(1)
    dialog.path.setText(os.path.join(TEMP, "planetx_ov_red.png"))
    dialog._path_edited()
    dialog.accept()
    item = window.myplaces.find(key)
    out["saved_box"] = item.overlay.box
    out["saved_corner"] = [round(v, 6) for v in item.overlay.corners[2]]
    out["saved_alpha"] = item.overlay.color[3]
    out["saved_link"] = (item.image, os.path.basename(item.href))
    out["tool_after"] = type(window.handles.tool).__name__


@check(1500)
def overlays_kmz():
    # KMZ - картинки внутрь архива, KML - папка картинок рядом, ссылка
    # на файл остаётся ссылкой. Чтение обратно.
    window = state["window"]
    out = result["overlays"]
    from planetx.core.kml import read_file
    out["ground_linked_layers"] = len(window._ground_rasters)
    path = os.path.join(TEMP, "planetx_overlays.kmz")
    window.export_kml(None, path=path)
    with open(path, "rb") as stream:
        back = read_file(stream.read())
    out["kmz_kinds"] = sorted(i.kind for i in back.overlays())
    out["kmz_images"] = all(i.image for i in back.overlays())
    plain = os.path.join(TEMP, "planetx_overlays.kml")
    window.export_kml(None, path=plain)
    files = os.path.join(TEMP, "planetx_overlays_files")
    out["kml_files"] = sorted(os.listdir(files)) \
        if os.path.isdir(files) else None
    with open(plain, encoding="utf-8") as stream:
        text = stream.read()
    out["kml_hrefs"] = text.count("planetx_overlays_files/")
    before = len(window.myplaces.overlays)
    key = window.import_kml(None, path=plain)
    out["imported"] = len(window.myplaces.overlays) - before
    linked = [o for o in window.myplaces.overlays[before:]
              if o.image is None]
    out["imported_links"] = sorted(os.path.basename(o.href)
                                   for o in linked)
    state["overlay_import"] = key


@check(1500)
def overlays_project():
    # Картинки на поверхности - слоями проекта QGIS в GeoTIFF. Вопрос
    # автора от 5 октября 2026 года - «растры положить в кугис обратно».
    from qgis.core import QgsProject
    window = state["window"]
    out = result["overlays"]
    key = state["overlay_keys"][0]
    item = window.myplaces.find(key)
    path = os.path.join(TEMP, "planetx_ov_ground.tif")
    layers = window.ground_to_project(key, target=path)
    out["project_layers"] = len(layers)
    if layers:
        layer = layers[0]
        box = layer.extent()
        lats = [c[0] for c in item.overlay.corners]
        lons = [c[1] for c in item.overlay.corners]
        out["project_crs"] = layer.crs().authid()
        out["project_extent"] = [round(box.xMinimum() - min(lons), 4),
                                 round(box.xMaximum() - max(lons), 4),
                                 round(box.yMinimum() - min(lats), 4),
                                 round(box.yMaximum() - max(lats), 4)]
        out["project_opacity"] = round(layer.renderer().opacity(), 2)
        out["project_group"] = QgsProject.instance().layerTreeRoot() \
            .findLayer(layer.id()).parent().name()
    folder = os.path.join(TEMP, "planetx_ov_project")
    os.makedirs(folder, exist_ok=True)
    more = window.ground_to_project(None, target=folder)
    # В профиле могут остаться картинки демо по ссылкам, тогда выгрузка
    # ждёт их загрузки.
    out["project_folder"] = len(more) or (
        "waits" if window._ground_export is not None else 0)
    window._ground_export = None
    for layer in layers + more:
        QgsProject.instance().removeMapLayer(layer.id())


@check(2000)
def aral_open():
    # Демо «Аральское море» - наложения по ссылкам, просьба автора
    # от 5 октября 2026 года «демки к растрам, можно по ссылкам».
    window = state["window"]
    action = next(a for a in window.toolbar.demo.menu().actions()
                  if a.text() in ("Аральское море", "Aral Sea"))
    action.trigger()
    key = window.panel.current_folder() if hasattr(
        window.panel, "current_folder") else None
    result["aral"] = {"folder": key}


@check(3000)
def aral_wait():
    window = state["window"]
    started = state.setdefault("aral_started", time.monotonic())
    if window._href_replies and time.monotonic() - started < 60.0:
        return 500


@check(2000)
def aral_check():
    window = state["window"]
    view = window.view
    out = result["aral"]
    items = [o for o in window.myplaces.overlays
             if o.href.startswith("https://")]
    out["overlays"] = sorted(o.kind for o in items)
    out["visible"] = sorted(o.kind for o in items if o.visible)
    out["loaded"] = len(window._link_images)
    out["ground_layers"] = len(window._ground_rasters)
    out["ground_errors"] = window.ground_layers.errors
    out["photos_drawn"] = view.photos.drawn
    out["screen"] = [(l.x(), l.y(), l.width(), l.height(), l.isVisible())
                     for l in window.screen_overlays.labels]
    out["view_size"] = [view.width(), view.height()]
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_aral.png"))
    window.grab().save(os.path.join(TEMP, "planetx_aral_window.png"))
    # Папка трёх снимков - в проект QGIS. Скрытые снимки ещё не
    # загружены, выгрузка ждёт их.
    frames = next(f for f in window.myplaces.folders
                  if f.name.startswith("Снимки MODIS"))
    target = os.path.join(TEMP, "planetx_aral_project")
    os.makedirs(target, exist_ok=True)
    state["aral_layers"] = window.ground_to_project(frames.key,
                                                    target=target)
    out["export_now"] = len(state["aral_layers"])
    out["export_waits"] = window._ground_export is not None


@check(3000)
def aral_project_wait():
    window = state["window"]
    started = state.setdefault("aral_export", time.monotonic())
    if window._ground_export is not None \
            and time.monotonic() - started < 60.0:
        return 500


@check(1000)
def aral_project_check():
    from qgis.core import QgsProject
    window = state["window"]
    out = result["aral"]
    group = QgsProject.instance().layerTreeRoot().findGroup(
        "PlanetX - картинки")
    layers = [n.layer() for n in group.findLayers()] if group else []
    out["project_layers"] = [(l.name(), l.isValid(), l.crs().authid())
                             for l in layers]
    if layers:
        box = layers[0].extent()
        out["project_extent"] = [round(box.xMinimum(), 3),
                                 round(box.yMinimum(), 3),
                                 round(box.xMaximum(), 3),
                                 round(box.yMaximum(), 3)]
    for layer in layers:
        QgsProject.instance().removeMapLayer(layer.id())


@check(2000)
def quarry_open():
    # Врезка своего рельефа, демо «Карьер», решение автора от 5 октября
    # 2026 года. Растр 1 м в UTM 40N, карьер 150 м глубиной.
    window = state["window"]
    action = next(a for a in window.toolbar.demo.menu().actions()
                  if a.text() in ("Карьер, свой рельеф",
                                  "Quarry, own terrain"))
    started = time.monotonic()
    action.trigger()
    result["quarry"] = {
        "prepare_s": round(time.monotonic() - started, 2),
        "insets": [(e.name, e.level, [round(v) for v in e.bounds])
                   for e in window.insets],
        "deep": [[round(v, 6) for v in box] for box in window.view.store.deep]}


def _quarry_wait(limit):
    window = state["window"]
    started = state.setdefault("quarry_wait", time.monotonic())
    busy = window.terrain_loader is not None and window.terrain_loader.busy()
    if (busy or window.view.load_missing) \
            and time.monotonic() - started < limit:
        return 500
    state.pop("quarry_wait", None)


@check(3000)
def quarry_wait():
    return _quarry_wait(40.0)


def _dem_at(lat, lon):
    from osgeo import gdal, osr
    path = os.path.join(ROOT, "planetx", "demo", "quarry", "quarry_dem.tif")
    ds = gdal.Open(path)
    ref = osr.SpatialReference()
    ref.ImportFromWkt(ds.GetProjection())
    wgs = osr.SpatialReference()
    wgs.ImportFromEPSG(4326)
    for r in (ref, wgs):
        r.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    x, y, _ = osr.CoordinateTransformation(wgs, ref).TransformPoint(lon,
                                                                    lat)
    x0, dx, _, y0, _, dy = ds.GetGeoTransform()
    col, row = int((x - x0) / dx), int((y - y0) / dy)
    value = ds.GetRasterBand(1).ReadAsArray(col, row, 1, 1)[0, 0]
    return float(value)


@check(2000)
def quarry_check():
    import numpy as np
    window = state["window"]
    out = result["quarry"]
    store = window.view.store
    lat, lon = 59.490, 56.970
    out["centre"] = [round(store.heights_at([lat], [lon],
                                            scaled=False)[0], 2),
                     round(_dem_at(lat, lon), 2)]
    # Профиль с запада на восток через дно, шаг около 2 м.
    k = 1.0 / (111320.0 * math.cos(math.radians(lat)))
    lons = lon + np.arange(-1000.0, 1000.0, 2.0) * k
    line = store.heights_at(np.full(lons.shape, lat), lons, scaled=False)
    steps = np.abs(np.diff(line))
    out["profile"] = [round(float(line.min()), 1), round(float(line.max()),
                                                         1)]
    # Уступ - подряд идущие точки с перепадом больше 3 м на 2 м пути.
    steep = steps > 3.0
    out["faces"] = int(np.sum(steep[1:] & ~steep[:-1]) + steep[0])
    # Край охвата на востоке: 1.2 км от центра, полоса 120 м.
    lons = lon + np.arange(1000.0, 1400.0, 2.0) * k
    edge = store.heights_at(np.full(lons.shape, lat), lons, scaled=False)
    out["edge_jump"] = round(float(np.abs(np.diff(edge)).max()), 2)
    out["levels"] = sorted({key[0] for key in store.tiles
                            if key[0] >= 14})
    from planetx.ui.scene import capture as capture_scene
    scene, _ = capture_scene(window, None, "quarry")
    out["scene_relief"] = [e["name"] for e in scene.layers
                           if e.get("relief")]
    window.view.grabFramebuffer().save(os.path.join(TEMP,
                                                    "planetx_quarry.png"))
    # Ближе к уступам: высоты уровней глубже 15.
    from planetx.core.navigation import Pose
    window.view.navigator.show(Pose(lat, lon - 450.0 * k, 350.0, 90.0,
                                    55.0))
    window.view.update()


@check(3000)
def quarry_close_wait():
    return _quarry_wait(40.0)


@check(2000)
def quarry_close_check():
    window = state["window"]
    out = result["quarry"]
    store = window.view.store
    out["levels_close"] = sorted({key[0] for key in store.tiles
                                  if key[0] >= 15})
    window.view.grabFramebuffer().save(os.path.join(
        TEMP, "planetx_quarry_close.png"))
    window.grab().save(os.path.join(TEMP, "planetx_quarry_window.png"))
    # Выключение врезки возвращает Terrarium.
    ids = list(window.panel.inset_ids)
    window.set_insets([])
    state["quarry_ids"] = ids


@check(3000)
def quarry_off_wait():
    return _quarry_wait(30.0)


@check(1500)
def quarry_off_check():
    window = state["window"]
    out = result["quarry"]
    store = window.view.store
    out["centre_off"] = round(store.heights_at([59.490], [56.970],
                                               scaled=False)[0], 2)
    out["deep_off"] = len(store.deep)
    window.set_insets(state["quarry_ids"])


@check(1500)
def globe_menu():
    # Меню правой кнопки на глобусе в середине вида. С 0.34.0 до
    # 5 октября 2026 года список self._ground закрывал метод окна
    # _ground, и меню падало с «'list' object is not callable».
    from qgis.PyQt.QtWidgets import QMenu
    from planetx.ui import globemenu
    window = state["window"]
    view = window.view
    before = set(window.findChildren(QMenu))
    globemenu.show(window, view.width() * view.devicePixelRatioF() / 2.0,
                   view.height() * view.devicePixelRatioF() / 2.0)
    menus = [m for m in window.findChildren(QMenu) if m not in before]
    result["globe_menu"] = [a.text() for m in menus for a in m.actions()]
    for menu in menus:
        menu.close()


@check(1500)
def middle_turn():
    # Прижатое колесо поворачивает и наклоняет вид. Замечание автора
    # от 5 октября 2026 года - на рабочем компьютере не работает.
    from qgis.PyQt.QtCore import Qt
    window = state["window"]
    view = window.view
    middle = _qt(Qt, "MouseButton", "MiddleButton")
    none = _qt(Qt, "MouseButton", "NoButton")
    before = view.navigator.pose
    x, y = view.width() / 2.0, view.height() / 2.0
    _send_mouse(view, "MouseButtonPress", x, y, middle, middle)
    for k in range(1, 11):
        _send_mouse(view, "MouseMove", x + 10.0 * k, y - 6.0 * k, none,
                    middle)
    _send_mouse(view, "MouseButtonRelease", x + 100.0, y - 60.0, middle,
                none)
    after = view.navigator.pose
    result["middle_turn"] = {
        "heading": [round(before.heading, 2), round(after.heading, 2)],
        "tilt": [round(before.tilt, 2), round(after.tilt, 2)],
        "turning_after": view.turning}
    # То же с открытыми окнами «Новая метка» и «Линейка»: щелчок ставит
    # точку, потом колесо.
    left = _qt(Qt, "MouseButton", "LeftButton")
    for name, opener in (("place", window._open_place),
                         ("ruler", window._open_ruler)):
        opener()
        QgsApplication.processEvents()
        _send_mouse(view, "MouseButtonPress", x - 50.0, y, left, left)
        _send_mouse(view, "MouseButtonRelease", x - 50.0, y, left, none)
        QgsApplication.processEvents()
        start = view.navigator.pose
        _send_mouse(view, "MouseButtonPress", x, y, middle, middle)
        for k in range(1, 11):
            _send_mouse(view, "MouseMove", x - 10.0 * k, y + 3.0 * k, none,
                        middle)
        _send_mouse(view, "MouseButtonRelease", x - 100.0, y + 30.0,
                    middle, none)
        end = view.navigator.pose
        result["middle_turn"][name] = [round(start.heading, 2),
                                       round(end.heading, 2)]
        dialog = window.place_dialog if name == "place" \
            else window.ruler_dialog
        if dialog is not None:
            dialog.close()


@check(300)
def lights_on():
    # Огни городов при солнце, просьба автора от 5 октября 2026 года.
    # Европа в 21:00 UTC - ночь, с 2500 км отвесно.
    from planetx.core import sun
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    window.set_extra("stars", False)
    for key in ("cutaway", "quakes", "clouds", "temperature"):
        window.set_extra(key, False)
    window.set_extra("sun", True)
    window.sun_timer.stop()
    t = SUN_TIME + 15.0 * 3600.0
    view.sun = sun.direction(t)
    view.navigator.stop()
    view.navigator.set_pose(Pose(52.0, 20.0, 2.5e6, 0.0, 0.0))
    result["lights"] = {"elevation": round(sun.elevation(52.0, 20.0, t), 1),
                        "loader": "lights" in window.gibs_loaders}
    view.update()


@check(3000)
def lights_wait():
    window = state["window"]
    started = state.setdefault("lights_wait", time.monotonic())
    loader = window.gibs_loaders.get("lights")
    if loader is not None and loader.busy() \
            and time.monotonic() - started < 40.0:
        return 500


@check(1500)
def lights_check():
    from planetx.net.loader import image_to_rgba
    window = state["window"]
    view = window.view
    out = result["lights"]
    out["textures"] = len(view.gibs["lights"].textures)
    out["attribution"] = "Black Marble" in window.attribution.text()
    image = view.grabFramebuffer()
    image.save(os.path.join(TEMP, "planetx_lights.png"))
    rgba = image_to_rgba(image).astype(float)
    bright = rgba[..., :3].mean(axis=2)
    out["bright_px"] = int((bright > 120).sum())
    out["mean"] = round(float(bright.mean()), 1)
    # Без огней тот же кадр: слой скрыт на время одного кадра.
    view.gibs["lights"].shown = False
    image = view.grabFramebuffer()
    view.gibs["lights"].shown = True
    plain = image_to_rgba(image).astype(float)[..., :3].mean(axis=2)
    out["bright_px_without"] = int((plain > 120).sum())
    out["gl"] = dict(view.gl_errors)
    window.set_body("mars")
    out["mars_loader"] = "lights" in window.gibs_loaders
    window.set_body("earth")
    out["earth_loader"] = "lights" in window.gibs_loaders
    window.set_extra("sun", False)
    out["off_loader"] = "lights" in window.gibs_loaders


@check(300)
def fires_on():
    # Пожары NASA FIRMS, решение автора от 5 октября 2026 года. Южная
    # Америка с 4000 км - в октябре там сезон пожаров.
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    for key in ("cutaway", "quakes", "sun", "clouds", "temperature"):
        window.set_extra(key, False)
    view.navigator.stop()
    view.navigator.set_pose(Pose(-12.0, -55.0, 4.0e6, 0.0, 0.0))
    started = time.monotonic()
    window.set_extra("fires", True)
    state["fires_started"] = started
    result["fires"] = {"reply": window._fire_reply is not None}


@check(2000)
def fires_wait():
    window = state["window"]
    if window._fire_reply is not None \
            and time.monotonic() - state["fires_started"] < 90.0:
        return 500
    result["fires"]["load_s"] = round(time.monotonic()
                                      - state["fires_started"], 1)


@check(1500)
def fires_check():
    import numpy as np
    window = state["window"]
    view = window.view
    out = result["fires"]
    data = window.fire_data
    out["count"] = len(data) if data is not None else None
    out["message"] = window.message[0]
    out["drawn"] = view.fires.drawn
    out["legend"] = [not window.fire_legend.isHidden(),
                     window.legend_panel.isVisible()]
    out["attribution"] = "FIRMS" in window.attribution.text()
    out["timebar_extent"] = window.timebar.extent is not None \
        if hasattr(window.timebar, "extent") else None
    out["time_available"] = window.toolbar.time.isEnabled() \
        if hasattr(window.toolbar, "time") else None
    started = time.perf_counter()
    for _ in range(5):
        image = view.grabFramebuffer()
    out["frame_ms"] = round((time.perf_counter() - started) / 5 * 1000, 1)
    image.save(os.path.join(TEMP, "planetx_fires.png"))
    window.grab().save(os.path.join(TEMP, "planetx_fires_window.png"))
    # Опрос: щелчок по самому мощному видимому очагу.
    layer = view.fires
    pixels, front = view.camera.project(layer.focus)
    w, h = view.camera.width, view.camera.height
    inside = front & (pixels[:, 0] > 0) & (pixels[:, 0] < w) \
        & (pixels[:, 1] > 0) & (pixels[:, 1] < h)
    if np.any(inside):
        n = int(np.nonzero(inside)[0][np.argmax(data.frp[inside])])
        found = window._identify_fires(float(pixels[n, 0]),
                                       float(pixels[n, 1]))
        out["identify"] = [(name, dict(values))
                           for name, values, _ in found[0][1][:1]] \
            if found else []
    # Строка «Пожары» - первая в группе «Планета огня», переключатель
    # общего выбора тем: тема снимает пожары, пожары снимают тему.
    panel = window.panel
    row = panel.extra_items["fires"]
    group = row.parent()
    out["row_parent"] = group.text(0) if group is not None else None
    from qgis.PyQt.QtCore import Qt
    checked = _qt(Qt, "CheckState", "Checked")
    smoke = panel.theme_items["smoke"]
    smoke.setCheckState(0, checked)
    QgsApplication.processEvents()
    after_theme = [window.theme_key, bool(window.extras.get("fires")),
                   row.checkState(0) == checked]
    row.setCheckState(0, checked)
    QgsApplication.processEvents()
    after_fires = [window.theme_key, bool(window.extras.get("fires")),
                   smoke.checkState(0) == checked,
                   group.checkState(0) == checked]
    out["radio"] = [after_theme, after_fires]
    out["gl"] = dict(view.gl_errors)
    window.set_extra("fires", False)
    out["off"] = [view.fires.fires is None, window.fire_legend.isVisible()]


@check(1500)
def sources_open():
    # Окно «Источники данных», состав утверждён автором 5 октября 2026
    # года. Открывается кнопкой окна «Свойства вида».
    window = state["window"]
    window._show_properties()
    window.properties.sources_requested.emit()
    dialog = window.sources_dialog
    rows = []
    for n in range(dialog.tree.topLevelItemCount()):
        group = dialog.tree.topLevelItem(n)
        rows += [group.child(k).text(0) for k in range(group.childCount())]
    result["sources"] = {"visible": dialog.isVisible(), "rows": rows}
    dialog.probe()
    state["sources_started"] = time.monotonic()


@check(2000)
def sources_wait():
    window = state["window"]
    if window.sources_dialog.replies \
            and time.monotonic() - state["sources_started"] < 60.0:
        return 500


@check(1500)
def sources_check():
    window = state["window"]
    dialog = window.sources_dialog
    out = result["sources"]
    checks = {}
    for n in range(dialog.tree.topLevelItemCount()):
        group = dialog.tree.topLevelItem(n)
        for k in range(group.childCount()):
            item = group.child(k)
            checks[item.text(0)] = item.text(3)
    out["checks"] = checks
    # Свой рельеф: тот же Terrarium по своему адресу, с подписью.
    own = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/" \
        "{z}/{x}/{y}.png?own=1"
    dialog.terrain_url.setText(own)
    dialog.terrain_credit.setText("Test terrain")
    dialog._apply("terrain")
    loader = window.terrain_loader
    out["terrain_url"] = loader.source.url if loader else None
    out["terrain_credit"] = "Test terrain" in window.attribution.text()
    dialog._reset("terrain")
    out["terrain_reset"] = window.terrain_loader.source.url
    # Своя векторная основа: тот же TileJSON с параметром.
    dialog.vector_url.setText("https://tiles.openfreemap.org/planet?own=1")
    dialog.vector_credit.setText("Test base")
    dialog._apply("vector")
    state["vector_started"] = time.monotonic()


@check(2000)
def sources_vector_wait():
    window = state["window"]
    if window._tilejson is not None \
            and time.monotonic() - state["vector_started"] < 30.0:
        return 500


@check(1500)
def sources_vector_check():
    from qgis.PyQt.QtWidgets import QMessageBox
    from planetx.ui.tilesource import save_connection
    window = state["window"]
    dialog = window.sources_dialog
    out = result["sources"]
    out["vector_layer"] = window.ofm_layer is not None
    out["vector_credit"] = "Test base" in window.attribution.text()
    dialog._reset("vector")
    # Подложка: подключение XYZ появляется в списке и удаляется окном.
    save_connection("PlanetX test XYZ", "https://tile.example/{z}/{x}/{y}"
                    ".png", 12, "Test XYZ")
    window.sources_changed("basemaps")
    dialog.rebuild()
    names = [s.name for s in window.sources]
    out["xyz_added"] = "PlanetX test XYZ" in names
    base = dialog.tree.topLevelItem(0)
    for k in range(base.childCount()):
        if base.child(k).text(0) == "PlanetX test XYZ":
            dialog.tree.setCurrentItem(base.child(k))
    out["edit_enabled"] = dialog.edit.isEnabled()
    yes = getattr(QMessageBox.StandardButton, "Yes", None) \
        or QMessageBox.Yes
    question = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *a, **k: yes)
    try:
        dialog._remove()
    finally:
        QMessageBox.question = question
    out["xyz_removed"] = "PlanetX test XYZ" not in [
        s.name for s in window.sources]
    out["gl"] = dict(window.view.gl_errors)
    dialog.close()


@check(1500)
def overlays_clean():
    window = state["window"]
    out = result["overlays"]
    images_before = window.myplaces.image_layer.featureCount()
    keys = [k for k in state["overlay_keys"] if k]
    if state.get("overlay_import"):
        keys.append(state["overlay_import"])
    window.myplaces.remove_many(keys)
    out["left"] = len(window.myplaces.overlays) - out["before"]
    out["images_removed"] = images_before \
        - window.myplaces.image_layer.featureCount()
    out["ground_after"] = len(window._ground_rasters)
    out["screen_after"] = len(window.screen_overlays.labels)
    out["gl"] = dict(window.view.gl_errors)


def _image_server():
    """Сервер картинки на 127.0.0.1 в потоке: отдаёт байты из словаря
    и считает запросы."""
    import http.server
    import threading
    served = {"data": b"", "count": 0}

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            return None

        def do_GET(self):
            served["count"] += 1
            body = served["data"]
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            # Ответ годен час: обновление обязано идти мимо кэша QGIS.
            self.send_header("Cache-Control", "max-age=3600")
            self.end_headers()
            self.wfile.write(body)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, served


@check(3000)
def overlay_refresh():
    """Картинка на поверхности по адресу с обновлением через 10 с."""
    from planetx.core.kml import read_kml
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    # Наложения прерванных прогонов этого шага.
    old = [o.key for o in window.myplaces.overlays if o.name == "Свежая"]
    if old:
        window.myplaces.remove_many(old)
    red = _overlay_png("planetx_rf_red.png", (230, 20, 20, 255))
    with open(red, "rb") as fh:
        red_bytes = fh.read()
    server, served = _image_server()
    served["data"] = red_bytes
    state["image_server"] = (server, served)
    url = "http://127.0.0.1:{}/img.png".format(server.server_address[1])
    state["refresh_url"] = url
    text = ('<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
            '<name>Обновление</name><GroundOverlay><name>Свежая</name>'
            '<Icon><href>{}</href><refreshMode>onInterval</refreshMode>'
            '<refreshInterval>10</refreshInterval></Icon><LatLonBox>'
            '<north>21</north><south>19</south><east>31</east>'
            '<west>29</west></LatLonBox></GroundOverlay></Document></kml>'
            ).format(url)
    state["refresh_key"] = window.myplaces.import_tree(
        read_kml(text.encode("utf-8")))
    window.view.navigator.stop()
    window.view.navigator.set_pose(Pose(20.0, 30.0, 400000.0, 0.0, 0.0))
    window._refresh_overlays()
    result["overlay_refresh"] = {"url_requests_start": served["count"]}


def _refresh_state(window):
    from planetx.ui.overlays import folder
    url = state["refresh_url"]
    sources = [layer.source() for layer in window._ground_rasters]
    fid = [o.fid for o in window.myplaces.overlays
           if o.href == url][0]
    mine = [os.path.basename(s) for s in sources
            if os.path.basename(s).startswith("{}_".format(fid))]
    files = [n for n in os.listdir(folder())
             if n.startswith("{}_".format(fid))]
    return {"gen": window._link_gen.get(url),
            "requests": state["image_server"][1]["count"],
            "source": mine,
            "files": len(files),
            "refresh": [o.overlay.refresh for o in window.myplaces.overlays
                        if o.href == url]}


@check(500)
def overlay_refresh_first():
    window = state["window"]
    out = result["overlay_refresh"]
    out["first"] = _refresh_state(window)
    # Сервер меняет картинку, глобус берёт её через промежуток.
    blue = _overlay_png("planetx_rf_blue.png", (20, 20, 230, 255))
    with open(blue, "rb") as fh:
        state["image_server"][1]["data"] = fh.read()


@check(12000)
def overlay_refresh_wait():
    # Пауза дольше промежутка 10 с.
    return None


@check(1500)
def overlay_refresh_second():
    window = state["window"]
    out = result["overlay_refresh"]
    out["second"] = _refresh_state(window)


@check(12000)
def overlay_refresh_same():
    # Та же картинка ещё раз: номер не растёт, прежний файл удалён.
    return None


SAT_SAMPLES = os.environ.get(
    "PLANETX_SAT_SAMPLES",
    os.path.join(TEMP, "claude", "C--Dev-planetx",
                 "7087209f-26e4-42e4-91cf-1a0075997747", "scratchpad",
                 "sgp4ref"))


def _file_server(files):
    """Сервер файлов на 127.0.0.1 в потоке: путь /<имя> - байты files,
    счёт запросов по имени."""
    import http.server
    import threading
    counts = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            return None

        def do_GET(self):
            name = self.path.strip("/").split("?")[0]
            counts[name] = counts.get(name, 0) + 1
            body = files.get(name)
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/csv")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, counts


@check(1000)
def sat_on():
    """Спутники трёх групп с сервера на 127.0.0.1 вместо CelesTrak."""
    from qgis.core import QgsSettings
    from planetx.core import satellites as core
    from planetx.core.navigation import Pose
    from planetx.ui import satellites as ui_sat
    window = state["window"]
    window.set_body("earth")
    files = {}
    for group, name in (("stations", "stations"), ("gnss", "gps-ops"),
                        ("geo", "geo")):
        with open(os.path.join(SAT_SAMPLES, name + ".csv"), "rb") as fh:
            files[group + ".csv"] = fh.read()
    server, counts = _file_server(files)
    state["sat_server"] = (server, counts, core.FEED)
    core.FEED = "http://127.0.0.1:{}/{{group}}.csv".format(
        server.server_address[1])
    for group in ("stations", "gnss", "geo", "science"):
        path = ui_sat.group_file(group)
        if os.path.exists(path):
            os.remove(path)
        QgsSettings().remove(ui_sat.FAILED_KEY + group)
    manager = window.satellite_manager
    window.set_extra("satellites", False)
    manager.set_groups({"stations", "gnss", "geo"})
    window.panel.set_satellite_groups(manager.groups)
    window.view.navigator.stop()
    window.view.navigator.set_pose(Pose(0.0, 60.0, 90000e3, 0.0, 0.0))
    window.set_extra("satellites", True)
    result["satellites"] = {"pending_at_start": len(manager.replies)}


@check(4000)
def sat_wait():
    return None


@check(1500)
def sat_check():
    import time as _time
    from planetx.ui import satellites as ui_sat
    window = state["window"]
    manager = window.satellite_manager
    view = window.view
    server, counts, feed = state["sat_server"]
    out = result["satellites"]
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_sat.png"))
    out.update({
        "count": manager.count(),
        "groups": sorted(manager.swarm.groups),
        "requests": dict(counts),
        "files": sorted(g for g in ("stations", "gnss", "geo")
                        if os.path.exists(ui_sat.group_file(g))),
        "drawn": view.satellites.drawn,
        "tick": manager.tick.isActive(),
        "credit": "CelesTrak" in window.attribution.text(),
        "pending": view.data_pending})
    seen = view.satellites.seen
    if seen.size:
        index = int(seen[0])
        pixels, _ = view.camera.project(view.satellites.points[[index]])
        px, py = (float(v) for v in pixels[0])
        found = window._identify_satellites(px, py)
        out["picked"] = [found[0][1][0][0]] + [
            "{}: {}".format(k, v) for k, v in found[0][1][0][1]] \
            if found else None
    # Повторное включение берёт файлы, запросов не прибавляется.
    window.set_extra("satellites", False)
    window.set_extra("satellites", True)
    while not manager.swarm.init_some():
        pass
    out["requests_after_toggle"] = dict(counts)
    out["count_after_toggle"] = manager.count()
    # Шкала на 2020 год: элементы старше 30 суток, точек нет, кадр
    # не стоит секунды на интегрирование резонансов.
    old = 1594771200.0  # 15 июля 2020 года
    window._time_range = (old - 3600.0, old)
    manager.time_changed()
    start = _time.perf_counter()
    view.grabFramebuffer()
    out["old_frame_ms"] = round((_time.perf_counter() - start) * 1000, 1)
    out["old_drawn"] = view.satellites.drawn
    out["old_tick"] = manager.tick.isActive()
    window._time_range = None
    manager.time_changed()
    # После отказа группа не просится два часа.
    from qgis.core import QgsSettings
    QgsSettings().setValue(ui_sat.FAILED_KEY + "science", _time.time())
    manager.set_groups({"stations", "gnss", "geo", "science"})
    out["refused_error"] = manager.errors.get("science")
    out["science_requests"] = counts.get("science.csv", 0)
    manager.set_groups({"stations", "gnss", "geo"})
    QgsSettings().remove(ui_sat.FAILED_KEY + "science")
    out["gl"] = dict(view.gl_errors)


@check(1000)
def sat_path():
    """Выбор МКС пунктом меню: виток с высотами и след на земле, потом
    камера следом."""
    from qgis.PyQt.QtWidgets import QMenu
    from planetx.core.navigation import Pose
    from planetx.ui import globemenu
    window = state["window"]
    view = window.view
    manager = window.satellite_manager
    manager.select(None)
    index = manager.swarm.index_of(25544)
    point, _ = manager.swarm.motion(index, manager.moment())
    lat, lon, _ = (float(v) for v in ecef_to_geodetic_point(point))
    # МКС над точкой взгляда с 20 000 км.
    view.navigator.stop()
    view.navigator.set_pose(Pose(lat, lon, 20000e3, 0.0, 0.0))
    view.grabFramebuffer()
    pixels, _ = view.camera.project(point.reshape(1, 3))
    px, py = (float(v) for v in pixels[0])
    out = result.setdefault("sat_path", {})
    out["under"] = manager.under(px, py)
    before = set(window.findChildren(QMenu))
    globemenu.show(window, px, py)
    menus = [m for m in window.findChildren(QMenu) if m not in before]
    actions = [a for m in menus for a in m.actions()]
    out["menu"] = [a.text() for a in actions if a.text()]
    for action in actions:
        if action.text() == "Орбита и след" or \
                action.text() == "Orbit and ground track":
            action.trigger()
    for menu in menus:
        menu.close()
    shapes = manager.shapes()
    out["selected"] = manager.selected
    out["shapes"] = len(shapes)
    if shapes:
        alts = shapes[0].alts
        out["orbit_km"] = [round(min(alts) / 1000.0),
                           round(max(alts) / 1000.0)]
        out["orbit_points"] = len(shapes[0].points)
        out["track_lat"] = round(max(abs(p[0]) for p in shapes[1].points), 2)
    out["in_view"] = sum(1 for s in view.features.shapes if s.alts is not None
                         and len(s.alts) == len(shapes[0].points)) \
        if shapes else 0
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_sat_path.png"))
    # Камера следом: шаг часов на минуту - точка взгляда под МКС.
    manager.clock = manager.moment()
    manager.set_follow(True)
    out["follow_tick"] = manager.tick.interval()
    manager.clock += 60.0
    manager._tick()
    point, _ = manager.swarm.motion(index, manager.moment())
    lat, lon, _ = (float(v) for v in ecef_to_geodetic_point(point))
    pose = view.navigator.pose
    out["follow_offset"] = [round(pose.lat - lat, 4),
                            round((pose.lon - lon + 180.0) % 360.0 - 180.0, 4)]
    out["follow_distance"] = round(pose.distance / 1000.0)
    out["follow_heading"] = round(pose.heading, 1)
    out["gl"] = dict(view.gl_errors)


@check(4500)
def sat_follow_stress():
    """Камера следом за спутником при часах ×3600 и одновременно мышь:
    колесо, перетаскивание, взгляд с Ctrl, поворот средней кнопкой.
    Каждые 30 мс поза проверяется на NaN. Повтор ошибки автора от
    6 октября 2026 года - NaN в nearest_terrain из paintGL."""
    import math as _math
    from qgis.PyQt.QtCore import Qt, QTimer
    window = state["window"]
    view = window.view
    manager = window.satellite_manager
    manager.clock = None
    manager.select(25544)
    manager.set_follow(True)
    window._time_toggled(True)
    bar = window.timebar
    bar.speed.setCurrentIndex(bar.speed.findData(3600.0))
    if not bar.timer.isActive():
        bar.toggle()
    left = _qt(Qt, "MouseButton", "LeftButton")
    middle = _qt(Qt, "MouseButton", "MiddleButton")
    none = _qt(Qt, "MouseButton", "NoButton")
    ctrl = _qt(Qt, "KeyboardModifier", "ControlModifier")
    w, h = view.width(), view.height()
    geo = [i for i, g in enumerate(manager.swarm.group_of) if g == "geo"]
    out = result.setdefault("sat_follow", {"ticks": 0, "bad": [],
                                           "errors": []})
    seq = {"k": 0}

    def finite(pose):
        return all(_math.isfinite(x) for x in (
            pose.lat, pose.lon, pose.distance, pose.heading, pose.tilt,
            pose.h))

    def tick():
        k = seq["k"]
        seq["k"] += 1
        out["ticks"] = k
        x = w * (0.2 + 0.6 * ((k * 37) % 100) / 100.0)
        y = h * (0.2 + 0.6 * ((k * 53) % 100) / 100.0)
        try:
            mode = k % 6
            if mode == 0:
                view.navigator.wheel(x * view.devicePixelRatioF(),
                                     y * view.devicePixelRatioF(),
                                     0.5 if k % 12 else 2.0,
                                     time.monotonic())
            elif mode == 1:
                _send_mouse(view, "MouseButtonPress", x, y, left, left)
                _send_mouse(view, "MouseMove", x + 40, y + 25, none, left)
                _send_mouse(view, "MouseButtonRelease", x + 40, y + 25,
                            left, none)
            elif mode == 2:
                _send_mouse(view, "MouseButtonPress", x, y, left, left,
                            ctrl)
                _send_mouse(view, "MouseMove", x + 30, y - 20, none, left,
                            ctrl)
                _send_mouse(view, "MouseButtonRelease", x + 30, y - 20,
                            left, none, ctrl)
            elif mode == 3:
                _send_mouse(view, "MouseButtonPress", x, y, middle, middle)
                _send_mouse(view, "MouseMove", x + 20, y - 60, none,
                            middle)
                _send_mouse(view, "MouseButtonRelease", x + 20, y - 60,
                            middle, none)
            if k == 60 and geo:
                # Геостационарный: скорость относительно Земли около нуля.
                manager.select(int(manager.swarm.numbers[geo[0]]))
                manager.set_follow(True)
            view.repaint()
        except (ValueError, ZeroDivisionError, RuntimeError) as error:
            out["errors"].append("{}: {}".format(k, error))
        pose = view.navigator.pose
        if not finite(pose) and len(out["bad"]) < 5:
            out["bad"].append([k, pose.lat, pose.lon, pose.distance,
                               pose.heading, pose.tilt, pose.h])
        if k >= 120:
            state.pop("follow_timer").stop()

    timer = QTimer()
    timer.setInterval(30)
    timer.timeout.connect(tick)
    state["follow_timer"] = timer
    timer.start()


@check(500)
def sat_follow_check():
    window = state["window"]
    out = result["sat_follow"]
    timer = state.pop("follow_timer", None)
    if timer is not None:
        timer.stop()
    window.timebar.stop()
    window.satellite_manager.set_follow(False)
    pose = window.view.navigator.pose
    out["pose"] = [pose.lat, pose.lon, pose.distance, pose.heading,
                   pose.tilt]
    out["gl"] = dict(window.view.gl_errors)


@check(1500)
def pole_view():
    """Камера отвесно над Северным полюсом с 20 000 км. До 6 октября
    2026 года высота глаза выходила NaN и кадр падал в nearest_terrain."""
    import math as _math
    import traceback as _tb
    from planetx.core.navigation import Pose, nearest_terrain
    window = state["window"]
    window.set_body("earth")
    view = window.view
    out = result.setdefault("pole_view", {})
    for km in (1500, 3000, 5000, 20000):
        view.navigator.stop()
        view.navigator.set_pose(Pose(90.0, 0.0, km * 1e3, 0.0, 0.0))
        view.makeCurrent()
        try:
            view._render(view.devicePixelRatioF())
            error = None
        except (ValueError, ZeroDivisionError, FloatingPointError) as exc:
            error = "".join(_tb.format_exception_only(exc)).strip()
        finally:
            view.doneCurrent()
        near = nearest_terrain(view.camera.eye, view.terrain_at)
        out[str(km)] = {"render_error": error,
                        "nearest_km": round(near / 1000.0)
                        if _math.isfinite(near) else str(near)}
    out["gl"] = dict(view.gl_errors)


ROUTE_A = (58.0105, 56.2294)  # Эспланада, Пермь
ROUTE_B = (58.0186, 56.2930)  # Мотовилиха


@check(500)
def route_car():
    """Маршрут на машине по тайлам векторной основы из меню глобуса."""
    import time as _time
    window = state["window"]
    window.set_body("earth")
    manager = window.route_manager
    manager.clear()
    manager.set_mode("car")
    state["route_start"] = _time.monotonic()
    state["route_keys"] = []
    manager.finished.connect(lambda key: state["route_keys"].append(
        (key, round(_time.monotonic() - state["route_start"], 1))))
    window.route_point(*ROUTE_A, "Эспланада", end=False)
    window.route_point(*ROUTE_B, "Мотовилиха", end=True)


def _route_wait(limit=60.0):
    """Ждать конца расчёта маршрута, не дольше limit секунд."""
    import time as _time
    manager = state["window"].route_manager
    start = _time.monotonic()
    while manager.busy() and _time.monotonic() - start < limit:
        QgsApplication.processEvents()
        _time.sleep(0.02)


def _route_report(window):
    """Маршрут: длина, время, метка и проход только по дугам графа."""
    import numpy as np
    from planetx.core import routing
    manager = window.route_manager
    route = manager.last
    out = {"keys": list(state.get("route_keys", [])),
           "answer": window.panel.answer.text()[:200]}
    if route is None:
        return out
    out["km"] = round(route.length / 1000.0, 2)
    out["minutes"] = round(route.seconds / 60.0, 1)
    out["points"] = len(route.points)
    g = manager.graph
    index = {tuple(np.rint(n).astype(np.int64)): i
             for i, n in enumerate(g.nodes)}
    arcs = set(zip(g.start.tolist(), g.target.tolist()))
    inner = []
    for lat, lon in route.points[2:-2]:
        x, y = routing.to_grid(lat, lon)
        inner.append(index.get((int(round(x)), int(round(y)))))
    pairs = list(zip(inner[:-1], inner[1:]))
    out["nodes_known"] = sum(i is not None for i in inner)
    out["arcs_ok"] = sum((a, b) in arcs for a, b in pairs)
    out["arcs_total"] = len(pairs)
    return out


@check(500)
def route_car_check():
    _route_wait()
    window = state["window"]
    result["route"] = {"car": _route_report(window)}
    place = [p for p in window.myplaces.places
             if p.name.startswith("Маршрут") or p.name.startswith("Route")]
    result["route"]["places"] = [(p.name, p.measure) for p in place]
    window.view.grabFramebuffer().save(
        os.path.join(TEMP, "planetx_route.png"))
    state["route_keys"].clear()
    state["route_start"] = __import__("time").monotonic()
    window.route_manager.link("foot")


@check(8000)
def route_view():
    """Вид над серединой маршрута: обе метки, на машине и пешком."""
    from planetx.core.navigation import Pose
    _route_wait()
    view = state["window"].view
    view.navigator.stop()
    view.navigator.set_pose(Pose(0.5 * (ROUTE_A[0] + ROUTE_B[0]),
                                 0.5 * (ROUTE_A[1] + ROUTE_B[1]), 6500.0,
                                 0.0, 0.0))


@check(500)
def route_shot():
    state["window"].view.grabFramebuffer().save(
        os.path.join(TEMP, "planetx_route.png"))


@check(500)
def route_foot_check():
    _route_wait()
    window = state["window"]
    result["route"]["foot"] = _route_report(window)
    # Меню на глобусе в середине вида: новые пункты.
    from qgis.PyQt.QtWidgets import QMenu
    from planetx.core.navigation import Pose
    from planetx.ui import globemenu
    view = window.view
    view.navigator.stop()
    view.navigator.set_pose(Pose(ROUTE_A[0], ROUTE_A[1], 3000.0, 0.0,
                                 0.0))
    view.grabFramebuffer()
    before = set(window.findChildren(QMenu))
    ratio = view.devicePixelRatioF()
    globemenu.show(window, view.width() * ratio / 2.0,
                   view.height() * ratio / 2.0)
    menus = [m for m in window.findChildren(QMenu) if m not in before]
    result["route"]["menu"] = [a.text() for m in menus
                               for a in m.actions() if a.text()]
    for menu in menus:
        menu.close()
    # Вращение вокруг точки: перелёт, потом азимут растёт.
    window.spin_here(*ROUTE_B)
    state["spin_heading"] = None


@check(500)
def route_spin_wait():
    return None


@check(500)
def route_spin_check():
    import time as _time
    window = state["window"]
    nav = window.view.navigator
    first = (nav.pose.heading, nav.pose.lat, nav.pose.lon, nav.pose.tilt)
    start = _time.monotonic()
    while _time.monotonic() - start < 1.0:
        QgsApplication.processEvents()
        _time.sleep(0.02)
    second = nav.pose.heading
    result["route"]["spin"] = {
        "at_point": [round(first[1] - ROUTE_B[0], 4),
                     round(first[2] - ROUTE_B[1], 4)],
        "tilt": round(first[3], 1),
        "turned_deg_per_s": round((second - first[0]) % 360.0, 1),
        "flying": nav.flight is not None}
    nav.stop()
    result["route"]["stopped"] = nav.flight is None
    # Метки маршрутов убираются.
    for p in list(window.myplaces.places):
        if p.name.startswith("Маршрут") or p.name.startswith("Route"):
            window.myplaces.remove(p.key)
    window.route_manager.clear()
    result["route"]["gl"] = dict(window.view.gl_errors)


@check(500)
def menu_actions():
    """Меню на глобусе после причёсывания терминов: координаты первой
    строкой, «Что здесь?» с адресом Nominatim, «Измерить расстояние»,
    «Скопировать ссылку на место». Один живой запрос к Nominatim."""
    from qgis.PyQt.QtWidgets import QApplication, QMenu
    from planetx.core.navigation import Pose
    from planetx.ui import globemenu
    window = state["window"]
    window.set_body("earth")
    view = window.view
    view.navigator.stop()
    view.navigator.set_pose(Pose(ROUTE_A[0], ROUTE_A[1], 3000.0, 0.0, 0.0))
    view.grabFramebuffer()
    ratio = view.devicePixelRatioF()
    px, py = view.width() * ratio / 2.0, view.height() * ratio / 2.0
    before = set(window.findChildren(QMenu))
    globemenu.show(window, px, py)
    menus = [m for m in window.findChildren(QMenu) if m not in before]
    actions = {a.text(): a for m in menus for a in m.actions() if a.text()}
    out = result.setdefault("menu_actions", {})
    out["items"] = list(actions)
    first = [a for m in menus for a in m.actions()][0]
    first.trigger()
    out["coords_copied"] = QApplication.clipboard().text() == first.text()
    actions["Скопировать ссылку на место"].trigger()
    out["link"] = QApplication.clipboard().text()
    actions["Измерить расстояние"].trigger()
    out["ruler"] = {"open": window._ruler_open(),
                    "points": len(window.ruler.points)}
    window.ruler_dialog.close()
    actions["Что здесь?"].trigger()
    out["identified"] = window.identified is not None \
        and window.identified.isVisible()
    for menu in menus:
        menu.close()
    state["what_at"] = window._identify_at[:2]


@check(500)
def menu_actions_check():
    import time as _time
    window = state["window"]
    out = result["menu_actions"]
    start = _time.monotonic()
    lat, lon = state.pop("what_at")
    while window._address_value(lat, lon) == "загружается" \
            and _time.monotonic() - start < 15.0:
        QgsApplication.processEvents()
        _time.sleep(0.05)
    out["address"] = window._address_value(lat, lon)
    groups = window._identify_site(lat, lon, None)
    out["site_rows"] = [row[0] for row in groups[0][1][0][1]] \
        if groups else []
    window.identified.close()


def ecef_to_geodetic_point(point):
    from planetx.core.ellipsoid import ecef_to_geodetic
    return ecef_to_geodetic(point)


@check(500)
def sat_path_off():
    window = state["window"]
    manager = window.satellite_manager
    manager.clock = None
    out = result["sat_path"]
    # Снятие строки снимает выбор, витка и камеры следом больше нет.
    window.set_extra("satellites", False)
    out["after_off"] = {"selected": manager.selected,
                        "follow": manager.follow,
                        "shapes": len(manager.shapes()),
                        "tick": manager.tick.isActive()}
    window.set_extra("satellites", True)


@check(800)
def clock_on():
    """Часы глобуса: строка «Солнце» без меток со временем открывает
    шкалу на часах компьютера, показ ×3600."""
    import time as _time
    window = state["window"]
    window.set_body("earth")
    bar = window.timebar
    out = result.setdefault("clock", {})
    window.set_extra("sun", False)
    out["before"] = {"known": bar.known, "data": bar.data}
    window.set_extra("sun", True)
    window._time_toggled(True)
    window.toolbar.set_time_shown(True)
    out["opened"] = {
        "known": bar.known, "shown": bar.shown(),
        "point": bar.track.point, "now_button": bar.now.isVisibleTo(bar),
        "rate": bar.speed.currentData(), "label": bar.label.text(),
        "from_now": round(bar.range()[1] - _time.time(), 1),
        "available": window.toolbar.time.isEnabled()
        if hasattr(window.toolbar, "time") else None}
    bar.speed.setCurrentIndex(bar.speed.findData(3600.0))
    bar.toggle()
    state["clock_start"] = (bar.range()[1], _time.monotonic(),
                            tuple(window.view.sun))


@check(500)
def clock_wait():
    return None


@check(500)
def clock_check():
    import time as _time
    import numpy as np
    window = state["window"]
    bar = window.timebar
    out = result["clock"]
    moment, wall, sun_dir = state.pop("clock_start")
    now = bar.range()[1]
    out["rate_seen"] = round((now - moment) / (_time.monotonic() - wall))
    cos = float(np.clip(np.dot(np.array(sun_dir),
                               np.array(window.view.sun)), -1.0, 1.0))
    out["sun_turned_deg"] = round(float(np.degrees(np.arccos(cos))), 2)
    out["sun_moment"] = round(window.sun_time() - now, 1)
    out["satellite_moment"] = round(
        window.satellite_manager.moment() - now, 1)
    # Край охвата: показ идёт дальше, охват сдвигается за моментом.
    a, b = bar.extent()
    bar.track.set_range(b - 1.0, b - 1.0)
    bar._last = _time.monotonic() - 1.0
    bar._step()
    a2, b2 = bar.extent()
    hi = bar.range()[1]
    out["past_end"] = {"moved_s": round(hi - b),
                       "inside": a2 <= hi <= b2,
                       "playing": bar.timer.isActive()}
    bar.to_now()
    out["now"] = {"from_now": round(bar.range()[1] - _time.time(), 1),
                  "rate": bar.speed.currentData(),
                  "playing": bar.timer.isActive()}
    bar.stop()
    window.set_extra("sun", False)
    out["after_off"] = {"known": bar.known, "shown": bar.shown()}
    out["gl"] = dict(window.view.gl_errors)


@check(500)
def sat_off():
    from planetx.core import satellites as core
    window = state["window"]
    window.set_extra("satellites", False)
    server, counts, feed = state.pop("sat_server")
    core.FEED = feed
    server.shutdown()
    out = result["satellites"]
    out["after_off"] = {"source": window.view.satellites.source is None,
                        "tick": window.satellite_manager.tick.isActive(),
                        "credit": "CelesTrak" in window.attribution.text()}


@check(1500)
def overlay_refresh_check():
    window = state["window"]
    out = result["overlay_refresh"]
    window._refresh_overlays()
    out["third"] = _refresh_state(window)
    window.myplaces.remove(state.pop("refresh_key"))
    server, _ = state.pop("image_server")
    server.shutdown()
    out["ground_after"] = len(window._ground_rasters)
    out["gl"] = dict(window.view.gl_errors)

@check(2000)
def section_open():
    # Разрез вниз поперёк Японского жёлоба: с востока на запад по 38.5°
    # с. ш., плита уходит под Японию. Зоны плит - с локальной копии.
    from planetx.core.features import Shape
    window = state["window"]
    folder = os.environ.get("PLANETX_TERRAIN_DIR")
    if folder:
        from qgis.PyQt.QtCore import QUrl
        window.slab_base = QUrl.fromLocalFile(
            os.path.join(folder, "slab2")).toString() + "/{code}.npz"
    key = window.myplaces.add(Shape("line", [(38.5, 146.0), (38.5, 132.0)],
                                    name="Через Японский жёлоб"))
    state["section_key"] = key
    window._place_action("section", key)
    result["section"] = {"started": time.monotonic(),
                         "dialog": window.section_dialog is not None}


@check(3000)
def ground_refs():
    # Сторож сбоя QGIS 3.36 на выходе, 5 октября 2026 года. Закрытое окно
    # Qt удаляет позже, а очистка проекта при выходе будила его, и оно
    # собирало новое наложение с растрами картинок вне проекта. Python
    # удалял их после выхода QGIS. Шаг закрывает окно, очищает проект,
    # как finish, и считает живые растры и наложение без сборки мусора.
    import gc
    from qgis.core import QgsRasterLayer
    window = state["window"]
    from qgis.PyQt import sip

    def rasters():
        return len([l for l in gc.get_objects()
                    if isinstance(l, QgsRasterLayer)
                    and not sip.isdeleted(l)])

    before = rasters()
    window.close()
    QgsProject.instance().clear()
    alive = rasters()
    overlay = window.overlay
    result["ground_refs"] = {
        "before": before, "after": alive,
        "overlay_after_close": overlay is not None
        and not getattr(overlay, "stopped", True)}


@check(1000)
def section_wait():
    window = state["window"]
    out = result["section"]
    waiting = (window.crust is None and not window.crust_error) \
        or window._quake_reply is not None or window._slab_replies
    if waiting and time.monotonic() - out["started"] < 60.0:
        return 1000
    out["wait_s"] = round(time.monotonic() - out["started"], 1)


@check(1000)
def section_check():
    import numpy as np
    window = state["window"]
    dialog = window.section_dialog
    out = result["section"]
    s = dialog.chart.section
    out["length_km"] = round(float(s.distance[-1]))
    out["crust"] = s.bounds is not None
    slab = np.isfinite(s.slab_top)
    out["slab_points"] = int(slab.sum())
    out["slab_depth_km"] = [round(float(np.nanmin(s.slab_top)), 1),
                            round(float(np.nanmax(s.slab_top)), 1)] \
        if slab.any() else None
    out["moho_km"] = [round(float(v), 1) for v in
                      (np.min(-s.bounds[:, -1]), np.max(-s.bounds[:, -1]))] \
        if s.bounds is not None else None
    out["quakes"] = len(s.quakes)
    out["feed_events"] = len(window.quake_events)
    out["feed_error"] = window.quake_error
    out["near_line"] = sorted(
        (round(q.lat, 1), round(q.lon, 1), round(q.depth))
        for q in window.quake_events
        if 36.0 < q.lat < 41.0 and 130.0 < q.lon < 147.0)[:8]
    out["deep_quakes"] = sum(1 for q in s.quakes if q[1] > 70.0)
    out["stats"] = dialog.stats.text()
    # За 30 суток ближайшие очаги у этой линии - в 100-150 км от неё.
    dialog.band.setValue(400.0)
    out["quakes_400km"] = len(dialog.chart.section.quakes)
    dialog.grab().save(os.path.join(TEMP, "planetx_section.png"))
    # Курсор над графиком - метка на глобусе.
    dialog.chart.hovered.emit(len(s.distance) // 2)
    out["mark"] = window._section_mark is not None \
        and window._section_mark in window.view.tool_marks
    dialog.chart.hovered.emit(-1)
    out["mark_after"] = window._section_mark is not None
    # Глубина 2891 км - до границы ядра.
    dialog.depth.setCurrentIndex(3)
    out["depth_core"] = dialog.chart.section.depth
    dialog.grab().save(os.path.join(TEMP, "planetx_section_core.png"))
    # Стенка на глобусе: вид с юга с наклоном, разрез до 700 км.
    from planetx.core.navigation import Pose
    dialog.depth.setCurrentIndex(2)
    view = window.view
    view.navigator.stop()
    view.navigator.show(Pose(30.0, 139.0, 3500000.0, 0.0, 55.0))
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_section_wall.png"))
    out["wall_vertices"] = view.section_wall.vertex_count()
    out["wall_drawn"] = view.section_wall.drawn
    dialog.close()
    view.grabFramebuffer()
    out["wall_after_close"] = view.section_wall.drawn
    window.myplaces.remove(state["section_key"])
    out["gl"] = dict(window.view.gl_errors)


@check(10000)
def cutaway_on():
    # Разрез Земли: сектор над Европой, вид сбоку с 15 000 км.
    from planetx.core.navigation import Pose
    window = state["window"]
    nav = window.view.navigator
    nav.stop()
    # Сектор 143.5° в. д. - 126.5° з. д.: западная грань идёт через
    # Японский жёлоб. Землетрясения - очаги у жёлоба, в вынутом секторе.
    nav.set_pose(Pose(45.0, -171.5, 15000000.0, 0.0, 0.0))
    # Зоны плит Slab2 - из локальной копии planetx-terrain, если есть.
    folder = os.environ.get("PLANETX_TERRAIN_DIR")
    if folder:
        from qgis.PyQt.QtCore import QUrl
        window.slab_base = QUrl.fromLocalFile(
            os.path.join(folder, "slab2")).toString() + "/{code}.npz"
    window.set_extra("cutaway", True)
    window.set_extra("quakes", True)
    nav.set_pose(Pose(25.0, 175.0, 18000000.0, 300.0, 20.0))
    result["cutaway"] = {"wedge": list(window.view.wedge),
                         "started": time.monotonic()}


@check(1000)
def cutaway_wait():
    # Модель коры CRUST1.0 скачивается с сайта UCSD.
    window = state["window"]
    out = result["cutaway"]
    out.setdefault("pending_seen", 0)
    out["pending_seen"] = max(out["pending_seen"],
                              window.view.data_pending)
    if (window.crust is None and not window.crust_error
            or window._slab_replies) \
            and time.monotonic() - out["started"] < 60.0:
        return 1000
    out["crust_s"] = round(time.monotonic() - out["started"], 1)
    out["crust_error"] = window.crust_error
    out["crust"] = window.crust is not None
    out["legend_crust"] = window.cutaway_legend.crust
    out["credit"] = "CRUST1.0" in window.attribution.text()
    out["slab_codes"] = list(window._slab_codes)
    out["slab_loaded"] = sorted(window.slab_zones)
    out["slab_errors"] = dict(window.slab_errors)
    out["slab_credit"] = "Slab2" in window.attribution.text()
    out["legend_slabs"] = window.cutaway_legend.slabs
    out["pending_after"] = window.view.data_pending


@check(3000)
def cutaway_check():
    window = state["window"]
    view = window.view
    out = result["cutaway"]
    image = view.grabFramebuffer()
    image.save(os.path.join(TEMP, "planetx_cutaway.png"))
    out["legend"] = window.cutaway_legend.isVisible()
    window.grab().save(os.path.join(TEMP, "planetx_cutaway_window.png"))
    out["faces_drawn"] = view.cutaway.drawn
    out["vertices"] = view.cutaway.vertex_count()
    out["gain"] = view.wedge_gain
    out["slab_vertices"] = view.cutaway_slabs.vertex_count()
    out["slab_drawn"] = view.cutaway_slabs.drawn
    # Угол тянется мышью: юго-западный угол - на 10° севернее и 15°
    # западнее, через пиксели экрана.
    import numpy as np
    from planetx.core.ellipsoid import geodetic_to_ecef
    corners = window.wedge_corners
    out["corner_tool"] = view.vertex_tool is corners
    out["corner_marks"] = sum(1 for m in view.tool_marks
                              if -420004 < m.id <= -420000)
    before = view.wedge
    lat, lon = before.south, before.west
    target = (lat + 10.0, lon - 15.0)
    xyz = geodetic_to_ecef(np.array([lat, target[0]]),
                           np.array([lon, target[1]]), np.zeros(2))
    pixels, _ = view.camera.project(xyz)
    out["grabbed"] = corners.grab(*pixels[0])
    corners.move(*pixels[1])
    corners.drop()
    after = view.wedge
    out["wedge_after"] = [round(v, 1) for v in after]
    out["moved_by"] = [round(after.south - before.south, 1),
                       round((after.west - before.west + 180.0) % 360.0
                             - 180.0, 1)]
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_cutaway_moved.png"))
    out["gl_drag"] = dict(view.gl_errors)
    out["legend_gain"] = window.cutaway_legend.gain
    out["gl"] = dict(view.gl_errors)
    # Ближе: западная грань у Японского жёлоба, взгляд на запад
    # из вынутого сектора, 400 км.
    from planetx.core.navigation import Pose
    view.navigator.set_pose(Pose(38.0, 145.0, 400000.0, 270.0, 80.0))


@check(3000)
def cutaway_close():
    window = state["window"]
    view = window.view
    out = result["cutaway"]
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_cutaway_close.png"))
    out["close_faces_drawn"] = view.cutaway.drawn
    out["close_gain"] = view.wedge_gain
    window.grab().save(os.path.join(TEMP, "planetx_cutaway_close_win.png"))
    window.set_extra("cutaway", False)
    window.set_extra("quakes", False)


@check(1000)
def cutaway_off():
    window = state["window"]
    view = window.view
    out = result["cutaway"]
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_cutaway_off.png"))
    out["off_wedge"] = view.wedge
    out["off_deep"] = view.camera.deep
    out["off_faces_drawn"] = view.cutaway.drawn
    out["gl_after"] = dict(view.gl_errors)


@check(1000)
def quakes_off():
    window = state["window"]
    view = window.view
    out = result["quakes"]
    view.grabFramebuffer()
    out["off_drawn"] = view.quakes.drawn
    out["off_legend"] = window.quake_legend.isVisible()
    out["off_credit"] = "USGS" in window.attribution.text()
    out["gl_after"] = dict(view.gl_errors)


@check(15000)
def vegas_open():
    # Демо «Тоннели Vegas Loop» из меню значка «Демо».
    window = state["window"]
    action = next(a for a in window.toolbar.demo.menu().actions()
                  if a.text() in ("Тоннели Vegas Loop", "Vegas Loop tunnels"))
    action.trigger()
    result["vegas"] = {"icon": window.toolbar.subsurface.isVisible(),
                       "started": window.subsurface.job is not None
                       or window.subsurface.model is not None}


@check(3000)
def vegas_wait():
    window = state["window"]
    if window.subsurface.job is not None:
        return 500


@check(3000)
def vegas_check():
    import numpy as np
    window = state["window"]
    view = window.view
    out = result["vegas"]
    model = window.subsurface.model
    out["tunnels"] = len(model.tunnels) if model else None
    out["missing"] = model.missing if model else None
    out["status"] = window.subsurface.dialog.status.text() \
        if window.subsurface.dialog else None
    out["vertices"] = view.subsurface.vertex_count()
    out["drawn"] = view.subsurface.drawn
    out["alpha"] = view.surface_alpha
    out["places"] = len([p for p in window.myplaces.places
                         if "Station" in p.name])
    if model and model.tunnels:
        _, pts, depth, diameter, _ = model.tunnels[0]
        g = window.subsurface._ground(pts[:, 0], pts[:, 1])
        out["first"] = {"depth": depth, "diameter": diameter,
                        "ground": [round(float(np.min(g)), 1),
                                   round(float(np.max(g)), 1)]}
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_vegas.png"))
    # Окно «Объекты»: щелчок по пикселю оси первого тоннеля.
    pick = next(p for p in window.subsurface.picks if p.kind == "tunnel")
    pixels, front = view.camera.project(pick.xyz)
    k = len(pixels) // 2
    found = window.subsurface.identify(float(pixels[k][0]),
                                       float(pixels[k][1]), 6.0)
    out["identify"] = [(name, dict(values)) for name, values, _ in found[:1]]
    out["identify_far"] = len(window.subsurface.identify(-500.0, -500.0,
                                                         6.0))
    # Разрез модели вдоль самого длинного тоннеля.
    longest = max(model.tunnels, key=lambda t: len(t[1]))
    pts = longest[1]
    window._open_model_section("Тоннель", [tuple(pts[0]), tuple(pts[-1])])
    found = window.model_section_dialog.chart.section
    out["model_section"] = {
        "tunnels": len(found.tunnels) if found else None,
        "depth": [round(float(found.ground[0] - found.tunnels[0][2][0]), 1)]
        if found and found.tunnels else None}
    window.model_section_dialog.grab().save(
        os.path.join(TEMP, "planetx_vegas_section.png"))
    window.model_section_dialog.close()
    out["gl"] = dict(view.gl_errors)


@check(8000)
def template_make():
    # Кнопка «Создать шаблон…» без окна выбора файла: шаблон у точки
    # взгляда над Пермью и его постройка.
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.view.navigator.stop()
    window.view.navigator.set_pose(Pose(58.01, 56.25, 3000.0, 0.0, 55.0))
    window.subsurface.open_dialog()
    path = os.path.join(TEMP, "planetx_template.gpkg")
    window.subsurface.make_template(path)
    from qgis.core import QgsProject
    group = QgsProject.instance().layerTreeRoot().findGroup(
        "Шаблон подземного")
    result["template"] = {"exists": os.path.exists(path),
                          "group_layers": len(group.findLayers())
                          if group else None}


@check(1000)
def template_wait():
    window = state["window"]
    if window.subsurface.job is not None:
        return 500
    model = window.subsurface.model
    out = result["template"]
    out["model"] = None if model is None else {
        "holes": len(model.holes), "tunnels": len(model.tunnels),
        "sections": len(model.sections), "rings": len(model.rings),
        "images": len(model.images), "beds": model.beds,
        "missing": model.missing}
    out["status"] = window.subsurface.dialog.status.text()
    out["gl"] = dict(window.view.gl_errors)
    window.grab().save(os.path.join(TEMP, "planetx_template.png"))
    window.subsurface.clear()


@check(15000)
def subsurface_tour():
    # Тур демо «Пермские отложения»: описание остановки под кнопками.
    window = state["window"]
    key = window.open_demo("subsurface")
    stops = window._tour_stops(key)
    window.tour.start(stops)
    bar = window.tour.bar
    result["subsurface_tour"] = {
        "stops": [s.name for s in stops],
        "caption": bar.caption.text(), "caption_shown": bar.caption
        .isVisible()}


@check(1000)
def subsurface_tour_check():
    window = state["window"]
    window.tour.play_from(2)
    bar = window.tour.bar
    out = result["subsurface_tour"]
    out["caption_3"] = bar.caption.text()
    window.grab().save(os.path.join(TEMP, "planetx_subsurface_tour.png"))
    window.tour.stop()
    window.subsurface.clear()
    out["gl"] = dict(window.view.gl_errors)


@check(15000)
def subsurface_open():
    # Подземный режим, шаг 4 плана фазы 3: демо из меню значка «Демо».
    window = state["window"]
    action = next(a for a in window.toolbar.demo.menu().actions()
                  if a.text() in ("Пермские отложения",
                                  "Permian deposits"))
    action.trigger()
    result["subsurface"] = {"started": window.subsurface.job is not None
                            or window.subsurface.model is not None}


@check(3000)
def subsurface_wait():
    window = state["window"]
    if window.subsurface.job is not None:
        return 500


@check(3500)
def subsurface_check():
    window = state["window"]
    view = window.view
    out = result["subsurface"]
    model = window.subsurface.model
    out["holes"] = len(model.holes) if model else None
    out["horizons"] = len(model.horizons) if model else None
    out["sections"] = len(model.sections) if model else None
    out["rings"] = len(model.rings) if model else None
    out["missing"] = model.missing if model else None
    out["skipped"] = model.skipped if model else None
    out["status"] = window.subsurface.dialog.status.text() \
        if window.subsurface.dialog else None
    out["meshes"] = sorted(view.subsurface.buffers)
    out["vertices"] = view.subsurface.vertex_count()
    out["drawn"] = view.subsurface.drawn
    out["cut_shown"] = view.gibs["cut"].shown
    out["cut_textures"] = len(view.gibs["cut"].textures)
    out["alpha"] = view.surface_alpha
    out["marks"] = len(view.subsurface_marks)
    out["scale"] = view.store.scale
    out["gl"] = dict(view.gl_errors)
    if model:
        import numpy as np
        lines = list(model.sections) + [np.vstack([r, r[:1]])
                                        for r in model.rings]
        out["nan_samples"] = [
            int(sum(np.isnan(h.at(line[:, 0], line[:, 1])).sum()
                    for h in model.horizons)) for line in lines]
        out["line_points"] = [len(line) for line in lines]
    # Исключение из paintGL не доходит до журнала QGIS: кадр
    # рисуется здесь, ошибка - в отчёт.
    import traceback
    view.makeCurrent()
    try:
        view._fit_camera()
        view._render(view.devicePixelRatioF())
        out["render_error"] = ""
    except (RuntimeError, ValueError, TypeError, AttributeError,
            KeyError, IndexError) as exc:
        out["render_error"] = traceback.format_exc()[-1500:] or str(exc)
    view.doneCurrent()
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_subsurface.png"))
    out["images"] = len(model.images) if model else None
    out["legend"] = [window.beds_legend.isVisible(),
                     len(window.beds_legend.items)]
    out["beds"] = list(model.beds) if model else None
    out["source"] = window.subsurface.settings.get("source")
    window.grab().save(os.path.join(TEMP, "planetx_subsurface_window.png"))
    out["image_walls"] = view.image_walls.drawn
    # Окно «Объекты»: щелчок по середине ствола первой скважины.
    pick = next((p for p in window.subsurface.picks if p.kind == "hole"),
                None)
    if pick is not None:
        pixels, front = view.camera.project(pick.xyz)
        k = len(pixels) // 2
        found = window.subsurface.identify(float(pixels[k][0]),
                                           float(pixels[k][1]), 6.0)
        out["identify"] = [(name, dict(values))
                           for name, values, _ in found[:1]]
    # Замер кадров по вариантам: PLANETX_SS_VARIANT=opaque - поверхность
    # непрозрачна, none - подземного нет, та же камера.
    variant = os.environ.get("PLANETX_SS_VARIANT", "")
    if variant == "opaque":
        window.subsurface.set_options(dict(window.subsurface.settings,
                                           opacity=1.0))
    elif variant == "none":
        window.subsurface.clear()
    out["variant"] = variant
    _swing_start("ss_top")


@check(8000)
def image_view():
    # Разрез 3-3 с картинкой вблизи: камера к югу от его середины
    # смотрит на север, в вырез.
    import numpy as np
    from planetx.core.navigation import Pose
    window = state["window"]
    if "ss_top_swing" in state:
        # Качание камеры для замера кадров идёт, если шаг его отчёта
        # не запускался.
        _swing_report("ss_top")
    model = window.subsurface.model
    _, pts, _, _, _ = model.images[0]
    lat, lon = (float(v) for v in np.mean(pts, axis=0))
    window.view.navigator.stop()
    window.view.navigator.set_pose(Pose(lat - 0.003, lon + 0.012, 1800.0,
                                        0.0, 70.0))
    window.view.update()


@check(1000)
def image_view_check():
    window = state["window"]
    view = window.view
    result.setdefault("subsurface", {})["image_close"] = {
        "drawn": view.image_walls.drawn, "gl": dict(view.gl_errors)}
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_image_wall.png"))



@check(3000)
def subsurface_toggle():
    # Геология - обычные слои глобуса: флажок устьев снят - скважин
    # в 3D нет, наложение геологические слои не рисует.
    from qgis.core import QgsProject
    window = state["window"]
    out = result.setdefault("subsurface", {})
    group = QgsProject.instance().layerTreeRoot().findGroup(
        "Пермские отложения")
    collar = [node.layer() for node in group.findLayers()
              if node.layer().name() == "collar"]
    used = set(window.subsurface.sync_project(window._shown_in_order()))
    out["overlay_has_geology"] = bool(used & set(window._applied_layers
                                                 or ()))
    state["collar_id"] = collar[0].id() if collar else None
    window.set_layer_shown(state["collar_id"], False)
    window.refresh()


@check(3000)
def subsurface_toggle_check():
    window = state["window"]
    out = result["subsurface"]
    if window.subsurface.job is not None:
        return 500
    model = window.subsurface.model
    out["holes_after_uncheck"] = len(model.holes) if model else None
    out["horizons_after_uncheck"] = len(model.horizons) if model else None
    window.set_layer_shown(state["collar_id"], True)
    window.refresh()


@check(3000)
def subsurface_style():
    # Стиль из QGIS: раскраска псевдоцветом у кровли roof_05, слой
    # устьев полупрозрачный. Перерисовка слоёв пересобирает модель.
    from qgis.core import (QgsColorRampShader, QgsProject,
                           QgsRasterShader,
                           QgsSingleBandPseudoColorRenderer)
    from qgis.PyQt.QtGui import QColor
    window = state["window"]
    layers = {layer.name(): layer for layer in
              QgsProject.instance().mapLayers().values()}
    roof = layers["roof_05"]
    stats = roof.dataProvider().bandStatistics(1)
    ramp = QgsColorRampShader(stats.minimumValue, stats.maximumValue)
    ramp.setColorRampItemList([
        QgsColorRampShader.ColorRampItem(stats.minimumValue,
                                         QColor(255, 0, 0)),
        QgsColorRampShader.ColorRampItem(stats.maximumValue,
                                         QColor(255, 255, 0))])
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(ramp)
    roof.setRenderer(QgsSingleBandPseudoColorRenderer(
        roof.dataProvider(), 1, shader))
    roof.triggerRepaint()
    layers["collar"].setOpacity(0.5)
    layers["collar"].triggerRepaint()


@check(3000)
def subsurface_style_check():
    from qgis.core import QgsProject
    window = state["window"]
    if window.subsurface.job is not None:
        return 500
    out = result.setdefault("subsurface", {})
    out["stale_auto"] = [window._layers_stale, window.auto_refresh,
                         window.refresh_timer.isActive()]
    model = window.subsurface.model
    styled = [h.code for h in model.horizons if h.colors is not None]
    out["styled_roofs"] = styled
    out["collar_alpha"] = model.alpha.get("collar")
    view = window.view
    out["after_restyle"] = {
        "surface_alpha": view.surface_alpha,
        "opacity": window.subsurface.settings.get("opacity"),
        "cut": window.subsurface.settings.get("cut"),
        "cut_shown": view.gibs["cut"].shown,
        "drawn": view.subsurface.drawn}
    window.view.grabFramebuffer().save(
        os.path.join(TEMP, "planetx_subsurface_style.png"))
    layers = {layer.name(): layer for layer in
              QgsProject.instance().mapLayers().values()}
    layers["collar"].setOpacity(1.0)


@check(3000)
def subsurface_places():
    # Вырез и стенка разреза по меткам, нарисованным на глобусе.
    from planetx.core.features import Shape
    window = state["window"]
    if "ss_top_swing" in state:
        _swing_report("ss_top")
    manager = window.subsurface
    south, north, west, east = manager.model.box()
    mid_lat, mid_lon = (south + north) / 2, (west + east) / 2
    ring = [(south + 0.001, west + 0.002), (south + 0.001, mid_lon),
            (mid_lat, mid_lon), (mid_lat, west + 0.002)]
    cut_key = window.myplaces.add(Shape("polygon", ring, name="Вырез пробы"))
    line_key = window.myplaces.add(Shape(
        "line", [(mid_lat - 0.004, west + 0.003),
                 (mid_lat - 0.004, mid_lon - 0.003)], name="Стенка пробы"))
    state["place_keys"] = (cut_key, line_key)
    out = result.setdefault("subsurface", {})
    before = manager.view.subsurface.vertex_count()
    state["places_before"] = before
    window.view.grabFramebuffer().save(
        os.path.join(TEMP, "planetx_places_0.png"))
    window._place_action("model_cut", cut_key)
    window._place_action("model_wall", line_key)
    out["places"] = {
        "parts": dict(manager.place_parts),
        "mask_rings": len(manager._mask_key[1]) if manager._mask_key
        else None,
        "vertices_grew": manager.view.subsurface.vertex_count() > before,
        "message": window.message[0]}


@check(3000)
def subsurface_places_check():
    from planetx.core.features import Shape
    window = state["window"]
    manager = window.subsurface
    out = result["subsurface"]["places"]
    if not state.get("places_waited"):
        # Маска выреза строится тайлами, кадр - когда они пришли.
        state["places_waited"] = True
        return 4000
    out["vertices_grew"] = window.view.subsurface.vertex_count() \
        > state["places_before"]
    view = window.view
    import traceback
    stuck = list(manager.tiles.running.values()) if manager.tiles else []
    out["stuck_errors"] = [
        "".join(traceback.format_exception(f.exception()))[-600:]
        for f in stuck if f.done() and f.exception() is not None]
    out["view_state"] = {
        "model": manager.model is not None,
        "cut_shown": view.gibs["cut"].shown,
        "cut_textures": len(view.gibs["cut"].textures),
        "surface_alpha": view.surface_alpha, "drawn": view.subsurface.drawn,
        "tiles": None if manager.tiles is None else [
            len(manager.tiles.queue), len(manager.tiles.running),
            view.gibs["cut"].loader is manager.tiles,
            manager.tiles.pool is not None],
        "pose": [round(view.navigator.pose.lat, 4),
                 round(view.navigator.pose.lon, 4),
                 round(view.navigator.pose.distance)]}
    window.view.grabFramebuffer().save(
        os.path.join(TEMP, "planetx_subsurface_places.png"))
    cut_key, line_key = state["place_keys"]
    # Правка формы метки выреза пересобирает модель.
    old_key = manager._places_key
    place = window.myplaces.find(cut_key)
    pts = list(place.shape.points)
    pts[2] = (pts[2][0] + 0.002, pts[2][1] + 0.003)
    window.myplaces.set_shape(cut_key, place.shape._replace(points=pts))
    out["rebuilt_on_edit"] = manager._places_key != old_key
    window._place_action("model_cut", cut_key)
    window._place_action("model_wall", line_key)
    out["parts_after_off"] = dict(manager.place_parts)
    state["places_off_at"] = time.monotonic()
    out["mask_rings_after_off"] = len(manager._mask_key[1]) \
        if manager._mask_key else None
    out["gl"] = dict(window.view.gl_errors)


@check(4000)
def subsurface_places_off():
    window = state["window"]
    window.view.grabFramebuffer().save(
        os.path.join(TEMP, "planetx_places_2.png"))
    cut_key, line_key = state["place_keys"]
    window.myplaces.remove(cut_key)
    window.myplaces.remove(line_key)


@check(1000)
def model_section_open():
    # Окно «Разрез модели» по пути через середину модели с запада на
    # восток: пласты, скважины и картинка не нужна - только модель.
    window = state["window"]
    model = window.subsurface.model
    south, north, west, east = model.box()
    # Через первый ряд скважин: ряды стоят через 700 м.
    lat = model.holes[0][1]
    window._open_model_section("Проба", [(lat, west), (lat, east)])
    dialog = window.model_section_dialog
    found = dialog.chart.section
    out = result.setdefault("subsurface", {})
    out["model_section"] = {
        "shown": dialog.isVisible(),
        "beds": len(found.beds) if found else None,
        "holes": len(found.holes) if found else None,
        "length": round(float(found.distance[-1])) if found else None,
        "stats": dialog.stats.text()}
    dialog.grab().save(os.path.join(TEMP, "planetx_model_section.png"))
    dialog.close()

@check(500)
def subsurface_under():
    # Камера под землёй: точка взгляда на низу модели, глаз ниже рельефа.
    from planetx.core.navigation import Pose
    window = state["window"]
    out = result["subsurface"]
    if "ss_top_swing" in state:
        out["swing_over_model"] = _swing_report("ss_top")
    settings = dict(window.subsurface.settings, under=True)
    window.subsurface.set_options(settings)
    nav = window.view.navigator
    nav.stop()
    # show сажает точку взгляда на пол, set_pose - нет.
    nav.show(Pose(59.445, 56.89, 1500.0, 20.0, 75.0))
    out["floor"] = window.view.floor is not None


@check(3000)
def subsurface_under_check():
    window = state["window"]
    view = window.view
    out = result["subsurface"]
    out["eye_underground"] = view.eye_underground()
    out["gl_under"] = dict(view.gl_errors)
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_subsurface_under.png"))
    if os.environ.get("PLANETX_SS_PARTS"):
        # Отладка: каждая сетка отдельно с того же места.
        keep = dict(view.subsurface.buffers)
        for name in keep:
            view.subsurface.buffers = {name: keep[name]}
            view.grabFramebuffer().save(os.path.join(
                TEMP, "planetx_ss_%s.png" % name))
        view.subsurface.buffers = keep
    window.subsurface.set_options(dict(window.subsurface.settings,
                                       under=False))
    window.subsurface.clear()
    view.repaint()
    out["cleared"] = not view.subsurface.active and view.floor is None \
        and not view.gibs["cut"].shown and view.surface_alpha == 1.0
    window.myplaces.remove(window.myplaces.folders[-1].key)
    window.set_relief_scale(1.0)


@check(40000)
def jezero_open():
    # Демо «Кратер Езеро» из меню значка «Демо», шаг 5 плана фазы 3.
    window = state["window"]
    action = next(a for a in window.toolbar.demo.menu().actions()
                  if a.text() in ("Кратер Езеро", "Jezero crater"))
    folders = len(window.myplaces.folders)
    action.trigger()
    result["jezero"] = {"new_folder": len(window.myplaces.folders)
                        - folders}


@check(8000)
def jezero_probe():
    # Что под пикселями кадра: точка рельефа, высота, тайл кадра
    # и его снимок. Потом масштаб рельефа 1 для сравнения.
    from planetx.core.ellipsoid import ecef_to_geodetic
    from planetx.core.navigation import ground_under
    from planetx.core.tiling import lonlat_to_tile
    window = state["window"]
    view = window.view
    view._fit_camera()
    cam = view.camera
    probes = {}
    for name, fx, fy in (("brown", 0.75, 0.85), ("green", 0.3, 0.3),
                         ("crater", 0.5, 0.6)):
        px, py = cam.width * fx, cam.height * fy
        hit = ground_under(cam, px, py, view.navigator.pose.terrain)
        if hit is None:
            probes[name] = None
            continue
        lat, lon, h = (float(v) for v in ecef_to_geodetic(hit))
        drawn = [k for k in view.selection.draw
                 if lonlat_to_tile(lat, lon, k[0]) == (k[1], k[2])]
        probes[name] = {"lat": round(lat, 3), "lon": round(lon, 3),
                        "h": round(h), "drawn": drawn,
                        "textured": [k in view.textures for k in drawn],
                        "terrain": round(float(view.store.height_at(
                            lat, lon) or 0.0))}
    result.setdefault("jezero", {})["probe"] = probes
    result["jezero"]["levels"] = sorted({k[0] for k in view.selection.draw})
    result["jezero"]["eye_alt"] = round(float(cam.altitude()))
    result["jezero"]["source_max"] = window.source.max_level
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_jezero_s3.png"))
    # Подстилка в проверочном режиме зелёная. Над равниной Исиды при
    # масштабе 3 она закрывала рельеф, на прежнем коде пикселей много.
    import numpy as np
    view.show_holes = True
    image = view.grabFramebuffer()
    view.show_holes = False
    image = image.convertToFormat(image.Format.Format_RGBA8888) \
        if hasattr(image, "Format") else image.convertToFormat(17)
    ptr = image.constBits()
    ptr.setsize(image.sizeInBytes()) if hasattr(ptr, "setsize") else None
    rgba = np.frombuffer(ptr, dtype=np.uint8).reshape(
        image.height(), image.bytesPerLine() // 4, 4)
    green = (rgba[..., 0] == 0) & (rgba[..., 1] == 255) & (rgba[..., 2] == 0)
    result["jezero"]["underlay_pixels"] = int(green.sum())
    result["jezero"]["store_depth"] = round(view.store.depth())
    state["jz_scale"] = window._scale
    window.set_relief_scale(1.0)


@check(500)
def jezero_check():
    window = state["window"]
    window.view.grabFramebuffer().save(
        os.path.join(TEMP, "planetx_jezero_s1.png"))
    window.set_relief_scale(state["jz_scale"])
    window = state["window"]
    view = window.view
    out = result["jezero"]
    folder = window.myplaces.folders[-1]
    state["jz_folder"] = folder.key
    places = window.myplaces.places_in(folder.key)
    out["folder"] = folder.name
    out["places"] = len(places)
    out["body"] = window.body_key()
    out["slope"] = window.extras.get("slope")
    out["slope_textures"] = len(view.gibs["slope"].textures)
    out["legend"] = window.slope_legend.isVisible()
    out["stops"] = len(window._tour_stops(folder.key))
    out["gl"] = dict(view.gl_errors)
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_jezero.png"))
    rim = next(p for p in places if p.name.startswith("Край кратера"))
    line = next(p for p in places if p.name.startswith("Профиль"))
    window._place_action("profile", line.key)
    window._place_action("viewshed", rim.key)
    dialog = window.viewshed_dialog
    dialog.radius.setValue(30.0)
    state["jz_started"] = time.monotonic()
    dialog.build.emit(2.0, 0.0, 30000.0)


@check(3000)
def jezero_wait():
    window = state["window"]
    if window.viewshed_job is not None \
            and time.monotonic() - state["jz_started"] < 45.0:
        return 500


@check(500)
def jezero_done():
    window = state["window"]
    out = result["jezero"]
    vs = window.viewshed_result
    out["viewshed_share"] = round(vs.share, 3) if vs else None
    out["viewshed_status"] = window.viewshed_dialog.status.text()
    window.profile_dialog.refresh()
    p = window.profile_dialog.chart.profile
    if p is not None:
        out["profile_km"] = round(p.flat / 1000.0, 1)
        out["profile_low_high"] = [round(p.low), round(p.high)]
    window.view.grabFramebuffer().save(
        os.path.join(TEMP, "planetx_jezero_viewshed.png"))
    out["gl_after"] = dict(window.view.gl_errors)
    window.viewshed_dialog.clear.emit()
    window.viewshed_dialog.close()
    window.profile_dialog.close()
    window.myplaces.remove(state["jz_folder"])
    window.set_extra("slope", False)
    window.set_body("earth")


@check(500)
def tile_source():
    # Подложка в разделе «Слои» и окно «Новый источник тайлов».
    from planetx.ui.tilesource import TileSourceDialog
    window = state["window"]
    panel = window.panel
    group = panel.base_group
    rows = [group.child(i).text(0) for i in range(group.childCount())]
    osm = next(i for i in range(group.childCount())
               if group.child(i).text(0) == "OpenStreetMap")
    panel._geo_clicked(group.child(osm), 0)
    result["tile_source"] = {"rows": rows, "after_click": window.source.name}
    panel._geo_clicked(group.child(0), 0)
    pose = window.view.navigator.pose
    dialog = TileSourceDialog(window, (pose.lat, pose.lon))
    dialog.show()
    # Адрес одного тайла ArcGIS: уровень, ряд, столбец.
    dialog.address.setText(
        "https://server.arcgisonline.com/ArcGIS/rest/services/"
        "World_Topo_Map/MapServer/tile/5/10/17")
    dialog._check()
    state["tile_dialog"] = dialog


@check(500)
def tile_source_wait():
    import time
    dialog = state["tile_dialog"]
    began = state.setdefault("tile_began", time.monotonic())
    if (dialog.got < 4 or dialog.replies) \
            and time.monotonic() - began < 30:
        return 500
    out = result["tile_source"]
    out.update({"template": dialog.template, "name": dialog.name.text(),
                "got": dialog.got, "failed": dialog.failed,
                "level": dialog.level.value(),
                "status": dialog.status.text()})
    dialog.preview.pixmap().save(os.path.join(TEMP,
                                              "planetx_tile_preview.png"))
    dialog.grab().save(os.path.join(TEMP, "planetx_tile_dialog.png"))
    return None


@check(3000)
def tile_source_save():
    import planetx.ui.window as wmod
    from qgis.core import QgsSettings
    window = state["window"]
    dialog = state["tile_dialog"]
    dialog.accept()

    class Done:
        saved_name = dialog.saved_name

        def __init__(self, *args):
            pass

        def exec(self):
            return True
    real = wmod.TileSourceDialog
    wmod.TileSourceDialog = Done
    try:
        window.add_tile_source()
    finally:
        wmod.TileSourceDialog = real
    out = result["tile_source"]
    out["saved"] = dialog.saved_name
    out["source"] = window.source.name
    out["source_url"] = window.source.url
    group = window.panel.base_group
    out["rows_after"] = [group.child(i).text(0)
                         for i in range(group.childCount())]
    settings = QgsSettings()
    prefix = "connections/xyz/items/%s/" % dialog.saved_name
    out["settings_url"] = settings.value(prefix + "url")


@check(500)
def tile_source_check():
    from qgis.core import QgsSettings
    window = state["window"]
    out = result["tile_source"]
    out["loaded_levels"] = sorted({k[0] for k in window.view.textures})
    out["errors"] = len(window.errors)
    window.view.grabFramebuffer().save(
        os.path.join(TEMP, "planetx_tile_source.png"))
    window.panel.geo.grab().save(os.path.join(TEMP, "planetx_geo.png"))
    # Подложка по умолчанию обратно, подключение убирается.
    window.panel._geo_clicked(window.panel.base_group.child(0), 0)
    settings = QgsSettings()
    prefix = "connections/xyz/items/%s/" % out["saved"]
    for key in settings.allKeys():
        if key.startswith(prefix):
            settings.remove(key)


@check(500)
def basemap_checkbox():
    # Щелчок мышью по флажку подложки. До 2 октября 2026 года флажок
    # выбирал подложку, строки группы пересоздавались, и Qt присылал
    # itemClicked без строки - AttributeError в _geo_clicked, нашёл
    # автор на QGIS 3.40.15. Ошибки слотов идут в sys.excepthook.
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtTest import QTest
    from qgis.PyQt.QtWidgets import QStyle, QStyleOptionViewItem
    from planetx.qt_compat import enum
    window = state["window"]
    panel = window.panel
    base = next(s for s in panel.sections if s.name == "base")
    was_open = base.is_open()
    base.set_open(True)
    tree = panel.geo
    group = panel.base_group
    osm = next(i for i in range(group.childCount())
               if group.child(i).text(0) == "OpenStreetMap")
    row = group.child(osm)
    tree.scrollToItem(row)
    QgsApplication.processEvents()
    option = QStyleOptionViewItem()
    option.rect = tree.visualItemRect(row)
    option.features |= enum(QStyleOptionViewItem, "ViewItemFeature",
                            "HasCheckIndicator")
    box = tree.style().subElementRect(
        enum(QStyle, "SubElement", "SE_ItemViewItemCheckIndicator"),
        option, tree)
    caught = []
    hook = sys.excepthook
    sys.excepthook = lambda kind, value, tb: caught.append(repr(value))
    try:
        QTest.mouseClick(tree.viewport(),
                         enum(Qt, "MouseButton", "LeftButton"),
                         enum(Qt, "KeyboardModifier", "NoModifier"),
                         box.center())
        QgsApplication.processEvents()
    finally:
        sys.excepthook = hook
    result["basemap_checkbox"] = {
        "visible": not option.rect.isEmpty(),
        "source": window.source.name,
        "same_row": group.child(osm) is row,
        "errors": caught}
    panel._geo_clicked(group.child(0), 0)
    base.set_open(was_open)


@check(2000)
def folder_props():
    # Свойства папки как у Google Earth, 2 октября 2026 года.
    from planetx.core import kml, placetree
    from planetx.core.features import Shape
    from planetx.ui.folderprops import FolderDialog
    window = state["window"]
    store = window.myplaces
    out = result.setdefault("folder_props", {})
    top = store.add_folder("Проверка папки")
    state["fp_top"] = top
    a = store.add(Shape("point", [(58.0, 56.0)], name="в"), folder=top)
    b = store.add(Shape("point", [(58.1, 56.1)], name="а"), folder=top)
    c = store.add(Shape("point", [(58.2, 56.2)], name="б"), folder=top)
    # Окно свойств: имя, описание, группа переключателей, вид.
    dialog = FolderDialog(store.find(top), window.current_view, window)
    dialog.name.setText("Проверка папки 2")
    dialog.description.setPlainText("описание папки")
    dialog.radio.setChecked(True)
    dialog._snapshot()
    dialog.grab().save(os.path.join(TEMP, "planetx_folder_props.png"))
    store.update(top, dialog.values())
    folder = store.find(top)
    out["saved"] = [folder.name, folder.description, folder.radio,
                    folder.expandable, folder.view is not None]
    # Переключатели: включение всех оставляет первую по списку.
    window._places_toggled({a: True, b: True, c: True})
    out["radio_visible"] = [store.find(k).visible for k in (a, b, c)]
    # Щелчок по выбранному переключателю его не гасит.
    window._places_toggled({a: False})
    out["radio_keeps"] = store.find(a).visible
    window.panel.select_place(a)
    window.panel.list.grab().save(os.path.join(TEMP,
                                               "planetx_radio_list.png"))
    # Сортировка от А до Я.
    window._place_action("sort", top)
    out["sorted"] = [n.name for n in placetree.children(store.nodes(),
                                                        top)]
    # KML туда и обратно.
    text = kml.write_kml(store.export_tree(top))
    out["kml"] = ["radioFolder" in text, "описание папки" in text,
                  "<LookAt>" in text]
    back = kml.read_kml(text.encode("utf-8"))
    out["kml_back"] = [back.radio, back.description, back.view is not None]
    # Папка без раскрытия: строк детей в списке нет.
    store.update(top, {"expandable": 0, "radio": 0})
    item = None
    group = window.panel.places_group
    for i in range(group.childCount()):
        if group.child(i).data(0, 256 + 1) == top:
            item = group.child(i)
    out["closed_rows"] = item.childCount() if item is not None else None
    window._places_toggled({top: False})
    out["closed_hidden"] = [store.find(k).visible for k in (a, b, c)]
    # Вырезать и вставить.
    window._place_action("cut", b)
    out["after_cut"] = store.find(b) is None
    window.paste_places(top)
    out["after_paste"] = sorted(p.name for p in store.places_in(top))
    # Перелёт к виду папки.
    window._place_action("fly", top)
    out["fly"] = window.view.navigator.flight is not None
    # Без вида - перелёт к охвату меток папки.
    window.view.navigator.stop()
    store.update(top, {"view": ""})
    window._place_action("fly", top)
    flight = window.view.navigator.flight
    out["fly_extent"] = flight is not None


@check(500)
def folder_props_check():
    window = state["window"]
    window.myplaces.remove(state["fp_top"])
    result["folder_props"]["removed"] = \
        window.myplaces.find(state["fp_top"]) is None


@check(12000)
def slope_on():
    # Уклон над Эльбрусом, шаг 1 плана фазы 3.
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    nav = window.view.navigator
    nav.stop()
    nav.set_pose(Pose(43.35, 42.44, 40000.0, 0.0, 45.0))
    window.set_extra("slope", True)


def _slope_report(name):
    window = state["window"]
    view = window.view
    layer = view.gibs["slope"]
    image = view.grabFramebuffer()
    image.save(os.path.join(TEMP, "planetx_%s.png" % name))
    return {"textures": len(layer.textures), "shown": layer.shown,
            "max_level": layer.max_level,
            "loader": "slope" in window.gibs_loaders,
            "legend": window.slope_legend.isVisible(),
            "mode": window.slope_legend.mode,
            "errors": len(window.gibs_loaders["slope"].errors)
            if "slope" in window.gibs_loaders
            and hasattr(window.gibs_loaders["slope"], "errors") else None,
            "gl": dict(view.gl_errors)}


@check(12000)
def slope_check():
    window = state["window"]
    result["slope"] = {"elbrus": _slope_report("slope_elbrus")}
    window.set_extra("aspect", True)
    result["slope"]["aspect_turns_slope_off"] = \
        not window.extras.get("slope")


@check(500)
def aspect_check():
    from planetx.core.navigation import Pose
    window = state["window"]
    result["slope"]["aspect"] = _slope_report("aspect_elbrus")
    window.set_extra("slope", True)
    window.set_body("mars")
    nav = window.view.navigator
    nav.stop()
    nav.set_pose(Pose(18.65, -133.8, 1.2e6, 0.0, 30.0))


@check(12000)
def slope_mars():
    pass


@check(500)
def slope_mars_check():
    window = state["window"]
    result["slope"]["mars"] = _slope_report("slope_mars")
    window.set_body("mercury")
    result["slope"]["mercury_loader"] = "slope" in window.gibs_loaders
    window.set_body("earth")
    window.set_extra("slope", False)
    result["slope"]["off"] = "slope" not in window.gibs_loaders


@check(500)
def viewshed_on():
    # Видимость с вершины Чегет, радиус 10 км, шаг 2 плана фазы 3.
    from planetx.core.features import Shape
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    nav = window.view.navigator
    nav.stop()
    nav.set_pose(Pose(43.2425, 42.5157, 45000.0, 0.0, 30.0))
    key = window.myplaces.add(Shape("point", [(43.2425, 42.5157)],
                                    name="Чегет"))
    state["vs_key"] = key
    window._place_action("viewshed", key)
    dialog = window.viewshed_dialog
    result["viewshed"] = {"dialog": dialog is not None
                          and dialog.isVisible()}
    state["vs_started"] = time.monotonic()
    dialog.build.emit(2.0, 0.0, 10000.0)


@check(10000)
def viewshed_wait():
    window = state["window"]
    if window.viewshed_job is not None \
            and time.monotonic() - state["vs_started"] < 45.0:
        return 500
    result["viewshed"]["seconds"] = round(
        time.monotonic() - state["vs_started"], 1)


@check(500)
def viewshed_check():
    import numpy as np
    window = state["window"]
    view = window.view
    out = result["viewshed"]
    vs = window.viewshed_result
    layer = view.gibs["viewshed"]
    out["computed"] = vs is not None
    out["status"] = window.viewshed_dialog.status.text()
    if vs is not None:
        out["share"] = round(vs.share, 3)
        out["step"] = round(vs.step, 1)
        out["shape"] = list(vs.visible.shape)
        seen, inside = vs.at(np.array([43.2425, 43.2425]),
                             np.array([42.5160, 42.8]), 6378137.0)
        out["near_seen"] = bool(seen[0])
        out["far_inside"] = bool(inside[1])
    out["shown"] = layer.shown
    out["max_level"] = layer.max_level
    out["textures"] = len(layer.textures)
    out["gl"] = dict(view.gl_errors)
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_viewshed.png"))
    window.viewshed_dialog.clear.emit()
    out["cleared"] = not layer.shown and window.viewshed_tiles is None
    window.viewshed_dialog.close()
    window.myplaces.remove(state["vs_key"])


@check(8000)
def profile_hover_on():
    # Точка профиля под курсором графика: та же высота в другом месте
    # пути не возвращает метку на прежнее место. Путь через Эльбрус.
    from planetx.core.features import Shape
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    nav = window.view.navigator
    nav.stop()
    nav.set_pose(Pose(43.35, 42.44, 30000.0, 0.0, 30.0))
    key = window.myplaces.add(Shape("line", [(43.30, 42.38), (43.40, 42.50)],
                                    name="Профиль"))
    state["ph_key"] = key
    window._place_action("profile", key)


def _same_height_pair(p):
    """Два номера точек профиля с одной подписью высоты, дальше 1 км
    друг от друга, и третий номер с другой подписью."""
    import numpy as np
    text = np.rint(p.height).astype(int)
    for i in range(len(text)):
        far = np.nonzero((text == text[i])
                         & (np.abs(p.distance - p.distance[i]) > 1000.0))[0]
        if len(far):
            other = int(np.nonzero(text != text[i])[0][0])
            return i, int(far[0]), other
    return None


@check(500)
def profile_hover_a():
    window = state["window"]
    window.profile_dialog.refresh()
    p = window.profile_dialog.chart.profile
    pair = _same_height_pair(p)
    result["profile_hover"] = {"pair": list(pair) if pair else None}
    state["ph_pair"] = pair
    if pair:
        window.profile_dialog.chart.hovered.emit(float(pair[0]))


@check(500)
def profile_hover_b():
    window = state["window"]
    if state["ph_pair"]:
        window.profile_dialog.chart.hovered.emit(float(state["ph_pair"][2]))


@check(500)
def profile_hover_c():
    window = state["window"]
    if state["ph_pair"]:
        window.profile_dialog.chart.hovered.emit(float(state["ph_pair"][1]))


@check(500)
def profile_hover_check():
    from planetx.core.places import identity
    window = state["window"]
    out = result["profile_hover"]
    mark = window._profile_mark
    labels = window.view.labels
    row = labels._row.get(identity(mark)) if mark is not None else None
    if row is not None:
        drawn = labels._places[row]
        out["mark"] = [round(mark.lat, 6), round(mark.lon, 6)]
        out["drawn"] = [round(drawn.lat, 6), round(drawn.lon, 6)]
        out["same_place"] = out["mark"] == out["drawn"]
        # Сразу после переезда, в первом кадре, надпись видна: прежний
        # ответ о видимости держится до новой проверки.
        # Точка встаёт на высоту, которой ещё не было: у неё новая
        # строка таблицы надписей и нет ответа о видимости.
        import numpy as np
        p = window.profile_dialog.chart.profile
        seen = {int(round(float(p.height[i]))) for i in state["ph_pair"]}
        fresh = next(i for i in np.argsort(-p.height)
                     if int(round(float(p.height[i]))) not in seen)
        window.profile_dialog.chart.hovered.emit(float(fresh))
        frame = window.view.frame
        # repaint у QOpenGLWidget кадр не рисует, grabFramebuffer рисует.
        window.view.grabFramebuffer()
        key = identity(window._profile_mark)
        out["shown_right_after_move"] = key in labels.shown
        out["debug"] = {"frames": window.view.frame - frame,
                        "shown": len(labels.shown),
                        "hidden": str(labels.hidden.get(key)),
                        "in_tool_marks": window._profile_mark
                        in window.view.tool_marks,
                        "count": labels.count}
    out["row"] = row
    window.profile_dialog.close()
    window.myplaces.remove(state["ph_key"])


class _SyncPool:
    """Подмена ThreadPoolExecutor: задание выполняется сразу."""

    def __init__(self, max_workers=1):
        pass

    def submit(self, fn, *args):
        from concurrent.futures import Future
        future = Future()
        future.set_result(fn(*args))
        return future

    def shutdown(self, wait=True):
        pass


def _gap_watch(name):
    """Паузы цикла событий: таймер 5 мс пишет промежутки между
    срабатываниями. Пауза больше 50 мс - мышь заметно не отвечает."""
    from qgis.PyQt.QtCore import QTimer
    timer = QTimer()
    gaps = []
    last = [time.perf_counter()]

    def tick():
        now = time.perf_counter()
        gaps.append(now - last[0])
        last[0] = now
    timer.timeout.connect(tick)
    timer.start(5)
    state[name + "_gaps"] = (timer, gaps)


def _time_calls(name, targets):
    """Длительность вызовов методов: обёртка на экземпляре пишет
    время каждого вызова. Снимается в _calls_report."""
    found = {}
    for obj, attr in targets:
        original = getattr(obj, attr)
        times = found.setdefault(attr, [])

        def wrapped(*args, _f=original, _t=times, **kwargs):
            started = time.perf_counter()
            try:
                return _f(*args, **kwargs)
            finally:
                _t.append(time.perf_counter() - started)
        setattr(obj, attr, wrapped)
    state[name + "_calls"] = (targets, found)


def _calls_report(name):
    targets, found = state.pop(name + "_calls")
    for obj, attr in targets:
        if attr in obj.__dict__:
            delattr(obj, attr)
    out = {}
    for attr, times in found.items():
        ms = sorted(t * 1000.0 for t in times)
        out[attr] = {"calls": len(ms),
                     "max_ms": round(ms[-1], 1) if ms else None,
                     "over_50": sum(1 for t in ms if t > 50.0)}
    return out


def _gap_report(name):
    timer, gaps = state.pop(name + "_gaps")
    timer.stop()
    ms = sorted(g * 1000.0 for g in gaps)
    return {"ticks": len(ms), "max_ms": round(ms[-1], 1) if ms else None,
            "over_50": sum(1 for g in ms if g > 50.0),
            "over_100": sum(1 for g in ms if g > 100.0)}


@check(500)
def insolation_on():
    # Инсоляция у Чегета 21 декабря 2026 года, радиус 5 км, шаг 3
    # плана фазы 3.
    from qgis.PyQt.QtCore import QDate
    from planetx.core.features import Shape
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    nav = window.view.navigator
    nav.stop()
    nav.set_pose(Pose(43.2425, 42.5157, 25000.0, 0.0, 30.0))
    key = window.myplaces.add(Shape("point", [(43.2425, 42.5157)],
                                    name="Чегет"))
    state["ins_key"] = key
    if os.environ.get("PLANETX_OLD_DIALOG"):
        # Прежнее окно для сторожа: места под состояние не оставлено.
        from planetx.ui import insolation as insui
        insui.fit_status = lambda *args: None
    window._place_action("insolation", key)
    dialog = window.insolation_dialog
    result["insolation"] = {"dialog": dialog is not None
                            and dialog.isVisible()}
    dialog.first.setDate(QDate(2026, 12, 21))
    dialog.last.setDate(QDate(2026, 12, 21))
    dialog.radius.setValue(5.0)
    _gap_watch("ins")
    _time_calls("ins", [(window, "_insolation_poll"),
                        (window, "_show_insolation"),
                        (window, "_true_heights"),
                        # paintGL не оборачивается: виртуальный метод Qt
                        # после снятия обёртки больше не вызывается.
                        (window.view, "_render"),
                        (window.view, "add_gibs")])
    # Таймер связан с прежним методом, его вызовы идут мимо обёртки.
    window.insolation_timer.timeout.disconnect()
    window.insolation_timer.timeout.connect(
        lambda: window._insolation_poll())
    if os.environ.get("PLANETX_OLD_TILES"):
        # Прежнее поведение для сторожа: картинки тайлов считаются
        # в главном потоке, рабочий поток подменён синхронным.
        from planetx.ui import viewshed as vsui
        vsui.ThreadPoolExecutor = _SyncPool
    state["ins_started"] = time.monotonic()
    # Как кнопка «Построить»: даты и радиус из полей окна.
    from planetx.ui.insolation import day_start
    out = result["insolation"]
    out["start"] = day_start(dialog.first.date())
    dialog.build.emit(float(out["start"]),
                      float(day_start(dialog.last.date())),
                      dialog.radius.value() * 1000.0)


@check(10000)
def insolation_wait():
    window = state["window"]
    job = window.insolation_job
    # Камера ходит, пока рабочий поток считает: так видно, мешает ли
    # расчёт мыши.
    if job is not None and "points" in job \
            and "ins_calc_swing" not in state:
        _swing_start("ins_calc")
    if job is not None and time.monotonic() - state["ins_started"] < 60.0:
        return 100
    if "ins_calc_swing" in state:
        result["insolation"]["swing_while_computing"] = \
            _swing_report("ins_calc")
    result["insolation"]["seconds"] = round(
        time.monotonic() - state["ins_started"], 1)


@check(3500)
def insolation_check():
    import numpy as np
    window = state["window"]
    view = window.view
    out = result["insolation"]
    ins = window.insolation_result
    layer = view.gibs["insolation"]
    out["computed"] = ins is not None
    out["status"] = window.insolation_dialog.status.text()
    if ins is not None:
        out["days"] = ins.days
        out["cell"] = round(ins.cell, 1)
        out["hours_min"] = round(float(ins.hours.min()), 2)
        out["hours_median"] = round(float(np.median(ins.hours)), 2)
        out["hours_max"] = round(float(ins.hours.max()), 2)
        out["top"] = ins.top
    out["legend"] = window.insolation_legend.isVisible()
    out["gaps"] = _gap_report("ins")
    out["calls"] = _calls_report("ins")
    out["shown"] = layer.shown
    out["textures"] = len(layer.textures)
    out["gl"] = dict(view.gl_errors)
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_insolation.png"))
    # Поля окна не сжаты строкой состояния в две строки.
    dialog = window.insolation_dialog
    out["fields"] = {name: [w.height(), w.sizeHint().height()]
                     for name, w in (("first", dialog.first),
                                     ("last", dialog.last),
                                     ("radius", dialog.radius))}
    out["fields_clipped"] = any(h < hint for h, hint
                                in out["fields"].values())
    _swing_start("ins_on")


def _swing_start(name):
    """Камера ходит по долготе ±0.05° от позы, как при перетаскивании
    мышью, 3 с. Паузы цикла событий и кадры пишутся."""
    from qgis.PyQt.QtCore import QTimer
    from planetx.core.navigation import Pose
    window = state["window"]
    nav = window.view.navigator
    nav.stop()
    base = nav.pose
    started = time.perf_counter()
    timer = QTimer()

    def step():
        t = time.perf_counter() - started
        nav.set_pose(Pose(base.lat, base.lon + 0.05 * math.sin(t * 2.0),
                          base.distance, base.heading, base.tilt))
        window.view.update()
    timer.timeout.connect(step)
    timer.start(16)
    state[name + "_swing"] = (timer, base, window.view.frame)
    _gap_watch(name)


def _swing_report(name):
    window = state["window"]
    timer, base, frame = state.pop(name + "_swing")
    timer.stop()
    window.view.navigator.set_pose(base)
    out = _gap_report(name)
    out["frames"] = window.view.frame - frame
    return out


@check(3500)
def insolation_turn():
    window = state["window"]
    out = result["insolation"]
    out["swing_with_layer"] = _swing_report("ins_on")
    window.insolation_dialog.clear.emit()
    layer = window.view.gibs["insolation"]
    out["cleared"] = not layer.shown and window.insolation_tiles is None \
        and not window.insolation_legend.isVisible()
    _swing_start("ins_off")


@check(500)
def insolation_turn_check():
    window = state["window"]
    out = result["insolation"]
    out["swing_without_layer"] = _swing_report("ins_off")
    window.insolation_dialog.close()
    window.myplaces.remove(state["ins_key"])


def local_terrain():
    """PLANETX_TERRAIN_DIR - папка с тайлами высот тел вместо хранилища
    planetx-terrain, для проверки до публикации тайлов."""
    folder = os.environ.get("PLANETX_TERRAIN_DIR")
    if not folder:
        return
    from qgis.PyQt.QtCore import QUrl
    from planetx.core import planets
    for planet in (planets.MARS_PLANET, planets.MOON_PLANET):
        name, _, level, credit = planet.terrain
        url = QUrl.fromLocalFile(os.path.join(folder, planet.key)).toString()
        planet.terrain = (name, url + "/{z}/{x}/{y}.png", level, credit)
    for planet in planets.OTHER_PLANETS:
        name, _, level, credit, link = planet.imagery
        url = QUrl.fromLocalFile(os.path.join(folder, "imagery",
                                              planet.key)).toString()
        planet.imagery = (name, url + "/{z}/{x}/{y}.jpg", level, credit,
                          link)


@check(500)
def bodies_cycle():
    # Все тела меню по очереди: тайлы снимков, ошибки, снимок вида.
    from planetx.core import planets
    local_terrain()
    window = state["window"]
    view = window.view
    keys = [p.key for p in planets.OTHER_PLANETS]
    out = result.setdefault("bodies", {})
    i = state.get("body_i", 0)
    if i > 0:
        key = keys[i - 1]
        levels = sorted({k[0] for k in view.textures})
        out[key] = {"levels": levels, "errors": len(window.errors),
                    "gl": dict(view.gl_errors),
                    "attribution": window.attribution.text()[-60:]}
        view.grabFramebuffer().save(
            os.path.join(TEMP, "planetx_body_%s.png" % key))
    if i < len(keys):
        state["body_i"] = i + 1
        window.set_body(keys[i])
        return 8000
    window.set_body("earth")
    return None


@check(20000)
def mars_relief():
    # Рельеф Марса по тайлам высот: Олимп с наклоном камеры.
    from planetx.core.navigation import Pose
    local_terrain()
    window = state["window"]
    window.set_relief(True)
    window.set_body("mars")
    nav = window.view.navigator
    nav.stop()
    nav.set_pose(Pose(18.65, -133.8, 9.0e5, 20.0, 60.0))
    window.view.update()


@check(300)
def mars_relief_check():
    window = state["window"]
    view = window.view
    store = view.store
    loader = window.terrain_loader
    result["mars_relief"] = {
        "source": loader.source.url[:60] if loader else None,
        "scale": store.scale, "max_level": store.max_level,
        "tiles": sorted({k[0] for k in store.tiles}),
        "olympus_m": round(store.height_at(18.65, -133.8) / (store.scale
                                                            or 1.0)),
        "hellas_m": round(store.height_at(-42.4, 70.5) / (store.scale
                                                         or 1.0)),
        "errors": {str(k): str(v) for k, v in
                   list(window.terrain_errors.items())[:3]},
        "relief_enabled": not window.panel.geo_items["relief"].isDisabled(),
        "attribution": window.attribution.text()[-80:],
        "gl": dict(view.gl_errors)}
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_mars_relief.png"))
    window.set_body("earth")


@check(20000)
def moon_relief():
    # Рельеф Луны: кратер Коперник с низким наклоном камеры.
    from planetx.core.navigation import Pose
    local_terrain()
    window = state["window"]
    window.set_relief(True)
    window.set_body("moon")
    nav = window.view.navigator
    nav.stop()
    nav.set_pose(Pose(9.62, -20.08, 2.5e5, 0.0, 65.0))
    window.view.update()


@check(300)
def moon_relief_check():
    window = state["window"]
    view = window.view
    store = view.store
    result["moon_relief"] = {
        "tiles": sorted({k[0] for k in store.tiles}),
        # Коперник около 93 км, вал в 1.5° от центра по долготе.
        "rim_m": round(store.height_at(9.62, -20.08 + 1.5)),
        "floor_m": round(store.height_at(9.62, -20.08)),
        "errors": {str(k): str(v) for k, v in
                   list(window.terrain_errors.items())[:3]},
        "gl": dict(view.gl_errors)}
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_moon_relief.png"))
    window.set_body("earth")


SKY_SCENE = os.path.join(TEMP, "planetx_sky_scene.planetx")


@check(2000)
def sky_scene():
    # Сцена с видом неба: сохранить, выйти на Землю, открыть.
    window = state["window"]
    window.set_body("sky")
    window.show_sky(279.2, 38.8, 30.0)  # Вега
    ok = window.save_scene(SKY_SCENE)
    window.set_body("earth")
    result["sky_scene"] = {"saved": ok,
                           "left": window.view.sky_view is None}
    window.open_scene(SKY_SCENE)


@check(300)
def sky_scene_check():
    window = state["window"]
    sky = window.view.sky_view
    result["sky_scene"]["sky"] = None if sky is None else [
        round(math.degrees(sky.ra), 2), round(math.degrees(sky.dec), 2),
        round(sky.fov, 1)]
    result["sky_scene"]["menu"] = [k for k, a in
                                   window.toolbar.body_actions.items()
                                   if a.isChecked()]
    window.set_body("earth")


BODY_SCENE = os.path.join(TEMP, "planetx_body_scene.planetx")


@check(3000)
def body_scene_mars():
    state["window"].set_body("mars")


@check(3000)
def body_scene_save():
    # Сцена на Марсе с меткой, потом Земля и открытие сцены.
    from planetx.core.features import Shape
    from planetx.core.navigation import Pose
    window = state["window"]
    store = window.myplaces
    folder = store.add_folder("Сцена Марса")
    store.add(Shape("point", [(18.65, -133.8)], name="Олимп"),
              folder=folder)
    window.panel.select_place(folder)
    nav = window.view.navigator
    nav.stop()
    nav.set_pose(Pose(18.0, -134.0, 900000.0, 10.0, 30.0))
    ok = window.save_scene(BODY_SCENE)
    mars_shapes = len(window.view.features.shapes) \
        if hasattr(window.view.features, "shapes") else None
    store.remove(folder)
    window.set_body("earth")
    result["body_scene"] = {"saved": ok, "mars_shapes": mars_shapes}


@check(5000)
def body_scene_open():
    window = state["window"]
    state["body_scene_key"] = window.open_scene(BODY_SCENE)


@check(300)
def body_scene_check():
    from planetx.core import ellipsoid
    window = state["window"]
    key = state["body_scene_key"]
    places = window.myplaces.places_in(key) if key else []
    pose = window.view.navigator.pose
    result["body_scene"].update({
        "planet": window.planet.key, "a": ellipsoid.A,
        "places": [(p.name, p.body) for p in places],
        "pose": [round(pose.lat, 2), round(pose.lon, 2),
                 round(pose.distance)]})
    window.set_body("earth")
    result["body_scene"]["earth_hides_mars"] = all(
        p.body != window.planet.key for p in places)
    if key:
        window.myplaces.remove(key)


@check(300)
def ruler3d():
    # 3D-линейка: здания центра Перми, камера сверху под углом.
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    window.set_extra("buildings", True)
    view.navigator.stop()
    view.navigator.set_pose(Pose(58.0105, 56.2294, 900.0, 0.0, 45.0))
    view.update()


@check(120000)
def ruler3d_check():
    # Пиксели над зданиями: точка 3D-линейки выше рельефа под ней.
    # 3D-путь по двум крышам и земле, 3D-многоугольник по одной крыше,
    # сохранение в «Мои метки» и KML с absolute.
    import time as _time
    import numpy as np
    from planetx.core import kml
    window = state["window"]
    view = window.view
    out = {"buildings": view.buildings.drawn}
    ratio = view.devicePixelRatioF()
    w, h = view.width() * ratio, view.height() * ratio
    roofs, grounds = [], []
    started = _time.perf_counter()
    count = 0
    for j in range(8, 40):
        for i in range(4, 60):
            px, py = w * i / 64.0, h * j / 48.0
            hit = window._surface(px, py)
            ground = window._ground(px, py)
            count += 1
            if hit is None or ground is None:
                continue
            under = float(view.store.heights_at(
                np.array([hit[0]]), np.array([hit[1]]), scaled=False)[0])
            (roofs if hit[2] > under + 6.0 else grounds).append(
                (px, py, hit, hit[2] - under))
    out["pick_ms"] = round((_time.perf_counter() - started) * 1000.0
                           / max(count, 1), 1)
    out["roof_pixels"] = len(roofs)
    out["ground_pixels"] = len(grounds)
    window._open_ruler()
    window.ruler_dialog.tabs.setCurrentIndex(4)
    ruler = window.ruler
    out["mode"] = ruler.mode
    if len(roofs) >= 2 and grounds:
        a, b = roofs[0], roofs[-1]
        g = grounds[len(grounds) // 2]
        for px, py, _, _ in (a, b, g):
            window._clicked(px, py)
        values = ruler.values(rubber=False)
        xyz = ruler.space_points()
        chords = float(np.linalg.norm(xyz[1] - xyz[0])
                       + np.linalg.norm(xyz[2] - xyz[1]))
        out["path3d"] = {"points": len(ruler.points),
                         "above": [round(a[3], 1), round(b[3], 1)],
                         "length": round(values["length"], 2),
                         "chords": round(chords, 2)}
        shape = ruler.shape(rubber=False, name="3D-путь проверки")
        key = window.myplaces.add(shape, measure="проверка")
        place = window.myplaces.find(key)
        out["saved_alts"] = place is not None and place.shape.alts \
            is not None and len(place.shape.alts) == 3
        text = kml.write_kml(window.myplaces.export_tree(None))
        out["kml_absolute"] = "<altitudeMode>absolute</altitudeMode>" in text
        window.myplaces.remove(key)
    # 3D-многоугольник по одной крыше: три точки рядом с первой крышей.
    window.ruler_dialog.tabs.setCurrentIndex(5)
    out["mode5"] = ruler.mode
    if roofs:
        # Самая частая высота крыши в кадре - одна ровная крыша.
        groups = {}
        for r in roofs:
            groups.setdefault(round(r[2][2], 1), []).append(r)
        same = max(groups.values(), key=len)
        same = [same[0], same[len(same) // 2], same[-1]]
        out["roof_group"] = len(max(groups.values(), key=len))
        if len({(r[0], r[1]) for r in same}) == 3:
            for x, y, _, _ in same:
                window._clicked(x, y)
            values = ruler.values(rubber=False)
            out["polygon3d"] = {"area": round(values["area"], 1),
                                "tilt": round(values["tilt"], 2)}
    out["gl_errors"] = dict(view.gl_errors)
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_ruler3d.png"))
    window.ruler_dialog.close()
    window.set_extra("buildings", False)
    result["ruler3d"] = out


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


@check(1000)
def close_without_heights():
    # Закрытие окна на теле без загрузчика высот. Окно закрывается,
    # шаг ставится последним. На прежнем коде AttributeError в журнале.
    from planetx.core import planets
    window = state["window"]
    saved = planets.MOON_PLANET.terrain
    planets.MOON_PLANET.terrain = None
    from qgis.PyQt.QtGui import QCloseEvent
    try:
        window.set_body("moon")
        out = result["close_without_heights"] = {
            "loader": window.terrain_loader is not None, "error": ""}
        # Ошибка в начале закрытия: сигнал closed всё равно уходит,
        # иначе плагин держит ссылку на уничтоженное окно.
        got = []
        window.closed.connect(lambda: got.append(True))
        sync, window.sync = window.sync, None
        try:
            window.closeEvent(QCloseEvent())
        except AttributeError:
            got.append(False)
        window.sync = sync
        out["closed_after_error"] = got
        # closeEvent напрямую: исключение из обработчика события Qt
        # уходит в окно QGIS мимо сборщика ошибок.
        try:
            window.closeEvent(QCloseEvent())
        except AttributeError as exc:
            out["error"] = str(exc)
        # Повторное закрытие: загрузчики уже сняты, abort не падает.
        out["second_error"] = ""
        try:
            window.closeEvent(QCloseEvent())
        except TypeError as exc:
            out["second_error"] = str(exc)
        if not out["error"] and not out["second_error"]:
            window.close()
    finally:
        planets.MOON_PLANET.terrain = saved


# Выбор шагов: PLANETX_STEPS=tour_start,tour_wait. Окно открывается
# всегда. Без переменной идут все шаги.
ONLY = os.environ.get("PLANETX_STEPS")
if ONLY:
    CHECKS[:] = [c for c in CHECKS if c[0].__name__ == "open_globe"
                 or c[0].__name__ in ONLY.split(",")]
else:
    CHECKS[:] = [c for c in CHECKS if c[0].__name__ not in MANUAL]
QTimer.singleShot(3000, run)
