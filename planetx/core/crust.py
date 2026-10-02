# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Кора Земли по модели CRUST1.0. Без Qt.

Шаг 1 плана «сверху вниз», 2 октября 2026 года. CRUST1.0 (Laske,
Masters, Ma, Pasyanos, 2013) - сетка ячеек 1°×1°, в каждой 9 отметок
границ в километрах, вверх положительно:

0. верх воды (на суше - рельеф);
1. низ воды;
2. низ льда;
3-5. низ верхних, средних и нижних осадков;
6-8. низ верхней, средней и нижней коры, последняя - Мохо.

Слой нулевой толщины в ячейке - две равные отметки подряд. Модель
лежит на сайте UCSD, файл границ crust1.bnds в архиве crust1.0.tar.gz
(URL). Модуль не распространяет её, а скачивает при первом показе,
решение автора от 2 октября 2026 года. Авторы просят ссылаться на
сайт модели или на статью, см. CITATION.

Строки файла идут с широты 89.5° на юг, внутри строки широты - долготы
от -179.5° на восток (readme модели). Ячейка - середина клетки, точка
относится к ячейке, в которую попадает.
"""
import io
import tarfile

import numpy as np

URL = "https://igppweb.ucsd.edu/~gabi/crust1/crust1.0.tar.gz"
MEMBER = "crust1.bnds"
CITATION = ("CRUST1.0, Laske, Masters, Ma, Pasyanos, 2013",
            "https://igppweb.ucsd.edu/~gabi/crust1.html")
ROWS, COLS, BOUNDS = 180, 360, 9
# Слои между соседними отметками: ключ.
LAYERS = ("water", "ice", "sediments_upper", "sediments_middle",
          "sediments_lower", "crust_upper", "crust_middle", "crust_lower")
MOHO = 8


class CrustError(ValueError):
    """Файл модели не того вида."""


def parse_bounds(text):
    """Отметки границ (ROWS, COLS, BOUNDS) в км, float32, из текста
    crust1.bnds."""
    if isinstance(text, bytes):
        text = text.decode("ascii", errors="replace")
    try:
        values = np.array(text.split(), dtype=np.float32)
    except ValueError as error:
        raise CrustError(str(error)) from error
    if values.size != ROWS * COLS * BOUNDS:
        raise CrustError("{} values".format(values.size))
    return values.reshape(ROWS, COLS, BOUNDS)


def from_archive(data):
    """Модель из байтов архива crust1.0.tar.gz."""
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            member = tar.getmember(MEMBER)
            text = tar.extractfile(member).read()
    except (tarfile.TarError, KeyError, OSError, EOFError) as error:
        raise CrustError(str(error)) from error
    return Crust(parse_bounds(text))


def cells(lats, lons):
    """Номера строки и столбца ячейки для широт и долгот."""
    lats = np.asarray(lats, dtype=np.float64)
    lons = np.asarray(lons, dtype=np.float64)
    row = np.clip(np.floor(90.0 - lats), 0, ROWS - 1).astype(np.int64)
    col = np.floor((lons + 180.0) % 360.0).astype(np.int64) % COLS
    return row, col


class Crust:
    """Отметки границ CRUST1.0."""

    def __init__(self, bounds):
        self.bounds = bounds

    def at(self, lats, lons):
        """Отметки границ (..., BOUNDS) в км для точек."""
        row, col = cells(lats, lons)
        return self.bounds[row, col]

    def moho(self, lats, lons):
        """Глубина Мохо ниже уровня моря, км, положительная."""
        return -self.at(lats, lons)[..., MOHO].astype(np.float64)

    def thickness(self, lats, lons):
        """Толщина коры без воды, км: от низа воды до Мохо."""
        b = self.at(lats, lons).astype(np.float64)
        return b[..., 1] - b[..., MOHO]

    def layers(self, lats, lons):
        """Слои в точках: ключ, верх и низ в км, только ненулевые.
        Список на точку, порядок сверху вниз."""
        b = np.atleast_2d(self.at(lats, lons))
        out = []
        for row in b:
            out.append([(LAYERS[k], float(row[k]), float(row[k + 1]))
                        for k in range(len(LAYERS))
                        if row[k] > row[k + 1]])
        return out
