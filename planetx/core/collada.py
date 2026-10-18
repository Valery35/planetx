# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Чтение моделей Collada (.dae), как в Model KML Google Earth.

Расчёт без Qt. Разбор идёт через expat в лёгкое дерево core/kml.py,
объявления сущностей DTD запрещены, как у KML.

Из файла берутся сетки треугольников (triangles, polylist, polygons -
многоугольники режутся веером), положения, нормали и первый набор
текстурных координат, материалы profile_COMMON - цвет diffuse или
картинка через sampler2D и surface, прозрачность transparency.
Узлы сцены - matrix, translate, rotate, scale в порядке записи,
instance_geometry, instance_node и вложенные узлы. Линии (lines,
linestrips) пропускаются. Единица - unit meter, ось вверх - up_axis.
Анимации library_animations - ключи преобразований узлов по sid
(целиком, .X, .Y, .Z, .ANGLE, (n)), см. core/animation.py.

Итог - core.models.Part: координаты в метрах, ось Z вверх. Модель
Google Earth лежит так, что X смотрит на восток, Y - на север.
Текстурная координата v переворачивается: в Collada начало внизу
картинки, в модуле - вверху, как у glTF.
"""
from urllib.parse import unquote

import numpy as np

try:  # внутри плагина QGIS
    from . import animation, kml
    from .models import Part, ModelError, from_y_up
except ImportError:  # headless-тесты
    import animation
    import kml
    from models import Part, ModelError, from_y_up

# Многоугольник длиннее режется веером, сетка такого размера - уже не
# модель здания: защита от файла с ошибкой в счёте вершин.
MAX_POLYGON = 4096


def _child(node, name):
    for child in node:
        if child.tag == name:
            return child
    return None


def _children(node, name):
    return [child for child in node if child.tag == name]


def _ref(text):
    """Ссылка вида #id без решётки."""
    text = (text or "").strip()
    return text[1:] if text.startswith("#") else text


def _numbers(node, kind=float):
    text = node.text if node is not None else ""
    if not text or not text.strip():
        return np.zeros(0)
    try:
        return np.array(text.split(), dtype=np.float64 if kind is float
                        else np.int64)
    except ValueError as error:
        raise ModelError("bad numbers in <{}>".format(node.tag)) from error


class _Doc:
    """Разобранный файл: узлы по id, единица и ось."""

    def __init__(self, root):
        self.root = root
        self.ids = {}
        for node in root.iter():
            ident = node.get("id")
            if ident:
                self.ids[ident] = node
        asset = _child(root, "asset")
        self.unit = 1.0
        self.y_up = False
        if asset is not None:
            unit = _child(asset, "unit")
            if unit is not None:
                try:
                    self.unit = float(unit.get("meter", "1") or 1.0)
                except ValueError:
                    self.unit = 1.0
            axis = _child(asset, "up_axis")
            if axis is not None and axis.text.strip().upper() == "Y_UP":
                self.y_up = True
        self.materials = {}

    def find(self, ref):
        return self.ids.get(_ref(ref))


def _source(doc, ref):
    """Массив (количество, шаг) источника по ссылке."""
    node = doc.find(ref)
    if node is None:
        raise ModelError("source not found: {}".format(ref))
    if node.tag == "vertices":
        found = None
        for item in _children(node, "input"):
            if item.get("semantic") == "POSITION":
                found = item.get("source")
        if found is None:
            raise ModelError("vertices without POSITION")
        return _source(doc, found)
    values = _numbers(_child(node, "float_array"))
    stride = 1
    common = _child(node, "technique_common")
    accessor = _child(common, "accessor") if common is not None else None
    if accessor is not None:
        try:
            stride = max(int(accessor.get("stride", "1") or 1), 1)
        except ValueError:
            stride = 1
        try:
            offset = int(accessor.get("offset", "0") or 0)
        except ValueError:
            offset = 0
        values = values[offset:]
    count = len(values) // stride
    return values[:count * stride].reshape(count, stride)


def _color(node):
    """RGBA 0-1 из <color> или None."""
    item = _child(node, "color") if node is not None else None
    if item is None:
        return None
    values = _numbers(item)
    if len(values) < 3:
        return None
    rgba = list(values[:4]) + [1.0] * (4 - len(values[:4]))
    return tuple(float(min(max(v, 0.0), 1.0)) for v in rgba)


def _image_path(doc, ident):
    node = doc.ids.get(ident)
    if node is None or node.tag != "image":
        return None
    init = _child(node, "init_from")
    if init is None:
        return None
    # Collada 1.5 кладёт адрес во вложенный <ref>.
    ref = _child(init, "ref")
    text = (ref.text if ref is not None else init.text).strip()
    if text.startswith("file://"):
        text = text[7:]
        if len(text) > 2 and text[0] == "/" and text[2] == ":":
            text = text[1:]
    return unquote(text.replace("\\", "/"))


