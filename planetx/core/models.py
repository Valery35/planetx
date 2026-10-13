# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""3D-модели на глобусе, как Model в KML Google Earth. Просьба автора
от 13 октября 2026 года.

Расчёт без Qt. Модель - файл Collada (.dae, core/collada.py), glTF
(.gltf, .glb, core/gltf.py) или OBJ (.obj, core/obj.py) с картинками.
Файлы модели хранятся одним пакетом - архивом ZIP с главным файлом,
картинками и записью planetx.json (главный файл и замены путей
ResourceMap KML).

Место - как Location, Orientation и Scale KML. Точка (широта,
долгота, высота), азимут heading по часовой стрелке от севера вокруг
оси вверх, наклон tilt вокруг оси X и крен roll вокруг оси Y против
часовой стрелки, масштаб по трём осям. Ось X модели смотрит на
восток, Y - на север, Z - вверх. Высота - по altitudeMode:
clampToGround - на рельефе, relativeToGround - над рельефом,
absolute - над уровнем моря.

Вершины в видеокарту идут смещением от точки модели в ECEF, float32
хватает: модель здания - сотни метров.
"""
import io
import json
import math
import os
import posixpath
import zipfile
from urllib.parse import unquote

import numpy as np

try:  # внутри плагина QGIS
    from . import ellipsoid
    from .camera import enu
except ImportError:  # headless-тесты
    import ellipsoid
    from camera import enu

MODES = ("clampToGround", "relativeToGround", "absolute")
EXTENSIONS = (".dae", ".gltf", ".glb", ".obj")
PACKAGE_NOTE = "planetx.json"
# Вершин в одной модели не больше - иначе модель не грузится. Модель
# здания SketchUp - десятки тысяч, сетка съёмки с дрона - миллионы.
MAX_VERTICES = 3000000
GRAY = (0.8, 0.8, 0.8, 1.0)
MODEL_VERTEX = np.dtype([("position", np.float32, 3),
                         ("normal", np.float32, 3),
                         ("uv", np.float32, 2)])


class ModelError(ValueError):
    """Файл модели не читается."""


class Part:
    """Часть модели одного материала: треугольники вершинами подряд.

    positions - (N, 3) метры, N кратно 3. normals - (N, 3) или None,
    uv - (N, 2), v от верха картинки, или None. image - путь картинки
    в пакете или None, rgba - цвет 0-1, у картинки - множитель."""

    def __init__(self, positions, normals, uv, image, rgba):
        self.positions = np.asarray(positions, dtype=np.float64)
        self.normals = None if normals is None \
            else np.asarray(normals, dtype=np.float64)
        self.uv = None if uv is None else np.asarray(uv, dtype=np.float64)
        self.image = image
        self.rgba = tuple(float(v) for v in rgba)


def from_y_up(part):
    """Часть с осью Y вверх (glTF, Collada Y_UP) в ось Z вверх: передняя
    сторона +Z смотрит на юг."""
    def turn(values):
        if values is None:
            return None
        return np.stack([values[:, 0], -values[:, 2], values[:, 1]],
                        axis=1)
    return Part(turn(part.positions), turn(part.normals), part.uv,
                part.image, part.rgba)


def flat_normals(positions):
    """Нормали граней по вершинам подряд."""
    tri = positions.reshape(-1, 3, 3)
    normal = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(normal, axis=1, keepdims=True)
    normal = normal / np.where(length > 0.0, length, 1.0)
    return np.repeat(normal, 3, axis=0)


def merge(parts):
    """Части одного материала - вместе, без нормалей - с нормалями
    граней. Пустые части пропускаются. Вершин больше MAX_VERTICES -
    ModelError."""
    groups = {}
    for part in parts:
        if len(part.positions) < 3:
            continue
        count = len(part.positions) // 3 * 3
        positions = part.positions[:count]
        if not np.all(np.isfinite(positions)):
            continue
        normals = part.normals[:count] if part.normals is not None \
            else flat_normals(positions)
        uv = part.uv[:count] if part.uv is not None and part.image \
            else np.zeros((count, 2))
        key = (part.image if part.uv is not None else None, part.rgba)
        groups.setdefault(key, []).append((positions, normals, uv))
    out = []
    total = 0
    for (image, rgba), items in groups.items():
        positions = np.concatenate([p for p, _, _ in items])
        total += len(positions)
        out.append(Part(positions, np.concatenate([n for _, n, _ in items]),
                        np.concatenate([u for _, _, u in items]),
                        image, rgba))
    if total > MAX_VERTICES:
        raise ModelError("too many vertices: {}".format(total))
    if not out:
        raise ModelError("no triangles")
    return out


def bounds(parts):
    """Наименьшие и наибольшие координаты модели, (2, 3)."""
    allp = np.concatenate([p.positions for p in parts])
    return np.stack([allp.min(axis=0), allp.max(axis=0)])


def rotation(heading, tilt, roll):
    """Поворот модели в местных осях восток, север, вверх, как
    Orientation KML."""
    h, t, r = (math.radians(v) for v in (heading, tilt, roll))
    ch, sh = math.cos(h), math.sin(h)
    ct, st = math.cos(t), math.sin(t)
    cr, sr = math.cos(r), math.sin(r)
    # Азимут - по часовой стрелке, если смотреть сверху.
    rz = np.array([[ch, sh, 0.0], [-sh, ch, 0.0], [0.0, 0.0, 1.0]])
    rx = np.array([[1.0, 0.0, 0.0], [0.0, ct, -st], [0.0, st, ct]])
    ry = np.array([[cr, 0.0, sr], [0.0, 1.0, 0.0], [-sr, 0.0, cr]])
    return rz @ rx @ ry


def frame(lat, lon, heading=0.0, tilt=0.0, roll=0.0,
          scale=(1.0, 1.0, 1.0)):
    """Матрица 3×3 из координат модели в смещение ECEF от точки модели.
    """
    return enu(lat, lon).T @ rotation(heading, tilt, roll) \
        @ np.diag([float(v) for v in scale])


def vertices(parts, lat, lon, heading=0.0, tilt=0.0, roll=0.0,
             scale=(1.0, 1.0, 1.0)):
    """Вершины частей для видеокарты: список массивов MODEL_VERTEX,
    положения - смещение ECEF от точки модели."""
    matrix = frame(lat, lon, heading, tilt, roll, scale)
    try:
        normal_matrix = np.linalg.inv(matrix).T
    except np.linalg.LinAlgError:
        normal_matrix = matrix
    mirrored = np.linalg.det(matrix) < 0.0
    out = []
    for part in parts:
        array = np.zeros(len(part.positions), dtype=MODEL_VERTEX)
        array["position"] = part.positions @ matrix.T
        normals = part.normals @ normal_matrix.T
        length = np.linalg.norm(normals, axis=1, keepdims=True)
        array["normal"] = normals / np.where(length > 0.0, length, 1.0)
        array["uv"] = part.uv
        if mirrored:
            array = array.reshape(-1, 3)[:, ::-1].ravel()
        out.append(array)
    return out


def anchor(lat, lon, mode, alt, ground, scale=1.0):
    """Точка модели в ECEF. ground - высота рельефа под точкой на
    экране, scale - масштаб рельефа вида. Высота над уровнем моря
    absolute растягивается вместе с рельефом, подъём над рельефом
    relativeToGround - нет."""
    if mode == "absolute":
        height = alt * scale
    elif mode == "relativeToGround":
        height = ground + alt
    else:
        height = ground
    return np.asarray(ellipsoid.geodetic_to_ecef(lat, lon, height),
                      dtype=np.float64)


def radius(parts, scale=(1.0, 1.0, 1.0)):
    """Радиус шара вокруг точки модели, метры."""
    box = bounds(parts) * np.asarray(scale, dtype=np.float64)
    return float(np.max(np.linalg.norm(box, axis=1)))


# Пакет файлов модели.

def _clean(path):
    path = path.replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return posixpath.normpath(path).lstrip("/") if path else path


def pack(main, files, aliases=None):
    """Пакет модели: архив ZIP. main - путь главного файла, files -
    {путь: байты}, aliases - {путь в модели: путь в пакете}."""
    buffer = io.BytesIO()
    note = {"main": _clean(main)}
    if aliases:
        note["aliases"] = {k: _clean(v) for k, v in aliases.items()}
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(PACKAGE_NOTE, json.dumps(note).encode("utf-8"))
        for path, data in files.items():
            archive.writestr(_clean(path), data)
    return buffer.getvalue()


def unpack(data):
    """(главный файл, {путь: байты}, замены) из пакета."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            note = {}
            if PACKAGE_NOTE in archive.namelist():
                try:
                    note = json.loads(archive.read(PACKAGE_NOTE))
                except ValueError:
                    note = {}
            files = {name: archive.read(name)
                     for name in archive.namelist()
                     if name != PACKAGE_NOTE and not name.endswith("/")}
    except zipfile.BadZipFile as error:
        raise ModelError(str(error)) from error
    main = note.get("main") if isinstance(note, dict) else None
    if main not in files:
        main = next((n for n in files
                     if n.lower().endswith(EXTENSIONS)), None)
    if main is None:
        raise ModelError("no model file in package")
    aliases = note.get("aliases") if isinstance(note, dict) else None
    return main, files, aliases if isinstance(aliases, dict) else {}


