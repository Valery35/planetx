# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Страницы PlanetX для www.informpp.ru - главная и пять разделов.

    python tools/build_pages.py

Решение автора от 17 октября 2026 года - модулю одна страница мала,
нужна группа страниц. Каждая страница - самодостаточный файл HTML
в site/pages для блока «Встроить» Google Сайтов, на двух языках
с переключателем, снимки встроены строками data:. Меню ведёт по
подстраницам сайта (адреса - PAGES), ссылки открываются во всём окне.
Стиль, снимки и подпись источников - как у прежней одной страницы
tools/build_site.py. Раздел «Что нового» собирается из CHANGELOG.md
(русский) и поля changelog файла metadata.txt (английский).
"""
import base64
import html
import io
import json
import os
import re
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_site  # noqa: E402

ROOT = build_site.ROOT
OUT = os.path.join(ROOT, "site", "pages")
SITE = "https://www.informpp.ru/главная-страница/qgis-planetx"
# Страница: ключ, путь подстраницы, название по-русски и по-английски.
PAGES = (
    ("main", "", "Главная", "Overview"),
    ("places", "places", "Метки", "Places"),
    ("project", "project", "Проект QGIS", "QGIS project"),
    ("data", "data", "Данные", "Data"),
    ("imagery", "imagery", "Космоснимки", "Satellite imagery"),
    ("news", "news", "Что нового", "What's new"),
)
NEWS_FROM = (0, 93, 0)  # «Что нового» - выпуски с этого номера
RELEASES = "https://github.com/Valery35/planetx/releases/latest"
CHANGELOG_URL = "https://github.com/Valery35/planetx/blob/main/CHANGELOG.md"


def url(path):
    return SITE + ("/" + path if path else "")


# ---------------------------------------------------------------- тексты

T = {}  # ключ - (русский, английский)


def t(key, ru, en):
    T[key] = (ru, en)
    return key


def span(key, tag="span", cls=""):
    attr = ' class="%s"' % cls if cls else ""
    return '<%s%s data-i18n="%s"></%s>' % (tag, attr, key, tag)


def figure(src, key):
    return ('<figure><img alt="" src="%s">\n<figcaption data-i18n="%s">'
            '</figcaption></figure>' % (src, key))


def features(prefix, items, group=None):
    """Строки возможностей: (название ru, en, описание ru, en[,
    источник]). group - (ru, en) заголовок группы строк или None."""
    out = []
    if group:
        out.append('<div class="group" data-i18n="%s"></div>'
                   % t(prefix + ".g", *group))
    for n, item in enumerate(items, 1):
        h = t("%s.r%d.h" % (prefix, n), item[0], item[1])
        p = t("%s.r%d.p" % (prefix, n), item[2], item[3])
        note = ""
        if len(item) > 4 and item[4]:
            note = '<em class="src">%s</em>' % html.escape(item[4])
        out.append('<div class="row"><b data-i18n="%s"></b><span>'
                   '<span data-i18n="%s"></span>%s</span></div>'
                   % (h, p, note))
    return "\n".join(out)


def table(*blocks):
    return '<div class="tools">%s</div>' % "\n".join(blocks)


def cards(prefix, items, kind="trio"):
    out = ['<div class="%s">' % kind]
    for n, (h_ru, h_en, p_ru, p_en) in enumerate(items, 1):
        h = t("%s.c%d.h" % (prefix, n), h_ru, h_en)
        p = t("%s.c%d.p" % (prefix, n), p_ru, p_en)
        out.append('<div class="card"><h3 data-i18n="%s"></h3>'
                   '<p data-i18n="%s"></p></div>' % (h, p))
    out.append("</div>")
    return "\n".join(out)


def section(sid, eyebrow, h2, sub, body=""):
    e = t(sid + ".eyebrow", *eyebrow)
    h = t(sid + ".h2", *h2)
    s = t(sid + ".sub", *sub) if sub else None
    return ('<section id="%s"><div class="wrap">\n'
            '<div class="eyebrow" data-i18n="%s"></div>\n'
            '<h2 data-i18n="%s"></h2>\n%s%s\n</div></section>'
            % (sid, e, h, '<p class="sub" data-i18n="%s"></p>\n' % s
               if s else "", body))


def buttons(main=True):
    t("cta.release", "Скачать выпуск", "Download the release")
    t("cta.install", "Каталог модулей QGIS", "QGIS plugin catalogue")
    t("cta.code", "Исходный код", "Source code")
    t("cta.manual", "Руководство PDF", "Manual PDF")
    t("cta.manual.url", build_site.PDF_URL + "PlanetX.pdf",
      build_site.PDF_URL + "PlanetX_en.pdf")
    rows = ['<div class="cta">',
            '<a class="btn btn-main" target="_blank" data-i18n="cta.release" '
            'href="%s"></a>' % RELEASES,
            '<a class="btn btn-ghost" target="_blank" data-i18n="cta.install" '
            'href="https://plugins.qgis.org/plugins/planetx/"></a>']
    if main:
        rows += ['<a class="btn btn-ghost" target="_blank" data-i18n='
                 '"cta.code" href="https://github.com/Valery35/planetx"></a>',
                 '<a class="btn btn-ghost" target="_blank" data-i18n='
                 '"cta.manual" data-i18n-href="cta.manual.url" href="%s">'
                 '</a>' % RELEASES]
    rows.append("</div>")
    return "\n".join(rows)


# ---------------------------------------------------------------- страницы

def page_main(img):
    t("hero.eyebrow", "Плагин QGIS · 3D-глобус", "QGIS plugin · 3D globe")
    t("hero.h1", "Вся Земля в окне QGIS, от космоса до улицы",
      "The whole Earth in a QGIS window, from space to the street")
    t("hero.lead",
      "PlanetX открывает глобус в QGIS. Космоснимки лежат на рельефе, "
      "вокруг планеты светится атмосфера, границы, дороги и названия "
      "включаются флажками. Слои текущего проекта ложатся на глобус "
      "в порядке карты, рядом - открытые данные о Земле от недр до неба.",
      "PlanetX opens a globe right inside QGIS. Satellite imagery lies on "
      "the terrain, the atmosphere glows around the planet, and borders, "
      "roads and names are switched on with check boxes. Layers of the "
      "current project lie on the globe in the map order, next to open "
      "data about the Earth from its depths to the sky.")
    t("hero.shot", "Кавказ с наклоном камеры. Эльбрус, Сванетия, вершины "
      "с высотой, заповедники и национальные парки.",
      "The Caucasus with a tilted camera. Elbrus, Svaneti, peaks with "
      "their heights, nature reserves and national parks.")
    hero = ('<div class="wrap hero">\n%s\n%s\n%s\n%s\n'
            '<figure class="shot"><img alt="" src="%s">\n'
            '<figcaption data-i18n="hero.shot"></figcaption></figure>\n'
            '</div>' % (span("hero.eyebrow", "div", "eyebrow"),
                        span("hero.h1", "h1"),
                        span("hero.lead", "p", "lead"), buttons(),
                        img("caucasus.jpg")))
    # Плашки главной - ссылки на подстраницы, просьба автора от
    # 17 октября 2026 года «с главной ссылки на остальные». Отдельного
    # блока разделов нет, он повторял плашки.
    tasks = (
        ("create", "places", "Создавать", "Create",
         "Метки, пути, многоугольники, круги, картинки на поверхности "
         "и 3D-модели на рельефе. KML и KMZ из Google Earth открываются "
         "с папками, видами, временем и турами.",
         "Placemarks, paths, polygons, circles, surface images and 3D "
         "models on the terrain. KML and KMZ from Google Earth open with "
         "folders, views, time and tours."),
        ("present", "places", "Показывать", "Present",
         "Туры с подписями остановок, своими слоями и временем, запись "
         "видео MP4, сцена одним файлом, страница HTML с глобусом.",
         "Tours with stop captions, own layers and time, MP4 video "
         "recording, a scene in one file, an HTML page with the globe."),
        ("measure", "places", "Измерять", "Measure",
         "Длина и площадь по рельефу, профиль высот с водой морей и озёр, "
         "видимость из точки, часы солнца, маршрут, номер листа карты.",
         "Length and area along the terrain, an elevation profile with "
         "the water of seas and lakes, viewshed, hours of sun, a route, a "
         "map sheet number."),
        ("project", "project", "Работать с проектом QGIS", "Work with the "
         "QGIS project",
         "Слои проекта на рельефе, свой рельеф до 1 м и батиметрия, гриды "
         "и скважины под землёй, геологический разрез вдоль пути.",
         "Project layers on the terrain, own terrain down to 1 m and "
         "bathymetry, grids and boreholes underground, a geological "
         "section along a path."),
        ("data", "data", "Изучать данные о Земле", "Study Earth data",
         "Около 90 карт и слоёв - геология и геофизика, землетрясения "
         "с 1904 года, воды, почвы, погода, темы NASA, энергетика.",
         "About 90 maps and layers - geology and geophysics, earthquakes "
         "since 1904, water, soils, weather, NASA themes, energy."),
        ("imagery", "imagery", "Брать космоснимки", "Get satellite images",
         "Sentinel-2, Landsat с 1972 года, ASTER и MODIS участком "
         "в проект QGIS - каналы, индексы, температура, ряд по датам.",
         "Sentinel-2, Landsat since 1972, ASTER and MODIS of an area into "
         "the QGIS project - bands, indices, temperature, time series."),
    )
    paths = dict((k, path) for k, path, _, _ in PAGES)
    parts = []
    for key, page_key, h_ru, h_en, p_ru, p_en in tasks:
        h = t("tasks.%s.h" % key, h_ru, h_en)
        p = t("tasks.%s.p" % key, p_ru, p_en)
        parts.append('<a class="card link" target="_blank" href="%s">'
                     '<h3 data-i18n="%s"></h3><p data-i18n="%s"></p></a>'
                     % (url(paths[page_key]), h, p))
    tasks = section(
        "tasks", ("Что можно делать", "What you can do"),
        ("От меток и туров до разреза под участком",
         "From placemarks and tours to a section under a site"), None,
        '<div class="trio">%s</div>' % "\n".join(parts))
    idea = section(
        "idea", ("Как устроен глобус", "How the globe works"),
        ("Своё окно, свой движок, данные из открытых источников",
         "Its own window, its own engine, data from open sources"),
        ("Глобус рисуется на OpenGL 3.3 собственным движком, а не штатным "
         "3D-видом QGIS. Тайлы подложки, высот и векторной основы идут через "
         "сетевые настройки и кэш QGIS. В видеокарту попадают только "
         "смещения от центра тайла и от глаза, на уровне улиц картинка "
         "не дрожит. Работает в QGIS 3.36 и новее и в QGIS 4, на Windows "
         "и Linux.",
         "The globe is drawn with OpenGL 3.3 by its own engine rather than "
         "the built-in QGIS 3D view. Base map, terrain and vector tiles go "
         "through the QGIS network settings and cache. Only offsets from "
         "the tile centre and from the eye reach the graphics card, the "
         "picture does not jitter at street level. Works in QGIS 3.36 and "
         "later and in QGIS 4, on Windows and Linux."),
        figure(img("window.jpg"), t(
            "idea.fig", "Окно глобуса над Пермью с 13 км. Слева разделы "
            "«Метки», «Проект QGIS» и «Слои», вверху панель значков, справа "
            "кольцо навигации.", "The globe window over Perm from 13 km. On "
            "the left the Places, QGIS project and Layers sections, the icon "
            "bar on top, the navigation ring on the right.")) + cards("idea", (
            ("Подложка и рельеф", "Base map and terrain",
             "Esri World Imagery как пример, OpenStreetMap, OpenTopoMap, "
             "готовые снимки и карты или любое подключение XYZ Tiles. "
             "Рельеф Terrarium, Copernicus DEM 30 м или GEDTM30, дно морей "
             "по сетке GEBCO 2026.",
             "Esri World Imagery as an example, OpenStreetMap, OpenTopoMap, "
             "ready imagery and maps or any XYZ Tiles connection. Terrarium, "
             "Copernicus DEM 30 m or GEDTM30 terrain, the sea floor from the "
             "GEBCO 2026 grid."),
            ("Ровные подписи", "Upright labels",
             "Названия стран, городов, рек, вершин с высотой, заповедников "
             "и номера дорог из векторной основы OpenFreeMap. Надписи ровные "
             "при любом повороте, язык - QGIS, местный или один из 15.",
             "Names of countries, cities, rivers, peaks with heights, "
             "reserves and road numbers from the OpenFreeMap vector base. "
             "Labels stay upright at any turn, the language is that of "
             "QGIS, local or one of 15."),
            ("Атмосфера и свет", "Atmosphere and light",
             "Свечение воздуха, небо у горизонта, свет солнца на дату "
             "и время, ночная сторона с огнями городов, 3D-здания "
             "OpenFreeMap.",
             "The glow of the air, the sky at the horizon, sunlight for a "
             "date and time, the night side with city lights, OpenFreeMap "
             "3D buildings."))))
    rows = (
        ("ЛКМ", "Left", "Захват Земли", "Grab the Earth",
         "Точка под курсором следует за мышью, после отпускания Земля "
         "вращается по инерции. Двойной щелчок - перелёт к точке.",
         "The point under the cursor follows the mouse, after release the "
         "Earth keeps rotating by inertia. A double click flies to the "
         "point."),
        ("Колесо", "Wheel", "Приближение к курсору", "Zoom to the cursor",
         "Колесо приближает к точке под курсором, точка остаётся на месте.",
         "The wheel zooms to the point under the cursor, and the point "
         "stays in place."),
        ("СКМ", "Middle", "Поворот и наклон", "Turn and tilt",
         "Средняя кнопка или левая с Shift поворачивают и наклоняют вид, "
         "левая с Ctrl сдвигает его вдоль экрана.", "The middle button or "
         "Shift with the left button turns and tilts the view, Ctrl with "
         "the left button shifts it along the screen."),
        ("N U R", "N U R", "Север, отвесно, сброс", "North, down, reset",
         "N ставит север вверх, U - отвесный взгляд, R - то и другое. "
         "Стрелки сдвигают вид, PageUp и PageDown приближают.",
         "N puts north up, U looks straight down, R does both. The arrows "
         "move the view, PageUp and PageDown zoom."),
        ("Ctrl+K", "Ctrl+K", "Строка «Поиск»", "The Search line",
         "Место, координаты в градусах, UTM или MGRS, слой, окно или "
         "инструмент по названию. Enter выполняет действие или перелетает "
         "к месту.", "A place, coordinates in degrees, UTM or MGRS, a "
         "layer, a window or a tool by name. Enter runs the action or flies "
         "to the place."),
        ("Угол", "Corner", "Кольцо навигации", "Navigation ring",
         "Кольцо компаса, джойстики взгляда и сдвига, ползунок высоты. "
         "Точка в середине кольца возвращает отвесный взгляд.",
         "The compass ring, the look and move sticks, the height slider. "
         "The dot in the middle of the ring returns the straight down "
         "view."),
        ("F11", "F11", "Во весь экран", "Full screen",
         "Панели прячутся, остаются глобус, навигация, шкала времени "
         "и тур - для показа.", "The panels hide, the globe, navigation, "
         "time slider and tour stay - for presentations."))
    tools = ['<div class="tools">']
    for n, (k_ru, k_en, h_ru, h_en, p_ru, p_en) in enumerate(rows, 1):
        tools.append('<div class="tool"><div class="num" data-i18n="%s">'
                     '</div><div class="txt"><b data-i18n="%s"></b>'
                     '<span data-i18n="%s"></span></div></div>' % (
                         t("k%d" % n, k_ru, k_en), t("c%d.h" % n, h_ru, h_en),
                         t("c%d.p" % n, p_ru, p_en)))
    tools.append("</div>")
    controls = section(
        "controls", ("Управление", "Controls"),
        ("Навигация мышью и клавиатурой", "Mouse and keyboard navigation"),
        None, "\n".join(tools))
    worlds = section(
        "worlds", ("Другие тела и небо", "Other bodies and the sky"),
        ("Марс, Луна и звёздное небо", "Mars, the Moon and the starry sky"),
        ("Значок «Тело» заменяет Землю Марсом, Луной и ещё 14 телами по "
         "мозаикам USGS и NASA, у Марса и Луны - с рельефом. Навигация, "
         "метки, туры и линейка работают на любом теле. Пункт «Небо» "
         "показывает 5080 звёзд, 88 созвездий, Солнце, Луну и планеты на "
         "выбранный момент.",
         "The Body icon replaces the Earth with Mars, the Moon and 14 more "
         "bodies from USGS and NASA mosaics, Mars and the Moon with terrain. "
         "Navigation, places, tours and the ruler work on any body. The Sky "
         "item shows 5080 stars, 88 constellations, the Sun, the Moon and "
         "the planets at the chosen moment."),
        '<div class="trio">%s%s%s</div>' % (
            figure(img("mars.jpg", build_site.HALF_WIDTH), t(
                "worlds.mars", "Марс. Вулканы Фарсиды и долины Маринер, "
                "мозаика Viking.", "Mars. The Tharsis volcanoes and Valles "
                "Marineris, Viking mosaic.")),
            figure(img("moon.jpg", build_site.HALF_WIDTH), t(
                "worlds.moon", "Видимая сторона Луны, карта альбедо LOLA "
                "с отмывкой рельефа.", "The near side of the Moon, LOLA "
                "albedo map with hill shading.")),
            figure(img("sky.jpg", build_site.HALF_WIDTH), t(
                "worlds.sky", "Небо 1 октября 2026 года. Орион, Телец "
                "и Близнецы, Луна у Плеяд.", "The sky on 1 October 2026. "
                "Orion, Taurus and Gemini, the Moon at the Pleiades."))))
    fam = section(
        "family", ("Набор плагинов", "The set of plugins"),
        ("PlanetX в линейке Информ++", "PlanetX in the Inform++ family"),
        ("Isoliner строит контуры, Topoliner приводит их в порядок, "
         "Isoliner3D показывает геологию в объёме, PlanetX показывает Землю "
         "целиком. Все плагины работают независимо.",
         "Isoliner builds contours, Topoliner puts them in order, "
         "Isoliner3D shows geology in three dimensions, PlanetX shows the "
         "whole Earth. All plugins work independently."),
        family() + buttons(main=False))
    return "\n".join([hero, tasks, idea, controls, worlds, fam])


def pair(left, right):
    return '<div class="pair">%s%s</div>' % (left, right)


def page_places(img):
    store = section(
        "store", ("Мои метки", "My places"),
        ("Свои объекты на глобусе в одном файле",
         "Your own objects on the globe in one file"),
        ("Метки, пути, многоугольники, круги, картинки, 3D-модели и туры "
         "лежат в разделе «Метки» левой панели. Хранилище - один файл "
         "GeoPackage в профиле QGIS, метки видны в любом проекте. Объекты "
         "рисуются щелчками по глобусу и садятся на рельеф, их можно "
         "поднять над землёй и выдавить до неё.",
         "Placemarks, paths, polygons, circles, images, 3D models and tours "
         "live in the Places section of the left panel. The store is one "
         "GeoPackage file in the QGIS profile, places are visible in any "
         "project. Objects are drawn with clicks on the globe and sit on "
         "the terrain, they can be raised above the ground and extruded "
         "down to it."),
        figure(img("demo.jpg"), t(
            "store.fig", "Демо «Пермь» со шкалой времени на 11:30-13:00. "
            "Эспланада, маршрут прогулки, путь и 3D-здания.", "The Perm demo "
            "with the time slider at 11:30-13:00. The Esplanade, the walk "
            "route, a path and 3D buildings.")) + table(features("kinds", (
            ("Метка", "Placemark",
             "Точка со значком из 35 стандартных или из библиотеки SVG QGIS, "
             "подпись, цвет и размер.",
             "A point with one of 35 standard icons or an icon from the QGIS "
             "SVG library, a label, colour and size."),
            ("Путь и многоугольник", "Path and polygon",
             "Линия и область по дугам большого круга, сгущение по рельефу. "
             "Вершины тянутся мышью, середина отрезка ставит новую.",
             "A line and an area along great circle arcs, densified over the "
             "terrain. Vertices are dragged with the mouse, the middle of a "
             "segment adds a new one."),
            ("Круг", "Circle",
             "Центр и точка окружности, кольцо на эллипсоиде из 128 вершин.",
             "A centre and a point of the circle, a ring of 128 vertices on "
             "the ellipsoid."),
            ("3D-путь и 3D-многоугольник", "3D path and 3D polygon",
             "Точки садятся на крыши и стены 3D-зданий, длина - прямыми "
             "отрезками, площадь и наклон - в плоскости фигуры.",
             "Points sit on roofs and walls of 3D buildings, the length is "
             "measured in straight segments, the area and tilt in the "
             "plane of the shape."),
            ("Картинки", "Images",
             "На поверхности рамкой с поворотом или четырьмя углами, фото "
             "с камерой в пространстве, картинка на экране. Файл или ссылка "
             "с обновлением через промежуток.",
             "On the surface with a rotated box or four corners, a photo "
             "with its camera in space, an image on the screen. A file or a "
             "link refreshed at an interval."),
            ("3D-модели", "3D models",
             "Collada, glTF и OBJ с картинками. Модель ставится на место "
             "ручками рамки - сдвиг, поворот, масштаб, хранится ссылкой на "
             "файл.",
             "Collada, glTF and OBJ with textures. The model is placed with "
             "the handles of its box - move, turn, scale, kept as a link to "
             "the file."),
            ("Папки", "Folders",
             "Вложенные папки, группа переключателей, перенос мышью, "
             "выделение нескольких строк, ползунок непрозрачности.",
             "Nested folders, radio groups, drag and drop, selecting several "
             "rows, an opacity slider."),
            ("Сетевые ссылки", "Network links",
             "Папка с документом KML по адресу, обновление через "
             "промежуток - например лента землетрясений USGS.",
             "A folder with a KML document at an address, refreshed at an "
             "interval - for example the USGS earthquake feed.")))))
    props = section(
        "props", ("Свойства метки", "Placemark properties"),
        ("Вид, время и показ каждой метки",
         "View, time and display of each placemark"),
        ("Окно свойств стоит в панели справа от вида и не мешает глобусу. "
         "Правка видна на глобусе сразу, «OK» её записывает. Щелчок по "
         "метке на глобусе открывает карточку с описанием и кнопкой "
         "«Объясни это» - вопросом помощнику об этой метке.",
         "The properties window stands in the panel to the right of the view "
         "and does not cover the globe. Edits show on the globe at once, OK "
         "saves them. A click on a placemark on the globe opens its card with "
         "the description and the Explain this button - a question to the "
         "assistant about this placemark."),
        table(features("props", (
            ("Оформление", "Style",
             "Цвета линии и заливки с прозрачностью, толщина, значок, "
             "поток штрихов по пути для схем логистики.",
             "Line and fill colours with transparency, width, icon, a flow "
             "of dashes along a path for logistics diagrams."),
            ("Высота", "Height",
             "Подъём над рельефом с ползунком и выдавливание до земли - "
             "стена у линии, столбик у точки.",
             "Lift above the terrain with a slider and extrusion down to the "
             "ground - a wall for a line, a column for a point."),
            ("Время", "Time",
             "Момент или промежуток. Шкала времени показывает метки своего "
             "промежутка, путь с промежутком растёт по шкале.",
             "A moment or an interval. The time slider shows the places of "
             "its interval, a path with an interval grows along the "
             "slider."),
            ("Скрывать дальше", "Hide beyond",
             "Метка или папка видна только ближе заданного расстояния, "
             "Region KML.",
             "A placemark or a folder is visible only closer than a given "
             "distance, KML Region."),
            ("Вид метки", "Placemark view",
             "Точка взгляда, расстояние, азимут и наклон, дата вида, "
             "включённые слои, сектор разреза и непрозрачности строк. "
             "Перелёт и тур возвращают их целиком.",
             "Look-at point, distance, heading and tilt, view date, layers "
             "switched on, the cutaway sector and row opacities. A flight "
             "and a tour bring them all back."),
            ("Описание", "Description",
             "Текст или HTML, как в KML. Показывается в карточке, в подписи "
             "остановки тура и в окне «Объекты».",
             "Text or HTML, as in KML. Shown in the card, in the tour stop "
             "caption and in the Identify window.")))))
    measure = section(
        "measure", ("Измерения", "Measuring"),
        ("Линейка, профиль высот и анализ у метки",
         "Ruler, elevation profile and analysis at a place"),
        ("Измерение сохраняется меткой. Меню пути и точки «Моих меток» "
         "открывает профиль высот, разрез Земли вниз, разрез модели, "
         "видимость, инсоляцию и снимки спутников у метки. Профиль знает "
         "уровень моря и воду своих водоёмов.",
         "A measurement is saved as a placemark. The path and point menus of "
         "My Places open the elevation profile, the Earth section downwards, "
         "the model section, viewshed, insolation and satellite images at "
         "the place. The profile knows the sea level and the water of own "
         "lakes."),
        pair(figure(img("ruler.png", build_site.HALF_WIDTH), t(
                 "measure.ruler", "Линейка - путь 11.5 км на карте и "
                 "12.47 км по рельефу через Эльбрус.", "The ruler - an 11.5 "
                 "km path on the map and 12.47 km along the terrain across "
                 "Elbrus.")),
             figure(img("profile.png", build_site.HALF_WIDTH), t(
                 "measure.profile", "Профиль высот того же пути - высоты, "
                 "набор и потеря высоты, средний и наибольший уклон.",
                 "The elevation profile of the same path - heights, ascent "
                 "and descent, mean and greatest slope."))) + pair(
            figure(img("profile_lake.png", build_site.HALF_WIDTH), t(
                "measure.lake", "Профиль 3 км через Бриенцское озеро по "
                "своей батиметрии. Дно на 308 м, вода до уровня 564 м.",
                "A 3 km profile across Lake Brienz from own bathymetry. The "
                "bed at 308 m, water up to the 564 m level.")),
            figure(img("profile_trench.png", build_site.HALF_WIDTH), t(
                "measure.trench", "Профиль 221 км через Марианский жёлоб "
                "по сетке GEBCO 2026. Дно до -10 797 м.", "A 221 km profile "
                "across the Mariana Trench from the GEBCO 2026 grid. The "
                "floor down to -10 797 m."))) + table(features(
                    "tools", (
                        ("Линейка", "Ruler",
                         "Линия, путь, многоугольник, круг, 3D-путь "
                         "и 3D-многоугольник. Длина на эллипсоиде и по "
                         "рельефу, площадь, курс линии, единицы на выбор.",
                         "Line, path, polygon, circle, 3D path and 3D "
                         "polygon. Length on the ellipsoid and along the "
                         "terrain, area, bearing, units of choice."),
                        ("Профиль высот", "Elevation profile",
                         "До 2000 точек по самому точному уровню высот, "
                         "набор и потеря высоты, уклон, вода морей "
                         "и своих водоёмов, точка под курсором на глобусе.",
                         "Up to 2000 points from the finest height level, "
                         "ascent and descent, slope, the water of seas and "
                         "own lakes, the point under the cursor on the "
                         "globe."),
                        ("Видимость из точки", "Viewshed",
                         "Что видно с высоты наблюдателя в круге до "
                         "десятков километров с учётом кривизны "
                         "и рефракции.",
                         "What is visible from the observer height within a "
                         "circle of up to tens of kilometres with curvature "
                         "and refraction."),
                        ("Инсоляция", "Insolation",
                         "Часы прямого солнца в сутки за промежуток дат "
                         "с тенями от рельефа.",
                         "Hours of direct sun per day over a date range with "
                         "terrain shadows."),
                        ("Маршрут", "Route",
                         "На машине, пешком или на велосипеде. Сервис OSRM "
                         "до тысяч километров, по тайлам основы - до 50 км "
                         "без сервиса.",
                         "By car, on foot or by bicycle. The OSRM service up "
                         "to thousands of kilometres, along base tiles - up "
                         "to 50 km without the service."),
                        ("Номер листа карты", "Map sheet number",
                         "IMW 1:1 000 000, российская номенклатура до "
                         "1:200 000, NATO JOG и квадрат MGRS в точке.",
                         "IMW 1:1 000 000, the Russian nomenclature down to "
                         "1:200 000, NATO JOG and the MGRS square at a "
                         "point.")))))
    tours = section(
        "tours", ("Туры и показ", "Tours and presentation"),
        ("Облёт меток с подписями и запись видео",
         "A fly-through of places with captions and video recording"),
        ("Тур облетает отмеченные метки папки по порядку списка. Каждая "
         "остановка возвращает свой вид, время, слои и сектор разреза. "
         "Подпись остановки стоит внизу кадра. Клавиши → и ← ведут по "
         "остановкам, пробел ставит паузу, на паузе вид вертят мышью.",
         "A tour flies over the checked places of a folder in list order. "
         "Each stop brings back its view, time, layers and cutaway sector. "
         "The stop caption stands at the bottom of the frame. The → and ← "
         "keys step through the stops, Space pauses, the view can be turned "
         "with the mouse during a pause."),
        table(features("tour", (
            ("Темп остановки", "Stop pace",
             "Своя пауза и скорость перелёта у каждой метки, тур по кругу "
             "для показа без присмотра.",
             "Its own pause and flight speed for each placemark, a looped "
             "tour for unattended shows."),
            ("Плавная смена", "Smooth change",
             "Перелёт по методу van Wijk и Nuij, слои остановки проявляются "
             "за полсекунды.",
             "A van Wijk and Nuij flight, the layers of a stop fade in over "
             "half a second."),
            ("Запись", "Recording",
             "Видео MP4 в размере окна или кадры PNG до 3840×2160, каждый "
             "кадр ждёт загрузки тайлов, подписи остановок в кадре.",
             "MP4 video at the window size or PNG frames up to 3840×2160, "
             "each frame waits for the tiles, stop captions in the frame."),
            ("Запись облёта", "Recorded fly-through",
             "Движение камеры записывается меткой-туром, путь облёта "
             "правится мышью.",
             "The camera movement is recorded as a tour placemark, its path "
             "is edited with the mouse.")))))
    share = section(
        "share", ("Обмен", "Exchange"),
        ("KML, сцены, страница HTML и помощник",
         "KML, scenes, an HTML page and the assistant"),
        None,
        table(features("share", (
            ("KML и KMZ", "KML and KMZ",
             "Открытие и запись папок, стилей, видов, времени, Region, "
             "треков gx:Track, туров gx:Tour, картинок и моделей. Файлы "
             "Google Earth открываются, копия в буфер обмена вставляется "
             "в Google Earth.",
             "Opening and writing folders, styles, views, time, Region, "
             "gx:Track tracks, gx:Tour tours, images and models. Google Earth "
             "files open, a copy to the clipboard pastes into Google "
             "Earth."),
            ("Сцена", "Scene",
             "Файл .planetx - камера, время, слои проекта ссылкой, строки "
             "«Слоёв», сектор разреза и метки сцены. Открывается на другом "
             "компьютере.",
             "A .planetx file - camera, time, project layers by reference, "
             "Layers rows, the cutaway sector and the scene places. It opens "
             "on another computer."),
            ("Поделиться видом", "Share the view",
             "Страница HTML с глобусом, метками и облётом открывается "
             "в браузере без QGIS.",
             "An HTML page with the globe, places and fly-through opens in a "
             "browser without QGIS."),
            ("Помощник", "Assistant",
             "Метки по описанию одним запросом - «Путешествия Колумба» "
             "с датами этапов, разговор с действиями модуля. Claude, Grok, "
             "DeepSeek, OpenRouter или своя модель.",
             "Places from a description in one request - Columbus voyages "
             "with dates of the legs, a conversation with plugin actions. "
             "Claude, Grok, DeepSeek, OpenRouter or a local model."),
            ("Демо", "Demos",
             "Подготовленные сцены - Пермь, Японский жёлоб, Аральское море, "
             "Москва в исторических картах, карьер, Бриенцское озеро, "
             "3D-модели, Марс, Луна, небо.",
             "Prepared scenes - Perm, the Japan Trench, the Aral Sea, Moscow "
             "in historical maps, a quarry, Lake Brienz, 3D models, Mars, the "
             "Moon, the sky.")))) + pair(
            figure(img("aral.jpg", build_site.HALF_WIDTH), t(
                "share.aral", "Демо «Аральское море». Снимки MODIS 2000, 2014 "
                "и 2023 годов по ссылкам, фото и карта на экране.",
                "The Aral Sea demo. MODIS images of 2000, 2014 and 2023 by "
                "links, a photo and a map on the screen.")),
            figure(img("models.jpg", build_site.HALF_WIDTH), t(
                "share.models", "Демо «3D-модели» - церковь Покрова "
                "в Перми, модель Collada на своём месте.", "The 3D models "
                "demo - the Church of the Intercession in Perm, a Collada "
                "model in its place."))))
    return "\n".join([store, props, measure, tours, share])


def page_project(img):
    layers = section(
        "layers", ("Слои проекта", "Project layers"),
        ("Карта QGIS на рельефе глобуса", "The QGIS map on the globe terrain"),
        ("Отмеченные слои текущего проекта рисует сам QGIS - со стилями, "
         "порядком и прозрачностью карты, - и картинка ложится на рельеф. "
         "Векторные, растровые, WMS, XYZ, PostGIS и любые другие слои QGIS. "
         "Правка данных и стиля видна на глобусе после перерисовки, "
         "автообновление включено по умолчанию.",
         "The checked layers of the current project are drawn by QGIS "
         "itself - with the styles, order and opacity of the map - and the "
         "picture lies on the terrain. Vector, raster, WMS, XYZ, PostGIS and "
         "any other QGIS layers. Edits to the data and style show on the "
         "globe after a redraw, auto refresh is on by default."),
        table(features("link", (
            ("Связь с картой", "Link with the map",
             "Глобус следует за окном карты QGIS или карта за глобусом, "
             "в любой системе координат. Выделение объектов общее.",
             "The globe follows the QGIS map window or the map follows the "
             "globe, in any coordinate system. Feature selection is "
             "shared."),
            ("Подписи", "Labels",
             "Подписи слоёв по настройкам QGIS ставятся надписями глобуса - "
             "ровно при любом повороте, без обрезки на стыках тайлов.",
             "Layer labels from the QGIS settings become globe labels - "
             "upright at any turn, not cut at tile edges."),
            ("Опрос щелчком", "Identify",
             "Окно «Объекты» показывает атрибуты слоёв под щелчком вместе "
             "с метками, очагами, высотой, корой и значениями карт.",
             "The Identify window shows layer attributes under the click "
             "together with places, quakes, height, crust and map "
             "values."),
            ("Время слоёв", "Layer time",
             "Слой с временными свойствами QGIS показывается на промежутке "
             "шкалы времени глобуса. Точечный слой с полем времени - трек "
             "с камерой следом.",
             "A layer with QGIS temporal properties is shown for the "
             "interval of the globe time slider. A point layer with a time "
             "field is a track with a follow camera."),
            ("Исторические карты", "Historical maps",
             "Растру ставится год. Карты одной группы сменяют друг друга по "
             "шкале, шторка сравнивает два года. Карты Рамсея из каталога "
             "56 тысяч листов привязываются в проект.",
             "A raster gets a year. Maps of one group replace each other "
             "along the slider, a swipe compares two years. Rumsey maps from "
             "a catalogue of 56 thousand sheets are georeferenced into the "
             "project."),
            ("Выдавливание", "Extrusion",
             "Многоугольники, линии и точки слоя поднимаются по полю или "
             "постоянной высоте - кварталы, стены, столбики, цвет из "
             "стиля.",
             "Polygons, lines and points of a layer are extruded by a field "
             "or a constant height - blocks, walls, columns, colour from "
             "the style.")))) + pair(
            figure(img("moscow.jpg", build_site.HALF_WIDTH), t(
                "layers.moscow", "Демо «Москва, исторические карты» - "
                "карта своего года поверх снимка, шкала ведёт по годам.",
                "The Moscow historical maps demo - the map of its year over "
                "imagery, the slider steps through the years.")),
            figure(img("contours.jpg", build_site.HALF_WIDTH), t(
                "layers.contours", "Горизонтали у Эльбруса на снимке, "
                "выгружаются в проект слоем с отметками.", "Contours at "
                "Elbrus over imagery, exported to the project as a layer "
                "with elevations."))))
    relief = section(
        "relief", ("Свой рельеф", "Own terrain"),
        ("Съёмка, батиметрия, выемка и насыпь",
         "Survey, bathymetry, cut and fill"),
        ("Растр высот проекта врезается в рельеф глобуса с плавным краем "
         "и уровнями до 17 - около 1 м на пиксель. Растр глубин водоёма "
         "даёт дно и воду на своём уровне. Профиль высот, линейка, уклон "
         "и горизонтали считают по своему рельефу.",
         "A project elevation raster is inset into the globe terrain with "
         "a smooth edge and levels down to 17 - about 1 m per pixel. A lake "
         "depth raster gives the bed and the water at its own level. The "
         "elevation profile, ruler, slope and contours use the own "
         "terrain."),
        figure(img("brienz.jpg"), t(
            "relief.fig", "Демо «Бриенцское озеро». Дно по сетке "
            "swissBATHY3D 10 м, вода на уровне 564 м, путь через самое "
            "глубокое место.", "The Lake Brienz demo. The bed from the "
            "swissBATHY3D 10 m grid, water at 564 m, a path across the "
            "deepest point.")) + table(features("relief", (
                ("Рельеф глобуса", "Globe terrain",
                 "Пункт меню растра. Растр в любой системе координат, "
                 "несколько растров по порядку проекта, сцена хранит выбор.",
                 "A raster menu item. A raster in any coordinate system, "
                 "several rasters in project order, the scene keeps the "
                 "choice."),
                ("Батиметрия водоёма", "Lake bathymetry",
                 "Растр глубин или отметок дна и уровень воды. Вода видна на "
                 "глобусе и на профиле высот.",
                 "A raster of depths or bed elevations and the water level. "
                 "The water shows on the globe and on the elevation "
                 "profile."),
                ("Батиметрия по промерам", "Bathymetry from soundings",
                 "Точки эхолота с глубиной в поле или Z - грид глубин с "
                 "шагом по плотности промеров и маской дальше 10 шагов.",
                 "Echo sounder points with depth in a field or Z - a depth "
                 "grid with a cell from the sounding density and a mask "
                 "beyond 10 cells."),
                ("Выемка и насыпь", "Cut and fill",
                 "Две съёмки на одной сетке - объёмы и площади выемки "
                 "и насыпи с порогом, растр разности со шкалой.",
                 "Two surveys on one grid - cut and fill volumes and areas "
                 "with a threshold, a difference raster with a "
                 "scale."),
                ("Горизонтали в проект", "Contours into the project",
                 "Горизонтали видимого участка и изолинии растра - слой "
                 "GeoPackage с подписями отметок.",
                 "Contours of the visible area and isolines of a raster - a "
                 "GeoPackage layer with elevation labels.")))))
    under = section(
        "under", ("Под землёй", "Underground"),
        ("Геологическая модель из слоёв проекта",
         "A geological model from project layers"),
        ("Скважины, кровли пластов, гриды, тоннели и слои с отметками Z - "
         "обычные слои проекта. Флажок слоя ставит его под землю, земля над "
         "моделью становится прозрачной, многоугольник «Моих меток» "
         "вырезает блок, камера опускается под поверхность. Щелчок по "
         "стволу даёт пласт и глубину по стволу.",
         "Boreholes, bed tops, grids, tunnels and layers with Z values are "
         "ordinary project layers. A layer check box puts it underground, "
         "the ground above the model turns transparent, a My Places "
         "polygon cuts a block, the camera goes below the surface. A click "
         "on a hole gives the bed and the depth along the hole."),
        figure(img("b2_close.jpg"), t(
            "under.fig", "Рабочий проект у Соликамска - гриды кровель "
            "и подошв пластов В, А'Б и КрII под прозрачной землёй, "
            "изолинии на верхней кровле, стенки блока до низа модели.",
            "A working project near Solikamsk - grids of the tops and "
            "bottoms of the V, A'B and KrII beds under transparent ground, "
            "isolines on the upper top, block walls down to the model "
            "bottom.")) + table(features(
                "under", (
                    ("Скважины", "Boreholes",
                     "Устья, интервалы и инклинометрия, ствол по минимальной "
                     "кривизне, цвет по коду пласта.",
                     "Collars, intervals and surveys, the hole by minimum "
                     "curvature, colour by bed code."),
                    ("Кровли и гриды", "Tops and grids",
                     "Растр отметок - поверхность под землёй в цветах стиля "
                     "QGIS, пара _top и _bottom - пласт с торцами, блок "
                     "со стенками до низа модели.",
                     "An elevation raster is a surface underground in the "
                     "QGIS style colours, a _top and _bottom pair is a bed "
                     "with edges, a block with walls down to the model "
                     "bottom."),
                    ("Объёмом по Z", "Volume by Z",
                     "Линии и многоугольники с отметками Z - «3D-забор» "
                     "разреза, тоннели, здания многогранниками.",
                     "Lines and polygons with Z values - a section fence, "
                     "tunnels, buildings as polyhedral surfaces."),
                    ("Разрезы с картинкой", "Sections with an image",
                     "Картинка разреза на вертикальной стенке вдоль линии "
                     "между отметками верха и низа.",
                     "A section picture on a vertical wall along a line "
                     "between the top and bottom elevations.")))))
    section_ = section(
        "model", ("Разрез модели", "Model section"),
        ("Геологический разрез вдоль пути", "A geological section along a "
         "path"),
        ("Окно «Разрез модели» строит разрез по любому пути «Моих меток» "
         "из отмеченных слоёв проекта - кровель, скважин в полосе вдоль "
         "линии и объектов с Z. Цвета пластов и породы между ними задаются "
         "щелчком правой кнопки по разрезу и хранятся в проекте. Разрез "
         "сохраняется картинкой PNG и таблицей CSV по точкам пути.",
         "The Model section window builds a section along any My Places "
         "path from the checked project layers - tops, boreholes in a band "
         "along the line and Z objects. Colours of the beds and of the rock "
         "between them are set with a right click on the section and kept "
         "in the project. The section is saved as a PNG picture and a CSV "
         "table by path points."),
        figure(img("b2_section.png"), t(
            "model.fig", "Разрез 13 км через тот же проект - рельеф, "
            "пласты В, А'Б и КрII своими цветами, порода между ними.",
            "A 13 km section across the same project - terrain, the V, A'B "
            "and KrII beds in their colours, the rock between them.")) +
        figure(img("model_section.png"), t(
            "model.fig2", "Демо «Пермские отложения» - 9 кровель, 6 "
            "скважин в полосе 200 м, наклонная скважина C-04.",
            "The Permian deposits demo - 9 tops, 6 boreholes in a 200 m "
            "band, the inclined hole C-04.")))
    back = section(
        "back", ("Обратно в проект", "Back to the project"),
        ("Данные глобуса слоями QGIS", "Globe data as QGIS layers"),
        None, table(features("back", (
            ("Видимое на глобусе", "What the globe shows",
             "Землетрясения, станции, месторождения, ЛЭП, кабели и другие "
             "слои вида - GeoPackage по рамке вида с цветом и размером.",
             "Earthquakes, power plants, deposits, power lines, cables and "
             "other view layers - a GeoPackage within the view box with "
             "colour and size."),
            ("Кора CRUST1.0", "CRUST1.0 crust",
             "Кровли трёх слоёв осадков, трёх слоёв коры и Мохо - растры "
             "отметок по рамке вида.",
             "Tops of three sediment layers, three crust layers and the Moho "
             "as elevation rasters within the view box."),
            ("Метки и картинки", "Places and images",
             "Папка «Моих меток» - слоем GeoPackage, картинки на "
             "поверхности - GeoTIFF.",
             "A My Places folder as a GeoPackage layer, surface images as "
             "GeoTIFF.")))))
    return "\n".join([layers, relief, under, section_, back])


def trio(*figs):
    return '<div class="trio">%s</div>' % "".join(figs)


def shot(name, key, ru, en):
    """Снимок тройки или пары страницы «Данные» - 460 пикселей хватает
    колонке, страница с двумя десятками снимков легче для блока."""
    return figure(img_ref[0](name, SHOT_WIDTH), t(key, ru, en))


SHOT_WIDTH = 460


img_ref = [None]


def page_data(img):
    img_ref[0] = img
    intro = section(
        "catalogue", ("Каталог «Добавить данные»", "The Add data catalogue"),
        ("Около 90 карт и слоёв о Земле одной панелью",
         "About 90 maps and layers about the Earth in one panel"),
        ("Кнопка «Добавить данные» раздела «Слои» открывает каталог на "
         "месте списка. Слой включается флажком, щелчок по строке "
         "показывает источник, разрешение, период и условия. Данные "
         "запрашиваются у источников при показе, модуль их не "
         "распространяет.",
         "The Add data button of the Layers section opens the catalogue in "
         "place of the list. A layer is turned on with a check box, a click "
         "on a row shows the source, resolution, period and terms. The data "
         "are requested from the sources when shown, the plugin does not "
         "redistribute them."),
        '<div class="side">%s%s</div>' % (
            figure(img("catalog.png", NARROW), t(
                "catalogue.fig", "Каталог в левой панели окна глобуса.",
                "The catalogue in the left panel of the globe window.")),
            table(features("work", (
                ("Значение в точке", "Value at a point",
                 "Щелчок по глобусу даёт значение карты, класс породы или "
                 "почвы, сведения об очаге, станции, месторождении.",
                 "A click on the globe gives the map value, rock or soil "
                 "class, details of a quake, plant or deposit."),
                ("Шкала и непрозрачность", "Scale and opacity",
                 "У каждой карты шкала в углу вида, непрозрачность - "
                 "ползунком в меню строки.",
                 "Each map has a scale in the view corner, opacity is a "
                 "slider in the row menu."),
                ("Шкала времени", "Time slider",
                 "Темы NASA, погода, течения, землетрясения и пожары идут "
                 "по общей шкале. Шторка сравнивает два дня.",
                 "NASA themes, weather, currents, earthquakes and fires "
                 "follow one time slider. A swipe compares two days."),
                ("В проект QGIS", "Into the QGIS project",
                 "Карта значений - сеткой GeoTIFF, точки и линии вида - "
                 "GeoPackage со стилем, картографические службы - слоем "
                 "XYZ или WMS.",
                 "A value map as a GeoTIFF grid, view points and lines as "
                 "a GeoPackage with style, map services as an XYZ or WMS "
                 "layer."))))))
    depths = section(
        "depths", ("Недра и геофизика", "The Earth's interior"),
        ("Геология, поля и строение Земли",
         "Geology, fields and the structure of the Earth"),
        None,
        trio(shot("geology.jpg", "depths.geology", "Геологическая карта "
                  "Macrostrat, запад США.", "The Macrostrat geological map, "
                  "the western United States."),
             shot("gravity.jpg", "depths.gravity", "Аномалии силы тяжести "
                  "XGM2019e, Гималаи и Тибет.", "XGM2019e gravity "
                  "anomalies, the Himalaya and Tibet."),
             shot("emag.jpg", "depths.emag", "Магнитные аномалии EMAG2v3, "
                  "Курская аномалия.", "EMAG2v3 magnetic anomalies, the "
                  "Kursk anomaly.")) +
        trio(shot("seafloor_age.jpg", "depths.age", "Возраст "
                  "океанического дна, Атлантика.", "Ocean floor age, the "
                  "Atlantic."),
             shot("heatflow.jpg", "depths.heat", "Тепловой поток IHFC "
                  "2024, Северная Америка.", "IHFC 2024 heat flow, North "
                  "America."),
             shot("plates.jpg", "depths.plates", "Границы плит, скорости "
                  "движения и вулканы, запад Тихого океана.", "Plate "
                  "boundaries, plate motion and volcanoes, the western "
                  "Pacific.")) +
        table(features("geo", (
            ("Геологическая карта", "Geological map",
             "Породы и возраст по картам масштабов от 1:5 млн до крупных "
             "региональных, щелчок - порода, возраст, источник карты.",
             "Rocks and ages from maps of scales from 1:5 million to "
             "large regional ones, a click gives rock, age and map source.",
             "Macrostrat · CC BY 4.0"),
            ("Литология", "Lithology",
             "16 классов пород на клетке 1 км по базе 2015 года.",
             "16 rock classes on a 1 km cell from the 2015 database.",
             "GLiM, Hartmann & Moosdorf · CC BY 3.0"),
            ("Активные разломы", "Active faults",
             "13 696 разломов с видом смещения.",
             "13 696 faults with the slip type.",
             "GEM Global Active Faults · CC BY-SA 4.0"),
            ("Границы и скорости плит", "Plate boundaries and motion",
             "54 плиты, классы границ, стрелки скорости в мм/год.",
             "54 plates, boundary classes, velocity arrows in mm/year.",
             "PB2002, NNR-MORVEL56"),
            ("Вулканы", "Volcanoes",
             "Вулканы голоцена с годами извержений.",
             "Holocene volcanoes with eruption years.",
             "Smithsonian GVP"),
            ("Землетрясения", "Earthquakes",
             "M4.5+ за 30 суток и около 74 тысяч событий с 1904 года, "
             "очаги на своей глубине, время на шкале.",
             "M4.5+ over 30 days and about 74 thousand events since 1904, "
             "foci at their depths, time on the slider.",
             "USGS, ISC-GEM · CC BY-SA 3.0"),
            ("Магнитное поле", "Magnetic field",
             "Аномалии на высоте 4 км, полюса с 1590 года, склонение "
             "и поле в точке с 1590 года.",
             "Anomalies at 4 km altitude, poles since 1590, declination "
             "and field at a point since 1590.",
             "EMAG2v3, IGRF-14, gufm1"),
            ("Сила тяжести и геоид", "Gravity and geoid",
             "Аномалии в свободном воздухе и Буге с поправкой на рельеф, "
             "геоид с масштабом до 20 000.",
             "Free-air and Bouguer anomalies with terrain correction, the "
             "geoid with an exaggeration up to 20 000.",
             "XGM2019e, ETOPO 2022, EGM2008"),
            ("Возраст дна, тепловой поток", "Seafloor age, heat flow",
             "Возраст океанической коры в млн лет, тепловой поток "
             "в мВт/м².",
             "Ocean crust age in million years, heat flow in mW/m².",
             "Seton et al. 2020, IHFC 2024 · CC BY 4.0"),
            ("Строение Земли", "Earth structure",
             "Разрез с корой CRUST1.0 двух типов, мантией PREM "
             "с томографией SEISGLOB2, плитами Slab2.",
             "A cutaway with the two-type CRUST1.0 crust, the PREM mantle "
             "with SEISGLOB2 tomography, Slab2 slabs.",
             "CRUST1.0, PREM, SEISGLOB2, Slab2"),
            ("Палеогеография", "Paleogeography",
             "Суша и море на 109 возрастов до 540 млн лет назад.",
             "Land and sea for 109 ages back to 540 million years.",
             "PALEOMAP PaleoDEM · CC BY 4.0"),
            ("Месторождения и разработки", "Deposits and mining",
             "Около 300 тысяч точек, 44 929 контуров разработок по "
             "снимкам, шахты и карьеры OSM.",
             "About 300 thousand points, 44 929 mining outlines from "
             "imagery, OSM mines and quarries.",
             "USGS MRDS, Maus et al. 2022 · CC BY-SA 4.0, OSM")))) +
        trio(shot("iscgem.jpg", "depths.iscgem", "Землетрясения ISC-GEM "
                  "с 1904 года, запад Тихого океана.", "ISC-GEM "
                  "earthquakes since 1904, the western Pacific."),
             shot("deposits.jpg", "depths.deposits", "Месторождения USGS, "
                  "Невада.", "USGS deposits, Nevada."),
             shot("glim.jpg", "depths.glim", "Литология GLiM, Азия.",
                  "GLiM lithology, Asia.")) +
        '<div class="pair">%s%s</div>' % (
             shot("cutaway.jpg", "depths.cutaway", "Разрез Земли у "
                  "Японского жёлоба - оболочки, кора и очаги.", "Earth "
                  "cutaway at the Japan Trench - shells, crust and foci."),
             shot("section_japan.png", "depths.section", "Окно «Разрез» "
                  "по 38.5° с. ш. - кора CRUST1.0, плита Slab2 до 600 км.",
                  "The Section window along 38.5° N - CRUST1.0 crust, the "
                  "Slab2 slab down to 600 km.")))
    land = section(
        "land", ("Вода, суша, почвы", "Water, land, soils"),
        ("Что покрывает поверхность", "What covers the surface"),
        None,
        trio(shot("worldcover.jpg", "land.cover", "Покрытие земель ESA "
                  "WorldCover 2021, Пермь.", "ESA WorldCover 2021 land "
                  "cover, Perm."),
             shot("water.jpg", "land.water", "Изменения воды JRC "
                  "1984-2021, Аральское море.", "JRC water transitions "
                  "1984-2021, the Aral Sea."),
             shot("soil.jpg", "land.soil", "Кислотность почв SoilGrids, "
                  "Восточная Европа.", "SoilGrids soil pH, Eastern "
                  "Europe.")) +
        table(features("land", (
            ("Покрытие земель", "Land cover",
             "11 классов на клетке 10 м - лес, пашня, город, вода, лёд.",
             "11 classes on a 10 m cell - forest, cropland, built-up, "
             "water, ice.",
             "ESA WorldCover 2021 · CC BY 4.0"),
            ("Поверхностные воды", "Surface water",
             "Повторяемость воды и изменения за 1984-2021 годы, клетка "
             "30 м.",
             "Water occurrence and transitions over 1984-2021, a 30 m "
             "cell.",
             "JRC Global Surface Water · Copernicus"),
            ("Почвы", "Soils",
             "Глина, песок, органический углерод, кислотность слоя "
             "0-5 см, клетка 250 м.",
             "Clay, sand, organic carbon, pH of the 0-5 cm layer, a 250 m "
             "cell.",
             "SoilGrids 2.0, ISRIC · CC BY 4.0"),
            ("Течения", "Currents",
             "Струйки и скорость течений за сутки с 2017 года.",
             "Streaks and speed of currents per day since 2017.",
             "NOAA CoastWatch"),
            ("Глубины морей", "Sea depths",
             "Дно океанов с клеткой 450 м, профиль показывает воду.",
             "The ocean floor on a 450 m cell, the profile shows water.",
             "GEBCO 2026")))))
    nasa = section(
        "nasa", ("Погода и снимки NASA", "Weather and NASA imagery"),
        ("Карты на день шкалы времени", "Maps for the day of the time "
         "slider"),
        ("27 тем NASA GIBS - снег, лёд, осадки, газы, растительность, "
         "температура - и прогноз NOAA GFS на 16 суток. День выбирает "
         "правый бегунок шкалы, шторка сравнивает два дня.",
         "27 NASA GIBS themes - snow, ice, precipitation, gases, "
         "vegetation, temperature - and the NOAA GFS 16 day forecast. The "
         "right handle of the slider picks the day, a swipe compares two "
         "days."),
        trio(shot("wind.jpg", "nasa.wind", "Ветер GFS струйками над "
                  "Атлантикой.", "GFS wind as streaks over the Atlantic."),
             shot("temperature_gfs.jpg", "nasa.temp", "Температура воздуха "
                  "GFS со значениями.", "GFS air temperature with "
                  "values."),
             shot("sea_ice.jpg", "nasa.ice", "Морской лёд GHRSST MUR, "
                  "Арктика.", "GHRSST MUR sea ice, the Arctic.")) +
        trio(shot("ndvi.jpg", "nasa.ndvi", "Растительность MODIS NDVI "
                  "за 16 суток, Африка.", "MODIS 16 day NDVI vegetation, "
                  "Africa."),
             shot("methane.jpg", "nasa.methane", "Метан AIRS за месяц, "
                  "Азия.", "AIRS monthly methane, Asia."),
             figure(img("fires.jpg", build_site.HALF_WIDTH), t(
                 "nasa.fires", "Пожары FIRMS за 24 часа, Южная Америка.",
                 "FIRMS fires over 24 hours, South America."))))
    energy = section(
        "energy", ("Энергетика и спутники", "Energy and satellites"),
        ("Электростанции, линии, кадастр, спутники",
         "Power plants, lines, cadastre, satellites"),
        None,
        '<div class="pair">%s%s</div>' % (
            shot("plants.jpg", "energy.plants", "34 936 электростанций WRI, "
                 "цвет - топливо, размер - мощность.", "34 936 WRI power "
                 "plants, colour - fuel, size - capacity."),
            shot("satellites.jpg", "energy.sats", "Спутники навигации, "
                 "погоды, станции и геостационарные на момент шкалы.",
                 "Navigation and weather satellites, stations and "
                 "geostationary satellites at the slider moment.")) +
        table(features("energy", (
            ("Электростанции", "Power plants",
             "Топливо, мощность, год ввода.",
             "Fuel, capacity, commissioning year.", "WRI · CC BY 4.0"),
            ("ЛЭП, трубопроводы, кабели", "Power lines, pipelines, cables",
             "Линии по классам напряжения, подстанции, 1949 подводных "
             "кабелей.",
             "Lines by voltage class, substations, 1949 submarine cables.",
             "OpenStreetMap · ODbL"),
            ("Кадастр Росреестра", "Rosreestr cadastre",
             "Участки поверх снимка, щелчок - номер и сведения участка.",
             "Parcels over imagery, a click gives the parcel number and "
             "details.", "НСПД"),
            ("Спутники", "Satellites",
             "9 групп по элементам орбит, виток, след и камера следом.",
             "9 groups from orbital elements, orbit, ground track and "
             "follow camera.", "CelesTrak")))))
    return "\n".join([intro, depths, land, nasa, energy])


def page_imagery(img):
    sats = section(
        "imagery", ("Космоснимки", "Satellite imagery"),
        ("Снимки спутников участком в проект QGIS",
         "Satellite images of an area into the QGIS project"),
        ("Пункт «Космоснимки здесь…» меню на глобусе или меню метки "
         "открывает окно поиска сцен. Участок - квадрат по ширине вида "
         "или многоугольник «Моих меток». Облачность считается над самим "
         "участком по маске сцены, а не по всей сцене. Сочетания каналов "
         "и индексы ложатся слоями проекта со стилем.",
         "The Satellite images here… item of the globe menu or a placemark "
         "menu opens the scene search window. The area is a square by the "
         "view width or a My Places polygon. Cloud cover is counted over "
         "the area itself by the scene mask, not over the whole scene. "
         "Band composites and indices go to the project as styled "
         "layers."),
        figure(img("sentinel.png"), t(
            "imagery.fig", "Окно «Космоснимки» - сцены участка с "
            "облачностью над ним и превью выбранной.", "The Satellite "
            "images window - scenes of the area with the cloud cover over "
            "it and a preview of the selected one.")) +
        table(features("sat", (
            ("Sentinel-2", "Sentinel-2",
             "С 2015 года, 10-20 м, 12 каналов. Естественные и ложные "
             "цвета, NDVI, NDWI, NBR и другие индексы.",
             "Since 2015, 10-20 m, 12 bands. Natural and false colours, "
             "NDVI, NDWI, NBR and other indices.",
             "Copernicus · Earth Search"),
            ("Landsat 4-9", "Landsat 4-9",
             "С 1982 года, 30 м. Индексы и температура поверхности, дыры "
             "температуры закрываются формулой USGS.",
             "Since 1982, 30 m. Indices and surface temperature, gaps in "
             "temperature are filled by the USGS formula.",
             "USGS · Planetary Computer"),
            ("Landsat 1-5 MSS", "Landsat 1-5 MSS",
             "1972-1993 годы, 60 м, четыре канала, отражение на верху "
             "атмосферы, сбойные строки убираются.",
             "1972-1993, 60 m, four bands, top of atmosphere reflectance, "
             "bad lines are removed.",
             "USGS · Planetary Computer"),
            ("ASTER", "ASTER",
             "2000-2006 годы без входа, после 2006 года - по ключу NASA "
             "Earthdata. 14 каналов, минеральные отношения - глины, "
             "карбонаты, кварц.",
             "2000-2006 without login, after 2006 with a NASA Earthdata "
             "key. 14 bands, mineral ratios - clays, carbonates, quartz.",
             "NASA LP DAAC"),
            ("MODIS", "MODIS",
             "Температура поверхности днём и ночью, NDVI и EVI, снег, "
             "гари, 250-1000 м.",
             "Day and night surface temperature, NDVI and EVI, snow, burnt "
             "area, 250-1000 m.",
             "NASA · Planetary Computer"),
            ("Вся сцена", "Whole scene",
             "Исходные файлы всех каналов с маской облаков скачиваются "
             "как есть, слой-набор собирает их в один растр.",
             "Original files of all bands with the cloud mask are "
             "downloaded as they are, a layer set joins them into one "
             "raster.", "")))))
    t("key.h", "Ключ NASA Earthdata для снимков ASTER после 2006 года",
      "NASA Earthdata key for ASTER images after 2006")
    for key in ("key.p", "key.s1", "key.s2", "key.s3", "key.note"):
        t(key, build_site.RU[key], build_site.EN[key])
    key = ('<div class="card key"><h3 data-i18n="key.h"></h3>'
           '<p data-i18n="key.p"></p><ol><li data-i18n="key.s1"></li>'
           '<li data-i18n="key.s2"></li><li data-i18n="key.s3"></li></ol>'
           '<p data-i18n="key.note"></p></div>')
    series = section(
        "series", ("Ряд по датам", "Time series"),
        ("Как менялся участок", "How the area changed"),
        ("Кнопка «Ряд по датам…» строит график индекса или температуры "
         "участка по всем найденным сценам - медиану без облаков "
         "и разброс внутри участка. Щелчок по точке выбирает сцену, ряд "
         "записывается таблицей CSV.",
         "The Time series… button plots an index or the temperature of "
         "the area over all found scenes - the cloud free median and the "
         "spread within the area. A click on a point selects the scene, "
         "the series is saved as a CSV table."),
        figure(img("series.png"), t(
            "series.fig", "NDVI центра Перми по сценам Sentinel-2 за год.",
            "NDVI of central Perm from Sentinel-2 scenes over a year.")) +
        key)
    return "\n".join([sats, series])


def family():
    t("fam.a", "Открыть в каталоге QGIS", "Open in the QGIS catalogue")
    rows = []
    for n, (name, slug, ru, en) in enumerate((
            ("Isoliner", "grid_isolines",
             "Кригинг, изолинии, рельеф и водосборы, разрезы с чертежами, "
             "геологическая модель пласта.",
             "Kriging, isolines, relief and catchments, sections with "
             "drawings, a geological bed model."),
            ("Topoliner", "topoliner",
             "Чистка топологии контуров и полигонов, прореживание "
             "с сохранением топологии.",
             "Topology cleaning of contours and polygons, thinning that "
             "preserves topology."),
            ("Isoliner3D", "isoliner3d",
             "Тела пластов, скважины и разрезы в объёме, карта текстурой "
             "на рельефе, блочная модель.",
             "Bed bodies, boreholes and sections in three dimensions, a map "
             "draped on the relief, a block model.")), 1):
        p = t("fam.c%d.p" % n, ru, en)
        rows.append('<div class="card"><h3>%s</h3><p data-i18n="%s"></p>'
                    '<p><a target="_blank" href="https://plugins.qgis.org/'
                    'plugins/%s/" data-i18n="fam.a"></a></p></div>'
                    % (name, p, slug))
    return '<div class="trio">%s</div>' % "\n".join(rows)


def releases():
    """Выпуски от NEWS_FROM: [(номер, дата, [пункты по-русски],
    текст по-английски)]."""
    with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as fh:
        log = fh.read()
    with open(os.path.join(ROOT, "planetx", "metadata.txt"),
              encoding="utf-8") as fh:
        meta = fh.read()
    english = {}
    block = meta.split("changelog=", 1)[1]
    for m in re.finditer(r"(?:^|\n)\s*(\d+\.\d+\.\d+) (.*?)(?=\n\s*\d+\.\d+"
                         r"\.\d+ |\n\S|\Z)", block, re.S):
        english[m.group(1)] = " ".join(m.group(2).split())
    out = []
    for m in re.finditer(r"^## (\d+\.\d+\.\d+) - (.+?)\n(.*?)(?=^## |\Z)",
                         log, re.S | re.M):
        number = m.group(1)
        if tuple(int(v) for v in number.split(".")) < NEWS_FROM:
            continue
        items = [" ".join(i.split()) for i in
                 re.split(r"^- ", m.group(3), flags=re.M) if i.strip()]
        out.append((number, m.group(2), items, english.get(number, "")))
    return out


MONTHS = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля",
          "августа", "сентября", "октября", "ноября", "декабря")
MONTHS_EN = ("January", "February", "March", "April", "May", "June", "July",
             "August", "September", "October", "November", "December")


def date_en(text):
    """«17 октября 2026 года» - «17 October 2026»."""
    m = re.match(r"(\d+) (\S+) (\d+)", text)
    if not m or m.group(2) not in MONTHS:
        return text
    return "%s %s %s" % (m.group(1), MONTHS_EN[MONTHS.index(m.group(2))],
                         m.group(3))


def page_news(img):
    blocks = []
    for number, date, items, en in releases():
        k = number.replace(".", "_")
        ru = "<ul>%s</ul>" % "".join("<li>%s</li>" % html.escape(i)
                                     for i in items)
        body = t("news.%s" % k, ru, "<p>%s</p>" % html.escape(en))
        when = t("news.%s.date" % k, html.escape(date),
                 html.escape(date_en(date)))
        blocks.append('<div class="card release"><h3>PlanetX %s</h3>'
                      '<p class="date" data-i18n="%s"></p>'
                      '<div data-i18n="%s"></div></div>'
                      % (number, when, body))
    t("news.all", "Все выпуски - в журнале изменений на GitHub.",
      "All releases are in the changelog on GitHub.")
    blocks.append('<p class="sub"><a target="_blank" href="%s" '
                  'data-i18n="news.all"></a></p>' % CHANGELOG_URL)
    return section("news", ("Что нового", "What's new"),
                   ("Изменения по выпускам", "Changes by release"), None,
                   "\n".join(blocks) + buttons(main=False))


BUILDERS = {"main": page_main, "places": page_places,
            "project": page_project, "data": page_data,
            "imagery": page_imagery, "news": page_news}

STYLE_EXTRA = """
.nav a.on{color:var(--teal-deep);font-weight:600}
.card.link{display:block;text-decoration:none;color:inherit}
.card.link:hover{border-color:var(--teal)}
.card.link h3{color:var(--teal-deep)}
.row{display:grid;grid-template-columns:minmax(220px,1fr) 1.4fr;gap:14px;
  padding:10px 20px;border-bottom:1px solid var(--line);font-size:15px}
