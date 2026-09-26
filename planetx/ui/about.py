# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «О модуле»: версия, управление, источники данных, ссылки.

Модуль не импортирует OpenGL, окно открывается и там, где глобус
работать не может.
"""
import html
import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon, QPixmap
from qgis.PyQt.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout,
                                 QLabel, QVBoxLayout)

from ..i18n import tr
from ..meta import plugin_version
from ..qt_compat import enum

ROOT = os.path.dirname(os.path.dirname(__file__))
REPOSITORY = "https://github.com/Valery35/planetx"
ISSUES = REPOSITORY + "/issues"
CATALOG = "https://plugins.qgis.org/plugins/planetx/"
OSM = "https://www.openstreetmap.org/copyright"
TERRAIN = ("https://github.com/tilezen/joerd/blob/master/docs/"
           "attribution.md")
INFORM = "https://www.informpp.ru/"


def _link(url, text):
    return '<a href="{}">{}</a>'.format(url, html.escape(text))


def _items(rows):
    return "<ul>" + "".join("<li>{}</li>".format(row) for row in rows) \
        + "</ul>"


def about_html():
    """Текст окна в HTML. Отдельно от окна, чтобы его проверял тест."""
    controls = _items(html.escape(line) for line in (
        tr("Левая кнопка тянет Землю, после отпускания она вращается "
           "по инерции."),
        tr("Колесо приближает к точке под курсором."),
        tr("Средняя кнопка или левая с Shift поворачивают и наклоняют "
           "вид."),
        tr("Координаты в поле внизу окна запускают перелёт."),
        tr("Список внизу окна меняет подложку."),
    ))
    sources = _items((
        _link(OSM, tr("Подложка OpenStreetMap: © участники "
                      "OpenStreetMap.")),
        _link(TERRAIN, tr("Рельеф: Mapzen Terrain Tiles, данные SRTM, "
                          "GMTED, ETOPO1 и других источников.")),
        html.escape(tr("Космоснимки и другие подложки берутся "
                       "из подключений XYZ Tiles в QGIS. Условия "
                       "использования задаёт их владелец.")),
    ))
    links = " · ".join((
        _link(REPOSITORY, tr("Исходный код")),
        _link(ISSUES, tr("Сообщить об ошибке")),
        _link(CATALOG, tr("Страница в каталоге QGIS")),
    ))
    return "".join((
        "<h2>PlanetX {}</h2>".format(html.escape(plugin_version())),
        "<p>{}</p>".format(html.escape(tr(
            "Трёхмерный глобус внутри QGIS в духе Google Earth. Рельеф, "
            "атмосфера, подложки из подключений QGIS."))),
        "<h3>{}</h3>".format(html.escape(tr("Управление"))), controls,
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
        text = QLabel(about_html(), self)
        text.setWordWrap(True)
        text.setOpenExternalLinks(True)
        text.setTextInteractionFlags(enum(
            Qt, "TextInteractionFlag", "TextBrowserInteraction"))
        text.setMinimumWidth(480)
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
