# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Геологическая карта Macrostrat. Без Qt.

Решение автора от 17 октября 2026 года по списку открытых данных
помощника - геологическая карта строкой «Недр». Macrostrat (Peters и
соавторы, университет Висконсин-Мэдисон) сводит геологические карты
мира разных масштабов в одну, данные под CC BY 4.0, сверено 17 октября
2026 года по ответу /api/v2/meta. Тайлы PNG 512 × 512 по адресу TILES
без ключа, цвет - возраст пород по шкале карт. Сведения о породе
в точке - запрос mobile/map_query: название подразделения, литология,
возраст по стратиграфической шкале и карта-источник.

Карта собрана из карт разного масштаба, каждый показывается до своего
уровня. Глубже уровня самой подробной карты места тайл приходит пустым,
целиком прозрачным, - так у Перми с уровня 10 (карта Европы 1:5 000 000),
у Невады подробные карты есть и на уровне 15. Пустой тайл не рисуется
(rgba даёт None), на его месте остаётся увеличенный предок.

На глобусе геологическая карта делит слой вида «emag» с картами
значений геофизики, на глобусе одна такая карта. Непрозрачность -
выбор помощника, утверждает автор.
"""
import json

import numpy as np

TILES = "https://tiles.macrostrat.org/carto/{z}/{x}/{y}.png"
MAX_LEVEL = 14
QUERY = ("https://macrostrat.org/api/v2/mobile/map_query?"
         "lat={lat:.5f}&lng={lon:.5f}&z={z}")
ATTRIBUTION = ("Geology: Macrostrat, CC BY 4.0", "https://macrostrat.org/")
PAGE = "https://macrostrat.org/map/loc/{lon:.4f}/{lat:.4f}"
OPACITY = 0.75
# Глубже карты места map_query отвечает пустой записью, как тайлы.
# Тогда запрос повторяется на столько уровней мельче, выбор помощника.
QUERY_STEP = 3


def query_url(lat, lon, z):
    """Адрес сведений о породе в точке на уровне карты z."""
    z = int(min(max(round(z), 0), 16))
    return QUERY.format(lat=lat, lon=lon, z=z)


def coarser(z):
    """Уровень следующего запроса, когда на уровне z карта в точке пуста:
    на 3 мельче, None - мельче спрашивать некуда."""
    z = int(round(z))
    return None if z <= 1 else max(1, z - QUERY_STEP)


def page_url(lat, lon):
    """Страница карты Macrostrat у точки."""
    return PAGE.format(lat=lat, lon=lon)


def rgba(tile, opacity=OPACITY):
    """Тайл карты (RGBA uint8) в премноженную альфу с непрозрачностью
    opacity. Целиком прозрачный тайл - None: карта места кончилась на
    более мелком уровне, рисуется предок."""
    tile = np.asarray(tile)
    alpha = tile[..., 3].astype(np.float32) / 255.0 * opacity
    if not alpha.any():
        return None
    out = np.empty(tile.shape, np.uint8)
    for k in range(3):
        out[..., k] = np.round(tile[..., k].astype(np.float32) * alpha)
    out[..., 3] = np.round(alpha * 255.0)
    return out


def _age(item, prefix):
    value = item.get(prefix + "_age")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_query(data):
    """Подразделения карты в точке из ответа map_query: список словарей
    name, strat_name, lith, descrip, comments, top (название верхней
    границы возраста), bottom (нижней), top_age и bottom_age (млн лет
    или None), color, scale, source (название карты), authors, year,
    url. Пустой список - карта в точке ничего не показывает."""
    if isinstance(data, (bytes, bytearray)):
        data = data.decode("utf-8")
    answer = json.loads(data)
    found = ((answer.get("success") or {}).get("data") or {})
    units = []
    for item in found.get("burwell") or ():
        if not (item.get("name") or item.get("lith")
                or item.get("t_int_name")):
            # Глубже карты места служба отвечает пустой записью {}.
            continue
        ref = item.get("ref") or {}
        units.append({
            "name": str(item.get("name") or ""),
            "strat_name": str(item.get("strat_name") or ""),
            "lith": str(item.get("lith") or ""),
            "descrip": str(item.get("descrip") or ""),
            "comments": str(item.get("comments") or ""),
            "top": str(item.get("t_int_name") or ""),
            "bottom": str(item.get("b_int_name") or ""),
            "top_age": _age(item, "t_int"),
            "bottom_age": _age(item, "b_int"),
            "color": str(item.get("color") or ""),
            "scale": str(item.get("scale") or ""),
            "source": str(ref.get("name") or ""),
            "authors": str(ref.get("authors") or ""),
            "year": str(ref.get("ref_year") or ""),
            "url": str(ref.get("url") or "")})
    return units


def age_text(unit):
    """Возраст подразделения: названия интервалов и пределы в млн лет
    без единицы, например («Late Permian», «274.4-251.9»)."""
    top, bottom = unit["top"], unit["bottom"]
    names = top if not bottom or bottom == top else "{} - {}".format(
        bottom, top)
    low, high = unit["top_age"], unit["bottom_age"]
    if low is None or high is None:
        return names, ""
    return names, "{:g}-{:g}".format(round(high, 1), round(low, 1))
