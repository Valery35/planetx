# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно глобуса: вид OpenGL и строка состояния с подписью источника."""
import os
import time

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (QHBoxLayout, QLabel, QLineEdit,
                                 QPushButton, QVBoxLayout, QWidget)

from ..core.flight import Flight, parse_latlon
from ..core.mipmap import mip_chain
from ..core.tiling import tile_mesh
from ..i18n import tr
from ..net.loader import TileLoader
from ..qt_compat import enum
from ..render.view import GlobeView, start_keys

ATTRIBUTION = ('<a href="https://www.openstreetmap.org/copyright">'
               '© OpenStreetMap contributors</a>')
STATUS_PERIOD = 0.25  # секунд между обновлениями строки состояния
MESSAGE_TIME = 5.0  # секунд, сколько видно сообщение об ошибке ввода
# Расстояние в конце перелёта - текущее, но не больше этого, метров.
# Из космоса перелёт кончается на 2 км, от улицы к улице идёт на месте.
FLIGHT_DISTANCE = 2000.0


def _prepare(key, rgba):
    """Работа рабочего потока: сетка вершин и уровни мипмапов тайла."""
    return tile_mesh(*key), mip_chain(rgba)


def distance_text(metres):
    """Расстояние для строки состояния, метры или километры."""
    if metres < 10000.0:
        return tr("{value} м", value="%.0f" % metres)
    return tr("{value} км", value="{:,.0f}".format(metres / 1000.0)
              .replace(",", " "))


class GlobeWindow(QWidget):
    """Отдельное окно поверх главного окна QGIS."""

    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent, enum(Qt, "WindowType", "Window"))
        # Закрытое окно уничтожается вместе с контекстом OpenGL
        # и загрузчиком. Пункт меню открывает новое.
        self.setAttribute(enum(Qt, "WidgetAttribute", "WA_DeleteOnClose"))
        self.setWindowTitle("PlanetX")
        self.setWindowIcon(QIcon(os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "icon.svg")))
        self.view = GlobeView(self)
        self.status = QLabel(self)
        attribution = QLabel(ATTRIBUTION, self)
        attribution.setOpenExternalLinks(True)
        self.place = QLineEdit(self)
        self.place.setPlaceholderText(tr("Широта, долгота"))
        self.place.setToolTip(tr(
            "Координаты в градусах, например 58.0105, 56.2294.\n"
            "Enter запускает перелёт. Перелёт прерывается мышью."))
        self.place.setMaximumWidth(260)
        self.place.returnPressed.connect(self.fly)
        go = QPushButton(tr("Лететь"), self)
        go.clicked.connect(self.fly)
        self.message = ("", 0.0)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(6, 2, 6, 2)
        bottom.addWidget(self.place, 0)
        bottom.addWidget(go, 0)
        bottom.addWidget(self.status, 1)
        bottom.addWidget(attribution, 0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.view, 1)
        layout.addLayout(bottom)

        self.errors = {}
        # Сетка вершин и мипмапы тайла считаются в рабочем потоке
        # загрузчика, главному потоку остаётся передать их в видеокарту.
        self.loader = TileLoader(parent=self, prepare=_prepare)
        self.loader.loaded.connect(self._loaded)
        self.loader.failed.connect(self._failed)
        self._shown_at = 0.0
        self.view.changed.connect(self._frame_done)
        self.view.loader = self.loader
        # Мелкие уровни важнее: они первыми закрывают весь шар.
        self.loader.want_many((key, -key[0]) for key in start_keys())
        self._show_state()

    def _loaded(self, key, rgba, prepared):
        self.errors.pop(key, None)
        mesh, levels = prepared
        self.view.add_image(key, levels, mesh)
        # Пока уровни 0-2 не готовы, полных кадров нет и сигнала changed
        # тоже. Строка загрузки обновляется отсюда, с тем же ограничением.
        self._frame_done()

    def _failed(self, key, error):
        self.errors[key] = error
        self._show_state()

    def _frame_done(self):
        """После кадра строка обновляется не чаще STATUS_PERIOD.

        setText на каждом кадре перерисовывает строку и отнимает время
        у цикла событий. Замер 26 сентября 2026 года показал до 22 мс
        между кадром и следующим paintGL.
        """
        now = time.monotonic()
        if now - self._shown_at >= STATUS_PERIOD:
            self._shown_at = now
            self._show_state()

    def fly(self):
        """Перелёт к координатам из поля ввода."""
        text = self.place.text()
        target = parse_latlon(text)
        if target is None:
            self.message = (tr("Не удалось прочитать координаты: {text}",
                               text=text), time.monotonic())
            self._show_state()
            return
        navigator = self.view.navigator
        distance = min(navigator.pose.distance, FLIGHT_DISTANCE)
        flight = Flight(navigator.pose, *target, distance,
                        fov_y=self.view.camera.fov_y)
        navigator.start_flight(flight, time.monotonic())
        self.view.setFocus()
        self.view.update()

    def _show_state(self):
        keys = start_keys()
        done = sum(1 for key in keys if self.view.has(key))
        text, shown = self.message
        if text and time.monotonic() - shown < MESSAGE_TIME:
            self.status.setText(text)
            return
        if self.errors:
            text = tr("Подложка не загрузилась: {error}",
                      error=next(iter(self.errors.values())))
        elif done < len(keys):
            text = tr("Загрузка подложки: {done} из {total}",
                      done=done, total=len(keys))
        elif self.view.error:
            text = tr("Контекст OpenGL 3.3 недоступен: {version}",
                      version=self.view.error)
        else:
            text = tr("Высота {height}, тайлов в кадре {count}",
                      height=distance_text(self.view.altitude()),
                      count=self.view.drawn)
        self.status.setText(text)

    def closeEvent(self, event):
        self.loader.abort()
        super().closeEvent(event)
        # Окно с WA_DeleteOnClose Qt уничтожает позже. Плагин узнаёт
        # о закрытии сразу, чтобы меню открыло новое окно, а не это.
        self.closed.emit()
