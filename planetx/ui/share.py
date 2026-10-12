# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""«Поделиться видом»: страница HTML из окна глобуса.

Страницу собирает core/share.py. Здесь - выбор файла, метки из
выделенного в «Моих метках», запись и показ страницы браузером системы.
Модуль сам в сеть не ходит, библиотеку и тайлы грузит браузер.
"""
import os

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox

from ..core import share
from ..i18n import tr, ui_language


def texts():
    """Подписи кнопок страницы на языке интерфейса."""
    return {"home": tr("Исходный вид"), "play": tr("▶ Облёт"),
            "stop": tr("⏹ Остановить")}


def places_tree(window):
    """Выделенные метки и папки деревом core.kml или None."""
    keys = window.panel.list.selected_keys()
    if not keys:
        return None
    return window.myplaces.export_keys(keys, name="PlanetX")


def share_view(window, path=None, show=True):
    """Записать страницу вида. path None - окно выбора файла. show -
    открыть страницу браузером системы. Итог - путь файла или None."""
    title = tr("Поделиться видом")
    if window.view.sky_view is not None or not window.planet.earth:
        QMessageBox.information(window, title, tr(
            "Страница строится только для Земли. Вернитесь на Землю "
            "и повторите."))
        return None
    tree = places_tree(window)
    if path is None:
        name = tree.children[0].name if tree is not None \
            and len(tree.children) == 1 else "PlanetX"
        path, _ = QFileDialog.getSaveFileName(
            window, title, (name or "PlanetX") + ".html",
            tr("Страница HTML (*.html)"))
    if not path:
        return None
    pose = window.view.navigator.pose
    data = share.page_data(
        (pose.lat, pose.lon, pose.distance, pose.heading, pose.tilt),
        tree, relief=bool(window._relief), scale=float(window._scale),
        texts=texts(), fov=window.view.camera.fov_y)
    name = os.path.splitext(os.path.basename(path))[0]
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(share.page(name, data, ui_language()))
    except OSError as error:
        QMessageBox.warning(window, title, tr(
            "Файл не записан: {error}", error=str(error)))
        return None
    if show:
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
    return path
