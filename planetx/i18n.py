# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Перевод интерфейса.

Устройство взято из Topoliner. Исходный язык русский, английский
перевод лежит в словаре EN. Язык берётся из настройки локали QGIS,
а не системы. Файлы .qm не нужны, для них понадобился бы lrelease.
"""
import os

__all__ = ["tr", "is_russian", "set_language", "EN"]

EN = {
    "Загрузка подложки: {done} из {total}":
        "Loading base map: {done} of {total}",
    "Подложка не загрузилась: {error}":
        "Base map failed to load: {error}",
    "Обзор с высоты {height}": "View from {height}",
    "Для глобуса нужен модуль Python {name}. В этой сборке QGIS его нет.":
        "The globe needs the Python module {name}. This QGIS build "
        "does not have it.",
    "Поиск": "Search",
    "Название места или координаты в градусах, например Пермь или "
    "58.0105, 56.2294. Enter запускает поиск или перелёт. Несколько "
    "найденных мест показываются списком ниже, перелёт начинается "
    "щелчком по строке. Перелёт прерывается мышью.":
        "A place name or coordinates in degrees, for example Perm or "
        "58.0105, 56.2294. Enter starts the search or the flight. Several "
        "places found are listed below, a click on a row starts the "
        "flight. The mouse interrupts the flight.",
    "Поиск: {text}": "Searching: {text}",
    "Поиск не удался: {error}": "Search failed: {error}",
    "Ничего не найдено: {text}": "Nothing found: {text}",
    "О модуле": "About",
    "Метки": "Places",
    "Слои проекта": "Project layers",
    "Свернуть или развернуть «Мои метки».": "Collapse or expand My Places.",
    "Свернуть или развернуть слои проекта QGIS.":
        "Collapse or expand the QGIS project layers.",
    "Свернуть или развернуть векторную основу и рельеф.":
        "Collapse or expand the vector base and terrain.",
    "Свойства вида: подложка, масштаб рельефа, язык подписей, "
    "связь с картой, обновление, формат координат.":
        "View properties: base map, terrain exaggeration, label language, "
        "link with the map, update, coordinate format.",
    "Шкала времени меток. Пока шкала открыта, метки вне её "
    "промежутка скрыты. Закрытая шкала показывает все метки.":
        "Placemark time slider. While the slider is open, placemarks "
        "outside its interval are hidden. A closed slider shows all "
        "placemarks.",
    "Подложка": "Base map",
    "{name} · {kind}": "{name} · {kind}",
    "Отметка показывает слой на глобусе, видимость на карте QGIS "
    "не меняется. Двойной щелчок переносит к слою, меню по правой "
    "кнопке - перелёт, прозрачность и свойства.":
        "The check shows the layer on the globe, its visibility on the "
        "QGIS map does not change. Double-clicking flies to the layer, the "
        "right-click menu flies there, sets opacity and opens properties.",
    "Подлететь": "Fly to",
    "растр": "raster",
    "точки": "points",
    "линии": "lines",
    "полигоны": "polygons",
    "таблица": "table",
    "слой": "layer",
    "Обновить глобус: настройки или слои изменились":
        "Refresh the globe: settings or layers have changed",
    "Обновить глобус": "Refresh the globe",
    "Свойства вида": "View properties",
    "Настройки или слои изменились. Глобус покажет их после кнопки "
    "«Обновить».":
        "Settings or layers have changed. The globe shows them after "
        "the Refresh button.",
    "Обновление": "Update",
    "Обновлять автоматически": "Update automatically",
    "Населённые пункты": "Places",
    "Границы": "Borders",
    "Дороги": "Roads",
    "Железные дороги": "Railways",
    "Светлая линия с тёмным пунктиром. При отдалении пропадают вместе "
    "с магистралями. Станционные и подъездные пути не рисуются.":
        "A light line with a dark dash. When zooming out they disappear "
        "together with motorways. Station and siding tracks are not "
        "drawn.",
    "Рельеф": "Terrain",
    "Вертикальный масштаб": "Vertical exaggeration",
    "Множитель высот рельефа. Больше 1 - горы и долины выразительнее, "
    "равнинный рельеф становится заметен. Камера остаётся над поднятой "
    "поверхностью. После смены глобус пересобирает поверхность "
    "за несколько секунд.":
        "Multiplier of terrain heights. Above 1 mountains and valleys "
        "stand out more, and flat terrain becomes visible. The camera "
        "stays above the raised surface. After a change the globe "
        "rebuilds the surface within a few seconds.",
    "Векторная основа не загрузилась: {error}":
        "Vector base failed to load: {error}",
    "Поле «Поиск» слева вверху находит место по названию или "
    "координатам и запускает перелёт.":
        "The Search field at the top left finds a place by name or "
        "coordinates and starts a flight.",
    "Двойной щелчок левой кнопкой приближает к точке, правой - "
    "отдаляет. Правая кнопка с перетаскиванием приближает "
    "и отдаляет, левая с Ctrl поворачивает взгляд.":
        "A left double click zooms in to the point, a right double click "
        "zooms out. Dragging with the right button zooms in and out, the "
        "left button with Ctrl looks around.",
    "Стрелки сдвигают вид, PageUp и PageDown приближают "
    "и отдаляют, N ставит север вверху, U даёт взгляд отвесно.":
        "Arrows move the view, PageUp and PageDown zoom in and out, N puts "
        "north up, U looks straight down.",
    "Значок «Свойства вида» на панели значков открывает "
    "свойства вида. В них выбираются подложка и масштаб рельефа.":
        "The View properties icon on the icon bar opens the view "
        "properties. There you choose the base map and the terrain "
        "exaggeration.",
    "Поиск мест: Nominatim, © участники OpenStreetMap.":
        "Place search: Nominatim, © OpenStreetMap contributors.",
    "Облака: NASA GIBS, снимки VIIRS.": "Clouds: NASA GIBS, VIIRS imagery.",
    "Звёзды: каталог ярких звёзд Йельского университета.":
        "Stars: the Yale Bright Star Catalogue.",
    "Координатная сетка, звёзды, облака, температура суши и моря, "
    "3D-здания.":
        "A coordinate grid, stars, clouds, land and sea temperature, "
        "3D buildings.",
    "Температура: NASA GIBS, MODIS и GHRSST MUR.":
        "Temperature: NASA GIBS, MODIS and GHRSST MUR.",
    "Векторная основа: OpenFreeMap, © OpenMapTiles, © участники "
    "OpenStreetMap.":
        "Vector base: OpenFreeMap, © OpenMapTiles, © OpenStreetMap "
        "contributors.",
    "О модуле PlanetX": "About PlanetX",
    "С нажатой левой кнопкой Земля поворачивается вслед "
    "за курсором, после отпускания вращается по инерции.":
        "The left button drags the Earth, after release it keeps "
        "rotating by inertia.",
    "Колесо приближает к точке под курсором.":
        "The wheel zooms to the point under the cursor.",
    "Средняя кнопка или левая с Shift поворачивают и наклоняют вид.":
        "The middle button or the left one with Shift turns and tilts "
        "the view.",
    "Подложка OpenStreetMap: © участники OpenStreetMap.":
        "OpenStreetMap base map: © OpenStreetMap contributors.",
    "Рельеф: Mapzen Terrain Tiles, данные SRTM, GMTED, ETOPO1 и других "
    "источников.":
        "Terrain: Mapzen Terrain Tiles, data from SRTM, GMTED, ETOPO1 "
        "and other sources.",
    "Космоснимки Esri World Imagery - пример подложки, условия "
    "использования задаёт Esri.":
        "Esri World Imagery satellite imagery is an example base map, "
        "Esri sets its terms of use.",
    "Свои подложки берутся из подключений XYZ Tiles в QGIS, их условия "
    "задаёт владелец.":
        "Your own base maps come from the XYZ Tiles connections in QGIS, "
        "their owners set the terms of use.",
    "Источники данных и условия их использования":
        "Data sources and their terms of use",
    "Исходный код": "Source code",
    "Страница модуля": "Plugin page",
    "Возможности": "Features",
    "Координатная сетка": "Grid",
    "Параллели и меридианы с подписями градусов, экватор, "
    "тропики и полярные круги. Шаг сетки меняется с высотой "
    "камеры.":
        "Parallels and meridians with degree labels, the equator, the "
        "tropics and the polar circles. The grid step changes with "
        "the camera height.",
    "Звёзды": "Stars",
    "Звёзды каталога ярких звёзд Йельского университета "
    "и Млечный путь по карте неба NASA. Картинка неба "
    "скачивается при первом показе. Звёзды видны "
    "из космоса и гаснут, когда камера опускается "
    "в атмосферу.":
        "Stars of the Yale Bright Star Catalogue and the Milky Way from the "
        "NASA sky map. The sky image is downloaded when first shown. The "
        "stars show from space and fade when the camera descends into the "
        "atmosphere.",
    "Млечный путь: NASA/Goddard Space Flight Center Scientific "
    "Visualization Studio, Gaia DR2: ESA/Gaia/DPAC.":
        "Milky Way: NASA/Goddard Space Flight Center Scientific "
        "Visualization Studio, Gaia DR2: ESA/Gaia/DPAC.",
    "Облака": "Clouds",
    "Облака по снимкам VIIRS из NASA GIBS за последние "
    "полные сутки. Они лежат полупрозрачной пеленой "
    "поверх снимка. Снег и лёд тоже белые и остаются "
    "видны.":
        "Clouds from NASA GIBS VIIRS imagery of the last complete day. "
        "They lie as a translucent veil over the imagery. Snow and ice "
        "are white too and stay visible.",
    "3D-здания": "3D buildings",
    "Объёмные здания из OpenStreetMap по векторным "
    "тайлам OpenFreeMap. Они видны, когда камера ближе "
    "6 км к земле. Высота взята из OSM, иначе из "
    "этажности. Здание без этих сведений получает "
    "высоту 5 м.":
        "3D buildings from OpenStreetMap in OpenFreeMap vector tiles. "
        "They show when the camera is closer than 6 km to the ground. "
        "The height comes from OSM or from the number of floors. A "
        "building without either gets a height of 5 m.",
    "Температура": "Temperature",
    "Температура поверхности по данным NASA GIBS: суша "
    "днём за 8 дней по MODIS, море за сутки по GHRSST "
    "MUR. Под облаками на суше бывают пропуски. Шкала "
    "в градусах стоит в левом нижнем углу вида.":
        "Surface temperature from NASA GIBS: land by day over 8 days from "
        "MODIS, sea over a day from GHRSST MUR. Land may have gaps under "
        "clouds. The scale in degrees is in the bottom left corner of the "
        "view.",
    "Суша, °C": "Land, °C",
    "Море, °C": "Sea, °C",
    "{angle} с. ш.": "{angle}N",
    "{angle} ю. ш.": "{angle}S",
    "{angle} в. д.": "{angle}E",
    "{angle} з. д.": "{angle}W",
    "Экватор": "Equator",
    "Тропик Рака": "Tropic of Cancer",
    "Тропик Козерога": "Tropic of Capricorn",
    "Северный полярный круг": "Arctic Circle",
    "Южный полярный круг": "Antarctic Circle",
    "Копировать": "Copy",
    "Вставить": "Paste",
    "KML в буфере обмена, меток {count}.":
        "KML in the clipboard, places {count}.",
    "Вставка": "Pasted",
    "В буфере обмена нет меток KML.": "The clipboard holds no KML places.",
    "Вставлено меток {count}.": "Places pasted {count}.",
    "Высота ползунком. Шкала логарифмическая, "
    "у земли шаг - метры, выше - сотни метров и километры.":
        "Height by slider. The scale is logarithmic, "
        "near the ground the step is metres, higher up hundreds of metres "
        "and kilometres.",
    "Поверхность земли": "Ground",
    "Космос": "Space",
    "Требования": "Requirements",
    "Космоснимки, рельеф с отмывкой склонов и атмосфера, подложки "
    "из подключений XYZ Tiles QGIS.":
        "Satellite imagery, terrain with hill shading and atmosphere, base "
        "maps from QGIS XYZ Tiles connections.",
    "Раздел «Слои» с границами, названиями, дорогами, реками "
    "и вершинами, подписи на 15 языках.":
        "The Layers section with borders, names, roads, rivers and peaks, "
        "labels in 15 languages.",
    "Слои текущего проекта на глобусе в порядке карты QGIS, "
    "синхронизация с окном карты и определение объектов.":
        "Layers of the current project on the globe in the QGIS map order, "
        "synchronization with the map window and feature identification.",
    "«Мои метки» с папками, метками, путями, многоугольниками "
    "и сохранёнными видами, чтение и запись KML и KMZ.":
        "My Places with folders, placemarks, paths, polygons and saved "
        "views, reading and writing KML and KMZ.",
    "Линейка на эллипсоиде WGS84 и по рельефу, профиль высот, "
    "координаты в градусах, UTM и MGRS.":
        "A ruler on the WGS84 ellipsoid and along the terrain, the "
        "elevation profile, coordinates in degrees, UTM and MGRS.",
    "Значки меток, время меток со шкалой времени, подъём "
    "и выдавливание меток.":
        "Placemark icons, placemark time with a time slider, lifting "
        "and extruding places.",
    "Туры по меткам и вдоль путей, запись тура с экрана "
    "и кадрами PNG для видео, демо «Пермь».":
        "Tours over places and along paths, recording a tour from the "
        "screen and as PNG frames for a video, the Perm demo.",
    "Растущие треки по «Временному контроллеру» QGIS.":
        "Growing tracks along the QGIS Temporal Controller.",
    "Сцены в файл, снимок вида в файл и в макет QGIS.":
        "Scenes to a file, view snapshot to a file and into a QGIS layout.",
    "В правом верхнем углу вида кольцо компаса, джойстики взгляда "
    "и сдвига и ползунок высоты. Они появляются, когда курсор "
    "подходит к углу.":
        "The top right corner of the view holds the compass ring, the look "
        "and move sticks and the height slider. They appear when the "
        "cursor comes near the corner.",
    "QGIS 3.36 и новее, в том числе QGIS 4.":
        "QGIS 3.36 and newer, including QGIS 4.",
    "Видеокарта с OpenGL 3.3.": "A graphics card with OpenGL 3.3.",
    "Модуль Python PyOpenGL. В сборках QGIS для Windows он есть.":
        "The Python module PyOpenGL. QGIS builds for Windows include it.",
    "Кольцо поворачивает вид, буква N ставит север вверху. "
    "Джойстик в кольце поворачивает взгляд, нижний сдвигает вид. "
    "Ползунок задаёт высоту, плюс и минус приближают и отдаляют.":
        "The ring turns the view, the letter N puts north up. The stick "
        "inside the ring looks around, the lower one moves the view. The "
        "slider sets the height, plus and minus zoom in and out.",
    "с. ш.": "N",
    "ю. ш.": "S",
    "в. д.": "E",
    "з. д.": "W",
    "Координаты": "Coordinates",
    "Формат": "Format",
    "Десятичные градусы": "Decimal degrees",
    "Градусы, минуты, секунды": "Degrees, minutes, seconds",
    "Как записаны координаты в строке состояния и в окне "
    "«Объекты». Поле «Поиск» понимает все четыре формата "
    "независимо от выбора. Выше 84° северной и ниже 80° "
    "южной широты UTM и MGRS заменяются десятичными "
    "градусами.":
        "How coordinates are written in the status line and the Features "
        "window. The Search field understands all four formats whatever "
        "the choice. North of 84° and south of 80° UTM and MGRS are "
        "replaced with decimal degrees.",
    "Руководство": "Manual",
    "Сообщить об ошибке": "Report a bug",
    "Страница в каталоге QGIS": "QGIS plugin page",
    "Трёхмерный глобус внутри QGIS. Рельеф, "
    "атмосфера, подложки из подключений QGIS.":
        "A 3D globe inside QGIS. Terrain, "
        "atmosphere, base maps from QGIS connections.",
    "Управление": "Controls",
    "Источники данных": "Data sources",
    "Разработка при поддержке": "Developed with the support of",
    "ООО «Информ++»": "Inform++ LLC",
    "Лицензия GNU GPL версии 3.": "License GNU GPL version 3.",
    "Источник картинки на глобусе. Esri World Imagery - пример "
    "подложки, условия её использования задаёт Esri. В списке также "
    "OpenStreetMap и подключения XYZ Tiles из обозревателя QGIS, кроме "
    "подключений рельефа. Новое подключение появляется здесь при "
    "следующем открытии окна.":
        "Source of the globe imagery. Esri World Imagery is an example "
        "base map, Esri sets its terms of use. The list also holds "
        "OpenStreetMap and the XYZ Tiles connections from the QGIS "
        "browser, except terrain connections. A new connection appears "
        "here the next time the window opens.",
    "{name} - пример": "{name} - example",
    "{value} м": "{value} m",
    "{value} км": "{value} km",
    "Контекст OpenGL 3.3 недоступен: {version}":
        "OpenGL 3.3 context is unavailable: {version}",
    "{name}, {ele} м":
        "{name}, {ele} m",
    "Слои":
        "Layers",
    "Границы и названия":
        "Borders and names",
    "Границы стран и областей и подписи на глобусе.":
        "Country and region borders and labels on the globe.",
    "Границы стран ярко-жёлтые, границы областей тонкие белые. Морские "
    "границы не рисуются.":
        "Country borders are bright yellow, region borders thin and white. "
        "Maritime borders are not drawn.",
    "Названия стран, областей, городов, посёлков и деревень. При "
    "приближении появляются всё более мелкие пункты.":
        "Names of countries, regions, cities, towns and villages. Smaller "
        "places appear as you zoom in.",
    "Названия водоёмов":
        "Water names",
    "Названия морей, озёр и водохранилищ, голубым курсивом.":
        "Names of seas, lakes and reservoirs, in light blue italics.",
    "Транспорт": "Transport",
    "Дороги, их номера, железные дороги и аэропорты.":
        "Roads, their numbers, railways and airports.",
    "Магистрали жёлтые, главные дороги светло-жёлтые, остальные тонкие "
    "белые. Над городом дороги закрывают подложку густой сеткой.":
        "Motorways are yellow, main roads light yellow, other roads thin "
        "and white. Over a city the roads cover the base map with a dense "
        "grid.",
    "Номера дорог":
        "Road numbers",
    "Таблички с номерами магистралей и главных дорог. Европейские маршруты "
    "на зелёной табличке. Подписываются с высоты ниже 1000 км.":
        "Number plates of motorways and main roads. European routes are on "
        "a green plate. Labelled from altitudes below 1000 km.",
    "Аэропорты":
        "Airports",
    "Названия аэропортов с квадратным значком, при приближении взлётные "
    "полосы. Подписываются с высоты ниже 1000 км.":
        "Airport names with a square mark, runways when zoomed in. "
        "Labelled from altitudes below 1000 km.",
    "Природа":
        "Nature",
    "Реки, вершины и охраняемые территории.":
        "Rivers, peaks and protected areas.",
    "Вершины":
        "Peaks",
    "Вершины и вулканы с высотой в метрах, треугольный значок. "
    "Подписываются с высоты ниже 400 км.":
        "Peaks and volcanoes with height in metres, a triangle mark. "
        "Labelled from altitudes below 400 km.",
    "Заповедники и нацпарки":
        "Reserves and national parks",
    "Заповедники, национальные парки и заказники, зелёный контур и "
    "название. Названия видны ниже 3000 км, контур вместе "
    "с магистралями.":
        "Nature reserves, national parks and refuges, a green outline and a "
        "name. Names are shown below 3000 km, the outline together with "
        "motorways.",
    "Высоты Mapzen Terrain Tiles поднимают поверхность и дают отмывку "
    "склонов. Без рельефа Земля гладкая, высоты не загружаются. "
    "Вертикальный масштаб - в свойствах вида.":
        "Mapzen Terrain Tiles heights raise the surface and shade the "
        "slopes. Without terrain the Earth is smooth and no heights are "
        "loaded. Vertical exaggeration is in the view properties.",
    "Без флажка глобус показывает новую подложку, масштаб рельефа и слои "
    "проекта после кнопки «Обновить». С флажком он обновляется сам после "
    "каждой смены настроек и каждой правки данных, стиля и порядка слоёв. "
    "На тяжёлых слоях это частая перерисовка.":
        "Without this option the globe shows a new base map, terrain "
        "exaggeration and project layers after the Refresh button. With it "
        "the globe updates itself after every change of settings and every "
        "edit of layer data, style and order. With heavy layers this means "
        "frequent redrawing.",
    "Реки":
        "Rivers",
    "Узкие реки синими линиями. Появляются примерно с 600 м на пиксель.":
        "Narrow rivers as blue lines. They appear from about 600 m per "
        "pixel.",
    "Водоёмы":
        "Lakes and reservoirs",
    "Берега озёр, водохранилищ и широких рек обведены синей линией. "
    "Водохранилища в данных разрезаны на куски, и контур проходит и по "
    "разрезам.":
        "Shores of lakes, reservoirs and wide rivers are outlined in blue. "
        "Reservoirs are split into pieces in the data, and the outline also "
        "follows the cuts.",
    "Сохранить вид. Точка взгляда становится меткой в «Моих метках», "
    "перелёт к ней возвращает высоту, азимут и наклон.":
        "Save view. The look-at point becomes a placemark in My Places, "
        "flying to it restores the height, heading and tilt.",
    "Новая метка": "New placemark",
    "Новая метка, путь или многоугольник в «Мои метки».":
        "A new placemark, path or polygon in My Places.",
    "Метка": "Placemark",
    "Цвет": "Color",
    "Толщина": "Width",
    "Название в «Моих метках» и подпись точки на глобусе.":
        "The name in My Places and the label of a point on the globe.",
    "Цвет линии и контура. Заливка многоугольника того же цвета, "
    "полупрозрачная.":
        "The color of the line and outline. The polygon fill has the same "
        "color, semi-transparent.",
    "Толщина линии и контура в пикселях экрана. От масштаба не зависит.":
        "The width of the line and outline in screen pixels. It does not "
        "depend on the scale.",
    "Записать объект в «Мои метки».": "Write the object to My Places.",
    "Убрать поставленные точки.": "Remove the points placed.",
    "Щелчок по глобусу ставит метку. Новый щелчок переносит её.":
        "A click on the globe places the placemark. A new click moves it.",
    "Линейка": "Ruler",
    "Длина на карте": "Map length",
    "Длина по рельефу": "Ground length",
    "Курс": "Heading",
    "Азимут начала линии от севера по часовой стрелке "
    "на эллипсоиде WGS84.":
        "Azimuth of the start of the line clockwise from north on the "
        "WGS84 ellipsoid.",
    "Длина вдоль поверхности рельефа с подъёмами и спусками. "
    "Высоты берутся из Mapzen Terrain Tiles, недостающие "
    "загружаются. Пока они загружаются, перед числом стоит «≈».":
        "Length along the terrain surface with its rises and falls. "
        "Heights come from Mapzen Terrain Tiles, missing ones are loaded. "
        "While they load, the number is preceded by «≈».",
    "Профиль высот": "Elevation profile",
    "График высоты вдоль линии или пути с наибольшей и наименьшей "
    "высотой, набором и потерей высоты и уклонами.":
        "A chart of height along the line or path with the highest and "
        "lowest height, ascent, descent and slopes.",
    "Точку можно перетащить мышью, Backspace убирает последнюю.":
        "A point can be dragged with the mouse, Backspace removes the "
        "last one.",
    "Профиль высот: {name}": "Elevation profile: {name}",
    "Нет данных": "No data",
    "{distance}, высота {height}, уклон {slope}":
        "{distance}, height {height}, slope {slope}",
    "Отметьте на глобусе хотя бы две точки.":
        "Mark at least two points on the globe.",
    "Длина по карте {flat}, по рельефу {ground}. Наименьшая "
    "высота {low}, наибольшая {high}. Набор высоты {gain}, "
    "потеря {loss}. Средний уклон {mean}, наибольший {max}.":
        "Map length {flat}, ground length {ground}. Lowest height {low}, "
        "highest {high}. Ascent {gain}, descent {loss}. Mean slope "
        "{mean}, maximum {max}.",
    "Высоты ещё загружаются, числа уточнятся.":
        "Heights are still loading, the numbers will be refined.",
    "Линейка. Длина, периметр и площадь на эллипсоиде, сохранение "
    "измерения в «Мои метки».":
        "Ruler. Length, perimeter and area on the ellipsoid, the "
        "measurement is saved to My Places.",
    "Линия": "Line",
    "Путь": "Path",
    "Многоугольник": "Polygon",
    "Круг": "Circle",
    "Длина": "Length",
    "Периметр": "Perimeter",
    "Площадь": "Area",
    "Радиус": "Radius",
    "Метры": "Meters",
    "Километры": "Kilometers",
    "Мили": "Miles",
    "Морские мили": "Nautical miles",
    "Кв. метры": "Square meters",
    "Гектары": "Hectares",
    "Кв. километры": "Square kilometers",
    "Кв. мили": "Square miles",
    "м": "m",
    "км": "km",
    "мили": "mi",
    "мор. мили": "nmi",
    "м²": "m²",
    "га": "ha",
    "км²": "km²",
    "кв. мили": "sq mi",
    "Сохранить": "Save",
    "Очистить": "Clear",
    "Сохранить фигуру в «Мои метки» вместе с измерением.":
        "Save the shape to My Places together with the measurement.",
    "Убрать точки линейки с глобуса.":
        "Remove the ruler points from the globe.",
    "Щелчками по глобусу отметьте начало и конец линии. Третий щелчок "
    "начинает новую линию.":
        "Click the globe at the start and the end of the line. A third "
        "click starts a new line.",
    "Щелчками по глобусу отметьте точки пути.":
        "Click the globe at the points of the path.",
    "Щелчками по глобусу отметьте вершины многоугольника.":
        "Click the globe at the vertices of the polygon.",
    "Первый щелчок по глобусу - центр круга, второй задаёт радиус.":
        "The first click on the globe sets the centre of the circle, the "
        "second sets the radius.",
    "Сохранить измерение": "Save measurement",
    "Сохранить вид": "Save view",
    "Вид": "View",
    "Моя метка": "My placemark",
    "Мой путь": "My path",
    "Мой многоугольник": "My polygon",
    "Слои как на карте QGIS": "Layers as on the QGIS map",
    "С флажком глобус показывает слои проекта, включённые в дереве слоёв "
    "QGIS, и отметка в списке глобуса включает слой и на карте. Без "
    "флажка отметки глобуса свои и карту не меняют. Флажок хранится "
    "в проекте.":
        "When checked, the globe shows the project layers switched on in "
        "the QGIS layer tree, and a check mark in the globe list switches "
        "the layer on the map too. When unchecked, the globe has its own "
        "check marks and does not change the map. The option is stored in "
        "the project.",
    "Новые слои сразу на глобус": "New layers straight to the globe",
    "С флажком слой, добавленный в проект, например результат обработки, "
    "сразу отмечается на глобусе. Без флажка его отмечают в списке "
    "глобуса.":
        "When checked, a layer added to the project, such as a processing "
        "result, is checked on the globe at once. When unchecked, it is "
        "checked in the globe list by hand.",
    "Выделить на карте": "Select on map",
    "Выделить найденные объекты в слоях QGIS. Выделение видно на карте, "
    "в таблице атрибутов и на глобусе.":
        "Select the features found in the QGIS layers. The selection shows "
        "on the map, in the attribute table and on the globe.",
    "Мои метки": "My Places",
    "Сохранённые метки, виды, пути, многоугольники и измерения. Они "
    "хранятся в общем файле профиля QGIS и видны в любом проекте. "
    "Двойной щелчок по метке переносит к ней. Метки и папки "
    "перетаскиваются мышью. Меню по правой кнопке - тур, новая папка, "
    "перелёт, переименование, удаление, слои меток в проекте. Несколько "
    "строк выделяются с Ctrl и Shift, выделенное удаляется клавишей Del.":
        "Saved placemarks, views, paths, polygons and measurements. They "
        "are kept in a shared file of the QGIS profile and are visible in "
        "any project. Double-clicking a place flies there. Places and "
        "folders are moved by dragging. The right-click menu plays a "
        "tour, makes a new folder, flies there, renames, deletes and adds "
        "the places layers to the project. Several rows are selected with "
        "Ctrl and Shift, the Del key deletes the selection.",
    "Показать выбранное": "Show selected",
    "Скрыть выбранное": "Hide selected",
    "Удалить выбранное ({count})": "Delete selected ({count})",
    "Удалить выбранное": "Delete selected",
    "Удалить выбранное из «Моих меток»? Строк {count}, папки удаляются "
    "со всем содержимым.":
        "Delete the selection from My Places? Rows {count}, folders are "
        "deleted with all their contents.",
    "Мои метки - точки": "My Places - points",
    "Мои метки - линии": "My Places - lines",
    "Мои метки - многоугольники": "My Places - polygons",
    "Без названия": "Untitled",
    "Переименовать…": "Rename…",
    "Удалить": "Delete",
    "Добавить слои меток в проект": "Add the places layers to the project",
    "Переименовать": "Rename",
    "Название": "Name",
    "Удалить метку": "Delete placemark",
    "Удалить «{name}» из «Моих меток»?": "Delete \"{name}\" from My Places?",
    "значения в точке": "values at the point",
    "{point}, высота {height} м": "{point}, elevation {height} m",
    "Объекты": "Features",
    "Объект": "Feature",
    "Значение": "Value",
    "Под точкой объектов нет": "No features at the point",
    "Синхронизация с окном карты QGIS. Направление - в свойствах вида.":
        "Synchronization with the QGIS map window. The direction is set "
        "in the view properties.",
    "Определить объекты. Щелчок по глобусу показывает координаты и высоту "
    "точки и объекты слоёв проекта, отмеченных на глобусе.":
        "Identify features. A click on the globe shows the coordinates and "
        "elevation of the point and the features of the project layers "
        "checked on the globe.",
    "В обе стороны": "Both ways",
    "Карта ведёт глобус": "Map leads the globe",
    "Глобус ведёт карту": "Globe leads the map",
    "Кто за кем следует, когда синхронизация включена значком в углу "
    "вида. Карта ведёт глобус - сдвиг и масштаб карты переносят глобус "
    "на тот же участок, наклон и поворот глобуса остаются. Глобус ведёт "
    "карту - после остановки глобуса карта встаёт в его точку взгляда "
    "в своей системе координат.":
        "Which side follows which when synchronization is switched on with "
        "the button in the corner of the view. Map leads the globe - "
        "panning and zooming the map move the globe to the same area, the "
        "tilt and heading of the globe stay. Globe leads the map - after "
        "the globe stops, the map centres on its look-at point in the map "
        "coordinate system.",
    "Карта QGIS": "QGIS map",
    "Синхронизация": "Synchronization",
    "Подписи": "Labels",
    "Язык": "Language",
    "Как в QGIS": "As in QGIS",
    "Местные названия": "Local names",
    "Язык названий пунктов, водоёмов, вершин и других подписей глобуса. "
    "«Как в QGIS» берёт язык интерфейса QGIS. Если названия на выбранном "
    "языке нет, ставится название латиницей или местное. Подписи "
    "меняются сразу.":
        "Language of place, water, peak and other labels on the globe. "
        "\"As in QGIS\" takes the QGIS interface language. If a name in "
        "the chosen language is missing, the Latin or local name is shown. "
        "Labels change at once.",
    "русский": "Russian",
    "английский": "English",
    "немецкий": "German",
    "французский": "French",
    "испанский": "Spanish",
    "итальянский": "Italian",
    "португальский": "Portuguese",
    "польский": "Polish",
    "украинский": "Ukrainian",
    "казахский": "Kazakh",
    "турецкий": "Turkish",
    "арабский": "Arabic",
    "китайский": "Chinese",
    "японский": "Japanese",
    "корейский": "Korean",
    "Скрыть боковую панель": "Hide sidebar",
    "Показать боковую панель": "Show sidebar",
    # Тур.

    "Запустить тур": "Play tour",
    " с": " s",
    "Сколько секунд камера стоит на каждой остановке. Новая пауза "
    "действует с перехода кнопками или с нового запуска тура.":
        "How many seconds the camera stays at each stop. A new pause "
        "applies from the next button step or a new start of the tour.",
    "Остановка {n} из {count}: {name}": "Stop {n} of {count}: {name}",
    "Предыдущая остановка": "Previous stop",
    "Пауза": "Pause",
    "Следующая остановка": "Next stop",
    "Закончить тур": "End tour",
    "Сколько тура прошло. Ползунок перематывает тур. Камера сразу "
    "встаёт в эту точку, тур идёт дальше с неё.":
        "How much of the tour has passed. The slider winds the tour. The "
        "camera moves to that point at once, and the tour goes on from it.",
    "Записать тур кадрами PNG, 25 кадров в секунду тура, в размере "
    "окна. Каждый кадр ждёт загрузки тайлов, поэтому запись идёт "
    "дольше тура. Кадры с теми же номерами в папке заменяются.":
        "Record the tour as PNG frames, 25 frames per second of the tour, "
        "at the window size. Each frame waits for tiles to load, so "
        "recording takes longer than the tour. Frames with the same "
        "numbers in the folder are replaced.",
    "Запись: кадр {n} из {count}": "Recording: frame {n} of {count}",
    "Папка для кадров тура": "Folder for tour frames",
    "Запись тура прервана на кадре {n}.":
        "Tour recording stopped at frame {n}.",
    "Видеокарта не создала буфер размера окна.":
        "The graphics card could not create a buffer of the window size.",
    "Тур записан в {folder}. Кадров {count}, {fps} в секунду.":
        "Tour recorded in {folder}. Frames {count}, {fps} per second.",
    "Продолжить": "Continue",
    "В туре нет остановок. Отметьте флажком метки в «Моих метках».":
        "The tour has no stops. Check places in My Places.",
    "Тур по пути": "Tour along the path",
    "Тур вдоль выбранного пути": "Tour along the selected path",
    "Тур по отмеченным «Моим меткам»": "Tour over the checked places",
    "Тур: выберите папку «Мои метки» или путь в ней":
        "Tour: select the My Places folder or a path in it",
    "Тур по отмеченным меткам папки": "Tour over the checked places of "
                                      "the folder",
    "Новая папка": "New Folder",
    "Удалить папку": "Delete folder",
    "Удалить папку «{name}» со всем содержимым?":
        "Delete folder “{name}” with all its contents?",

    # KML и KMZ.
    "Открыть KML или KMZ…": "Open KML or KMZ…",
    "Открыть KML или KMZ": "Open KML or KMZ",
    "Сохранить как KML…": "Save as KML…",
    "Сохранить как KML": "Save as KML",
    "KML и KMZ (*.kml *.kmz)": "KML and KMZ (*.kml *.kmz)",
    "KMZ (*.kmz);;KML (*.kml)": "KMZ (*.kmz);;KML (*.kml)",
    "Файл не прочитан: {error}": "The file was not read: {error}",
    "Файл не записан: {error}": "The file was not written: {error}",
    "В файле нет точек, линий и многоугольников.":
        "The file has no points, lines or polygons.",

    # Свойства метки.
    "Свойства…": "Properties…",
    "Свойства: {name}": "Properties: {name}",
    "Описание метки. Оно сохраняется в файле меток и уходит в KML.":
        "Description of the place. It is kept in the places file and goes "
        "to KML.",
    "Описание": "Description",
    " м": " m",
    "Подъём над рельефом. Ноль - "
    "объект лежит на земле.":
        "Height above the terrain. "
        "Zero lays the object on the ground.",
    "Высота над землёй": "Height above ground",
    "Выдавить до земли": "Extend to ground",
    "Значок": "Icon",
    "Кружок": "Circle", "Кнопка": "Pushpin", "Флаг": "Flag",
    "Справка": "Information", "Фотоаппарат": "Camera", "Дом": "House",
    "Вершина": "Peak", "Лес": "Forest", "Вода": "Water",
    "Геодезический пункт": "Survey point", "Карьер": "Quarry",
    "Пеший маршрут": "Hiking", "Лагерь": "Camp", "Автомобиль": "Car",
    "Автобус": "Bus", "Железная дорога": "Railway", "Трамвай": "Tram",
    "Аэропорт": "Airport", "Судно": "Ship", "Заправка": "Fuel",
    "Стоянка": "Parking", "Больница": "Hospital", "Аптека": "Pharmacy",
    "Школа": "School", "Храм": "Church", "Музей": "Museum",
    "Гостиница": "Hotel", "Ресторан": "Restaurant", "Кафе": "Cafe",
    "Магазин": "Shop", "Полиция": "Police", "Пожарная часть": "Fire station",
    "Почта": "Post office", "Горные лыжи": "Skiing", "Купание": "Swimming",
    "Нет": "None", "Момент": "Moment", "Промежуток": "Interval",
    "Цвет значка метки на глобусе и в списке.":
        "Color of the placemark icon on the globe and in the list.",
    "Значок точки на глобусе и в списке. В KML он уходит "
    "адресом стандартного значка той же темы.":
        "Icon of the point on the globe and in the list. In KML it goes as "
        "the address of a standard icon of the same theme.",
    "Собственное время метки, как TimeStamp и TimeSpan "
    "в KML. Метка со временем видна, пока её время "
    "попадает в промежуток шкалы времени вверху вида. Метка "
    "без времени видна всегда.":
        "The placemark's own time, as TimeStamp and TimeSpan in KML. "
        "A placemark with a time shows while its time falls into the "
        "interval of the time slider at the top of the view. A placemark "
        "without a time always shows.",
    "Дата и время вида. Перелёт к метке "
    "и тур ставят шкалу времени на это время.":
        "Date and time of the view. A flight to the "
        "placemark and a tour set the time slider to this time.",
    "Дата/время": "Date/time",
    "Записать тур с экрана. Двигайте камеру "
    "мышью, клавишами или перелётами, повторный щелчок "
    "останавливает запись. Тур ложится в «Мои метки».":
        "Record a tour from the screen. Move the camera with the mouse, "
        "keys or flights, a second click stops recording. The tour goes "
        "into My Places.",
    "Тур": "Tour",
    "Демо «Пермь»": "Perm demo",
    "Сцена с метками по Перми: значки, время прогулки на шкале, "
    "виды, маршрут, выдавленный многоугольник, записанный облёт "
    "и 3D-здания. Метки ложатся новой папкой в «Мои метки».":
        "A scene with placemarks around Perm: icons, the time of a walk on "
        "the time slider, views, a route, an extruded polygon, a recorded "
        "flight and 3D buildings. The placemarks go into My Places as a new "
        "folder.",
    "Сохранить тур": "Save tour",
    "Тур не записан, камера не двигалась.":
        "The tour was not recorded, the camera did not move.",
    "Запись тура {clock}. Повторный щелчок "
    "по кнопке записи её заканчивает.":
        "Recording a tour {clock}. A second click on the record button "
        "ends it.",
    "Проиграть: промежуток идёт вдоль шкалы, метки появляются "
    "и скрываются по своему времени.":
        "Play: the interval moves along the slider, placemarks appear and "
        "hide by their time.",
    "Промежуток времени меток. Бегунки тянутся по одному или "
    "вместе за середину, щелчок по полосе переносит промежуток. "
    "Метки вне промежутка скрыты, метки без времени видны "
    "всегда.":
        "The time interval of placemarks. The handles are dragged one at a "
        "time or together by the middle, a click on the bar moves the "
        "interval. Placemarks outside the interval are hidden, placemarks "
        "without a time always show.",
    "Скорость проигрывания. При ×1 промежуток проходит шкалу "
    "за 20 секунд.":
        "Playback speed. At ×1 the interval crosses the slider in 20 "
        "seconds.",
    "Снимок вида метки": "Snapshot view",
    "Вид метки": "Place view",
    "Откуда смотрит камера, когда летит к метке или стоит на ней "
    "в туре. Без своего вида камера "
    "берёт метку в кадр целиком.":
        "Where the camera looks from when it flies to the place or stands "
        "at it in a tour. Without a "
        "view of its own the camera frames the whole place.",
    "Широта": "Latitude",
    "Широта точки, на которую смотрит камера. Она может "
    "не совпадать с меткой.":
        "Latitude of the point the camera looks at. It may differ from "
        "the place.",
    "Долгота": "Longitude",
    "Долгота точки, на которую смотрит камера.":
        "Longitude of the point the camera looks at.",
    "Расстояние": "Range",
    "Расстояние от камеры до точки взгляда. "
    "Больше - вид шире.":
        "Distance from the camera to the look point. Larger "
        "gives a wider view.",
    "Азимут": "Heading",
    "Куда смотрит камера. 0 - север "
    "вверху кадра.":
        "Where the camera faces. 0 puts north "
        "at the top of the frame.",
    "Наклон": "Tilt",
    "Наклон камеры. 0 - взгляд "
    "отвесно вниз, больше - к горизонту.":
        "Camera tilt. 0 looks straight down, "
        "larger values look towards the horizon.",
    "Снимок текущего вида": "Snapshot current view",
    "Взять вид глобуса сейчас: точку взгляда, расстояние, азимут "
    "и наклон.":
        "Take the current globe view: look point, range, heading and tilt.",
    "Сброс": "Reset",
    "Вернуть вид, который был у метки при открытии окна.":
        "Return the view the place had when the window opened.",
    "Стена от поднятого объекта до земли, у точки - стойка. Работает при "
    "высоте больше нуля.":
        "A wall from the raised object down to the ground, a post for a "
        "point. Works with a height above zero.",
    "Цвет линии или контура.": "Color of the line or outline.",
    "Цвет заливки многоугольника. Прозрачность задаётся здесь же. "
    "Заливкой красится и стена до земли.":
        "Fill color of the polygon, with its transparency. The wall down "
        "to the ground takes this color too.",
    "Заливка": "Fill",
    # Треки.
    "Трек…": "Track…",
    "Трек: {name}": "Track: {name}",
    "Поле с датой и временем точки. Годятся поля даты и времени, текст "
    "в виде ISO 8601 и число секунд от 1970 года.":
        "The field with the date and time of the point. Date and time "
        "fields, ISO 8601 text and seconds since 1970 are accepted.",
    "Время": "Time",
    "Один объект": "One object",
    "Поле, которое отличает объекты друг от друга, например номер машины. "
    "У каждого объекта свой путь и своя метка.":
        "The field that tells objects apart, for example a vehicle number. "
        "Each object gets its own path and label.",
    "Цвет пройденного пути.": "Color of the path travelled.",
    "Камера следом": "Camera follows",
    "Камера держит первый объект трека в центре, азимут - по ходу "
    "движения. Расстояние и наклон меняются колесом и мышью.":
        "The camera keeps the first object of the track in the center, "
        "heading along the motion. Distance and tilt change with the wheel "
        "and the mouse.",
    "Убрать трек": "Remove track",
    "Слой больше не показывается треком.":
        "The layer is no longer shown as a track.",
    # Состояние загрузки.
    "загрузка стоит {seconds} с": "loading stalled for {seconds} s",
    "загрузка {count}": "loading {count}",
    "Загрузка стоит {seconds} с": "Loading stalled for {seconds} s",
    "Идёт загрузка: {count}": "Loading: {count}",
    "метки тяжёлые, {count} тыс. вершин":
        "places are heavy, {count} thousand vertices",
    # Сцена.
    "Сцена - камера, время, слои на глобусе, настройки вида и выбранная "
    "папка «Моих меток» с её туром. Сохраняется в файл и открывается "
    "на другом компьютере.":
        "A scene is the camera, time, layers on the globe, view settings "
        "and the selected My Places folder with its tour. It saves to a "
        "file and opens on another computer.",
    "Сохранить сцену…": "Save Scene…",
    "Открыть сцену…": "Open Scene…",
    "Сохранить сцену": "Save Scene",
    "Открыть сцену": "Open Scene",
    "Сцена PlanetX (*{ext})": "PlanetX scene (*{ext})",
    "Сцена сохранена: {path}": "Scene saved: {path}",
    "Сцена открыта, слои не найдены: {names}":
        "Scene opened, layers not found: {names}",
    # Меню слоя проекта.
    "Прозрачность": "Transparency",
    "{value} %": "{value} %",
    "Свойства слоя…": "Layer Properties…",
    "Прозрачность слоя QGIS. Она меняется и на карте, сквозь прозрачный "
    "слой видна подложка и слои под ним.":
        "Transparency of the QGIS layer. It changes on the map too, the "
        "base map and the layers below show through a transparent layer.",
    # Снимок вида.
    "Снимок вида": "View snapshot",
    "Вид в макет": "View to layout",
    "Снимок вида в файл PNG или JPEG, в том числе больше окна.":
        "Snapshot of the view to a PNG or JPEG file, larger than the "
        "window if needed.",
    "Вид в макет QGIS неизменной картинкой, вставленной в проект.":
        "The view into a QGIS layout as a fixed picture embedded in the "
        "project.",
    "Пропорции окна": "Window proportions",
    "Высота снимка следует за шириной в пропорциях окна глобуса. Без "
    "флажка снимок захватывает больше или меньше по сторонам, чем окно.":
        "The snapshot height follows the width in the proportions of the "
        "globe window. Without the check box the snapshot covers more or "
        "less at the sides than the window.",
    "Снять сейчас": "Take now",
    "Не ждать остальных тайлов. На снимке останутся менее подробные "
    "места.":
        "Do not wait for the remaining tiles. Some places on the snapshot "
        "stay less detailed.",
    "Отмена": "Cancel",
    "Ширина": "Width",
    "Высота": "Height",
    "Ширина снимка. Снимок шире окна берёт более подробные тайлы, надписи "
    "и линии на нём крупнее в той же доле.":
        "Snapshot width. A snapshot wider than the window takes more "
        "detailed tiles, its labels and lines are larger in the same "
        "proportion.",
    "Высота снимка. Угол обзора по вертикали тот же, что у окна.":
        "Snapshot height. The vertical field of view is the same as in the "
        "window.",
    "Новый макет": "New layout",
    "Макет, в первый лист которого ляжет картинка вида. Новый макет "
    "создаётся с листом по умолчанию.":
        "The layout whose first page receives the view picture. A new "
        "layout is created with the default page.",
    "Ширина картинки на листе. Вместе с разрешением задаёт размер снимка "
    "в пикселях и подробность тайлов.":
        "Picture width on the page. Together with the resolution it sets "
        "the snapshot size in pixels and the tile detail.",
    "Высота картинки на листе. Угол обзора по вертикали тот же, что "
    "у окна.":
        "Picture height on the page. The vertical field of view is the "
        "same as in the window.",
    " dpi": " dpi",
    "Разрешение вывода макета. Надписи на бумаге выходят того же размера, "
    "что на экране. Большое разрешение дольше грузит тайлы.":
        "Output resolution of the layout. Labels on paper come out the "
        "same size as on screen. A high resolution loads tiles longer.",
    "Макет": "Layout",
    "Разрешение": "Resolution",
    "Снимок {width} × {height} пикселей":
        "Snapshot {width} × {height} pixels",
    "Загрузка тайлов для снимка…": "Loading tiles for the snapshot…",
    "Снимок ждёт загрузки: {count}": "Snapshot waits for loading: {count}",
    " Часть тайлов не загрузилась, там менее подробный снимок.":
        " Some tiles did not load, the imagery there is less detailed.",
    "Вставить в макет": "Insert into layout",
    "Сохранить…": "Save…",
    "Глобус дорисовывает вид в нужном размере и ждёт загрузки подробных "
    "тайлов. Камера на это время стоит.":
        "The globe renders the view at the required size and waits for "
        "the detailed tiles. The camera stays still meanwhile.",
    "Выбрать файл PNG или JPEG и снять вид в нём. Глобус ждёт загрузки "
    "подробных тайлов, камера на это время стоит.":
        "Choose a PNG or JPEG file and take the view into it. The globe "
        "waits for the detailed tiles, the camera stays still meanwhile.",
    " пикс.": " px",
    " мм": " mm",
    "Изображения (*.png *.jpg *.jpeg)": "Images (*.png *.jpg *.jpeg)",
    "Глобус ещё не готов к снимку.": "The globe is not ready for a "
                                     "snapshot yet.",
    "Видеокарта не создала буфер такого размера. Уменьшите снимок.":
        "The graphics card did not create a buffer of this size. Make the "
        "snapshot smaller.",
    "Не удалось записать {path}": "Could not write {path}",
    "Картинка вставлена в макет «{name}».":
        "The picture is inserted into layout “{name}”.",
    "Снимок сохранён: {path}": "Snapshot saved: {path}",
}

_language = None


def _detect():
    """Двухбуквенный код языка интерфейса QGIS."""
    value = ""
    try:
        from qgis.core import QgsSettings
    except ImportError:  # headless-тесты, язык берётся из окружения
        QgsSettings = None
    if QgsSettings is not None:
        value = QgsSettings().value("locale/userLocale", "") or ""
    if not value:
        # locale.getdefaultlocale устарел и выдаёт предупреждение Python.
        # Язык берётся из переменных окружения напрямую.
        for name in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
            found = os.environ.get(name)
            if found:
                value = found.split(":")[0].split(".")[0]
                break
    return (value or "en")[:2].lower()


def set_language(code):
    """Задать язык принудительно. Нужно тестам."""
    global _language
    _language = (code or "en")[:2].lower()


def ui_language():
    """Двухбуквенный код языка интерфейса QGIS."""
    global _language
    if _language is None:
        _language = _detect()
    return _language


def is_russian():
    return ui_language() == "ru"


def tr(text, /, **values):
    """Перевод строки и подстановка значений в фигурные скобки.

    Строка только позиционная, иначе подстановка {text} падала
    с TypeError, 27 сентября 2026 года.
    """
    out = text if is_russian() else EN.get(text, text)
    return out.format(**values) if values else out