def resolve(files, main, ref, aliases=None):
    """Путь в пакете для ссылки ref из главного файла или None."""
    if not ref:
        return None
    ref = ref.replace("\\", "/")
    if aliases and ref in aliases and aliases[ref] in files:
        return aliases[ref]
    base = posixpath.dirname(main)
    lower = {name.lower(): name for name in files}
    for path in (_clean(posixpath.join(base, ref)), _clean(ref)):
        if path in files:
            return path
        if path.lower() in lower:
            return lower[path.lower()]
    # Картинка с тем же именем в любой папке пакета.
    name = posixpath.basename(ref).lower()
    found = [n for n in files if posixpath.basename(n).lower() == name]
    return found[0] if len(found) == 1 else None


def refs(main, data, fetch=None):
    """Ссылки главного файла модели на другие файлы: картинки Collada,
    буферы и картинки glTF, кроме data:, файлы MTL и их картинки у OBJ.
    fetch(путь) - байты файла рядом, нужен OBJ для чтения MTL."""
    try:
        from . import collada, gltf, obj
    except ImportError:  # headless-тесты
        import collada
        import gltf
        import obj
    if main.lower().endswith(".dae"):
        return collada.images(data)
    if main.lower().endswith(".obj"):
        return obj.refs(data, fetch or (lambda ref: None))
    if data[:4] == gltf.GLB_MAGIC:
        text, _ = gltf.split_glb(data)
    else:
        text = data
    try:
        doc = json.loads(text)
    except ValueError as error:
        raise ModelError("bad glTF JSON") from error
    out = []
    for name in ("buffers", "images"):
        items = doc.get(name) if isinstance(doc, dict) else None
        for item in items if isinstance(items, list) else ():
            uri = item.get("uri") if isinstance(item, dict) else None
            if isinstance(uri, str) and uri and not uri.startswith("data:"):
                out.append(unquote(uri))
    return out


