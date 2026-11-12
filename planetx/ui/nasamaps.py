# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Каталог «Добавить данные»: карты и слои глобуса с превью.

С 12 октября 2026 года каталог стоит в левой панели на месте списка
«Слоёв», а не отдельным окном, решение автора. История окна - ниже.

Просьба автора от 7 октября 2026 года - «компактный красивый интерфейс
к картам NASA». Карта - тема NASA GIBS, поле прогноза GFS, пожары FIRMS
или температура суши и моря, включена одна из всех. Превью темы GIBS -
её тайл уровня 1 над Евразией на последний готовый день поверх тайла
подложки, у поля прогноза и пожаров - полоса цветов шкалы. Кнопки
групп сужают витрину, строка поиска ищет по названию. Окно немодальное,
одно на глобус, выбор делает окно глобуса (`GlobeWindow.set_theme`).

Тем же днём автор перенёс сюда и слои «Небо и свет», «Недра»
и «Анализ рельефа» («добавь остальные слои рядом и исключим их из
списка»). Слои включаются независимо, щелчок переключает строку окна
глобуса (`GlobeWindow.set_extra`), включённый слой отмечен бирочкой.
"""
import html
import math
import os
import time

import numpy as np
from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QPoint, QSize, Qt
from qgis.PyQt.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from qgis.PyQt.QtWidgets import (QHBoxLayout, QLabel, QLineEdit,
                                 QListWidget, QListWidgetItem, QPushButton,
                                 QVBoxLayout, QWidget)

from ..core import (clouds, cutaway, deposits, fires, flow, paleo,
                    plants, plates, quakes, slope, stars, sun, temperature,
                    themes, trains, vessels, weather)
from ..core import aircraft
from ..core import basemap, wms
from ..core import satellites as satellites_core
from ..i18n import is_russian, tr
from ..net.overlay import fetch_bytes
from ..qt_compat import enum, enum_int
from .registry import ROWS
from .satellites import group_names as satellite_group_names
from .themes import group_names, layer_tip, theme_names
from .weather import AURORA, field_of

THUMB = 104  # пикселей стороны превью
ICON = 40  # пикселей стороны значка строки каталога
CATEGORY_WIDTH = 150  # пикселей, столбец категорий каталога
PARALLEL = 4  # запросов превью сразу
# Место и размер окна каталога. Размер первого показа - выбор помощника.
GEOMETRY_KEY = "PlanetX/catalog_geometry"
SIZE = (780, 640)
KEY_ROLE = enum_int(enum(Qt, "ItemDataRole", "UserRole"))
ALL = ""  # кнопка «Все» групп
LAYER = "layer"  # вид строки витрины: слой глобуса со своим флажком
# Вкладка «Спутники»: карточки групп CelesTrak, ключ - SAT + группа.
# Просьба автора от 8 октября 2026 года - меню «Группы спутников»
# внизу окна висело некрасиво. Во вкладке «Все» карточек групп нет.
SAT = "sat:"
SAT_GROUP = "satellites"
# Категория «Подоснова»: встроенные и готовые подложки (basemap.READY),
# ключ BASE + ключ источника. Просьба автора от 18 октября 2026 года -
# готовые источники в подменю меню «Основа» он не нашёл. Щелчок ставит
# подложку, у источников с предупреждением - через окно согласия.
# Превью таких источников не просится до согласия.
BASE = "base:"
BASE_GROUP = "basemaps"
# Категория «Локальные данные» - подложки отдельных районов из служб WMS
# (core.wms.LOCAL), строки того же вида, что «Подоснова», просьба
# автора от 24 октября 2026 года.
LOCAL_GROUP = "local"
BUILTIN_BASES = ("esri_imagery", "osm")
# Категория «Карта»: группы векторной основы (ключ VECTOR + номер
# группы панели) и строки, которые до 12 октября 2026 года стояли
# в группе «Карта» раздела «Слои».
MAP = "map"
VECTOR = "vector:"
# Вид строки слоя всего каталога GIBS: строки приходят по запросу.
GIBS = "gibsall"
GIBS_SEARCH = 3  # знаков поиска, с которых просится каталог GIBS
MAP_ROWS = ("grid", "buildings", "contours", "cadastre")
# Цвета превью строк «Карты» - выбор помощника.
VECTOR_COLORS = (((250, 220, 60), (240, 240, 240)),
                 ((255, 200, 70), (250, 240, 180), (90, 90, 90)),
                 ((60, 120, 220), (90, 170, 90), (150, 110, 70)))
MAP_COLORS = {"grid": ((250, 220, 60), (230, 230, 230)),
              "buildings": ((200, 190, 175), (150, 140, 130)),
              "contours": ((150, 100, 60), (250, 220, 60)),
              "cadastre": ((230, 90, 80), (250, 225, 220)),
              "geoid": ((60, 90, 170), (120, 170, 120), (200, 150, 80)),
              "air": ((10, 15, 40), (90, 150, 230), (200, 225, 250)),
              **ROWS.colors()}
# Вторая строка слоя в каталоге - источник.
SOURCES = {"stars": "Yale BSC, NASA SVS", "clouds": "NASA GIBS, VIIRS",
           "sun": "NASA Black Marble", "satellites": "CelesTrak",
           "currents": "NOAA CoastWatch",
           "cutaway": "PREM, CRUST1.0, Slab2", "paleo": "PALEOMAP",
           "slope": "Terrarium", "aspect": "Terrarium",
           "grid": "", "buildings": "OpenFreeMap",
           "contours": "Terrarium",
           "cadastre": "Rosreestr NSPD",
           "geoid": "EGM2008, NGA", "air": "",
           **ROWS.sources()}
# Слои витрины: ключ строки окна глобуса и группа.
# Недра с 27 октября 2026 года - четыре подгруппы вместо 21 строки
# подряд, решение автора.
LAYERS = ROWS.place((
          ("stars", "sky"), ("air", "sky"), ("clouds", "sky"), ("sun", "sky"),
          ("satellites", "sky"),
          ("cutaway", "geology"), ("paleo", "geology"),
          ("geoid", "geophysics"),
          ("currents", "water"),
          ("slope", "terrain"),
          ("aspect", "terrain")))
# Строки-окна: источник данных у точки взгляда открывает своё окно
# (действие строки «Поиск» GlobeWindow._actions). Прежде их было видно
# только в меню на глобусе, решение автора от 27 октября 2026 года.
TOOL = "tool:"
TOOLS = (("here:change", "change"), ("here:recognize", "change"),
         ("here:sentinel", "survey"),
         ("here:lidar", "survey"), ("here:oam", "survey"),
         ("here:rumsey", "oldmaps"),
         ("here:etomesto", "oldmaps"))
# Левый столбец каталога: раздел - заголовок, щелчок по нему показывает
# все его группы. Ключ раздела «Недра» - прежний ключ группы "depths".
SECTION = "section:"
TOOL_COLORS = ((70, 120, 190), (235, 235, 235))  # превью строки-окна
# ЛЭП и кабели OSM и горизонтали - строки группы «Карта» раздела «Слои»,
# решение автора от 11 октября 2026 года. Названия берутся отсюда.
# Слои, которые есть и вне Земли: звёзды везде, уклон - где есть высоты.
ANY_BODY = ("stars", "air")
RELIEF_BODY = ("slope", "aspect")
# Заливка и обвод контуров горных разработок, выбор помощника.
MINING_FILL = (235, 125, 35, 90)
MINING_LINE = (205, 85, 20, 255)
PALEO_AGE = 100  # млн лет, возраст карты на превью палеогеографии
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "data")


def layer_group_names():
    """Группы слоёв витрины: ключ, название, подсказка."""
    return (
        ("sky", tr("Небо и свет"), tr(
            "Солнце и ночная сторона, звёзды, облака "
            "и искусственные спутники.")),
        ("geology", tr("Геология"), tr(
            "Геологическая и литологическая карты, разрез Земли "
            "и палеогеография.")),
        ("seismic", tr("Землетрясения и плиты"), tr(
            "Землетрясения за месяц и с 1904 года, границы плит, активные "
            "разломы, скорости плит и вулканы.")),
        ("geophysics", tr("Геофизика"), tr(
            "Магнитное поле, аномалии силы тяжести, геоид, возраст "
            "океанического дна и тепловой поток.")),
        ("resources", tr("Полезные ископаемые"), tr(
            "Месторождения USGS, горные разработки по снимкам, шахты "
            "и карьеры OpenStreetMap.")),
        ("survey", tr("Снимки у точки"), tr(
            "Окна поиска снимков Sentinel-2, Landsat, MODIS, ASTER, "
            "OpenAerialMap и облаков точек лидара у точки взгляда.")),
        ("change", tr("Изменения местности"), tr(
            "Где местность изменилась между двумя годами 2017-2025 - по "
            "эмбеддингам AlphaEarth Foundations.")),
        ("oldmaps", tr("Исторические карты"), tr(
            "Окна каталогов исторических карт у точки взгляда - "
            "коллекция Рамсея и сайт «Это Место».")),
        ("infra", tr("Энергетика"), tr(
            "Электростанции мира, линии электропередачи, подстанции, "
            "трубопроводы и подводные кабели.")),
        ("transport", tr("Транспорт"), tr(
            "Поезда Финляндии, суда Балтики и самолёты в реальном "
            "времени по открытым данным Fintraffic и сети ADS-B "
            "adsb.lol.")),
        ("soil", tr("Почвы"), tr(
            "Свойства верхнего слоя почвы 0-5 см по SoilGrids - глина, "
            "песок, органический углерод и кислотность, сетка 250 м.")),
        ("terrain", tr("Анализ рельефа"), tr(
            "Раскраска поверхности по уклону или по стороне "
            "света склона, включается одна из двух. Горизонтали "
            "рельефа поверх них.")),
        ("tiles", tr("Наложения карт"), tr(
            "Прозрачные карты поверх подложки - морские знаки, пешие, "
            "велосипедные и конные маршруты, горнолыжные трассы. "
            "Включать можно несколько сразу.")),
        ("wiki", tr("Энциклопедия"), tr(
            "Статьи Википедии с координатами у точки взгляда. Щелчок "
            "по статье открывает её первый абзац, ссылку и кнопку "
            "«Объясни это».")),
        (SAT_GROUP, tr("Спутники"), tr(
            "Группы искусственных спутников CelesTrak. Щелчок по группе "
            "показывает её на глобусе или убирает.")))


def catalog_sections():
    """Разделы левого столбца каталога: ключ, название, подсказка,
    группы по порядку. Раскладка - решение автора от 27 октября
    2026 года."""
    return (
        (SECTION + "base", tr("Основа"), tr(
            "Подоснова, векторная карта, прозрачные наложения карт "
            "и статьи Википедии."),
         (BASE_GROUP, LOCAL_GROUP, MAP, "tiles", "wiki")),
        (SECTION + "now", tr("Земля сейчас"), tr(
            "Погода, снимки и карты NASA по дням - огонь, вода, воздух, "
            "жизнь, а также почвы."),
         ("weather", "fire", "water", "gases", "life", "soil",
          themes.GIBS_GROUP)),
        (SECTION + "archive", tr("Архив и съёмка"), tr(
            "Прежние снимки, исторические карты, космоснимки и облака "
            "точек у точки взгляда."),
         ("archive", "change", "oldmaps", "survey")),
        ("depths", tr("Недра"), tr(
            "Геология, землетрясения и плиты, геофизика и полезные "
            "ископаемые."),
         ("geology", "seismic", "geophysics", "resources")),
        (SECTION + "sky", tr("Небо"), tr(
            "Солнце, звёзды, облака, атмосфера и искусственные спутники."),
         ("sky", SAT_GROUP)),
        (SECTION + "infra", tr("Энергетика и транспорт"), tr(
            "Электростанции, ЛЭП, трубопроводы, кабели, поезда, суда "
            "и самолёты."),
         ("infra", "transport")),
        (SECTION + "terrain", "", "", ("terrain",)))


def tool_names():
    """Строка-окно каталога: ключ TOOL + действие - (название,
    подсказка)."""
    return {
        TOOL + "here:sentinel": (tr("Космоснимки"), tr(
            "Окно поиска снимков Sentinel-2, Landsat 1-9, MODIS и ASTER "
            "участка у точки взгляда - облачность над участком, сочетания "
            "каналов и индексы слоями проекта, ряд по датам.")),
        TOOL + "here:change": (tr("Окно «Изменения местности»"), tr(
            "Окно сравнения двух лет у точки взгляда - годы, промежуток "
            "степени изменения, подробный участок с пикселем от 10 м, "
            "растр в проект QGIS и места изменений в «Мои метки».")),
        TOOL + "here:recognize": (tr("Распознавание"), tr(
            "Окно распознавания участка у точки взгляда - свои образцы, "
            "цвета снимка, похожие на образец, леса, поля, вода, заросшие "
            "поля. Классы растром и многоугольниками в проект QGIS.")),
        TOOL + "here:lidar": (tr("Облака точек лидара"), tr(
            "Плитки облаков точек IGN LiDAR HD во Франции и USGS 3DEP "
            "в США у точки взгляда слоями проекта, точки на глобусе.")),
        TOOL + "here:oam": (tr("Снимки OpenAerialMap"), tr(
            "Открытые снимки с дронов и самолётов в рамке вида, новые "
            "первыми, с пикселем, размером файла и лицензией снимка. "
            "Снимок ложится слоем тайлов в проект.")),
        TOOL + "here:rumsey": (tr("Исторические карты Рамсея"), tr(
            "Карты коллекции Дэвида Рамсея у точки взгляда, привязанные "
            "по опорным точкам Стэнфорда, слоем проекта с годом карты.")),
        TOOL + "here:etomesto": (tr("Старые карты «Это Место»"), tr(
            "Каталог старых карт сайта etomesto.com у точки взгляда. Карта "
            "открывается страницей сайта в браузере.")),
    }


def layer_names():
    """Слой витрины: ключ - (название, подсказка)."""
    return {
        "stars": (tr("Звёзды"), tr(
            "Звёзды каталога ярких звёзд Йельского университета "
            "и Млечный путь по карте неба NASA. Картинка неба "
            "скачивается при первом показе. Звёзды видны "
            "из космоса и гаснут, когда камера опускается "
            "в атмосферу.")),
        "air": (tr("Атмосфера"), tr(
            "Голубое свечение воздуха вокруг планеты, небо над "
            "горизонтом и дымка над далёкой поверхностью. Без флажка "
            "фон вида - чёрный космос, поверхность видна без дымки. "
            "У тел без воздуха строка ничего не меняет.")),
        "clouds": (tr("Облака"), tr(
            "Облака по снимкам VIIRS из NASA GIBS за последние "
            "полные сутки. Они лежат полупрозрачной пеленой "
            "поверх снимка. Снег и лёд тоже белые и остаются "
            "видны.")),
        "sun": (tr("Солнце"), tr(
            "Свет рельефа, зданий и воздуха по положению солнца. "
            "Ночная сторона Земли тёмная. Время солнца - конец "
            "промежутка открытой шкалы времени, без неё - часы "
            "компьютера. Без флажка свет падает с северо-запада, "
            "как на карте рельефа.")),
        "satellites": (tr("Спутники"), tr(
            "Искусственные спутники по орбитальным элементам CelesTrak, "
            "положение по модели SGP4. Время - правый бегунок шкалы "
            "времени, без шкалы - часы компьютера. Группы выбирает "
            "вкладка «Спутники» витрины. Элементы группы обновляются "
            "не чаще раза в 2 часа.")),
        "currents": (tr("Течения"), tr(
            "Поверхностные течения океана белыми бегущими струйками над "
            "заливкой скорости. Геострофические течения NOAA CoastWatch по "
            "спутниковой альтиметрии за последние готовые сутки, сетка "
            "0.5°. Первое включение за сеанс скачивает около 4 МБ.")),
        "geoid": (tr("Геоид"), tr(
            "Форма уровенной поверхности Земли - геоида - по модели "
            "EGM2008 NGA. Пока строка включена, высоты глобуса - высоты "
            "геоида над эллипсоидом, от -107 до +86 м, растянутые "
            "в 10 000 раз, и Земля выглядит «измятой». Горбы - там, где "
            "сила тяжести больше, например у Новой Гвинеи, впадины - "
            "где меньше, самая глубокая - в Индийском океане. Рельеф "
            "и вода на это время убраны, выключение строки их "
            "возвращает.")),
        "cutaway": (tr("Разрез Земли"), tr(
            "Вынимает из Земли сектор под точкой взгляда - "
            "четверть полушария шириной 90° по долготе. На его "
            "гранях видны кора, мантия и ядро по радиусам "
            "модели PREM. Где грань проходит через зону "
            "субдукции, на ней видна погружающаяся плита. "
            "Углы сектора тянутся мышью. Сектор ставится заново "
            "при каждом включении строки.")),
        "paleo": (tr("Палеогеография"), tr(
            "Рельеф суши и глубины моря в прошлом, до 540 млн "
            "лет назад, по картам PaleoDEM PALEOMAP. Возраст "
            "задаёт ползунок в левом нижнем углу вида. Снимок, "
            "границы и подписи на это время убраны.")),
        "slope": (tr("Уклон"), tr(
            "Уклон поверхности по высотам рельефа, классами от "
            "ровного до круче 35°. Шкала стоит в левом нижнем "
            "углу вида. Есть у Земли, Марса и Луны.")),
        "aspect": (tr("Экспозиция"), tr(
            "Куда обращён склон - цвет стороны света, ровное "
            "место серое. Включается вместо уклона.")),
        "grid": (tr("Координатная сетка"), tr(
            "Параллели и меридианы с подписями градусов, экватор, "
            "тропики и полярные круги. Шаг сетки меняется с высотой "
            "камеры.")),
        "buildings": (tr("3D-здания"), tr(
            "Объёмные здания из OpenStreetMap по векторным тайлам "
            "OpenFreeMap. Они видны, когда камера ближе 6 км к земле. "
            "Высота взята из OSM, иначе из этажности. Здание без этих "
            "сведений получает высоту 5 м.")),
        "contours": (tr("Горизонтали"), tr(
            "Линии равных высот рельефа, как на топографической карте. "
            "Сечение подбирается по масштабу вида - от сотен метров "
            "издалека до 5-10 м вблизи, каждая пятая горизонталь "
            "утолщённая и подписана отметкой. Ниже "
            "уровня моря - синие изобаты. Строятся по высотам глобуса "
            "и по своему рельефу растром проекта.")),
        "cadastre": (tr("Кадастр Росреестра"), tr(
            "Земельные участки из Национальной системы пространственных "
            "данных Росреестра поверх снимка, только по России. Видны "
            "вблизи, с высоты около 10 км и ниже. Служба отвечает "
            "медленно и отказывает на частые запросы, поэтому участки "
            "приходят по одному тайлу.")),
        **ROWS.names(),
    }


def map_names():
    """Карта витрины: ключ - (название, подсказка)."""
    names = dict(theme_names())
    names[themes.FIRES] = (tr("Пожары"), tr(
        "Очаги пожаров за последние 24 часа по снимкам VIIRS спутника "
        "NOAA-20, сводка NASA FIRMS. Цвет и размер точки показывают "
        "мощность излучения."))
    names[themes.TEMPERATURE] = (tr("Температура поверхности"), tr(
        "Температура суши днём по MODIS за 8 суток и моря по GHRSST MUR "
        "за сутки, данные NASA GIBS."))
    return names


def ramp_image(colors, base=None):
    """Превью из полосы цветов шкалы поверх картинки подложки."""
    image = QImage(THUMB, THUMB, enum(QImage, "Format", "Format_ARGB32"))
    image.fill(QColor(40, 48, 60))
    painter = QPainter(image)
    if base is not None:
        painter.drawImage(image.rect(), base)
    band = THUMB // 4
    count = max(len(colors), 1)
    for n, color in enumerate(colors):
        left = THUMB * n // count
        right = THUMB * (n + 1) // count
        painter.fillRect(left, THUMB - band, right - left, band,
                         QColor(*color[:3]))
    painter.end()
    return image


def tile_image(data, base=None, clear=()):
    """Превью из тайла темы поверх тайла подложки. Цвета clear -
    прозрачные классы темы."""
    image = QImage(THUMB, THUMB, enum(QImage, "Format", "Format_ARGB32"))
    image.fill(QColor(40, 48, 60))
    tile = QImage.fromData(data) if data else QImage()
    painter = QPainter(image)
    if base is not None:
        painter.drawImage(image.rect(), base)
    if not tile.isNull():
        if clear:
            tile = _cleared(tile, clear)
        painter.setOpacity(themes.OPACITY)
        painter.drawImage(image.rect(), tile)
    painter.end()
    return image


def _rgba_array(tile):
    """Пиксели картинки массивом (высота, ширина, 4) RGBA uint8."""
    tile = tile.convertToFormat(enum(QImage, "Format", "Format_RGBA8888"))
    width, height, line = tile.width(), tile.height(), tile.bytesPerLine()
    ptr = tile.constBits()
    ptr.setsize(height * line)
    return np.frombuffer(ptr, np.uint8).reshape(height, line)[
        :, :width * 4].reshape(height, width, 4).copy()


def _rgba_image(pixels, premultiplied=False):
    """Картинка из массива RGBA uint8."""
    name = "Format_RGBA8888_Premultiplied" if premultiplied \
        else "Format_RGBA8888"
    height, width = pixels.shape[:2]
    return QImage(np.ascontiguousarray(pixels).tobytes(), width, height,
                  width * 4, enum(QImage, "Format", name)).copy()


def _over(under, top):
    """Превью из двух картинок одна над другой, любая может быть None."""
    image = _blank()
    painter = QPainter(image)
    for picture in (under, top):
        if picture is not None:
            painter.drawImage(image.rect(), picture)
    painter.end()
    return image


def _cleared(tile, clear):
    """Тайл, у которого пиксели цветов clear прозрачны."""
    pixels = _rgba_array(tile)
    for color in clear:
        pixels[np.all(pixels[..., :3] == color, axis=-1), 3] = 0
    return _rgba_image(pixels)


def ramp_of(key):
    """Цвета шкалы карты без тайла: поле прогноза или пожары."""
    if key == themes.FIRES:
        return [color for _, color in fires.FRP_STOPS]
    return weather.legend(field_of(key))["colors"]


def _blank(color=(40, 48, 60)):
    image = QImage(THUMB, THUMB, enum(QImage, "Format", "Format_ARGB32"))
    image.fill(QColor(*color))
    return image


def _thumb_xy(lat, lon):
    """Пиксель превью для точки: тайл THUMB_TILE в Web Mercator."""
    z, x, y = themes.THUMB_TILE
    world = THUMB * (1 << z)
    lat = max(-85.0, min(85.0, lat))
    mx = (lon + 180.0) / 360.0 * world - x * THUMB
    s = math.sin(math.radians(lat))
    my = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * world \
        - y * THUMB
    return mx, my


def stars_image():
    """Превью звёзд: Орион и соседи из каталога модуля, восток слева."""
    image = _blank((8, 10, 22))
    try:
        data = np.load(os.path.join(DATA_DIR, "stars.npy"))
    except OSError:
        return image
    ra_lo, ra_hi, dec_lo, dec_hi = 1.0, 1.9, -0.45, 0.45
    pick = (data[:, 0] > ra_lo) & (data[:, 0] < ra_hi) \
        & (data[:, 1] > dec_lo) & (data[:, 1] < dec_hi)
    data = data[pick]
    sizes = stars.sizes(data[:, 2]) * 0.8
    colors = np.clip(stars.colors(data[:, 3]) * 255.0, 0, 255)
    painter = QPainter(image)
    painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
    painter.setPen(enum(Qt, "PenStyle", "NoPen"))
    for (ra, dec), size, color in zip(data[:, :2], sizes, colors):
        painter.setBrush(QColor(*(int(c) for c in color)))
        x = (ra_hi - ra) / (ra_hi - ra_lo) * THUMB
        y = (dec_hi - dec) / (dec_hi - dec_lo) * THUMB
        painter.drawEllipse(int(x - size / 2), int(y - size / 2),
                            max(1, int(size)), max(1, int(size)))
    painter.end()
    return image


def satellites_image(base=None):
    """Превью спутников: шар с подложкой, орбиты и точки."""
    image = _blank((8, 10, 22))
    painter = QPainter(image)
    painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
    radius = THUMB * 0.3
    cx = cy = THUMB / 2.0
    painter.setPen(enum(Qt, "PenStyle", "NoPen"))
    painter.setBrush(QColor(40, 90, 160))
    painter.drawEllipse(int(cx - radius), int(cy - radius),
                        int(2 * radius), int(2 * radius))
    pen = painter.pen()
    for n, (tilt, color) in enumerate(((20, (255, 255, 255)),
                                       (-45, (255, 200, 80)),
                                       (70, (120, 220, 255)))):
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(tilt)
        painter.setBrush(enum(Qt, "BrushStyle", "NoBrush"))
        painter.setPen(QColor(*color))
        a, b = THUMB * (0.42 - 0.04 * n), THUMB * (0.14 + 0.03 * n)
        painter.drawEllipse(int(-a), int(-b), int(2 * a), int(2 * b))
        painter.setPen(enum(Qt, "PenStyle", "NoPen"))
        painter.setBrush(QColor(*color))
        for k in range(5):
            angle = 2 * math.pi * (k / 5.0 + 0.1 * n)
            painter.drawEllipse(int(a * math.cos(angle)) - 2,
                                int(b * math.sin(angle)) - 2, 4, 4)
        painter.restore()
    painter.setPen(pen)
    painter.end()
    return image


# Орбиты превью групп спутников: доля радиуса шара, сплющенность
# эллипса, наклон в градусах, количество точек.
SAT_ORBITS = {
    "stations": (1.18, 0.35, 25, 2), "visual": (1.22, 0.4, -30, 10),
    "gnss": (1.75, 0.55, 35, 12), "weather": (1.25, 0.95, 80, 8),
    "resource": (1.22, 0.9, 75, 10), "science": (1.4, 0.5, -20, 8),
    "geo": (2.25, 0.18, 0, 16), "starlink": (1.15, 0.45, 40, 60),
    "oneweb": (1.3, 0.85, 70, 36)}


def satellite_group_image(group, color):
    """Превью группы спутников: шар и орбита группы её цветом."""
    image = _blank((8, 10, 22))
    painter = QPainter(image)
    painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
    reach, flat, tilt, count = SAT_ORBITS.get(group, (1.3, 0.5, 20, 8))
    radius = THUMB * 0.42 / reach
    cx = cy = THUMB / 2.0
    painter.setPen(enum(Qt, "PenStyle", "NoPen"))
    painter.setBrush(QColor(40, 90, 160))
    painter.drawEllipse(int(cx - radius), int(cy - radius),
                        int(2 * radius), int(2 * radius))
    painter.translate(cx, cy)
    painter.rotate(tilt)
    a, b = radius * reach, radius * reach * flat
    painter.setBrush(enum(Qt, "BrushStyle", "NoBrush"))
    painter.setPen(QColor(*color, 140))
    painter.drawEllipse(int(-a), int(-b), int(2 * a), int(2 * b))
    painter.setPen(enum(Qt, "PenStyle", "NoPen"))
    painter.setBrush(QColor(*color))
    size = 3 if count > 20 else 5
    for k in range(count):
        angle = 2 * math.pi * (k / count + 0.05)
        painter.drawEllipse(int(a * math.cos(angle)) - size // 2,
                            int(b * math.sin(angle)) - size // 2,
                            size, size)
    painter.end()
    return image


def cutaway_image():
    """Превью разреза: оболочки PREM кольцами, вынут сектор."""
    image = _blank((8, 10, 22))
    painter = QPainter(image)
    painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
    painter.setPen(enum(Qt, "PenStyle", "NoPen"))
    outer = THUMB * 0.44
    cx = cy = THUMB / 2.0
    painter.setBrush(QColor(40, 90, 160))
    painter.drawEllipse(int(cx - outer), int(cy - outer), int(2 * outer),
                        int(2 * outer))
    top = cutaway.SHELLS[-1][2]
    for name, low, high, color in reversed(cutaway.SHELLS):
        r = outer * high / top
        painter.setBrush(QColor(*color))
        # Сектор 90° справа сверху, углы Qt - в шестнадцатых градуса.
        painter.drawPie(int(cx - r), int(cy - r), int(2 * r), int(2 * r),
                        0, 90 * 16)
    painter.end()
    return image


def plates_image(base=None):
    """Превью границ плит: линии PB2002 над Евразией по группам."""
    image = _blank()
    painter = QPainter(image)
    painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
    if base is not None:
        painter.drawImage(image.rect(), base)
    try:
        with open(os.path.join(DATA_DIR, "plates.json"),
                  encoding="utf-8") as fh:
            data = plates.Plates.from_text(fh.read())
    except (OSError, ValueError):
        painter.end()
        return image
    pen = painter.pen()
    pen.setWidthF(1.6)
    for line in data.boundaries:
        pen.setColor(QColor(*plates.color(line.code)[:3]))
        painter.setPen(pen)
        points = [_thumb_xy(la, lo) for la, lo in zip(line.lats, line.lons)]
        for a, b in zip(points, points[1:]):
            if abs(a[0] - b[0]) < THUMB / 2:
                painter.drawLine(int(a[0]), int(a[1]), int(b[0]), int(b[1]))
    painter.end()
    return image


def sun_image(base, lights):
    """Превью солнца: правая половина в ночи с огнями городов."""
    image = _blank()
    painter = QPainter(image)
    if base is not None:
        painter.drawImage(image.rect(), base)
    for x in range(THUMB):
        night = min(1.0, max(0.0, (x - THUMB * 0.35) / (THUMB * 0.25)))
        painter.fillRect(x, 0, 1, THUMB, QColor(4, 6, 16, int(225 * night)))
    if lights is not None:
        painter.setClipRect(int(THUMB * 0.5), 0, THUMB, THUMB)
        painter.drawImage(image.rect(), lights)
    painter.end()
    return image


def layer_ramp(key):
    """Цвета шкалы слоя без своей картинки."""
    if key in ("quakes", "iscgem"):
        return [color for _, color in quakes.DEPTH_STOPS]
    if key in ("deposits", "osm_mines"):
        return [group[2] for group in deposits.GROUPS]
    if key == "plants":
        return [f[2] for f in plants.FUELS]
    if key == "trains":
        return [tuple(int(round(v * 255)) for v in color)
                for _, color in trains.CATEGORIES]
    if key == "vessels":
        return [tuple(int(round(v * 255)) for v in color)
                for _, color, _ in vessels.GROUPS]
    if key == "aircraft":
        return [tuple(int(round(v * 255)) for v in color)
                for _, _, _, color in aircraft.GROUPS]
    if key == "currents":
        return [c for _, c in flow.CURRENT_STOPS]
    if key == "mining":
        return [MINING_FILL[:3], MINING_LINE[:3]]
    if key == "slope":
        return [color for _, color in slope.SLOPE_STOPS]
    return [color for _, color in slope.ASPECT_STOPS]


def layer_url(key):
    """Адрес тайла превью слоя или None, если картинка рисуется сама."""
    z, x, y = themes.THUMB_TILE
    if key == "clouds":
        template = clouds.url_template(time.time())
    elif key == "paleo":
        template = paleo.TILE_URL.replace("{age}", str(PALEO_AGE))
    elif key == "sun":
        template = sun.LIGHTS_URL
    else:
        return None
    return template.replace("{z}", str(z)).replace("{x}", str(x)).replace(
        "{y}", str(y))


def base_keys():
    """Строки категории «Подоснова» по порядку: встроенные подложки,
    затем готовые источники групп меню «Основа»."""
    return [BASE + k for k in BUILTIN_BASES] + [
        BASE + k for _, keys in basemap.READY_GROUPS for k in keys]


def local_keys():
    """Строки категории «Локальные данные»."""
    return [BASE + k for k in wms.LOCAL_KEYS]


def base_key(source):
    """Ключ строки «Подосновы» источника подложки или ""."""
    entry = getattr(source, "entry", None)
    if entry is not None and entry.get("local"):
        return BASE + entry["local"]
    if source.ready:
        return BASE + source.ready
    if source.builtin:
        return BASE + ("esri_imagery" if source.example else "osm")
    return ""


def _base_source(key):
    name = key[len(BASE):]
    if name == "esri_imagery":
        return basemap.esri_imagery()
    if name == "osm":
        return basemap.osm()
    if name in wms.LOCAL_KEYS:
        return wms.source(wms.local_entry(name, is_russian()))
    return basemap.ready_source(name, is_russian())


def base_name(key):
    """Название и подсказка строки «Подосновы»."""
    source = _base_source(key)
    if key[len(BASE):] in wms.LOCAL_KEYS:
        return source.name, wms.local_about(key[len(BASE):], is_russian())
    row = basemap.ready_entry(key[len(BASE):])
    if row is not None and row[7]:
        tip = tr("Условия сервиса не разрешают брать тайлы по прямому "
                 "адресу. Перед добавлением окно предупредит об этом.")
    else:
        tip = tr("Подложка глобуса до уровня {level}. Подпись на "
                 "глобусе - {credit}.", level=source.max_level,
                 credit=source.attribution[0])
        if isinstance(source, basemap.RegionalXyz):
            tip += " " + tr("Карта одной страны. Вокруг неё и издалека "
                            "глобус показывает подложку Esri.")
    return source.name, tip


def base_credit(key):
    """Вторая строка «Подосновы» - подпись источника."""
    return _base_source(key).attribution[0]


def base_url(key):
    """Адрес тайла превью подложки или None - у строк не
    «Подосновы» и у источников с предупреждением до согласия."""
    if not key.startswith(BASE):
        return None
    name = key[len(BASE):]
    if name in wms.LOCAL_KEYS:
        # Превью района - картинка охвата службы, тайл 1/1/0 мира был
        # бы снимком Esri.
        entry = wms.local_entry(name)
        return entry["template"].replace("{bbox}", wms.bbox_text(
            wms.preview_bbox(entry["box"])))
    row = basemap.ready_entry(name)
    if row is not None and row[7]:
        return None
    source = _base_source(key)
    if isinstance(source, basemap.RegionalXyz):
        # Превью районной карты - тайл её района, а не мира.
        return source.tile_url(*source.preview_tile())
    return source.tile_url(*themes.THUMB_TILE)


def day_text(day):
    """«2026-10-05» в «05.10.2026»."""
    if not day:
        return ""
    year, month, date = day.split("-")
    return "{}.{}.{}".format(date, month, year)


class NasaMaps(QWidget):
    """Каталог «Добавить данные» - немодальное окно поверх глобуса.
    window - окно глобуса.

    До 12 октября 2026 года - отдельное окно «Карты и слои», потом
    каталог выезжал в левой панели поверх списка «Слоёв». Решение автора
    от 18 октября 2026 года - снова отдельное немодальное окно: в панели
    каталог закрывал список и раздвигал панель, «каждый раз приходится
    остальное прятать». Слева категории, справа строки с флажками
    и описание выбранной строки. Карты витрины - одна на глобусе, слои
    включаются вместе, строки «Карты» - категория каталога. Место
    и размер окна помнят настройки (GEOMETRY_KEY).
    """

    def __init__(self, window, parent=None):
        super().__init__(parent, enum(Qt, "WindowType", "Tool"))
        self.setWindowTitle(tr("Добавить данные"))
        self.globe = window
        self.names = dict(map_names(), **layer_names())
        self.names.update(tool_names())
        self.lights = None  # тайл огней городов для превью солнца
        self.items = {}
        self.heads = {}  # заголовки строк: «одна на глобусе», «вместе»
        self.thumbs = {}  # ключ - превью QImage
        self.base = None  # тайл подложки под превью
        self._queue = []
        self._replies = {}
        self._loaded = set()  # превью по тайлу, которые пришли
        self._stopped = False  # каталог закрыт, запросов нет
        self._group = ALL
        self._quiet = False  # флажки ставит сам каталог
        self._chosen = ""  # строка, описание которой показано
        self._series = {}  # ключ слоя каталога GIBS - ряд дат
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit(self)
        self.search.setPlaceholderText(tr("снег, рудники, ветер"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        top.addWidget(self.search, 1)
        self.groups = QListWidget(self)
        self.groups.setFixedWidth(CATEGORY_WIDTH)
        self.groups.setTextElideMode(enum(Qt, "TextElideMode", "ElideNone"))
        self.groups.setWordWrap(True)
        titles = {key: (title, tip) for key, title, tip in [
            (BASE_GROUP, tr("Подоснова"), tr(
                "Подложки глобуса - снимки и карты. На глобусе "
                "одна подоснова, под картами и слоями.")),
            (LOCAL_GROUP, tr("Локальные данные"), tr(
                "Подробные снимки и карты отдельных районов из служб "
                "их владельцев. Строка ставит подоснову, вне района "
                "на глобусе снимки Esri.")),
            (MAP, tr("Карта"), tr(
                "Векторная основа OpenFreeMap, координатная сетка, "
                "3D-здания и горизонтали."))]
            + list(group_names()) + list(layer_group_names())}
        # Раздел - ключ, название, подсказка, группы. Раздел из одной
        # группы стоит строкой этой группы.
        self.sections = {}
        bold = None
        row = QListWidgetItem(tr("Все"), self.groups)
        row.setData(KEY_ROLE, ALL)
        row.setToolTip(tr("Все карты и слои каталога."))
        for key, title, tip, members in catalog_sections():
            if len(members) == 1:
                row = QListWidgetItem(titles[members[0]][0], self.groups)
                row.setData(KEY_ROLE, members[0])
                row.setToolTip(titles[members[0]][1])
                continue
            self.sections[key] = members
            row = QListWidgetItem(title, self.groups)
            row.setData(KEY_ROLE, key)
            row.setToolTip(tip)
            if bold is None:
                bold = row.font()
                bold.setBold(True)
            row.setFont(bold)
            for member in members:
                row = QListWidgetItem("   " + titles[member][0], self.groups)
                row.setData(KEY_ROLE, member)
                row.setToolTip(titles[member][1])
        self.groups.setCurrentRow(0)
        self.groups.currentItemChanged.connect(
            lambda item, _: self._set_group(item.data(KEY_ROLE))
            if item is not None else None)
        self.list = QListWidget(self)
        self.list.setIconSize(QSize(ICON, ICON))
        self.list.setTextElideMode(enum(Qt, "TextElideMode", "ElideRight"))
        self.list.itemChanged.connect(self._changed)
        self.list.itemClicked.connect(lambda item: self._describe(
            item.data(KEY_ROLE)))
        self.list.itemDoubleClicked.connect(self._clicked)
        self.details = QLabel(self)
        self.details.setWordWrap(True)
        self.details.setTextFormat(enum(Qt, "TextFormat", "RichText"))
        self.details.setAlignment(enum(Qt, "AlignmentFlag", "AlignTop"))
        self.toggle = QPushButton(self)
        self.toggle.clicked.connect(self._toggle_chosen)
        self.export = QPushButton(tr("В проект QGIS…"), self)
        self.export.setToolTip(tr(
            "Видимое на глобусе слоем в проект QGIS - объекты в рамке "
            "вида или картинка карты."))
        self.export.clicked.connect(self._export_chosen)
        buttons = QHBoxLayout()
        buttons.addWidget(self.toggle, 1)
        buttons.addWidget(self.export, 1)
        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.addWidget(self.list, 3)
        right.addWidget(self.details, 1)
        right.addLayout(buttons)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.addWidget(self.groups)
        body.addLayout(right, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addLayout(top)
        layout.addLayout(body, 1)
        self._head("bases", tr("Подоснова на глобусе - одна"))
        for key in base_keys():
            self.names[key] = base_name(key)
            self._row(key, BASE_GROUP, BASE)
            self.thumbs[key] = ramp_image([])
        for key in local_keys():
            self.names[key] = base_name(key)
            self._row(key, LOCAL_GROUP, BASE)
            self.thumbs[key] = ramp_image([])
        self._head("maps", tr("Карта на глобусе - одна"))
        for key, group, kind in themes.gallery_items():
            self._row(key, group, kind)
            self.thumbs[key] = ramp_image(ramp_of(key)) \
                if kind in ("weather", themes.FIRES) else ramp_image([])
        self._head("layers", tr("Слои - включаются вместе"))
        from .panel import geo_tree
        for n, (title, tip, rows) in enumerate(geo_tree()):
            key = VECTOR + str(n)
            self.names[key] = (title, tip)
            self._row(key, MAP, VECTOR)
            self.thumbs[key] = ramp_image(VECTOR_COLORS[n % 3])
        for key in MAP_ROWS:
            self._row(key, MAP, LAYER)
            self.thumbs[key] = self._layer_thumb(key)
        for key, group in LAYERS:
            self._row(key, group, LAYER)
            self.thumbs[key] = self._layer_thumb(key)
        for group, title, tip in satellite_group_names():
            key = SAT + group
            self.names[key] = (title, tip)
            self._row(key, SAT_GROUP, SAT)
            self.thumbs[key] = satellite_group_image(
                group, satellites_core.COLORS[group])
        self._head("tools", tr("Окна у точки взгляда"))
        for action, group in TOOLS:
            key = TOOL + action
            self._row(key, group, TOOL)
            item = self.items[key][0]
            # У окна нет состояния «на глобусе» - строка без флажка.
            item.setFlags(item.flags()
                          & ~enum(Qt, "ItemFlag", "ItemIsUserCheckable"))
            item.setData(enum(Qt, "ItemDataRole", "CheckStateRole"), None)
            self.thumbs[key] = ramp_image(TOOL_COLORS)
        self._filter()
        self._load_base()
        self.refresh()

    def _head(self, name, title):
        """Заголовок строк каталога - без флажка и без выбора."""
        item = QListWidgetItem(title, self.list)
        item.setFlags(enum(Qt, "ItemFlag", "NoItemFlags"))
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        self.heads[name] = item

    def _row(self, key, group, kind):
        name, tip = self.names[key]
        item = QListWidgetItem(name, self.list)
        item.setData(KEY_ROLE, key)
        item.setToolTip(tip)
        item.setFlags(item.flags()
                      | enum(Qt, "ItemFlag", "ItemIsUserCheckable"))
        item.setCheckState(enum(Qt, "CheckState", "Unchecked"))
        self.items[key] = (item, group, kind)

    # Превью.

    def _load_base(self):
        """Тайл подложки под превью, затем тайлы тем."""
        source = self.globe.sources[self.globe._basemap]
        url = source.tile_url(*themes.THUMB_TILE)
        self._replies["base"] = fetch_bytes(url, self._base_done)

    def _base_done(self, data, error):
        self._replies.pop("base", None)
        image = QImage.fromData(data) if data else QImage()
        self.base = None if image.isNull() else image
        self._queue = []
        for key, (item, group, kind) in self.items.items():
            if kind in ("gibs", themes.TEMPERATURE) or layer_url(key) \
                    or base_url(key):
                self._queue.append(key)
            elif kind == BASE:
                self._label(key)
            elif kind == themes.EVENTS:
                # Снимки событий: превью - подложка, снимков без события нет.
                self._set_thumb(key, _over(self.base, None))
            elif kind == LAYER:
                self._set_thumb(key, self._layer_thumb(key))
            elif kind in (SAT, VECTOR, GIBS, TOOL):
                self._label(key)
            else:
                self._set_thumb(key, ramp_image(ramp_of(key), self.base))
        self._pump()

    def _layer_thumb(self, key, data=None):
        """Превью слоя. data - байты его тайла, если он есть."""
        if key == "stars":
            return stars_image()
        if key == "satellites":
            return satellites_image()
        if key == "cutaway":
            return cutaway_image()
        if key == "plates":
            return plates_image(self.base)
        if key == "sun":
            lights = QImage.fromData(data) if data else QImage()
            return sun_image(self.base, None if lights.isNull() else lights)
        if key == "clouds":
            # Облака, как на глобусе: прозрачность по белизне снимка.
            tile = QImage.fromData(data) if data else QImage()
            if not tile.isNull():
                tile = _rgba_image(clouds.cloud_rgba(
                    _rgba_array(tile), themes.THUMB_TILE), premultiplied=True)
            return _over(self.base, None if tile.isNull() else tile)
        if key == "paleo":
            tile = QImage.fromData(data) if data else QImage()
            return _over(None if tile.isNull() else tile, None)
        if key in MAP_COLORS:
            return ramp_image(MAP_COLORS[key], self.base)
        return ramp_image(layer_ramp(key), self.base)

    def _pump(self):
        """Следующие запросы превью, не больше PARALLEL сразу. Теме
        нужен ряд дат - его просит окно глобуса."""
        if self._stopped:
            return
        waiting = []
        while self._queue and len(self._replies) < PARALLEL:
            key = self._queue.pop(0)
            url = self._thumb_url(key)
            if url is None:
                waiting.append(key)
                continue
            self._replies[key] = fetch_bytes(
                url, lambda data, error, k=key: self._thumb_done(k, data))
        self._queue[:0] = waiting

    def _thumb_url(self, key):
        if self.items[key][2] == LAYER:
            return layer_url(key)
        if self.items[key][2] == BASE:
            return base_url(key)
        if self.items[key][2] == GIBS:
            day = themes.pick_day(self._gibs_series(key))
            return themes.thumb_url(themes.BY_KEY[key], day) if day \
                else None
        if key == themes.TEMPERATURE:
            z, x, y = themes.THUMB_TILE
            return temperature.url_template(temperature.LAND).replace(
                "{z}", str(z)).replace("{x}", str(x)).replace("{y}", str(y))
        intervals = self.globe._theme_domains.get(key)
        if intervals is None:
            theme = themes.BY_KEY[key]
            self.globe._theme_fetch(key, "domains", theme.domains_url())
            return None
        day = themes.pick_day(intervals)
        if day is None:
            return None
        return themes.thumb_url(themes.BY_KEY[key], day)

    def _thumb_done(self, key, data):
        self._replies.pop(key, None)
        if data:
            self._loaded.add(key)
        if self.items[key][2] == LAYER:
            self._set_thumb(key, self._layer_thumb(key, data))
        elif self.items[key][2] == BASE:
            tile = QImage.fromData(data) if data else QImage()
            self._set_thumb(key, _over(None if tile.isNull() else tile,
                                       None))
        else:
            self._set_thumb(key, tile_image(data, self.base,
                                            themes.CLEAR.get(key, ())))
        self._pump()

    def _set_thumb(self, key, image):
        self.thumbs[key] = image
        self._label(key)

    def _gibs_series(self, key):
        if key not in self._series:
            self._series[key] = themes.BY_KEY[key].series(time.time())
        return self._series[key]

    def domains_arrived(self, key):
        """Окно глобуса получило ряд дат темы: подпись дня и превью."""
        if key not in self.items:
            return
        self._label(key)
        if key in self._queue:
            self._pump()

    # Выбор и вид.

    def is_on(self, key):
        """Строка каталога показана на глобусе."""
        kind = self.items[key][2]
        window = self.globe
        if kind == LAYER:
            return bool(window.extras.get(key))
        if kind == SAT:
            return bool(window.extras.get("satellites")) \
                and key[len(SAT):] in window.satellite_manager.groups
        if kind == VECTOR:
            return bool(self._vector_keys(key) & set(window._groups))
        if kind == BASE:
            return base_key(window.source) == key
        if kind == TOOL:
            return False
        return key == window.gallery_key()

    def _vector_keys(self, key):
        from .panel import geo_tree
        rows = geo_tree()[int(key[len(VECTOR):])][2]
        return {row[0] for row in rows}

    def subtitle(self, key):
        """Вторая строка: источник и день карты."""
        kind = self.items[key][2]
        if kind == "gibs":
            intervals = self.globe._theme_domains.get(key)
            day = themes.pick_day(intervals) if intervals else None
            if key == themes.WAYBACK:
                name = themes.BY_KEY[key].name
                return "{}, {}".format(name, day_text(day)) if day \
                    else name
            return tr("NASA GIBS, {day}", day=day_text(day)) if day \
                else tr("NASA GIBS")
        if kind == GIBS:
            day = themes.pick_day(self._gibs_series(key))
            return tr("NASA GIBS, {day}", day=day_text(day)) if day \
                else tr("NASA GIBS")
        if kind == "weather":
            return tr("прогноз NOAA SWPC") if key == AURORA \
                else tr("прогноз NOAA GFS")
        if kind == themes.EVENTS:
            title = self.globe.event_title()
            return "Vantor, Planet" + (", " + title if title else "")
        if kind == themes.FIRES:
            return tr("NASA FIRMS, 24 часа")
        if kind == themes.TEMPERATURE:
            return tr("NASA GIBS, суша и море")
        if kind == VECTOR:
            return tr("OpenFreeMap")
        if kind == SAT:
            return tr("CelesTrak")
        if kind == BASE:
            return base_credit(key)
        if kind == TOOL:
            return tr("окно у точки взгляда")
        return SOURCES.get(key, "")

    def _label(self, key):
        item = self.items[key][0]
        sub = self.subtitle(key)
        item.setText(self.names[key][0] + ("\n" + sub if sub else ""))
        image = self.thumbs.get(key) or ramp_image([])
        item.setIcon(QIcon(QPixmap.fromImage(image)))

    def refresh(self):
        """Флажки строк, доступность по телу и описание."""
        self._quiet = True
        checked = enum(Qt, "CheckState", "Checked")
        unchecked = enum(Qt, "CheckState", "Unchecked")
        planet = self.globe.planet
        relief = bool(getattr(planet, "terrain", None)) or planet.earth
        enabled = enum(Qt, "ItemFlag", "ItemIsEnabled")
        for key, (item, group, kind) in self.items.items():
            if kind != GIBS:
                self._label(key)
            if kind != TOOL:
                item.setCheckState(checked if self.is_on(key)
                                   else unchecked)
            usable = planet.earth or key in ANY_BODY + ("grid",) \
                or (key in RELIEF_BODY + ("contours",) and relief)
            # Спутники, подоснова и окна у точки - только у Земли.
            usable = usable and (kind not in (SAT, BASE, TOOL)
                                 or planet.earth)
            flags = item.flags()
            item.setFlags(flags | enabled if usable else flags & ~enabled)
        self._quiet = False
        self._describe(self._chosen)

    def _changed(self, item):
        """Флажок строки поставлен или снят мышью."""
        if self._quiet:
            return
        key = item.data(KEY_ROLE)
        if key not in self.items:
            return
        want = item.checkState() == enum(Qt, "CheckState", "Checked")
        if want != self.is_on(key):
            self._clicked(item)
        else:
            self.refresh()

    def _clicked(self, item):
        """Строка на глобус или с глобуса."""
        key = item.data(KEY_ROLE)
        if key not in self.items:
            return
        kind = self.items[key][2]
        self._chosen = key
        if kind == SAT:
            self._toggle_satellites(key[len(SAT):])
        elif kind == BASE:
            # Подоснова не снимается, щелчок по включённой - ничего.
            if not self.is_on(key):
                self._set_base(key)
        elif kind == LAYER:
            self.globe.set_extra(key, not self.globe.extras.get(key))
        elif kind == TOOL:
            # «here:sentinel» - окно GlobeWindow.sentinel_here у точки
            # взгляда.
            pose = self.globe.view.navigator.pose
            getattr(self.globe, key.split(":")[-1] + "_here")(pose.lat,
                                                              pose.lon)
            return
        elif kind == VECTOR:
            keys = self._vector_keys(key)
            groups = set(self.globe._groups)
            groups = groups - keys if keys & groups else groups | keys
            self.globe.set_line_groups(groups)
        else:
            self.globe.set_theme("" if key == self.globe.gallery_key()
                                  else key)
        self.refresh()

    def _describe(self, key):
        """Описание строки под списком и кнопки к ней."""
        if key not in self.items:
            self._chosen = ""
            self.details.setText(tr(
                "Флажок показывает карту или слой на глобусе. Строка - "
                "описание. Карта на глобусе одна, слои включаются "
                "вместе с ней."))
            self.toggle.setVisible(False)
            self.export.setVisible(False)
            return
        self._chosen = key
        if self.items[key][2] == GIBS and key not in self._loaded \
                and key not in self._replies and key not in self._queue:
            self._queue.append(key)
            self._pump()
        name, tip = self.names[key]
        sub = self.subtitle(key)
        text = "<b>{}</b>".format(html.escape(name))
        if sub:
            text += "<br><i>{}</i>".format(html.escape(sub))
        self.details.setText(text + "<br>" + html.escape(tip))
        on = self.is_on(key)
        self.toggle.setVisible(True)
        self.toggle.setEnabled(bool(self.items[key][0].flags() & enum(
            Qt, "ItemFlag", "ItemIsEnabled")))
        self.toggle.setText(tr("Убрать с глобуса") if on
                            else tr("Показать на глобусе"))
        if self.items[key][2] == TOOL:
            self.toggle.setText(tr("Открыть окно"))
        if self.items[key][2] == BASE:
            self.toggle.setEnabled(self.toggle.isEnabled() and not on)
            self.toggle.setText(tr("Подоснова на глобусе") if on
                                else tr("Поставить подосновой"))
        self.export.setVisible(bool(self.globe.export_key(key)))

    def _toggle_chosen(self):
        if self._chosen in self.items:
            self._clicked(self.items[self._chosen][0])

    def _export_chosen(self):
        row = self.globe.export_key(self._chosen)
        if row:
            self.globe.active_export(row)

    def _set_base(self, key):
        """Подложка строки key подосновой глобуса."""
        name = key[len(BASE):]
        window = self.globe
        if name in BUILTIN_BASES:
            index = next((n for n, s in enumerate(window.sources)
                          if base_key(s) == key), None)
            if index is not None:
                window._panel_basemap(index)
        elif name in wms.LOCAL_KEYS:
            window.add_local_source(name)
        else:
            window.add_ready_source(name)
        self.refresh()

    def _toggle_satellites(self, group):
        """Группа спутников на глобус или с глобуса. Первая группа
        включает слой «Спутники», последняя снятая - выключает."""
        manager = self.globe.satellite_manager
        on = bool(self.globe.extras.get("satellites"))
        groups = set(manager.groups)
        if on and group in groups:
            groups.discard(group)
        else:
            groups.add(group)
        manager.set_groups(groups)
        if groups and not on:
            self.globe.set_extra("satellites", True)
        elif not groups and on:
            self.globe.set_extra("satellites", False)
        self.refresh()

    def _set_group(self, group):
        self._group = group
        for n in range(self.groups.count()):
            row = self.groups.item(n)
            if row.data(KEY_ROLE) == group and self.groups.currentRow() != n:
                self.groups.blockSignals(True)
                self.groups.setCurrentRow(n)
                self.groups.blockSignals(False)
        self._filter()

    def _filter(self, *args):
        text = self.search.text().strip().lower()
        if (self._group == themes.GIBS_GROUP or len(text) >= GIBS_SEARCH) \
                and "gibs" not in self.heads:
            self.globe.load_gibs(self._gibs_arrived)
        seen = {"maps": False, "layers": False, "bases": False,
                "gibs": False, "tools": False}
        words = text.split()
        # Раздел левого столбца - все его группы, кроме слоёв каталога
        # GIBS: их больше тысячи, они только в своей группе и в поиске.
        members = self.sections.get(self._group, (self._group,))
        for key, (item, group, kind) in self.items.items():
            # Во «Всех» групп спутников и слоёв каталога GIBS нет, во
            # вкладке «Спутники» есть и сам слой. Поиск идёт по всему
            # каталогу, у слоёв GIBS - по всем словам запроса.
            if text and kind == GIBS:
                name = (self.names[key][0] + " " + key).lower()
                fits = all(word in name for word in words)
            elif text:
                fits = text in self.names[key][0].lower() \
                    or text in self.names[key][1].lower()
            elif self._group == ALL:
                fits = kind not in (SAT, BASE, GIBS)
            elif self._group in self.sections:
                fits = group in members and kind != GIBS
            else:
                fits = group == self._group or (
                    self._group == SAT_GROUP and key == "satellites")
            item.setHidden(not fits)
            if fits:
                seen["bases" if kind == BASE
                     else "layers" if kind in (LAYER, SAT, VECTOR)
                     else "tools" if kind == TOOL
                     else "gibs" if kind == GIBS else "maps"] = True
        for name, head in self.heads.items():
            head.setHidden(not seen[name])

    def _gibs_arrived(self):
        """Пришёл каталог GIBS: строки слоёв под своим заголовком. Превью
        слоя просится, когда строку выбирают."""
        if "gibs" in self.heads:
            return
        self._head("gibs", tr("Слои NASA GIBS - тоже одна карта на "
                              "глобусе"))
        blank = ramp_image([])
        # Подпись строки шлёт itemChanged, и без _quiet каждая из тысячи
        # строк обновляла весь каталог - 24 с на QGIS 4.
        self._quiet = True
        # Слои, которые уже стоят в каталоге своими картами, второй раз
        # не идут - замечание автора от 27 октября 2026 года о дублях.
        known = themes.built_in(clouds.LAYER, temperature.LAND,
                                temperature.SEA, sun.LIGHTS_LAYER,
                                basemap.BLUE_MARBLE_LAYER)
        for theme in self.globe.gibs_layers:
            if theme.layer in known:
                continue
            self.names[theme.key] = (theme.title, layer_tip(theme))
            self._row(theme.key, themes.GIBS_GROUP, GIBS)
            self.thumbs[theme.key] = blank
            self._label(theme.key)
        self._quiet = False
        self.refresh()
        self._filter()

    def place(self):
        """Место и размер окна: прежние из настроек, впервые - у левого
        верхнего угла вида глобуса."""
        saved = QgsSettings().value(GEOMETRY_KEY)
        if saved is not None and self.restoreGeometry(saved):
            return
        self.resize(*SIZE)
        view = self.globe.view
        self.move(view.mapToGlobal(QPoint(40, 40)))

    def closeEvent(self, event):
        QgsSettings().setValue(GEOMETRY_KEY, self.saveGeometry())
        self.stop()
        super().closeEvent(event)

    def stop(self):
        # Снятый запрос отвечает сразу, и обработчик ответа запускал
        # следующие. Прежде их ссылки тут же терялись очисткой словаря,
        # и QGIS падал в обработчике ответа, 7 октября 2026 года. Теперь
        # закрытый каталог новых запросов не запускает, а ответ снятого
        # убирает его из словаря сам.
        self._stopped = True
        self._queue = []
        for reply in list(self._replies.values()):
            reply.abort()

    def resume(self):
        """Каталог снова открыт: недостающие превью просятся заново."""
        if not self._stopped:
            return
        self._stopped = False
        if self.base is None and "base" not in self._replies:
            self._load_base()
        else:
            self._queue = [key for key, (_, _, kind) in self.items.items()
                           if self._thumb_missing(key, kind)]
            self._pump()

    def _thumb_missing(self, key, kind):
        """Превью по тайлу, которое не пришло, - закрытие сняло запрос."""
        return (kind in ("gibs", themes.TEMPERATURE) or layer_url(key)
                or kind == GIBS and key == self._chosen
                or base_url(key)) \
            and key not in self._replies and key not in self._loaded
