# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Архив тайлов PMTiles версии 3 частями файла. Модуль не знает про Qt.

Просьба автора от 25 октября 2026 года после разбора RustGIS 0.4.0 -
вторым пунктом здания Overture Maps, их дают одним архивом PMTiles
на 180 ГБ. Архив читается так же, как COG (core/cog.py): fetch(начало,
длина) поставляет вызывающий, вызов ждёт ответа.

Устройство по спецификации PMTiles v3 (github.com/protomaps/PMTiles,
spec/v3): заголовок 127 байт, корневой каталог, листовые каталоги,
тайлы. Каталог - число записей и четыре столбца целых в varint:
номера тайлов разностями, длины серий, длины, смещения (0 - сразу за
предыдущим). Запись с серией 0 - ссылка на листовой каталог. Номер
тайла - сумма тайлов мельче уровня и позиция на кривой Гильберта.
"""
import bisect
import gzip
import struct
import threading
from collections import OrderedDict

HEAD = 16384  # байт начала: заголовок и корневой каталог
LEAVES_KEPT = 64  # листовых каталогов в памяти
COMPRESSION = {1: None, 2: "gzip"}


class PmtilesError(ValueError):
    """Файл не разбирается как поддержанный PMTiles."""


def tile_id(z, x, y):
    """Номер тайла z/x/y в архиве."""
    acc = ((1 << (2 * z)) - 1) // 3
    d = 0
    s = (1 << z) >> 1
    while s > 0:
        rx = 1 if x & s else 0
        ry = 1 if y & s else 0
        d += s * s * ((3 * rx) ^ ry)
        if ry == 0:
            if rx == 1:
                x = s - 1 - x
                y = s - 1 - y
            x, y = y, x
        s >>= 1
    return acc + d


def _varints(data, at, count):
    out = []
    for _ in range(count):
        value = shift = 0
        while True:
            byte = data[at]
            at += 1
            value |= (byte & 0x7F) << shift
            if byte < 0x80:
                break
            shift += 7
        out.append(value)
    return out, at


def directory(data):
    """Записи каталога: списки номеров, серий, смещений и длин."""
    (count,), at = _varints(data, 0, 1)
    deltas, at = _varints(data, at, count)
    runs, at = _varints(data, at, count)
    lengths, at = _varints(data, at, count)
    raw, at = _varints(data, at, count)
    ids, offsets = [], []
    last = 0
    for i in range(count):
        last += deltas[i]
        ids.append(last)
        if i > 0 and raw[i] == 0:
            offsets.append(offsets[-1] + lengths[i - 1])
        else:
            offsets.append(raw[i] - 1)
    return ids, runs, offsets, lengths


def find(entries, target):
    """(серия, смещение, длина) записи с номером target или None."""
    ids, runs, offsets, lengths = entries
    n = bisect.bisect_right(ids, target) - 1
    if n < 0:
        return None
    if runs[n] == 0 or target < ids[n] + runs[n]:
        return runs[n], offsets[n], lengths[n]
    return None


def _unpack(data, kind):
    if kind == 2:
        return gzip.decompress(data)
    if kind in (0, 1):
        return data
    raise PmtilesError("compression %d" % kind)


class Archive:
    """Архив PMTiles по fetch. Заголовок и корень читаются при создании,
    листовые каталоги и тайлы - по просьбе. Тайлы - без сжатия."""

    def __init__(self, fetch):
        self.fetch = fetch
        self.lock = threading.Lock()
        self.leaves = OrderedDict()
        head = fetch(0, HEAD)
        if len(head) < 127 or head[:7] != b"PMTiles" or head[7] != 3:
            raise PmtilesError("not PMTiles v3")
        (root_at, root_len, self.meta_at, self.meta_len, self.leaf_at,
         _, self.data_at, _, _, _, _, _, self.internal, self.compression,
         self.kind, self.min_zoom, self.max_zoom) = struct.unpack_from(
            "<QQQQQQQQQQQBBBBBB", head, 8)
        raw = head[root_at:root_at + root_len] \
            if root_at + root_len <= len(head) else fetch(root_at, root_len)
        self.root = directory(_unpack(raw, self.internal))

    def _leaf(self, offset, length):
        key = (offset, length)
        with self.lock:
            if key in self.leaves:
                self.leaves.move_to_end(key)
                return self.leaves[key]
        found = directory(_unpack(self.fetch(self.leaf_at + offset, length),
                                  self.internal))
        with self.lock:
            self.leaves[key] = found
            while len(self.leaves) > LEAVES_KEPT:
                self.leaves.popitem(last=False)
        return found

    def tile(self, z, x, y):
        """Байты тайла без сжатия или None, если тайла в архиве нет."""
        if not self.min_zoom <= z <= self.max_zoom:
            return None
        target = tile_id(z, x, y)
        entries = self.root
        for _ in range(4):  # глубина каталогов в спецификации не больше 3
            found = find(entries, target)
            if found is None:
                return None
            run, offset, length = found
            if run:
                return _unpack(self.fetch(self.data_at + offset, length),
                               self.compression)
            entries = self._leaf(offset, length)
        raise PmtilesError("directory depth")
