# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Литологическая карта мира GLiM (Hartmann, Moosdorf 2012).

Global Lithological Map Database v1.0, 1 235 259 многоугольников
в масштабе около 1:3 750 000, первый уровень классификации - 16 классов
поля xx. Тайлы Web Mercator уровней 0-MAX_LEVEL собирает
tools/build_glim.py в planetx-terrain/glim: PNG с цветом класса, вода
и «нет данных» прозрачны, пустые тайлы тоже пишутся. Класс под щелчком -
по цвету пикселя тайла (class_of).

Цвета классов - выбор помощника, утверждает автор.

Модуль Qt не знает.
"""
import numpy as np

FOLDER = "glim"
MAX_LEVEL = 7  # около 1.2 км на пиксель у экватора, масштаб карты 1:3.75 млн
OPACITY = 0.75
ATTRIBUTION = ("Lithology: GLiM, Hartmann & Moosdorf 2012, CC BY 3.0",
               "https://doi.org/10.1594/PANGAEA.788537")

# Код поля xx, номер в растре сборки и цвет. Номер 0 - пусто.
CLASSES = (
    ("su", 1, (238, 228, 150)),  # рыхлые отложения
    ("ss", 2, (236, 186, 110)),  # обломочные осадочные
    ("sm", 3, (205, 165, 120)),  # смешанные осадочные
    ("sc", 4, (110, 180, 225)),  # карбонатные осадочные
    ("ev", 5, (225, 120, 200)),  # эвапориты
    ("py", 6, (250, 150, 95)),  # пирокластика
    ("va", 7, (232, 80, 72)),  # кислые вулканические
    ("vi", 8, (198, 96, 140)),  # средние вулканические
    ("vb", 9, (150, 52, 52)),  # основные вулканические
    ("pa", 10, (250, 165, 185)),  # кислые плутонические
    ("pi", 11, (205, 125, 175)),  # средние плутонические
    ("pb", 12, (130, 80, 135)),  # основные плутонические
    ("mt", 13, (140, 170, 100)),  # метаморфические
    ("ig", 14, (232, 242, 252)),  # лёд и ледники
    ("wb", 15, None),  # водоёмы - прозрачно
    ("nd", 16, None),  # нет данных - прозрачно
)
CODES = {code: number for code, number, _ in CLASSES}


def palette():
    """Цвета по номеру класса растра сборки: массив (17, 4) uint8,
    альфа 0 у пустого, воды и «нет данных»."""
    table = np.zeros((len(CLASSES) + 1, 4), dtype=np.uint8)
    for _, number, color in CLASSES:
        if color is not None:
            table[number] = color + (255,)
    return table


def class_of(rgb):
    """Код класса по цвету пикселя тайла или None. Цвет сравнивается
    с допуском: сжатие PNG без потерь, но масштабирование картинки
    в загрузчике может смешать соседей."""
    best, score = None, 30
    for code, _, color in CLASSES:
        if color is None:
            continue
        d = sum(abs(int(a) - int(b)) for a, b in zip(rgb[:3], color))
        if d < score:
            best, score = code, d
    return best


def rgba(tile, opacity=OPACITY):
    """Картинка тайла (h, w, 4) uint8 в слой вида: альфа умножена на
    непрозрачность, цвет предумножен. Тайл без единого пикселя карты -
    None, как пустой тайл Macrostrat (core/geology.py)."""
    tile = np.asarray(tile)
    alpha = tile[..., 3].astype(np.float32) / 255.0 * opacity
    if not np.any(alpha > 0.0):
        return None
    out = np.empty(tile.shape[:2] + (4,), dtype=np.uint8)
    for band in range(3):
        out[..., band] = (tile[..., band] * alpha).astype(np.uint8)
    out[..., 3] = (alpha * 255.0).astype(np.uint8)
    return out
