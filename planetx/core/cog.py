# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Чтение облачного GeoTIFF (COG) частями файла без GDAL. Модуль не знает
про Qt.

Рельеф 30 м и глубины морей (core/dem.py) читались через GDAL /vsicurl
в рабочих потоках. Сеть GDAL - curl мимо прокси QGIS, его служебные
потоки распознавания имён завершаются после каждого запроса, а с ними
вызываются DllMain всех библиотек процесса под блокировкой загрузчика
Windows. У пользователя Владимира 23 октября 2026 года QGIS вставал
при подлёте к участку с рельефом Copernicus. Просьба автора того же
дня - читать Copernicus без завершения потоков. Части файла теперь
просит менеджер сети модуля (прокси QGIS, свои потоки Qt), здесь -
только разбор и выборка.

fetch(начало, длина) -> байты: поставляет вызывающий, вызов ждёт ответа.
Поддержано то, что есть в файлах рельефа: TIFF и BigTIFF с прямым
порядком байтов, тайлы, сжатие DEFLATE, LZW или без сжатия, предиктор
1, 2 и 3, один канал Float32, Int16 или Int32, система EPSG:4326.
LZW у ALOS AW3D30 и USGS 3DEP (25 октября 2026 года): сжатый тайл
заворачивается в маленький TIFF серой картинкой по 8 бит шириной
в байты строки (lzw_tiff) и раскодируется читателем TIFF Qt, его
ставит вызывающий (set_lzw). Без него - lzw_decode на Python, для
тестов, он в десятки раз медленнее.

