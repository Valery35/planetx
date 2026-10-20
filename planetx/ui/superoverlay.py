# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Суперналожения KML в окне глобуса: загрузка документов и картинок.

Ссылка суперналожения - папка «Моих меток» с viewRefreshMode onRegion
(Folder.view_mode). Её документ и документы под ней не пишутся в файл
меток, как у обычной сетевой ссылки (ui/netlink.py): дерево
core.superoverlay держит их в памяти. Раз в TICK мс дерево смотрит на
вид, окно загружает документы активных ссылок и картинки видимых тайлов
через кэш QGIS, а видимые тайлы ложатся растрами QGIS в наложение под
картинками на поверхности, как и они (ui/overlays.GroundLayers). Так
тайлы лежат на рельефе со светом и дымкой поверхности. Состав растров
меняется не чаще раза в APPLY_GAP мс: наложение собирается заново
целиком, а тайлы приходят по одному.
"""
import glob
import math
import os
import time

import numpy as np
from qgis.PyQt.QtCore import QObject, QTimer

from ..core import kml, netlink, superoverlay
from ..core import overlays as core_overlays
from ..core.ellipsoid import ecef_to_geodetic
from ..core.sync import ground_size, view_box
from ..i18n import tr
from ..net.overlay import fetch_bytes
from .overlays import GroundLayers, folder

TICK = 400  # мс между шагами по виду
APPLY_GAP = 1000  # мс, растры тайлов меняются не чаще
DOCUMENTS = 4  # документов в пути одновременно
IMAGES = 6  # картинок в пути одновременно
IMAGES_KEPT = 400  # картинок тайлов в памяти
FID = "superoverlay"  # начало имён файлов растров тайлов


class SuperOverlays(QObject):
    """Суперналожения окна window."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.trees = {}  # ключ папки - (адрес, core.superoverlay.Tree)
        self.docs = {}  # (ключ папки, адрес) - ответ сети в пути
        self.images = {}  # адрес картинки - байты, по давности
        self.image_replies = {}  # адрес картинки - ответ сети в пути
        self.failed = set()  # адреса картинок, которые не пришли
        self.ground = GroundLayers()
        self.rasters = []  # растры видимых тайлов, верхний первым
        self.entries = []
        self._shown = None  # ключи видимых тайлов, по ним новые растры
        self._applied_at = 0.0
        self.stopped = False
        self.timer = QTimer(self)
        self.timer.setInterval(TICK)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.apply_timer = QTimer(self)
        self.apply_timer.setSingleShot(True)
        self.apply_timer.timeout.connect(self._apply)

    def roots(self):
        """Отмеченные вместе с родителями папки-ссылки суперналожений,
        у которых над ними нет другой такой ссылки."""
        folders = {f.key: f for f in self.window.myplaces.folders}
        out = []
        for item in folders.values():
            if not item.link or item.view_mode != "onRegion":
                continue
            node, shown, nested = item, True, False
            seen = set()
            while node is not None and node.key not in seen:
                seen.add(node.key)
                if not node.visible:
                    shown = False
                    break
                if node is not item and node.link \
                        and node.view_mode == "onRegion":
                    nested = True
                node = folders.get(node.parent)
            if shown and not nested:
                out.append(item)
        return out

    def tick(self):
        if self.stopped:
            return
        window = self.window
        view = window.view
        roots = self.roots() if window.planet.earth \
            and view.sky_view is None else []
        keys = {f.key for f in roots}
        for key in list(self.trees):
            if key not in keys:
                self._drop_tree(key)
        if not roots:
            self._set_tiles([])
            return
        now = time.monotonic()
        eye = np.array(view.camera.eye, dtype=np.float64)
        lat, lon, _ = (float(v) for v in ecef_to_geodetic(eye))
        camera = view.camera
        focal = max(view.height(), 1) / (
            2.0 * math.tan(math.radians(camera.fov_y) / 2.0))
        pose = view.navigator.pose
        width, height = ground_size(pose.distance, camera.fov_y,
                                    camera.aspect)
        box = view_box(pose.lat, pose.lon, width, height)
        tiles = []
        for item in roots:
            entry = self.trees.get(item.key)
            if entry is None or entry[0] != item.link:
                self._drop_tree(item.key)
                regions = (item.region,) if item.region else ()
                entry = (item.link, superoverlay.Tree(item.link, regions))
                self.trees[item.key] = entry
            tree = entry[1]
            wanted, shown = tree.step(tuple(eye), (lat, lon), focal, box,
                                      now)
            for node in wanted:
                if len(self.docs) >= DOCUMENTS:
                    break
                self._fetch_doc(item.key, tree, node)
            for node in tree.trim(now):
                self.docs.pop((item.key, node.url), None)
            tiles += shown
        self._set_tiles(tiles)

    # Документы.

    def _fetch_doc(self, key, tree, node):
        node.state = "loading"
        url = node.url
        path = None if netlink.is_web(url) else netlink.local_path(url)
        if path is not None:
            try:
                with open(path, "rb") as fh:
                    data = fh.read()
            except OSError as error:
                self._doc_done(key, tree, node, None, str(error))
                return
            self._doc_done(key, tree, node, data, "")
            return

        def done(data, error, key=key, tree=tree, node=node):
            if self.stopped:
                return
            self.docs.pop((key, node.url), None)
            self._doc_done(key, tree, node, data, error)
        self.docs[(key, url)] = fetch_bytes(url, done)

    def _doc_done(self, key, tree, node, data, error):
        entry = self.trees.get(key)
        if entry is None or entry[1] is not tree:
            return
        folder_tree = None
        if data:
            try:
                folder_tree = kml.read_file(bytes(data))
            except kml.KmlError as problem:
                error = str(problem)
        if folder_tree is None:
            self.window.message = (tr(
                "Тайл суперналожения не загружен: {error}",
                error=error or node.url), time.monotonic())
            self.window._show_state()
        else:
            netlink.resolve_tree(folder_tree, node.url)
        tree.loaded(node, folder_tree)
        # Следующий шаг - из цикла событий: файл на диске приходит сразу,
        # и шаг из шага шёл бы вглубь по уровням тайлов.
        QTimer.singleShot(0, self.tick)

    # Картинки.

    def _image(self, tile):
        """Байты картинки тайла или None, тогда она просится."""
        if tile.image:
            return tile.image
        href = tile.href
        data = self.images.get(href)
        if data is not None:
            # Свежая - в конец, старые уходят первыми.
            self.images[href] = self.images.pop(href)
            return data
        if href in self.failed or href in self.image_replies \
                or len(self.image_replies) >= IMAGES or not href:
            return None
        path = None if netlink.is_web(href) else netlink.local_path(href)
        if path is not None:
            try:
                with open(path, "rb") as fh:
                    data = fh.read()
            except OSError:
                self.failed.add(href)
                return None
            self._keep(href, data)
            return data

        def done(data, error, href=href):
            if self.stopped:
                return
            self.image_replies.pop(href, None)
            if data:
                self._keep(href, bytes(data))
            else:
                self.failed.add(href)
            QTimer.singleShot(0, self.tick)
        self.image_replies[href] = fetch_bytes(href, done)
        return None

    def _keep(self, href, data):
        self.images[href] = data
        while len(self.images) > IMAGES_KEPT:
            self.images.pop(next(iter(self.images)))

    # Растры.

    def _set_tiles(self, tiles):
        """Видимые тайлы, нижние первыми, парами (тайл, закрытие):
        растры тех, чьи картинки уже есть. Тайл, закрытый детьми
        с пришедшими картинками, не рисуется. Новый состав ложится
        в наложение после паузы."""
        found = {}
        for tile, _ in tiles:
            data = self._image(tile)
            if data is not None:
                found[tile.key] = data
        entries = []
        for tile, cover in tiles:
            data = found.get(tile.key)
            if cover is not None and all(key in found for key in cover):
                continue
            if data is None:
                continue
            overlay = core_overlays.Overlay(
                "ground", corners=list(tile.corners), color=tile.color,
                order=tile.order)
            entries.append((tile.key, tile, overlay, data))
        shown = tuple(e[0] for e in entries)
        if shown == self._shown:
            return
        self._shown = shown
        self.entries = entries
        wait = APPLY_GAP - (time.monotonic() - self._applied_at) * 1000.0
        if not self.apply_timer.isActive():
            self.apply_timer.start(max(0, int(wait)))

    def _apply(self):
        if self.stopped:
            return
        self._applied_at = time.monotonic()
        # GroundLayers ставит больший drawOrder выше, при равном порядок
        # прежний - подробные тайлы из конца списка идут первыми.
        entries = [(key, FID, tr("Суперналожение"), overlay,
                    lambda data=data: data)
                   for key, _, overlay, data in reversed(self.entries)]
        layers = self.ground.layers(entries)
        ids = [layer.id() for layer in layers]
        if ids == [layer.id() for layer in self.rasters]:
            return
        self.rasters = layers
        self.window._update_overlay(keep=True)

    def _drop_tree(self, key):
        self.trees.pop(key, None)
        for pair in [p for p in self.docs if p[0] == key]:
            reply = self.docs.pop(pair)
            reply.abort()

    def stop(self):
        """Окно закрывается: таймеры и ответы в пути снимаются, растры
        отпускаются, файлы растров тайлов удаляются."""
        self.stopped = True
        self.timer.stop()
        self.apply_timer.stop()
        for reply in list(self.docs.values()) \
                + list(self.image_replies.values()):
            reply.abort()
        self.docs.clear()
        self.image_replies.clear()
        self.rasters = []
        self.ground.clear()
        locked = []
        for path in glob.glob(os.path.join(folder(), FID + "_*")):
            try:
                os.remove(path)
            except OSError:
                # Файл держит GDAL - уйдёт при следующем закрытии.
                locked.append(path)
        return locked
