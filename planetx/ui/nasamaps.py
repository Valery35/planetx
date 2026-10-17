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
from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from qgis.PyQt.QtWidgets import (QHBoxLayout, QLabel, QLineEdit,
                                 QListWidget, QListWidgetItem, QPushButton,
                                 QToolButton, QVBoxLayout, QWidget)

from ..core import (clouds, cutaway, deposits, fires, flow, paleo,
                    plants, plates, quakes, slope, stars, sun, temperature,
                    themes, weather)
from ..core import satellites as satellites_core
from ..i18n import tr
from ..net.overlay import fetch_bytes
from ..qt_compat import enum, enum_int
from .satellites import group_names as satellite_group_names
from .themes import group_names, theme_names
from .weather import AURORA, field_of

THUMB = 104  # пикселей стороны превью
ICON = 40  # пикселей стороны значка строки каталога
CATEGORY_WIDTH = 116  # пикселей, столбец категорий каталога
PARALLEL = 4  # запросов превью сразу
KEY_ROLE = enum_int(enum(Qt, "ItemDataRole", "UserRole"))
ALL = ""  # кнопка «Все» групп
LAYER = "layer"  # вид строки витрины: слой глобуса со своим флажком
# Вкладка «Спутники»: карточки групп CelesTrak, ключ - SAT + группа.
# Просьба автора от 8 октября 2026 года - меню «Группы спутников»
# внизу окна висело некрасиво. Во вкладке «Все» карточек групп нет.
SAT = "sat:"
SAT_GROUP = "satellites"
# Категория «Карта»: группы векторной основы (ключ VECTOR + номер
# группы панели) и строки, которые до 12 октября 2026 года стояли
# в группе «Карта» раздела «Слои».
MAP = "map"
VECTOR = "vector:"
MAP_ROWS = ("grid", "buildings", "contours", "cadastre")
# ЛЭП, трубопроводы и кабели - категория «Энергетика», просьба автора
# от 12 октября 2026 года.
ENERGY_ROWS = ("infra_osm", "cables")
# Цвета превью строк «Карты» - выбор помощника.
VECTOR_COLORS = (((250, 220, 60), (240, 240, 240)),
                 ((255, 200, 70), (250, 240, 180), (90, 90, 90)),
                 ((60, 120, 220), (90, 170, 90), (150, 110, 70)))
MAP_COLORS = {"grid": ((250, 220, 60), (230, 230, 230)),
              "buildings": ((200, 190, 175), (150, 140, 130)),
              "contours": ((150, 100, 60), (250, 220, 60)),
              "cadastre": ((230, 90, 80), (250, 225, 220)),
              "infra_osm": ((220, 60, 60), (240, 150, 40), (90, 90, 200)),
              "cables": ((60, 200, 200), (170, 110, 220)),
              "magpoles": ((235, 70, 60), (70, 130, 235)),
              "magdecl": ((215, 70, 60), (40, 170, 70), (60, 110, 215)),
              "seafloor_age": ((230, 40, 40), (245, 230, 70), (60, 90, 200)),
              "platemotion": ((255, 225, 60), (60, 60, 60)),
              "volcanoes": ((230, 40, 30), (245, 140, 40), (240, 210, 70)),
              "faults": ((225, 45, 40), (40, 120, 230), (30, 170, 70)),
              "geology": ((251, 167, 148), (128, 197, 101), (191, 128, 196)),
              "gravity": ((30, 40, 130), (245, 245, 240), (150, 30, 30)),
              "bouguer": ((60, 120, 210), (245, 245, 240), (230, 120, 60)),
              "heatflow": ((40, 50, 140), (245, 235, 160), (220, 70, 40)),
              "emag": ((40, 60, 150), (245, 245, 235), (160, 30, 35)),
              "geoid": ((60, 90, 170), (120, 170, 120), (200, 150, 80)),
              "air": ((10, 15, 40), (90, 150, 230), (200, 225, 250))}
