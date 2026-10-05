# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Наложения картинок на глобусе: на поверхности, на экране, фото.

Картинка на поверхности становится растром QGIS по углам и рисуется
в наложении вместе со слоями проекта: ложится по рельефу так же, как
они. Углы-параллелограмм дают геопреобразование, прочие - привязку по
четырём точкам и пересчёт GDAL методом тонких пластин. Файлы растров
лежат в папке профиля PlanetX/overlays и пересоздаются при смене
картинки или углов.

Картинка на экране - подпись поверх вида, мышь проходит сквозь неё.
Фото - плоскость в 3D (core.overlays.photo_mesh), текстура - картинка.

Окно свойств наложения немодальное: название, описание, картинка,
непрозрачность, у картинки на экране - угол и размер. Углы картинки на
поверхности тянутся мышью, пока окно открыто, середин отрезков у них
нет.
"""
import glob
import hashlib
import os

import numpy as np
from qgis.core import QgsApplication, QgsRasterLayer
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QImage, QPixmap, QTransform
from qgis.PyQt.QtWidgets import (QApplication, QComboBox, QDialog,
                                 QDialogButtonBox,
                                 QDoubleSpinBox, QFileDialog, QFormLayout,
                                 QGraphicsOpacityEffect, QHBoxLayout, QLabel,
                                 QLineEdit, QPlainTextEdit, QPushButton,
                                 QSlider, QSpinBox)

from ..core import editing, overlays
from ..i18n import tr
from ..qt_compat import enum
from .handles import DrawVertices, PropVertices

IMAGE_SIDE = 4096  # пикселей, картинка фото больше уменьшается
# Угол картинки на экране: (overlayXY, screenXY) - доли вида.
CORNERS = (("top_left", (0.0, 1.0), (0.0, 1.0)),
           ("top_right", (1.0, 1.0), (1.0, 1.0)),
           ("bottom_left", (0.0, 0.0), (0.0, 0.0)),
           ("bottom_right", (1.0, 0.0), (1.0, 0.0)),
           ("center", (0.5, 0.5), (0.5, 0.5)))
MARGIN = 10  # пикселей от края вида у картинки на экране
OUTLINE = (255, 214, 0, 255)  # контур картинки, пока открыто её окно


def folder():
    """Папка файлов растров картинок на поверхности."""
    path = os.path.join(QgsApplication.qgisSettingsDirPath(), "PlanetX",
                        "overlays")
    os.makedirs(path, exist_ok=True)
    return path


def qimage(data):
    """Картинка из байтов или пустая QImage."""
    image = QImage()
    if data:
        image.loadFromData(data)
    return image


def image_rgba(data, side=IMAGE_SIDE):
    """Картинка для текстуры: массив (высота, ширина, 4) uint8, строки
    сверху вниз, или None."""
    image = qimage(data)
    if image.isNull():
        return None
    if max(image.width(), image.height()) > side:
        image = image.scaled(side, side, enum(Qt, "AspectRatioMode",
                                              "KeepAspectRatio"),
                             enum(Qt, "TransformationMode",
                                  "SmoothTransformation"))
    image = image.convertToFormat(enum(QImage, "Format",
                                       "Format_RGBA8888"))
    width, height, line = image.width(), image.height(), \
        image.bytesPerLine()
    bits = image.constBits()
    bits.setsize(line * height)
    rows = np.frombuffer(bits, dtype=np.uint8).reshape(height, line)
    return rows[:, :width * 4].reshape(height, width, 4).copy()


def _ext(data):
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"GIF":
        return "gif"
    return "jpg"


def ground_file(fid, overlay, data):
    """Файл растра VRT с привязкой картинки на поверхности по углам, или
    None, если GDAL картинку не прочёл. Имя - по картинке и углам, так
    одинаковый растр не пересоздаётся."""
    stamp = hashlib.sha256(data + repr(overlay.corners).encode(
        "ascii")).hexdigest()[:16]
    base = os.path.join(folder(), "{}_{}".format(fid, stamp))
    vrt = base + ".vrt"
    if os.path.exists(vrt):
        return vrt
    from osgeo import gdal
    source = base + "." + _ext(data)
    with open(source, "wb") as stream:
        stream.write(data)
    dataset = gdal.Open(source)
    if dataset is None:
        return None
    width, height = dataset.RasterXSize, dataset.RasterYSize
    dataset = None
    transform = overlays.affine(overlay.corners)
    if transform is not None:
        x0, a, b, y0, d, e = transform
        out = gdal.Translate(vrt, source, format="VRT",
                             outputSRS="EPSG:4326")
        if out is None:
            return None
        out.SetGeoTransform((x0, a / width, b / height, y0, d / width,
                             e / height))
        out = None
        return vrt
    (y_ll, x_ll), (y_lr, x_lr), (y_ur, x_ur), (y_ul, x_ul) = \
        overlay.corners
    points = [gdal.GCP(x_ul, y_ul, 0.0, 0.0, 0.0),
              gdal.GCP(x_ur, y_ur, 0.0, width, 0.0),
              gdal.GCP(x_lr, y_lr, 0.0, width, height),
              gdal.GCP(x_ll, y_ll, 0.0, 0.0, height)]
    marked = base + "_gcp.vrt"
    out = gdal.Translate(marked, source, format="VRT", GCPs=points,
                         outputSRS="EPSG:4326")
    if out is None:
        return None
    out = None
    out = gdal.Warp(vrt, marked, format="VRT", dstSRS="EPSG:4326",
                    tps=True, dstAlpha=True)
    if out is None:
        return None
    out = None
    return vrt


def ground_geotiff(fid, overlay, data, path):
    """Картинка на поверхности файлом GeoTIFF в WGS84 по её растру VRT,
    для слоя проекта QGIS. Возвращает, записан ли файл."""
    from osgeo import gdal
    vrt = ground_file(fid, overlay, data) if data else None
    if vrt is None:
        return False
    out = gdal.Translate(path, vrt, format="GTiff",
                         creationOptions=["COMPRESS=DEFLATE", "TILED=YES"])
    if out is None:
        return False
    out = None
    return os.path.exists(path)


class GroundLayers:
    """Растры QGIS картинок на поверхности, по одному на наложение."""

    def __init__(self):
        self._layers = {}  # (номер, картинка, углы) - растр
        # Начала имён файлов прежних растров тех же наложений. Картинка
        # по ссылке с обновлением давала бы новые файлы каждый раз.
        self._stale = set()
        self.errors = []

    def layers(self, entries):
        """Растры картинок, верхняя первой. entries - (метка картинки,
        номер наложения, название, core.overlays.Overlay, байты())."""
        wanted = {}
        self.errors = []
        # Прежние растры отпущены наложением окна после прошлого вызова.
        self._remove_stale()
        for token, fid, name, overlay, data in sorted(
                entries, key=lambda e: -e[3].order):
            key = (fid, token, tuple(overlay.corners), overlay.color)
            layer = self._layers.get(key)
            if layer is None:
                image = data()
                path = ground_file(fid, overlay, image) if image else None
                if path is None:
                    self.errors.append(name)
                    continue
                layer = QgsRasterLayer(path, name, "gdal")
                if not layer.isValid():
                    self.errors.append(name)
                    continue
                layer.renderer().setOpacity(overlay.color[3] / 255.0)
            wanted[key] = layer
        sources = {layer.source() for layer in wanted.values()}
        fids = {key[0] for key in wanted}
        for key, layer in self._layers.items():
            # Растр того же наложения с другой картинкой или углами.
            if key not in wanted and key[0] in fids \
                    and layer.source() not in sources:
                self._stale.add(os.path.splitext(layer.source())[0])
        self._layers = wanted
        return list(wanted.values())

    def _remove_stale(self):
        """Удалить файлы прежних растров. Файл, который ещё держит GDAL,
        остаётся до следующего вызова."""
        used = {os.path.splitext(layer.source())[0]
                for layer in self._layers.values()}
        for base in list(self._stale):
            if base in used:
                self._stale.discard(base)
                continue
            locked = []
            for path in glob.glob(glob.escape(base) + "*"):
                try:
                    os.remove(path)
                except OSError:
                    locked.append(path)
            if not locked:
                self._stale.discard(base)

    def clear(self):
        """Отпустить все растры."""
        self._layers = {}


class ScreenOverlays:
    """Картинки на экране поверх вида view."""

    def __init__(self, view):
        self.view = view
        self.labels = []
        self.items = []

    def set_items(self, items):
        """[(наложение, байты картинки)]: картинки по порядку рисования."""
        self.items = sorted(items, key=lambda pair: pair[0].order)
        for label in self.labels:
            label.deleteLater()
        self.labels = []
        for overlay, data in self.items:
            image = qimage(data)
            if image.isNull():
                continue
            label = QLabel(self.view)
            label.setAttribute(enum(Qt, "WidgetAttribute",
                                    "WA_TransparentForMouseEvents"))
            label.setStyleSheet("background: transparent;")
            label.image = image
            label.overlay = overlay
            effect = QGraphicsOpacityEffect(label)
            effect.setOpacity(overlay.color[3] / 255.0)
            label.setGraphicsEffect(effect)
            self.labels.append(label)
        self.place()

    def place(self):
        """Места картинок по размеру вида, после смены размера."""
        width, height = self.view.width(), self.view.height()
        for label in self.labels:
            overlay = label.overlay
            image = label.image
            x, y, w, h = overlays.screen_rect(
                overlay, width, height, image.width(), image.height())
            pixmap = QPixmap.fromImage(image).scaled(
                max(int(round(w)), 1), max(int(round(h)), 1),
                enum(Qt, "AspectRatioMode", "IgnoreAspectRatio"),
                enum(Qt, "TransformationMode", "SmoothTransformation"))
            if overlay.rotation:
                pixmap = pixmap.transformed(
                    QTransform().rotate(-overlay.rotation),
                    enum(Qt, "TransformationMode", "SmoothTransformation"))
            label.setPixmap(pixmap)
            label.resize(pixmap.size())
            label.move(int(round(x + (w - pixmap.width()) / 2.0)),
                       int(round(y + (h - pixmap.height()) / 2.0)))
            label.show()
            # Над картинкой вида, под панелью значков и шкалами.
            label.lower()


class CornerVertices(PropVertices):
    """Углы картинки на поверхности, пока открыто её окно свойств:
    четыре угла тянутся, новых вершин нет."""

    def middles(self):
        return []


def corner_of(overlay):
    """Ключ угла CORNERS картинки на экране по её точке привязки или
    "custom"."""
    for key, anchor, _ in CORNERS:
        if tuple(overlay.overlay_xy[:2]) == anchor:
            return key
    return "custom"


class BoxVertices(DrawVertices):
    """Ручки рамки картинки на поверхности, как у Google Earth: крест
    в середине сдвигает её, ромб над северной стороной поворачивает,
    углы и середины сторон растягивают от противоположного угла или
    стороны, с Shift - от середины."""

    def __init__(self, window, dialog):
        super().__init__(window)
        self.dialog = dialog
        self.handle = None

    def active(self):
        return self.dialog.isVisible() \
            and self.window.view.sky_view is None \
            and self.dialog.overlay.box is not None

    def _handles(self):
        corners, sides, centre, rotate = overlays.box_handles(
            self.dialog.overlay.box)
        return corners + [centre, rotate], sides

    def screen(self):
        points, sides = self._handles()
        return self._project(points) + self._project(sides)

    def grab(self, px, py):
        found = self.under(px, py)
        if found is None:
            return False
        kind, index = found
        if kind == editing.MIDDLE:
            self.handle = ("side", index)
        elif index < 4:
            self.handle = ("corner", index)
        else:
            self.handle = ("center" if index == 4 else "rotate", 0)
        self.index = index
        self._press = (px, py)
        self._moved = False
        self.hot = None
        return True

    def move(self, px, py):
        if self.handle is None:
            return
        found = self.window._ground(px, py)
        if found is None:
            return
        self._moved = True
        shift = QApplication.keyboardModifiers() & enum(
            Qt, "KeyboardModifier", "ShiftModifier")
        self.dialog.set_box(overlays.box_drag(
            self.dialog.overlay.box, self.handle[0], self.handle[1],
            found[0], found[1], centred=bool(shift)))

    def drop(self):
        self.handle = None
        self.index = None

    def hint(self):
        if self.hot is None:
            return ""
        kind, index = self.hot
        if kind == editing.MIDDLE:
            return tr("Растянуть сторону")
        if index == 4:
            return tr("Сдвинуть картинку")
        if index == 5:
            return tr("Повернуть картинку")
        return tr("Растянуть от угла, с Shift - от середины")


class OverlayDialog(QDialog):
    """Окно свойств наложения. Сигнал changed - правки для показа на
    глобусе сразу, в файл они идут по «OK». mode_changed - рамка
    картинки на поверхности стала четырьмя углами.

    Картинка хранится в файле меток или ссылкой на файл или адрес
    в сети, как поле «Link» Google Earth. image - байты новой картинки
    для файла меток, link - ссылка или None, если картинка в файле."""

    changed = pyqtSignal()
    mode_changed = pyqtSignal()

    def __init__(self, item, image, parent=None):
        super().__init__(parent)
        self.item = item
        self.overlay = overlays.from_params(item.kind, item.overlay.params(),
                                            item.overlay.corners)
        self.image = None
        self._image = image
        self.link = item.href if item.image is None and item.href else None
        titles = {"ground": tr("Картинка на поверхности"),
                  "screen": tr("Картинка на экране"),
                  "photo": tr("Фото")}
        self.setWindowTitle(titles[item.kind])
        form = QFormLayout(self)
        self.name = QLineEdit(item.name, self)
        self.name.setToolTip(tr("Название наложения в «Моих метках»."))
        form.addRow(tr("Название"), self.name)
        self.description = QPlainTextEdit(item.description, self)
        self.description.setFixedHeight(70)
        self.description.setToolTip(tr(
            "Описание наложения. Оно уходит в KML вместе с картинкой."))
        form.addRow(tr("Описание"), self.description)
        self.store = QComboBox(self)
        self.store.addItem(tr("В файле меток"), "file")
        self.store.addItem(tr("Ссылка на файл или адрес"), "link")
        self.store.setCurrentIndex(1 if self.link else 0)
        self.store.setToolTip(tr(
            "Где лежит картинка. В файле меток - копия внутри «Моих "
            "меток», она видна и без исходного файла. Ссылка - путь к "
            "файлу или адрес в сети, картинка читается при показе, правка "
            "файла видна на глобусе."))
        self.store.currentIndexChanged.connect(self._store_changed)
        form.addRow(tr("Хранение"), self.store)
        row = QHBoxLayout()
        self.path = QLineEdit(self.link or "", self)
        self.path.setPlaceholderText(tr("Путь к файлу или адрес http(s)"))
        self.path.setToolTip(tr(
            "Путь к файлу картинки или её адрес в сети. Картинка "
            "читается заново при каждом показе."))
        self.path.editingFinished.connect(self._path_edited)
        row.addWidget(self.path, 1)
        browse = QPushButton(tr("Обзор…"), self)
        browse.setToolTip(tr(
            "Выбрать файл картинки. В файле меток картинка заменяется "
            "копией, у ссылки меняется путь. Углы и положение остаются."))
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        form.addRow(tr("Картинка"), row)
        self.file = QLabel(self)
        form.addRow("", self.file)
        self.refresh = QSpinBox(self)
        self.refresh.setRange(0, 86400)
        self.refresh.setSingleStep(10)
        self.refresh.setSuffix(tr(" с"))
        self.refresh.setSpecialValueText(tr("не обновлять"))
        self.refresh.setValue(int(round(self.overlay.refresh)))
        self.refresh.setToolTip(tr(
            "Картинка по ссылке читается заново через этот промежуток, "
            "пока она видна. Так на глобусе стоит свежий снимок или "
            "карта, которую сервер или программа обновляет сама. Ноль - "
            "картинка читается при показе. Промежуток короче {low} с "
            "поднимается до {low} с.", low=int(overlays.MIN_REFRESH)))
        self.refresh.setKeyboardTracking(False)
        self.refresh.valueChanged.connect(self._refresh_edited)
        form.addRow(tr("Обновлять"), self.refresh)
        self.opacity = QSlider(enum(Qt, "Orientation", "Horizontal"), self)
        self.opacity.setRange(0, 100)
        self.opacity.setValue(int(round(self.overlay.color[3] / 2.55)))
        self.opacity.setToolTip(tr(
            "Непрозрачность картинки. У нуля сквозь неё виден снимок."))
        self.opacity.valueChanged.connect(self._opacity)
        form.addRow(tr("Непрозрачность"), self.opacity)
        if item.kind == "ground":
            self._ground_rows(form)
        if item.kind == "screen":
            self._screen_rows(form)
        buttons = QDialogButtonBox(
            enum(QDialogButtonBox, "StandardButton", "Ok")
            | enum(QDialogButtonBox, "StandardButton", "Cancel"), self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self._store_shown()
        self._show_file()

    # Место картинки на поверхности.

    def _ground_rows(self, form):
        self.edges = {}
        names = (("north", tr("Север")), ("south", tr("Юг")),
                 ("east", tr("Восток")), ("west", tr("Запад")),
                 ("rotation", tr("Поворот")))
        for key, text in names:
            spin = QDoubleSpinBox(self)
            if key == "rotation":
                spin.setRange(-180.0, 180.0)
                spin.setDecimals(2)
                spin.setSuffix("°")
                spin.setToolTip(tr(
                    "Поворот картинки вокруг середины против часовой "
                    "стрелки."))
            else:
                limit = 90.0 if key in ("north", "south") else 180.0
                spin.setRange(-limit, limit)
                spin.setDecimals(6)
                spin.setSuffix("°")
                spin.setToolTip(tr(
                    "Край рамки картинки в градусах. Рамка задана сторонами "
                    "света и поворотом, как LatLonBox в KML."))
            spin.setKeyboardTracking(False)
            spin.valueChanged.connect(self._edges_edited)
            form.addRow(text, spin)
            self.edges[key] = spin
        self.convert = QPushButton(tr("Перевести в четыре угла"), self)
        self.convert.setToolTip(tr(
            "Каждый угол картинки тянется мышью отдельно, картинка может "
            "стать неправильным четырёхугольником, как gx:LatLonQuad "
            "в KML. Обратно в рамку она не переводится."))
        self.convert.clicked.connect(self._to_corners)
        form.addRow(self.convert)
        self.hint = QLabel(self)
        self.hint.setWordWrap(True)
        form.addRow(self.hint)
        self._edges_shown()

    def _edges_shown(self):
        box = self.overlay.box
        for spin in self.edges.values():
            spin.setEnabled(box is not None)
        self.convert.setVisible(box is not None)
        self.hint.setText(
            tr("Крест в середине сдвигает картинку, ромб поворачивает, "
               "углы и середины сторон растягивают, с Shift - от "
               "середины.") if box is not None else
            tr("Углы картинки тянутся мышью на глобусе, пока окно "
               "открыто."))
        if box is None:
            return
        for spin in self.edges.values():
            spin.blockSignals(True)
        for key, value in zip(("north", "south", "east", "west",
                               "rotation"), box):
            self.edges[key].setValue(value)
        for spin in self.edges.values():
            spin.blockSignals(False)

    def _edges_edited(self, *args):
        if self.overlay.box is None:
            return
        self.overlay.set_box(tuple(self.edges[key].value() for key in (
            "north", "south", "east", "west", "rotation")))
        self.changed.emit()

    def set_box(self, box):
        """Новая рамка с ручек на глобусе."""
        self.overlay.set_box(box)
        self._edges_shown()
        self.changed.emit()

    def _to_corners(self):
        self.overlay.set_corners(self.overlay.corners)
        self._edges_shown()
        self.mode_changed.emit()
        self.changed.emit()

    # Картинка: в файле меток или ссылкой.

    def _store_shown(self):
        linked = self.store.currentData() == "link"
        self.path.setEnabled(linked)
        self.refresh.setEnabled(linked)

    def _refresh_edited(self, value):
        self.overlay.refresh = overlays.refresh_interval(value)
        self.changed.emit()

    def _store_changed(self, *args):
        linked = self.store.currentData() == "link"
        if linked:
            self.link = self.path.text().strip() or self.link or ""
        else:
            # Копия в файл меток - картинка, которая видна сейчас.
            if self.image is None and self._image:
                self.image = self._image
            self.link = None
        self._store_shown()
        self._show_file()
        self.changed.emit()

    def _path_edited(self):
        if self.store.currentData() != "link":
            return
        text = self.path.text().strip()
        if text != (self.link or ""):
            self.link = text
            self._image = None
            self.changed.emit()
            self._show_file()

    def _show_file(self):
        if self.store.currentData() == "link":
            self.file.setText(tr("по ссылке {link}", link=self.link)
                              if self.link else tr("ссылки нет"))
            return
        image = qimage(self.image or self._image)
        self.file.setText(tr("{w} × {h} пикселей", w=image.width(),
                             h=image.height()) if not image.isNull()
                          else tr("картинки нет"))

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Картинка наложения"), "",
            tr("Картинки (*.png *.jpg *.jpeg *.gif)"))
        if not path:
            return
        if self.store.currentData() == "link":
            self.path.setText(path)
            self._path_edited()
            return
        with open(path, "rb") as stream:
            data = stream.read()
        if qimage(data).isNull():
            return
        self.image = data
        self._show_file()
        self.changed.emit()

    def _opacity(self, value):
        color = list(self.overlay.color)
        color[3] = int(round(value * 2.55))
        self.overlay.color = tuple(color)
        self.changed.emit()

    # Картинка на экране.

    def _screen_rows(self, form):
        self.corner = QComboBox(self)
        names = {"top_left": tr("Левый верхний"),
                 "top_right": tr("Правый верхний"),
                 "bottom_left": tr("Левый нижний"),
                 "bottom_right": tr("Правый нижний"),
                 "center": tr("Середина")}
        for key, _, _ in CORNERS:
            self.corner.addItem(names[key], key)
        index = self.corner.findData(corner_of(self.overlay))
        if index >= 0:
            self.corner.setCurrentIndex(index)
        self.corner.setToolTip(tr("Угол вида, к которому прижата картинка."))
        self.corner.currentIndexChanged.connect(self._screen)
        form.addRow(tr("Место"), self.corner)
        self.size = QDoubleSpinBox(self)
        self.size.setRange(0.0, 100.0)
        self.size.setSuffix(" %")
        self.size.setDecimals(0)
        width = self.overlay.size
        self.size.setValue(width[0] * 100.0 if width[0] > 0
                           and width[2] == "fraction" else 0.0)
        self.size.setSpecialValueText(tr("свой размер"))
        self.size.setToolTip(tr(
            "Ширина картинки в долях ширины вида. Ноль - картинка своего "
            "размера в пикселях."))
        self.size.valueChanged.connect(self._screen)
        form.addRow(tr("Ширина"), self.size)

    def _screen(self, *args):
        key = self.corner.currentData()
        for name, anchor, place in CORNERS:
            if name == key:
                inset_x = 0.0 if place[0] == 0.5 else MARGIN
                inset_y = 0.0 if place[1] == 0.5 else MARGIN
                x_units = "fraction" if place[0] == 0.5 else (
                    "pixels" if place[0] == 0.0 else "insetPixels")
                y_units = "fraction" if place[1] == 0.5 else (
                    "pixels" if place[1] == 0.0 else "insetPixels")
                self.overlay.overlay_xy = (anchor[0], anchor[1], "fraction",
                                           "fraction")
                self.overlay.screen_xy = (
                    place[0] if x_units == "fraction" else inset_x,
                    place[1] if y_units == "fraction" else inset_y,
                    x_units, y_units)
        share = self.size.value() / 100.0
        self.overlay.size = (share, 0.0, "fraction", "fraction") if share \
            else (-1.0, -1.0, "fraction", "fraction")
        self.changed.emit()

    # Четыре угла - протокол окна свойств метки для PropVertices.

    @property
    def points(self):
        return list(self.overlay.corners)

    def set_points(self, points):
        self.overlay.set_corners(points)
        self.changed.emit()

    def values(self):
        """Поля файла по «OK»."""
        return {"name": self.name.text(),
                "description": self.description.toPlainText()}
