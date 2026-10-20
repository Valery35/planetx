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

# PLANETX_STEPS_OUT - свой файл итога, когда два проверочных QGIS идут
# одновременно.
OUT = os.environ.get("PLANETX_STEPS_OUT") or os.path.join(
    TEMP, "planetx_steps.json")
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


def save():
    """Итог на диск. Пишется после каждого шага: прогон, снятый по
    сроку, оставляет итог пройденных шагов."""
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1, default=str)


def finish():
    result["finished"] = True
    save()
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
            ValueError, OSError, ImportError, IndexError, StopIteration):
        result["errors"].append("%s: %s" % (
            function.__name__, traceback.format_exc().splitlines()[-1]))
        # Полная трассировка - для разбора, в отчёте отдельно.
        result.setdefault("traces", {})[function.__name__] = \
            traceback.format_exc()
    if again:
        # Шаг ждёт: повторяется через again мс.
        QTimer.singleShot(again, lambda: run(index))
        return
    result["last_step"] = function.__name__
    result["steps_run"] = index + 1
    try:
        save()
    except (OSError, TypeError, ValueError):
        result["errors"].append("save: " + traceback.format_exc()
                                .splitlines()[-1])
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
    from planetx.ui.guide import GUIDE_KEY
    from qgis.core import QgsSettings
    # Знакомство с модулем закрывало бы кадры шагов, его проверяет
    # свой шаг guide_tour.
    QgsSettings().setValue(GUIDE_KEY, True)
    plugin = PlanetXPlugin(iface)
    plugin.initGui()
    plugin.run()
    state["plugin"] = plugin
    state["window"] = plugin.window
    plugin.window.showNormal()
    # Строки «Слоёв» и карта витрины, оставшиеся в настройках
    # проверочного профиля от прежних шагов, выключаются: вырез разреза
    # Земли закрывал кадры рельефа шагов dem_* (замечание автора от
    # 10 октября 2026 года). Нужное шаг включает сам.
    window = plugin.window
    for key, on in list(window.extras.items()):
        if on and key not in ("stars", "air"):
            window.set_extra(key, False)
    if not window.extras.get("air", True):
        window.set_extra("air", True)
    if window.theme_key:
        window.set_theme("")



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
    dialog.line_width.setValue(4.0)
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
    import qgis.PyQt.QtWidgets as wmod  # QInputDialog окна и его частей
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
def draw_circle():
    """Вкладка «Круг» окна «Новая метка»: центр и точка окружности,
    правка точки мышью без середин, запись многоугольником."""
    import math
    window = state["window"]
    store = window.myplaces
    window._open_place()
    dialog = window.place_dialog
    dialog.tabs.setCurrentIndex(3)
    d = window.drawer
    out = {"mode": d.mode, "name": dialog.name.text(),
           "save_before": dialog.save.isEnabled()}
    d.add(58.0, 56.25)
    d.add(58.0 + 1000.0 / 111320.0, 56.25)  # 1 км к северу
    out["middles"] = len(window.draw_vertices.middles())
    out["save_after"] = dialog.save.isEnabled()
    d.move(1, 58.0 + 2000.0 / 111320.0, 56.25)
    window._save_place()
    place = [p for p in store.places if p.name == out["name"]][0]
    lat0, lon0 = 58.0, 56.25
    radii = [math.hypot((la - lat0) * 111320.0,
                        (lo - lon0) * 111320.0 * math.cos(math.radians(la)))
             for la, lo in place.shape.points]
    out.update(kind=place.kind, points=len(place.shape.points),
               radius_min=round(min(radii)), radius_max=round(max(radii)))
    out["next_name"] = dialog.name.text()
    dialog.close()
    store.remove_many([place.key]) if hasattr(store, "remove_many") \
        else None
    result["draw_circle"] = out


@check(500)
def snow_ready():
    """Суточный снег открывается на готовом дне: не позже вчерашнего
    по UTC, картинки тайлов не пустые."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    view = window.view
    view.navigator.stop()
    view.navigator.set_pose(Pose(72.0, -40.0, 6000000.0, 0.0, 0.0))
    window.set_theme("snow")
    state["snow_started"] = time.monotonic()
    result["snow_ready"] = {}


@check(500)
def snow_ready_wait():
    window = state["window"]
    layer = window.view.gibs["theme"]
    spent = time.monotonic() - state["snow_started"]
    if (not layer.textures or layer.missing or layer.pending) \
            and spent < 60.0:
        return 500
    image = window.view.grabFramebuffer()
    out = result["snow_ready"]
    out.update(day=getattr(window, "theme_day", None),
               seconds=round(spent, 1), textures=len(layer.textures),
               utc_today=time.strftime("%Y-%m-%d", time.gmtime()))
    image.save(os.path.join(TEMP, "planetx_snow_ready.png"))
    window.set_theme("")


@check(500)
def swipe_on():
    """Шторка сравнения: морской лёд над Арктикой, левая часть - год
    назад, белая линия по границе, шаг дня, выключение с темой."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    view = window.view
    view.navigator.stop()
    view.navigator.set_pose(Pose(80.0, 30.0, 6000000.0, 0.0, 0.0))
    window.set_theme("sea_ice")
    state["swipe_started"] = time.monotonic()
    state.pop("swipe_asked", None)
    result["swipe"] = {}


@check(500)
def swipe_wait():
    window = state["window"]
    view = window.view
    spent = time.monotonic() - state["swipe_started"]
    out = result["swipe"]
    if "swipe_asked" not in state:
        if "sea_ice" not in window._theme_domains and spent < 60.0:
            return 500
        out["button_shown"] = window.timebar.compare.isVisibleTo(
            window.timebar)
        window.set_compare(True)
        state["swipe_asked"] = True
        return 500
    layers = [view.gibs[name] for name in ("theme", "compare")]
    if any(not layer.textures or layer.missing or layer.pending
           for layer in layers) and spent < 90.0:
        return 500
    image = view.grabFramebuffer()
    image.save(os.path.join(TEMP, "planetx_swipe.png"))
    # Окно целиком: панели и шторка поверх вида.
    window.grab().save(os.path.join(TEMP, "planetx_swipe_window.png"))
    x = int(image.width() * view.swipe)
    white = sum(1 for y in range(image.height())
                if image.pixelColor(x, y).lightness() > 250)
    out.update(seconds=round(spent, 1), swipe=view.swipe,
               theme_day=window.theme_day,
               compare=window._compare_shown,
               bar=window.swipe_bar.isVisible(),
               left_tag=window.swipe_bar.left_day.text(),
               checked=window.timebar.compare.isChecked(),
               textures=[len(layer.textures) for layer in layers],
               white_line=white, height=image.height())
    before = window._compare_shown
    window._compare_step(-1)
    out["stepped"] = (before, window._compare_shown)
    window._swipe_moved(0.3)
    out["moved"] = view.swipe
    window.set_theme("")
    out["off"] = dict(swipe=view.swipe, bar=window.swipe_bar.isVisible(),
                      loader="compare" in window.gibs_loaders,
                      shown=view.gibs["compare"].shown,
                      at=window._compare_at)


@check(500)
def tour_panel():
    """Панель тура - строкой под шкалой времени, без шкалы - на её
    месте под панелью значков. Синие значки шагов и шторки шкалы."""
    from qgis.PyQt.QtWidgets import QApplication
    window = state["window"]
    timebar, bar = window.timebar, window.tour.bar
    window.set_body("earth")
    timebar.set_stepper(lambda moment, delta: None)
    timebar.set_compare(True, False)
    timebar.set_extent((time.time() - 86400.0, time.time()))
    timebar.open_bar()
    out_shown = timebar.shown()
    bar.show()
    bar.set_state(True, 0, 3, "Проба", "")
    bar.set_time(10.0, 60.0)
    QApplication.processEvents()
    out = {"time": [timebar.x(), timebar.y(), timebar.width(),
                    timebar.height()],
           "tour": [bar.x(), bar.y(), bar.width(), bar.height()]}
    out["time_shown"] = out_shown
    out["joined"] = bar.y() == timebar.y() + timebar.height() - 1 \
        and bar.x() == timebar.x()
    out["icons"] = [not b.icon().isNull()
                    for b in timebar.steps + [timebar.compare]]
    window.grab().save(os.path.join(TEMP, "planetx_tour_panel.png"))
    timebar.close_bar()
    QApplication.processEvents()
    out["alone"] = [bar.x(), bar.y()]
    out["alone_at_anchor"] = (bar.x(), bar.y()) == tuple(timebar.anchor())
    bar.hide()
    timebar.set_stepper(None)
    timebar.set_compare(False, False)
    result["tour_panel"] = out


@check(500)
def gallery_flip():
    """Витрина закрыта, пока грузятся превью: запросы сняты, новых нет.
    На прежнем коде закрытие запускало запросы и теряло ссылки на них,
    QGIS падал в обработчике ответа."""
    window = state["window"]
    window.set_body("earth")
    gallery = window.open_gallery()
    gallery.close()
    out = {"replies_after_close": len(gallery._replies),
           "queue_after_close": len(gallery._queue)}
    gallery = window.open_gallery()
    out["replies_after_reopen"] = len(gallery._replies)
    state["gallery_flip_started"] = time.monotonic()
    result["gallery_flip"] = out


@check(500)
def gallery_flip_wait():
    window = state["window"]
    gallery = window.gallery
    spent = time.monotonic() - state["gallery_flip_started"]
    if (gallery._queue or gallery._replies) and spent < 60.0:
        return 500
    out = result["gallery_flip"]
    out["seconds"] = round(spent, 1)
    out["left"] = len(gallery._queue) + len(gallery._replies)
    gallery.close()


@check(500)
def fires_flip():
    """Пожары включены и сразу выключены: запрос сводки снят до ответа."""
    window = state["window"]
    window.set_body("earth")
    window.set_theme("fires")
    window.set_theme("")
    result["fires_flip"] = {"pending": window.view.data_pending,
                            "reply": window._fire_reply is not None}


@check(500)
def map_close():
    """Карта витрины: значок нажат, пока карта на глобусе, крестик на
    шкале убирает карту, щелчок мимо крестика уходит виду. Ряд дат
    морского льда пришёл в шаге swipe_wait."""
    from qgis.PyQt.QtCore import QPoint, Qt
    from qgis.PyQt.QtTest import QTest
    from qgis.PyQt.QtWidgets import QAbstractButton
    window = state["window"]
    out = {}

    def click(widget, x, y):
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton,
                         Qt.KeyboardModifier.NoModifier,
                         QPoint(int(x), int(y)))

    window.set_theme("sea_ice")
    legend = window.theme_legend
    out["gallery_icon"] = hasattr(window.toolbar, "gallery")
    out["legend_shown"] = not legend.isHidden()
    click(legend, 5, legend.height() - 3)
    out["after_miss"] = window.theme_key
    rect = legend._close_rect()
    click(legend, rect.center().x(), rect.center().y())
    out["after_hit"] = window.theme_key
    window.set_theme("fires")
    fire = window.fire_legend
    rect = fire._close_rect()
    click(fire, rect.center().x(), rect.center().y())
    out["fires_after"] = window.gallery_key()
    gallery = window.open_gallery()
    out["off_button"] = any(b.text() in ("Выключить", "Turn off")
                            for b in gallery.findChildren(QAbstractButton))
    gallery.close()
    result["map_close"] = out


@check(500)
def gallery_open():
    """Витрина «Карты NASA и погода»: строка в «Слоях» и значок, группы
    «Слоёв», превью, выбор карты, температура в общем выборе."""
    window = state["window"]
    window.set_body("earth")
    window.set_theme("")
    panel = window.panel
    out = {"tops": [panel.geo.topLevelItem(i).text(0)
                    for i in range(panel.geo.topLevelItemCount())
                    if not panel.geo.topLevelItem(i).isHidden()],
           "row": panel_row(window)}
    # Кнопка «Добавить данные» открывает каталог отдельным окном, панель
    # и список «Слоёв» не меняются.
    width = window.splitter.sizes()[0]
    panel.add_data.click()
    gallery = window.gallery
    out["visible"] = gallery.isVisible()
    out["window"] = gallery.isWindow()
    out["list_visible"] = panel.geo.isVisible()
    out["items"] = len(gallery.items)
    out["panel_width"] = [width, window.splitter.sizes()[0]]
    state["gallery_started"] = time.monotonic()
    result["gallery"] = out


@check(500)
def gallery_wait():
    window = state["window"]
    gallery = window.gallery
    spent = time.monotonic() - state["gallery_started"]
    if (gallery._queue or gallery._replies) and spent < 60.0:
        return 500
    out = result["gallery"]
    out["seconds"] = round(spent, 1)
    out["thumbs"] = len(gallery.thumbs)
    out["base"] = gallery.base is not None
    snow = gallery.items["snow"][0]
    out["snow_text"] = snow.text()
    gallery._clicked(snow)
    out["chosen"] = [window.theme_key, panel_row(window)]
    from qgis.PyQt.QtCore import Qt
    out["selected"] = [k for k, (i, _, _) in gallery.items.items()
                       if i.checkState() == Qt.CheckState.Checked]
    gallery._clicked(gallery.items["temperature"][0])
    out["temperature"] = [window.theme_key,
                          bool(window.extras.get("temperature")),
                          panel_row(window)]
    gallery._clicked(gallery.items["temperature"][0])
    out["off"] = [window.gallery_key(), panel_row(window)]
    # Слои неба, недр и рельефа - флажками в витрине.
    plates_item = gallery.items["plates"][0]
    gallery._clicked(plates_item)
    out["plates_on"] = [bool(window.extras.get("plates")),
                        window.gallery_key()]
    gallery._clicked(plates_item)
    out["plates_off"] = bool(window.extras.get("plates"))
    gallery._clicked(gallery.items["slope"][0])
    gallery._clicked(gallery.items["aspect"][0])
    out["slope_aspect"] = [bool(window.extras.get("slope")),
                           bool(window.extras.get("aspect"))]
    gallery._clicked(gallery.items["aspect"][0])
    # Вкладка «Спутники»: карточки групп, щелчок включает группу и слой.
    gallery._set_group("satellites")
    out["sat_tab"] = [k for k, (it, g, kind) in gallery.items.items()
                      if not it.isHidden()]
    before = bool(window.extras.get("satellites"))
    groups = set(window.satellite_manager.groups)
    gallery._clicked(gallery.items["sat:gnss"][0])
    out["sat_groups"] = sorted(window.satellite_manager.groups)
    out["sat_layer_on"] = bool(window.extras.get("satellites"))
    gallery.grab().save(os.path.join(TEMP, "planetx_gallery_sat.png"))
    gallery._clicked(gallery.items["sat:gnss"][0])
    window.satellite_manager.set_groups(groups)
    window.set_extra("satellites", before)
    gallery._set_group("")
    out["sat_in_all"] = any(not gallery.items[k][0].isHidden()
                            for k in gallery.items if k.startswith("sat:"))
    out["bottom_button"] = hasattr(gallery, "sat_button")
    gallery._set_group("depths")
    out["depths_group"] = [k for k, (it, g, kind) in gallery.items.items()
                           if not it.isHidden()]
    gallery._set_group("fire")
    out["fire_group"] = [k for k, (it, g, kind) in gallery.items.items()
                         if not it.isHidden()]
    gallery._set_group("")
    gallery.search.setText("снег")
    out["search"] = [k for k, (it, g, kind) in gallery.items.items()
                     if not it.isHidden()]
    gallery.search.setText("")
    gallery.grab().save(os.path.join(TEMP, "planetx_gallery.png"))
    gallery.list.scrollToItem(gallery.items["aspect"][0])
    gallery.grab().save(os.path.join(TEMP, "planetx_gallery_layers.png"))
    gallery.close()
    out["closed"] = [not gallery.isVisible(), window.splitter.sizes()[0]]
    window.panel.geo.grab().save(os.path.join(TEMP, "planetx_layers.png"))


@check(500)
def gallery_bases():
    """Категория «Подоснова» каталога: все подложки с превью, щелчок
    ставит подоснову, у Google - через окно согласия."""
    from qgis.core import QgsSettings
    from planetx.ui import window as wmod
    window = state["window"]
    window.set_body("earth")
    settings = QgsSettings()
    state["bases_before"] = (settings.value(wmod.READY_KEY, []),
                             settings.value(wmod.ACCEPTED_KEY, []),
                             window.source.name)
    window.panel.add_data.click()
    gallery = window.gallery
    gallery._set_group("basemaps")
    rows = [k for k, (it, g, kind) in gallery.items.items()
            if not it.isHidden()]
    result["gallery_bases"] = {
        "rows": len(rows), "first": rows[:3],
        "in_all": any(not gallery.items[k][0].isHidden()
                      for k in rows if gallery._set_group("") is None)}
    gallery._set_group("basemaps")
    state["bases_started"] = time.monotonic()


@check(500)
def gallery_bases_wait():
    from qgis.PyQt.QtCore import Qt
    window = state["window"]
    gallery = window.gallery
    spent = time.monotonic() - state["bases_started"]
    keys = [k for k in gallery.items if k.startswith("base:")]
    waiting = [k for k in keys if k in gallery._replies
               or k in gallery._queue]
    if waiting and spent < 40.0:
        return 500
    out = result["gallery_bases"]
    out["thumbs_loaded"] = sum(1 for k in keys if k in gallery._loaded)
    checked = [k for k in keys if gallery.items[k][0].checkState()
               == Qt.CheckState.Checked]
    out["checked_before"] = checked
    gallery._clicked(gallery.items["base:esri_ocean"][0])
    out["ocean"] = [window.source.name,
                    gallery.items["base:esri_ocean"][0].checkState()
                    == Qt.CheckState.Checked]
    asked = []
    window._accept_terms = lambda name, terms: asked.append(name) or False
    gallery._clicked(gallery.items["base:google_satellite"][0])
    del window._accept_terms
    out["google_declined"] = [asked, window.source.name]
    gallery._clicked(gallery.items["base:esri_imagery"][0])
    out["back"] = window.source.name
    gallery.grab().save(os.path.join(TEMP, "planetx_gallery_bases.png"))
    gallery.close()
    settings_restore = state.pop("bases_before")
    from qgis.core import QgsSettings
    from planetx.ui import window as wmod
    settings = QgsSettings()
    for key, value in ((wmod.READY_KEY, settings_restore[0]),
                       (wmod.ACCEPTED_KEY, settings_restore[1])):
        if value:
            settings.setValue(key, value)
        else:
            settings.remove(key)
    window.sources = wmod.all_sources()
    names = [s.name for s in window.sources]
    name = settings_restore[2]
    window._panel_basemap(names.index(name) if name in names else 0)


def panel_row(window):
    """Строка карты каталога в списке «Слоёв», "" - её нет."""
    row = window.panel.active_rows.get("map")
    return row.text(0) if row is not None else ""


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
    layout = dialog.target_layout
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
    dialog.lift.setValue(400.0)
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
    window.set_layer_shown(layer.id(), True)
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


@check(500)
def share_page():
    # «Поделиться видом»: страница HTML с камерой вида и выделенной
    # папкой «Моих меток». Браузер не открывается.
    import re
    from planetx.core.features import Shape
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.view.navigator.show(Pose(58.0, 56.25, 12000.0, 20.0, 50.0))
    folder = window.myplaces.add_folder("Проба страницы")
    window.myplaces.add(Shape("line", [(58.0, 56.2), (58.01, 56.25)],
                              name="Путь страницы"), folder=folder)
    window.myplaces.add(Shape("point", [(58.0105, 56.2386)],
                              name="Эспланада"), folder=folder)
    path = os.path.join(TEMP, "planetx_share.html")
    keys = window.panel.list.selected_keys
    window.panel.list.selected_keys = lambda: [folder]
    try:
        written = window.share_view(path, show=False)
    finally:
        window.panel.list.selected_keys = keys
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    found = re.search(r'<script id="planetx-data" type="application/json">'
                      r'(.*?)</script>', text, re.S)
    data = json.loads(found.group(1)) if found else {}
    pose = window.view.navigator.pose
    result["share_page"] = {
        "written": written == path,
        "camera": data.get("camera"),
        "pose": [round(pose.lat, 3), round(pose.lon, 3),
                 round(pose.distance), round(pose.heading, 1),
                 round(pose.tilt, 1)],
        "names": [f["properties"]["name"] for f in
                  data.get("places", {}).get("features", [])],
        "stops": len((data.get("tour") or {}).get("stops", [])),
        "relief": data.get("relief"), "fov": data.get("fov"),
        "esri": "arcgis" in text.lower(),
        "message": window.status.text()}
    window.myplaces.remove(folder)


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
    window.set_layer_shown(layer.id(), True)
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
    import qgis.PyQt.QtWidgets as window_module  # QMessageBox окна
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
    # Слои проекта - свой раздел «Проект QGIS» между «Метками»
    # и «Слоями», решение автора от 17 октября 2026 года.
    from qgis.core import QgsVectorLayer
    window = state["window"]
    panel = window.panel
    layer = QgsVectorLayer("Point?crs=EPSG:4326", "Слой раздела", "memory")
    QgsProject.instance().addMapLayer(layer)
    QgsApplication.processEvents()
    places, project, base = panel.sections
    out = {"titles": [s.header.text() for s in panel.sections],
           "layer_in_own_list": any(
               row.text(0).startswith("Слой раздела")
               for row in panel.project_rows()),
           "tree_tops": panel.list.topLevelItemCount()}
    before = [s.height() for s in panel.sections]
    places.set_open(False)
    QgsApplication.processEvents()
    after = [s.height() for s in panel.sections]
    out["heights_open"] = before
    out["heights_places_closed"] = after
    out["closed_is_header"] = after[0] <= places.header.sizeHint().height()
    out["others_grew"] = sum(after[1:]) > sum(before[1:])
    out["project_rows_in_base"] = sum(
        1 for i in range(panel.geo.topLevelItemCount())
        if panel.geo.topLevelItem(i).text(0) == "Проект QGIS")
    places.set_open(True)
    QgsApplication.processEvents()
    out["reopened"] = places.height() > places.header.sizeHint().height()
    asked = []
    window.properties = None
    window._show_properties = lambda: asked.append(1)
    window.toolbar.properties_clicked.disconnect()
    window.toolbar.properties_clicked.connect(window._show_properties)
    window.toolbar.properties.click()
    out["header_buttons"] = base.row.count()
    out["properties_button"] = len(asked)
    # Подмена снимается, иначе следующие шаги полного прогона получали
    # заглушку вместо окна свойств, 10 октября 2026 года.
    del window._show_properties
    window.toolbar.properties_clicked.disconnect()
    window.toolbar.properties_clicked.connect(window._show_properties)
    flown = []
    panel.fly_to_layer.connect(lambda layer: flown.append(layer.name()))
    row = next(row for row in panel.project_rows()
               if row.text(0).startswith("Слой раздела"))
    window.view.navigator.flight = None
    panel.project_tree.itemDoubleClicked.emit(row, 0)
    out["double_click_flies"] = flown
    # Слой пустой: перелёта нет. На прежнем коде охват без объектов
    # давал перелёт в NaN, QGIS 3.36 показывал ошибку paintGL каждый
    # кадр, 12 октября 2026 года.
    out["empty_layer_no_flight"] = window.view.navigator.flight is None
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


@check(1000)
def crust_file():
    # Модель коры из архива в профиле QGIS: после первой загрузки она
    # записана туда, следующий запрос в сеть не идёт. Архив можно
    # положить вручную - вопрос пользователя Ивана от 16 октября 2026
    # года. Без архива шаг сначала ждёт загрузки из сети, до 60 с.
    window = state["window"]
    path = window._crust_path()
    if not os.path.isfile(path):
        if "crust_wait" not in state:
            state["crust_wait"] = time.monotonic()
            window.crust = None
            window.crust_error = None
            window._want_crust()
        if time.monotonic() - state["crust_wait"] < 60.0:
            return 1000
    out = {"file": os.path.isfile(path),
           "size": os.path.getsize(path) if os.path.isfile(path) else 0}
    window.crust = None
    window.crust_error = None
    window._want_crust()
    out["loaded"] = window.crust is not None
    out["network"] = window._crust_reply is not None
    out["vp"] = window.crust is not None and window.crust.vp is not None
    result["crust_file"] = out


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
    both = ctrl | shift
    _send_mouse(view, "MouseButtonPress", cx, cy, left, left, both)
    _send_mouse(view, "MouseMove", cx + 50, cy - 20, none, left, both)
    _send_mouse(view, "MouseButtonRelease", cx + 50, cy - 20, left, none,
                both)
    eye1, _ = nav.pose.eye_rotation()
    out["ctrl_look"] = {"heading": round(nav.pose.heading, 3),
                        "tilt": round(nav.pose.tilt, 3),
                        "eye_moved_m": round(float(
                            ((eye1 - eye0) ** 2).sum() ** 0.5), 3)}
    # Ctrl с левой кнопкой - сдвиг вида параллельно экрану: оси камеры
    # прежние, точка взгляда идёт за курсором. Вид разреза издалека.
    nav.stop()
    nav.set_pose(Pose(20.0, 175.0, 1.5e7, 330.0, 25.0))
    view._fit_camera()
    nav.pose.apply(view.camera)
    eye0, rot0 = nav.pose.eye_rotation()
    target, _ = Pose(20.0, 175.0, 0.0).eye_rotation()
    _send_mouse(view, "MouseButtonPress", cx, cy, left, left, ctrl)
    _send_mouse(view, "MouseMove", cx + 60, cy - 40, none, left, ctrl)
    _send_mouse(view, "MouseMove", cx + 120, cy - 80, none, left, ctrl)
    _send_mouse(view, "MouseButtonRelease", cx + 120, cy - 80, left, none,
                ctrl)
    view._fit_camera()
    nav.pose.apply(view.camera)
    eye1, rot1 = nav.pose.eye_rotation()
    from planetx.core.navigation import pixel_at
    seen = pixel_at(view.camera, eye1, rot1, target)
    out["ctrl_shift"] = {
        "axes_change": float(abs(rot1 - rot0).max()),
        "along_view_m": round(float((eye1 - eye0) @ rot0[:, 2]), 3),
        "target_px": None if seen is None else
        [round(float(seen[0]) / ratio - cx, 2),
         round(float(seen[1]) / ratio - cy, 2)],
        "roll": round(nav.pose.roll, 3)}
    view.setFocus()
    _send_key(view, "Key_R")
    flight = nav.flight[1] if nav.flight else None
    out["key_r_after_shift_roll"] = None if flight is None else \
        flight.end.roll
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
    out["slider_height"] = dialog.lift.value()
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
    dialog.lift.setValue(3600.0)
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
    import qgis.PyQt.QtWidgets as wmod  # QInputDialog окна и его частей
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
    import qgis.PyQt.QtWidgets as wmod  # QInputDialog окна и его частей
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
    # Без разреза Земли все кружки в эпицентрах на поверхности.
    out["deep_without_cutaway"] = int(view.quakes.deep().sum())
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
                first = body["messages"][0]["content"]
                if isinstance(first, str) and "течения" in first:
                    answer = self.actions(len(body["messages"]))
                elif isinstance(last, str):
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

        def actions(self, count):
            """Круги разговора о слоях: список действий, потом течения,
            горизонтали, непрозрачность и окно снимков, потом текст."""
            if count == 1:
                return {"content": [{"type": "tool_use", "id": "a1",
                                     "name": "list_actions", "input": {}}]}
            if count == 3:
                calls = (("run_action", {"key": "layer:currents"}),
                         ("run_action", {"key": "layer:contours"}),
                         ("set_opacity", {"key": "currents",
                                          "value": 0.4}),
                         ("run_action", {"key": "here:sentinel"}),
                         ("run_action", {"key": "tool:record"}))
                return {"content": [
                    {"type": "tool_use", "id": "b%d" % n, "name": name,
                     "input": args}
                    for n, (name, args) in enumerate(calls)]}
            return {"content": [{"type": "text", "text": "Включил."}]}

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


@check(4000)
def assistant_actions():
    # Помощник включает слои и открывает окна действиями строки
    # «Поиск» (list_actions, run_action) и меняет непрозрачность.
    from planetx.core import assistant as ai
    from planetx.ui import assistant as ui_ai
    window = state["window"]
    window.set_body("earth")
    for key in ("currents", "contours"):
        window.set_extra(key, False)
    server, seen = _fake_model()
    state["fake_actions"] = (server, seen)
    state.setdefault("real_load_key", ui_ai.load_key)
    ui_ai.load_key = lambda provider: "test-key"
    window.open_assistant()
    dialog = window.assistant_dialog
    _use_service(dialog, ai.ANTHROPIC,
                 "http://127.0.0.1:%d" % server.server_port)
    dialog.input.setText("Покажи течения и включи горизонтали")
    dialog.send()


@check(1000)
def assistant_actions_check():
    from planetx.ui import assistant as ui_ai
    window = state["window"]
    server, seen = state["fake_actions"]
    out = result.setdefault("assistant_actions", {})
    out["requests"] = len(seen)
    listed = seen[1][1]["messages"][-1]["content"][0]["content"] \
        if len(seen) > 1 else ""
    out["list_has_currents"] = "layer:currents" in listed
    out["list_has_record"] = "tool:record" in listed
    out["results"] = [r["content"] for r in
                      seen[2][1]["messages"][-1]["content"]] \
        if len(seen) > 2 else None
    out["currents_on"] = bool(window.extras.get("currents"))
    out["contours_on"] = bool(window.extras.get("contours"))
    out["currents_opacity"] = round(window._layer_opacity("currents"), 2)
    sentinel = getattr(window, "sentinel_dialog", None)
    out["sentinel_shown"] = sentinel is not None and sentinel.isVisible()
    out["recording"] = window.toolbar.record.isChecked()
    window._active_opacity("currents", 1.0)
    for key in ("currents", "contours"):
        window.set_extra(key, False)
    if sentinel is not None:
        sentinel.close()
    window.assistant_dialog.close()
    server.shutdown()
    ui_ai.load_key = state["real_load_key"]
    out["gl"] = dict(window.view.gl_errors)


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


REFRESH_SECONDS = float(os.environ.get("PLANETX_REFRESH_SECONDS", "120"))


@check(500)
def refresh_stress():
    """Зависание проверочного QGIS 10 октября 2026 года: главный поток
    больше 10 с стоял в LayerOverlay.abort при пересборке наложения,
    пока прежнее грузило тайлы, сразу после открытия окна. Шаг каждые
    300 мс переносит камеру в новое место и зовёт refresh."""
    import random
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    state["refresh_rnd"] = random.Random(int(time.time()))
    state["refresh_started"] = time.monotonic()
    result["refresh_stress"] = {"rounds": 0, "max_ms": 0.0}


@check(300)
def refresh_stress_run():
    from planetx.core.navigation import Pose
    window = state["window"]
    out = result["refresh_stress"]
    rnd = state["refresh_rnd"]
    if time.monotonic() - state["refresh_started"] > REFRESH_SECONDS:
        return None
    window.view.navigator.show(Pose(rnd.uniform(-50.0, 65.0),
                                    rnd.uniform(-170.0, 170.0),
                                    rnd.uniform(20000.0, 3000000.0),
                                    rnd.uniform(0.0, 360.0),
                                    rnd.uniform(0.0, 50.0)))
    started = time.perf_counter()
    window.refresh()
    out["max_ms"] = round(max(out["max_ms"],
                              (time.perf_counter() - started) * 1000.0), 1)
    out["rounds"] += 1
    with open(os.path.join(TEMP, "planetx_refresh_progress.txt"), "w") as fh:
        fh.write("{} {}\n".format(out["rounds"], out["max_ms"]))
    return 300


GALLERY_SECONDS = float(os.environ.get("PLANETX_GALLERY_SECONDS", "240"))
GALLERY_PERIOD = 1500  # мс между переключениями карт витрины
GALLERY_EXTRAS = ("clouds", "plates", "quakes", "slope", "contours")


@check(1000)
def gallery_stress():
    """Зависания рабочего компьютера 9 октября 2026 года - при
    переключении карт витрины. Шаг переключает темы GIBS, поля погоды,
    слои витрины и подложку, двигает камеру и меряет паузы главного
    потока таймером 50 мс и длительность каждого
    QgsNetworkAccessManager.get()."""
    import random
    from qgis.core import QgsNetworkAccessManager
    from qgis.PyQt.QtCore import QTimer
    from planetx.core import themes
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    seed = int(time.time())
    out = result["gallery_stress"] = {"seed": seed, "switches": 0,
                                      "gets": 0, "max_get_ms": 0.0,
                                      "gets_over_100ms": 0,
                                      "slow_gets": [], "gaps": []}
    state["gallery_rnd"] = random.Random(seed)
    state["gallery_started"] = time.monotonic()
    state["gallery_keys"] = [t.key for t in themes.THEMES]
    manager = QgsNetworkAccessManager.instance()
    small = os.environ.get("PLANETX_GALLERY_CACHE_MB")
    if small:
        # Свой маленький кэш в отдельной папке: чистка идёт всё время,
        # общий кэш QGIS пользователя не трогается.
        from qgis.core import QgsSettings
        settings = QgsSettings()
        state["gallery_cache"] = (settings.value("cache/directory", ""),
                                  settings.value("cache/size-bytes", 0))
        folder = os.path.join(TEMP, "planetx_cache_small")
        settings.setValue("cache/directory", folder)
        settings.setValue("cache/size-bytes", int(small) * 1024 * 1024)
        manager.setupDefaultProxyAndCache()
        out["cache"] = [folder, int(small)]
    original = manager.get

    def timed(request):
        started = time.perf_counter()
        reply = original(request)
        spent = (time.perf_counter() - started) * 1000.0
        out["gets"] += 1
        out["max_get_ms"] = round(max(out["max_get_ms"], spent), 1)
        if spent > 100.0:
            out["gets_over_100ms"] += 1
            if len(out["slow_gets"]) < 20:
                out["slow_gets"].append(
                    [round(spent), request.url().host(),
                     round(time.monotonic() - state["gallery_started"], 1)])
        return reply
    manager.get = timed
    state["gallery_get"] = (manager, original)
    beat = {"last": time.monotonic(), "max": 0.0}

    def tick():
        now = time.monotonic()
        gap = now - beat["last"]
        beat["last"] = now
        beat["max"] = max(beat["max"], gap)
        if gap > 0.5 and len(out["gaps"]) < 40:
            out["gaps"].append([round(gap, 2), round(
                now - state["gallery_started"], 1)])
    timer = QTimer()
    timer.timeout.connect(tick)
    timer.start(50)
    state["gallery_timer"] = (timer, beat)
    window.view.navigator.stop()
    window.view.navigator.show(Pose(55.0, 40.0, 3000000.0, 0.0, 0.0))


@check(GALLERY_PERIOD)
def gallery_stress_run():
    from planetx.core.navigation import Pose
    window = state["window"]
    out = result["gallery_stress"]
    rnd = state["gallery_rnd"]
    now = time.monotonic()
    if now - state["gallery_started"] < GALLERY_SECONDS:
        choice = rnd.random()
        if choice < 0.55:
            window.set_theme(rnd.choice(state["gallery_keys"]))
        elif choice < 0.8:
            key = rnd.choice(GALLERY_EXTRAS)
            window.set_extra(key, not window.extras.get(key, False))
        elif choice < 0.9 and len(window.sources) > 1:
            window._switch_basemap(rnd.choice(window.sources))
        else:
            window.set_theme("")
        out["switches"] += 1
        lat = rnd.uniform(-50.0, 65.0)
        lon = rnd.uniform(-170.0, 170.0)
        window.view.navigator.show(Pose(
            lat, lon, rnd.uniform(300000.0, 6000000.0),
            rnd.uniform(0.0, 360.0), rnd.uniform(0.0, 40.0)))
        return GALLERY_PERIOD
    timer, beat = state.pop("gallery_timer")
    timer.stop()
    manager, original = state.pop("gallery_get")
    del manager.get
    if "gallery_cache" in state:
        from qgis.core import QgsSettings
        folder = out["cache"][0]
        out["cache_files"] = sum(len(f) for _, _, f in os.walk(folder))
        out["cache_mb"] = round(sum(
            os.path.getsize(os.path.join(d, n)) for d, _, f in
            os.walk(folder) for n in f) / 1e6, 1)
        directory, size = state.pop("gallery_cache")
        settings = QgsSettings()
        settings.setValue("cache/directory", directory)
        settings.setValue("cache/size-bytes", size)
        manager.setupDefaultProxyAndCache()
    out["max_gap_s"] = round(beat["max"], 2)
    out["gl"] = dict(window.view.gl_errors)
    out["seconds"] = round(now - state["gallery_started"], 1)
    window.set_theme("")
    for key in GALLERY_EXTRAS:
        window.set_extra(key, False)


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


@check(300)
def search_focus():
    # Подсказки строки «Поиск» прячутся, когда фокус уходит на глобус,
    # и остаются при переходе в свой список.
    from planetx.core.features import Shape
    window = state["window"]
    panel = window.panel
    window.set_body("earth")
    window.set_sidebar(True)
    window.activateWindow()
    window.raise_()
    state["focus_key"] = window.myplaces.add(
        Shape("point", [(58.0, 56.2)], name="Проба фокуса Вокзал"))
    out = result["search_focus"] = {}
    window.place.setFocus()
    window.place.setText("проба фокуса")
    window.place.textEdited.emit("проба фокуса")
    out["rows"] = panel.hints.count()
    out["place_focus"] = window.place.hasFocus()
    panel.hints.setFocus()


@check(300)
def search_focus_list():
    window = state["window"]
    panel = window.panel
    out = result.setdefault("search_focus", {})
    # В списке подсказок - список виден.
    out["after_list"] = [panel.hints.hasFocus(), not panel.hints.isHidden()]
    window.view.setFocus()


@check(300)
def search_focus_check():
    window = state["window"]
    panel = window.panel
    out = result.setdefault("search_focus", {})
    out["after_globe"] = [window.view.hasFocus(), not panel.hints.isHidden()]
    key = state.pop("focus_key", None)
    if key:
        window.myplaces.remove(key)
    window.place.setText("")
    panel.hide_hints()


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
    geo.scrollToItem(window.panel.active_rows.get("map")
                     or geo.topLevelItem(0))
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
    # Строка витрины в «Слоях» называет карту на глобусе.
    panel = window.panel
    out["row_on"] = panel_row(window)
    window.set_theme("")
    out["bar_after_off"] = window.timebar.track.point
    window.myplaces.set_visible_many(state.pop("timed_places", {}))
    out["row_off"] = panel_row(window)
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


@check(200)
def overlays_box_close():
    # Окно рамки картинки закрыто в overlays_add, Qt его удалил. До
    # 9 октября 2026 года ручки рамки (BoxVertices) оставались на виде
    # и падали на удалённом окне в sync и paintEvent, QGIS 3.40.15.
    # Ошибки слотов и событий идут в sys.excepthook.
    window = state["window"]
    tool = window.handles.tool
    caught = []
    hook = sys.excepthook
    sys.excepthook = lambda kind, value, tb: caught.append(repr(value))
    try:
        try:
            window.handles.sync()
            window.handles.grab()
        except RuntimeError as error:
            caught.append(repr(error))
    finally:
        sys.excepthook = hook
    result["overlays"]["box_close"] = {
        "tool": type(tool).__name__,
        "dialog_tool": hasattr(tool, "dialog"),
        "errors": caught}


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


@check(1000)
def deposits_on():
    """Месторождения USGS: первое включение качает архивы (около 25 МБ),
    разбор в потоке, файл профиля. Вид - Невада, где точек MRDS много."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.view.navigator.show(Pose(40.9, -116.3, 400000.0, 0.0, 0.0))
    state["dep_start"] = time.monotonic()
    window.set_extra("deposits", True)
    result["deposits"] = {}


@check(1000)
def deposits_wait():
    window = state["window"]
    spent = time.monotonic() - state["dep_start"]
    if window.deposit_data is None and spent < 300.0:
        return 1000
    out = result["deposits"]
    out["load_seconds"] = round(spent, 1)
    data = window.deposit_data
    out["records"] = len(data) if data is not None else 0
    out["major"] = int(data.major.sum()) if data is not None else 0
    out["message"] = (getattr(window, "message", None) or ("",))[0]
    return None


@check(1500)
def deposits_check():
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    out = result["deposits"]
    frames = []
    for _ in range(5):
        started = time.monotonic()
        image = view.grabFramebuffer()
        frames.append(round((time.monotonic() - started) * 1000.0, 1))
    image.save(os.path.join(TEMP, "planetx_deposits.png"))
    out["drawn_nevada"] = view.deposits.drawn
    out["frame_ms"] = frames
    out["legend"] = window.deposit_legend.isVisible()
    window.deposit_legend.grab().save(os.path.join(
        TEMP, "planetx_deposit_legend.png"))
    window.grab().save(os.path.join(TEMP, "planetx_deposits_window.png"))
    out["credit"] = "USGS MRDS" in window.attribution.text()
    ratio = view.devicePixelRatioF()
    px, py = view.width() * ratio / 2.0, view.height() * ratio / 2.0
    found = window._identify_deposits(px, py)
    out["identify"] = [(f[0], dict(f[1]).get("Полезные ископаемые",
                                              dict(f[1]).get("Commodities")))
                       for _, features in found for f in features][:3]
    data = view.deposits.data
    out["sets"] = {"major": int(data.major.sum()),
                   "facility": int(data.facility.sum()), "all": len(data)}
    # Североуральск - рудник бокситов набора minfac, щелчок без режима
    # опроса открывает окно «Объекты».
    view.navigator.show(Pose(60.15, 59.96, 60000.0, 0.0, 0.0))
    state["deposits_world_pose"] = Pose(30.0, 60.0, 1.8e7, 0.0, 0.0)


@check(1500)
def deposits_click():
    import numpy as np
    window = state["window"]
    view = window.view
    out = result["deposits"]
    window.identifying = False
    # Точка рудника - как её рисует вид (на рельефе), по записи набора.
    layer = view.deposits
    data = layer.data
    record = next(n for n in range(len(data))
                  if data.text(n)[0].startswith("Severoural"))
    spot = int(np.nonzero(layer.order == record)[0][0])
    pixels, front = view.camera.project(layer.focus[spot:spot + 1])
    px, py = float(pixels[0][0]), float(pixels[0][1])
    found = window._identify_deposits(px, py)
    out["click_debug"] = {
        "pixel": [round(px), round(py)], "front": bool(front[0]),
        "camera": [view.camera.width, view.camera.height],
        "found": [f[0] for _, fs in found for f in fs][:5],
        "under": window._point_under(px, py),
        "pose": [round(view.navigator.pose.lat, 3),
                 round(view.navigator.pose.lon, 3),
                 round(view.navigator.pose.distance)]}
    window._clicked(px, py)
    dialog = window.identified
    text = ""
    if dialog is not None and dialog.isVisible():
        parts = []

        def walk(item):
            parts.append(item.text(0) + " " + item.text(1))
            for k in range(item.childCount()):
                walk(item.child(k))
        for k in range(dialog.tree.topLevelItemCount()):
            walk(dialog.tree.topLevelItem(k))
        text = " | ".join(parts)
    out["click_without_mode"] = {"shown": dialog is not None
                                 and dialog.isVisible(),
                                 "severouralsk": "Severoural" in text,
                                 "text": text[:300]}
    if dialog is not None:
        dialog.close()
    view.navigator.show(state["deposits_world_pose"])
    view.update()


def _mirror_failures():
    """Отказы зеркал Overpass - выключение строки отказом не считается."""
    from planetx.ui.overpass import MIRRORS
    return sum(m.failures for m in MIRRORS.mirrors)


@check(1000)
def mining_on():
    """Горные разработки и шахты OSM над Березниками: контуры Maus 2022
    (файл 25 МБ в профиль) и тайлы Overpass по виду."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.view.navigator.show(Pose(59.45, 56.80, 40000.0, 0.0, 0.0))
    state["mining_started"] = time.monotonic()
    window.set_extra("mining", True)
    window.set_extra("osm_mines", True)
    # Выключение посреди запроса - не отказ сервера: сервер прежний.
    window.set_extra("osm_mines", False)
    window.set_extra("osm_mines", True)
    state["osm_server_after_toggle"] = _mirror_failures()
    result["mining"] = {"gallery": [k for k, _ in
                                    __import__("planetx.ui.nasamaps",
                                               fromlist=["LAYERS"]).LAYERS
                                    if k in ("mining", "osm_mines")]}


@check(2000)
def mining_wait():
    window = state["window"]
    started = state["mining_started"]
    waiting = window._mining_reply is not None \
        or window.osm_mines_tiles.reply is not None \
        or bool(window.osm_mines_tiles.queue) \
        or window.view.data_pending or (window.overlay is not None
                                        and window.overlay.busy())
    if waiting and time.monotonic() - started < 120.0:
        return 2000
    result["mining"]["load_s"] = round(time.monotonic() - started, 1)


@check(1500)
def mining_check():
    from qgis.core import QgsRectangle
    window = state["window"]
    view = window.view
    out = result["mining"]
    layer = window.mining_layer
    out["layer"] = layer is not None and layer.featureCount()
    out["in_overlay"] = layer is not None and window.overlay is not None \
        and any(la is layer for la in window.overlay.layers)
    out["osm_tiles"] = len(window.osm_mines_tiles.items)
    out["osm_points"] = 0 if view.osm_mines.data is None \
        else len(view.osm_mines.data)
    names = [] if view.osm_mines.data is None else [
        view.osm_mines.data.text(n)[0]
        for n in range(len(view.osm_mines.data))]
    out["osm_named"] = [n for n in names if n][:6]
    # Контур под щелчком - середина ближайшего к виду контура.
    found = []
    if layer is not None:
        box = QgsRectangle(56.5, 59.2, 57.1, 59.7)
        request = __import__("qgis.core", fromlist=["QgsFeatureRequest"]) \
            .QgsFeatureRequest().setFilterRect(box)
        for feature in layer.getFeatures(request):
            point = feature.geometry().pointOnSurface().asPoint()
            found = window._identify_mining(point.y(), point.x())
            break
    out["polygon_click"] = [f[0] for _, fs in found for f in fs][:2]
    out["polygon_values"] = [dict(f[1]) for _, fs in found for f in fs][:1]
    # Точка OSM - щелчок без режима опроса.
    window.identifying = False
    clicked = None
    if view.osm_mines.data is not None and len(view.osm_mines.data):
        seen = view.osm_mines.visible(view.camera.eye)
        if len(seen):
            pixels, front = view.camera.project(view.osm_mines.focus[seen[:1]])
            px, py = float(pixels[0][0]), float(pixels[0][1])
            clicked = window._point_under(px, py)
    out["osm_click"] = clicked
    out["server_after_toggle"] = state["osm_server_after_toggle"]
    # Длинное слово в строке состояния не раздвигает панель.
    from qgis.PyQt.QtWidgets import QApplication
    before = window.panel.width()
    saved = window.message
    window.message = ("x" * 600, time.monotonic())
    window._show_state()
    QApplication.processEvents()
    out["panel_width"] = [before, window.panel.width()]
    window.message = saved
    window._show_state()
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_mining.png"))
    # Подпись на карте короткая, без меток вида «Mines:».
    out["credit"] = "Maus" in window.attribution.text() \
        and "OpenStreetMap" in window.attribution.text()
    window.set_extra("mining", False)
    window.set_extra("osm_mines", False)
    out["after_off"] = view.osm_mines.data is None and (
        window.overlay is None
        or not any(la is layer for la in window.overlay.layers))


@check(1000)
def deposits_world():
    window = state["window"]
    view = window.view
    out = result["deposits"]
    started = time.monotonic()
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_deposits_world.png"))
    out["world_frame_ms"] = round((time.monotonic() - started) * 1000.0, 1)
    out["drawn_world"] = view.deposits.drawn
    window.set_extra("deposits", False)
    out["after_off"] = view.deposits.data is None


def _click_text(window):
    """Текст окна «Объекты» после щелчка, окно закрывается."""
    dialog = window.identified
    if dialog is None or not dialog.isVisible():
        return None
    parts = []

    def walk(item):
        parts.append(item.text(0) + " " + item.text(1))
        for k in range(item.childCount()):
            walk(item.child(k))
    for k in range(dialog.tree.topLevelItemCount()):
        walk(dialog.tree.topLevelItem(k))
    dialog.close()
    return " | ".join(parts)


@check(1000)
def infra_on():
    """Электростанции WRI и ЛЭП OSM над Березниками с 40 км."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.view.navigator.show(Pose(59.45, 56.80, 40000.0, 0.0, 0.0))
    state["infra_started"] = time.monotonic()
    window.set_extra("plants", True)
    window.set_extra("infra_osm", True)
    # Выключение посреди запроса - не отказ сервера.
    window.set_extra("infra_osm", False)
    window.set_extra("infra_osm", True)
    state["infra_server_after_toggle"] = _mirror_failures()
    from planetx.ui import nasamaps
    # ЛЭП - строка «Карты» раздела «Слои», в витрине только станции.
    result["infra"] = {"gallery": [k for k, _ in nasamaps.LAYERS
                                   if k in ("plants", "infra_osm")],
                       "map_row": "infra_osm" in window.panel.extra_items}


@check(2000)
def infra_wait():
    window = state["window"]
    started = state["infra_started"]
    waiting = window._plant_reply is not None \
        or window._plant_job is not None \
        or window.infra_tiles.reply is not None \
        or bool(window.infra_tiles.queue) or window.view.data_pending \
        or (window.overlay is not None and window.overlay.busy())
    if waiting and time.monotonic() - started < 150.0:
        return 2000
    result["infra"]["load_s"] = round(time.monotonic() - started, 1)


@check(1500)
def infra_active():
    """Раздел «На глобусе»: строки включённого, ползунок непрозрачности
    точек и слоя QGIS, «В проект QGIS» для станций и ЛЭП."""
    from qgis.core import QgsProject
    from qgis.PyQt.QtWidgets import QApplication
    window = state["window"]
    view = window.view
    panel = window.panel
    # Строки включённого - в одну линию, без виджетов, решение автора
    # от 12 октября 2026 года. Непрозрачность - в меню «⋯» строки.
    heights = {key: panel.geo.visualItemRect(item).height()
               for key, item in panel.active_rows.items()}
    out = {"rows": list(panel.active_rows),
           "widgets": sum(panel.geo.itemWidget(item, 0) is not None
                          for item in panel.active_rows.values()),
           "heights": sorted(set(heights.values())),
           "menu": {key: panel._active_values.get(key)
                    for key in ("plants", "infra_osm")}}
    panel.grab().save(os.path.join(TEMP, "planetx_active_panel.png"))
    panel.active_opacity.emit("plants", 0.4)
    out["plants_opacity"] = round(view.plants.opacity, 2)
    panel.active_opacity.emit("infra_osm", 0.5)
    QApplication.processEvents()
    out["infra_opacity"] = round(window.infra_lines.opacity(), 2) \
        if window.infra_lines is not None else None
    panel.active_opacity.emit("plants", 1.0)
    panel.active_opacity.emit("infra_osm", 1.0)
    folder = os.path.join(TEMP, "planetx_active")
    os.makedirs(folder, exist_ok=True)
    counts = {}
    for key in ("plants", "infra_osm"):
        path = os.path.join(folder, key + ".gpkg")
        if os.path.exists(path):
            os.remove(path)
        counts[key] = window.active_export(key, path)
    out["exported"] = counts
    root = QgsProject.instance().layerTreeRoot()
    group = root.findGroup("PlanetX - слои глобуса") \
        or root.findGroup("PlanetX - globe layers")
    out["group"] = [] if group is None else [
        (node.name(), node.layer().featureCount())
        for node in group.findLayers()]
    if group is not None:
        for node in group.findLayers():
            QgsProject.instance().removeMapLayer(node.layerId())
        root.removeChildNode(group)
    # Снятие флажка строки убирает слой.
    panel.set_active_checked("plants", False)
    QApplication.processEvents()
    QApplication.processEvents()
    # Снятый флажок выключает слой, строка остаётся до «Убрать».
    out["plants_off"] = not window.extras.get("plants") \
        and "plants" in panel.active_rows \
        and not panel.active_checked("plants")
    panel.set_active_checked("plants", True)
    QApplication.processEvents()
    QApplication.processEvents()
    out["plants_back"] = bool(window.extras.get("plants"))
    window._active_off("plants")
    out["plants_removed"] = "plants" not in panel.active_rows
    window.set_extra("plants", True)
    result["infra"]["active"] = out


@check(1500)
def infra_check():
    window = state["window"]
    view = window.view
    out = result["infra"]
    out["plants"] = 0 if window.plant_data is None \
        else len(window.plant_data)
    out["plants_drawn"] = view.plants.drawn
    lines = window.infra_lines
    out["lines"] = 0 if lines is None else lines.featureCount()
    out["substations"] = 0 if window.infra_points is None \
        else window.infra_points.featureCount()
    out["styles"] = {} if lines is None else {
        s: sum(1 for f in lines.getFeatures() if f["style"] == s)
        for s in ("v500", "v220", "v110", "v35", "cable", "telecom",
                  "gas", "oil", "water", "other")}
    out["in_overlay"] = lines is not None and window.overlay is not None \
        and any(la is lines for la in window.overlay.layers)
    out["legends"] = [window.plant_legend.isVisible(),
                      window.infra_legend.isVisible()]
    out["server_after_toggle"] = state["infra_server_after_toggle"]
    window.identifying = False
    # Электростанция - щелчок без режима опроса по ближайшей к середине.
    clicked = None
    data = view.plants.data
    if data is not None:
        seen = view.plants.visible(view.camera.eye)
        if len(seen):
            pixels, front = view.camera.project(view.plants.focus[seen])
            middle = (view.camera.width / 2.0, view.camera.height / 2.0)
            gap = ((pixels[:, 0] - middle[0]) ** 2
                   + (pixels[:, 1] - middle[1]) ** 2)
            gap[~front] = 1e18
            n = int(gap.argmin())
            px, py = float(pixels[n][0]), float(pixels[n][1])
            clicked = window._point_under(px, py)
            window._clicked(px, py)
    out["plant_click"] = clicked
    out["plant_text"] = (_click_text(window) or "")[:300]
    # Линия - середина отрезка самой мощной линии в кадре.
    feature = None
    if lines is not None:
        for style in ("v500", "v220", "v110", "v35", "gas", "oil"):
            feature = next((f for f in lines.getFeatures()
                            if f["style"] == style), None)
            if feature is not None:
                break
    if feature is not None:
        from planetx.core.ellipsoid import geodetic_to_ecef
        import numpy as np
        vertices = feature.geometry().asPolyline()
        a, b = vertices[len(vertices) // 2 - 1], vertices[len(vertices) // 2]
        lat, lon = (a.y() + b.y()) / 2.0, (a.x() + b.x()) / 2.0
        from planetx.core.navigation import Pose
        view.navigator.show(Pose(lat, lon, 3000.0, 0.0, 0.0))
        view.repaint()
        pixels, front = view.camera.project(np.array([geodetic_to_ecef(
            lat, lon, view.store.height_at(lat, lon) * view.store.scale)]))
        px, py = float(pixels[0][0]), float(pixels[0][1])
        out["line_under"] = bool(window._point_under(px, py))
        window._clicked(px, py)
        out["line_text"] = (_click_text(window) or "")[:300]
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_infra.png"))
    text = window.attribution.text()
    out["credit"] = "WRI" in text and "OpenStreetMap" in text
    window.set_extra("plants", False)
    window.set_extra("infra_osm", False)
    out["after_off"] = view.plants.data is None and (
        window.overlay is None
        or not any(la is lines for la in window.overlay.layers)) \
        and not window.plant_legend.isVisible() \
        and not window.infra_legend.isVisible()


@check(3000)
def cables_on():
    """Подводные кабели над Северной Атлантикой с 6000 км."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.view.navigator.show(Pose(50.0, -30.0, 6000000.0, 0.0, 0.0))
    window.set_extra("cables", True)
    result["cables"] = {"map_row": "cables" in window.panel.extra_items}


@check(1500)
def cables_check():
    import os as _os
    from qgis.core import QgsProject
    window = state["window"]
    out = result["cables"]
    layer = window.cable_layer
    out["features"] = 0 if layer is None else layer.featureCount()
    out["in_overlay"] = layer is not None and window.overlay is not None \
        and any(la is layer for la in window.overlay.layers)
    data = window.cables_data
    cable = next(c for c in data.cables if c.name == "TAT13")
    n = len(cable.lats) // 2
    lat = (cable.lats[n - 1] + cable.lats[n]) / 2.0
    lon = (cable.lons[n - 1] + cable.lons[n]) / 2.0
    found = window._identify_cables(lat, lon, 30000.0)
    out["identify"] = [f[0] for _, fs in found for f in fs]
    out["row"] = "cables" in window.panel.active_rows
    out["credit"] = "OpenStreetMap" in window.attribution.text()
    window.view.grabFramebuffer().save(_os.path.join(TEMP,
                                                     "planetx_cables.png"))
    path = _os.path.join(TEMP, "planetx_active", "cables.gpkg")
    _os.makedirs(_os.path.dirname(path), exist_ok=True)
    if _os.path.exists(path):
        _os.remove(path)
    out["exported"] = window.active_export("cables", path)
    root = QgsProject.instance().layerTreeRoot()
    group = root.findGroup("PlanetX - слои глобуса") \
        or root.findGroup("PlanetX - globe layers")
    if group is not None:
        for node in group.findLayers():
            QgsProject.instance().removeMapLayer(node.layerId())
        root.removeChildNode(group)
    window.set_extra("cables", False)
    out["after_off"] = window.overlay is None or not any(
        la is layer for la in window.overlay.layers)


TILE_OVERLAYS = ("hiking", "cycling", "sea_marks")


@check(1000)
def tile_overlays_on():
    """Наложения тайлов в Альпах у Церматта с 40 км: пешие
    и велосипедные маршруты и морские знаки сразу."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.view.navigator.show(Pose(46.02, 7.75, 40000.0, 0.0, 0.0))
    window.view.update()
    for key in TILE_OVERLAYS:
        window.set_extra(key, True)
    result["tile_overlays"] = {
        "layers": sorted(window.tile_layers),
        "valid": all(window.tile_layers[k].isValid() for k in TILE_OVERLAYS)}
    state["ls_started"] = time.monotonic()


def _overlay_settled(window):
    overlay = window.overlay
    return overlay is not None and not overlay.busy() \
        and not window.view._overlay_missing \
        and not window.view.load_missing


@check(1000)
def tile_overlays_wait():
    """Картинки наложения пришли, кадр с наложениями. Потом наложения
    выключаются."""
    window = state["window"]
    spent = time.monotonic() - state["ls_started"]
    if spent < 60.0 and not _overlay_settled(window):
        return 1000
    out = result["tile_overlays"]
    out["seconds_on"] = round(spent, 1)
    out["in_overlay"] = sorted(
        k for k in TILE_OVERLAYS if window.overlay is not None and any(
            la is window.tile_layers[k] for la in window.overlay.layers))
    out["credits"] = window.attribution.text()
    out["rows"] = [k for k in TILE_OVERLAYS
                   if k in window.panel.active_rows]
    state["tile_on"] = window.view.grabFramebuffer()
    state["tile_on"].save(os.path.join(TEMP, "planetx_tile_overlays.png"))
    for key in TILE_OVERLAYS:
        window.set_extra(key, False)
    state["ls_started"] = time.monotonic()
    return None


@check(1000)
def tile_overlays_check():
    """Без наложений кадр другой, слоёв в наложении нет."""
    window = state["window"]
    spent = time.monotonic() - state["ls_started"]
    if spent < 60.0 and (window.view.load_missing or (
            window.overlay is not None and not _overlay_settled(window))):
        return 1000
    out = result["tile_overlays"]
    off = window.view.grabFramebuffer()
    on = state.pop("tile_on")
    diff = 0
    for y in range(0, on.height(), 4):
        for x in range(0, on.width(), 4):
            if on.pixel(x, y) != off.pixel(x, y):
                diff += 1
    out["changed_share"] = round(diff / ((on.height() // 4)
                                         * (on.width() // 4)), 3)
    out["after_off"] = window.overlay is None or not any(
        la is layer for la in window.overlay.layers
        for layer in window.tile_layers.values())
    out["credit_off"] = "waymarkedtrails" not in window.attribution.text()
    return None


@check(1000)
def currents_on():
    """Течения NOAA над Гольфстримом с 3000 км."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.set_theme("")
    window.view.navigator.show(Pose(38.0, -65.0, 3000000.0, 0.0, 0.0))
    window.set_extra("currents", True)
    state["flow_started"] = time.monotonic()
    result["flow"] = {"gallery": "currents" in [
        k for k, _ in __import__("planetx.ui.nasamaps",
                                 fromlist=["LAYERS"]).LAYERS]}


@check(1000)
def currents_wait():
    window = state["window"]
    if window.flow.fields["currents"] is None \
            and window.flow.currents_reply is not None \
            and time.monotonic() - state["flow_started"] < 90.0:
        return 1000
    result["flow"]["currents_load_s"] = round(
        time.monotonic() - state["flow_started"], 1)


@check(3000)
def currents_check():
    window = state["window"]
    view = window.view
    out = result["flow"]
    out["day"] = window.flow.currents_day
    out["error"] = window.flow.error
    out["drawn"] = view.flows["currents"].drawn
    out["legend"] = window.current_legend.isVisible()
    out["row"] = "currents" in window.panel.active_rows
    out["credit"] = "CoastWatch" in window.attribution.text()
    # Цена шага частиц и кадра.
    started = time.perf_counter()
    for _ in range(40):
        window.flow._tick()
    out["tick_ms"] = round((time.perf_counter() - started) * 25.0, 2)
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_currents.png"))
    window.set_extra("currents", False)
    out["after_off"] = view.flows["currents"].particles is None \
        and not window.current_legend.isVisible()


@check(1000)
def wind_on():
    """Ветер GFS: раскраска и струйки над Европой с 6000 км."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.view.navigator.show(Pose(50.0, 10.0, 6000000.0, 0.0, 0.0))
    window.set_theme("weather_wind")
    state["flow_started"] = time.monotonic()


@check(1000)
def wind_wait():
    window = state["window"]
    if window.flow.fields["wind"] is None \
            and time.monotonic() - state["flow_started"] < 90.0:
        return 1000
    result["flow"]["wind_load_s"] = round(
        time.monotonic() - state["flow_started"], 1)


@check(3000)
def wind_check():
    window = state["window"]
    view = window.view
    out = result["flow"]
    for _ in range(40):
        window.flow._tick()
    out["wind_drawn"] = view.flows["wind"].drawn
    field = window.flow.fields["wind"]
    out["wind_grid"] = None if field is None else list(field.u.shape)
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_wind.png"))
    window.set_theme("")
    out["wind_after_off"] = view.flows["wind"].particles is None \
        and window.flow.fields["wind"] is None


@check(1000)
def rumsey_open():
    """Карты Рамсея у Москвы: каталог из локальной копии planetx-terrain
    (PLANETX_TERRAIN_DIR, иначе C:/Dev/planetx-terrain)."""
    from qgis.PyQt.QtCore import QUrl
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.set_theme("")
    window.view.navigator.show(Pose(55.75, 37.62, 30000.0, 0.0, 0.0))
    folder = os.environ.get("PLANETX_TERRAIN_DIR") or "C:/Dev/planetx-terrain"
    # PLANETX_RUMSEY_NET - каталог из хранилища через зеркала.
    window.rumsey_loader.base = None if os.environ.get("PLANETX_RUMSEY_NET") \
        else QUrl.fromLocalFile(folder).toString()
    window.rumsey_loader.catalogue = None
    state["rumsey_dialog"] = window.rumsey_here(55.75, 37.62)
    state["rumsey_started"] = time.monotonic()
    result["rumsey"] = {}


@check(1000)
def rumsey_list():
    window = state["window"]
    dialog = state["rumsey_dialog"]
    if window.rumsey_loader.catalogue is None \
            and time.monotonic() - state["rumsey_started"] < 60.0:
        return 1000
    out = result["rumsey"]
    out["catalogue"] = 0 if window.rumsey_loader.catalogue is None \
        else len(window.rumsey_loader.catalogue)
    out["rows"] = dialog.list.topLevelItemCount()
    out["first"] = [dialog.list.topLevelItem(n).text(0) + " "
                    + dialog.list.topLevelItem(n).text(1)[:50]
                    for n in range(min(8, out["rows"]))]
    # План Москвы 1739 года, иначе первая строка.
    pick = 0
    for n in range(out["rows"]):
        item = dialog.list.topLevelItem(n)
        if item.text(0) == "1739":
            pick = n
            break
    item = dialog.list.topLevelItem(pick)
    out["picked"] = item.text(0) + " " + item.text(1)[:60]
    dialog.grab().save(os.path.join(TEMP, "planetx_rumsey_dialog.png"))
    row = item.data(0, 0x0100)
    number = int(window.rumsey_loader.catalogue.number[row])
    from planetx.ui.rumsey import rumsey_folder
    cached = os.path.join(rumsey_folder(), "{}.tif".format(number))
    if os.path.exists(cached):
        os.remove(cached)
    dialog.list.setCurrentItem(item)
    state["rumsey_started"] = time.monotonic()
    dialog._load()


@check(1000)
def rumsey_wait():
    window = state["window"]
    if window.rumsey_loader.job is not None \
            and time.monotonic() - state["rumsey_started"] < 180.0:
        return 1000
    result["rumsey"]["build_s"] = round(
        time.monotonic() - state["rumsey_started"], 1)


@check(3000)
def rumsey_check():
    from qgis.core import QgsProject
    from planetx.ui.project import read_map_years
    window = state["window"]
    out = result["rumsey"]
    dialog = state["rumsey_dialog"]
    out["status"] = dialog.status.text()
    root = QgsProject.instance().layerTreeRoot()
    group = root.findGroup("Карты Рамсея") or root.findGroup("Rumsey maps")
    layers = [] if group is None else [n.layer() for n in group.findLayers()]
    out["layers"] = [la.name()[:60] for la in layers]
    if layers:
        e = layers[0].extent()
        out["extent"] = [round(v, 3) for v in (e.xMinimum(), e.yMinimum(),
                                                e.xMaximum(), e.yMaximum())]
        out["size"] = [layers[0].width(), layers[0].height()]
        out["year"] = read_map_years().get(layers[0].id())
        out["on_globe"] = layers[0].id() in window.shown_layers()
    out["credit"] = "Rumsey" in window.attribution.text()
    window.view.grabFramebuffer().save(os.path.join(TEMP,
                                                    "planetx_rumsey.png"))
    dialog.close()
    if group is not None:
        for node in group.findLayers():
            QgsProject.instance().removeMapLayer(node.layerId())
        root.removeChildNode(group)


BODY_CONTOUR_VIEWS = (
    ("mars", "far", (18.65, -133.8, 1500000.0, 0.0, 0.0)),
    ("mars", "near", (18.65, -133.8, 150000.0, 0.0, 40.0)),
    ("moon", "far", (-43.3, -11.2, 800000.0, 0.0, 0.0)),
    ("moon", "near", (-43.3, -11.2, 120000.0, 0.0, 40.0)))


@check(1000)
def contours_bodies():
    """Горизонтали на Марсе (Олимп) и Луне (кратер Тихо) издалека
    и вблизи: текстуры слоя, кадры, ошибки OpenGL."""
    from planetx.core.navigation import Pose
    window = state["window"]
    index = state.get("body_contours", 0)
    out = result.setdefault("contours_bodies", {})
    if index:
        body, name, _ = BODY_CONTOUR_VIEWS[index - 1]
        view = window.view
        layer = view.gibs["contours"]
        out[body + "_" + name] = {
            "textures": len(layer.textures),
            "levels": sorted({k[0] for k in layer.textures}),
            "max_level": layer.max_level,
            "legend": not window.contour_legend.isHidden(),
            "palette": window._contour_palette,
            "gl": dict(view.gl_errors)}
        view.grabFramebuffer().save(os.path.join(
            TEMP, "planetx_contours_{}_{}.png".format(body, name)))
    if index >= len(BODY_CONTOUR_VIEWS):
        window.set_extra("contours", False)
        window.set_body("earth")
        state.pop("body_contours", None)
        return None
    body, name, pose = BODY_CONTOUR_VIEWS[index]
    if window.planet.key != body:
        window.set_body(body)
    window.set_extra("contours", True)
    window.view.navigator.stop()
    window.view.navigator.set_pose(Pose(*pose))
    state["body_contours"] = index + 1
    return 20000


@check(1000)
def command_bar():
    """Строка «Поиск» как строка действий: подсказки «течения»
    и «линейка», Enter по названию включает слой, «Пермь» остаётся
    поиском места, Ctrl+K ставит курсор в строку."""
    window = state["window"]
    window.set_body("earth")
    window.set_extra("currents", False)
    out = {}
    hints = window.search_suggestions("течения")
    out["currents_hint"] = [(h.kind, h.text, h.note) for h in hints[:3]]
    hints = window.search_suggestions("линей")
    out["ruler_hint"] = [(h.kind, h.text) for h in hints[:3]]
    window.fly("течения")
    out["currents_on"] = bool(window.extras.get("currents"))
    out["text_after"] = window.place.text()
    window.fly("течения")
    out["currents_off"] = not window.extras.get("currents")
    out["perm_action"] = window._exact_action("Пермь") is not None
    window.place.setText("слово")
    window.focus_search()
    out["focus"] = window.place.hasFocus() or not window.isActiveWindow()
    out["selected"] = window.place.selectedText()
    window.place.clear()
    window.panel.hide_hints()
    out["actions"] = len(window._actions)
    result["command_bar"] = out


@check(1000)
def guide_tour():
    """Знакомство с модулем: пять остановок, у каждой - вырез вокруг
    своего места и окошко внутри окна, раздел «Слои» раскрывается,
    «Готово» на последней закрывает, настройка помнит показ."""
    from qgis.core import QgsSettings
    from planetx.ui.guide import GUIDE_KEY
    window = state["window"]
    QgsSettings().setValue(GUIDE_KEY, False)
    window.start_guide()
    guide = window.guide
    out = {"setting": QgsSettings().value(GUIDE_KEY, False, type=bool),
           "stops": []}
    window.panel.section("base").set_open(False)
    for n in range(len(guide.items)):
        guide.show_stop(n)
        # Раздел раскрывается за проход цикла событий, вырез считается
        # второй раз по таймеру окна.
        QgsApplication.processEvents()
        guide._place_if_alive()
        hole = guide.shade.hole
        box = guide.geometry()
        out["stops"].append({
            "title": guide.title.text(),
            "hole": [hole.x(), hole.y(), hole.width(), hole.height()],
            "inside": window.rect().contains(box),
            "next": guide.next.text()})
    out["layers_open"] = window.panel.section("base").is_open()
    out["action"] = [h.text for h in window.search_suggestions("знакомство")
                     if h.kind == "action"]
    guide.next.click()
    out["closed"] = window.guide is None
    path = os.path.join(TEMP, "planetx_guide.png")
    window.start_guide()
    window.guide.show_stop(1)
    window.grab().save(path)
    window.guide.finish()
    result["guide"] = out


@check(1000)
def side_panel():
    """Панель свойств справа: свойства метки встают в неё, вид
    сужается, свойства папки заменяют метку её «Отменой», «OK» папки
    пишет название, панель прячется, вид возвращает место."""
    from planetx.core.features import Shape
    window = state["window"]
    store = window.myplaces
    store.add(Shape("point", [(58.0, 56.2)], name="Панель теста"))
    place = [p for p in store.places if p.name == "Панель теста"][0]
    folder = store.add_folder("Папка панели теста")
    out = {"sizes_before": window.splitter.sizes(),
           # Пустая панель скрыта, снимок автора от 17 октября 2026 года.
           "hidden_empty": window.side.isHidden()}
    window._place_action("properties", place.key)
    dialog = window.prop_dialogs[place.key]
    QgsApplication.processEvents()
    out["hosted"] = window.side.dialog is dialog
    out["embedded"] = not dialog.isWindow()
    out["title"] = window.side.title.text()
    out["sizes_open"] = window.splitter.sizes()
    dialog.name.setText("Панель теста 2")
    window._place_action("properties", folder)
    QgsApplication.processEvents()
    out["place_closed"] = place.key not in window.prop_dialogs
    out["place_name"] = store.find(place.key).name
    folder_dialog = window.side.dialog
    out["folder_hosted"] = type(folder_dialog).__name__
    folder_dialog.name.setText("Папка панели 2")
    folder_dialog.accept()
    QgsApplication.processEvents()
    out["folder_name"] = store.find(folder).name
    out["hidden"] = window.side.isHidden()
    out["sizes_after"] = window.splitter.sizes()
    store.remove(place.key)
    store.remove(folder)
    result["side_panel"] = out


@check(500)
def draw_shot():
    """Меню значка «Новая метка»: пункты видов объекта, пункт открывает
    окно на своей вкладке. Снимки planetx_draw_window.png и
    planetx_draw.png."""
    window = state["window"]
    actions = window.toolbar.place_button.menu().actions()
    opened = {}
    for action, mode in zip(actions, ("point", "path", "polygon",
                                      "circle")):
        action.trigger()
        QgsApplication.processEvents()
        opened[mode] = window.drawer.mode
    dialog = window.place_dialog
    result["draw_menu"] = {
        "items": [a.text() for a in actions], "opened": opened,
        "popup": int(getattr(window.toolbar.place_button.popupMode(),
                             "value", window.toolbar.place_button
                             .popupMode())),
        "line_width": dialog.line_width.value(),
        "width_method": callable(dialog.width)}
    window.grab().save(os.path.join(TEMP, "planetx_draw_window.png"))
    dialog.grab().save(os.path.join(TEMP, "planetx_draw.png"))
    result["draw_shot"] = {
        "visible": dialog.isVisible(), "window": dialog.isWindow(),
        "parent": type(dialog.parent()).__name__,
        "geometry": list(dialog.geometry().getRect()),
        "tabs": [dialog.tabs.tabText(i) for i in range(dialog.tabs.count())],
        "tabs_visible": dialog.tabs.isVisible(),
        "tabs_size": [dialog.tabs.width(), dialog.tabs.height()]}
    dialog.reject()
    QgsApplication.processEvents()


@check(500)
def menu_shot():
    """Выпадающие меню панели значков в цветах плашки: снимки
    planetx_menu_<кнопка>.png и цвет фона меню. Ручной шаг."""
    from qgis.PyQt.QtCore import QPoint
    window = state["window"]
    bar = window.toolbar
    out = {}
    for name in ("demo", "body", "scene", "place_button"):
        button = getattr(bar, name)
        menu = button.menu()
        menu.popup(button.mapToGlobal(QPoint(0, button.height())))
        QgsApplication.processEvents()
        image = menu.grab().toImage()
        image.save(os.path.join(TEMP, "planetx_menu_{}.png".format(name)))
        color = image.pixelColor(image.width() // 2, image.height() - 6)
        out[name] = [color.red(), color.green(), color.blue()]
        menu.hide()
        QgsApplication.processEvents()
    result["menu_shot"] = out


@check(500)
def props_shot():
    """Окно свойств многоугольника в боковой панели: группы сверху вниз,
    лишняя высота под окном. Снимок окна глобуса - planetx_props.png,
    высоты окна и панели. Ручной шаг."""
    from planetx.core.features import Shape
    window = state["window"]
    store = window.myplaces
    key = store.add(Shape("polygon", [(58.0, 56.2), (58.1, 56.4),
                                      (58.0, 56.5)], name="Окно свойств"))
    window._place_action("properties", key)
    QgsApplication.processEvents()
    dialog = window.prop_dialogs[key]
    window.grab().save(os.path.join(TEMP, "planetx_props.png"))
    result["props_shot"] = {
        "dialog_h": dialog.height(), "hint_h": dialog.sizeHint().height(),
        "panel_h": window.side.height(),
        "groups": [b.title() for b in dialog.findChildren(
            __import__("qgis.PyQt.QtWidgets",
                       fromlist=["QGroupBox"]).QGroupBox)]}
    dialog.reject()
    QgsApplication.processEvents()
    store.remove(key)


@check(500)
def mirror_tiles():
    """Тайлы planetx-terrain: первое зеркало - закрытый порт, загрузчик
    уходит на jsDelivr и получает тайлы."""
    from planetx.core import basemap
    from planetx.net.loader import TileLoader
    window = state["window"]
    url = ("https://raw.githubusercontent.com/Valery35/planetx-terrain/"
           "main/imagery/mercury/{z}/{x}/{y}.jpg")
    source = basemap.Source("Mercury", url, 4)
    source.urls = ("https://127.0.0.1:9/{z}/{x}/{y}.jpg",) + source.urls
    loader = TileLoader(source, parent=window)
    got = []
    loader.loaded.connect(lambda key, *a: got.append(key))
    state["mirror"] = (loader, source, got, time.monotonic())
    for x in range(2):
        for y in range(2):
            loader.want((1, x, y), 1.0)


@check(1000)
def mirror_tiles_wait():
    loader, source, got, started = state["mirror"]
    if len(got) < 4 and time.monotonic() - started < 60.0:
        loader._pump()
        for x in range(2):
            for y in range(2):
                if (1, x, y) not in got:
                    loader.want((1, x, y), 1.0)
        return 1000
    result["mirror_tiles"] = {"tiles": len(got), "mirror": source.mirror,
                              "seconds": round(time.monotonic() - started,
                                               1)}
    loader.abort()


@check(1000)
def currents_time():
    """Течения на день шкалы времени: 15 июля 2020 года."""
    from planetx.core.navigation import Pose
    from planetx.core import flow as flow_core
    window = state["window"]
    window.set_body("earth")
    window.view.navigator.show(Pose(38.0, -65.0, 3000000.0, 0.0, 0.0))
    window.set_extra("currents", True)
    state["flow_started"] = time.monotonic()
    state["currents_moment"] = flow_core.day_seconds("2020-07-15")


@check(1000)
def currents_time_wait():
    window = state["window"]
    flow = window.flow
    out = result.setdefault("currents_time", {})
    if not flow.currents_last:
        if time.monotonic() - state["flow_started"] < 60.0:
            return 1000
        out["error"] = "no last day"
        return None
    if "span" not in out:
        out["last"] = flow.currents_last
        out["span"] = flow.currents_span() is not None
        if not window.timebar.shown():
            window.timebar.open_bar()
        moment = state["currents_moment"]
        window.timebar.set_range(moment, moment)
        window._time_changed(*window.timebar.range())
        state["flow_started"] = time.monotonic()
        return 1000
    if flow.currents_day != "2020-07-15" \
            and time.monotonic() - state["flow_started"] < 60.0:
        return 1000
    out["day"] = flow.currents_day
    out["kept"] = sorted(flow.currents_days)
    out["drawn"] = window.view.flows["currents"].drawn
    path = os.path.join(TEMP, "planetx_active", "currents.tif")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        os.remove(path)
    out["exported"] = window.active_export("currents", path)
    window.view.grabFramebuffer().save(os.path.join(
        TEMP, "planetx_currents_2020.png"))
    window.set_extra("currents", False)
    from qgis.core import QgsProject
    root = QgsProject.instance().layerTreeRoot()
    group = root.findGroup("PlanetX - слои глобуса") \
        or root.findGroup("PlanetX - globe layers")
    out["group"] = [] if group is None else [
        n.layer().name() for n in group.findLayers()]
    if group is not None:
        for node in group.findLayers():
            QgsProject.instance().removeMapLayer(node.layerId())
        root.removeChildNode(group)
    window.timebar.close_bar()


@check(1000)
def theme_export():
    """Тема NASA в проект картинкой WMS GIBS по рамке вида."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.view.navigator.show(Pose(60.0, 60.0, 3000000.0, 0.0, 0.0))
    window.set_theme("snow")
    state["theme_started"] = time.monotonic()


@check(1000)
def theme_export_go():
    window = state["window"]
    if window.theme_day is None \
            and time.monotonic() - state["theme_started"] < 60.0:
        return 1000
    path = os.path.join(TEMP, "planetx_active", "theme.tif")
    if os.path.exists(path):
        os.remove(path)
    state["theme_path"] = path
    result["theme_export"] = {"day": window.theme_day,
                              "rows": list(window.panel.active_rows)}
    window.active_export("map", path)
    state["theme_started"] = time.monotonic()


@check(1000)
def theme_export_wait():
    from qgis.core import QgsProject
    window = state["window"]
    out = result["theme_export"]
    root = QgsProject.instance().layerTreeRoot()
    group = root.findGroup("PlanetX - слои глобуса") \
        or root.findGroup("PlanetX - globe layers")
    if group is None and time.monotonic() - state["theme_started"] < 60.0:
        return 1000
    layers = [] if group is None else [n.layer() for n in group.findLayers()]
    out["layers"] = [(la.name(), la.width(), la.height()) for la in layers]
    if layers:
        e = layers[0].extent()
        out["extent"] = [round(v, 2) for v in (
            e.xMinimum(), e.yMinimum(), e.xMaximum(), e.yMaximum())]
    out["message"] = window.message[0] if window.message else ""
    if group is not None:
        for node in group.findLayers():
            QgsProject.instance().removeMapLayer(node.layerId())
        root.removeChildNode(group)
    window.set_theme("")


@check(1000)
def rumsey_search():
    """Поиск карт Рамсея по всему каталогу, рамки на глобусе, перелёт."""
    window = state["window"]
    dialog = window.rumsey_here(55.75, 37.62)
    state["rumsey_dialog"] = dialog
    state["rumsey_started"] = time.monotonic()


@check(1000)
def rumsey_search_check():
    window = state["window"]
    dialog = state["rumsey_dialog"]
    if window.rumsey_loader.catalogue is None \
            and time.monotonic() - state["rumsey_started"] < 60.0:
        return 1000
    out = {}
    out["footprints_view"] = window.rumsey_footprints.featureCount() \
        if window.rumsey_footprints is not None else 0
    dialog.everywhere.setChecked(True)
    dialog.filter.setText("Perm")
    out["found"] = dialog.list.topLevelItemCount()
    out["first"] = [dialog.list.topLevelItem(n).text(0) + " "
                    + dialog.list.topLevelItem(n).text(1)[:40]
                    for n in range(min(5, out["found"]))]
    if out["found"]:
        dialog.list.setCurrentItem(dialog.list.topLevelItem(0))
        dialog._fly()
    out["footprints"] = window.rumsey_footprints.featureCount() \
        if window.rumsey_footprints is not None else 0
    out["in_overlay"] = window.rumsey_footprints is not None \
        and window.overlay is not None and any(
            la is window.rumsey_footprints for la in window.overlay.layers)
    dialog.close()
    out["after_close"] = window.rumsey_footprints is None
    result["rumsey_search"] = out


BRIENZ_DEEP = (46.72744, 7.9565)


@check(3000)
def brienz_open():
    """Своя батиметрия, демо «Бриенцское озеро»: растр отметок дна
    swissBATHY3D, вода на 564 м."""
    window = state["window"]
    action = next(a for a in window.toolbar.demo.menu().actions()
                  if a.text() in ("Бриенцское озеро, своя батиметрия",
                                  "Lake Brienz, own bathymetry"))
    started = time.monotonic()
    action.trigger()
    result["brienz"] = {
        "prepare_s": round(time.monotonic() - started, 2),
        "insets": [(e.name, e.lake) for e in window.insets]}


@check(3000)
def brienz_wait():
    return _quarry_wait(60.0)


def _brienz_depth():
    window = state["window"]
    lat, lon = BRIENZ_DEEP
    return round(float(window.view.store.heights_at(
        [lat], [lon], scaled=False)[0]), 1)


@check(2000)
def brienz_check():
    """Дно, вода, кадр. Потом тот же растр глубинами: глубина =
    564 - отметка, слой с видом depth даёт то же дно."""
    import numpy as np
    from osgeo import gdal
    from qgis.core import QgsProject, QgsRasterLayer
    from planetx.ui.project import (read_bathymetry, read_insets,
                                    write_bathymetry)
    window = state["window"]
    out = result["brienz"]
    out["bed_deepest"] = _brienz_depth()
    out["water_vertices"] = window.view.lake_water.vertex_count()
    window.view.grabFramebuffer().save(os.path.join(TEMP,
                                                    "planetx_brienz.png"))
    out["water_drawn"] = window.view.lake_water.drawn
    # Профиль через озеро - вода над дном до уровня 564 м.
    key = next(p.key for p in window.myplaces.places
               if p.name == "Профиль через озеро")
    window._place_action("profile", key)
    dialog = window.profile_dialog
    water = dialog.chart.water
    out["profile_water"] = None if water is None else {
        "wet": int(np.isfinite(water).sum()), "points": len(water),
        "level": float(np.nanmax(water)) if np.isfinite(water).any()
        else None}
    dialog.grab().save(os.path.join(TEMP, "planetx_brienz_profile.png"))
    window.set_relief(False)
    # Сетки снимаются в кадре: смотрится очередь, без вызовов OpenGL.
    pending = window.view.lake_water.pending
    out["water_removed_without_relief"] = bool(pending) and all(
        mesh is None for mesh in pending.values())
    window.set_relief(True)
    # Глубины: растр 564 - дно в папке TEMP.
    src = os.path.join(ROOT, "planetx", "demo", "brienz",
                       "brienzersee_bed.tif")
    path = os.path.join(TEMP, "planetx_brienz_depth.tif")
    ds = gdal.Open(src)
    bed = ds.GetRasterBand(1).ReadAsArray()
    depth = np.where(bed == -9999.0, -9999.0, 564.0 - bed)
    copy = gdal.GetDriverByName("GTiff").CreateCopy(path, ds)
    copy.GetRasterBand(1).WriteArray(depth.astype(np.float32))
    copy = ds = None
    layer = QgsRasterLayer(path, "Brienz depths", "gdal")
    QgsProject.instance().addMapLayer(layer)
    old = [i for i in read_insets()
           if read_bathymetry().get(i, ("", 0))[0] == "bed"]
    lakes = {layer.id(): ("depth", 564.0)}
    write_bathymetry(lakes)
    window.set_insets([layer.id()])
    state["brienz_depth_layer"] = (layer.id(), old)
    out["depth_entry"] = [(e.name, e.lake) for e in window.insets]


@check(3000)
def brienz_depth_wait():
    return _quarry_wait(60.0)


@check(1000)
def brienz_depth_check():
    from qgis.core import QgsProject
    window = state["window"]
    out = result["brienz"]
    out["bed_from_depths"] = _brienz_depth()
    out["water_vertices_depths"] = window.view.lake_water.vertex_count()
    layer_id, _ = state["brienz_depth_layer"]
    window.set_insets([])
    QgsProject.instance().removeMapLayer(layer_id)
    pending = window.view.lake_water.pending
    out["water_removed_after_off"] = bool(pending) and all(
        mesh is None for mesh in pending.values())


@check(2000)
def volume_check():
    """Выемка и насыпь: новая съёмка - съёмка карьера демо, дно углублено
    на 15 м в круге 60 м, отвал 20 м квадратом 80 м. Объёмы сверяются
    с точными по пикселям."""
    import numpy as np
    from osgeo import gdal
    from qgis.core import QgsProject, QgsRasterLayer
    window = state["window"]
    src = os.path.join(ROOT, "planetx", "demo", "quarry", "quarry_dem.tif")
    old = QgsRasterLayer(src, "survey 2025", "gdal")
    QgsProject.instance().addMapLayer(old)
    ds = gdal.Open(src)
    dem = ds.GetRasterBand(1).ReadAsArray().astype(np.float64)
    rows, cols = dem.shape
    yy, xx = np.mgrid[0:rows, 0:cols]
    pit = (yy - rows // 2) ** 2 + (xx - cols // 2) ** 2 <= 60 ** 2
    dump = (yy >= 200) & (yy < 280) & (xx >= 200) & (xx < 280)
    new = dem.copy()
    new[pit] -= 15.0
    new[dump] += 20.0
    path = os.path.join(TEMP, "planetx_survey_2026.tif")
    copy = gdal.GetDriverByName("GTiff").CreateCopy(path, ds)
    copy.GetRasterBand(1).WriteArray(new.astype(np.float32))
    copy = None
    _, dx, _, _, _, dy = ds.GetGeoTransform()
    cell = abs(dx * dy)
    layer = QgsRasterLayer(path, "survey 2026", "gdal")
    QgsProject.instance().addMapLayer(layer)
    started = time.monotonic()
    done = window.volume_compare(layer.id(), (old.id(), "", 0.1))
    raster_id, out = done
    result["volumes"] = {
        "seconds": round(time.monotonic() - started, 2),
        "cut": round(out["cut"]), "cut_expected": round(
            pit.sum() * 15.0 * cell),
        "fill": round(out["fill"]), "fill_expected": round(
            dump.sum() * 20.0 * cell),
        "deepest": round(out["deepest"], 2),
        "highest": round(out["highest"], 2),
        "on_globe": raster_id in window._shown}
    for layer_id in (raster_id, layer.id(), old.id()):
        QgsProject.instance().removeMapLayer(layer_id)


@check(3000)
def sounding_build():
    """Батиметрия по промерам: галсы с севера на юг через 50 м, точка
    через 5 м, глубины 564 - дно растра swissBATHY3D. Грид по ним -
    своя батиметрия."""
    import numpy as np
    from osgeo import gdal, osr
    from qgis.core import (QgsFeature, QgsGeometry, QgsPoint, QgsProject,
                           QgsVectorLayer)
    from planetx.ui.project import write_bathymetry, write_insets
    from planetx.ui.sounding import read_points
    from planetx.core import sounding
    window = state["window"]
    write_insets([])
    write_bathymetry({})
    window.set_insets([])
    path = os.path.join(ROOT, "planetx", "demo", "brienz",
                        "brienzersee_bed.tif")
    ds = gdal.Open(path)
    x0, dx, _, y0, _, dy = ds.GetGeoTransform()
    bed = ds.GetRasterBand(1).ReadAsArray()
    srs = osr.SpatialReference(wkt=ds.GetProjection())
    epsg = srs.GetAuthorityCode(None)
    layer = QgsVectorLayer("PointZ?crs=EPSG:{}".format(epsg), "soundings",
                           "memory")
    features = []
    step_col = max(1, int(round(50.0 / dx)))
    step_row = max(1, int(round(5.0 / abs(dy))))
    for col in range(0, bed.shape[1], step_col):
        for row in range(0, bed.shape[0], step_row):
            value = float(bed[row, col])
            if value == -9999.0 or not np.isfinite(value):
                continue
            feature = QgsFeature()
            feature.setGeometry(QgsGeometry(QgsPoint(
                x0 + (col + 0.5) * dx, y0 + (row + 0.5) * dy,
                -(564.0 - value))))
            features.append(feature)
    layer.dataProvider().addFeatures(features)
    QgsProject.instance().addMapLayer(layer)
    state["sounding_layer"] = layer.id()
    started = time.monotonic()
    points = read_points(layer, "")
    xs, ys = points[0], points[1]
    cell = sounding.auto_cell(xs, ys)
    raster = window.sounding_bathymetry(layer.id(), (
        points, cell, cell * sounding.MAX_GAP_CELLS, 564.0,
        os.path.join(TEMP, "planetx_soundings.tif")))
    result["sounding"] = {
        "points": len(xs), "cell": cell,
        "build_s": round(time.monotonic() - started, 2),
        "raster": raster is not None,
        "insets": [(e.name, e.lake) for e in window.insets]}
    state["sounding_raster"] = raster


@check(3000)
def sounding_wait():
    return _quarry_wait(60.0)


@check(1000)
def sounding_check():
    from qgis.core import QgsProject
    window = state["window"]
    out = result["sounding"]
    out["bed_deepest"] = _brienz_depth()
    out["water_vertices"] = window.view.lake_water.vertex_count()
    window.view.grabFramebuffer().save(os.path.join(
        TEMP, "planetx_sounding.png"))
    window.set_insets([])
    for key in ("sounding_raster", "sounding_layer"):
        if state.get(key):
            QgsProject.instance().removeMapLayer(state[key])


def _year(window):
    from planetx.core import oldmaps
    moment = window._map_moment()
    return None if moment is None else oldmaps.year_label(moment)


def _map_names(window):
    """Названия растров-карт наложения, видные сейчас."""
    from qgis.core import QgsProject
    hidden = window._maps_hidden()
    return sorted(QgsProject.instance().mapLayer(i).name()
                  for i in window._map_years
                  if i in (window._applied_layers or ()) and i not in hidden)


@check(500)
def ua_send():
    """Заголовок User-Agent на сервере: запрос PlanetX несёт свой,
    запрос QGIS - заголовок QGIS. Прежний обработчик запросов на Python
    QGIS звал для всех запросов всех потоков, см. AGENTS.md."""
    import http.server
    import threading
    from qgis.core import QgsNetworkAccessManager
    from qgis.PyQt.QtCore import QUrl
    from qgis.PyQt.QtNetwork import QNetworkRequest
    from planetx.net.overlay import fetch_bytes
    seen = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            return None

        def do_GET(self):
            seen[self.path] = self.headers.get("User-Agent", "")
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:{}".format(server.server_address[1])
    got = {}
    state["ua"] = (server, seen, got, [
        fetch_bytes(base + "/planetx", lambda data, error:
                    got.update(planetx=(data, error)), fresh=True),
        QgsNetworkAccessManager.instance().get(
            QNetworkRequest(QUrl(base + "/qgis")))])


@check(1000)
def sources_shot():
    """Снимок окна «Источники данных» с группой рельефа."""
    from planetx.ui.sources import SourcesDialog
    window = state["window"]
    dialog = SourcesDialog(window)
    dialog.show()
    dialog.grab().save(os.path.join(TEMP, "planetx_sources.png"))
    result["sources_shot"] = {"models": [dialog.model.itemText(i) for i in
                                         range(dialog.model.count())]}
    dialog.close()


@check(500)
def ssl_send():
    """Запрос PlanetX к серверу с самоподписанным сертификатом: Qt его
    обрывает, ошибка SSL пишется в журнал работы."""
    from planetx.net.overlay import fetch_bytes
    got = {}
    state["ssl"] = (got, fetch_bytes(
        "https://self-signed.badssl.com/",
        lambda data, error: got.update(done=(data, error)), fresh=True))


@check(500)
def ssl_check():
    from qgis.core import QgsApplication
    got, _ = state["ssl"]
    if "done" not in got and state.setdefault("ssl_wait", 0) < 40:
        state["ssl_wait"] += 1
        return 500
    path = os.path.join(QgsApplication.qgisSettingsDirPath(), "PlanetX",
                        "planetx.log")
    with open(path, encoding="utf-8") as stream:
        tail = stream.read()[-4000:]
    data, error = got.get("done", (None, "timeout"))
    result["ssl"] = {"data": data is not None, "error": error,
                     "journal": "self-signed.badssl.com" in tail}


@check(500)
def ua_check():
    server, seen, got, replies = state["ua"]
    if len(seen) < 2 and state.setdefault("ua_wait", 0) < 20:
        state["ua_wait"] += 1
        return 500
    server.shutdown()
    result["user_agent"] = {
        "planetx": seen.get("/planetx"), "qgis": seen.get("/qgis"),
        "reply": got.get("planetx", (None, ""))[0]}


@check(3000)
def oldmaps_open():
    """Исторические карты, демо «Москва, исторические карты»: пять планов
    Wikimedia Commons тайлами XYZ Wikimaps Warper с годами карт."""
    window = state["window"]
    action = next(a for a in window.toolbar.demo.menu().actions()
                  if a.text() in ("Москва, исторические карты",
                                  "Moscow, historical maps"))
    action.trigger()
    result["oldmaps"] = {
        "years": sorted(window._map_years.values()),
        "bar_shown": window.timebar.shown(),
        "point": window.timebar.track.point,
        "stepper": window.timebar.stepper is not None,
        "compare_button": window.timebar.compare.isVisibleTo(window.timebar),
        "year": _year(window),
        "shown_maps": _map_names(window)}


def _overlay_wait(name, limit, loader=None):
    window = state["window"]
    started = state.setdefault(name, time.monotonic())
    loader = loader or window.overlay
    busy = loader is not None and loader.busy()
    # Вид просит тайлы наложения в кадре: сразу после пересборки
    # загрузчик ещё пуст.
    elapsed = time.monotonic() - started
    if (busy or window.view.load_missing or elapsed < 6.0) \
            and elapsed < limit:
        return 500
    state.pop(name, None)


@check(3000)
def oldmaps_wait():
    return _overlay_wait("oldmaps_wait", 60.0)


@check(1000)
def oldmaps_check():
    """Кадр 1813 года, два шага шкалы вперёд - 1912 год, шторка."""
    window = state["window"]
    out = result["oldmaps"]
    window.view.grabFramebuffer().save(os.path.join(
        TEMP, "planetx_oldmaps_1813.png"))
    window.timebar.step(1)
    window.timebar.step(1)
    window._apply_layer_time()
    out["after_steps"] = _year(window)
    out["shown_after_steps"] = _map_names(window)
    out["applied_hidden"] = len(window._applied_maps)
    window.set_compare(True)
    out["swipe"] = {
        "left": window.swipe_bar.left_day.text(),
        "right": window.swipe_bar.right.text(),
        "compare_shown": window.view.gibs["compare"].shown,
        "swipe_maps": window.view.swipe_maps}


@check(3000)
def oldmaps_swipe_wait():
    window = state["window"]
    return _overlay_wait("oldmaps_swipe", 60.0) \
        or _overlay_wait("oldmaps_swipe_left", 60.0,
                         window.map_compare_overlay)


@check(1000)
def oldmaps_swipe_check():
    window = state["window"]
    out = result["oldmaps"]
    window.view.grabFramebuffer().save(os.path.join(
        TEMP, "planetx_oldmaps_swipe.png"))
    out["swipe"]["left_textures"] = len(window.view.gibs["compare"].textures)
    window._compare_step(-1)
    out["swipe"]["left_after_step"] = window.swipe_bar.left_day.text()
    window.set_compare(False)
    out["swipe"]["off"] = (window._map_compare_at is None
                           and window.map_compare_overlay is None
                           and not window.view.swipe_maps)
    window.timebar.close_bar()
    window._time_toggled(False)
    window._apply_layer_time()
    out["closed_bar_shown"] = len(_map_names(window))


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
    # Пожары - карта витрины: тема снимает пожары, пожары снимают тему.
    window.set_theme("smoke")
    QgsApplication.processEvents()
    after_theme = [window.theme_key, bool(window.extras.get("fires"))]
    window.set_theme("fires")
    QgsApplication.processEvents()
    after_fires = [window.theme_key, bool(window.extras.get("fires")),
                   window.gallery_key()]
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


# 3D-модели, как Model KML Google Earth. Просьба автора от 13 октября
# 2026 года. Куб 20 м с картинкой в шахматку - файл Collada рядом
# с картинкой, как пишет SketchUp.
def _cube_dae(folder):
    from qgis.PyQt.QtGui import QColor, QImage
    os.makedirs(os.path.join(folder, "cube"), exist_ok=True)
    image = QImage(64, 64, QImage.Format.Format_ARGB32
                   if hasattr(QImage, "Format") else QImage.Format_ARGB32)
    for x in range(64):
        for y in range(64):
            image.setPixelColor(x, y, QColor(230, 30, 30) if (x // 16
                                + y // 16) % 2 else QColor(240, 240, 240))
    image.save(os.path.join(folder, "cube", "checker.png"), "PNG")
    faces = (((0, 0, 1), [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]),
             ((0, 0, -1), [(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)]),
             ((1, 0, 0), [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)]),
             ((-1, 0, 0), [(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)]),
             ((0, 1, 0), [(0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)]),
             ((0, -1, 0), [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)]))
    pos, nrm, p = [], [], []
    for f, (normal, corners) in enumerate(faces):
        for c in corners:
            pos += [20 * c[0] - 10, 20 * c[1] - 10, 20 * c[2]]
        nrm += list(normal)
        for k in (0, 1, 2, 0, 2, 3):
            p += [4 * f + k, f, k]
    text = """<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema"
 version="1.4.1"><asset><unit meter="1"/><up_axis>Z_UP</up_axis></asset>
<library_images><image id="i"><init_from>cube/checker.png</init_from>
</image></library_images><library_effects><effect id="e">
<profile_COMMON><newparam sid="s"><surface type="2D"><init_from>i
</init_from></surface></newparam><newparam sid="t"><sampler2D><source>s
</source></sampler2D></newparam><technique sid="c"><lambert><diffuse>
<texture texture="t" texcoord="u"/></diffuse></lambert></technique>
</profile_COMMON></effect></library_effects><library_materials>
<material id="m"><instance_effect url="#e"/></material>
</library_materials><library_geometries><geometry id="g"><mesh>
<source id="p"><float_array id="pa" count="72">{pos}</float_array>
<technique_common><accessor source="#pa" count="24" stride="3"/>
</technique_common></source><source id="n"><float_array id="na"
 count="18">{nrm}</float_array><technique_common><accessor source="#na"
 count="6" stride="3"/></technique_common></source><source id="t">
<float_array id="ta" count="8">0 0 1 0 1 1 0 1</float_array>
<technique_common><accessor source="#ta" count="4" stride="2"/>
</technique_common></source><vertices id="v"><input semantic="POSITION"
 source="#p"/></vertices><triangles count="12" material="M">
<input semantic="VERTEX" source="#v" offset="0"/><input semantic="NORMAL"
 source="#n" offset="1"/><input semantic="TEXCOORD" source="#t"
 offset="2"/><p>{p}</p></triangles></mesh></geometry>
</library_geometries><library_visual_scenes><visual_scene id="s"><node>
<instance_geometry url="#g"><bind_material><technique_common>
<instance_material symbol="M" target="#m"/></technique_common>
</bind_material></instance_geometry></node></visual_scene>
</library_visual_scenes><scene><instance_visual_scene url="#s"/></scene>
</COLLADA>""".format(pos=" ".join(str(v) for v in pos),
                     nrm=" ".join(str(v) for v in nrm),
                     p=" ".join(str(v) for v in p))
    path = os.path.join(folder, "cube.dae")
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(text)
    return path


@check(4000)
def models_add():
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.view.navigator.stop()
    # Эспланада в Перми, вид сбоку на 150 м.
    window.view.navigator.set_pose(Pose(58.0104, 56.2294, 150.0, 30.0,
                                        60.0))
    out = result.setdefault("models", {})
    out["before"] = len(window.myplaces.overlays)
    out["centre_before"] = _centre_pixel(window.view)
    path = _cube_dae(os.path.join(TEMP, "planetx_model"))
    key = window.add_model(path=path)
    state["model_key"] = key
    out["key"] = key
    dialog = window.overlay_dialogs.get(key)
    out["dialog"] = dialog is not None
    out["info"] = dialog.model_info.text() if dialog is not None else None
    item = window.myplaces.find(key)
    # Модель добавляется ссылкой на файл, как Link у Google Earth.
    out["linked"] = bool(item and item.href == path and item.image is None)
    if dialog is not None:
        out["handles"] = type(window.handles.tool).__name__
        out["extent"] = dialog.extent
        dialog.place["heading"].setValue(45.0)
        if dialog.extent is not None:
            # Крест рамки - на 0.001° к северу: модель сдвигается.
            from planetx.core import overlays as core_overlays
            box = core_overlays.model_box(dialog.overlay.camera,
                                          dialog.overlay.scale,
                                          dialog.extent)
            lat0, lon0 = core_overlays.box_frame(box)[:2]
            before = dialog.overlay.camera[0]
            dialog.set_place(*core_overlays.model_drag(
                dialog.overlay.camera, dialog.overlay.scale, dialog.extent,
                "center", 0, lat0 + 0.001, lon0))
            out["moved_north"] = round(dialog.overlay.camera[0] - before,
                                       6)
        # Копия в файл меток.
        dialog.store.setCurrentIndex(0)
        dialog.accept()


@check(3000)
def models_check():
    from planetx.core.kml import read_file
    window = state["window"]
    out = result["models"]
    view = window.view
    item = window.myplaces.find(state["model_key"])
    out["saved_heading"] = item.overlay.camera[3] if item else None
    out["stored"] = bool(item and item.image is not None)
    out["drawn"] = view.models.drawn
    out["loaded_parts"] = sum(len(v) for v in view.models.loaded.values())
    out["centre_after"] = _centre_pixel(view)
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_model.png"))
    # KMZ туда и обратно: место, поворот и картинка модели.
    path = os.path.join(TEMP, "planetx_model.kmz")
    window.export_kml(None, path=path)
    with open(path, "rb") as stream:
        back = [o for o in read_file(stream.read()).overlays()
                if o.kind == "model"]
    out["kmz_models"] = len(back)
    out["kmz_place"] = list(back[-1].overlay.camera) if back else None
    out["gl"] = dict(view.gl_errors)


@check(1500)
def models_clean():
    window = state["window"]
    out = result["models"]
    if state.get("model_key"):
        window.myplaces.remove_many([state["model_key"]])
    out["left"] = len(window.myplaces.overlays) - out["before"]
    out["models_after"] = len(window.view.models.source)
    out["gl"] = dict(window.view.gl_errors)


@check(1000, manual=True)
def clean_models():
    """Убрать из «Моих меток» проверочного профиля модели, оставшиеся
    от прерванных прогонов и съёмки роликов."""
    window = state["window"]
    keys = [o.key for o in window.myplaces.overlays if o.kind == "model"]
    if keys:
        window.myplaces.remove_many(keys)
    result["clean_models"] = {"removed": len(keys)}

@check(9000)
def models_anim():
    """Анимированная модель: куб Collada с ключами поворота вокруг оси
    вверх за 4 с."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.view.navigator.stop()
    window.view.navigator.set_pose(Pose(58.0104, 56.2294, 600.0, 30.0,
                                        40.0))
    window.view.update()
    folder = os.path.join(TEMP, "planetx_model_anim")
    # Куб прерванного прогона не мешает.
    window.myplaces.remove_many([o.key for o in window.myplaces.overlays
                                 if (o.href or "").startswith(folder)])
    path = _cube_dae(folder)
    with open(path, encoding="utf-8") as stream:
        text = stream.read()
    text = text.replace(
        '<visual_scene id="s"><node>',
        '<visual_scene id="s"><node id="spin">'
        '<rotate sid="rz">0 0 1 0</rotate>', 1)
    text = text.replace("<library_geometries>", """<library_animations>
<animation><source id="at"><float_array id="ata" count="2">0 4
</float_array><technique_common><accessor source="#ata" count="2"
 stride="1"/></technique_common></source><source id="av"><float_array
 id="ava" count="2">0 360</float_array><technique_common><accessor
 source="#ava" count="2" stride="1"/></technique_common></source>
<sampler id="as"><input semantic="INPUT" source="#at"/><input
 semantic="OUTPUT" source="#av"/></sampler><channel source="#as"
 target="spin/rz.ANGLE"/></animation></library_animations>
<library_geometries>""", 1)
    with open(path, "w", encoding="utf-8") as stream:
        stream.write(text)
    key = window.add_model(path=path)
    state["anim_key"] = key
    dialog = window.overlay_dialogs.get(key)
    result["models_anim"] = {
        "info": dialog.model_info.text() if dialog is not None else None}
    if dialog is not None:
        dialog.accept()


@check(1500)
def models_anim_check():
    import time as _time
    import numpy as np
    from qgis.PyQt.QtTest import QTest
    window = state["window"]
    view = window.view
    out = result["models_anim"]
    out["animated"] = view.models.animated
    out["drawn"] = view.models.drawn
    item = view.models.source[0] if view.models.source else None
    out["turn"] = [round(float(m[0][0][0]), 4) for m in (
        view.models.poses(item, _time.monotonic() + s)[0]
        for s in (0.0, 0.5))] if item is not None else None
    first = view.grabFramebuffer()
    QTest.qWait(500)
    second = view.grabFramebuffer()

    def pixels(image):
        bits = image.constBits()
        bits.setsize(image.sizeInBytes())
        return np.frombuffer(bits, np.uint8).astype(np.int16)
    diff = np.abs(pixels(first) - pixels(second))
    # Куб поворачивается на 45° за полсекунды - меняется часть кадра.
    out["changed_share"] = round(float((diff > 30).mean()), 5)
    second.save(os.path.join(TEMP, "planetx_model_anim.png"))
    window.myplaces.remove_many([state["anim_key"]])
    out["models_after"] = len(view.models.source)
    # Тот же вид без модели: кадры не меняются, сторож доли выше.
    first = view.grabFramebuffer()
    QTest.qWait(500)
    still = np.abs(pixels(first) - pixels(view.grabFramebuffer()))
    out["still_share"] = round(float((still > 30).mean()), 5)
    out["animated_after"] = view.models.animated
    out["gl"] = dict(view.gl_errors)


@check(4000)
def models_demo():
    """Демо «3D-модели, Суздаль и Пермь»: модели из файла сцены
    places.kmz ложатся в «Мои метки» с файлами."""
    window = state["window"]
    action = next(a for a in window.toolbar.demo.menu().actions()
                  if a.text() in ("3D-модели, Суздаль и Пермь",
                                  "3D models, Suzdal and Perm"))
    places = window.myplaces
    before = {o.key for o in places.overlays}
    folders = {f.key for f in places.folders}
    action.trigger()
    state["models_demo"] = [f.key for f in places.folders
                            if f.key not in folders]
    result["models_demo"] = {
        "added": [o.name for o in places.overlays
                  if o.key not in before and o.kind == "model"]}


@check(1000)
def models_look():
    """Кадр каждой модели демо вблизи после загрузки подложки: модель
    глазами, а не по счётчику. Ручной шаг, в общий прогон не входит."""
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    models = [o for o in window.myplaces.overlays if o.kind == "model"
              and o.name in result["models_demo"]["added"]]
    look = state.setdefault("models_look", {"index": 0, "since": None})
    if look["index"] >= len(models):
        return None
    model = models[look["index"]].overlay.camera
    if look["since"] is None:
        view.navigator.stop()
        view.navigator.show(Pose(model[0], model[1], 120.0, 30.0, 60.0))
        look["since"] = time.monotonic()
        return 2000
    waited = time.monotonic() - look["since"]
    # Сразу после перелёта загрузчик ещё не знает о новых тайлах.
    if (view.load_missing or waited < 8.0) and waited < 40.0:
        return 1000
    view.grabFramebuffer().save(os.path.join(
        TEMP, "planetx_model_look_{}.png".format(look["index"])))
    result.setdefault("models_look", []).append(
        {"name": models[look["index"]].name, "drawn": view.models.drawn,
         "waited": round(waited, 1)})
    look["index"] += 1
    look["since"] = None
    return 500


@check(3000)
def models_demo_check():
    window = state["window"]
    view = window.view
    out = result["models_demo"]
    out["drawn"] = view.models.drawn
    out["loaded_parts"] = sum(len(v) for v in view.models.loaded.values())
    out["camera"] = [round(v, 4) for v in (
        view.navigator.pose.lat, view.navigator.pose.lon)]
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_models_demo.png"))
    if state["models_demo"]:
        window.myplaces.remove_many(state["models_demo"])
    out["models_after"] = len(view.models.source)
    out["gl"] = dict(view.gl_errors)


@check(12000)
def turbines_demo():
    """Демо «Анимированная модель, ветряки»: три модели glTF с ротором
    на ключах поворота."""
    window = state["window"]
    action = next(a for a in window.toolbar.demo.menu().actions()
                  if a.text() in ("Анимированная модель, ветряки",
                                  "Animated model, wind turbines"))
    places = window.myplaces
    folders = {f.key for f in places.folders}
    action.trigger()
    state["turbines_demo"] = [f.key for f in places.folders
                              if f.key not in folders]


@check(1000)
def turbines_demo_check():
    import time as _time
    import numpy as np
    from qgis.PyQt.QtTest import QTest
    window = state["window"]
    view = window.view

    def pixels(image):
        bits = image.constBits()
        bits.setsize(image.sizeInBytes())
        return np.frombuffer(bits, np.uint8).astype(np.int16)
    first = view.grabFramebuffer()
    QTest.qWait(700)
    second = view.grabFramebuffer()
    second.save(os.path.join(TEMP, "planetx_turbines.png"))
    result["turbines_demo"] = {
        "drawn": view.models.drawn, "animated": view.models.animated,
        "changed_share": round(float(
            (np.abs(pixels(first) - pixels(second)) > 30).mean()), 5),
        "gl": dict(view.gl_errors)}
    if state["turbines_demo"]:
        window.myplaces.remove_many(state["turbines_demo"])
    result["turbines_demo"]["models_after"] = len(view.models.source)
    del _time


@check(1500)
def track_model():
    """Модель по треку: куб Collada едет по пути двух объектов слоя
    в памяти на момент шкалы времени, азимут - по ходу движения."""
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsVectorLayer
    from qgis.PyQt.QtCore import QDateTime
    from planetx.core.navigation import Pose
    from planetx.ui.track import seconds
    window = state["window"]
    window.set_body("earth")
    layer = QgsVectorLayer(
        "Point?crs=EPSG:4326&field=t:datetime&field=obj:string",
        "Трек модели", "memory")
    base = QDateTime.fromString("2026-10-18T10:00:00", "yyyy-MM-ddTHH:mm:ss")
    # Восточный объект идёт на восток, северный - на север, 600 м за 60 с.
    rows = [("east", 0, 58.0100, 56.2200), ("east", 60, 58.0100, 56.2302),
            ("north", 0, 58.0050, 56.2250), ("north", 60, 58.0104, 56.2250)]
    features = []
    for obj, dt, lat, lon in rows:
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
        f["t"] = base.addSecs(dt)
        f["obj"] = obj
        features.append(f)
    layer.dataProvider().addFeatures(features)
    QgsProject.instance().addMapLayer(layer)
    state["track_model_layer"] = layer
    path = _cube_dae(os.path.join(TEMP, "planetx_track_model"))
    t0 = seconds(base)
    state["track_model_t0"] = t0
    window.set_layer_shown(layer.id(), True)
    window.tracks.set_track(layer, {"time": "t", "object": "obj",
                                    "color": [255, 80, 40, 255],
                                    "follow": False, "model": path,
                                    "model_scale": 2.0, "model_turn": 0.0})
    _open_time(t0, t0 + 30)
    window.view.navigator.stop()
    window.view.navigator.show(Pose(58.0090, 56.2260, 2500.0, 0.0, 45.0))
    window.view.update()


@check(1500)
def track_model_check():
    import time as _time
    import numpy as np
    window = state["window"]
    view = window.view
    t0 = state["track_model_t0"]
    items = view.models.groups.get("tracks", [])
    out = {"models": len(items),
           "meshes": len({item.mesh for item in items})}

    def where():
        found = {}
        for item in items:
            moved = item.mover(_time.monotonic())
            if moved is None:
                continue
            lat, lon, linear = moved
            # Ось X модели (восток у исходного места) после поворота -
            # куда она смотрит: азимут по местным осям точки.
            from planetx.core.camera import enu
            axes = enu(lat, lon) @ (linear @ (np.linalg.inv(enu(0.0, 0.0))
                                              @ np.array([0.0, 1.0, 0.0])))
            heading = float(np.degrees(np.arctan2(axes[0], axes[1]))) % 360
            found[item.key[2]] = [round(lat, 5), round(lon, 5),
                                  round(heading, 1)]
        return found
    out["at_30s"] = where()
    window.timebar.set_range(t0, t0 + 45)
    QgsApplication.processEvents()
    out["at_45s"] = where()
    view.repaint()
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_track_model.png"))
    out["drawn"] = view.models.drawn
    window._time_toggled(False)
    window.toolbar.set_time_shown(False)
    window.tracks.set_track(state["track_model_layer"], None)
    QgsProject.instance().removeMapLayer(state["track_model_layer"].id())
    out["models_after"] = len(view.models.groups.get("tracks", []))
    out["gl"] = dict(view.gl_errors)
    result["track_model"] = out


@check(1500)
def track_height():
    """Высота трека: «самолёт» - Z точки над уровнем моря в футах,
    «дрон» - поле h над землёй в метрах. Модель встаёт на высоту,
    путь самолёта - в воздухе."""
    import time as _time
    from qgis.core import (QgsFeature, QgsGeometry, QgsPoint,
                           QgsVectorLayer)
    from qgis.PyQt.QtCore import QDateTime
    from planetx.core import ellipsoid
    from planetx.core.navigation import Pose
    from planetx.ui.track import FOOT, HEIGHT_Z, seconds
    window = state["window"]
    view = window.view
    base = QDateTime.fromString("2026-10-19T10:00:00", "yyyy-MM-ddTHH:mm:ss")
    t0 = seconds(base)
    out = {}
    path = _cube_dae(os.path.join(TEMP, "planetx_track_model"))
    plane = QgsVectorLayer("PointZ?crs=EPSG:4326&field=t:datetime",
                           "Самолёт", "memory")
    rows = [(0, 58.000, 56.200, 1000.0), (60, 58.010, 56.200, 5000.0)]
    features = []
    for dt, lat, lon, z in rows:
        f = QgsFeature(plane.fields())
        f.setGeometry(QgsGeometry(QgsPoint(lon, lat, z)))
        f["t"] = base.addSecs(dt)
        features.append(f)
    plane.dataProvider().addFeatures(features)
    drone = QgsVectorLayer("Point?crs=EPSG:4326&field=t:datetime"
                           "&field=h:double", "Дрон", "memory")
    features = []
    for dt, lat, lon, h in ((0, 58.005, 56.210, 100.0),
                            (60, 58.005, 56.220, 100.0)):
        f = QgsFeature(drone.fields())
        f.setGeometry(QgsGeometry(QgsPoint(lon, lat)))
        f["t"] = base.addSecs(dt)
        f["h"] = h
        features.append(f)
    drone.dataProvider().addFeatures(features)
    QgsProject.instance().addMapLayers([plane, drone])
    common = {"time": "t", "object": "", "color": [255, 80, 40, 255],
              "follow": False, "model": path, "model_scale": 1.0,
              "model_turn": 0.0}
    window.set_layer_shown(plane.id(), True)
    window.tracks.set_track(plane, dict(common, height=HEIGHT_Z,
                                        height_mode="absolute",
                                        height_unit=FOOT))
    window.set_layer_shown(drone.id(), True)
    window.tracks.set_track(drone, dict(common, height="h",
                                        height_mode="relative",
                                        height_unit=1.0))
    _open_time(t0, t0 + 30)
    view.navigator.stop()
    view.navigator.show(Pose(58.004, 56.205, 3000.0, 0.0, 70.0))
    view.update()
    QgsApplication.processEvents()
    items = {item.key[1]: item for item in
             view.models.groups.get("tracks", [])}
    scale = view.store.scale
    for name, layer in (("plane", plane), ("drone", drone)):
        item = items.get(layer.id())
        moved = item.mover(_time.monotonic()) if item else None
        if moved is None:
            out[name] = None
            continue
        item.place = (moved[0], moved[1], item.place[2],
                      moved[3] if len(moved) > 3 else 0.0)
        center = view._model_anchor(item)
        _, _, h = ellipsoid.ecef_to_geodetic(center)
        ground = view.store.height_at(moved[0], moved[1]) \
            if view.store.scale else 0.0
        out[name] = {"mode": item.place[2],
                     "alt_m": round(moved[3], 1) if len(moved) > 3
                     else None,
                     "center_h": round(float(h), 1),
                     "ground": round(float(ground), 1),
                     "relief_scale": scale}
    lines = [s for s in window.tracks.shapes() if s.kind == "line"]
    out["air_lines"] = [[round(a, 1) for a in s.alts] for s in lines
                        if s.alts]
    view.repaint()
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_track_height.png"))
    out["gl"] = dict(view.gl_errors)
    window._time_toggled(False)
    window.toolbar.set_time_shown(False)
    for layer in (plane, drone):
        window.tracks.set_track(layer, None)
        QgsProject.instance().removeMapLayer(layer.id())
    out["models_after"] = len(view.models.groups.get("tracks", []))
    result["track_height"] = out


@check(1000)
def trains_on():
    """Поезда Финляндии: строка включена, положения пришли со службы
    Digitraffic, издалека - точки с подписями."""
    from planetx.core.navigation import Pose
    window = state["window"]
    manager = window.train_manager
    look = state.setdefault("trains_on", {"since": None})
    if look["since"] is None:
        window.set_body("earth")
        window.view.navigator.stop()
        window.view.navigator.show(Pose(62.0, 25.5, 1500000.0, 0.0, 0.0))
        window.view.update()
        window.set_extra("trains", True)
        look["since"] = time.monotonic()
        return 1000
    waited = time.monotonic() - look["since"]
    if (not manager.count() or not manager.fleet.info) and waited < 40.0:
        return 1000
    window.view.grabFramebuffer().save(os.path.join(
        TEMP, "planetx_trains_far.png"))
    names = window.train_legend.rows()
    result["trains_on"] = {
        "waited": round(waited, 1), "trains": manager.count(),
        "typed": sum(1 for k in manager.fleet.trains
                     if k in manager.fleet.info),
        "points": len(manager.shapes()), "near": manager.near,
        "error": manager.error, "legend_rows": len(names),
        "legend_shown": window.train_legend.isVisible(),
        "credit": "digitraffic" in window.attribution.text().lower()}
    return None


@check(1000)
def trains_near():
    """Вблизи Хельсинки: рельсы из основы, модели вагонов едут по ним."""
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    manager = window.train_manager
    look = state.setdefault("trains_near", {"since": None})
    if look["since"] is None:
        view.navigator.stop()
        # Пути у Пасилы, к северу от главного вокзала.
        view.navigator.show(Pose(60.1990, 24.9330, 2500.0, 0.0, 55.0))
        view.update()
        look["since"] = time.monotonic()
        return 2000
    waited = time.monotonic() - look["since"]
    ready = manager.fleet.rails is not None and not manager.rail_replies \
        and view.models.groups.get("trains")
    if (not ready or view.load_missing) and waited < 60.0:
        return 1000
    result["trains_near"] = {"waited": round(waited, 1)}
    return None


@check(1000)
def trains_near_check():
    import time as _time
    import numpy as np
    from qgis.PyQt.QtTest import QTest
    from planetx.core import ellipsoid, routing, trains as core
    window = state["window"]
    view = window.view
    manager = window.train_manager
    fleet = manager.fleet
    out = result["trains_near"]
    items = view.models.groups.get("trains", [])
    out["near"] = manager.near
    out["models"] = len(items)
    out["meshes"] = len({item.mesh for item in items})
    out["rail_lines"] = len(fleet.rails) if fleet.rails is not None else 0
    out["points"] = len(manager.shapes())
    now, clock = _time.monotonic(), _time.time()
    snapped, gaps = 0, []
    for item in items:
        train = fleet.trains.get(tuple(item.key[1:3]))
        if train is None or item.key[3]:
            continue
        lat, lon, _ = fleet.place(train, now, clock)
        if train.rail is not None:
            snapped += 1
            x, y = routing.to_grid(lat, lon)
            found = fleet.rails.snap(x, y, 1e9)
            if found is not None:
                xy, _ = fleet.rails.point(*found)
                gaps.append(float(np.hypot(xy[0] - x, xy[1] - y))
                            * routing.unit_metres(lat))
    out["snapped"] = snapped
    out["rail_gap_m"] = round(max(gaps), 3) if gaps else None
    view.repaint()
    first = view.grabFramebuffer()
    out["drawn"] = view.models.drawn
    out["animated"] = view.models.animated
    QTest.qWait(1500)
    second = view.grabFramebuffer()
    second.save(os.path.join(TEMP, "planetx_trains_near.png"))

    def pixels(image):
        bits = image.constBits()
        bits.setsize(image.sizeInBytes())
        return np.frombuffer(bits, np.uint8).astype(np.int16)
    out["changed_share"] = round(float(
        (np.abs(pixels(first) - pixels(second)) > 30).mean()), 5)
    # Опрос щелчком у первой модели на экране.
    picked = None
    for item in items:
        if item.mover is None:
            continue
        moved = item.mover(_time.monotonic())
        if moved is None:
            continue
        lat, lon, _ = moved
        point = np.asarray([ellipsoid.geodetic_to_ecef(
            lat, lon, view.label_height(lat, lon))], dtype=np.float64)
        pixels_xy, front = view.camera.project(point)
        if front[0]:
            found = window._identify_trains(float(pixels_xy[0][0]),
                                            float(pixels_xy[0][1]))
            if found:
                picked = [found[0][1][0][0]] + [
                    v for v in found[0][1][0][1][:3]]
                break
    out["picked"] = picked
    out["gl"] = dict(view.gl_errors)
    del core


@check(1500)
def trains_off():
    window = state["window"]
    window.set_extra("trains", False)
    QgsApplication.processEvents()
    manager = window.train_manager
    result["trains_off"] = {
        "trains": manager.count(),
        "models": len(window.view.models.groups.get("trains", [])),
        "points": len(manager.shapes()),
        "polling": manager.poll.isActive(),
        "legend_shown": window.train_legend.isVisible()}


@check(1000)
def trains_demo():
    """Демо «Поезда Финляндии, вживую»: строка поездов из сцены, камера
    над путями у Пасилы, модели вагонов на рельсах."""
    window = state["window"]
    view = window.view
    look = state.setdefault("trains_demo", {"since": None})
    if look["since"] is None:
        action = next(a for a in window.toolbar.demo.menu().actions()
                      if a.text() in ("Поезда Финляндии, вживую",
                                      "Trains of Finland, live"))
        folders = {f.key for f in window.myplaces.folders}
        action.trigger()
        look["folders"] = [f.key for f in window.myplaces.folders
                           if f.key not in folders]
        look["since"] = time.monotonic()
        return 3000
    manager = window.train_manager
    waited = time.monotonic() - look["since"]
    ready = manager.on and manager.near and manager.fleet.rails is not None \
        and not manager.rail_replies and view.models.drawn
    if (not ready or view.load_missing) and waited < 60.0:
        return 1000
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_trains_demo.png"))
    result["trains_demo"] = {
        "waited": round(waited, 1), "on": window.extras.get("trains"),
        "near": manager.near, "drawn": view.models.drawn,
        "rails": len(manager.fleet.rails) if manager.fleet.rails else 0,
        "camera": [round(view.navigator.pose.lat, 4),
                   round(view.navigator.pose.lon, 4)],
        "gl": dict(view.gl_errors)}
    if look["folders"]:
        window.myplaces.remove_many(look["folders"])
    window.set_extra("trains", False)
    result["trains_demo"]["models_after"] = len(
        view.models.groups.get("trains", []))
    return None


@check(1000, manual=True)
def post_trains_video():
    """Ролик поездов для поста: демо «Поезда Финляндии, вживую», облёт
    над путями у Пасилы, кадры со знаком PlanetX и подписью источников.
    Поезда идут по часам съёмки - кадр ровно 1/25 с хода.
    PLANETX_POST_POSE - широта, долгота, расстояние, азимут, наклон,
    PLANETX_POST_ORBIT - градусы азимута за ролик и секунды."""
    import ctypes
    from qgis.PyQt.QtCore import Qt as _Qt
    from qgis.PyQt.QtGui import QImage
    from qgis.PyQt.QtTest import QTest
    from planetx.core import video
    from planetx.core.navigation import Pose
    from planetx.ui.snapshot import draw_attribution, plain_text
    window = state["window"]
    view = window.view
    manager = window.train_manager
    look = state.setdefault("post_trains", {"since": None})
    pose = Pose(*[float(v) for v in os.environ.get(
        "PLANETX_POST_POSE", "60.1925,24.9318,1100,345,62").split(",")])
    if look["since"] is None:
        # Своя основа прерванного шага sources_vector в подписи ролика
        # не нужна.
        from qgis.core import QgsSettings
        from planetx.core import sources as _sources
        QgsSettings().remove(_sources.VECTOR_KEY)
        QgsSettings().remove(_sources.VECTOR_CREDIT_KEY)
        window.sources_changed("vector")
        action = next(a for a in window.toolbar.demo.menu().actions()
                      if a.text() in ("Поезда Финляндии, вживую",
                                      "Trains of Finland, live"))
        action.trigger()
        look["since"] = time.monotonic()
        return 4000
    if not look.get("posed"):
        view.navigator.stop()
        view.navigator.show(pose)
        view.update()
        look["posed"] = time.monotonic()
        return 2000
    waited = time.monotonic() - look["posed"]
    ready = manager.near and manager.fleet.rails is not None \
        and not manager.rail_replies and view.models.drawn
    # Вид прибывших поездов приходит по одному за несколько опросов.
    if (not ready or view.load_missing or waited < 40.0) and waited < 90.0:
        return 1000
    fps, seconds, turn = 25, 16.0, 0.0
    orbit = os.environ.get("PLANETX_POST_ORBIT", "50,16")
    if orbit:
        turn, seconds = (float(v) for v in orbit.split(","))
    first = view.grabFramebuffer()
    width, height = video.even_size(first.width() // 2,
                                    first.height() // 2)
    out = os.path.join(TEMP, "planetx_post_trains.mp4")
    writer = video.Mp4Writer(out, width, height, fps)
    manager.freeze()
    try:
        for k in range(int(fps * seconds)):
            share = k / (fps * seconds)
            view.navigator.show(Pose(pose.lat, pose.lon, pose.distance,
                                     (pose.heading + turn * share) % 360.0,
                                     pose.tilt))
            view.update()
            QTest.qWait(30)
            started = time.monotonic()
            while view.load_missing and time.monotonic() - started < 3.0:
                QTest.qWait(50)
            view.repaint()
            image = view.grabFramebuffer().scaled(
                width, height, _Qt.AspectRatioMode.IgnoreAspectRatio,
                _Qt.TransformationMode.SmoothTransformation)
            image = image.convertToFormat(QImage.Format.Format_RGB32)
            image.setDevicePixelRatio(1.0)
            draw_attribution(image, plain_text(
                window.attribution.text()), 1.0)
            if k == 0:
                image.save(os.path.join(TEMP, "planetx_post_trains.png"))
            bits = image.constBits()
            bits.setsize(image.sizeInBytes())
            frame = bytearray(bytes(bits))
            holder = ctypes.c_char.from_buffer(frame)
            writer.write(ctypes.addressof(holder))
            del holder
            manager.step_clock(1.0 / fps)
    finally:
        writer.close()
        manager.unfreeze()
    result["post_trains"] = {"frames": writer.count, "size": [width, height],
                             "models": len(view.models.groups.get(
                                 "trains", [])),
                             "drawn": view.models.drawn,
                             "waited": round(waited, 1)}
    return None


def _ease(t, keys):
    """Значение по опорным точкам [(время, значение)] с плавным
    переходом половиной косинуса между ними."""
    if t <= keys[0][0]:
        return keys[0][1]
    for (t0, v0), (t1, v1) in zip(keys, keys[1:]):
        if t <= t1:
            share = (t - t0) / (t1 - t0) if t1 > t0 else 1.0
            share = 0.5 - 0.5 * math.cos(math.pi * share)
            return v0 + (v1 - v0) * share
    return keys[-1][1]


@check(1000, manual=True)
def post_cockpit_video():
    """Ролик полёта из кабины для поста: истребитель над долиной
    Церматта к Маттерхорну, приборы на стекле, знак PlanetX и подпись
    источников. Полёт идёт шагами по 1/25 с ролика, крен и тангаж -
    плавный график _ease. PLANETX_POST_FLIGHT - широта, долгота,
    высота над уровнем моря, курс, PLANETX_POST_SECONDS - длина."""
    import ctypes
    from qgis.PyQt.QtCore import QPoint, Qt as _Qt
    from qgis.PyQt.QtGui import QImage, QPainter, QRegion
    from qgis.PyQt.QtTest import QTest
    from qgis.PyQt.QtWidgets import QWidget
    from planetx.core import flightsim as core_flight, video
    from planetx.ui.snapshot import draw_attribution, plain_text
    window = state["window"]
    view = window.view
    flight = window.flight
    look = state.setdefault("post_cockpit", {"since": None})
    lat, lon, alt, heading = [float(v) for v in os.environ.get(
        "PLANETX_POST_FLIGHT", "46.06,7.79,4300,212").split(",")]
    seconds = float(os.environ.get("PLANETX_POST_SECONDS", "16"))
    if look["since"] is None:
        flight.start(lat, lon, core_flight.FIGHTER)
        flight.timer.stop()
        plane = flight.plane
        plane.alt = alt
        plane.heading = heading
        plane.pitch = -3.0
        flight.set_cockpit(True)
        flight._follow(flight._ground(plane.lat, plane.lon))
        look["since"] = time.monotonic()
        return 3000
    waited = time.monotonic() - look["since"]
    if view.load_missing and waited < 60.0:
        return 1000
    fps = 25
    rolls = [(0.0, 0.0), (3.0, 0.0), (5.0, 35.0), (10.0, 35.0),
             (12.0, 0.0), (14.0, -20.0), (16.0, 0.0)]
    pitches = [(0.0, -3.0), (6.0, -3.0), (9.0, 0.0), (13.0, 4.0),
               (16.0, 2.0)]
    first = view.grabFramebuffer()
    width, height = video.even_size(first.width() // 2,
                                    first.height() // 2)
    ratio = first.width() / max(view.width(), 1)
    out = os.path.join(TEMP, "planetx_post_cockpit.mp4")
    writer = video.Mp4Writer(out, width, height, fps)
    plane = flight.plane
    lows = []
    try:
        for k in range(int(fps * seconds)):
            t = k / float(fps)
            share = t * 16.0 / seconds
            plane.roll = _ease(share, rolls)
            plane.pitch = _ease(share, pitches)
            ground = flight._ground(plane.lat, plane.lon)
            core_flight.step(plane, 1.0 / fps, ground=ground)
            if plane.crashed:
                break
            ground = flight._ground(plane.lat, plane.lon)
            lows.append(plane.alt - ground)
            flight._follow(ground)
            out_state = core_flight.readout(plane, ground)
            out_state["pitch"] = plane.pitch
            out_state["roll"] = plane.roll
            flight.hud.set_state(out_state)
            QTest.qWait(30)
            started = time.monotonic()
            while view.load_missing and time.monotonic() - started < 3.0:
                QTest.qWait(50)
            view.repaint()
            image = view.grabFramebuffer().convertToFormat(
                QImage.Format.Format_ARGB32_Premultiplied)
            image.setDevicePixelRatio(ratio)
            painter = QPainter(image)
            # Без фона окна - иначе серый фон закрыл бы кадр.
            flight.hud.render(painter, QPoint(0, 0), QRegion(),
                              QWidget.RenderFlag.DrawChildren)
            painter.end()
            image.setDevicePixelRatio(1.0)
            image = image.scaled(
                width, height, _Qt.AspectRatioMode.IgnoreAspectRatio,
                _Qt.TransformationMode.SmoothTransformation)
            image = image.convertToFormat(QImage.Format.Format_RGB32)
            draw_attribution(image, plain_text(
                window.attribution.text()), 1.0)
            if k == int(fps * 6):
                image.save(os.path.join(TEMP, "planetx_post_cockpit.png"))
            bits = image.constBits()
            bits.setsize(image.sizeInBytes())
            frame = bytearray(bytes(bits))
            holder = ctypes.c_char.from_buffer(frame)
            writer.write(ctypes.addressof(holder))
            del holder
    finally:
        writer.close()
    result["post_cockpit"] = {
        "frames": writer.count, "size": [width, height],
        "crashed": plane.crashed, "lowest_m": round(min(lows), 0)
        if lows else None, "heading": round(plane.heading, 1),
        "waited": round(waited, 1), "gl": dict(view.gl_errors)}
    flight.stop()
    return None


@check(4000)
def altitude_modes():
    """Режимы высоты метки: окно свойств над Чёрным морем ставит
    «Вдоль морского дна», режим пишется в файл меток и в KML."""
    from planetx.core.features import Shape
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    window.set_body("earth")
    window.set_sea_depths(True)
    view.navigator.stop()
    view.navigator.show(Pose(43.0, 34.0, 40000.0, 0.0, 45.0))
    view.update()
    store = window.myplaces
    old = [p.key for p in store.places if p.name.startswith("Режим высоты")]
    if old:
        store.remove_many(old)
    store.add(Shape("point", [(43.0, 34.0)], name="Режим высоты"))
    store.add(Shape("line", [(42.95, 33.95), (43.05, 34.05)],
                    name="Режим высоты, путь"))
    state["alt_keys"] = [p.key for p in store.places
                         if p.name.startswith("Режим высоты")]
    result["altitude_modes"] = {}


@check(500)
def altitude_modes_check():
    """Режим из окна: точка на дне, путь на дне, абсолютная точка на
    своей высоте, KML переносит режимы."""
    from planetx.core import features as core_features, kml
    from planetx.render.features import build
    window = state["window"]
    view = window.view
    store = window.myplaces
    out = result["altitude_modes"]
    keys = state["alt_keys"]
    point = [p for p in store.places if p.key in keys
             and p.shape.kind == "point"][0]
    line = [p for p in store.places if p.key in keys
            and p.shape.kind == "line"][0]
    window._place_action("properties", point.key)
    dialog = window.prop_dialogs[point.key]
    out["modes"] = [dialog.altmode.itemData(i)
                    for i in range(dialog.altmode.count())]
    dialog.altmode.setCurrentIndex(dialog.altmode.findData(
        core_features.SEAFLOOR))
    out["lift_enabled_on_floor"] = dialog.lift.isEnabled()
    out["preview_mode"] = [s.mode for s in view.features.shapes
                           if s.name == "Режим высоты"]
    dialog.accept()
    QgsApplication.processEvents()
    window._place_action("properties", line.key)
    dialog = window.prop_dialogs[line.key]
    dialog.altmode.setCurrentIndex(dialog.altmode.findData(
        core_features.SEAFLOOR))
    dialog.accept()
    QgsApplication.processEvents()
    saved = {p.shape.kind: p for p in store.places if p.key in keys}
    out["saved"] = {k: p.shape.mode for k, p in saved.items()}
    floor = float(view.store.heights_at([43.0], [34.0])[0])
    surface = float(view.label_heights([43.0], [34.0])[0])
    out["floor_m"] = round(floor, 1)
    out["surface_m"] = round(surface, 1)
    built = build(saved["line"].shape, view.store.heights_at,
                  surface_at=view.label_heights,
                  scale=view.store.scale or 1.0)
    center, offsets = built[0], built[1]
    from planetx.core.ellipsoid import ecef_to_geodetic
    h = ecef_to_geodetic(center + offsets[0])[2]
    lat0, lon0 = saved["line"].shape.points[0]
    out["line_on_floor"] = round(float(h) - float(view.store.heights_at(
        [lat0], [lon0])[0]), 2)
    marks = [m for m in view._own_marks() if m.name == "Режим высоты"]
    out["mark_base"] = marks[0].base if marks else None
    # Абсолютная высота точки - через файл меток, как окно.
    store.update(saved["point"].key, {"altmode": core_features.ABSOLUTE,
                                      "height": 1500.0})
    QgsApplication.processEvents()
    window._refresh_shapes()
    marks = [m for m in view._own_marks() if m.name == "Режим высоты"]
    out["abs_mark"] = (marks[0].base, round(marks[0].lift, 1)) \
        if marks else None
    text = kml.write_kml(kml.KFolder("x", True, [
        _kplace_of(store, p) for p in saved.values()]))
    back = kml.read_kml(text.encode("utf-8")).children
    out["kml_modes"] = sorted((p.kind, p.mode) for p in back)
    view.repaint()
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_altitude_modes.png"))
    store.remove_many([p.key for p in saved.values()])
    out["gl"] = dict(view.gl_errors)


def _kplace_of(store, place):
    from planetx.ui.myplaces import _kplace
    return _kplace(store.find(place.key))


@check(1000, manual=True)
def post_haul_video():
    """Ролик проезда с самосвалом для поста: демо «Самосвалы, Качканар»,
    камера следом за первым самосвалом от погрузки вверх по съезду,
    знак PlanetX и подпись источников. Момент треков - шагами по
    1/25 с ролика с ускорением PLANETX_POST_RATE, PLANETX_HAUL - демо,
    PLANETX_POST_SECONDS - длина, PLANETX_POST_TILT - наклон."""
    import ctypes
    from qgis.core import QgsProject
    from qgis.PyQt.QtCore import Qt as _Qt
    from qgis.PyQt.QtGui import QImage
    from qgis.PyQt.QtTest import QTest
    from planetx.core import video
    from planetx.core.navigation import Pose
    from planetx.ui.snapshot import draw_attribution, plain_text
    from planetx.ui.track import seconds as field_seconds
    window = state["window"]
    view = window.view
    tracks = window.tracks
    look = state.setdefault("post_haul", {"since": None})
    rate = float(os.environ.get("PLANETX_POST_RATE", "12"))
    length = float(os.environ.get("PLANETX_POST_SECONDS", "20"))
    tilt = float(os.environ.get("PLANETX_POST_TILT", "62"))
    if look["since"] is None:
        # Своя основа прерванного шага sources_vector в подписи ролика
        # не нужна.
        from qgis.core import QgsSettings
        from planetx.core import sources as _sources
        QgsSettings().remove(_sources.VECTOR_KEY)
        QgsSettings().remove(_sources.VECTOR_CREDIT_KEY)
        window.sources_changed("vector")
        window.set_body("earth")
        # Папки демо прежних прогонов дали бы чужие метки в кадре.
        old = [f.key for f in window.myplaces.folders
               if f.name.startswith("PlanetX: демо, самосвалы")]
        if old:
            window.myplaces.remove_many(old)
        window.open_demo(os.environ.get("PLANETX_HAUL", "haul_kachkanar"))
        look["since"] = time.monotonic()
        return 3000
    if not look.get("start"):
        if not tracks._at and time.monotonic() - look["since"] < 60.0:
            return 1000
        timer = getattr(window, "_haul_timer", None)
        if timer is not None:
            timer.stop()
        if window.timebar.timer.isActive():
            window.timebar.toggle()
        layer_id = next(iter(tracks.tracks))
        layer = QgsProject.instance().mapLayer(layer_id)
        key = sorted(k for k in tracks._at if k[0] == layer_id)[0]
        rows = sorted((field_seconds(f["time"]), f["loaded"],
                       f.geometry().asPoint())
                      for f in layer.getFeatures()
                      if str(f["truck"]) == key[1])
        # Начало подъёма - первая гружёная точка, после которой
        # самосвал сдвинулся, за 8 с до неё - конец погрузки.
        start = rows[0][0]
        for a, b in zip(rows, rows[1:]):
            if a[1] and a[2] != b[2]:
                start = a[0] - 8.0 * rate / 10.0
                break
        look["start"], look["key"] = start, key
        tracks.set_moment(start)
        tracks.set_follow(key)
        tracks.follow_timer.stop()
        lat, lon = tracks._at[key][:2]
        view.navigator.stop()
        view.navigator.show(Pose(lat, lon, 400.0, 0.0, tilt))
        tracks._chase_step()
        view.update()
        look["posed"] = time.monotonic()
        return 2000
    waited = time.monotonic() - look["posed"]
    if view.load_missing and waited < 60.0:
        return 1000
    fps = 25
    reaches = [(0.0, 420.0), (4.0, 140.0), (length - 4.0, 140.0),
               (length, 260.0)]
    first = view.grabFramebuffer()
    width, height = video.even_size(first.width() // 2,
                                    first.height() // 2)
    out = os.path.join(TEMP, "planetx_post_haul.mp4")
    writer = video.Mp4Writer(out, width, height, fps)
    key = look["key"]
    path = []
    try:
        for k in range(int(fps * length)):
            t = k / float(fps)
            tracks.set_moment(look["start"] + t * rate)
            tracks.chase.reach = _ease(t, reaches)
            pose = view.navigator.pose
            view.navigator.show(Pose(pose.lat, pose.lon, pose.distance,
                                     pose.heading, tilt))
            tracks._chase_step()
            if tracks.followed is None:
                break
            path.append(tracks._at[key][:2])
            QTest.qWait(30)
            started = time.monotonic()
            while view.load_missing and time.monotonic() - started < 3.0:
                QTest.qWait(50)
            view.repaint()
            image = view.grabFramebuffer().scaled(
                width, height, _Qt.AspectRatioMode.IgnoreAspectRatio,
                _Qt.TransformationMode.SmoothTransformation)
            image = image.convertToFormat(QImage.Format.Format_RGB32)
            image.setDevicePixelRatio(1.0)
            draw_attribution(image, plain_text(
                window.attribution.text()), 1.0)
            if k == int(fps * 8):
                image.save(os.path.join(TEMP, "planetx_post_haul.png"))
            bits = image.constBits()
            bits.setsize(image.sizeInBytes())
            frame = bytearray(bytes(bits))
            holder = ctypes.c_char.from_buffer(frame)
            writer.write(ctypes.addressof(holder))
            del holder
    finally:
        writer.close()
        tracks.set_follow(None)
        tracks.release()
    moved = 0.0
    for (a, b), (c, d) in zip(path, path[1:]):
        moved += math.hypot((c - a) * 111320.0,
                            (d - b) * 111320.0 * math.cos(math.radians(a)))
    result["post_haul"] = {"frames": writer.count, "size": [width, height],
                           "truck": key[1], "moved_m": round(moved),
                           "drawn": view.models.drawn,
                           "waited": round(waited, 1),
                           "gl": dict(view.gl_errors)}
    return None


@check(1000)
def trains_record():
    """Запись облёта с поездами: часы поездов идут по шкале записи,
    кадр - 1/25 с, после записи - снова часы компьютера."""
    import time as _time
    from planetx.core.tour import Stop
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    manager = window.train_manager
    look = state.setdefault("trains_record", {"since": None})
    if look["since"] is None:
        window.set_extra("trains", True)
        view.navigator.stop()
        view.navigator.show(Pose(60.1972, 24.9338, 650.0, 330.0, 62.0))
        view.update()
        look["since"] = _time.monotonic()
        return 2000
    waited = _time.monotonic() - look["since"]
    ready = manager.near and manager.fleet.rails is not None \
        and not manager.rail_replies and view.models.drawn
    if not look.get("started"):
        if not ready and waited < 60.0:
            return 1000
        clocks = look["clocks"] = []
        original = manager.set_clock

        def spy(seconds):
            original(seconds)
            clocks.append(manager.frozen[1])
        manager.set_clock = spy
        if os.path.exists(TRAINS_VIDEO):
            os.remove(TRAINS_VIDEO)
        state["record_done"] = None
        if "record_link" not in state:
            state["record_link"] = window.recorder.done.connect(
                lambda ok, text: state.__setitem__("record_done",
                                                   (ok, text)))
        window.tour.bar.pause.setValue(0.4)
        window.tour.start([Stop("A", 60.1972, 24.9338, 650.0, 330.0, 62.0),
                           Stop("B", 60.1990, 24.9330, 700.0, 350.0, 60.0)])
        look["polling_before"] = manager.poll.isActive()
        look["began"] = window.record_tour(TRAINS_VIDEO, "video")
        look["started"] = _time.monotonic()
        return 1000
    if window.recorder.active and _time.monotonic() - look["started"] < 600:
        if look.get("polling_during") is None:
            look["polling_during"] = manager.poll.isActive()
        return 1000
    del manager.set_clock
    clocks = look["clocks"]
    steps = [round(b - a, 4) for a, b in zip(clocks, clocks[1:])]
    result["trains_record"] = {
        "began": look["began"], "done": state["record_done"],
        "frames": len(clocks), "steps": sorted(set(steps))[:5],
        "polling_before": look["polling_before"],
        "polling_during": look.get("polling_during"),
        "frozen_after": manager.frozen is not None,
        "polling_after": manager.poll.isActive(),
        "bytes": os.path.getsize(TRAINS_VIDEO)
        if os.path.exists(TRAINS_VIDEO) else 0,
        "gl": dict(view.gl_errors)}
    window.set_extra("trains", False)
    return None


TRAINS_VIDEO = os.path.join(TEMP, "planetx_trains_tour.mp4")


@check(1000)
def trains_close():
    """Ответы службы после закрытия окна окна не трогают: менеджер
    выключен, ждущие запросы сняты. 19 октября 2026 года ответ после
    перезагрузки модуля звал удалённое окно (RuntimeError)."""
    window = state["window"]
    manager = window.train_manager
    window.set_extra("trains", True)
    QgsApplication.processEvents()
    calls = []
    original = window._refresh_shapes
    window._refresh_shapes = lambda: calls.append(1)
    try:
        pending = manager.reply is not None
        manager.close()
        manager._latest(b"[]", "")
        manager._types({"data": {"currentlyRunningTrains": []}}, "")
        manager._one((1, "2026-10-19"), [], "")
    finally:
        window._refresh_shapes = original
    result["trains_close"] = {"pending_before": pending,
                              "window_calls": len(calls),
                              "on": manager.on,
                              "reply": manager.reply is not None,
                              "polling": manager.poll.isActive()}
    window.set_extra("trains", False)


def _live_wait(name, key, pose, ready, limit=60.0):
    """Общий ход шагов судов и самолётов: включить строку, поставить
    позу, ждать ready() не дольше limit секунд. Возвращает паузу шага
    или None, когда пора проверять."""
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    look = state.setdefault(name, {"since": None})
    if look["since"] is None:
        window.set_body("earth")
        if key:
            window.set_extra(key, True)
        view.navigator.stop()
        view.navigator.show(Pose(*pose))
        view.update()
        look["since"] = time.monotonic()
        return 2000
    look["waited"] = round(time.monotonic() - look["since"], 1)
    if not ready() and look["waited"] < limit:
        return 1000
    return None


def _live_pick(window, manager):
    """Опрос щелчком у первой точки или модели на экране."""
    import numpy as np
    from planetx.core import ellipsoid
    view = window.view
    now = time.monotonic()
    for key, lat, lon, _, alt in manager.fleet.positions(now):
        height = alt * view.store.scale if alt == alt \
            else view.label_height(lat, lon)
        point = np.asarray([ellipsoid.geodetic_to_ecef(lat, lon, height)])
        pixels, front = view.camera.project(point)
        if not front[0] or not (0 <= pixels[0][0] < view.camera.width
                                and 0 <= pixels[0][1] < view.camera.height):
            continue
        found = window._identify_live(float(pixels[0][0]),
                                      float(pixels[0][1]))
        if found:
            name, values, _ = found[0][1][0]
            return [name] + [list(v) for v in values[:4]]
    return None


@check(1000)
def vessels_on():
    """Суда Балтики издалека: положения Digitraffic, сведения о судах,
    точки с названиями."""
    window = state["window"]
    manager = window.vessel_manager
    pause = _live_wait("vessels_on", "vessels",
                       (60.0, 23.5, 400000.0, 0.0, 0.0),
                       lambda: len(manager.fleet) and manager.fleet.info)
    if pause:
        return pause
    window.view.grabFramebuffer().save(os.path.join(TEMP,
                                                    "planetx_vessels.png"))
    groups = {}
    for key in manager.fleet.items:
        group = manager.group_of(key)
        groups[group] = groups.get(group, 0) + 1
    result["vessels_on"] = {
        "waited": state["vessels_on"]["waited"],
        "ships": len(manager.fleet), "info": len(manager.fleet.info),
        "groups": groups, "points": len(manager.shapes()),
        "near": manager.near, "error": manager.error,
        "legend": window.vessel_legend.isVisible(),
        "credit": "digitraffic" in window.attribution.text().lower()}
    return None


@check(1000)
def vessels_near():
    """Суда у Хельсинки вблизи: модели своей длины на воде."""
    window = state["window"]
    view = window.view
    manager = window.vessel_manager
    pause = _live_wait("vessels_near", None,
                       (60.150, 24.960, 4000.0, 0.0, 55.0),
                       lambda: view.models.groups.get("vessels")
                       and not view.load_missing)
    if pause:
        return pause
    view.repaint()
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_vessels_near.png"))
    items = view.models.groups.get("vessels", [])
    heights = []
    for item in items[:20]:
        moved = item.mover(time.monotonic())
        if moved is not None:
            heights.append(round(moved[3], 1))
    result["vessels_near"] = {
        "waited": state["vessels_near"]["waited"], "near": manager.near,
        "models": len(items), "drawn": view.models.drawn,
        "heights": sorted(set(heights))[:6],
        "picked": _live_pick(window, manager),
        "gl": dict(view.gl_errors)}
    window.set_extra("vessels", False)
    result["vessels_near"]["after"] = [
        len(view.models.groups.get("vessels", [])), len(manager.shapes()),
        manager.poll.isActive(), window.vessel_legend.isVisible()]
    return None


@check(1000, manual=True)
def vessels_look():
    """Кадр крупного судна вблизи: модель глазами. Ручной шаг после
    vessels_on, PLANETX_LOOK_DISTANCE - расстояние камеры, м."""
    from planetx.core import ellipsoid
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    manager = window.vessel_manager
    look = state.setdefault("vessels_look", {"since": None})
    if look["since"] is None:
        manager.set_on(True)
        window.set_extra("vessels", True)
        moving = [(item.sample.speed, key)
                  for key, item in manager.fleet.items.items()
                  if manager.group_of(key) in ("passenger", "cargo")]
        if not moving:
            return 2000
        _, key = max(moving)
        look["key"] = key
        sample = manager.fleet.items[key].sample
        view.navigator.stop()
        view.navigator.show(Pose(sample.lat, sample.lon, float(
            os.environ.get("PLANETX_LOOK_DISTANCE", "600")), 30.0, 60.0))
        view.update()
        look["since"] = time.monotonic()
        return 2000
    waited = time.monotonic() - look["since"]
    if (view.load_missing or waited < 10.0) and waited < 40.0:
        return 1000
    key = look["key"]
    item = manager.fleet.items.get(key)
    lat, lon, heading, alt = manager.fleet.place(item, time.monotonic(),
                                                 time.time())
    view.navigator.show(Pose(lat, lon, view.navigator.pose.distance, 30.0,
                             60.0))
    view.repaint()
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_vessel_look.png"))
    result["vessels_look"] = {
        "name": manager.label(key), "group": manager.group_of(key),
        "size": manager.size(key), "ground": round(manager._ground(lat,
                                                                   lon), 1),
        "store_h": round(view.store.height_at(lat, lon), 1),
        "sea_floor": view.sea_floor, "drawn": view.models.drawn,
        "speed_kn": round(item.sample.speed / 0.514444, 1)}
    return None


@check(1000)
def aircraft_on():
    """Самолёты у Хельсинки: борта adsb.lol в круге у точки взгляда,
    в воздухе - на своей высоте."""
    window = state["window"]
    manager = window.aircraft_manager
    pause = _live_wait("aircraft_on", "aircraft",
                       (60.32, 24.96, 150000.0, 0.0, 0.0),
                       lambda: len(manager.fleet))
    if pause:
        return pause
    window.view.grabFramebuffer().save(os.path.join(TEMP,
                                                    "planetx_aircraft.png"))
    airborne = [item.sample.alt for item in manager.fleet.items.values()
                if item.sample.alt == item.sample.alt]
    air_points = [s for s in manager.shapes() if s.alts]
    result["aircraft_on"] = {
        "waited": state["aircraft_on"]["waited"],
        "aircraft": len(manager.fleet), "airborne": len(airborne),
        "highest_m": round(max(airborne), 0) if airborne else None,
        "points": len(manager.shapes()), "air_points": len(air_points),
        "url": manager.url(), "error": manager.error,
        "credit": "adsb.lol" in window.attribution.text(),
        "picked": _live_pick(window, manager)}
    return None


@check(1000)
def aircraft_near():
    """Самолёты вблизи аэропорта Хельсинки-Вантаа: модели на высоте
    борта, на земле - на рельефе."""
    window = state["window"]
    view = window.view
    manager = window.aircraft_manager
    pause = _live_wait("aircraft_near", None,
                       (60.3172, 24.9633, 6000.0, 0.0, 50.0),
                       lambda: manager.near and not view.load_missing,
                       limit=30.0)
    if pause:
        return pause
    items = view.models.groups.get("aircraft", [])
    rows = []
    for item in items[:10]:
        moved = item.mover(time.monotonic())
        fleet_item = manager.fleet.items.get(item.key[1])
        if moved is None or fleet_item is None:
            continue
        rows.append([item.key[1], round(moved[3], 0),
                     None if fleet_item.sample.alt != fleet_item.sample.alt
                     else round(fleet_item.sample.alt, 0)])
    view.repaint()
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_aircraft_near.png"))
    result["aircraft_near"] = {
        "waited": state["aircraft_near"]["waited"], "near": manager.near,
        "models": len(items), "drawn": view.models.drawn,
        "model_vs_sample_alt": rows, "gl": dict(view.gl_errors)}
    return None


@check(1000)
def aircraft_follow():
    """Камера следом за самолётом на 10 км и точка у далёкого борта
    вблизи. Борт условный: положение подставлено в менеджер, служба
    на шаг не влияет."""
    import numpy as np
    from planetx.core import ellipsoid, movers
    from planetx.core.aircraft import Info
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    manager = window.aircraft_manager
    look = state.setdefault("aircraft_follow", {"since": None})
    if look["since"] is None:
        window.set_extra("aircraft", True)
        manager.poll.stop()
        view.navigator.stop()
        view.navigator.show(Pose(60.20, 24.80, 4000.0, 0.0, 60.0))
        view.update()
        now = time.time()
        manager.fleet.items.clear()
        manager.fleet.update([
            movers.Sample("test1", now, 60.20, 24.80, 230.0, 90.0, 90.0,
                          10000.0, 0.0),
            movers.Sample("test2", now, 60.30, 24.90, 120.0, 180.0, 180.0,
                          3000.0, 0.0)], time.monotonic(), keep=True)
        manager.fleet.info.update({
            "test1": Info("TEST1", "", "A320", "A3"),
            "test2": Info("TEST2", "", "A320", "A3")})
        manager._rebuild(force=True)
        look["points_near"] = sorted(
            (s.name, round(s.height, 0)) for s in manager.shapes())
        manager.set_follow("test1")
        look["since"] = time.monotonic()
        return 1500
    pose = view.navigator.pose
    lat, lon, heading, alt = manager.where("test1")
    point = np.asarray([ellipsoid.geodetic_to_ecef(
        lat, lon, alt * view.store.scale)], dtype=np.float64)
    pixels, front = view.camera.project(point)
    centre = (view.camera.width / 2.0, view.camera.height / 2.0)
    view.repaint()
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_aircraft_follow.png"))
    result["aircraft_follow"] = {
        "points_near": look["points_near"],
        "followed": manager.followed, "heading": round(pose.heading, 1),
        "distance": round(pose.distance, 0), "tilt": round(pose.tilt, 1),
        "on_screen_px": [round(float(pixels[0][0] - centre[0]), 1),
                         round(float(pixels[0][1] - centre[1]), 1)],
        "front": bool(front[0]), "frame": view.camera.height}
    probe = np.asarray([
        ellipsoid.geodetic_to_ecef(pose.lat, pose.lon, 0.0),
        ellipsoid.geodetic_to_ecef(lat, lon, 0.0)], dtype=np.float64)
    px2, _ = view.camera.project(probe)
    result["aircraft_follow"]["look_px"] = [round(float(v), 1)
                                              for v in px2[0]]
    result["aircraft_follow"]["ground_px"] = [round(float(v), 1)
                                                for v in px2[1]]
    result["aircraft_follow"]["size"] = [view.camera.width,
                                           view.camera.height]
    eye = ellipsoid.ecef_to_geodetic(np.asarray(view.camera.eye))
    result["aircraft_follow"]["eye"] = [round(float(v), 4) for v in eye]
    result["aircraft_follow"]["plane"] = [round(lat, 4), round(lon, 4),
                                            round(alt, 0)]
    result["aircraft_follow"]["look"] = [round(pose.lat, 4),
                                           round(pose.lon, 4)]
    result["aircraft_follow"]["models"] = [
        [item.key[1], item.mover(time.monotonic()) is not None]
        for item in view.models.groups.get("aircraft", [])]
    result["aircraft_follow"]["drawn"] = view.models.drawn
    # Колесо в камере следом: два щелчка ближе - расстояние до самолёта
    # 0.64 прежнего, поза вида не гасит его. Esc отпускает камеру.
    from qgis.PyQt.QtCore import QEvent, QPoint, QPointF, Qt
    from qgis.PyQt.QtGui import QKeyEvent, QWheelEvent
    from qgis.PyQt.QtWidgets import QApplication
    from planetx.qt_compat import enum
    before = manager.chase.reach
    centre = QPointF(view.width() / 2.0, view.height() / 2.0)
    QApplication.sendEvent(view, QWheelEvent(
        centre, QPointF(view.mapToGlobal(centre.toPoint())), QPoint(0, 0),
        QPoint(0, 240), enum(Qt, "MouseButton", "NoButton"),
        enum(Qt, "KeyboardModifier", "NoModifier"),
        enum(Qt, "ScrollPhase", "NoScrollPhase"), False))
    manager._follow_step()
    plane = np.asarray([ellipsoid.geodetic_to_ecef(
        lat, lon, alt * view.store.scale)], dtype=np.float64)
    eye_gap = float(np.linalg.norm(np.asarray(view.camera.eye) - plane[0]))
    result["aircraft_follow"]["wheel"] = [round(before, 0),
                                          round(manager.chase.reach, 0),
                                          round(eye_gap, 0)]
    QApplication.sendEvent(view, QKeyEvent(
        enum(QEvent, "Type", "KeyPress"), enum(Qt, "Key", "Key_Escape"),
        enum(Qt, "KeyboardModifier", "NoModifier")))
    result["aircraft_follow"]["esc_released"] = manager.followed is None
    manager.set_follow(None)
    result["aircraft_follow"]["after"] = manager.follow_timer.isActive()
    window.set_extra("aircraft", False)
    return None


@check(1000)
def flight_sim():
    """Режим полёта: клавиши на виде, модель и камера следом, строка
    показаний, Esc, касание земли кончает полёт."""
    import numpy as np
    from qgis.PyQt.QtCore import QEvent, Qt
    from qgis.PyQt.QtGui import QKeyEvent
    from qgis.PyQt.QtWidgets import QApplication
    from planetx.core import ellipsoid
    from planetx.core.navigation import Pose
    from planetx.qt_compat import enum
    window = state["window"]
    view = window.view
    flight = window.flight
    look = state.setdefault("flight_sim", {"phase": 0})
    out = result.setdefault("flight_sim", {})

    def key(name, press=True):
        kind = enum(QEvent, "Type", "KeyPress" if press else "KeyRelease")
        QApplication.sendEvent(view, QKeyEvent(
            kind, enum(Qt, "Key", name),
            enum(Qt, "KeyboardModifier", "NoModifier")))

    phase = look["phase"]
    look["phase"] += 1
    if phase == 0:
        view.navigator.stop()
        view.navigator.show(Pose(60.20, 24.80, 3000.0, 90.0, 60.0))
        view.update()
        flight.start(60.20, 24.80)
        plane = flight.plane
        out["start"] = [round(plane.alt, 0), round(plane.heading, 1),
                        round(plane.speed * 3.6, 0)]
        look["heading"] = plane.heading
        key("Key_Right")
        return 1000
    if phase == 1:
        plane = flight.plane
        out["roll_held"] = round(plane.roll, 1)
        key("Key_Right", False)
        key("Key_PageUp")
        look["speed"] = plane.speed
        return 1500
    if phase == 2:
        plane = flight.plane
        key("Key_PageUp", False)
        out["turned"] = round((plane.heading - look["heading"]) % 360.0, 1)
        out["throttle"] = round(plane.throttle, 2)
        out["faster"] = plane.speed > look["speed"]
        point = np.asarray([ellipsoid.geodetic_to_ecef(
            plane.lat, plane.lon, plane.alt * view.store.scale)],
            dtype=np.float64)
        pixels, front = view.camera.project(point)
        out["on_screen_px"] = [
            round(float(pixels[0][0] - view.camera.width / 2.0), 1),
            round(float(pixels[0][1] - view.camera.height / 2.0), 1)]
        out["front"] = bool(front[0])
        view.repaint()
        view.grabFramebuffer().save(os.path.join(TEMP,
                                                 "planetx_flight.png"))
        out["drawn"] = view.models.drawn
        out["lines"] = flight.readout.lines
        out["readout_visible"] = flight.readout.isVisible()
        # Из кабины: модели нет, глаз у самолёта, при крене вправо
        # правая сторона земли на кадре выше левой.
        key("Key_V")
        plane.roll = 30.0
        plane.pitch = -10.0
        flight._follow(flight._ground(plane.lat, plane.lon))
        eye = ellipsoid.ecef_to_geodetic(np.asarray(view.camera.eye))
        from planetx.core.trains import destination
        side = []
        for turn in (-20.0, 20.0):
            s_lat, s_lon = destination(plane.lat, plane.lon,
                                       plane.heading + turn, 3000.0)
            side.append(ellipsoid.geodetic_to_ecef(
                s_lat, s_lon, flight._ground(s_lat, s_lon)
                * view.store.scale))
        px, _ = view.camera.project(np.asarray(side, dtype=np.float64))
        out["cockpit"] = {
            "on": flight.cockpit,
            "model": flight._mover(0.0) is None,
            "eye_to_plane_m": round(float(np.hypot(
                (eye[0] - plane.lat) * 111320.0,
                (eye[1] - plane.lon) * 111320.0
                * np.cos(np.radians(plane.lat)))), 1),
            "eye_alt": round(float(eye[2]), 0),
            "plane_alt": round(plane.alt * view.store.scale, 0),
            "left_y": round(float(px[0][1]), 1),
            "right_y": round(float(px[1][1]), 1)}
        # Горизонт: при ровном полёте точка в 20 км впереди на высоте
        # самолёта - у середины кадра, верх кадра - небо.
        plane.roll = 0.0
        plane.pitch = 0.0
        flight._follow(flight._ground(plane.lat, plane.lon))
        h_lat, h_lon = destination(plane.lat, plane.lon, plane.heading,
                                   20000.0)
        px, ahead = view.camera.project(np.asarray([
            ellipsoid.geodetic_to_ecef(h_lat, h_lon,
                                       plane.alt * view.store.scale)],
            dtype=np.float64))
        out["cockpit"]["horizon_px"] = [
            round(float(px[0][0] - view.camera.width / 2.0), 1),
            round(float(px[0][1] - view.camera.height / 2.0), 1),
            bool(ahead[0])]
        out["cockpit"]["tilt"] = round(view.navigator.pose.tilt, 1)
        out["cockpit"]["air"] = view.navigator.air
        view.repaint()
        image = view.grabFramebuffer()
        image.save(os.path.join(TEMP, "planetx_cockpit.png"))
        out["cockpit"]["top_rgb"] = image.pixelColor(
            image.width() // 2, image.height() // 8).name()
        # Индикатор на стекле - только в кабине, H прячет его.
        flight._tick()
        out["hud"] = {"cockpit": flight.hud.isVisible(),
                      "lines": len(flight.readout.lines)}
        flight.view.grab().save(os.path.join(TEMP,
                                             "planetx_cockpit_hud.png"))
        key("Key_H")
        out["hud"]["after_h"] = flight.hud.isVisible()
        out["hud"]["lines_after_h"] = len(flight.readout.lines)
        key("Key_H")
        key("Key_V")
        out["cockpit_off"] = [flight.cockpit, flight._mover(0.0) is not None,
                              view.navigator.air]
        flight._tick()
        out["hud"]["outside"] = flight.hud.isVisible()
        key("Key_Escape")
        out["after_esc"] = [flight.plane is None,
                            len(view.models.groups.get("flightsim", [])),
                            flight.readout.isVisible()]
        # Касание земли: полёт низко с носом вниз, винтовой самолёт.
        from planetx.core import flightsim as core_flight
        flight.start(60.20, 24.80, core_flight.LIGHT)
        plane = flight.plane
        out["light_start_kmh"] = round(plane.speed * 3.6, 0)
        plane.alt = flight._ground(plane.lat, plane.lon) + 30.0
        plane.pitch = -20.0
        return 2500
    if phase == 3:
        out["crashed"] = [flight.plane is not None
                          and flight.plane.crashed, flight.readout.lines]
        return 3500
    out["after_crash"] = [flight.plane is None,
                          len(view.models.groups.get("flightsim", []))]
    out["gl"] = dict(view.gl_errors)
    return None


def _title_dark(widget):
    """Тёмный ли заголовок окна Windows (атрибут DWM 20), None - не
    Windows или атрибут не читается."""
    import ctypes
    if sys.platform != "win32":
        return None
    value = ctypes.c_int(-1)
    code = ctypes.windll.dwmapi.DwmGetWindowAttribute(
        ctypes.c_void_p(int(widget.window().winId())), 20,
        ctypes.pointer(value), ctypes.sizeof(value))
    return bool(value.value) if code == 0 else None


@check(1500)
def ui_theme():
    """Оформление: светлое, тёмное и «Как в QGIS» из окна свойств вида.
    Цвет плашки панели значков, значка, левой панели и окна свойств,
    снимки всего окна."""
    from planetx.ui import style
    window = state["window"]
    look = state.setdefault("ui_theme", {"n": 0})
    out = result.setdefault("ui_theme", {})
    order = [style.LIGHT, style.DARK, style.QGIS]
    n = look["n"]
    if n > 0:
        name = order[n - 1]
        image = window.grab().toImage()
        image.save(os.path.join(TEMP, "planetx_theme_{}.png".format(name)))
        bar = window.toolbar
        corner = bar.mapTo(window, bar.rect().topLeft())
        plate = image.pixelColor(corner.x() + 3, bar.height() // 2
                                 + corner.y()).name()
        panel = window.panel
        spot = panel.mapTo(window, panel.rect().center())
        dialog = window.properties
        out[name] = {
            "current": style.current(),
            "toolbar_plate": plate,
            "panel": image.pixelColor(spot.x(), spot.y()).name(),
            "icon_text": style.TEXT.name(),
            "window_rules": len(window.styleSheet()),
            "dialog_combo": dialog.ui_theme.currentText(),
            "toolbar_sheet_has_plate": style._rgba(style.PLATE)
            in bar.styleSheet(),
            "title_dark": _title_dark(window),
            "dialog_title_dark": _title_dark(dialog)}
    if n >= len(order):
        window.properties.close()
        return None
    look["n"] += 1
    window._show_properties()
    index = [code for code, _ in window.properties.ui_themes].index(
        order[n])
    window.properties.ui_theme.setCurrentIndex(index)
    return 1500


@check(1000)
def ui_theme_windows():
    """Тёмное оформление окон модуля: профиль высот с графиком, «О модуле»
    из меню QGIS, меню правой кнопки на глобусе. Снимки окон."""
    from qgis.PyQt.QtWidgets import QApplication, QDialog, QMenu
    from planetx.core.features import Shape
    from planetx.core.navigation import Pose
    from planetx.ui import style
    from planetx.ui.about import AboutDialog
    window = state["window"]
    look = state.setdefault("ui_theme_windows", {"n": 0})
    out = result.setdefault("ui_theme_windows", {})
    if look["n"] == 0:
        look["n"] = 1
        window.set_ui_theme(style.DARK)
        window.view.navigator.stop()
        window.view.navigator.set_pose(Pose(43.35, 42.44, 30000.0, 0.0,
                                            30.0))
        key = window.myplaces.add(Shape(
            "line", [(43.30, 42.38), (43.40, 42.50)], name="Профиль"))
        look["key"] = key
        window._place_action("profile", key)
        about = AboutDialog(None)
        style.dress(about)
        about.show()
        look["about"] = about
        menu = QMenu(window)
        menu.addAction("Подлететь сюда")
        menu.addAction("Полёт отсюда")
        menu.addSeparator()
        menu.addAction("Что здесь?")
        menu.popup(window.mapToGlobal(window.rect().center()))
        look["menu"] = menu
        return 6000
    shots = {}
    for widget in QApplication.topLevelWidgets():
        if not widget.isVisible() or widget is window:
            continue
        if isinstance(widget, (QDialog, QMenu)):
            name = type(widget).__name__
            image = widget.grab().toImage()
            image.save(os.path.join(TEMP, "planetx_dark_{}.png".format(
                name)))
            shots[name] = image.pixelColor(image.width() // 2,
                                           image.height() - 6).name()
    out["shots"] = shots
    look["menu"].close()
    look["about"].close()
    for widget in QApplication.topLevelWidgets():
        if widget.isVisible() and type(widget).__name__ == "ProfileDialog":
            widget.close()
    window.myplaces.remove(look["key"])
    window.set_ui_theme(style.QGIS)
    return None


@check(1000)
def flight_mars():
    """Режим полёта над Марсом: самолёт на кадре, движется, касание
    поверхности тела. Замечание автора от 19 октября 2026 года - «над
    Марсом и т. п. не летает»."""
    import numpy as np
    from planetx.core import ellipsoid
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    flight = window.flight
    look = state.setdefault("flight_mars", {"n": 0})
    out = result.setdefault("flight_mars", {})
    n = look["n"]
    look["n"] += 1
    if n == 0:
        window.set_body("mars")
        return 3000
    if n == 1:
        view.navigator.stop()
        view.navigator.show(Pose(18.4, 77.5, 20000.0, 0.0, 60.0))
        view.update()
        return 5000
    if n == 2:
        flight.start(18.4, 77.5)
        plane = flight.plane
        look["start"] = (plane.lat, plane.lon)
        out["start_alt"] = round(plane.alt, 0)
        out["ground"] = round(flight._ground(plane.lat, plane.lon), 0)
        return 3000
    plane = flight.plane
    out["moved_m"] = None if plane is None else round(float(np.hypot(
        (plane.lat - look["start"][0]) * 59000.0,
        (plane.lon - look["start"][1]) * 59000.0)), 0)
    out["flying"] = flight.flying
    if plane is not None:
        point = np.asarray([ellipsoid.geodetic_to_ecef(
            plane.lat, plane.lon, plane.alt * view.store.scale)],
            dtype=np.float64)
        pixels, front = view.camera.project(point)
        out["on_screen_px"] = [
            round(float(pixels[0][0] - view.camera.width / 2.0), 1),
            round(float(pixels[0][1] - view.camera.height / 2.0), 1)]
        out["front"] = bool(front[0])
        eye = ellipsoid.ecef_to_geodetic(np.asarray(view.camera.eye))
        out["eye"] = [round(float(v), 4) for v in eye]
        out["plane"] = [round(plane.lat, 4), round(plane.lon, 4),
                        round(plane.alt, 0)]
        out["scale"] = view.store.scale
        out["radius_a"] = ellipsoid.A
        pose = view.navigator.pose
        # Точка взгляда на рельефе тела, не на эллипсоиде.
        out["look_h"] = round(pose.h, 0)
        out["look_ground"] = round(view.terrain_at(pose.lat, pose.lon), 0)
    view.repaint()
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_flight_mars.png"))
    out["drawn"] = view.models.drawn
    out["lines"] = flight.readout.lines
    flight.stop()
    window.set_body("earth")
    return None


@check(1000)
def live_close():
    """Поздние ответы служб после закрытия менеджеров окна не трогают."""
    window = state["window"]
    calls = []
    original = window._refresh_shapes
    window._refresh_shapes = lambda: calls.append(1)
    out = {}
    try:
        for manager in (window.vessel_manager, window.aircraft_manager):
            manager.set_on(True)
            manager.close()
            manager._done(b'{"features": [], "ac": [], "now": 0}', "")
            manager._info_done(b"[]", "")
            out[manager.group_name()] = manager.on
    finally:
        window._refresh_shapes = original
    out["window_calls"] = len(calls)
    for key in ("vessels", "aircraft"):
        window.set_extra(key, False)
    result["live_close"] = out


@check(1000, manual=True)
def borders_probe():
    """Жёлтые полосы границ издалека: кадр через 1 с после позы и после
    полной загрузки, жёлтые пиксели и недостающие картинки наложения.
    PLANETX_BORDERS_POSE - широта, долгота, расстояние, азимут, наклон."""
    import numpy as np
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    look = state.setdefault("borders_probe", {"since": None})
    pose = Pose(*[float(v) for v in os.environ.get(
        "PLANETX_BORDERS_POSE", "62.0,25.5,1500000,0,0").split(",")])

    def yellow(image):
        bits = image.constBits()
        bits.setsize(image.sizeInBytes())
        px = np.frombuffer(bits, np.uint8).reshape(
            image.height(), image.width(), 4)
        b, g, r = (px[..., k].astype(np.int16) for k in range(3))
        return int(((r > 200) & (g > 200) & (b < 90)).sum())
    if look["since"] is None:
        window.set_body("earth")
        view.navigator.stop()
        view.navigator.show(pose)
        view.update()
        look["since"] = time.monotonic()
        return 1000
    if "early" not in look:
        view.repaint()
        image = view.grabFramebuffer()
        image.save(os.path.join(TEMP, "planetx_borders_early.png"))
        look["early"] = {"yellow": yellow(image),
                         "overlay_missing": view._overlay_missing,
                         "load_missing": view.load_missing}
        return 1000
    waited = time.monotonic() - look["since"]
    if (view.load_missing or waited < 10.0) and waited < 90.0:
        return 1000
    view.repaint()
    image = view.grabFramebuffer()
    image.save(os.path.join(TEMP, "planetx_borders_late.png"))
    result["borders_probe"] = {
        "early": look["early"],
        "late": {"yellow": yellow(image),
                 "overlay_missing": view._overlay_missing,
                 "load_missing": view.load_missing,
                 "waited": round(waited, 1)},
        "groups": sorted(getattr(window, "_groups", []))}
    return None


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
    from qgis.core import QgsSettings
    from planetx.core import sources
    # Этот шаг проверяет расчёт по тайлам, сервис выключен.
    QgsSettings().setValue(sources.ROUTER_ON_KEY, False)
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
    out["via"] = manager.via
    if manager.via != "tiles":
        return out
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


@check(6000)
def article_circle():
    """Снимки для статьи: круг 1 км у Эспланады в окне «Новая метка»
    и окно «Номенклатура листа» у Перми."""
    window = state["window"]
    window._open_place()
    dialog = window.place_dialog
    dialog.tabs.setCurrentIndex(3)
    d = window.drawer
    d.add(*ROUTE_A)
    d.add(ROUTE_A[0] + 1000.0 / 111320.0, ROUTE_A[1])
    sheets = window.sheets_here(*ROUTE_A)
    sheets.grab().save(os.path.join(TEMP, "planetx_article_sheets.png"))
    dialog.grab().save(os.path.join(TEMP, "planetx_article_place.png"))


@check(500)
def article_circle_shot():
    window = state["window"]
    window.view.grabFramebuffer().save(
        os.path.join(TEMP, "planetx_article_circle.png"))
    window.place_dialog.close()
    window.sheets_dialog.close()


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
def contours_on():
    """Горизонтали рельефа над Пермью: строка «Горизонтали» витрины."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.set_extra("contours",
                     os.environ.get("PLANETX_CONTOURS_OFF") is None)
    window.view.navigator.stop()
    window.view.navigator.set_pose(Pose(57.98, 56.20, 7000.0, 30.0, 60.0))
    result["contours"] = {"on": window.extras.get("contours")}


@check(35000)
def contours_check():
    window = state["window"]
    view = window.view
    layer = view.gibs["contours"]
    out = result["contours"]
    out["textures"] = len(layer.textures)
    out["missing"] = layer.missing
    sel = view.selection
    out["levels"] = sorted({k[0] for k in sel.draw}) if sel else None
    out["want"] = len(sel.want) if sel else None
    out["busy"] = view.loader.busy() if view.loader else None
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_contours.png"))
    from planetx.core.navigation import Pose
    view.navigator.stop()
    view.navigator.set_pose(Pose(43.35, 42.44, 14000.0, 200.0, 55.0))


@check(20000, manual=True)
def contours_perm():
    """Горизонтали над окраиной Перми с 1.6 км, отвесно."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.set_extra("contours", True)
    window.view.navigator.stop()
    window.view.navigator.set_pose(Pose(57.955, 56.255, 1600.0, 0.0, 0.0))


@check(500, manual=True)
def contours_perm_shot():
    view = state["window"].view
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_contours_perm.png"))
    window = state["window"]
    legend = window.contour_legend
    out = result["contours_perm"] = {
        "textures": len(view.gibs["contours"].textures),
        "gl": dict(view.gl_errors),
        "basemap": window.source.name,
        "palette": window._contour_palette,
        "legend": not legend.isHidden(),
        "legend_step": legend.step,
        "legend_export": legend.export is not None}
    legend.grab().save(os.path.join(TEMP, "planetx_contour_legend.png"))
    osm = next(s for s in window.sources if "OpenStreetMap" in s.name)
    state["contours_basemap"] = window.source
    window._switch_basemap(osm)
    out["palette_osm"] = window._contour_palette


@check(15000, manual=True)
def contours_perm_osm():
    window = state["window"]
    view = window.view
    view.grabFramebuffer().save(os.path.join(
        TEMP, "planetx_contours_perm_osm.png"))
    window._switch_basemap(state["contours_basemap"])
    result["contours_perm"]["palette_back"] = window._contour_palette
    window.set_extra("contours", False)
    result["contours_perm"]["legend_off"] = \
        window.contour_legend.isHidden()


def _isobath_pixels(view):
    """Голубые пиксели изобат на снимке (палитра imagery) в кадре."""
    import numpy as np
    from planetx.net.loader import image_to_rgba
    rgba = image_to_rgba(view.grabFramebuffer()).astype(int)
    r, g, b = rgba[..., 0], rgba[..., 1], rgba[..., 2]
    return int(((b > 200) & (g > 160) & (r < 170) & (b - r > 60)).sum())


@check(25000, manual=True)
def contours_japan():
    """Изобаты над Японским жёлобом с 30 км."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.set_sea_depths(True)
    window.set_extra("contours", True)
    window.view.navigator.stop()
    window.view.navigator.set_pose(Pose(38.0, 143.9, 30000.0, 0.0, 0.0))


@check(25000, manual=True)
def contours_japan_far():
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_japan_30km.png"))
    source = window.gibs_loaders["contours"].source
    out = result["contours_japan"] = {
        "far_pixels": _isobath_pixels(view),
        "far_levels": sorted(set(source.levels.values())),
        "far_textures": len(view.gibs["contours"].textures)}
    out["palette"] = window._contour_palette
    view.navigator.stop()
    view.navigator.set_pose(Pose(38.0, 143.9, 5000.0, 0.0, 0.0))


@check(500, manual=True)
def contours_japan_near():
    window = state["window"]
    view = window.view
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_japan_5km.png"))
    source = window.gibs_loaders["contours"].source
    out = result["contours_japan"]
    out["near_pixels"] = _isobath_pixels(view)
    out["near_levels"] = sorted(set(source.levels.values()))
    out["legend_step"] = window.contour_legend.step
    out["gl"] = dict(view.gl_errors)


@check(500)
def contours_export():
    """Горизонтали вида над Эльбрусом - слоем GeoPackage в проект."""
    window = state["window"]
    path = os.path.join(TEMP, "planetx_contours_view.gpkg")
    state["contours_path"] = path
    state["contours_started"] = time.monotonic()
    window.contour_export.view_contours(path=path)


def _contour_layers(path):
    from qgis.core import QgsProject
    return [layer for layer in QgsProject.instance().mapLayers().values()
            if layer.source().replace("\\", "/").startswith(
                path.replace("\\", "/"))]


def _contour_report(path, window):
    from qgis.core import QgsProject
    layers = _contour_layers(path)
    out = {"layers": len(layers),
           "message": window.message[0] if window.message else None}
    if layers:
        layer = layers[0]
        elevs = sorted({round(f["elev"], 3) for f in layer.getFeatures()})
        out["features"] = layer.featureCount()
        out["crs"] = layer.crs().authid() or layer.crs().description()
        out["elev"] = [elevs[0], elevs[-1]] if elevs else None
        out["levels"] = len(elevs)
        out["labels"] = layer.labelsEnabled()
        node = QgsProject.instance().layerTreeRoot().findLayer(layer.id())
        out["group"] = node.parent().name() if node is not None else None
    return out


@check(500)
def contours_export_wait():
    window = state["window"]
    if window.contour_export.job is not None \
            and time.monotonic() - state["contours_started"] < 45.0:
        return 500
    result["contours"]["export"] = _contour_report(state["contours_path"],
                                                   window)
    _render_layers(_contour_layers(state["contours_path"]),
                   os.path.join(TEMP, "planetx_contours_layer.png"))
    return None


def _render_layers(layers, path):
    """Снимок слоёв средствами QGIS, как на карте, в файл path."""
    from qgis.core import QgsMapRendererParallelJob, QgsMapSettings
    from qgis.PyQt.QtCore import QSize
    if not layers:
        return
    settings = QgsMapSettings()
    settings.setLayers(layers)
    settings.setDestinationCrs(layers[0].crs())
    extent = layers[0].extent()
    extent.scale(0.35)
    settings.setExtent(extent)
    settings.setOutputSize(QSize(1200, 900))
    job = QgsMapRendererParallelJob(settings)
    job.start()
    job.waitForFinished()
    job.renderedImage().save(path)


@check(25000)
def contours_mountain():
    window = state["window"]
    view = window.view
    result["contours"]["mountain_textures"] = len(
        view.gibs["contours"].textures)
    view.grabFramebuffer().save(
        os.path.join(TEMP, "planetx_contours_elbrus.png"))
    window.set_extra("contours", False)
    result["contours"]["off"] = (view.gibs["contours"].loader is None)
    result["contours"]["gl"] = dict(view.gl_errors)


@check(500)
def extrude_layers_on():
    """Выдавливание: кварталы, точки и линия в памяти у Перми с полем
    высоты h, слои отмечены на глобусе."""
    from qgis.core import (QgsFeature, QgsField, QgsGeometry, QgsProject,
                           QgsVectorLayer)
    from qgis.PyQt.QtCore import QVariant
    from planetx.core.navigation import Pose
    from planetx.ui.project import write_extrude
    window = state["window"]
    window.set_body("earth")
    made = []
    specs = (("Polygon", "blocks"), ("Point", "towers"),
             ("LineString", "fence"))
    for geom, name in specs:
        layer = QgsVectorLayer(geom + "?crs=EPSG:4326", name, "memory")
        layer.dataProvider().addAttributes([QgsField("h", QVariant.Double)])
        layer.updateFields()
        feats = []
        if geom == "Polygon":
            for i in range(3):
                for j in range(3):
                    lat, lon = 58.010 + i * 0.002, 56.230 + j * 0.004
                    wkt = "POLYGON(({0} {1}, {2} {1}, {2} {3}, {0} {3}, " \
                        "{0} {1}))".format(lon, lat, lon + 0.0025,
                                           lat + 0.0012)
                    f = QgsFeature(layer.fields())
                    f.setGeometry(QgsGeometry.fromWkt(wkt))
                    f["h"] = 30.0 + 40.0 * (i * 3 + j)
                    feats.append(f)
        elif geom == "Point":
            for k in range(5):
                f = QgsFeature(layer.fields())
                f.setGeometry(QgsGeometry.fromWkt("POINT({} {})".format(
                    56.226 + k * 0.004, 58.0065)))
                f["h"] = 60.0 + 30.0 * k
                feats.append(f)
        else:
            f = QgsFeature(layer.fields())
            f.setGeometry(QgsGeometry.fromWkt(
                "LINESTRING(56.226 58.0085, 56.242 58.0085, 56.244 58.017)"))
            f["h"] = 25.0
            feats.append(f)
        layer.dataProvider().addFeatures(feats)
        layer.updateExtents()
        QgsProject.instance().addMapLayer(layer)
        made.append(layer.id())
    state["extrude_ids"] = made
    write_extrude({i: {"field": "h", "factor": 1.0} for i in made})
    for layer_id in made:
        window.set_layer_shown(layer_id, True)
    window._apply_vector(force=True)
    view = window.view
    view.navigator.stop()
    view.navigator.set_pose(Pose(58.0125, 56.236, 2600.0, 20.0, 62.0))
    result["extrude"] = {"counts": dict(window.extruder.counts)}


@check(15000)
def extrude_layers_check():
    window = state["window"]
    view = window.view
    out = result["extrude"]
    out["meshes"] = sorted(view.extruded.buffers)
    out["vertices"] = view.extruded.vertex_count()
    out["drawn"] = view.extruded.drawn
    out["gl"] = dict(view.gl_errors)
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_extrude.png"))


@check(500)
def extrude_layers_off():
    from planetx.ui.project import write_extrude
    window = state["window"]
    write_extrude({})
    window._apply_vector(force=True)
    view = window.view
    view.grabFramebuffer()
    result["extrude"]["after_off"] = view.extruded.vertex_count()


@check(500)
def tour_edit_open():
    """Правка пути записанного облёта в окне «Свойства…»."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    samples = [(0.25 * k, 58.00 + 0.0004 * k, 56.20 + 0.0008 * k,
                3000.0, 45.0, 55.0) for k in range(120)]
    place = window.save_recorded(samples, "Облёт для правки")
    if not hasattr(place, "key"):
        place = window.myplaces.find(place)
    state["tour_key"] = place.key
    window.view.navigator.stop()
    window.view.navigator.set_pose(Pose(58.024, 56.248, 9000.0, 0.0, 0.0))
    window._open_place_properties(place)
    dialog = window.prop_dialogs[place.key]
    out = result["tour_edit"] = {}
    out["keys"] = len(dialog.points)
    tool = window.handles.tool
    out["tool"] = type(tool).__name__
    out["middles"] = len(tool.middles())
    out["drawn_in_preview"] = place.key in window.previews


@check(3000)
def tour_edit_check():
    window = state["window"]
    key = state["tour_key"]
    dialog = window.prop_dialogs[key]
    out = result["tour_edit"]
    tool = window.handles.tool
    middle = len(dialog.points) // 2
    lat, lon = dialog.points[middle]
    out["key_sample"] = dialog.tour_keys[middle]
    tool.edit.move(middle, lat, lon + 0.01)
    dialog.factor_slider.setValue(dialog.factor_slider.maximum())
    out["preview_points"] = len(window.previews[key].points)
    out["factor"] = round(dialog.factor, 3)
    dialog.accept()
    place = window.myplaces.find(key)
    tour = place.tour
    k = out["key_sample"]
    out["moved_lon"] = round(tour[k][2] - (56.20 + 0.0008 * k), 6)
    out["first_lon"] = round(tour[0][2] - 56.20, 6)
    out["distance"] = round(tour[k][3], 1)
    out["samples"] = len(tour)
    out["line_points"] = len(place.shape.points)
    out["gl"] = dict(window.view.gl_errors)
    window.myplaces.remove(key)


NETLINK_DOC = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Local</name>
{}</Document></kml>"""
NETLINK_PLACE = ("<Placemark><name>P{0}</name><Point><coordinates>"
                 "56.2{0},58.0,0</coordinates></Point></Placemark>")


def _netlink_file(count):
    path = os.path.join(TEMP, "planetx_netlink_local.kml")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(NETLINK_DOC.format("".join(
            NETLINK_PLACE.format(n) for n in range(count))))
    return path


@check(2000)
def netlink_local():
    """Сетевая ссылка на файл на диске: две метки."""
    window = state["window"]
    window.set_body("earth")
    path = _netlink_file(2)
    key = window.myplaces.add_folder("Local link")
    window.myplaces.set_link(key, path, 0.0)
    state["netlink_key"] = key
    window.netlinks.tick()


@check(2000)
def netlink_local_check():
    import time as _time
    from planetx.core import placetree
    window = state["window"]
    key = state["netlink_key"]
    out = result["netlink"] = {}
    nodes = window.myplaces.nodes()
    out["first"] = len(placetree.children(nodes, key))
    # Файл правит другая программа: время правки новое.
    _time.sleep(1.1)
    _netlink_file(3)
    window.netlinks.tick()
    out["second"] = len(placetree.children(window.myplaces.nodes(), key))
    out["is_link_menu"] = window.panel.is_link(key)


@check(500)
def netlink_example():
    """Пример examples/network_link/link.kml: USGS и GitHub."""
    from planetx.core import kml
    window = state["window"]
    window.myplaces.remove(state["netlink_key"])
    import planetx
    root = os.path.dirname(os.path.dirname(os.path.realpath(
        planetx.__file__)))
    path = os.path.join(root, "examples", "network_link", "link.kml")
    result["netlink"]["example_path"] = path
    with open(path, "rb") as fh:
        tree = kml.read_kml(fh.read(), "link")
    top = window.myplaces.import_tree(tree)
    state["netlink_top"] = top
    state["netlink_started"] = time.monotonic()
    window.netlinks.tick()


@check(500)
def netlink_example_wait():
    from planetx.core import placetree
    window = state["window"]
    links = window.netlinks
    if (links.replies or not links.loaded) \
            and time.monotonic() - state["netlink_started"] < 60.0:
        return 500
    out = result["netlink"]
    nodes = window.myplaces.nodes()
    rows = {}
    for folder in links.links():
        rows[folder.link.rsplit("/", 1)[-1]] = {
            "children": len(placetree.children(nodes, folder.key)),
            "error": links.errors.get(folder.key)}
    out["example"] = rows
    out["places"] = sum(1 for p in window.myplaces.places
                        if p.body == "earth")
    out["message"] = window.message[0] if window.message else None
    out["gl"] = dict(window.view.gl_errors)
    window.myplaces.remove(state["netlink_top"])
    return None


@check(500)
def journal_check():
    """Журнал работы модуля: файл, строка загрузки, сторож зависания."""
    from planetx import journal
    name = journal.path()
    with open(name, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    timer = journal._state["timer"]
    result["journal"] = {
        "path": name,
        "lines": len(lines),
        "started": any("PlanetX" in line and "QGIS" in line
                       for line in lines),
        "watchdog": timer is not None and timer.isActive(),
        "hangs": sum("не отвечал" in line or "not respond" in line
                     for line in lines)}


@check(500)
def sentinel_open():
    """Снимки Sentinel-2 у Перми: участок 2 км вокруг точки, поиск
    через STAC Earth Search за год, облачность над участком по SCL."""
    window = state["window"]
    window.set_body("earth")
    dialog = window.sentinel_here(*ROUTE_A)
    dialog.side.setValue(2.0)
    dialog.search()
    state["s2_started"] = time.monotonic()
    result["sentinel"] = {}


@check(500)
def sentinel_wait():
    window = state["window"]
    dialog = window.sentinel_dialog
    spent = time.monotonic() - state["s2_started"]
    busy = dialog.reply is not None or dialog.cloud_jobs
    if busy and spent < 180.0:
        return 500
    out = result["sentinel"]
    out["seconds"] = round(spent, 1)
    out["scenes"] = len(dialog.scenes)
    out["clouds"] = len(dialog.clouds)
    out["unread"] = sum(1 for c, _ in dialog.clouds.values() if c is None)
    shown = [dialog.list.topLevelItem(n)
             for n in range(dialog.list.topLevelItemCount())
             if not dialog.list.topLevelItem(n).isHidden()]
    out["shown"] = len(shown)
    out["first"] = [shown[0].text(c) for c in range(5)] if shown else None
    out["status"] = dialog.status.text()
    if shown:
        dialog.list.setCurrentItem(shown[0])
    return None


@check(500)
def landsat_open():
    """Снимки Landsat у Перми: тот же участок 2 км, каталог Planetary
    Computer, ключ SAS без учётной записи, облачность по qa_pixel.
    PLANETX_LANDSAT_YEAR - год съёмки, по умолчанию 2024, лето."""
    from qgis.PyQt.QtCore import QDate
    window = state["window"]
    window.set_body("earth")
    point = os.environ.get("PLANETX_LANDSAT_POINT")
    dialog = window.sentinel_here(*(tuple(map(float, point.split(",")))
                                    if point else ROUTE_A))
    year = int(os.environ.get("PLANETX_LANDSAT_YEAR", "2024"))
    dialog.side.setValue(2.0)
    dialog.start.setDate(QDate(year, 5, 1))
    dialog.end.setDate(QDate(year, 9, 30))
    dialog.mission.setCurrentIndex(dialog.mission.findData("landsat"))
    state["ls_started"] = time.monotonic()
    result["landsat"] = {"year": year,
                         "link_enabled": dialog.mode.model().item(1)
                         .isEnabled(),
                         "products": [dialog.products.item(n).text()
                                      for n in range(dialog.products.count())]}


@check(500)
def landsat_wait():
    window = state["window"]
    dialog = window.sentinel_dialog
    spent = time.monotonic() - state["ls_started"]
    busy = dialog.reply is not None or dialog.cloud_jobs \
        or dialog.sas_reply is not None or dialog.sas_waiting
    if busy and spent < 240.0:
        return 500
    out = result["landsat"]
    out["seconds"] = round(spent, 1)
    out["scenes"] = len(dialog.scenes)
    out["platforms"] = sorted({s.tile.split(" ")[0] for s in dialog.scenes})
    out["clouds"] = len(dialog.clouds)
    out["unread"] = sum(1 for c, _ in dialog.clouds.values() if c is None)
    out["key"] = bool(dialog.sas)
    shown = [dialog.list.topLevelItem(n)
             for n in range(dialog.list.topLevelItemCount())
             if not dialog.list.topLevelItem(n).isHidden()]
    out["shown"] = len(shown)
    out["first"] = [shown[0].text(c) for c in range(5)] if shown else None
    out["status"] = dialog.status.text()
    if shown:
        dialog.list.setCurrentItem(shown[0])
    return None


@check(500)
def mss_open():
    """Снимки Landsat 1-5 MSS у Перми: участок 10 км, даты сегодняшние -
    окно само ставит лето 1975 года и возвращает их при уходе с MSS."""
    window = state["window"]
    window.set_body("earth")
    dialog = window.sentinel_here(*ROUTE_A)
    dialog.side.setValue(10.0)
    state["mss_dates"] = (dialog.start.date().toString("yyyy-MM-dd"),
                          dialog.end.date().toString("yyyy-MM-dd"))
    dialog.mission.setCurrentIndex(dialog.mission.findData("mss"))
    state["ls_started"] = time.monotonic()
    result["mss"] = {"dates": [dialog.start.date().toString("yyyy-MM-dd"),
                               dialog.end.date().toString("yyyy-MM-dd")],
                     "link_enabled": dialog.mode.model().item(1)
                     .isEnabled(),
                     "products": [dialog.products.item(n).text()
                                  for n in range(dialog.products.count())]}


@check(500)
def mss_wait():
    window = state["window"]
    dialog = window.sentinel_dialog
    spent = time.monotonic() - state["ls_started"]
    busy = dialog.reply is not None or dialog.cloud_jobs \
        or dialog.sas_reply is not None or dialog.sas_waiting
    if busy and spent < 240.0:
        return 500
    out = result["mss"]
    out["seconds"] = round(spent, 1)
    out["scenes"] = len(dialog.scenes)
    out["missions"] = sorted({s.mission for s in dialog.scenes})
    out["platforms"] = sorted({s.tile.split(" ")[0] for s in dialog.scenes})
    out["clouds"] = len(dialog.clouds)
    out["unread"] = sum(1 for c, _ in dialog.clouds.values() if c is None)
    shown = [dialog.list.topLevelItem(n)
             for n in range(dialog.list.topLevelItemCount())
             if not dialog.list.topLevelItem(n).isHidden()]
    out["shown"] = len(shown)
    out["first"] = [shown[0].text(c) for c in range(5)] if shown else None
    out["status"] = dialog.status.text()
    if shown:
        dialog.list.setCurrentItem(shown[0])
    return None


@check(500)
def mss_build():
    from qgis.PyQt.QtCore import Qt
    dialog = state["window"].sentinel_dialog
    for n in range(dialog.products.count()):
        dialog.products.item(n).setCheckState(Qt.CheckState.Checked)
    folder = os.path.join(TEMP, "planetx_mss")
    state["mss_folder"] = folder
    dialog.add(folder=folder)
    state["ls_build"] = time.monotonic()


@check(500)
def mss_built():
    from osgeo import gdal
    import numpy as np
    from qgis.core import QgsProject
    dialog = state["window"].sentinel_dialog
    spent = time.monotonic() - state["ls_build"]
    if (dialog.build_job is not None or dialog.sas_waiting) \
            and spent < 240.0:
        return 500
    out = result["mss"]
    out["build_seconds"] = round(spent, 1)
    out["build_status"] = dialog.status.text()
    out["preview"] = dialog.preview.pixmap() is not None \
        and not dialog.preview.pixmap().isNull()
    group = QgsProject.instance().layerTreeRoot().findGroup("Landsat")
    layers = [n.layer() for n in group.findLayers()] if group else []
    out["layers"] = [(l.name(), l.isValid(), l.renderer().type(),
                      l.bandCount(), l.metadata().rights())
                     for l in layers]
    folder = state["mss_folder"]
    files = sorted(os.listdir(folder)) if os.path.isdir(folder) else []
    out["files"] = files
    for name in files:
        if not name.endswith(".tif"):
            continue
        ds = gdal.Open(os.path.join(folder, name))
        a = ds.ReadAsArray()
        finite = a[np.isfinite(a)]
        key = name[len("LM1_19750601_181-019_"):-4]
        out[key] = {"size": [ds.RasterXSize, ds.RasterYSize],
                    "res": ds.GetGeoTransform()[1],
                    "valid": round(finite.size / a.size, 3),
                    "median": round(float(np.median(finite)), 3)
                    if finite.size else None,
                    "range": [round(float(finite.min()), 3),
                              round(float(finite.max()), 3)]
                    if finite.size else None}
        ds = None
    # Полосы - насыщенные строки зелёного: пиксели, отличные от среднего
    # соседей сверху и снизу больше чем на 0.05 отражения.
    bands_file = [n for n in files if n.endswith("_mss_bands.tif")]
    if bands_file:
        from planetx.core import sentinel as s2
        ds = gdal.Open(os.path.join(folder, bands_file[0]))
        a = ds.ReadAsArray().astype(float)
        ds = None
        g = a[0]
        around = (g[:-2] + g[2:]) / 2.0
        out["green_line_outliers"] = int(np.nansum(
            np.abs(g[1:-1] - around) > 0.05))
        # Пиксели, где зелёный к остальным каналам выбит от соседей на
        # 3 строки выше и ниже, - полосы и их провалы.
        bands = dict(zip(s2.MSS_BANDS, a))
        out["green_ratio_off"] = int(s2._ratio_off(
            bands, "green", list(s2.MSS_BANDS)).sum())
    if dialog.preview.pixmap() is not None:
        dialog.preview.pixmap().save(os.path.join(TEMP,
                                                  "planetx_mss_preview.png"))
    dialog.grab().save(os.path.join(TEMP, "planetx_mss_dialog.png"))
    if layers:
        state["window"].view.update()
    if group is not None:
        QgsProject.instance().removeMapLayers(group.findLayerIds())
        QgsProject.instance().layerTreeRoot().removeChildNode(group)
    # Уход с MSS возвращает прежние даты поиска.
    dialog.mission.setCurrentIndex(dialog.mission.findData("sentinel2"))
    out["dates_back"] = [dialog.start.date().toString("yyyy-MM-dd"),
                         dialog.end.date().toString("yyyy-MM-dd")] == \
        list(state["mss_dates"])
    dialog.close()
    return None


@check(500)
def mss_command():
    """Ранние снимки Landsat выделены: подсказка строки «Поиск» по
    слову «MSS», действие открывает окно сразу на MSS с летом 1975
    года, пункт есть в меню на глобусе. Шаги идут в порядке записи
    в этом файле, поэтому шаг стоит после mss_built - он закрывает
    окно."""
    from qgis.PyQt.QtWidgets import QMenu
    from planetx.ui import globemenu
    window = state["window"]
    window.set_body("earth")
    out = {}
    hints = window.search_suggestions("mss")
    out["hint"] = [(h.kind, h.text) for h in hints[:3]]
    out["hint_old"] = [h.text for h in
                       window.search_suggestions("старые снимки")[:3]]
    dialog = getattr(window, "sentinel_dialog", None)
    if dialog is not None:
        dialog.use_mission("sentinel2")
    window._actions["here:mss"]()
    dialog = window.sentinel_dialog
    out["mission"] = dialog.current_mission()
    out["dates"] = [dialog.start.date().toString("yyyy-MM-dd"),
                    dialog.end.date().toString("yyyy-MM-dd")]
    out["searching"] = dialog.reply is not None
    view = window.view
    before = set(window.findChildren(QMenu))
    globemenu.show(window, view.width() * view.devicePixelRatioF() / 2.0,
                   view.height() * view.devicePixelRatioF() / 2.0)
    menus = [m for m in window.findChildren(QMenu) if m not in before]
    out["menu"] = [a.text() for m in menus for a in m.actions()
                   if "Космоснимки" in a.text() or "Landsat" in a.text()
                   or "ASTER" in a.text()]
    for menu in menus:
        menu.close()
    dialog.close()
    # Действие «Снимки ASTER здесь»: окно на ASTER с датами 2000-2006.
    out["aster_hint"] = [(h.kind, h.text) for h in
                         window.search_suggestions("астер")[:3]]
    dialog.use_mission("sentinel2")
    window._actions["here:aster"]()
    out["aster_mission"] = dialog.current_mission()
    out["aster_dates"] = [dialog.start.date().toString("yyyy-MM-dd"),
                          dialog.end.date().toString("yyyy-MM-dd")]
    dialog.close()
    result["mss_command"] = out


CUPRITE = (37.535, -117.205)  # Куприт, Невада - изменённые породы
FAKE_KEY = "planetx-test-key"  # ключ поддельного хранилища NASA


@check(500)
def nasa_open():
    """ASTER NASA после 2006 года у Куприта: поиск по настоящему каталогу
    CMR без ключа, 2018-2024 годы."""
    from qgis.PyQt.QtCore import QDate
    window = state["window"]
    window.set_body("earth")
    dialog = window.sentinel_here(*CUPRITE)
    dialog.side.setValue(10.0)
    dialog.mission.setCurrentIndex(dialog.mission.findData("aster_nasa"))
    dialog.start.setDate(QDate(2018, 1, 1))
    dialog.end.setDate(QDate(2024, 12, 31))
    dialog.search()
    state["ls_started"] = time.monotonic()
    result["nasa"] = {"products": [dialog.products.item(n).text()
                                   for n in range(dialog.products.count())],
                      "clear_enabled": dialog.clear.isEnabled()}


@check(500)
def nasa_wait():
    dialog = state["window"].sentinel_dialog
    spent = time.monotonic() - state["ls_started"]
    if (dialog.reply is not None or dialog.preview_job is not None) \
            and spent < 120.0:
        return 500
    if dialog.preview.pixmap() is None and spent < 30.0 and dialog.scenes:
        return 500
    out = result["nasa"]
    out["seconds"] = round(spent, 1)
    out["scenes"] = len(dialog.scenes)
    out["tiles"] = sorted({s.tile for s in dialog.scenes})
    out["years"] = sorted({s.when[:4] for s in dialog.scenes})
    shown = [dialog.list.topLevelItem(n)
             for n in range(dialog.list.topLevelItemCount())
             if not dialog.list.topLevelItem(n).isHidden()]
    out["shown"] = len(shown)
    out["first"] = [shown[0].text(c) for c in range(5)] if shown else None
    out["status"] = dialog.status.text()
    pixmap = dialog.preview.pixmap()
    out["preview"] = pixmap is not None and not pixmap.isNull()
    return None


def _fake_nasa(folder):
    """Поддельное хранилище NASA LP DAAC на 127.0.0.1: файлы каналов
    у Куприта, с ключом FAKE_KEY - переадресация 307 на файл, иначе -
    303 на страницу входа Earthdata, как у настоящего."""
    import http.server
    import threading
    import numpy as np
    from osgeo import gdal, osr
    os.makedirs(folder, exist_ok=True)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(32611)
    x0, y0 = 476000.0, 4160000.0  # около Куприта, UTM 11
    names = {}
    for key, (group, _, _, _) in __import__(
            "planetx.core.aster", fromlist=["BANDS"]).BANDS.items():
        if group == "SWIR":
            continue
        res = 15.0 if group == "VNIR" else 90.0
        size = int(16000 / res)
        name = "FAKE_{}.tif".format(
            __import__("planetx.core.aster",
                       fromlist=["file_suffix"]).file_suffix(key))
        ds = gdal.GetDriverByName("GTiff").Create(
            os.path.join(folder, name), size, size, 1,
            gdal.GDT_Byte if group == "VNIR" else gdal.GDT_UInt16)
        ds.SetGeoTransform((x0, res, 0.0, y0, 0.0, -res))
        ds.SetProjection(srs.ExportToWkt())
        ramp = np.add.outer(np.arange(size), np.arange(size)) % 200 + 20
        if group == "TIR":
            ramp = ramp * 0 + 1300 + (ramp % 7)
        ds.GetRasterBand(1).WriteArray(ramp)
        ds = None
        names[key] = name
    requests = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            return None

        def do_GET(self):
            requests.append((self.path, self.headers.get("Authorization")))
            if self.path.startswith("/protected/"):
                if self.headers.get("Authorization") == "Bearer " + FAKE_KEY:
                    self.send_response(307)
                    self.send_header("Location", "/files/" + self.path[11:]
                                     + "?X-Amz-Signature=fake")
                else:
                    self.send_response(303)
                    self.send_header(
                        "Location", "https://urs.earthdata.nasa.gov/oauth/"
                        "authorize?client_id=fake")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            path = os.path.join(folder, self.path.split("?")[0][7:])
            if not os.path.isfile(path):
                self.send_response(404)
                self.end_headers()
                return
            data = open(path, "rb").read()
            span = self.headers.get("Range")
            if span:
                lo, hi = span.split("=")[1].split("-")
                lo = int(lo)
                hi = min(int(hi) if hi else len(data) - 1, len(data) - 1)
                self.send_response(206)
                self.send_header("Content-Range", "bytes {}-{}/{}".format(
                    lo, hi, len(data)))
                part = data[lo:hi + 1]
            else:
                self.send_response(200)
                part = data
            self.send_header("Content-Length", str(len(part)))
            self.send_header("Accept-Ranges", "bytes")
            self.end_headers()
            self.wfile.write(part)

        def do_HEAD(self):
            path = os.path.join(folder, self.path.split("?")[0][7:])
            self.send_response(200 if os.path.isfile(path) else 404)
            if os.path.isfile(path):
                self.send_header("Content-Length",
                                 str(os.path.getsize(path)))
                self.send_header("Accept-Ranges", "bytes")
            self.end_headers()

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:{}/protected/".format(server.server_port)
    return server, {k: base + n for k, n in names.items()}, requests


@check(500)
def nasa_wrong_key():
    """Неверный ключ: хранилище ведёт на страницу входа, окно стирает
    ключ и говорит об этом."""
    from qgis.core import QgsSettings
    from planetx.core import sentinel as s2
    from planetx.ui import sentinel as ui
    dialog = state["window"].sentinel_dialog
    server, hrefs, requests = _fake_nasa(os.path.join(TEMP,
                                                      "planetx_fake_nasa"))
    state["fake_nasa"] = (server, hrefs, requests)
    assets = {k: s2.Asset(h, 1.0, 0.0, 0, None) for k, h in hrefs.items()}
    scene = s2.Scene("FAKE_NASA", "2024-10-23 17:53", 0.0, "ASTER VNIR TIR",
                     32611, 36.0, "", assets, "aster_nasa")
    state["fake_scene"] = scene
    QgsSettings().setValue(ui.EARTHDATA_KEY, "wrong-key")
    dialog._start_nasa_build(scene, ["aster_false"],
                             os.path.join(TEMP, "planetx_nasa"))
    state["ls_build"] = time.monotonic()


@check(500)
def nasa_wrong_key_check():
    from qgis.core import QgsSettings
    from planetx.ui import sentinel as ui
    dialog = state["window"].sentinel_dialog
    if dialog.signing is not None and time.monotonic() \
            - state["ls_build"] < 20.0:
        return 500
    result["nasa"]["wrong_key"] = {
        "status": dialog.status.text(),
        "key_removed": not QgsSettings().value(ui.EARTHDATA_KEY, ""),
        "requests": len(state["fake_nasa"][2])}
    return None


@check(500)
def nasa_edge():
    """Участок за краем снимка сцены (в 40 км от поддельных файлов):
    слоёв нет, окно говорит, что в каналах нет данных. До 0.77.0 окно
    добавляло слои из одних NaN."""
    from qgis.core import QgsSettings
    from planetx.core import sentinel as s2
    from planetx.ui import sentinel as ui
    dialog = state["window"].sentinel_dialog
    QgsSettings().setValue(ui.EARTHDATA_KEY, FAKE_KEY)
    state["ring_kept"] = dialog.ring_used
    dialog.ring_used = s2.square(37.2, -117.7, 2000.0)
    dialog._start_nasa_build(state["fake_scene"], ["aster_false"],
                             os.path.join(TEMP, "planetx_nasa_edge"))
    state["ls_build"] = time.monotonic()


@check(500)
def nasa_edge_check():
    from qgis.core import QgsProject
    dialog = state["window"].sentinel_dialog
    if (dialog.signing is not None or dialog.build_job is not None) \
            and time.monotonic() - state["ls_build"] < 60.0:
        return 500
    group = QgsProject.instance().layerTreeRoot().findGroup("ASTER")
    result["nasa"]["edge"] = {
        "status": dialog.status.text(),
        "layers": len(group.findLayers()) if group else 0}
    if group is not None:
        QgsProject.instance().removeMapLayers(group.findLayerIds())
        QgsProject.instance().layerTreeRoot().removeChildNode(group)
    dialog.ring_used = state["ring_kept"]
    return None


@check(500)
def nasa_whole():
    """Вся сцена, исходные файлы: все файлы каналов скачаны, слой-набор
    из 8 каналов VNIR и TIR."""
    import shutil
    dialog = state["window"].sentinel_dialog
    folder = os.path.join(TEMP, "planetx_nasa_whole")
    shutil.rmtree(folder, ignore_errors=True)
    state["whole_folder"] = folder
    state["fake_nasa"][2].clear()
    dialog._start_nasa_build(state["fake_scene"], [], folder, whole=True)
    state["ls_build"] = time.monotonic()


@check(500)
def nasa_whole_check():
    from qgis.core import QgsProject
    dialog = state["window"].sentinel_dialog
    if (dialog.signing is not None or dialog.build_job is not None) \
            and time.monotonic() - state["ls_build"] < 120.0:
        return 500
    group = QgsProject.instance().layerTreeRoot().findGroup("ASTER")
    layers = [n.layer() for n in group.findLayers()] if group else []
    folder = state["whole_folder"]
    files = []
    for top, _, names in os.walk(folder):
        files += [n for n in names]
    files_requests = [r for r in state["fake_nasa"][2]
                      if r[0].startswith("/files/")]
    result["nasa"]["whole"] = {
        "status": dialog.status.text(),
        "layers": [(l.name(), l.isValid(), l.bandCount(),
                    l.renderer().type()) for l in layers],
        "files": sorted(files),
        "key_sent_to_files": any(r[1] for r in files_requests)}
    if group is not None:
        QgsProject.instance().removeMapLayers(group.findLayerIds())
        QgsProject.instance().layerTreeRoot().removeChildNode(group)
    return None


@check(500)
def nasa_build():
    """Верный ключ: адреса подписаны, каналы прочитаны, слои в проекте."""
    from qgis.core import QgsSettings
    from planetx.ui import sentinel as ui
    dialog = state["window"].sentinel_dialog
    QgsSettings().setValue(ui.EARTHDATA_KEY, FAKE_KEY)
    folder = os.path.join(TEMP, "planetx_nasa")
    state["nasa_folder"] = folder
    dialog._start_nasa_build(state["fake_scene"],
                             ["aster_false", "aster_swir", "quartz",
                              "all_bands"], folder)
    state["ls_build"] = time.monotonic()


@check(500)
def nasa_built():
    from qgis.core import QgsProject, QgsSettings
    from planetx.ui import sentinel as ui
    dialog = state["window"].sentinel_dialog
    spent = time.monotonic() - state["ls_build"]
    if (dialog.signing is not None or dialog.build_job is not None) \
            and spent < 120.0:
        return 500
    out = result["nasa"]
    out["build_status"] = dialog.status.text()
    server, hrefs, requests = state["fake_nasa"]
    auth = [r for r in requests if r[0].startswith("/protected/")]
    files = [r for r in requests if r[0].startswith("/files/")]
    out["signed_requests"] = len(auth)
    out["file_requests"] = len(files)
    out["key_sent_to_files"] = any(r[1] for r in files)
    group = QgsProject.instance().layerTreeRoot().findGroup("ASTER")
    layers = [n.layer() for n in group.findLayers()] if group else []
    out["layers"] = [(l.name(), l.isValid(), l.bandCount()) for l in layers]
    folder = state["nasa_folder"]
    tifs = [n for n in sorted(os.listdir(folder)) if n.endswith(".tif")] \
        if os.path.isdir(folder) else []
    out["files"] = tifs
    for name in tifs:
        if name.endswith("_all_bands.tif"):
            out["all_bands"] = _all_bands_info(os.path.join(folder, name))
    if group is not None:
        QgsProject.instance().removeMapLayers(group.findLayerIds())
        QgsProject.instance().layerTreeRoot().removeChildNode(group)
    QgsSettings().remove(ui.EARTHDATA_KEY)
    server.shutdown()
    dialog.close()
    return None


@check(500)
def aster_open():
    """Снимки ASTER у Куприта: участок 10 км, даты сегодняшние - окно
    ставит 2000-2006 годы."""
    window = state["window"]
    window.set_body("earth")
    dialog = window.sentinel_here(*CUPRITE)
    dialog.side.setValue(10.0)
    dialog.mission.setCurrentIndex(dialog.mission.findData("aster"))
    state["ls_started"] = time.monotonic()
    result["aster"] = {
        "dates": [dialog.start.date().toString("yyyy-MM-dd"),
                  dialog.end.date().toString("yyyy-MM-dd")],
        "clear_enabled": dialog.clear.isEnabled(),
        "products": [(dialog.products.item(n).text(),
                      dialog.products.item(n).checkState() ==
                      _qt_checked())
                     for n in range(dialog.products.count())]}


def _qt_checked():
    from qgis.PyQt.QtCore import Qt
    return Qt.CheckState.Checked


@check(500)
def aster_wait():
    dialog = state["window"].sentinel_dialog
    spent = time.monotonic() - state["ls_started"]
    busy = dialog.reply is not None or dialog.cloud_jobs \
        or dialog.sas_reply is not None or dialog.sas_waiting
    if busy and spent < 240.0:
        return 500
    out = result["aster"]
    out["seconds"] = round(spent, 1)
    out["scenes"] = len(dialog.scenes)
    out["tiles"] = sorted({s.tile for s in dialog.scenes})
    out["unread"] = sum(1 for c, _ in dialog.clouds.values() if c is None)
    shown = [dialog.list.topLevelItem(n)
             for n in range(dialog.list.topLevelItemCount())
             if not dialog.list.topLevelItem(n).isHidden()]
    out["shown"] = len(shown)
    # Сцена с SWIR - первая из показанных с тайлом «ASTER».
    pick = [it for it in shown if it.text(4) == "ASTER"]
    out["first"] = [pick[0].text(c) for c in range(5)] if pick else None
    out["status"] = dialog.status.text()
    if pick:
        dialog.list.setCurrentItem(pick[0])
    return None


@check(500)
def aster_build():
    from qgis.PyQt.QtCore import Qt
    dialog = state["window"].sentinel_dialog
    for n in range(dialog.products.count()):
        dialog.products.item(n).setCheckState(Qt.CheckState.Checked)
    folder = os.path.join(TEMP, "planetx_aster")
    state["aster_folder"] = folder
    dialog.add(folder=folder)
    state["ls_build"] = time.monotonic()


@check(500)
def aster_frame():
    """Кадр для объявления: на глобусе только индекс каолинита у Куприта.
    Запускается вместо aster_built, тот убирает слои."""
    from planetx.core.navigation import Pose
    from qgis.core import QgsProject
    window = state["window"]
    dialog = window.sentinel_dialog
    spent = time.monotonic() - state["ls_build"]
    if (dialog.build_job is not None or dialog.sas_waiting) \
            and spent < 300.0:
        return 500
    root = QgsProject.instance().layerTreeRoot()
    group = root.findGroup("ASTER")
    shown = []
    for node in group.findLayers() if group else []:
        on = "kaolinite" in node.layer().source()
        node.setItemVisibilityChecked(on)
        window.set_layer_shown(node.layer().id(), on)
        if on:
            shown.append(node.layer().name())
    dialog.close()
    nav = window.view.navigator
    nav.stop()
    nav.show(Pose(CUPRITE[0] - 0.06, CUPRITE[1], 17000.0, 0.0, 45.0))
    state["frame_started"] = time.monotonic()
    result["aster_frame"] = {"shown": shown}
    return None


@check(1000)
def aster_frame_shot():
    view = state["window"].view
    spent = time.monotonic() - state["frame_started"]
    if spent < 20.0 or (view.load_missing and spent < 90.0):
        return 1000
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_aster_globe.png"))
    state["window"].grab().save(os.path.join(TEMP,
                                             "planetx_aster_window.png"))
    result["aster_frame"].update({"seconds": round(spent, 1),
                                  "missing": view.load_missing})
    return None


@check(500)
def aster_built():
    from osgeo import gdal
    import numpy as np
    from qgis.core import QgsProject
    dialog = state["window"].sentinel_dialog
    spent = time.monotonic() - state["ls_build"]
    if (dialog.build_job is not None or dialog.sas_waiting) \
            and spent < 300.0:
        return 500
    out = result["aster"]
    out["build_seconds"] = round(spent, 1)
    out["build_status"] = dialog.status.text()
    out["preview"] = dialog.preview.pixmap() is not None \
        and not dialog.preview.pixmap().isNull()
    group = QgsProject.instance().layerTreeRoot().findGroup("ASTER")
    layers = [n.layer() for n in group.findLayers()] if group else []
    out["layers"] = [(l.name(), l.isValid(), l.renderer().type(),
                      l.bandCount(), l.metadata().rights()) for l in layers]
    folder = state["aster_folder"]
    files = sorted(os.listdir(folder)) if os.path.isdir(folder) else []
    out["files"] = files
    for name in files:
        if not name.endswith(".tif"):
            continue
        key = name[len("AST_20060815_"):-4]
        if key == "all_bands":
            out["all_bands"] = _all_bands_info(os.path.join(folder, name))
            continue
        ds = gdal.Open(os.path.join(folder, name))
        a = ds.ReadAsArray()
        finite = a[np.isfinite(a)]
        if key == "kaolinite":
            # Изменённые холмы Куприта (середина-правее, верх кадра)
            # против конуса выноса на юго-западе.
            h, w = a.shape
            out["kaolinite_hills_vs_southwest"] = [
                round(float(np.nanmedian(
                    a[int(h * .15):int(h * .45), int(w * .6):int(w * .85)])),
                    3),
                round(float(np.nanmedian(
                    a[int(h * .4):int(h * .8), int(w * .05):int(w * .3)])),
                    3)]
        out[key] = {"size": [ds.RasterXSize, ds.RasterYSize],
                    "res": round(ds.GetGeoTransform()[1], 1),
                    "valid": round(finite.size / a.size, 3),
                    "p2_p50_p98": [round(float(np.percentile(finite, q)), 3)
                                   for q in (2, 50, 98)]
                    if finite.size else None}
        ds = None
    dialog.grab().save(os.path.join(TEMP, "planetx_aster_dialog.png"))
    if group is not None:
        QgsProject.instance().removeMapLayers(group.findLayerIds())
        QgsProject.instance().layerTreeRoot().removeChildNode(group)
    dialog.mission.setCurrentIndex(dialog.mission.findData("sentinel2"))
    out["dates_back"] = dialog.start.date().toString("yyyy-MM-dd")
    dialog.close()
    return None


@check(500)
def landsat_build():
    from qgis.PyQt.QtCore import Qt
    window = state["window"]
    dialog = window.sentinel_dialog
    want = ("natural", "ndvi", "lst", "all_bands")
    for n in range(dialog.products.count()):
        item = dialog.products.item(n)
        item.setCheckState(Qt.CheckState.Checked
                           if item.data(Qt.ItemDataRole.UserRole) in want
                           else Qt.CheckState.Unchecked)
    folder = os.path.join(TEMP, "planetx_landsat")
    state["ls_folder"] = folder
    dialog.add(folder=folder)
    state["ls_build"] = time.monotonic()


@check(500)
def landsat_built():
    from osgeo import gdal
    import numpy as np
    from qgis.core import QgsProject
    window = state["window"]
    dialog = window.sentinel_dialog
    spent = time.monotonic() - state["ls_build"]
    if (dialog.build_job is not None or dialog.sas_waiting) \
            and spent < 240.0:
        return 500
    out = result["landsat"]
    out["build_seconds"] = round(spent, 1)
    out["build_status"] = dialog.status.text()
    out["preview"] = dialog.preview.pixmap() is not None \
        and not dialog.preview.pixmap().isNull()
    group = QgsProject.instance().layerTreeRoot().findGroup("Landsat")
    layers = [n.layer() for n in group.findLayers()] if group else []
    out["layers"] = [(l.name(), l.isValid(), l.renderer().type(),
                      l.metadata().rights(), l.metadata().abstract())
                     for l in layers]
    folder = state["ls_folder"]
    files = sorted(os.listdir(folder)) if os.path.isdir(folder) else []
    out["files"] = files
    for name in files:
        if not name.endswith(".tif"):
            continue
        ds = gdal.Open(os.path.join(folder, name))
        a = ds.ReadAsArray()
        finite = a[np.isfinite(a)]
        key = name.rsplit("_", 1)[1][:-4]
        out[key] = {"size": [ds.RasterXSize, ds.RasterYSize],
                    "res": ds.GetGeoTransform()[1],
                    "valid": round(finite.size / a.size, 3),
                    "median": round(float(np.median(finite)), 3)
                    if finite.size else None,
                    "range": [round(float(finite.min()), 2),
                              round(float(finite.max()), 2)]
                    if finite.size else None}
        ds = None
        if name.endswith("_all_bands.tif"):
            out["all_bands"] = _all_bands_info(os.path.join(folder, name))
    out["all_bands_style"] = [
        (l.renderer().redBand(), l.renderer().greenBand(),
         l.renderer().blueBand()) for l in layers
        if l.renderer().type() == "multibandcolor" and l.bandCount() > 4]
    dialog.grab().save(os.path.join(TEMP, "planetx_landsat_dialog.png"))
    if group is not None:
        QgsProject.instance().removeMapLayers(group.findLayerIds())
        QgsProject.instance().layerTreeRoot().removeChildNode(group)
    dialog.close()
    return None


DEM_POINT = (65.0348, 60.1166)  # гора Народная, 1895 м


def _dem_set(kind):
    """Выбор рельефа kind окна «Источники данных», перелёт к Народной."""
    from qgis.core import QgsSettings
    from planetx.core import sources
    from planetx.core.navigation import Pose
    window = state["window"]
    QgsSettings().setValue(sources.DEM_KEY, kind)
    window.sources_changed("terrain")
    window.view.navigator.show(Pose(DEM_POINT[0], DEM_POINT[1], 6000.0,
                                    0.0, 0.0))
    window.view.update()
    state["dem"] = {"kind": kind, "start": time.monotonic(), "still": 0}


def _dem_wait():
    """Ждать, пока загрузчик высот опустеет, и записать высоты у
    вершины: наибольшая в квадрате 600 м и уровни тайлов."""
    import numpy as np
    window = state["window"]
    info = state["dem"]
    spent = time.monotonic() - info["start"]
    loader = window.terrain_loader
    busy = bool(loader.replies) or bool(loader.decoding)
    info["still"] = 0 if busy else info["still"] + 1
    if (info["still"] < 3 or spent < 5.0) and spent < 150.0:
        return 1000
    store = window.view.store
    lat, lon = DEM_POINT
    k = 1.0 / (111320.0 * math.cos(math.radians(lat)))
    offsets = np.arange(-300.0, 300.0, 10.0)
    lats = lat + offsets[:, None] / 111320.0 + 0 * offsets[None, :]
    lons = lon + 0 * offsets[:, None] + offsets[None, :] * k
    heights = store.heights_at(lats.ravel(), lons.ravel(), scaled=False)
    model = window.dem
    result.setdefault("dem", {})[info["kind"] or "terrarium"] = {
        "seconds": round(spent, 1),
        "peak": round(float(np.nanmax(heights)), 1),
        "levels": max([key[0] for key in store.tiles] or [0]),
        "errors": model.errors if model is not None else None,
        "last_error": model.last_error[:200] if model is not None else None,
        "credit": window._terrain_credit()[-60:],
    }
    window.view.grabFramebuffer().save(os.path.join(
        TEMP, "planetx_dem_{}.png".format(info["kind"] or "terrarium")))
    return None


@check(1000)
def dem_terrarium():
    _dem_set("")


@check(1000)
def dem_terrarium_wait():
    return _dem_wait()


@check(1000)
def dem_copernicus():
    _dem_set("copernicus30")


@check(1000)
def dem_copernicus_wait():
    return _dem_wait()


@check(1000)
def dem_gedtm():
    _dem_set("gedtm30")


@check(1000)
def dem_gedtm_wait():
    return _dem_wait()


@check(500)
def dem_off():
    _dem_set("")
    result["dem"]["off_model"] = state["window"].dem is None


# Продукты MODIS: спутник окна, точка, даты, сторона участка, км.
MODIS_CASES = (
    ("modis_lst1", (58.0105, 56.2294), (2024, 7, 1),
     (2024, 7, 31), 20.0),
    ("modis_lst8", (58.0105, 56.2294), (2024, 6, 1), (2024, 8, 31), 20.0),
    ("modis_veg", (58.0105, 56.2294), (2024, 6, 1), (2024, 8, 31), 20.0),
    ("modis_snow1", (58.0105, 56.2294), (2025, 3, 1), (2025, 3, 31),
     20.0),
    ("modis_snow8", (58.0105, 56.2294), (2024, 12, 1), (2025, 2, 28),
     20.0),
    ("modis_burn", (-35.5, 150.0), (2019, 12, 1), (2019, 12, 31), 60.0),
)


@check(500)
def modis_run():
    """Все продукты MODIS по очереди: поиск, облачность, выгрузка всех
    продуктов первой сцены в проект, значения файлов."""
    names = os.environ.get("PLANETX_MODIS", "")
    state["modis"] = {"n": -1, "phase": "next", "cases": [
        c for c in MODIS_CASES if not names or c[0] in names.split(",")]}
    result["modis"] = {}


@check(1000)
def modis_wait():
    import numpy as np
    from osgeo import gdal
    from qgis.core import QgsProject
    from qgis.PyQt.QtCore import QDate, Qt
    window = state["window"]
    st = state["modis"]
    dialog = getattr(window, "sentinel_dialog", None)
    if st["phase"] == "next":
        st["n"] += 1
        if st["n"] >= len(st["cases"]):
            dialog.close()
            return None
        mission, point, start, end, side = st["cases"][st["n"]]
        dialog = window.sentinel_here(*point)
        dialog.side.setValue(side)
        dialog.start.setDate(QDate(*start))
        dialog.end.setDate(QDate(*end))
        dialog.mission.setCurrentIndex(dialog.mission.findData(mission))
        if dialog.searched != mission:
            dialog.search()
        st.update(phase="search", t=time.monotonic(), mission=mission)
        return 1000
    mission = st["mission"]
    out = result["modis"].setdefault(mission, {})
    spent = time.monotonic() - st["t"]
    if st["phase"] == "search":
        busy = dialog.reply is not None or dialog.cloud_jobs \
            or dialog.sas_reply is not None or dialog.sas_waiting
        if busy and spent < 240.0:
            return 1000
        shown = [dialog.list.topLevelItem(n)
                 for n in range(dialog.list.topLevelItemCount())
                 if not dialog.list.topLevelItem(n).isHidden()]
        out.update(search_seconds=round(spent, 1),
                   scenes=len(dialog.scenes),
                   unread=sum(1 for c, _ in dialog.clouds.values()
                              if c is None),
                   shown=len(shown), status=dialog.status.text(),
                   clouds=[[round(c or -1), round(v or -1)] for c, v in
                           list(dialog.clouds.values())[:12]],
                   first=[shown[0].text(c) for c in range(5)]
                   if shown else None)
        if not shown:
            st["phase"] = "next"
            return 500
        dialog.list.setCurrentItem(shown[0])
        for n in range(dialog.products.count()):
            dialog.products.item(n).setCheckState(Qt.CheckState.Checked)
        folder = os.path.join(TEMP, "planetx_modis")
        dialog.add(folder=folder)
        st.update(phase="build", t=time.monotonic())
        return 1000
    busy = dialog.build_job is not None or dialog.sas_waiting \
        or dialog.preview_job is not None
    if busy and spent < 240.0:
        return 1000
    out["build_seconds"] = round(spent, 1)
    out["build_status"] = dialog.status.text()
    out["preview"] = dialog.preview.pixmap() is not None \
        and not dialog.preview.pixmap().isNull()
    group = QgsProject.instance().layerTreeRoot().findGroup("MODIS")
    layers = [n.layer() for n in group.findLayers()] if group else []
    out["layers"] = []
    for layer in layers:
        ds = gdal.Open(layer.source())
        a = ds.ReadAsArray() if ds is not None else None
        ds = None
        finite = a[np.isfinite(a)] if a is not None else np.array([])
        out["layers"].append({
            "name": layer.name(), "valid": layer.isValid(),
            "crs": layer.crs().authid(),
            "size": [layer.width(), layer.height()],
            "data": round(finite.size / a.size, 3) if a is not None else 0,
            "range": [round(float(finite.min()), 2),
                      round(float(finite.max()), 2)] if finite.size
            else None,
            "rights": layer.metadata().rights()})
    if group is not None:
        QgsProject.instance().removeMapLayers(group.findLayerIds())
        QgsProject.instance().layerTreeRoot().removeChildNode(group)
    st["phase"] = "next"
    return 500


@check(500)
def landsat_rebuild():
    """После landsat_build: та же сцена ещё раз, пока прежние слои в
    проекте держат свои файлы. На прежнем коде - «Снимок не загружен:
    Deleting ... failed: Permission denied»."""
    dialog = state["window"].sentinel_dialog
    if dialog.build_job is not None or dialog.sas_waiting:
        return 500
    out = result.setdefault("landsat_again", {})
    out["first_status"] = dialog.status.text()
    dialog.add(folder=state["ls_folder"])
    state["ls_build"] = time.monotonic()
    return None


@check(500)
def landsat_rebuilt():
    from qgis.core import QgsProject
    dialog = state["window"].sentinel_dialog
    spent = time.monotonic() - state["ls_build"]
    if (dialog.build_job is not None or dialog.sas_waiting) \
            and spent < 240.0:
        return 500
    out = result["landsat_again"]
    out["status"] = dialog.status.text()
    group = QgsProject.instance().layerTreeRoot().findGroup("Landsat")
    layers = [n.layer() for n in group.findLayers()] if group else []
    out["layers"] = [(l.name(), l.isValid(),
                      os.path.basename(l.source())) for l in layers]
    out["files"] = sorted(os.listdir(state["ls_folder"]))
    if group is not None:
        QgsProject.instance().removeMapLayers(group.findLayerIds())
        QgsProject.instance().layerTreeRoot().removeChildNode(group)
    dialog.close()
    return None


def _all_bands_info(path):
    """Файл «Все каналы»: каналы с подписями и медианами, размер."""
    from osgeo import gdal
    import numpy as np
    ds = gdal.Open(path)
    out = {"size": [ds.RasterXSize, ds.RasterYSize],
           "res": ds.GetGeoTransform()[1], "bands": []}
    for n in range(1, ds.RasterCount + 1):
        band = ds.GetRasterBand(n)
        a = band.ReadAsArray()
        finite = a[np.isfinite(a)]
        out["bands"].append([band.GetDescription(),
                             round(float(np.median(finite)), 3)
                             if finite.size else None])
    ds = None
    out["mb"] = round(os.path.getsize(path) / 1e6, 1)
    return out


@check(500)
def sentinel_build():
    from qgis.PyQt.QtCore import Qt
    window = state["window"]
    dialog = window.sentinel_dialog
    want = ("natural", "infrared", "ndvi", "ndmi", "all_bands")
    for n in range(dialog.products.count()):
        item = dialog.products.item(n)
        item.setCheckState(Qt.CheckState.Checked
                           if item.data(Qt.ItemDataRole.UserRole) in want
                           else Qt.CheckState.Unchecked)
    folder = os.path.join(TEMP, "planetx_s2")
    state["s2_folder"] = folder
    dialog.mode.setCurrentIndex(0)
    dialog.add(folder=folder)
    state["s2_build"] = time.monotonic()


@check(500)
def sentinel_built():
    from osgeo import gdal
    import numpy as np
    from qgis.core import QgsProject
    window = state["window"]
    dialog = window.sentinel_dialog
    spent = time.monotonic() - state["s2_build"]
    if dialog.build_job is not None and spent < 240.0:
        return 500
    out = result["sentinel"]
    out["build_seconds"] = round(spent, 1)
    out["build_status"] = dialog.status.text()
    group = QgsProject.instance().layerTreeRoot().findGroup("Sentinel-2")
    layers = [n.layer() for n in group.findLayers()] if group else []
    out["layers"] = [(l.name(), l.isValid(), l.renderer().type(),
                      l.metadata().rights()) for l in layers]
    files = sorted(os.listdir(state["s2_folder"])) \
        if os.path.isdir(state["s2_folder"]) else []
    out["files"] = files
    for name in files:
        if name.endswith("_ndvi.tif"):
            ds = gdal.Open(os.path.join(state["s2_folder"], name))
            a = ds.ReadAsArray()
            finite = a[np.isfinite(a)]
            out["ndvi"] = {"size": [ds.RasterXSize, ds.RasterYSize],
                           "res": ds.GetGeoTransform()[1],
                           "valid": round(finite.size / a.size, 3),
                           "mean": round(float(finite.mean()), 3)
                           if finite.size else None}
            ds = None
        if name.endswith("_natural.tif"):
            ds = gdal.Open(os.path.join(state["s2_folder"], name))
            a = ds.ReadAsArray()
            out["natural_median"] = [round(float(np.nanmedian(b)), 3)
                                     for b in a]
            ds = None
        if name.endswith("_all_bands.tif"):
            out["all_bands"] = _all_bands_info(
                os.path.join(state["s2_folder"], name))
    out["all_bands_style"] = [
        (l.renderer().redBand(), l.renderer().greenBand(),
         l.renderer().blueBand()) for l in layers
        if l.renderer().type() == "multibandcolor" and l.bandCount() > 4]
    dialog.grab().save(os.path.join(TEMP, "planetx_sentinel_dialog.png"))
    return None


@check(500)
def sentinel_link():
    """Вся сцена ссылкой VRT: естественные цвета."""
    from qgis.PyQt.QtCore import Qt
    dialog = state["window"].sentinel_dialog
    for n in range(dialog.products.count()):
        item = dialog.products.item(n)
        item.setCheckState(Qt.CheckState.Checked
                           if item.data(Qt.ItemDataRole.UserRole) ==
                           "natural" else Qt.CheckState.Unchecked)
    dialog.mode.setCurrentIndex(1)
    dialog.add(folder=os.path.join(TEMP, "planetx_s2_link"))
    state["s2_build"] = time.monotonic()


@check(500)
def sentinel_link_done():
    from qgis.core import QgsProject
    dialog = state["window"].sentinel_dialog
    spent = time.monotonic() - state["s2_build"]
    if dialog.build_job is not None and spent < 120.0:
        return 500
    group = QgsProject.instance().layerTreeRoot().findGroup("Sentinel-2")
    vrt = [n.layer() for n in group.findLayers()
           if n.layer().source().endswith(".vrt")] if group else []
    result["sentinel"]["link"] = {
        "seconds": round(spent, 1), "status": dialog.status.text(),
        "layers": [(l.name(), l.isValid(), l.width(), l.height())
                   for l in vrt]}
    dialog.mode.setCurrentIndex(0)
    return None


@check(500)
def sentinel_place():
    """Участок - многоугольник «Моих меток»: поиск по контуру."""
    from planetx.core.features import Shape
    window = state["window"]
    lat, lon = ROUTE_A
    ring = [(lat - 0.004, lon - 0.008), (lat - 0.004, lon + 0.008),
            (lat + 0.006, lon)]
    key = window.myplaces.add(Shape("polygon", ring, name="S2 area"))
    place = window.myplaces.find(key)
    dialog = window.sentinel_place(place)
    result["sentinel"]["place"] = {
        "side_hidden": dialog.side.isHidden(),
        "ring": len(dialog.ring_used), "where": dialog.where.text()}
    window.myplaces.remove(key)
    from planetx.core.navigation import Pose
    window.view.navigator.stop()
    window.view.navigator.set_pose(Pose(lat, lon, 6000.0, 0.0, 30.0))


@check(25000)
def sentinel_check():
    window = state["window"]
    view = window.view
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_sentinel.png"))
    window.sentinel_dialog.close()
    result["sentinel"]["gl"] = dict(view.gl_errors)


@check(300)
def journal_foreign():
    """Журнал пишет и чужие необработанные ошибки Python с именем
    модуля, и свои. Обработчик QGIS на время шага снят."""
    import sys
    from planetx import journal
    out = result.setdefault("journal_foreign", {})
    prior = journal._state["prior"]
    journal._state["prior"] = None
    try:
        for name, path in (
                ("foreign", os.path.join("python", "plugins", "otherone",
                                         "render.py")),
                ("own", os.path.join("python", "plugins", "planetx",
                                     "net", "overlay.py"))):
            code = compile("def slot():\n    raise ValueError('" + name
                           + " test')\nslot()\n", path, "exec")
            try:
                exec(code, {})
            except ValueError:
                sys.excepthook(*sys.exc_info())
    finally:
        journal._state["prior"] = prior
    with open(journal.path(), encoding="utf-8") as handle:
        tail = handle.read()[-3000:]
    out["hook"] = sys.excepthook is journal._state["hook"]
    out["foreign"] = "не PlanetX (otherone)" in tail \
        and "foreign test" in tail
    out["own"] = "own test" in tail


@check(300)
def overlay_deleted_layer():
    """Наложение со слоем, удалённым из проекта до пересборки, готовит
    отрисовку тайла без ошибки. 10 октября 2026 года ошибка Python
    в конце отрисовки роняла QGIS 3.36 в окне этой ошибки."""
    from qgis.core import QgsProject, QgsVectorLayer
    from planetx.net.overlay import LayerOverlay
    out = result.setdefault("overlay_deleted_layer", {})
    layer = QgsVectorLayer("Point?crs=EPSG:4326", "gone", "memory")
    QgsProject.instance().addMapLayer(layer)
    overlay = LayerOverlay([layer])
    QgsProject.instance().removeMapLayer(layer.id())
    from qgis.PyQt import sip
    from qgis.PyQt.QtCore import QCoreApplication, QEvent
    from planetx.qt_compat import enum
    QCoreApplication.sendPostedEvents(
        None, enum(QEvent, "Type", "DeferredDelete"))
    out["deleted"] = sip.isdeleted(layer)
    try:
        settings = overlay._settings((5, 10, 10))
        out["error"] = ""
        out["layers"] = len(settings.layers())
    except RuntimeError as error:
        out["error"] = str(error)
    finally:
        overlay.abort()
        overlay.deleteLater()


@check(2000)
def journal_hang():
    """Главный поток стоит внутри вызова Qt дольше journal.DUMP_AFTER -
    журнал пишет дамп процесса и стеки потоков C++ по нему."""
    import glob
    import time as _time
    from qgis.PyQt.QtCore import QThread
    from planetx import journal
    out = result.setdefault("journal_hang", {})
    out["watch"] = journal._state["watch"] is not None
    before = set(glob.glob(os.path.join(journal.folder(), "hang-*.dmp")))
    started = _time.monotonic()
    QThread.msleep(int((journal.DUMP_AFTER + 6) * 1000))
    out["slept"] = round(_time.monotonic() - started, 1)
    _time.sleep(1.5)
    made = set(glob.glob(os.path.join(journal.folder(), "hang-*.dmp")))
    made -= before
    out["dumps"] = len(made)
    out["dump_kb"] = [round(os.path.getsize(n) / 1024) for n in made]
    with open(journal.path(), encoding="utf-8") as handle:
        text = handle.read()
    names = [os.path.basename(n) for n in made]
    at = max((text.rfind(n) for n in names), default=-1)
    out["noted"] = at >= 0
    report = text[at:] if at >= 0 else ""
    lines = report.split("\n")
    out["main_frames"] = [line.strip() for line in lines[2:8]]
    out["sleep"] = any("Sleep" in line for line in lines[2:6])
    out["report_kb"] = round(len(report.encode("utf-8")) / 1024, 1)
    out["threads"] = sum(1 for line in lines if not line.startswith(" ")
                         and line[:1].isalpha())
    for name in made:
        os.remove(name)


@check(2000)
def journal_hang_gil():
    """Главный поток стоит в вызове C, не отпустив GIL, - так висел
    проверочный QGIS 10 октября 2026 года. Поток Python внутри QGIS
    тут бессилен, дамп пишет процесс-сторож hangwatch.py снаружи."""
    import ctypes
    import glob
    import time as _time
    from planetx import journal
    out = result.setdefault("journal_hang_gil", {})
    out["watch"] = bool(journal._state["watch"])
    before = set(glob.glob(os.path.join(journal.folder(), "hang-*.dmp")))
    started = _time.monotonic()
    # PyDLL держит GIL на время вызова.
    ctypes.PyDLL("kernel32").Sleep(int((journal.DUMP_AFTER + 8) * 1000))
    out["slept"] = round(_time.monotonic() - started, 1)
    _time.sleep(3.0)
    made = set(glob.glob(os.path.join(journal.folder(), "hang-*.dmp")))
    made -= before
    out["dumps"] = len(made)
    with open(journal.path(), encoding="utf-8") as handle:
        text = handle.read()
    names = [os.path.basename(n) for n in made]
    at = max((text.rfind(n) for n in names), default=-1)
    report = text[at:] if at >= 0 else ""
    lines = report.split("\n")
    out["main_frames"] = [line.strip() for line in lines[1:7]]
    out["sleep"] = any("Sleep" in line for line in lines[1:6])
    out["report_kb"] = round(len(report.encode("utf-8")) / 1024, 1)
    for name in made:
        os.remove(name)


@check(2000)
def journal_deadlock():
    """Главный поток ждёт мьютекс Qt, который держит рабочий поток, -
    так выглядит взаимная блокировка внутри QGIS. В разборе дампа
    главный поток стоит в QMutex, рабочий - в своём ожидании."""
    import glob
    import threading
    import time as _time
    from qgis.PyQt.QtCore import QMutex, QThread
    from planetx import journal
    out = result.setdefault("journal_deadlock", {})
    mutex = QMutex()
    taken = threading.Event()

    def holder():
        mutex.lock()
        taken.set()
        QThread.msleep(int((journal.DUMP_AFTER + 6) * 1000))
        mutex.unlock()
    worker = threading.Thread(target=holder, name="planetx-holder")
    before = set(glob.glob(os.path.join(journal.folder(), "hang-*.dmp")))
    worker.start()
    taken.wait(5)
    started = _time.monotonic()
    mutex.lock()
    mutex.unlock()
    out["waited"] = round(_time.monotonic() - started, 1)
    worker.join()
    _time.sleep(1.5)
    made = set(glob.glob(os.path.join(journal.folder(), "hang-*.dmp")))
    made -= before
    out["dumps"] = len(made)
    with open(journal.path(), encoding="utf-8") as handle:
        text = handle.read()
    names = [os.path.basename(n) for n in made]
    at = max((text.rfind(n) for n in names), default=-1)
    report = text[at:] if at >= 0 else ""
    blocks = report.split("\n")
    main = []
    for line in blocks[3:]:
        if not line.startswith(" "):
            break
        main.append(line.strip())
    out["main_frames"] = main[:8]
    out["main_in_mutex"] = any("Mutex" in line for line in main[:8])
    out["holder_seen"] = report.count("msleep") + report.count("SleepEx")
    for name in made:
        os.remove(name)


@check(300)
def journal_crash():
    """Сеанс умершего процесса с файлом стеков QGIS даёт записи
    о падении, ошибки рабочего потока и «неподнимаемые» ошибки идут
    в журнал, строка памяти пишется, свой сеанс жив."""
    import gc
    import tempfile
    import threading
    from planetx import journal
    out = result.setdefault("journal_crash", {})
    pid = 4000000
    while journal.alive(pid):
        pid += 4
    os.makedirs(journal.sessions(), exist_ok=True)
    session = os.path.join(journal.sessions(), "{}.txt".format(pid))
    with open(session, "w", encoding="utf-8") as handle:
        handle.write("2026-10-10 12:00:00")
    stacks = os.path.join(tempfile.gettempdir(),
                          "qgis-python-crash-info-{}".format(pid))
    with open(stacks, "w", encoding="utf-8") as handle:
        handle.write("Windows fatal exception: access violation\n\n"
                     "Current thread:\n  File \"fake_crash.py\", line 7\n")
    try:
        out["found"] = journal.harvest() == [pid]
    finally:
        os.remove(stacks)
    out["session_removed"] = not os.path.exists(session)
    out["own_session"] = os.path.exists(os.path.join(
        journal.sessions(), "{}.txt".format(os.getpid())))
    out["alive_self"] = journal.alive(os.getpid())

    def worker():
        raise ValueError("thread test")
    thread = threading.Thread(target=worker, name="planetx-test")
    thread.start()
    thread.join()

    class Bad:
        def __del__(self):
            raise ValueError("unraisable test")
    Bad()
    gc.collect()
    journal.note_resources()
    with open(journal.path(), encoding="utf-8") as handle:
        tail = handle.read()[-6000:]
    out["crash_line"] = "{}".format(pid) in tail and "fake_crash.py" in tail
    out["thread"] = "thread test" in tail and "planetx-test" in tail
    out["unraisable"] = "unraisable test" in tail
    out["resources"] = "GDI" in tail


@check(500)
def opacity_slider():
    """Ползунок непрозрачности под «Моими метками»: многоугольник,
    затем папка с двумя метками. Значение пишется в файл меток,
    выделение переживает перестройку списка."""
    from qgis.PyQt.QtCore import QCoreApplication
    from planetx.core.features import Shape
    from planetx.ui.myplaces import MyPlaces
    window = state["window"]
    store = window.myplaces
    panel = window.panel
    out = result.setdefault("opacity_slider", {})

    def settle():
        _wait = time.monotonic() + 0.4
        while time.monotonic() < _wait:
            QCoreApplication.processEvents()

    def select(keys):
        panel.list.clearSelection()
        for key in keys:
            panel.select_place(key)
            panel.list.currentItem().setSelected(True)
        settle()

    folder = store.add_folder("Прозрачность")
    poly = store.add(Shape("polygon", [(57.9, 56.1), (57.9, 56.3),
                                       (58.0, 56.2)],
                           color=(255, 0, 0, 200), width=2.0,
                           fill=(255, 0, 0, 100), name="Квадрат"),
                     folder=folder)
    line = store.add(Shape("line", [(57.8, 56.0), (57.85, 56.4)],
                           color=(0, 0, 255, 255), width=2.0, name="Линия"),
                     folder=folder)
    settle()
    select([poly])
    out["enabled"] = panel.opacity.isEnabled()
    out["start"] = panel.opacity.value()
    panel.opacity.setValue(39)
    settle()
    shape = store.find(poly).shape
    out["poly_after"] = [shape.color[3], shape.fill[3]]
    out["still_selected"] = panel.list.selected_keys()
    reread = MyPlaces(store.path)
    reread.load()
    out["file"] = [reread.find(poly).shape.color[3],
                   reread.find(poly).shape.fill[3]]
    panel.opacity.setValue(78)
    settle()
    shape = store.find(poly).shape
    out["poly_back"] = [shape.color[3], shape.fill[3]]
    select([folder])
    out["folder_start"] = panel.opacity.value()
    panel.opacity.setValue(0)
    settle()
    out["folder_zero"] = [store.find(poly).shape.color[3],
                          store.find(line).shape.color[3]]
    select([folder])
    out["folder_reselect"] = panel.opacity.value()
    panel.opacity.setValue(50)
    settle()
    out["folder_from_zero"] = [store.find(poly).shape.color[3],
                               store.find(poly).shape.fill[3],
                               store.find(line).shape.color[3]]
    panel.list.clearSelection()
    settle()
    out["disabled_empty"] = not panel.opacity.isEnabled()
    store.remove(folder)


@check(1500)
def layer_click():
    """Щелчки мышью по флажку строки «Слоёв проекта» глобуса в обоих
    режимах follow. Падение QGIS 10 октября 2026 года - флажок
    перестраивал список прямо из обработчика щелчка, строка удалялась,
    пока Qt ещё меняла её флажок. Строка обязана пережить щелчок."""
    from qgis.core import QgsProject, QgsVectorLayer
    from qgis.PyQt.QtCore import QPoint, Qt
    from qgis.PyQt.QtTest import QTest
    from planetx.qt_compat import enum
    left = enum(Qt, "MouseButton", "LeftButton")
    window = state["window"]
    out = result.setdefault("layer_click", {"clicks": []})
    layers_added = [QgsVectorLayer("LineString?crs=EPSG:4326",
                                   "click {}".format(n), "memory")
                    for n in range(3)]
    QgsProject.instance().addMapLayers(layers_added)
    window._show_layers()
    # Слои проекта - свой список раздела «Проект QGIS» (с 0.92.0). Щелчок
    # идёт в список строки: прямоугольник строки чужого списка попадал
    # в строку «Основы» с меню, и модальное меню вешало прогон.
    out["panel_rows"] = len(window.panel.project_rows())

    import planetx.ui.panel as panel_module

    def click(tree, item):
        rect = tree.visualItemRect(item)
        point = QPoint(rect.left() + 10, rect.center().y())
        # Панель узнаёт щелчок по «⋯» по положению курсора мыши, а QTest
        # курсор не двигает: при мыши правее списка открывалось меню
        # строки, его exec вешал прогон. Курсор панели на время щелчка -
        # точка щелчка, мышь пользователя не трогается.
        where = tree.viewport().mapToGlobal(point)

        class Cursor:
            @staticmethod
            def pos():
                return where
        real = panel_module.QCursor
        panel_module.QCursor = Cursor
        try:
            QTest.mouseClick(tree.viewport(), left, enum(
                Qt, "KeyboardModifier", "NoModifier"), point)
        finally:
            panel_module.QCursor = real

    for follow in (False, True):
        window.follow = follow
        for item in window.panel.project_rows():
            if not item.text(0).startswith("click "):
                continue
            before = str(item.checkState(0))
            click(item.treeWidget(), item)
            # Флажки слоёв уходят окну через проход цикла событий.
            QgsApplication.processEvents()
            QgsApplication.processEvents()
            alive = not _deleted(item)
            out["clicks"].append((
                follow, alive, before,
                str(item.checkState(0)) if alive else "-"))
            break
    window.follow = False
    QgsProject.instance().removeMapLayers([l.id() for l in layers_added])


def _deleted(item):
    try:
        item.text(0)
        return False
    except RuntimeError:
        return True


@check(500)
def route_long():
    """Дальний маршрут через сервис OSRM: Пермь - Сочи, около
    2900 км. Три запроса к серверу FOSSGIS с паузой не меньше 1 с."""
    import time as _time
    from qgis.core import QgsSettings
    from planetx.core import sources
    QgsSettings().setValue(sources.ROUTER_ON_KEY, True)
    window = state["window"]
    window.set_body("earth")
    manager = window.route_manager
    manager.clear()
    manager.set_mode("car")
    state["route_keys"] = []
    state["route_start"] = _time.monotonic()
    manager.finished.connect(lambda key: state["route_keys"].append(
        (key, round(_time.monotonic() - state["route_start"], 1))))
    window.route_point(*ROUTE_A, "Пермь", end=False)
    window.route_point(43.5855, 39.7231, "Сочи", end=True)


@check(500)
def route_long_check():
    _route_wait()
    window = state["window"]
    out = {"car": _route_report(window)}
    from planetx.core.navigation import Pose
    view = window.view
    for name, pose in (("long", Pose(51.0, 48.0, 3500000.0, 0.0, 0.0)),
                       ("near", Pose(58.00, 56.27, 15000.0, 0.0, 0.0))):
        view.navigator.stop()
        view.navigator.set_pose(pose)
        until = __import__("time").monotonic() + 8.0
        while __import__("time").monotonic() < until:
            QgsApplication.processEvents()
            __import__("time").sleep(0.05)
        view.grabFramebuffer().save(
            os.path.join(TEMP, "planetx_route_%s.png" % name))
    # Велосипед по короткому пути, ссылка строки под поиском.
    manager = window.route_manager
    manager.clear()
    window.route_point(*ROUTE_A, "Эспланада", end=False)
    window.route_point(*ROUTE_B, "Мотовилиха", end=True)
    _route_wait()
    manager.link("bike")
    _route_wait()
    out["bike"] = _route_report(window)
    out["links"] = window.panel.answer.text()[-300:]
    for p in list(window.myplaces.places):
        if p.name.startswith("Маршрут") or p.name.startswith("Route"):
            window.myplaces.remove(p.key)
    manager.clear()
    result["route_long"] = out


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
def menu_links():
    """Свои пункты меню на глобусе: подменю «Открыть в браузере», адрес
    с точкой и масштабом браузеру, окно списка с проверкой строк."""
    from qgis.PyQt.QtWidgets import QMenu
    from planetx.core.navigation import Pose
    from planetx.ui import globemenu, menulinks
    window = state["window"]
    window.set_body("earth")
    view = window.view
    view.navigator.stop()
    view.navigator.set_pose(Pose(ROUTE_A[0], ROUTE_A[1], 3000.0, 0.0, 0.0))
    view.grabFramebuffer()
    old = menulinks.QgsSettings().value(menulinks.LINKS_KEY, "")
    opened = []

    class Browser:
        @staticmethod
        def openUrl(url):
            opened.append(url.toString())
    real = menulinks.QDesktopServices
    menulinks.QDesktopServices = Browser
    out = {}
    try:
        menulinks.save([("Пример", "https://example.org/?p={lat},{lon}"
                         "&z={zoom}")])
        ratio = view.devicePixelRatioF()
        px, py = view.width() * ratio / 2.0, view.height() * ratio / 2.0
        before = set(window.findChildren(QMenu))
        globemenu.show(window, px, py)
        menus = [m for m in window.findChildren(QMenu) if m not in before]
        sub = [m for m in menus if m.title() == "Открыть в браузере"]
        out["submenu"] = [a.text() for a in sub[0].actions()] if sub \
            else None
        if sub:
            sub[0].actions()[0].trigger()
        out["opened"] = opened
        for menu in menus:
            menu.close()
        dialog = menulinks.MenuLinksDialog(window)
        out["rows"] = dialog.table.rowCount()
        dialog._add()
        dialog.table.item(1, 1).setText("https://x.org/{lat}")
        dialog.accept()
        out["bad_status"] = dialog.status.text()
        out["bad_saved"] = len(menulinks.saved())
        dialog.table.item(1, 1).setText("https://x.org/{lat}/{lon}")
        dialog.accept()
        out["good_saved"] = [name for name, _ in menulinks.saved()]
        dialog.deleteLater()
    finally:
        menulinks.QDesktopServices = real
        menulinks.QgsSettings().setValue(menulinks.LINKS_KEY, old)
    result["menu_links"] = out


@check(500)
def region_hide():
    """Region KML: метка со «Скрывать дальше 50 км» видна с 40 км
    и скрыта со 100 км, Region папки скрывает её метки, поле окна
    свойств показывает и меняет расстояние, KML туда и обратно."""
    from planetx.core import kml, region
    from planetx.core.features import Shape
    from planetx.core.navigation import Pose
    from planetx.ui.placeprops import PlaceProperties
    window = state["window"]
    window.set_body("earth")
    store = window.myplaces
    view = window.view
    folder = store.add_folder("Region")
    key = store.add(Shape("point", [(58.0105, 56.2294)], name="Близко"),
                    folder=folder)
    store.update(key, {"region": region.text(
        region.for_distance([(58.0105, 56.2294)], 50.0))})
    out = {}

    def hidden_at(height):
        view.navigator.stop()
        view.navigator.set_pose(Pose(58.0105, 56.2294, height, 0.0, 0.0))
        view.grabFramebuffer()
        window._region_eye = None
        window._update_regions()
        return key in window._region_hidden
    out["at_40km"] = hidden_at(40000.0)
    out["at_100km"] = hidden_at(100000.0)
    place = store.find(key)
    dialog = PlaceProperties(place, window)
    out["field_km"] = round(dialog.far.value(), 1)
    dialog.show()
    dialog.grab().save(os.path.join(TEMP, "planetx_place_far.png"))
    dialog.far.setValue(200.0)
    store.update(key, dialog.values())
    dialog.close()
    out["after_edit_km"] = round(region.distance_km(store.find(key).region),
                                 1)
    out["edited_at_100km"] = hidden_at(100000.0)
    store.update(key, {"region": ""})
    store.update(folder, {"region": region.text(
        region.for_distance([(58.0105, 56.2294)], 30.0))})
    out["folder_at_100km"] = hidden_at(100000.0)
    out["folder_at_20km"] = hidden_at(20000.0)
    text = kml.write_kml(store.export_tree(folder))
    back = kml.read_kml(text.encode("utf-8"))
    out["kml_folder_km"] = round(region.distance_km(back.region), 1)
    store.remove_many([folder]) if hasattr(store, "remove_many") \
        else store.remove(folder)
    out["after_remove"] = len(window._region_hidden)
    result["region_hide"] = out


@check(500)
def toolbar_buttons():
    """Панель значков: «Обновить» видна только без автообновления,
    окно «Подземный режим» открывают свойства вида и строка «Земля над
    гридами», значка подземного режима нет."""
    from qgis.PyQt.QtWidgets import QPushButton, QToolButton
    window = state["window"]
    bar = window.toolbar
    out = {"subsurface_icon": hasattr(bar, "subsurface")}
    auto = window.auto_refresh
    window._set_auto(True)
    out["refresh_with_auto"] = bar.refresh.isVisibleTo(bar)
    window._set_auto(False)
    out["refresh_without_auto"] = bar.refresh.isVisibleTo(bar)
    window._set_auto(auto)
    out["record_tip"] = bar.record.toolTip()[:15]
    window._show_properties()
    buttons = [b for b in window.properties.findChildren(QPushButton)
               if b.text() == tr_text("Подземный режим…")]
    out["properties_button"] = len(buttons)
    manager = window.subsurface
    if buttons:
        buttons[0].click()
        out["dialog_from_properties"] = manager.dialog is not None \
            and manager.dialog.isVisible()
        manager.dialog.close()
    window.properties.close()
    row = window.panel.ground_row
    under = [b for b in row.findChildren(QToolButton) if b.text() == "…"]
    out["panel_button"] = len(under)
    if under:
        under[0].click()
        out["dialog_from_panel"] = manager.dialog is not None \
            and manager.dialog.isVisible()
        manager.dialog.close()
    result["toolbar_buttons"] = out


def tr_text(text):
    from planetx.i18n import tr
    return tr(text)


@check(500)
def grids_open():
    """Гриды по отметкам: копии гридов автора в %TEMP%\\planetx_grids
    со стилями и системой координат его проекта, пункт «Поверхность
    по отметкам» у каждого."""
    import glob
    from qgis.core import (QgsCoordinateReferenceSystem, QgsProject,
                           QgsRasterLayer)
    window = state["window"]
    window.set_body("earth")
    folder = os.path.join(TEMP, "planetx_grids")
    with open(os.path.join(folder, "crs.wkt"), encoding="utf-8") as fh:
        crs = QgsCoordinateReferenceSystem.fromWkt(fh.read())
    ids = []
    for path in sorted(glob.glob(os.path.join(folder, "*.asc"))):
        name = os.path.splitext(os.path.basename(path))[0]
        layer = QgsRasterLayer(path, name, "gdal")
        layer.setCrs(crs)
        qml = os.path.splitext(path)[0] + ".qml"
        if os.path.exists(qml):
            layer.loadNamedStyle(qml)
        QgsProject.instance().addMapLayer(layer)
        ids.append(layer.id())
    for layer_id in ids:
        window.set_layer_shown(layer_id, True)
        window.set_grid(layer_id, True)
    state["grids_ids"] = ids
    state["grids_started"] = time.monotonic()
    result["grids"] = {"layers": len(ids)}


@check(500)
def grids_wait():
    from planetx.core.navigation import Pose
    window = state["window"]
    manager = window.subsurface
    spent = time.monotonic() - state["grids_started"]
    if (manager.model is None or manager.job is not None
            or not window.view.subsurface.active) and spent < 60.0:
        return 500
    out = result["grids"]
    model = manager.model
    out["seconds"] = round(spent, 1)
    out["horizons"] = len(model.horizons) if model else 0
    out["panel_row"] = not window.panel.ground_row.isHidden()
    view = window.view
    view.navigator.stop()
    view.navigator.set_pose(Pose(59.545, 56.80, 9000.0, 25.0, 62.0))
    state["grids_step"] = 0
    state["grids_shot_at"] = time.monotonic()
    return None


@check(500)
def grids_shots():
    window = state["window"]
    view = window.view
    if time.monotonic() - state["grids_shot_at"] < 12.0:
        return 500
    out = result["grids"]
    for alpha in (1.0, 0.35, 0.0):
        window.panel.ground_slider.setValue(int(alpha * 100))
        view.repaint()
        image = view.grabFramebuffer()
        image.save(os.path.join(
            TEMP, "planetx_grids_%d.png" % int(alpha * 100)))
    out["surface_alpha"] = view.surface_alpha
    out["gl"] = dict(view.gl_errors)
    mesh = view.subsurface.meshes.get("horizons") \
        if hasattr(view.subsurface, "meshes") else None
    out["vertices"] = len(mesh.vertices) if mesh is not None else None
    # Масштаб рельефа 5 - пласты толщиной 5-10 м видны плитами.
    window.set_relief_scale(5.0)
    state["grids_shot_at"] = time.monotonic()
    return None


@check(500)
def grids_contours():
    """Изолинии первого грида - слоем GeoPackage в проект."""
    from qgis.core import QgsProject
    window = state["window"]
    layer = QgsProject.instance().mapLayer(state["grids_ids"][0])
    path = os.path.join(TEMP, "planetx_grid_contours.gpkg")
    window.contour_export.grid_contours(layer, path=path)
    result["grids"]["contours"] = _contour_report(path, window)
    _render_layers(_contour_layers(path),
                   os.path.join(TEMP, "planetx_grid_contours.png"))
    result["grids"]["contours"]["grid_crs"] = layer.crs().authid() \
        or layer.crs().description()


def _black_pixels(image):
    """Пиксели кадра без цвета, все каналы ниже 8."""
    from planetx.net.loader import image_to_rgba
    rgba = image_to_rgba(image)
    return int((rgba[..., :3].max(axis=2) < 8).sum())


@check(500)
def grids_scaled():
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    if time.monotonic() - state["grids_shot_at"] < 15.0:
        return 500
    out = result["grids"]
    out["scale"] = window.subsurface.scale
    for name, pose in (("s5", Pose(59.545, 56.80, 9000.0, 25.0, 62.0)),
                       ("edge", Pose(59.535, 56.80, 3500.0, 15.0, 70.0))):
        view.navigator.set_pose(pose)
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            QgsApplication.processEvents()
            time.sleep(0.05)
        for alpha in (0.35, 0.0):
            window.panel.ground_slider.setValue(int(alpha * 100))
            view.repaint()
            image = view.grabFramebuffer()
            image.save(os.path.join(
                TEMP, "planetx_grids_%s_%d.png" % (name, int(alpha * 100))))
            # Чёрные пиксели - пустой кадр. Над дальней стенкой блока
            # их не должно быть, сторож прохода прозрачной земли.
            out.setdefault("black", {})["%s_%d" % (name, alpha * 100)] = \
                _black_pixels(image)
    window.set_relief_scale(1.0)
    out["gl_scaled"] = dict(view.gl_errors)
    return None


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


@check(500)
def sheets_menu():
    """Пункт «Номенклатура листа» меню на глобусе: окно с номерами
    листов у Перми, щелчок по строке копирует номер, вторая точка
    (Нарвик) заменяет первую в том же окне."""
    from qgis.PyQt.QtWidgets import QApplication, QMenu
    from planetx.core.navigation import Pose
    from planetx.ui import globemenu
    window = state["window"]
    window.set_body("earth")
    view = window.view
    view.navigator.stop()
    view.navigator.set_pose(Pose(58.01, 56.23, 3000.0, 0.0, 0.0))
    view.grabFramebuffer()
    ratio = view.devicePixelRatioF()
    px, py = view.width() * ratio / 2.0, view.height() * ratio / 2.0
    before = set(window.findChildren(QMenu))
    globemenu.show(window, px, py)
    menus = [m for m in window.findChildren(QMenu) if m not in before]
    actions = {a.text(): a for m in menus for a in m.actions() if a.text()}
    out = result.setdefault("sheets_menu", {})
    out["item"] = "Номенклатура листа" in actions
    out["submenu"] = [t for t in actions if "\t" in t]
    [a for t, a in actions.items() if t.startswith("O-40-А\t")][0].trigger()
    out["menu_copied"] = QApplication.clipboard().text()
    actions["Все номера в окне…"].trigger()
    for menu in menus:
        menu.close()
    dialog = window.sheets_dialog
    table = dialog.table

    def rows():
        return [[table.item(r, c).text() for c in range(3)]
                for r in range(table.rowCount())]
    out["visible"] = dialog.isVisible()
    out["perm"] = rows()
    table.cellClicked.emit(3, 0)
    out["copied"] = QApplication.clipboard().text()
    out["status"] = dialog.status.text()
    again = window.sheets_here(68.44, 17.43)
    out["same_dialog"] = again is dialog
    out["narvik"] = rows()
    dialog.close()


@check(500)
def weather_failover():
    """Первое зеркало GFS - закрытый порт этой машины: запрос уходит на
    следующее зеркало, закрытое выводится на паузу. Ставится до
    weather_open, снимает weather_mirror_check."""
    from planetx.core.mirrors import Mirrors
    from planetx.core import weather
    from planetx.ui import weather as ui_weather
    state["weather_mirrors"] = ui_weather.MIRRORS
    state["weather_dead"] = "https://127.0.0.1:9/gfs"
    ui_weather.MIRRORS = Mirrors((state["weather_dead"],) + weather.BUCKETS)
    window = state["window"]
    window.weather.newest = None
    window.weather.indexes.clear()
    window.weather.sources.clear()
    window.weather.grids.clear()


@check(500)
def weather_open():
    """Поле температуры GFS на нынешний момент над Европой."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.set_theme("")
    view = window.view
    view.navigator.stop()
    view.navigator.set_pose(Pose(55.0, 40.0, 6000000.0, 0.0, 0.0))
    window.set_theme("weather_temperature")
    state["weather_started"] = time.monotonic()
    result["weather"] = {}


def _weather_wait(name, limit=60.0):
    window = state["window"]
    manager = window.weather
    layer = window.view.gibs["theme"]
    spent = time.monotonic() - state["weather_started"]
    if (not manager.ready() or not layer.textures or layer.missing) \
            and spent < limit and not manager.error:
        return 500
    run, hour, key = manager.shown or (None, None, None)
    result["weather"][name] = {
        "seconds": round(spent, 1), "field": key, "hour": hour,
        "run": time.strftime("%Y-%m-%d %H", time.gmtime(run))
        if run else None,
        "error": manager.error, "textures": len(layer.textures),
        "legend": window.theme_legend.isVisible(),
        "legend_title": str(getattr(window.theme_legend, "title", "")),
        "bar": [window.timebar.shown(), window.timebar.track.point],
        "credit": "NOAA GFS" in window.attribution.text()}
    window.view.grabFramebuffer().save(
        os.path.join(TEMP, "planetx_weather_%s.png" % name))
    return None


@check(500)
def weather_wait():
    return _weather_wait("temperature")


@check(500)
def weather_mirror_check():
    from planetx.ui import weather as ui_weather
    import time as _time
    pool = ui_weather.MIRRORS
    dead = next(m for m in pool.mirrors if m.url == state["weather_dead"])
    result["weather"]["mirrors"] = {
        "sources": sorted(set(window_sources())),
        "dead_down": dead.down_until > _time.monotonic(),
        "state": pool.describe(_time.monotonic())}
    ui_weather.MIRRORS = state["weather_mirrors"]


def window_sources():
    return [s.split("//")[-1].split("/")[0]
            for s in state["window"].weather.sources.values()]


@check(500)
def weather_values():
    """Числа поля температуры на глобусе: есть, градусы, при перелёте
    к Перми с 600 км пересчитываются, без поля сняты."""
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    marks = list(view.value_marks)
    out = {"far": len(marks), "texts": [m.name for m in marks[:6]]}
    view.navigator.set_pose(Pose(58.0, 56.2, 600000.0, 0.0, 0.0))
    window._update_values()
    near = view.value_marks
    out["near"] = len(near)
    out["near_texts"] = [m.name for m in near[:6]]
    out["degrees"] = all(m.name.endswith("°") for m in near)
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_weather_values.png"))
    result["weather"]["values"] = out


@check(500)
def weather_step():
    """Шаг шкалы вперёд - следующий час прогноза."""
    window = state["window"]
    before = window.weather.shown
    window.timebar.step(1)
    window._apply_theme()
    result["weather"]["step_from"] = before[1] if before else None
    state["weather_started"] = time.monotonic()


@check(500)
def weather_step_wait():
    return _weather_wait("step")


@check(500)
def weather_rain():
    window = state["window"]
    window.set_theme("weather_precipitation")
    state["weather_started"] = time.monotonic()


@check(500)
def weather_rain_wait():
    return _weather_wait("precipitation")


@check(500)
def weather_off():
    window = state["window"]
    window.set_theme("")
    result["weather"]["off"] = {
        "loader": "theme" in window.gibs_loaders,
        "legend": window.theme_legend.isVisible(),
        "active": window.weather.active(),
        "values": len(window.view.value_marks)}
    result["weather"]["gl"] = dict(window.view.gl_errors)
    return None


@check(500)
def reply_owner():
    """Кому принадлежит ответ сети: Python или C++. Если Python, то
    deleteLater и сборка мусора удаляют ответ дважды."""
    try:
        from PyQt6 import sip
    except ImportError:
        import sip
    from qgis.core import QgsNetworkAccessManager
    from qgis.PyQt.QtCore import QUrl
    from qgis.PyQt.QtNetwork import QNetworkRequest
    reply = QgsNetworkAccessManager.instance().get(
        QNetworkRequest(QUrl("http://127.0.0.1:9/")))
    result["reply_owner"] = {"py_owned": sip.ispyowned(reply),
                             "parent": str(reply.parent())}
    reply.abort()
    reply.deleteLater()


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
    dialog.depth_box.setCurrentIndex(3)
    out["depth_core"] = dialog.chart.section.depth
    dialog.grab().save(os.path.join(TEMP, "planetx_section_core.png"))
    # Стенка на глобусе: вид с юга с наклоном, разрез до 700 км.
    from planetx.core.navigation import Pose
    dialog.depth_box.setCurrentIndex(2)
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
    # Шаг стоит в середине списка, следующим шагам нужно живое окно.
    # Без этого полный прогон 10 октября 2026 года дал 97 ошибок
    # про удалённое окно.
    plugin = state["plugin"]
    plugin.run()
    state["window"] = plugin.window
    plugin.window.showNormal()


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
    # На своей глубине - только очаги в вынутом секторе.
    out["quakes_deep"] = [int(view.quakes.deep().sum()),
                          len(view.quakes.events)]
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
    result["vegas"] = {"icon": not hasattr(window.toolbar, "subsurface"),
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


@check(1000)
def stop_ground():
    """Земля над подземной моделью у вида метки (@ground): прозрачность,
    вырез и камера под землёй переживают файл меток и возвращаются
    видом метки. Идёт после vegas_*, модель тоннелей уже собрана."""
    from planetx.core import lookat
    from planetx.core.features import Shape
    window = state["window"]
    sub = window.subsurface
    out = result["stop_ground"] = {"model": sub.model is not None}
    if sub.model is None:
        return
    before = {k: sub.settings[k] for k in ("opacity", "cut", "under")}
    state["ground_before"] = before
    sub.set_options(dict(sub.settings, opacity=0.3, cut=True, under=False))
    snap = window.view_state()
    out["snapshot"] = snap.get(lookat.GROUND)
    store = window.myplaces
    key = store.add(Shape("point", [(36.13, -115.16)], name="Земля"),
                    view=(36.13, -115.16, 3000.0, 0.0, 45.0))
    store.update(key, {"layers": lookat.layers_text(snap)})
    layers = store.find(key).layers
    out["stored"] = layers.get(lookat.GROUND)
    # Другие настройки, потом вид метки возвращает свои.
    sub.set_options(dict(sub.settings, opacity=0.9, cut=False, under=True))
    out["changed"] = [sub.settings["opacity"], sub.settings["cut"],
                      sub.settings["under"]]
    window._apply_view_layers(layers)
    out["back"] = [sub.settings["opacity"], sub.settings["cut"],
                   sub.settings["under"]]
    out["alpha"] = round(window.view.surface_alpha, 3)
    out["floor_off"] = window.view.floor is None
    store.remove(key)
    sub.set_options(dict(sub.settings, **before))
    out["restored"] = [sub.settings[k] for k in ("opacity", "cut", "under")]
    out["gl"] = dict(window.view.gl_errors)


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
def model_section_menu():
    """Меню правой кнопки окна «Разрез модели»: свой цвет пласта под
    курсором и «Цвета разреза по умолчанию». Меню и окно выбора цвета
    подменяются - шаг нажимает пункт сам."""
    from qgis.PyQt.QtCore import QPoint
    from qgis.PyQt.QtGui import QColor, QContextMenuEvent
    from qgis.PyQt.QtWidgets import QMenu
    from planetx.qt_compat import enum
    from planetx.ui import subsection
    window = state["window"]
    model = window.subsurface.model
    south, north, west, east = model.box()
    lat = model.holes[0][1]
    window._open_model_section("Проба", [(lat, west), (lat, east)])
    dialog = window.model_section_dialog
    chart = dialog.chart
    chart.reset_colors()
    out = result.setdefault("subsurface", {})["section_menu"] = {}
    # Точка графика над пластом.
    spot = None
    for y in range(10, chart.height(), 6):
        k, _ = chart._at(QPoint(chart.width() // 2, y))
        if k is not None and chart.owner(k) != subsection.core.HOST:
            spot = QPoint(chart.width() // 2, y)
            break
    out["spot"] = spot is not None
    seen = []
    pick = {"index": 0}

    class Menu(QMenu):
        def exec(self, *args):
            actions = [a for a in self.actions() if not a.isSeparator()]
            seen.append([a.text() for a in actions])
            actions[pick["index"]].trigger()
    menu_class, get_color = subsection.QMenu, subsection.QColorDialog.getColor
    subsection.QMenu = Menu
    subsection.QColorDialog.getColor = staticmethod(
        lambda *args: QColor(10, 200, 30))
    try:
        if spot is not None:
            reason = enum(QContextMenuEvent, "Reason", "Mouse")
            chart.contextMenuEvent(QContextMenuEvent(
                reason, spot, chart.mapToGlobal(spot)))
            out["own"] = {k: dict(v) for k, v in chart.own.items()}
            out["saved"] = bool(subsection.read_section_colors())
            pick["index"] = -1
            chart.contextMenuEvent(QContextMenuEvent(
                reason, spot, chart.mapToGlobal(spot)))
            out["own_after_reset"] = dict(chart.own)
            out["saved_after_reset"] = bool(subsection.read_section_colors())
    finally:
        subsection.QMenu = menu_class
        subsection.QColorDialog.getColor = get_color
    out["menus"] = seen
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
    rows = panel.basemap_names()
    osm = rows.index("OpenStreetMap")
    panel._basemap_activated(osm)
    result["tile_source"] = {"rows": rows, "after_click": window.source.name}
    panel._basemap_activated(0)
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
    # add_tile_source живёт в части окна ui/globe/state.py.
    import planetx.ui.globe.state as wmod
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
    out["rows_after"] = window.panel.basemap_names()
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
    window.panel._basemap_activated(0)
    settings = QgsSettings()
    prefix = "connections/xyz/items/%s/" % out["saved"]
    for key in settings.allKeys():
        if key.startswith(prefix):
            settings.remove(key)


@check(500)
def basemap_checkbox():
    """Строки «Основа» и «Рельеф» наверху списка «Слоёв», выбор - меню
    строки, решение автора от 12 октября 2026 года. Пункт «Добавить
    источник тайлов…» открывает окно и подложку не меняет. До
    12 октября здесь проверялся флажок подложки, который пересоздавал
    свою строку."""
    from planetx.ui.panel import ADD_SOURCE, MORE_ROLE, RELIEF
    window = state["window"]
    panel = window.panel
    names = panel.basemap_names()
    osm = names.index("OpenStreetMap")
    asked = []
    panel.add_source_requested.disconnect()
    panel.add_source_requested.connect(lambda: asked.append(1))
    caught = []
    hook = sys.excepthook
    sys.excepthook = lambda kind, value, tb: caught.append(repr(value))
    try:
        panel._basemap_activated(osm)
        source = window.source.name
        panel._basemap_activated(ADD_SOURCE)
        QgsApplication.processEvents()
    finally:
        sys.excepthook = hook
        panel.add_source_requested.disconnect()
        panel.add_source_requested.connect(window.add_tile_source)
    relief = panel.geo_items[RELIEF]
    result["basemap_checkbox"] = {
        "rows": names, "source": source, "add_asked": len(asked),
        "after_add": window.source.name,
        "base_text": panel.base_item.text(0),
        "top": [panel.geo.topLevelItem(i).text(0) for i in range(2)],
        "menu_rows": [panel.base_item.data(0, MORE_ROLE),
                      relief.data(0, MORE_ROLE)],
        "relief_text": relief.text(0),
        "relief_models": [k for k, _, _ in panel._relief_models],
        "errors": caught}
    panel._basemap_activated(0)


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
        "NASA GIBS" in window.attribution.text()
    window.set_extra("clouds", False)
    view.update()


@check(1000)
def clouds_off():
    window = state["window"]
    view = window.view
    result["clouds"]["off_textures"] = len(view.gibs["clouds"].textures)
    result["clouds"]["off_loader"] = "clouds" not in window.gibs_loaders
    result["clouds"]["off_attribution"] = \
        "NASA GIBS" in window.attribution.text()
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
        "attribution": "NASA GIBS" in window.attribution.text()}
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
    import qgis.PyQt.QtWidgets as wmod  # QInputDialog окна и его частей
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


def _watch_loader(loader, name):
    """Счёт пришедших и неудачных тайлов загрузчика в state[name]."""
    seen = state[name] = {"loaded": 0, "failed": 0, "errors": []}
    loader.loaded.connect(
        lambda *a: seen.__setitem__("loaded", seen["loaded"] + 1))

    def failed(key, text):
        seen["failed"] += 1
        if len(seen["errors"]) < 3:
            seen["errors"].append("{} {}".format(key, text))
    loader.failed.connect(failed)
    return seen


@check(500)
def ready_menu():
    """Готовые источники меню «Основа»: состав подменю, отказ
    от предупреждения не добавляет источник, согласие добавляет
    и запоминается, источник без предупреждения ставится сразу."""
    from qgis.core import QgsSettings
    from planetx.core.navigation import Pose
    from planetx.ui import window as wmod
    window = state["window"]
    window.set_body("earth")
    settings = QgsSettings()
    state["ready_before"] = (settings.value(wmod.READY_KEY, []),
                             settings.value(wmod.ACCEPTED_KEY, []),
                             window.source.name)
    settings.remove(wmod.READY_KEY)
    settings.remove(wmod.ACCEPTED_KEY)
    menu = window.panel.basemap_menu()
    ready = [a.menu() for a in menu.actions() if a.menu() is not None]
    groups = [a for a in ready[0].actions() if a.menu() is not None] \
        if ready else []
    items = [b for a in groups for b in a.menu().actions()]
    out = result["ready"] = {
        "submenu": {a.text(): [b.text() for b in a.menu().actions()]
                    for a in groups},
        "items": len(items),
        "warned_tips": sum(1 for a in items if a.toolTip()
                           and a.toolTip() != a.text())}
    menu.deleteLater()
    asked = []
    window._accept_terms = lambda name, terms: asked.append(name) or False
    out["declined"] = window.add_ready_source("yandex_satellite")
    out["after_decline"] = [s.name for s in window.sources if s.ready]
    window._accept_terms = lambda name, terms: asked.append(name) or True
    out["accepted"] = window.add_ready_source("yandex_satellite")
    out["asked"] = list(asked)
    out["accepted_saved"] = settings.value(wmod.ACCEPTED_KEY, [])
    # Второй раз предупреждение не спрашивается.
    window._accept_terms = lambda name, terms: asked.append("again") or True
    window.add_ready_source("yandex_satellite")
    out["asked_again"] = "again" in asked
    del window._accept_terms
    out["source"] = window.source.name
    nav = window.view.navigator
    nav.stop()
    nav.show(Pose(58.0105, 56.2294, 6000.0, 0.0, 0.0))
    state["ready_seen"] = _watch_loader(window.loader, "ready_seen")
    state["ls_started"] = time.monotonic()


@check(1000)
def ready_wait():
    """Снимок Яндекса пересчитан и пришёл, кадр в файл. Потом
    OpenTopoMap - без предупреждения."""
    window = state["window"]
    seen = state["ready_seen"]
    spent = time.monotonic() - state["ls_started"]
    if spent < 25.0 and (window.view.load_missing or seen["loaded"] < 20):
        return 1000
    out = result["ready"]
    out["yandex"] = dict(seen, seconds=round(spent, 1),
                         parts=len(window.loader.started))
    window.view.grabFramebuffer().save(os.path.join(
        TEMP, "planetx_ready_yandex.png"))
    out["opentopo"] = window.add_ready_source("opentopomap")
    out["opentopo_source"] = window.source.name
    out["attribution"] = window.attribution.text()
    # Новая подложка 18 октября 2026 года - Blue Marble NASA из космоса.
    from planetx.core.navigation import Pose
    out["blue_marble"] = window.add_ready_source("nasa_blue_marble")
    window.view.navigator.show(Pose(50.0, 60.0, 9000000.0, 0.0, 0.0))
    window.view.update()
    state["ready_seen"] = _watch_loader(window.loader, "ready_seen")
    state["ls_started"] = time.monotonic()
    return None


@check(1000)
def ready_new_wait():
    """Blue Marble пришла тайлами, кадр в файл."""
    window = state["window"]
    seen = state["ready_seen"]
    spent = time.monotonic() - state["ls_started"]
    if spent < 25.0 and (window.view.load_missing or seen["loaded"] < 10):
        return 1000
    out = result["ready"]
    out["blue_marble_seen"] = dict(seen, seconds=round(spent, 1),
                                   source=window.source.name,
                                   credits=window.attribution.text())
    window.view.grabFramebuffer().save(os.path.join(
        TEMP, "planetx_ready_bluemarble.png"))
    return None


@check(500)
def ready_cleanup():
    from qgis.core import QgsSettings
    from planetx.ui import window as wmod
    window = state["window"]
    ready, accepted, name = state["ready_before"]
    settings = QgsSettings()
    for key, value in ((wmod.READY_KEY, ready),
                       (wmod.ACCEPTED_KEY, accepted)):
        if value:
            settings.setValue(key, value)
        else:
            settings.remove(key)
    window.sources = wmod.all_sources()
    names = [s.name for s in window.sources]
    window._panel_basemap(names.index(name) if name in names else 0)
    result["ready"]["restored"] = window.source.name


@check(500)
def cadastre_on():
    """Кадастр Росреестра у Перми: тайлы НСПД с Referer и сертификатом
    Минцифры из модуля, по одному с паузой."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    nav = window.view.navigator
    nav.stop()
    nav.show(Pose(58.0105, 56.2294, 2500.0, 0.0, 0.0))
    window.set_extra("cadastre", True)
    loader = window.gibs_loaders.get("cadastre")
    result["cadastre"] = {"loader": loader is not None,
                          "gap": loader.source.gap if loader else None}
    if loader is not None:
        _watch_loader(loader, "cadastre_seen")
    state["ls_started"] = time.monotonic()


@check(1000)
def cadastre_check():
    window = state["window"]
    seen = state.get("cadastre_seen", {"loaded": 0})
    layer = window.view.gibs["cadastre"]
    spent = time.monotonic() - state["ls_started"]
    if spent < 60.0 and (seen["loaded"] < 6 or layer.missing):
        return 1000
    loader = window.gibs_loaders.get("cadastre")
    out = result["cadastre"]
    out.update(dict(seen, seconds=round(spent, 1),
                    textures=len(layer.textures),
                    levels=sorted({k[0] for k in layer.textures}),
                    asked=len(loader.started) if loader else 0,
                    attribution="NSPD" in window.attribution.text(),
                    gl_errors=dict(window.view.gl_errors)))
    window.view.grabFramebuffer().save(os.path.join(
        TEMP, "planetx_cadastre.png"))
    window.set_extra("cadastre", False)
    out["off"] = "cadastre" not in window.gibs_loaders
    return None


@check(500)
def geoid_on():
    """Геоид над Индийским океаном: высоты - тайлы геоида локальной копии
    planetx-terrain, масштаб geoid.SCALE, воды нет."""
    from qgis.PyQt.QtCore import QUrl
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    folder = os.environ.get("PLANETX_TERRAIN_DIR") or "C:/Dev/planetx-terrain"
    window.geoid_url = QUrl.fromLocalFile(os.path.join(
        folder, "geoid")).toString() + "/{z}/{x}/{y}.png"
    result["geoid"] = {"before": {"scale": window.view.store.scale,
                                  "sea_floor": window.view.sea_floor}}
    window.view.navigator.stop()
    window.view.navigator.show(Pose(-5.0, 95.0, 18000000.0, 0.0, 20.0))
    window.set_extra("geoid", True)
    state["ls_started"] = time.monotonic()


@check(1000)
def geoid_check():
    window = state["window"]
    store = window.view.store
    spent = time.monotonic() - state["ls_started"]
    low = store.height_at(4.7, 78.8)
    if spent < 30.0 and (spent < 8.0 or not low):
        return 1000
    out = result["geoid"]
    out.update(seconds=round(spent, 1), scale=store.scale,
               sea_floor=window.view.sea_floor,
               max_level=store.max_level,
               low_m=round(low / store.scale, 2) if store.scale else None,
               high_m=round(store.height_at(-4.5, 147.3) / store.scale, 2)
               if store.scale else None,
               attribution="EGM2008" in window.attribution.text(),
               errors=dict(window.terrain_errors),
               gl_errors=dict(window.view.gl_errors))
    view = window.view

    def middle(image):
        # Средний цвет квадрата в середине кадра - впадина у Индии.
        w, h = image.width(), image.height()
        side = min(w, h) // 10
        sums = [0, 0, 0]
        for y in range(h // 2 - side, h // 2 + side, 4):
            for x in range(w // 2 - side, w // 2 + side, 4):
                c = image.pixelColor(x, y)
                sums[0] += c.red()
                sums[1] += c.green()
                sums[2] += c.blue()
        n = (2 * side // 4) ** 2
        return [round(s / n) for s in sums]

    # Сторож дымки: тот же кадр с воздухом над поверхностью, как было
    # до правки, - впадина белеет.
    out["surface_air"] = view.surface_air
    image = view.grabFramebuffer()
    image.save(os.path.join(TEMP, "planetx_geoid.png"))
    out["middle_rgb"] = middle(image)
    view.surface_air = True
    hazy = view.grabFramebuffer()
    hazy.save(os.path.join(TEMP, "planetx_geoid_hazy.png"))
    out["middle_rgb_hazy"] = middle(hazy)
    view.surface_air = False
    # Щелчок в середине вида - группа «Место» окна «Объекты».
    ratio = view.devicePixelRatioF()
    window.identify_here(view.width() * ratio / 2.0,
                         view.height() * ratio / 2.0)
    tree = window.identified.tree
    rows = []
    for n in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(n)
        for m in range(top.childCount()):
            item = top.child(m)
            rows += [(top.text(0), item.child(k).text(0),
                      item.child(k).text(1))
                     for k in range(item.childCount())]
    out["identify"] = rows[:8]
    out["point"] = window.identified.point.text()
    window.identified.close()
    window.set_extra("geoid", False)
    out["after"] = {"scale": window.view.store.scale,
                    "sea_floor": window.view.sea_floor,
                    "surface_air": window.view.surface_air,
                    "max_level": store.max_level}
    return None


@check(500)
def geoid_cutaway():
    """Геоид и разрез Земли вместе: край граней - на «измятой»
    поверхности (замечание пользователя от 14 октября 2026 года),
    ползунок масштаба двигает поверхность и грани вместе."""
    from qgis.PyQt.QtCore import QUrl
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    window.set_body("earth")
    folder = os.environ.get("PLANETX_TERRAIN_DIR") or "C:/Dev/planetx-terrain"
    window.geoid_url = QUrl.fromLocalFile(os.path.join(
        folder, "geoid")).toString() + "/{z}/{x}/{y}.png"
    meshes = state["cut_meshes"] = {}
    original = view.cutaway.set_mesh

    def keep(name, mesh):
        meshes[name] = mesh
        original(name, mesh)
    view.cutaway.set_mesh = keep
    window.set_geoid_scale(10000.0)
    view.navigator.stop()
    view.navigator.show(Pose(-5.0, 95.0, 18000000.0, 30.0, 30.0))
    window.set_extra("geoid", True)
    window.set_extra("cutaway", True)
    state["ls_started"] = time.monotonic()


def _cut_mismatch(view):
    """Наибольшее расхождение края граней разреза с поверхностью, км:
    по каждому направлению дуги - самая дальняя вершина грани против
    эллипсоида плюс высота хранилища высот."""
    import numpy as np
    from planetx.core import cutaway
    mesh = state["cut_meshes"].get("faces")
    if mesh is None:
        return None
    p = mesh.vertices["position"].astype(np.float64) + mesh.center
    r = np.linalg.norm(p, axis=1)
    # Вершины у центра Земли (низ внутреннего ядра) направления не
    # имеют.
    p, r = p[r > 0.3 * 6378137.0], r[r > 0.3 * 6378137.0]
    d = p / r[:, None]
    key = np.round(d, 5)
    top = {}
    every = {}
    for k, rr, dd in zip(map(tuple, key), r, d):
        every.setdefault(k, []).append(rr)
        if k not in top or rr > top[k][0]:
            top[k] = (rr, dd)
    state["cut_every"] = every
    # Шум float32 вершин изредка делит точку дуги округлением на две
    # группы, в меньшей - только граница ядра. В настоящей точке дуги
    # вершин много, от ядра до коры.
    top = {k: v for k, v in top.items() if len(every[k]) > 2}
    rs = np.array([v[0] for v in top.values()])
    ds = np.array([v[1] for v in top.values()])
    base = cutaway.boundary(ds)
    lats, lons = cutaway._latlon(ds)
    a, b = 6378137.0, 6356752.314245
    geodetic = np.degrees(np.arctan2(np.tan(np.radians(lats)),
                                     (b / a) ** 2))
    # Выше 85.05° тайлов нет, там полярная шапка, у полюса долгота
    # не определена.
    near = np.abs(geodetic) < 85.0
    rs, base, geodetic, lons = rs[near], base[near], geodetic[near], \
        lons[near]
    surface = view.store.heights_at(geodetic, lons)
    miss = np.abs(rs - base - surface)
    worst = int(np.argmax(miss))
    keys = [k for k in top]
    near_keys = [k for k, ok in zip(keys, near) if ok]
    radii = sorted(state["cut_every"][near_keys[worst]])
    state.setdefault("cut_radii", []).append(
        [round((v - float(base[worst])) / 1000.0, 1) for v in radii])
    result["cut_radii"] = state["cut_radii"]
    state.setdefault("cut_worst", []).append(
        [round(float(geodetic[worst]), 2), round(float(lons[worst]), 2),
         round(float((rs - base)[worst]) / 1000.0, 1),
         round(float(surface[worst]) / 1000.0, 1),
         int(np.sum(miss > 20000.0)), len(miss)])
    result["cut_worst"] = state["cut_worst"]
    return round(float(np.max(miss)) / 1000.0, 1)


@check(1000)
def geoid_cutaway_check():
    window = state["window"]
    view = window.view
    spent = time.monotonic() - state["ls_started"]
    if spent < 10.0:
        return 1000
    view.repaint()
    out = result["geoid_cutaway"] = {
        "seconds": round(spent, 1), "lift": view.wedge_lift,
        "scale": view.store.scale, "tiles": len(view.store.tiles),
        "mismatch_km": _cut_mismatch(view)}
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_geoid_cut.png"))
    # Ручка угла захватывается щелчком по нарисованному кружку
    # (замечание автора от 15 октября 2026 года - плохо захватывались).
    # До правки точка захвата была на эллипсоиде, в пикселях - shift.
    import numpy as np
    from planetx.core.ellipsoid import geodetic_to_ecef
    corners = window.wedge_corners
    _, lat, lon = corners.points()[0]
    mark = geodetic_to_ecef(np.array([lat]), np.array([lon]),
                            np.array([view.label_height(lat, lon)]))
    flat = geodetic_to_ecef(np.array([lat]), np.array([lon]), np.zeros(1))
    (mx, my), _ = view.camera.project(mark)[0][0], True
    (fx, fy), _ = view.camera.project(flat)[0][0], True
    out["corner_grabbed"] = corners.grab(float(mx), float(my))
    corners.drop()
    out["corner_shift_px"] = round(float(np.hypot(mx - fx, my - fy)), 1)
    # Сторож: грани по эллипсоиду, как до правки, - ступень в сотни км.
    view.wedge_lift = False
    view.grabFramebuffer().save(os.path.join(
        TEMP, "planetx_geoid_cut_flat.png"))
    out["mismatch_without_lift_km"] = _cut_mismatch(view)
    view.wedge_lift = True
    # Ползунок на ×20 000: поверхность и грани вместе.
    window.set_geoid_scale(20000.0)
    view.grabFramebuffer()
    out["scale_20000"] = view.store.scale
    out["mismatch_20000_km"] = _cut_mismatch(view)
    window.set_geoid_scale(10000.0)
    window.set_extra("cutaway", False)
    window.set_extra("geoid", False)
    out["lift_after"] = view.wedge_lift
    out["gl_errors"] = dict(view.gl_errors)
    return None


@check(500)
def fullscreen_on():
    """Во весь экран: окно размером с экран, панели и панель значков
    скрыты, органы навигации на месте."""
    window = state["window"]
    QApplication = __import__("qgis.PyQt.QtWidgets",
                              fromlist=["QApplication"]).QApplication
    state["full_before"] = (window.size().width(), window.size().height(),
                            window.panel.isVisible())
    window.toggle_fullscreen()
    QApplication.processEvents()
    screen = window.screen().geometry() if hasattr(window, "screen") \
        else QApplication.desktop().screenGeometry(window)
    result["fullscreen"] = {
        "before": list(state["full_before"]),
        "screen": [screen.width(), screen.height()]}


@check(1500)
def fullscreen_check():
    window = state["window"]
    out = result["fullscreen"]
    out.update(full=window.isFullScreen(), flag=window.is_fullscreen(),
               size=[window.width(), window.height()],
               panel=window.panel.isVisible(),
               toolbar=window.toolbar.isVisible(),
               navpad=window.navpad.isVisible(),
               attribution=window.attribution.isVisible())
    window.view.grabFramebuffer().save(os.path.join(
        TEMP, "planetx_fullscreen.png"))
    window.toggle_fullscreen()
    return None


@check(1500)
def fullscreen_off():
    window = state["window"]
    out = result["fullscreen"]
    out["after"] = [window.size().width(), window.size().height(),
                    window.panel.isVisible()]
    out["after_full"] = window.isFullScreen()
    out["toolbar_after"] = window.toolbar.isVisible()
    out["escape_enabled"] = window._full_escape.isEnabled()
    # Выход из режима не показывает пустую панель свойств.
    out["side_hidden_after"] = window.side.isHidden()
    return None


@check(500)
def flows_open():
    """Демо «Поток грузов, схема»: три пути с потоком, штрихи бегут."""
    window = state["window"]
    window.set_body("earth")
    key = window.open_demo("flows")
    state["flows_key"] = key
    state["ls_started"] = time.monotonic()


@check(1000)
def flows_check():
    import numpy as np
    window = state["window"]
    view = window.view
    spent = time.monotonic() - state["ls_started"]
    if spent < 6.0:
        return 1000
    places = window.myplaces.places_in(state["flows_key"])
    flows = [p for p in places if getattr(p.shape, "flow", False)]
    groups = view.path_flow.groups
    first = groups[0][0][0, 0].copy() if groups else None
    time.sleep(0.3)
    window._tick_flow()
    moved = None
    if groups and view.path_flow.groups:
        second = view.path_flow.groups[0][0][0, 0]
        moved = round(float(np.linalg.norm(second - first)) / 1000.0, 1)
    view.repaint()
    image = view.grabFramebuffer()
    image.save(os.path.join(TEMP, "planetx_flows.png"))
    out = result["flows"] = {
        "places": len(places), "flow_paths": len(flows),
        "groups": len(view.path_flow.groups),
        "dashes": sum(len(g[0]) for g in view.path_flow.groups),
        "drawn": view.path_flow.drawn,
        "timer": window._flow_timer.isActive(),
        "first_dash_moved_km": moved,
        "gl_errors": dict(view.gl_errors)}
    # Все пути с потоком скрыты (в профиле могли остаться прежние
    # демо) - штрихов нет, таймер стоит.
    every = [p for p in window.myplaces.places
             if getattr(p.shape, "flow", False) and p.visible]
    window.myplaces.set_visible_many({p.key: False for p in every})
    out["groups_hidden"] = len(view.path_flow.groups)
    out["paths_hidden"] = len(window._flow_paths)
    out["timer_hidden"] = window._flow_timer.isActive()
    window.myplaces.set_visible_many({p.key: True for p in flows})
    return None


@check(500)
def tour_captions_on():
    """Подписи остановок тура на кадре: тур из двух остановок, на
    первой - подпись с названием и описанием без разметки."""
    from planetx.core.tour import Stop
    window = state["window"]
    window.set_body("earth")
    stops = [Stop("Пермь", 58.01, 56.23, 20000.0, 0.0, 45.0),
             Stop("Кунгур", 57.43, 56.94, 8000.0)]
    stops[0].description = "Столица Пермского края на <b>Каме</b>."
    state["caption_stops"] = stops
    window.tour.bar.captions.setChecked(True)
    window.tour.bar.pause.setValue(4.0)
    window.tour.start(stops)
    state["ls_started"] = time.monotonic()


@check(500)
def tour_captions_check():
    from qgis.PyQt.QtGui import QImage, QColor
    from planetx.core.timeline import Timeline
    window = state["window"]
    player = window.tour
    layer = player.stop_caption
    spent = time.monotonic() - state["ls_started"]
    if spent < 40.0 and not (layer.isVisible() and layer.alpha >= 1.0):
        return 500
    out = result["tour_captions"] = {
        "seconds": round(spent, 1), "visible": layer.isVisible(),
        "title": layer.title, "text": layer.text,
        "alpha": round(layer.alpha, 2),
        "bar_caption": player.bar.caption.isVisible()}
    window.grab().save(os.path.join(TEMP, "planetx_tour_caption.png"))
    # Кнопка снимает подписи, описание - снова строкой под кнопками.
    player.bar.captions.setChecked(False)
    out["off_visible"] = layer.isVisible()
    out["off_bar_caption"] = player.bar.caption.isVisible()
    player.bar.captions.setChecked(True)
    # Кадр записи на остановке получает ту же подпись.
    stops = state["caption_stops"]
    recorder = window.recorder
    line = Timeline(stops, 4.0)
    image = QImage(800, 600, QImage.Format.Format_RGB32)
    image.fill(QColor(0, 0, 0))
    recorder.line = line
    recorder.n = int((line.tour.arrivals[0] + 2.0) * line.fps)
    recorder.ratio = 1.0
    try:
        recorder._draw_caption(image)
    finally:
        recorder.line = None
    lit = sum(1 for y in range(300, 600, 4) for x in range(0, 800, 4)
              if image.pixelColor(x, y).red() > 100)
    out["record_lit"] = lit
    image.save(os.path.join(TEMP, "planetx_tour_caption_frame.png"))
    player.stop()
    out["after_stop"] = layer.isVisible()
    return None


@check(500)
def zlayer_on():
    """Слой с Z объёмом по отметкам: синтетический «3D-забор» разреза
    у Березников - вертикальные четырёхугольники двух пластов через
    20 м вдоль линии, как у Isoliner3D, и линия с Z."""
    import math as _m
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, \
        QgsVectorLayer
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    lat0, lon0 = 59.45, 56.88
    fence = QgsVectorLayer(
        "MultiPolygonZ?crs=EPSG:4326&field=bed:string&field=top:string"
        "&field=color:string", "Разрез (3D-забор) проба", "memory")
    beds = (("В", "#9a69e3", 0.0, -12.0), ("А'Б", "#6ddb3b", -12.0, -40.0))
    feats = []
    step_lat = 20.0 / 111000.0
    for name, color, top, bottom in beds:
        quads = []
        for i in range(40):
            a = lat0 + i * step_lat
            b = a + step_lat
            ta = 150.0 + top - 10.0 * _m.sin(i / 6.0)
            tb = 150.0 + top - 10.0 * _m.sin((i + 1) / 6.0)
            ba = 150.0 + bottom - 10.0 * _m.sin(i / 6.0)
            bb = 150.0 + bottom - 10.0 * _m.sin((i + 1) / 6.0)
            quads.append("(({lo} {a} {ta}, {lo} {b} {tb}, {lo} {b} {bb}, "
                         "{lo} {a} {ba}, {lo} {a} {ta}))".format(
                             lo=lon0, a=a, b=b, ta=ta, tb=tb, ba=ba, bb=bb))
        feature = QgsFeature(fence.fields())
        feature.setGeometry(QgsGeometry.fromWkt(
            "MultiPolygon Z (" + ",".join(quads) + ")"))
        feature.setAttributes([name, name + "_top", color])
        feats.append(feature)
    fence.dataProvider().addFeatures(feats)
    line = QgsVectorLayer("LineStringZ?crs=EPSG:4326&field=name:string",
                          "Ось выработки проба", "memory")
    feature = QgsFeature(line.fields())
    feature.setGeometry(QgsGeometry.fromWkt(
        "LineString Z ({lo} {a} 120, {lo2} {b} 100)".format(
            lo=lon0 - 0.004, a=lat0, lo2=lon0 + 0.004,
            b=lat0 + 0.006)))
    feature.setAttributes(["Штрек 1"])
    line.dataProvider().addFeatures([feature])
    QgsProject.instance().addMapLayers([fence, line])
    state["zlayers"] = [fence.id(), line.id()]
    window.view.navigator.stop()
    window.view.navigator.show(Pose(lat0 + 0.0036, lon0, 900.0,
                                    90.0, 60.0))
    for layer in (fence, line):
        window.set_layer_shown(layer.id(), True)
    window.set_zlayer(fence.id(), True)
    window.set_zlayer(line.id(), True)
    state["zlayer_shown"] = [i in window._shown for i in state["zlayers"]]
    window.subsurface.set_opacity(0.35)
    state["ls_started"] = time.monotonic()


@check(1000)
def zlayer_check():
    import numpy as np
    from qgis.core import QgsProject
    from planetx.ui.subsurface import subsurface_ids
    window = state["window"]
    view = window.view
    manager = window.subsurface
    spent = time.monotonic() - state["ls_started"]
    model = manager.model
    if spent < 30.0 and (model is None or manager.job is not None):
        return 1000
    # Маска прозрачной земли над моделью приходит тайлами после сборки.
    if spent < 8.0:
        return 1000
    shapes = model.zshapes if model is not None else []
    buf = view.subsurface.buffers.get("zlayers") \
        if hasattr(view.subsurface, "buffers") else None
    out = result["zlayer"] = {
        "shown": state.get("zlayer_shown"),
        "shown_now": [i in window._shown for i in state["zlayers"]],
        "seconds": round(spent, 1), "shapes": len(shapes),
        "kinds": sorted({s.kind for s in shapes}),
        "colors": sorted({s.color[:3] for s in shapes}),
        "pending_mesh": manager.view.subsurface.pending.get("zlayers")
        is not None, "vertices": getattr(buf, "vertices", 0),
        # Слои с Z не рисуются плоской картинкой наложения.
        "overlay_skips": len(set(state["zlayers"]) & subsurface_ids(
            state["zlayers"]))}
    view.repaint()
    out["vertices"] = getattr(view.subsurface.buffers.get("zlayers"),
                              "vertices", 0)
    # Щелчок по контуру первого пласта - окно «Объекты» даёт поля.
    pick = [p for p in manager.picks if p.kind == "zshape"]
    out["picks"] = len(pick)
    if pick:
        pixels, front = view.camera.project(pick[0].xyz)
        ok = np.where(front)[0]
        if len(ok):
            px, py = pixels[ok[len(ok) // 2]]
            found = manager.identify(float(px), float(py), 6.0)
            out["identify"] = [(t, v[:3]) for t, v, _ in found[:2]]
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_zlayer.png"))
    for layer_id in state["zlayers"]:
        window.set_zlayer(layer_id, False)
    model = manager.model
    out["after_off"] = len(model.zshapes) if model is not None else 0
    QgsProject.instance().removeMapLayers(state["zlayers"])
    out["gl_errors"] = dict(view.gl_errors)
    return None


@check(500)
def crust_export():
    """Кора CRUST1.0 в проект над Восточно-Европейской платформой:
    семь поверхностей группой, отметки у Перми."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.view.navigator.stop()
    window.view.navigator.show(Pose(55.0, 45.0, 2500000.0, 0.0, 0.0))
    folder = os.path.join(TEMP, "planetx_crust_export")
    os.makedirs(folder, exist_ok=True)
    state["crust_folder"] = folder
    state["crust_started"] = time.monotonic()
    result["crust_export"] = {"first": window.crust_to_project(folder)}


@check(1000)
def crust_export_check():
    from qgis.core import QgsProject
    window = state["window"]
    out = result.setdefault("crust_export", {})
    root = QgsProject.instance().layerTreeRoot()
    group = root.findGroup("PlanetX - кора CRUST1.0") \
        or root.findGroup("PlanetX - CRUST1.0 crust")
    if group is None and time.monotonic() - state["crust_started"] < 60.0:
        return 1000
    layers = [node.layer() for node in group.findLayers()] if group else []
    out["layers"] = [layer.name() for layer in layers]
    out["message"] = window.message[0] if window.message else None
    if layers:
        first = layers[0]
        extent = first.extent()
        out["size"] = [first.width(), first.height()]
        out["extent"] = [round(extent.xMinimum(), 1),
                         round(extent.yMinimum(), 1),
                         round(extent.xMaximum(), 1),
                         round(extent.yMaximum(), 1)]
        perm = {}
        from qgis.core import QgsPointXY
        for layer in layers:
            value, ok = layer.dataProvider().sample(
                QgsPointXY(56.5, 59.5), 1)
            perm[layer.name()] = round(value) if ok else None
        out["perm"] = perm
        QgsProject.instance().removeMapLayers([l.id() for l in layers])
    if group is not None:
        root.removeChildNode(group)
    out["gl"] = dict(window.view.gl_errors)
    return None


@check(15000, manual=True)
def credit_shot():
    """Кадр правого нижнего угла: короткая подпись источников и PlanetX
    при силе тяжести и разрезе Земли."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.view.navigator.show(Pose(40.0, 140.0, 9000000.0, 0.0, 0.0))
    window.set_extra("gravity", True)
    window.set_extra("quakes", True)
    QgsApplication.processEvents()
    window.view.grab().save(os.path.join(TEMP, "planetx_credit.png"))
    result["credit_shot"] = {
        "text": window.attribution.text(),
        "brand": [window.brand.x(), window.brand.y(),
                  window.view.width(), window.view.height()]}
    window.set_extra("gravity", False)
    window.set_extra("quakes", False)


@check(1000, manual=True)
def slab_grazing():
    """Плита Slab2 у Суматры на экваториальной грани разреза под
    косым взглядом - вид снимка автора от 16 октября 2026 года."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.set_extra("cutaway", True)
    window.set_wedge_box(95.0, 185.0, 0.0, 60.0)
    window.view.navigator.show(Pose(4.0, 100.0, 2500000.0, 0.0, 50.0))
    state["slab_started"] = time.monotonic()


@check(1000, manual=True)
def slab_grazing_check():
    from planetx.net.loader import image_to_rgba
    window = state["window"]
    view = window.view
    if time.monotonic() - state["slab_started"] < 25.0:
        return 1000
    out = result.setdefault("slab_grazing", {})
    out["slabs"] = len(view.wedge_slabs or [])
    out["codes"] = list(getattr(window, "_slab_codes", []) or [])
    for tilt in (40.0, 55.0, 70.0):
        from planetx.core.navigation import Pose
        view.navigator.show(Pose(4.0, 100.0, 2500000.0, 0.0, tilt))
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            QgsApplication.processEvents()
            time.sleep(0.05)
        view.repaint()
        image = view.grabFramebuffer()
        image.save(os.path.join(TEMP, "planetx_slab_%d.png" % tilt))
        # Пиксели цвета плиты на западной грани и переходы плита - грань
        # по строкам. Спор глубины давал гребёнку - переходов на прежнем
        # коде в 3-4 раза больше, 16 октября 2026 года.
        rgba = image_to_rgba(image)[380:1030, 650:1350, :3].astype(int)
        r, g, b = rgba[..., 0], rgba[..., 1], rgba[..., 2]
        slab = (b > r + 15) & (b < 110) & (g < 80)
        out["slab_%d" % tilt] = [
            int(slab.sum()), int((slab[:, 1:] != slab[:, :-1]).sum())]
    out["gl"] = dict(view.gl_errors)
    return None


@check(8000)
def tile_fade():
    """Проявление тайлов: камера над Пермью, загрузка, потом
    приближение - тайлы, сменившие предка, проявляются и через TILE_FADE
    рисуются резко."""
    from planetx.core.navigation import Pose
    from planetx.net.overlay import PLACES
    window = state["window"]
    window.set_body("earth")
    state["fade_groups"] = set(window._groups)
    window.set_line_group(PLACES, True)
    window.view.navigator.stop()
    window.view.navigator.show(Pose(58.01, 56.23, 400000.0, 0.0, 0.0))


@check(500)
def tile_fade_check():
    from planetx.core.navigation import Pose
    from planetx.render.view import TILE_FADE
    view = state["window"].view
    out = result["tile_fade"] = {"before": len(view._fading)}
    view.navigator.show(Pose(58.01, 56.23, 60000.0, 0.0, 0.0))
    seen, frames, labels, shown_labels = 0, [], 0, 0
    started = time.monotonic()
    while time.monotonic() - started < 6.0:
        QgsApplication.processEvents()
        view.repaint()
        frames.append(time.monotonic())
        seen = max(seen, len(view._fading))
        labels = max(labels, len(view.labels.born))
        shown_labels = max(shown_labels, view.labels.count)
        time.sleep(0.01)
    # Без новых тайлов проявление кончается за TILE_FADE.
    quiet = time.monotonic()
    while (view._fading or view.labels.born) \
            and time.monotonic() - quiet < 3.0:
        QgsApplication.processEvents()
        view.repaint()
        time.sleep(0.02)
    gaps = [b - a for a, b in zip(frames, frames[1:])]
    out.update({"most_fading": seen, "fade_s": TILE_FADE,
                "most_labels_fading": labels,
                "most_labels": shown_labels,
                "labels_left": len(view.labels.born),
                "ended_s": round(time.monotonic() - quiet, 2),
                "left": len(view._fading),
                "frame_ms_median": round(sorted(gaps)[len(gaps) // 2]
                                         * 1000, 1) if gaps else None,
                "gl": dict(view.gl_errors)})
    view.tile_fade = False
    view.navigator.show(Pose(58.01, 56.23, 3000.0, 0.0, 0.0))
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        QgsApplication.processEvents()
        view.repaint()
        time.sleep(0.02)
    out["off_fading"] = len(view._fading)
    view.tile_fade = True
    state["window"].set_line_groups(state.pop("fade_groups", set()))
    return None


@check(300)
def layer_appear():
    # Проявление картинок слоя карты (core/appear.py): сила тяжести над
    # Гималаями, тайлы приходят и сменяют части предка.
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.view.navigator.stop()
    window.view.navigator.show(Pose(30.0, 85.0, 6.0e6, 0.0, 0.0))
    window.set_extra("gravity", True)


@check(300)
def layer_appear_check():
    from planetx.core import appear
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    layer = view.gibs["emag"]
    out = result["layer_appear"] = {}
    most, bias, hide = 0, 0.0, 0.0
    started = time.monotonic()
    # Приближение - тайлы делятся, приходят подробные картинки слоя.
    for distance in (3.0e6, 1.5e6, 8.0e5):
        view.navigator.show(Pose(30.0, 85.0, distance, 0.0, 0.0))
        until = time.monotonic() + 4.0
        while time.monotonic() < until:
            QgsApplication.processEvents()
            view.repaint()
            states = layer.appear.states
            most = max(most, len(states))
            for _, _, b, h in states.values():
                bias, hide = max(bias, b), max(hide, h)
            time.sleep(0.01)
    quiet = time.monotonic()
    while layer.appear.busy() and time.monotonic() - quiet < 3.0:
        QgsApplication.processEvents()
        view.repaint()
        time.sleep(0.02)
    out.update({"most_appearing": most, "max_bias": round(bias, 2),
                "max_hide": round(hide, 2),
                "ended_s": round(time.monotonic() - quiet, 2),
                "left": len(layer.appear.states),
                "duration_s": appear.DURATION,
                "seconds": round(time.monotonic() - started, 1),
                "gl": dict(view.gl_errors)})
    # Без проявления (снимок вида, запись тура) - сразу резко.
    view.tile_fade = False
    view.navigator.show(Pose(31.0, 86.0, 6.0e5, 0.0, 0.0))
    until = time.monotonic() + 3.0
    while time.monotonic() < until:
        QgsApplication.processEvents()
        view.repaint()
        time.sleep(0.02)
    out["off_appearing"] = len(layer.appear.states)
    view.tile_fade = True
    window.set_extra("gravity", False)
    return None


@check(500)
def tour_layers():
    """Слои у остановок тура: снимок вида в окне свойств запоминает
    строки «Слоёв», файл меток их хранит, тур включает их у каждой
    остановки."""
    from planetx.core import lookat
    from planetx.core.features import Shape
    window = state["window"]
    window.set_body("earth")
    store = window.myplaces
    for place in list(store.places):
        if place.visible:
            store.set_visible(place.key, False)
    out = result["tour_layers"] = {}
    a = store.add(Shape("point", [(58.0, 56.25)], name="Слои 1"),
                  view=(58.0, 56.25, 400000.0, 0.0, 0.0))
    b = store.add(Shape("point", [(55.75, 37.62)], name="Слои 2"),
                  view=(55.75, 37.62, 400000.0, 0.0, 0.0))
    state["layers_keys"] = (a, b)
    # Окно свойств: снимок вида при включённой сетке и снятых плитах.
    window.set_extra("grid", True)
    window.set_extra("plates", False)
    place = store.find(a)
    window._open_place_properties(place)
    dialog = window.prop_dialogs[a]
    dialog._snapshot()
    values = dialog.values()
    out["dialog_layers"] = lookat.layers_parse(values["layers"])
    out["label"] = dialog.keep_layers.text()
    # Темп остановки: пауза 4 с и перелёт вдвое быстрее.
    dialog.stop_pause.setValue(4.0)
    dialog.stop_speed.setValue(2.0)
    out["pace_field"] = dialog.values()["pace"]
    values["pace"] = out["pace_field"]
    dialog.reject()
    store.update(a, {"layers": values["layers"],
                     "pace": values["pace"]})
    store.update(b, {"layers": lookat.layers_text(
        {"grid": False, "plates": True})})
    out["read_back"] = [store.find(k).layers.get("grid")
                        for k in (a, b)]
    # Тур: перед ним всё наоборот, у остановок - своё.
    window.set_extra("grid", False)
    window.set_extra("plates", True)
    window.tour.bar.pause.setValue(1.0)
    stops = []
    for key in (a, b):
        place = store.find(key)
        stop = window.place_stop(place, along=True)
        stop.layers = place.layers
        if place.pace:
            stop.pause, stop.speed = place.pace
        stops.append(stop)
    window.tour.start(stops)
    out["pauses"] = list(window.tour.tour.pauses)
    out["speeds"] = list(window.tour.tour.speeds)
    out["after_start"] = [bool(window.extras.get("grid")),
                          bool(window.extras.get("plates")),
                          [getattr(s, "layers", None) is not None
                           for s in window.tour.stops],
                          window.tour._reached]
    state["layers_seen"] = []
    state["layers_began"] = time.monotonic()


@check(300)
def tour_layers_wait():
    window = state["window"]
    player = window.tour
    seen = state["layers_seen"]
    if player.tour is not None and player.playing:
        mark = (player.index, bool(window.extras.get("grid")),
                bool(window.extras.get("plates")))
        if not seen or seen[-1] != mark:
            seen.append(mark)
        if time.monotonic() - state["layers_began"] < 60.0:
            return 300
    out = result.setdefault("tour_layers", {})
    out["seen"] = seen
    player.stop()
    for key in state.pop("layers_keys", ()):
        window.myplaces.remove(key)
    window.set_extra("grid", False)
    window.set_extra("plates", False)
    out["gl"] = dict(window.view.gl_errors)
    return None


@check(1500)
def stop_state():
    """Состояние вида у метки: сектор разреза и непрозрачность строки
    переживают файл меток и возвращаются видом метки, очаги
    проявляются плавно."""
    from planetx.core import lookat
    from planetx.core.features import Shape
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.view.navigator.show(Pose(30.0, 140.0, 9000000.0, 0.0, 0.0))
    window.view.update()
    store = window.myplaces
    out = result["stop_state"] = {}
    window.set_extra("quakes", False)
    window.set_extra("cutaway", True)
    window.set_wedge_box(120.0, 160.0, 0.0, 38.5)
    snap = window.view_state()
    snap["quakes"] = True
    snap[lookat.OPACITY] = dict(snap.get(lookat.OPACITY) or {},
                                quakes=0.6)
    key = store.add(Shape("point", [(30.0, 140.0)], name="Состояние"),
                    view=(30.0, 140.0, 9000000.0, 0.0, 0.0))
    store.update(key, {"layers": lookat.layers_text(snap)})
    state["state_key"] = key
    layers = store.find(key).layers
    out["stored"] = {k: layers.get(k) for k in (lookat.WEDGE,
                                                lookat.OPACITY)}
    # Другой сектор, потом вид метки возвращает свой.
    window.set_wedge_box(0.0, 90.0, 0.0, 45.0)
    window._apply_view_layers(layers)
    wedge = window.view.wedge
    out["wedge_back"] = [round(v, 3) for v in wedge] if wedge else None
    out["quakes_on"] = bool(window.extras.get("quakes"))
    out["fading"] = sorted(getattr(window, "_fades", {}) or {})
    out["opacity_start"] = round(window.view.quakes.opacity, 3)


@check(1000)
def stop_state_check():
    from planetx.core import lookat
    window = state["window"]
    out = result.setdefault("stop_state", {})
    out["opacity_end"] = round(window.view.quakes.opacity, 3)
    out["fades_left"] = len(getattr(window, "_fades", {}) or {})
    # Плавное выключение: строка гаснет и снимается в конце.
    window._apply_view_layers({"quakes": False})
    out["off_during"] = bool(window.extras.get("quakes"))
    state["off_began"] = time.monotonic()
    out["switch_quakes"] = lookat.switches(
        window.myplaces.find(state["state_key"]).layers).get("quakes")


@check(300)
def stop_state_done():
    window = state["window"]
    out = result.setdefault("stop_state", {})
    out["off_after"] = bool(window.extras.get("quakes"))
    out["opacity_restored"] = round(window.view.quakes.opacity, 3)
    window.myplaces.remove(state.pop("state_key"))
    window.set_extra("cutaway", False)
    from qgis.core import QgsSettings
    QgsSettings().remove("PlanetX/opacity/quakes")
    window._apply_layer_opacity("quakes")
    out["gl"] = dict(window.view.gl_errors)


@check(500)
def tour_free():
    """Камера, взятая на паузе остановки, тур не останавливает: после
    паузы тур летит к следующей остановке. Клавиши показа."""
    from planetx.core.tour import Stop
    window = state["window"]
    window.set_body("earth")
    player = window.tour
    player.bar.pause.setValue(3.0)
    stops = [Stop("А", 58.0, 56.25, 300000.0),
             Stop("Б", 58.5, 57.0, 300000.0),
             Stop("В", 59.0, 57.5, 300000.0)]
    player.start(stops)
    state["free_seen"] = []
    state["free_grabbed"] = None
    state["free_began"] = time.monotonic()
    result["tour_free"] = {}


@check(200)
def tour_free_wait():
    from planetx.core.navigation import Pose
    window = state["window"]
    player = window.tour
    nav = window.view.navigator
    out = result["tour_free"]
    tour = player.tour
    if state["free_grabbed"] is None:
        # Ждём остановки А и берём камеру посреди паузы.
        if tour is not None and player.index == 0 \
                and tour.arrived(player.t) and player.playing:
            nav.stop()
            pose = nav.pose
            nav.show(Pose(pose.lat + 0.2, pose.lon, pose.distance,
                          30.0, 20.0))
            window.view.update()
            player.tick()
            state["free_grabbed"] = time.monotonic()
            out["free"] = player._free is not None
            out["playing_in_free"] = player.playing
            out["index_in_free"] = player.index
        elif time.monotonic() - state["free_began"] > 60.0:
            out["timeout"] = "no arrival"
            return None
        return 200
    if player.index == 1 and player._free is None and player.playing:
        out["moved_on"] = round(time.monotonic() - state["free_grabbed"], 2)
        return None
    if time.monotonic() - state["free_grabbed"] > 20.0:
        out["moved_on"] = None
        out["state"] = [player.index, player._free is not None,
                        player.playing]
        return None
    return 200


@check(500)
def tour_keys():
    from qgis.PyQt.QtCore import QEvent, Qt
    from qgis.PyQt.QtGui import QKeyEvent
    from qgis.PyQt.QtWidgets import QApplication
    from planetx.qt_compat import enum
    window = state["window"]
    player = window.tour
    out = result.setdefault("tour_free", {})

    def press(name):
        event = QKeyEvent(enum(QEvent, "Type", "KeyPress"),
                          enum(Qt, "Key", name),
                          enum(Qt, "KeyboardModifier", "NoModifier"))
        QApplication.sendEvent(window.view, event)

    press("Key_Right")
    out["right"] = player.index
    press("Key_Left")
    press("Key_Left")
    out["left"] = player.index
    press("Key_Space")
    out["space_pause"] = player.playing
    press("Key_Space")
    out["space_play"] = player.playing
    press("Key_Escape")
    out["escape"] = player.tour is None
    out["gl"] = dict(window.view.gl_errors)


@check(1500)
def place_card():
    """Щелчок по метке на глобусе - карточка в панели справа, ответ
    помощника на «Объясни это» - в карточке. Окно свойств карточка
    не вытесняет."""
    from planetx.core.features import Shape
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    store = window.myplaces
    result["place_card"] = {}
    key = store.add(Shape("point", [(58.01, 56.23)], name="Эспланада"))
    store.update(key, {"description": "<b>Площадь</b> в центре Перми."})
    state["card_key"] = key
    window.view.navigator.stop()
    window.view.navigator.show(Pose(58.01, 56.23, 3000.0, 0.0, 0.0))
    window.view.update()


@check(500)
def place_card_check():
    from planetx.ui.placecard import PlaceCard, explain_question
    window = state["window"]
    out = result.setdefault("place_card", {})
    view = window.view
    view.repaint()
    QgsApplication.processEvents()
    cam = view.camera
    window._clicked(cam.width / 2.0, cam.height / 2.0)
    card = window.side.dialog
    out["card"] = isinstance(card, PlaceCard)
    out["visible"] = window.side.isVisible()
    if isinstance(card, PlaceCard):
        out["title"] = card.windowTitle()
        out["text"] = card.text.toPlainText()
        out["explain_enabled"] = card.explain_button.isEnabled()
        place = window.myplaces.find(state["card_key"])
        out["question"] = explain_question(place, "Метка")
        window._explaining = card
        window._assistant_said("assistant", "Это площадь.")
        out["answer"] = card.answer.text()
        # Окно свойств в панели, щелчок по метке его не вытесняет.
        window._open_place_properties(place)
        window._clicked(cam.width / 2.0, cam.height / 2.0)
        out["props_kept"] = not isinstance(window.side.dialog, PlaceCard)
        window.side.close_dialog()
    # Щелчок мимо меток карточку не открывает.
    window.side.close_dialog()
    window._clicked(5.0, 5.0)
    out["empty_click"] = window.side.dialog is None
    window.myplaces.remove(state.pop("card_key"))
    window.panel.set_answer("")
    out["gl"] = dict(view.gl_errors)


def _dark_openers(window):
    """Немодальные окна модуля и окна панели справа: имя - открытие."""
    from planetx.core.features import Shape
    store = window.myplaces
    key = store.add(Shape("point", [(58.01, 56.23)], name="Окна"))
    state["dark_key"] = key

    def place():
        return store.find(key)

    def modal(make):
        # Окна, которые модуль открывает exec, - здесь show, иначе шаг
        # ждал бы закрытия.
        def opener():
            dialog = make()
            state.setdefault("dark_keep", []).append(dialog)
            dialog.show()
        return opener

    from qgis.core import QgsProject, QgsVectorLayer
    from qgis.PyQt.QtWidgets import QMessageBox
    from planetx.ui.menulinks import MenuLinksDialog
    from planetx.ui.netlink import LinkDialog
    from planetx.ui.record import RecordDialog
    from planetx.ui.sounding import SoundingDialog
    from planetx.ui.tilesource import TileSourceDialog
    from planetx.ui.track import TrackDialog
    points = QgsVectorLayer(
        "Point?crs=EPSG:4326&field=time:datetime&field=depth:double",
        "dark points", "memory")
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY
    features = []
    for k, (lat, lon) in enumerate(((58.01, 56.23), (58.02, 56.24),
                                    (58.03, 56.22))):
        feature = QgsFeature(points.fields())
        feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon, lat)))
        feature.setAttribute("depth", 5.0 + k)
        features.append(feature)
    points.dataProvider().addFeatures(features)
    QgsProject.instance().addMapLayer(points, False)
    state["dark_layer"] = points
    cam = window.view.camera
    return [
        ("tilesource", modal(lambda: TileSourceDialog(window,
                                                      (58.0, 56.2)))),
        ("menulinks", modal(lambda: MenuLinksDialog(window))),
        ("record", modal(lambda: RecordDialog(window))),
        ("netlink", modal(lambda: LinkDialog(parent=window))),
        ("track", modal(lambda: TrackDialog(points, None, window))),
        ("sounding", modal(lambda: SoundingDialog(
            points, 0.0, os.path.join(TEMP, "dark.tif"), window))),
        ("message", modal(lambda: QMessageBox(
            QMessageBox.Icon.Question, "PlanetX",
            "Окно вопроса модуля в оформлении окна глобуса.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            window))),
        ("properties", window._show_properties),
        ("sources", window.open_sources),
        ("catalog", window.open_gallery),
        ("new_place", lambda: window._open_place("point")),
        ("sheets", lambda: window.sheets_here(58.01, 56.23)),
        ("sentinel", lambda: window.sentinel_here(58.01, 56.23)),
        ("identify", lambda: window.identify_here(cam.width / 2.0,
                                                  cam.height / 2.0)),
        ("assistant", window.open_assistant),
        ("snapshot", lambda: window._open_snapshot(False)),
        ("section", lambda: window._open_section(
            "Разрез", [(58.0, 56.0), (58.1, 56.5)])),
        ("ruler", window._open_ruler),
        ("subsurface", window.subsurface.open_dialog),
        ("viewshed", lambda: window._open_viewshed(place())),
        ("insolation", lambda: window._open_insolation(place())),
        ("place_card", lambda: window.open_place_card(place())),
        ("place_props", lambda: window._open_place_properties(place())),
    ]


@check(1200, manual=True)
def dark_windows():
    """Окна модуля в оформлении PLANETX_THEME (по умолчанию тёмное):
    каждое открывается, снимается в TEMP/planetx_<оформление>_<имя>.png
    и закрывается. Доля светлых пикселей окна - поле light, у тёмного
    окна она мала, title_dark - тёмный ли заголовок окна."""
    from qgis.PyQt.QtWidgets import QApplication
    from planetx.ui import style
    window = state["window"]
    out = result.setdefault("dark_windows", {})
    look = state.get("dark")
    theme = os.environ.get("PLANETX_THEME", style.DARK)
    if look is None:
        window.set_ui_theme(theme)
        look = state["dark"] = {"n": 0, "items": _dark_openers(window),
                                "before": None}
    items = look["items"]
    n = look["n"]
    if look["before"] is not None:
        name = items[n][0]
        shots = []
        new = [w for w in QApplication.topLevelWidgets()
               if w.isVisible() and w not in look["before"]
               and w is not window]
        if window.side.isVisible() and window.side.dialog is not None:
            new.append(window.side)
        for k, widget in enumerate(new):
            image = widget.grab().toImage()
            path = os.path.join(TEMP, "planetx_{}_{}{}.png".format(
                theme, name, "_{}".format(k) if k else ""))
            image.save(path)
            light = 0
            total = 0
            for y in range(0, image.height(), 6):
                for x in range(0, image.width(), 6):
                    c = image.pixelColor(x, y)
                    total += 1
                    if c.lightness() > 200:
                        light += 1
            shots.append({"widget": type(widget).__name__,
                          "size": [image.width(), image.height()],
                          "light": round(light / max(total, 1), 2),
                          "title_dark": _title_dark(widget)
                          if widget is not window.side else None})
            if widget is not window.side:
                widget.close()
        window.side.close_dialog()
        out[name] = shots or "no window"
        look["before"] = None
        look["n"] = n = n + 1
        if n >= len(items):
            window.myplaces.remove(state.pop("dark_key"))
            QgsProject_ = __import__("qgis.core", fromlist=["QgsProject"])
            QgsProject_.QgsProject.instance().removeMapLayer(
                state.pop("dark_layer").id())
            return None
    look["before"] = set(w for w in QApplication.topLevelWidgets()
                         if w.isVisible())
    try:
        items[n][1]()
    except (AttributeError, TypeError, ValueError, RuntimeError) as error:
        out[items[n][0]] = "error: {}".format(error)
    return 1200


@check(2000)
def haul_open():
    """Демо «Самосвалы, Качканар»: слой самосвалов треком с моделью,
    шкала времени идёт."""
    from planetx.core.features import Shape
    window = state["window"]
    window.set_body("earth")
    result["haul"] = {}
    # Метка со временем 1875 года, как у автора: шкала начинается с
    # неё, а самосвалы должны стоять на своём рейсе.
    key = window.myplaces.add(Shape("point", [(11.35, 142.2)],
                                    name="Челленджер"))
    window.myplaces.update(key, {"time": "1875-03-23"})
    state["haul_old_key"] = key
    window.open_demo(os.environ.get("PLANETX_HAUL", "haul_kachkanar"))
    state["haul_since"] = time.monotonic()


@check(500)
def haul_wait():
    """Ждёт моделей самосвалов на виде и загрузки, не дольше 60 с."""
    window = state["window"]
    view = window.view
    view.repaint()
    QgsApplication.processEvents()
    waited = time.monotonic() - state["haul_since"]
    drawn = getattr(view.models, "drawn", 0)
    if (view.load_missing or not drawn) and waited < 60.0:
        return 1000
    out = result["haul"]
    out["waited"] = round(waited, 1)
    out["tracks"] = len(window.tracks.tracks)
    out["at"] = len(window.tracks._at)
    out["drawn"] = drawn
    bar = window.timebar
    out["bar_shown"] = bar.shown()
    out["playing"] = bar.timer.isActive()
    out["speed"] = bar.speed.currentData()
    out["loop"] = bar.loop.isChecked()
    out["load_missing"] = view.load_missing
    import datetime as _dt
    out["bar_start_year"] = (_dt.datetime(1970, 1, 1) + _dt.timedelta(
        seconds=bar.extent()[0])).year
    span = getattr(window, "_haul_span", None)
    moment = bar.range()[1]
    out["moment_in_trip"] = span is not None \
        and span[0] <= moment <= span[1]
    # Конец рейса - момент снова в начале.
    if span is not None:
        bar.set_point(True, at=span[1] + 60.0)
        window._haul_loop()
        out["loop_back"] = abs(bar.range()[1] - span[0]) < 1.0
    return None


@check(500)
def haul_check():
    """Самосвалы едут: положения через 2 с другие, азимут модели - по
    ходу. Кадр вблизи самосвала - в TEMP."""
    import math as _math
    from qgis.PyQt.QtTest import QTest
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    out = result["haul"]
    before = dict(window.tracks._at)
    QTest.qWait(2000)
    after = dict(window.tracks._at)
    moved = [k for k in after if k in before and before[k][:2]
             != after[k][:2]]
    out["moved"] = len(moved)
    # Азимут по сдвигу точки и азимут модели.
    gaps = []
    for k in moved:
        lat0, lon0 = before[k][:2]
        lat1, lon1, heading = after[k][:3]
        dy = (lat1 - lat0) * 111320.0
        dx = (lon1 - lon0) * 111320.0 * _math.cos(_math.radians(lat1))
        if _math.hypot(dx, dy) < 2.0:
            continue
        course = _math.degrees(_math.atan2(dx, dy)) % 360.0
        gaps.append(round(((heading - course + 180.0) % 360.0) - 180.0, 1))
    out["heading_gap"] = gaps
    # Вблизи первого самосвала, показ на паузе - самосвал стоит.
    bar = window.timebar
    if bar.timer.isActive():
        bar.toggle()
    after = dict(window.tracks._at)
    key = sorted(after)[0]
    lat, lon, heading = after[key][:3]
    view.navigator.stop()
    view.navigator.show(Pose(lat, lon, 70.0, heading + 120.0, 62.0))
    view.update()
    started = time.monotonic()
    while time.monotonic() - started < 25.0:
        QTest.qWait(500)
        view.repaint()
        if not view.load_missing:
            break
    image = view.grabFramebuffer()
    shot = os.path.join(TEMP, "planetx_haul_truck.png")
    image.save(shot)
    out["shot"] = shot
    view.navigator.show(Pose(lat, lon, 1500.0, heading, 55.0))
    view.update()
    QTest.qWait(3000)
    view.repaint()
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_haul_pit.png"))
    out["gl"] = dict(view.gl_errors)
    return None

@check(500)
def haul_follow():
    """Камера следом за самосвалом: пункт меню правой кнопки над
    самосвалом, самосвал в середине кадра через 3 с хода, колесо меняет
    расстояние, Esc отпускает."""
    import numpy as _np
    from qgis.PyQt.QtCore import QPoint, QPointF, Qt
    from qgis.PyQt.QtGui import QWheelEvent
    from qgis.PyQt.QtTest import QTest
    from qgis.PyQt.QtWidgets import QApplication, QMenu
    from planetx.core.ellipsoid import geodetic_to_ecef
    from planetx.core.navigation import Pose
    from planetx.ui import globemenu
    window = state["window"]
    view = window.view
    tracks = window.tracks
    out = result["haul"]
    bar = window.timebar
    if not bar.timer.isActive():
        bar.toggle()
    key = sorted(tracks._at)[0]
    lat, lon = tracks._at[key][:2]
    view.navigator.stop()
    view.navigator.show(Pose(lat, lon, 1200.0, 0.0, 40.0))
    view.update()
    QTest.qWait(500)
    view.repaint()

    def pixel(target):
        lat, lon = tracks._at[target][:2]
        h = view.label_height(lat, lon)
        p, _ = view.camera.project(geodetic_to_ecef(
            _np.array([lat]), _np.array([lon]), _np.array([h])))
        return float(p[0][0]), float(p[0][1])

    px, py = pixel(key)
    out["under"] = tracks.under(px, py) == key
    menu = QMenu()
    globemenu.track_items(window, menu, px, py)
    texts = [a.text() for a in menu.actions()]
    out["menu"] = texts
    follow = [a for a in menu.actions() if a.isCheckable()]
    if not follow:
        return None
    follow[0].setChecked(True)
    QTest.qWait(3000)
    view.repaint()
    x, y = pixel(key)
    ratio = view.devicePixelRatioF()
    cx = view.width() * ratio / 2.0
    cy = view.height() * ratio / 2.0
    out["followed"] = tracks.followed == key
    out["off_centre_px"] = round(float(_np.hypot(x - cx, y - cy)), 1)
    reach = tracks.chase.reach
    point = QPointF(view.width() / 2.0, view.height() / 2.0)
    from planetx.qt_compat import enum
    QApplication.sendEvent(view, QWheelEvent(
        point, QPointF(view.mapToGlobal(point.toPoint())), QPoint(0, 0),
        QPoint(0, 240), enum(Qt, "MouseButton", "NoButton"),
        enum(Qt, "KeyboardModifier", "NoModifier"),
        enum(Qt, "ScrollPhase", "NoScrollPhase"), False))
    out["wheel"] = [round(reach), round(tracks.chase.reach)]
    from qgis.PyQt.QtCore import QEvent
    from qgis.PyQt.QtGui import QKeyEvent
    QApplication.sendEvent(view, QKeyEvent(
        enum(QEvent, "Type", "KeyPress"), enum(Qt, "Key", "Key_Escape"),
        enum(Qt, "KeyboardModifier", "NoModifier")))
    out["esc_released"] = tracks.followed is None
    shot = os.path.join(TEMP, "planetx_haul_follow.png")
    tracks.set_follow(key)
    QTest.qWait(2000)
    view.repaint()
    view.grabFramebuffer().save(shot)
    tracks.set_follow(None)
    out["follow_shot"] = shot
    return None


@check(500)
def haul_close():
    """Снятие демо: трек и слой убраны, шкала стоит."""
    from qgis.core import QgsProject
    window = state["window"]
    window.myplaces.remove(state.pop("haul_old_key"))
    project = QgsProject.instance()
    root = project.layerTreeRoot()
    group = root.findGroup("Самосвалы в карьере") \
        or root.findGroup("Haul trucks in the pit")
    # Снятый флажок слоя в «Проект QGIS» убирает трек и модели с вида,
    # замечание автора от 20 октября 2026 года.
    out = result["haul"]
    layer_id = group.findLayers()[0].layerId() if group is not None \
        else None
    if layer_id is not None:
        window.set_layer_shown(layer_id, False)
        out["hidden"] = [len(window.tracks.tracks), len(window.tracks._at),
                         len(window.view.models.groups.get("tracks", []))]
        window.set_layer_shown(layer_id, True)
        out["shown_again"] = [len(window.tracks.tracks),
                              len(window.view.models.groups.get(
                                  "tracks", []))]
    if group is not None:
        for node in group.findLayers():
            window.tracks.set_track(node.layer(), None)
            project.removeMapLayer(node.layerId())
        root.removeChildNode(group)
    window.timebar.stop()
    result["haul"]["after_tracks"] = len(window.tracks.tracks)


@check(1500)
def wiki_on():
    """Википедия рядом: центр Перми с 6 км, строка «Википедия рядом»
    и сетка - включённый слой для вопроса помощнику."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    result["wiki"] = {}
    window.view.navigator.stop()
    window.view.navigator.show(Pose(58.01, 56.235, 6000.0, 0.0, 0.0))
    window.view.update()
    window.set_extra("grid", True)
    window.set_extra("wiki", True)
    state["wiki_since"] = time.monotonic()


@check(500)
def wiki_wait():
    """Ждёт тайлов статей и подписей статей на экране, не дольше 40 с."""
    from planetx.ui.globe.wiki import WIKI_ID
    window = state["window"]
    view = window.view
    window._want_wiki()
    view.repaint()
    QgsApplication.processEvents()
    shown = [k for k in view.labels.shown if (k[0] or 0) >= WIKI_ID]
    waited = time.monotonic() - state["wiki_since"]
    if (len(window.wiki_articles.tiles) < 9 or not shown) and waited < 40.0:
        return 1000
    out = result["wiki"]
    out["waited"] = round(waited, 1)
    out["tiles"] = len(window.wiki_articles.tiles)
    out["articles"] = len(window.wiki_articles.articles())
    out["marks"] = len(view.wiki_marks)
    out["shown"] = len(shown)
    out["lang"] = window.wiki_articles.lang
    out["credit"] = "Wikipedia" in window.attribution.text()
    return None


@check(500)
def wiki_click():
    """Щелчок по подписанной статье - карточка статьи в панели."""
    import numpy as np
    from planetx.core.ellipsoid import geodetic_to_ecef
    from planetx.core.places import identity
    from planetx.ui.placecard import ArticleCard
    window = state["window"]
    view = window.view
    out = result["wiki"]
    shown = view.labels.shown
    mark = next((m for m in view.wiki_marks if identity(m) in shown), None)
    if mark is None:
        out["click"] = "no shown mark"
        return None
    h = float(view.label_heights(np.array([mark.lat]),
                                 np.array([mark.lon]))[0])
    pixel, _ = view.camera.project(geodetic_to_ecef(mark.lat, mark.lon, h))
    px, py = float(pixel[0]), float(pixel[1])
    state["wiki_pixel"] = (px, py)
    window.side.close_dialog()
    # Группа окна «Объекты» - до карточки: панель справа сужает вид,
    # и точка статьи уходит с пикселя.
    out["objects_group"] = len(window._identify_wiki(px, py))
    window._clicked(px, py)
    card = window.side.dialog
    out["card"] = isinstance(card, ArticleCard)
    out["title"] = card.article.title if out["card"] else None
    out["mark"] = mark.name
    out["link"] = card.link if out["card"] else None
    state["wiki_since"] = time.monotonic()
    return None


@check(500)
def wiki_card():
    """Первый абзац в карточке, вопрос помощнику со статьёй и слоями,
    метка из статьи в «Мои метки», снятие строки."""
    from planetx.ui.placecard import ArticleCard, article_question
    window = state["window"]
    out = result["wiki"]
    card = window.side.dialog
    if not isinstance(card, ArticleCard):
        out["summary"] = "no card"
        return None
    waited = time.monotonic() - state["wiki_since"]
    if not card.extract and waited < 20.0:
        return 1000
    out["extract"] = card.extract[:120]
    out["double_space"] = "  " in card.extract
    a = card.article
    layers = window._explain_layers()
    out["layers"] = layers
    question = article_question(a.title, card.extract, a.lat, a.lon, layers)
    out["question_has_extract"] = bool(card.extract) \
        and " ".join(card.extract.split())[:40] in question
    out["question_has_grid"] = any(name in question for name in layers)
    before = len(window.myplaces.places)
    window.keep_article(card)
    added = [p for p in window.myplaces.places
             if p.shape.name == a.title]
    out["kept"] = len(window.myplaces.places) - before
    out["kept_link"] = bool(added) and card.link in added[-1].description
    for place in added:
        window.myplaces.remove(place.key)
    window.side.close_dialog()
    window.set_extra("wiki", False)
    window.set_extra("grid", False)
    out["marks_after"] = len(window.view.wiki_marks)
    out["gl"] = dict(window.view.gl_errors)
    return None


@check(8000)
def crossfade_on():
    """Плавная смена подложки: камера над Пермью, загрузка."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.view.navigator.stop()
    window.view.navigator.show(Pose(58.01, 56.23, 30000.0, 0.0, 0.0))


@check(500)
def crossfade_check():
    import numpy as np
    from planetx.net.loader import image_to_rgba
    window = state["window"]
    view = window.view
    out = result["crossfade"] = {}

    def frame():
        view.repaint()
        QgsApplication.processEvents()
        return image_to_rgba(view.grabFramebuffer())[..., :3].astype(int)

    def diff(a, b):
        return round(float(np.abs(a - b).mean()), 2)

    before = frame()
    # Прежний кадр лежит в текстуре перехода с конца кадра (_cross_keep).
    out["kept_before"] = view._cross_kept
    old = window.source
    other = [s for s in window.sources if s is not old]
    window._switch_basemap(other[0])
    out["switched"] = [old.name, other[0].name]
    out["started"] = view._cross is not None
    first = frame()
    out["hold_diff"] = diff(before, first)
    alphas = []
    started = time.monotonic()
    while view._cross is not None and time.monotonic() - started < 8.0:
        QgsApplication.processEvents()
        view.repaint()
        state_ = view._cross
        if state_ is not None and state_.get("fading") is not None:
            alphas.append(round(1.0 - (time.monotonic() - state_["fading"])
                                / state_["span"], 2))
        time.sleep(0.03)
    out["seconds"] = round(time.monotonic() - started, 2)
    out["fade_steps"] = len(alphas)
    out["ended"] = view._cross is None
    after = frame()
    out["after_diff"] = diff(before, after)
    window._switch_basemap(old)
    deadline = time.monotonic() + 6.0
    while view._cross is not None and time.monotonic() < deadline:
        QgsApplication.processEvents()
        view.repaint()
        time.sleep(0.03)
    out["gl"] = dict(view.gl_errors)
    return None


@check(300)
def snapshot_brand():
    """PlanetX в углу снимка вида и кадра записи: в самом углу плашка
    названия, левее - подпись источников."""
    from qgis.PyQt.QtGui import QColor, QImage
    from planetx.ui.snapshot import draw_attribution
    out = result["snapshot_brand"] = {}
    for name, brand in (("with", "PlanetX"), ("without", "")):
        image = QImage(600, 200, QImage.Format.Format_RGB32
                       if hasattr(QImage, "Format") else QImage.Format_RGB32)
        image.fill(QColor(0, 0, 160))
        draw_attribution(image, "Esri", 1.0, brand=brand)
        image.save(os.path.join(TEMP, "planetx_brand_%s.png" % name))
        # Изменённые пиксели нижней полосы: знак и подпись, фона-плашки
        # нет - далеко над ними картинка не меняется.
        changed = [x for x in range(image.width())
                   for y in range(image.height() - 34, image.height())
                   if QColor(image.pixel(x, y)) != QColor(0, 0, 160)]
        above = sum(1 for x in range(0, image.width(), 3)
                    for y in range(0, image.height() - 40, 3)
                    if QColor(image.pixel(x, y)) != QColor(0, 0, 160))
        out[name] = [min(changed), max(changed), above] \
            if changed else None
    # Со знаком подпись сдвинута влево на его ширину.
    out["shifted"] = bool(out["with"] and out["without"]
                          and out["with"][0] < out["without"][0] - 40)
    window = state["window"]
    out["view_brand"] = window.brand.text()


@check(300)
def zlayer_polyhedral():
    """Слои многогранников PolyhedralSurfaceZ и TIN Z читаются гранями,
    прежде чтение падало на exteriorRing. В QGIS без этих типов (3.36)
    поле types пустое."""
    from qgis.core import QgsFeature, QgsGeometry, QgsVectorLayer
    from planetx.ui.subsurface import read_zlayer
    out = result["zlayer_polyhedral"] = {"types": []}
    for name, wkt in (
            ("PolyhedralSurfaceZ", "POLYHEDRALSURFACE Z (((56.2 58 100, "
             "56.201 58 100, 56.201 58.001 100, 56.2 58 100)), ((56.2 58 "
             "100, 56.201 58 100, 56.201 58 130, 56.2 58 100)))"),
            ("TINZ", "TIN Z (((56.2 58 100, 56.201 58 100, 56.201 58.001 "
             "100, 56.2 58 100)))")):
        geometry = QgsGeometry.fromWkt(wkt)
        if geometry.isNull():
            continue
        layer = QgsVectorLayer(name + "?crs=EPSG:4326", "probe", "memory")
        if not layer.isValid():
            continue
        feature = QgsFeature()
        feature.setGeometry(geometry)
        layer.dataProvider().addFeatures([feature])
        out["types"].append(name)
        shapes = read_zlayer(layer)
        out[name] = [len(s.parts) for s in shapes]


def _post_shot(name):
    """Кадр для объявления: окно во весь экран целиком, с органами
    навигации и подписями поверх вида."""
    window = state["window"]
    window.grab().save(os.path.join(TEMP, "planetx_post_%s.png" % name))


def _post_full(on):
    window = state["window"]
    if window.isFullScreen() != on:
        window.toggle_fullscreen()


SPEED_PLACES = ((58.0105, 56.2294), (55.7522, 37.6156), (43.3499, 42.4453),
                (46.5600, 8.0000), (59.4500, 56.8800), (35.3606, 138.7274))
SPEED_STAY = 8.0  # с на место, камера кружит


@check(500, manual=True)
def speed_profile():
    """Ручной шаг: профиль Python главного потока при облёте шести мест.
    Камера кружит над местом с наклоном 60° и уходит к следующему, вид
    обычный - подложка, рельеф, подписи, звёзды. Пишутся интервалы
    кадров, паузы цикла событий и самые затратные функции модуля."""
    import cProfile
    import math as _m
    from qgis.PyQt.QtCore import QTimer
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    view = window.view
    frames = state["speed_frames"] = []
    gaps = state["speed_gaps"] = []
    view.frameSwapped.connect(lambda: frames.append(time.perf_counter()))
    t0 = time.perf_counter()
    state["speed_t0"] = t0
    tick = {"last": t0}

    def move():
        now = time.perf_counter()
        gaps.append(now - tick["last"])
        tick["last"] = now
        t = now - t0
        k = min(int(t // SPEED_STAY), len(SPEED_PLACES) - 1)
        lat, lon = SPEED_PLACES[k]
        a = (t % SPEED_STAY) / SPEED_STAY * 2 * _m.pi
        view.navigator.show(Pose(lat + 0.01 * _m.sin(a),
                                 lon + 0.02 * _m.cos(a), 15000.0,
                                 (t * 25.0) % 360.0, 60.0))
        view.update()
    timer = state["speed_timer"] = QTimer()
    timer.timeout.connect(move)
    timer.start(16)
    # PLANETX_SPEED_NOPROF - замер без профилировщика, он замедляет
    # Python в разы.
    # PLANETX_SPEED_SAMPLE - выборка стека только главного потока раз
    # в 4 мс. cProfile в Python 3.12 идёт через sys.monitoring и пишет
    # все потоки сразу, по нему не видно, что держит главный поток.
    if os.environ.get("PLANETX_SPEED_SAMPLE"):
        state["speed_samples"] = _start_sampler()
        os.environ["PLANETX_SPEED_NOPROF"] = "1"
    prof = state["speed_prof"] = None if os.environ.get(
        "PLANETX_SPEED_NOPROF") else cProfile.Profile()
    if prof is not None:
        prof.enable()


@check(500, manual=True)
def gl_fast_check():
    """Ручной шаг: включились ли быстрые вызовы кадра и каких адресов
    не дал контекст."""
    from planetx.render import gpu
    view = state["window"].view
    view.makeCurrent()
    context = view.context()
    missing = []
    for name, _ in gpu._FRAME_CALLS:
        address = context.getProcAddress(name.encode())
        if not (int(address) if address is not None else 0):
            missing.append(name)
    view.doneCurrent()
    result["gl_fast"] = {"fast": gpu.gl.fast, "missing": missing}


def _start_sampler(period=0.004):
    """Поток выборки стека главного потока: счёт верхних строк модуля
    (свой кадр и кадр внутри) и всех функций модуля в стеке."""
    import sys as _sys
    import threading
    main = threading.main_thread().ident
    data = {"leaf": {}, "inclusive": {}, "via": {}, "total": 0, "busy": 0,
            "stop": False}

    def name(frame):
        path = frame.f_code.co_filename.replace("\\", "/")
        short = path.split("/planetx/")[-1] if "/planetx/" in path \
            else path.rsplit("/", 1)[-1]
        return "%s:%s" % (short, frame.f_code.co_name)

    def run():
        while not data["stop"]:
            time.sleep(period)
            frame = _sys._current_frames().get(main)
            data["total"] += 1
            if frame is None:
                continue
            data["busy"] += 1
            leaf = "%s:%d" % (name(frame), frame.f_lineno)
            data["leaf"][leaf] = data["leaf"].get(leaf, 0) + 1
            # Чужой код наверху - кто из модуля его позвал.
            if not name(frame).startswith("planetx/"):
                up = frame
                while up is not None and not name(up).startswith(
                        "planetx/"):
                    up = up.f_back
                if up is not None:
                    via = "%s <- %s:%d" % (name(frame), name(up),
                                           up.f_lineno)
                    data["via"][via] = data["via"].get(via, 0) + 1
            seen = set()
            while frame is not None:
                key = name(frame)
                if key not in seen:
                    seen.add(key)
                    data["inclusive"][key] = \
                        data["inclusive"].get(key, 0) + 1
                frame = frame.f_back
    threading.Thread(target=run, daemon=True).start()
    return data


@check(1000, manual=True)
def speed_profile_done():
    import pstats
    import statistics
    spent = time.perf_counter() - state["speed_t0"]
    if spent < SPEED_STAY * len(SPEED_PLACES):
        return 1000
    prof = state["speed_prof"]
    if prof is not None:
        prof.disable()
    state["speed_timer"].stop()
    samples = state.get("speed_samples")
    if samples is not None:
        samples["stop"] = True
        result["speed_samples"] = {
            "total": samples["total"], "busy": samples["busy"],
            "leaf": sorted(samples["leaf"].items(),
                           key=lambda kv: -kv[1])[:40],
            "via": sorted(samples["via"].items(),
                          key=lambda kv: -kv[1])[:30],
            "inclusive": sorted(samples["inclusive"].items(),
                                key=lambda kv: -kv[1])[:60]}
    frames = state["speed_frames"]
    gaps = [g * 1000.0 for g in state["speed_gaps"][1:]]
    iv = [(b - a) * 1000.0 for a, b in zip(frames, frames[1:])]
    worst = None
    j = 0
    for i, start in enumerate(frames):
        while j < len(frames) and frames[j] < start + 1.0:
            j += 1
        if frames[-1] - start >= 1.0:
            worst = j - i if worst is None else min(worst, j - i)
    stats = pstats.Stats(prof) if prof is not None else None
    rows = []
    calls = {}
    for (path, line, name), (cc, nc, tt, ct, by) in (
            stats.stats.items() if stats else ()):
        calls.setdefault(name, []).extend(
            (round(v[2], 3), "%s:%d %s" % (
                k[0].replace("\\", "/").split("planetx/planetx/")[-1],
                k[1], k[2])) for k, v in by.items())
        rows.append((tt, ct, nc, "%s:%d %s" % (
            path.replace("\\", "/").split("planetx/planetx/")[-1],
            line, name)))
    total = sum(r[0] for r in rows)
    own = [r for r in rows if "planetx" in r[3] or "/" not in r[3]]
    result["speed"] = {
        "seconds": round(spent, 1), "frames": len(frames),
        "fps": round(len(frames) / spent, 1), "worst_second": worst,
        "interval_median": round(statistics.median(iv), 1) if iv else None,
        "interval_p95": round(sorted(iv)[int(len(iv) * 0.95)], 1)
        if iv else None,
        "loop_gaps_over_50": sum(1 for g in gaps if g > 50.0),
        "loop_gap_max": round(max(gaps), 1) if gaps else None,
        "profiled_s": round(total, 2),
        "tottime": [(round(r[0], 3), r[2], r[3]) for r in sorted(
            rows, key=lambda r: -r[0])[:40]],
        "cumtime": [(round(r[1], 3), r[2], r[3]) for r in sorted(
            own, key=lambda r: -r[1])[:40]],
        # Кто зовёт тяжёлые функции: время вызова от каждого вызывающего.
        "callers": {n: sorted(calls.get(n, []), reverse=True)[:6] for n in (
            "glCheckError", "_packed", "_fields", "height_at", "probe",
            "drawEllipse", "at", "createRequest", "sample", "best")}}
    return None


@check(500, manual=True)
def post_flows():
    """Ручной шаг: кадр демо «Поток грузов, схема» для объявления."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.set_extra("air", True)
    _post_full(True)
    # Метки прежних шагов проверочного профиля в кадр не идут.
    window.clear_places(confirm=False)
    window.open_demo("flows")
    state["ls_started"] = time.monotonic()
    state["post_pose"] = Pose(54.0, 75.0, 8500000.0, 0.0, 0.0)


@check(1000, manual=True)
def post_flows_shot():
    window = state["window"]
    spent = time.monotonic() - state["ls_started"]
    if spent < 4.0:
        return 1000
    if "post_posed" not in state:
        state["post_posed"] = True
        window.view.navigator.stop()
        window.view.navigator.show(state["post_pose"])
        return 1000
    if spent < 25.0:
        return 1000
    _post_shot("flows")
    state.pop("post_posed", None)
    return None


@check(500, manual=True)
def post_turbines():
    """Ручной шаг: демо ветряков во весь экран для объявления."""
    window = state["window"]
    window.set_body("earth")
    window.set_extra("air", True)
    _post_full(True)
    window.clear_places(confirm=False)
    window.open_demo("turbines")
    state["ls_started"] = time.monotonic()


@check(1000, manual=True)
def post_turbines_video():
    """Кадр и ролик MP4 на один оборот ротора. Время анимации ставится
    на каждый кадр само: ролик идёт с настоящей скоростью при любой
    скорости съёмки. Ветряки повёрнуты по фазе, чтобы не крутились
    одинаково. PLANETX_POST_POSE - широта, долгота, расстояние, азимут,
    наклон через запятую. PLANETX_POST_ORBIT - облёт: градусы азимута
    за ролик и длительность в секундах через запятую. Перед кадром
    облёта шаг ждёт загрузки тайлов новой позы, не дольше 3 с."""
    from qgis.PyQt.QtTest import QTest
    import ctypes
    from qgis.PyQt.QtCore import Qt as _Qt
    from qgis.PyQt.QtGui import QImage
    from planetx.core import video
    from planetx.core.navigation import Pose
    from planetx.ui.snapshot import draw_attribution, plain_text
    window = state["window"]
    view = window.view
    spent = time.monotonic() - state["ls_started"]
    if spent < 4.0:
        return 1000
    if "post_posed" not in state:
        state["post_posed"] = time.monotonic()
        pose = os.environ.get("PLANETX_POST_POSE", "57.9936,56.0185,420,"
                              "130,84")
        view.navigator.stop()
        view.navigator.show(Pose(*[float(v) for v in pose.split(",")]))
        view.update()
        return 2000
    waited = time.monotonic() - state["post_posed"]
    if (view.load_missing or waited < 10.0) and waited < 60.0:
        return 1000
    fps, seconds = 25, 6.0
    orbit = os.environ.get("PLANETX_POST_ORBIT")
    turn = 0.0
    if orbit:
        turn, seconds = (float(v) for v in orbit.split(","))
    start = view.navigator.pose
    first = view.grabFramebuffer()
    width, height = video.even_size(first.width() // 2,
                                    first.height() // 2)
    out = os.path.join(TEMP, "planetx_post_turbines.mp4")
    writer = video.Mp4Writer(out, width, height, fps)
    keys = sorted(view.models.started)
    phases = {key: n * 0.9 for n, key in enumerate(keys)}
    try:
        for k in range(int(fps * seconds)):
            if turn:
                share = k / (fps * seconds)
                view.navigator.show(Pose(start.lat, start.lon,
                                         start.distance,
                                         (start.heading + turn * share)
                                         % 360.0, start.tilt))
                view.update()
                QTest.qWait(30)
                waited_at = time.monotonic()
                while view.load_missing and \
                        time.monotonic() - waited_at < 3.0:
                    QTest.qWait(50)
            now = time.monotonic()
            for key in keys:
                view.models.started[key] = now - k / fps - phases[key]
            image = view.grabFramebuffer().scaled(
                width, height, _Qt.AspectRatioMode.IgnoreAspectRatio,
                _Qt.TransformationMode.SmoothTransformation)
            image = image.convertToFormat(QImage.Format.Format_RGB32)
            # Кадр несёт масштаб экрана: без сброса знак и подпись
            # рисовались бы за краем картинки.
            image.setDevicePixelRatio(1.0)
            # Подпись источников и знак PlanetX - как у записи тура.
            draw_attribution(image, plain_text(
                window.attribution.text()), 1.0)
            if k == 0:
                image.save(os.path.join(TEMP, "planetx_post_turbines.png"))
            bits = image.constBits()
            bits.setsize(image.sizeInBytes())
            frame = bytearray(bytes(bits))
            holder = ctypes.c_char.from_buffer(frame)
            writer.write(ctypes.addressof(holder))
            del holder
    finally:
        writer.close()
    result["post_turbines"] = {"frames": writer.count, "size": [width,
                                                                height],
                               "models": len(keys), "waited": round(
                                   waited, 1)}
    state.pop("post_posed", None)
    return None


@check(1000, manual=True)
def flicker_probe():
    """Ручной шаг: облёт по кругу с 450 м у Перми, на каждом кадре -
    разброс яркости нижней половины кадра (у «плоского» кадра без
    снимка он мал) и что рисовал кадр. PLANETX_FLICKER_FRAMES -
    количество кадров."""
    import numpy as np
    from qgis.PyQt.QtTest import QTest
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    window.set_body("earth")
    count = int(os.environ.get("PLANETX_FLICKER_FRAMES", "200"))
    start = Pose(57.9940, 56.0170, 450.0, 130.0, 72.0)
    view.navigator.stop()
    view.navigator.show(start)
    view.update()
    since = time.monotonic()
    while time.monotonic() - since < 30.0 and (
            view.load_missing or time.monotonic() - since < 8.0):
        QTest.qWait(200)
    seen = {}
    original = view._tile_fades

    def fades(draw):
        out = original(draw)
        seen["tiles"] = len(draw)
        seen["fade_max"] = max(out) if out else 0.0
        seen["fading"] = sum(1 for v in out if v > 0.0)
        return out
    view._tile_fades = fades
    forgot = {"n": 0}
    forget = view._forget

    lost = []

    def counted(key):
        forgot["n"] += 1
        if key[0] <= 8:
            import traceback as _tb
            frame = _tb.extract_stack(limit=3)[0]
            sel = view.selection
            lost.append((key, "%s:%d" % (frame.name, frame.lineno),
                         bool(sel and key in sel.keep)))
        return forget(key)
    view._forget = counted
    rows = []
    try:
        for k in range(count):
            view.navigator.show(Pose(start.lat, start.lon, start.distance,
                                     (start.heading + 360.0 * k / count)
                                     % 360.0, start.tilt))
            view.update()
            QTest.qWait(30)
            waited = time.monotonic()
            while view.load_missing and time.monotonic() - waited < 3.0:
                QTest.qWait(50)
            image = view.grabFramebuffer()
            bits = image.constBits()
            bits.setsize(image.sizeInBytes())
            pixels = np.frombuffer(bits, np.uint8).reshape(
                image.height(), image.width(), 4)
            low = pixels[pixels.shape[0] // 2::8, ::8, :3].astype(
                np.float32)
            sel = view.selection
            levels = {}
            for key in (sel.draw if sel else ()):
                levels[key[0]] = levels.get(key[0], 0) + 1
            rows.append({"k": k, "lost": [str(x) for x in lost[-12:]],
                         "std": round(float(low.std()), 1),
                         "levels": levels, "textures": len(view.textures),
                         "forgot": forgot["n"],
                         "want": len(sel.want) if sel else None,
                         "missing": view.load_missing,
                         "mean": [round(float(v), 1)
                                  for v in low.mean(axis=(0, 1))],
                         "cross": view._cross is not None,
                         "errors": dict(view.gl_errors), **dict(seen)})
            del lost[:]
            if low.std() < 30.0:
                image.save(os.path.join(TEMP, "planetx_flat_%d.png" % k))
                from planetx.core import lod as _lod
                fresh = _lod.select(view.camera, view.textures.__contains__,
                                    max_level=view.max_level,
                                    heights=view.store.range_for)
                plain = {}
                for key in fresh.draw:
                    plain[key[0]] = plain.get(key[0], 0) + 1
                rows[-1]["without_memo"] = plain
                again = view.grabFramebuffer()
                bits = again.constBits()
                bits.setsize(again.sizeInBytes())
                px = np.frombuffer(bits, np.uint8).reshape(
                    again.height(), again.width(), 4)
                rows[-1]["again_std"] = round(float(
                    px[px.shape[0] // 2::8, ::8, :3].astype(
                        np.float32).std()), 1)
                rows[-1]["memo_size"] = len(view.memo.values)
                top = min(fresh.draw)
                loader = view.loader
                kids = {}
                for kid in _lod.children(top):
                    kids[str(kid)] = {
                        "texture": kid in view.textures,
                        "pending": kid in view.pending,
                        "want": round(fresh.want[kid], 1)
                        if kid in fresh.want else None,
                        "keep": kid in fresh.keep,
                        "queued": kid in getattr(loader.queue, "waiting",
                                                 {}),
                        "active": kid in loader.queue.active,
                        "failed": kid in loader.queue.failed_at,
                        "missing": kid in loader.missing,
                        "busy": loader.busy()}
                rows[-1]["top"] = str(top)
                rows[-1]["kids"] = kids
                rows[-1]["eye"] = [round(float(v), 1)
                                   for v in view.camera.eye]
    finally:
        view._tile_fades = original
        view._forget = forget
    stds = [r["std"] for r in rows]
    result["flicker"] = {
        "frames": len(rows), "median_std": float(np.median(stds)),
        "flat": [r for r in rows if r["std"] < 30.0],
        "min_std": min(stds),
        "sample": rows[:3]}


@check(500, manual=True)
def post_caption():
    """Ручной шаг: подпись остановки тура на кадре."""
    from planetx.core.tour import Stop
    window = state["window"]
    window.set_body("earth")
    window.set_extra("air", True)
    _post_full(True)
    stops = [Stop("Березники", 59.408, 56.805, 6000.0, 20.0, 60.0),
             Stop("Соликамск", 59.648, 56.771, 6000.0, 0.0, 60.0)]
    stops[0].description = ("Верхнекамское месторождение калийных солей. "
                            "Здесь добывают сильвинит с 1934 года.")
    window.tour.bar.captions.setChecked(True)
    window.tour.bar.pause.setValue(60.0)
    window.tour.start(stops)
    state["ls_started"] = time.monotonic()


@check(1000, manual=True)
def post_caption_shot():
    window = state["window"]
    layer = window.tour.stop_caption
    spent = time.monotonic() - state["ls_started"]
    if spent < 60.0 and not (layer.isVisible() and layer.alpha >= 1.0
                             and spent > 35.0):
        return 1000
    _post_shot("caption")
    window.tour.stop()
    return None


@check(500, manual=True)
def post_fence():
    """Ручной шаг: «3D-забор» разреза из пяти пластов по дуге у
    Березников под прозрачной землёй."""
    import math as _m
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, \
        QgsVectorLayer
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.set_extra("air", True)
    _post_full(True)
    window.clear_places(confirm=False)
    lat0, lon0 = 59.45, 56.86
    fence = QgsVectorLayer(
        "MultiPolygonZ?crs=EPSG:4326&field=bed:string&field=color:string",
        "Разрез (3D-забор) объявление", "memory")
    beds = (("Q", "#e8d27a", 0.0, 60.0),
            ("P2sl", "#c98a52", 60.0, 220.0),
            ("ПКС", "#e45f5f", 220.0, 330.0),
            ("КрII", "#9a69e3", 330.0, 450.0),
            ("В", "#4f8fd8", 450.0, 650.0))
    n = 120
    points = []
    for i in range(n + 1):
        t = i / n
        lat = lat0 + 0.03 * t
        lon = lon0 + 0.03 * _m.sin(t * _m.pi * 1.2)
        ground = 150.0 + 12.0 * _m.sin(t * 7.0)
        points.append((lat, lon, ground, t))
    feats = []
    for k, (name, color, top, bottom) in enumerate(beds):
        quads = []
        for (la, lo, g, t), (lb, lob, gb, tb) in zip(points, points[1:]):
            wave_a = 40.0 * _m.sin(t * 5.0 + k) * (k > 0)
            wave_b = 40.0 * _m.sin(tb * 5.0 + k) * (k > 0)
            ta = g - top - wave_a if k else g
            tb_ = gb - top - wave_b if k else gb
            ba = g - bottom - 40.0 * _m.sin(t * 5.0 + k + 1)
            bb = gb - bottom - 40.0 * _m.sin(tb * 5.0 + k + 1)
            quads.append("(({0} {1} {2}, {3} {4} {5}, {3} {4} {6}, "
                         "{0} {1} {7}, {0} {1} {2}))".format(
                             lo, la, ta, lob, lb, tb_, bb, ba))
        feature = QgsFeature(fence.fields())
        feature.setGeometry(QgsGeometry.fromWkt(
            "MultiPolygon Z (" + ",".join(quads) + ")"))
        feature.setAttributes([name, color])
        feats.append(feature)
    fence.dataProvider().addFeatures(feats)
    QgsProject.instance().addMapLayers([fence])
    state["zlayers"] = [fence.id()]
    window.view.navigator.stop()
    window.set_relief_scale(3.0)
    window.view.navigator.show(Pose(lat0 + 0.015, lon0 + 0.012, 5200.0,
                                    100.0, 48.0))
    window.set_layer_shown(fence.id(), True)
    window.set_zlayer(fence.id(), True)
    window.subsurface.set_opacity(0.15)
    state["ls_started"] = time.monotonic()


@check(1000, manual=True)
def post_fence_shot():
    from qgis.core import QgsProject
    window = state["window"]
    spent = time.monotonic() - state["ls_started"]
    if spent < 30.0:
        return 1000
    _post_shot("fence")
    window.set_relief_scale(1.0)
    window.set_zlayer(state["zlayers"][0], False)
    QgsProject.instance().removeMapLayers(state["zlayers"])
    return None


@check(500, manual=True)
def post_geoid():
    """Ручной шаг: геоид с разрезом Земли, грани по «измятой»
    поверхности."""
    from qgis.PyQt.QtCore import QUrl
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.set_extra("air", True)
    _post_full(True)
    folder = os.environ.get("PLANETX_TERRAIN_DIR") or "C:/Dev/planetx-terrain"
    window.geoid_url = QUrl.fromLocalFile(os.path.join(
        folder, "geoid")).toString() + "/{z}/{x}/{y}.png"
    window.set_geoid_scale(10000.0)
    window.view.navigator.stop()
    window.view.navigator.show(Pose(5.0, 90.0, 17000000.0, 20.0, 25.0))
    window.set_extra("geoid", True)
    window.set_extra("cutaway", True)
    window.set_wedge_box(60.0, 120.0, 0.0, 60.0)
    state["ls_started"] = time.monotonic()


@check(1000, manual=True)
def post_geoid_shot():
    window = state["window"]
    spent = time.monotonic() - state["ls_started"]
    if spent < 25.0:
        return 1000
    _post_shot("geoid")
    window.set_extra("cutaway", False)
    window.set_extra("geoid", False)
    _post_full(False)
    return None


@check(500)
def air_toggle():
    """Строка «Атмосфера»: без неё нет ни гало, ни дымки. Средний цвет
    кадра Земли с 18 000 км с воздухом и без него, флаг вида после
    выключения и включения."""
    from planetx.core.navigation import Pose
    window = state["window"]
    view = window.view
    window.set_body("earth")
    view.navigator.stop()
    view.navigator.show(Pose(30.0, 60.0, 18000000.0, 0.0, 0.0))

    def mean(image):
        w, h = image.width(), image.height()
        sums = [0, 0, 0]
        n = 0
        for y in range(0, h, 8):
            for x in range(0, w, 8):
                c = image.pixelColor(x, y)
                sums[0] += c.red()
                sums[1] += c.green()
                sums[2] += c.blue()
                n += 1
        return [round(s / n, 1) for s in sums]

    out = result["air"] = {}
    out["on"] = mean(view.grabFramebuffer())
    window.set_extra("air", False)
    out["flag_off"] = view.atmosphere
    out["off"] = mean(view.grabFramebuffer())
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_air_off.png"))
    window.set_extra("air", True)
    out["flag_on"] = view.atmosphere
    out["gl_errors"] = dict(view.gl_errors)
    return None


@check(500)
def emag_on():
    """Магнитные аномалии над Курской магнитной аномалией: тайлы из
    локальной копии planetx-terrain (PLANETX_TERRAIN_DIR, иначе
    C:/Dev/planetx-terrain), шкала, значение под щелчком."""
    from qgis.PyQt.QtCore import QUrl
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    folder = os.environ.get("PLANETX_TERRAIN_DIR") or "C:/Dev/planetx-terrain"
    window.field_urls["emag"] = QUrl.fromLocalFile(os.path.join(
        folder, "emag")).toString() + "/{z}/{x}/{y}.png"
    window.view.navigator.stop()
    window.view.navigator.show(Pose(51.3, 37.0, 1500000.0, 0.0, 0.0))
    window.set_extra("emag", True)
    loader = window.gibs_loaders.get("emag")
    result["emag"] = {"loader": loader is not None,
                      # Панель шкал показывает себя следующим проходом
                      # цикла событий, шкала уже не скрыта.
                      "legend": not window.field_legend.isHidden()}
    if loader is not None:
        _watch_loader(loader, "emag_seen")
    state["ls_started"] = time.monotonic()


@check(1000)
def emag_check():
    window = state["window"]
    seen = state.get("emag_seen", {"loaded": 0})
    layer = window.view.gibs["emag"]
    spent = time.monotonic() - state["ls_started"]
    if spent < 40.0 and (seen["loaded"] < 6 or layer.missing
                         or spent < 10.0) and "seconds" not in \
            result["emag"]:
        return 1000
    out = result["emag"]
    if "seconds" not in out:
        out.update(dict(seen, seconds=round(spent, 1),
                        textures=len(layer.textures),
                        attribution="EMAG2" in window.attribution.text(),
                        gl_errors=dict(window.view.gl_errors)))
        window.view.grabFramebuffer().save(os.path.join(
            TEMP, "planetx_emag.png"))
        # Щелчок у Курска - значение из тайла уровня MAX_LEVEL.
        window._ask_field(51.75, 36.2)
        state["ls_started"] = time.monotonic()
        return 500
    value = window._field_value
    if value is not None and value[2] is None and not value[3] \
            and spent < 15.0:
        return 500
    out["kursk"] = value[2:] if value else None
    out["group"] = window._identify_field()[0][1][0][1] \
        if window._identify_field() else None
    window.set_extra("emag", False)
    out["off"] = "emag" not in window.gibs_loaders \
        and not window.field_legend.isVisible()
    return None


def _trench_depths(window):
    """Высоты хранилища вида поперёк Японского жёлоба по 38° с. ш.,
    143.6-144.4° в. д.: наименьшая и количество нулей."""
    import numpy as np
    lons = np.arange(143.6, 144.41, 0.05)
    lats = np.full(lons.shape, 38.0)
    h = window.view.store.heights_at(lats, lons, scaled=False)
    keys = [k for k in window.view.store.tiles if k[0] >= 11]
    return {"low": round(float(np.min(h))), "level": _store_level(
                window, 38.0, 144.0),
            "zeros": int(np.sum(np.abs(h) < 1.0)),
            "points": int(len(h)), "deep_tiles": len(keys)}


def _store_level(window, lat, lon):
    """Уровень самого подробного тайла высот вида в точке или -1."""
    from planetx.core.fields import pixel_of
    tiles = window.view.store.tiles
    for z in range(17, -1, -1):
        (x, y), _ = pixel_of(lat, lon, z)
        if (z, x, y) in tiles:
            return z
    return -1


def _sea_loaded(window, started, limit, point, level):
    """Дождались ли высот вида: в точке point тайл высот уровня level
    или глубже, чтения GEBCO кончились, или вышел срок."""
    sea = getattr(window, "sea_dem", None)
    busy = sea is not None and any(not job.done()
                                   for job in list(sea.jobs.values()))
    spent = time.monotonic() - started
    return spent > limit or (spent > 5.0 and not busy
                             and _store_level(window, *point) >= level)


@check(500)
def gebco_terrarium():
    """Глубины морей: сначала дно тайлов высот у Японского жёлоба с 60
    км (тайлы уровней 11-12), потом GEBCO 2026."""
    from qgis.core import QgsSettings
    from planetx.core import dem, sources
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.set_sea_depths(True)
    QgsSettings().setValue(sources.SEA_DEM_KEY, dem.TERRARIUM)
    window.sources_changed("terrain")
    window.view.navigator.stop()
    window.view.navigator.show(Pose(38.0, 144.0, 20000.0, 0.0, 0.0))
    window.view.update()
    result["gebco"] = {"sea_dem_off": window.sea_dem is None}
    state["ls_started"] = time.monotonic()


@check(1000)
def gebco_terrarium_wait():
    window = state["window"]
    if not _sea_loaded(window, state["ls_started"], 60.0, (38.0, 144.0),
                       12):
        return 1000
    from qgis.core import QgsSettings
    from planetx.core import dem, sources
    out = result["gebco"]
    out["terrarium"] = _trench_depths(window)
    window.view.grabFramebuffer().save(os.path.join(
        TEMP, "planetx_gebco_terrarium.png"))
    QgsSettings().setValue(sources.SEA_DEM_KEY, dem.GEBCO)
    window.sources_changed("terrain")
    out["sea_dem_on"] = window.sea_dem is not None \
        and window.sea_dem.kind == dem.GEBCO
    state["ls_started"] = time.monotonic()
    return None


@check(1000)
def gebco_wait():
    window = state["window"]
    if not _sea_loaded(window, state["ls_started"], 60.0, (38.0, 144.0),
                       12):
        return 1000
    out = result["gebco"]
    out["gebco"] = _trench_depths(window)
    out["seconds"] = round(time.monotonic() - state["ls_started"], 1)
    out["errors"] = window.sea_dem.errors
    out["last_error"] = window.sea_dem.last_error[:200]
    out["credit"] = "GEBCO" in window.attribution.text()
    out["gl_errors"] = dict(window.view.gl_errors)
    window.view.grabFramebuffer().save(os.path.join(
        TEMP, "planetx_gebco.png"))
    # Марианский жёлоб с 600 км.
    from planetx.core.navigation import Pose
    window.view.navigator.stop()
    window.view.navigator.show(Pose(11.35, 142.4, 600000.0, 0.0, 30.0))
    window.view.update()
    state["ls_started"] = time.monotonic()
    return None


@check(1000)
def gebco_check():
    import numpy as np
    window = state["window"]
    if not _sea_loaded(window, state["ls_started"], 60.0, (11.35, 142.2),
                       7):
        return 1000
    out = result["gebco"]
    out["mariana_level"] = _store_level(window, 11.35, 142.2)
    h = window.view.store.heights_at(np.array([11.33, 11.35, 11.37]),
                                     np.array([142.2, 142.2, 142.2]),
                                     scaled=False)
    out["mariana_m"] = round(float(np.min(h)))
    # Без глубин морей GEBCO не нужен, подпись уходит.
    window.set_sea_depths(False)
    out["off_entries"] = [type(e).__name__
                          for e in window._height_entries()]
    out["off_credit"] = "GEBCO" in window.attribution.text()
    window.set_sea_depths(True)
    from qgis.core import QgsSettings
    from planetx.core import sources
    QgsSettings().remove(sources.SEA_DEM_KEY)
    window.sources_changed("terrain")
    return None


@check(500)
def faults_on():
    """Активные разломы GEM над Турцией с 2500 км: загрузка файла базы,
    слой наложения, щелчок по Северо-Анатолийскому разлому, выгрузка
    в проект."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.view.navigator.stop()
    window.view.navigator.show(Pose(40.0, 33.0, 2500000.0, 0.0, 0.0))
    window.view.update()
    window.set_extra("faults", True)
    result["faults"] = {"gallery": "faults" in [
        k for k, _ in __import__("planetx.ui.nasamaps",
                                 fromlist=["LAYERS"]).LAYERS],
        "cached_file": os.path.exists(window._faults_path())}
    state["ls_started"] = time.monotonic()


@check(1000)
def faults_wait():
    window = state["window"]
    if window.fault_layer is None \
            and time.monotonic() - state["ls_started"] < 120.0:
        return 1000
    result["faults"]["load_s"] = round(
        time.monotonic() - state["ls_started"], 1)
    return None


@check(3000)
def faults_check():
    import os as _os
    from qgis.core import QgsProject
    window = state["window"]
    out = result["faults"]
    layer = window.fault_layer
    out["features"] = 0 if layer is None else layer.featureCount()
    out["in_overlay"] = layer is not None and window.overlay is not None \
        and any(la is layer for la in window.overlay.layers)
    data = window.faults_data
    # У разломов Турции (каталог EMME) названий нет.
    named = [f for f in data.faults if 39.0 < f.lats[0] < 42.0
             and 26.0 < f.lons[0] < 42.0] if data is not None else []
    out["in_turkey"] = len(named)
    if named:
        fault = named[0]
        n = len(fault.lats) // 2
        lat = (fault.lats[n - 1] + fault.lats[n]) / 2.0
        lon = (fault.lons[n - 1] + fault.lons[n]) / 2.0
        found = window._identify_faults(lat, lon, 5000.0)
        out["identify"] = [(f[0], f[1]) for _, fs in found for f in fs]
    out["legend"] = not window.fault_legend.isHidden()
    out["credit"] = "GEM" in window.attribution.text()
    out["row"] = "faults" in window.panel.active_rows
    window.view.grabFramebuffer().save(_os.path.join(TEMP,
                                                     "planetx_faults.png"))
    path = _os.path.join(TEMP, "planetx_active", "faults.gpkg")
    _os.makedirs(_os.path.dirname(path), exist_ok=True)
    if _os.path.exists(path):
        _os.remove(path)
    out["exported"] = window.active_export("faults", path)
    root = QgsProject.instance().layerTreeRoot()
    group = root.findGroup("PlanetX - слои глобуса") \
        or root.findGroup("PlanetX - globe layers")
    if group is not None:
        for node in group.findLayers():
            QgsProject.instance().removeMapLayer(node.layerId())
        root.removeChildNode(group)
    window.set_extra("faults", False)
    out["after_off"] = (window.overlay is None or not any(
        la is layer for la in window.overlay.layers)) \
        and window.fault_legend.isHidden()


@check(500)
def geology_on():
    """Геологическая карта Macrostrat над Пермью: снимает карту значений,
    тайлы с 1500 км, вблизи пустые тайлы глубже карты Европы, порода под
    щелчком, слой тайлов в проект."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.set_extra("gravity", True)
    window.set_extra("geology", True)
    out = result["geology"] = {
        "gravity_off": not window.extras.get("gravity"),
        "field_shown": window._field_shown}
    window.view.navigator.stop()
    window.view.navigator.show(Pose(58.0, 56.25, 1500000.0, 0.0, 0.0))
    loader = window.gibs_loaders.get("emag")
    out["loader"] = loader is not None
    if loader is not None:
        _watch_loader(loader, "geology_seen")
    state["ls_started"] = time.monotonic()


@check(1000)
def geology_wait():
    window = state["window"]
    seen = state.get("geology_seen", {"loaded": 0})
    layer = window.view.gibs["emag"]
    spent = time.monotonic() - state["ls_started"]
    out = result["geology"]
    if "far" not in out:
        if spent < 40.0 and (seen["loaded"] < 6 or layer.missing
                             or spent < 8.0):
            return 1000
        out["far"] = dict(seen, seconds=round(spent, 1),
                          textures=len(layer.textures),
                          credit="Macrostrat" in window.attribution.text())
        window.view.grabFramebuffer().save(os.path.join(
            TEMP, "planetx_geology_far.png"))
        # Вблизи - тайлы глубже карты Европы 1:5 000 000 пустые.
        from planetx.core.navigation import Pose
        window.view.navigator.stop()
        window.view.navigator.show(Pose(58.0, 56.25, 20000.0, 0.0, 0.0))
        window.view.update()
        state["ls_started"] = time.monotonic()
        return 1000
    # Слой рисуется по тайлам подложки, они догружаются первыми.
    if spent < 60.0 and (layer.missing or layer.pending or spent < 12.0
                         or window.view.load_missing):
        return 1000
    out["near"] = {"seconds": round(spent, 1), "empty": len(layer.empty),
                   "missing": layer.missing,
                   "textures": len(layer.textures),
                   "deepest_texture": max((k[0] for k in layer.textures),
                                          default=None),
                   "empty_near": sorted(k for k in layer.empty
                                        if k[0] >= 10)[:6],
                   "levels": sorted({k[0] for k in layer.textures}),
                   "base_level": max((k[0] for k in window.view.textures),
                                     default=None),
                   "distance_km": round(
                       window.view.navigator.pose.distance / 1000.0, 1),
                   "draw_level": max((k[0] for k in getattr(
                       window.view, "drawn_keys", ()) or ()), default=None)}
    window.view.grabFramebuffer().save(os.path.join(
        TEMP, "planetx_geology_near.png"))
    window._ask_geology(58.0, 56.25)
    state["ls_started"] = time.monotonic()
    return None


@check(1000)
def geology_check():
    from qgis.core import QgsProject
    window = state["window"]
    out = result["geology"]
    value = window._geology_value
    if value is not None and value[1] is None and not value[2] \
            and time.monotonic() - state["ls_started"] < 30.0:
        return 1000
    groups = window._identify_geology()
    out["identify"] = [(f[0], f[1]) for _, fs in groups for f in fs]
    out["exported"] = window.active_export("geology")
    root = QgsProject.instance().layerTreeRoot()
    group = root.findGroup("PlanetX - слои глобуса") \
        or root.findGroup("PlanetX - globe layers")
    out["project_layer"] = None
    if group is not None:
        nodes = group.findLayers()
        out["project_layer"] = [n.layer().providerType() for n in nodes]
        for node in nodes:
            QgsProject.instance().removeMapLayer(node.layerId())
        root.removeChildNode(group)
    window.set_extra("geology", False)
    out["off"] = "emag" not in window.gibs_loaders
    out["gl_errors"] = dict(window.view.gl_errors)
    return None


@check(1000)
def section_history():
    """Исторические очаги ISC-GEM в окне «Разрез»: строка включена -
    очаги в полосе своим списком, подпись с их количеством."""
    window = state["window"]
    window.set_body("earth")
    window.set_extra("iscgem", True)
    state["sh_started"] = time.monotonic()
    result["section_history"] = {}


@check(1000)
def section_history_check():
    window = state["window"]
    out = result["section_history"]
    spent = time.monotonic() - state["sh_started"]
    if not window.history_events and spent < 120.0:
        return 1000
    if "opened" not in out:
        out["events"] = len(window.history_events or [])
        window._open_section("ISC-GEM", [(38.5, 146.0), (38.5, 132.0)])
        out["opened"] = True
        state["sh_started"] = time.monotonic()
        return 1000
    if window.crust is None and spent < 60.0:
        return 1000
    started = time.monotonic()
    built, _ = window._section(700.0, 300.0)
    out["build_s"] = round(time.monotonic() - started, 2)
    out["recent"] = len(built.quakes)
    out["history"] = len(built.history)
    out["deepest"] = max((q[1] for q in built.history), default=None)
    if "stats" not in out:
        window.section_dialog.refresh()
        out["stats"] = window.section_dialog.stats.text()
        window.section_dialog.grab().save(os.path.join(
            TEMP, "planetx_section_history.png"))
        # Шкала на 1950-1980 годы: окно пересобирается само после паузы.
        import calendar
        lo = calendar.timegm((1950, 1, 1, 0, 0, 0))
        hi = calendar.timegm((1980, 1, 1, 0, 0, 0))
        window._time_changed(float(lo), float(hi))
        state["sh_started"] = time.monotonic()
        return 1500
    out["stats_1950_1980"] = window.section_dialog.stats.text()
    built, _ = window._section(700.0, 300.0)
    out["history_1950_1980"] = len(built.history)
    import datetime
    epoch = datetime.datetime(1970, 1, 1)
    years = sorted({(epoch + datetime.timedelta(seconds=q[3].time)).year
                    for q in built.history if q[3].time is not None})
    out["years"] = [years[0], years[-1]] if years else []
    window.section_dialog.grab().save(os.path.join(
        TEMP, "planetx_section_history_time.png"))
    window._time_range = None
    window.set_extra("iscgem", False)
    window.section_dialog.refresh()
    out["stats_off"] = window.section_dialog.stats.text()
    window.section_dialog.close()
    return None


@check(1000)
def copy_view():
    """Кнопка «Копия вида в буфер обмена»: кадр глобуса со шкалами
    и подписями, без панели значков, органов навигации и шкалы
    времени."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.set_extra("quakes", True)
    window.view.navigator.stop()
    window.view.navigator.show(Pose(36.0, 140.0, 4000000.0, 0.0, 0.0))
    window.view.update()
    state["cv_started"] = time.monotonic()
    result["copy_view"] = {}


@check(1000)
def copy_view_check():
    from qgis.PyQt.QtWidgets import QApplication
    from planetx.ui.commands import build as commands_build
    window = state["window"]
    out = result["copy_view"]
    if not window.view.quakes.events \
            and time.monotonic() - state["cv_started"] < 60.0:
        return 1000
    if not window.timebar.shown():
        window.toolbar.time.setChecked(True)
        return 1000
    QApplication.processEvents()
    copied = window.copy_view()
    clip = QApplication.clipboard().image()
    frame = window.view.grabFramebuffer()
    ratio = window.view.devicePixelRatioF()

    def differs(widget):
        """Доля пикселей области виджета, где копия отличается от
        голого кадра, - нарисован ли виджет в копии."""
        if widget is None or not widget.isVisible():
            return None
        g = widget.geometry()
        x0, y0 = int(g.x() * ratio), int(g.y() * ratio)
        x1 = min(int((g.x() + g.width()) * ratio), frame.width())
        y1 = min(int((g.y() + g.height()) * ratio), frame.height())
        same = total = 0
        for y in range(y0, y1, 3):
            for x in range(x0, x1, 3):
                total += 1
                same += copied.pixel(x, y) == frame.pixel(x, y)
        return round(1.0 - same / max(total, 1), 3)
    out.update(size=[copied.width(), copied.height()],
               frame=[frame.width(), frame.height()],
               clipboard=[clip.width(), clip.height()],
               toolbar=differs(window.toolbar),
               navpad=differs(window.navpad),
               timebar=differs(window.timebar),
               legend=differs(window.legend_panel),
               attribution=differs(window.attribution),
               action="tool:copy_view" in commands_build(window)[1],
               message=window.message[0] if window.message else "")
    copied.save(os.path.join(TEMP, "planetx_copy_view.png"))
    window.toolbar.time.setChecked(False)
    window.set_extra("quakes", False)
    return None


@check(1000)
def wayback_on():
    """Архив снимков Esri Wayback над центром Перми: список выпусков,
    цепочка изменений в середине вида, шаг шкалы назад, шторка, дата
    съёмки под щелчком, слой XYZ в проект."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.view.navigator.stop()
    window.view.navigator.show(Pose(58.0105, 56.2294, 3000.0, 0.0, 0.0))
    window.view.update()
    window.set_theme("wayback")
    state["wb_started"] = time.monotonic()
    state.pop("wb_stage", None)
    result["wayback"] = {}


@check(1000)
def wayback_wait():
    from planetx.core import themes
    window = state["window"]
    view = window.view
    out = result["wayback"]
    spent = time.monotonic() - state["wb_started"]
    timer = getattr(window, "_wayback_timer", None)
    busy = "wayback" not in window._theme_domains \
        or getattr(window, "_wayback_tile", None) is None \
        or getattr(window, "_wayback_reply", None) is not None \
        or (timer is not None and timer.isActive())
    layer = view.gibs["theme"]
    if spent < 90.0 and (busy or layer.missing or layer.pending
                         or not layer.textures):
        return 1000
    stage = state.get("wb_stage")
    changes = window.wayback_changes()
    if stage is None:
        out.update(seconds=round(spent, 1),
                   releases=len(getattr(window, "_wayback_releases", [])),
                   changes=len(changes), first=changes[:1],
                   last=changes[-1:], theme_day=window.theme_day,
                   tile=list(window._wayback_tile or ()),
                   textures=len(layer.textures),
                   credit="Wayback" in window.attribution.text(),
                   url=themes.BY_KEY["wayback"].url(window.theme_day)[-40:])
        view.grabFramebuffer().save(os.path.join(TEMP,
                                                 "planetx_wayback.png"))
        # Шаг шкалы назад - предыдущий выпуск с изменениями.
        moment = window._theme_step(themes.moment(window.theme_day), -1)
        out["step_back"] = moment is not None
        if moment is not None:
            window.timebar.set_range(window.timebar.range()[0], moment)
            window._time_range = window.timebar.range()
            window._apply_theme()
        out["stepped_day"] = window.theme_day
        window.set_compare(True)
        state["wb_stage"] = "compare"
        state["wb_started"] = time.monotonic()
        return 1000
    compare = view.gibs["compare"]
    if spent < 60.0 and (not compare.textures or compare.missing
                         or compare.pending):
        return 1000
    out["compare"] = dict(shown=window._compare_shown, swipe=view.swipe,
                          textures=len(compare.textures))
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_wayback_swipe.png"))
    window.set_compare(False)
    window._ask_wayback(58.0105, 56.2294)
    state["wb_started"] = time.monotonic()
    return None


@check(1000)
def wayback_check():
    from qgis.core import QgsProject
    window = state["window"]
    out = result["wayback"]
    meta = getattr(window, "_wayback_meta", None)
    if meta is not None and meta[2] is None and not meta[3] \
            and time.monotonic() - state["wb_started"] < 30.0:
        return 1000
    groups = window._identify_wayback()
    out["identify"] = [(f[0], f[1]) for _, fs in groups for f in fs]
    out["exported"] = window.active_export("map")
    root = QgsProject.instance().layerTreeRoot()
    group = root.findGroup("PlanetX - слои глобуса") \
        or root.findGroup("PlanetX - globe layers")
    out["project_layer"] = None
    if group is not None:
        nodes = group.findLayers()
        out["project_layer"] = [(n.layer().name(), n.layer().providerType())
                                for n in nodes]
        for node in nodes:
            QgsProject.instance().removeMapLayer(node.layerId())
        root.removeChildNode(group)
    window.set_theme("")
    out["off"] = dict(loader="theme" in window.gibs_loaders,
                      reply=getattr(window, "_wayback_reply", None) is None,
                      compare="compare" in window.gibs_loaders)
    out["gl_errors"] = dict(window.view.gl_errors)
    return None


@check(500, manual=True)
def wayback_frames():
    """Ручной шаг: кадры Wayback над Пермью во время загрузки, шага
    выпуска и шторки - поиск полос на снимке автора 18 октября 2026
    года."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.set_extra("vector", True) if "vector" in window.extras else None
    window.view.navigator.stop()
    window.view.navigator.show(Pose(58.01, 56.25, 19000.0, 0.0, 0.0))
    window.view.update()
    window.set_theme("wayback")
    state["wbf"] = {"t0": time.monotonic(), "n": 0, "stage": 0}
    result["wayback_frames"] = []


@check(300, manual=True)
def wayback_frames_wait():
    from planetx.core import themes
    window = state["window"]
    view = window.view
    st = state["wbf"]
    spent = time.monotonic() - st["t0"]
    layer = view.gibs["theme"]
    name = "planetx_wbf_{:02d}.png".format(st["n"])
    view.grabFramebuffer().save(os.path.join(TEMP, name))
    result["wayback_frames"].append(dict(
        name=name, t=round(spent, 1), stage=st["stage"],
        day=window.theme_day, tex=len(layer.textures),
        missing=layer.missing, cross=view._cross is not None,
        appear=layer.appear.busy() if hasattr(layer, "appear") else None))
    st["n"] += 1
    if st["stage"] == 0 and spent > 12.0:
        moment = window._theme_step(themes.moment(window.theme_day), -1)
        if moment is not None:
            window.timebar.set_range(window.timebar.range()[0], moment)
            window._time_range = window.timebar.range()
            window._apply_theme()
        st.update(stage=1, t0=time.monotonic())
    elif st["stage"] == 1 and spent > 6.0:
        window.set_compare(True)
        st.update(stage=2, t0=time.monotonic())
    elif st["stage"] == 2 and spent > 6.0:
        from planetx.core.navigation import Pose
        view.navigator.show(Pose(58.0, 56.27, 7000.0, 0.0, 0.0))
        view.update()
        st.update(stage=3, t0=time.monotonic())
    elif st["stage"] == 3 and spent > 6.0:
        window.set_compare(False)
        window.set_theme("")
        return None
    return 300


def _tilemap_start(window, case):
    from planetx.core.navigation import Pose
    key, lat, lon, distance = case[:4]
    window.set_extra(key, True)
    window.view.navigator.stop()
    window.view.navigator.show(Pose(lat, lon, distance, 0.0, 0.0))
    window.view.update()
    loader = window.gibs_loaders.get("emag")
    result["tilemaps"][case[6] if len(case) > 6 else key] = {
        "loader": loader is not None,
                               "shown": window._tilemap_shown}
    if loader is not None:
        _watch_loader(loader, "tilemap_seen")
    state["tm_phase"] = "tiles"
    state["ls_started"] = time.monotonic()


@check(500)
def tilemaps_on():
    """Карты картинками (core/tilemaps.py) по очереди: изменения
    и повторяемость воды JRC у Арала и Байкала, глина и pH SoilGrids у Перми,
    литология GLiM с локальной копии planetx-terrain, если она собрана.
    Тайлы, шкала, подпись, значение под щелчком, выгрузка в проект,
    снятие карты значений при включении."""
    from qgis.PyQt.QtCore import QUrl
    window = state["window"]
    window.set_body("earth")
    window.set_extra("gravity", True)
    cases = [("water_transitions", 45.0, 59.5, 900000.0, 45.3, 59.9),
             ("water_occurrence", 53.6, 108.1, 300000.0, 53.6, 108.1),
             ("soil_clay", 58.0, 56.25, 400000.0, 58.0, 56.25),
             ("soil_ph", 58.0, 56.25, 400000.0, 58.0, 56.25)]
    folder = os.environ.get("PLANETX_TERRAIN_DIR") or "C:/Dev/planetx-terrain"
    if os.path.isdir(os.path.join(folder, "glim", "7")):
        window.tilemap_urls["glim"] = QUrl.fromLocalFile(os.path.join(
            folder, "glim")).toString() + "/{z}/{x}/{y}.png"
        cases.append(("glim", 58.0, 56.25, 2000000.0, 58.0, 56.25))
    if os.path.isdir(os.path.join(folder, "worldcover", "5")):
        window.tilemap_coarse["worldcover"] = QUrl.fromLocalFile(
            os.path.join(folder, "worldcover")).toString() \
            + "/{z}/{x}/{y}.png"
    # Покрытие земель: сначала издалека (свои уровни 0-5), потом центр
    # Перми вблизи (тайлы службы), щелчок по застройке у Эспланады.
    cases.append(("worldcover", 50.0, 60.0, 6000000.0, 58.0, 56.25,
                  "worldcover_far"))
    cases.append(("worldcover", 58.0, 56.25, 30000.0, 58.0103, 56.2346))
    state["tm_cases"] = cases
    result["tilemaps"] = {"cases": [c[6] if len(c) > 6 else c[0]
                                    for c in cases]}
    _tilemap_start(window, cases[0])
    result["tilemaps"]["gravity_off"] = not window.extras.get("gravity")


@check(1000)
def tilemaps_wait():
    from qgis.core import QgsProject
    window = state["window"]
    case = state["tm_cases"][0]
    key = case[0]
    out = result["tilemaps"][case[6] if len(case) > 6 else key]
    layer = window.view.gibs["emag"]
    seen = state.get("tilemap_seen", {"loaded": 0, "failed": 0})
    spent = time.monotonic() - state["ls_started"]
    if state["tm_phase"] == "tiles":
        if spent < 60.0 and (seen["loaded"] < 4 or layer.missing
                             or layer.pending or spent < 6.0):
            return 1000
        out.update(seen=dict(seen), seconds=round(spent, 1),
                   textures=len(layer.textures), empty=len(layer.empty),
                   levels=sorted({k[0] for k in layer.textures}),
                   field_legend=not window.field_legend.isHidden(),
                   class_legend=not window.class_legend.isHidden(),
                   class_rows=len(window.class_legend.rows()))
        out["credit"] = window.attribution.text()[-160:]
        window.view.grabFramebuffer().save(os.path.join(
            TEMP, "planetx_tilemap_{}.png".format(key)))
        window._ask_tilemap(case[4], case[5])
        state["tm_phase"] = "value"
        state["ls_started"] = time.monotonic()
        return 1000
    value = window._tilemap_value
    if value is not None and value[2] is None and not value[3] \
            and spent < 30.0:
        return 1000
    out["value"] = None if value is None else list(value[2:])
    groups = window._identify_tilemap()
    out["identify"] = [(f[0], f[1]) for _, fs in groups for f in fs]
    if key in ("soil_clay", "water_transitions"):
        out["exported"] = window.active_export(key)
        root = QgsProject.instance().layerTreeRoot()
        group = root.findGroup("PlanetX - слои глобуса") \
            or root.findGroup("PlanetX - globe layers")
        if group is not None:
            nodes = group.findLayers()
            out["project_layer"] = [n.layer().providerType() for n in nodes]
            for node in nodes:
                QgsProject.instance().removeMapLayer(node.layerId())
            root.removeChildNode(group)
    window.set_extra(key, False)
    out["off"] = "emag" not in window.gibs_loaders \
        and window.field_legend.isHidden() \
        and window.class_legend.isHidden()
    state["tm_cases"].pop(0)
    if state["tm_cases"]:
        _tilemap_start(window, state["tm_cases"][0])
        return 1000
    result["tilemaps"]["gl_errors"] = dict(window.view.gl_errors)
    return None


@check(500)
def iscgem_on():
    """Исторические землетрясения ISC-GEM: каталог по частям из ComCat
    или из файла профиля, точки на глобусе, шкала времени, подпись,
    опрос у сильнейшего видимого события, выгрузка в проект."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.view.navigator.stop()
    window.view.navigator.show(Pose(38.0, 142.0, 6000000.0, 0.0, 0.0))
    window.view.update()
    window.set_extra("iscgem", True)
    result["iscgem"] = {"from_file": window.history_events is not None}
    state["ls_started"] = time.monotonic()


@check(1000)
def iscgem_wait():
    import numpy as np
    window = state["window"]
    out = result["iscgem"]
    spent = time.monotonic() - state["ls_started"]
    if window.history_events is None and spent < 240.0:
        return 1000
    layer = window.view.history
    out.update(seconds=round(spent, 1),
               events=len(window.history_events or []),
               shown=len(layer.events),
               timebar=window.toolbar.time.isEnabled(),
               credit="ISC-GEM" in window.attribution.text(),
               message=str(getattr(window, "message", ("",))[0])[:80])
    if layer.events:
        eye = np.asarray(window.view.camera.eye, dtype=np.float64)
        from planetx.core import quakes
        facing = quakes.facing(eye, layer.epicenter, layer.lats, layer.lons)
        mags = np.where(facing, [q.mag for q in layer.events], -1.0)
        best = int(np.argmax(mags))
        pixels, _ = window.view.camera.project(layer.focus[best:best + 1])
        found = window._identify_quakes(pixels[0, 0], pixels[0, 1])
        out["strongest"] = [layer.events[best].place,
                            layer.events[best].mag]
        out["identify"] = [[f[0] for f in fs][:3] for _, fs in found]
        out["identify_values"] = [f[1] for _, fs in found for f in fs][:1]
        path = os.path.join(TEMP, "planetx_iscgem.gpkg")
        if os.path.exists(path):
            os.remove(path)
        out["exported"] = window.active_export("iscgem", path)
        _drop_export_group()
    window.view.grabFramebuffer().save(os.path.join(
        TEMP, "planetx_iscgem.png"))
    window.set_extra("iscgem", False)
    out["off"] = not window.view.history.events
    out["gl_errors"] = dict(window.view.gl_errors)
    return None


def _drop_export_group():
    from qgis.core import QgsProject
    root = QgsProject.instance().layerTreeRoot()
    group = root.findGroup("PlanetX - слои глобуса") \
        or root.findGroup("PlanetX - globe layers")
    if group is not None:
        for node in group.findLayers():
            QgsProject.instance().removeMapLayer(node.layerId())
        root.removeChildNode(group)


@check(500)
def style_shot():
    """Единый вид элементов поверх глобуса (ui/style.py): панель значков,
    шкала времени часов Солнца, шкала разломов, органы навигации.
    Снимок окна - planetx_style.png. Ручной шаг."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.view.navigator.stop()
    window.view.navigator.show(Pose(40.0, 33.0, 6000000.0, 0.0, 0.0))
    window.view.update()
    window.set_extra("sun", True)
    window.set_extra("faults", True)
    state["ls_started"] = time.monotonic()


@check(1000)
def style_shot_check():
    window = state["window"]
    if window.fault_layer is None \
            and time.monotonic() - state["ls_started"] < 60.0:
        return 1000
    window.navpad.hot = True
    window.navpad.update()
    window.toolbar.time.setEnabled(True)
    window.toolbar.time.setChecked(True)
    window.timebar.show()
    window.timebar._place()
    from qgis.PyQt.QtWidgets import QApplication
    QApplication.processEvents()
    window.grab().save(os.path.join(TEMP, "planetx_style.png"))
    result["style"] = {"timebar": window.timebar.shown(),
                       "legend": not window.fault_legend.isHidden()}
    window.navpad.hot = False
    window.set_extra("faults", False)
    window.set_extra("sun", False)
    return None


@check(500)
def etomesto_open():
    """Каталог «Это Место» у Перми: один запрос к сайту, список карт,
    поиск по слову, адрес страницы карты. Пункт есть в меню на глобусе."""
    from qgis.PyQt.QtWidgets import QMenu
    from planetx.ui import globemenu
    window = state["window"]
    window.set_body("earth")
    view = window.view
    before = set(window.findChildren(QMenu))
    globemenu.show(window, view.width() * view.devicePixelRatioF() / 2.0,
                   view.height() * view.devicePixelRatioF() / 2.0)
    menus = [m for m in window.findChildren(QMenu) if m not in before]
    result["etomesto"] = {"menu": [a.text() for m in menus
                                   for a in m.actions()
                                   if "Это Место" in a.text()]}
    for menu in menus:
        menu.close()
    window.etomesto_here(58.0105, 56.2502)
    state["ls_started"] = time.monotonic()


@check(1000)
def etomesto_check():
    window = state["window"]
    dialog = window.etomesto_dialog
    spent = time.monotonic() - state["ls_started"]
    if dialog.reply is not None and spent < 30.0:
        return 1000
    out = result["etomesto"]
    out["seconds"] = round(spent, 1)
    out["maps"] = len(dialog.items)
    out["first"] = dialog.items[:3]
    dialog.search.setText("перми план")
    out["found"] = dialog.list.topLevelItemCount()
    dialog.list.setCurrentItem(dialog.list.topLevelItem(0))
    out["page"] = dialog.page()
    out["status"] = dialog.status.text()
    dialog.close()
    return None


@check(1000)
def poles_on():
    """Магнитные полюса: строка включает полюса и след, шкала времени
    открывается, бегунок на 1900 год ставит полюс таблицы NOAA, окно
    «Объекты» в Москве даёт склонение IGRF-14."""
    from planetx.core import geomag, when
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.view.navigator.stop()
    window.view.navigator.show(Pose(80.0, 100.0, 9000000.0, 0.0, 0.0))
    window.set_extra("magpoles", True)
    out = {"time_shown": window.timebar.shown(),
           "shapes_now": [(s.kind, s.name, len(s.points))
                          for s in window._pole_shapes()]}
    lo = when.parse("1590-01-01")
    window.timebar.set_range(lo, when.parse("1900-07-02"))
    out["year"] = round(window.magnetic_year(), 2)
    points = [s.points[0] for s in window._pole_shapes()
              if s.kind == "point"]
    model, poles = window.geomag
    table = geomag.pole_at(poles["north"], window.magnetic_year())
    out["north_1900"] = [round(v, 3) for v in points[0]]
    out["table_1900"] = [round(v, 3) for v in table]
    out["trail_1900"] = [len(s.points) for s in window._pole_shapes()
                         if s.kind == "line"]
    # Левый бегунок обрезает начало следа - замечание пользователя от
    # 14 октября 2026 года. До правки след шёл с 1590 года.
    window.timebar.set_range(when.parse("1900-07-02"),
                             when.parse("2000-07-02"))
    lines = [s for s in window._pole_shapes() if s.kind == "line"]
    out["trail_1900_2000"] = [len(s.points) for s in lines]
    out["trail_start"] = [round(v, 3) for v in lines[0].points[0]]
    out["table_1900_start"] = [round(v, 3) for v in geomag.pole_at(
        poles["north"], geomag.year_of(when.parse("1900-07-02")))]
    window.timebar.set_range(lo, when.parse("2020-01-01"))
    window._identify_at = None
    groups = window._identify_magnetic(55.75, 37.62)
    out["moscow_2020"] = groups[0][1][0][1] if groups else None
    out["attribution"] = "IGRF" in window.attribution.text()
    window.view.grabFramebuffer().save(os.path.join(TEMP,
                                                    "planetx_poles.png"))
    window.set_extra("magpoles", False)
    out["shapes_off"] = len(window._pole_shapes())
    out["gl_errors"] = dict(window.view.gl_errors)
    result["poles"] = out


@check(500)
def demo_fetch():
    """Демо без файла в модуле: дно Бриенцского озера скачивается
    из выпуска demo-data GitHub в профиль, потом демо открывается."""
    from qgis.core import QgsApplication
    window = state["window"]
    window.set_body("earth")
    window.demo_local = False
    cache = os.path.join(QgsApplication.qgisSettingsDirPath(), "PlanetX",
                         "demo", "brienz", "brienzersee_bed.tif")
    if os.path.exists(cache):
        os.remove(cache)
    key = window.open_demo("brienz")
    result["demo_fetch"] = {"key_at_once": key,
                            "loading": bool(window._demo_replies),
                            "message": window.message[0]}
    state["demo_cache"] = cache
    state["ls_started"] = time.monotonic()


@check(1000)
def demo_fetch_check():
    from qgis.core import QgsProject
    window = state["window"]
    spent = time.monotonic() - state["ls_started"]
    if window._demo_replies and spent < 90.0:
        return 1000
    out = result["demo_fetch"]
    cache = state["demo_cache"]
    out["seconds"] = round(spent, 1)
    out["size"] = os.path.getsize(cache) if os.path.exists(cache) else None
    root = QgsProject.instance().layerTreeRoot()
    group = root.findGroup("Бриенцское озеро, своя батиметрия")
    layers = group.findLayers() if group is not None else []
    out["layer_source"] = layers[0].layer().source() if layers else None
    out["layer_valid"] = bool(layers) and layers[0].layer().isValid()
    out["message_after"] = window.message[0]
    window.demo_local = True
    return None


@check(500)
def cadastre_info():
    """Сведения об участке щелчком: «Получить сведения» в точке
    ул. Луначарского, 34 в Перми, окно «Объекты» с группой кадастра
    и подсветка контура."""
    from planetx.core.navigation import Pose
    window = state["window"]
    window.set_body("earth")
    window.set_extra("cadastre", True)
    nav = window.view.navigator
    nav.stop()
    nav.show(Pose(58.0105, 56.2502, 600.0, 0.0, 0.0))
    view = window.view
    ratio = view.devicePixelRatioF()
    window.identify_here(view.width() * ratio / 2.0,
                         view.height() * ratio / 2.0)
    result["cadastre_info"] = {
        "waiting": window._parcels is not None
        and window._parcels[1] is None}
    state["ls_started"] = time.monotonic()


@check(1000)
def cadastre_info_check():
    from qgis.PyQt.QtWidgets import QApplication
    window = state["window"]
    parcels = window._parcels
    spent = time.monotonic() - state["ls_started"]
    if parcels is not None and parcels[1] is None and not parcels[2] \
            and spent < 30.0:
        return 1000
    out = result["cadastre_info"]
    out["seconds"] = round(spent, 1)
    out["error"] = parcels[2] if parcels else "no state"
    out["numbers"] = [p["number"] for p in parcels[1] or ()] \
        if parcels else []
    out["outline_shapes"] = len(window.parcel_shapes)
    tree = window.identified.tree
    rows = {}
    take = None
    for n in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(n)
        if top.text(0) != "Кадастр Росреестра":
            continue
        for m in range(top.childCount()):
            parcel = top.child(m)
            rows[parcel.text(0)] = [(parcel.child(k).text(0),
                                     parcel.child(k).text(1))
                                    for k in range(parcel.childCount())]
            if take is None and parcel.childCount():
                take = parcel.child(0)
    out["rows"] = rows
    if take is not None:
        window.identified._take_value(take, 1)
        out["clipboard"] = QApplication.clipboard().text()
    window.view.grabFramebuffer().save(os.path.join(
        TEMP, "planetx_parcel.png"))
    window.set_extra("cadastre", False)
    out["outline_after_off"] = len(window.parcel_shapes)
    out["gl_errors"] = dict(window.view.gl_errors)
    return None


@check(500)
def modis_whole_open():
    """Поиск MODIS для шага scene_whole: первый случай MODIS_CASES."""
    from qgis.PyQt.QtCore import QDate
    mission, point, start, end, side = MODIS_CASES[0]
    dialog = state["window"].sentinel_here(*point)
    dialog.side.setValue(side)
    dialog.start.setDate(QDate(*start))
    dialog.end.setDate(QDate(*end))
    dialog.mission.setCurrentIndex(dialog.mission.findData(mission))
    if dialog.searched != mission:
        dialog.search()
    state["ls_started"] = time.monotonic()


@check(1000)
def modis_whole_wait():
    dialog = state["window"].sentinel_dialog
    busy = dialog.reply is not None or dialog.cloud_jobs \
        or dialog.sas_reply is not None or dialog.sas_waiting
    if busy and time.monotonic() - state["ls_started"] < 240.0:
        return 1000
    shown = [dialog.list.topLevelItem(n)
             for n in range(dialog.list.topLevelItemCount())
             if not dialog.list.topLevelItem(n).isHidden()]
    if shown:
        dialog.list.setCurrentItem(shown[0])
    result["modis_whole"] = {"scenes": len(dialog.scenes),
                             "first": shown[0].text(4) if shown else None}
    return None


@check(500)
def scene_whole():
    """Вся сцена, исходные файлы, у выбранной сцены окна после шагов
    *_wait любого спутника. Стоит в конце файла - шаги идут в порядке
    записи. У MSS - четыре канала, маски qa_pixel и qa_radsat,
    mtl.json и слой-набор в ложных цветах."""
    from planetx.ui import sentinel as ui
    import shutil
    dialog = state["window"].sentinel_dialog
    folder = os.path.join(TEMP, "planetx_scene_whole")
    shutil.rmtree(folder, ignore_errors=True)
    state["whole_folder"] = folder
    dialog.mode.setCurrentIndex(dialog.mode.findData("whole"))
    state["whole_group"] = ui.GROUPS[dialog.current_mission()]
    dialog.add(folder=folder)
    state["ls_build"] = time.monotonic()
    result["scene_whole"] = {"started": dialog.build_job is not None
                             or bool(dialog.sas_waiting)}


@check(1000)
def scene_whole_check():
    from qgis.core import QgsProject
    dialog = state["window"].sentinel_dialog
    spent = time.monotonic() - state["ls_build"]
    if (dialog.build_job is not None or dialog.sas_waiting) \
            and spent < 300.0:
        return 1000
    root = QgsProject.instance().layerTreeRoot()
    group = root.findGroup(state["whole_group"])
    layers = [n.layer() for n in group.findLayers()] if group else []
    files = []
    for top, _, names in os.walk(state["whole_folder"]):
        files += [(n, os.path.getsize(os.path.join(top, n))) for n in names]
    r = layers[0].renderer() if layers else None
    result["scene_whole"].update({
        "seconds": round(spent, 1),
        "status": dialog.status.text(),
        "layers": [(l.name(), l.isValid(), l.bandCount(), l.width(),
                    l.height()) for l in layers],
        "renderer": r.type() if r is not None else None,
        "bands_shown": [r.redBand(), r.greenBand(), r.blueBand()]
        if r is not None and r.type() == "multibandcolor" else None,
        "files": sorted(files)})
    if group is not None:
        QgsProject.instance().removeMapLayers(group.findLayerIds())
        QgsProject.instance().layerTreeRoot().removeChildNode(group)
    dialog.mode.setCurrentIndex(0)
    return None


@check(3000)
def crust_types_on():
    # Кора двух типов и растяжение - просьбы пользователя Ивана от
    # 15 октября 2026 года. Сектор над Атлантикой у Европы, северная
    # грань режет и океан, и материк, вид с 12 000 км.
    from planetx.core.navigation import Pose
    window = state["window"]
    nav = window.view.navigator
    nav.stop()
    window.set_cutaway_stretch(True)
    window.set_extra("cutaway", True)
    window.set_wedge_box(-40.0, 20.0, 0.0, 50.0)
    window.set_extra("quakes", True)
    nav.set_pose(Pose(30.0, -5.0, 12000000.0, 330.0, 30.0))
    result["crust_types"] = {"started": time.monotonic()}


@check(1000)
def crust_types_check():
    import numpy as np
    from planetx.core import cutaway
    window = state["window"]
    view = window.view
    out = result["crust_types"]
    if window.crust is None and not window.crust_error \
            and time.monotonic() - out["started"] < 60.0:
        return 1000
    out["crust"] = window.crust is not None
    out["vp"] = window.crust is not None and window.crust.vp is not None
    legend = window.cutaway_legend
    out["legend_oceanic"] = legend.oceanic
    out["legend_rows"] = [text for text, _ in legend.rows]
    mesh = cutaway.faces(view.wedge, crust=window.crust,
                         gain=view.wedge_gain)
    rgb = mesh.vertices["color"][:, :3]

    def has(color):
        return bool(np.any(np.all(rgb == np.array(color, np.uint8),
                                  axis=1)))
    out["faces_oceanic"] = has(cutaway.OCEAN_COLORS["crust_upper"])
    out["faces_continental"] = has(cutaway.CRUST_COLORS["crust_upper"])
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_crust_types.png"))
    # Растяжение: издалека ступень больше 1, без флажка - 1, очаги и
    # шкала следом, флажок обратно - прежняя ступень.
    out["gain_stretched"] = view.wedge_gain
    window.panel.cutaway_stretch_changed.emit(False)
    out["gain_true_scale"] = view.wedge_gain
    out["legend_gain_true_scale"] = legend.gain
    out["setting_off"] = window.cutaway_stretch()
    out["panel_off"] = window.panel.cutaway_stretch
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_crust_true_scale.png"))
    window.panel.cutaway_stretch_changed.emit(True)
    out["gain_back"] = view.wedge_gain
    out["setting_on"] = window.cutaway_stretch()
    # Модель не пришла: строка с причиной в шкале, потом снова модель.
    model = window.crust
    window.crust = None
    window._crust_done(None, "Host igppweb.ucsd.edu not found")
    out["missing_row"] = legend.rows[0][0] if legend.rows else ""
    out["missing_title_crust"] = legend.crust
    window.crust = model
    window.crust_error = ""
    legend.set_missing("")
    legend.set_crust(model is not None, model is not None
                     and model.vp is not None)
    out["missing_cleared"] = not legend.missing
    out["gl"] = dict(view.gl_errors)
    # Вблизи: экваториальная грань у берега Габона, океан переходит
    # в материк, вид из вынутого сектора на юг.
    from planetx.core.navigation import Pose
    view.navigator.set_pose(Pose(1.0, 9.0, 900000.0, 200.0, 70.0))
    return None


@check(3000)
def crust_types_close():
    window = state["window"]
    view = window.view
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_crust_close.png"))
    result["crust_types"]["close_gain"] = view.wedge_gain
    window.set_extra("quakes", False)
    window.set_extra("cutaway", False)


@check(2000)
def fields_on():
    # Возраст дна над Северной Атлантикой с локальной копии
    # planetx-terrain, потом тепловой поток снимает его.
    from qgis.PyQt.QtCore import QUrl
    from planetx.core.navigation import Pose
    window = state["window"]
    folder = os.environ.get("PLANETX_TERRAIN_DIR") or "C:/Dev/planetx-terrain"
    for key in ("seafloor_age", "heatflow"):
        window.field_urls[key] = QUrl.fromLocalFile(os.path.join(
            folder, key)).toString() + "/{z}/{x}/{y}.png"
    window.view.navigator.stop()
    window.view.navigator.show(Pose(35.0, -40.0, 6000000.0, 0.0, 0.0))
    window.set_extra("seafloor_age", True)
    result["fields"] = {"age_loader": "emag" in window.gibs_loaders,
                        "age_level": window.view.gibs["emag"].max_level}
    state["ls_started"] = time.monotonic()


@check(1000)
def fields_check():
    window = state["window"]
    out = result["fields"]
    spent = time.monotonic() - state["ls_started"]
    layer = window.view.gibs["emag"]
    if "age_textures" not in out:
        if len(layer.textures) < 6 and spent < 30.0:
            return 1000
        out["age_textures"] = len(layer.textures)
        out["age_title"] = window.field_legend.title
        out["age_credit"] = "Seton" in window.attribution.text()
        window.view.grabFramebuffer().save(os.path.join(
            TEMP, "planetx_seafloor_age.png"))
        # Щелчок у Японского жёлоба - около 133 млн лет.
        window._ask_field(38.0, 146.0)
        state["ls_started"] = time.monotonic()
        return 500
    if "age_value" not in out:
        value = window._field_value
        if value is not None and value[2] is None and not value[3] \
                and spent < 15.0:
            return 500
        out["age_value"] = value[2:] if value else None
        out["age_group"] = window._identify_field()[0][1][0][1] \
            if window._identify_field() else None
        window.set_extra("heatflow", True)
        out["age_off_by_heat"] = not window.extras.get("seafloor_age")
        out["heat_level"] = layer.max_level
        out["heat_title"] = window.field_legend.title
        state["ls_started"] = time.monotonic()
        return 1000
    if "heat_textures" not in out:
        if len(layer.textures) < 6 and spent < 30.0:
            return 1000
        out["heat_textures"] = len(layer.textures)
        window.view.grabFramebuffer().save(os.path.join(
            TEMP, "planetx_heatflow.png"))
        window._ask_field(44.6, -110.5)
        state["ls_started"] = time.monotonic()
        return 500
    value = window._field_value
    if value is not None and value[2] is None and not value[3] \
            and spent < 15.0:
        return 500
    out["yellowstone"] = value[2:] if value else None
    window.set_extra("heatflow", False)
    state["gravity_started"] = time.monotonic()


@check(1000)
def gravity_check():
    # Сила тяжести с локальной копии: шкала, тайлы, провал над
    # Марианским жёлобом.
    from qgis.PyQt.QtCore import QUrl
    from planetx.core.navigation import Pose
    window = state["window"]
    out = result.setdefault("gravity", {})
    layer = window.view.gibs["emag"]
    if "textures" not in out:
        if not window.extras.get("gravity"):
            folder = os.environ.get("PLANETX_TERRAIN_DIR") \
                or "C:/Dev/planetx-terrain"
            window.field_urls["gravity"] = QUrl.fromLocalFile(
                os.path.join(folder, "gravity")).toString() \
                + "/{z}/{x}/{y}.png"
            window.view.navigator.show(Pose(15.0, 145.0, 6000000.0, 0.0, 0.0))
            window.set_extra("gravity", True)
            state["gravity_started"] = time.monotonic()
            return 1000
        spent = time.monotonic() - state["gravity_started"]
        if len(layer.textures) < 6 and spent < 30.0:
            return 1000
        out["textures"] = len(layer.textures)
        out["level"] = layer.max_level
        out["title"] = window.field_legend.title
        out["credit"] = "XGM2019e" in window.attribution.text()
        window.view.grabFramebuffer().save(os.path.join(
            TEMP, "planetx_gravity.png"))
        window._ask_field(11.35, 142.2)
        state["gravity_started"] = time.monotonic()
        return 500
    value = window._field_value
    spent = time.monotonic() - state["gravity_started"]
    if value is not None and value[2] is None and not value[3] \
            and spent < 15.0:
        return 500
    out["mariana"] = value[2:] if value else None
    rows = window._identify_field()
    out["group"] = rows[0][0] if rows else None
    window.set_extra("gravity", False)
    out["off"] = not layer.shown
    out["off"] = "emag" not in window.gibs_loaders \
        and not window.field_legend.isVisible()
    out["gl"] = dict(window.view.gl_errors)
    return None


@check(1000)
def bouguer_check():
    # Аномалия Буге с локальной копии: шкала, подпись, отрицательная
    # под Тибетом и положительная в Тихом океане, снимает силу тяжести.
    from qgis.PyQt.QtCore import QUrl
    from planetx.core.navigation import Pose
    window = state["window"]
    out = result.setdefault("bouguer", {})
    layer = window.view.gibs["emag"]
    points = (("tibet", 32.0, 88.0), ("pacific", 20.0, -160.0))
    if "textures" not in out:
        if not window.extras.get("bouguer"):
            folder = os.environ.get("PLANETX_TERRAIN_DIR") \
                or "C:/Dev/planetx-terrain"
            window.field_urls["bouguer"] = QUrl.fromLocalFile(
                os.path.join(folder, "bouguer")).toString() \
                + "/{z}/{x}/{y}.png"
            window.set_extra("gravity", True)
            window.view.navigator.show(Pose(32.0, 88.0, 8000000.0, 0.0, 0.0))
            window.set_extra("bouguer", True)
            out["gravity_after"] = bool(window.extras.get("gravity"))
            state["bouguer_started"] = time.monotonic()
            state["bouguer_points"] = list(points)
            return 1000
        spent = time.monotonic() - state["bouguer_started"]
        if len(layer.textures) < 6 and spent < 30.0:
            return 1000
        out["textures"] = len(layer.textures)
        out["title"] = window.field_legend.title
        out["credit"] = "ETOPO" in window.attribution.text()
        window.view.grabFramebuffer().save(os.path.join(
            TEMP, "planetx_bouguer.png"))
    pending = state["bouguer_points"]
    if "asked" in state:
        value = window._field_value
        spent = time.monotonic() - state["bouguer_started"]
        if value is not None and value[2] is None and not value[3] \
                and spent < 15.0:
            return 500
        out[state.pop("asked")] = value[2:] if value else None
    if pending:
        name, lat, lon = pending.pop(0)
        window._ask_field(lat, lon)
        state["asked"] = name
        state["bouguer_started"] = time.monotonic()
        return 500
    rows = window._identify_field()
    out["row"] = rows[0][1][0][0] if rows and rows[0][1] else None
    window.set_extra("bouguer", False)
    out["off"] = "emag" not in window.gibs_loaders \
        and not window.field_legend.isVisible()
    out["gl"] = dict(window.view.gl_errors)
    return None


@check(3000)
def tomo_on():
    # Томография мантии на гранях: сектор у Японии, плита уходит в
    # мантию. Модель SEISGLOB2 скачивается с EarthScope.
    from planetx.core.navigation import Pose
    window = state["window"]
    nav = window.view.navigator
    nav.stop()
    window.set_extra("cutaway", True)
    window.set_wedge_box(140.0, 230.0, 0.0, 60.0)
    window.panel.cutaway_tomo_changed.emit(True)
    nav.set_pose(Pose(20.0, 175.0, 15000000.0, 330.0, 25.0))
    result["tomo"] = {"started": time.monotonic(),
                      "from_file": window.tomo is not None}


@check(2000)
def tomo_check():
    import numpy as np
    from planetx.core import cutaway, tomography
    window = state["window"]
    view = window.view
    out = result["tomo"]
    if window.tomo is None and (window._tomo_reply is not None
                                or window._tomo_job is not None) \
            and time.monotonic() - out["started"] < 180.0:
        return 2000
    out["seconds"] = round(time.monotonic() - out["started"], 1)
    out["loaded"] = window.tomo is not None
    out["view_tomo"] = view.wedge_tomo is not None
    out["legend_tomo"] = window.cutaway_legend.tomo
    out["legend_rows"] = [t for t, _ in window.cutaway_legend.rows][:6]
    out["credit"] = "SEISGLOB2" in window.attribution.text()
    if window.tomo is not None:
        mesh = cutaway.faces(view.wedge, crust=window.crust,
                             gain=view.wedge_gain, tomo=window.tomo)
        rgb = mesh.vertices["color"][:, :3].astype(int)
        red = np.all(rgb == np.array(tomography.STOPS[0][1]), axis=1)
        out["vertices"] = int(len(rgb))
        out["slowest"] = int(red.sum())
        out["japan_slab_500"] = round(float(tomography.sample(
            window.tomo, [37.0], [133.0], 500.0)[0]), 2)
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_tomo.png"))
    window.panel.cutaway_tomo_changed.emit(False)
    out["off"] = view.wedge_tomo is None and not window.cutaway_legend.tomo
    window.set_extra("cutaway", False)
    out["gl"] = dict(view.gl_errors)
    return None


@check(2000)
def volcanoes_on():
    # Вулканы над Камчаткой: список GVP скачивается в профиль.
    from planetx.core.navigation import Pose
    window = state["window"]
    window.view.navigator.stop()
    window.view.navigator.show(Pose(55.0, 159.0, 2500000.0, 0.0, 0.0))
    window.set_extra("volcanoes", True)
    result["volcanoes"] = {"legend": not window.volcano_legend.isHidden()}
    state["ls_started"] = time.monotonic()


@check(1000)
def volcanoes_check():
    import numpy as np
    from planetx.core.ellipsoid import geodetic_to_ecef
    window = state["window"]
    view = window.view
    out = result["volcanoes"]
    if window.volcano_data is None and window._volcano_reply is not None \
            and time.monotonic() - state["ls_started"] < 60.0:
        return 1000
    data = window.volcano_data
    out["count"] = len(data) if data is not None else 0
    out["drawn_layer"] = view.volcanoes.data is not None
    out["credit"] = "Volcanism" in window.attribution.text()
    out["message"] = window.message[0] if window.message else ""
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_volcanoes.png"))
    # Щелчок по Ключевской сопке.
    if data is not None:
        names = [data.text(n)[1] for n in range(len(data))]
        k = names.index("Klyuchevskoy") if "Klyuchevskoy" in names else 0
        h = float(data.elevation[k])
        xyz = geodetic_to_ecef(np.array([data.lat[k]]),
                               np.array([data.lon[k]]), np.array([h]))
        pixels, _ = view.camera.project(xyz)
        found = window._identify_volcanoes(*pixels[0])
        out["click"] = [(name, values[:3]) for name, values, _ in
                        found[0][1]][:2] if found else None
        out["point_under"] = window._point_under(*pixels[0])
    window.set_extra("volcanoes", False)
    out["off"] = view.volcanoes.data is None \
        and window.volcano_legend.isHidden()
    out["gl"] = dict(view.gl_errors)
    return None


@check(2000)
def platemotion_on():
    # Стрелки скоростей над Тихим океаном с 8000 км, щелчок у Гавайев.
    from planetx.core.navigation import Pose
    window = state["window"]
    window.view.navigator.stop()
    window.view.navigator.show(Pose(20.0, -160.0, 8000000.0, 0.0, 0.0))
    window.set_extra("platemotion", True)


@check(1000)
def platemotion_check():
    window = state["window"]
    view = window.view
    out = result["platemotion"] = {}
    out["shapes"] = len(window.motion_shapes)
    out["marks"] = len(window._motion_marks)
    out["credit"] = "MORVEL" in window.attribution.text()
    out["hawaii"] = window._motion_rows(19.7, -155.5)
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_platemotion.png"))
    # Сдвиг вида на шаг - стрелки заново.
    from planetx.core.navigation import Pose
    view.navigator.show(Pose(40.0, 20.0, 8000000.0, 0.0, 0.0))
    window._update_plate_arrows()
    out["moved_marks"] = len(window._motion_marks)
    window.set_extra("platemotion", False)
    out["off"] = not window.motion_shapes and not view.geo_marks
    out["gl"] = dict(view.gl_errors)


@check(2000)
def magdecl_on():
    # Линии склонения на 2020 год над Европой с 9000 км.
    from planetx.core.navigation import Pose
    from planetx.core import when
    window = state["window"]
    window.view.navigator.set_pose(Pose(50.0, 30.0, 9000000.0, 0.0, 0.0))
    window.set_extra("magdecl", True)
    window.timebar.set_range(when.parse("1590-01-01"),
                             when.parse("2020-06-01"))
    window._refresh_shapes()


@check(1000)
def magdecl_check():
    window = state["window"]
    view = window.view
    out = result["magdecl"] = {}
    out["timebar"] = window.timebar.shown()
    out["year"] = round(window.magnetic_year(), 2)
    cache = getattr(window, "_decl_cache", None)
    out["lines"] = len(cache[1]) if cache else 0
    out["levels"] = sorted({lvl for lvl, _ in cache[1]})[:5] if cache \
        else []
    out["marks"] = len(view.geo_marks)
    out["zero_label"] = any(m.name == "0°" for m in view.geo_marks)
    out["credit"] = "IGRF" in window.attribution.text()
    view.grabFramebuffer().save(os.path.join(TEMP, "planetx_magdecl.png"))
    # До 1900 года - gufm1, файл скачивается в профиль.
    from planetx.core import when
    window.timebar.set_range(when.parse("1590-01-01"),
                             when.parse("1800-06-01"))
    window._refresh_shapes()
    state["ls_started"] = time.monotonic()


@check(1000)
def magdecl_1800():
    window = state["window"]
    view = window.view
    out = result["magdecl"]
    model = window.geomag[0]
    if model.gufm is None and getattr(window, "_gufm_reply", None) \
            is not None and time.monotonic() - state["ls_started"] < 60.0:
        return 1000
    out["gufm"] = model.gufm is not None
    out["marks_1800"] = len(view.geo_marks)
    found = window._identify_magnetic(51.5, -0.12)
    out["london_1800"] = found[0][1][0][1] if found else None
    out["credit_gufm"] = "gufm1" in window.attribution.text()
    view.grabFramebuffer().save(os.path.join(TEMP,
                                             "planetx_magdecl_1800.png"))
    window.set_extra("magdecl", False)
    out["marks_off"] = len(view.geo_marks)
    out["gl"] = dict(view.gl_errors)


@check(1000)
def geo_section():
    """Геологический разрез по слоям проекта: два растра кровель
    в EPSG:4326 без пункта «Поверхность по отметкам» и «3D-забор» с Z
    у Березников, подземной модели на глобусе нет. Слои отмечаются
    флажками окна разреза, второй растр снимается, разрез пишется
    картинкой и таблицей."""
    import numpy as _np
    from osgeo import gdal as _gdal
    from qgis.core import QgsFeature, QgsGeometry, QgsProject, \
        QgsRasterLayer, QgsVectorLayer
    from qgis.PyQt.QtCore import Qt
    from planetx.qt_compat import enum
    window = state["window"]
    window.set_body("earth")
    window.subsurface.clear()
    lat0, lon0 = 59.45, 56.88
    layers = []
    for name, level in (("кровля_проба_1", 140.0), ("кровля_проба_2", 110.0)):
        path = os.path.join(TEMP, "planetx_{}.tif".format(
            "top1" if level > 120 else "top2"))
        ds = _gdal.GetDriverByName("GTiff").Create(path, 60, 60, 1,
                                                   _gdal.GDT_Float32)
        ds.SetGeoTransform((lon0 - 0.006, 0.0002, 0.0, lat0 + 0.010, 0.0,
                            -0.0002))
        ds.SetProjection('GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID['
                         '"WGS 84",6378137,298.257223563]],PRIMEM["Greenwich"'
                         ',0],UNIT["degree",0.0174532925199433],AUTHORITY['
                         '"EPSG","4326"]]')
        rows = _np.arange(60, dtype=_np.float32)[:, None]
        ds.GetRasterBand(1).WriteArray(_np.repeat(level + rows * 0.2, 60,
                                                  axis=1))
        ds = None
        layers.append(QgsRasterLayer(path, name, "gdal"))
    fence = QgsVectorLayer("MultiPolygonZ?crs=EPSG:4326&field=color:string",
                           "Забор проба", "memory")
    step = 20.0 / 111000.0
    quads = ",".join(
        "(({lo} {a} 100, {lo} {b} 100, {lo} {b} 80, {lo} {a} 80, "
        "{lo} {a} 100))".format(lo=lon0, a=lat0 + i * step,
                                b=lat0 + (i + 1) * step) for i in range(20))
    feature = QgsFeature(fence.fields())
    feature.setGeometry(QgsGeometry.fromWkt("MultiPolygon Z (" + quads
                                            + ")"))
    feature.setAttributes(["#c06030"])
    fence.dataProvider().addFeatures([feature])
    layers.append(fence)
    QgsProject.instance().addMapLayers(layers)
    state["geo_layers"] = [la.id() for la in layers]
    out = result.setdefault("geo_section", {})
    out["valid"] = [la.isValid() for la in layers]
    window._open_model_section("Проба", [(lat0, lon0), (lat0 + 0.008,
                                                       lon0)])
    dialog = window.model_section_dialog
    out["default_choice"] = [list(c) if isinstance(c, tuple) else c
                             for c in dialog.choice()]
    out["rows"] = [dialog.layers.item(n).text()
                   for n in range(dialog.layers.count())]
    checked = enum(Qt, "CheckState", "Checked")
    unchecked = enum(Qt, "CheckState", "Unchecked")
    ours = {la.id() for la in layers}
    for n in range(dialog.layers.count()):
        item = dialog.layers.item(n)
        data = item.data(enum(Qt, "ItemDataRole", "UserRole"))
        if data and data[1] in ours:
            item.setCheckState(checked)
    found = dialog.chart.section
    out["beds"] = len(found.beds) - 1 if found else None
    out["fences"] = len(found.fences) if found else None
    if found is not None:
        i = len(found.distance) // 2
        out["tops_middle"] = [round(float(top[i]), 1)
                              for _, _, top, _ in found.beds[1:]]
        out["fence_span"] = [round(float(min(f[1].min()
                                             for f in found.fences))),
                             round(float(max(f[1].max()
                                             for f in found.fences)))] \
            if found.fences else None
    out["stats"] = dialog.stats.text()
    picture = dialog.save_picture(os.path.join(TEMP,
                                               "planetx_geo_section.png"))
    table = dialog.save_table(os.path.join(TEMP, "planetx_geo_section.csv"))
    out["picture"] = bool(picture) and os.path.getsize(picture) > 1000
    if table:
        with open(table, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        out["table_rows"] = len(lines)
        out["table_head"] = lines[0]
    # Второй растр снимается флажком - кровель на одну меньше.
    for n in range(dialog.layers.count()):
        item = dialog.layers.item(n)
        data = item.data(enum(Qt, "ItemDataRole", "UserRole"))
        if data and data[1] == layers[1].id():
            item.setCheckState(unchecked)
    found = dialog.chart.section
    out["beds_after_off"] = len(found.beds) - 1 if found else None


@check(500)
def geo_section_check():
    from qgis.core import QgsProject
    window = state["window"]
    if window.model_section_dialog is not None:
        window.model_section_dialog.close()
    QgsProject.instance().removeMapLayers(state.get("geo_layers", []))

def _series_scenes(started, name, limit=240.0):
    """Ждать конца поиска и облачности окна снимков, потом открыть ряд.
    None - готово, число - пауза повтора."""
    dialog = state["window"].sentinel_dialog
    spent = time.monotonic() - state[started]
    busy = dialog.reply is not None or dialog.cloud_jobs \
        or dialog.sas_reply is not None or dialog.sas_waiting
    if dialog.cloud_jobs and dialog.series_button.isEnabled():
        # Кнопка ряда включается до конца подсчёта облачности.
        result[name]["button_early"] = True
    if busy and spent < limit:
        return 500
    out = result[name]
    out["search_seconds"] = round(spent, 1)
    out["scenes"] = len(dialog.scenes)
    out["series_scenes"] = len(dialog.series_scenes())
    out["button"] = dialog.series_button.isEnabled()
    dialog.open_series()
    state[started] = time.monotonic()
    return None


def _series_done(started, name, limit=300.0):
    """Ждать расчёта ряда и записать итог. None - готово."""
    series = state["window"].sentinel_dialog.series
    spent = time.monotonic() - state[started]
    if series is None:
        result[name]["series"] = None
        return None
    if series.jobs and spent < limit:
        return 500
    rows = series.rows()
    out = result[name]
    out["series_seconds"] = round(spent, 1)
    out["product"] = series.current_product()
    out["computed"] = len(series.values)
    out["points"] = len(rows)
    out["status"] = series.status.text()
    out["medians"] = [[when[:10], round(p.median, 3), round(p.share)]
                      for _, when, _, p in rows]
    return None


@check(500)
def series_open():
    """Ряд по датам: Sentinel-2 у Перми, участок 2 км за год до
    сегодня, NDVI. Сцены - видимые в списке окна снимков."""
    window = state["window"]
    window.set_body("earth")
    dialog = window.sentinel_here(*ROUTE_A)
    dialog.side.setValue(2.0)
    dialog.mission.setCurrentIndex(dialog.mission.findData("sentinel2"))
    dialog.search()
    state["series_started"] = time.monotonic()
    result["series"] = {}


@check(500)
def series_wait():
    return _series_scenes("series_started", "series")


@check(500)
def series_check():
    """NDVI ряда: точки есть, летняя медиана выше зимней, щелчок по
    точке выбирает сцену списка, CSV записан, смена величины считает
    заново."""
    again = _series_done("series_started", "series")
    if again:
        return again
    dialog = state["window"].sentinel_dialog
    series = dialog.series
    out = result["series"]
    if series is None:
        return None
    rows = series.rows()
    summer = [p.median for _, when, _, p in rows
              if when[5:7] in ("06", "07", "08")]
    winter = [p.median for _, when, _, p in rows
              if when[5:7] in ("11", "12", "01", "02", "03")]
    out["summer"] = round(sum(summer) / len(summer), 3) if summer else None
    out["winter"] = round(sum(winter) / len(winter), 3) if winter else None
    if rows:
        # Щелчок по самой поздней точке графика - сцена в списке.
        chart = series.chart
        chart.resize(700, 300)
        target = chart.rows[-1]
        rect = chart._plot()
        point = chart._screen(rect, chart._ranges())(target[0],
                                                    target[3].median)
        out["nearest"] = chart._nearest(point)
        chart.picked.emit(str(target[2]))
        current = dialog._scene(dialog.list.currentItem())
        out["picked"] = current is not None and current.id == target[2]
    path = os.path.join(TEMP, "planetx_series.csv")
    from planetx.core import series as core_series
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(core_series.csv_text(
            [(s.when, s.id, series.values.get(s.id))
             for s in series.scenes], series.product.currentText()))
    with open(path, encoding="utf-8") as fh:
        out["csv_lines"] = len(fh.read().splitlines())
    series.product.setCurrentIndex(series.product.findData("ndsi"))
    out["restarted"] = bool(series.jobs) or series.generation > 1
    return None


@check(500)
def series_landsat_open():
    """Ряд по датам Landsat: температура поверхности у Перми летом
    2024 года, ключ SAS Planetary Computer."""
    from qgis.PyQt.QtCore import QDate
    window = state["window"]
    dialog = window.sentinel_here(*ROUTE_A)
    if dialog.series is not None:
        dialog.series.close()
    dialog.side.setValue(2.0)
    dialog.start.setDate(QDate(2024, 5, 1))
    dialog.end.setDate(QDate(2024, 9, 30))
    dialog.mission.setCurrentIndex(dialog.mission.findData("landsat"))
    state["series_ls_started"] = time.monotonic()
    result["series_landsat"] = {}


@check(500)
def series_landsat_wait():
    again = _series_scenes("series_ls_started", "series_landsat")
    if again:
        return again
    series = state["window"].sentinel_dialog.series
    if series is not None:
        series.product.setCurrentIndex(series.product.findData("lst"))
    return None


@check(500)
def series_landsat_check():
    again = _series_done("series_ls_started", "series_landsat")
    if again:
        return again
    dialog = state["window"].sentinel_dialog
    if dialog.series is not None:
        dialog.series.close()
    dialog.close()
    return None

POINTCLOUD = os.environ.get(
    "PLANETX_POINTCLOUD",
    r"C:\Dev\pointclouds\autzen\autzen-classified.copc.laz")
POINTCLOUD_LAZ = os.environ.get(
    "PLANETX_POINTCLOUD_LAZ",
    r"C:\Dev\pointclouds\columbia_lake\SRMT_final_580000_5568000.laz")


def _pc_add(path, name, provider, distance, tilt):
    """Облако слоем проекта, отмечено на глобусе, камера над ним."""
    from qgis.core import (QgsCoordinateReferenceSystem,
                           QgsCoordinateTransform, QgsPointCloudLayer,
                           QgsProject)
    from planetx.core.navigation import Pose
    window = state["window"]
    layer = QgsPointCloudLayer(path, name, provider)
    QgsProject.instance().addMapLayer(layer)
    window.set_layer_shown(layer.id(), True)
    window._apply_vector(force=True)
    tr = QgsCoordinateTransform(layer.crs(),
                                QgsCoordinateReferenceSystem("EPSG:4326"),
                                QgsProject.instance())
    center = tr.transform(layer.extent().center())
    window.view.navigator.stop()
    window.view.navigator.show(Pose(center.y(), center.x(), distance,
                                    20.0, tilt))
    window.view.update()
    state.setdefault("pc_layers", []).append(layer.id())
    state["pc_began"] = time.monotonic()
    return layer, (round(center.y(), 5), round(center.x(), 5))


def _pc_settled(limit):
    """Ждать конца перевода и клеток облаков: None - готово."""
    window = state["window"]
    manager = window.pointclouds
    view = window.view
    view.update()
    busy = manager.processes or manager.jobs or view.pointclouds.pending
    # После перевода в COPC первая клетка просится в следующем кадре.
    busy = busy or any(e.cloud is None or not (e.ready or e.arrived)
                       or any(e.arrived.values())
                       for e in manager.entries.values())
    if busy and time.monotonic() - state["pc_began"] < limit:
        return 500
    return None


def _pc_report(name):
    window = state["window"]
    view = window.view
    manager = window.pointclouds
    out = result.setdefault("pointcloud", {}).setdefault(name, {})
    out["seconds"] = round(time.monotonic() - state["pc_began"], 1)
    out["cells"] = view.pointclouds.drawn
    out["points"] = view.pointclouds.points
    out["blocks"] = len(view.pointclouds.blocks)
    out["entries"] = {e.name: {"copc": bool(e.copc),
                               "cloud": e.cloud is not None,
                               "ready": len(e.ready), "zfactor":
                               round(e.zfactor, 4)}
                      for e in manager.entries.values()}
    out["in_overlay"] = [i for i in state.get("pc_layers", ())
                         if i in window._overlay_layers()]
    out["pending"] = view.data_pending
    out["gl"] = dict(view.gl_errors)
    return out


@check(1000)
def pointcloud_open():
    """Облако COPC (Autzen) слоем проекта точками на глобусе."""
    if not os.path.exists(POINTCLOUD):
        state["pc_began"] = time.monotonic()
        result.setdefault("pointcloud", {})["autzen"] = {"skipped": True}
        return
    layer, center = _pc_add(POINTCLOUD, "Autzen", "copc", 3000.0, 45.0)
    result.setdefault("pointcloud", {})["autzen"] = {
        "valid": layer.isValid(), "center": center,
        "program": state["window"].pointclouds.program}


@check(1000)
def pointcloud_wait():
    wait = _pc_settled(120.0)
    if wait:
        return wait
    _pc_report("autzen")


@check(1500)
def pointcloud_near():
    """Ближе - клетки делятся, точек больше."""
    from planetx.core.navigation import Pose
    window = state["window"]
    pose = window.view.navigator.pose
    window.view.navigator.show(Pose(pose.lat, pose.lon, 600.0, 40.0, 60.0))
    window.view.update()
    state["pc_began"] = time.monotonic()


@check(1000)
def pointcloud_near_wait():
    wait = _pc_settled(120.0)
    if wait:
        return wait
    out = _pc_report("autzen_near")
    state["window"].view.grabFramebuffer().save(
        os.path.join(TEMP, "planetx_pointcloud.png"))
    out["far_points"] = result["pointcloud"]["autzen"].get("points")


@check(1000)
def pointcloud_laz():
    """LAZ с дрона: перевод в COPC один раз, потом клетки."""
    if not os.path.exists(POINTCLOUD_LAZ):
        result.setdefault("pointcloud", {})["laz"] = {"skipped": True}
        return
    layer, center = _pc_add(POINTCLOUD_LAZ, "Columbia Lake", "pdal",
                            700.0, 50.0)
    result.setdefault("pointcloud", {})["laz"] = {
        "valid": layer.isValid(), "center": center}


@check(1000)
def pointcloud_laz_wait():
    if result.get("pointcloud", {}).get("laz", {}).get("skipped"):
        return
    wait = _pc_settled(240.0)
    if wait:
        return wait
    out = _pc_report("laz_done")
    state["window"].view.grabFramebuffer().save(
        os.path.join(TEMP, "planetx_pointcloud_laz.png"))
    from planetx.ui.pointcloud import cache_folder
    out["cache"] = sorted(n for n in os.listdir(cache_folder())
                          if n.endswith(".copc.laz"))


def _pc_entry(name):
    for entry in state["window"].pointclouds.entries.values():
        if entry.name == name:
            return entry
    return None


@check(1000)
def pointcloud_menu():
    """Меню слоя облака, шкала классов, смена цвета на высоты."""
    from qgis.PyQt.QtWidgets import QMenu
    window = state["window"]
    entry = _pc_entry("Columbia Lake")
    out = result.setdefault("pointcloud", {})["menu"] = {}
    if entry is None:
        out["entry"] = None
        return
    menu = QMenu()
    window.panel._cloud_menu(menu, entry.layer_id)
    out["menu"] = {a.text(): [b.text() for b in a.menu().actions()
                              if b.text()]
                   for a in menu.actions() if a.menu() is not None}
    menu.deleteLater()
    legend = window.cloud_legend
    out["legend_class"] = [legend.isVisible(), legend.title,
                           len(legend.rows())]
    out["seen"] = sorted(entry.seen)
    out["has_rgb"] = entry.has_rgb
    state["pc_fetched"] = window.pointclouds.fetched
    window.set_pointcloud_style(entry.layer_id,
                                {"mode": "height", "size": 3.0})
    window.view.update()
    state["pc_began"] = time.monotonic()


@check(1000)
def pointcloud_menu_wait():
    wait = _pc_settled(120.0)
    if wait:
        return wait
    from planetx.ui.project import read_pointclouds
    window = state["window"]
    entry = _pc_entry("Columbia Lake")
    out = result["pointcloud"]["menu"]
    legend = window.cloud_legend
    out["legend_height"] = [legend.isVisible(), legend.title,
                            [r[1] for r in legend.rows()]]
    out["stored"] = read_pointclouds().get(entry.layer_id)
    out["size"] = window.view.pointclouds.sizes.get(entry.layer_id)
    out["refetched"] = window.pointclouds.fetched - state["pc_fetched"]
    out["points_height"] = window.view.pointclouds.points
    window.view.grabFramebuffer().save(
        os.path.join(TEMP, "planetx_pointcloud_height.png"))
    window.set_pointcloud_style(entry.layer_id,
                                {"mode": "class", "size": 2.0,
                                 "classes": [2]})
    window.view.update()
    state["pc_began"] = time.monotonic()


@check(1000)
def pointcloud_ground_wait():
    wait = _pc_settled(120.0)
    if wait:
        return wait
    window = state["window"]
    view = window.view
    out = result["pointcloud"]["menu"]
    out["points_ground"] = view.pointclouds.points
    out["legend_ground"] = [r[1] for r in window.cloud_legend.rows()]
    view.grabFramebuffer().save(
        os.path.join(TEMP, "planetx_pointcloud_ground.png"))
    entry = _pc_entry("Columbia Lake")
    window.set_pointcloud_style(entry.layer_id, {"mode": "rgb"})
    view.update()
    state["pc_began"] = time.monotonic()


@check(1000)
def pointcloud_pick():
    """Точка облака под серединой кадра - опрос щелчком."""
    wait = _pc_settled(120.0)
    if wait:
        return wait
    import numpy as np
    window = state["window"]
    view = window.view
    camera = view.camera
    out = result.setdefault("pointcloud", {}).setdefault("pick", {})
    if not window.pointclouds.entries:
        out["skipped"] = True
        return
    # Пиксель одной из точек клетки в кадре, рядом с серединой.
    key = next((k for k in view.pointclouds.shown
                if k in view.pointclouds.blocks), None)
    if key is None:
        if time.monotonic() - state["pc_began"] < 60.0:
            view.update()
            return 500
        out["block"] = None
        return
    from qgis.core import (QgsDoubleRange, QgsGeometry, QgsPointXY,
                           QgsRectangle)
    from planetx.core import pointcloud as pcore
    from planetx.core.ellipsoid import ecef_to_geodetic, geodetic_to_ecef
    entry = window.pointclouds.entries[key[0]]
    block = view.pointclouds.blocks[key]
    del ecef_to_geodetic, block
    x0, y0, x1, y1 = pcore.bounds(entry.cloud, key[2])
    rows = entry.layer.dataProvider().identify(
        pcore.spacing(entry.cloud),
        QgsGeometry.fromRect(QgsRectangle(x0, y0, x1, y1)),
        QgsDoubleRange(), 50)
    if not rows:
        out["probe"] = None
        return
    row = rows[0]
    p = entry.transform.transform(QgsPointXY(float(row["X"]),
                                             float(row["Y"])))
    h = pcore.display(np.array([float(row["Z"])]), entry.cloud,
                      entry.zfactor, view.store.scale)[0]
    xyz = np.array(geodetic_to_ecef(p.y(), p.x(), float(h)))
    pixel, front = camera.project(np.asarray([xyz]))
    px, py = (float(v) for v in pixel[0])
    out["probe"] = {"z": round(float(row["Z"]), 2),
                    "class": int(row.get("Classification", 0))}
    started = time.perf_counter()
    found = window.pointclouds.identify(camera, px, py, 12.0)
    out["seconds"] = round(time.perf_counter() - started, 3)
    out["pixel"] = [round(px), round(py)]
    out["found"] = found


@check(1000)
def pointcloud_relief():
    """Смена масштаба рельефа: точки идут за рельефом без новых
    запросов к PDAL."""
    window = state["window"]
    out = result.setdefault("pointcloud", {})["relief"] = {
        "fetched_before": window.pointclouds.fetched,
        "scale_before": window.view.store.scale}
    state["pc_scale"] = window.view.store.scale
    window.view.set_relief(1.0 if window.view.store.scale != 1.0 else 2.0)
    window.view.update()
    state["pc_began"] = time.monotonic()


@check(3000)
def pointcloud_relief_check():
    import numpy as np
    from planetx.core.ellipsoid import ecef_to_geodetic
    window = state["window"]
    view = window.view
    out = result["pointcloud"]["relief"]
    out["scale_after"] = view.store.scale
    out["fetched_after"] = window.pointclouds.fetched
    out["points"] = view.pointclouds.points
    blocks = [view.pointclouds.blocks[k] for k in view.pointclouds.shown
              if k in view.pointclouds.blocks][:3]
    gaps = []
    for block in blocks:
        middle, _ = block.lifted(view.store.scale)
        lat, lon, h = (float(v) for v in ecef_to_geodetic(middle))
        gaps.append(round(h - float(view.store.height_at(lat, lon)), 1))
    out["cell_middle_minus_terrain"] = gaps
    view.set_relief(state.pop("pc_scale"))
    view.update()


@check(500)
def pointcloud_off():
    """Снятие отметки убирает точки из видеокарты."""
    from qgis.core import QgsProject
    window = state["window"]
    for layer_id in state.get("pc_layers", ()):
        window.set_layer_shown(layer_id, False)
    window._apply_vector(force=True)
    window.view.repaint()
    out = result.setdefault("pointcloud", {})["off"] = {}
    out["entries"] = len(window.pointclouds.entries)
    out["blocks"] = len(window.view.pointclouds.blocks)
    out["chooser"] = window.view.pointclouds.chooser is not None
    QgsProject.instance().removeMapLayers(state.pop("pc_layers", []))


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


# Короткий набор перед выпуском, PLANETX_STEPS=smoke, его запускает
# tools/release_check.py. Просьба автора от 17 октября 2026 года -
# вместо полного прогона на 3 часа. Цепочки шагов берутся целиком
# (включение, ожидание, проверка, выключение), шаги идут в порядке
# файла. Состав - главные части модуля, выбор помощника, утверждает
# автор. Полный прогон остаётся для больших правок движка.
SMOKE = (
    # метки, свои объекты, слои проекта, каталог
    "places_folder", "shapes_set", "shapes_check", "link_setup",
    "link_selection", "link_selection_check", "layer_opacity",
    "layer_opacity_check", "gallery_open", "gallery_wait",
    # снимок вида, тур, KML
    "shot_file", "shot_file_wait", "tour_start", "tour_wait", "kml_io",
    # панель, навигация, звёзды, тела, небо
    "accordion", "ge_nav", "navpad_plus", "stars_on", "stars_off",
    "body_mars", "body_mars_check", "body_moon_check", "body_earth_check",
    "sky_on", "sky_check",
    # глубины, землетрясения, поиск, опрос
    "seafloor_on", "seafloor_check", "seafloor_off", "quakes_on",
    "quakes_check", "search_bar", "search_bar_check", "identify_on",
    "identify_wait", "identify_check",
    # темы NASA, наложения картинок, строка действий, меню
    "themes_open", "themes_bar", "themes_off", "overlays_open",
    "overlays_add", "overlays_check", "command_bar", "side_panel",
    "globe_menu", "overlays_clean",
    # источники данных, горизонтали, разрез Земли, уклон, здания
    "sources_open", "sources_wait", "sources_check", "contours_on",
    "contours_check", "toolbar_buttons", "layer_click", "cutaway_on",
    "cutaway_wait", "cutaway_check", "cutaway_close", "cutaway_off",
    "quakes_off", "slope_on", "slope_check", "buildings_on",
    "buildings_wait", "buildings_off",
    # показ, проявление, подпись, геофизика, журнал
    "fullscreen_on", "fullscreen_check", "fullscreen_off", "tile_fade",
    "tile_fade_check", "layer_appear", "layer_appear_check",
    "crossfade_on", "crossfade_check", "snapshot_brand",
    "fields_on", "fields_check", "journal_check",
    # состояние вида метки, свободная камера и клавиши тура, карточка
    "stop_state", "stop_state_check", "stop_state_done", "tour_free",
    "tour_free_wait", "tour_keys", "place_card", "place_card_check",
    "close_without_heights",
)

# Главное - раскладка на глобусе: подложка без дыр, рельеф и дно, слои
# проекта и свои объекты, слои карт, картинки на поверхности, разрез
# Земли, здания, тела, проявление тайлов и слоёв. Предложение автора
# от 17 октября 2026 года - при проверке выделить главное, остальное
# (окна, туры, поиск, помощник, снимки спутников) проверять по
# отдельному заданию. PLANETX_STEPS=globe.
GLOBE = (
    "shapes_set", "shapes_check", "link_setup", "layer_opacity",
    "layer_opacity_check", "shot_file", "shot_file_wait", "ge_nav",
    "stars_on", "stars_off", "body_mars", "body_mars_check",
    "body_moon_check", "body_earth_check", "seafloor_on", "seafloor_check",
    "seafloor_off", "themes_open", "themes_bar", "themes_off",
    "overlays_open", "overlays_add", "overlays_check", "overlays_clean",
    "contours_on", "contours_check", "cutaway_on", "cutaway_wait",
    "cutaway_check", "cutaway_close", "cutaway_off", "slope_on",
    "slope_check", "buildings_on", "buildings_wait", "buildings_off",
    "tile_fade", "tile_fade_check", "layer_appear", "layer_appear_check",
    "crossfade_on", "crossfade_check", "fields_on", "fields_check",
    "pointcloud_open", "pointcloud_wait", "pointcloud_near",
    "pointcloud_near_wait", "pointcloud_laz", "pointcloud_laz_wait",
    "pointcloud_menu", "pointcloud_menu_wait", "pointcloud_ground_wait",
    "pointcloud_pick", "pointcloud_relief", "pointcloud_relief_check",
    "pointcloud_off",
    "close_without_heights",
)

# Выбор шагов: PLANETX_STEPS=tour_start,tour_wait, smoke или globe. Окно
# открывается всегда. Без переменной идут все шаги.
ONLY = os.environ.get("PLANETX_STEPS")
if ONLY in ("smoke", "globe"):
    _set = SMOKE if ONLY == "smoke" else GLOBE
    _names = {c[0].__name__ for c in CHECKS}
    _missing = [name for name in _set if name not in _names]
    if _missing:
        result["errors"].append(ONLY + ": нет шагов " + ", ".join(_missing))
    ONLY = ",".join(_set)
if ONLY:
    CHECKS[:] = [c for c in CHECKS if c[0].__name__ == "open_globe"
                 or c[0].__name__ in ONLY.split(",")]
else:
    CHECKS[:] = [c for c in CHECKS if c[0].__name__ not in MANUAL]
QTimer.singleShot(3000, run)
