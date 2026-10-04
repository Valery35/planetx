# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Названия и подсказки тем NASA GIBS для раздела «Слои», ползунок
даты темы.

Слои, адреса и даты - core/themes.py. Здесь только то, что видит
человек, через tr().
"""
from qgis.PyQt.QtCore import Qt, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import QFrame, QHBoxLayout, QLabel, QSlider, \
    QToolButton

from ..i18n import tr
from ..qt_compat import enum

STYLE = ("QFrame#planetxThemeBar { background: rgba(250, 250, 250, 230); "
         "border: 1px solid rgba(0, 0, 0, 60); border-radius: 4px; }")
SLIDER_WIDTH = 260
SETTLE = 300  # мс после остановки ползунка до смены дня
PLAY_PERIOD = 900  # мс на шаг показа


def group_names():
    """Группы тем: ключ, название, подсказка."""
    return (
        ("fire", tr("Планета огня"), tr(
            "Дым, аэрозоль и угарный газ пожаров и промышленности по "
            "данным NASA. Включена одна тема из всех групп. Флажок группы "
            "выключает её тему и включает снова. День темы задаёт её "
            "ползунок в левом нижнем углу вида.")),
        ("water", tr("Планета воды"), tr(
            "Осадки, влажность почвы, снег, лёд, пар, хлорофилл, солёность "
            "и наводнения по данным NASA. Включена одна тема из всех "
            "групп. Флажок группы выключает её тему и включает снова.")),
        ("gases", tr("Газы"), tr(
            "Диоксид азота, диоксид серы, метан, углекислый газ и озон по "
            "данным NASA. Включена одна тема из всех групп. Флажок группы "
            "выключает её тему и включает снова.")),
        ("life", tr("Земля и жизнь"), tr(
            "Растительность, пыль, ночные огни и типы покрова по данным "
            "NASA. Включена одна тема из всех групп. Флажок группы "
            "выключает её тему и включает снова.")))


def theme_names():
    """Тема: ключ - (название, подсказка)."""
    return {
        "smoke": (tr("Дым, аэрозольный индекс"), tr(
            "Поглощающий аэрозоль - дым пожаров и пыль - по OMPS за "
            "сутки, с 2012 года.")),
        "aerosol": (tr("Оптическая толщина аэрозоля"), tr(
            "Насколько воздух ослабляет свет из-за дыма, пыли и смога, "
            "MODIS за сутки, с 2017 года.")),
        "co": (tr("Угарный газ"), tr(
            "Доля угарного газа на высоте около 5 км по AIRS за сутки, "
            "с 2002 года. Шлейфы пожаров видны на тысячи километров.")),
        "co_emission": (tr("Выбросы угарного газа"), tr(
            "Выбросы угарного газа у поверхности по реанализу MERRA-2 "
            "за месяц, с 1980 года. Ряд отстаёт на несколько месяцев.")),
        "rain": (tr("Осадки"), tr(
            "Интенсивность осадков IMERG за сутки, с 2000 года.")),
        "soil": (tr("Влажность почвы"), tr(
            "Влажность верхних сантиметров почвы по SMAP за сутки, "
            "с 2015 года. В ряду бывают пропущенные дни.")),
        "snow": (tr("Снежный покров"), tr(
            "Снег по снимкам MODIS Terra за сутки, с 2000 года. Под "
            "облаками пропуски.")),
        "sea_ice": (tr("Морской лёд"), tr(
            "Сплочённость морского льда по GHRSST MUR за сутки, "
            "с 2002 года.")),
        "vapor": (tr("Водяной пар"), tr(
            "Водяной пар в толще атмосферы по MODIS Terra за сутки, "
            "с 2000 года.")),
        "chlorophyll": (tr("Хлорофилл"), tr(
            "Хлорофилл водорослей в поверхностном слое моря по PACE "
            "за сутки, с 2024 года.")),
        "salinity": (tr("Солёность моря"), tr(
            "Солёность поверхности моря по SMAP, скользящее среднее "
            "за 8 суток, с 2015 года.")),
        "flood": (tr("Наводнения"), tr(
            "Вода, вышедшая за обычные берега, по MODIS за 3 суток, "
            "с 2021 года.")),
        "no2": (tr("Диоксид азота"), tr(
            "Диоксид азота в тропосфере по TROPOMI за сутки, с 2018 года. "
            "Видны города, дороги и электростанции.")),
        "so2": (tr("Диоксид серы"), tr(
            "Диоксид серы у поверхности по OMPS за сутки, с 2012 года. "
            "Видны вулканы и заводы.")),
        "methane": (tr("Метан"), tr(
            "Доля метана на высоте около 7 км по AIRS за месяц, "
            "с 2002 года.")),
        "co2": (tr("Углекислый газ"), tr(
            "Среднее содержание углекислого газа в столбе атмосферы по "
            "OCO-2, полосы витков за сутки, с 2014 года. Ряд отстаёт "
            "на несколько месяцев.")),
        "ozone": (tr("Озон"), tr(
            "Общее содержание озона по OMI за сутки, с 2004 года. Видна "
            "озоновая дыра над Антарктидой.")),
        "ndvi": (tr("Растительность"), tr(
            "Индекс растительности NDVI по MODIS Terra за 16 суток, "
            "с 2000 года. Ряд отстаёт на месяц.")),
        "dust": (tr("Пыль"), tr(
            "Пыль в атмосфере по AIRS за сутки, с 2002 года.")),
        "night": (tr("Ночные огни"), tr(
            "Ночной снимок VIIRS за сутки, с 2021 года. Видны огни "
            "городов, пожары, факелы и полярные сияния.")),
        "land_cover": (tr("Типы покрова"), tr(
            "Типы земного покрова IGBP по MODIS за год, с 2001 года. "
            "Классы - в шкале в углу вида.")),
    }


class ThemeBar(QFrame):
    """Ползунок даты темы NASA: дни ряда темы, шаг назад и вперёд,
    показ подряд. Сигнал day_changed - день YYYY-MM-DD. Просьба автора
    от 5 октября 2026 года - у покрытий момент, а не промежуток."""

    day_changed = pyqtSignal(str)

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("planetxThemeBar")
        self.setStyleSheet(STYLE)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(4)
        self.days = []
        self.back = self._button("⏮", tr("На шаг ряда назад."),
                                 lambda: self.step(-1))
        layout.addWidget(self.back)
        self.slider = QSlider(enum(Qt, "Orientation", "Horizontal"), self)
        self.slider.setFixedWidth(SLIDER_WIDTH)
        self.slider.setToolTip(tr(
            "День темы. Ползунок идёт по дням ряда, пропущенных дней в нём "
            "нет."))
        self.slider.valueChanged.connect(self._moved)
        layout.addWidget(self.slider)
        self.forward = self._button("⏭", tr("На шаг ряда вперёд."),
                                    lambda: self.step(1))
        layout.addWidget(self.forward)
        self.play = self._button("▶\ufe0f", tr(
            "Показ дней подряд к концу ряда. Следующий день ждёт, пока "
            "загрузится нынешний."), self.toggle)
        layout.addWidget(self.play)
        self.label = QLabel(self)
        layout.addWidget(self.label)
        # День уходит сигналом, когда ползунок остановился.
        self.settle = QTimer(self)
        self.settle.setSingleShot(True)
        self.settle.setInterval(SETTLE)
        self.settle.timeout.connect(self._emit)
        self.timer = QTimer(self)
        self.timer.setInterval(PLAY_PERIOD)
        self.timer.timeout.connect(self._step)
        # ready() - показан ли нынешний день. Ставит окно.
        self.ready = None
        self.hide()

    def _button(self, text, tip, slot):
        button = QToolButton(self)
        button.setText(text)
        button.setToolTip(tip)
        button.setAutoRaise(True)
        button.clicked.connect(slot)
        return button

    def day(self):
        if not self.days:
            return None
        return self.days[self.slider.value()]

    def set_days(self, days, day):
        """Дни ряда и выбранный день. Сигнал не идёт."""
        self.stop()
        self.days = list(days)
        self.slider.blockSignals(True)
        self.slider.setRange(0, max(len(self.days) - 1, 0))
        if day in self.days:
            self.slider.setValue(self.days.index(day))
        else:
            self.slider.setValue(len(self.days) - 1)
        self.slider.blockSignals(False)
        self._show()

    def step(self, delta):
        self.slider.setValue(self.slider.value() + delta)
        self.settle.stop()
        self._emit()

    def _show(self):
        self.label.setText(self.day() or "")
        self.adjustSize()

    def _moved(self, *args):
        self._show()
        self.settle.start()

    def _emit(self):
        if self.days:
            self.day_changed.emit(self.day())

    def toggle(self):
        if self.timer.isActive():
            self.stop()
        elif self.slider.value() < self.slider.maximum():
            self.timer.start()
            self.play.setText("⏸")

    def stop(self):
        self.timer.stop()
        self.play.setText("▶\ufe0f")

    def _step(self):
        if self.ready is not None and not self.ready():
            return
        if self.slider.value() >= self.slider.maximum():
            self.stop()
            return
        self.step(1)
