# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Снимки ASTER для окна «Минералы по спектру»: свой поиск подходящих
сцен участка и загрузка всех каналов.

Просьба автора от 2 ноября 2026 года - путь через окно «Космоснимки»
и «Все каналы сцены» неочевиден, окну нужна своя выборка, только
подходящие снимки. Подходящий снимок - сцена ASTER L1T Planetary
Computer (2000-2006 годы) с каналами VNIR и SWIR, днём при солнце не
ниже SUN_MIN, облачностью сцены не больше CLOUD_MAX и данными не меньше
VALID_MIN процентов участка. Поиск, ключ SAS, облачность и сборка - те же
функции, что у окна «Космоснимки» (ui/sentinel.py), снимок ложится
в проект слоем «Все каналы сцены» в группу «ASTER».
"""
import json
import os
import time

from qgis.core import QgsProject, QgsRasterLayer
from qgis.PyQt.QtCore import QObject, QTimer, pyqtSignal

from ..core import aster
from ..core import sentinel as s2
from ..i18n import tr
from ..net.overlay import fetch_bytes, post_json
from .sentinel import (CLOUD_WORKERS, GROUPS, SAS_LIFE, SAS_PAUSE, SAS_TRIES,
                       build, executor, scene_cloud, style_composite, titles,
                       warm)

# Пороги подходящего снимка - выбор помощника, утверждает автор.
CLOUD_MAX = 10.0  # облачность сцены, %
SUN_MIN = 25.0  # высота солнца, градусы
VALID_MIN = 50.0  # участка с данными, %
SHOWN = 30  # снимков в списке


def suitable(scene):
    """Сцена с каналами VNIR и SWIR, днём, малой облачностью."""
    return "VNIR" in scene.assets and "SWIR" in scene.assets \
        and scene.sun is not None and scene.sun >= SUN_MIN \
        and scene.cloud is not None and scene.cloud <= CLOUD_MAX


def order(found):
    """Порядок списка [(сцена, доля данных)]: облачность, покрытие,
    новые раньше."""
    return sorted(found, key=lambda p: (round(p[0].cloud), -round(p[1]),
                                        [-ord(c) for c in p[0].when]))


def folder():
    """Папка файлов - как у окна «Космоснимки»."""
    return os.path.join(QgsProject.instance().homePath()
                        or os.path.expanduser("~"), "sentinel")


class AsterScenes(QObject):
    """Поиск подходящих сцен ASTER участка и загрузка всех каналов."""

    found = pyqtSignal(list)  # [(сцена, доля данных участка)]
    loaded = pyqtSignal(object)  # слой QgsRasterLayer
    status = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.generation = 0
        self.reply = None
        self.scenes = []
        self.jobs = []
        self.result = []
        self.load_job = None
        self.ring = None
        self.sas = ""
        self.sas_until = 0.0
        self.sas_tries = 0
        self.sas_waiting = []
        self.timer = QTimer(self)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self._poll)

    def busy(self):
        return bool(self.jobs) or self.reply is not None \
            or self.load_job is not None or bool(self.sas_waiting)

    def stop(self):
        self.generation += 1
        self.jobs = []
        self.load_job = None
        self.sas_waiting = []
        self.timer.stop()

    # --- поиск ----------------------------------------------------------

    def search(self, ring):
        self.stop()
        self.ring = list(ring)
        self.scenes = []
        self.result = []
        self.status.emit(tr("Поиск снимков ASTER участка…"))
        body = s2.search_body(s2.geojson(self.ring), aster.FIRST_DAY,
                              aster.LAST_DAY, CLOUD_MAX,
                              mission=aster.MISSION)
        self._ask(body, self.generation)

    def _ask(self, body, generation):
        self.reply = post_json(
            s2.SEARCHES[aster.MISSION],
            {"Content-Type": "application/json",
             "Accept": "application/geo+json"}, body,
            lambda data, error, g=generation: self._page(data, error, g))

    def _page(self, data, error, generation):
        self.reply = None
        if generation != self.generation:
            return
        if data is None or error:
            self.status.emit(tr("Каталог не ответил: {error}",
                                error=error or "-"))
            self.found.emit([])
            return
        scenes, following = s2.parse_page(data)
        self.scenes += [s for s in scenes if suitable(s)]
        if following and len(self.scenes) < s2.MAX_SCENES:
            self._ask(following, generation)
            return
        if not self.scenes:
            self.status.emit(tr(
                "Подходящих снимков ASTER нет: нужны сцены 2000-2006 годов "
                "с каналами SWIR, днём, облачностью до {cloud} %.",
                cloud="{:.0f}".format(CLOUD_MAX)))
            self.found.emit([])
            return
        self.status.emit(tr("Сцен {count}, проверяется покрытие участка…",
                            count=len(self.scenes)))
        self._with_token(lambda: self._start_clouds(generation))

    def _start_clouds(self, generation):
        if generation != self.generation:
            return
        warm()
        pool = executor("scenes", CLOUD_WORKERS)
        self.jobs = [(generation, s, pool.submit(scene_cloud, s, self.ring,
                                                 self.sas))
                     for s in self.scenes]
        self.timer.start()

    # --- ключ SAS -------------------------------------------------------

    def _with_token(self, action):
        if self.sas and time.monotonic() < self.sas_until:
            action()
            return
        self.sas_waiting.append(action)
        if len(self.sas_waiting) == 1:
            self.sas_tries = 0
            self._ask_token()

    def _ask_token(self):
        self.sas_tries += 1
        href = None
        for s in self.scenes:
            href = next(iter(s.assets.values())).href
            break
        fetch_bytes(s2.sas_url(aster.MISSION, href), self._token_done,
                    fresh=True)

    def _token_done(self, data, error):
        sas = ""
        if data is not None and not error:
            try:
                sas = str(json.loads(bytes(data).decode("utf-8"))
                          .get("token") or "")
            except (ValueError, UnicodeDecodeError, AttributeError):
                sas = ""
        if not sas:
            if self.sas_tries < SAS_TRIES and self.sas_waiting:
                QTimer.singleShot(SAS_PAUSE, self._ask_token)
                return
            self.sas_waiting = []
            self.status.emit(tr(
                "Служба ключей Planetary Computer не ответила: {error}. "
                "Повторите поиск позже.", error=error or "-"))
            self.found.emit([])
            return
        self.sas = sas
        self.sas_until = time.monotonic() + SAS_LIFE
        waiting, self.sas_waiting = self.sas_waiting, []
        for action in waiting:
            action()

    # --- загрузка -------------------------------------------------------

    def load(self, scene, ring):
        """Все каналы сцены по участку ring слоем проекта."""
        if self.load_job is not None:
            return
        generation = self.generation
        self.status.emit(tr("Загрузка каналов снимка {when}…",
                            when=scene.when[:10]))

        def start():
            if generation != self.generation:
                return
            warm()
            self.load_job = (generation, scene, executor(
                "scenes", CLOUD_WORKERS).submit(
                    build, scene, list(ring), ["all_bands"], folder(),
                    False, self.sas))
            self.timer.start()

        self._with_token(start)

    def _poll(self):
        pending = []
        for generation, scene, job in self.jobs:
            if not job.done():
                pending.append((generation, scene, job))
                continue
            if generation != self.generation:
                continue
            try:
                _, cloud, valid = job.result()
            except (RuntimeError, ValueError, OSError):
                cloud = None
            if cloud is not None and valid is not None \
                    and valid >= VALID_MIN:
                self.result.append((scene, valid))
        counting = bool(self.jobs)
        self.jobs = pending
        if counting and not pending:
            found = order(self.result)[:SHOWN]
            self.status.emit(tr(
                "Подходящих снимков ASTER: {count}. Выберите снимок "
                "и нажмите «Загрузить».", count=len(found)) if found
                else tr("Подходящих снимков ASTER над участком нет: "
                        "у сцен меньше {valid} % участка.",
                        valid="{:.0f}".format(VALID_MIN)))
            self.found.emit(found)
        if self.load_job is not None and self.load_job[2].done():
            generation, scene, job = self.load_job
            self.load_job = None
            if generation == self.generation:
                self._loaded(scene, job)
        if not self.jobs and self.load_job is None:
            self.timer.stop()

    def _loaded(self, scene, job):
        try:
            made = job.result()
        except (RuntimeError, ValueError, OSError) as error:
            self.status.emit(tr("Снимок не загружен: {error}",
                                error=str(error)))
            return
        layer = add_layer(scene, made[0])
        if layer is None:
            self.status.emit(tr("Снимок не открылся слоем."))
            return
        self.loaded.emit(layer)


def add_layer(scene, made):
    """Слой «Все каналы сцены» в группу дня внутри группы «ASTER»,
    показ - ложные цвета, как у окна «Космоснимки»."""
    _, path, ranges, _ = made
    layer = QgsRasterLayer(path, "{} - {}".format(
        titles(scene.mission)["all_bands"], scene.when[:10]), "gdal")
    if not layer.isValid():
        return None
    keys = s2.all_keys(scene)
    shown = [keys.index(k) for k in s2.ALL_SHOWN[scene.mission]]
    style_composite(layer, [ranges[i] for i in shown],
                    bands=tuple(i + 1 for i in shown))
    metadata = layer.metadata()
    metadata.setRights([s2.credit(scene)])
    layer.setMetadata(metadata)
    project = QgsProject.instance()
    root = project.layerTreeRoot()
    group = GROUPS[scene.mission]
    top = root.findGroup(group) or root.insertGroup(0, group)
    name = "{} {}".format(scene.when[:10], scene.tile)
    day = top.findGroup(name) or top.insertGroup(0, name)
    project.addMapLayer(layer, False)
    day.addLayer(layer)
    return layer
