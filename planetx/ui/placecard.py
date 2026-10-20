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

С 19 октября 2026 года, просьба автора «делай Википедию вместе
с «Объясни это»», вопрос несёт и названия включённых строк «Слоёв»
глобуса (layers_text) - слои проекта по-прежнему не уходят. Карточка
статьи Википедии рядом (ArticleCard) - первый абзац статьи, ссылка на
неё и та же кнопка. Помощник получает текст статьи и отвечает по нему.
"""
import html

from qgis.PyQt.QtCore import QUrl, pyqtSignal
from qgis.PyQt.QtGui import QDesktopServices, QTextDocument
from qgis.PyQt.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton,
                                 QTextBrowser, QVBoxLayout)

from ..core import balloon
from ..core.flight import lon_span, wrap_lon
from ..i18n import tr

# Наибольшая длина описания в вопросе помощнику, знаков.
EXPLAIN_LIMIT = 2000
# Строк «Слоёв» глобуса в вопросе помощнику не больше.
LAYERS_LIMIT = 12
# Полей объекта в вопросе помощнику не больше.
FIELDS_LIMIT = 20


def fields_html(data):
    """Поля объекта таблицей HTML под описанием, без полей - пусто."""
    if not data:
        return ""
    rows = "".join(
        "<tr><td style='padding-right:8px'><b>{}</b></td><td>{}</td></tr>"
        .format(html.escape(str(n)), html.escape(str(v)))
        for n, v in data)
    return "<table>{}</table>".format(rows)


def description_html(text):
    """Описание метки для показа: HTML как есть, простой текст -
    с переносами строк."""
    text = text or ""
    if "<" in text and ">" in text:
        return text
    return html.escape(text).replace("\n", "<br>")


class Card(QDialog):
    """Основа карточки в панели справа: текст, ответ помощника под ним,
    ряд кнопок с «Объясни это» первой. Сигналы несут ключ."""

    explain = pyqtSignal(object)
    fly = pyqtSignal(object)

    def __init__(self, key, title, can_explain, tip, parent=None):
        super().__init__(parent)
        self.key = key
        self.setWindowTitle(title or tr("Без названия"))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.text = QTextBrowser(self)
        self.text.setOpenLinks(False)
        self.text.anchorClicked.connect(self._link)
        self.text.setMinimumHeight(160)
        layout.addWidget(self.text)
        # Ответ помощника на «Объясни это» - под текстом.
        self.answer = QLabel(self)
        self.answer.setWordWrap(True)
        self.answer.setOpenExternalLinks(True)
        self.answer.hide()
        layout.addWidget(self.answer)
        self.buttons = QHBoxLayout()
        self.explain_button = QPushButton(tr("Объясни это"), self)
        self.explain_button.setToolTip(tip)
        self.explain_button.setEnabled(bool(can_explain))
        if not can_explain:
            self.explain_button.setToolTip(tr(
                "Помощник не подключён. Ключ API вводят в окне "
                "«Настройки помощника»."))
        self.explain_button.clicked.connect(
            lambda: self.explain.emit(self.key))
        self.buttons.addWidget(self.explain_button)
        fly = QPushButton(tr("Подлететь"), self)
        fly.clicked.connect(lambda: self.fly.emit(self.key))
        self.buttons.addWidget(fly)
        layout.addLayout(self.buttons)

    def finish_buttons(self):
        """Растяжка и «Закрыть» в конце ряда кнопок."""
        self.buttons.addStretch(1)
        close = QPushButton(tr("Закрыть"), self)
        close.clicked.connect(self.reject)
        self.buttons.addWidget(close)

    def _link(self, url):
        QDesktopServices.openUrl(QUrl(url))

    def show_answer(self, text):
        """Ответ помощника или строка ожидания под текстом."""
        self.answer.setText(text)
        self.answer.setVisible(bool(text))


class PlaceCard(Card):
    """Карточка метки. Сигналы несут ключ метки."""

    properties = pyqtSignal(object)

    def __init__(self, place, can_explain, parent=None):
        super().__init__(place.key, place.shape.name, can_explain, tr(
            "Спросить помощника, что это за объект и чем интересно место. "
            "Помощнику уходят название, вид, координаты, описание и поля "
            "этой метки и названия включённых слоёв глобуса. Ответ появится "
            "здесь и под строкой «Поиск»."), parent)
        fields = fields_html(getattr(place, "data", None))
        template = getattr(place, "balloon", "")
        if template:
            # Окно по шаблону BalloonStyle из KML.
            self.text.setHtml(balloon.fill(
                template, place.shape.name, place.description,
                getattr(place, "data", None)))
        elif place.description or fields:
            self.text.setHtml(description_html(place.description)
                              + fields)
        else:
            self.text.setPlainText(tr(
                "У метки нет описания. Его пишут в окне «Свойства…» метки."))
        props = QPushButton(tr("Свойства…"), self)
        props.clicked.connect(lambda: self.properties.emit(self.key))
        self.buttons.addWidget(props)
        self.finish_buttons()


class ArticleCard(Card):
    """Карточка статьи Википедии рядом (core.wikipedia.Article). Первый
    абзац приходит позже - set_extract. Ключ сигналов - сама статья."""

    keep = pyqtSignal(object)

    def __init__(self, article, link, can_explain, parent=None):
        super().__init__(article, article.title, can_explain, tr(
            "Спросить помощника об этом месте по тексту статьи. Помощнику "
            "уходят заголовок, первый абзац и координаты статьи и названия "
            "включённых слоёв глобуса. Ответ появится здесь и под строкой "
            "«Поиск»."), parent)
        self.article = article
        self.link = link
        self.extract = ""
        self.set_extract("")
        keep = QPushButton(tr("В «Мои метки»"), self)
        keep.setToolTip(tr("Метка в точке статьи с первым абзацем "
                           "и ссылкой на статью в описании."))
        keep.clicked.connect(lambda: self.keep.emit(self.key))
        self.buttons.addWidget(keep)
        self.finish_buttons()

    def set_extract(self, text, error=""):
        """Первый абзац статьи, строка загрузки или причина отказа."""
        self.extract = text or ""
        if text:
            body = html.escape(text).replace("\n", "<br>")
        elif error:
            body = html.escape(tr("Текст статьи не загрузился: {error}",
                                  error=error))
        else:
            body = html.escape(tr("Загрузка статьи…"))
        self.text.setHtml('<p><b>{}</b></p><p>{}</p><p><a href="{}">{}</a>'
                          '</p><p style="color:gray">{}</p>'.format(
                              html.escape(self.article.title), body,
                              html.escape(self.link, quote=True),
                              html.escape(tr("Статья в Википедии")),
                              html.escape(tr("Текст - Википедия, "
                                             "CC BY-SA 4.0"))))


def layers_text(names):
    """Фраза о включённых строках «Слоёв» глобуса для вопроса помощнику,
    без строк - пустая."""
    names = [n for n in names if n][:LAYERS_LIMIT]
    if not names:
        return ""
    return tr("На глобусе включены слои - {names}.",
              names=", ".join(names))


def _clip(text):
    text = " ".join((text or "").split())
    if len(text) > EXPLAIN_LIMIT:
        text = text[:EXPLAIN_LIMIT].rsplit(" ", 1)[0] + "…"
    return text


def article_question(title, extract, lat, lon, layers=()):
    """Вопрос помощнику о статье Википедии: заголовок, точка, первый
    абзац не длиннее EXPLAIN_LIMIT и включённые слои глобуса."""
    question = tr(
        "Объясни, что это за объект и чем интересно это место. Статья "
        "Википедии «{title}», точка {lat:.5f}, {lon:.5f}.",
        title=title, lat=lat, lon=lon)
    text = _clip(extract)
    if text:
        question += " " + tr("Первый абзац статьи - {text}", text=text)
        question += " " + tr("Опирайся на текст статьи и не придумывай "
                             "того, чего в нём нет.")
    extra = layers_text(layers)
    if extra:
        question += " " + extra
    return question


def explain_question(place, kind_name, layers=()):
    """Вопрос помощнику о метке: название, вид, точка, описание без
    разметки не длиннее EXPLAIN_LIMIT и названия включённых строк
    «Слоёв» глобуса."""
    points = place.shape.points or [(0.0, 0.0)]
    lat = sum(p[0] for p in points) / len(points)
    # Середина дуги долгот: среднее у пути через линию перемены дат
    # уводило точку на другую сторону Земли.
    west, east = lon_span(p[1] for p in points)
    lon = wrap_lon((west + east) / 2.0)
    text = _clip(_plain(place.description))
    question = tr(
        "Объясни, что это за объект и чем интересно это место. "
        "{kind} «{name}», точка {lat:.5f}, {lon:.5f}.",
        kind=kind_name, name=place.shape.name or tr("Без названия"),
        lat=lat, lon=lon)
    if text:
        question += " " + tr("Описание метки - {text}", text=text)
    fields = _clip("; ".join("{} = {}".format(n, v) for n, v in (
        getattr(place, "data", None) or ())[:FIELDS_LIMIT]))
    if fields:
        question += " " + tr("Поля объекта - {fields}.", fields=fields)
    extra = layers_text(layers)
    if extra:
        question += " " + extra
    return question


def _plain(text):
    """Описание без разметки HTML."""
    doc = QTextDocument()
    doc.setHtml(description_html(text))
    return doc.toPlainText()
