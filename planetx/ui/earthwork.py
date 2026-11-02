# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «Земляные работы»: выемка и насыпь до ровной площадки.

Участок - многоугольник (ui/area.py), высоты - GridHeights из ui/hydro.py,
с моделью 30 м и своим рельефом. Площадка - отметка окна, кнопка «Равные
объёмы» ставит отметку, при которой выемка равна насыпи. Смена отметки
считается без загрузки высот. Показ на глобусе - слой вида «viewshed»,
один на видимость, классификацию, похожие области и это окно. Расчёт -
core/volumes.py. На открытых высотах итог идёт с оценкой ошибки, на своём
рельефе растром проекта - без неё. OK пишет разность GeoTIFF в подгруппу
расчёта (ui/results.py).
"""
from qgis.PyQt.QtCore import QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import (QDialog, QDialogButtonBox, QFormLayout,
                                 QLabel, QPushButton, QVBoxLayout)

from ..core import ellipsoid, volumes
from ..i18n import tr
from ..qt_compat import enum
from .area import Area
from .export import add_raster
from .hydro import GridHeights, _spin, number
from .inset import DemSource
from .relief import write_grid
from .results import (Session, accepted, built_text, keep_buttons,
                      result_path, show_layer)
from .viewshed import ResultTiles, display_level, fit_status

LAYER = "viewshed"  # слой вида, общий с видимостью и классификацией
SIDE = 1.0  # км, сторона участка по умолчанию
MOST = 20.0  # км, наибольший участок
PAUSE = 150  # мс, пауза смены отметки перед новой раскраской


def volume_text(value):
    """Объём с пробелами между разрядами."""
    return "{:,.0f}".format(value).replace(",", " ")


def summary_text(out):
    """Сводка объёмов окна."""
    return tr(
        "Выемка {cut} м³ на {cut_area} га, насыпь {fill} м³ на {fill_area} "
        "га. Разность насыпи и выемки {net} м³.",
        cut=volume_text(out["cut"]), cut_area=number(out["cut_area"] / 1e4),
        fill=volume_text(out["fill"]),
        fill_area=number(out["fill_area"] / 1e4),
        net=volume_text(out["net"]))


def warning_text(work, share):
    """Оговорка об открытых высотах, пустая строка на своём рельефе."""
    if share >= volumes.OWN_ENOUGH:
        return ""
    error = volume_text(volumes.open_error(work, share))
    if share <= 0.0:
        return tr(
            "Высоты участка - открытые модели с ошибкой в метры. Ошибка "
            "±{metres} м меняет объём на ±{error} м³, итог - только оценка. "
            "Для расчёта нужен свой рельеф, пункт «Рельеф глобуса» меню "
            "растра.", metres="{:g}".format(volumes.OPEN_ERROR), error=error)
    return tr(
        "Свой рельеф покрывает {share} % участка, остальное - открытые "
        "модели. Ошибка ±{metres} м меняет объём на ±{error} м³, итог - "
        "только оценка.", share="{:.0f}".format(100.0 * share),
        metres="{:g}".format(volumes.OPEN_ERROR), error=error)


class EarthworkDialog(QDialog):
    """Окно «Земляные работы». Сигналы build, level_changed, balance. OK
    записывает разность в проект QGIS, «Отмена» убирает её."""

    build = pyqtSignal()
    level_changed = pyqtSignal()
    balance = pyqtSignal()

    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle(tr("Земляные работы"))
        self.point = None
        self.place = QLabel(self)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.area = Area(window, self, SIDE, MOST,
                         "PlanetX/earthwork/side")
        self.level = _spin(self, -500.0, 9000.0, 0.0, tr(" м"), decimals=2)
        self.level.setToolTip(tr(
            "Отметка ровной площадки над уровнем моря. Всё выше неё - "
            "выемка, ниже - насыпь. Смена отметки считается сразу, без "
            "загрузки высот."))
        self.level.valueChanged.connect(lambda _: self.level_changed.emit())
        form = QFormLayout()
        form.addRow(tr("Точка"), self.place)
        form.addRow(tr("Участок"), self.area.widget)
        form.addRow(tr("Отметка площадки"), self.level)
        buttons = QDialogButtonBox(self)
        run = QPushButton(tr("Построить"), self)
        run.setDefault(True)
        run.setToolTip(tr(
            "Высоты участка, выемка и насыпь до отметки площадки - "
            "раскраска на глобусе и объёмы. Первый расчёт ставит отметку "
            "равных объёмов."))
        run.clicked.connect(self.build)
        self.equal = QPushButton(tr("Равные объёмы"), self)
        self.equal.setToolTip(tr(
            "Отметка, при которой вынутого грунта хватает на насыпь."))
        self.equal.clicked.connect(self.balance)
        for button in (run, self.equal):
            buttons.addButton(button, enum(QDialogButtonBox, "ButtonRole",
                                           "ActionRole"))
        self.to_project = keep_buttons(self, buttons)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.status)
        layout.addWidget(buttons)
        fit_status(self, layout)
        self.set_ready(False)

    def set_ready(self, ready):
        for button in (self.to_project, self.equal):
            button.setEnabled(ready)

    def set_level(self, value):
        """Отметка без сигнала смены."""
        self.level.blockSignals(True)
        self.level.setValue(value)
        self.level.blockSignals(False)


class EarthworkTool(GridHeights):
    """Выемка и насыпь участка до площадки."""

    def __init__(self, window):
        super().__init__(window)
        self.dialog = None
        self.session = Session(window, tr("Земляные работы"))
        self.state = None  # сетка, высоты, площадка, сводка, неполнота
        self.tiles = None
        self.pause = QTimer(self)
        self.pause.setSingleShot(True)
        self.pause.setInterval(PAUSE)
        self.pause.timeout.connect(self._apply)

    def open_here(self, lat, lon):
        """Окно для точки - пункт подменю «Анализ участка»."""
        dialog = self.dialog
        if dialog is None:
            dialog = EarthworkDialog(self.window)
            dialog.build.connect(lambda: self._start(
                self.dialog, self._built))
            dialog.level_changed.connect(self._level_moved)
            dialog.balance.connect(self.set_balance)
            dialog.finished.connect(self._done)
            self.dialog = dialog
        dialog.point = (lat, lon)
        dialog.place.setText(self.window._point_title(lat, lon, None))
        dialog.status.setText("")
        dialog.show()
        dialog.raise_()
        dialog.area.open_at(lat, lon)
        return dialog

    # --- расчёт ------------------------------------------------------------

    def _built(self, dialog, grid, z, partial):
        level = volumes.balance_level(z)
        if level is None:
            dialog.status.setText(tr("На участке нет высот."))
            return None
        self.state = {"grid": grid, "z": z, "partial": partial,
                      "work": None, "out": None}
        dialog.set_level(round(level, 2))
        dialog.set_ready(True)
        return self._apply()

    def _level_moved(self):
        if self.state is not None:
            self.pause.start()

    def set_balance(self):
        """Отметка равных объёмов."""
        state = self.state
        if state is None:
            return
        self.dialog.set_level(round(volumes.balance_level(state["z"]), 2))
        self._apply()

    def own_boxes(self):
        """Рамки своего рельефа - врезок растрами проекта."""
        return [entry.bounds for entry in self.window.insets
                if not isinstance(entry, DemSource)]

    def _apply(self):
        """Выемка и насыпь при нынешней отметке, без загрузки высот."""
        state = self.state
        dialog = self.dialog
        if state is None or dialog is None:
            return None
        keep = state["work"] is not None and self.tiles is not None
        work = volumes.earthwork(state["z"], state["grid"],
                                 dialog.level.value(), ellipsoid.A)
        out = volumes.summary(work.diff, float(state["grid"].cell) ** 2)
        state["work"] = work
        state["out"] = out
        state["share"] = volumes.own_share(work, self.own_boxes(),
                                           ellipsoid.A)
        parts = [summary_text(out),
                 tr("Шаг сетки {step} м.", step=number(state["grid"].cell)),
                 warning_text(work, state["share"])]
        if state["partial"]:
            parts.append(tr("Загружены не все высоты, расчёт шёл "
                            "по менее подробным."))
        parts.append(built_text())
        dialog.status.setText(" ".join(p for p in parts if p))
        self._show(work, keep)
        return work

    # --- показ на глобусе --------------------------------------------------

    def _show(self, work, keep):
        window = self.window
        old = self.tiles
        self.tiles = None
        if old is not None:
            old.abort()
            old.deleteLater()
        if not keep:
            window.class_tool.clear()
            window.similar_tool.clear()
            window.spectral_tool.clear()
            window.emit_tool.clear()
            window._show_viewshed(None)
        tiles = ResultTiles(work, ellipsoid.A, volumes.tile_rgba,
                            parent=self)
        tiles.loaded.connect(lambda key, rgba, levels:
                             window.view.add_gibs(LAYER, key, levels))
        self.tiles = tiles
        layer = window.view.gibs[LAYER]
        layer.max_level = display_level(work.grid.cell, work.lat,
                                        ellipsoid.A)
        layer.empty.clear()
        window.view.set_gibs(LAYER, True, tiles, keep=keep)
        window.view.update()

    def _drop_tiles(self):
        if self.tiles is not None:
            self.tiles.abort()
            self.tiles.deleteLater()
            self.tiles = None

    def drop(self):
        """Слой вида занимает другой инструмент."""
        self.pause.stop()
        self._drop_tiles()
        self.state = None
        if self.dialog is not None:
            self.dialog.set_ready(False)

    def clear(self):
        shown = self.tiles is not None
        self.drop()
        if shown:
            self.window.view.set_gibs(LAYER, False)

    # --- выгрузка ----------------------------------------------------------

    def _done(self, code):
        """Окно закрыто: OK - разность в проект QGIS, иначе участок
        просто убирается."""
        self.job = None
        self.timer.stop()
        self.window.spinner.set_job(self.busy_key())
        if accepted(code):
            self.export()
        self.clear()
        self.session.reset()
        self.dialog.area.end()

    def export(self, path=None):
        """Растр «площадка минус рельеф» в подгруппу расчёта: плюс -
        насыпь, минус - выемка. Сводка - в описании слоя."""
        state = self.state
        if state is None or state["work"] is None:
            return None
        self.pause.stop()
        self._apply()
        path = path or result_path("earthwork")
        work = state["work"]
        if not write_grid(path, work.grid, work.diff):
            self.dialog.status.setText(tr("Растры не записаны в «{path}».",
                                          path=path))
            return None
        reach = work.reach
        stops = [(-reach, volumes.CUT_RGB), (0.0, (255, 255, 255, 0)),
                 (reach, volumes.FILL_RGB)]
        note = " ".join(p for p in (
            summary_text(state["out"]),
            warning_text(work, state["share"])) if p)
        layer = add_raster(
            path, tr("Выемка и насыпь до отметки {level} м",
                     level="{:.2f}".format(work.level)), stops,
            group=self.session.group_for(self.dialog.area.ring),
            abstract=note)
        show_layer(self.window, layer)
        return path

    def close(self):
        self.pause.stop()
        self.timer.stop()
        self._drop_tiles()
        if self.dialog is not None:
            self.dialog.close()

