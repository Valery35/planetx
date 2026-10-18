# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Карточка метки в панели справа от вида: название, описание, кнопки.

Просьба автора от 17 октября 2026 года, «панель контекста» из плана
другой модели. Щелчок по метке на глобусе без включённого инструмента
открывает её карточку. Описание - HTML метки, как в KML и Google Earth,
простой текст показывается с переносами строк. Ссылки открывает
система. Кнопка «Объясни это» отдаёт помощнику название, вид, точку
и описание этой одной метки - нажатие и есть согласие отправить их,
решение автора того же дня. Без нажатия названия меток в модель
не уходят, как прежде.
"""
import html

from qgis.PyQt.QtCore import QUrl, pyqtSignal
from qgis.PyQt.QtGui import QDesktopServices, QTextDocument
from qgis.PyQt.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton,
                                 QTextBrowser, QVBoxLayout)

from ..core.flight import lon_span, wrap_lon
from ..i18n import tr

# Наибольшая длина описания в вопросе помощнику, знаков.
EXPLAIN_LIMIT = 2000


def description_html(text):
    """Описание метки для показа: HTML как есть, простой текст -
    с переносами строк."""
    text = text or ""
    if "<" in text and ">" in text:
        return text
    return html.escape(text).replace("\n", "<br>")


class PlaceCard(QDialog):
    """Карточка метки. Сигналы несут ключ метки."""

    explain = pyqtSignal(object)
    fly = pyqtSignal(object)
    properties = pyqtSignal(object)

    def __init__(self, place, can_explain, parent=None):
        super().__init__(parent)
        self.key = place.key
        self.setWindowTitle(place.shape.name or tr("Без названия"))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.text = QTextBrowser(self)
        self.text.setOpenLinks(False)
        self.text.anchorClicked.connect(self._link)
        if place.description:
            self.text.setHtml(description_html(place.description))
        else:
            self.text.setPlainText(tr(
                "У метки нет описания. Его пишут в окне «Свойства…» метки."))
        self.text.setMinimumHeight(160)
        layout.addWidget(self.text)
        # Ответ помощника на «Объясни это» - под описанием.
        self.answer = QLabel(self)
        self.answer.setWordWrap(True)
        self.answer.setOpenExternalLinks(True)
        self.answer.hide()
        layout.addWidget(self.answer)
        buttons = QHBoxLayout()
        self.explain_button = QPushButton(tr("Объясни это"), self)
        self.explain_button.setToolTip(tr(
            "Спросить помощника, что это за объект и чем интересно место. "
            "Помощнику уходят название, вид, координаты и описание этой "
            "метки. Ответ появится здесь и под строкой «Поиск»."))
        self.explain_button.setEnabled(bool(can_explain))
        if not can_explain:
            self.explain_button.setToolTip(tr(
                "Помощник не подключён. Ключ API вводят в окне "
                "«Настройки помощника»."))
        self.explain_button.clicked.connect(
            lambda: self.explain.emit(self.key))
        buttons.addWidget(self.explain_button)
        fly = QPushButton(tr("Подлететь"), self)
        fly.clicked.connect(lambda: self.fly.emit(self.key))
        buttons.addWidget(fly)
        props = QPushButton(tr("Свойства…"), self)
        props.clicked.connect(lambda: self.properties.emit(self.key))
        buttons.addWidget(props)
        buttons.addStretch(1)
        close = QPushButton(tr("Закрыть"), self)
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def _link(self, url):
        QDesktopServices.openUrl(QUrl(url))

    def show_answer(self, text):
        """Ответ помощника или строка ожидания под описанием."""
        self.answer.setText(text)
        self.answer.setVisible(bool(text))


def explain_question(place, kind_name):
    """Вопрос помощнику о метке: название, вид, точка и описание без
    разметки, не длиннее EXPLAIN_LIMIT."""
    points = place.shape.points or [(0.0, 0.0)]
    lat = sum(p[0] for p in points) / len(points)
    # Середина дуги долгот: среднее у пути через линию перемены дат
    # уводило точку на другую сторону Земли.
    west, east = lon_span(p[1] for p in points)
    lon = wrap_lon((west + east) / 2.0)
    text = " ".join(_plain(place.description).split())
    if len(text) > EXPLAIN_LIMIT:
        text = text[:EXPLAIN_LIMIT].rsplit(" ", 1)[0] + "…"
    question = tr(
        "Объясни, что это за объект и чем интересно это место. "
        "{kind} «{name}», точка {lat:.5f}, {lon:.5f}.",
        kind=kind_name, name=place.shape.name or tr("Без названия"),
        lat=lat, lon=lon)
    if text:
        question += " " + tr("Описание метки - {text}", text=text)
    return question


def _plain(text):
    """Описание без разметки HTML."""
    doc = QTextDocument()
    doc.setHtml(description_html(text))
    return doc.toPlainText()
