# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Снимок вида в файл и картинка вида в макете QGIS.

Снимок рисуется в невидимый буфер нужного размера и ждёт, пока
загрузятся тайлы, картинки слоёв и надписи для этого размера
(render/view.py, start_shot). Подпись источников ставится в угол
снимка, условия Esri и OpenStreetMap её требуют.

В макет вид ложится неизменной картинкой, вставленной в проект.
Решения автора от 28 сентября 2026 года: картинка хранится внутри
проекта, размер снимка - по размеру картинки в макете и разрешению
вывода макета.
"""
from qgis.core import (Qgis, QgsLayoutItemPicture, QgsLayoutPoint,
                       QgsLayoutSize, QgsPrintLayout, QgsProject)
from qgis.PyQt.QtCore import QBuffer, QIODevice, QRectF, Qt
from qgis.PyQt.QtGui import QColor, QFont, QPainter, QTextDocument
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDialog,
                                 QDialogButtonBox, QDoubleSpinBox,
                                 QFileDialog, QFormLayout, QLabel,
                                 QPushButton, QSpinBox, QVBoxLayout)
from qgis.utils import iface

from ..core.snapshot import (MAX_SIDE, MIN_SIDE, PAGE_MARGIN, clamp_size,
                             file_ratio, fit_on_page, layout_pixels,
                             layout_ratio)
from ..i18n import tr
from ..qt_compat import enum, enum_int

NEW_LAYOUT = ""  # данные строки «Новый макет» в списке макетов
LAYOUT_NAME = "PlanetX"
PICTURE_ID = "PlanetX"
# Подпись источников в углу снимка, в логических пикселях.
ATTRIBUTION_FONT = 11
ATTRIBUTION_PAD = 4
# Формат картинки макета: в QGIS 4 областное имя, в QGIS 3 плоское.
if hasattr(Qgis, "PictureFormat"):
    RASTER = Qgis.PictureFormat.Raster
else:
    RASTER = getattr(QgsLayoutItemPicture, "FormatRaster")


def plain_text(html):
    """Текст подписи источников без разметки ссылок."""
    doc = QTextDocument()
    doc.setHtml(html)
    return doc.toPlainText().strip()


def draw_attribution(image, text, ratio):
    """Подпись источников в правом нижнем углу снимка, на месте."""
    if not text:
        return
    painter = QPainter(image)
    try:
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        painter.setRenderHint(enum(QPainter, "RenderHint",
                                   "TextAntialiasing"))
        font = QFont(painter.font())
        font.setPixelSize(max(6, int(round(ATTRIBUTION_FONT * ratio))))
        painter.setFont(font)
        pad = ATTRIBUTION_PAD * ratio
        # Длинная подпись переносится на следующие строки. Обрезка
        # многоточием теряла часть подписи Esri в узкой картинке макета.
        flags = enum_int(enum(Qt, "AlignmentFlag", "AlignRight")) \
            | enum_int(enum(Qt, "AlignmentFlag", "AlignBottom")) \
            | enum_int(enum(Qt, "TextFlag", "TextWordWrap"))
        room = QRectF(0.0, 0.0, image.width() - 4.0 * pad,
                      image.height() - 4.0 * pad)
        text_box = painter.boundingRect(room, flags, text)
        width = text_box.width() + 2.0 * pad
        height = text_box.height() + pad
        box = QRectF(image.width() - width - pad,
                     image.height() - height - pad, width, height)
        painter.setPen(enum(Qt, "PenStyle", "NoPen"))
        painter.setBrush(QColor(255, 255, 255, 190))
        painter.drawRoundedRect(box, 3.0 * ratio, 3.0 * ratio)
        painter.setPen(QColor(0, 0, 0))
        painter.drawText(box.adjusted(pad, 0.5 * pad, -pad, -0.5 * pad),
                         flags, text)
    finally:
        painter.end()


def embedded(image):
    """Путь картинки макета со встроенным PNG, как у встроенных
    картинок QGIS."""
    buffer = QBuffer()
    buffer.open(enum(QIODevice, "OpenModeFlag", "WriteOnly"))
    image.save(buffer, "PNG")
    return "base64:" + bytes(buffer.data().toBase64()).decode("ascii")


def new_layout(project):
    """Новый макет с листом по умолчанию и свободным именем."""
    manager = project.layoutManager()
    names = {layout.name() for layout in manager.layouts()}
    name, n = LAYOUT_NAME, 1
    while name in names:
        n += 1
        name = "{} {}".format(LAYOUT_NAME, n)
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName(name)
    manager.addLayout(layout)
    return layout


def page_size(layout):
    """Размер первого листа макета в мм."""
    size = layout.pageCollection().page(0).pageSize()
    return size.width(), size.height()


def insert_picture(layout, image, width_mm, height_mm):
    """Картинка вида на первом листе макета, в поле PAGE_MARGIN."""
    item = QgsLayoutItemPicture(layout)
    item.setId(PICTURE_ID)
    item.setPicturePath(embedded(image), RASTER)
    layout.addLayoutItem(item)
    item.attemptMove(QgsLayoutPoint(PAGE_MARGIN, PAGE_MARGIN))
    item.attemptResize(QgsLayoutSize(width_mm, height_mm))
    return item


class SnapshotDialog(QDialog):
    """Окно снимка вида. to_layout - картинка в макет, иначе в файл."""

    def __init__(self, window, to_layout, parent=None):
        super().__init__(parent or window)
        self.window = window
        self.view = window.view
        self.to_layout = to_layout
        self.path = None
        self.layout = None
        self.ratio = 1.0
        # Снимок начат этим окном. Сигналы вида слышат оба окна снимка.
        self.mine = False
        self.setWindowTitle(tr("Вид в макет") if to_layout
                            else tr("Снимок вида"))
        camera = self.view.camera
        self.aspect = camera.width / max(camera.height, 1)
        form = QFormLayout()
        self.size_text = QLabel(self)
        self.keep = QCheckBox(tr("Пропорции окна"), self)
        self.keep.setChecked(True)
        self.keep.setToolTip(tr(
            "Высота снимка следует за шириной в пропорциях окна глобуса. "
            "Без флажка снимок захватывает больше или меньше по сторонам, "
            "чем окно."))
        if to_layout:
            self._layout_fields(form)
        else:
            self._file_fields(form)
        form.addRow("", self.keep)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.start = QPushButton(tr("Вставить") if to_layout
                                 else tr("Сохранить…"), self)
        self.start.setToolTip(tr(
            "Глобус дорисовывает вид в нужном размере и ждёт загрузки "
            "подробных тайлов. Камера на это время стоит.") if to_layout
            else tr("Выбрать файл PNG или JPEG и снять вид в нём. "
                    "Глобус ждёт загрузки подробных тайлов, камера на это "
                    "время стоит."))
        self.now = QPushButton(tr("Снять сейчас"), self)
        self.now.setToolTip(tr(
            "Не ждать остальных тайлов. На снимке останутся менее "
            "подробные места."))
        self.now.setEnabled(False)
        self.stop = QPushButton(tr("Отмена"), self)
        buttons = QDialogButtonBox(self)
        role = enum(QDialogButtonBox, "ButtonRole", "ActionRole")
        for button in (self.start, self.now, self.stop):
            buttons.addButton(button, role)
        self.start.clicked.connect(self._start)
        self.now.clicked.connect(self.view.finish_shot)
        self.stop.clicked.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.size_text)
        layout.addWidget(self.status)
        layout.addWidget(buttons)
        self.view.shot_progress.connect(self._progress)
        self.view.shot_done.connect(self._done)
        self._update_size()

    # Поля.

    def _file_fields(self, form):
        camera = self.view.camera
        self.width_px = QSpinBox(self)
        self.height_px = QSpinBox(self)
        for box in (self.width_px, self.height_px):
            box.setRange(MIN_SIDE, MAX_SIDE)
            box.setSuffix(tr(" пикс."))
        self.width_px.setValue(min(2 * camera.width, MAX_SIDE))
        self.height_px.setValue(clamp_size(self.width_px.value(),
                                           self.width_px.value()
                                           / self.aspect)[1])
        self.width_px.setToolTip(tr(
            "Ширина снимка. Снимок шире окна берёт более подробные тайлы, "
            "надписи и линии на нём крупнее в той же доле."))
        self.height_px.setToolTip(tr(
            "Высота снимка. Угол обзора по вертикали тот же, что у окна."))
        self.width_px.valueChanged.connect(self._width_changed)
        self.height_px.valueChanged.connect(self._update_size)
        form.addRow(tr("Ширина"), self.width_px)
        form.addRow(tr("Высота"), self.height_px)

    def _layout_fields(self, form):
        project = QgsProject.instance()
        self.layouts = QComboBox(self)
        for layout in project.layoutManager().printLayouts():
            self.layouts.addItem(layout.name(), layout.name())
        self.layouts.addItem(tr("Новый макет"), NEW_LAYOUT)
        self.layouts.setToolTip(tr(
            "Макет, в первый лист которого ляжет картинка вида. Новый "
            "макет создаётся с листом по умолчанию."))
        self.width_mm = QDoubleSpinBox(self)
        self.height_mm = QDoubleSpinBox(self)
        for box in (self.width_mm, self.height_mm):
            box.setRange(10.0, 2000.0)
            box.setDecimals(1)
            box.setSuffix(tr(" мм"))
        self.width_mm.setToolTip(tr(
            "Ширина картинки на листе. Вместе с разрешением задаёт размер "
            "снимка в пикселях и подробность тайлов."))
        self.height_mm.setToolTip(tr(
            "Высота картинки на листе. Угол обзора по вертикали тот же, "
            "что у окна."))
        self.dpi = QSpinBox(self)
        self.dpi.setRange(72, 1200)
        self.dpi.setSuffix(tr(" dpi"))
        self.dpi.setToolTip(tr(
            "Разрешение вывода макета. Надписи на бумаге выходят того же "
            "размера, что на экране. Большое разрешение дольше грузит "
            "тайлы."))
        self.layouts.currentIndexChanged.connect(self._layout_chosen)
        self.width_mm.valueChanged.connect(self._width_changed)
        self.height_mm.valueChanged.connect(self._update_size)
        self.dpi.valueChanged.connect(self._update_size)
        form.addRow(tr("Макет"), self.layouts)
        form.addRow(tr("Ширина"), self.width_mm)
        form.addRow(tr("Высота"), self.height_mm)
        form.addRow(tr("Разрешение"), self.dpi)
        self._layout_chosen()

    def _chosen_layout(self):
        name = self.layouts.currentData()
        if not name:
            return None
        return QgsProject.instance().layoutManager().layoutByName(name)

    def _layout_chosen(self, *args):
        layout = self._chosen_layout()
        if layout is None:
            page, dpi = (297.0, 210.0), 300
        else:
            page, dpi = page_size(layout), layout.renderContext().dpi()
        width, height = fit_on_page(page[0], page[1], self.aspect)
        for box, value in ((self.width_mm, width), (self.height_mm, height),
                           (self.dpi, int(round(dpi)))):
            box.blockSignals(True)
            box.setValue(value)
            box.blockSignals(False)
        self._update_size()

    def _width_changed(self, *args):
        if self.keep.isChecked():
            if self.to_layout:
                self.height_mm.blockSignals(True)
                self.height_mm.setValue(self.width_mm.value() / self.aspect)
                self.height_mm.blockSignals(False)
            else:
                self.height_px.blockSignals(True)
                self.height_px.setValue(clamp_size(
                    self.width_px.value(),
                    self.width_px.value() / self.aspect)[1])
                self.height_px.blockSignals(False)
        self._update_size()

    def pixels(self):
        """Размер снимка в пикселях и масштаб надписей."""
        if self.to_layout:
            dpi = self.dpi.value()
            size = layout_pixels(self.width_mm.value(),
                                 self.height_mm.value(), dpi)
            return size, layout_ratio(dpi)
        size = clamp_size(self.width_px.value(), self.height_px.value())
        camera = self.view.camera
        return size, file_ratio(self.view.devicePixelRatioF(),
                                camera.width, size[0])

    def _update_size(self, *args):
        (width, height), _ = self.pixels()
        self.size_text.setText(tr("Снимок {width} × {height} пикселей",
                                  width=width, height=height))

    # Снимок.

    def _busy(self, busy):
        self.start.setEnabled(not busy)
        self.now.setEnabled(busy)
        for child in self.findChildren((QSpinBox, QDoubleSpinBox, QComboBox,
                                        QCheckBox)):
            child.setEnabled(not busy)

    def _start(self):
        if not self.to_layout:
            path, _ = QFileDialog.getSaveFileName(
                self, tr("Снимок вида"), "planetx.png",
                tr("Изображения (*.png *.jpg *.jpeg)"))
            if not path:
                return
            self.path = path
        (width, height), ratio = self.pixels()
        self.ratio = ratio
        if not self.view.start_shot(width, height, ratio):
            self.status.setText(tr("Глобус ещё не готов к снимку."))
            return
        self.mine = True
        self._busy(True)
        self.status.setText(tr("Загрузка тайлов для снимка…"))

    def _progress(self, missing):
        if not self.mine:
            return
        self.status.setText(tr("Снимок ждёт загрузки: {count}",
                               count=missing))

    def _done(self, image, complete):
        if not self.mine:
            return
        self.mine = False
        self._busy(False)
        if image is None:
            self.status.setText(tr(
                "Видеокарта не создала буфер такого размера. Уменьшите "
                "снимок."))
            return
        draw_attribution(image, plain_text(self.window.attribution.text()),
                         self.ratio)
        note = "" if complete else tr(
            " Часть тайлов не загрузилась, там менее подробный снимок.")
        if self.to_layout:
            layout = self._chosen_layout()
            if layout is None:
                layout = new_layout(QgsProject.instance())
            self.layout = layout
            insert_picture(layout, image, self.width_mm.value(),
                           self.height_mm.value())
            self.status.setText(tr("Картинка вставлена в макет «{name}».",
                                   name=layout.name()) + note)
            iface.openLayoutDesigner(layout)
            return
        if image.save(self.path):
            self.status.setText(tr("Снимок сохранён: {path}",
                                   path=self.path) + note)
        else:
            self.status.setText(tr("Не удалось записать {path}",
                                   path=self.path))

    def reject(self):
        """Закрытие окна бросает начатый снимок."""
        if self.mine:
            self.mine = False
            self._busy(False)
            self.view.cancel_shot()
        super().reject()
