# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Реестр строк каталога «Добавить данные» и раздела «Слои».

Строка описывает себя одной записью Row в своём файле ui/<строка>.py:
ключ, группа каталога, источник, цвета превью, слова строки «Поиск», слои
вида, которые гасит ползунок непрозрачности, общий слой вида одной карты,
название и подсказка, исполнитель у окна глобуса. Каталог, строка «Поиск»
и окно глобуса обходят реестр и не знают строку по имени. Решение автора
от 7 ноября 2026 года, правило «Как снять перегруз» doc/PLAN.md Lite.

Исполнитель - класс, его экземпляр один на окно и на все строки с этим
классом. Он даёт turn(key, on), shown_key (ключ показанной строки или
None), identify(lat, lon) - группы окна «Объекты», credit() - (текст,
адрес) подписи источников или None, close(). Исполнитель точек даёт
ещё pick(px, py) - группы окна «Объекты» по точкам у пикселя кадра,
и point_rows(layer, index) - поля и строки выгрузки точек.

Необязательные крючки, окно обходит их у всех исполнителей: ask(lat,
lon) - запрос службы под щелчком, shapes() и marks() - свои линии
и надписи вида, view_changed(), time_changed(), time_marks(),
time_events(), wedge_changed(), place_values(lat, lon) - строки группы
«Место», card_under(px, py) - функция открытия карточки под щелчком,
pixel_groups(px, py) - группы окна «Объекты» по пикселю, credits() -
пары подписи источников, legend и sync_legend() - шкала строки,
base_source() - подложка Земли вместо выбранной, flat_relief() - рельеф
выключен.
"""


class RowError(ValueError):
    """Ошибка описания строки или повтор ключа."""


class Row:
    """Описание строки каталога."""

    def __init__(self, key, group, names, tool=None, source="",
                 colors=(), words=(), fades=(), view_map=None,
                 default=False, earth=True, after=None, qgis_layer=False,
                 points=None, catalog=True, remember=True, preview=None):
        if not key or not group:
            raise RowError("row needs key and group")
        if not callable(names):
            raise RowError("names of {} must be callable".format(key))
        self.key = key
        self.group = group
        self.names = names  # () -> (название, подсказка), через tr
        self.tool = tool
        self.source = source
        self.colors = tuple(colors)
        self.words = tuple(words)
        self.fades = tuple(fades)
        self.view_map = view_map  # общий слой вида, на глобусе одна карта
        self.default = bool(default)
        self.earth = bool(earth)
        self.after = after  # ключ строки, за которой стоит строка каталога
        # Строка рисуется слоем QGIS в картинке наложения: непрозрачность
        # меняет слой, «В проект QGIS…» - исполнитель.
        self.qgis_layer = bool(qgis_layer)
        # Строка рисуется точками - поле вида points: ползунок меняет их
        # непрозрачность, «В проект QGIS…» пишет точки рамки вида.
        self.points = points
        # Строка стоит в каталоге слоёв (place). False - карточку даёт
        # другая часть каталога, как пожарам - общий выбор тем.
        self.catalog = bool(catalog)
        # False - строка не переживает закрытие окна: при открытии она
        # выключена, как палеогеография (решение автора от 3 октября
        # 2026 года).
        self.remember = bool(remember)
        # Шаблон адреса тайла {z}/{x}/{y} превью каталога или None -
        # превью рисуется цветами colors.
        self.preview = preview
class Registry:
    """Строки по порядку регистрации."""

    def __init__(self):
        self.rows = []
        self.by_key = {}

    def add(self, *rows):
        for row in rows:
            if row.key in self.by_key:
                raise RowError("repeated row key {}".format(row.key))
            self.rows.append(row)
            self.by_key[row.key] = row
        return self

    def get(self, key):
        return self.by_key.get(key)

    def keys(self):
        return tuple(row.key for row in self.rows)

    def defaults(self):
        return {row.key: row.default for row in self.rows}

    def earth_keys(self):
        return tuple(row.key for row in self.rows if row.earth)

    def fades(self):
        return {row.key: row.fades for row in self.rows if row.fades}

    def forgotten(self):
        """Ключи строк, выключенных при открытии окна."""
        return tuple(row.key for row in self.rows if not row.remember)

    def previews(self):
        """Ключ строки - шаблон адреса тайла превью."""
        return {row.key: row.preview for row in self.rows if row.preview}

    def qgis_keys(self):
        return tuple(row.key for row in self.rows if row.qgis_layer)

    def points(self):
        """Ключ строки - поле вида её точек."""
        return {row.key: row.points for row in self.rows if row.points}

    def view_maps(self, layer):
        """Ключи строк, которые делят слой вида layer."""
        return tuple(row.key for row in self.rows if row.view_map == layer)

    def groups(self):
        """Пары (ключ, группа каталога) по порядку."""
        return tuple((row.key, row.group) for row in self.rows)

    def place(self, pairs):
        """Пары (ключ, группа) каталога pairs со строками реестра: строка
        с after встаёт за своей строкой, в том числе за строкой реестра,
        прочие - в конец по порядку."""
        out = list(pairs)
        pending = [row for row in self.rows if row.catalog]
        while pending:
            keys = [key for key, _ in out]
            ready = [row for row in pending
                     if row.after is None or row.after in keys]
            if not ready:
                raise RowError("rows placed after unknown keys: {}".format(
                    ", ".join(row.key for row in pending)))
            for row in ready:
                keys = [key for key, _ in out]
                at = len(out) if row.after is None \
                    else keys.index(row.after) + 1
                out.insert(at, (row.key, row.group))
                pending.remove(row)
        return tuple(out)

    def sources(self):
        return {row.key: row.source for row in self.rows}

    def colors(self):
        return {row.key: row.colors for row in self.rows if row.colors}

    def words(self):
        return {row.key: row.words for row in self.rows if row.words}

    def names(self):
        return {row.key: row.names() for row in self.rows}

    def tools(self):
        """Классы исполнителей без повторов, по порядку."""
        out = []
        for row in self.rows:
            if row.tool is not None and row.tool not in out:
                out.append(row.tool)
        return out