.row span{color:var(--ink-soft)}
.row .src{display:block;font-style:normal;font-size:13px;margin-top:3px;
  color:var(--teal-deep)}
@media(max-width:860px){.row{grid-template-columns:1fr}}
figure.narrow{max-width:620px}
.side{display:grid;grid-template-columns:1fr 1fr;gap:28px;align-items:start;
  margin-top:34px}
.side figure{margin:0}
.side .row{grid-template-columns:1fr;gap:4px}
@media(max-width:860px){.side{grid-template-columns:1fr}}
.release{margin-top:20px}
.release .date{color:var(--ink-soft);font-size:14px;margin:2px 0 8px}
.release ul{margin:0;padding-left:20px;color:var(--ink-soft);font-size:16px}
.release li + li{margin-top:6px}
.release div p{color:var(--ink-soft);font-size:16px}
"""


def page(key, img, version):
    T.clear()
    body = BUILDERS[key](img)
    title_ru = dict((k, ru) for k, _, ru, _ in PAGES)[key]
    title_en = dict((k, en) for k, _, _, en in PAGES)[key]
    t("title", "PlanetX - %s · Информ++" % title_ru,
      "PlanetX - %s · Inform++" % title_en)
    t("brand.sub", "для QGIS", "for QGIS")
    nav = []
    for k, path, ru, en in PAGES:
        nk = t("nav.%s" % k, ru, en)
        nav.append('<a target="_blank" href="%s" data-i18n="%s"%s></a>'
                   % (url(path), nk, ' class="on"' if k == key else ""))
    t("ftr.line1", build_site.RU["ftr.line1"], build_site.EN["ftr.line1"])
    t("ftr.line2", build_site.RU["ftr.line2"], build_site.EN["ftr.line2"])
    t("ftr.line3", build_site.RU["ftr.line3"], build_site.EN["ftr.line3"])
    texts = {"ru": {k: v[0] for k, v in T.items()},
             "en": {k: v[1] for k, v in T.items()}}
    style = re.search(r"<style>(.*?)</style>", build_site.PAGE,
                      re.S).group(1)
    script = re.search(r"function apply\(lang\)(.*?)</script>",
                       build_site.PAGE, re.S).group(0)
    script = script[:-len("</script>")]
    return """<!-- PlanetX - страница «%s» для www.informpp.ru.        -->