# Вторая строка слоя в каталоге - источник.
SOURCES = {"stars": "Yale BSC, NASA SVS", "clouds": "NASA GIBS, VIIRS",
           "sun": "NASA Black Marble", "satellites": "CelesTrak",
           "quakes": "USGS", "plates": "PB2002", "deposits": "USGS",
           "mining": "Maus et al. 2022", "osm_mines": "OpenStreetMap",
           "plants": "WRI", "currents": "NOAA CoastWatch",
           "cutaway": "PREM, CRUST1.0, Slab2", "paleo": "PALEOMAP",
           "slope": "Terrarium", "aspect": "Terrarium",
           "grid": "", "buildings": "OpenFreeMap",
           "contours": "Terrarium", "infra_osm": "OpenStreetMap",
           "cables": "OpenStreetMap", "cadastre": "Rosreestr NSPD",
           "magpoles": "NOAA NCEI, IGRF-14", "emag": "EMAG2v3, NOAA NCEI",
           "magdecl": "IGRF-14", "seafloor_age": "Seton et al. 2020",
           "heatflow": "IHFC 2024", "gravity": "XGM2019e, ICGEM",
           "bouguer": "XGM2019e, ETOPO 2022",
           "platemotion": "NNR-MORVEL56",
           "volcanoes": "Smithsonian GVP",
           "faults": "GEM Global Active Faults", "geology": "Macrostrat",
           "geoid": "EGM2008, NGA", "air": ""}
