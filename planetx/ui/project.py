# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Слои текущего проекта для глобуса и слежение за их изменениями.

В списке глобуса все слои проекта в порядке отрисовки дерева слоёв,
с учётом своего порядка слоёв, если он задан. Какие из них видны
на глобусе, решают отметки списка, они хранятся в проекте. Изменением
считаются порядок, добавление и удаление слоя и перерисовка слоя QGIS.
Перерисовку слой просит при правке данных и стиля.
"""
import json
import string
from functools import partial

from qgis.core import QgsProject
from qgis.PyQt.QtCore import QObject, QTimer, pyqtSignal

ENTRY = "PlanetX"  # запись проекта с настройками глобуса
AUTO_REFRESH = "auto_refresh"  # обновлять глобус без кнопки
SHOWN = "layers"  # номера слоёв, отмеченных в списке глобуса
FOLLOW = "follow_legend"  # видимость на глобусе как в легенде QGIS
INSETS = "insets"  # растры проекта - рельеф глобуса
# Растры проекта - поверхности по абсолютным отметкам под землёй,
# пункт «Поверхность по отметкам» меню слоя.
GRIDS = "grids"
# Векторные слои с Z объёмом по отметкам - пункт «Объёмом по отметкам Z».
ZLAYERS = "zlayers"
# Из них - слои с истинными отметками Z и без рельефа, пункт
# «Истинные отметки Z».
ZTRUE = "zlayers_true"
# Векторные слои, выдавленные по полю, - строка JSON.
EXTRUDE = "extrude"
# Батиметрия врезок своего рельефа - строка JSON, core/bathymetry.py.
BATHYMETRY = "bathymetry"
# Годы исторических карт - растров и тайлов проекта, строка JSON
# {номер слоя: год}, core/oldmaps.py.
MAP_YEARS = "map_years"
# Стороны шторки слоёв проекта - строка JSON {номер слоя: left или
# right}, core/sides.py, и флажок, включена ли шторка.
SWIPE_SIDES = "swipe_sides"
SIDE_SWIPE = "side_swipe"
SECTION_COLORS = "section_colors"  # свои цвета окна «Разрез модели»
# Облака точек: {номер слоя: {"mode", "size", "classes"}}.
POINTCLOUDS = "pointclouds"


def map_layers(project=None):
    """Все годные слои проекта сверху вниз, как их рисует карта."""
    project = project or QgsProject.instance()
    return [layer for layer in project.layerTreeRoot().layerOrder()
            if layer.isValid()]


def visible_on_map(layer, project=None):
    """Включён ли слой в дереве слоёв QGIS."""
    project = project or QgsProject.instance()
    node = project.layerTreeRoot().findLayer(layer.id())
    return node is not None and node.isVisible()


# Слой, выгруженный «В проект QGIS…» из слоя глобуса, - копия того, что
# глобус уже рисует сам. Сам на глобус он не встаёт, ни в режиме
# «как на карте QGIS», ни новым слоем, иначе одни данные шли бы дважды.
# Флажок в разделе «Проект QGIS» его показывает. Замечание автора
# от 27 октября 2026 года.
COPY_PROPERTY = "planetx/globe_copy"


def is_copy(layer):
    """Слой - выгрузка слоя глобуса в проект."""
    return bool(layer.customProperty(COPY_PROPERTY, False))


def legend_shown(layers, project=None):
    """Номера слоёв, включённых в дереве слоёв QGIS, без выгрузок слоёв
    глобуса - видимость глобуса в режиме «как на карте QGIS»."""
    return {layer.id() for layer in layers
            if visible_on_map(layer, project) and not is_copy(layer)}


def set_visible_on_map(layer_id, on, project=None):
    """Включить или выключить слой в дереве слоёв QGIS."""
    project = project or QgsProject.instance()
    node = project.layerTreeRoot().findLayer(layer_id)
    if node is not None:
        node.setItemVisibilityChecked(bool(on))


def read_flag(name, default, project=None):
    project = project or QgsProject.instance()
    value, ok = project.readBoolEntry(ENTRY, name, default)
    return bool(value) if ok else default


def write_flag(name, value, project=None):
    project = project or QgsProject.instance()
    project.writeEntryBool(ENTRY, name, bool(value))


def read_shown(project=None):
    """Отмеченные слои из проекта или None, если записи ещё нет."""
    project = project or QgsProject.instance()
    value, ok = project.readListEntry(ENTRY, SHOWN, [])
    return set(value) if ok else None


def write_shown(ids, project=None):
    project = project or QgsProject.instance()
    project.writeEntry(ENTRY, SHOWN, sorted(ids))


def read_insets(project=None):
    """Номера растров проекта - врезок своего рельефа."""
    project = project or QgsProject.instance()
    value, ok = project.readListEntry(ENTRY, INSETS, [])
    return list(value) if ok else []


def write_insets(ids, project=None):
    project = project or QgsProject.instance()
    project.writeEntry(ENTRY, INSETS, list(ids))


def read_bathymetry(project=None):
    """Батиметрия растров-врезок: {номер слоя: (вид, уровень воды)}."""
    from ..core.bathymetry import parse
    project = project or QgsProject.instance()
    value, ok = project.readEntry(ENTRY, BATHYMETRY, "")
    return parse(value) if ok else {}


def write_bathymetry(settings, project=None):
    from ..core.bathymetry import dump
    project = project or QgsProject.instance()
    project.writeEntry(ENTRY, BATHYMETRY, dump(settings))


def read_map_years(project=None):
    """Годы исторических карт проекта: {номер слоя: год}, год
    астрономический."""
    project = project or QgsProject.instance()
    value, ok = project.readEntry(ENTRY, MAP_YEARS, "")
    if not ok or not value:
        return {}
    try:
        data = json.loads(value)
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): int(v) for k, v in data.items()
            if isinstance(v, int) and not isinstance(v, bool)}


def write_map_years(years, project=None):
    project = project or QgsProject.instance()
    project.writeEntry(ENTRY, MAP_YEARS, json.dumps(
        {k: int(v) for k, v in years.items()}, sort_keys=True))


def read_swipe_sides(project=None):
    """Стороны шторки слоёв: {номер слоя: left или right}."""
    from ..core.sides import parse
    project = project or QgsProject.instance()
    value, ok = project.readEntry(ENTRY, SWIPE_SIDES, "")
    return parse(value) if ok else {}


def write_swipe_sides(sides, project=None):
    from ..core.sides import dump
    project = project or QgsProject.instance()
    project.writeEntry(ENTRY, SWIPE_SIDES, dump(sides))


def read_section_colors(project=None):
    """Свои цвета окна «Разрез модели»: {ключ: {"fill" или "line":
    (r, g, b)}}, ключ - код пласта или core.subsurface.HOST."""
    project = project or QgsProject.instance()
    value, ok = project.readEntry(ENTRY, SECTION_COLORS, "")
    try:
        data = json.loads(value) if ok and value else {}
    except ValueError:
        return {}
    out = {}
    for key, parts in (data.items() if isinstance(data, dict) else ()):
        if not isinstance(parts, dict):
            continue
        for part in ("fill", "line"):
            text = str(parts.get(part) or "").lstrip("#").lower()
            if len(text) == 6 and all(c in string.hexdigits for c in text):
                out.setdefault(str(key), {})[part] = tuple(
                    int(text[i:i + 2], 16) for i in (0, 2, 4))
    return out


def write_section_colors(colors, project=None):
    """Свои цвета разреза модели в запись проекта, «#rrggbb»."""
    project = project or QgsProject.instance()
    data = {str(key): {part: "#%02x%02x%02x" % tuple(rgb[:3])
                       for part, rgb in parts.items()}
            for key, parts in colors.items() if parts}
    project.writeEntry(ENTRY, SECTION_COLORS,
                       json.dumps(data, sort_keys=True))


