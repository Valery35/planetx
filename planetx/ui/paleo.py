# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Палеогеография - карты PaleoDEM PALEOMAP подложкой из тайлов
planetx-terrain: ползунок возраста, период, показ. Строка реестра
каталога (core/rows.py) и исполнитель."""
from qgis.PyQt.QtCore import QObject, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import QFrame, QHBoxLayout, QLabel, QSlider, \
    QToolButton

from ..core import basemap, paleo
from ..core.rows import Row
from ..i18n import tr
from ..qt_compat import enum
from .style import plate, set_glyph

# Плашка и значки - общий вид элементов поверх глобуса, ui/style.py.
PLAY_PERIOD = 900  # мс на шаг возраста при показе
SLIDER_WIDTH = 260
KEY = "paleo"
PREVIEW_AGE = 100  # млн лет, возраст карты на превью каталога


def period_names():
    return {"quaternary": tr("Четвертичный период"), "neogene": tr("Неоген"),
            "paleogene": tr("Палеоген"), "cretaceous": tr("Мел"),
            "jurassic": tr("Юра"), "triassic": tr("Триас"),
            "permian": tr("Пермский период"), "carboniferous": tr("Карбон"),
            "devonian": tr("Девон"), "silurian": tr("Силур"),
            "ordovician": tr("Ордовик"), "cambrian": tr("Кембрий"),
            "precambrian": tr("Докембрий")}


class PaleoBar(QFrame):
    """Панель возраста. Сигнал age_changed - возраст в млн лет."""

    age_changed = pyqtSignal(int)

    def __init__(self, parent):
        super().__init__(parent)
        plate(self, "planetxPaleo")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(6)
        self.slider = QSlider(enum(Qt, "Orientation", "Horizontal"), self)
        self.slider.setRange(0, len(paleo.AGES) - 1)
        # Прошлое слева, настоящее справа, как на шкале времени.
        self.slider.setInvertedAppearance(True)
        self.slider.setFixedWidth(SLIDER_WIDTH)
        self.slider.setToolTip(tr(
            "Возраст в миллионах лет назад. Карта рельефа и глубин на "
            "этот возраст - PaleoDEM PALEOMAP, Scotese и Wright 2018."))
        self.slider.valueChanged.connect(self._moved)
        layout.addWidget(self.slider)
        self.play = QToolButton(self)
        set_glyph(self.play, "▶\ufe0f")
        self.play.setAutoRaise(True)
        self.play.setToolTip(tr(
            "Показ от выбранного возраста к настоящему по всем картам "
            "набора."))
        self.play.clicked.connect(self.toggle)
        layout.addWidget(self.play)
        self.label = QLabel(self)
        layout.addWidget(self.label)
        # Возраст уходит сигналом, когда ползунок остановился.
        self.settle = QTimer(self)
        self.settle.setSingleShot(True)
        self.settle.setInterval(250)
        self.settle.timeout.connect(self._emit)
        self.timer = QTimer(self)
        self.timer.setInterval(PLAY_PERIOD)
        self.timer.timeout.connect(self._step)
        # ready() - показан ли нынешний возраст. Показ ждёт его, иначе
        # шаги обгоняют ответы службы и глобус стоит. Ставит окно.
        self.ready = None
        self._show()
        self.hide()

    def age(self):
        return paleo.AGES[self.slider.value()]

    def set_age(self, age):
        self.slider.setValue(paleo.AGES.index(paleo.nearest(age)))

    def _show(self):
        age = self.age()
        name = period_names()[paleo.period(age)]
        self.label.setText(tr("{age} млн лет назад, {period}", age=age,
                              period=name) if age else tr("Настоящее"))
        self.adjustSize()

    def _moved(self, *args):
        self._show()
        self.settle.start()

    def _emit(self):
        self.age_changed.emit(self.age())

    def toggle(self):
        if self.timer.isActive():
            self.stop()
        elif self.slider.value() > 0:
            self.timer.start()
            set_glyph(self.play, "⏸")

    def stop(self):
        self.timer.stop()
        set_glyph(self.play, "▶\ufe0f")

    def _step(self):
        if self.ready is not None and not self.ready():
            return
        value = self.slider.value()
        if value <= 0:
            self.stop()
            return
        self.slider.setValue(value - 1)
        # Возраст уходит сразу, без ожидания остановки ползунка.
        self.settle.stop()
        self._emit()


class PaleoTool(QObject):
    """Режим палеогеографии: карта возраста - подложка Земли, рельеф
    выключен, ползунок возраста над шкалами. Окно берёт подложку
    (base_source) и масштаб рельефа (flat_relief) у исполнителя."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.bar = PaleoBar(window.view)
        self.bar.age_changed.connect(self.set_age)
        self.bar.ready = self.ready
        # Ползунок ставит на место раскладка окна (_place_attribution).
        window.paleo_bar = self.bar
        self.age = 0
        # Шаги проверки подменяют адрес на локальную копию хранилища.
        self.url = paleo.TILE_URL
        self.sources = {}

    shown_key = None

    def on(self):
        window = self.window
        return bool(getattr(window, "extras", {}).get(KEY)) \
            and window.planet.earth and window.view.sky_view is None

    def turn(self, key, on):
        """Ползунок возраста, гладкая основа и карта возраста."""
        window = self.window
        shown = self.on()
        self.bar.setVisible(shown)
        window.view.plain_base = shown
        if window._relief_target() != window.view.store.scale:
            window.view.set_relief(window._relief_target())
            window._update_water()
            window._place_rows()
        window._place_attribution()
        if not shown:
            self.bar.stop()
            if window.planet.earth:
                window._switch_basemap(window._earth_source())
            window._show_attribution()
            return True
        self.set_age(self.bar.age())
        return True

    def set_age(self, age):
        """Карта возраста age млн лет - подложка. Уровни 0-2 прежнего
        возраста стоят на экране, пока не придут новые, глубокие тайлы
        снимаются сразу (change_source, coarse): кадр не смешивает два
        возраста, новый встаёт грубым и уточняется."""
        self.age = age
        if self.on():
            window = self.window
            window._switch_basemap(window._earth_source(), coarse=True)

    def source(self, age):
        """Источник тайлов карты возраста age, один на возраст: смена
        источника сравнивается по тождеству."""
        url = self.url.format(age=age, z="{z}", x="{x}", y="{y}")
        found = self.sources.get(url)
        if found is None:
            found = basemap.Source(tr("{age} млн лет назад", age=age), url,
                                   paleo.MAX_LEVEL, paleo.ATTRIBUTION,
                                   builtin=True, missing=(404,))
            self.sources[url] = found
        return found

    def base_source(self):
        """Подложка Земли в режиме или None."""
        return self.source(self.age) if self.on() else None

    def flat_relief(self):
        """В палеогеографии рельеф выключен: нынешние горы на берегах
        прошлого лишние, решение автора от 4 октября 2026 года."""
        return self.on()

    def ready(self):
        """Показан ли нынешний возраст: уровни 0-2 его карты на экране
        и ни одного тайла прежней карты в кадре. Показ ждёт этого, иначе
        шаги обгоняют загрузку."""
        from ..render.view import start_keys
        view = self.window.view
        keep = view.selection.keep if view.selection else ()
        return all(key in view.textures and key not in view.stale
                   for key in start_keys()) \
            and not any(key in view.stale for key in keep)

    @property
    def legend(self):
        return self.bar

    def sync_legend(self):
        shown = self.on()
        self.bar.setVisible(shown)
        self.window.view.plain_base = shown

    def identify(self, lat, lon, tolerance=0.0):
        return []

    def credit(self):
        return None

    def close(self):
        self.bar.stop()


ROWS = (
    Row(KEY, "geology", lambda: (tr("Палеогеография"), tr(
        "Рельеф суши и глубины моря в прошлом, до 540 млн "
        "лет назад, по картам PaleoDEM PALEOMAP. Возраст "
        "задаёт ползунок в левом нижнем углу вида. Снимок, "
        "границы и подписи на это время убраны.")), PaleoTool,
        source="PALEOMAP", after="cutaway", remember=False,
        words=("палеогеография", "пангея", "древняя земля", "paleo",
               "pangaea"),
        preview=paleo.TILE_URL.replace("{age}", str(PREVIEW_AGE))),
)
