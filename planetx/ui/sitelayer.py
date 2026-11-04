# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Общий слой вида окон анализа участка.

Слой вида «viewshed» делят видимость из точки, классификация, похожие
области, минералы по спектру, минералы EMIT и земляные работы. У слоя
один хозяин: инструмент, который показывает результат, занимает слой
(SiteLayer.claim), прежний хозяин снимает свой результат сам (drop).
Так новый инструмент не правит прежние. Решение автора от 2 ноября
2026 года - «стандартизируй инструменты анализа по максимуму».

SiteTool - общая основа показа результата инструмента на этом слое:
картинки тайлов, глубина, непрозрачность, снятие и очистка.
"""
import math

import numpy as np

try:  # внутри плагина QGIS
    from ..i18n import tr
except ImportError:  # тесты без пакета
    def tr(text, **values):
        return text.format(**values)

LAYER = "viewshed"  # слой вида, общий у окон анализа участка
LEGEND_ROWS = 12  # строк шкалы классов, остальные - одной строкой


def class_rows(classes, colors, names):
    """Классы с клетками по убыванию доли: [(цвет, «имя N %»)]."""
    classes = np.asarray(classes)
    counts = np.bincount(classes[classes >= 0].ravel().astype(np.int64),
                         minlength=len(names))[:len(names)]
    total = max(int(counts.sum()), 1)
    return [(colors[n], "{} {:.0f} %".format(names[n],
                                             100.0 * counts[n] / total))
            for n in np.argsort(-counts, kind="stable") if counts[n]]


def add_preview(dialog, layout, buttons):
    """Флажок «Показывать на глобусе» слева от кнопок окна инструмента:
    dialog.preview. layout - раскладка окна, buttons - QDialogButtonBox
    в ней."""
    from qgis.PyQt.QtWidgets import QCheckBox, QHBoxLayout
    box = QCheckBox(tr("Показывать на глобусе"), dialog)
    box.setChecked(True)
    box.setToolTip(tr(
        "Снятый флажок прячет результат на глобусе, под ним виден снимок, "
        "по которому удобно ставить образцы. Результат и кнопка OK "
        "остаются."))
    index = layout.indexOf(buttons)
    layout.removeWidget(buttons)
    row = QHBoxLayout()
    row.addWidget(box)
    row.addWidget(buttons, 1)
    layout.insertLayout(index, row)
    dialog.preview = box
    return box


def result_level(result):
    """Глубина тайлов слоя вида по шагу сетки результата."""
    lat = (result["box"][1] + result["box"][3]) / 2.0
    pixel = 2 * math.pi * 6378137.0 * math.cos(math.radians(lat)) / 256
    return max(1, min(18, int(math.ceil(math.log2(pixel
                                                  / result["step"])))))


class SiteLayer:
    """Хозяин общего слоя вида у окна глобуса."""

    def __init__(self):
        self.owner = None

    def claim(self, owner):
        """owner показывает свой результат: прежний хозяин снимает свой,
        слой вида при этом не выключается."""
        old, self.owner = self.owner, owner
        if old is not None and old is not owner:
            old.drop()

    def release(self, owner):
        if self.owner is owner:
            self.owner = None


class SiteTool:
    """Основа показа результата инструмента на общем слое вида.
    Наследник держит window и tiles, задаёт forget - что снимается
    вместе с картинками (результат, кнопка OK)."""

    window = None
    tiles = None
    shown_opacity = 1.0  # непрозрачность показанного предпросмотра

    def put_tiles(self, tiles, level, opacity=None, keep=False):
        """Картинки тайлов tiles на общем слое: занять слой, глубина
        level, непрозрачность opacity (None - как есть). keep - новые
        картинки ложатся поверх прежних без мигания."""
        window = self.window
        view = window.view
        window.site_layer.claim(self)
        old = self.tiles
        self.tiles = None
        if old is not None:
            old.abort()
            old.deleteLater()
        tiles.loaded.connect(lambda key, rgba, levels:
                             view.add_gibs(LAYER, key, levels))
        self.tiles = tiles
        layer = view.gibs[LAYER]
        layer.max_level = level
        layer.empty.clear()
        view.set_gibs(LAYER, True, tiles, keep=keep)
        self.shown_opacity = 1.0 if opacity is None else opacity
        box = self._preview_box()
        layer.fade = 1.0 - self.shown_opacity \
            if box is None or box.isChecked() else 1.0
        self._show_legend()
        view.update()

    def _preview_box(self):
        """Флажок «Показывать на глобусе» окна инструмента (add_preview),
        связь с ним заводится при первом показе."""
        box = getattr(getattr(self, "dialog", None), "preview", None)
        if box is not None and not getattr(box, "planetx_linked", False):
            box.toggled.connect(self.set_preview)
            box.planetx_linked = True
        return box

    def set_preview(self, on):
        """Предпросмотр виден или спрятан: под ним виден снимок, результат
        и кнопка OK остаются. Просьба Василия Швалёва от 4 ноября 2026
        года - образцы ставятся по снимку."""
        if self.tiles is None:
            return
        self.window.view.gibs[LAYER].fade = \
            1.0 - self.shown_opacity if on else 1.0
        self.window.view.update()

    def legend_rows(self):
        """Строки шкалы классов [(цвет, подпись)] по результату
        с полями classes, colors и names - по убыванию доли участка.
        Наследник без классов отвечает пустым списком."""
        result = getattr(self, "result", None)
        if not result or "names" not in result \
                or "classes" not in result:
            return []
        return class_rows(result["classes"], result["colors"],
                          result["names"])

    def _show_legend(self):
        legend = getattr(self.window, "site_legend", None)
        if legend is None:
            return
        rows = self.legend_rows()
        if not rows:
            legend.hide()
            return
        shown, more = rows[:LEGEND_ROWS], len(rows) - LEGEND_ROWS
        legend.set_rows(getattr(self, "legend_title", ""), shown,
                        tr("Ещё классов: {n}", n=more) if more > 0 else "")
        legend.show()

    def _hide_legend(self):
        legend = getattr(self.window, "site_legend", None)
        # Шкала своя, пока свои картинки на слое: снятый раньше
        # инструмент не прячет шкалу нового хозяина.
        if legend is not None and self.tiles is not None:
            legend.hide()

    def set_opacity(self, value):
        """Непрозрачность результата - доля прозрачности слоя вида, без
        пересборки картинок тайлов."""
        self.shown_opacity = value
        if self.tiles is None:
            return
        box = self._preview_box()
        if box is None or box.isChecked():
            self.window.view.gibs[LAYER].fade = 1.0 - value
            self.window.view.update()

    def _drop_tiles(self):
        self._hide_legend()
        if self.tiles is not None:
            # Прозрачность слоя у видимости своя.
            self.window.view.gibs[LAYER].fade = 0.0
            self.tiles.abort()
            self.tiles.deleteLater()
            self.tiles = None

    def forget(self):
        """Что снимается вместе с картинками, у наследника."""

    def drop(self):
        """Слой вида занимает другой инструмент: результат снимается без
        выключения слоя."""
        self._drop_tiles()
        self.forget()

    def clear(self):
        """Результат снимается, свой слой выключается."""
        shown = self.tiles is not None
        self.drop()
        self.window.site_layer.release(self)
        if shown:
            self.window.view.set_gibs(LAYER, False)


class ViewshedOwner:
    """Видимость из точки как хозяин общего слоя: её картинки держит
    окно глобуса (globe/tools.py)."""

    def __init__(self, window):
        self.window = window

    def drop(self):
        self.window._drop_viewshed()
