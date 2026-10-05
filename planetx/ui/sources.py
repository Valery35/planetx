# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «Источники данных»: все источники глобуса, их условия,
проверка доступности, свой рельеф и своя векторная основа, подложки.

Решение автора от 30 сентября 2026 года, состав утверждён 5 октября
2026 года. Открывается кнопкой окна «Свойства вида». Адреса по
умолчанию и проверка своих адресов - core/sources.py.
"""
import time

from qgis.core import QgsSettings
from qgis.PyQt.QtCore import Qt, QUrl, pyqtSignal
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                                 QFormLayout, QGroupBox, QHBoxLayout,
                                 QLabel, QLineEdit, QMessageBox,
                                 QPushButton, QTreeWidget, QTreeWidgetItem,
                                 QVBoxLayout)

from ..core import (basemap, crust, fires, paleo, planets, quakes, slabs,
                    sources, sun)
from ..i18n import tr
from ..net.overlay import fetch_bytes
from ..qt_compat import enum
from .tilesource import TileSourceDialog, remove_connection

SOURCES_DOC = "https://github.com/Valery35/planetx/blob/main/doc/SOURCES.md"
NAME, WHAT, TERMS, CHECK = range(4)
URL_ROLE = enum(Qt, "ItemDataRole", "UserRole")
SOURCE_ROLE = URL_ROLE + 1  # индекс подложки в списке источников окна


def catalogue(terrain_url, vector_url):
    """Источники по группам: (группа, [(название, что показывает,
    условия, адрес проверки или None)])."""
    terrain_probe = sources.tile_probe(terrain_url)
    mars = planets.TERRAIN_TILES % "mars"
    return (
        (tr("Рельеф"), [
            (tr("Рельеф Земли") if terrain_url == sources.TERRAIN_URL
             else tr("Свой рельеф"),
             tr("Высоты суши и дна морей, уровни 0-15"),
             "https://github.com/tilezen/joerd/blob/master/docs/"
             "attribution.md" if terrain_url == sources.TERRAIN_URL
             else SOURCES_DOC, terrain_probe),
            (tr("Марс, Луна и другие тела"),
             tr("Высоты и снимки тел из хранилища planetx-terrain"),
             SOURCES_DOC, sources.tile_probe(mars))]),
        (tr("Векторная основа"), [
            ("OpenFreeMap" if vector_url == sources.VECTOR_TILEJSON
             else tr("Своя основа"),
             tr("Границы, дороги, воды, названия, 3D-здания"),
             "https://openfreemap.org/" if vector_url
             == sources.VECTOR_TILEJSON else SOURCES_DOC, vector_url)]),
        ("NASA", [
            ("NASA GIBS", tr("Облака, температура, темы, огни городов"),
             "https://nasa-gibs.github.io/gibs-api-docs/",
             sources.tile_probe(sun.LIGHTS_URL)),
            ("NASA FIRMS", tr("Пожары за 24 часа"),
             "https://www.earthdata.nasa.gov/data/tools/firms",
             fires.ATTRIBUTION[1]),
            ("NASA SVS", tr("Млечный путь, около 10 МБ"),
             "https://svs.gsfc.nasa.gov/4851", None)]),
        (tr("Науки о Земле"), [
            ("USGS", tr("Землетрясения за 30 суток"), quakes.ATTRIBUTION[1],
             quakes.FEED),
            ("USGS Slab2", tr("Плиты на разрезах"), slabs.ATTRIBUTION[1],
             slabs.URL.format(code="kur")),
            ("CRUST1.0", tr("Кора на разрезах"), crust.CITATION[1],
             crust.URL),
            ("PB2002", tr("Границы плит, файл модуля"),
             "https://github.com/fraxen/tectonicplates", None),
            ("PALEOMAP PaleoDEM", tr("Палеогеография"), paleo.ATTRIBUTION[1],
             sources.tile_probe(paleo.TILE_URL.replace("{age}", "0")))]),
    )


class SourcesDialog(QDialog):
    """Окно «Источники данных». window - окно глобуса: его подложки
    (sources), точка взгляда для окна источника тайлов. Сигнал changed
    несёт, что сменилось: "terrain", "vector" или "basemaps"."""

    changed = pyqtSignal(str)

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.setWindowTitle(tr("Источники данных"))
        self.setModal(False)
        self.setMinimumWidth(760)
        self.replies = {}

        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels([tr("Источник"), tr("Что показывает"),
                                   tr("Условия"), tr("Проверка")])
        self.tree.setColumnWidth(NAME, 210)
        self.tree.setColumnWidth(WHAT, 250)
        self.tree.setColumnWidth(TERMS, 90)
        self.tree.itemClicked.connect(self._clicked)
        self.tree.currentItemChanged.connect(self._current)

        self.check = QPushButton(tr("Проверить"), self)
        self.check.setToolTip(tr(
            "Запросить у каждого источника один тайл или файл мимо кэша "
            "и показать ответ и время. Большие файлы вроде картинки "
            "звёздного неба не запрашиваются."))
        self.check.clicked.connect(self.probe)
        self.add = QPushButton(tr("Добавить подложку…"), self)
        self.add.setToolTip(tr(
            "Окно нового источника тайлов. Источник записывается "
            "подключением XYZ Tiles QGIS и становится подложкой."))
        self.add.clicked.connect(self._add)
        self.edit = QPushButton(tr("Изменить…"), self)
        self.edit.setToolTip(tr(
            "Адрес, название, уровни и подпись выбранной подложки из "
            "подключений XYZ Tiles QGIS."))
        self.edit.clicked.connect(self._edit)
        self.remove = QPushButton(tr("Удалить"), self)
        self.remove.setToolTip(tr(
            "Удалить выбранное подключение XYZ Tiles из QGIS. Оно "
            "пропадает и из обозревателя QGIS."))
        self.remove.clicked.connect(self._remove)
        buttons_row = QHBoxLayout()
        for button in (self.check, self.add, self.edit, self.remove):
            buttons_row.addWidget(button)
        buttons_row.addStretch(1)

        settings = QgsSettings()
        self.terrain_url = QLineEdit(
            settings.value(sources.TERRAIN_KEY, "") or "", self)
        self.terrain_url.setPlaceholderText(sources.TERRAIN_URL)
        self.terrain_url.setToolTip(tr(
            "Шаблон тайлов высот с {z}, {x}, {y}, например своё "
            "хранилище или сервер. Пустое поле - рельеф по умолчанию. "
            "Глобус просит тайлы до уровня 15, глубже берёт их предков."))
        self.encoding = QComboBox(self)
        self.encoding.addItems(["Terrarium", "Mapbox Terrain-RGB"])
        self.encoding.setCurrentIndex(sources.ENCODINGS.index(
            settings.value(sources.ENCODING_KEY, "terrarium")
            if settings.value(sources.ENCODING_KEY, "terrarium")
            in sources.ENCODINGS else "terrarium"))
        self.encoding.setToolTip(tr(
            "Как высота записана в цвете тайла. Terrarium - как у рельефа "
            "по умолчанию, Mapbox Terrain-RGB - высота с шагом 0.1 м."))
        self.terrain_credit = QLineEdit(
            settings.value(sources.TERRAIN_CREDIT_KEY, "") or "", self)
        self.terrain_credit.setToolTip(tr(
            "Подпись своего рельефа в углу вида и на снимках."))
        terrain = QGroupBox(tr("Свой рельеф"), self)
        form = QFormLayout(terrain)
        form.addRow(tr("Адрес"), self.terrain_url)
        form.addRow(tr("Запись высот"), self.encoding)
        form.addRow(tr("Подпись"), self.terrain_credit)
        form.addRow(self._apply_row("terrain"))

        self.vector_url = QLineEdit(
            settings.value(sources.VECTOR_KEY, "") or "", self)
        self.vector_url.setPlaceholderText(sources.VECTOR_TILEJSON)
        self.vector_url.setToolTip(tr(
            "Адрес TileJSON векторных тайлов в схеме OpenMapTiles. Из них "
            "берутся границы, дороги, воды, названия и 3D-здания. Пустое "
            "поле - OpenFreeMap."))
        self.vector_credit = QLineEdit(
            settings.value(sources.VECTOR_CREDIT_KEY, "") or "", self)
        self.vector_credit.setToolTip(tr(
            "Подпись своей основы в углу вида и на снимках."))
        vector = QGroupBox(tr("Своя векторная основа"), self)
        form = QFormLayout(vector)
        form.addRow("TileJSON", self.vector_url)
        form.addRow(tr("Подпись"), self.vector_credit)
        form.addRow(self._apply_row("vector"))

        self.status = QLabel(self)
        self.status.setWordWrap(True)
        close = QDialogButtonBox(
            enum(QDialogButtonBox, "StandardButton", "Close"), self)
        close.rejected.connect(self.close)
        layout = QVBoxLayout(self)
        layout.addWidget(self.tree, 1)
        layout.addLayout(buttons_row)
        layout.addWidget(terrain)
        layout.addWidget(vector)
        layout.addWidget(self.status)
        layout.addWidget(close)
        self.rebuild()

    def _apply_row(self, what):
        row = QHBoxLayout()
        apply = QPushButton(tr("Применить"), self)
        apply.setToolTip(tr("Глобус берёт данные по новому адресу."))
        apply.clicked.connect(lambda _=False: self._apply(what))
        reset = QPushButton(tr("Как было"), self)
        reset.setToolTip(tr("Вернуть источник по умолчанию."))
        reset.clicked.connect(lambda _=False: self._reset(what))
        row.addStretch(1)
        row.addWidget(apply)
        row.addWidget(reset)
        return row

    # Таблица.

    def rebuild(self):
        """Строки таблицы по нынешним адресам и подложкам."""
        self.tree.clear()
        base = QTreeWidgetItem(self.tree, [tr("Подложки")])
        for index, source in enumerate(self.window.sources):
            what = tr("Снимок или карта под всеми слоями")
            terms = source.attribution[1] or SOURCES_DOC
            if source.url == basemap.ESRI_URL:
                terms = ("https://www.esri.com/en-us/legal/terms/"
                         "full-master-agreement")
            elif source.url == basemap.OSM_URL:
                terms = "https://operations.osmfoundation.org/policies/tiles/"
            elif not source.builtin:
                what = tr("Подключение XYZ Tiles QGIS")
            item = self._row(base, source.name, what, terms,
                             sources.tile_probe(source.url))
            item.setData(NAME, SOURCE_ROLE, index)
        terrain, encoding = self.window._terrain_choice()
        for group, rows in catalogue(terrain, self.window._vector_choice()):
            parent = QTreeWidgetItem(self.tree, [group])
            for name, what, terms, probe in rows:
                self._row(parent, name, what, terms, probe)
        self.tree.expandAll()
        self._current(self.tree.currentItem(), None)

    def _row(self, parent, name, what, terms, probe):
        item = QTreeWidgetItem(parent, [name, what, tr("открыть") if terms
                                        else "", "" if probe else
                                        tr("без проверки")])
        item.setData(TERMS, URL_ROLE, terms)
        item.setData(CHECK, URL_ROLE, probe)
        item.setToolTip(TERMS, terms or "")
        item.setToolTip(CHECK, probe or "")
        return item

    def _clicked(self, item, column):
        url = item.data(TERMS, URL_ROLE)
        if column == TERMS and url:
            QDesktopServices.openUrl(QUrl(url))

    def _selected_source(self):
        item = self.tree.currentItem()
        index = item.data(NAME, SOURCE_ROLE) if item is not None else None
        if index is None:
            return None
        return self.window.sources[index]

    def _current(self, item, previous):
        source = self._selected_source()
        user = source is not None and not source.builtin
        self.edit.setEnabled(user)
        self.remove.setEnabled(user)

    # Проверка.

    def probe(self):
        """Один запрос к каждому источнику мимо кэша, ответ и время
        в столбце «Проверка»."""
        self._abort()
        items = []
        for n in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(n)
            items += [group.child(k) for k in range(group.childCount())]
        for item in items:
            url = item.data(CHECK, URL_ROLE)
            if not url:
                continue
            item.setText(CHECK, tr("ждём…"))
            started = time.monotonic()
            self.replies[id(item)] = fetch_bytes(
                url, lambda data, error, item=item, started=started:
                self._probed(item, started, data, error),
                prefer_cache=False)

    def _probed(self, item, started, data, error):
        self.replies.pop(id(item), None)
        ms = (time.monotonic() - started) * 1000.0
        if data is None:
            item.setText(CHECK, tr("ошибка"))
            item.setToolTip(CHECK, error)
        else:
            item.setText(CHECK, tr("{ms} мс, {kb} КБ", ms="{:.0f}".format(ms),
                                   kb="{:.0f}".format(len(data) / 1024.0)))

    def _abort(self):
        for reply in list(self.replies.values()):
            reply.abort()
        self.replies.clear()

    def closeEvent(self, event):
        self._abort()
        super().closeEvent(event)

    # Свои адреса.

    def _apply(self, what):
        settings = QgsSettings()
        if what == "terrain":
            url = self.terrain_url.text().strip()
            if url and not sources.template_ok(url):
                self.status.setText(tr(
                    "Адрес рельефа - шаблон с {z}, {x} и {y}."))
                return
            settings.setValue(sources.TERRAIN_KEY, url)
            settings.setValue(sources.ENCODING_KEY,
                              sources.ENCODINGS[self.encoding.currentIndex()])
            settings.setValue(sources.TERRAIN_CREDIT_KEY,
                              self.terrain_credit.text().strip())
        else:
            url = self.vector_url.text().strip()
            if url and not sources.tilejson_ok(url):
                self.status.setText(tr("Адрес TileJSON начинается с http, "
                                       "https или file."))
                return
            settings.setValue(sources.VECTOR_KEY, url)
            settings.setValue(sources.VECTOR_CREDIT_KEY,
                              self.vector_credit.text().strip())
        self.status.setText("")
        self.changed.emit(what)
        self.rebuild()

    def _reset(self, what):
        if what == "terrain":
            self.terrain_url.clear()
            self.encoding.setCurrentIndex(0)
            self.terrain_credit.clear()
        else:
            self.vector_url.clear()
            self.vector_credit.clear()
        self._apply(what)

    # Подложки.

    def _add(self):
        pose = self.window.view.navigator.pose
        dialog = TileSourceDialog(self, (pose.lat, pose.lon))
        if dialog.exec():
            self.changed.emit("basemaps")
            self.rebuild()

    def _edit(self):
        source = self._selected_source()
        if source is None or source.builtin:
            return
        pose = self.window.view.navigator.pose
        dialog = TileSourceDialog(self, (pose.lat, pose.lon), edit=source)
        if dialog.exec():
            self.changed.emit("basemaps")
            self.rebuild()

    def _remove(self):
        source = self._selected_source()
        if source is None or source.builtin:
            return
        answer = QMessageBox.question(
            self, tr("Удалить подложку"),
            tr("Удалить подключение «{name}» из QGIS?", name=source.name))
        if answer != enum(QMessageBox, "StandardButton", "Yes"):
            return
        remove_connection(source.name)
        self.changed.emit("basemaps")
        self.rebuild()