<!-- Собирается tools/build_pages.py, править лучше его.        -->
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title data-i18n="title"></title>
<style>%s%s</style>
<header class="hdr"><div class="wrap">
<a class="brand" target="_blank" href="%s">PlanetX
<span data-i18n="brand.sub"></span></a>
<div class="right"><nav class="nav">%s</nav>
<div class="lang"><button type="button" data-lang="ru">RU</button>
<button type="button" data-lang="en">EN</button></div></div>
</div></header>
%s
<footer class="ftr"><div class="wrap">
PlanetX %s &middot; <span data-i18n="ftr.line1"></span><br>
<span data-i18n="ftr.line2"></span>,
<a target="_blank" href="https://www.informpp.ru/">www.informpp.ru</a><br>
<span data-i18n="ftr.line3"></span>
</div></footer>
<script>
var TEXTS = %s;
%s</script>
""" % (title_ru, style, STYLE_EXTRA, url(""), "\n".join(nav), body,
       version, json.dumps(texts, ensure_ascii=False), script)


# Снимки руководства, от которых на странице нужна часть: файл в
# doc/figures/ru - (лево, верх, право, низ) в пикселях снимка. Снимок
# каталога - вся левая панель высотой 1860 пикселей с пустым разделом
# «Проект QGIS», на странице во всю ширину он выходил огромной пустой
# панелью - замечание автора от 17 октября 2026 года. На странице -
# только каталог.
CROPS = {"catalog.png": (0, 1340, 920, 1815),
         # профиль озера снят до конца загрузки высот, строка чисел внизу
         # говорит «уточнятся» - на странице только график
         "profile_lake.png": (0, 0, 2200, 950),
         # слева у магнитных аномалий не догрузились тайлы карты
         "emag.jpg": (490, 0, 1400, 1005),
         # строка с папкой файлов на диске автора не идёт на страницу
         "sentinel.png": (0, 0, 2200, 1225)}
# Папки снимков по порядку поиска - снимки сайта (tools/qgis_site_shots.py),
# руководства и прежней страницы.
FOLDERS = (os.path.join(ROOT, "site", "shots"),
           os.path.join(ROOT, "doc", "figures", "ru"),
           build_site.IMAGES)
# Ширина узкого снимка на странице, пикселей.
NARROW = 620


def cropped(name, box, width):
    """Снимок из первой папки FOLDERS, где он есть, в строке data -
    JPEG не шире width, box - часть снимка или None."""
    path = next(os.path.join(f, name) for f in FOLDERS
                if os.path.exists(os.path.join(f, name)))
    with Image.open(path) as picture:
        picture = picture.convert("RGB")
        if box:
            picture = picture.crop(box)
        if picture.width > width:
            height = round(picture.height * width / picture.width)
            picture = picture.resize((width, height), Image.LANCZOS)
        out = io.BytesIO()
        picture.save(out, "JPEG", quality=build_site.WEB_QUALITY,
                     optimize=True, progressive=True)
    return "data:image/jpeg;base64," + base64.b64encode(
        out.getvalue()).decode("ascii")


def main():
    os.makedirs(OUT, exist_ok=True)
    cache = {}

    def img(name, width=build_site.WEB_WIDTH):
        if (name, width) not in cache:
            cache[name, width] = cropped(name, CROPS.get(name), width)
        return cache[name, width]

    version = build_site.version()
    for key, path, ru, _ in PAGES:
        text = page(key, img, version)
        target = os.path.join(OUT, "planetx_%s.html" % key)
        with open(target, "wb") as fh:
            fh.write(text.encode("utf-8"))
        print("%-8s %6.0f КБ  %s" % (key, len(text.encode("utf-8")) / 1024,
                                     url(path)))


if __name__ == "__main__":
    main()
