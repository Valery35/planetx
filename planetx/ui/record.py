# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Запись тура кадрами PNG (шаг 13).

Кадры идут по шкале core/timeline.py, FPS в секунду времени тура.
Каждый кадр снимается как снимок вида (render/view.py, start_shot):
камера стоит в позе кадра, треки - в моменте кадра, снимок ждёт
загрузки. Поэтому запись идёт медленнее тура, а готовые кадры
не зависят от скорости сети и видеокарты.

Рядом с кадрами ложится frames.json: частота, размер, поза камеры
и момент времени данных каждого кадра, недогруженные кадры. По нему
повтор записи сверяется с первой.
"""
import json
import os

from qgis.PyQt.QtCore import QObject, QTimer, pyqtSignal

from ..core.timeline import FPS, Timeline
from ..i18n import tr
from .snapshot import draw_attribution, plain_text

FRAME_NAME = "frame_{:05d}.png"
INDEX_NAME = "frames.json"
# Кадр, который ждёт загрузки дольше, снимается как есть и попадает
# в список недогруженных. Иначе один неприходящий тайл вешал бы запись.
FRAME_WAIT = 20000  # мс


class TourRecorder(QObject):
    """Запись тура в папку. progress - (кадр, всего), done - текст."""

    progress = pyqtSignal(int, int)
    done = pyqtSignal(bool, str)

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.view = window.view
        self.line = None
        self.folder = ""
        self.n = 0
        self.size = (0, 0)
        self.ratio = 1.0
        self.frames = []
        self.incomplete = []
        self.wait = QTimer(self)
        self.wait.setSingleShot(True)
        self.wait.timeout.connect(self._force)
        self.view.shot_done.connect(self._shot)

    @property
    def active(self):
        return self.line is not None

    def start(self, stops, pause, folder):
        """Начать запись остановок stops с паузой pause в папку folder.
        Возвращает False, если записать нельзя."""
        if self.active or not stops:
            return False
        view = self.view
        self.ratio = view.devicePixelRatioF()
        # Чётные стороны: кодеры видео не принимают нечётные.
        width = max(2, int(round(view.width() * self.ratio)) // 2 * 2)
        height = max(2, int(round(view.height() * self.ratio)) // 2 * 2)
        self.size = (width, height)
        self.line = Timeline(stops, pause, self.window.tracks.data_span(),
                             FPS, view.camera.fov_y)
        self.folder = folder
        self.n = 0
        self.frames = []
        self.incomplete = []
        self._next()
        return True

    def cancel(self):
        if not self.active:
            return
        self.view.cancel_shot()
        self._finish(False, tr("Запись тура прервана на кадре {n}.",
                               n=self.n))

    def _next(self):
        frame = self.line.frame(self.n)
        tracks = self.window.tracks
        if frame.moment is not None:
            tracks.set_moment(frame.moment)
        self.view.navigator.show(frame.pose)
        if not self.view.start_shot(self.size[0], self.size[1], self.ratio):
            self._finish(False, tr("Глобус ещё не готов к снимку."))
            return
        self.wait.start(FRAME_WAIT)
        self.progress.emit(self.n + 1, self.line.count)

    def _force(self):
        if self.active:
            self.view.finish_shot()

    def _shot(self, image, complete):
        if not self.active:
            return
        if image is None:
            self._finish(False, tr(
                "Видеокарта не создала буфер размера окна."))
            return
        draw_attribution(image, plain_text(
            self.window.attribution.text()), self.ratio)
        path = os.path.join(self.folder, FRAME_NAME.format(self.n))
        if not image.save(path):
            self._finish(False, tr("Не удалось записать {path}", path=path))
            return
        pose = self.view.navigator.pose
        self.frames.append({
            "pose": [pose.lat, pose.lon, pose.distance, pose.heading,
                     pose.tilt],
            "moment": self.line.frame(self.n).moment})
        if not complete:
            self.incomplete.append(self.n)
        self.n += 1
        if self.n < self.line.count:
            self._next()
            return
        self._write_index()
        self._finish(True, tr(
            "Тур записан в {folder}. Кадров {count}, {fps} в секунду.",
            count=self.line.count, fps=FPS, folder=self.folder))

    def _write_index(self):
        data = {"fps": FPS, "count": self.line.count,
                "width": self.size[0], "height": self.size[1],
                "incomplete": self.incomplete, "frames": self.frames}
        with open(os.path.join(self.folder, INDEX_NAME), "w",
                  encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)

    def _finish(self, ok, text):
        self.wait.stop()
        self.line = None
        self.window.tracks.release()
        self.done.emit(ok, text)
