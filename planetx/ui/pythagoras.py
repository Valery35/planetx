# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Проект Pythagoras (.pyt) в проект QGIS: окно, запись GeoPackage
слоями по слоям Pythagoras и видам геометрии, группа в дереве слоёв."""
import os

from qgis.core import (Qgis, QgsApplication, QgsCoordinateReferenceSystem,
                       QgsCoordinateTransform, QgsCsException,
                       QgsMarkerSymbol,
                       QgsPalLayerSettings, QgsProject, QgsRectangle,
                       QgsSingleSymbolRenderer, QgsVectorLayer,
                       QgsVectorLayerSimpleLabeling)
from qgis.gui import QgsCustomDropHandler, QgsProjectionSelectionWidget
from qgis.PyQt.QtCore import QSettings, Qt, pyqtSignal
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (QApplication, QCheckBox, QDialog,
                                 QDialogButtonBox, QFileDialog, QFormLayout,
                                 QFrame, QHBoxLayout, QHeaderView, QLabel,
                                 QLineEdit, QMessageBox, QPushButton,
                                 QTreeWidget, QTreeWidgetItem, QVBoxLayout)

from ..core import pythagoras
from ..i18n import tr
from ..qt_compat import enum
from .inset import warm

KEY = "PlanetX/pythagoras/"
SUFFIX = {"point": "points", "line": "lines", "polygon": "polygons",
          "text": "texts"}
LAYER_ROLE = enum(Qt, "ItemDataRole", "UserRole")
CHECKABLE = enum(Qt, "ItemFlag", "ItemIsUserCheckable")
CHECKED = enum(Qt, "CheckState", "Checked")
UNCHECKED = enum(Qt, "CheckState", "Unchecked")


def layer_title(names, number):
    """Имя слоя Pythagoras по номеру, без имени - «Слой N»."""
    return names.get(number) or tr("Слой {n}", n=number)


def _safe(name):
    for char in '\\/:*?"<>|':
        name = name.replace(char, "_")
    return name.strip() or "layer"


def write_gpkg(path, names, feats, wkt):
    """Объекты в файл GeoPackage path: слой на пару «слой Pythagoras,
    вид геометрии». Главный поток. Возвращает список (имя слоя
    Pythagoras, имя слоя GeoPackage, вид) или None при ошибке GDAL."""
    from osgeo import ogr, osr
    warm()
    geom = {"point": ogr.wkbPoint25D, "line": ogr.wkbLineString,
            "polygon": ogr.wkbPolygon, "text": ogr.wkbPoint}
    groups = {}
    for f in feats:
        groups.setdefault((layer_title(names, f["layer"]), f["kind"]),
                          []).append(f)
    driver = ogr.GetDriverByName("GPKG")
    if os.path.exists(path):
        driver.DeleteDataSource(path)
    out = driver.CreateDataSource(path)
    if out is None:
        return None
    srs = osr.SpatialReference()
    srs.ImportFromWkt(wkt)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    made = []
    for (name, kind), items in sorted(groups.items()):
        lname = _safe("{}_{}".format(name, SUFFIX[kind]))
        layer = out.CreateLayer(lname, srs, geom[kind])
        fields = [("ObjectId", ogr.OFTInteger), ("layer", ogr.OFTString),
                  ("code", ogr.OFTString), ("color", ogr.OFTInteger)]
        fields += {"point": [("z", ogr.OFTReal), ("symbol", ogr.OFTInteger)],
                   "polygon": [("area", ogr.OFTReal)],
                   "text": [("text", ogr.OFTString)]}.get(kind, [])
        for fname, ftype in fields:
            layer.CreateField(ogr.FieldDefn(fname, ftype))
        defn = layer.GetLayerDefn()
        layer.StartTransaction()
        for f in items:
            row = ogr.Feature(defn)
            row.SetField("ObjectId", int(f["id"]))
            row.SetField("layer", name)
            if f.get("code"):
                row.SetField("code", f["code"])
            if f.get("color") is not None:
                row.SetField("color", int(f["color"]))
            if kind == "point":
                if f.get("z") is not None:
                    row.SetField("z", float(f["z"]))
                row.SetField("symbol", int(f["symbol"]))
            if kind == "polygon" and f.get("area") is not None:
                row.SetField("area", float(f["area"]))
            if kind == "text" and f.get("text"):
                row.SetField("text", f["text"])
            row.SetGeometry(_geometry(ogr, kind, f))
            layer.CreateFeature(row)
        layer.CommitTransaction()
        made.append((name, lname, kind))
    out = None
    return made


def _geometry(ogr, kind, f):
    pts = f["coords"]
    if kind == "point":
        g = ogr.Geometry(ogr.wkbPoint25D)
        g.AddPoint(pts[0][0], pts[0][1], float(f.get("z") or 0.0))
        return g
    if kind == "text":
        g = ogr.Geometry(ogr.wkbPoint)
        g.AddPoint_2D(pts[0][0], pts[0][1])
        return g
    line = ogr.Geometry(ogr.wkbLinearRing if kind == "polygon"
                        else ogr.wkbLineString)
    for x, y in pts:
        line.AddPoint_2D(x, y)
    if kind == "line":
        return line
    line.CloseRings()
    poly = ogr.Geometry(ogr.wkbPolygon)
    poly.AddGeometry(line)
    return poly


def drop_group(title):
    """Убрать из проекта группу прежней выгрузки, иначе QGIS держит
    файл GeoPackage открытым и записать его заново нельзя."""
    project = QgsProject.instance()
    root = project.layerTreeRoot()
    group = root.findGroup(title)
    if group is None:
        return
    project.removeMapLayers(group.findLayerIds())
    root.removeChildNode(group)


def kind_name(kind):
    return {"point": tr("точки"), "line": tr("линии"),
            "polygon": tr("площади"), "text": tr("надписи")}[kind]


def readable(name):
    """Имя слоя Pythagoras для дерева слоёв - подчёркивания пробелами."""
    return " ".join(name.replace("_", " ").split()) or name


def add_to_project(path, title, made):
    """Слои файла path группой title вверху дерева, внутри - группы
    по слоям Pythagoras. Надписи подписаны полем text. Слой назван
    «Имя слоя - вид», так он узнаётся и в списке слоёв глобуса.
    Возвращает номера слоёв и их общий охват."""
    project = QgsProject.instance()
    top = project.layerTreeRoot().insertGroup(0, title)
    groups = {}
    ids = []
    extent = QgsRectangle()
    for name, lname, kind in made:
        shown = "{} - {}".format(readable(name), kind_name(kind))
        layer = QgsVectorLayer("{}|layername={}".format(path, lname),
                               shown, "ogr")
        if not layer.isValid():
            continue
        if kind == "text":
            _label(layer)
        project.addMapLayer(layer, False)
        group = groups.get(name)
        if group is None:
            group = groups[name] = top.addGroup(readable(name))
        group.addLayer(layer)
        ids.append(layer.id())
        if not layer.extent().isEmpty():
            extent.combineExtentWith(layer.extent())
    return ids, extent


def show_result(ids, extent, crs):
    """Карта QGIS и открытое окно глобуса - к новым слоям."""
    from qgis.utils import iface
    if extent.isEmpty():
        return
    if iface is not None:
        canvas = iface.mapCanvas()
        transform = QgsCoordinateTransform(
            crs, canvas.mapSettings().destinationCrs(),
            QgsProject.instance())
        try:
            box = transform.transformBoundingBox(extent)
        except QgsCsException:
            box = None
        if box is not None and not box.isEmpty():
            box.scale(1.1)
            canvas.setExtent(box)
            canvas.refresh()
    for widget in QApplication.topLevelWidgets():
        if hasattr(widget, "show_added_layers") and widget.isVisible():
            widget.show_added_layers(ids, extent, crs)


def _label(layer):
    symbol = QgsMarkerSymbol.createSimple({"size": "0.6",
                                           "color": "60,60,60"})
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    settings = QgsPalLayerSettings()
    settings.fieldName = "text"
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


ICON = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                    "pythagoras.svg")
COLUMNS = ("point", "line", "polygon", "text")
# Пример - выдуманный карьер у Березников (tools/make_pyt_demo.py),
# координаты UTM 40N.
DEMO = os.path.join(os.path.dirname(os.path.dirname(__file__)), "demo",
                    "pythagoras", "quarry.pyt")
DEMO_CRS = "EPSG:32640"
_dialog = None


def icon():
    """Значок проекта Pythagoras для меню и кнопок."""
    return QIcon(ICON)


def show_dialog(parent=None, path=None):
    """Окно «Проект Pythagoras», одно на QGIS. path - файл .pyt,
    который сразу читается, например брошенный в окно QGIS."""
    global _dialog
    try:
        alive = _dialog is not None and _dialog.isVisible() is not None
    except RuntimeError:
        alive = False
    if not alive:
        _dialog = PythagorasDialog(parent)
    if path:
        _dialog.open_file(path)
    _dialog.show()
    _dialog.raise_()
    _dialog.activateWindow()
    return _dialog


def is_pyt(path):
    return bool(path) and path.lower().endswith(".pyt") \
        and os.path.isfile(path)


class PytDropHandler(QgsCustomDropHandler):
    """Файл .pyt, брошенный в окно QGIS, открывает окно «Проект
    Pythagoras» с этим файлом."""

    def handleFileDrop(self, path):
        if not is_pyt(path):
            return False
        from qgis.utils import iface
        show_dialog(iface.mainWindow() if iface else None, path)
        return True


class DropBox(QFrame):
    """Поле файла: перетаскивание .pyt или кнопка выбора."""

    dropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setObjectName("pytDrop")
        self._style(False)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        self.text = QLabel(self)
        self.text.setWordWrap(True)
        self.text.setTextFormat(enum(Qt, "TextFormat", "RichText"))
        lay.addWidget(self.text, 1)
        buttons = QVBoxLayout()
        self.pick = QPushButton(tr("Выбрать файл…"), self)
        buttons.addWidget(self.pick)
        self.demo = QPushButton(tr("Открыть пример"), self)
        self.demo.setToolTip(tr(
            "Выдуманный карьер у Березников - уступы, отвал, дорога, "
            "опорные пункты и подписи. Система координат ставится сама."))
        buttons.addWidget(self.demo)
        lay.addLayout(buttons)
        self.show_file(None)

    def _style(self, hover):
        self.setStyleSheet(
            "#pytDrop {border: 2px dashed %s; border-radius: 8px; "
            "background: %s;}" % (("#1e88e5", "rgba(30,136,229,30)")
                                  if hover else ("#9e9e9e", "transparent")))

    def show_file(self, path, info=None):
        if not path:
            self.text.setText(tr(
                "Перетащите сюда файл <b>.pyt</b> из проводника "
                "или нажмите «Выбрать файл…»."))
            return
        size = os.path.getsize(path) / 1048576.0 if os.path.isfile(path) \
            else 0.0
        line = "<b>{}</b> &nbsp;<span style='color:gray'>{}</span>" \
            .format(os.path.basename(path),
                    tr("{size} МБ", size="{:.1f}".format(size)))
        if info:
            line += "<br>" + info
        self.text.setText(line)

    def _accepts(self, event):
        urls = event.mimeData().urls() if event.mimeData() else []
        return any(is_pyt(u.toLocalFile()) for u in urls)

    def dragEnterEvent(self, event):
        if self._accepts(event):
            self._style(True)
            event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._style(False)

    def dropEvent(self, event):
        self._style(False)
        for url in event.mimeData().urls():
            if is_pyt(url.toLocalFile()):
                event.acceptProposedAction()
                self.dropped.emit(url.toLocalFile())
                return


class PythagorasDialog(QDialog):
    """Окно «Проект Pythagoras»: файл, слои с количеством объектов,
    система координат, папка результата."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Проект Pythagoras"))
        self.setWindowIcon(icon())
        self.setMinimumSize(620, 560)
        self.setAcceptDrops(True)
        self.source = ""
        self.names = {}
        self.feats = []
        self.lost = 0
        settings = QSettings()
        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        head = QHBoxLayout()
        picture = QLabel(self)
        picture.setPixmap(icon().pixmap(56, 56))
        head.addWidget(picture, 0, enum(Qt, "AlignmentFlag", "AlignTop"))
        title = QLabel(self)
        title.setWordWrap(True)
        title.setTextFormat(enum(Qt, "TextFormat", "RichText"))
        title.setText("<span style='font-size:15pt; font-weight:600'>{}"
                      "</span><br>{}".format(
                          tr("Проект Pythagoras в QGIS"),
                          tr("Файл .pyt читается напрямую, без DXF и SHP. "
                             "Каждый слой Pythagoras становится слоями "
                             "точек, линий, площадей и надписей "
                             "в GeoPackage и группой в проекте.")))
        head.addWidget(title, 1)
        lay.addLayout(head)

        lay.addWidget(self._step(1, tr("Файл проекта - свой или пример")))
        self.drop = DropBox(self)
        self.drop.pick.clicked.connect(self._pick_file)
        self.drop.dropped.connect(self.open_file)
        self.drop.demo.clicked.connect(self.open_demo)
        lay.addWidget(self.drop)

        lay.addWidget(self._step(2, tr("Слои, которые нужны в QGIS")))
        self.table = QTreeWidget(self)
        self.table.setRootIsDecorated(False)
        self.table.setAlternatingRowColors(True)
        self.table.setHeaderLabels([tr("Слой Pythagoras"), tr("Точки"),
                                    tr("Линии"), tr("Площади"),
                                    tr("Надписи")])
        self.table.setToolTip(tr(
            "Слои файла и количество объектов в них. Флажок решает, "
            "попадёт ли слой в проект."))
        header = self.table.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, enum(QHeaderView, "ResizeMode",
                                            "Stretch"))
        for column in range(1, 5):
            header.setSectionResizeMode(column, enum(
                QHeaderView, "ResizeMode", "ResizeToContents"))
        self.table.itemChanged.connect(lambda *_: self._totals())
        lay.addWidget(self.table, 1)
        marks = QHBoxLayout()
        self.total = QLabel(self)
        marks.addWidget(self.total, 1)
        links = QLabel("<a href='all'>{}</a> &nbsp; <a href='none'>{}</a>"
                       .format(tr("Все"), tr("Ни одного")), self)
        links.linkActivated.connect(lambda key: self._mark_all(key == "all"))
        marks.addWidget(links)
        lay.addLayout(marks)

        lay.addWidget(self._step(3, tr("Система координат и папка "
                                       "результата")))
        form = QFormLayout()
        self.crs = QgsProjectionSelectionWidget(self)
        self.crs.setToolTip(tr(
            "Система координат проекта Pythagoras. В файле .pyt её нет, "
            "она задаётся здесь и записывается в GeoPackage."))
        saved = QgsCoordinateReferenceSystem(
            settings.value(KEY + "crs", "", str))
        if saved.isValid():
            self.crs.setCrs(saved)
        elif QgsProject.instance().crs().isValid():
            self.crs.setCrs(QgsProject.instance().crs())
        form.addRow(tr("Система координат"), self.crs)
        self.folder = QLineEdit(settings.value(KEY + "folder", "", str),
                                self)
        self.folder.setPlaceholderText(tr("Папка файла .pyt"))
        self.folder.setToolTip(tr(
            "Папка файла GeoPackage. Пустое поле - папка файла .pyt."))
        pick_dir = QPushButton(tr("Обзор…"), self)
        pick_dir.clicked.connect(self._pick_folder)
        row = QHBoxLayout()
        row.addWidget(self.folder, 1)
        row.addWidget(pick_dir)
        form.addRow(tr("Папка результата"), row)
        lay.addLayout(form)
        self.all_points = QCheckBox(tr("Точки построения тоже"), self)
        self.all_points.setChecked(settings.value(KEY + "all_points",
                                                  False, bool))
        self.all_points.setToolTip(tr(
            "Pythagoras хранит каждую вершину линии точкой. Без флажка "
            "в слои точек попадают только точки со знаком, как при "
            "выгрузке в SHP из самого Pythagoras. С флажком - и все "
            "вершины."))
        self.all_points.toggled.connect(lambda *_: self._fill())
        lay.addWidget(self.all_points)

        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(
            3 * self.status.fontMetrics().lineSpacing())
        self.status.setAlignment(enum(Qt, "AlignmentFlag", "AlignTop"))
        self.status.setTextFormat(enum(Qt, "TextFormat", "RichText"))
        lay.addWidget(self._step(4, tr(
            "«В проект QGIS» - слои лягут в проект группой, карта QGIS "
            "и глобус покажут участок, окно закроется.")))
        lay.addWidget(self.status)
        ok = enum(QDialogButtonBox, "StandardButton", "Ok")
        close = enum(QDialogButtonBox, "StandardButton", "Close")
        buttons = QDialogButtonBox(ok | close, self)
        self.go = buttons.button(ok)
        self.go.setText(tr("В проект QGIS"))
        self.go.setIcon(icon())
        self.go.setEnabled(False)
        buttons.accepted.connect(self.convert)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _step(self, number, text):
        """Заголовок шага окна - номер в кружке и текст."""
        label = QLabel(self)
        label.setWordWrap(True)
        label.setTextFormat(enum(Qt, "TextFormat", "RichText"))
        label.setText(
            "<span style='background:#1e88e5; color:white; "
            "font-weight:600'>&nbsp;{}&nbsp;</span>&nbsp; "
            "<b>{}</b>".format(number, text))
        return label

    # Перетаскивание на всё окно.
    def dragEnterEvent(self, event):
        self.drop.dragEnterEvent(event)

    def dragLeaveEvent(self, event):
        self.drop.dragLeaveEvent(event)

    def dropEvent(self, event):
        self.drop.dropEvent(event)

    def _pick_file(self):
        start = QSettings().value(KEY + "file", "", str)
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Проект Pythagoras"), start,
            tr("Проект Pythagoras (*.pyt)"))
        if path:
            self.open_file(path)

    def _pick_folder(self):
        path = QFileDialog.getExistingDirectory(
            self, tr("Папка результата"),
            self.folder.text() or os.path.dirname(self.source))
        if path:
            self.folder.setText(path)

    def open_demo(self):
        """Пример карьера в системе координат примера."""
        self.crs.setCrs(QgsCoordinateReferenceSystem(DEMO_CRS))
        self.open_file(DEMO)

    def open_file(self, path):
        """Чтение файла и таблица его слоёв."""
        if not is_pyt(path):
            self._say(tr("Файл .pyt не найден."), error=True)
            return
        QApplication.setOverrideCursor(enum(Qt, "CursorShape", "WaitCursor"))
        try:
            with open(path, "rb") as handle:
                raw = handle.read()
            self.names, self.feats, self.lost = pythagoras.features(raw)
        except OSError as error:
            self._say(tr("Файл не прочитан: {error}", error=error),
                      error=True)
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.source = path
        QSettings().setValue(KEY + "file", path)
        self.drop.setToolTip(path)
        self._fill()
        self.go.setEnabled(bool(self.feats))
        self._say(tr("Отметьте слои и нажмите «В проект QGIS».")
                  if self.feats else tr("В файле не найдено объектов."),
                  error=not self.feats)

    def _chosen_feats(self):
        if self.all_points.isChecked():
            return self.feats
        return [f for f in self.feats
                if f["kind"] != "point" or f["symbol"] != 0]

    def _fill(self):
        """Строки таблицы: слой и количество объектов по видам."""
        off = {self.table.topLevelItem(i).data(0, LAYER_ROLE)
               for i in range(self.table.topLevelItemCount())
               if self.table.topLevelItem(i).checkState(0) == UNCHECKED}
        counts = {}
        for f in self._chosen_feats():
            row = counts.setdefault(f["layer"], dict.fromkeys(COLUMNS, 0))
            row[f["kind"]] += 1
        self.table.blockSignals(True)
        self.table.clear()
        order = sorted(counts, key=lambda n: layer_title(self.names, n))
        for number in order:
            row = counts[number]
            item = QTreeWidgetItem(
                [readable(layer_title(self.names, number))]
                + [str(row[k]) if row[k] else "" for k in COLUMNS])
            item.setData(0, LAYER_ROLE, number)
            item.setFlags(item.flags() | CHECKABLE)
            item.setCheckState(0, UNCHECKED if number in off else CHECKED)
            for column in range(1, 5):
                item.setTextAlignment(column, enum(
                    Qt, "AlignmentFlag", "AlignRight"))
            self.table.addTopLevelItem(item)
        self.table.blockSignals(False)
        self._totals()

    def _layers_on(self):
        return {self.table.topLevelItem(i).data(0, LAYER_ROLE)
                for i in range(self.table.topLevelItemCount())
                if self.table.topLevelItem(i).checkState(0) == CHECKED}

    def _mark_all(self, on):
        self.table.blockSignals(True)
        for i in range(self.table.topLevelItemCount()):
            self.table.topLevelItem(i).setCheckState(
                0, CHECKED if on else UNCHECKED)
        self.table.blockSignals(False)
        self._totals()

    def _totals(self):
        on = self._layers_on()
        chosen = self._chosen_feats()
        count = sum(1 for f in chosen if f["layer"] in on)
        if self.source:
            self.drop.show_file(self.source, tr(
                "Слоёв {layers}, объектов {count}.",
                layers=self.table.topLevelItemCount(), count=len(chosen)))
        self.total.setText(tr("Отмечено слоёв {layers} из {all}, "
                              "объектов {count}.", layers=len(on),
                              all=self.table.topLevelItemCount(),
                              count=count))
        self.go.setEnabled(bool(on) and bool(self.source))

    def _say(self, text, error=False):
        color = "#c62828" if error else "#2e7d32"
        self.status.setText("<span style='color:{}'>{}</span>".format(
            color, text))

    def convert(self):
        """Запись GeoPackage и группа в проекте. Итог - в строке окна."""
        if not self.source:
            self._pick_file()
            return
        crs = self.crs.crs()
        if not crs.isValid():
            self._say(tr("Не выбрана система координат."), error=True)
            return
        on = self._layers_on()
        feats = [f for f in self._chosen_feats() if f["layer"] in on]
        if not feats:
            self._say(tr("Не отмечено ни одного слоя."), error=True)
            return
        folder = self.folder.text().strip() or os.path.dirname(self.source)
        if not self.folder.text().strip() and self.source == DEMO:
            # Папка модуля - не место для результата, пример ложится
            # в профиль QGIS.
            folder = os.path.join(QgsApplication.qgisSettingsDirPath(),
                                  "PlanetX", "pythagoras")
            os.makedirs(folder, exist_ok=True)
        base = os.path.splitext(os.path.basename(self.source))[0]
        target = os.path.join(folder, base + ".gpkg")
        title = tr("Pythagoras - {name}", name=base)
        if os.path.exists(target):
            yes = enum(QMessageBox, "StandardButton", "Yes")
            no = enum(QMessageBox, "StandardButton", "No")
            if QMessageBox.question(
                    self, tr("Проект Pythagoras"),
                    tr("Файл {path} уже есть. Заменить его?", path=target),
                    yes | no, no) != yes:
                return
        settings = QSettings()
        settings.setValue(KEY + "folder", self.folder.text().strip())
        settings.setValue(KEY + "all_points", self.all_points.isChecked())
        settings.setValue(KEY + "crs", crs.authid())
        failure = tr("Файл не записан: {path}", path=target)
        QApplication.setOverrideCursor(enum(Qt, "CursorShape", "WaitCursor"))
        try:
            drop_group(title)
            made = write_gpkg(target, self.names, feats, crs.toWkt())
            ids, extent = add_to_project(target, title, made) if made \
                else ([], QgsRectangle())
        except OSError as error:
            made = None
            failure = tr("Файл не записан: {error}", error=error)
        finally:
            QApplication.restoreOverrideCursor()
        if not made:
            self._say(failure, error=True)
            return
        kinds = dict.fromkeys(COLUMNS, 0)
        for f in feats:
            kinds[f["kind"]] += 1
        text = tr("Готово. В проект добавлена группа «{title}» - слоёв "
                  "{count}: точек {points}, линий {lines}, площадей "
                  "{areas}, надписей {texts}.", title=title, count=len(ids),
                  points=kinds["point"], lines=kinds["line"],
                  areas=kinds["polygon"], texts=kinds["text"])
        if self.lost:
            text += " " + tr("Площадей без контура: {n}.", n=self.lost)
        self._say(text)
        # Итог должен быть виден сразу - карта и глобус летят к участку,
        # окно закрывается, сообщение остаётся в полосе QGIS. Замечание
        # автора 10 октября 2026 года - после «В проект QGIS» глобус
        # стоял на прежнем месте, и было непонятно, что произошло.
        show_result(ids, extent, crs)
        from qgis.utils import iface
        if iface is not None:
            iface.messageBar().pushMessage(
                tr("Проект Pythagoras"),
                text + " " + tr("Файл: {path}", path=target),
                Qgis.MessageLevel.Success, 15)
        self.hide()
