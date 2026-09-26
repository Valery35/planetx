# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Уровни мипмапов картинки на NumPy.

glGenerateMipmap на новой текстуре стоит 1.6 мс главного потока, замер
26 сентября 2026 года. Уровни считаются здесь, в рабочем потоке
загрузчика, главный поток только передаёт их в видеокарту.
"""
import numpy as np


def mip_chain(rgba):
    """Уровни от исходного до 1×1.

    Уровень k - среднее исходной картинки по блокам 2^k × 2^k, округлённое
    один раз. Усреднение уровня из предыдущего округляло бы на каждом
    шаге, и сдвиг копился бы: у картинки 256×256 до 1.6 из 255 на
    последнем уровне. Стороны картинки - степени двойки.
    """
    base = np.ascontiguousarray(rgba, dtype=np.uint8)
    h, w = base.shape[:2]
    levels = [base]
    wide = base.astype(np.float32)
    size_h, size_w = h, w
    while size_h > 1 or size_w > 1:
        size_h, size_w = max(1, size_h // 2), max(1, size_w // 2)
        block_h, block_w = h // size_h, w // size_w
        mean = wide.reshape(size_h, block_h, size_w, block_w, 4).mean(
            axis=(1, 3))
        levels.append(np.ascontiguousarray(np.rint(mean), dtype=np.uint8))
    return levels
