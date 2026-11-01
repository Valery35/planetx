# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Сцена вида в glTF 2.0 и 3D Tiles 1.1. Расчёт без Qt.

Слово автора от 1 ноября 2026 года. Объекты вида - куски Item со своим
центром в ECEF и смещениями float32, как в видеокарте, поэтому точность
на месте не теряется.

- GLB - один файл, метры от начала в точке lat, lon, ось Y вверх, как
  требует glTF, X на восток, Z на юг. Другие программы получают сцену
  на плоскости у начала, место записано в asset.extras.
- 3D Tiles - tileset.json и файл GLB на кусок. Кусок стоит в ECEF: у тайла
  сдвиг в центр, вершины - ECEF в осях glTF (x, z, -y), обратный поворот
  делает читатель 3D Tiles по gltfUpAxis Y. Корень без содержимого,
  детей рисуют все сразу (refine ADD).

У куска цвет вершин или картинка PNG с uv. Материал без блеска,
двусторонний: крыши и стены сеток вида обращены как придётся.
"""
import json
import math
import struct
from collections import namedtuple

import numpy as np

try:  # внутри плагина QGIS
    from . import ellipsoid
except ImportError:  # headless-тесты
    import ellipsoid

GENERATOR = "PlanetX"
GLB_MAGIC = 0x46546C67
JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942
FLOAT, UBYTE, UINT = 5126, 5121, 5125
ARRAY_BUFFER, ELEMENT_BUFFER = 34962, 34963
TILE_ERROR = 16.0  # м, геометрическая ошибка кусков

Item = namedtuple("Item", "center positions normals colors indices uvs "
                          "picture name")
Item.__new__.__defaults__ = (None, None, "")
Item.__doc__ = """Кусок сцены. center - центр в ECEF, positions - (n, 3)
смещения float32, normals - (n, 3) float32 или None, colors - (n, 4)
uint8 или None, indices - (m, 3) или None для списка треугольников,
uvs - (n, 2) float32 или None, picture - байты PNG или None."""


def _pad(data, fill=b"\0"):
    return data + fill * (-len(data) % 4)


class _Writer:
    """Буфер и списки accessor документа glTF."""

    def __init__(self):
        self.blob = bytearray()
        self.views = []
        self.accessors = []

    def view(self, data, target=None):
        entry = {"buffer": 0, "byteOffset": len(self.blob),
                 "byteLength": len(data)}
        if target is not None:
            entry["target"] = target
        self.views.append(entry)
        self.blob += _pad(bytes(data))
        return len(self.views) - 1

    def accessor(self, array, kind, code, bounds=False, normalized=False,
                 target=ARRAY_BUFFER):
        entry = {"bufferView": self.view(array.tobytes(), target),
                 "componentType": code, "count": len(array), "type": kind}
        if bounds:
            entry["min"] = [float(v) for v in array.min(axis=0)]
            entry["max"] = [float(v) for v in array.max(axis=0)]
        if normalized:
            entry["normalized"] = True
        self.accessors.append(entry)
        return len(self.accessors) - 1


def _flat_normals(positions, indices):
    """Нормали вершин по граням, куску без своих нормалей."""
    normals = np.zeros_like(positions, dtype=np.float64)
    faces = np.asarray(indices).reshape(-1, 3)
    cross = np.cross(positions[faces[:, 1]] - positions[faces[:, 0]],
                     positions[faces[:, 2]] - positions[faces[:, 0]])
    for column in range(3):
        np.add.at(normals, faces[:, column], cross)
    length = np.linalg.norm(normals, axis=1, keepdims=True)
    length[length == 0.0] = 1.0
    return normals / length


def _unit(normals):
    normals = np.asarray(normals, dtype=np.float64)
    length = np.linalg.norm(normals, axis=1, keepdims=True)
    length[length == 0.0] = 1.0
    return (normals / length).astype(np.float32)


def glb(parts, extras=None):
    """Байты GLB. parts - куски с готовыми в осях glTF positions float32:
    словари positions, normals, colors, indices, uvs, picture."""
    writer = _Writer()
    primitives, materials, textures, images = [], [], [], []
    for part in parts:
        positions = np.ascontiguousarray(part["positions"], dtype=np.float32)
        count = len(positions)
        if not count:
            continue
        indices = part.get("indices")
        if indices is None:
            indices = np.arange(count, dtype=np.uint32)
        indices = np.ascontiguousarray(indices, dtype=np.uint32).reshape(-1)
        normals = part.get("normals")
        if normals is None:
            normals = _flat_normals(positions, indices)
        attributes = {
            "POSITION": writer.accessor(positions, "VEC3", FLOAT, True),
            "NORMAL": writer.accessor(_unit(normals), "VEC3", FLOAT)}
        colors = part.get("colors")
        if colors is not None:
            attributes["COLOR_0"] = writer.accessor(
                np.ascontiguousarray(colors, dtype=np.uint8), "VEC4", UBYTE,
                normalized=True)
        material = {"doubleSided": True, "pbrMetallicRoughness": {
            "metallicFactor": 0.0, "roughnessFactor": 1.0}}
        if part.get("picture"):
            attributes["TEXCOORD_0"] = writer.accessor(
                np.ascontiguousarray(part["uvs"], dtype=np.float32), "VEC2",
                FLOAT)
            images.append({"bufferView": writer.view(part["picture"]),
                           "mimeType": "image/png"})
            textures.append({"source": len(images) - 1})
            material["pbrMetallicRoughness"]["baseColorTexture"] = {
                "index": len(textures) - 1}
        materials.append(material)
        primitives.append({
            "attributes": attributes, "mode": 4,
            "material": len(materials) - 1,
            "indices": writer.accessor(indices, "SCALAR", UINT,
                                       target=ELEMENT_BUFFER)})
    document = {
        "asset": {"version": "2.0", "generator": GENERATOR},
        "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": primitives}], "materials": materials,
        "buffers": [{"byteLength": len(writer.blob)}],
        "bufferViews": writer.views, "accessors": writer.accessors}
    if extras:
        document["asset"]["extras"] = extras
    if images:
        document["images"] = images
        document["textures"] = textures
    text = _pad(json.dumps(document, ensure_ascii=False,
                           separators=(",", ":")).encode("utf-8"), b" ")
    blob = bytes(writer.blob)
    length = 12 + 8 + len(text) + 8 + len(blob)
    return b"".join((struct.pack("<III", GLB_MAGIC, 2, length),
                     struct.pack("<II", len(text), JSON_CHUNK), text,
                     struct.pack("<II", len(blob), BIN_CHUNK), blob))


def _part(item, positions, normals):
    return {"positions": positions, "normals": normals,
            "colors": item.colors, "indices": item.indices,
            "uvs": item.uvs, "picture": item.picture}


def enu_axes(lat, lon):
    """Оси восток, север, вверх в точке, строками."""
    phi, lam = math.radians(lat), math.radians(lon)
    return np.array([
        (-math.sin(lam), math.cos(lam), 0.0),
        (-math.sin(phi) * math.cos(lam), -math.sin(phi) * math.sin(lam),
         math.cos(phi)),
        (math.cos(phi) * math.cos(lam), math.cos(phi) * math.sin(lam),
         math.sin(phi))])


def scene_glb(items, lat, lon, height=0.0):
    """Один файл GLB: метры от точки lat, lon, height, Y вверх."""
    origin = np.asarray(ellipsoid.geodetic_to_ecef(lat, lon, height),
                        dtype=np.float64).reshape(3)
    axes = enu_axes(lat, lon)
    parts = []
    for item in items:
        shift = axes @ (np.asarray(item.center, dtype=np.float64) - origin)
        local = np.asarray(item.positions, dtype=np.float64) @ axes.T + shift
        # Восток, вверх, на юг - правая тройка glTF.
        positions = np.stack((local[:, 0], local[:, 2], -local[:, 1]),
                             axis=1).astype(np.float32)
        normals = None
        if item.normals is not None:
            turned = np.asarray(item.normals, dtype=np.float64) @ axes.T
            normals = np.stack((turned[:, 0], turned[:, 2], -turned[:, 1]),
                               axis=1)
        parts.append(_part(item, positions, normals))
    return glb(parts, {"origin": {"lat": lat, "lon": lon, "height": height}})


def _gltf_axes(values):
    """ECEF в оси glTF: читатель 3D Tiles вернёт (x, -z, y)."""
    values = np.asarray(values, dtype=np.float32)
    return np.stack((values[:, 0], values[:, 2], -values[:, 1]), axis=1)


def tileset(items):
    """3D Tiles: (текст tileset.json, [(имя файла, байты GLB)])."""
    files, children, centers, radii = [], [], [], []
    for number, item in enumerate(items):
        if not len(item.positions):
            continue
        normals = None if item.normals is None else _gltf_axes(item.normals)
        name = "tile{}.glb".format(number + 1)
        files.append((name, glb([_part(item, _gltf_axes(item.positions),
                                       normals)])))
        radius = float(np.linalg.norm(item.positions, axis=1).max()) + 1.0
        center = [float(v) for v in item.center]
        children.append({
            "transform": [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0,
                          1.0, 0.0] + center + [1.0],
            "boundingVolume": {"sphere": [0.0, 0.0, 0.0, radius]},
            "geometricError": 0.0, "content": {"uri": name}})
        centers.append(center)
        radii.append(radius)
    if not children:
        return None, []
    middle = np.mean(np.asarray(centers), axis=0)
    reach = max(float(np.linalg.norm(np.asarray(c) - middle)) + r
                for c, r in zip(centers, radii))
    root = {"boundingVolume": {"sphere": [float(v) for v in middle]
                               + [reach]},
            "geometricError": TILE_ERROR, "refine": "ADD",
            "children": children}
    text = json.dumps({"asset": {"version": "1.1", "gltfUpAxis": "Y",
                                 "generator": GENERATOR},
                       "geometricError": TILE_ERROR, "root": root},
                      indent=1)
    return text, files
