# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Снимки Sentinel-2 для окна «Выделение объектов»: свой поиск
подходящих сцен участка и загрузка сочетания «Сельское хозяйство».

Просьба автора от 3 ноября 2026 года - «система громоздкая, упрости»:
снимок для задачи не надо искать окном «Космоснимки». Подходящая сцена -
Sentinel-2 L2A Earth Search за последние YEARS года в месяцах сезона,
облачность над участком по маске SCL не больше CLOUD_MAX, данные не
меньше VALID_MIN участка. Поиск, облачность и сборка - функции окна
«Космоснимки» (ui/sentinel.py), снимок ложится в проект слоем сочетания
в группу «Sentinel-2», как у окна снимков, с подписями каналов.
"""
import os

from qgis.core import QgsProject, QgsRasterLayer
from qgis.PyQt.QtCore import QDate, QObject, QTimer, pyqtSignal

from ..core import sentinel as s2
from ..i18n import tr
from ..net.overlay import post_json
from .sentinel import (CLOUD_WORKERS, GROUPS, build, executor, scene_cloud,
                       style_composite, titles, warm)

MISSION = "sentinel2"
PRODUCT = "agriculture"  # B11 B8 B2: хвоя, листва и почва различимы
YEARS = 3  # лет назад от сегодня
SCENE_CLOUD = 40.0  # облачность сцены в каталоге, %
CLOUD_MAX = 5.0  # облачность над участком, %
VALID_MIN = 90.0  # участка с данными, %
SUN_MIN = 20.0  # высота солнца, градусы
SHOWN = 8  # снимков в списке
SEARCH_TRIES = 3
SEARCH_PAUSE = 3000  # мс, растёт с номером повтора
# Сезоны: лето - хвоя и листва в листе, другой сезон - листва без листьев
# или жёлтая, у хвои ближний ИК прежний. Выбор помощника.
SUMMER = (6, 7, 8)
OFF_SEASON = (4, 5, 9, 10)


def folder():
    """Папка файлов - как у окна «Космоснимки»."""
    return os.path.join(QgsProject.instance().homePath()
                        or os.path.expanduser("~"), "sentinel")


def order(found):
    """[(сцена, облачность, данные)]: облачность, новые раньше."""
    return sorted(found, key=lambda p: (round(p[1]),
                                        [-ord(c) for c in p[0].when]))


class SceneFinder(QObject):
    """Поиск подходящих сцен Sentinel-2 участка и загрузка сочетания."""

    found = pyqtSignal(list)  # [(сцена, облачность над участком, данные)]
    loaded = pyqtSignal(object)  # слой QgsRasterLayer
    status = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.generation = 0
        self.reply = None
        self.tries = 0
        self.retrying = False
        self.scenes = []
        self.jobs = []
        self.result = []
        self.load_job = None
        self.ring = None
        self.months = SUMMER
        self.timer = QTimer(self)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self._poll)

    def busy(self):
        return bool(self.jobs) or self.reply is not None \
            or self.load_job is not None or self.retrying

    def stop(self):
        self.generation += 1
        self.jobs = []
        self.load_job = None
        self.retrying = False
        self.timer.stop()

    def search(self, ring, months):
        self.stop()
        self.tries = 0
        self.ring = list(ring)
        self.months = tuple(months)
        self.scenes = []
        self.result = []
        self.status.emit(tr("Поиск снимков Sentinel-2 участка…"))
        today = QDate.currentDate()
        body = s2.search_body(
            s2.geojson(self.ring),
            today.addYears(-YEARS).toString("yyyy-MM-dd"),
            today.toString("yyyy-MM-dd"), SCENE_CLOUD, mission=MISSION)
        self._ask(body, self.generation)

    def _ask(self, body, generation):
        self.reply = post_json(
            s2.SEARCHES[MISSION],
            {"Content-Type": "application/json",
             "Accept": "application/geo+json"}, body,
            lambda data, error, g=generation, b=body:
            self._page(data, error, g, b))

    def _again(self, body, generation):
        self.retrying = False
        if generation == self.generation:
            self._ask(body, generation)

    def _page(self, data, error, generation, body):
        self.reply = None
        if generation != self.generation:
            return
        if data is None or error:
            if self.tries < SEARCH_TRIES:
                self.tries += 1
                self.retrying = True
                self.status.emit(tr(
                    "Каталог занят, повтор поиска {n} из {total}…",
                    n=self.tries, total=SEARCH_TRIES))
                QTimer.singleShot(SEARCH_PAUSE * self.tries,
                                  lambda: self._again(body, generation))
                return
            self.status.emit(tr("Каталог не ответил: {error}",
                                error=error or "-"))
            self.found.emit([])
            return
        self.tries = 0
        scenes, following = s2.parse_page(data)
        self.scenes += [s for s in scenes
                        if int(s.when[5:7]) in self.months
                        and (s.sun is None or s.sun >= SUN_MIN)]
        if following and len(self.scenes) < s2.MAX_SCENES:
            self._ask(following, generation)
            return
        if not self.scenes:
            self.status.emit(tr("Сцен Sentinel-2 нужного сезона над "
                                "участком нет."))
            self.found.emit([])
            return
        self.status.emit(tr("Сцен {count}, считается облачность над "
                            "участком…", count=len(self.scenes)))
        warm()
        pool = executor("scenes", CLOUD_WORKERS)
        self.jobs = [(generation, s, pool.submit(scene_cloud, s, self.ring))
                     for s in self.scenes]
        self.timer.start()

    def load(self, scene, ring):
        """Сочетание «Сельское хозяйство» сцены по участку ring слоем."""
        if self.load_job is not None:
            return
        self.status.emit(tr("Загрузка снимка {when}…", when=scene.when[:10]))
        warm()
        self.load_job = (self.generation, scene, executor(
            "scenes", CLOUD_WORKERS).submit(
                build, scene, list(ring), [PRODUCT], folder(), False))
        self.timer.start()

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
                    and cloud <= CLOUD_MAX and valid >= VALID_MIN:
                self.result.append((scene, cloud, valid))
        counting = bool(self.jobs)
        self.jobs = pending
        if counting and not pending:
            found = order(self.result)[:SHOWN]
            self.status.emit(
                tr("Подходящих снимков: {count}. Двойной щелчок по снимку "
                   "загружает его.", count=len(found)) if found
                else tr("Подходящих снимков нет: у сцен над участком "
                        "облачность больше {cloud} % или данных меньше "
                        "{valid} %.", cloud="{:.0f}".format(CLOUD_MAX),
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
    """Слой сочетания в группу дня внутри группы «Sentinel-2», показ -
    как у окна «Космоснимки»."""
    _, path, ranges, _ = made
    layer = QgsRasterLayer(path, "{} - {}".format(
        titles(MISSION)[PRODUCT], scene.when[:10]), "gdal")
    if not layer.isValid():
        return None
    style_composite(layer, ranges)
    metadata = layer.metadata()
    metadata.setRights([s2.credit(scene)])
    layer.setMetadata(metadata)
    project = QgsProject.instance()
    root = project.layerTreeRoot()
    group = GROUPS[MISSION]
    top = root.findGroup(group) or root.insertGroup(0, group)
    name = "{} {}".format(scene.when[:10], scene.tile)
    day = top.findGroup(name) or top.insertGroup(0, name)
    project.addMapLayer(layer, False)
    day.addLayer(layer)
    return layer
