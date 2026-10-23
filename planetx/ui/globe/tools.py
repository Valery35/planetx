# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Инструменты вида: снимок, линейка, свой рельеф, видимость, инсоляция,
профиль и разрезы, меню «Моих меток».

Часть окна глобуса GlobeWindow (ui/window.py)."""
import math
import os
import time

import numpy as np
from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsApplication, QgsCsException, QgsProject,
                       QgsRasterLayer)
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtGui import QPainter, QRegion
from qgis.PyQt.QtWidgets import (QApplication, QInputDialog, QMessageBox,
                                 QWidget)

from ...core import (ellipsoid, lookat, placetree, insolation, section, slabs,
                     viewshed)
from ...core.measure import LENGTH_UNITS, convert, number, segment_midpoints
from ...core.planets import EARTH_PLANET
from ...core.placetree import is_folder
from ...core.places import Place as MarkPlace
from ... import journal
from ...i18n import tr
from ...qt_compat import enum
from ..measure import RulerDialog, unit_short, _xy as ruler_xy
from ..elevation import HeightSource, ProfileDialog
from ..section import SectionDialog
from ..myplaces import OverlayItem
from ..project import (map_layers, read_bathymetry, read_grids, read_insets,
                       read_zlayers, read_ztrue, set_visible_on_map,
                       write_bathymetry, write_grids, write_insets,
                       write_shown, write_zlayers, write_ztrue)
from ..netlink import LinkDialog
from ..inset import prepare as prepare_inset, water_mesh
from ..bathymetry import REMOVE as BATHY_REMOVE, BathymetryDialog
from ..folderprops import FolderDialog
from ..viewshed import ResultTiles, ViewshedDialog, display_level
from ..insolation import InsolationDialog
from ..roofs import RoofLoader
from ...core import roofs
from ..subsection import ModelSectionDialog, build as model_section
from ..snapshot import SnapshotDialog, draw_attribution, plain_text
from .base import (CALC_BUDGET, HEIGHT_CHUNK, SECTION_TIME_PAUSE,
                   VIEWSHED_POLL, VIEWSHED_WAIT)

# Здания для инсоляции - и за кругом: тень здания 100 м при солнце 6°
# над горизонтом длиной около 1 км. Выбор помощника.
ROOF_MARGIN = 1000.0


class ToolsMixin:
    """Часть окна глобуса GlobeWindow."""

    # Снимок вида.

    def copy_view(self):
        """Копия вида в буфер обмена, просьба автора от 18 октября 2026
        года. Кадр глобуса и поверх него содержательные слои вида -
        шкалы, подписи источников, знак PlanetX, надписи неба, картинки
        на экране, подпись остановки тура. Панель значков, органы
        навигации, значок загрузки, шкала времени, панель тура, шторка,
        ручки и ползунок палеогеографии в картинку не идут. Их не
        прячут на экране - скрытая шкала времени поменяла бы промежуток
        данных."""
        view = self.view
        tools = {self.toolbar, self.navpad, self.spinner, self.timebar,
                 self.swipe_bar, self.handles,
                 getattr(self, "paleo_bar", None),
                 getattr(getattr(self, "tour", None), "bar", None),
                 getattr(self, "guide", None),
                 # Подпись источников с тенью и знак PlanetX render не
                 # рисует - их кладёт draw_attribution, как у снимка.
                 self.attribution, self.brand}
        image = view.grabFramebuffer()
        image.setDevicePixelRatio(view.devicePixelRatioF())
        painter = QPainter(image)
        children = enum(QWidget, "RenderFlag", "DrawChildren")
        for child in view.children():
            if not isinstance(child, QWidget) or child in tools \
                    or not child.isVisible():
                continue
            child.render(painter, child.pos(), QRegion(), children)
        painter.end()
        ratio = image.devicePixelRatio()
        image.setDevicePixelRatio(1.0)
        draw_attribution(image, plain_text(self.attribution.text()), ratio)
        image.setDevicePixelRatio(ratio)
        QApplication.clipboard().setImage(image)
        journal.note("copy view {}x{}".format(image.width(), image.height()))
        self.message = (tr("Вид скопирован в буфер обмена."),
                        time.monotonic())
        self._show_state()
        return image

    def _open_snapshot(self, to_layout):
        # Окно строится заново: пропорции окна глобуса и список макетов
        # с прошлого раза могли измениться. Окно с начатым снимком
        # остаётся.
        dialog = self.shot_dialogs.get(to_layout)
        if dialog is not None and not dialog.mine:
            dialog.deleteLater()
            dialog = None
        if dialog is None and self.view.shot is None:
            dialog = SnapshotDialog(self, to_layout)
            self.shot_dialogs[to_layout] = dialog
        if dialog is None:
            return  # идёт снимок другого окна
        dialog.show()
        dialog.raise_()

    # Линейка.

    def _true_heights(self, lats, lons):
        """Настоящие высоты рельефа, без вертикального масштаба."""
        return self.view.store.heights_at(lats, lons, scaled=False)

    def _has_height_tile(self, key):
        # Тайлов глубже предельного уровня источника нет, у тела без
        # высот их нет совсем: линейка и профиль их не ждут. Иначе вид
        # просил бы на Марсе земные тайлы Terrarium.
        if key in self.view.store.tiles:
            return True
        if self.terrain_loader is None:
            return True
        return key[0] > self.view.store.cap(key)

    # Свой рельеф.

    def _load_insets(self):
        """Врезки своего рельефа из записи проекта. Нижний в проекте
        растр врезается первым, верхний - последним."""
        ids = read_insets()
        lakes = read_bathymetry()
        order = {layer.id(): n for n, layer in enumerate(map_layers())}
        entries = []
        for layer_id in sorted(ids, key=lambda i: -order.get(i, -1)):
            layer = QgsProject.instance().mapLayer(layer_id)
            if layer is None:
                continue
            QApplication.setOverrideCursor(enum(Qt, "CursorShape",
                                                "WaitCursor"))
            try:
                entry = prepare_inset(layer, lakes.get(layer_id))
            finally:
                QApplication.restoreOverrideCursor()
            if isinstance(entry, str):
                self.message = (tr("Растр «{name}» не стал рельефом "
                                   "глобуса: {why}.", name=layer.name(),
                                   why=entry), time.monotonic())
                continue
            entries.append(entry)
        self.insets = tuple(entries)
        self.panel.inset_ids = set(ids)
        self._update_water()

    def _update_water(self):
        """Вода врезок с батиметрией на уровне водоёма (ui.inset.
        water_mesh). Без рельефа и вне Земли воды нет: дно и вода
        легли бы в одну плоскость."""
        water = self.view.lake_water
        water.clear()
        scale = self._relief_target()
        if not scale or not getattr(self, "planet", EARTH_PLANET).earth:
            self.view.update()
            return
        for entry in getattr(self, "insets", ()):
            if entry.lake is not None:
                water.set_mesh(entry.layer_id, water_mesh(entry, scale))
        self.view.update()

    def edit_bathymetry(self, layer_id):
        """Окно «Батиметрия водоёма» растра layer_id в панели свойств.
        Возвращает окно, итог - _bathymetry_done."""
        layer = QgsProject.instance().mapLayer(layer_id)
        if layer is None:
            return None
        lakes = read_bathymetry()
        level = 0.0
        extent = layer.extent()
        if not extent.isEmpty():
            # Высота рельефа в середине растра - обычно поверхность воды.
            lat, lon = self._layer_center(layer)
            if lat is not None:
                level = float(self.view.store.heights_at(
                    [lat], [lon], scaled=False)[0])
                level = round(level, 1) if math.isfinite(level) else 0.0
        dialog = BathymetryDialog(layer.name(), lakes.get(layer_id), level,
                                  self)
        dialog.setAttribute(enum(Qt, "WidgetAttribute", "WA_DeleteOnClose"))
        dialog.finished.connect(
            lambda result, d=dialog: self._bathymetry_done(layer_id, d,
                                                           result))
        self.side.host(dialog)
        return dialog

    def _bathymetry_done(self, layer_id, dialog, result):
        """Окно «Батиметрия водоёма» закрыто: OK - растр врезкой
        с батиметрией, «Убрать» - без неё, «Отмена» - без перемен."""
        lakes = read_bathymetry()
        ids = [i for i in read_insets() if i != layer_id]
        if result == BATHY_REMOVE:
            lakes.pop(layer_id, None)
        elif result:
            lakes[layer_id] = dialog.setting()
            ids.append(layer_id)
        else:
            return
        write_bathymetry(lakes)
        self.set_insets(ids)

    def sounding_bathymetry(self, layer_id, values=None):
        """Пункт «Батиметрия по промерам…» точечного слоя: растр глубин
        по промерам в проект, своей батиметрией с уровнем воды. values -
        готовые значения окна для проверочных шагов. Возвращает номер
        растра или None."""
        from ..sentinel import free_path
        from ..sounding import SoundingDialog, build_grid
        layer = QgsProject.instance().mapLayer(layer_id)
        if layer is None:
            return None
        if values is None:
            lat, lon = self._layer_center(layer)
            level = 0.0
            if lat is not None:
                level = float(self.view.store.heights_at(
                    [lat], [lon], scaled=False)[0])
                level = round(level, 1) if math.isfinite(level) else 0.0
            folder = os.path.join(QgsApplication.qgisSettingsDirPath(),
                                  "PlanetX", "bathymetry")
            stem = "".join(c if c.isalnum() or c in "-_" else "_"
                           for c in layer.name()) or "soundings"
            path = os.path.join(folder, stem + ".tif")
            dialog = SoundingDialog(layer, level, path, self)
            if not dialog.exec():
                return None
            values = dialog.values()
        (xs, ys, zs, epsg), cell, limit, level, path = values
        os.makedirs(os.path.dirname(path), exist_ok=True)
        stem, ext = os.path.splitext(os.path.basename(path))
        path = free_path(os.path.dirname(path), stem, ext or ".tif")
        QApplication.setOverrideCursor(enum(Qt, "CursorShape", "WaitCursor"))
        try:
            done = build_grid(xs, ys, zs, epsg, cell, limit, path)
        finally:
            QApplication.restoreOverrideCursor()
        if isinstance(done, str) or not done:
            QMessageBox.warning(self, tr("Батиметрия по промерам"), tr(
                "Растр глубин не построен. Ошибка - {error}.",
                error=done or "0"))
            return None
        raster = QgsRasterLayer(path, tr("{name} - глубины",
                                         name=layer.name()), "gdal")
        if not raster.isValid():
            return None
        project = QgsProject.instance()
        project.addMapLayer(raster, False)
        root = project.layerTreeRoot()
        title = tr("PlanetX - батиметрия")
        group = root.findGroup(title) or root.insertGroup(0, title)
        group.addLayer(raster)
        lakes = read_bathymetry()
        lakes[raster.id()] = ("depth", level)
        write_bathymetry(lakes)
        self.set_insets(read_insets() + [raster.id()])
        self.message = (tr(
            "Растр глубин построен, ячеек {cells} по {cell:g} м.",
            cells=done, cell=cell), time.monotonic())
        self._show_state()
        return raster.id()

    def volume_compare(self, layer_id, values=None):
        """Пункт «Выемка и насыпь…» растра: разность с прежней съёмкой
        в проект и сводка объёмов. values - (прежняя, участок, порог)
        для проверочных шагов, тогда окна сводки нет. Возвращает
        (номер растра разности, сводка) или None."""
        from ..sentinel import free_path
        from ..volumes import (VolumeDialog, compute, style_difference,
                              summary_text)
        project = QgsProject.instance()
        layer = project.mapLayer(layer_id)
        if layer is None:
            return None
        quiet = values is not None
        if values is None:
            dialog = VolumeDialog(layer, self)
            if not dialog.exec():
                return None
            values = dialog.values()
        old_id, area_id, threshold = values
        old = project.mapLayer(old_id)
        area = project.mapLayer(area_id) if area_id else None
        if old is None:
            return None
        folder = os.path.join(QgsApplication.qgisSettingsDirPath(),
                              "PlanetX", "volumes")
        os.makedirs(folder, exist_ok=True)
        stem = "".join(c if c.isalnum() or c in "-_" else "_"
                       for c in "{} - {}".format(layer.name(), old.name()))
        path = free_path(folder, stem or "difference", ".tif")
        QApplication.setOverrideCursor(enum(Qt, "CursorShape", "WaitCursor"))
        try:
            out, error = compute(old, layer, area, threshold, path)
        finally:
            QApplication.restoreOverrideCursor()
        if out is None:
            QMessageBox.warning(self, tr("Выемка и насыпь"), tr(
                "Разность съёмок не посчитана. Ошибка - {error}.",
                error=error))
            return None
        raster = QgsRasterLayer(path, tr("{new} - {old}, разность",
                                         new=layer.name(), old=old.name()),
                                "gdal")
        if not raster.isValid():
            return None
        style_difference(raster, out)
        project.addMapLayer(raster, False)
        root = project.layerTreeRoot()
        title = tr("PlanetX - выемка и насыпь")
        group = root.findGroup(title) or root.insertGroup(0, title)
        group.addLayer(raster)
        self._shown.add(raster.id())
        if self.follow:
            set_visible_on_map(raster.id(), True)
        write_shown(self._shown)
        self._show_layers()
        self.refresh()
        if not quiet:
            QMessageBox.information(self, tr("Выемка и насыпь"),
                                    summary_text(out))
        return raster.id(), out

    def _layer_center(self, layer):
        """Середина охвата слоя в широте и долготе или (None, None)."""
        wgs = QgsCoordinateReferenceSystem("EPSG:4326")
        try:
            transform = QgsCoordinateTransform(layer.crs(), wgs,
                                               QgsProject.instance())
            point = transform.transform(layer.extent().center())
        except QgsCsException:
            return None, None
        return point.y(), point.x()

    def set_inset(self, layer_id, on):
        """Растр проекта layer_id - рельеф глобуса или нет."""
        ids = [i for i in read_insets() if i != layer_id]
        if on:
            ids.append(layer_id)
        self.set_insets(ids)

    def set_grid(self, layer_id, on):
        """Растр проекта layer_id - поверхность по отметкам или нет.
        Подземная модель собирается заново, как после «Обновить»."""
        ids = [i for i in read_grids() if i != layer_id]
        if on:
            ids.append(layer_id)
        write_grids(ids)
        self.panel.grid_ids = set(ids)
        self._apply_vector(force=True)
        self._show_state()

    def set_zlayer(self, layer_id, on):
        """Векторный слой проекта layer_id с Z - объёмом по отметкам
        или плоской картинкой. Подземная модель собирается заново."""
        ids = [i for i in read_zlayers() if i != layer_id]
        if on:
            ids.append(layer_id)
        write_zlayers(ids)
        self.panel.zlayer_ids = set(ids)
        self._apply_vector(force=True)
        self._show_state()

    def set_ztrue(self, layer_id, on):
        """Слой с Z layer_id и без рельефа - на истинных отметках над
        уровнем моря или от поверхности. Модель собирается заново."""
        ids = [i for i in read_ztrue() if i != layer_id]
        if on:
            ids.append(layer_id)
        write_ztrue(ids)
        self.panel.ztrue_ids = set(ids)
        self._apply_vector(force=True)

    def set_insets(self, ids):
        """Растры проекта ids - рельеф глобуса, прочие - нет."""
        write_insets(ids)
        self._load_insets()
        self._refresh_relief()
        self._show_state()

    def _refresh_relief(self):
        """Высоты заново: врезки сменились."""
        self._body_terrain(self.planet)
        self.view.reset_heights()
        self._set_surface()

    # Видимость из точки.

    def _open_viewshed(self, item):
        """Окно «Видимость из точки» для точечной метки item."""
        lat, lon = item.shape.points[0]
        self.viewshed_here(lat, lon, item.name or tr("Без названия"))

    def viewshed_here(self, lat, lon, name=None):
        """Окно «Видимость из точки» для точки lat, lon - пункт меню
        на глобусе."""
        dialog = self.viewshed_dialog
        if dialog is None:
            dialog = ViewshedDialog(self)
            dialog.build.connect(self._build_viewshed)
            dialog.clear.connect(self._clear_viewshed)
            self.viewshed_dialog = dialog
        dialog.point = (lat, lon)
        dialog.place.setText(self._point_title(lat, lon, name))
        dialog.status.setText("")
        dialog.show()
        dialog.raise_()

    def _build_viewshed(self, observer, target, radius_m):
        """Расчёт видимости: сначала тайлы высот под кругом, потом
        расчёт в _viewshed_poll."""
        dialog = self.viewshed_dialog
        if self._surface_source() is None or self.view.sky_view is not None:
            dialog.status.setText(tr("Для этого тела высот нет."))
            return
        lat, lon = dialog.point
        cell = radius_m / viewshed.STEPS
        _, keys = viewshed.height_tiles(lat, lon, radius_m, cell,
                                        ellipsoid.A,
                                        self.view.store.max_level)
        self._stop_roofs(self.viewshed_job)
        self.viewshed_job = {"lat": lat, "lon": lon, "radius": radius_m,
                             "cell": cell, "observer": observer,
                             "target": target, "keys": keys,
                             "started": time.monotonic(),
                             "roofs": self._roofs(dialog, lat, lon,
                                                  radius_m, cell)}
        self.viewshed_timer.start()
        self._viewshed_poll()

    def _viewshed_poll(self):
        job = self.viewshed_job
        if job is None:
            self.viewshed_timer.stop()
            return
        missing = [k for k in job["keys"] if not self._has_height_tile(k)]
        waited = time.monotonic() - job["started"]
        if missing and waited < VIEWSHED_WAIT:
            self.view.want_tool_heights(missing)
            self.viewshed_dialog.status.setText(tr(
                "Загрузка высот: {done} из {total}",
                done=len(job["keys"]) - len(missing),
                total=len(job["keys"])))
            return
        roofs = job["roofs"]
        if self._roofs_wait(roofs, waited, self.viewshed_timer,
                            self.viewshed_dialog):
            return
        self.viewshed_timer.setInterval(VIEWSHED_POLL)
        self.viewshed_timer.stop()
        self.viewshed_job = None
        heights = self._surface_heights if roofs is None \
            else roofs.heights(self._surface_heights)
        result = viewshed.compute(job["lat"], job["lon"], job["radius"],
                                  job["cell"], heights,
                                  observer=job["observer"],
                                  target=job["target"])
        self._show_viewshed(result)
        text = tr("Видно {share} площади круга. Шаг расчёта {step} м.",
                  share="{:.0f}%".format(100.0 * result.share),
                  step="{:.0f}".format(result.step))
        if missing:
            text += " " + tr("Загружены не все высоты, расчёт шёл "
                             "по менее подробным.")
        text += self._roofs_text(roofs)
        self.viewshed_dialog.status.setText(text)

    def _show_viewshed(self, result):
        """Слой видимости по результату result, None убирает слой."""
        old = self.viewshed_tiles
        if old is not None:
            old.abort()
            old.deleteLater()
        self.viewshed_tiles = None
        self.viewshed_result = result
        if result is None:
            self.view.set_gibs("viewshed", False)
            return
        tiles = ResultTiles(result, ellipsoid.A, parent=self)
        tiles.loaded.connect(lambda key, rgba, levels:
                             self.view.add_gibs("viewshed", key, levels))
        self.viewshed_tiles = tiles
        self.view.gibs["viewshed"].max_level = display_level(
            result.step, result.lat, ellipsoid.A)
        self.view.set_gibs("viewshed", True, tiles)

    def _clear_viewshed(self):
        self._stop_roofs(self.viewshed_job)
        self.viewshed_job = None
        self.viewshed_timer.stop()
        self._show_viewshed(None)
        if self.viewshed_dialog is not None:
            self.viewshed_dialog.status.setText("")

    # Здания для видимости и инсоляции (ui/roofs.py).

    def _roofs(self, dialog, lat, lon, reach, cell):
        """Загрузчик крыш круга или None: флажок окна снят, не Земля."""
        if not dialog.buildings.isChecked() or not self.planet.earth \
                or self.view.sky_view is not None:
            return None
        loader = RoofLoader(getattr(self, "_ofm_source", None), lat, lon,
                            reach, cell)
        loader.own = self._burn_own(loader.grid)
        return loader

    def _burn_own(self, grid):
        """Свои здания в растр крыш: выдавленные многоугольники «Моих
        меток», выдавленные слои проекта и 3D-модели на месте. Просьба
        автора от 20 октября 2026 года. Возвращает их количество."""
        before = grid.count
        for shape in self.view.features.shapes:
            if shape.kind != "polygon" or not shape.extrude \
                    or shape.height <= 0.0 or shape.alts is not None:
                continue
            height = float(shape.height)
            if shape.mode == "absolute":
                lats, lons = np.array(shape.points).T
                height -= float(np.min(self._true_heights(lats, lons)))
            rings = [np.array(shape.points)] + [
                np.array(hole) for hole in (shape.holes or ())]
            grid.burn(rings, height)
        for footprint in self.extruder.footprints.values():
            grid.burn_footprint(footprint)
        for parts, overlay in getattr(self, "_roof_models", []):
            lat, lon, alt, heading, tilt, roll = overlay.camera
            if overlay.mode == "absolute":
                lift = alt - float(self._true_heights(
                    np.array([lat]), np.array([lon]))[0])
            elif overlay.mode == "relativeToGround":
                lift = alt
            else:
                lift = 0.0
            for part in parts:
                grid.burn_triangles(*roofs.model_triangles(
                    part.positions, lat, lon, heading, tilt, roll,
                    overlay.scale, lift))
            grid.count -= len(parts) - 1  # модель - одно здание
        return grid.count - before

    def _roofs_wait(self, roofs, waited, timer, dialog):
        """Ждать ли зданий: разбор пришедших тайлов частями, строка
        состояния. Пока здания идут, таймер окна - без паузы."""
        if roofs is None or roofs.ready or waited >= VIEWSHED_WAIT:
            return False
        roofs.step(CALC_BUDGET)
        timer.setInterval(0 if roofs.arrived else VIEWSHED_POLL)
        dialog.status.setText(tr(
            "Загрузка зданий: {done} из {total}", done=roofs.done,
            total=roofs.total))
        return not roofs.ready

    def _roofs_text(self, roofs):
        """Добавка строки итога о зданиях."""
        if roofs is None:
            return ""
        roofs.stop()
        if roofs.skipped:
            text = " " + tr("Здания OpenFreeMap не учтены - круг слишком "
                            "большой.")
        else:
            text = " " + tr("Учтено зданий {count}.",
                            count=roofs.grid.count)
            if roofs.done < roofs.total:
                text += " " + tr("Загружены не все тайлы зданий.")
        if roofs.own:
            text += " " + tr("Своих {count}.", count=roofs.own)
        return text

    def _stop_roofs(self, job):
        if job is not None and job.get("roofs") is not None:
            job["roofs"].stop()

    # Инсоляция.

    def _point_title(self, lat, lon, name):
        """Подпись точки окна видимости и инсоляции."""
        text = "{:.5f}, {:.5f}".format(lat, lon)
        return "{}  {}".format(name, text) if name else text

    def _open_insolation(self, item):
        """Окно «Инсоляция» для точечной метки item."""
        lat, lon = item.shape.points[0]
        self.insolation_here(lat, lon, item.name or tr("Без названия"))

    def insolation_here(self, lat, lon, name=None):
        """Окно «Инсоляция» для точки lat, lon - пункт меню на глобусе."""
        dialog = self.insolation_dialog
        if dialog is None:
            dialog = InsolationDialog(self)
            dialog.build.connect(self._build_insolation)
            dialog.clear.connect(self._clear_insolation)
            self.insolation_dialog = dialog
        dialog.point = (lat, lon)
        dialog.place.setText(self._point_title(lat, lon, name))
        dialog.status.setText("")
        dialog.show()
        dialog.raise_()

    def _build_insolation(self, start, end, radius_m):
        """Расчёт инсоляции: тайлы высот под сеткой, потом высоты узлов
        и расчёт частями по проходам цикла событий (_insolation_poll)."""
        dialog = self.insolation_dialog
        if not self.planet.earth or self.view.sky_view is not None:
            dialog.status.setText(tr("Инсоляция считается только для "
                                     "Земли."))
            return
        lat, lon = dialog.point
        cell, margin, _ = insolation.layout(radius_m)
        _, keys = viewshed.height_tiles(lat, lon, margin * cell + radius_m,
                                        cell, ellipsoid.A,
                                        self.view.store.max_level)
        self._stop_roofs(self.insolation_job)
        self.insolation_job = {"lat": lat, "lon": lon, "radius": radius_m,
                               "start": start, "end": end, "keys": keys,
                               "started": time.monotonic(),
                               "work": None, "missing": False,
                               "roofs": self._roofs(
                                   dialog, lat, lon,
                                   radius_m + ROOF_MARGIN, cell)}
        self.insolation_timer.setInterval(VIEWSHED_POLL)
        self.insolation_timer.start()
        self._insolation_poll()

    def _insolation_poll(self):
        job = self.insolation_job
        dialog = self.insolation_dialog
        if job is None:
            self.insolation_timer.stop()
            return
        work = job["work"]
        if work is None:
            missing = [k for k in job["keys"]
                       if not self._has_height_tile(k)]
            waited = time.monotonic() - job["started"]
            if missing and waited < VIEWSHED_WAIT:
                self.view.want_tool_heights(missing)
                dialog.status.setText(tr(
                    "Загрузка высот: {done} из {total}",
                    done=len(job["keys"]) - len(missing),
                    total=len(job["keys"])))
                return
            if "points" not in job and self._roofs_wait(
                    job["roofs"], waited, self.insolation_timer, dialog):
                return
            # Высоты снимаются в главном потоке, хранилище высот вида
            # меняется только в нём. Узлов 640 тысяч, они снимаются
            # частями по HEIGHT_CHUNK за проход цикла событий, чтобы
            # вид отвечал мыши.
            if "points" not in job:
                job["missing"] = bool(missing)
                lats, lons = insolation.grid_points(job["lat"], job["lon"],
                                                    job["radius"])
                job["points"] = (lats.ravel(), lons.ravel())
                job["heights"] = []
                self.insolation_timer.setInterval(0)
            lats, lons = job["points"]
            done = sum(len(part) for part in job["heights"])
            if done < len(lats):
                end = done + HEIGHT_CHUNK
                heights = self._surface_heights(lats[done:end],
                                                lons[done:end])
                if job["roofs"] is not None:
                    heights = heights + job["roofs"].grid.at(
                        lats[done:end], lons[done:end])
                job["heights"].append(heights)
                dialog.status.setText(tr(
                    "Высоты узлов сетки: {share}",
                    share="{:.0f}%".format(100.0 * done / len(lats))))
                return
            heights = np.concatenate(job["heights"])
            job["work"] = insolation.parts(
                job["lat"], job["lon"], job["radius"], heights,
                job["start"], job["end"], ellipsoid.A)
            return
        # Расчёт идёт частями в главном потоке, не дольше CALC_BUDGET
        # за проход цикла событий. В рабочем потоке он отнимал у вида
        # GIL: при движении камеры 34 кадра из 125 шли дольше 50 мс.
        started = time.perf_counter()
        result = None
        try:
            while time.perf_counter() - started < CALC_BUDGET:
                share = next(work)
        except StopIteration as stop:
            result = stop.value
        if result is None:
            dialog.status.setText(tr("Расчёт инсоляции: {share}",
                                     share="{:.0f}%".format(100.0 * share)))
            return
        self.insolation_timer.stop()
        self.insolation_timer.setInterval(VIEWSHED_POLL)
        self.insolation_job = None
        self._show_insolation(result)
        text = tr("За {days} сут. прямое солнце светит от {low} "
                  "до {high} ч в сутки. Шаг сетки - {step} м.",
                  days=result.days,
                  low="{:.1f}".format(float(result.hours.min())),
                  high="{:.1f}".format(float(result.hours.max())),
                  step="{:.0f}".format(result.cell))
        if job["missing"]:
            text += " " + tr("Загружены не все высоты, расчёт шёл "
                             "по менее подробным.")
        text += self._roofs_text(job["roofs"])
        dialog.status.setText(text)

    def _show_insolation(self, result):
        """Слой инсоляции по результату result, None убирает слой."""
        old = self.insolation_tiles
        if old is not None:
            old.abort()
            old.deleteLater()
        self.insolation_tiles = None
        self.insolation_result = result
        if result is None:
            self.view.set_gibs("insolation", False)
            self.insolation_legend.hide()
            return
        tiles = ResultTiles(result, ellipsoid.A, insolation.tile_rgba,
                            parent=self)
        tiles.loaded.connect(lambda key, rgba, levels:
                             self.view.add_gibs("insolation", key, levels))
        self.insolation_tiles = tiles
        self.view.gibs["insolation"].max_level = display_level(
            result.cell, result.lat, ellipsoid.A)
        self.view.set_gibs("insolation", True, tiles)
        self.insolation_legend.set_top(result.top)
        self.insolation_legend.show()
        self._place_attribution()

    def _clear_insolation(self):
        self._stop_roofs(self.insolation_job)
        self.insolation_job = None
        self.insolation_timer.stop()
        self._show_insolation(None)
        if self.insolation_dialog is not None:
            self.insolation_dialog.status.setText("")

    def _ruler_changed(self):
        self._update_tool_marks()
        dialog = self.profile_dialog
        if dialog is not None and dialog.isVisible() \
                and dialog.source is self.ruler:
            dialog.refresh()

    def _undo_point(self):
        """Backspace над видом: последняя точка линейки."""
        if self._ruler_open():
            self.ruler.remove_last()
        elif self._place_open():
            self.drawer.remove_last()

    def _heights_arrived(self):
        """Пришёл тайл высот: длина по рельефу и профиль уточняются."""
        if self._ruler_open() and len(self.ruler.points) >= 2:
            self.ruler_dialog.show_values()
        dialog = self.profile_dialog
        if dialog is not None and dialog.isVisible():
            dialog.refresh()

    def _update_tool_marks(self):
        """Длины отрезков линейки у их середин и точка профиля под
        курсором графика."""
        marks = []
        ruler = self.ruler
        if self._ruler_open() and ruler.mode in ("line", "path",
                                                 "polygon"):
            points = ruler._points(True)
            closed = ruler.mode == "polygon"
            pairs = list(zip(points, points[1:]))
            if closed and len(points) >= 3:
                pairs.append((points[-1], points[0]))
            unit = self.ruler_dialog.length_unit()
            short = unit_short()[unit]
            middles = segment_midpoints(points, closed)
            for n, ((a, b), (lat, lon)) in enumerate(zip(pairs, middles)):
                length = ruler.da.measureLine(ruler_xy([a, b]))
                text = "{} {}".format(
                    number(convert(length, unit, LENGTH_UNITS)), short)
                marks.append(MarkPlace(-300000 - n, text, "ruler", 1, lat,
                                       lon))
        if self._profile_mark is not None:
            marks.append(self._profile_mark)
        if self._section_mark is not None:
            marks.append(self._section_mark)
        for n, lat, lon in self.wedge_corners.points():
            # Подпись угла - его широта и долгота, видна, пока его тянут.
            marks.append(MarkPlace(-420000 - n, "{:.0f}°, {:.0f}°".format(
                lat, lon), "mark", 1, lat, lon))
        self.view.tool_marks = marks
        self.view.update()

    def _open_profile(self, title, points, source):
        """Окно «Профиль высот» для точек points() с высотами source."""
        if self.profile_dialog is None:
            self.profile_dialog = ProfileDialog(title, points, source, self,
                                                water=self._profile_water)
            self.profile_dialog.point_hovered.connect(self._profile_hover)
            self.profile_dialog.finished.connect(
                lambda *args: self._profile_hover(None))
        else:
            self.profile_dialog.set_points(title, points, source)
        self.profile_dialog.show()
        self.profile_dialog.raise_()

    def _profile_water(self, lats, lons, heights):
        """Уровень своих водоёмов в точках профиля: врезки с батиметрией
        при включённом рельефе на Земле."""
        from ...core.bathymetry import profile_water
        lakes = [(entry.bounds, entry.lake[1])
                 for entry in getattr(self, "insets", ())
                 if getattr(entry, "lake", None) is not None]
        if not lakes or not self.planet.earth:
            return None
        return profile_water(lats, lons, heights, lakes)

    def _open_section(self, title, points):
        """Окно «Разрез» вниз вдоль пути points [(широта, долгота)].
        Кора, зоны плит и сводка землетрясений просятся, если их нет."""
        self._section_points = list(points)
        if self.section_dialog is None:
            self.section_dialog = SectionDialog(title, self._section, self)
            self.section_dialog.point_hovered.connect(self._section_hover)
            self.section_dialog.finished.connect(self._section_closed)
        else:
            self.section_dialog.set_source(title, self._section)
        self.section_dialog.show()
        self.section_dialog.raise_()

    def _section(self, depth, width):
        """Разрез по точкам пути и данным, что уже есть, и пояснение,
        что ещё загружается."""
        found = section.along(self._section_points)
        if found is None:
            return None, ""
        _, lats, lons = found
        self._want_crust()
        if not self.quake_events:
            self._want_quakes()
        codes = slabs.touched(self._read_slab_index(), lats, lons)
        self._request_slabs(codes)
        zones = [self.slab_zones[c] for c in codes if c in self.slab_zones]
        waiting = []
        if self.crust is None and self._crust_reply is not None:
            waiting.append(tr("кора CRUST1.0"))
        if any(c in self._slab_replies for c in codes):
            waiting.append(tr("плиты Slab2"))
        if self._quake_reply is not None:
            waiting.append(tr("землетрясения"))
        notes = tr("Загружаются: {what}.", what=", ".join(waiting)) \
            if waiting else ""
        # Исторические землетрясения ISC-GEM - в разрез, пока включена
        # их строка. Вопрос автора от 18 октября 2026 года.
        history = (self.history_events or []) \
            if self.extras.get("iscgem") else []
        # Очаги - в промежутке шкалы времени, как на глобусе. Просьба
        # автора от 18 октября 2026 года.
        span = getattr(self, "_time_range", None)
        built = section.build(self._section_points, self.crust, zones,
                              section.in_time(self.quake_events or [], span),
                              depth, width,
                              history=section.in_time(history, span))
        # Стенка на глобусе - из того же разреза.
        self.view.section_wall.set_mesh(
            "wall", section.wall_mesh(built) if built is not None else None)
        self.view.update()
        return built, notes

    def _open_model_section(self, title, points):
        """Окно «Разрез модели» вдоль пути points: кровли, скважины,
        тоннели и объекты с Z в метрах. Слои - отметки окна из слоёв
        проекта (ui.subsurface.section_layers), по умолчанию - слои
        подземной модели глобуса. Модель читается заново только при
        смене отметок."""
        from ..subsurface import (section_defaults, section_layers,
                                  section_model)
        points = list(points)
        manager = self.subsurface
        rasters, roles, zlayers = section_layers()
        settings = manager.settings if manager.from_project() else None
        defaults = section_defaults(rasters, roles, zlayers, settings)
        cache = {}

        def provider(band, choice):
            horizons, holes, chosen_z = choice
            if not (horizons or holes or chosen_z or roles.get("tunnels")):
                return None
            key = (horizons, holes, chosen_z)
            if key not in cache:
                cache.clear()
                cache[key] = section_model(horizons, roles, holes, chosen_z)
            return model_section(cache[key], manager._ground, points, band)
        layers = (rasters, "collar" in roles, zlayers, defaults)
        if self.model_section_dialog is None:
            self.model_section_dialog = ModelSectionDialog(title, provider,
                                                           self, layers)
            self.model_section_dialog.point_hovered.connect(
                self._model_section_hover)
            self.model_section_dialog.finished.connect(
                lambda *args: self._model_section_hover(None))
        else:
            self.model_section_dialog.set_source(title, provider, layers)
        self.model_section_dialog.show()
        self.model_section_dialog.raise_()

    def _model_section_hover(self, point):
        """Точка разреза модели под курсором графика - метка на глобусе."""
        if point is None:
            self._section_mark = None
        else:
            lat, lon, distance = point
            self._section_mark = MarkPlace(
                -410000, tr("{value} м", value="{:.0f}".format(distance)),
                "mark", 1, lat, lon)
        self._update_tool_marks()

    def _section_closed(self, *args):
        """Окно «Разрез» закрыто: метка и стенка уходят с глобуса."""
        self._section_hover(None)
        self.view.section_wall.clear()
        self.view.update()

    def _refresh_section(self):
        if self.section_dialog is not None \
                and self.section_dialog.isVisible():
            self.section_dialog.refresh()

    def _section_follow_time(self):
        """Шкала времени сдвинулась: открытый разрез пересобирается после
        паузы SECTION_TIME_PAUSE - сборка с каталогом ISC-GEM стоит
        около 0.25 с, на каждом шаге показа её не повторить."""
        if self.section_dialog is None \
                or not self.section_dialog.isVisible():
            return
        timer = getattr(self, "_section_time_timer", None)
        if timer is None:
            timer = self._section_time_timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._refresh_section)
        timer.start(SECTION_TIME_PAUSE)

    def _section_hover(self, point):
        """Точка разреза под курсором графика - метка на глобусе."""
        if point is None:
            self._section_mark = None
        else:
            lat, lon, distance = point
            self._section_mark = MarkPlace(
                -410000, tr("{value} км", value="{:.0f}".format(distance)),
                "mark", 1, lat, lon)
        self._update_tool_marks()

    def _ruler_profile(self):
        self._open_profile(tr("Линейка"), lambda: self.ruler._points(False),
                           self.ruler)

    def _profile_hover(self, point):
        """Точка профиля под курсором графика - метка на глобусе."""
        if point is None:
            self._profile_mark = None
        else:
            lat, lon, height = point
            self._profile_mark = MarkPlace(
                -400000, tr("{value} м", value="{:.0f}".format(height)),
                "mark", 1, lat, lon)
        self._update_tool_marks()

    def _ruler_open(self):
        return self.ruler_dialog is not None and self.ruler_dialog.isVisible()

    def _open_ruler(self):
        if self._place_open():
            self.place_dialog.close()
        if self.ruler_dialog is None:
            self.ruler_dialog = RulerDialog(self.ruler, self)
            self.ruler_dialog.save_requested.connect(self._save_ruler)
            self.ruler_dialog.profile_requested.connect(
                self._ruler_profile)
            self.ruler_dialog.finished.connect(self._ruler_closed)
        self.ruler_dialog.show()
        self.ruler_dialog.raise_()
        self.view.vertex_tool = self.ruler_vertices
        self._refresh_shapes()
        self._tool_cursor()

    def _ruler_closed(self, *args):
        self.view.vertex_tool = self.wedge_corners \
            if self.view.wedge is not None else None
        self.ruler.clear()
        self._refresh_shapes()
        self._tool_cursor()

    def _save_ruler(self):
        """«Сохранить»: фигура линейки в «Мои метки» с измерением."""
        titles = {"line": tr("Линия"), "path": tr("Путь"),
                  "polygon": tr("Многоугольник"), "circle": tr("Круг"),
                  "path3d": tr("3D-путь"),
                  "polygon3d": tr("3D-многоугольник")}
        name, ok = QInputDialog.getText(
            self, tr("Сохранить измерение"), tr("Название"),
            text=self.new_name(titles[self.ruler.mode]))
        if not ok:
            return
        shape = self.ruler.shape(rubber=False, name=name.strip())
        if shape is None:
            return
        self.myplaces.add(shape, measure=self.ruler_dialog.summary(),
                          folder=self.panel.current_folder())
        self.ruler.clear()

    def _places_toggled(self, states):
        """Флажки «Моих меток» из панели. Флажок папки без раскрытия
        переходит на всё её содержимое, в папке-переключателе остаётся
        одна видимая строка (core/placetree.radio_states)."""
        states = dict(states)
        nodes = self.myplaces.nodes()
        for folder in self.myplaces.folders:
            if not folder.expandable and folder.key in states:
                for key in placetree.descendants(nodes, folder.key):
                    states[key] = states[folder.key]
        radio = {f.key for f in self.myplaces.folders if f.radio}
        shown = {item.key for item in self.myplaces.places
                 + self.myplaces.overlays + self.myplaces.folders
                 if item.visible}
        self.myplaces.set_visible_many(
            placetree.radio_states(nodes, radio, states, shown))

    def _place_action(self, action, key):
        """Действие меню «Моих меток»: тур, папка, перелёт, имя,
        удаление, слои в проект. key "" - корень «Мои метки»."""
        if action == "project":
            self.myplaces.add_to_project()
            return
        if action == "clear":
            self.clear_places()
            return
        if action in ("draw_point", "draw_line", "draw_polygon"):
            # «Добавить» в меню папки: окно «Новая метка» на нужной
            # вкладке, новая метка ложится в эту папку.
            if key:
                self.panel.select_place(key)
            self._open_place()
            self.place_dialog.tabs.setCurrentIndex(
                ("draw_point", "draw_line", "draw_polygon").index(action))
            return
        if action == "record_tour":
            if key:
                self.panel.select_place(key)
            self.toolbar.record.setChecked(True)
            return
        if action in ("add_ground", "add_photo", "add_screen"):
            self.add_overlay(action[4:], key or None)
            return
        if action == "add_model":
            self.add_model(key or None)
            return
        if action == "add_link":
            self.add_link(key or None)
            return
        if action == "reload_link":
            self.netlinks.reload(key)
            return
        if action == "ground_project":
            self.ground_to_project(key or None)
            return
        if action == "sort":
            self.myplaces.sort_folder(key or None)
            return
        if action == "cut":
            # «Вырезать» Google Earth: копия в буфер обмена, строка
            # уходит из списка, «Вставить» кладёт её на новое место.
            self.copy_places([key])
            self.myplaces.remove(key)
            return
        if action in ("new_folder", "new_folder_after"):
            # Папка сразу с названием, без окна, переименовывается потом.
            # На метке - сразу под ней, на папке - внутрь, как у GE.
            if action == "new_folder":
                parent, after = key or None, None
            else:
                place = self.myplaces.find(key)
                parent, after = (place.folder if place else None), key
            new = self.myplaces.add_folder(tr("Новая папка"), parent,
                                           after=after)
            if new is not None:
                self.panel.select_place(new)
            return
        if action == "import_kml":
            self.import_kml(key or None)
            return
        if action == "copy":
            self.copy_places([key] if key else [])
            return
        if action == "paste":
            place = self.myplaces.find(key) if key else None
            folder = key if is_folder(key) else (
                place.folder if place is not None else None)
            self.paste_places(folder)
            return
        if action == "export_kml":
            self.export_kml(key or None)
            return
        if action == "tour" and (not key or is_folder(key)):
            self.tour.start(self._tour_stops(key or None))
            return
        item = self.myplaces.find(key)
        if item is None:
            return
        if is_folder(key):
            self._folder_action(action, item)
            return
        if isinstance(item, OverlayItem):
            if action == "properties":
                self._open_overlay_properties(item)
                return
            if action == "fly" and item.kind == "screen":
                return
        if action == "fly":
            self.fly_to_place(item)
        elif action == "tour":
            stop = self.place_stop(item, along=True)
            stop.time = item.view_time or item.time
            stop.description = item.description or ""
            stop.layers = getattr(item, "layers", None)
            pace = getattr(item, "pace", None)
            if pace:
                stop.pause, stop.speed = pace
            self.tour.start([stop])
        elif action == "properties":
            self._open_place_properties(item)
        elif action == "sentinel":
            self.sentinel_place(item)
        elif action == "profile":
            points = list(item.shape.points)
            self._open_profile(item.name, lambda: points, HeightSource(
                self._true_heights, self._has_height_tile,
                self.view.want_tool_heights))
        elif action == "section":
            self._open_section(item.name, list(item.shape.points))
        elif action == "model_section":
            self._open_model_section(item.name, list(item.shape.points))
        elif action in ("model_wall", "model_cut"):
            # Метка режет подземную модель или ставит стенку разреза,
            # повторный выбор убирает. Решение автора от 4 октября 2026
            # года - вырез и разрез рисуются на глобусе.
            on = self.subsurface.toggle_place(
                key, "cut" if action == "model_cut" else "section")
            names = {("model_cut", True): tr("Вырез модели по «{name}»."),
                     ("model_cut", False): tr("Вырез модели по «{name}» "
                                              "убран."),
                     ("model_wall", True): tr("Стенка разреза по «{name}»."),
                     ("model_wall", False): tr("Стенка разреза по «{name}» "
                                               "убрана.")}
            self.message = (names[(action, on)].format(
                name=item.name or tr("Без названия")), time.monotonic())
            self._show_state()
        elif action == "viewshed":
            self._open_viewshed(item)
        elif action == "insolation":
            self._open_insolation(item)
        elif action == "snapshot":
            # «Снимок вида» Google Earth: вид глобуса сейчас становится
            # видом метки, по нему идут перелёт к метке и тур.
            self.myplaces.update(key, {"view": lookat.text(
                self.current_view())})
        elif action == "remove":
            name = item.name or tr("Без названия")
            if is_folder(key):
                title = tr("Удалить папку")
                question = tr("Удалить папку «{name}» со всем "
                              "содержимым?", name=name)
            else:
                title = tr("Удалить метку")
                question = tr("Удалить «{name}» из «Моих меток»?",
                              name=name)
            answer = QMessageBox.question(self, title, question)
            if answer == enum(QMessageBox, "StandardButton", "Yes"):
                self.myplaces.remove(key)

    def clear_places(self, confirm=True):
        """«Очистить «Мои метки»» - удалить все метки и папки после
        подтверждения. Просьба автора от 4 октября 2026 года."""
        top = [n.key for n in self.myplaces.folders if n.parent is None] \
            + [p.key for p in self.myplaces.places + self.myplaces.overlays
               if p.folder is None]
        if not top:
            return False
        if confirm:
            answer = QMessageBox.question(
                self, tr("Очистить «Мои метки»"), tr(
                    "Удалить все метки и папки «Моих меток», всего меток "
                    "{count}? Отменить удаление нельзя.",
                    count=len(self.myplaces.places)))
            if answer != enum(QMessageBox, "StandardButton", "Yes"):
                return False
        self.myplaces.remove_many(top)
        self.made_folder = None
        return True

    def add_link(self, parent=None):
        """«Добавить - Сетевую ссылку…»: папка-ссылка в папке parent,
        содержимое приходит загрузкой."""
        dialog = LinkDialog(tr("Сетевая ссылка"), "", 0.0, self)
        if not dialog.exec():
            return None
        name, link, refresh = dialog.values()
        if not link:
            return None
        key = self.myplaces.add_folder(name or link, parent)
        if key is not None:
            self.myplaces.set_link(key, link, refresh)
            self.panel.select_place(key)
            self.netlinks.tick()
        return key

    def _folder_action(self, action, folder):
        """Перелёт к виду папки, снимок вида, свойства, имя, удаление."""
        key = folder.key
        if action == "fly":
            self.fly_to_folder(folder)
        elif action == "snapshot":
            self.myplaces.update(key, {"view": lookat.text(
                self.current_view())})
        elif action == "properties" and folder.link:
            dialog = LinkDialog(folder.name, folder.link, folder.refresh,
                                self)
            if dialog.exec():
                name, link, refresh = dialog.values()
                self.myplaces.update(key, {"name": name or folder.name})
                self.myplaces.set_link(key, link, refresh)
                self.netlinks.reload(key)
        elif action == "properties":
            dialog = FolderDialog(
                folder, self.current_view, self,
                [point for p in self.myplaces.places_in(key)
                 for point in p.shape.points])
            dialog.setAttribute(enum(Qt, "WidgetAttribute",
                                     "WA_DeleteOnClose"))

            def done(result, key=key, dialog=dialog):
                if result:
                    self.myplaces.update(key, dialog.values())
            dialog.finished.connect(done)
            self.side.host(dialog)
        elif action == "remove":
            answer = QMessageBox.question(
                self, tr("Удалить папку"), tr(
                    "Удалить папку «{name}» со всем содержимым?",
                    name=folder.name or tr("Без названия")))
            if answer == enum(QMessageBox, "StandardButton", "Yes"):
                self.myplaces.remove(key)

    def _places_action(self, action, keys):
        """Действие над несколькими выбранными строками «Моих меток»:
        показать, скрыть, удалить."""
        keys = [k for k in keys if self.myplaces.find(k) is not None]
        if not keys:
            return
        if action == "copy":
            self.copy_places(keys)
            return
        if action in ("show", "hide"):
            self.myplaces.set_visible_many(
                {k: action == "show"
                 for k in self.myplaces.with_contents(keys)})
        elif action == "remove":
            if len(keys) == 1:
                self._place_action("remove", keys[0])
                return
            answer = QMessageBox.question(
                self, tr("Удалить выбранное"), tr(
                    "Удалить выбранное из «Моих меток»? Строк {count}, "
                    "папки удаляются со всем содержимым.",
                    count=len(keys)))
            if answer == enum(QMessageBox, "StandardButton", "Yes"):
                self.myplaces.remove_many(keys)