def _effect(doc, effect):
    """(картинка или None, RGBA 0-1, двусторонний) эффекта."""
    profile = _child(effect, "profile_COMMON")
    if profile is None:
        return None, (0.8, 0.8, 0.8, 1.0)
    params = {p.get("sid"): p for p in _children(profile, "newparam")}
    technique = _child(profile, "technique")
    shading = None
    if technique is not None:
        for name in ("lambert", "phong", "blinn", "constant"):
            shading = _child(technique, name)
            if shading is not None:
                break
    image = None
    rgba = (0.8, 0.8, 0.8, 1.0)
    if shading is not None:
        slot = _child(shading, "diffuse") or _child(shading, "emission")
        texture = _child(slot, "texture") if slot is not None else None
        if texture is not None:
            image = _texture_image(doc, params, texture.get("texture", ""))
            rgba = (1.0, 1.0, 1.0, 1.0)
        else:
            rgba = _color(slot) or rgba
        alpha = _child(shading, "transparency")
        value = _child(alpha, "float") if alpha is not None else None
        if value is not None:
            try:
                share = float(value.text)
            except ValueError:
                share = 1.0
            # SketchUp пишет непрозрачность прямо, как A_ONE; значение
            # вне 0-1 не принимается.
            if 0.0 <= share <= 1.0:
                rgba = rgba[:3] + (rgba[3] * share,)
    return image, rgba


def _texture_image(doc, params, sid):
    """Путь картинки по sampler2D - surface - image или прямо по id."""
    seen = set()
    while sid in params and sid not in seen:
        seen.add(sid)
        param = params[sid]
        sampler = _child(param, "sampler2D")
        surface = _child(param, "surface")
        if sampler is not None:
            source = _child(sampler, "source")
            if source is not None:
                sid = source.text.strip()
                continue
            instance = _child(sampler, "instance_image")
            if instance is not None:
                return _image_path(doc, _ref(instance.get("url")))
            return None
        if surface is not None:
            init = _child(surface, "init_from")
            return _image_path(doc, init.text.strip()) \
                if init is not None else None
        return None
    return _image_path(doc, sid)


def _material(doc, ident):
    """(картинка, RGBA) материала по id, с памятью."""
    if ident in doc.materials:
        return doc.materials[ident]
    found = (None, (0.8, 0.8, 0.8, 1.0))
    node = doc.ids.get(ident)
    if node is not None and node.tag == "material":
        instance = _child(node, "instance_effect")
        effect = doc.find(instance.get("url")) if instance is not None \
            else None
        if effect is not None:
            found = _effect(doc, effect)
    doc.materials[ident] = found
    return found


