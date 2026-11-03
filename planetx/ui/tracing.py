# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Трассировка участка: окно «Трассировка» подменю «Анализ участка».

Просьба автора от 3 ноября 2026 года - векторизация снимка по цветам,
как «Векторизация растра» Inkscape, по сообщению Василия Швалёва.
Источник, участок, сетка и показ - те же, что у классификации
(ui/aefclass.py), только растр проекта или подложка глобуса. Ядро -
core/tracing.py. На глобусе - цвета клеток, OK записывает гладкие
многоугольники областей слоем GeoPackage в подгруппу расчёта.
"""
from qgis.core import QgsProject, QgsSettings
from qgis.PyQt.QtCore import QObject, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                                 QDoubleSpinBox,
                                 QFormLayout, QLabel, QPushButton, QSpinBox,
                                 QVBoxLayout)

from ..core import aef, rasterclass, segments, tracing
from ..i18n import tr
from ..qt_compat import enum
from .aef import _poll_job, _run_job, stop_point
from .aefclass import (AUTO, BASEMAP, RASTER_SIDE, ClassTiles, SourceBox,
                       fill_pixels, pixel_text, problem_text, raster_reader,
                       set_credit)
from .area import Area
from .inset import warm
from .results import (Session, accepted, add_vector, built_text,
                      keep_buttons, result_path)
from .sitelayer import SiteTool, result_level
from .viewshed import fit_status

SETTINGS = "PlanetX/tracing/"
OPACITY = 0.8  # непрозрачность цветов на глобусе - выбор помощника


class TraceSource(SourceBox):
    """Источники трассировки: подложка глобуса и растры проекта - у
    эмбеддингов AlphaEarth цвета нет."""

    def refill(self):
        super().refill()
        empty = self.findData("")
        if empty >= 0:
            self.blockSignals(True)
            self.removeItem(empty)
            self.blockSignals(False)
            self.currentIndexChanged.emit(self.currentIndex())


class TraceDialog(QDialog):
    """Окно «Трассировка». Сигнал build - «Построить». OK записывает
    многоугольники в проект QGIS, «Отмена» убирает показ."""

    build = pyqtSignal()

    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle(tr("Трассировка"))
        self.point = None
        settings = QgsSettings()
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.source = TraceSource(self)
        self.source.setToolTip(tr(
            "Снимок, который раскладывается на цвета. Подложка глобуса - "
            "картинка текущей подложки под участком, растр проекта - его "
            "каналы, первые три дают цвета слоя."))
        self.area = Area(window, self, 1.0, RASTER_SIDE, SETTINGS + "side")
        self.level = QComboBox(self)
        self.wanted_pixel = int(settings.value(SETTINGS + "pixel", AUTO))
        fill_pixels(self.level, True, self.wanted_pixel)
        self.level.setToolTip(tr(
            "Пиксель сетки участка. «Авто» берёт пиксель растра или "
            "верхнего уровня подложки, если на участке клеток не больше "
            "640 тысяч. Трассировка принимает до 4 млн клеток."))
        self.volume = QLabel(self)
        self.volume.setWordWrap(True)
        self.colors = QSpinBox(self)
        self.colors.setRange(2, 32)
        self.colors.setValue(int(settings.value(SETTINGS + "colors",
                                                tracing.COLORS)))
        self.colors.setToolTip(tr(
            "На сколько цветов раскладывается снимок. Больше цветов - "
            "подробнее области и больше многоугольников."))
        self.smooth = QSpinBox(self)
        self.smooth.setRange(0, 5)
        self.smooth.setValue(int(settings.value(SETTINGS + "smooth",
                                                tracing.SMOOTH)))
        self.smooth.setToolTip(tr(
            "Проходов сглаживания снимка окном 3 × 3 перед раскладкой на "
            "цвета. Сглаживание убирает шум, границы выходят ровнее, мелкие "
            "детали пропадают."))
        self.least = QSpinBox(self)
        self.least.setRange(1, 100000)
        self.least.setValue(int(settings.value(SETTINGS + "least",
                                               tracing.LEAST)))
        self.least.setToolTip(tr(
            "Область меньше этого количества клеток сливается с соседом по "
            "самой длинной общей границе."))
        self.corner = QDoubleSpinBox(self)
        self.corner.setRange(0.0, 1.33)
        self.corner.setSingleStep(0.05)
        self.corner.setDecimals(2)
        self.corner.setValue(float(settings.value(SETTINGS + "corner",
                                                  tracing.CORNER)))
        self.corner.setToolTip(tr(
            "Скругление углов контуров, как у Potrace. 0 - одни углы, "
            "ломаная. Чем больше, тем больше углов становится плавными "
            "дугами."))
        form = QFormLayout()
        form.addRow(tr("Источник"), self.source)
        form.addRow(tr("Участок"), self.area.widget)
        form.addRow(tr("Пиксель"), self.level)
        form.addRow("", self.volume)
        form.addRow(tr("Цветов"), self.colors)
        form.addRow(tr("Сглаживание снимка"), self.smooth)
        form.addRow(tr("Наименьшая область, клеток"), self.least)
        form.addRow(tr("Скругление углов"), self.corner)
        hint = QLabel(tr(
            "На глобусе - цвета клеток участка. OK записывает гладкие "
            "многоугольники областей в проект, у соседних областей граница "
            "общая."), self)
        hint.setWordWrap(True)
        buttons = QDialogButtonBox(self)
        run = QPushButton(tr("Построить"), self)
        run.setDefault(True)
        run.setToolTip(tr(
            "Снимок участка раскладывается на цвета, области одного цвета "
            "обводятся гладкими контурами."))
        run.clicked.connect(self.build)
        buttons.addButton(run, enum(QDialogButtonBox, "ButtonRole",
                                    "ActionRole"))
        self.to_project = keep_buttons(self, buttons)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addWidget(self.status)
        layout.addWidget(buttons)
        fit_status(self, layout)
        self.source.currentIndexChanged.connect(lambda _: self._volume())
        self.level.currentIndexChanged.connect(lambda _: self._pixel())
        self.area.changed.connect(self._volume)
        for box in (self.colors, self.smooth, self.least, self.corner):
            box.valueChanged.connect(lambda _: self._remember())
        self.to_project.setEnabled(False)

    def raster_id(self):
        return self.source.currentData() or ""

    def raster(self):
        return QgsProject.instance().mapLayer(self.raster_id())

    def _pixel(self):
        self.wanted_pixel = self.level.currentData()
        self._remember()
        self._volume()

    def _volume(self):
        source = self.raster_id()
        layer = None if source == BASEMAP else self.raster()
        if not source or self.point is None or self.area.check() \
                or (source != BASEMAP and layer is None):
            self.volume.setText("")
            return
        self.volume.setText(pixel_text(
            self.area.window, source, layer, self.level.currentData(),
            self.area.box(), self.area.size()))

    def _remember(self):
        settings = QgsSettings()
        settings.setValue(SETTINGS + "pixel", self.wanted_pixel)
        settings.setValue(SETTINGS + "colors", self.colors.value())
        settings.setValue(SETTINGS + "smooth", self.smooth.value())
        settings.setValue(SETTINGS + "least", self.least.value())
        settings.setValue(SETTINGS + "corner", self.corner.value())


class TraceTool(SiteTool, QObject):
    """Трассировка участка у окна глобуса."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.dialog = None
        self.tiles = None
        self.result = None
        self.grid = None  # (ключ сетки, сетка) - смена настроек без загрузки
        self.job = None
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(lambda: _poll_job(self))
        self.session = Session(window, tr("Трассировка"))

    @property
    def legend_title(self):
        return tr("Трассировка")

    def open_here(self, lat, lon):
        dialog = self.dialog
        if dialog is None:
            dialog = TraceDialog(self.window)
            dialog.build.connect(self.build)
            dialog.finished.connect(self._closed)
            self.dialog = dialog
        dialog.source.refill()
        dialog.point = (lat, lon)
        dialog.status.setText("")
        dialog.show()
        dialog.raise_()
        dialog.area.open_at(lat, lon)
        dialog._volume()
        self.window._refresh_shapes()
        return dialog

    def _closed(self, code=0):
        if accepted(code) and self.result is not None:
            self.export()
        self.clear()
        self.session.reset()
        self.dialog.area.end()

    # --- расчёт ---------------------------------------------------------

    def build(self):
        dialog = self.dialog
        if dialog is None or dialog.point is None or self.job is not None:
            return
        layer = dialog.raster()
        if dialog.raster_id() != BASEMAP and layer is None:
            dialog.status.setText(tr("Растра больше нет в проекте."))
            return
        problem = dialog.area.check()
        if problem:
            dialog.status.setText(problem)
            return
        ring = list(dialog.area.ring)
        box = dialog.area.box()
        side = dialog.area.size()
        lat, lon = dialog.point
        zone = aef.zone_of(lon, lat)
        reader = raster_reader(self, layer, box, side,
                               dialog.level.currentData())
        if reader is None:
            return
        read, key, name, credit = reader
        cached = self.grid if self.grid and self.grid[0] == key else None
        colors, smooth = dialog.colors.value(), dialog.smooth.value()
        least, corner = dialog.least.value(), dialog.corner.value()

        def work():
            index = aef.ZoneIndex(zone, [])
            found = cached[1] if cached else read(index)
            if isinstance(found, str):
                return {"problem": found}
            stop_point(self)
            x0, y0, step, grid = found
            inside = aef.ring_mask(index, x0, y0, step, grid.shape[1:], ring)
            good = rasterclass.usable(grid) & inside
            if not good.any():
                return {"problem": "outside", "found": found}
            if segments.too_big(*good.shape):
                return {"problem": "pieces", "found": found}
            out = tracing.trace(grid, good, colors, smooth, least, corner,
                                progress=lambda: stop_point(self))
            return dict(out, index=index, found=found)

        dialog.status.setText(tr("Снимок раскладывается на цвета…"))
        _run_job(self, work, lambda out: self._built(
            out, key, box, name, ring, credit), tr("Трассировка"))

    def _built(self, out, key, box, raster, ring, credit=None):
        dialog = self.dialog
        if out is None:
            dialog.status.setText(tr("Для участка нет данных."))
            return
        if out.get("found") is not None:
            self.grid = (key, out["found"])
        if out.get("problem"):
            dialog.status.setText(problem_text(out["problem"]))
            return
        x0, y0, step, _ = out["found"]
        colors = tracing.display_colors(out["centers"])
        names = ["#%02x%02x%02x" % rgb for rgb in colors]
        self.result = {"index": out["index"], "x0": x0, "y0": y0,
                       "step": step, "box": box, "classes": out["classes"],
                       "kinds": out["kinds"], "shapes": out["shapes"],
                       "colors": colors, "names": names, "raster": raster,
                       "credit": credit, "ring": ring}
        dialog.status.setText(tr(
            "Цветов {colors}, областей {regions}.",
            colors=len(colors), regions=len(out["shapes"]))
            + " " + built_text())
        dialog.to_project.setEnabled(bool(out["shapes"]))
        self.show()

    # --- показ ----------------------------------------------------------

    def show(self):
        if self.result is None:
            self._drop_tiles()
            return
        self.put_tiles(ClassTiles(self.result, parent=self),
                       result_level(self.result), OPACITY)

    def forget(self):
        self.result = None
        if self.dialog is not None:
            self.dialog.to_project.setEnabled(False)

    # --- выгрузка -------------------------------------------------------

    def export(self, path=None):
        """Многоугольники областей слоем traced GeoPackage в подгруппу
        расчёта: поля cls (номер цвета с 1), color и area_ha."""
        result = self.result
        if result is None or not result["shapes"]:
            return None
        path = path or result_path("tracing", ".gpkg")
        if not write_traced(path, result):
            self.dialog.status.setText(tr("Слой не записан в «{path}».",
                                          path=path))
            return None
        group = self.session.group_for(result["ring"])
        values = [(n + 1, rgb, name) for n, (rgb, name) in enumerate(
            zip(result["colors"], result["names"]))]
        layer = add_vector(self.window, path, "traced",
                           tr("Трассировка {source}",
                              source=result["raster"] or ""),
                           group, (0, 0, 0), width=0.0,
                           classes=("cls", values))
        if layer is not None:
            _stroke_as_fill(layer)
            set_credit(layer, result)
        return path

    def close(self):
        self.timer.stop()
        self._drop_tiles()
        if self.dialog is not None:
            self.dialog.close()


