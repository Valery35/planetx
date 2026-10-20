# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Наложения картинок и 3D-модели, KML, туры и виды меток.

Часть окна глобуса GlobeWindow (ui/window.py)."""
import hashlib
import math
import os
import time

import numpy as np
from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsCsException, QgsProject, QgsRasterLayer)
from qgis.PyQt.QtCore import QMimeData, Qt
from qgis.PyQt.QtGui import QImage
from qgis.PyQt.QtWidgets import (QApplication, QFileDialog, QInputDialog,
                                 QMessageBox)

from ... import journal
from ...core import lookat, models, overlays
from ...core.ellipsoid import ecef_to_geodetic
from ...core.features import Shape
from ...core.flight import fit_view, lon_span
from ...core.kml import (KOverlay, KmlError, image_ext as kml_image_ext,
                         read_file as read_kml_file, read_kml, write_kml,
                         write_kmz, drop_empty_models, model_files)
from ...core.models import package_file as model_package
from ...core.tour import PathStop, RecordedStop, Stop, clock, thin
from ...i18n import tr
from ...net.overlay import fetch_bytes
from ...qt_compat import enum
from ...render.models import Model as ModelItem
from ..overlays import (OUTLINE, BoxVertices, CornerVertices, ModelVertices,
                        OverlayDialog, ground_geotiff, image_rgba)
from .. import globemenu
from ..handles import PropVertices, ShapeEdit, TourEdit
from ..myplaces import tour_text
from ..placeprops import PlaceProperties
from .base import (KML_MIME, MODEL_DISTANCE, MODEL_SIDE, MODEL_TILT,
                   SCREEN_TOP, SEARCH_MIN_DISTANCE)


class PicturesMixin:
    """Часть окна глобуса GlobeWindow."""

    # Наложения картинок (core/overlays.py, ui/overlays.py).

    def _overlay_edit(self, item):
        """Наложение item с правками открытого окна свойств: (метка
        картинки, Overlay, байты()). Углы картинки на поверхности
        приходят из окна после паузы в движении, см. _overlay_preview.
        Картинка - из файла меток, новая из окна или по ссылке."""
        overlay, data, link = self._overlay_edits.get(
            item.key, (item.overlay, None, None))
        if data is not None:
            token = "new:" + hashlib.sha256(data).hexdigest()
            return token, overlay, lambda data=data: data
        if link is None and item.image is not None:
            return item.image, overlay, \
                lambda item=item: self.myplaces.image(item.image)
        link = link if link is not None else item.href
        if item.kind == "model":
            # Модель по ссылке - пакет из файла и файлов рядом с ним.
            return self._link_token(link), overlay, \
                lambda link=link: self._model_link_data(link)
        return self._link_token(link), overlay, \
            lambda link=link: self._link_data(link)

    def _model_link_data(self, link):
        """Пакет модели по ссылке на файл .dae, .gltf, .glb или .obj или
        None. Адрес в сети у модели не читается - у неё файлы рядом."""
        if not link or link.startswith(("http://", "https://")):
            return None
        return models.package_file(link)

    def _link_token(self, link):
        """Метка картинки по ссылке: путь и время правки файла или адрес
        и пришёл ли ответ. Правка файла пересобирает растр."""
        if not link:
            return "link:"
        if link.startswith(("http://", "https://")):
            # Номер картинки растёт с каждой новой картинкой адреса.
            return "link:{}:{}".format(link, self._link_gen.get(link))
        try:
            stamp = os.path.getmtime(link)
        except OSError:
            stamp = None
        return "link:{}:{}".format(link, stamp)

    def _link_data(self, link):
        """Байты картинки по ссылке или None. Файл читается сразу, адрес
        в сети просится через кэш QGIS, ответ хранится в памяти, в файл
        меток не пишется - так ведёт себя поле Link Google Earth."""
        if not link:
            return None
        if link.startswith(("http://", "https://")):
            if link in self._link_images:
                return self._link_images[link]
            self._ask_link(link)
            return None
        try:
            with open(link, "rb") as stream:
                return stream.read()
        except OSError:
            return None

    def _ask_link(self, link, fresh=False):
        """Запросить картинку по адресу, если запроса ещё нет. fresh -
        мимо кэша QGIS, для обновления по промежутку."""
        self._link_asked[link] = time.monotonic()
        if link not in self._href_replies:
            self._href_replies[link] = fetch_bytes(
                link, lambda data, error, link=link:
                self._link_done(link, data, error), fresh=fresh)

    def _refresh_links(self):
        """Картинки по ссылке с обновлением: адрес просится заново мимо
        кэша, файл перечитывается по времени правки. Обновляются только
        видимые наложения, как у refreshMode onInterval в KML."""
        files = False
        now = time.monotonic()
        if self.view.sky_view is not None:
            return
        maps = self._map_grounds()
        for item in self.myplaces.overlays:
            if not item.visible or item.body != self.planet.key \
                    or not self._overlay_time_ok(item, maps):
                continue
            _, overlay, _ = self._overlay_edit(item)
            interval = overlays.refresh_interval(overlay.refresh)
            edits = self._overlay_edits.get(item.key)
            link = edits[2] if edits is not None and edits[2] is not None \
                else (item.href if item.image is None else None)
            if not interval or not link:
                continue
            asked = self._link_asked.get(link)
            if asked is not None and now - asked < interval:
                continue
            if link.startswith(("http://", "https://")):
                self._ask_link(link, fresh=True)
            else:
                self._link_asked[link] = now
                files = True
        if files:
            # Метка картинки файла - время его правки.
            self._refresh_overlays()

    def _link_done(self, link, data, error):
        self._href_replies.pop(link, None)
        if data and not QImage.fromData(data).isNull():
            data = bytes(data)
            if data != self._link_images.get(link):
                # Новая картинка - новая метка, растр и текстура заново.
                self._link_images[link] = data
                self._link_gen[link] = self._link_gen.get(link, 0) + 1
                self._refresh_overlays()
        else:
            self.message = (tr("Картинка по ссылке не загрузилась: {link}",
                               link=link), time.monotonic())
            self._show_state()
        self._ground_export_ready()

    def _overlay_bytes(self, item):
        """Байты картинки наложения: из файла меток или по ссылке.
        У модели - пакет её файлов."""
        if item.image is not None:
            return self.myplaces.image(item.image)
        if item.kind == "model":
            return self._model_link_data(item.href)
        return self._link_data(item.href)

    def _refresh_overlays(self):
        """Картинки на поверхности - растры в наложении, фото - плоскости
        в 3D, картинки на экране - поверх вида. Видны отмеченные
        наложения тела на глобусе в промежутке шкалы времени."""
        if not hasattr(self, "ground_layers"):
            return
        maps = self._map_grounds()
        items = [o for o in self.myplaces.overlays
                 if o.visible and self._overlay_time_ok(o, maps)
                 and o.body == self.planet.key
                 and self.view.sky_view is None]
        entries = []
        photos = []
        screens = []
        shown_models = []
        moving = []
        for item in items:
            token, overlay, data = self._overlay_edit(item)
            if item.kind == "model" and overlay.track:
                moving.append((item.key, item.name, overlay.track,
                               overlay.mode))
            if item.kind == "ground":
                entries.append((token, item.fid, item.name, overlay, data))
            elif item.kind == "model":
                shown_models.append((token, overlay, data))
            elif item.kind == "photo":
                photos.append((token, overlay, data))
            else:
                screens.append((token, overlay, data))
        layers = self.ground_layers.layers(entries)
        ids = [layer.id() for layer in layers]
        if ids != self._ground_ids:
            self._ground_rasters = layers
            self._ground_ids = ids
            self._update_overlay(keep=True)
        else:
            self._apply_map_compare()
        key = [(token, overlay.params()) for token, overlay, _ in photos]
        if key != self._photo_key:
            self._photo_key = key
            walls = []
            for token, overlay, data in photos:
                rgba = self._photo_images.get(token)
                if rgba is None:
                    rgba = image_rgba(data())
                    if rgba is None:
                        continue
                    self._photo_images[token] = rgba
                if overlay.color[3] < 255:
                    rgba = rgba.copy()
                    rgba[..., 3] = (rgba[..., 3].astype(np.uint16)
                                    * overlay.color[3] // 255)
                walls.append(overlays.photo_mesh(overlay.camera, overlay.fov,
                                                 overlay.near) + (rgba,))
            self.view.photos.set_walls(walls)
            self.view.update()
            # Текстуры прежних картинок, например до обновления по
            # ссылке, не копятся.
            tokens = {token for token, _, _ in photos}
            self._photo_images = {token: rgba for token, rgba
                                  in self._photo_images.items()
                                  if token in tokens}
        self._show_models(shown_models)
        if getattr(self, "model_tracks", None) is not None:
            self.model_tracks.set_items(moving)
        key = [(token, overlay.params()) for token, overlay, _ in screens]
        if key != self._screen_key:
            self._screen_key = key
            self.screen_overlays.set_items(
                [(overlay, data()) for _, overlay, data in screens])

    def _model_data(self, token, data):
        """Разобранная модель по метке пакета: (части core.models, {путь
        картинки: RGBA}, анимация или None) или None, если файл не
        читается. Разбор - раз
        на пакет, итог хранится, пока модель видна."""
        if token in self._model_cache:
            return self._model_cache[token]
        found = None
        package = data()
        if package:
            try:
                parts, pictures, moving = models.read_animated(package)
                found = (parts, {path: image_rgba(raw, MODEL_SIDE)
                                 for path, raw in pictures.items()}, moving)
            except models.ModelError as error:
                journal.note("model unreadable: {}".format(error))
                self.message = (tr("Модель не читается: {error}",
                                   error=str(error)), time.monotonic())
                self._show_state()
        self._model_cache[token] = found
        return found

    def _show_models(self, shown):
        """3D-модели на глобус: части в вершины по месту окна свойств
        или файла. shown - [(метка пакета, Overlay, байты())]."""
        key = [(token, overlay.params()) for token, overlay, _ in shown]
        if key == self._model_key:
            return
        self._model_key = key
        out = []
        for token, overlay, data in shown:
            found = self._model_data(token, data)
            if found is None:
                continue
            parts, pictures, moving = found
            if overlay.track:
                out.append(self._track_model(token, overlay, parts,
                                             pictures, moving))
                continue
            lat, lon, alt, heading, tilt, roll = overlay.camera
            arrays = models.vertices(parts, lat, lon, heading, tilt, roll,
                                     overlay.scale)
            out.append(ModelItem(
                (token, overlay.params()),
                [(array, pictures.get(part.image), part.rgba, part.track)
                 for array, part in zip(arrays, parts)],
                (lat, lon, overlay.mode, alt),
                models.radius(parts, overlay.scale),
                overlay.color[3] / 255.0, moving,
                models.frame(lat, lon, heading, tilt, roll, overlay.scale)))
        tokens = {token for token, _, _ in shown}
        self._model_cache = {token: value for token, value
                             in self._model_cache.items()
                             if token in tokens}
        self.view.models.set_models(out)
        self.view.update()

    def _track_model(self, token, overlay, parts, pictures, moving):
        """Модель gx:Track: вершины один раз у начала координат, место
        и поворот на момент шкалы времени (core.track.model_pose).
        Закрытая шкала - модель в конце пути, вне времени пути её нет."""
        from ...core.track import model_pose
        scale = overlay.scale
        base = models.frame(0.0, 0.0, 0.0, 0.0, 0.0, scale)
        arrays = models.vertices(parts, 0.0, 0.0, 0.0, 0.0, 0.0, scale)
        rows = overlay.track
        first = rows[0]

        def mover(now):
            del now
            span = getattr(self, "_time_range", None)
            pose = model_pose(rows, span[1] if span else rows[-1][0])
            if pose is None:
                return None
            lat, lon, alt, heading, tilt, roll = pose
            return lat, lon, models.moved(base, lat, lon, heading, tilt,
                                          roll, scale), alt
        return ModelItem(
            (token, overlay.params()),
            [(array, pictures.get(part.image), part.rgba, part.track)
             for array, part in zip(arrays, parts)],
            (first[1], first[2], overlay.mode, first[3]),
            models.radius(parts, scale), overlay.color[3] / 255.0, moving,
            base, mover=mover)

    def model_summary(self, item):
        """Сведения о модели для окна свойств: части, вершины, размеры
        в метрах по осям X, Y, Z или пустая строка."""
        token, overlay, data = self._overlay_edit(item)
        found = self._model_data(token, data)
        if found is None:
            return tr("Модель не читается.")
        parts, pictures, moving = found
        box = models.bounds(parts)
        size = (box[1] - box[0]) * abs(np.asarray(overlay.scale))
        count = sum(len(part.positions) for part in parts)
        text = tr("Треугольников {count}, материалов {parts}, картинок "
                  "{images}. Размер {x:.1f} × {y:.1f} × {z:.1f} м.",
                  count=count // 3, parts=len(parts),
                  images=len([p for p in pictures.values()
                              if p is not None]),
                  x=size[0], y=size[1], z=size[2])
        if moving is not None:
            text += " " + tr("Анимация {seconds:.1f} с, движется частей "
                             "{tracks}.", seconds=moving.duration,
                             tracks=len(moving.tracks))
        return text

    def model_extent(self, item):
        """Коробка модели (xmin, xmax, ymin, ymax) в её единицах или
        None, если файл не читается."""
        token, _, data = self._overlay_edit(item)
        found = self._model_data(token, data)
        if found is None:
            return None
        box = models.bounds(found[0])
        return (float(box[0][0]), float(box[1][0]), float(box[0][1]),
                float(box[1][1]))

    def add_model(self, folder=None, path=None):
        """«Добавить → 3D-модель…»: файл Collada, glTF или OBJ встаёт
        в точку взгляда, потом открывается окно свойств. KMZ открывается как
        файл меток - модель в нём уже стоит на своём месте. Возвращает
        ключ или None."""
        if path is None:
            path, _ = QFileDialog.getOpenFileName(
                self, tr("3D-модель"), "",
                tr("3D-модели (*.dae *.gltf *.glb *.obj *.kmz)"))
        if not path:
            return None
        if path.lower().endswith(".kmz"):
            return self.import_kml(folder, path)
        package = model_package(path)
        if package is None:
            self.message = (tr("Модель не читается: {name}",
                               name=os.path.basename(path)),
                            time.monotonic())
            self._show_state()
            return None
        pose = self.view.navigator.pose
        overlay = overlays.Overlay(
            "model", camera=(pose.lat, pose.lon, 0.0, 0.0, 0.0, 0.0))
        name = os.path.splitext(os.path.basename(path))[0]
        # Модель - ссылкой на файл, как Link у Google Earth: правка файла
        # видна на глобусе. В файл меток её копирует поле «Хранение».
        key = self.myplaces.add_overlay(KOverlay(
            name, overlay, href=path, view=self.current_view()), folder)
        if key is not None:
            self.panel.select_place(key)
            self._open_overlay_properties(self.myplaces.find(key))
        return key

    def add_overlay(self, kind, folder=None, path=None):
        """«Добавить → Картинку на поверхности, Фото, Картинку на
        экране»: картинка из файла встаёт по нынешнему виду, потом
        открывается окно свойств. Возвращает ключ или None."""
        if path is None:
            path, _ = QFileDialog.getOpenFileName(
                self, tr("Картинка наложения"), "",
                tr("Картинки (*.png *.jpg *.jpeg *.gif)"))
        if not path:
            return None
        with open(path, "rb") as stream:
            data = stream.read()
        image = QImage()
        if not image.loadFromData(data):
            self.message = (tr("Картинка не читается: {name}",
                               name=os.path.basename(path)),
                            time.monotonic())
            self._show_state()
            return None
        aspect = image.width() / float(max(image.height(), 1))
        pose = self.view.navigator.pose
        camera = self.view.camera
        if kind == "ground":
            visible = 2.0 * pose.distance * math.tan(
                math.radians(camera.fov_y) / 2.0) * camera.aspect
            overlay = overlays.Overlay("ground", box=overlays.fit_box(
                pose.lat, pose.lon, overlays.NEW_SHARE * visible, aspect))
        elif kind == "photo":
            lat, lon, alt = (float(v) for v in ecef_to_geodetic(camera.eye))
            shot, fov, near = overlays.view_camera(
                lat, lon, alt, pose.heading, pose.tilt, camera.fov_y,
                aspect, pose.distance)
            overlay = overlays.Overlay("photo", camera=shot, fov=fov,
                                       near=near)
        else:
            overlay = overlays.Overlay(
                "screen", overlay_xy=(0.0, 1.0, "fraction", "fraction"),
                screen_xy=(10.0, SCREEN_TOP, "pixels", "insetPixels"))
        name = os.path.splitext(os.path.basename(path))[0]
        key = self.myplaces.add_overlay(KOverlay(
            name, overlay, image=data,
            view=self.current_view() if kind != "screen" else None),
            folder)
        if key is not None:
            self.panel.select_place(key)
            self._open_overlay_properties(self.myplaces.find(key))
        return key

    def ground_to_project(self, key=None, target=None):
        """Картинки на поверхности - слоями проекта QGIS: файлы GeoTIFF
        в WGS84 по углам картинки и растровые слои в группе «PlanetX -
        картинки». key - картинка или папка, у папки - все её картинки
        на поверхности. target - файл для одной картинки или папка для
        нескольких, без него - окно выбора. Возвращает новые слои."""
        keys = self.myplaces.with_contents([key]) if key \
            else [o.key for o in self.myplaces.overlays]
        items = [o for o in self.myplaces.overlays
                 if o.key in keys and o.kind == "ground"]
        if not items:
            self.message = (tr("В папке нет картинок на поверхности."),
                            time.monotonic())
            self._show_state()
            return []
        start = QgsProject.instance().homePath() or os.path.expanduser("~")
        if target is None and len(items) == 1:
            target, _ = QFileDialog.getSaveFileName(
                self, tr("Картинка в проект QGIS"),
                os.path.join(start, (items[0].name or "overlay") + ".tif"),
                tr("GeoTIFF (*.tif)"))
        elif target is None:
            target = QFileDialog.getExistingDirectory(
                self, tr("Папка для картинок"), start)
        if not target:
            return []
        # Скрытая картинка по ссылке ещё не загружена. Выгрузка ждёт
        # ответов и идёт из _link_done, когда пришёл последний.
        for item in items:
            self._overlay_bytes(item)
        if any(item.image is None and item.href in self._href_replies
               for item in items):
            self._ground_export = ([item.key for item in items], target)
            self.message = (tr("Картинки по ссылкам загружаются, слои "
                               "добавятся после загрузки."),
                            time.monotonic())
            self._show_state()
            return []
        return self._write_ground(items, target)

    def _ground_export_ready(self):
        """Ждущая выгрузка в проект, если пришли все её ссылки."""
        if self._ground_export is None:
            return
        keys, target = self._ground_export
        items = [o for o in self.myplaces.overlays if o.key in keys]
        if any(item.image is None and item.href in self._href_replies
               for item in items):
            return
        self._ground_export = None
        self._write_ground(items, target)

    def _write_ground(self, items, target):
        """Файлы GeoTIFF картинок items и слои в группе «PlanetX -
        картинки». target - файл одной картинки или папка."""
        project = QgsProject.instance()
        group = project.layerTreeRoot().findGroup(tr("PlanetX - картинки"))
        if group is None:
            group = project.layerTreeRoot().insertGroup(
                0, tr("PlanetX - картинки"))
        added = []
        for n, item in enumerate(items):
            if len(items) == 1 and not os.path.isdir(target):
                path = target
            else:
                name = "".join(c if c.isalnum() or c in "-_ " else "_"
                               for c in (item.name or "overlay")).strip()
                path = os.path.join(target, "{}_{}.tif".format(
                    name or "overlay", n + 1))
            ok = ground_geotiff(item.fid, item.overlay,
                                self._overlay_bytes(item), path)
            layer = QgsRasterLayer(path, item.name or os.path.basename(path),
                                   "gdal") if ok else None
            if layer is None or not layer.isValid():
                self.message = (tr("Картинка «{name}» не записана.",
                                   name=item.name), time.monotonic())
                self._show_state()
                continue
            layer.renderer().setOpacity(item.overlay.color[3] / 255.0)
            project.addMapLayer(layer, False)
            group.addLayer(layer)
            added.append(layer)
        if added:
            self.message = (tr("В проект добавлено картинок {count}.",
                               count=len(added)), time.monotonic())
            self._show_state()
        return added

    def _open_overlay_properties(self, item):
        """Немодальное окно свойств наложения. Правки видны сразу,
        «OK» пишет их в файл, «Отмена» возвращает прежнее."""
        key = item.key
        dialog = self.overlay_dialogs.get(key)
        if dialog is None:
            dialog = OverlayDialog(item, self._overlay_bytes(item), self)
            dialog.setAttribute(enum(Qt, "WidgetAttribute",
                                     "WA_DeleteOnClose"))
            self.overlay_dialogs[key] = dialog
            dialog.changed.connect(
                lambda key=key: self._overlay_preview(key))
            dialog.mode_changed.connect(
                lambda dialog=dialog: self._overlay_tool(dialog))

            def done(result, key=key, dialog=dialog):
                self.overlay_dialogs.pop(key, None)
                self._overlay_edits.pop(key, None)
                self.previews.pop(key, None)
                self._end_prop_vertices(dialog)
                if result:
                    self.myplaces.set_overlay(
                        key, dialog.overlay,
                        image=dialog.image if dialog.link is None else None,
                        link=dialog.link, **dialog.values())
                else:
                    self._refresh_shapes()
            dialog.finished.connect(done)
        self.side.host(dialog)
        self._overlay_tool(dialog)
        self._overlay_preview(key)

    def _overlay_tool(self, dialog):
        """Ручки картинки на поверхности по способу привязки: рамка -
        сдвиг, поворот и растяжение, четыре угла - каждый угол сам."""
        if dialog.item.kind not in ("ground", "model") \
                or self._place_open() or self._ruler_open():
            return
        self._end_prop_vertices(dialog)
        if dialog.item.kind == "model":
            tool = ModelVertices(self, dialog)
        elif dialog.overlay.box is not None:
            tool = BoxVertices(self, dialog)
        else:
            tool = CornerVertices(self, dialog, ShapeEdit(
                "polygon", dialog.points, dialog.set_points))
        self.view.vertex_tool = tool
        self.handles.tool = tool
        self.handles.sync()

    def _overlay_preview(self, key):
        """Правка окна свойств наложения на глобусе. Контур углов
        картинки на поверхности - сразу, сама картинка - после паузы
        в движении: растр пересобирается целиком."""
        dialog = self.overlay_dialogs.get(key)
        if dialog is None:
            return
        overlay = dialog.overlay
        if overlay.kind == "ground":
            self.previews[key] = Shape("polygon", list(overlay.corners),
                                       color=OUTLINE, width=2.0)
            self._ground_pending[key] = dialog
            self._ground_timer.start()
        else:
            self._overlay_edits[key] = (
                overlays.from_params(overlay.kind, overlay.params()),
                dialog.image if dialog.link is None else None, dialog.link)
            if overlay.kind == "model":
                self._model_frame(key, dialog)
        self._refresh_shapes()
        self.handles.sync()

    def _model_frame(self, key, dialog):
        """Рамка модели на земле - след её коробки, по ней ходят ручки.
        Другой файл модели - другая коробка и сведения под полями."""
        token = self._overlay_edit(dialog.item)[0]
        if token != getattr(dialog, "model_token", None):
            dialog.model_token = token
            dialog.extent = self.model_extent(dialog.item)
            dialog.set_model_info(self.model_summary(dialog.item))
        overlay = dialog.overlay
        if dialog.extent is None:
            self.previews.pop(key, None)
            return
        box = overlays.model_box(overlay.camera, overlay.scale,
                                 dialog.extent)
        self.previews[key] = Shape("polygon", overlays.box_corners(*box),
                                   color=OUTLINE, width=2.0)

    def _ground_settled(self):
        """Пауза в движении углов: картинки на поверхности по окнам."""
        pending, self._ground_pending = self._ground_pending, {}
        for key, dialog in pending.items():
            if key in self.overlay_dialogs:
                overlay = dialog.overlay
                self._overlay_edits[key] = (
                    overlays.from_params("ground", overlay.params(),
                                         list(overlay.corners)),
                    dialog.image if dialog.link is None else None,
                    dialog.link)
        self._refresh_overlays()

    def _open_place_properties(self, place):
        """Немодальное окно свойств метки. Правки видны на глобусе
        сразу, «OK» записывает их, «Отмена» возвращает прежний вид."""
        key = place.key
        dialog = self.prop_dialogs.get(key)
        if dialog is None:
            dialog = PlaceProperties(place, self,
                                     current_view=self.current_view,
                                     current_layers=self.view_state)
            dialog.setAttribute(enum(Qt, "WidgetAttribute",
                                     "WA_DeleteOnClose"))
            self.prop_dialogs[key] = dialog

            def preview(shape, key=key):
                self.previews[key] = shape
                self._refresh_shapes()
                self.handles.sync()

            def done(result, key=key, dialog=dialog):
                self.prop_dialogs.pop(key, None)
                self.previews.pop(key, None)
                self._end_prop_vertices(dialog)
                if result:
                    samples = dialog.edited_tour()
                    if dialog.shape_changed():
                        self.myplaces.set_shape(key, dialog.preview())
                    values = dialog.values()
                    if samples is not None:
                        values["tour"] = tour_text(samples)
                    self.myplaces.update(key, values)
                else:
                    self._refresh_shapes()
            dialog.changed.connect(preview)
            dialog.finished.connect(done)
            if place.tour:
                # Путь облёта на глобусе не рисуется, пока окно закрыто.
                preview(dialog.preview())
        self.side.host(dialog)
        self._begin_prop_vertices(place, dialog)

    def _begin_prop_vertices(self, place, dialog):
        """Вершины метки тянутся мышью, пока открыто её окно свойств.
        Окно «Новая метка» и линейка главнее - при них вершины свойств
        не берутся."""
        if not (globemenu.editable(place) or place.tour) \
                or self._place_open() or self._ruler_open():
            return
        edit = TourEdit(dialog.points, dialog.set_points) if place.tour \
            else ShapeEdit(place.kind, dialog.points, dialog.set_points)
        tool = PropVertices(self, dialog, edit)
        self.view.vertex_tool = tool
        self.handles.tool = tool
        self.handles.sync()

    def _end_prop_vertices(self, dialog):
        """Снять ручки окна свойств dialog. Ручки рамки картинки
        (BoxVertices) не наследуют PropVertices, поэтому окно узнаётся
        по полю dialog. Иначе после закрытия окна с WA_DeleteOnClose
        ручки обращались к удалённому окну, QGIS 3.40.15, 9 октября
        2026 года."""
        tool = self.handles.tool
        if getattr(tool, "dialog", None) is dialog:
            self.handles.tool = self.draw_vertices
            if self.view.vertex_tool is tool:
                self.view.vertex_tool = self.wedge_corners \
                    if self.view.wedge is not None else None
            self.handles.sync()

    def copy_places(self, keys):
        """Метки и папки keys в буфер обмена текстом KML, как Google
        Earth. Пустой keys - все «Мои метки». Текст открывается
        в блокноте, правится и вставляется обратно."""
        tree = self.myplaces.export_keys(keys) if keys \
            else self.myplaces.export_tree(None)
        text = write_kml(tree)
        mime = QMimeData()
        mime.setText(text)
        mime.setData(KML_MIME, text.encode("utf-8"))
        QApplication.clipboard().setMimeData(mime)
        self.message = (tr("KML в буфере обмена, меток {count}.",
                           count=len(tree.places())), time.monotonic())
        self._show_state()
        return text

    def paste_places(self, folder=None):
        """KML из буфера обмена в папку folder (None - корень «Моих
        меток»). Содержимое ложится само, без новой папки. Возвращает
        количество вставленных меток."""
        mime = QApplication.clipboard().mimeData()
        data = b""
        if mime is not None and mime.hasFormat(KML_MIME):
            data = bytes(mime.data(KML_MIME))
        elif mime is not None and mime.hasText():
            data = mime.text().encode("utf-8")
        tree = None
        if data.strip():
            try:
                tree = read_kml(data, tr("Вставка"))
            except KmlError:
                tree = None
        if tree is None or not tree.children:
            self.message = (tr("В буфере обмена нет меток KML."),
                            time.monotonic())
            self._show_state()
            return 0
        self.myplaces.import_tree(tree, folder, wrap=False)
        count = len(tree.places())
        self.message = (tr("Вставлено меток {count}.", count=count),
                        time.monotonic())
        self._show_state()
        return count

    def import_kml(self, parent=None, path=None):
        """Открыть KML или KMZ в папку parent новой папкой и подлететь
        к содержимому, как Google Earth."""
        if path is None:
            path, _ = QFileDialog.getOpenFileName(
                self, tr("Открыть KML или KMZ"), "",
                tr("KML и KMZ (*.kml *.kmz)"))
        if not path:
            return None
        name = os.path.splitext(os.path.basename(path))[0]
        try:
            with open(path, "rb") as fh:
                tree = read_kml_file(fh.read(), name)
        except (OSError, KmlError) as error:
            QMessageBox.warning(self, tr("Открыть KML или KMZ"), tr(
                "Файл не прочитан: {error}", error=str(error)))
            return None
        places = tree.places()
        found = tree.overlays()
        # Картинка наложения простого KML - ссылка на файл рядом с ним,
        # как у Google Earth. Из KMZ картинка ложится в файл меток.
        for item in found:
            if item.image is None and item.href and "://" not in item.href \
                    and not os.path.isabs(item.href):
                item.href = os.path.normpath(os.path.join(
                    os.path.dirname(path), item.href.replace("/", os.sep)))
            if item.kind == "model" and item.image is None:
                # Модель простого KML - файлы рядом, в файл меток они
                # ложатся пакетом.
                item.image = model_package(item.href, item.aliases)
        # Модель без файлов не встаёт.
        drop_empty_models(tree)
        found = tree.overlays()
        if not places and not found:
            QMessageBox.information(self, tr("Открыть KML или KMZ"), tr(
                "В файле нет точек, линий, многоугольников и наложений."))
        key = self.myplaces.import_tree(tree, parent)
        if key is not None:
            self.panel.select_place(key)
        points = [p for place in places for p in place.points] + [
            p for item in found for p in item.overlay.corners] + [
            tuple(item.overlay.camera[:2]) for item in found
            if item.kind == "model"]
        if points:
            lats = [p[0] for p in points]
            west, east = lon_span(p[1] for p in points)
            camera = self.view.camera
            lat, lon, distance = fit_view(west, min(lats), east,
                                          max(lats), camera.fov_y,
                                          camera.aspect)
            self._fly_to(lat, lon, distance)
        return key

    def export_kml(self, folder=None, path=None):
        """Сохранить папку folder (None - все «Мои метки») в KML или KMZ."""
        tree = self.myplaces.export_tree(folder)
        if path is None:
            path, _ = QFileDialog.getSaveFileName(
                self, tr("Сохранить как KML"), (tree.name or "PlanetX")
                + ".kmz", tr("KMZ (*.kmz);;KML (*.kml)"))
        if not path:
            return False
        kmz = path.lower().endswith(".kmz")
        hrefs = {}
        try:
            for n, item in enumerate(tree.overlays()):
                if item.kind == "model":
                    if item.image is None and kmz:
                        # Модель по ссылке на файл ложится в архив.
                        item.image = self._model_link_data(item.href)
                    if item.image and not kmz:
                        # Файлы модели - в папку рядом с KML.
                        stem = os.path.splitext(os.path.basename(path))[0]
                        prefix = "{}_files/model{}/".format(stem, n + 1)
                        href, aliases, files = model_files(item, prefix)
                        for name, data in files:
                            target = os.path.join(os.path.dirname(path),
                                                  *name.split("/"))
                            os.makedirs(os.path.dirname(target),
                                        exist_ok=True)
                            with open(target, "wb") as fh:
                                fh.write(data)
                        hrefs[id(item)] = (href, aliases)
                    continue
                if item.image is None and item.href \
                        and os.path.isfile(item.href) and kmz:
                    # Картинка по ссылке на файл ложится в архив.
                    with open(item.href, "rb") as fh:
                        item.image = fh.read()
                if item.image and not kmz:
                    # Рядом с KML - папка картинок, ссылки на неё.
                    stem = os.path.splitext(os.path.basename(path))[0]
                    folder = os.path.join(os.path.dirname(path),
                                          stem + "_files")
                    os.makedirs(folder, exist_ok=True)
                    name = "overlay{}.{}".format(n + 1,
                                                 kml_image_ext(item.image))
                    with open(os.path.join(folder, name), "wb") as fh:
                        fh.write(item.image)
                    hrefs[id(item)] = stem + "_files/" + name
            data = write_kmz(tree) if kmz \
                else write_kml(tree, hrefs).encode("utf-8")
            with open(path, "wb") as fh:
                fh.write(data)
        except (OSError, models.ModelError) as error:
            QMessageBox.warning(self, tr("Сохранить как KML"), tr(
                "Файл не записан: {error}", error=str(error)))
            return False
        return True

    def place_stop(self, place, along=False):
        """Остановка над меткой: вид метки, иначе точка, охват линии
        и многоугольника.

        Вид метки (core/lookat.py) задаёт точку взгляда, расстояние,
        азимут и наклон, как вид метки Google Earth. along - путь
        проезжается вдоль, как в туре Google Earth.
        """
        points = place.shape.points
        name = place.shape.name
        if place.tour:
            # Записанный тур: проигрывание, перелёт - к его началу.
            extra = getattr(place, "tour_extra", None) or {}
            recorded = RecordedStop(name, place.tour,
                                    extra.get("bounce", ()),
                                    extra.get("updates", ()))
            # Метки, которые меняет тур, - в папке тура (_tour_live).
            recorded.scope = place.folder
            return recorded if along else Stop(
                name, *place.tour[0][1:])
        if along and place.kind == "line" and len(points) > 1:
            return PathStop(name, points)
        if place.kind == "photo" and getattr(place, "overlay", None):
            # Фото: глаз в точке его камеры, как перелёт Google Earth.
            return Stop(name, *overlays.photo_pose(place.overlay.camera,
                                                   place.overlay.near))
        if place.view is not None:
            return Stop(name, *place.view)
        if place.kind == "model" and getattr(place, "overlay", None):
            # Модель без вида - сбоку и сверху, как здание.
            lat, lon = place.overlay.camera[:2]
            return Stop(name, lat, lon, MODEL_DISTANCE, 0.0, MODEL_TILT)
        if len(points) == 1:
            lat, lon = points[0]
            return Stop(name, lat, lon, SEARCH_MIN_DISTANCE)
        lats = [p[0] for p in points]
        west, east = lon_span(p[1] for p in points)
        camera = self.view.camera
        lat, lon, distance = fit_view(west, min(lats), east,
                                      max(lats), camera.fov_y, camera.aspect)
        return Stop(name, lat, lon, distance)

    def fly_to_folder(self, folder):
        """Перелёт к папке, как двойной щелчок в Google Earth: к виду
        папки, без него - к охвату её меток. Берутся метки тела, которое
        на глобусе, без них - тела первой метки папки."""
        if folder.view is not None:
            self._fly_to(*folder.view)
            return
        places = self.myplaces.places_in(folder.key)
        if not places:
            return
        here = [p for p in places if p.body == self.body_key()]
        if not here:
            self.set_body(places[0].body)
            here = [p for p in places if p.body == self.body_key()]
        points = [pt for p in here for pt in p.shape.points]
        if len(points) == 1 or len(here) == 1:
            stop = self.place_stop(here[0])
            self._fly_to(stop.lat, stop.lon, stop.distance, stop.heading,
                         stop.tilt)
            return
        camera = self.view.camera
        lats = [p[0] for p in points]
        west, east = lon_span(p[1] for p in points)
        lat, lon, distance = fit_view(west, min(lats), east,
                                      max(lats), camera.fov_y, camera.aspect)
        self._fly_to(lat, lon, max(distance, SEARCH_MIN_DISTANCE), 0.0, 0.0)

    def fly_to_place(self, place):
        """Перелёт к метке, как остановка тура. Метка другого тела
        сначала переключает тело."""
        if place.body != self.body_key():
            self.set_body(place.body)
        stop = self.place_stop(place)
        self._fly_to(stop.lat, stop.lon, stop.distance, stop.heading,
                     stop.tilt)
        self._show_time(place.view_time or place.time)
        self._apply_view_layers(getattr(place, "layers", None))

    def _tour_stops(self, folder=None):
        """Остановки тура: отмеченные метки папки folder и вложенных
        папок в порядке списка, None - все «Мои метки»."""
        stops = []
        for place in self.myplaces.places_in(folder):
            # Тур идёт по меткам тела, которое сейчас на глобусе,
            # в небе - по меткам неба.
            if place.visible and place.body == self.body_key():
                stop = self.place_stop(place, along=True)
                stop.time = place.view_time or place.time
                stop.description = place.description or ""
                stop.layers = getattr(place, "layers", None)
                pace = getattr(place, "pace", None)
                if pace:
                    stop.pause, stop.speed = pace
                stops.append(stop)
        return stops

    def _record_toggled(self, on):
        """Кнопка записи тура: начать или закончить и сохранить."""
        if on:
            self._recording = []
            self._record_start = time.monotonic()
            self._record_sample()
            self._record_timer.start()
            return
        self._record_timer.stop()
        samples = thin(self._recording or [])
        self._recording = None
        if len(samples) < 2 or samples[-1][0] <= 0.0:
            self.message = (tr("Тур не записан, камера не двигалась."),
                            time.monotonic())
            self._show_state()
            return
        default = self.new_name(tr("Тур"))
        name, ok = QInputDialog.getText(self, tr("Сохранить тур"),
                                        tr("Название"), text=default)
        if not ok:
            return
        self.save_recorded(samples, name.strip() or default)

    def save_recorded(self, samples, name):
        """Записанный тур в «Мои метки». Линия метки - точки
        взгляда, на глобусе она не рисуется."""
        points = [(s[1], s[2]) for s in samples]
        return self.myplaces.add(
            Shape("line", points, name=name), tour=list(samples),
            folder=self.panel.current_folder(), body=self.body_key())

    def _record_sample(self):
        """Поза камеры в запись, раз в RECORD_PERIOD."""
        if self._recording is None:
            return
        pose = self.view.navigator.pose
        t = time.monotonic() - self._record_start
        self._recording.append((t, pose.lat, pose.lon, pose.distance,
                                pose.heading, pose.tilt))
        self.message = (tr("Запись тура {clock}. Повторный щелчок "
                           "по кнопке записи её заканчивает.",
                           clock=clock(t)), time.monotonic())
        self._show_state()

    def save_view(self):
        """Вид глобуса меткой в «Моих метках», как в Google Earth.

        Метка стоит в точке взгляда, вид - в поле view.
        """
        default = self.new_name(tr("Вид"))
        name, ok = QInputDialog.getText(self, tr("Сохранить вид"),
                                        tr("Название"), text=default)
        if not ok:
            return
        # В небе поза навигатора - взгляд на небо: точка метки -
        # склонение и прямое восхождение, расстояние - поле зрения.
        pose = self.view.navigator.pose
        shape = Shape("point", [(pose.lat, pose.lon)],
                      name=name.strip() or default)
        self.myplaces.add(shape, view=self.current_view(),
                          folder=self.panel.current_folder(),
                          body=self.body_key())

    def current_view(self):
        """Вид глобуса сейчас для метки, core.lookat."""
        pose = self.view.navigator.pose
        return lookat.make(pose.lat, pose.lon, pose.distance,
                           pose.heading, pose.tilt)

    def _fly_extent(self, extent, crs):
        """Перелёт к охвату в системе координат crs, взгляд отвесный.

        Охват пустого слоя пуст, перелёта к нему нет. Прежде он давал
        NaN позы, и каждый кадр QGIS 3.36 падал в paintGL на int(NaN)
        высоты под глазом, 12 октября 2026 года."""
        if extent.isNull():
            return
        wgs = QgsCoordinateReferenceSystem("EPSG:4326")
        transform = QgsCoordinateTransform(crs, wgs, QgsProject.instance())
        try:
            box = transform.transformBoundingBox(extent)
        except QgsCsException:
            return
        corners = (box.xMinimum(), box.yMinimum(), box.xMaximum(),
                   box.yMaximum())
        if box.isNull() or not all(math.isfinite(v) for v in corners):
            return
        camera = self.view.camera
        lat, lon, distance = fit_view(*corners, camera.fov_y, camera.aspect)
        if not all(math.isfinite(v) for v in (lat, lon, distance)):
            return
        self._fly_to(lat, lon, distance)