def _primitive(doc, prim):
    """(положения, нормали или None, uv или None) треугольников
    примитива, по вершине на угол."""
    inputs = []
    for item in _children(prim, "input"):
        try:
            offset = int(item.get("offset", "0") or 0)
            index = int(item.get("set", "0") or 0)
        except ValueError as error:
            raise ModelError("bad input") from error
        inputs.append((item.get("semantic"), offset, index,
                       item.get("source")))
    if not inputs:
        return None
    width = max(offset for _, offset, _, _ in inputs) + 1
    corners = []  # номера углов в списке p, по треугольникам
    if prim.tag == "triangles":
        p = _numbers(_child(prim, "p"), int)
        count = len(p) // width
        rows = p[:count * width].reshape(count, width)
        rows = rows[:count // 3 * 3]
    elif prim.tag in ("polylist", "polygons"):
        if prim.tag == "polylist":
            p = _numbers(_child(prim, "p"), int)
            counts = _numbers(_child(prim, "vcount"), int)
            pieces = []
            at = 0
            for n in counts:
                n = int(n)
                pieces.append(p[at * width:(at + n) * width])
                at += n
        else:
            pieces = [_numbers(item, int) for item in _children(prim, "p")]
        for piece in pieces:
            n = len(piece) // width
            if n < 3 or n > MAX_POLYGON:
                continue
            piece = piece[:n * width].reshape(n, width)
            for k in range(1, n - 1):
                corners.extend((piece[0], piece[k], piece[k + 1]))
        rows = np.array(corners, dtype=np.int64).reshape(-1, width)
    else:
        return None
    if not len(rows):
        return None
    positions = normals = uv = None
    texcoord_set = None
    for semantic, offset, index, source in inputs:
        if semantic == "VERTEX":
            data = _source(doc, source)
            positions = data[rows[:, offset]][:, :3]
        elif semantic == "NORMAL" and normals is None:
            data = _source(doc, source)
            normals = data[rows[:, offset]][:, :3]
        elif semantic == "TEXCOORD" and (texcoord_set is None
                                         or index < texcoord_set):
            data = _source(doc, source)
            uv = data[rows[:, offset]][:, :2].copy()
            uv[:, 1] = 1.0 - uv[:, 1]
            texcoord_set = index
    if positions is None:
        raise ModelError("primitive without VERTEX")
    return positions, normals, uv


TRANSFORMS = ("matrix", "translate", "rotate", "scale")
SELECTORS = {"X": 0, "Y": 1, "Z": 2, "ANGLE": 3}


def _transform(node, change=None):
    """Матрица 4×4 узла по его преобразованиям в порядке записи.
    change(sid, значения) - значения преобразования на момент
    анимации."""
    out = np.eye(4)
    for item in node:
        tag = item.tag
        values = None
        if tag in TRANSFORMS:
            values = _numbers(item)
            sid = item.get("sid")
            if change is not None and sid:
                values = change(sid, values)
        if tag == "matrix" and len(values) == 16:
            step = values.reshape(4, 4)
        elif tag == "translate" and len(values) == 3:
            step = np.eye(4)
            step[:3, 3] = values
        elif tag == "scale" and len(values) == 3:
            step = np.diag([values[0], values[1], values[2], 1.0])
        elif tag == "rotate" and len(values) == 4:
            step = _rotation(values[:3], values[3])
        else:
            continue
        out = out @ step
    return out


def _rotation(axis, degrees):
    axis = np.asarray(axis, dtype=np.float64)
    length = np.linalg.norm(axis)
    out = np.eye(4)
    if length == 0.0:
        return out
    x, y, z = axis / length
    a = np.radians(degrees)
    c, s = np.cos(a), np.sin(a)
    t = 1.0 - c
    out[:3, :3] = [[t * x * x + c, t * x * y - s * z, t * x * z + s * y],
                   [t * x * y + s * z, t * y * y + c, t * y * z - s * x],
                   [t * x * z - s * y, t * y * z + s * x, t * z * z + c]]
    return out


def _bindings(instance):
    """Символ материала - id материала из bind_material."""
    out = {}
    bind = _child(instance, "bind_material")
    common = _child(bind, "technique_common") if bind is not None else None
    if common is not None:
        for item in _children(common, "instance_material"):
            out[item.get("symbol", "")] = _ref(item.get("target"))
    return out


class _Tracks:
    """Дорожки анимации при обходе сцены: moving - id узлов с ключами."""

    def __init__(self, moving):
        self.moving = moving
        self.chains = {}
        self.rest = {}


def _walk(doc, node, matrix, out, tracks=None, chain=(), depth=0):
    if depth > 64:
        raise ModelError("node nesting too deep")
    matrix = matrix @ _transform(node)
    chain = chain + (node,)
    for item in node:
        if item.tag == "instance_geometry":
            geometry = doc.find(item.get("url"))
            if geometry is not None:
                start = len(out)
                _geometry(doc, geometry, matrix, _bindings(item), out)
                if tracks is not None and len(out) > start and any(
                        n.get("id") in tracks.moving for n in chain):
                    track = len(tracks.chains)
                    tracks.chains[track] = list(chain)
                    tracks.rest[track] = np.linalg.inv(matrix)
                    for part in out[start:]:
                        part.track = track
        elif item.tag == "instance_node":
            target = doc.find(item.get("url"))
            if target is not None:
                _walk(doc, target, matrix, out, tracks, chain, depth + 1)
        elif item.tag == "node":
            _walk(doc, item, matrix, out, tracks, chain, depth + 1)


def _target(text):
    """(id узла, sid, номер значения или None) из target канала."""
    path, _, sid = (text or "").partition("/")
    index = None
    if "." in sid:
        sid, _, name = sid.partition(".")
        index = SELECTORS.get(name.upper())
        if index is None:
            return None
    elif "(" in sid:
        sid, _, rest = sid.partition("(")
        numbers = [int(v) for v in rest.replace(")", " ").replace(
            "(", " ").split() if v.isdigit()]
        if not numbers:
            return None
        index = numbers[0] * 4 + numbers[1] if len(numbers) > 1 \
            else numbers[0]
    return (path, sid, index) if path and sid else None


def _keys(doc):
    """{(id узла, sid): [(номер, времена, значения, способ)]} всех
    каналов library_animations."""
    out = {}
    for channel in doc.root.iter():
        if channel.tag != "channel":
            continue
        target = _target(channel.get("target"))
        sampler = doc.find(channel.get("source"))
        if target is None or sampler is None:
            continue
        inputs = {item.get("semantic"): item.get("source")
                  for item in _children(sampler, "input")}
        if "INPUT" not in inputs or "OUTPUT" not in inputs:
            continue
        times = _source(doc, inputs["INPUT"])[:, 0]
        values = _source(doc, inputs["OUTPUT"])
        if not len(times) or len(values) != len(times):
            continue
        mode = animation.LINEAR
        if "INTERPOLATION" in inputs:
            node = doc.find(inputs["INTERPOLATION"])
            names = _child(node, "Name_array") if node is not None else None
            if names is not None and names.text \
                    and names.text.split()[0] == "STEP":
                mode = animation.STEP
        path, sid, index = target
        out.setdefault((path, sid), []).append((index, times, values, mode))
    return out


def _animation(doc, keys, tracks):
    if not tracks.chains:
        return None
    duration = max(float(times[-1]) for items in keys.values()
                   for _, times, _, _ in items)

    def local(node, t):
        ident = node.get("id")

        def change(sid, values):
            items = keys.get((ident, sid))
            if not items:
                return values
            values = values.copy()
            for index, times, keyed, mode in items:
                found = animation.sample(times, keyed, t, mode)
                if index is None:
                    if len(found) == len(values):
                        values = found
                elif index < len(values) and len(found):
                    values[index] = found[0]
            return values
        return _transform(node, change)
    return animation.Animation(duration, local, tracks.chains, tracks.rest,
                               animation.scaled_convert(doc.unit, doc.y_up))


def _geometry(doc, geometry, matrix, bindings, out):
    mesh = _child(geometry, "mesh")
    if mesh is None:
        return
    linear = matrix[:3, :3]
    # Нормали - обратной транспонированной, у зеркального узла
    # она та же, что у прямого, порядок углов разворачивается ниже.
    try:
        normal_matrix = np.linalg.inv(linear).T
    except np.linalg.LinAlgError:
        return
    mirrored = np.linalg.det(linear) < 0.0
    for prim in mesh:
        if prim.tag not in ("triangles", "polylist", "polygons"):
            continue
        found = _primitive(doc, prim)
        if found is None:
            continue
        positions, normals, uv = found
        positions = positions @ linear.T + matrix[:3, 3]
        if normals is not None:
            normals = normals @ normal_matrix.T
            length = np.linalg.norm(normals, axis=1, keepdims=True)
            normals = normals / np.where(length > 0.0, length, 1.0)
        if mirrored:
            order = np.arange(len(positions)).reshape(-1, 3)[:, ::-1]
            order = order.ravel()
            positions = positions[order]
            normals = normals[order] if normals is not None else None
            uv = uv[order] if uv is not None else None
        symbol = prim.get("material", "")
        image, rgba = _material(doc, bindings.get(symbol, symbol))
        out.append(Part(positions, normals, uv if image else None,
                        image, rgba))


def read_dae(data):
    """Части модели из байтов .dae: список core.models.Part, метры,
    ось Z вверх."""
    return read_dae_animated(data)[0]


def read_dae_animated(data):
    """(части, как у read_dae, анимация core.animation.Animation или
    None)."""
    try:
        root = kml._parse(data)
    except kml.KmlError as error:
        raise ModelError(str(error)) from error
    if root.tag != "COLLADA":
        raise ModelError("not COLLADA")
    doc = _Doc(root)
    out = []
    scene = _child(root, "scene")
    instance = _child(scene, "instance_visual_scene") \
        if scene is not None else None
    visual = doc.find(instance.get("url")) if instance is not None else None
    if visual is None:
        library = _child(root, "library_visual_scenes")
        scenes = _children(library, "visual_scene") \
            if library is not None else []
        visual = scenes[0] if scenes else None
    if visual is None:
        raise ModelError("no visual scene")
    try:
        keys = _keys(doc)
        tracks = _Tracks({path for path, _ in keys})
        for node in _children(visual, "node"):
            _walk(doc, node, np.eye(4), out, tracks)
        moving = _animation(doc, keys, tracks)
    except (IndexError, ValueError) as error:
        raise ModelError("bad COLLADA: {}".format(error)) from error
    for part in out:
        part.positions = part.positions * doc.unit
    if doc.y_up:
        out = [from_y_up(part) for part in out]
    return out, moving


def images(data):
    """Пути картинок файла .dae, как записаны в library_images."""
    try:
        root = kml._parse(data)
    except kml.KmlError as error:
        raise ModelError(str(error)) from error
    doc = _Doc(root)
    out = []
    for node in root.iter():
        if node.tag == "image":
            path = _image_path(doc, node.get("id"))
            if path and path not in out:
                out.append(path)
    return out
