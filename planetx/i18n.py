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
    "Глобус": "Globe",
    "Свойства вида: двойной щелчок": "View properties: double click",
    "Подложка": "Base map",
    "{name} · {kind}": "{name} · {kind}",
    "Отметка показывает слой на глобусе, видимость на карте QGIS "
    "не меняется. Меню по правой кнопке - перелёт к слою.":
        "The check shows the layer on the globe, its visibility on the "
        "QGIS map does not change. The right-click menu flies to the "
        "layer.",
    "Подлететь": "Fly to",
    "Свойства вида…": "View properties…",
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
    "Двойной щелчок по строке «Глобус» открывает свойства вида. В них "
    "выбираются подложка, масштаб рельефа и язык подписей.":
        "A double click on the Globe row opens the view properties. "
        "There you choose the base map, the terrain exaggeration and the "
        "label language.",
    "Поиск мест: Nominatim, © участники OpenStreetMap.":
        "Place search: Nominatim, © OpenStreetMap contributors.",
    "Векторная основа: OpenFreeMap, © OpenMapTiles, © участники "
    "OpenStreetMap.":
        "Vector base: OpenFreeMap, © OpenMapTiles, © OpenStreetMap "
        "contributors.",
    "О модуле PlanetX": "About PlanetX",
    "Левая кнопка тянет Землю, после отпускания она вращается "
    "по инерции.":
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
    "Сообщить об ошибке": "Report a bug",
    "Страница в каталоге QGIS": "QGIS plugin page",
    "Трёхмерный глобус внутри QGIS в духе Google Earth. Рельеф, "
    "атмосфера, подложки из подключений QGIS.":
        "A 3D globe inside QGIS in the spirit of Google Earth. Terrain, "
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
    "перелёт, переименование, удаление, слои меток в проекте.":
        "Saved placemarks, views, paths, polygons and measurements. They "
        "are kept in a shared file of the QGIS profile and are visible in "
        "any project. Double-clicking a place flies there. Places and "
        "folders are moved by dragging. The right-click menu plays a "
        "tour, makes a new folder, flies there, renames, deletes and adds "
        "the places layers to the project.",
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
    "Подъём над рельефом, как «относительно земли» в Google Earth. Ноль - "
    "объект лежит на земле.":
        "Height above the terrain, as relative to ground in Google Earth. "
        "Zero lays the object on the ground.",
    "Высота над землёй": "Height above ground",
    "Выдавить до земли": "Extend to ground",
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
    "Вставить": "Insert",
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
