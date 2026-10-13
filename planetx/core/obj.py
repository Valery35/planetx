# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Чтение моделей Wavefront OBJ с материалами MTL.

Расчёт без Qt. Из файла берутся вершины v, текстурные координаты vt,
нормали vn и грани f - многоугольник режется веером, номера бывают
и отрицательными, от конца списка. Материал - usemtl, из файлов
mtllib берутся цвет Kd, непрозрачность d или Tr и картинка map_Kd.
Прочие строки (линии l, точки p, группы) пропускаются.

Единицы в OBJ не записаны, считаются метрами. Ось вверх тоже не
записана. Blender и большинство программ пишут ось Y вверх, как
glTF, - так модуль файл и читает (core.models.from_y_up). Модель с осью
Z вверх встаёт на бок, её ставит поле «Наклон» окна свойств, 90°.
Текстурная координата v переворачивается: в OBJ начало внизу картинки.
"""
import numpy as np

try:  # внутри плагина QGIS
    from .models import GRAY, ModelError, Part, from_y_up
except ImportError:  # headless-тесты
    from models import GRAY, ModelError, Part, from_y_up

# Многоугольник длиннее режется не так: защита от испорченной строки.
MAX_POLYGON = 4096


def _text(data):
    if isinstance(data, bytes):
        return data.decode("utf-8", "replace")
    return data


def _rest(line):
    """Остаток строки после слова: имя файла может быть с пробелами."""
    parts = line.split(None, 1)
    return parts[1].strip() if len(parts) > 1 else ""


def _texture_name(rest):
    """Имя картинки map_Kd без ключей вида -s 1 1 1."""
    words = rest.split()
    out = []
    skip = 0
    for word in words:
        if skip:
            skip -= 1
            continue
        if word.startswith("-") and not out:
            # -s, -o, -t берут три числа, -bm, -mm и прочие - одно-два.
            skip = 3 if word in ("-s", "-o", "-t") else (
                2 if word == "-mm" else 1)
            continue
        out.append(word)
    return " ".join(out).replace("\\", "/")


def _floats(text, count):
    """Первые count чисел строки или None, если их нет или запись
    неверна - такая строка MTL пропускается."""
    words = text.split()[:count]
    if len(words) < count:
        return None
    try:
        return [float(word) for word in words]
    except ValueError:
        return None


def read_mtl(data):
    """Материалы файла MTL: {имя: (картинка или None, RGBA 0-1)}."""
    out = {}
    name = None
    color = [0.8, 0.8, 0.8]
    alpha = 1.0
    image = None

    def close():
        if name is not None:
            out[name] = (image, tuple(color) + (alpha,))
    for raw in _text(data).splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key = line.split(None, 1)[0]
        rest = _rest(line)
        if key == "newmtl":
            close()
            name, color, alpha, image = rest, [0.8, 0.8, 0.8], 1.0, None
        elif key == "Kd":
            values = _floats(rest, 3)
            if values is not None:
                color = [min(max(v, 0.0), 1.0) for v in values]
        elif key in ("d", "Tr"):
            values = _floats(rest, 1)
            if values is not None:
                value = min(max(values[0], 0.0), 1.0)
                alpha = value if key == "d" else 1.0 - value
        elif key == "map_Kd":
            image = _texture_name(rest) or None
    close()
    return out


def libraries(data):
    """Имена файлов mtllib."""
    out = []
    for raw in _text(data).splitlines():
        line = raw.strip()
        if line.startswith("mtllib"):
            name = _rest(line).replace("\\", "/")
            if name and name not in out:
                out.append(name)
    return out


def refs(data, fetch):
    """Файлы, на которые ссылается OBJ: файлы MTL и их картинки.
    fetch(путь) - байты файла рядом или None."""
    out = []
    for name in libraries(data):
        out.append(name)
        found = fetch(name)
        if found is None:
            continue
        for image, _ in read_mtl(found).values():
            if image and image not in out:
                out.append(image)
    return out


def _index(text, count):
    """Номер из записи грани: от 1, отрицательный - от конца."""
    if not text:
        return None
    value = int(text)
    if value < 0:
        value += count
    else:
        value -= 1
    if not 0 <= value < count:
        raise ModelError("face index out of range")
    return value


def read(data, fetch):
    """Части core.models.Part с осью Z вверх из OBJ. fetch(путь) -
    байты файла MTL рядом или None. Пути картинок частей - как
    в MTL."""
    materials = {}
    for name in libraries(data):
        found = fetch(name)
        if found is not None:
            materials.update(read_mtl(found))
    positions, texcoords, normals = [], [], []
    groups = {}  # материал - [(номера v, vt, vn) углов]
    current = None
    for number, raw in enumerate(_text(data).splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key = line.split(None, 1)[0]
        try:
            if key == "v":
                positions.append([float(v) for v in line.split()[1:4]])
            elif key == "vt":
                values = [float(v) for v in line.split()[1:3]]
                texcoords.append(values + [0.0] * (2 - len(values)))
            elif key == "vn":
                normals.append([float(v) for v in line.split()[1:4]])
            elif key == "usemtl":
                current = _rest(line)
            elif key == "f":
                corners = []
                for word in line.split()[1:]:
                    items = word.split("/")
                    items += [""] * (3 - len(items))
                    corners.append((
                        _index(items[0], len(positions)),
                        _index(items[1], len(texcoords)),
                        _index(items[2], len(normals))))
                if len(corners) < 3 or len(corners) > MAX_POLYGON:
                    continue
                target = groups.setdefault(current, [])
                for k in range(1, len(corners) - 1):
                    target.extend((corners[0], corners[k], corners[k + 1]))
        except ValueError as error:
            raise ModelError("bad OBJ line {}: {}".format(number, error)) \
                from error
    if any(len(p) != 3 for p in positions) \
            or any(len(n) != 3 for n in normals):
        raise ModelError("bad OBJ vertex")
    v = np.asarray(positions, dtype=np.float64).reshape(-1, 3)
    vt = np.asarray(texcoords, dtype=np.float64).reshape(-1, 2)
    vn = np.asarray(normals, dtype=np.float64).reshape(-1, 3)
    out = []
    for name, corners in groups.items():
        image, rgba = materials.get(name, (None, GRAY))
        pos = v[[c[0] for c in corners]]
        has_uv = all(c[1] is not None for c in corners)
        has_n = all(c[2] is not None for c in corners)
        uv = None
        if image and has_uv:
            uv = vt[[c[1] for c in corners]].copy()
            uv[:, 1] = 1.0 - uv[:, 1]
        nrm = vn[[c[2] for c in corners]] if has_n else None
        out.append(from_y_up(Part(pos, nrm, uv, image if uv is not None
                                  else None, rgba)))
    return out
