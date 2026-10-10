# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Месторождения USGS: файл в профиле QGIS и разбор в рабочем потоке.

Архивы USGS скачиваются один раз, разбор (core.deposits.parse) идёт
в постоянном пуле «deposits» (net/gdalnet.py), итог пишется файлом
PlanetX/deposits.npz профиля, как файлы групп спутников. Это отступление
от правила «своего кэша на диске плагин не заводит», написанного для
тайлов: архив MRDS - 23 МБ, ответ USGS без заголовков кэширования.
"""
import os

from qgis.core import QgsApplication

from ..core import deposits


def deposits_path():
    """Файл месторождений в профиле QGIS."""
    folder = os.path.join(QgsApplication.qgisSettingsDirPath(), "PlanetX")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "deposits.npz")


def parse_deposits(mrds, major, path):
    """Разбор обоих архивов и запись файла path. Рабочий поток, Qt не
    трогает. Возвращает core.deposits.Deposits."""
    data = deposits.parse(mrds, major)
    deposits.save(data, path)
    return data
