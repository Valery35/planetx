# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Строка «Спутники» окна глобуса: группы CelesTrak, загрузка, показ.

Расчёт - core/satellites.py и core/sgp4.py, отрисовка -
render/satellites.py. Правило CelesTrak - одна загрузка группы
на обновление, данные обновляются раз в 2 часа. Ответ CelesTrak
6 октября 2026 года шёл без заголовков кэширования, кэш QGIS его
не хранит. Поэтому группа хранится файлом в профиле QGIS
(PlanetX/satellites/<группа>.csv). Файл моложе REFETCH читается
без сети, и при новом включении строки, и после перезапуска QGIS.
После ответа с ошибкой группа не просится до конца того же срока,
иначе адрес попадает в блокировку CelesTrak, показывается прежний
файл, если он есть.

Начальные величины спутников считаются частями по INIT_BUDGET
за проход цикла событий. Положения на кадр считает вид через
`source`. Без открытой шкалы времени спутники идут по часам
компьютера, таймер просит кадр раз в TICK мс.
"""
import os
import time

from qgis.core import QgsApplication, QgsSettings
from qgis.PyQt.QtCore import QObject, QTimer, pyqtSignal

from ..core import satellites as core
from ..core import sgp4
from ..core.features import Shape
from ..core.navigation import lifted
from ..i18n import tr
from ..net.overlay import fetch_bytes

GROUPS_KEY = "PlanetX/satellite_groups"
FAILED_KEY = "PlanetX/satellites/failed/"  # + группа: секунды UTC
TICK = 250  # мс между кадрами по часам компьютера
FOLLOW_TICK = 50  # мс, пока камера идёт следом за спутником
PICK_PIXELS = 8  # логических пикселей от точки спутника при опросе
PATH_WIDTH = 1.5  # логических пикселей, линии витка и следа
TRACK_ALPHA = 150  # непрозрачность следа на земле, витка - 255


def group_names():
    """Группы строки «Спутники»: ключ CelesTrak, название, подсказка."""
    names = {
        "stations": (tr("Космические станции"), tr(
            "Международная космическая станция, китайская станция "
            "«Тяньгун» и пристыкованные к ним корабли.")),
        "visual": (tr("Яркие спутники"), tr(
            "Около ста спутников и ступеней ракет, которые видны с Земли "
            "без бинокля.")),
        "gnss": (tr("Навигация"), tr(
            "Спутники GPS, ГЛОНАСС, Galileo и BeiDou на средних "
            "орбитах около 20 000 км и геосинхронных.")),
        "weather": (tr("Метеоспутники"), tr(
            "Метеорологические спутники на полярных и геостационарных "
            "орбитах.")),
        "resource": (tr("Наблюдение Земли"), tr(
            "Спутники съёмки Земли, в том числе Landsat и Sentinel.")),
        "science": (tr("Научные"), tr(
            "Научные спутники и обсерватории на околоземных орбитах.")),
        "geo": (tr("Геостационарные"), tr(
            "Действующие спутники на геосинхронной орбите, около "
            "36 000 км над экватором. Над Землёй они почти неподвижны.")),
        "starlink": (tr("Starlink"), tr(
            "Спутники связи SpaceX на высоте 340-570 км, их тысячи. "
            "Загрузка и первый расчёт идут дольше прочих групп.")),
        "oneweb": (tr("OneWeb"), tr(
            "Спутники связи OneWeb на высоте около 1200 км.")),
    }
    return [(key,) + names[key] for key, _ in core.GROUPS]


def folder():
    """Папка файлов групп CelesTrak в профиле QGIS."""
    path = os.path.join(QgsApplication.qgisSettingsDirPath(), "PlanetX",
                        "satellites")
    os.makedirs(path, exist_ok=True)
    return path


def group_file(group):
    return os.path.join(folder(), group + ".csv")


def read_file(group):
    """Элементы группы из файла и его возраст в секундах или (None,
    None), если файла нет или он не читается."""
    path = group_file(group)
    try:
        with open(path, encoding="utf-8") as stream:
            text = stream.read()
        age = time.time() - os.path.getmtime(path)
    except OSError:
        return None, None
    elements = sgp4.parse_csv(text)
    return (elements, age) if len(elements) else (None, None)


def read_groups():
    """Выбранные группы из настроек, без них - DEFAULT_GROUPS."""
    value = QgsSettings().value(GROUPS_KEY, None)
    if value is None:
        return set(core.DEFAULT_GROUPS)
    if isinstance(value, str):
        value = [v for v in value.split(",") if v]
    known = {key for key, _ in core.GROUPS}
    return {str(v) for v in value if str(v) in known}


class SatelliteManager(QObject):
    """Спутники окна глобуса."""

    # Сменилось количество показанных спутников или пришла ошибка.
    changed = pyqtSignal()

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.view = window.view
        self.swarm = core.Swarm()
        self.on = False
        self.groups = read_groups()
        self.replies = {}
        self.errors = {}
        self.init_timer = QTimer(self)
        self.init_timer.setSingleShot(True)
        self.init_timer.timeout.connect(self._init_step)
        self.tick = QTimer(self)
        self.tick.setInterval(TICK)
        self.tick.timeout.connect(self._tick)
        # Часы проверочных шагов: секунды UTC или None - часы компьютера.
        self.clock = None
        # Выбранный спутник - номер NORAD или None, у него виток орбиты
        # и след. follow - камера следом за ним.
        self.selected = None
        self.follow = False
        self._shapes = []
        self._path_key = None

    # Время.

    def moment(self):
        """Секунды UTC от 1970 года, на которые показываются спутники:
        правый бегунок открытой шкалы времени, иначе часы."""
        span = self.window.satellite_span()
        if span is not None:
            return span
        return self.clock if self.clock is not None else time.time()

    def time_changed(self):
        """Шкала времени сдвинулась или закрылась."""
        self._update_tick()
        self._update_path()
        self._follow_step()
        self.view.update()

    def _update_tick(self):
        running = self.on and self.count() > 0 \
            and self.window.satellite_span() is None
        self.tick.setInterval(FOLLOW_TICK if self.follow else TICK)
        if running and not self.tick.isActive():
            self.tick.start()
        elif not running:
            self.tick.stop()

    def _tick(self):
        self._update_path()
        self._follow_step()
        self.view.update()

    # Выбранный спутник: виток, след, камера следом.

    def under(self, px, py):
        """Номер NORAD спутника под пикселем кадра или None."""
        if not self.on or not self.count():
            return None
        radius = PICK_PIXELS * self.view.devicePixelRatioF()
        index = self.view.satellites.pick(self.view.camera, px, py, radius)
        return None if index is None else int(self.swarm.numbers[index])

    def name_of(self, number):
        index = self.swarm.index_of(number)
        return None if index is None else self.swarm.names[index]

    def select(self, number):
        """Выбрать спутник по номеру NORAD, None - снять выбор и камеру
        следом."""
        self.selected = number
        if number is None:
            self.follow = False
        self._path_key = None
        self._mark()
        self._update_path()
        self._update_tick()
        self.view.update()

    def set_follow(self, on):
        """Камера следом за выбранным спутником."""
        self.follow = bool(on) and self.selected is not None
        self._update_tick()
        self._follow_step()

    def _mark(self):
        index = None if self.selected is None \
            else self.swarm.index_of(self.selected)
        self.view.satellites.highlight = index

    def shapes(self):
        """Виток и след выбранного спутника для своих объектов глобуса."""
        return list(self._shapes)

    def _update_path(self):
        index = None
        if self.on and self.selected is not None and self.count():
            index = self.swarm.index_of(self.selected)
        if index is None:
            if self._shapes:
                self._shapes = []
                self._path_key = None
                self.window._refresh_shapes()
            return
        moment = self.moment()
        key = (self.selected, int(moment // core.ORBIT_REFRESH))
        if key == self._path_key:
            return
        self._path_key = key
        found = core.path(self.swarm.f, index, moment)
        shapes = []
        if found is not None:
            lat, lon, h, tlat, tlon = found
            rgb = tuple(int(v) for v in core.COLORS.get(
                self.swarm.group_of[index], (255, 255, 255)))
            shapes.append(Shape(
                "line", list(zip(lat.tolist(), lon.tolist())),
                color=rgb + (255,), width=PATH_WIDTH, alts=h.tolist()))
            if len(tlat) > 1:
                shapes.append(Shape(
                    "line", list(zip(tlat.tolist(), tlon.tolist())),
                    color=rgb + (TRACK_ALPHA,), width=PATH_WIDTH))
        self._shapes = shapes
        self.window._refresh_shapes()

    def _follow_step(self):
        if not self.follow or self.selected is None:
            return
        index = self.swarm.index_of(self.selected)
        motion = None if index is None \
            else self.swarm.motion(index, self.moment())
        if motion is None:
            return
        point, velocity = motion
        lat, lon, _ = (float(v) for v in
                       core.ellipsoid.ecef_to_geodetic(point))
        # Расстояние и наклон остаются у пользователя: колесо приближает
        # и при камере следом, гасятся только перелёт и инерция.
        nav = self.view.navigator
        nav.inertia = None
        nav.flight = None
        pose = nav.pose.copy()
        pose.lat, pose.lon = lat, lon
        pose.heading = core.heading(point, velocity)
        if pose.terrain is not None:
            pose.h = pose.terrain(lat, lon)
        nav.set_pose(lifted(pose))

    # Строка и группы.

    def set_on(self, on):
        self.on = bool(on)
        if self.on:
            for group in self.groups:
                self._fetch(group)
            self._show()
        else:
            self._abort(set(self.replies))
            self.swarm.keep(set())
            self.selected = None
            self.follow = False
            self._show()
            self._update_path()
        self._update_tick()
        self.changed.emit()

    def set_groups(self, groups):
        self.groups = set(groups)
        QgsSettings().setValue(GROUPS_KEY, sorted(self.groups))
        self._abort(set(self.replies) - self.groups)
        self.swarm.keep(self.groups)
        if self.on:
            for group in self.groups:
                if group not in self.swarm.groups:
                    self._fetch(group)
            self.init_timer.start(0)
        self._show()
        self.changed.emit()

    def _fetch(self, group):
        if group in self.replies or group in self.swarm.groups:
            return
        elements, age = read_file(group)
        if elements is not None and age < core.REFETCH:
            # Файл моложе обновления CelesTrak - сеть не нужна.
            self._use(group, elements)
            return
        failed = float(QgsSettings().value(FAILED_KEY + group, 0.0) or 0.0)
        if time.time() - failed < core.REFETCH:
            # После ошибки CelesTrak просит не спрашивать снова.
            self.errors[group] = tr(
                "CelesTrak отказал в группе, новый запрос - через 2 часа "
                "после отказа.")
            self.changed.emit()
            if elements is not None:
                self._use(group, elements)
            return
        self.replies[group] = fetch_bytes(
            core.feed(group),
            lambda data, error, group=group: self._done(group, data, error),
            prefer_cache=False)
        self._count_pending()

    def _done(self, group, data, error):
        if self.replies.pop(group, None) is None:
            return
        self._count_pending()
        elements = None
        text = data.decode("utf-8", "replace") if data else ""
        if text:
            elements = sgp4.parse_csv(text)
        if elements is None or not len(elements):
            QgsSettings().setValue(FAILED_KEY + group, time.time())
            self.errors[group] = error or tr("Ответ без элементов орбит.")
            self.changed.emit()
            old, _ = read_file(group)
            if old is not None:
                self._use(group, old)
            return
        self.errors.pop(group, None)
        try:
            with open(group_file(group), "w", encoding="utf-8",
                      newline="\n") as stream:
                stream.write(text)
        except OSError as failure:
            # Без файла группа покажется, но в следующий раз уйдёт
            # в сеть раньше срока.
            self.errors[group] = str(failure)
        self._use(group, elements)

    def _use(self, group, elements):
        """Элементы группы - в расчёт, если строка и группа ещё
        включены."""
        if not self.on or group not in self.groups:
            return
        self.swarm.set_group(group, elements)
        self.init_timer.start(0)

    def _abort(self, groups):
        """Снять запросы групп. Запрос сначала уходит из списка: снятый
        ответ приходит сразу, и обработчик не должен принять его за
        отказ CelesTrak."""
        replies = [self.replies.pop(group) for group in groups
                   if group in self.replies]
        self._count_pending()
        for reply in replies:
            reply.abort()

    _counted = 0

    def _count_pending(self):
        """Ждущие ответы - в счётчик загрузки вида, его показывает
        значок загрузки."""
        count = len(self.replies)
        self.view.data_pending = max(
            0, self.view.data_pending + count - self._counted)
        self._counted = count

    def _init_step(self):
        if not self.swarm.init_some():
            self.init_timer.start(0)
            return
        if self.selected is not None \
                and self.swarm.index_of(self.selected) is None:
            # Группа выбранного спутника снята.
            self.selected = None
            self.follow = False
        self._mark()
        self._path_key = None
        self._update_path()
        self._show()
        self._update_tick()
        self.changed.emit()

    def _show(self):
        """Точки вида: источник положений на кадр или пусто."""
        points = self.view.satellites
        if self.on and self.swarm.f is not None and len(self.swarm):
            points.source = self._positions
            points.colors = self.swarm.colors
            points.sizes = self.swarm.sizes
        else:
            points.source = None
            points.clear()
        self.view.update()

    def _positions(self):
        return self.swarm.positions(self.moment())

    def count(self):
        return len(self.swarm) if self.swarm.f is not None else 0

    # Опрос.

    def identify(self, px, py):
        """Спутник у точки щелчка: [(название, [(поле, значение)])].
        Найденный спутник становится выбранным."""
        number = self.under(px, py)
        if number is None:
            return []
        index = self.swarm.index_of(number)
        info = self.swarm.info(index, self.moment())
        names = {key: name for key, name, _ in group_names()}
        values = [(tr("Номер NORAD"), str(info["number"])),
                  (tr("Группа"), names.get(info["group"], info["group"])),
                  (tr("Высота"), tr("{value} км", value="{:.0f}".format(
                      info["height"]))),
                  (tr("Скорость"), tr("{value} км/с", value="{:.2f}".format(
                      info["speed"]))),
                  (tr("Возраст элементов"), tr(
                      "{value} сут", value="{:.1f}".format(info["age"])))]
        self.select(number)
        return [(info["name"], values)]

    def close(self):
        self.tick.stop()
        self.init_timer.stop()
        self._abort(set(self.replies))