def read_pointclouds(project=None):
    """Настройки облаков точек на глобусе: {номер слоя: словарь
    core.pointcloud.style}."""
    project = project or QgsProject.instance()
    value, ok = project.readEntry(ENTRY, POINTCLOUDS, "")
    try:
        data = json.loads(value) if ok and value else {}
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def write_pointclouds(styles, project=None):
    project = project or QgsProject.instance()
    project.writeEntry(ENTRY, POINTCLOUDS, json.dumps(styles, sort_keys=True))


def layer_group(layer_id, project=None):
    """Имя пути группы слоя в дереве проекта, «» - корень. Карты одной
    группы сменяют друг друга на шкале времени."""
    project = project or QgsProject.instance()
    node = project.layerTreeRoot().findLayer(layer_id)
    names = []
    parent = node.parent() if node is not None else None
    while parent is not None and parent.parent() is not None:
        names.append(parent.name())
        parent = parent.parent()
    return "/".join(reversed(names))


def read_grids(project=None):
    """Номера растров проекта - поверхностей по отметкам."""
    project = project or QgsProject.instance()
    value, ok = project.readListEntry(ENTRY, GRIDS, [])
    return list(value) if ok else []


def write_grids(ids, project=None):
    project = project or QgsProject.instance()
    project.writeEntry(ENTRY, GRIDS, list(ids))


def read_zlayers(project=None):
    """Номера векторных слоёв проекта с Z - объёмом по отметкам."""
    project = project or QgsProject.instance()
    value, ok = project.readListEntry(ENTRY, ZLAYERS, [])
    return list(value) if ok else []


