# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «Космоснимки»: сцены участка, каналы и индексы
в проект.

Участок - точка с квадратом стороной side или метка «Моих меток»
(многоугольник, путь - по рамке точек). Поиск - STAC API Earth Search
запросом через QgsNetworkAccessManager (net/overlay.post_json), страницы
по ссылке next. Landsat - каталог Planetary Computer, файлы по ключу
SAS, его окно просит у службы ключей раз в SAS_LIFE (_with_token).
Облачность над участком считается по маске облаков каждой
сцены в рабочих потоках, по CLOUD_WORKERS сразу, список дополняется по
мере расчёта. Превью - участок в естественных цветах по обзорным
уровням COG. Выдача - сочетания каналов и индексы
(core/sentinel.py): обрезка по участку в GeoTIFF отражениями float32
или вся сцена ссылкой VRT на файлы в сети (только сочетания). Слои
ложатся в группу дня внутри группы «Sentinel-2» вверху дерева,
растяжение - по процентилям 2-98 снимка, индексы - шкалой цветов.

GDAL в рабочих потоках: перед первым вызовом он зовётся в главном
потоке (inset.warm), в потоке ошибки гасятся, параметры сети - свои
у потока. FutureWarning osgeo в рабочем потоке роняет QGIS, см.
AGENTS.md.
"""
import json
import os
import time
from urllib.parse import urlsplit

import numpy as np
from qgis.core import (Qgis, QgsColorRampShader, QgsContrastEnhancement,
                       QgsMultiBandColorRenderer, QgsProject, QgsRasterLayer,
                       QgsRasterShader, QgsSettings,
                       QgsSingleBandGrayRenderer,
                       QgsSingleBandPseudoColorRenderer)
from qgis.PyQt.QtCore import QDate, Qt, QTimer
from qgis.PyQt.QtGui import QColor, QImage, QPixmap
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDialog,
                                 QDialogButtonBox, QDoubleSpinBox,
                                 QFileDialog, QGridLayout, QHBoxLayout,
                                 QInputDialog, QLabel, QLineEdit,
                                 QListWidget, QListWidgetItem,
                                 QPushButton, QSpinBox, QTreeWidget,
                                 QTreeWidgetItem, QVBoxLayout)

from ..core import aster, modis
from ..core import series as series_core
from ..core import sentinel as s2
from ..i18n import tr
from ..net.gdalnet import close_connections as _close_connections
from ..net.gdalnet import executor
from ..net.gdalnet import thread_gdal as _thread_gdal
from ..net.overlay import fetch_bytes, post_json, resolve_redirect
from ..qt_compat import enum
from .inset import warm as warm_gdal

POLL = 200  # мс между проверками заданий рабочих потоков
CLOUD_WORKERS = 4  # сцен, у которых маска облаков читается сразу
BAND_WORKERS = 4  # каналов сцены, читаемых сразу
PREVIEW = 256  # пикселей стороны превью участка
PREVIEW_WHITE = 0.25  # отражение белого в превью Landsat
SAS_TRIES = 3  # запросов ключа SAS Landsat до отказа
SAS_PAUSE = 2000  # мс между запросами ключа
SAS_LIFE = 45 * 60  # с, ключ просится заново раньше часа его жизни
SIDE_DEFAULT = 3.0  # км, сторона участка точки
SCENE_CLOUD_DEFAULT = 80  # %, облачность сцены в поиске
AREA_CLOUD_DEFAULT = 10  # %, облачность над участком в списке
DEFAULT_PRODUCTS = ("natural", "infrared", "ndvi")
# Продукты из всех каналов одним файлом.
MULTI = ("all_bands", "mss_bands")
# Растяжение сочетания ссылкой без скачивания - отражение по каналам.
LINK_RANGE = {"natural": (0.0, 0.25)}
LINK_RANGE_OTHER = (0.0, 0.45)
WHOLE_CHUNK = 1 << 20  # байт за одно чтение файла сцены целиком
WHOLE_SAMPLE = 1024  # пикселей стороны копии для растяжения всей сцены
SCENE_ROLE = enum(Qt, "ItemDataRole", "UserRole")
GROUP = "Sentinel-2"
GROUPS = {"sentinel2": GROUP, "landsat": "Landsat", "mss": "Landsat",
          "aster": "ASTER", "aster_nasa": "ASTER"}
# Ключ Earthdata пользователя для файлов ASTER NASA после 2006 года.
# Хранится в настройках QGIS открытым текстом, как ключ помощника
# с флажком «без мастер-пароля»; ключ NASA живёт 60 дней.
EARTHDATA_KEY = "PlanetX/earthdata/token"
# Даты поиска MSS, если прежние позже конца съёмки MSS: лето 1975
# года, Landsat 2. Выбор помощника, утверждает автор.
MSS_DATES = ("1975-05-01", "1975-09-30")
MSS_LAST = "2013-01-07"  # последний день коллекции landsat-c2-l1
GROUPS.update({key: "MODIS" for key in modis.MISSIONS})
STRETCH = enum(QgsContrastEnhancement, "ContrastEnhancementAlgorithm",
               "StretchToMinimumMaximum")


def titles(mission="sentinel2"):
    """Названия продуктов окна и слоёв. Номера каналов - Sentinel-2,
    у Landsat 4-7 и 8-9 они разные, поэтому у Landsat их нет."""
    names = {"natural": tr("Естественные цвета (B4 B3 B2)"),
             "infrared": tr("Ложные цвета, ближний ИК (B8 B4 B3)"),
             "agriculture": tr("Сельское хозяйство (B11 B8 B2)"),
             "swir": tr("Коротковолновый ИК (B12 B8A B4)"),
             "geology": tr("Геология (B12 B11 B2)"),
             "urban": tr("Застройка (B12 B11 B4)"),
             "ndvi": tr("NDVI - растительность"),
             "ndwi": tr("NDWI - открытая вода"),
             "ndmi": tr("NDMI - влажность растительности"),
             "nbr": tr("NBR - гари"),
             "ndsi": tr("NDSI - снег"),
             "lst": tr("Температура поверхности, °C"),
             "lst_day": tr("Температура поверхности днём, °C"),
             "lst_night": tr("Температура поверхности ночью, °C"),
             "modis_ndvi": tr("NDVI - растительность"),
             "modis_evi": tr("EVI - растительность"),
             "snow_cover": tr("Снег, % пикселя"),
             "snow_extent": tr("Снег и лёд за 8 суток"),
             "burn_date": tr("Гари, день года"),
             "mss_bands": tr("Все четыре канала MSS"),
             "all_bands": tr("Все каналы сцены"),
             "aster_false": tr("Ложные цвета (3N 2 1)"),
             "aster_swir": tr("Коротковолновый ИК (4 6 8)"),
             "kaolinite": tr("Каолинит, алунит, (4 + 6) / 5"),
             "aloh": tr("Серицит, мусковит, (5 + 7) / 6"),
             "mgoh": tr("Mg-OH и карбонаты, (7 + 9) / 8"),
             "ferric": tr("Оксиды железа, 2 / 1"),
             "quartz": tr("Кварц, 11² / (10 × 12)")}
    if mission in s2.LANDSATS:
        names = {k: v.split(" (")[0] for k, v in names.items()}
    return names


MISSIONS = ("sentinel2", "landsat", "mss", "aster", "aster_nasa") \
    + tuple(modis.MISSIONS)
# Годы спутников, у которых съёмка кончилась: последний день и даты
# поиска, если прежние позже. Выбор помощника, утверждает автор.
ERA = {"mss": (MSS_LAST, MSS_DATES),
       "aster": (aster.LAST_DAY, (aster.FIRST_DAY, aster.LAST_DAY))}


def mission_title(mission):
    return {"sentinel2": tr("Sentinel-2 - 10 м, с 2015 года"),
            "landsat": tr("Landsat 4-9 - 30 м, с 1982 года"),
            "mss": tr("Landsat 1-5 MSS - 60 м, 1972-1993 годы"),
            "aster": tr("ASTER - 15-90 м, 14 каналов, 2000-2006 годы"),
            "aster_nasa": tr("ASTER с 2007 года - NASA, нужен ключ "
                             "Earthdata"),
            "modis_lst1": tr("MODIS - температура за сутки, 1 км"),
            "modis_lst8": tr("MODIS - температура за 8 суток, 1 км"),
            "modis_veg": tr("MODIS - NDVI и EVI за 16 суток, 250 м"),
            "modis_snow1": tr("MODIS - снег за сутки, 500 м"),
            "modis_snow8": tr("MODIS - снег за 8 суток, 500 м"),
            "modis_burn": tr("MODIS - гари по месяцам, 500 м")}[mission]


def mission_credit(mission):
    if modis.is_modis(mission):
        return tr("MODIS Terra и Aqua версии 061 (NASA LP DAAC, снег - "
                  "NSIDC), файлы и каталог Microsoft Planetary Computer. "
                  "Слои несут подпись продукта и архива NASA.")
    if mission == "aster_nasa":
        return tr("ASTER L1T версии 004 (NASA LP DAAC, METI), каталог NASA "
                  "CMR, файлы - по ключу Earthdata, его можно получить "
                  "бесплатно на urs.earthdata.nasa.gov. После 2008 года - "
                  "только каналы VNIR и TIR. Значения - для нормального "
                  "усиления каналов.")
    if mission == "aster":
        return tr("ASTER L1T (NASA, METI), файлы и каталог Microsoft "
                  "Planetary Computer, съёмка 2000-2006 годов. Значения - "
                  "отражение на верху атмосферы и яркостная температура "
                  "для нормального усиления каналов. Слои несут подпись "
                  "«ASTER data courtesy of NASA/METI/AIST/Japan "
                  "Spacesystems».")
    if mission == "mss":
        return tr("Landsat 1-5 MSS Collection 2 Level-1 (USGS), файлы "
                  "и каталог Microsoft Planetary Computer. Значения - "
                  "отражение на верху атмосферы, без поправки на атмосферу. "
                  "Слои несут подпись «Landsat image courtesy of the U.S. "
                  "Geological Survey».")
    if mission == "landsat":
        return tr("Landsat 4-9 Collection 2 Level-2 (USGS), файлы и каталог "
                  "Microsoft Planetary Computer. Слои несут подпись "
                  "«Landsat image courtesy of the U.S. Geological Survey».")
    return tr("Copernicus Sentinel-2 L2A (ESA), файлы и каталог Earth Search "
              "Element 84 на AWS. Слои несут подпись «Contains modified "
              "Copernicus Sentinel data» с годом снимка.")


def warm():
    """Первые вызовы GDAL в главном потоке, см. описание модуля."""
    warm_gdal()


def read_window(href, box, res=None, size=None, nearest=False, count=1,
                srs=None):
    """Окно файла в сети по рамке box системы файла или системы srs
    (EPSG): шаг res или размер size (столбцы, строки). href - адрес
    или кортеж адресов тайлов. Рабочий поток. Массив или None."""
    gdal = _thread_gdal()
    options = {"format": "MEM", "outputBounds": box,
               "resampleAlg": "near" if nearest else "bilinear"}
    if srs is not None:
        options["dstSRS"] = "EPSG:{}".format(int(srs))
    sources = ["/vsicurl/" + h for h in href] if isinstance(href, tuple) \
        else "/vsicurl/" + href
    if size is not None:
        options["width"], options["height"] = size
    else:
        options["xRes"] = options["yRes"] = res
    gdal.PushErrorHandler("CPLQuietErrorHandler")
    try:
        try:
            ds = gdal.Warp("", sources, **options)
        except RuntimeError:
            ds = None
        if ds is None:
            return None
        if count == 1:
            out = ds.GetRasterBand(1).ReadAsArray()
        else:
            out = ds.ReadAsArray()
        ds = None
    finally:
        gdal.PopErrorHandler()
        _close_connections(gdal)
    return out


def read_json(href):
    """Небольшой файл JSON в сети через GDAL, как каналы. Рабочий
    поток. OSError, если не прочитан."""
    gdal = _thread_gdal()
    gdal.PushErrorHandler("CPLQuietErrorHandler")
    try:
        try:
            handle = gdal.VSIFOpenL("/vsicurl/" + href, "rb")
        except RuntimeError:  # режим исключений GDAL
            handle = None
        if handle is None:
            raise OSError("mtl.json")
        try:
            chunks = []
            while True:
                chunk = gdal.VSIFReadL(1, 65536, handle)
                if not chunk:
                    break
                chunks.append(chunk)
        finally:
            gdal.VSIFCloseL(handle)
    finally:
        gdal.PopErrorHandler()
        _close_connections(gdal)
    try:
        return json.loads(b"".join(chunks).decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as error:
        raise OSError("mtl.json: {}".format(error)) from error


def _href(scene, key, sas):
    """Адрес канала сцены, у Landsat - с ключом SAS."""
    href = scene.assets[key].href
    return s2.sign(href, sas) if s2.needs_key(scene.mission) else href


def _srs(scene):
    """Система вывода, если она не система файла: у MODIS - UTM."""
    return scene.epsg if modis.is_modis(scene.mission) else None


def scene_cloud(scene, ring, sas=""):
    """Облачность над участком по маске сцены (SCL у Sentinel-2,
    qa_pixel у Landsat): (номер сцены, облачность, доля с данными) или
    (номер, None, None), если маска не прочитана."""
    try:
        xy = s2.ring_utm(ring, scene.epsg)
    except ValueError:
        return scene.id, None, None
    key, res = s2.CLOUD_ASSET[scene.mission]
    box = s2.bounds(xy, res)
    raw = read_window(_href(scene, key, sas), box, res, nearest=True,
                      srs=_srs(scene))
    if raw is None:
        return scene.id, None, None
    cloud, valid = s2.clouds_of(scene, raw, s2.mask(xy, box, res))
    return scene.id, cloud, valid


def series_value(scene, ring, name, sas="", epsg=None):
    """Сводка продукта name по участку сцены для ряда по датам:
    (номер сцены, core.series.Point или None, сетка значений с NaN вне
    чистых пикселей участка). Сетка грубее выдачи (core.series.step),
    пиксели облаков и теней по маске сцены не считаются. epsg - общая
    система сеток ряда, у сцен другой зоны UTM окно пересчитывается в неё,
    так сетки всех сцен совпадают для карты тренда. Рабочий поток."""
    if scene.mission == "mss":
        scene = s2.toa(scene, read_json(_href(scene, "mtl.json", sas)))
    srs = epsg or _srs(scene)
    xy = s2.ring_utm(ring, srs or scene.epsg)
    res = series_core.step(xy, scene.mission)
    box = s2.bounds(xy, res)
    cloud_key = s2.CLOUD_ASSET[scene.mission][0]
    keys = s2.needed([name], scene.mission)
    if cloud_key not in keys:
        keys.append(cloud_key)
    near = modis.is_modis(scene.mission) or scene.mission == "mss"
    raw = {}
    for key in keys:
        raw[key] = read_window(_href(scene, key, sas), box, res,
                               nearest=near or key == cloud_key, srs=srs)
        if raw[key] is None:
            raise OSError(key)
    area = s2.mask(xy, box, res)
    clear = s2.clear_mask(scene, raw[cloud_key])
    if modis.is_modis(scene.mission):
        values = modis.value(name, raw[modis.PRODUCTS[name][0]])
    else:
        bands = {k: s2.reflectance(v, scene.assets[k])
                 for k, v in raw.items() if k != cloud_key}
        values = s2.product(name, bands, scene.mission)
    values = np.asarray(values, dtype=np.float32)
    grid = np.where(area & clear & np.isfinite(values), values, np.nan)
    return scene.id, series_core.point(values, area, clear), \
        (grid.astype(np.float32), box, res, srs or scene.epsg)


def preview(scene, ring, sas=""):
    """Участок в естественных цветах, не больше PREVIEW пикселей по
    стороне: массив (3, строки, столбцы) uint8 или None. У Landsat
    картинка собирается из трёх каналов отражения."""
    xy = s2.ring_utm(ring, scene.epsg)
    box = s2.bounds(xy, 10.0)
    width, height = box[2] - box[0], box[3] - box[1]
    scale = PREVIEW / max(width, height)
    size = (max(int(width * scale), 1), max(int(height * scale), 1))
    if modis.is_modis(scene.mission):
        # Первый продукт спутника своей шкалой цветов.
        name = modis.products_of(scene.mission)[0]
        key, scale, _ = modis.PRODUCTS[name]
        raw = read_window(_href(scene, key, sas), box, size=size,
                          nearest=True, srs=scene.epsg)
        if raw is None:
            return None
        return modis.colorize(modis.value(name, raw), scale)
    if scene.mission == aster.NASA_MISSION:
        # Файлы NASA - по ключу, превью - открытая картинка всей сцены.
        return _whole_picture(scene.thumbnail)
    if aster.is_aster(scene.mission):
        # Ложные цвета 3N, 2, 1 одним файлом VNIR, растяжение по снимку.
        dn = read_window(_href(scene, "VNIR", sas), box, size=size,
                         nearest=True, count=3)
        if dn is None:
            return None
        out = []
        for index in (2, 1, 0):
            values = dn[index].astype(np.float32)
            values[dn[index] == 0] = np.nan
            lo, hi = s2.stretch(values)
            out.append(np.nan_to_num(np.clip(
                (values - lo) / (hi - lo) * 255.0, 0.0, 255.0))
                .astype(np.uint8))
        return np.stack(out)
    if scene.mission == "mss":
        # Синего канала у MSS нет: ложные цвета, растяжение по снимку,
        # насыщенные строки заменены соседями.
        radsat = read_window(_href(scene, "qa_radsat", sas), box, size=size,
                             nearest=True)
        bands = {}
        for key in s2.MSS_BANDS:
            dn = read_window(_href(scene, key, sas), box, size=size,
                             nearest=True)
            if dn is None:
                return None
            bands[key] = s2.reflectance(dn, scene.assets[key])
        if radsat is not None:
            _clean_mss(scene, bands, radsat)
        out = []
        for key in ("nir08", "red", "green"):
            values = bands[key]
            lo, hi = s2.stretch(values)
            out.append(np.nan_to_num(np.clip(
                (values - lo) / (hi - lo) * 255.0, 0.0, 255.0))
                .astype(np.uint8))
        return np.stack(out)
    if scene.mission != "landsat":
        asset = scene.assets.get("visual")
        if asset is None:
            return None
        return read_window(asset.href, box, size=size, count=3)
    out = []
    for key in ("red", "green", "blue"):
        dn = read_window(_href(scene, key, sas), box, size=size,
                         nearest=True)
        if dn is None:
            return None
        values = s2.reflectance(dn, scene.assets[key])
        out.append(np.nan_to_num(np.clip(
            values / PREVIEW_WHITE * 255.0, 0.0, 255.0)).astype(np.uint8))
    return np.stack(out)


def _whole_picture(href):
    """Картинка всей сцены по адресу в сети, не больше PREVIEW по
    стороне: (3, строки, столбцы) uint8 или None. Рабочий поток."""
    if not href:
        return None
    gdal = _thread_gdal()
    gdal.PushErrorHandler("CPLQuietErrorHandler")
    try:
        try:
            ds = gdal.Open("/vsicurl/" + href)
        except RuntimeError:
            ds = None
        if ds is None or ds.RasterCount < 3:
            return None
        scale = PREVIEW / float(max(ds.RasterXSize, ds.RasterYSize))
        width = max(int(ds.RasterXSize * scale), 1)
        height = max(int(ds.RasterYSize * scale), 1)
        out = np.stack([ds.GetRasterBand(n).ReadAsArray(
            buf_xsize=width, buf_ysize=height) for n in (1, 2, 3)])
        ds = None
    finally:
        gdal.PopErrorHandler()
        _close_connections(gdal)
    return out.astype(np.uint8)


def free_path(folder, stem, ext):
    """Путь файла продукта. Прежний файл с тем же именем удаляется, а
    если он занят - например, открыт слоем проекта QGIS, - берётся имя
    с номером _2, _3 и дальше."""
    number = 1
    while True:
        name = stem if number == 1 else "{}_{}".format(stem, number)
        path = os.path.join(folder, name + ext)
        if not os.path.exists(path):
            return path
        try:
            os.remove(path)
        except PermissionError:
            number += 1
            continue
        return path


def _clean_mss(scene, bands, radsat):
    """Полосы MSS: насыщенные пиксели по qa_radsat и всплески одного
    канала заменяются соседями. bands меняется на месте. Всплески
    ищутся, только когда прочитаны все четыре канала."""
    bits = {k: s2.radsat_bit(scene.assets[k]) for k in bands}
    clean, _ = s2.clean_mss(bands, radsat, {k: b for k, b in bits.items()
                                            if b is not None})
    bands.update(clean)


def build(scene, ring, products, folder, clear_clouds, sas="",
          fill=False):
    """Продукты сцены по участку в GeoTIFF: список (продукт, путь,
    пределы растяжения по каналам[, доля пикселей температуры по
    формуле]). fill - дыры температуры Landsat закрываются формулой
    (core.sentinel.thermal_fill). Рабочий поток."""
    fill = fill and scene.mission == "landsat" and "lst" in products
    gdal = _thread_gdal()
    if aster.is_aster(scene.mission):
        return _build_aster(gdal, scene, ring, products, folder, sas)
    if scene.mission == "mss":
        scene = s2.toa(scene, read_json(_href(scene, "mtl.json", sas)))
    xy = s2.ring_utm(ring, scene.epsg)
    res = s2.step_for(xy, scene.mission, products)
    box = s2.bounds(xy, res)
    # Береговой канал есть у Landsat 8-9, у 4-7 его нет.
    keys = [k for k in s2.needed(products, scene.mission, fill)
            if k in scene.assets or k not in s2.OPTIONAL_BANDS]
    if scene.mission == "mss":
        # Всплески одного канала видны только рядом с остальными.
        keys = keys + [k for k in s2.MSS_BANDS if k not in keys]
    cloud_key = s2.CLOUD_ASSET[scene.mission][0]
    if clear_clouds:
        keys = keys + [cloud_key]
    mss = scene.mission == "mss"
    if mss:
        # Маска насыщения: по ней сбойные строки заменяются соседями.
        keys = keys + ["qa_radsat"]
    srs = _srs(scene)
    # У MSS каналы без сглаживания, иначе строка в один пиксель
    # расплылась бы на два и маска насыщения не накрыла бы её.
    near = modis.is_modis(scene.mission) or mss
    raw = dict(zip(keys, executor("bands", BAND_WORKERS).map(
        lambda k: read_window(_href(scene, k, sas), box, res,
                              nearest=near or k == cloud_key, srs=srs),
        keys)))
    missing = [k for k, v in raw.items() if v is None]
    if missing:
        raise OSError(", ".join(missing))
    inside = s2.mask(xy, box, res)
    if clear_clouds:
        quality = raw[cloud_key] if modis.is_modis(scene.mission) \
            else raw.pop(cloud_key)
        inside &= s2.clear_mask(scene, quality)
    if modis.is_modis(scene.mission):
        return _build_modis(gdal, scene, raw, inside, products, folder,
                            box, res)
    radsat = raw.pop("qa_radsat") if mss else None
    bands = {k: s2.reflectance(v, scene.assets[k]) for k, v in raw.items()}
    if radsat is not None:
        _clean_mss(scene, bands, radsat)
    for values in bands.values():
        values[~inside] = np.nan
    if not has_data(bands):
        raise OSError(no_data_text())
    filled = None
    if fill:
        bands["lwir"], filled = s2.thermal_fill(bands, scene.tile[1:2])
    os.makedirs(folder, exist_ok=True)
    out = []
    for name in products:
        values = s2.product(name, bands, scene.mission)
        path = free_path(folder, s2.file_name(scene, name), ".tif")
        labels = [s2.band_label(scene, k) for k in s2.all_keys(scene)] \
            if name in MULTI else None
        _write(gdal, path, values, box, res, scene.epsg, labels)
        if name in s2.COMPOSITES or name in MULTI:
            ranges = [s2.stretch(band) for band in values]
        elif name == "lst":
            ranges = [s2.TEMPERATURE[0]]
        else:
            ranges = [s2.INDICES[name][1]]
        out.append((name, path, ranges, filled if name == "lst" else None))
    return out


def _build_aster(gdal, scene, ring, products, folder, sas):
    """Продукты ASTER: файлы VNIR, SWIR, TIR читаются целиком по окну
    участка без сглаживания (нет данных - 0), значения - core.aster.
    Продукты без файла сцены - у части сцен нет SWIR - пропускаются,
    если не осталось ни одного - OSError."""
    wanted = list(products)
    products = aster.available(products, scene.assets)
    if not products:
        raise OSError(tr("у сцены нет каналов SWIR для {names}",
                         names=", ".join(wanted)))
    xy = s2.ring_utm(ring, scene.epsg)
    res = s2.step_for(xy, scene.mission, products)
    box = s2.bounds(xy, res)
    keys = aster.needed(products, scene.assets)
    if scene.mission == aster.NASA_MISSION:
        # Файл на канал, адреса уже подписаны (SentinelDialog.
        # _start_nasa_build), ключ не нужен.
        groups = {k: [k] for k in keys}
        files = keys
        raw = dict(zip(files, executor("bands", BAND_WORKERS).map(
            lambda k: read_window(scene.assets[k].href, box, res,
                                  nearest=True), files)))
        raw = {k: (None if v is None else v[None]) for k, v in raw.items()}
    else:
        groups = aster.files_of(keys)
        counts = {"VNIR": 3, "SWIR": 6, "TIR": 5}
        files = list(groups)
        raw = dict(zip(files, executor("bands", BAND_WORKERS).map(
            lambda f: read_window(_href(scene, f, sas), box, res,
                                  nearest=True, count=counts[f]), files)))
    missing = [f for f, v in raw.items() if v is None]
    if missing:
        raise OSError(", ".join(missing))
    inside = s2.mask(xy, box, res)
    day = time.strptime(scene.when[:10], "%Y-%m-%d").tm_yday
    sun = scene.sun if scene.sun is not None else 45.0
    bands = {}
    for name, keys in groups.items():
        for key in keys:
            index = 0 if scene.mission == aster.NASA_MISSION \
                else aster.BANDS[key][1] - 1
            dn = raw[name][index]
            values = aster.value(dn, key, sun, day)
            values[~inside] = np.nan
            bands[key] = values
            if key in aster.THERMAL:
                lum = aster.radiance(dn, key)
                lum[~inside] = np.nan
                bands["L" + key[1:]] = lum
    if not has_data(bands):
        raise OSError(no_data_text())
    os.makedirs(folder, exist_ok=True)
    out = []
    for name in products:
        values = aster.product(name, bands)
        path = free_path(folder, s2.file_name(scene, name), ".tif")
        labels = [aster.label(k) for k in aster.ORDER if k in bands] \
            if name == "all_bands" else None
        _write(gdal, path, values, box, res, scene.epsg, labels)
        if name in aster.COMPOSITES or name == "all_bands":
            ranges = [s2.stretch(band) for band in values]
        else:
            ranges = [s2.stretch(values)]
        out.append((name, path, ranges, None))
    return out


def _build_modis(gdal, scene, raw, inside, products, folder, box, res):
    """Продукты MODIS: значения по core.modis.value, вне участка и под
    облаками - NaN."""
    os.makedirs(folder, exist_ok=True)
    out = []
    for name in products:
        key, scale, _ = modis.PRODUCTS[name]
        values = modis.value(name, raw[key])
        values[~inside] = np.nan
        path = free_path(folder, s2.file_name(scene, name), ".tif")
        _write(gdal, path, values, box, res, scene.epsg)
        out.append((name, path, [scale[0]]))
    return out


def _write(gdal, path, values, box, res, epsg, labels=None):
    """Массив (каналы, строки, столбцы) или (строки, столбцы) float32
    в GeoTIFF с рамкой box и шагом res, нет данных - NaN. labels -
    подписи каналов, их показывают свойства слоя QGIS."""
    from osgeo import osr
    values = values if values.ndim == 3 else values[None]
    driver = gdal.GetDriverByName("GTiff")
    ds = driver.Create(path, values.shape[2], values.shape[1],
                       values.shape[0], gdal.GDT_Float32,
                       options=["COMPRESS=DEFLATE", "PREDICTOR=3",
                                "TILED=YES"])
    ds.SetGeoTransform((box[0], res, 0.0, box[3], 0.0, -res))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(int(epsg))
    ds.SetProjection(srs.ExportToWkt())
    for n, band in enumerate(values, start=1):
        target = ds.GetRasterBand(n)
        target.SetNoDataValue(float("nan"))
        if labels and n <= len(labels):
            target.SetDescription(labels[n - 1])
        target.WriteArray(band)
    ds.FlushCache()
    ds = None


def build_links(scene, products, folder):
    """Сочетания всей сцены ссылкой VRT на файлы в сети: список
    (продукт, путь, пределы растяжения в значениях файла)."""
    gdal = _thread_gdal()
    os.makedirs(folder, exist_ok=True)
    out = []
    for name in products:
        if name not in s2.COMPOSITES:
            continue
        keys = s2.COMPOSITES[name]
        path = free_path(folder, s2.file_name(scene, name), ".vrt")
        gdal.PushErrorHandler("CPLQuietErrorHandler")
        try:
            try:
                ds = gdal.BuildVRT(path, ["/vsicurl/" + scene.assets[k].href
                                          for k in keys],
                                   separate=True, resolution="highest")
            except RuntimeError:
                ds = None
            if ds is None:
                raise OSError(name)
            ds = None
        finally:
            gdal.PopErrorHandler()
            _close_connections(gdal)
        lo, hi = LINK_RANGE.get(name, LINK_RANGE_OTHER)
        ranges = []
        for key in keys:
            asset = scene.assets[key]
            ranges.append(((lo - asset.offset) / asset.scale,
                           (hi - asset.offset) / asset.scale))
        out.append((name, path, ranges))
    return out


def _copy(href, path):
    """Файл в сети в файл на диске через GDAL, как каналы - прокси
    и сертификаты те же. Пишется во временный файл .part, готовый
    переименовывается. Рабочий поток. OSError, если не скачан."""
    gdal = _thread_gdal()
    part = path + ".part"
    gdal.PushErrorHandler("CPLQuietErrorHandler")
    try:
        try:
            handle = gdal.VSIFOpenL("/vsicurl/" + href, "rb")
        except RuntimeError:  # режим исключений GDAL
            handle = None
        if handle is None:
            raise OSError(os.path.basename(path))
        try:
            with open(part, "wb") as out:
                while True:
                    chunk = gdal.VSIFReadL(1, WHOLE_CHUNK, handle)
                    if not chunk:
                        break
                    out.write(chunk)
        finally:
            gdal.VSIFCloseL(handle)
    finally:
        gdal.PopErrorHandler()
        _close_connections(gdal)
    if os.path.getsize(part) == 0:
        os.remove(part)
        raise OSError(os.path.basename(path))
    os.replace(part, path)


def _file_name(href):
    """Имя файла по адресу без параметров запроса (ключ SAS, подпись)."""
    return os.path.basename(urlsplit(href).path)


def download_scene(scene, folder, sas="", progress=None):
    """Сцена целиком: исходные файлы каналов, маски облаков и метаданных
    (core.sentinel.whole_files) как есть в папку сцены и слой-набор VRT
    всех каналов. Уже скачанный файл не скачивается снова. progress -
    список [скачано, всего], его читает окно. Рабочий поток. Список
    [(«whole», путь VRT, пределы растяжения, показанные каналы)]."""
    keys = s2.whole_files(scene)
    if not keys:
        raise OSError(tr("у этого спутника сцена целиком не загружается"))
    place = os.path.join(folder, s2.file_name(scene, "scene"))
    os.makedirs(place, exist_ok=True)

    def fetch(key):
        # У MODIS у ключа кортеж адресов - файлы тайлов дня.
        hrefs = _href(scene, key, sas)
        plain = scene.assets[key].href
        if not isinstance(hrefs, tuple):
            hrefs, plain = (hrefs,), (plain,)
        paths = []
        for href, name in zip(hrefs, plain):
            path = os.path.join(place, _file_name(name))
            if not os.path.exists(path):
                _copy(href, path)
            paths.append(path)
        if progress is not None:
            progress[0] += 1
        return key, paths

    paths = dict(executor("bands", BAND_WORKERS).map(fetch, keys))
    gdal = _thread_gdal()
    bands = s2.whole_bands(scene)
    vrt = os.path.join(place, s2.file_name(scene, "scene") + ".vrt")
    gdal.PushErrorHandler("CPLQuietErrorHandler")
    try:
        sources = []
        for _, file, index, _ in bands:
            path = paths[file][0]
            if len(paths[file]) > 1:
                # Тайлы MODIS одного слоя - одна мозаика.
                path = os.path.join(place, file + ".vrt")
                gdal.BuildVRT(path, paths[file])
            elif scene.mission == aster.MISSION:
                # В файле группы ASTER несколько каналов, а набор берёт
                # из каждого источника первый - канал выносится в свой VRT.
                one = os.path.join(place, "{}_{}.vrt".format(
                    os.path.splitext(os.path.basename(path))[0], index))
                gdal.Translate(one, path, format="VRT", bandList=[index])
                path = one
            sources.append(path)
        ds = gdal.BuildVRT(vrt, sources, separate=True,
                           resolution="highest")
    except RuntimeError as error:  # режим исключений GDAL
        raise OSError(str(error)) from error
    finally:
        gdal.PopErrorHandler()
    if ds is None:
        raise OSError(os.path.basename(vrt))
    for n, (_, _, _, label) in enumerate(bands, start=1):
        ds.GetRasterBand(n).SetDescription(label)
    order = [b[0] for b in bands]
    # У MODIS сочетания цветов нет, слой показывает первый канал.
    shown = [order.index(k) + 1
             for k in s2.ALL_SHOWN.get(scene.mission, ()) if k in order] \
        or [1]
    ranges = [_whole_range(ds.GetRasterBand(n)) for n in shown]
    ds = None
    return [("whole", vrt, ranges, tuple(shown))]


def _whole_range(band):
    """Пределы растяжения канала всей сцены по уменьшенной копии:
    2-98 % значений без пустых и нулей."""
    scale = max(1, max(band.XSize, band.YSize) // WHOLE_SAMPLE)
    values = band.ReadAsArray(buf_xsize=max(1, band.XSize // scale),
                              buf_ysize=max(1, band.YSize // scale))
    values = values.astype(np.float32)
    nodata = band.GetNoDataValue()
    if nodata is not None:
        values[values == nodata] = np.nan
    values[values == 0] = np.nan
    return s2.stretch(values)


def no_data_text():
    return tr("участок за краем снимка сцены, в каналах нет данных. "
              "Каталог знает только рамку сцены, а полоса съёмки может "
              "не доходить до её углов.")


def has_data(bands):
    """В прочитанных каналах участка есть хоть одно значение. Участок
    за краем снимка сцены даёт одни пустые: каталог NASA знает только
    рамку сцены, а полоса съёмки ASTER повёрнута внутри неё."""
    return any(np.isfinite(v).any() for v in bands.values())


def style_gray(layer, limits, band=1):
    """Один канал в серой шкале, растяжение по limits (нижний, верхний)."""
    renderer = QgsSingleBandGrayRenderer(layer.dataProvider(), band)
    enhancement = QgsContrastEnhancement(
        layer.dataProvider().dataType(band))
    enhancement.setContrastEnhancementAlgorithm(STRETCH)
    enhancement.setMinimumValue(limits[0])
    enhancement.setMaximumValue(limits[1])
    renderer.setContrastEnhancement(enhancement)
    layer.setRenderer(renderer)


def style_composite(layer, ranges, bands=(1, 2, 3)):
    """Сочетание трёх каналов с растяжением ranges. bands - каналы
    файла на красный, зелёный и синий, ranges - их пределы."""
    provider = layer.dataProvider()
    renderer = QgsMultiBandColorRenderer(provider, *bands)
    kind = provider.dataType(1)
    setters = (renderer.setRedContrastEnhancement,
               renderer.setGreenContrastEnhancement,
               renderer.setBlueContrastEnhancement)
    for setter, (lo, hi) in zip(setters, ranges):
        contrast = QgsContrastEnhancement(kind)
        contrast.setMinimumValue(lo)
        contrast.setMaximumValue(hi)
        contrast.setContrastEnhancementAlgorithm(STRETCH)
        setter(contrast)
    layer.setRenderer(renderer)


def style_ratio(layer, lo, hi):
    """Отношение каналов ASTER шкалой core.aster.RAMP на пределах
    растяжения по участку."""
    ramp = QgsColorRampShader(lo, hi)
    ramp.setColorRampItemList([
        QgsColorRampShader.ColorRampItem(lo + share * (hi - lo),
                                         QColor(*rgb),
                                         "{:.3g}".format(lo + share
                                                         * (hi - lo)))
        for share, rgb in aster.RAMP])
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(ramp)
    renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1,
                                                shader)
    renderer.setClassificationMin(lo)
    renderer.setClassificationMax(hi)
    layer.setRenderer(renderer)


def style_index(layer, name):
    """Индекс шкалой цветов core.sentinel.INDICES, температура -
    шкалой core.sentinel.TEMPERATURE, продукты MODIS - своими шкалами
    core.modis.PRODUCTS, классы - без переходов."""
    discrete = False
    if name in modis.PRODUCTS:
        _, ((lo, hi), stops), discrete = modis.PRODUCTS[name]
    elif name == "lst":
        (lo, hi), stops = s2.TEMPERATURE
    else:
        _, (lo, hi), stops = s2.INDICES[name]
    ramp = QgsColorRampShader(lo, hi)
    if discrete:
        # В QGIS 3.36 перечисления Qgis.ShaderInterpolationMethod нет,
        # там плоское имя класса шейдера.
        method = getattr(Qgis, "ShaderInterpolationMethod", None)
        ramp.setColorRampType(method.Exact if method is not None
                              else getattr(QgsColorRampShader, "Exact"))
    ramp.setColorRampItemList([
        QgsColorRampShader.ColorRampItem(value, QColor(*rgb),
                                         "{:g}".format(value))
        for value, rgb in stops])
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(ramp)
    renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1,
                                                shader)
    renderer.setClassificationMin(lo)
    renderer.setClassificationMax(hi)
    layer.setRenderer(renderer)


class SentinelDialog(QDialog):
    """Окно снимков Sentinel-2 участка. window - окно глобуса."""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.globe = window
        self.setWindowTitle(tr("Космоснимки"))
        self.setModal(False)
        # Ключ SAS коллекции нынешнего спутника и момент, после которого
        # он просится заново. Ключи коллекций - в sas_keys.
        self.sas = ""
        self.sas_until = 0.0
        self.sas_keys = {}
        self.sas_mission = ""  # адрес службы ключа, который просится
        self.sas_reply = None
        self.sas_waiting = []
        self.sas_tries = 0
        self.searched = "sentinel2"
        self.modern_dates = None  # даты поиска до перехода на MSS
        self.signing = None  # подпись адресов файлов ASTER NASA
        self.point = None  # (широта, долгота) или None
        self.ring = None  # кольцо участка (широта, долгота)
        self.area_name = ""
        self.scenes = []
        self.clouds = {}  # номер сцены - (облачность, доля с данными)
        self.generation = 0
        self.reply = None
        self.preview_job = None
        self.build_job = None
        self.progress = None  # [скачано, всего] у сцены целиком
        self.cloud_jobs = []
        self.series = None  # окно «Ряд по датам»
        self.timer = QTimer(self)
        self.timer.setInterval(POLL)
        self.timer.timeout.connect(self._poll)
        self._layout()

    def _layout(self):
        self.where = QLabel(self)
        self.where.setWordWrap(True)
        self.mission = QComboBox(self)
        for key in MISSIONS:
            self.mission.addItem(mission_title(key), key)
        self.mission.setToolTip(tr(
            "Sentinel-2 - 10 м, снимки с 2015 года, каждые 5 суток. "
            "Landsat - 30 м, снимки с 1982 года и тепловой канал, у Landsat "
            "7 после мая 2003 года на снимках пустые полосы. Landsat 1-5 "
            "MSS - 60 м, снимки 1972-1993 годов, четыре канала без "
            "синего и теплового. ASTER - 15-90 м, 14 каналов, снимки "
            "2000-2006 годов, минеральные индексы. MODIS - "
            "готовые продукты NASA с 2000 года, сцена - день или период, "
            "пиксель 250-1000 м. Смена спутника запускает новый поиск."))
        self.mission.currentIndexChanged.connect(
            lambda *_: self._mission_changed())
        self.side = QDoubleSpinBox(self)
        self.side.setRange(0.2, 100.0)
        self.side.setDecimals(1)
        self.side.setSuffix(tr(" км"))
        self.side.setValue(SIDE_DEFAULT)
        self.side.setToolTip(tr(
            "Сторона квадрата участка вокруг точки. При открытии окна она "
            "равна ширине видимой полосы глобуса. По участку считается "
            "облачность и обрезаются снимки. Больше участок - дольше "
            "загрузка каналов."))
        self.side_label = QLabel(tr("Сторона участка"), self)
        today = QDate.currentDate()
        self.start = QDateEdit(today.addYears(-1), self)
        self.end = QDateEdit(today, self)
        for edit in (self.start, self.end):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd")
        self.start.setToolTip(tr("Первый день съёмки в поиске."))
        self.end.setToolTip(tr("Последний день съёмки в поиске."))
        self.scene_cloud = QSpinBox(self)
        self.scene_cloud.setRange(0, 100)
        self.scene_cloud.setSuffix(" %")
        self.scene_cloud.setValue(SCENE_CLOUD_DEFAULT)
        self.scene_cloud.setToolTip(tr(
            "Наибольшая облачность всей сцены по оценке поставщика снимков, "
            "у Sentinel-2 сцена 110 × 110 км, у Landsat 185 × 180 км. Это "
            "отсев до расчёта облачности над участком. Сцена с облаками "
            "бывает чистой над участком."))
        self.area_cloud = QSpinBox(self)
        self.area_cloud.setRange(0, 100)
        self.area_cloud.setSuffix(" %")
        self.area_cloud.setValue(AREA_CLOUD_DEFAULT)
        self.area_cloud.setToolTip(tr(
            "Наибольшая доля облаков и их теней над участком по маске "
            "облаков сцены. Сцены облачнее в списке скрыты."))
        self.area_cloud.valueChanged.connect(self._filter)
        find = QPushButton(tr("Найти"), self)
        find.clicked.connect(lambda _=False: self.search())
        mission_row = QHBoxLayout()
        mission_row.addWidget(QLabel(tr("Спутник"), self))
        mission_row.addWidget(self.mission, 1)
        grid = QGridLayout()
        grid.addWidget(self.side_label, 0, 0)
        grid.addWidget(self.side, 0, 1)
        grid.addWidget(QLabel(tr("Съёмка с"), self), 1, 0)
        grid.addWidget(self.start, 1, 1)
        grid.addWidget(QLabel(tr("по"), self), 1, 2)
        grid.addWidget(self.end, 1, 3)
        grid.addWidget(QLabel(tr("Облачность сцены до"), self), 2, 0)
        grid.addWidget(self.scene_cloud, 2, 1)
        grid.addWidget(QLabel(tr("над участком до"), self), 2, 2)
        grid.addWidget(self.area_cloud, 2, 3)
        grid.addWidget(find, 2, 4)
        self.list = QTreeWidget(self)
        self.list.setRootIsDecorated(False)
        self.list.setHeaderLabels([tr("Дата, UTC"), tr("Над участком"),
                                   tr("Сцена"), tr("Солнце"), tr("Тайл")])
        self.list.currentItemChanged.connect(self._chosen)
        self.list.itemDoubleClicked.connect(lambda *a: self.add())
        self.preview = QLabel(self)
        self.preview.setFixedSize(PREVIEW, PREVIEW)
        self.preview.setAlignment(enum(Qt, "AlignmentFlag", "AlignCenter"))
        middle = QHBoxLayout()
        middle.addWidget(self.list, 1)
        middle.addWidget(self.preview)
        self.products = QListWidget(self)
        self._fill_products()
        self.products.setMaximumHeight(130)
        self.products.setToolTip(tr(
            "Сочетания каналов - картинка из трёх каналов отражения, "
            "индексы - нормированная разность двух каналов со шкалой "
            "цветов. Каждый отмеченный продукт ложится своим слоем."))
        self.clear = QCheckBox(tr("Облака и тени - пусто"), self)
        self.clear.setChecked(True)
        self.clear.setToolTip(tr(
            "Пиксели облаков, их теней и перистых облаков по маске "
            "облаков сцены остаются пустыми, индексы по ним не "
            "считаются."))
        self.fill = QCheckBox(tr("Дыры температуры - по формуле"), self)
        self.fill.setChecked(True)
        self.fill.setVisible(False)  # только у Landsat, _mission_changed
        self.fill.setToolTip(tr(
            "USGS не считает температуру там, где нет излучательной "
            "способности из базы ASTER GED, на большей части России это "
            "половина участка и больше. С флажком такие пиксели считаются "
            "той же формулой USGS из излучения и атмосферы сцены, "
            "излучательная способность - по NDVI. Где USGS посчитал, "
            "отличие в среднем меньше 0.5 °C."))
        self.mode = QComboBox(self)
        self.mode.addItem(tr("Обрезка по участку, GeoTIFF"), "clip")
        self.mode.addItem(tr("Вся сцена по ссылке, без скачивания"), "link")
        self.mode.addItem(tr("Вся сцена, исходные файлы"), "whole")
        self.mode.setToolTip(tr(
            "Обрезка загружает только участок, значения - отражение, "
            "файлы годятся для расчётов. Ссылка показывает всю сцену "
            "Sentinel-2 из сети, данные загружаются при показе, индексы "
            "так не строятся. Исходные файлы - все каналы сцены, маска "
            "облаков и метаданные как есть, в папку сцены, и слой-набор "
            "всех каналов. Сцена Sentinel-2 весит около 1 ГБ."))
        self.folder = os.path.join(QgsProject.instance().homePath()
                                   or os.path.expanduser("~"), "sentinel")
        self.folder_label = QLabel(self)
        self.folder_label.setWordWrap(True)
        choose = QPushButton(tr("Папка…"), self)
        choose.clicked.connect(lambda _=False: self._choose_folder())
        out_row = QHBoxLayout()
        out_row.addWidget(self.mode)
        out_row.addWidget(self.clear)
        out_row.addWidget(self.fill)
        out_row.addStretch(1)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_label, 1)
        folder_row.addWidget(choose)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        credit = self.credit = QLabel(mission_credit("sentinel2"), self)
        credit.setWordWrap(True)
        self.add_button = QPushButton(tr("В проект QGIS"), self)
        self.add_button.setToolTip(tr(
            "Отмеченные продукты выбранной сцены - слоями проекта в группу "
            "дня внутри группы «Sentinel-2». Слои видны на карте и на "
            "глобусе."))
        self.add_button.setEnabled(False)
        self.add_button.clicked.connect(lambda _=False: self.add())
        self.series_button = QPushButton(tr("Ряд по датам…"), self)
        self.series_button.setToolTip(tr(
            "График индекса или температуры участка по всем сценам списка - "
            "медиана участка без облаков на каждую дату. Щелчок по точке "
            "графика выбирает сцену в списке. У сочетаний каналов и у "
            "ASTER ряда нет."))
        self.series_button.setEnabled(False)
        self.series_button.clicked.connect(lambda _=False: self.open_series())
        buttons = QDialogButtonBox(
            enum(QDialogButtonBox, "StandardButton", "Close"), self)
        buttons.rejected.connect(self.close)
        buttons.addButton(self.series_button,
                          enum(QDialogButtonBox, "ButtonRole", "ActionRole"))
        buttons.addButton(self.add_button,
                          enum(QDialogButtonBox, "ButtonRole", "ActionRole"))
        layout = QVBoxLayout(self)
        layout.addWidget(self.where)
        layout.addLayout(mission_row)
        layout.addLayout(grid)
        layout.addLayout(middle, 1)
        layout.addWidget(self.products)
        layout.addLayout(out_row)
        layout.addLayout(folder_row)
        layout.addWidget(self.status)
        layout.addWidget(credit)
        layout.addWidget(buttons)
        self._show_folder()
        self.resize(760, 640)

    @staticmethod
    def pool():
        """Общий пул окна - облачность, превью, сборка."""
        return executor("scenes", CLOUD_WORKERS)

    def current_mission(self):
        return self.mission.currentData() or "sentinel2"

    def _fill_products(self):
        """Строки продуктов спутника, отметки прежних сохраняются."""
        checked = set(self.chosen_products()) if self.products.count() \
            else set(DEFAULT_PRODUCTS)
        mission = self.current_mission()
        if not checked & set(s2.products_of(mission)):
            checked = set(s2.products_of(mission)) if modis.is_modis(
                mission) else set(DEFAULT_PRODUCTS)
        if aster.is_aster(mission) and not checked & set(aster.DEFAULT):
            checked = set(aster.DEFAULT)
        names = titles(mission)
        self.products.clear()
        for key in s2.products_of(mission):
            item = QListWidgetItem(names[key])
            item.setData(SCENE_ROLE, key)
            if key == "lst":
                item.setToolTip(tr(
                    "Температура поверхности из продукта USGS Collection 2 "
                    "Level-2 - не радиационная температура. USGS уже учёл "
                    "излучательную способность поверхности по ASTER GED "
                    "и атмосферу. Модуль только переводит кельвины "
                    "в градусы Цельсия."))
            elif key == "all_bands":
                item.setToolTip(tr(
                    "Все каналы сцены одним файлом по порядку номеров, "
                    "отражение, тепловой канал Landsat - в кельвинах. "
                    "У Sentinel-2 12 каналов на шаге 10 м, участок со "
                    "стороной больше 20 км - на шаге 20 м. Слой показывает "
                    "естественные цвета, подписи каналов видны в свойствах "
                    "слоя QGIS."))
            elif key in aster.RATIOS:
                item.setToolTip(tr(
                    "Отношение каналов ASTER, принятое в поисках руд "
                    "(Rowan, Mars 2003, Ninomiya 2003) - (4 + 6) / 5 "
                    "выделяет каолинит и алунит, (5 + 7) / 6 - серицит "
                    "и мусковит, (7 + 9) / 8 - карбонаты, хлорит и эпидот, "
                    "2 / 1 - оксиды железа, кварцевый индекс - кварц по "
                    "тепловым каналам. Шкала растянута по участку, тёплые "
                    "цвета - больше минерала."))
            elif key == "mss_bands":
                item.setToolTip(tr(
                    "Зелёный, красный и два ближних инфракрасных канала "
                    "MSS одним файлом, отражение на верху атмосферы. "
                    "Слой показывает ложные цвета, остальные сочетания "
                    "задаются в свойствах слоя QGIS."))
            item.setFlags(item.flags()
                          | enum(Qt, "ItemFlag", "ItemIsUserCheckable"))
            item.setCheckState(enum(Qt, "CheckState", "Checked")
                               if key in checked else
                               enum(Qt, "CheckState", "Unchecked"))
            self.products.addItem(item)

    def use_mission(self, mission):
        """Спутник окна без поиска - поиск запустит новый участок.
        Действия строки «Поиск» по словам «MSS», «ASTER»."""
        index = self.mission.findData(mission)
        if index < 0 or index == self.mission.currentIndex():
            return
        self.mission.blockSignals(True)
        self.mission.setCurrentIndex(index)
        self.mission.blockSignals(False)
        self._mission_changed(search=False)

    def _mission_changed(self, search=True):
        """Другой спутник: продукты, подпись, режим выдачи, новый
        поиск. Ключ SAS Landsat живёт час, и слой ссылкой из
        сохранённого проекта потом не открылся бы, поэтому у Landsat
        только обрезка по участку."""
        mission = self.current_mission()
        self._fill_products()
        self.credit.setText(mission_credit(mission))
        link = self.mode.model().item(1)
        if link is not None:
            link.setEnabled(mission == "sentinel2")
        if self.mode.currentData() == "link" and mission != "sentinel2":
            self.mode.setCurrentIndex(0)
        # У MODIS облачности сцены в каталоге нет.
        self.scene_cloud.setEnabled(not modis.is_modis(mission))
        self.fill.setVisible(mission == "landsat")
        # У ASTER L1T маски облаков нет.
        self.clear.setEnabled(not aster.is_aster(mission))
        self._fit_dates(mission)
        if search:
            self.search()

    def _fit_dates(self, mission):
        """Даты поиска под годы спутника (ERA): у MSS промежуток позже
        2013 года пуст, он заменяется летом 1975 года, у ASTER - всеми
        2000-2006 годами. Прежние даты возвращаются при уходе на
        спутник, который снимает и сейчас."""
        era = ERA.get(mission)
        last = QDate.fromString(era[0], "yyyy-MM-dd") if era else None
        if era and self.start.date() > last:
            if self.modern_dates is None:
                self.modern_dates = (self.start.date(), self.end.date())
            self.start.setDate(QDate.fromString(era[1][0], "yyyy-MM-dd"))
            self.end.setDate(QDate.fromString(era[1][1], "yyyy-MM-dd"))
        elif mission == aster.NASA_MISSION and self.end.date() \
                < QDate.fromString(aster.NASA_FIRST, "yyyy-MM-dd"):
            # После ASTER 2000-2006 годов - прежние даты или год до
            # сегодня: у NASA сцены с 2007 года.
            if self.modern_dates is not None:
                self.start.setDate(self.modern_dates[0])
                self.end.setDate(self.modern_dates[1])
                self.modern_dates = None
            else:
                today = QDate.currentDate()
                self.start.setDate(today.addYears(-1))
                self.end.setDate(today)
        elif not era and self.modern_dates is not None:
            self.start.setDate(self.modern_dates[0])
            self.end.setDate(self.modern_dates[1])
            self.modern_dates = None

    # Ключ SAS Planetary Computer.

    def _token_url(self, mission):
        """Адрес службы ключа: по хранилищу файлов найденных сцен, до
        поиска - по коллекции (core.sentinel.sas_url)."""
        href = None
        for s in self.scenes:
            if s.mission == mission and s.assets:
                href = next(iter(s.assets.values())).href
                break
        return s2.sas_url(mission, href)

    def with_token(self, action):
        """action с действующим ключом SAS - для окна ряда."""
        self._with_token(action)

    def _with_token(self, action):
        """Выполнить action, когда есть действующий ключ SAS хранилища
        файлов спутника. У Sentinel-2 ключ не нужен."""
        mission = self.current_mission()
        if not s2.needs_key(mission):
            action()
            return
        url = self._token_url(mission)
        self.sas, self.sas_until = self.sas_keys.get(url, ("", 0.0))
        if self.sas and time.monotonic() < self.sas_until:
            action()
            return
        self.sas_mission = url
        self.sas_waiting.append(action)
        if self.sas_reply is None:
            self.sas_tries = 0
            self._ask_token()

    def _ask_token(self):
        self.sas_tries += 1
        self.status.setText(tr("Запрос ключа доступа к файлам…"))
        self.sas_reply = fetch_bytes(self.sas_mission, self._token_done,
                                     fresh=True)

    def _token_done(self, data, error):
        self.sas_reply = None
        sas = ""
        if data is not None and not error:
            try:
                sas = str(json.loads(bytes(data).decode("utf-8"))
                            .get("token") or "")
            except (ValueError, UnicodeDecodeError, AttributeError):
                sas = ""
        if not sas:
            if self.sas_tries < SAS_TRIES:
                QTimer.singleShot(SAS_PAUSE, self._ask_token)
                return
            self.sas_waiting = []
            self.add_button.setEnabled(
                self._scene(self.list.currentItem()) is not None)
            self.status.setText(tr(
                "Служба ключей Planetary Computer не ответила: {error}. "
                "Повторите поиск позже.", error=error or "-"))
            return
        self.sas = sas
        self.sas_until = time.monotonic() + SAS_LIFE
        self.sas_keys[self.sas_mission] = (self.sas, self.sas_until)
        waiting, self.sas_waiting = self.sas_waiting, []
        for action in waiting:
            action()

    # Участок.

    def show_point(self, lat, lon, width=None):
        """Участок - квадрат вокруг точки, сразу поиск. width - ширина
        видимой полосы глобуса в метрах, по ней сторона квадрата."""
        if width is not None:
            self.side.setValue(s2.side_for_view(width))
        self.point = (lat, lon)
        self.area_name = tr("Точка {lat}, {lon}", lat="{:.5f}".format(lat),
                            lon="{:.5f}".format(lon))
        self._area_changed(True)

    def show_place(self, place, width=None):
        """Участок - метка «Моих меток»: многоугольник своим контуром,
        путь - рамкой точек, точка - квадратом."""
        points = list(place.shape.points)
        if place.kind == "point" or len(points) < 2:
            self.show_point(*points[0], width=width)
            self.area_name = place.name or self.area_name
            self.where.setText(self.area_name)
            return
        self.point = None
        if place.kind == "polygon" and len(points) >= 3:
            self.ring = points
        else:
            lats = [p[0] for p in points]
            lons = [p[1] for p in points]
            self.ring = [(min(lats), min(lons)), (min(lats), max(lons)),
                         (max(lats), max(lons)), (max(lats), min(lons))]
        self.area_name = place.name or tr("Метка")
        self._area_changed(False)

    def _area_changed(self, point):
        self.side.setVisible(point)
        self.side_label.setVisible(point)
        self.where.setText(tr("Участок: {name}", name=self.area_name))
        self.search()

    def _current_ring(self):
        if self.point is not None:
            return s2.square(self.point[0], self.point[1],
                             self.side.value() * 1000.0)
        return self.ring

    def _choose_folder(self):
        path = QFileDialog.getExistingDirectory(
            self, tr("Папка снимков"), self.folder)
        if path:
            self.folder = path
            self._show_folder()

    def _show_folder(self):
        self.folder_label.setText(tr("Папка файлов: {path}",
                                     path=self.folder))

    # Поиск.

    def search(self):
        """Новый поиск: сцены участка за промежуток дат."""
        ring = self._current_ring()
        if ring is None:
            return
        self.ring_used = ring
        self.generation += 1
        self._stop_jobs()
        self.scenes = []
        self.clouds = {}
        self.list.clear()
        self.preview.clear()
        self.add_button.setEnabled(False)
        self.series_button.setEnabled(False)
        self.searched = self.current_mission()
        body = s2.search_body(
            s2.geojson(ring), self.start.date().toString("yyyy-MM-dd"),
            self.end.date().toString("yyyy-MM-dd"),
            self.scene_cloud.value(), mission=self.searched)
        self.status.setText(tr("Поиск сцен…"))
        if self.searched == aster.NASA_MISSION:
            generation = self.generation
            self.reply = fetch_bytes(
                aster.cmr_url(ring, self.start.date().toString("yyyy-MM-dd"),
                              self.end.date().toString("yyyy-MM-dd"),
                              self.scene_cloud.value()),
                lambda data, error: self._cmr_page(data, error, generation),
                fresh=True)
            return
        self._ask(body, self.generation)

    def _cmr_page(self, data, error, generation):
        """Ответ каталога NASA CMR. Маски облаков у ASTER нет, файлы
        по ключу - облачность над участком равна облачности сцены
        и считается сразу, без чтения файлов."""
        self.reply = None
        if generation != self.generation:
            return
        try:
            parsed = json.loads(bytes(data).decode("utf-8")) \
                if data is not None and not error else None
        except (ValueError, UnicodeDecodeError):
            parsed = None
        if parsed is None:
            self.status.setText(tr("Каталог не ответил: {error}",
                                   error=error or "-"))
            return
        self.scenes = s2.cmr_scenes(parsed)
        for s in self.scenes:
            self._row(s)
            self.clouds[s.id] = (s.cloud, 100.0)
            self._mark(s.id)
        self._summary()

    def _ask(self, body, generation):
        self.reply = post_json(
            s2.SEARCHES[self.searched],
            {"Content-Type": "application/json",
             "Accept": "application/geo+json"}, body,
            lambda data, error, g=generation: self._page(data, error, g))

    def _page(self, data, error, generation):
        self.reply = None
        if generation != self.generation:
            return
        if data is None or error:
            self.status.setText(tr("Каталог не ответил: {error}",
                                   error=error or "-"))
            return
        scenes, following = s2.parse_page(data)
        self.scenes += scenes
        grouped = modis.is_modis(self.searched)
        if not grouped:
            for s in scenes:
                self._row(s)
        if following and len(self.scenes) < s2.MAX_SCENES:
            self._ask(following, generation)
            return
        if grouped:
            # Тайлы одного дня - одна сцена, система вывода - UTM
            # середины участка.
            epsg = modis.utm_epsg(self.ring_used)
            self.scenes = [s._replace(epsg=epsg) for s in
                           modis.merge_tiles(self.scenes)]
            for s in self.scenes:
                self._row(s)
        self.status.setText(tr(
            "Найдено сцен {count}, считается облачность над участком…",
            count=len(self.scenes)))
        self._with_token(lambda: self._start_clouds(generation))

    def _row(self, s):
        item = QTreeWidgetItem([s.when, "…", "-" if modis.is_modis(
            s.mission) else "{:.0f} %".format(s.cloud),
                                "{:.0f}°".format(s.sun)
                                if s.sun is not None else "-", s.tile])
        item.setData(0, SCENE_ROLE, s.id)
        self.list.addTopLevelItem(item)

    def _start_clouds(self, generation):
        if generation != self.generation:
            return
        self.status.setText(tr(
            "Найдено сцен {count}, считается облачность над участком…",
            count=len(self.scenes)))
        warm()
        ring = self.ring_used
        self.cloud_jobs = [(generation, self.pool().submit(
            scene_cloud, s, ring, self.sas)) for s in self.scenes]
        self.timer.start()

    def _poll(self):
        counting = bool(self.cloud_jobs)
        pending = []
        for generation, job in self.cloud_jobs:
            if not job.done():
                pending.append((generation, job))
                continue
            if generation != self.generation:
                continue
            try:
                number, cloud, valid = job.result()
            except (RuntimeError, ValueError, OSError):
                # Сцена остаётся с «…» в столбце облачности.
                number = None
            if number is not None:
                self.clouds[number] = (cloud, valid)
                self._mark(number)
        self.cloud_jobs = pending
        if self.preview_job is not None and self.preview_job[1].done():
            self._preview_done()
        if self.build_job is not None and self.build_job[1].done():
            self._built()
        elif self.build_job is not None and self.progress:
            self.status.setText(tr(
                "Скачивание файлов сцены {when}: {done} из {total}…",
                when=self.build_job[0].when, done=self.progress[0],
                total=self.progress[1]))
        if not self.cloud_jobs and self.preview_job is None \
                and self.build_job is None:
            self.timer.stop()
        if counting and not pending:
            self._summary()

    def _mark(self, number):
        for n in range(self.list.topLevelItemCount()):
            item = self.list.topLevelItem(n)
            if item.data(0, SCENE_ROLE) != number:
                continue
            cloud, valid = self.clouds[number]
            if cloud is None:
                item.setText(1, "?")
            elif valid < 50.0:
                item.setText(1, tr("{cloud} %, данных {valid} %",
                                   cloud="{:.0f}".format(cloud),
                                   valid="{:.0f}".format(valid)))
            else:
                item.setText(1, "{:.0f} %".format(cloud))
            self._filter_item(item)
            if cloud is not None and not item.isHidden() \
                    and series_core.products(self.searched):
                # Ряд строится и по части списка, пока облачность
                # остальных сцен считается.
                self.series_button.setEnabled(True)
            if self.list.currentItem() is None and not item.isHidden():
                self.list.setCurrentItem(item)

    def _filter_item(self, item):
        cloud, valid = self.clouds.get(item.data(0, SCENE_ROLE),
                                       (None, None))
        hidden = cloud is not None and (
            cloud > self.area_cloud.value()
            or valid < s2.min_valid(self.searched))
        item.setHidden(bool(hidden))

    def _filter(self, *args):
        for n in range(self.list.topLevelItemCount()):
            self._filter_item(self.list.topLevelItem(n))
        self.series_button.setEnabled(
            bool(series_core.products(self.searched))
            and bool(self.series_scenes()))
        if self.scenes and not self.cloud_jobs:
            self._summary()

    def _summary(self):
        shown = sum(not self.list.topLevelItem(n).isHidden()
                    for n in range(self.list.topLevelItemCount()))
        self.status.setText(tr(
            "Сцен {total}, над участком не облачнее {cloud} % - {count}.",
            total=len(self.scenes), cloud=self.area_cloud.value(),
            count=shown))
        self.series_button.setEnabled(
            bool(series_core.products(self.searched))
            and bool(self.series_scenes()))

    def series_scenes(self):
        """Сцены ряда: видимые в списке, облачность над участком
        посчитана."""
        out = []
        for n in range(self.list.topLevelItemCount()):
            item = self.list.topLevelItem(n)
            s = self._scene(item)
            if s is None or item.isHidden():
                continue
            if self.clouds.get(s.id, (None, None))[0] is None:
                continue
            out.append(s)
        return out

    def open_series(self):
        """Окно «Ряд по датам» по сценам списка."""
        products = series_core.products(self.searched)
        scenes = self.series_scenes()
        if not products or not scenes:
            return
        if self.series is None:
            from .series import SeriesDialog
            self.series = SeriesDialog(self)
        self.series.show_series(self.searched, scenes, products,
                                titles(self.searched), self.area_name)
        self.series.show()
        self.series.raise_()

    def select_scene(self, number):
        """Сцена number - текущей строкой списка, её превью."""
        for n in range(self.list.topLevelItemCount()):
            item = self.list.topLevelItem(n)
            if item.data(0, SCENE_ROLE) == number:
                self.list.setCurrentItem(item)
                self.list.scrollToItem(item)
                return

    def _scene(self, item):
        number = item.data(0, SCENE_ROLE) if item is not None else None
        return next((s for s in self.scenes if s.id == number), None)

    def _chosen(self, item, previous=None):
        s = self._scene(item)
        self.add_button.setEnabled(s is not None)
        self.preview.clear()
        if s is None:
            return
        self._with_token(lambda: self._start_preview(s))

    def _start_preview(self, s):
        warm()
        self.preview_job = (s.id, self.pool().submit(preview, s,
                                                   self.ring_used,
                                                   self.sas))
        self.timer.start()

    def _preview_done(self):
        number, job = self.preview_job
        self.preview_job = None
        current = self._scene(self.list.currentItem())
        try:
            rgb = job.result()
        except (RuntimeError, ValueError, OSError):
            rgb = None
        if rgb is None or current is None or current.id != number:
            return
        rgb = np.ascontiguousarray(np.transpose(rgb[:3], (1, 2, 0)))
        height, width = rgb.shape[:2]
        image = QImage(rgb.data, width, height, 3 * width,
                       enum(QImage, "Format", "Format_RGB888")).copy()
        self.preview.setPixmap(QPixmap.fromImage(image).scaled(
            PREVIEW, PREVIEW, enum(Qt, "AspectRatioMode", "KeepAspectRatio"),
            enum(Qt, "TransformationMode", "SmoothTransformation")))

    # Выдача.

    def chosen_products(self):
        out = []
        for n in range(self.products.count()):
            item = self.products.item(n)
            if item.checkState() == enum(Qt, "CheckState", "Checked"):
                out.append(item.data(SCENE_ROLE))
        return out

    def add(self, folder=None):
        """Отмеченные продукты выбранной сцены в проект. Расчёт - в
        рабочем потоке, слои - по готовности."""
        s = self._scene(self.list.currentItem())
        products = self.chosen_products()
        if s is None or self.build_job is not None:
            return
        if not products and self.mode.currentData() != "whole":
            self.status.setText(tr("Не отмечено ни одного продукта."))
            return
        folder = folder or self.folder
        self.add_button.setEnabled(False)
        self._with_token(lambda: self._start_build(s, products, folder))

    # ASTER NASA после 2006 года: ключ Earthdata и подписанные адреса.

    def earthdata_token(self, ask=True):
        """Ключ Earthdata из настроек, при ask и пустом - окно ввода.
        Пустая строка - ключа нет."""
        token = str(QgsSettings().value(EARTHDATA_KEY, "") or "").strip()
        if token or not ask:
            return token
        text, ok = QInputDialog.getText(
            self, tr("Ключ NASA Earthdata"),
            tr("Снимки ASTER после 2006 года NASA отдаёт только по ключу "
               "Earthdata. Учётная запись бесплатная - "
               "urs.earthdata.nasa.gov, ключ создаёт раздел «Generate "
               "Token» профиля, он живёт 60 дней. Ключ хранится "
               "в настройках QGIS этого компьютера.\n\nКлюч:"),
            enum(QLineEdit, "EchoMode", "Password"))
        token = str(text or "").strip() if ok else ""
        if token:
            QgsSettings().setValue(EARTHDATA_KEY, token)
        return token

    def _start_nasa_build(self, s, products, folder, whole=False):
        products = aster.available(products, s.assets)
        if not products and not whole:
            self.status.setText(tr(
                "У сцены нет каналов для отмеченных продуктов - после 2008 "
                "года у ASTER только каналы VNIR и TIR."))
            self.add_button.setEnabled(True)
            return
        token = self.earthdata_token()
        if not token:
            self.status.setText(tr("Без ключа Earthdata файлы NASA "
                                   "не загружаются."))
            self.add_button.setEnabled(True)
            return
        keys = s2.whole_files(s) if whole \
            else aster.needed(products, s.assets)
        self.signing = {"scene": s, "keys": keys, "urls": {},
                        "products": products, "folder": folder,
                        "replies": [], "whole": whole}
        self.status.setText(tr("Адреса файлов NASA…"))
        for key in keys:
            self.signing["replies"].append(resolve_redirect(
                s.assets[key].href, {"Authorization": "Bearer " + token},
                lambda url, error, k=key, job=self.signing:
                self._signed(job, k, url, error)))

    def _signed(self, job, key, url, error):
        """Подписанный адрес файла канала пришёл. Переадресация на
        страницу входа - ключ не принят, он стирается из настроек."""
        if job is not self.signing:
            return
        if url is None or aster.LOGIN_HOST in url:
            self.signing = None
            self.add_button.setEnabled(True)
            if url is not None:
                QgsSettings().remove(EARTHDATA_KEY)
                self.status.setText(tr(
                    "Ключ Earthdata не принят - устарел или неверен. "
                    "При следующей загрузке окно спросит новый."))
            else:
                self.status.setText(tr("Файл NASA не получен: {error}",
                                       error=error or "-"))
            return
        job["urls"][key] = url
        if len(job["urls"]) < len(job["keys"]):
            return
        self.signing = None
        s = job["scene"]
        assets = dict(s.assets)
        for k, href in job["urls"].items():
            assets[k] = assets[k]._replace(href=href)
        warm()
        signed = s._replace(assets=assets)
        if job["whole"]:
            self.progress = [0, len(job["keys"])]
            build_job = self.pool().submit(download_scene, signed,
                                           job["folder"], "", self.progress)
        else:
            build_job = self.pool().submit(build, signed, self.ring_used,
                                           job["products"], job["folder"],
                                           False, "", False)
        self.build_job = (s, build_job)
        self.status.setText(tr("Загрузка каналов сцены {when}…",
                               when=s.when))
        self.timer.start()

    def _start_build(self, s, products, folder):
        whole = self.mode.currentData() == "whole"
        self.progress = None
        if s.mission == aster.NASA_MISSION:
            self._start_nasa_build(s, products, folder, whole)
            return
        warm()
        if whole:
            self.progress = [0, len(s2.whole_files(s))]
            job = self.pool().submit(download_scene, s, folder, self.sas,
                                     self.progress)
        elif self.mode.currentData() == "link" and s.mission == "sentinel2":
            job = self.pool().submit(build_links, s, products, folder)
        else:
            job = self.pool().submit(build, s, self.ring_used, products,
                                   folder, self.clear.isChecked(),
                                   self.sas, self.fill.isChecked())
        self.build_job = (s, job)
        self.status.setText(tr("Загрузка каналов сцены {when}…",
                               when=s.when))
        self.timer.start()

    def _built(self):
        s, job = self.build_job
        self.build_job = None
        self.add_button.setEnabled(True)
        try:
            made = job.result()
        except (RuntimeError, ValueError, OSError) as error:
            self.status.setText(tr("Снимок не загружен: {error}",
                                   error=str(error)))
            return
        if not made:
            self.status.setText(tr(
                "Ссылкой ложатся только сочетания каналов, индексы - "
                "обрезкой по участку."))
            return
        layers = self.add_layers(s, made)
        self.status.setText(tr("В проект добавлено слоёв {count}: {path}",
                               count=len(layers),
                               path=os.path.dirname(made[0][1])))

    def add_layers(self, s, made):
        """Слои продуктов в группу дня внутри группы «Sentinel-2»."""
        project = QgsProject.instance()
        root = project.layerTreeRoot()
        group = GROUPS.get(s.mission, GROUP)
        top = root.findGroup(group) or root.insertGroup(0, group)
        name = "{} {}".format(s.when[:10], s.tile)
        day = top.findGroup(name) or top.insertGroup(0, name)
        names = titles(s.mission)
        layers = []
        for product, path, ranges, *extra in made:
            title = tr("Вся сцена, исходные файлы") if product == "whole" \
                else names[product]
            layer = QgsRasterLayer(path, "{} - {}".format(
                title, s.when[:10]), "gdal")
            if not layer.isValid():
                continue
            if product == "whole":
                # Показ - естественные цвета, у MSS и ASTER - ложные,
                # у MODIS - первый канал в серой шкале.
                if len(extra[0]) == 3:
                    style_composite(layer, ranges, bands=extra[0])
                else:
                    style_gray(layer, ranges[0], extra[0][0])
                extra = []
            elif product in s2.COMPOSITES or product in aster.COMPOSITES:
                style_composite(layer, ranges)
            elif product in aster.RATIOS:
                style_ratio(layer, *ranges[0])
            elif product in MULTI:
                # Все каналы в файле, показ - естественные цвета, у MSS -
                # ложные (ближний ИК 0.8, красный, зелёный).
                order = s2.all_keys(s)
                shown = [order.index(k) for k in s2.ALL_SHOWN[s.mission]]
                style_composite(layer, [ranges[i] for i in shown],
                                bands=tuple(i + 1 for i in shown))
            else:
                style_index(layer, product)
            metadata = layer.metadata()
            metadata.setRights([s2.credit(s)])
            if extra and extra[0]:
                metadata.setAbstract(tr(
                    "Температура поверхности USGS Collection 2 Level-2. "
                    "{share} % пикселей посчитаны формулой USGS "
                    "с излучательной способностью по NDVI - там, где "
                    "у USGS значения нет.",
                    share="{:.0f}".format(100.0 * extra[0])))
            layer.setMetadata(metadata)
            project.addMapLayer(layer, False)
            day.addLayer(layer)
            self.globe.set_layer_shown(layer.id(), True)
            layers.append(layer)
        return layers

    def _stop_jobs(self):
        if self.reply is not None:
            reply, self.reply = self.reply, None
            reply.abort()
        for _, job in self.cloud_jobs:
            job.cancel()
        self.cloud_jobs = []

    def closeEvent(self, event):
        self.timer.stop()
        self.generation += 1
        if self.series is not None:
            self.series.close()
        if self.signing is not None:
            replies, self.signing = self.signing["replies"], None
            for reply in replies:
                reply.abort()
        self._stop_jobs()
        self.sas_waiting = []
        if self.sas_reply is not None:
            reply, self.sas_reply = self.sas_reply, None
            reply.abort()
        # Пул общий на всё время работы QGIS, его потоки не завершаются,
        # см. executor. Несделанные задачи снимаются.
        for job in (self.preview_job, self.build_job):
            if job is not None:
                job[1].cancel()
        self.preview_job = None
        self.build_job = None
        super().closeEvent(event)

