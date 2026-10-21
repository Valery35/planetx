# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Раздел руководства в панели справа - подсказка строки «Поиск».

Просьба автора от 20 октября 2026 года. Разделы - data/manual_ru.json
и manual_en.json (core/manualindex.py), язык - язык интерфейса QGIS.
Текст раздела показывается разметкой Markdown, без картинок. Ссылка
на другой раздел руководства открывает его в той же карточке, внешняя -
браузером системы. «Открыть на GitHub» - раздел руководства этой
версии модуля в браузере, с картинками.
"""
import os

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QPushButton

from ..core import manualindex
from ..i18n import is_russian, tr
from ..meta import plugin_version
from .about import REPOSITORY
from .placecard import Card

DATA = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "data")
PAGE = REPOSITORY + "/blob/v{version}/doc/{name}#{anchor}"

_INDEX = {}


def load_index():
    """Разделы руководства на языке интерфейса, читаются один раз.
    Без файла - пустой указатель."""
    lang = "ru" if is_russian() else "en"
    if lang not in _INDEX:
        path = os.path.join(DATA, "manual_{}.json".format(lang))
        try:
            with open(path, encoding="utf-8") as handle:
                _INDEX[lang] = manualindex.Index.from_json(handle.read())
        except (OSError, ValueError):
            _INDEX[lang] = manualindex.Index([])
    return _INDEX[lang]


def page_url(anchor):
    """Раздел руководства этой версии на GitHub."""
    name = "MANUAL.md" if is_russian() else "MANUAL.en.md"
    return PAGE.format(version=plugin_version(), name=name, anchor=anchor)


class ManualCard(Card):
    """Раздел руководства. Ключ - номер раздела в указателе."""

    def __init__(self, index, number, query="", parent=None):
        super().__init__(number, index.items[number][0], False, "", parent)
        self.index = index
        self.explain_button.hide()
        self.fly_button.hide()
        self.text.setMinimumHeight(320)
        web = QPushButton(tr("Открыть на GitHub"), self)
        web.setToolTip(tr("Раздел руководства этой версии модуля в "
                          "браузере, с картинками."))
        web.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl(page_url(self.index.items[self.key][1]))))
        self.buttons.addWidget(web)
        self.finish_buttons()
        self.show_section(number, query)

    def show_section(self, number, query=""):
        """Раздел number, прокрутка к абзацу со словами запроса."""
        self.key = number
        title, _, text = self.index.items[number]
        self.setWindowTitle(title)
        self.text.setMarkdown("## {}\n\n{}".format(title, text))
        if query:
            self._scroll_to(number, query)

    def _scroll_to(self, number, query):
        """Курсор на абзац, где больше всего слов запроса, иначе на
        первое слово запроса."""
        phrase = " ".join(self.index.snippet(number, query).split()[:4])
        if phrase and self.text.find(phrase.rstrip("…")):
            return
        for stem in self.index.stems(query):
            if self.text.find(stem):
                return

    def _link(self, url):
        """Ссылка на раздел руководства - в этой карточке."""
        url = QUrl(url)
        if not url.scheme() and url.fragment():
            number = self.index.find(url.fragment())
            if number is not None:
                self.show_section(number)
                return
        QDesktopServices.openUrl(url)