# Слои витрины: ключ строки окна глобуса и группа.
LAYERS = (("stars", "sky"), ("air", "sky"), ("clouds", "sky"), ("sun", "sky"),
          ("satellites", "sky"), ("geology", "depths"), ("quakes", "depths"),
          ("plates", "depths"), ("faults", "depths"),
          ("platemotion", "depths"), ("volcanoes", "depths"),
          ("magpoles", "depths"), ("magdecl", "depths"), ("emag", "depths"),
          ("gravity", "depths"), ("bouguer", "depths"), ("geoid", "depths"),
          ("seafloor_age", "depths"),
          ("heatflow", "depths"),
          ("deposits", "depths"), ("mining", "depths"),
          ("osm_mines", "depths"), ("plants", "infra"),
          ("currents", "water"),
          ("cutaway", "depths"), ("paleo", "depths"), ("slope", "terrain"),
          ("aspect", "terrain"))
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
        ("depths", tr("Недра"), tr(
            "Геологическая карта, землетрясения, границы плит и разломы, "
            "месторождения и горные разработки, разрез Земли "
            "и палеогеография.")),
        ("infra", tr("Энергетика"), tr(
            "Электростанции мира, линии электропередачи, подстанции, "
            "трубопроводы и подводные кабели.")),
        ("terrain", tr("Анализ рельефа"), tr(
            "Раскраска поверхности по уклону или по стороне "
            "света склона, включается одна из двух. Горизонтали "
            "рельефа поверх них.")),
        (SAT_GROUP, tr("Спутники"), tr(
            "Группы искусственных спутников CelesTrak. Щелчок по группе "
            "показывает её на глобусе или убирает.")))


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
        "quakes": (tr("Землетрясения"), tr(
            "Землетрясения магнитудой от 4.5 за последние 30 "
            "суток по сводке USGS. Кружок стоит в очаге на его "
            "глубине, линия ведёт к эпицентру на поверхности. "
            "Цвет показывает глубину очага, размер - магнитуду. "
            "Сводка загружается при включении строки.")),
        "deposits": (tr("Месторождения"), tr(
            "Месторождения, рудники и проявления полезных ископаемых "
            "USGS - база MRDS, около 300 тысяч точек, больше всего в США, "
            "3 тысячи крупных месторождений мира и 6.5 тысячи рудников "
            "и заводов мира с оператором и мощностью. Цвет - группа "
            "полезного ископаемого, большая точка - крупное "
            "месторождение, рудник или завод. Щелчок по точке показывает "
            "название, ископаемые, тип и ссылку на запись USGS. Первое "
            "включение скачивает около 25 МБ.")),
        "mining": (tr("Горные разработки"), tr(
            "Контуры карьеров, отвалов, хвостохранилищ и промплощадок "
            "мира по снимкам Sentinel-2 2019 года - около 45 тысяч "
            "участков, Maus и соавторы, 2022. Щелчок по контуру "
            "показывает страну и площадь. Первое включение скачивает "
            "около 25 МБ.")),
        "osm_mines": (tr("Шахты и карьеры OSM"), tr(
            "Шахты, рудники, стволы и карьеры из OpenStreetMap с "
            "названиями и ископаемым. Загружаются по месту вида, когда "
            "камера ниже 150 км. Цвет - группа ископаемого, как у "
            "месторождений. Щелчок по точке показывает название, "
            "оператора и ссылку на объект OpenStreetMap.")),
        "plants": (tr("Электростанции"), tr(
            "Около 35 тысяч электростанций мира из базы WRI Global Power "
            "Plant Database, данные на 2021 год. Цвет - вид топлива, "
            "размер - мощность. Щелчок по точке показывает название, "
            "мощность, год ввода и владельца. У части станций место "
            "в базе указано неверно. Первое включение скачивает около "
            "4 МБ.")),
        "currents": (tr("Течения"), tr(
            "Поверхностные течения океана белыми бегущими струйками над "
            "заливкой скорости. Геострофические течения NOAA CoastWatch по "
            "спутниковой альтиметрии за последние готовые сутки, сетка "
            "0.5°. Первое включение за сеанс скачивает около 4 МБ.")),
        "cables": (tr("Подводные кабели"), tr(
            "Подводные линии связи (бирюзовые) и силовые кабели "
            "(лиловые) из OpenStreetMap, видны с любой высоты. В OSM "
            "нанесена часть кабелей мира, больше всего в Атлантике "
            "и у Европы. Щелчок по линии показывает название, владельца "
            "и ссылку на объект OpenStreetMap.")),
        "infra_osm": (tr("ЛЭП, кабели и трубопроводы OSM"), tr(
            "Линии электропередачи по напряжению, подстанции, кабели "
            "и трубопроводы газа, нефти и воды из OpenStreetMap. "
            "Загружаются по месту вида, когда камера ниже 150 км. Щелчок "
            "по линии показывает напряжение, вещество, оператора и "
            "ссылку на объект OpenStreetMap.")),
        "plates": (tr("Границы плит"), tr(
            "Границы литосферных плит по модели PB2002. Красные - "
            "раздвиг плит на хребтах и рифтах, зелёные - сдвиг "
            "по трансформным разломам, синие - схождение "
            "в зонах субдукции и коллизии. Названия плит стоят "
            "надписями. Тип границы и скорость плит показывает "
            "окно «Объекты».")),
        "magpoles": (tr("Магнитные полюса"), tr(
            "Северный и южный магнитные полюса - точки, где стрелка "
            "компаса стоит отвесно, - на год шкалы времени и их путь "
            "с 1590 года по данным NOAA NCEI. Шкала открывается сама, "
            "бегунок ведёт полюса по годам. Щелчок по глобусу в режиме "
            "«Определить объекты» показывает склонение, наклонение "
            "и напряжённость поля в точке на тот же год по моделям "
            "gufm1 и IGRF-14, с 1590 по 2030 год.")),
        "magdecl": (tr("Линии склонения"), tr(
            "Линии равного магнитного склонения - угла между стрелкой "
            "компаса и направлением на север - через 10° на год шкалы "
            "времени по моделям IGRF-14 с 1900 года и gufm1 с 1590 "
            "года, gufm1 скачивается при первом показе. Красные - "
            "склонение восточное, синие - западное, зелёная - нулевое. "
            "У магнитных полюсов линии сходятся.")),
        "volcanoes": (tr("Вулканы"), tr(
            "Около 1200 вулканов, извергавшихся за последние 12 тысяч лет, "
            "по списку Global Volcanism Program Смитсоновского института. "
            "Цвет - время последнего извержения, размер - высота вулкана. "
            "Щелчок по точке показывает тип вулкана, год последнего "
            "извержения, тектоническую обстановку и страницу вулкана на "
            "сайте GVP. Первое включение скачивает около 2 МБ.")),
        "faults": (tr("Активные разломы"), tr(
            "Около 13.7 тысячи активных разломов мира по базе GEM Global "
            "Active Faults, сведённой из региональных каталогов. "
            "Цвет показывает вид смещения. Это сброс, взброс или надвиг, "
            "сдвиг, срединный хребет и складка. Щелчок по линии показывает "
            "название, вид "
            "смещения, скорость в мм/год, падение и каталог-источник. "
            "Первое включение скачивает около 11 МБ.")),
        "geology": (tr("Геологическая карта"), tr(
            "Геологическая карта мира Macrostrat, сведённая из карт разного "
            "масштаба. Цвет показывает возраст пород. В России и Европе "
            "самая подробная карта - 1:5 000 000, в США карты намного "
            "подробнее. Щелчок в режиме «Определить объекты» показывает "
            "подразделение, литологию, возраст в млн лет и карту-источник. "
            "На глобусе одна такая карта - геологическая или карта "
            "значений геофизики.")),
        "platemotion": (tr("Скорости плит"), tr(
            "Стрелки движения литосферных плит по модели NNR-MORVEL56 - "
            "скорость относительно среднего движения всех плит. Длина "
            "стрелки растёт со скоростью, число у её начала - мм/год. "
            "Тихоокеанская плита идёт на северо-запад около 70 мм/год, "
            "Евразийская - около 25. Окно «Объекты» показывает плиту, "
            "скорость и направление в точке.")),
        "seafloor_age": (tr("Возраст океанического дна"), tr(
            "Возраст океанической коры по сетке Seton и соавторов 2020 "
            "года, шаг 0.1°. Молодое дно у срединных хребтов красное, "
            "древнее у окраин океанов - синее и фиолетовое. Суша и "
            "континентальная кора не закрашены. На глобусе одна карта "
            "значений - возраст дна, магнитные аномалии, сила тяжести "
            "или тепловой поток. Щелчок в режиме «Определить объекты» "
            "показывает возраст в млн лет.")),
        "gravity": (tr("Аномалии силы тяжести"), tr(
            "Аномалия силы тяжести в свободном воздухе по модели XGM2019e "
            "до степени 719, шаг около 28 км. Красные - сила тяжести "
            "больше нормальной, синие - меньше. Над глубоководными "
            "желобами провалы до -300 мГал, над вулканическими островами "
            "и горами - подъём. Щелчок в режиме «Определить объекты» "
            "показывает аномалию в мГал.")),
        "bouguer": (tr("Аномалии Буге"), tr(
            "Аномалия силы тяжести за вычетом притяжения рельефа - "
            "поправка Буге по рельефу ETOPO 2022 с плотностью породы "
            "2670 кг/м³, вода и лёд своей плотностью, и поправка на "
            "рельеф вокруг в круге 167 км. Аномалия показывает плотность "
            "недр без влияния гор и глубин океана. Под горами она "
            "отрицательная, это толстая лёгкая кора, над океаном "
            "положительная. Щелчок в режиме «Определить объекты» "
            "показывает аномалию в мГал.")),
        "heatflow": (tr("Тепловой поток"), tr(
            "Поток тепла из недр через поверхность Земли по сетке 0.5°, "
            "построенной по 91 тысяче измерений базы IHFC 2024. Синие - "
            "холодные древние щиты, красные - рифты, хребты и вулканические "
            "области. Вдали от измерений сетка сглажена. Щелчок в режиме "
            "«Определить объекты» показывает поток в мВт/м².")),
        "emag": (tr("Магнитные аномалии"), tr(
            "Аномалии магнитного поля Земли по сетке EMAG2v3 NOAA NCEI - "
            "отклонение поля от нормального на высоте 4 км над "
            "эллипсоидом, шаг около 4 км. Красные - поле сильнее, "
            "синие - слабее. Аномалии выдают строение коры - хребты "
            "и полосы океанского дна, древние щиты, рудные районы. "
            "Пустые места - там съёмки нет. Щелчок в режиме «Определить "
            "объекты» показывает значение в нТл.")),
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
    if key == "quakes":
        return [color for _, color in quakes.DEPTH_STOPS]
    if key in ("deposits", "osm_mines"):
        return [group[2] for group in deposits.GROUPS]
    if key == "plants":
        return [f[2] for f in plants.FUELS]
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