Картинки - снимки событий Vantor и Planet (core/events.py): три-четыре
канала по 8 бит вперемежку, сжатие LZW, DEFLATE или JPEG, системы
EPSG:4326, 3857 и UTM WGS84. Тайл картинки здесь не распаковывается,
он заворачивается в маленький TIFF (tiff_bytes), его раскодирует
вызывающий - средствами Qt, LZW на Python шёл бы секунды на тайл.
"""
import math
import struct
import threading
import zlib
from collections import OrderedDict

import numpy as np

try:  # внутри плагина QGIS
    from .coords import utm_arrays
except ImportError:  # headless-тесты
    from coords import utm_arrays

HEAD = 65536  # байт начала файла: заголовок и каталоги COG
CACHE_BYTES = 64 << 20  # распакованных тайлов в памяти на файл
SIDE = 256
RADIUS = 6378137.0
# Картинки: сжатие без него, LZW, JPEG, DEFLATE, и теги, которые тайл
# уносит в свой TIFF - цветовая модель, лишние каналы, таблицы JPEG,
# прореживание цвета.
PICTURE_COMPRESSION = (1, 5, 7, 8, 32946)
PICTURE_TAGS = (262, 338, 347, 530)
JOIN_GAP = 65536  # байт промежутка, который читается ради одного запроса

_TYPES = {1: ("B", 1), 2: ("s", 1), 3: ("H", 2), 4: ("I", 4), 5: ("II", 8),
          6: ("b", 1), 7: ("B", 1), 8: ("h", 2), 9: ("i", 4), 11: ("f", 4),
          12: ("d", 8), 16: ("Q", 8), 17: ("q", 8), 18: ("Q", 8)}
_DTYPES = {(3, 32): "<f4", (2, 16): "<i2", (2, 32): "<i4", (1, 16): "<u2",
           (1, 8): "u1", (3, 64): "<f8"}
# Раскодирование LZW тайла высот: (сжатые байты, байт в строке, строк)
# -> байты. Ставит вызывающий (set_lzw), иначе lzw_decode_rows.
_LZW = []


def set_lzw(decoder):
    """Раскодирование LZW средствами вызывающего, None - на Python."""
    _LZW[:] = [decoder] if decoder is not None else []


class CogError(ValueError):
    """Файл не разбирается как поддержанный COG."""


class Image:
    """Один каталог файла: полное разрешение или обзор."""

    __slots__ = ("width", "height", "tile_w", "tile_h", "offsets", "counts",
                 "compression", "predictor", "dtype", "scale", "samples",
                 "picture", "keep", "planar")

    def __init__(self, tags, fetch_array):
        try:
            self.width = int(tags[256][0])
            self.height = int(tags[257][0])
            self.tile_w = int(tags[322][0])
            self.tile_h = int(tags[323][0])
        except KeyError as error:
            raise CogError("not a tiled TIFF") from error
        self.compression = int(tags.get(259, (1,))[0])
        self.predictor = int(tags.get(317, (1,))[0])
        self.samples = int(tags.get(277, (1,))[0])
        fmt = int(tags.get(339, (1,))[0])
        bits = int(tags.get(258, (8,))[0])
        self.picture = self.samples > 1
        self.keep = {}
        # Каналы вперемежку (1) или плоскостями (2) - у мозаик Planet.
        self.planar = int(tags.get(284, (1,))[0])
        if self.picture:
            # Снимок: каналы по 8 бит, раскодирует вызывающий.
            if self.samples not in (3, 4) or bits != 8 or fmt != 1 \
                    or self.planar not in (1, 2):
                raise CogError("picture layout")
            if self.compression not in PICTURE_COMPRESSION:
                raise CogError("compression %d" % self.compression)
            self.dtype = np.dtype("u1")
            self.keep = {tag: tags[tag] for tag in PICTURE_TAGS
                         if tag in tags}
        else:
            if self.compression not in (1, 5, 8, 32946):
                raise CogError("compression %d" % self.compression)
            if (fmt, bits) not in _DTYPES:
                raise CogError("sample %d/%d" % (fmt, bits))
            self.dtype = np.dtype(_DTYPES[(fmt, bits)])
        self.offsets = fetch_array(324)
        self.counts = fetch_array(325)
        self.scale = 1.0  # пикселей полного разрешения на пиксель

    @property
    def across(self):
        return -(-self.width // self.tile_w)

    @property
    def plane_tiles(self):
        """Тайлов в одной плоскости каналов."""
        return self.across * -(-self.height // self.tile_h)

    def decode(self, raw):
        """Распакованный тайл tile_h × tile_w."""
        need = self.tile_w * self.tile_h * self.dtype.itemsize
        if self.compression == 5:
            columns = self.tile_w * self.dtype.itemsize
            raw = (_LZW[0] if _LZW else lzw_decode_rows)(
                bytes(raw), columns, self.tile_h)
        elif self.compression != 1:
            raw = zlib.decompress(raw)
        if len(raw) < need:
            raise CogError("short tile")
        raw = raw[:need]
        if self.predictor == 3:
            size = self.dtype.itemsize
            rows = np.frombuffer(raw, np.uint8).reshape(
                self.tile_h, size * self.tile_w)
            rows = np.cumsum(rows, axis=1, dtype=np.uint8)
            planes = rows.reshape(self.tile_h, size, self.tile_w)
            # Байты значения в строке - сначала старшие, порядок меняется.
            data = np.ascontiguousarray(
                planes.transpose(0, 2, 1)[:, :, ::-1])
            return data.view(self.dtype).reshape(self.tile_h, self.tile_w)
        tile = np.frombuffer(raw, self.dtype).reshape(self.tile_h,
                                                      self.tile_w)
        if self.predictor == 2:
            tile = np.cumsum(tile, axis=1, dtype=self.dtype)
        return tile


class Cog:
    """Файл COG по fetch. Каталоги читаются при создании, тайлы - по
    просьбе, распакованные тайлы помнятся до CACHE_BYTES."""

    def __init__(self, fetch):
        self.fetch = fetch
        self.lock = threading.Lock()
        self.cache = OrderedDict()
        self.cached = 0
        head = fetch(0, HEAD)
        if len(head) < 16:
            raise CogError("short header")
        if head[:2] != b"II":
            raise CogError("byte order")
        magic = struct.unpack_from("<H", head, 2)[0]
        self.big = magic == 43
        if magic not in (42, 43):
            raise CogError("not TIFF")
        self.head = head
        offset = struct.unpack_from("<Q", head, 8)[0] if self.big \
            else struct.unpack_from("<I", head, 4)[0]
        self.images = []
        first = None
        while offset:
            tags, offset = self._ifd(offset)
            subfile = int(tags.get(254, (0,))[0])
            if first is None:
                first = tags
            if subfile & 4:  # маска
                continue
            self.images.append(Image(tags, lambda tag, t=tags:
                                     self._array(t, tag)))
        if not self.images:
            raise CogError("no images")
        full = self.images[0]
        for image in self.images:
            image.scale = full.width / image.width
        self.nodata = _nodata(first)
        self.transform = _transform(first)
        self.epsg = _epsg(first)

    # Каталоги.

    def _bytes(self, start, length):
        if start + length <= len(self.head):
            return self.head[start:start + length]
        return self.fetch(start, length)

    def _ifd(self, offset):
        count_fmt, entry, count_size, next_fmt = (
            ("<Q", 20, 8, "<Q") if self.big else ("<H", 12, 2, "<I"))
        count = struct.unpack(count_fmt, self._bytes(offset, count_size))[0]
        block = self._bytes(offset + count_size,
                            count * entry + (8 if self.big else 4))
        tags = {}
        for i in range(count):
            at = i * entry
            if self.big:
                tag, kind, n = struct.unpack_from("<HHQ", block, at)
                inline, value_at = 8, at + 12
            else:
                tag, kind, n = struct.unpack_from("<HHI", block, at)
                inline, value_at = 4, at + 8
            if kind not in _TYPES:
                continue
            code, size = _TYPES[kind]
            total = size * n
            if total <= inline:
                raw = block[value_at:value_at + total]
                tags[tag] = _values(raw, code, n, kind)
            else:
                where = struct.unpack_from("<Q" if self.big else "<I",
                                           block, value_at)[0]
                tags[tag] = ("@", where, kind, n)
        nxt = struct.unpack_from(next_fmt, block, count * entry)[0]
        for tag in (322, 323, 256, 257, 254, 259, 317, 277, 339, 258, 33550,
                    33922, 34735, 42113, 262, 284, 338, 347, 530):
            if tag in tags and tags[tag][0] == "@":
                _, where, kind, n = tags[tag]
                code, size = _TYPES[kind]
                tags[tag] = _values(self._bytes(where, size * n), code, n,
                                    kind)
        return tags, nxt

    def _array(self, tags, tag):
        """Значения тега массивом uint64 - смещения и длины тайлов."""
        value = tags.get(tag)
        if value is None:
            raise CogError("no tile index")
        if value[0] != "@":
            return np.asarray(value, dtype=np.uint64)
        _, where, kind, n = value
        code, size = _TYPES[kind]
        raw = self._bytes(where, size * n)
        dtype = {2: "<u2", 4: "<u4", 8: "<u8"}[size]
        return np.frombuffer(raw, dtype).astype(np.uint64)

    # Тайлы.

    def tile(self, level, col, row):
        """Распакованный тайл или None, если его нет в файле."""
        key = (level, col, row)
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
        image = self.images[level]
        index = row * image.across + col
        if index >= len(image.offsets):
            return None
        start, length = int(image.offsets[index]), int(image.counts[index])
        if length == 0:
            return None
        data = image.decode(self.fetch(start, length))
        with self.lock:
            self.cache[key] = data
            self.cached += data.nbytes
            while self.cached > CACHE_BYTES and len(self.cache) > 1:
                _, old = self.cache.popitem(last=False)
                self.cached -= old.nbytes
        return data

    def level_for(self, step):
        """Самый грубый обзор с пикселем не крупнее step градусов."""
        full = abs(self.transform[1])
        best = 0
        for n, image in enumerate(self.images):
            if full * image.scale <= step:
                best = n
        return best

    def sample(self, lon, lat, level):
        """Значения в точках (массивы градусов) билинейно с обзора level,
        NaN вне файла и без данных."""
        image = self.images[level]
        x0, dx, _, y0, _, dy = self.transform
        dx, dy = dx * image.scale, dy * image.scale
        # Узлы пикселей - их середины.
        fx = (lon - x0) / dx - 0.5
        fy = (lat - y0) / dy - 0.5
        out = np.full(fx.shape, np.nan, dtype=np.float32)
        inside = (fx > -0.5) & (fy > -0.5) & (fx < image.width - 0.5) \
            & (fy < image.height - 0.5)
        if not inside.any():
            return out
        fx = np.clip(fx, 0.0, image.width - 1.0)
        fy = np.clip(fy, 0.0, image.height - 1.0)
        c0 = int(np.floor(fx[inside].min()))
        c1 = int(np.ceil(fx[inside].max()))
        r0 = int(np.floor(fy[inside].min()))
        r1 = int(np.ceil(fy[inside].max()))
        block = self._block(level, c0, r0, c1, r1)
        ix = np.clip(np.floor(fx).astype(np.int64), c0, c1)
        iy = np.clip(np.floor(fy).astype(np.int64), r0, r1)
        jx = np.minimum(ix + 1, c1)
        jy = np.minimum(iy + 1, r1)
        tx = (fx - ix).astype(np.float32)
        ty = (fy - iy).astype(np.float32)
        a = block[iy - r0, ix - c0]
        b = block[iy - r0, jx - c0]
        c = block[jy - r0, ix - c0]
        d = block[jy - r0, jx - c0]
        value = (a * (1 - tx) + b * tx) * (1 - ty) + \
            (c * (1 - tx) + d * tx) * ty
        out[inside] = value[inside]
        return out

    def _block(self, level, c0, r0, c1, r1):
        """Пиксели c0..c1, r0..r1 обзора level в float32, NaN без данных."""
        image = self.images[level]
        out = np.full((r1 - r0 + 1, c1 - c0 + 1), np.nan, dtype=np.float32)
        for row in range(r0 // image.tile_h, r1 // image.tile_h + 1):
            for col in range(c0 // image.tile_w, c1 // image.tile_w + 1):
                tile = self.tile(level, col, row)
                if tile is None:
                    continue
                ty, tx = row * image.tile_h, col * image.tile_w
                ya, yb = max(r0, ty), min(r1 + 1, ty + image.tile_h)
                xa, xb = max(c0, tx), min(c1 + 1, tx + image.tile_w)
                part = tile[ya - ty:yb - ty, xa - tx:xb - tx] \
                    .astype(np.float32)
                if self.nodata is not None:
                    part = np.where(part == self.nodata, np.nan, part)
                out[ya - r0:yb - r0, xa - c0:xb - c0] = part
        return out

    # Картинки.

    def picture(self, level, col, row, decode):
        """Тайл картинки (tile_h, tile_w, 4) RGBA uint8 или None, если
        его нет в файле. decode(байты TIFF) - массив RGBA или None."""
        key = (level, col, row)
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key]
        image = self.images[level]
        index = row * image.across + col
        planes = image.samples if image.planar == 2 else 1
        spans = []
        for plane in range(planes):
            at = index + plane * image.plane_tiles
            if at >= len(image.offsets):
                return None
            spans.append((int(image.offsets[at]), int(image.counts[at])))
        if any(length == 0 for _, length in spans):
            return None
        data = decode(tiff_bytes(image, self._spans(spans)))
        if data is None or data.shape[:2] != (image.tile_h, image.tile_w):
            raise CogError("picture tile")
        if image.samples == 3:
            # Без канала прозрачности чёрное - за краем снимка.
            data = data.copy()
            data[..., 3] = np.where(data[..., :3].any(axis=2), 255, 0)
        with self.lock:
            self.cache[key] = data
            self.cached += data.nbytes
            while self.cached > CACHE_BYTES and len(self.cache) > 1:
                _, old = self.cache.popitem(last=False)
                self.cached -= old.nbytes
        return data

    def _spans(self, spans):
        """Байты частей файла (начало, длина). Близкие части - одним
        запросом: плоскости каналов тайла лежат рядом."""
        lo = min(start for start, _ in spans)
        hi = max(start + length for start, length in spans)
        total = sum(length for _, length in spans)
        if len(spans) > 1 and hi - lo <= 2 * total + JOIN_GAP:
            block = self.fetch(lo, hi - lo)
            return [block[start - lo:start - lo + length]
                    for start, length in spans]
        return [self.fetch(start, length) for start, length in spans]

    def sample_rgba(self, xs, ys, level, decode):
        """Цвета RGBA uint8 формы xs + (4,) в точках xs, ys системы
        файла билинейно с обзора level. Вне снимка - прозрачные. Цвет
        взвешивается прозрачностью соседей, край снимка не темнеет."""
        image = self.images[level]
        x0, dx, _, y0, _, dy = self.transform
        dx, dy = dx * image.scale, dy * image.scale
        fx = (xs - x0) / dx - 0.5
        fy = (ys - y0) / dy - 0.5
        out = np.zeros(fx.shape + (4,), dtype=np.uint8)
        inside = (fx > -0.5) & (fy > -0.5) & (fx < image.width - 0.5) \
            & (fy < image.height - 0.5)
        if not inside.any():
            return out
        fx = np.clip(fx[inside], 0.0, image.width - 1.0)
        fy = np.clip(fy[inside], 0.0, image.height - 1.0)
        c0, c1 = int(np.floor(fx.min())), int(np.ceil(fx.max()))
        r0, r1 = int(np.floor(fy.min())), int(np.ceil(fy.max()))
        block = self._picture_block(level, c0, r0, c1, r1, decode)
        ix = np.floor(fx).astype(np.int64)
        iy = np.floor(fy).astype(np.int64)
        jx = np.minimum(ix + 1, c1)
        jy = np.minimum(iy + 1, r1)
        tx = (fx - ix).astype(np.float32)[:, None]
        ty = (fy - iy).astype(np.float32)[:, None]
        color = np.zeros((len(fx), 3), dtype=np.float32)
        weight = np.zeros((len(fx), 1), dtype=np.float32)
        for px, py, w in ((ix, iy, (1 - tx) * (1 - ty)),
                          (jx, iy, tx * (1 - ty)),
                          (ix, jy, (1 - tx) * ty), (jx, jy, tx * ty)):
            corner = block[py - r0, px - c0].astype(np.float32)
            wa = w * corner[:, 3:4] / 255.0
            color += wa * corner[:, :3]
            weight += wa
        rgb = color / np.maximum(weight, 1e-6)
        part = np.concatenate([rgb, weight * 255.0], axis=1)
        out[inside] = np.clip(np.rint(part), 0, 255).astype(np.uint8)
        return out

    def _picture_block(self, level, c0, r0, c1, r1, decode):
        """Пиксели c0..c1, r0..r1 обзора level картинкой RGBA uint8,
        тайлов нет - прозрачные."""
        image = self.images[level]
        out = np.zeros((r1 - r0 + 1, c1 - c0 + 1, 4), dtype=np.uint8)
        for row in range(r0 // image.tile_h, r1 // image.tile_h + 1):
            for col in range(c0 // image.tile_w, c1 // image.tile_w + 1):
                tile = self.picture(level, col, row, decode)
                if tile is None:
                    continue
                ty, tx = row * image.tile_h, col * image.tile_w
                ya, yb = max(r0, ty), min(r1 + 1, ty + image.tile_h)
                xa, xb = max(c0, tx), min(c1 + 1, tx + image.tile_w)
                out[ya - r0:yb - r0, xa - c0:xb - c0] = \
                    tile[ya - ty:yb - ty, xa - tx:xb - tx]
        return out


def tiff_bytes(image, raws):
    """Сжатый тайл картинки image маленьким TIFF: raws - байты тайла,
    у каналов плоскостями - по плоскости на полосу. Его раскодирует
    читатель TIFF в Qt (libtiff) - LZW, DEFLATE, JPEG с таблицами файла
    и предиктором."""
    n = image.samples
    sizes = tuple(len(raw) for raw in raws)
    entries = {256: (4, (image.tile_w,)), 257: (4, (image.tile_h,)),
               258: (3, (8,) * n), 259: (3, (image.compression,)),
               262: (3, (2,)), 273: (4, (0,) * len(raws)), 277: (3, (n,)),
               278: (4, (image.tile_h,)), 279: (4, sizes),
               284: (3, (image.planar,)), 317: (3, (image.predictor,))}
    for tag, value in image.keep.items():
        entries[tag] = (7 if tag == 347 else 3, tuple(int(v) for v in value))
    # Длина каталога не зависит от смещений полос: сначала место,
    # потом смещения.
    data_at = len(_tiff_head(entries))
    offsets, at = [], data_at
    for size in sizes:
        offsets.append(at)
        at += size
    entries[273] = (4, tuple(offsets))
    return _tiff_head(entries) + b"".join(raws)


def lzw_tiff(raw, columns, rows):
    """Сжатый LZW тайл высот маленьким TIFF: серая картинка по 8 бит
    columns × rows без предиктора - читатель раскодирует только LZW,
    байты значений и предиктор разбирает Image.decode."""
    entries = {256: (4, (columns,)), 257: (4, (rows,)), 258: (3, (8,)),
               259: (3, (5,)), 262: (3, (1,)), 273: (4, (0,)),
               277: (3, (1,)), 278: (4, (rows,)), 279: (4, (len(raw),))}
    entries[273] = (4, (len(_tiff_head(entries)),))
    return _tiff_head(entries) + raw


def lzw_decode_rows(raw, columns, rows):
    """Раскодирование LZW на Python: columns × rows байт."""
    out = lzw_decode(raw)
    need = columns * rows
    if len(out) < need:
        raise CogError("short tile")
    return out[:need]


def lzw_decode(raw):
    """LZW в разметке TIFF: коды от 9 до 12 бит, старший бит первым,
    ширина растёт на код раньше (early change), 256 - сброс таблицы,
    257 - конец."""
    out = bytearray()
    table = [bytes((i,)) for i in range(256)] + [b"", b""]
    width = 9
    acc = bits = 0
    previous = None
    for byte in raw:
        acc = (acc << 8) | byte
        bits += 8
        while bits >= width:
            bits -= width
            code = (acc >> bits) & ((1 << width) - 1)
            if code == 257:
                return bytes(out)
            if code == 256:
                del table[258:]
                width = 9
                previous = None
                continue
            if previous is None:
                entry = table[code]
            elif code < len(table):
                entry = table[code]
                table.append(previous + entry[:1])
            else:
                entry = previous + previous[:1]
                table.append(entry)
            out += entry
            previous = entry
            if len(table) + 1 >= (1 << width) and width < 12:
                width += 1
        acc &= (1 << bits) - 1
    return bytes(out)


def _tiff_head(entries):
    """Заголовок и каталог TIFF с длинными значениями после него."""
    tags = sorted(entries)
    after = 8 + 2 + 12 * len(tags) + 4
    extra = bytearray()
    out = bytearray(b"II*\0" + struct.pack("<I", 8))
    out += struct.pack("<H", len(tags))
    for tag in tags:
        kind, values = entries[tag]
        code = {3: "H", 4: "I", 7: "B"}[kind]
        packed = struct.pack("<%d%s" % (len(values), code), *values)
        if len(packed) <= 4:
            value = packed.ljust(4, b"\0")
        else:
            value = struct.pack("<I", after + len(extra))
            extra += packed
            if len(extra) % 2:
                extra += b"\0"
        out += struct.pack("<HHI", tag, kind, len(values)) + value
    out += struct.pack("<I", 0)
    return bytes(out + extra)


def known_crs(epsg):
    """Система, в которую считает to_crs."""
    return epsg in (None, 4326, 3857) or 32601 <= epsg <= 32660 \
        or 32701 <= epsg <= 32760


def to_crs(epsg, lon, lat):
    """Долготы и широты (массивы градусов) в систему файла: EPSG:4326,
    3857, UTM WGS84 326xx и 327xx. Прочие - CogError."""
    if epsg in (None, 4326):
        return lon, lat
    if epsg == 3857:
        phi = np.radians(np.clip(lat, -85.0511, 85.0511))
        return (RADIUS * np.radians(lon),
                RADIUS * np.log(np.tan(math.pi / 4.0 + phi / 2.0)))
    if 32601 <= epsg <= 32660 or 32701 <= epsg <= 32760:
        return utm_arrays(lat, lon, epsg % 100, epsg >= 32701)
    raise CogError("crs %s" % epsg)


def _values(raw, code, n, kind):
    if kind == 2:
        return (raw.split(b"\0", 1)[0].decode("latin-1"),)
    if kind in (5, 10):
        return tuple(struct.unpack("<%d%s" % (2 * n, "I"), raw))
    return struct.unpack("<%d%s" % (n, code), raw)


def _nodata(tags):
    text = tags.get(42113)
    if not text:
        return None
    try:
        return float(str(text[0]).strip())
    except ValueError:
        return None


def _epsg(tags):
    """Код EPSG системы по ключам GeoTIFF: проекции (3072), иначе
    географической (2048), без ключей - None."""
    keys = tags.get(34735)
    if not keys or len(keys) < 4:
        return None
    found = {}
    for i in range(4, len(keys) - 3, 4):
        if keys[i + 1] == 0:
            found[keys[i]] = keys[i + 3]
    if found.get(3072):
        return int(found[3072])
    if found.get(2048):
        return int(found[2048])
    return 4326 if found.get(1024) == 2 else None


def _transform(tags):
    """Геопреобразование как у GDAL: (x0, dx, 0, y0, 0, -dy) левого
    верхнего угла. У растра PixelIsPoint (ключ 1025 = 2) привязка - к
    середине пикселя, угол сдвигается на полпикселя, как делает GDAL."""
    scale = tags.get(33550)
    tie = tags.get(33922)
    if not scale or not tie or len(tie) < 6:
        raise CogError("no georeference")
    sx, sy = float(scale[0]), float(scale[1])
    x0 = float(tie[3]) - float(tie[0]) * sx
    y0 = float(tie[4]) + float(tie[1]) * sy
    keys = tags.get(34735)
    if keys and len(keys) >= 4:
        for i in range(4, len(keys) - 3, 4):
            if keys[i] == 1025 and keys[i + 1] == 0 and keys[i + 3] == 2:
                x0 -= sx / 2.0
                y0 += sy / 2.0
    return (x0, sx, 0.0, y0, 0.0, -sy)


def tile_points(z, x, y, size=SIDE):
    """Середины пикселей тайла XYZ: долготы и широты, массивы size×size."""
    n = 1 << z
    u = (x + (np.arange(size) + 0.5) / size) / n
    v = (y + (np.arange(size) + 0.5) / size) / n
    lon = u * 360.0 - 180.0
    lat = np.degrees(np.arctan(np.sinh(np.pi * (1.0 - 2.0 * v))))
    return np.meshgrid(lon, lat)


def tile_window(cogs, z, x, y, size=SIDE):
    """Окно тайла z/x/y size×size float32 из файлов cogs (EPSG:4326),
    NaN без данных. Пиксель тайла сравнивается с пикселем обзора по
    долготе."""
    lon, lat = tile_points(z, x, y, size)
    step = 360.0 / (1 << z) / size
    out = np.full(lon.shape, np.nan, dtype=np.float32)
    for cog in cogs:
        part = cog.sample(lon, lat, cog.level_for(step))
        use = np.isfinite(part) & ~np.isfinite(out)
        out[use] = part[use]
    return out
