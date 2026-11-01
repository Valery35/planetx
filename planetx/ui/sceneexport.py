# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Выгрузка объектов вида: файл GLB или набор 3D Tiles.

Пункт меню значка «Сцена» и действие строки «Поиск». Идут сетки вида,
как они лежат в видеокарте: 3D-здания кадра, выдавленные слои, подземная
модель, неподвижные 3D-модели. Рельеф, снимки и анимация в файл не идут,
модели на треках и живые объекты тоже. Высоты - с масштабом рельефа вида.
Запись - core/sceneexport.py.
"""
import os

import numpy as np
from qgis.PyQt.QtCore import QBuffer, QByteArray
from qgis.PyQt.QtGui import QImage
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox

from ..core import sceneexport
from ..i18n import tr
from ..qt_compat import enum

NORMAL_UNIT = 127.0  # нормаль вершины зданий хранится в int8


def _png(rgba):
    """Байты PNG картинки RGBA (h, w, 4)."""
    rows = np.ascontiguousarray(rgba, dtype=np.uint8)
    image = QImage(rows.tobytes(), rows.shape[1], rows.shape[0],
                   rows.shape[1] * 4, enum(QImage, "Format",
                                           "Format_RGBA8888"))
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(enum(QBuffer, "OpenModeFlag", "WriteOnly"))
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def _vertex_item(center, vertices, indices, name):
    """Кусок из вершин core.buildings.VERTEX."""
    return sceneexport.Item(
        center, np.array(vertices["position"], dtype=np.float32),
        vertices["normal"][:, :3] / NORMAL_UNIT,
        np.array(vertices["color"], dtype=np.uint8),
        np.asarray(indices).reshape(-1, 3), name=name)


def _model_items(view):
    """Неподвижные 3D-модели: часть с картинкой или цветом - кусок."""
    models = view.models
    items = []
    for number, (model, center) in enumerate(zip(models.source,
                                                 models.centers)):
        if model.mover is not None or number in models.hidden:
            continue
        for vertices, rgba, color, _ in model.parts:
            positions = np.array(vertices["position"], dtype=np.float32)
            if not len(positions):
                continue
            picture = _png(rgba) if rgba is not None else None
            colors = None
            if picture is None:
                colors = np.tile(np.round(
                    np.asarray(color, dtype=np.float64) * 255.0).astype(
                        np.uint8), (len(positions), 1))
            items.append(sceneexport.Item(
                np.asarray(center, dtype=np.float64), positions,
                np.array(vertices["normal"], dtype=np.float32), colors,
                None, np.array(vertices["uv"], dtype=np.float32)
                if picture else None, picture, str(model.key)))
    return items


def collect(window):
    """Куски сцены вида."""
    view = window.view
    items = []
    buildings = view.buildings
    if buildings.shown:
        for key in buildings.wanted:
            item = buildings.buffers.get(key)
            if item is not None:
                items.append(sceneexport.Item(
                    item.center, item.positions, item.normals[:, :3]
                    / NORMAL_UNIT, item.colors, item.triangles,
                    name="building {}".format(key)))
    for owner in (view.extruded, view.subsurface):
        for name, mesh in owner.meshes.items():
            if len(mesh.indices):
                items.append(_vertex_item(mesh.center, mesh.vertices,
                                          mesh.indices, str(name)))
    return items + _model_items(view)


def write(items, path, pose):
    """Записать куски: path с .json - набор 3D Tiles в папку с именем
    файла, иначе один файл GLB. Возвращает путь главного файла."""
    if path.lower().endswith(".json"):
        text, files = sceneexport.tileset(items)
        folder = os.path.splitext(path)[0]
        os.makedirs(folder, exist_ok=True)
        for name, data in files:
            with open(os.path.join(folder, name), "wb") as fh:
                fh.write(data)
        main = os.path.join(folder, "tileset.json")
        with open(main, "w", encoding="utf-8") as fh:
            fh.write(text)
        return main
    with open(path, "wb") as fh:
        fh.write(sceneexport.scene_glb(items, pose.lat, pose.lon))
    return path


def export_scene(window, path=None):
    """Окно файла и запись. Возвращает путь или None."""
    title = tr("Выгрузить в glTF или 3D Tiles")
    items = collect(window)
    if not items:
        QMessageBox.information(window, title, tr(
            "В виде нет объектов для выгрузки: 3D-зданий, выдавленных "
            "слоёв, подземной модели или 3D-моделей."))
        return None
    if path is None:
        path, _ = QFileDialog.getSaveFileName(
            window, title, "PlanetX.glb",
            "glTF (*.glb);;3D Tiles (*.json)")
    if not path:
        return None
    try:
        main = write(items, path, window.view.navigator.pose)
    except (OSError, ValueError) as error:
        QMessageBox.warning(window, title, tr(
            "Файл не записан: {error}", error=str(error)))
        return None
    scale = window.view.store.scale or 1.0
    window.panel.set_answer(
        tr("Выгружено кусков {count}. Масштаб рельефа {scale} вошёл "
           "в высоты.", count=len(items), scale="{:g}".format(scale))
        if abs(scale - 1.0) > 1e-6 else
        tr("Выгружено кусков {count}.", count=len(items)))
    return main