def day_text(day):
    """«2026-10-05» в «05.10.2026»."""
    if not day:
        return ""
    year, month, date = day.split("-")
    return "{}.{}.{}".format(date, month, year)


class NasaMaps(QWidget):
    """Каталог «Добавить данные» в левой панели. window - окно глобуса.

    До 12 октября 2026 года - отдельное окно «Карты и слои». Решение
    автора того же дня - каталог выезжает в панели поверх списка
    «Слоёв», глобус остаётся виден. Слева категории, справа строки
    с флажками и описание выбранной строки. Карты витрины - одна на
    глобусе, слои включаются вместе, строки «Карты» - категория
    каталога.
    """

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.names = dict(map_names(), **layer_names())
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
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        back = QToolButton(self)
        # Синий значок, как кнопки шкалы времени: чёрная стрелка шрифтом
        # терялась, замечание автора от 15 октября 2026 года.
        from .timebar import ICON_SIDE, blue_icon
        back.setIcon(blue_icon("←"))
        back.setIconSize(QSize(ICON_SIDE, ICON_SIDE))
        back.setAutoRaise(True)
        back.setToolTip(tr("Назад к списку слоёв"))
        back.clicked.connect(self.close)
        top.addWidget(back)
        self.search = QLineEdit(self)
        self.search.setPlaceholderText(tr("снег, рудники, ветер"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        top.addWidget(self.search, 1)
        self.groups = QListWidget(self)
        self.groups.setFixedWidth(CATEGORY_WIDTH)
        self.groups.setTextElideMode(enum(Qt, "TextElideMode", "ElideNone"))
        self.groups.setWordWrap(True)
        for key, title, tip in [
                (ALL, tr("Все"), tr("Все карты и слои каталога.")),
                (MAP, tr("Карта"), tr(
                    "Векторная основа OpenFreeMap, координатная сетка, "
                    "3D-здания и горизонтали."))] \
                + list(group_names()) + list(layer_group_names()):
            row = QListWidgetItem(title, self.groups)
            row.setData(KEY_ROLE, key)
            row.setToolTip(tip)
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
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
        layout.addLayout(body, 1)
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
        for key in ENERGY_ROWS:
            self._row(key, "infra", LAYER)
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
        source = self.window.sources[self.window._basemap]
        url = source.tile_url(*themes.THUMB_TILE)
        self._replies["base"] = fetch_bytes(url, self._base_done)

    def _base_done(self, data, error):
        self._replies.pop("base", None)
        image = QImage.fromData(data) if data else QImage()
        self.base = None if image.isNull() else image
        self._queue = []
        for key, (item, group, kind) in self.items.items():
            if kind in ("gibs", themes.TEMPERATURE) or layer_url(key):
                self._queue.append(key)
            elif kind == LAYER:
                self._set_thumb(key, self._layer_thumb(key))
            elif kind in (SAT, VECTOR):
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
        if key == themes.TEMPERATURE:
            z, x, y = themes.THUMB_TILE
            return temperature.url_template(temperature.LAND).replace(
                "{z}", str(z)).replace("{x}", str(x)).replace("{y}", str(y))
        intervals = self.window._theme_domains.get(key)
        if intervals is None:
            theme = themes.BY_KEY[key]
            self.window._theme_fetch(key, "domains", theme.domains_url())
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
        else:
            self._set_thumb(key, tile_image(data, self.base,
                                            themes.CLEAR.get(key, ())))
        self._pump()

    def _set_thumb(self, key, image):
        self.thumbs[key] = image
        self._label(key)

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
        window = self.window
        if kind == LAYER:
            return bool(window.extras.get(key))
        if kind == SAT:
            return bool(window.extras.get("satellites")) \
                and key[len(SAT):] in window.satellite_manager.groups
        if kind == VECTOR:
            return bool(self._vector_keys(key) & set(window._groups))
        return key == window.gallery_key()

    def _vector_keys(self, key):
        from .panel import geo_tree
        rows = geo_tree()[int(key[len(VECTOR):])][2]
        return {row[0] for row in rows}

    def subtitle(self, key):
        """Вторая строка: источник и день карты."""
        kind = self.items[key][2]
        if kind == "gibs":
            intervals = self.window._theme_domains.get(key)
            day = themes.pick_day(intervals) if intervals else None
            return tr("NASA GIBS, {day}", day=day_text(day)) if day \
                else tr("NASA GIBS")
        if kind == "weather":
            return tr("прогноз NOAA SWPC") if key == AURORA \
                else tr("прогноз NOAA GFS")
        if kind == themes.FIRES:
            return tr("NASA FIRMS, 24 часа")
        if kind == themes.TEMPERATURE:
            return tr("NASA GIBS, суша и море")
        if kind == VECTOR:
            return tr("OpenFreeMap")
        if kind == SAT:
            return tr("CelesTrak")
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
        planet = self.window.planet
        relief = bool(getattr(planet, "terrain", None)) or planet.earth
        enabled = enum(Qt, "ItemFlag", "ItemIsEnabled")
        for key, (item, group, kind) in self.items.items():
            self._label(key)
            item.setCheckState(checked if self.is_on(key) else unchecked)
            usable = planet.earth or key in ANY_BODY + ("grid",) \
                or (key in RELIEF_BODY + ("contours",) and relief)
            # Спутники только у Земли, как и слой.
            usable = usable and (kind != SAT or planet.earth)
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
        elif kind == LAYER:
            self.window.set_extra(key, not self.window.extras.get(key))
        elif kind == VECTOR:
            keys = self._vector_keys(key)
            groups = set(self.window._groups)
            groups = groups - keys if keys & groups else groups | keys
            self.window.set_line_groups(groups)
        else:
            self.window.set_theme("" if key == self.window.gallery_key()
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
        self.export.setVisible(bool(self.window.export_key(key)))

    def _toggle_chosen(self):
        if self._chosen in self.items:
            self._clicked(self.items[self._chosen][0])

    def _export_chosen(self):
        row = self.window.export_key(self._chosen)
        if row:
            self.window.active_export(row)

    def _toggle_satellites(self, group):
        """Группа спутников на глобус или с глобуса. Первая группа
        включает слой «Спутники», последняя снятая - выключает."""
        manager = self.window.satellite_manager
        on = bool(self.window.extras.get("satellites"))
        groups = set(manager.groups)
        if on and group in groups:
            groups.discard(group)
        else:
            groups.add(group)
        manager.set_groups(groups)
        if groups and not on:
            self.window.set_extra("satellites", True)
        elif not groups and on:
            self.window.set_extra("satellites", False)
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
        seen = {"maps": False, "layers": False}
        for key, (item, group, kind) in self.items.items():
            # Во «Всех» групп спутников нет, во вкладке «Спутники» есть
            # и сам слой. Поиск идёт по всему каталогу.
            if text:
                fits = text in self.names[key][0].lower() \
                    or text in self.names[key][1].lower()
            elif self._group == ALL:
                fits = kind != SAT
            else:
                fits = group == self._group or (
                    self._group == SAT_GROUP and key == "satellites")
            item.setHidden(not fits)
            if fits:
                seen["layers" if kind in (LAYER, SAT, VECTOR)
                     else "maps"] = True
        for name, head in self.heads.items():
            head.setHidden(not seen[name])

    def close(self):
        """Каталог уходит, панель снова показывает список слоёв."""
        self.stop()
        self.window.close_gallery()
        return True

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
        return (kind in ("gibs", themes.TEMPERATURE) or layer_url(key)) \
            and key not in self._replies and key not in self._loaded