def _stroke_as_fill(layer):
    """Контур области - цветом её заливки: соседние области без чёрных
    линий между ними."""
    renderer = layer.renderer()
    if not hasattr(renderer, "categories"):
        return
    for n, category in enumerate(renderer.categories()):
        symbol = category.symbol().clone()
        part = symbol.symbolLayer(0)
        if hasattr(part, "setStrokeColor"):
            part.setStrokeColor(symbol.color())
            part.setStrokeWidth(0.1)
        renderer.updateCategorySymbol(n, symbol)
    layer.triggerRepaint()


def write_traced(path, result):
    """Многоугольники трассировки файлом GeoPackage в UTM. Кольца - углы
    клеток сетки результата, неверный многоугольник чинит MakeValid."""
    from osgeo import gdal, ogr, osr
    warm()
    # IsValid пишет о самопересечении предупреждением GDAL, кольцо
    # чинится ниже.
    gdal.PushErrorHandler("CPLQuietErrorHandler")
    try:
        return _write_traced(path, result)
    finally:
        gdal.PopErrorHandler()


def _write_traced(path, result):
    from osgeo import ogr, osr
    index = result["index"]
    srs = osr.SpatialReference()
    srs.ImportFromEPSG((32700 if index.south else 32600) + index.number)
    data = ogr.GetDriverByName("GPKG").CreateDataSource(path)
    if data is None:
        return False
    layer = data.CreateLayer("traced", srs, ogr.wkbMultiPolygon)
    for name, kind in (("cls", ogr.OFTInteger), ("color", ogr.OFTString),
                       ("area_ha", ogr.OFTReal)):
        layer.CreateField(ogr.FieldDefn(name, kind))
    x0, y0, step = result["x0"], result["y0"], result["step"]
    defn = layer.GetLayerDefn()
    layer.StartTransaction()
    for region, (outer, holes) in result["shapes"].items():
        polygon = ogr.Geometry(ogr.wkbPolygon)
        for points in [outer] + list(holes):
            ring = ogr.Geometry(ogr.wkbLinearRing)
            for x, y in points:
                ring.AddPoint_2D(x0 + x * step, y0 - y * step)
            ring.CloseRings()
            polygon.AddGeometry(ring)
        if not polygon.IsValid():
            polygon = polygon.MakeValid()
            if polygon is None:
                continue
        shape = ogr.ForceToMultiPolygon(polygon)
        kind = int(result["kinds"][region])
        feature = ogr.Feature(defn)
        feature.SetGeometry(shape)
        feature.SetField("cls", kind + 1)
        feature.SetField("color", result["names"][kind])
        feature.SetField("area_ha", shape.GetArea() / 1e4)
        layer.CreateFeature(feature)
    layer.CommitTransaction()
    data = None
    return True
