# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Темы NASA GIBS: растры по датам - огонь, вода, газы, земля и жизнь.

Просьба автора от 5 октября 2026 года, «Планета огня» и «Планета воды».
Слои выбрал помощник по полному списку GetCapabilities GIBS EPSG:3857
«best» на 5 октября 2026 года, у каждого проверен тайл на дату ряда.
Состав утверждает автор. Тайлы - PNG с прозрачностью там, где данных
нет, у ночного снимка - JPEG. Дата слоя - день ряда не позже
выбранного момента: ряд с пропусками даёт запрос DescribeDomains,
дата вне ряда отвечает 404. Шкала слоя - цветовая карта GIBS v1.3.

Расчёт без Qt: таблица слоёв, адреса, разбор ряда дат и выбор дня,
разбор цветовой карты, прозрачность тайла. Названия - в ui/themes.py.
"""
import calendar
import datetime
import html
import re

import numpy as np

ROOT = "https://gibs.earthdata.nasa.gov"
URL = (ROOT + "/wmts/epsg3857/best/{layer}/default/{time}/"
       "GoogleMapsCompatible_Level{level}/{{z}}/{{y}}/{{x}}.{ext}")
DOMAINS = (ROOT + "/wmts/epsg3857/best/1.0.0/{layer}/default/"
           "GoogleMapsCompatible_Level{level}/all/1900-01-01--2100-01-01.xml")
COLORMAP = ROOT + "/colormaps/v1.3/{name}.xml"
ATTRIBUTION = ("NASA GIBS", "https://earthdata.nasa.gov/gibs")
OPACITY = 0.8  # непрозрачность раскраски поверх снимка

GROUPS = ("fire", "water", "gases", "life")


class Theme:
    """Слой темы: ключ строки, группа, слой GIBS, расширение тайла,
    предельный уровень, цветовая карта (None - шкалы нет)."""

    __slots__ = ("key", "group", "layer", "ext", "level", "colormap")

    def __init__(self, key, group, layer, ext, level, colormap):
        self.key = key
        self.group = group
        self.layer = layer
        self.ext = ext
        self.level = level
        self.colormap = colormap

    def url(self, day):
        """Адрес тайла на день day (строка YYYY-MM-DD) для загрузчика."""
        return URL.format(layer=self.layer, time=day, level=self.level,
                          ext=self.ext)

    def domains_url(self):
        return DOMAINS.format(layer=self.layer, level=self.level)

    def colormap_url(self):
        return COLORMAP.format(name=self.colormap) if self.colormap \
            else None


THEMES = (
    Theme("smoke", "fire", "OMPS_Aerosol_Index", "png", 6,
          "OMPS_Aerosol_Index"),
    Theme("aerosol", "fire", "MODIS_Combined_Value_Added_AOD", "png", 6,
          "MODIS_Combined_Value_Added_AOD"),
    Theme("co", "fire", "AIRS_L2_Carbon_Monoxide_500hPa_Volume_Mixing_"
          "Ratio_Day", "png", 6, "AIRS_Carbon_Monoxide_Volume_Mixing_Ratio"),
    Theme("co_emission", "fire", "MERRA2_Carbon_Monoxide_Emission_Monthly",
          "png", 6, "MERRA2_Carbon_Monoxide_Emission_Monthly"),
    Theme("rain", "water", "IMERG_Precipitation_Rate", "png", 6,
          "GPM_Precipitation_Rate"),
    Theme("soil", "water", "SMAP_L3_Passive_Enhanced_Day_Soil_Moisture",
          "png", 6, "SMAP_Soil_Moisture"),
    Theme("snow", "water", "MODIS_Terra_NDSI_Snow_Cover", "png", 8,
          "MODIS_NDSI_Snow_Cover"),
    # Суточный снег зимой над Сибирью - 22 % тайла, остальное облака
    # и полярная ночь, 15 января 2026 года. Сводка за 8 суток - 60 %,
    # модель SMAP - 98 %. Слои добавлены по решению автора от 6 октября
    # 2026 года.
    Theme("snow_8day", "water", "MODIS_Terra_L3_Snow_Extent_8Day", "png",
          8, "MODIS_L3_Snow_Extent"),
    Theme("snow_mass", "water", "SMAP_L4_Snow_Mass", "png", 6,
          "SMAP_Snow_Mass"),
    Theme("sea_ice", "water", "GHRSST_L4_MUR_Sea_Ice_Concentration", "png",
          7, "GHRSST_Sea_Ice_Concentration"),
    Theme("vapor", "water", "MODIS_Terra_Water_Vapor_5km_Day", "png", 6,
          "MODIS_Water_Vapor"),
    Theme("chlorophyll", "water", "OCI_PACE_Chlorophyll_a", "png", 7,
          "MODIS_Chlorophyll"),
    Theme("salinity", "water", "SMAP_L3_Sea_Surface_Salinity_CAP_8Day_"
          "RunningMean", "png", 6, "SMAP_Sea_Surface_Salinity"),
    Theme("flood", "water", "MODIS_Combined_Flood_3-Day", "png", 9,
          "MODIS_Flood"),
    # Имя слоя целиком сканер секретов каталога принимал за ключ.
    Theme("no2", "gases", "TROPOMI_L2_Nitrogen_Dioxide_"
          "Tropospheric_Column", "png", 6,
          "OMI_Nitrogen_Dioxide_Tropo_Column"),
    Theme("so2", "gases", "OMPS_SO2_Planetary_Boundary_Layer", "png", 6,
          "OMPS_SO2_Planetary_Boundary_Layer"),
    Theme("methane", "gases", "AIRS_L3_Methane_400hPa_Volume_Mixing_Ratio_"
          "Monthly_Day", "png", 6, "AIRS_Methane_Volume_Mixing_Ratio"),
    Theme("co2", "gases", "OCO-2_Carbon_Dioxide_Total_Column_Average",
          "png", 8, "OCO_Carbon_Dioxide_Total_Column_Average"),
    Theme("ozone", "gases", "OMI_Ozone_TOMS_Total_Column", "png", 6,
          "OMI_Ozone_TOMS_Total_Column"),
    Theme("ndvi", "life", "MODIS_Terra_L3_NDVI_16Day", "png", 9,
          "MODIS_L3_NDVI"),
    Theme("dust", "life", "AIRS_L2_Dust_Score_Day", "png", 6,
          "AIRS_Dust_Score"),
    Theme("night", "life", "VIIRS_SNPP_DayNightBand_AtSensor_M15", "jpeg",
          8, None),
    Theme("land_cover", "life", "MODIS_Combined_L3_IGBP_Land_Cover_Type_"
          "Annual", "png", 8, "MODIS_IGBP_Land_Cover_Type"),
)
BY_KEY = {theme.key: theme for theme in THEMES}

_INTERVAL = re.compile(r"(\d{4}-\d{2}-\d{2})(?:T[\d:]+Z)?/"
                       r"(\d{4}-\d{2}-\d{2})(?:T[\d:]+Z)?/P(\d+)([DMY])")
_DOMAIN = re.compile(r"<Domain>([^<]*)</Domain>")


def _date(text):
    return datetime.date(*(int(part) for part in text.split("-")))


def parse_domains(data):
    """Ряд дат слоя из ответа DescribeDomains: список (начало, конец,
    шаг, единица шага D, M или Y). Шаги меньше суток не разбираются."""
    if isinstance(data, bytes):
        data = data.decode("utf-8", "replace")
    found = _DOMAIN.search(data or "")
    if found is None:
        return []
    out = []
    for start, end, count, unit in _INTERVAL.findall(found.group(1)):
        out.append((_date(start), _date(end), int(count), unit))
    return out


def _add(day, count, unit):
    if unit == "D":
        return day + datetime.timedelta(days=count)
    months = day.month - 1 + (count if unit == "M" else 12 * count)
    year = day.year + months // 12
    month = months % 12 + 1
    return day.replace(year=year, month=month,
                       day=min(day.day, calendar.monthrange(year,
                                                            month)[1]))


def _floor(start, end, count, unit, day):
    """Последний день ряда start..end с шагом не позже day."""
    if unit == "D":
        steps = (day - start).days // count
        found = start + datetime.timedelta(days=steps * count)
    else:
        months = (day.year - start.year) * 12 + day.month - start.month
        if unit == "Y":
            months -= months % 12
        step = count * (12 if unit == "Y" else 1)
        found = _add(start, months // step * step, "M")
        if found > day:
            found = _add(start, (months // step - 1) * step, "M")
    return min(found, end)


def pick_day(intervals, moment=None):
    """День ряда для момента moment (секунды UTC): последний день ряда
    не позже момента, раньше начала ряда - первый, без момента -
    последний. Строка YYYY-MM-DD или None, если ряд пуст."""
    if not intervals:
        return None
    ordered = sorted(intervals)
    if moment is None:
        return ordered[-1][1].isoformat()
    day = datetime.datetime.fromtimestamp(
        moment, datetime.timezone.utc).date()
    best = None
    for start, end, count, unit in ordered:
        if start > day:
            break
        best = _floor(start, end, count, unit, day)
    return (best or ordered[0][0]).isoformat()


def days(intervals):
    """Все дни ряда по порядку, строки YYYY-MM-DD: шаги ползунка темы.
    Ежедневный ряд с 2000 года - около 9500 дней."""
    out = []
    for start, end, count, unit in sorted(intervals):
        day = start
        while day <= end:
            out.append(day.isoformat())
            day = _add(day, count, unit)
    return sorted(set(out))


def moment(day):
    """Начало дня YYYY-MM-DD в секундах UTC."""
    return float(calendar.timegm(_date(day).timetuple()))


def span(intervals):
    """Охват ряда: (первый, последний) день в секундах UTC или None."""
    if not intervals:
        return None
    first = min(item[0] for item in intervals)
    last = max(item[1] for item in intervals)
    return tuple(float(calendar.timegm(day.timetuple()))
                 for day in (first, last))


_MAP = re.compile(r"<ColorMap\b([^>]*)>(.*?)</ColorMap>", re.S)
_ATTR = re.compile(r'(\w+)="([^"]*)"')
_ENTRY = re.compile(r"<LegendEntry\b([^>]*)/>")
_LEGEND = re.compile(r"<Legend\b([^>]*)>")


def parse_colormap(data):
    """Шкала слоя из цветовой карты GIBS v1.3: словарь kind
    («continuous» и «discrete» - полоса цветов, «classification» -
    классы), units, colors - цвета по порядку,
    labels - пары (доля от 0 до 1, подпись), names - подписи классов.
    Карта «нет данных» и прозрачные классы пропускаются. None - шкалы
    в ответе нет."""
    if isinstance(data, bytes):
        data = data.decode("utf-8", "replace")
    best = None
    for attrs, body in _MAP.findall(data or ""):
        legend = _LEGEND.search(body)
        if legend is None:
            continue
        head = dict(_ATTR.findall(legend.group(1)))
        kind = head.get("type", "continuous")
        entries = [dict(_ATTR.findall(e)) for e in _ENTRY.findall(body)]
        entries = [e for e in entries if "rgb" in e
                   and e.get("tooltip", "") != "No Data"]
        if not entries:
            continue
        found = {"kind": kind,
                 "units": html.unescape(dict(_ATTR.findall(attrs))
                                        .get("units", "")),
                 "colors": [tuple(int(v) for v in e["rgb"].split(","))
                            for e in entries],
                 "labels": [], "names": []}
        count = len(entries)
        for n, entry in enumerate(entries):
            if entry.get("showLabel") == "true" and entry.get("label"):
                found["labels"].append(
                    ((n + 0.5) / count, html.unescape(entry["label"])))
            found["names"].append(html.unescape(
                entry.get("label") or entry.get("tooltip", "")))
        if kind != "classification" and not found["labels"]:
            found["labels"] = [
                (0.0, html.unescape(head.get("minLabel", ""))),
                (1.0, html.unescape(head.get("maxLabel", "")))]
        if best is None or count > len(best["colors"]):
            best = found
    return best


def overlay_rgba(rgba, opacity=OPACITY):
    """Тайл темы в RGBA uint8 с премноженной альфой и непрозрачностью
    opacity. Где данных нет, прозрачно."""
    rgba = np.asarray(rgba, dtype=np.float32)
    alpha = rgba[..., 3:4] / 255.0 * opacity
    out = np.empty(rgba.shape, dtype=np.uint8)
    out[..., :3] = np.rint(rgba[..., :3] * alpha)
    out[..., 3:] = np.rint(alpha * 255.0)
    return out
