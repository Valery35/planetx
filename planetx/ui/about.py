# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «О модуле»: версия, возможности, управление, требования,
источники данных, ссылки. Текст длинный и прокручивается.

Модуль не импортирует OpenGL, окно открывается и там, где глобус
работать не может.
"""
import html
import os

from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QIcon, QPixmap
from qgis.PyQt.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout,
                                 QLabel, QTextBrowser, QVBoxLayout)

from ..i18n import is_russian, tr
from ..meta import plugin_version
from ..qt_compat import enum

ROOT = os.path.dirname(os.path.dirname(__file__))
REPOSITORY = "https://github.com/Valery35/planetx"
ISSUES = REPOSITORY + "/issues"
CATALOG = "https://plugins.qgis.org/plugins/planetx/"
OSM = "https://www.openstreetmap.org/copyright"
TERRAIN = ("https://github.com/tilezen/joerd/blob/master/docs/"
           "attribution.md")
OPENFREEMAP = "https://openfreemap.org/"
GIBS = ("https://www.earthdata.nasa.gov/engage/open-data-services-software/"
        "earthdata-developer-portal/gibs-api")
NOMINATIM_POLICY = "https://operations.osmfoundation.org/policies/nominatim/"
SVS = "https://svs.gsfc.nasa.gov/4851"
OPM = "https://github.com/openplanetary/opm/wiki/OPM-Basemaps"
CELESTIAL = "https://github.com/ofrohn/d3-celestial"
ESRI_TERMS ="https://www.esri.com/en-us/legal/terms/full-master-agreement"
SOURCES = REPOSITORY + "/blob/main/doc/SOURCES.md"
INFORM = "https://www.informpp.ru/"
PAGE = "https://www.informpp.ru/главная-страница/qgis-planetx"
# Руководство на языке интерфейса: PDF внутри модуля, его собирает
# tools/build_manual.py. Без PDF - страница руководства в хранилище.
MANUAL = REPOSITORY + "/blob/main/doc/"


def manual_url():
    """Адрес руководства на языке интерфейса."""
    name = "PlanetX.pdf" if is_russian() else "PlanetX_en.pdf"
    path = os.path.join(ROOT, "doc", name)
    if os.path.exists(path):
        return QUrl.fromLocalFile(path).toString()
    return MANUAL + ("MANUAL.md" if is_russian() else "MANUAL.en.md")


def _link(url, text):
    return '<a href="{}">{}</a>'.format(url, html.escape(text))


def _items(rows):
    return "<ul>" + "".join("<li>{}</li>".format(row) for row in rows) \
        + "</ul>"


def about_html():
    """Текст окна в HTML. Отдельно от окна, чтобы его проверял тест."""
    features = _items(html.escape(line) for line in (
        tr("Космоснимки, рельеф с отмывкой склонов и атмосфера, подложки "
           "из подключений XYZ Tiles QGIS."),
        tr("Раздел «Слои» с границами, названиями, дорогами, реками "
           "и вершинами, подписи на 15 языках."),
        tr("Координатная сетка, звёзды, облака, температура суши "
           "и моря, 3D-здания, свет солнца."),
        tr("Слои текущего проекта на глобусе в порядке карты QGIS, "
           "синхронизация с окном карты и определение объектов."),
        tr("«Мои метки» с папками, метками, путями, многоугольниками "
           "и сохранёнными видами, чтение и запись KML и KMZ."),
        tr("Линейка на эллипсоиде WGS84 и по рельефу, 3D-путь "
           "и 3D-многоугольник по зданиям, профиль высот, "
           "координаты в градусах, UTM и MGRS."),
        tr("Значки меток, время меток со шкалой времени, подъём "
           "и выдавливание меток."),
        tr("Туры по меткам и вдоль путей, запись тура с экрана "
           "и кадрами PNG для видео, демо «Пермь»."),
        tr("Растущие треки по «Временному контроллеру» QGIS."),
        tr("Сцены в файл, снимок вида в файл и в макет QGIS."),
    ))
    controls = _items(html.escape(line) for line in (
        tr("С нажатой левой кнопкой Земля поворачивается вслед "
           "за курсором, после отпускания вращается по инерции."),
        tr("Колесо приближает к точке под курсором."),
        tr("Средняя кнопка или левая с Shift поворачивают и наклоняют "
           "вид."),
        tr("Двойной щелчок левой кнопкой приближает к точке, правой - "
           "отдаляет. Правая кнопка с перетаскиванием приближает "
           "и отдаляет, левая с Ctrl поворачивает взгляд."),
        tr("Стрелки сдвигают вид, PageUp и PageDown приближают "
           "и отдаляют, N ставит север вверху, U даёт взгляд отвесно."),
        tr("В правом верхнем углу вида кольцо компаса, джойстики взгляда "
           "и сдвига и ползунок высоты. Они появляются, когда курсор "
           "подходит к углу."),
        tr("Поле «Поиск» слева вверху находит место по названию или "
           "координатам и запускает перелёт."),
        tr("Значок «Свойства вида» на панели значков открывает "
           "свойства вида. В них выбираются подложка и масштаб рельефа."),
    ))
    needs = _items(html.escape(line) for line in (
        tr("QGIS 3.36 и новее, в том числе QGIS 4."),
        tr("Видеокарта с OpenGL 3.3."),
        tr("Модуль Python PyOpenGL. В сборках QGIS для Windows он есть."),
    ))
    sources = _items((
        _link(OSM, tr("Подложка OpenStreetMap: © участники "
                      "OpenStreetMap.")),
        _link(TERRAIN, tr("Рельеф: Mapzen Terrain Tiles, данные SRTM, "
                          "GMTED, ETOPO1 и других источников.")),
        _link(OPENFREEMAP, tr("Векторная основа: OpenFreeMap, "
                              "© OpenMapTiles, © участники "
                              "OpenStreetMap.")),
        _link(ESRI_TERMS, tr("Космоснимки Esri World Imagery - пример "
                             "подложки, условия использования задаёт "
                             "Esri.")),
        _link(GIBS, tr("Облака: NASA GIBS, снимки VIIRS.")),
        _link(GIBS, tr("Температура: NASA GIBS, MODIS и GHRSST MUR.")),
        html.escape(tr("Звёзды: каталог ярких звёзд Йельского "
                       "университета.")),
        _link(SVS, tr("Млечный путь: NASA/Goddard Space Flight Center "
                      "Scientific Visualization Studio, Gaia DR2: "
                      "ESA/Gaia/DPAC.")),
        _link(OPM, tr("Марс: NASA, USGS, Viking MDIM2.1. Луна: USGS, "
                      "LRO LOLA. Тайлы: OpenPlanetaryMap.")),
        _link(CELESTIAL, tr("Созвездия и имена звёзд: d3-celestial, "
                            "© Olaf Frohn. Планеты: элементы орбит JPL.")),
        _link(NOMINATIM_POLICY, tr("Поиск мест: Nominatim, © участники "
                                   "OpenStreetMap.")),
        html.escape(tr("Свои подложки берутся из подключений XYZ Tiles "
                       "в QGIS, их условия задаёт владелец.")),
        _link(SOURCES, tr("Источники данных и условия их использования")),
    ))
    links = " · ".join((
        _link(PAGE, tr("Страница модуля")),
        _link(manual_url(), tr("Руководство")),
        _link(REPOSITORY, tr("Исходный код")),
        _link(ISSUES, tr("Сообщить об ошибке")),
        _link(CATALOG, tr("Страница в каталоге QGIS")),
    ))
    return "".join((
        "<h2>PlanetX {}</h2>".format(html.escape(plugin_version())),
        "<p>{}</p>".format(html.escape(tr(
            "Трёхмерный глобус внутри QGIS. Рельеф, "
            "атмосфера, подложки из подключений QGIS."))),
        "<h3>{}</h3>".format(html.escape(tr("Возможности"))), features,
        "<h3>{}</h3>".format(html.escape(tr("Управление"))), controls,
        "<h3>{}</h3>".format(html.escape(tr("Требования"))), needs,
        "<h3>{}</h3>".format(html.escape(tr("Источники данных"))), sources,
        "<p>{}</p>".format(links),
        "<p>{} {}</p>".format(
            html.escape(tr("Разработка при поддержке")),
            _link(INFORM, tr("ООО «Информ++»"))),
        "<p>{}</p>".format(html.escape(tr("Лицензия GNU GPL версии 3."))),
    ))


class AboutDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("О модуле PlanetX"))
        self.setWindowIcon(QIcon(os.path.join(ROOT, "icon.svg")))
        logo = QLabel(self)
        logo.setPixmap(QPixmap(os.path.join(ROOT, "icon.png")).scaled(
            96, 96, enum(Qt, "AspectRatioMode", "KeepAspectRatio"),
            enum(Qt, "TransformationMode", "SmoothTransformation")))
        logo.setAlignment(enum(Qt, "AlignmentFlag", "AlignTop"))
        text = QTextBrowser(self)
        text.setHtml(about_html())
        text.setOpenExternalLinks(True)
        text.setFrameShape(enum(QTextBrowser, "Shape", "NoFrame"))
        text.setMinimumSize(560, 520)
        buttons = QDialogButtonBox(
            enum(QDialogButtonBox, "StandardButton", "Close"), self)
        buttons.rejected.connect(self.reject)
        body = QHBoxLayout()
        body.addWidget(logo, 0)
        body.addWidget(text, 1)
        layout = QVBoxLayout(self)
        layout.addLayout(body)
        layout.addWidget(buttons)


def show_about(parent=None):
    AboutDialog(parent).exec()
