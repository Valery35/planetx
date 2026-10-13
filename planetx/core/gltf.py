# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Чтение моделей glTF 2.0: .gltf с файлами рядом и .glb одним файлом.

Расчёт без Qt. Берутся сетки треугольников (mode 4, полосы и веера
mode 5 и 6 разворачиваются), POSITION, NORMAL, TEXCOORD_0, номера
вершин, материал pbrMetallicRoughness - baseColorFactor и картинка
baseColorTexture. Узлы сцены - matrix или translation, rotation,
scale. Сжатие сеток KHR_draco_mesh_compression и EXT_meshopt не
читается - такой файл даёт ModelError с именем расширения.

Ось Y glTF смотрит вверх, итог переводится в ось Z вверх
(core.models.from_y_up): передняя сторона модели +Z смотрит на юг.
Картинки частей называются "gltf:<номер картинки>".
"""
import base64
import json
import struct

import numpy as np

try:  # внутри плагина QGIS
    from .models import Part, ModelError, from_y_up
except ImportError:  # headless-тесты
    from models import Part, ModelError, from_y_up

COMPONENTS = {5120: np.int8, 5121: np.uint8, 5122: np.int16,
              5123: np.uint16, 5125: np.uint32, 5126: np.float32}
SIZES = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
UNSUPPORTED = ("KHR_draco_mesh_compression", "EXT_meshopt_compression",
               "KHR_mesh_quantization")
GLB_MAGIC = b"glTF"


def split_glb(data):
    """(JSON, двоичный кусок или None) из байтов .glb."""
    if len(data) < 20 or data[:4] != GLB_MAGIC:
        raise ModelError("not GLB")
    _, _, total = struct.unpack_from("<4sII", data, 0)
    at = 12
    text = None
    blob = None
    while at + 8 <= min(total, len(data)):
        length, kind = struct.unpack_from("<II", data, at)
        chunk = data[at + 8:at + 8 + length]
        if kind == 0x4E4F534A:
            text = chunk
        elif kind == 0x004E4942 and blob is None:
            blob = chunk
        at += 8 + length
    if text is None:
        raise ModelError("GLB without JSON")
    return text, blob


class _Doc:
    def __init__(self, data, fetch):
        if data[:4] == GLB_MAGIC:
            text, self.blob = split_glb(data)
        else:
            text, self.blob = data, None
        try:
            self.json = json.loads(text)
        except ValueError as error:
            raise ModelError("bad glTF JSON") from error
        if not isinstance(self.json, dict):
            raise ModelError("bad glTF JSON")
        used = set(self.json.get("extensionsRequired") or ()) \
            | set(self.json.get("extensionsUsed") or ())
        for name in UNSUPPORTED:
            if name in used:
                raise ModelError("unsupported glTF extension: " + name)
        self.fetch = fetch
        self.buffers = {}

    def list(self, name):
        value = self.json.get(name)
        return value if isinstance(value, list) else []

    def item(self, name, index):
        items = self.list(name)
        if not isinstance(index, int) or not 0 <= index < len(items):
            raise ModelError("bad {} index {}".format(name, index))
        return items[index]

    def uri(self, uri):
        """Байты по uri: data: base64 или файл пакета."""
        if uri.startswith("data:"):
            head, _, body = uri.partition(",")
            try:
                return base64.b64decode(body) if head.endswith(";base64") \
                    else body.encode("utf-8")
            except ValueError as error:
                raise ModelError("bad data uri") from error
        data = self.fetch(uri)
        if data is None:
            raise ModelError("file not found: " + uri)
        return data

    def buffer(self, index):
        if index not in self.buffers:
            item = self.item("buffers", index)
            if "uri" in item:
                self.buffers[index] = self.uri(item["uri"])
            elif self.blob is not None:
                self.buffers[index] = self.blob
            else:
                raise ModelError("buffer without data")
        return self.buffers[index]

    def view(self, index):
        view = self.item("bufferViews", index)
        data = self.buffer(view.get("buffer", 0))
        start = int(view.get("byteOffset", 0))
        length = int(view.get("byteLength", 0))
        if start + length > len(data):
            raise ModelError("bufferView out of buffer")
        return data[start:start + length], view.get("byteStride")

    def accessor(self, index):
        """Массив (количество, размер) значений accessor."""
        acc = self.item("accessors", index)
        kind = COMPONENTS.get(acc.get("componentType"))
        size = SIZES.get(acc.get("type"))
        count = int(acc.get("count", 0))
        if kind is None or size is None:
            raise ModelError("bad accessor type")
        if "bufferView" not in acc:
            return np.zeros((count, size))
        data, stride = self.view(acc["bufferView"])
        offset = int(acc.get("byteOffset", 0))
        item = np.dtype(kind).itemsize * size
        stride = int(stride or item)
        need = offset + stride * (count - 1) + item if count else 0
        if need > len(data):
            raise ModelError("accessor out of bufferView")
        raw = np.frombuffer(data, dtype=np.uint8, count=need - offset,
                            offset=offset) if count else \
            np.zeros(0, np.uint8)
        if stride == item:
            values = raw.view(kind).reshape(count, size)
        else:
            rows = np.lib.stride_tricks.as_strided(
                raw, shape=(count, item), strides=(stride, 1))
            values = np.ascontiguousarray(rows).view(kind).reshape(
                count, size)
        values = values.astype(np.float64)
        if acc.get("normalized") and kind is not np.float32:
            top = float(np.iinfo(kind).max)
            values = np.maximum(values / top, -1.0)
        return values


def _node_matrix(node):
    if "matrix" in node and len(node["matrix"]) == 16:
        # Матрица glTF записана по столбцам.
        return np.array(node["matrix"], dtype=np.float64).reshape(4, 4).T
    out = np.eye(4)
    tx, ty, tz = node.get("translation", (0.0, 0.0, 0.0))
    qx, qy, qz, qw = node.get("rotation", (0.0, 0.0, 0.0, 1.0))
    sx, sy, sz = node.get("scale", (1.0, 1.0, 1.0))
    rot = np.array([
        [1 - 2 * (qy * qy + qz * qz), 2 * (qx * qy - qz * qw),
         2 * (qx * qz + qy * qw)],
        [2 * (qx * qy + qz * qw), 1 - 2 * (qx * qx + qz * qz),
         2 * (qy * qz - qx * qw)],
        [2 * (qx * qz - qy * qw), 2 * (qy * qz + qx * qw),
         1 - 2 * (qx * qx + qy * qy)]])
    out[:3, :3] = rot @ np.diag([sx, sy, sz])
    out[:3, 3] = (tx, ty, tz)
    return out


def _triangles(mode, count, indices):
    """Номера вершин треугольников по режиму примитива."""
    order = indices if indices is not None else np.arange(count)
    if mode == 4:
        return order[:len(order) // 3 * 3]
    if mode == 5 and len(order) >= 3:
        k = np.arange(len(order) - 2)
        even = k % 2 == 0
        tri = np.stack([order[k], np.where(even, order[k + 1], order[k + 2]),
                        np.where(even, order[k + 2], order[k + 1])], axis=1)
        return tri.ravel()
    if mode == 6 and len(order) >= 3:
        k = np.arange(1, len(order) - 1)
        tri = np.stack([np.full(len(k), order[0]), order[k], order[k + 1]],
                       axis=1)
        return tri.ravel()
    return np.zeros(0, dtype=np.int64)


def _material(doc, index):
    """(номер картинки или None, RGBA 0-1)."""
    if index is None:
        return None, (0.8, 0.8, 0.8, 1.0)
    material = doc.item("materials", index)
    pbr = material.get("pbrMetallicRoughness") or {}
    rgba = tuple(float(v) for v in pbr.get("baseColorFactor",
                                           (1.0, 1.0, 1.0, 1.0)))
    texture = pbr.get("baseColorTexture")
    if texture is None:
        return None, rgba
    tex = doc.item("textures", texture.get("index"))
    return tex.get("source"), rgba


def _picture(doc, index):
    image = doc.item("images", index)
    if "bufferView" in image:
        data, _ = doc.view(image["bufferView"])
        return bytes(data)
    return doc.uri(image.get("uri", ""))


def _mesh(doc, mesh, matrix, out, pictures):
    linear = matrix[:3, :3]
    try:
        normal_matrix = np.linalg.inv(linear).T
    except np.linalg.LinAlgError:
        return
    mirrored = np.linalg.det(linear) < 0.0
    for prim in mesh.get("primitives") or ():
        attributes = prim.get("attributes") or {}
        if "POSITION" not in attributes:
            continue
        positions = doc.accessor(attributes["POSITION"])[:, :3]
        indices = None
        if "indices" in prim:
            indices = doc.accessor(prim["indices"])[:, 0].astype(np.int64)
        order = _triangles(prim.get("mode", 4), len(positions), indices)
        if not len(order):
            continue
        if order.max() >= len(positions) or order.min() < 0:
            raise ModelError("index out of range")
        if mirrored:
            order = order.reshape(-1, 3)[:, ::-1].ravel()
        points = positions[order] @ linear.T + matrix[:3, 3]
        normals = None
        if "NORMAL" in attributes:
            normals = doc.accessor(attributes["NORMAL"])[:, :3][order]
            normals = normals @ normal_matrix.T
            length = np.linalg.norm(normals, axis=1, keepdims=True)
            normals = normals / np.where(length > 0.0, length, 1.0)
        image, rgba = _material(doc, prim.get("material"))
        uv = None
        name = None
        if image is not None and "TEXCOORD_0" in attributes:
            uv = doc.accessor(attributes["TEXCOORD_0"])[:, :2][order]
            name = "gltf:{}".format(image)
            if name not in pictures:
                pictures[name] = _picture(doc, image)
        out.append(Part(points, normals, uv, name, rgba))


def _walk(doc, index, parent, out, pictures, depth=0):
    if depth > 64:
        raise ModelError("node nesting too deep")
    node = doc.item("nodes", index)
    matrix = parent @ _node_matrix(node)
    if "mesh" in node:
        _mesh(doc, doc.item("meshes", node["mesh"]), matrix, out, pictures)
    for child in node.get("children") or ():
        _walk(doc, child, matrix, out, pictures, depth + 1)


def read(data, fetch):
    """(части core.models.Part с осью Z вверх, {имя картинки: байты})
    из .gltf или .glb. fetch(uri) - байты файла рядом или None."""
    doc = _Doc(data, fetch)
    scenes = doc.list("scenes")
    if scenes:
        index = doc.json.get("scene", 0)
        if not isinstance(index, int) or not 0 <= index < len(scenes):
            index = 0
        roots = scenes[index].get("nodes") or []
    else:
        roots = list(range(len(doc.list("nodes"))))
    out = []
    pictures = {}
    try:
        for index in roots:
            _walk(doc, index, np.eye(4), out, pictures)
    except (KeyError, TypeError) as error:
        raise ModelError("bad glTF: {}".format(error)) from error
    return [from_y_up(part) for part in out], pictures
