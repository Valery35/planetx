# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Сетевые ссылки KML: окно ссылки и загрузка содержимого.

Ссылка - папка «Моих меток» с адресом (MyPlaces.set_link). Пока
папка отмечена вместе с родителями, документ по адресу загружается
один раз за сеанс или через промежуток обновления и заменяет
содержимое папки (MyPlaces.replace_contents). Адрес в сети идёт через
QgsNetworkAccessManager мимо кэша, файл на диске перечитывается, когда
меняется время его правки. Вложенные ссылки загружаются так же, не
глубже core.netlink.DEPTH.
"""
import os
import time

from qgis.PyQt.QtCore import QObject, QTimer
from qgis.PyQt.QtWidgets import (QDialog, QDialogButtonBox, QDoubleSpinBox,
                                 QFormLayout, QLabel, QLineEdit)

from ..core import kml, netlink
from ..i18n import tr
from ..net.overlay import fetch_bytes
from ..qt_compat import enum

TICK = 1000  # мс между проверками сроков ссылок


class LinkDialog(QDialog):
    """Окно «Сетевая ссылка»: название, адрес, промежуток обновления."""

    def __init__(self, name="", link="", refresh=0.0, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Сетевая ссылка"))
        form = QFormLayout(self)
        form.addRow(QLabel(tr(
            "Папка «Моих меток» с содержимым документа KML или KMZ по "
            "адресу. Содержимое загружается заново через промежуток "
            "обновления, правки внутри папки при этом теряются.")))
        self.name = QLineEdit(name, self)
        self.name.setToolTip(tr("Название папки в «Моих метках»."))
        form.addRow(tr("Название"), self.name)
        self.link = QLineEdit(link, self)
        self.link.setPlaceholderText("https://…/doc.kml")
        self.link.setToolTip(tr(
            "Адрес документа KML или KMZ в сети (http, https) или путь "
            "файла на диске. Файл перечитывается, когда его меняет "
            "другая программа."))
        form.addRow(tr("Адрес"), self.link)
        self.refresh = QDoubleSpinBox(self)
        self.refresh.setRange(0.0, 7 * 86400.0)
        self.refresh.setDecimals(0)
        self.refresh.setSuffix(tr(" с"))
        self.refresh.setValue(float(refresh))
        self.refresh.setSpecialValueText(tr("Один раз"))
        self.refresh.setToolTip(tr(
            "Через сколько секунд документ загружается заново. Ноль - "
            "один раз за сеанс. Короче 10 с промежуток не бывает."))
        form.addRow(tr("Обновлять"), self.refresh)
        buttons = QDialogButtonBox(
            enum(QDialogButtonBox, "StandardButton", "Ok")
            | enum(QDialogButtonBox, "StandardButton", "Cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self):
        return (self.name.text().strip(), self.link.text().strip(),
                self.refresh.value())


class NetLinks(QObject):
    """Загрузка содержимого сетевых ссылок «Моих меток»."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        # Ключ папки - (время загрузки, адрес, время правки файла).
        self.loaded = {}
        self.replies = {}  # ключ папки - ответ сети в пути
        self.errors = {}  # ключ папки - текст последней ошибки
        self.stopped = False
        self.timer = QTimer(self)
        self.timer.setInterval(TICK)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def links(self):
        """Папки-ссылки «Моих меток»."""
        return [f for f in self.window.myplaces.folders if f.link]

    def _shown_depth(self, folder):
        """Глубина ссылки среди ссылок-предков или None, если папка или
        кто-то из родителей снят флажком."""
        by_key = {f.key: f for f in self.window.myplaces.folders}
        depth = 0
        node = folder
        while node is not None:
            if not node.visible:
                return None
            if node is not folder and node.link:
                depth += 1
            node = by_key.get(node.parent)
        return depth

    def tick(self):
        now = time.monotonic()
        for folder in self.links():
            depth = self._shown_depth(folder)
            if depth is None or depth > netlink.DEPTH \
                    or folder.key in self.replies:
                continue
            last = self.loaded.get(folder.key)
            if last is not None and last[1] != folder.link:
                last = None
            path = None if netlink.is_web(folder.link) \
                else netlink.local_path(folder.link)
            if path is not None:
                self._file(folder, path, last, now)
            elif netlink.due(last[0] if last else None, folder.refresh, now):
                self._fetch(folder, now)

    def reload(self, key):
        """«Загрузить заново» меню ссылки."""
        self.loaded.pop(key, None)
        self.tick()

    def _fetch(self, folder, now):
        key, url = folder.key, folder.link

        def done(data, error, key=key, url=url, now=now):
            if self.stopped:
                return
            self.replies.pop(key, None)
            self.loaded[key] = (now, url, None)
            self._arrived(key, url, data, error)
        self.replies[key] = fetch_bytes(url, done, prefer_cache=False,
                                        fresh=True)

    def _file(self, folder, path, last, now):
        try:
            stamp = os.path.getmtime(path)
        except OSError as error:
            if last is None:
                self.loaded[folder.key] = (now, folder.link, None)
                self._arrived(folder.key, folder.link, None, str(error))
            return
        if last is not None and last[2] == stamp:
            return
        self.loaded[folder.key] = (now, folder.link, stamp)
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError as error:
            self._arrived(folder.key, folder.link, None, str(error))
            return
        self._arrived(folder.key, folder.link, data, "")

    def _arrived(self, key, url, data, error):
        """Документ ссылки пришёл: содержимое папки заменяется."""
        folder = self.window.myplaces.find(key)
        if folder is None or folder.link != url:
            return
        tree = None
        if data is not None:
            try:
                tree = kml.read_file(data, folder.name)
            except kml.KmlError as problem:
                error = str(problem)
        if tree is None:
            self.errors[key] = error
            self.window.message = (tr(
                "Сетевая ссылка «{name}» не загружена: {error}",
                name=folder.name, error=error or "?"), time.monotonic())
            self.window._show_state()
            return
        self.errors.pop(key, None)
        netlink.resolve_tree(tree, url)
        self.window.myplaces.replace_contents(key, tree)

    def stop(self):
        """Окно закрывается: таймер и ответы в пути снимаются."""
        self.stopped = True
        self.timer.stop()
        for reply in list(self.replies.values()):
            reply.abort()
        self.replies.clear()
