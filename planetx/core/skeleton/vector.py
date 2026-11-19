# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Замена Blender mathutils для bpypolyskel: только то, что он зовёт.

Vector 2D/3D на обычных float (двойная точность). Сравнение по значению,
хеша нет - как у mathutils.Vector без freeze. geometry.intersect_point_line -
проекция точки на прямую, как в mathutils.geometry.
"""
import math


class Vector:
    __slots__ = ("_v",)
    __hash__ = None

    def __init__(self, seq=(0.0, 0.0)):
        self._v = [float(c) for c in seq]

    def __len__(self):
        return len(self._v)

    def __iter__(self):
        return iter(self._v)

    def __getitem__(self, i):
        return self._v[i]

    def __setitem__(self, i, value):
        self._v[i] = float(value)

    @property
    def x(self):
        return self._v[0]

    @x.setter
    def x(self, value):
        self._v[0] = float(value)

    @property
    def y(self):
        return self._v[1]

    @y.setter
    def y(self, value):
        self._v[1] = float(value)

    @property
    def z(self):
        return self._v[2]

    @z.setter
    def z(self, value):
        self._v[2] = float(value)

    @property
    def xy(self):
        return Vector(self._v[:2])

    def _same(self, other):
        if len(other) != len(self._v):
            raise ValueError("Vector: разная размерность")
        return other

    def __add__(self, other):
        return Vector([a + b for a, b in zip(self._v, self._same(other))])

    def __sub__(self, other):
        return Vector([a - b for a, b in zip(self._v, self._same(other))])

    def __iadd__(self, other):
        self._v = [a + b for a, b in zip(self._v, self._same(other))]
        return self

    def __isub__(self, other):
        self._v = [a - b for a, b in zip(self._v, self._same(other))]
        return self

    def __mul__(self, k):
        if isinstance(k, Vector):
            raise TypeError("Vector * Vector не поддержан")
        return Vector([a * k for a in self._v])

    __rmul__ = __mul__

    def __truediv__(self, k):
        return Vector([a / k for a in self._v])

    def __itruediv__(self, k):
        self._v = [a / k for a in self._v]
        return self

    def __neg__(self):
        return Vector([-a for a in self._v])

    def __eq__(self, other):
        if not isinstance(other, Vector):
            return NotImplemented
        return self._v == other._v

    def __ne__(self, other):
        r = self.__eq__(other)
        return r if r is NotImplemented else not r

    def dot(self, other):
        return sum(a * b for a, b in zip(self._v, other))

    def cross(self, other):
        a, b = self._v, list(other)
        if len(a) == 2:
            return a[0] * b[1] - a[1] * b[0]
        return Vector((a[1] * b[2] - a[2] * b[1],
                       a[2] * b[0] - a[0] * b[2],
                       a[0] * b[1] - a[1] * b[0]))

    @property
    def length_squared(self):
        return sum(a * a for a in self._v)

    @property
    def length(self):
        return math.sqrt(self.length_squared)

    magnitude = length

    def normalized(self):
        n = self.length
        if n == 0.0:
            return Vector(self._v)
        return Vector([a / n for a in self._v])

    def normalize(self):
        n = self.length
        if n != 0.0:
            self._v = [a / n for a in self._v]

    def copy(self):
        return Vector(self._v)

    def __repr__(self):
        return "Vector((%s))" % ", ".join("%.4f" % a for a in self._v)


class geometry:  # noqa: N801 - имя как в mathutils
    @staticmethod
    def intersect_point_line(pt, line_p1, line_p2):
        """Ближайшая к pt точка прямой line_p1-line_p2 и её доля вдоль неё."""
        d = line_p2 - line_p1
        dd = d.length_squared
        if dd == 0.0:
            return line_p1.copy(), 0.0
        t = (pt - line_p1).dot(d) / dd
        return line_p1 + d * t, t
