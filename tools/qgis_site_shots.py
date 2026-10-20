# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Снимки для страниц сайта в отдельном QGIS. Запускается при старте QGIS.

    qgis.bat --profiles-path %TEMP%\\planetx_shots --code
        tools\\qgis_site_shots.py

Просьба автора от 17 октября 2026 года - страницы сайта содержательные,
с графиками и снимками: профили с водой, разрезы, карты данных на
глобусе, окна снимков. Сюжеты - список JOBS: вид или демо, включённые
строки, ожидание загрузки не дольше своего срока, снимок кадра глобуса
или окна. Картинки ложатся в site/shots, итог - в
%TEMP%\\planetx_site_shots.json. QGIS пользователя не трогается, в конце
QGIS закрывается. PLANETX_SHOTS - имена сюжетов через запятую, без неё
снимаются все.
"""
import faulthandler
import json
import os
import sys
import time

ROOT = r"C:\Dev\planetx"
sys.path.insert(0, ROOT)
TEMP = os.environ.get("TEMP", ".")
OUT_DIR = os.path.join(ROOT, "site", "shots")
CRASH = open(os.path.join(TEMP, "planetx_site_shots_crash.txt"), "w",
             encoding="utf-8")
faulthandler.enable(CRASH, all_threads=True)

from qgis.core import QgsApplication, QgsProject  # noqa: E402
from qgis.PyQt.QtCore import QTimer  # noqa: E402
from qgis.utils import iface  # noqa: E402

WIDTH = 1400  # ширина снимка кадра, пикселей
QUALITY = 78  # качество JPEG
ONLY = [n for n in os.environ.get("PLANETX_SHOTS", "").split(",") if n]
result = {"files": [], "errors": [], "jobs": {}}
state = {}


def save(image, name):
    """Картинка в site/shots: кадр - JPEG шириной WIDTH, окно - PNG."""
    from qgis.PyQt.QtCore import Qt
    path = os.path.join(OUT_DIR, name)
    if name.endswith(".jpg"):
        if image.width() > WIDTH:
            image = image.scaledToWidth(WIDTH, getattr(getattr(
                Qt, "TransformationMode", Qt), "SmoothTransformation"))
        image.save(path, "JPG", QUALITY)
    else:
        image.save(path, "PNG")
    result["files"].append([name, image.width(), image.height()])


def window():
    return state["window"]


def pose(lat, lon, distance, heading=0.0, tilt=0.0):
    from planetx.core.navigation import Pose
    nav = window().view.navigator
    nav.stop()
    nav.show(Pose(lat, lon, distance, heading, tilt))
    window().view.update()


def frame(name):
    view = window().view
    view.repaint()
    QgsApplication.processEvents()
    save(view.grabFramebuffer().copy(), name)


def grab(widget, name):
    QgsApplication.processEvents()
    save(widget.grab().toImage(), name)


def tiles_ready():
    view = window().view
    view._heartbeat()
    return not view.load_missing and view.navigator.flight is None


def demo(text):
    """Демо из меню значка «Демо» по началу названия."""
    w = window()
    action = next(a for a in w.toolbar.demo_list
                  if a.text().startswith(text))
    action.trigger()


def extras(keys, on):
    for key in keys:
        if bool(window().extras.get(key)) != on:
            window().set_extra(key, on)


# Сюжет: имя, подготовка, готовность, срок ожидания, снимок, уборка.
class Job:
    def __init__(self, name, setup, shoot, ready=tiles_ready, limit=60.0,
                 settle=1.5, clean=None):
        self.name, self.setup, self.shoot = name, setup, shoot
        self.ready, self.limit, self.settle = ready, limit, settle
        self.clean = clean


def map_job(name, keys, view, limit=60.0, settle=2.0):
    """Строки «Слоёв» keys над видом view - снимок кадра."""
    def setup():
        pose(*view)
        extras(keys, True)

    def clean():
        extras(keys, False)
    return Job(name, setup, lambda: frame(name + ".jpg"), limit=limit,
               settle=settle, clean=clean)


def satellites_setup():
    """Спутники навигации, геостационарные и станции - кольца орбит
    видны с 25 000 км."""
    pose(30.0, 40.0, 2.5e7)
    extras(("satellites",), True)
    window().satellite_manager.set_groups(
        {"stations", "gnss", "geo", "weather"})


def models_ready():
    """После перелёта демо камера встаёт вблизи церкви Покрова в Перми,
    с 300 м модель на кадре мелкая."""
    w = window()
    if w.view.navigator.flight is not None:
        return False
    if not state.get("models_close"):
        state["models_close"] = True
        pose(57.9446, 56.2430, 140.0, 35.0, 68.0)
        return False
    return tiles_ready()


def theme_job(name, key, view, limit=60.0):
    """Карта витрины key (тема NASA или поле GFS) - снимок кадра."""
    def setup():
        pose(*view)
        window().set_theme(key)

    def ready():
        w = window()
        return tiles_ready() and w._theme_ready()

    def clean():
        window().set_theme("")
    return Job(name, setup, lambda: frame(name + ".jpg"), ready, limit,
               settle=4.0, clean=clean)


# Разрез Земли и окно «Разрез» вдоль пути у Японского жёлоба.
def japan_setup():
    w = window()
    w.set_sea_depths(True)
    w.view.navigator.stop()
    state["japan"] = w.open_demo("japan")


def japan_ready():
    import numpy as np
    w = window()
    dialog = w.section_dialog
    s = dialog.chart.section if dialog is not None else None
    return (w.crust is not None and w.quake_events and s is not None
            and np.isfinite(s.slab_top).any() and tiles_ready())


def japan_shoot():
    frame("cutaway_japan.jpg")
    grab(window().section_dialog, "section_japan.png")


def japan_clean():
    w = window()
    if w.section_dialog is not None:
        w.section_dialog.close()
    if state.get("japan"):
        w.myplaces.remove(state["japan"])
    extras(("cutaway", "quakes"), False)


# Подземный режим и окно «Разрез модели», демо «Пермские отложения».
def subsurface_ready():
    return window().subsurface.job is None and tiles_ready()


def subsurface_shoot():
    w = window()
    frame("subsurface.jpg")
    model = w.subsurface.model
    south, north, west, east = model.box()
    lat = model.holes[0][1]
    w._open_model_section("Пермские отложения", [(lat, west), (lat, east)])
    dialog = w.model_section_dialog
    dialog.resize(1200, 520)
    grab(dialog, "model_section.png")
    dialog.close()


# Гриды пластов проекта автора B2 под землёй и разрез модели по ним.
# Проект только читается, проверочный QGIS его не записывает.
B2 = r"C:\Users\ValH\Dropbox\ИИ\Isoliner\other\Slice\B2.qgz"


def b2_setup():
    from qgis.core import QgsProjectBadLayerHandler, QgsRasterLayer
    # Окно «Недостающие слои» остановило бы съёмку, недостающий слой
    # пропускается - гриды пластов на месте.
    state["bad_layers"] = QgsProjectBadLayerHandler()
    QgsProject.instance().setBadLayerHandler(state["bad_layers"])
    QgsProject.instance().read(B2)
    w = window()
    for layer in QgsProject.instance().mapLayers().values():
        if isinstance(layer, QgsRasterLayer):
            w.set_layer_shown(layer.id(), True)
            w.set_grid(layer.id(), True)
    state["b2_pose"] = False


def b2_ready():
    w = window()
    if w.subsurface.job is not None or w.subsurface.model is None:
        return False
    if not state["b2_pose"]:
        state["b2_pose"] = True
        # Земля почти прозрачна - видны пласты и блок под ней.
        w.subsurface.set_opacity(0.15)
        south, north, west, east = w.subsurface.model.box()
        span = max(north - south, (east - west) * 0.55) * 111e3
        pose((south + north) / 2, (west + east) / 2, span * 1.6, 25.0,
             62.0)
        return False
    return tiles_ready()


def b2_shoot():
    w = window()
    frame("b2_grids.jpg")
    south, north, west, east = w.subsurface.model.box()
    lat = (south + north) / 2
    w._open_model_section("B2", [(lat, west), (lat, east)])
    dialog = w.model_section_dialog
    dialog.resize(1200, 520)
    QgsApplication.processEvents()
    grab(dialog, "b2_section.png")
    dialog.close()


def b2_close_setup():
    """Ближний вид - низкий взгляд вдоль модели с другой стороны."""
    south, north, west, east = window().subsurface.model.box()
    span = max(north - south, (east - west) * 0.55) * 111e3
    pose((south + north) / 2, (west + east) / 2, span * 0.9, 200.0, 74.0)


def b2_clean():
    QgsProject.instance().clear()


# Своя батиметрия и профиль через озеро, демо «Бриенцское озеро».
def brienz_ready():
    w = window()
    busy = w.terrain_loader is not None and w.terrain_loader.busy()
    return not busy and tiles_ready()


def brienz_shoot():
    w = window()
    frame("brienz.jpg")
    key = next(p.key for p in w.myplaces.places
               if p.name == "Профиль через озеро")
    w._place_action("profile", key)
    dialog = w.profile_dialog
    dialog.resize(1100, 520)
    dialog.refresh()
    grab(dialog, "profile_lake.png")
    dialog.close()


# Профиль через Марианский жёлоб - дно океана и уровень моря.
def trench_setup():
    from planetx.core.features import Shape
    w = window()
    w.set_sea_depths(True)
    pose(11.35, 142.4, 900000.0, 0.0, 35.0)
    key = w.myplaces.add(Shape("line", [(10.4, 142.5), (12.4, 142.5)],
                               name="Через Марианский жёлоб",
                               color=(255, 214, 0, 255), width=3.0))
    state["trench"] = key
    w._place_action("profile", key)
    state["trench_started"] = time.monotonic()


def trench_ready():
    return time.monotonic() - state["trench_started"] > 20.0 \
        and tiles_ready()


def trench_shoot():
    w = window()
    frame("trench.jpg")
    dialog = w.profile_dialog
    dialog.resize(1100, 520)
    dialog.refresh()
    grab(dialog, "profile_trench.png")
    dialog.close()


def trench_clean():
    window().myplaces.remove(state.pop("trench"))


# Горизонтали и уклон у Эльбруса.
def elbrus_setup():
    pose(43.35, 42.45, 16000.0, 25.0, 55.0)
    extras(("contours",), True)


def elbrus_shoot():
    frame("contours.jpg")
    extras(("contours",), False)
    extras(("slope",), True)
    window().view.update()
    state["slope_started"] = time.monotonic()


def slope_ready():
    return time.monotonic() - state["slope_started"] > 8.0 \
        and tiles_ready()


# Демо с наложениями, моделями и историческими картами.
def demo_job(name, text, limit=90.0, settle=4.0):
    def setup():
        demo(text)
    return Job(name, setup, lambda: frame(name + ".jpg"), limit=limit,
               settle=settle)


# Окно «Космоснимки» и ряд по датам у Перми.
def sentinel_setup():
    w = window()
    dialog = w.sentinel_here(58.0105, 56.2294)
    dialog.side.setValue(2.0)
    dialog.mission.setCurrentIndex(dialog.mission.findData("sentinel2"))
    dialog.search()


def sentinel_ready():
    dialog = window().sentinel_dialog
    return not (dialog.reply is not None or dialog.cloud_jobs
                or dialog.sas_reply is not None or dialog.sas_waiting)


def sentinel_pick():
    """Первая сцена списка - превью грузится до снимка окна."""
    dialog = window().sentinel_dialog
    dialog.resize(1100, 720)
    if dialog.list.topLevelItemCount():
        dialog.list.setCurrentItem(dialog.list.topLevelItem(0))


def sentinel_shoot():
    dialog = window().sentinel_dialog
    grab(dialog, "sentinel.png")
    dialog.open_series()


def series_ready():
    series = window().sentinel_dialog.series
    return series is None or not series.jobs


def series_shoot():
    dialog = window().sentinel_dialog
    series = dialog.series
    if series is not None:
        series.resize(1100, 520)
        grab(series, "series.png")
        series.close()
    dialog.close()


JOBS = [
    Job("japan", japan_setup, japan_shoot, japan_ready, 120.0, 3.0,
        japan_clean),
    Job("subsurface", lambda: demo("Пермские отложения"), subsurface_shoot,
        subsurface_ready, 90.0, 3.0),
    Job("b2", b2_setup, b2_shoot, b2_ready, 180.0, 4.0),
    Job("b2_close", b2_close_setup, lambda: frame("b2_close.jpg"),
        limit=90.0, settle=4.0, clean=b2_clean),
    Job("brienz", lambda: demo("Бриенцское озеро"), brienz_shoot,
        brienz_ready, 90.0, 3.0),
    Job("trench", trench_setup, trench_shoot, trench_ready, 60.0, 2.0,
        trench_clean),
    Job("elbrus", elbrus_setup, elbrus_shoot, limit=60.0, settle=3.0),
    Job("slope", lambda: None, lambda: (frame("slope.jpg"),
                                        extras(("slope",), False)),
        slope_ready, 60.0, 2.0),
    map_job("geology", ("geology",), (39.5, -118.0, 7.0e5), limit=150.0,
            settle=40.0),
    map_job("glim", ("glim",), (45.0, 90.0, 9.0e6)),
    map_job("gravity", ("gravity",), (32.0, 85.0, 6.0e6)),
    map_job("emag", ("emag",), (52.0, 38.0, 3.0e6)),
    map_job("seafloor_age", ("seafloor_age",), (15.0, -35.0, 1.3e7)),
    map_job("heatflow", ("heatflow",), (30.0, -100.0, 1.3e7)),
    map_job("iscgem", ("iscgem",), (10.0, 150.0, 1.4e7), limit=120.0),
    map_job("plates", ("plates", "volcanoes", "platemotion"),
            (20.0, 160.0, 1.3e7), limit=90.0),
    map_job("faults", ("faults",), (39.0, 35.0, 1.2e6), limit=90.0,
            settle=6.0),
    map_job("deposits", ("deposits",), (40.0, -117.0, 9.0e5),
            limit=120.0),
    map_job("plants", ("plants",), (50.0, 10.0, 3.5e6), limit=90.0),
    map_job("worldcover", ("worldcover",), (57.5, 55.0, 6.0e5)),
    map_job("water", ("water_transitions",), (45.0, 60.0, 7.0e5)),
    map_job("soil", ("soil_ph",), (52.0, 30.0, 4.0e6)),
    Job("satellites", satellites_setup, lambda: frame("satellites.jpg"),
        limit=90.0, settle=25.0,
        clean=lambda: extras(("satellites",), False)),
    theme_job("wind", "weather_wind", (35.0, -40.0, 1.2e7)),
    theme_job("temperature_gfs", "weather_temperature",
              (45.0, 60.0, 1.2e7)),
    theme_job("sea_ice", "sea_ice", (80.0, 0.0, 1.0e7)),
    theme_job("ndvi", "ndvi", (5.0, 20.0, 1.2e7)),
    theme_job("methane", "methane", (35.0, 90.0, 1.3e7)),
    demo_job("aral", "Аральское море"),
    Job("models", lambda: demo("3D-модели"), lambda: frame("models.jpg"),
        models_ready, 150.0, 6.0),
    demo_job("moscow", "Москва"),
    Job("sentinel", sentinel_setup, sentinel_pick, sentinel_ready, 300.0,
        3.0),
    Job("sentinel_grab", lambda: None, sentinel_shoot, lambda: True, 10.0,
        10.0),
    Job("series", lambda: None, series_shoot, series_ready, 400.0, 2.0),
]


def finish():
    with open(os.path.join(TEMP, "planetx_site_shots.json"), "w",
              encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)
    if "plugin" in state:
        state["plugin"].unload()
    QgsProject.instance().clear()
    QgsApplication.instance().exit(0)


def start():
    os.makedirs(OUT_DIR, exist_ok=True)
    # Растры прежних прогонов в проекте проверочного профиля в кадр
    # не идут.
    QgsProject.instance().clear()
    from planetx import i18n
    i18n.set_language("ru")
    from planetx.plugin import PlanetXPlugin
    from planetx.ui.guide import GUIDE_KEY
    from qgis.core import QgsSettings
    QgsSettings().setValue(GUIDE_KEY, True)
    plugin = PlanetXPlugin(iface)
    plugin.initGui()
    plugin.run()
    w = plugin.window
    state["plugin"] = plugin
    state["window"] = w
    w.showNormal()
    w.resize(1600, 930)
    from planetx.net.overlay import BORDERS, PLACES
    w.set_line_groups(set(w.state()["groups"]) | {BORDERS, PLACES})
    # Строки прежних прогонов снимаются, звёзды и атмосфера остаются.
    extras([k for k, v in w.extras.items() if v
            and k not in ("stars", "air")], False)
    w.set_theme("")
    state["jobs"] = [j for j in JOBS if not ONLY or j.name in ONLY]
    QTimer.singleShot(3000, next_job)


def next_job():
    if not state["jobs"]:
        QTimer.singleShot(500, finish)
        return
    job = state["job"] = state["jobs"].pop(0)
    result["jobs"][job.name] = {}
    try:
        # Метки прежних снимков и демо в кадр не идут, демо задания
        # ставит свою папку уже после этого.
        places = window().myplaces
        places.set_visible_many({n.key: False for n in places.nodes()})
        job.setup()
    except (AttributeError, KeyError, RuntimeError, StopIteration,
            TypeError, ValueError) as error:
        result["errors"].append("%s setup: %r" % (job.name, error))
        QTimer.singleShot(500, next_job)
        return
    state["started"] = time.monotonic()
    QTimer.singleShot(3000, wait_job)


def wait_job():
    job = state["job"]
    spent = time.monotonic() - state["started"]
    try:
        ready = job.ready()
    except (AttributeError, KeyError, RuntimeError, TypeError) as error:
        result["errors"].append("%s ready: %r" % (job.name, error))
        ready = True
    if not ready and spent < job.limit:
        QTimer.singleShot(1000, wait_job)
        return
    result["jobs"][job.name] = {"seconds": round(spent, 1),
                                "ready": bool(ready)}
    QTimer.singleShot(int(job.settle * 1000), shoot_job)


def shoot_job():
    job = state["job"]
    try:
        job.shoot()
        if job.clean is not None:
            job.clean()
    except (AttributeError, IndexError, KeyError, RuntimeError,
            StopIteration, TypeError, ValueError) as error:
        result["errors"].append("%s shoot: %r" % (job.name, error))
    QTimer.singleShot(1000, next_job)


QTimer.singleShot(3000, start)
