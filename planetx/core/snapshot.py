# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Снимок вида: размер в пикселях, масштаб надписей, место на странице.

Расчёт без Qt. Снимок рисуется в невидимый буфер своего размера.
Выбор тайлов идёт по пикселям снимка, поэтому большой снимок берёт
более подробные тайлы, чем окно. Надписи и толщина линий задаются
в логических пикселях и умножаются на масштаб надписей снимка.
"""

MM_PER_INCH = 25.4
SCREEN_DPI = 96.0  # логический пиксель экрана при масштабе 100 %
MAX_SIDE = 8000  # пикселей на сторону снимка, не больше
MIN_SIDE = 16
PAGE_MARGIN = 10.0  # мм от края страницы макета до картинки


def clamp_size(width, height, max_side=MAX_SIDE):
    """Размер в пикселях в пределах MIN_SIDE-max_side, пропорции те же."""
    width = max(float(width), 1.0)
    height = max(float(height), 1.0)
    k = min(1.0, max_side / max(width, height))
    return (max(MIN_SIDE, int(round(width * k))),
            max(MIN_SIDE, int(round(height * k))))


def layout_pixels(width_mm, height_mm, dpi, max_side=MAX_SIDE):
    """Пиксели картинки макета при разрешении вывода dpi."""
    return clamp_size(width_mm / MM_PER_INCH * dpi,
                      height_mm / MM_PER_INCH * dpi, max_side)


def layout_ratio(dpi):
    """Пикселей снимка на логический пиксель для макета.

    Надпись на бумаге выходит того же размера, что на экране
    с масштабом 100 %.
    """
    return max(dpi / SCREEN_DPI, 0.25)


def file_ratio(window_ratio, window_width, shot_width):
    """Пикселей снимка на логический пиксель для снимка в файл.

    Снимок вдвое шире окна выглядит как окно, увеличенное вдвое:
    надписи и линии тоже вдвое крупнее.
    """
    return max(window_ratio * shot_width / max(window_width, 1), 0.25)


def fit_on_page(page_width, page_height, aspect, margin=PAGE_MARGIN):
    """Размер картинки в мм: вся ширина страницы без полей, пропорции
    aspect = ширина / высота. Если по высоте не входит - вся высота."""
    width = max(page_width - 2.0 * margin, 1.0)
    height = max(page_height - 2.0 * margin, 1.0)
    if width / aspect <= height:
        return width, width / aspect
    return height * aspect, height


def letterbox(src_width, src_height, dst_width, dst_height):
    """Прямоугольник (x0, y0, x1, y1) картинки src в окне dst.

    Картинка вписана целиком, пропорции сохранены, по центру.
    """
    k = min(dst_width / src_width, dst_height / src_height)
    width = int(round(src_width * k))
    height = int(round(src_height * k))
    x0 = (dst_width - width) // 2
    y0 = (dst_height - height) // 2
    return x0, y0, x0 + width, y0 + height