def write_zlayers(ids, project=None):
    project = project or QgsProject.instance()
    project.writeEntry(ENTRY, ZLAYERS, list(ids))


def read_ztrue(project=None):
    """Номера слоёв с Z, которые и без рельефа стоят на истинных
    отметках над уровнем моря, а не от поверхности."""
    project = project or QgsProject.instance()
    value, ok = project.readListEntry(ENTRY, ZTRUE, [])
    return list(value) if ok else []


def write_ztrue(ids, project=None):
    project = project or QgsProject.instance()
    project.writeEntry(ENTRY, ZTRUE, list(ids))


def read_extrude(project=None):
    """Выдавливание векторных слоёв: {номер слоя: {"field": поле,
    "factor": множитель}}."""
    project = project or QgsProject.instance()
    value, ok = project.readEntry(ENTRY, EXTRUDE, "")
    if not ok or not value:
        return {}
    try:
        data = json.loads(value)
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def write_extrude(settings, project=None):
    project = project or QgsProject.instance()
    project.writeEntry(ENTRY, EXTRUDE, json.dumps(settings,
                                                  ensure_ascii=False))


class ProjectWatch(QObject):
    """Сигнал changed при любом изменении слоёв проекта.

    Живёт вместе с окном. Связи с проектом, деревом слоёв и слоями
    идут через _link и снимаются по сигналу destroyed. Qt сам их
    не снимает, у лямбды нет получателя. Без этого сигнал проекта
    после закрытия окна обращался к удалённому объекту, QGIS 3.40.15
    писал RuntimeError.
    """

    changed = pyqtSignal()
    # Проект открыт заново или очищен, настройки нужно перечитать.
    reloaded = pyqtSignal()
    # Слой переименован: список нужно перерисовать, глобус - нет.
    renamed = pyqtSignal()
    # Выделение в векторном слое сменилось, номер слоя.
    selected = pyqtSignal(str)
    # Видимость в дереве слоёв QGIS сменилась.
    legend = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        project = QgsProject.instance()
        root = project.layerTreeRoot()
        self._wired = set()
        self._links = []
        self.destroyed.connect(partial(_unlink, self._links))
        # Запросы перерисовки и смены выделения за один проход цикла
        # событий. Перерисовка слоя, у которого в том же проходе сменилось
        # выделение, - от выделения, а не от правки данных или стиля.
        # QGIS шлёт её и до, и после сигнала выделения.
        self._repainted = set()
        self._selecting = set()
        self._pass = QTimer(self)
        self._pass.setSingleShot(True)
        self._pass.timeout.connect(self._end_pass)
        self._link(project.layersAdded, self._added)
        self._link(project.layersRemoved, self._changed)
        self._link(project.readProject, self._reloaded)
        self._link(project.cleared, self._reloaded)
        self._link(root.layerOrderChanged, self._changed)
        self._link(root.customLayerOrderChanged, self._changed)
        self._link(root.hasCustomLayerOrderChanged, self._changed)
        self._link(root.visibilityChanged,
                   lambda *args: self.legend.emit())
        self._wire(project.mapLayers().values())

    def _link(self, signal, slot):
        """Связь с чужим объектом, снимается вместе с этим объектом."""
        self._links.append(signal.connect(slot))

    def _wire(self, layers):
        for layer in layers:
            if layer.id() in self._wired:
                continue
            self._wired.add(layer.id())
            layer_id = layer.id()
            self._link(layer.repaintRequested,
                       lambda *args, lid=layer_id: self._repaint(lid))
            self._link(layer.nameChanged, self.renamed)
            if hasattr(layer, "selectionChanged"):
                self._link(layer.selectionChanged,
                           lambda *args, lid=layer_id: self._selection(lid))

    def _selection(self, layer_id):
        self._selecting.add(layer_id)
        self._pass.start(0)
        self.selected.emit(layer_id)

    def _repaint(self, layer_id):
        self._repainted.add(layer_id)
        self._pass.start(0)

    def _end_pass(self):
        changed = self._repainted - self._selecting
        self._repainted = set()
        self._selecting = set()
        if changed:
            self.changed.emit()

    def _added(self, layers):
        self._wire(layers)
        self.changed.emit()

    def _reloaded(self, *args):
        self._wired.clear()
        self._wire(QgsProject.instance().mapLayers().values())
        self.reloaded.emit()
        self.changed.emit()

    def _changed(self, *args):
        self.changed.emit()


def _unlink(links, *args):
    """Снять связи уничтоженного ProjectWatch.

    Связь с уже удалённым слоем Qt снял раньше, disconnect для неё
    возвращает False и ничего не делает.
    """
    for link in links:
        QObject.disconnect(link)
    links.clear()
