# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Запись тура: кадры PNG в папку или сразу видео MP4 (шаг 13).

Кадры идут по шкале core/timeline.py, FPS в секунду времени тура.
Каждый кадр снимается как снимок вида (render/view.py, start_shot):
камера стоит в позе кадра, треки - в моменте кадра, снимок ждёт
загрузки. Поэтому запись идёт медленнее тура, а готовые кадры
не зависят от скорости сети и видеокарты.

Рядом с кадрами ложится frames.json: частота, размер, поза камеры
и момент времени данных каждого кадра, недогруженные кадры. По нему
повтор записи сверяется с первой.

Два режима, просьба автора от 6 октября 2026 года. Кадры PNG -
профессиональный: размер любой, хоть 4K, монтаж в своей программе.
Видео MP4 - быстрый: размер окна, файл готов сразу, кодирует Windows
Media Foundation (core/video.py). Оба режима ждут полной загрузки
каждого кадра, решение автора того же дня.
"""
import json
import os

from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QObject, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QImage
from qgis.PyQt.QtWidgets import (QButtonGroup, QComboBox, QDialog,
                                 QDialogButtonBox, QLabel, QRadioButton,
                                 QVBoxLayout)

from ..core import video
from ..core.snapshot import file_ratio
from ..core.timeline import FPS, Timeline
from ..i18n import tr
from .snapshot import draw_attribution, plain_text

FRAME_NAME = "frame_{:05d}.png"
INDEX_NAME = "frames.json"
# Кадр, который ждёт загрузки дольше, снимается как есть и попадает
# в список недогруженных. Иначе один неприходящий тайл вешал бы запись.
FRAME_WAIT = 20000  # мс
MODE_KEY = "PlanetX/record_mode"
SIZE_KEY = "PlanetX/record_size"
# Размеры кадров PNG, 0 × 0 - как окно.
SIZES = ((0, 0), (1920, 1080), (2560, 1440), (3840, 2160))


def size_names():
    return [tr("Как окно"), tr("1920 × 1080 (Full HD)"),
            tr("2560 × 1440"), tr("3840 × 2160 (4K)")]


class RecordDialog(QDialog):
    """Выбор записи тура: видео MP4 в размере окна или кадры PNG."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(tr("Запись тура"))
        layout = QVBoxLayout(self)
        self.video = QRadioButton(tr("Видео MP4 в размере окна"), self)
        self.video.setToolTip(tr(
            "Готовый ролик H.264, 25 кадров в секунду. Кодирует "
            "Windows, сторонние программы не нужны. Каждый кадр ждёт "
            "загрузки, поэтому запись идёт дольше тура."))
        self.frames = QRadioButton(tr("Кадры PNG в папку"), self)
        self.frames.setToolTip(tr(
            "Кадры без потери качества в выбранном размере и файл "
            "frames.json с позами камеры. Из кадров ролик собирают "
            "программой монтажа или ffmpeg, см. руководство."))
        group = QButtonGroup(self)
        group.addButton(self.video)
        group.addButton(self.frames)
        layout.addWidget(self.video)
        if not video.available():
            self.video.setEnabled(False)
            note = QLabel(tr("Видео сразу пишется только в Windows."), self)
            note.setWordWrap(True)
            layout.addWidget(note)
        layout.addWidget(self.frames)
        self.size = QComboBox(self)
        self.size.addItems(size_names())
        self.size.setToolTip(tr(
            "Размер кадров PNG. Кадр крупнее окна рисуется заново в этом "
            "размере, надписи и линии крупнее в той же доле."))
        layout.addWidget(self.size)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        settings = QgsSettings()
        mode = settings.value(MODE_KEY, "video")
        (self.video if mode == "video" and video.available()
         else self.frames).setChecked(True)
        index = int(settings.value(SIZE_KEY, 0) or 0)
        self.size.setCurrentIndex(index if 0 <= index < len(SIZES) else 0)
        self.video.toggled.connect(self._mode)
        self._mode()

    def _mode(self, *args):
        self.size.setEnabled(self.frames.isChecked())

    def choice(self):
        """Режим «video» или «frames» и размер кадров (0, 0 - окно)."""
        mode = "video" if self.video.isChecked() else "frames"
        settings = QgsSettings()
        settings.setValue(MODE_KEY, mode)
        settings.setValue(SIZE_KEY, self.size.currentIndex())
        return mode, SIZES[self.size.currentIndex()]


class TourRecorder(QObject):
    """Запись тура в папку кадров или в файл MP4. progress - (кадр,
    всего), done - текст."""

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
        self.writer = None  # core.video.Mp4Writer в режиме видео
        self.wait = QTimer(self)
        self.wait.setSingleShot(True)
        self.wait.timeout.connect(self._force)
        self.view.shot_done.connect(self._shot)

    @property
    def active(self):
        return self.line is not None

    def start(self, stops, pause, folder, mode="frames", size=(0, 0)):
        """Начать запись остановок stops с паузой pause. Режим «frames» -
        кадры PNG размера size (0, 0 - окно) в папку folder, «video» -
        файл MP4 folder в размере окна. Возвращает False, если записать
        нельзя."""
        if self.active or not stops:
            return False
        view = self.view
        window_ratio = view.devicePixelRatioF()
        # Чётные стороны: кодеры видео не принимают нечётные.
        width, height = video.even_size(round(view.width() * window_ratio),
                                        round(view.height() * window_ratio))
        self.ratio = window_ratio
        if mode == "frames" and size[0] and size[1]:
            width, height = video.even_size(*size)
            self.ratio = file_ratio(window_ratio, view.camera.width, width)
        self.size = (width, height)
        self.writer = None
        if mode == "video":
            try:
                self.writer = video.Mp4Writer(folder, width, height, FPS)
            except video.VideoError as error:
                self.done.emit(False, tr(
                    "Видео не начато: {error}", error=str(error)))
                return False
        self.line = Timeline(stops, pause, self.window.time_span(),
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
        if self.writer is not None:
            if not self._write_video(image):
                return
        else:
            path = os.path.join(self.folder, FRAME_NAME.format(self.n))
            if not image.save(path):
                self._finish(False, tr("Не удалось записать {path}",
                                       path=path))
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
        if self.writer is not None:
            self._finish(True, tr(
                "Видео тура записано в {path}. Кадров {count}, {fps} "
                "в секунду.", count=self.line.count, fps=FPS,
                path=self.folder))
            return
        self._write_index()
        self._finish(True, tr(
            "Тур записан в {folder}. Кадров {count}, {fps} в секунду.",
            count=self.line.count, fps=FPS, folder=self.folder))

    def _write_video(self, image):
        """Кадр в MP4. Снимок приводится к RGB32 и размеру видео."""
        frame = image.convertToFormat(QImage.Format.Format_RGB32)
        width, height = self.size
        if frame.width() != width or frame.height() != height:
            frame = frame.copy(0, 0, width, height)
        if frame.bytesPerLine() != width * 4:
            self._finish(False, tr("Кадр видео не того формата."))
            return False
        try:
            self.writer.write(int(frame.constBits()))
        except video.VideoError as error:
            self._finish(False, tr("Видео прервано: {error}",
                                   error=str(error)))
            return False
        return True

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
        writer, self.writer = self.writer, None
        if writer is not None:
            # Прерванная запись тоже даёт годный файл из записанных кадров.
            try:
                writer.close()
            except video.VideoError as error:
                ok = False
                text = tr("Видео не дописано: {error}", error=str(error))
        self.window.tracks.release()
        self.done.emit(ok, text)
