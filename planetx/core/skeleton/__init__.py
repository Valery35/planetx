# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Лицензия GNU GPL версии 3.
"""Прямой скелет многоугольника для вальмовых крыш.

bpypolyskel (https://github.com/prochitecture/bpypolyskel, GPL-3,
коммит bd1ce5b от 13.03.2026) - Felkel-Obdržálek, порт Botffy/polyskel.
Файлы bpypolyskel.py, bpyeuclid.py, poly2FacesGraph.py взяты без
изменений, кроме одной строки импорта в bpyeuclid.py: Blender mathutils
заменён на vector.py (обычный Python). Это чужие копии, правила модуля
к ним не применяются, см. FOREIGN в tests/test_hygiene.py. Qt и numpy
модуль не знает.
"""
from .bpypolyskel import polygonize
from .vector import Vector

__all__ = ["Vector", "polygonize"]
