# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Анимация узлов 3D-моделей glTF и Collada. Просьба автора
от 18 октября 2026 года - «анимацию по тому, что есть, делай».

Расчёт без Qt. Анимация - ключи положения, поворота и масштаба узлов
сцены (glTF animations, Collada library_animations). Скиннинг
и морфинг не читаются: сетка со скелетом стоит в позе привязки.

Часть модели, у которой движется свой узел или узел выше по дереву,
получает дорожку - номер вхождения сетки в сцену (core.models.Part.
track). Дорожка помнит цепочку узлов от корня до сетки. На момент t
матрица дорожки - W(t) · W⁻¹, где W(t) - произведение местных матриц
цепочки на момент, W - то же в покое, в покое вершины части уже стоят.
Итог переводится в оси модели модуля (метры, ось Z вверх) матрицей
convert: D' = C · D · C⁻¹.
"""
import numpy as np

LINEAR, STEP, CUBIC = "LINEAR", "STEP", "CUBICSPLINE"


def sample(times, values, t, mode=LINEAR):
    """Значение ключей на момент t, вектор. times - (K,) по возрастанию,
    values - (K, n), у CUBICSPLINE (3K, n): касательная входа,
    значение, касательная выхода. До первого ключа - первое значение,
    после последнего - последнее."""
    times = np.asarray(times, dtype=np.float64)
    values = np.asarray(values, dtype=np.float64)
    cubic = mode == CUBIC and len(values) == 3 * len(times)
    keys = values[1::3] if cubic else values
    if len(times) == 0:
        return None
    if t <= times[0] or len(times) == 1:
        return keys[0].copy()
    if t >= times[-1]:
        return keys[-1].copy()
    i = int(np.searchsorted(times, t, side="right")) - 1
    span = times[i + 1] - times[i]
    s = (t - times[i]) / span if span > 0.0 else 0.0
    if mode == STEP:
        return keys[i].copy()
    if cubic:
        p0, p1 = values[3 * i + 1], values[3 * (i + 1) + 1]
        m0 = values[3 * i + 2] * span
        m1 = values[3 * (i + 1)] * span
        s2, s3 = s * s, s * s * s
        return ((2 * s3 - 3 * s2 + 1) * p0 + (s3 - 2 * s2 + s) * m0
                + (-2 * s3 + 3 * s2) * p1 + (s3 - s2) * m1)
    return keys[i] + (keys[i + 1] - keys[i]) * s


def slerp(a, b, s):
    """Сферическая интерполяция кватернионов (x, y, z, w)."""
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    dot = float(np.dot(a, b))
    if dot < 0.0:
        b, dot = -b, -dot
    if dot > 0.9995:
        out = a + (b - a) * s
    else:
        angle = np.arccos(min(dot, 1.0))
        out = (np.sin((1.0 - s) * angle) * a
               + np.sin(s * angle) * b) / np.sin(angle)
    length = np.linalg.norm(out)
    return out / length if length > 0.0 else np.array([0.0, 0.0, 0.0, 1.0])


def sample_rotation(times, values, t, mode=LINEAR):
    """Кватернион ключей на момент t: LINEAR - по дуге, прочие - как
    sample с нормировкой."""
    times = np.asarray(times, dtype=np.float64)
    values = np.asarray(values, dtype=np.float64)
    if mode != LINEAR or len(times) < 2 or t <= times[0] \
            or t >= times[-1]:
        out = sample(times, values, t, mode)
        if out is None:
            return None
        length = np.linalg.norm(out)
        return out / length if length > 0.0 else out
    i = int(np.searchsorted(times, t, side="right")) - 1
    span = times[i + 1] - times[i]
    s = (t - times[i]) / span if span > 0.0 else 0.0
    return slerp(values[i], values[i + 1], s)


def quaternion_matrix(q):
    """Матрица 3×3 поворота кватерниона (x, y, z, w)."""
    x, y, z, w = (float(v) for v in q)
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def trs(translation, rotation, scale):
    """Матрица 4×4 из сдвига, кватерниона и масштаба, как узел glTF."""
    out = np.eye(4)
    out[:3, :3] = quaternion_matrix(rotation) @ np.diag(
        [float(v) for v in scale])
    out[:3, 3] = [float(v) for v in translation]
    return out


class Animation:
    """Анимация модели: длительность и матрицы дорожек на момент.

    local(узел, t) - местная матрица узла 4×4 на момент, chains -
    {дорожка: [узлы от корня до сетки]}, rest - {дорожка: W⁻¹ в покое},
    convert - матрица 4×4 из осей файла в оси модели модуля."""

    def __init__(self, duration, local, chains, rest, convert=None):
        self.duration = float(duration)
        self.local = local
        self.chains = chains
        self.rest = rest
        self.convert = np.eye(4) if convert is None \
            else np.asarray(convert, dtype=np.float64)
        self.back = np.linalg.inv(self.convert)

    @property
    def tracks(self):
        return sorted(self.chains)

    def deltas(self, t):
        """{дорожка: матрица 4×4 в осях модели} на момент t секунд
        от начала, время идёт по кругу длительности."""
        if self.duration > 0.0:
            t = float(t) % self.duration
        out = {}
        for track, chain in self.chains.items():
            world = np.eye(4)
            for node in chain:
                world = world @ self.local(node, t)
            out[track] = self.convert @ world @ self.rest[track] \
                @ self.back
        return out


def scaled_convert(unit, y_up):
    """Матрица из осей файла в оси модели: единица в метры и, у файла
    с осью Y вверх, поворот как core.models.from_y_up."""
    out = np.diag([unit, unit, unit, 1.0])
    if y_up:
        turn = np.array([[1.0, 0.0, 0.0, 0.0], [0.0, 0.0, -1.0, 0.0],
                         [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0]])
        out = turn @ out
    return out


def frame_delta(frame, delta):
    """(линейная часть 3×3, сдвиг) матрицы дорожки в смещениях ECEF
    от точки модели. frame - матрица core.models.frame."""
    frame = np.asarray(frame, dtype=np.float64)
    back = np.linalg.inv(frame)
    return frame @ delta[:3, :3] @ back, frame @ delta[:3, 3]