def collect(main, data, fetch, aliases=None):
    """Пакет модели из главного файла и файлов по его ссылкам.

    main - имя главного файла, data - его байты, fetch(путь) - байты
    файла по пути от папки главного файла или None. aliases - замены
    путей ResourceMap KML {путь в модели: путь файла}. Файл по ссылке
    с «..» ложится в папку files пакета под заменой пути. Ненайденные
    файлы пропускаются, часть остаётся цветом материала."""
    name = posixpath.basename(main.replace("\\", "/")) or "model.dae"
    files = {name: data}
    new_aliases = {}
    def near(ref):
        return fetch((aliases or {}).get(ref, ref))
    for n, ref in enumerate(refs(name, data, near)):
        target = (aliases or {}).get(ref, ref)
        found = fetch(target)
        if found is None:
            continue
        path = _clean(ref)
        if not path or path.startswith("..") or path in files:
            path = "files/{}_{}".format(n, posixpath.basename(path)
                                        or "file")
            new_aliases[ref] = path
        files[path] = found
    return pack(name, files, new_aliases)


def package_file(path, aliases=None):
    """Пакет модели из файла .dae, .gltf, .glb или .obj на диске
    с файлами рядом по его ссылкам, или None, если файл не читается."""
    folder = os.path.dirname(path)

    def fetch(ref):
        target = os.path.normpath(os.path.join(folder, *ref.split("/")))
        try:
            with open(target, "rb") as stream:
                return stream.read()
        except OSError:
            return None
    if not path.lower().endswith(EXTENSIONS):
        return None
    try:
        with open(path, "rb") as stream:
            data = stream.read()
        return collect(os.path.basename(path), data, fetch, aliases)
    except (OSError, ModelError):
        return None


def read(data):
    """Части модели из пакета: (части после merge, {путь картинки:
    байты}). Пути картинок частей - пути в пакете, ненайденная
    картинка - часть без картинки, белым цветом материала."""
    try:
        from . import collada, gltf, obj
    except ImportError:  # headless-тесты
        import collada
        import gltf
        import obj
    main, files, aliases = unpack(data)

    def near(ref):
        return files.get(resolve(files, main, ref, aliases))
    kind = main.lower().rsplit(".", 1)[-1]
    if kind in ("dae", "obj"):
        parts = collada.read_dae(files[main]) if kind == "dae" \
            else obj.read(files[main], near)
        pictures = {}
        for part in parts:
            if part.image is None:
                continue
            found = resolve(files, main, part.image, aliases)
            part.image = found
            if found is None:
                part.uv = None
            else:
                pictures[found] = files[found]
    else:
        parts, pictures = gltf.read(files[main], near)
    return merge(parts), pictures
