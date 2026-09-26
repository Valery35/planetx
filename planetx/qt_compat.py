# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Имена Qt, которые различаются в Qt 5 и Qt 6.

QGIS 3.40 работает на Qt 5, QGIS 4 на Qt 6. Модуль собирает различия
в одном месте, остальной код берёт имена отсюда.
"""
from qgis.PyQt import QtCore

try:  # Qt 6
    from qgis.PyQt.QtGui import QAction
except ImportError:  # Qt 5
    from qgis.PyQt.QtWidgets import QAction

# В Qt 6 виджет OpenGL вынесен в отдельный модуль, и qgis.PyQt его
# не отдаёт. Поэтому модуль берётся из PyQt6 напрямую.
try:  # Qt 6
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget
except ImportError:  # Qt 5
    from qgis.PyQt.QtWidgets import QOpenGLWidget

QT_MAJOR = int(QtCore.QT_VERSION_STR.split(".")[0])


def enum(owner, scope, name):
    """Значение перечисления для областных и плоских имён.

    ``enum(Qt, "MouseButton", "LeftButton")`` работает в Qt 5 и в Qt 6.
    """
    return getattr(getattr(owner, scope, owner), name)


def enum_int(value):
    """Целое значение перечисления. В Qt 6 это enum Python, в Qt 5 int."""
    return value.value if hasattr(value, "value") else int(value)


__all__ = ["QAction", "QOpenGLWidget", "QT_MAJOR", "enum", "enum_int"]
