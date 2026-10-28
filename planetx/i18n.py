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
    # Снимок неба - обзоры HiPS, 24 октября 2026 года.
    "Объекты глубокого неба": "Deep-sky objects",
    "Подписи галактик, туманностей и скоплений каталогов Мессье, NGC "
    "и IC. Щелчок по подписи открывает карточку объекта.":
        "Labels of galaxies, nebulae and clusters of the Messier, NGC and "
        "IC catalogues. A click on a label opens the object card.",
    "Спросить помощника об этом объекте неба. Помощнику уходят "
    "обозначение, название, вид, созвездие и координаты объекта. Ответ "
    "появится здесь и под строкой «Поиск».":
        "Ask the assistant about this sky object. The assistant receives "
        "the designation, name, type, constellation and coordinates of "
        "the object. The answer appears here and under the Search line.",
    "Обозначение": "Designation",
    "Созвездие": "Constellation",
    "Другое название": "Other name",
    "Звёздная величина": "Magnitude",
    "Размер": "Size",
    "{size}′": "{size}′",
    "Прямое восхождение": "Right ascension",
    "Объект в базе SIMBAD": "Object in the SIMBAD database",
    "Каталог - OpenNGC, CC BY-SA 4.0": "Catalogue - OpenNGC, CC BY-SA 4.0",
    "Объясни, что это за объект неба и чем он интересен наблюдателю. "
    "{kind} {label} «{name}» в созвездии {const}, прямое восхождение "
    "{ra}, склонение {dec}.":
        "Explain what this sky object is and what makes it interesting to "
        "an observer. {kind} {label} \"{name}\" in the constellation "
        "{const}, right ascension {ra}, declination {dec}.",
    "Поиск на небе: {text}": "Sky search: {text}",
    "На небе не найдено: {text}": "Not found in the sky: {text}",
    "Найдено: {name}": "Found: {name}",
    "Снимки неба при приближении": "Sky imagery on zooming in",
    "Ближе поля зрения около 50° вместо картинки Млечного пути "
    "проявляется подробная карта неба NASA, ближе 6° - снимки "
    "обзора DSS. Без флажка небо - картинка Млечного пути "
    "и звёзды каталога.":
        "Below a field of view of about 50° the detailed NASA sky map "
        "fades in instead of the Milky Way image, below 6° the DSS "
        "survey images. Without the check box the sky is the Milky Way "
        "image and catalog stars.",
    # Суда Балтики и самолёты, 19 октября 2026 года.
    "Пассажирские": "Passenger",
    "Танкеры": "Tankers",
    "Рыболовные": "Fishing",
    "Буксиры и служебные": "Tugs and service",
    "Скоростные": "High-speed",
    "Яхты и катера": "Yachts and boats",
    "Прочие и без сведений": "Other and unknown",
    "Лёгкие": "Light",
    "Малые": "Small",
    "Пассажирские и грузовые": "Airliners and freighters",
    "Тяжёлые": "Heavy",
    "Вертолёты": "Helicopters",
    "Суда Балтики": "Baltic ships",
    "Суда": "Ships",
    "Щелчок по судну - сведения": "Click a ship for details",
    "Самолёты": "Aircraft",
    "Щелчок по борту - сведения": "Click an aircraft for details",
    "MMSI": "MMSI",
    "{value} уз": "{value} kn",
    "Код ICAO": "ICAO code",
    "{metres} м ({feet} футов)": "{metres} m ({feet} ft)",
    "на земле": "on the ground",
    "Позывной": "Call sign",
    "IMO": "IMO",
    "Назначение": "Destination",
    "Размеры": "Size",
    "{length} × {width} м": "{length} × {width} m",
    "Бортовой номер": "Registration",
    "Суда Финского и Ботнического заливов и Балтики у Финляндии по "
    "сигналам AIS, открытые данные Fintraffic Digitraffic, положения раз "
    "в 20 с. Издалека судно - точка цвета типа с названием, вблизи - "
    "условная модель своей длины, которая идёт своим курсом. Щелчок "
    "показывает тип, позывной, назначение, размеры и скорость.":
        "Ships of the Gulfs of Finland and Bothnia and the Baltic near "
        "Finland by AIS signals, Fintraffic Digitraffic open data, the "
        "positions every 20 s. From afar a ship is a dot in the colour of "
        "its type with its name, close up a schematic model of its length "
        "that keeps its course. A click shows the type, call sign, "
        "destination, size and speed.",
    "Самолёты по сигналам ADS-B сети добровольцев adsb.lol в круге у "
    "точки взгляда, раз в 10 с. Самолёт в воздухе стоит на своей высоте, "
    "вблизи - условная модель размера своей категории с креном. Щелчок "
    "показывает позывной, тип, бортовой номер, высоту и скорость. Над "
    "Россией приёмников сети почти нет.":
        "Aircraft by ADS-B signals of the adsb.lol volunteer network in a "
        "circle around the point of view, every 10 s. An aircraft in the "
        "air is shown at its altitude, close up as a schematic model of "
        "the size of its category with its bank. A click shows the call "
        "sign, type, registration, altitude and speed. The network has "
        "almost no receivers over Russia.",

    # Высота точек трека, 19 октября 2026 года.
    "По земле": "On the ground",
    "Откуда высота точки: Z точки или числовое поле. «По земле» - объект "
    "и модель стоят на рельефе.":
        "Where the height of a point comes from: the point Z or a numeric "
        "field. On the ground - the object and the model stand on the "
        "terrain.",
    "над уровнем моря": "above sea level",
    "над землёй": "above the ground",
    "Над уровнем моря - высота полёта по барометру или GPS, путь рисуется "
    "в воздухе. Над землёй - подъём над рельефом под точкой, например у "
    "дрона.":
        "Above sea level - the flight altitude by barometer or GPS, the "
        "path is drawn in the air. Above the ground - the rise over the "
        "terrain under the point, for example for a drone.",
    "метры": "metres",
    "футы": "feet",
    "Единицы высоты. Высоту самолётов ADS-B передают в футах.":
        "Height units. ADS-B aircraft altitude is given in feet.",
    "Единицы высоты": "Height units",
    # Модель по треку и поезда Финляндии, 18 октября 2026 года.
    "Дальнего следования": "Long-distance",
    "Пригородные": "Commuter",
    "Грузовые": "Cargo",
    "Локомотивы": "Locomotives",
    "Маневровые": "Shunting",
    "Путевые машины": "On-track machines",
    "Поезда Финляндии": "Trains of Finland",
    "Поезда": "Trains",
    "Щелчок по поезду - сведения": "Click a train for details",
    "Поезда Финляндии, суда Балтики и самолёты в реальном времени по "
    "открытым данным Fintraffic и сети ADS-B adsb.lol.":
        "Trains of Finland, Baltic ships and aircraft in real time from "
        "Fintraffic open data and the adsb.lol ADS-B network.",
    "Поезда Финляндии в реальном времени по открытым данным Fintraffic "
    "Digitraffic, положения обновляются раз в 10 с. Издалека поезд - точка "
    "цвета категории с номером, вблизи - модель вагона, которая едет по "
    "рельсам OpenStreetMap между обновлениями. Щелчок по поезду показывает "
    "вид, номер и скорость.":
        "Trains of Finland in real time from Fintraffic Digitraffic open "
        "data, the positions are updated every 10 s. From afar a train is "
        "a dot in the colour of its category with its number, close up it "
        "is a car model that moves along OpenStreetMap rails between "
        "updates. A click on a train shows its type, number and speed.",
    "без модели": "no model",
    "Файл 3D-модели glTF, Collada или OBJ. Модель едет по пути каждого "
    "объекта трека, перёд смотрит по ходу движения. Пустое поле - объект "
    "показан меткой.":
        "A glTF, Collada or OBJ 3D model file. The model moves along the "
        "path of every object of the track, its front facing the direction "
        "of travel. An empty field shows the object as a placemark.",
    "Выбрать файл модели.": "Choose the model file.",
    "Множитель размера модели. С множителем 1 модель стоит в своих метрах, "
    "больший множитель делает её заметной издалека.":
        "The size factor of the model. With the factor 1 the model keeps "
        "its own metres, a larger factor makes it visible from afar.",
    "Масштаб модели": "Model scale",
    "Поворот модели по часовой стрелке к ходу движения. Нужен, если перёд "
    "модели в файле смотрит не на север, например 180° у модели glTF, "
    "повёрнутой передом к зрителю.":
        "The clockwise turn of the model to the direction of travel. It is "
        "needed when the front of the model in the file does not face "
        "north, for example 180° for a glTF model facing the viewer.",
    "Поворот модели": "Model turn",
    "3D-модель трека": "Track 3D model",
    "3D-модели ({patterns})": "3D models ({patterns})",
    "Номер поезда": "Train number",
    "{value} км/ч": "{value} km/h",
    "Положение, UTC": "Position, UTC",
    "Категория": "Category",
    "Журнал работы": "Log",
    "Открывает журнал модуля программой системы. В журнале - события "
    "модуля, ошибки Python и стеки потоков, если QGIS не отвечал "
    "дольше 10 с. Файл пригодится при сообщении об ошибке.":
        "Opens the plugin log in the system program. The log holds "
        "plugin events, Python errors and the stacks of threads when "
        "QGIS did not respond for more than 10 s. The file helps with "
        "an error report.",
    "Главный поток QGIS не отвечал {seconds} с.":
        "The QGIS main thread did not respond for {seconds} s.",
    "Ошибка Python:": "Python error:",
    "Ошибки SSL запроса {number}:": "SSL errors of request {number}:",
    "Модуль выгружен.": "The plugin is unloaded.",
    "QGIS закрыт.": "QGIS is closed.",
    "Космоснимки здесь…": "Satellite images here…",
    "Инсоляция здесь…": "Insolation here…",
    "Тени здесь…": "Shadows here…",
    "Где тень и где солнце на момент шкалы времени - по рельефу и зданиям, "
    "тени идут за шкалой.":
        "Shade and sun at the moment of the time slider, from the terrain "
        "and buildings. The shadows follow the slider.",
    "Тени": "Shadows",
    "{local} (UTC {utc})": "{local} (UTC {utc})",
    "Момент - правый бегунок шкалы времени, без шкалы - часы компьютера. "
    "После «Построить» тени идут за шкалой: двигайте бегунок или пустите "
    "показ ▶.":
        "The moment is the right handle of the time slider, without the "
        "slider - the computer clock. After Build the shadows follow the "
        "slider. Move the handle or start playback ▶.",
    "Здания OpenFreeMap, свои 3D-модели и выдавленные многоугольники дают "
    "тени. Высота у части зданий OpenFreeMap условная. Здание уже шага "
    "сетки может не попасть в расчёт.":
        "OpenFreeMap buildings, your own 3D models and extruded polygons "
        "cast shadows. Some OpenFreeMap buildings have an assumed height. "
        "A building narrower than the grid step may be missed.",
    "Тени считаются только для Земли.":
        "Shadows are computed for the Earth only.",
    "Расчёт горизонта: {share}": "Computing the horizon: {share}",
    "Шаг сетки - {step} м.": "The grid step is {step} m.",
    "Построено в {time}.": "Built at {time}.",
    "Солнце ниже горизонта - тень везде.":
        "The Sun is below the horizon, everything is in shade.",
    "Солнце на высоте {height}°, на солнце {share} участка.":
        "The Sun is {height}° high, {share} of the area is in sunlight.",
    "Тени {moment}": "Shadows {moment}",
    "Тень": "Shade",
    "Тени рельефа, зданий и 3D-моделей вблизи камеры, в радиусе до 5 км "
    "от точки взгляда. Без флажка - свет солнца без теней, кадр рисуется "
    "быстрее.":
        "Shadows of the terrain, buildings and 3D models near the camera, "
        "within 5 km of the look point. Without the box the sunlight has "
        "no shadows, and the frame is drawn faster.",
    "Учитывать здания": "Include buildings",
    "Здания OpenFreeMap поднимают рельеф на свою высоту и закрывают обзор. "
    "Высота у части зданий условная. Здание уже шага расчёта может не "
    "попасть в расчёт. Только на Земле.":
        "OpenFreeMap buildings raise the terrain by their height and block "
        "the view. The height of some buildings is nominal. A building "
        "narrower than the computation step may be missed. Earth only.",
    "Здания OpenFreeMap дают тени и сами получают солнце крышей. Высота "
    "у части зданий условная. Здание уже шага сетки может не попасть "
    "в расчёт.":
        "OpenFreeMap buildings cast shadows and get the sun on their roofs. "
        "The height of some buildings is nominal. A building narrower than "
        "the grid step may be missed.",
    "Загрузка зданий: {done} из {total}":
        "Loading buildings: {done} of {total}",
    "Здания OpenFreeMap не учтены - круг слишком большой.":
        "OpenFreeMap buildings are not included, the circle is too large.",
    "Учтено зданий {count}.": "Buildings included: {count}.",
    "Своих {count}.": "Own {count}.",
    "Загружены не все тайлы зданий.": "Not all building tiles loaded.",
    "Космоснимки…": "Satellite images…",
    "Космоснимки": "Satellite images",
    "Температура поверхности, °C": "Surface temperature, °C",
    "Температура поверхности из продукта USGS Collection 2 Level-2 - не "
    "радиационная температура. USGS уже учёл излучательную способность "
    "поверхности по ASTER GED и атмосферу. Модуль только переводит "
    "кельвины в градусы Цельсия.":
        "Surface temperature from the USGS Collection 2 Level-2 product, "
        "not brightness temperature. USGS has already accounted for the "
        "surface emissivity from ASTER GED and for the atmosphere. The "
        "plugin only converts kelvins to degrees Celsius.",
    "Landsat 4-9 Collection 2 Level-2 (USGS), файлы и каталог Microsoft "
    "Planetary Computer. Слои несут подпись «Landsat image courtesy of the "
    "U.S. Geological Survey».":
        "Landsat 4-9 Collection 2 Level-2 (USGS), files and catalogue of "
        "Microsoft Planetary Computer. The layers carry the credit "
        "\"Landsat image courtesy of the U.S. Geological Survey\".",
    "Sentinel-2 - 10 м, с 2015 года": "Sentinel-2 - 10 m, since 2015",
    "Landsat 4-9 - 30 м, с 1982 года": "Landsat 4-9 - 30 m, since 1982",
    "Landsat 1-5 MSS - 60 м, 1972-1993 годы":
        "Landsat 1-5 MSS - 60 m, 1972-1993",
    "Все четыре канала MSS": "All four MSS bands",
    "Все каналы сцены": "All scene bands",
    "Все каналы сцены одним файлом по порядку номеров, отражение, тепловой "
    "канал Landsat - в кельвинах. У Sentinel-2 12 каналов на шаге 10 м, "
    "участок со стороной больше 20 км - на шаге 20 м. Слой показывает "
    "естественные цвета, подписи каналов видны в свойствах слоя QGIS.":
        "All bands of the scene in one file in the order of their numbers, "
        "reflectance, the Landsat thermal band in kelvins. Sentinel-2 has "
        "12 bands at a 10 m step, an area with a side over 20 km gets a "
        "20 m step. The layer shows natural colours, the band names are "
        "seen in the QGIS layer properties.",
    "Ранние снимки Landsat 1972-1993 здесь":
        "Early Landsat images 1972-1993 here",
    "Снимки ASTER здесь": "ASTER images here",
    "Landsat 1-5 MSS Collection 2 Level-1 (USGS), файлы и каталог "
    "Microsoft Planetary Computer. Значения - отражение на верху "
    "атмосферы, без поправки на атмосферу. Слои несут подпись «Landsat "
    "image courtesy of the U.S. Geological Survey».":
        "Landsat 1-5 MSS Collection 2 Level-1 (USGS), files and catalogue "
        "of Microsoft Planetary Computer. The values are top of atmosphere "
        "reflectance without atmospheric correction. The layers carry the "
        "credit \"Landsat image courtesy of the U.S. Geological Survey\".",
    "Зелёный, красный и два ближних инфракрасных канала MSS одним файлом, "
    "отражение на верху атмосферы. Слой показывает ложные цвета, "
    "остальные сочетания задаются в свойствах слоя QGIS.":
        "The green, red and two near infrared MSS bands in one file, top "
        "of atmosphere reflectance. The layer shows false colours, other "
        "combinations are set in the QGIS layer properties.",
    "Sentinel-2 - 10 м, снимки с 2015 года, каждые 5 суток. Landsat - 30 м, "
    "снимки с 1982 года и тепловой канал, у Landsat 7 после мая 2003 года на "
    "снимках пустые полосы. Landsat 1-5 MSS - 60 м, снимки 1972-1993 годов, "
    "четыре канала без синего и теплового. ASTER - 15-90 м, 14 каналов, "
    "снимки 2000-2006 годов, минеральные индексы. MODIS - готовые продукты "
    "NASA с 2000 года, сцена - день или период, пиксель 250-1000 м. Смена "
    "спутника запускает новый поиск.":
        "Sentinel-2 - 10 m, images since 2015, every 5 days. Landsat - "
        "30 m, images since 1982 and a thermal band, Landsat 7 images after "
        "May 2003 have empty stripes. Landsat 1-5 MSS - 60 m, images of "
        "1972-1993, four bands without blue and thermal. ASTER - 15-90 m, "
        "14 bands, images of 2000-2006, mineral indices. MODIS - ready NASA "
        "products since 2000, a scene is a day or a period, a pixel is "
        "250-1000 m. A change of the satellite starts a new search.",
    "ASTER - 15-90 м, 14 каналов, 2000-2006 годы":
        "ASTER - 15-90 m, 14 bands, 2000-2006",
    "ASTER с 2007 года - NASA, нужен ключ Earthdata":
        "ASTER since 2007 - NASA, an Earthdata key is needed",
    "ASTER L1T версии 004 (NASA LP DAAC, METI), каталог NASA CMR, файлы - по "
    "ключу Earthdata, его можно получить бесплатно на urs.earthdata.nasa.gov. "
    "После 2008 года - только каналы VNIR и TIR. Значения - для нормального "
    "усиления каналов.":
        "ASTER L1T version 004 (NASA LP DAAC, METI), the NASA CMR "
        "catalogue, the files by an Earthdata key, it is free at "
        "urs.earthdata.nasa.gov. After 2008 only the VNIR and TIR bands. "
        "The values are for the normal band gain.",
    "Ключ NASA Earthdata": "NASA Earthdata key",
    "Снимки ASTER после 2006 года NASA отдаёт только по ключу Earthdata. "
    "Учётная запись бесплатная - urs.earthdata.nasa.gov, ключ создаёт раздел "
    "«Generate Token» профиля, он живёт 60 дней. Ключ хранится в настройках "
    "QGIS этого компьютера.\n\nКлюч:":
        "NASA gives ASTER images after 2006 only by an Earthdata key. The "
        "account is free - urs.earthdata.nasa.gov, the key is made by the "
        "Generate Token section of the profile, it lives 60 days. The key "
        "is kept in the QGIS settings of this computer.\n\nKey:",
    "У сцены нет каналов для отмеченных продуктов - после 2008 года у ASTER "
    "только каналы VNIR и TIR.":
        "The scene has no bands for the checked products - after 2008 ASTER "
        "has only the VNIR and TIR bands.",
    "Без ключа Earthdata файлы NASA не загружаются.":
        "NASA files are not loaded without an Earthdata key.",
    "Адреса файлов NASA…": "NASA file addresses…",
    "Ключ Earthdata не принят - устарел или неверен. При следующей загрузке "
    "окно спросит новый.":
        "The Earthdata key was not accepted - it expired or is wrong. The "
        "window asks for a new one at the next load.",
    "Файл NASA не получен: {error}": "The NASA file was not received: {error}",
    "ASTER L1T (NASA, METI), файлы и каталог Microsoft Planetary Computer, "
    "съёмка 2000-2006 годов. Значения - отражение на верху атмосферы "
    "и яркостная температура для нормального усиления каналов. Слои несут "
    "подпись «ASTER data courtesy of NASA/METI/AIST/Japan Spacesystems».":
        "ASTER L1T (NASA, METI), files and catalogue of Microsoft Planetary "
        "Computer, images of 2000-2006. The values are top of atmosphere "
        "reflectance and brightness temperature for the normal band gain. "
        "The layers carry the credit \"ASTER data courtesy of "
        "NASA/METI/AIST/Japan Spacesystems\".",
    "Ложные цвета (3N 2 1)": "False colours (3N 2 1)",
    "Коротковолновый ИК (4 6 8)": "Shortwave infrared (4 6 8)",
    "Каолинит, алунит, (4 + 6) / 5": "Kaolinite, alunite, (4 + 6) / 5",
    "Серицит, мусковит, (5 + 7) / 6": "Sericite, muscovite, (5 + 7) / 6",
    "Mg-OH и карбонаты, (7 + 9) / 8": "Mg-OH and carbonates, (7 + 9) / 8",
    "Оксиды железа, 2 / 1": "Iron oxides, 2 / 1",
    "Кварц, 11² / (10 × 12)": "Quartz, 11² / (10 × 12)",
    "у сцены нет каналов SWIR для {names}":
        "the scene has no SWIR bands for {names}",
    "Отношение каналов ASTER, принятое в поисках руд (Rowan, Mars 2003, "
    "Ninomiya 2003) - (4 + 6) / 5 выделяет каолинит и алунит, (5 + 7) / 6 - "
    "серицит и мусковит, (7 + 9) / 8 - карбонаты, хлорит и эпидот, 2 / 1 - "
    "оксиды железа, кварцевый индекс - кварц по тепловым каналам. Шкала "
    "растянута по участку, тёплые цвета - больше минерала.":
        "An ASTER band ratio used in ore exploration (Rowan, Mars 2003, "
        "Ninomiya 2003) - (4 + 6) / 5 shows kaolinite and alunite, "
        "(5 + 7) / 6 shows sericite and muscovite, (7 + 9) / 8 shows "
        "carbonates, chlorite and epidote, 2 / 1 shows iron oxides, the "
        "quartz index shows quartz from the thermal bands. The scale is "
        "stretched over the area, warm colours mean more of the mineral.",
    "Наибольшая облачность всей сцены по оценке поставщика снимков, "
    "у Sentinel-2 сцена 110 × 110 км, у Landsat 185 × 180 км. Это отсев до "
    "расчёта облачности над участком. Сцена с облаками бывает чистой над "
    "участком.":
        "The largest cloud cover of the whole scene by the image provider, "
        "a Sentinel-2 scene is 110 × 110 km, a Landsat one 185 × 180 km. "
        "This is a filter before the cloud cover over the area is computed. "
        "A cloudy scene can be clear over the area.",
    "Наибольшая доля облаков и их теней над участком по маске облаков "
    "сцены. Сцены облачнее в списке скрыты.":
        "The largest share of clouds and their shadows over the area by the "
        "cloud mask of the scene. Cloudier scenes are hidden in the list.",
    "Пиксели облаков, их теней и перистых облаков по маске облаков сцены "
    "остаются пустыми, индексы по ним не считаются.":
        "Pixels of clouds, their shadows and cirrus by the cloud mask of the "
        "scene stay empty, indices are not computed over them.",
    "Дыры температуры - по формуле":
        "Temperature gaps by formula",
    "USGS не считает температуру там, где нет излучательной способности "
    "из базы ASTER GED, на большей части России это половина участка "
    "и больше. С флажком такие пиксели считаются той же формулой USGS из "
    "излучения и атмосферы сцены, излучательная способность - по NDVI. Где "
    "USGS посчитал, отличие в среднем меньше 0.5 °C.":
        "USGS does not compute the temperature where the ASTER GED database "
        "has no emissivity, over most of Russia that is half of the area or "
        "more. With the check box such pixels are computed by the same USGS "
        "formula from the radiance and atmosphere of the scene, the "
        "emissivity comes from NDVI. Where USGS computed the value, the "
        "mean difference is below 0.5 °C.",
    "Температура поверхности USGS Collection 2 Level-2. {share} % пикселей "
    "посчитаны формулой USGS с излучательной способностью по NDVI - там, "
    "где у USGS значения нет.":
        "Surface temperature of USGS Collection 2 Level-2. {share} % of the "
        "pixels are computed by the USGS formula with the emissivity from "
        "NDVI - where USGS has no value.",
    "Батиметрия водоёма":
        "Water body bathymetry",
    "Батиметрия водоёма…":
        "Water body bathymetry…",
    "Растр глубин или отметок дна озера, моря или водохранилища ложится в "
    "рельеф глобуса, над ним - полупрозрачная вода на уровне водоёма. В окне "
    "задаются, что в растре, и уровень воды.":
        "A raster of depths or bed elevations of a lake, sea or reservoir "
        "goes into the globe terrain, above it - semi-transparent water at "
        "the water body level. The window sets what the raster holds and "
        "the water level.",
    "Растр «{name}» ложится в рельеф глобуса дном водоёма, над ним рисуется "
    "вода на уровне водоёма. Уровень по умолчанию - высота рельефа в "
    "середине растра, у озера это обычно поверхность воды.":
        "The raster \"{name}\" goes into the globe terrain as the bed of "
        "the water body, water is drawn above it at the water body level. "
        "The default level is the terrain height in the middle of the "
        "raster, for a lake it is usually the water surface.",
    "Значения - глубины":
        "Values are depths",
    "Глубина под поверхностью воды, со знаком плюс или минус. Отметка дна - "
    "уровень воды минус глубина.":
        "The depth below the water surface, with a plus or minus sign. The "
        "bed elevation is the water level minus the depth.",
    "Значения - отметки дна":
        "Values are bed elevations",
    "Высота дна над уровнем моря, как у рельефа. Уровень воды нужен только "
    "для поверхности воды.":
        "The bed height above sea level, like the terrain. The water level "
        "is needed only for the water surface.",
    "Высота поверхности воды над уровнем моря. Вода рисуется на этой высоте "
    "над всеми точками, где дно ниже.":
        "The height of the water surface above sea level. The water is "
        "drawn at this height over all points where the bed is lower.",
    "Уровень воды":
        "Water level",
    "Убрать батиметрию":
        "Remove bathymetry",
    "Растр перестаёт быть рельефом глобуса, вода над ним не рисуется.":
        "The raster is no longer the globe terrain, no water is drawn over "
        "it.",
    "Бриенцское озеро, своя батиметрия":
        "Lake Brienz, own bathymetry",
    "Бриенцское озеро, дно":
        "Lake Brienz, bed",
    "Выемка {cut:,.0f} м³ на площади {cut_area:,.0f} м², до {deepest:.1f} "
    "м.\nНасыпь {fill:,.0f} м³ на площади {fill_area:,.0f} м², до "
    "{highest:.1f} м.\nРазность насыпи и выемки {net:,.0f} м³. Площадь "
    "сравнения {area:,.0f} м².":
        "Cut {cut:,.0f} m³ over {cut_area:,.0f} m², down to {deepest:.1f} "
        "m.\nFill {fill:,.0f} m³ over {fill_area:,.0f} m², up to "
        "{highest:.1f} m.\nFill minus cut {net:,.0f} m³. Compared area "
        "{area:,.0f} m².",
    "Выемка и насыпь":
        "Cut and fill",
    "Выемка и насыпь…":
        "Cut and fill…",
    "Растр «{name}» - новая съёмка рельефа. Разность с прежней съёмкой даёт "
    "выемку и насыпь, их объёмы и растр разности в проекте.":
        "The raster «{name}» is the new terrain survey. The difference with "
        "the earlier survey gives the cut and fill, their volumes and a "
        "difference raster in the project.",
    "Растр прежней съёмки того же участка. Он пересчитывается на сетку "
    "новой съёмки.":
        "The raster of the earlier survey of the same site. It is resampled "
        "to the grid of the new survey.",
    "Весь охват новой съёмки":
        "Whole extent of the new survey",
    "Многоугольники участка, например контур карьера и отвалов. Вне них "
    "разность не считается.":
        "Polygons of the site, for example the outline of the quarry and "
        "dumps. Outside them the difference is not computed.",
    "Разность меньше порога по модулю не входит в объёмы - это шум съёмки. "
    "Порог больше погрешности съёмок занижает объёмы.":
        "A difference smaller than the threshold in absolute value does not "
        "enter the volumes, it is survey noise. A threshold larger than the "
        "survey error underestimates the volumes.",
    "Прежняя съёмка":
        "Earlier survey",
    "Участок":
        "Site",
    "Порог":
        "Threshold",
    "В проекте нет другого растра - прежней съёмки.":
        "The project has no other raster for the earlier survey.",
    "PlanetX - выемка и насыпь":
        "PlanetX - cut and fill",
    "{new} - {old}, разность":
        "{new} - {old}, difference",
    "Разность съёмок не посчитана. Ошибка - {error}.":
        "The survey difference is not computed. Error - {error}.",
    "Растр - новая съёмка рельефа, например карьера с отвалами. Разность "
    "с прежней съёмкой даёт объёмы выемки и насыпи и растр разности "
    "в проекте.":
        "The raster is a new terrain survey, for example of a quarry with "
        "dumps. The difference with the earlier survey gives the cut and "
        "fill volumes and a difference raster in the project.",
    "Ошибки SSL запроса PlanetX {address}:":
        "SSL errors of the PlanetX request {address}:",
    "уровень воды {level}":
        "water level {level}",
    "Нет - только тайлы высот":
        "No - height tiles only",
    "Copernicus DEM 30 м - с лесом и домами":
        "Copernicus DEM 30 m - with forest and buildings",
    "GEDTM30 30 м - земля без леса и домов":
        "GEDTM30 30 m - bare ground without forest and buildings",
    "Рельеф - откуда берутся высоты":
        "Terrain - where the heights come from",
    "Высоты складываются из четырёх слоёв. Тайлы высот покрывают весь мир "
    "и дно морей. Модель 30 м уточняет сушу вблизи, сетка GEBCO - дно морей. "
    "Свой растр проекта заменяет всё в своём охвате.":
        "The heights are built from four layers. The height tiles cover the "
        "whole world and the sea floor. The 30 m model refines the land up "
        "close, the GEBCO grid refines the sea floor. An own raster of the "
        "project replaces everything within its extent.",
    "Тайлы высот - дно до уровня 10":
        "Height tiles - sea floor up to level 10",
    "GEBCO 2026 - сетка около 450 м":
        "GEBCO 2026 - a grid of about 450 m",
    "Глубины морей 450 м с уровня 5":
        "Sea depths of 450 m from level 5",
    "Глубины морей":
        "Sea depths",
    "Откуда берётся дно морей и океанов. В тайлах высот подробное дно есть "
    "до уровня 10, ближе в открытом море бывают пустые места на нуле. "
    "GEBCO 2026 - сетка глубин мира около 450 м, она заменяет дно тайлов, "
    "суша остаётся. Сетка читается из сети по участкам. Для навигации "
    "глубины не годятся.":
        "Where the floor of seas and oceans comes from. The height tiles hold "
        "a detailed floor up to level 10, closer up the open sea has empty "
        "spots at zero. GEBCO 2026 is a world depth grid of about 450 m, it "
        "replaces the floor of the tiles and the land stays. The grid is read "
        "from the network by areas. The depths are not fit for navigation.",
    "Тайлы высот по миру":
        "World height tiles",
    "Как записаны высоты":
        "Height encoding",
    "Подпись тайлов":
        "Tiles credit",
    "Уточнение суши 30 м":
        "30 m land refinement",
    "Свой растр высот, например съёмку карьера, включает пункт «Рельеф "
    "глобуса» меню растра в разделе «Слои проекта». Растр глубин озера - "
    "пункт «Батиметрия водоёма…» того же меню.":
        "An own height raster, for example a quarry survey, is switched on by "
        "the Globe terrain item of the raster menu in the Project layers "
        "section. A lake depth raster - the Water body bathymetry… item of "
        "the same menu.",
    "Адрес-шаблон тайлов высот с {z}, {x}, {y}, например свой сервер или "
    "MapTiler. Пустое поле - тайлы Mapzen по умолчанию. Глобус просит тайлы "
    "до уровня 15, глубже берёт их предков.":
        "An address template of height tiles with {z}, {x}, {y}, for example "
        "an own server or MapTiler. An empty field means the default Mapzen "
        "tiles. The globe requests tiles up to level 15 and takes their "
        "ancestors deeper.",
    "Рудники и заводы мира, USGS mineral operations":
        "World mines and plants, USGS mineral operations",
    "Оператор":
        "Operator",
    "Мощность (год сведений)":
        "Capacity (year of data)",
    "примерное, по району":
        "approximate, by district",
    "Рудник или завод мира":
        "World mine or plant",
    "Размер точки, цвет - группа:":
        "Point size, the colour is the group:",
    "Шахта или рудник":
        "Mine",
    "Ствол шахты":
        "Mine shaft",
    "Шахты и карьеры OSM":
        "OSM mines and quarries",
    "Закрыть свойства без записи правок, как кнопка «Отмена».":
        "Close the properties without saving the changes, like the "
        "Cancel button.",
    "Глобус":
        "Globe",
    "Готово":
        "Done",
    "Далее":
        "Next",
    "Закрыть":
        "Close",
    "Знакомство с модулем":
        "Getting to know the plugin",
    "Меню правой кнопки":
        "Right-click menu",
    "Назад":
        "Back",
    "Раздел «Слои»":
        "Layers section",
    "Строка «Поиск»":
        "Search field",
    "С нажатой левой кнопкой Земля поворачивается вслед за курсором. "
    "Колесо приближает к точке под курсором. Средняя кнопка или левая "
    "с Shift наклоняет и поворачивает вид. Двойной щелчок - перелёт "
    "к точке.":
        "The Earth follows the cursor while the left button is pressed. "
        "The wheel zooms "
        "to the point under the cursor. The middle button or the left "
        "one with Shift tilts and turns the view. A double click flies "
        "to the point.",
    "Здесь ищутся места, координаты и темы. Здесь же находятся "
    "возможности модуля - наберите «течения», «линейка» или «снимки» и "
    "выберите подсказку. Ctrl+K из любого места окна ставит курсор в эту "
    "строку.":
        "Places, coordinates and topics are searched here. The features "
        "of the plugin are found here too - type “currents”, “ruler” or "
        "“images” and choose a suggestion. Ctrl+K from anywhere in the "
        "window puts the cursor into this field.",
    "Правая кнопка на глобусе открывает меню точки - что здесь, "
    "космоснимки, исторические карты, маршрут, номенклатура листа, "
    "линейка и метка.":
        "The right button on the globe opens the menu of the point - "
        "what is here, satellite images, historical maps, a "
        "route, map sheet numbers, the ruler and a placemark.",
    "Значок открывает шкалу времени, когда у данных есть время - метки с "
    "датами, землетрясения, карты NASA, течения, исторические карты. "
    "Бегунок задаёт день, кнопки проигрывают время.":
        "The icon opens the time slider when the data have time - "
        "placemarks with dates, earthquakes, NASA maps, currents, "
        "historical maps. The handle sets the day, the buttons play the "
        "time.",
    "{name} - {what}":
        "{name} - {what}",
    "Вид в макет QGIS":
        "View to QGIS layout",
    "Записать облёт":
        "Record a flight",
    "Исторические карты Рамсея здесь":
        "Rumsey historical maps here",
    "Номенклатура листа здесь":
        "Map sheet numbers here",
    "Определить объекты":
        "Identify features",
    "Разговор с помощником":
        "Talk to the assistant",
    "Синхронизация с картой QGIS":
        "Sync with the QGIS map",
    "Космоснимки здесь": "Satellite images here",
    "Шкала времени":
        "Time slider",
    "включить":
        "turn on",
    "выключить":
        "turn off",
    "выполнить":
        "run",
    "закрыть":
        "close",
    "начать":
        "start",
    "остановить":
        "stop",
    "открыть каталог":
        "open the catalogue",
    "открыть демо":
        "open the demo",
    "открыть окно":
        "open the window",
    "перейти на тело":
        "go to the body",
    "показать карту":
        "show the map",
    "убрать карту":
        "remove the map",
    "Загрузка картинки «{title}»…":
        "Loading the image «{title}»…",
    "В проект добавлена картинка: {title}.":
        "Image added to the project: {title}.",
    "По всему каталогу":
        "Whole catalogue",
    "Искать по названию и году среди всех карт коллекции, а не только у "
    "вида. Кнопка «Показать на глобусе» перелетает к выбранной карте.":
        "Search by title and year among all maps of the collection, not "
        "only at the view. The Show on the globe button flies to the "
        "chosen map.",
    "Показать на глобусе":
        "Show on the globe",
    "Перелёт к рамке выбранной карты.":
        "Flight to the frame of the chosen map.",
    "Исторические карты Рамсея здесь…":
        "Rumsey historical maps here…",
    "Загрузка сведений о карте…":
        "Loading map details…",
    "Загрузка изображения карты…":
        "Loading the map image…",
    "Загрузка изображения карты: {done} из {total}":
        "Loading the map image: {done} of {total}",
    "Привязка карты…":
        "Georeferencing the map…",
    "Карта не собрана, подробности - в журнале работы.":
        "The map was not built, details are in the work log.",
    "Карты Рамсея":
        "Rumsey maps",
    "Год или название":
        "Year or title",
    "Карты коллекции Дэвида Рамсея, привязка - по его опорным точкам. "
    "Изображения - CC BY-NC-SA 3.0: только для некоммерческого "
    "использования, с указанием источника.":
        "Maps of the David Rumsey collection, georeferenced by its "
        "control points. The images are CC BY-NC-SA 3.0: non-commercial "
        "use only, with credit to the source.",
    "Карта собирается из изображения коллекции, привязывается и ложится "
    "в группу «Карты Рамсея» с годом карты. Год ставит карту на шкалу "
    "времени.":
        "The map is built from the collection image, georeferenced and "
        "put into the Rumsey maps group with the map year. The year "
        "places the map on the time slider.",
    "Страница карты":
        "Map page",
    "Страница карты на сайте коллекции в браузере.":
        "The map page on the collection site in the browser.",
    "Карт у вида: {count}, по годам. Щелчок по заголовку столбца "
    "меняет порядок.":
        "Maps at the view: {count}, by year. A click on a column "
        "header changes the order.",
    "Карта в проекте: {title}.":
        "Map in the project: {title}.",
    "Каталог карт Рамсея не загрузился, проверьте сеть.":
        "The Rumsey map catalogue did not load, check the network.",
    "Год":
        "Year",
    "Загрузка каталога карт…":
        "Loading the map catalogue…",
    "David Rumsey Map Collection, CC BY-NC-SA 3.0, некоммерческое "
    "использование":
        "David Rumsey Map Collection, CC BY-NC-SA 3.0, non-commercial use",
    "Течения не загрузились, проверьте сеть и включите строку снова.":
        "Currents did not load, check the network and turn the row on "
        "again.",
    "Течения, м/с":
        "Currents, m/s",
    "Геострофические, по спутниковой альтиметрии":
        "Geostrophic, from satellite altimetry",
    "Течения":
        "Currents",
    "Поверхностные течения океана белыми бегущими струйками над заливкой "
    "скорости. "
    "Геострофические течения NOAA CoastWatch по спутниковой альтиметрии "
    "за последние готовые сутки, сетка 0.5°. Первое включение за сеанс "
    "скачивает около 4 МБ.":
        "Ocean surface currents as white running streaks over a speed "
        "colouring. Geostrophic currents of NOAA CoastWatch from satellite "
        "altimetry for the latest ready day, 0.5° grid. The first "
        "switch-on in a session downloads about 4 MB.",
    "Осадки, влажность почвы, снег, лёд, пар, хлорофилл, солёность и "
    "наводнения по данным NASA, течения по данным NOAA.":
        "Precipitation, soil moisture, snow, ice, water vapor, "
        "chlorophyll, salinity and floods from NASA data, currents from "
        "NOAA data.",
    "Течения на {day}.":
        "Currents for {day}.",
    "Подводные кабели":
        "Submarine cables",
    "Подводные линии связи (бирюзовые) и силовые кабели (лиловые) из "
    "OpenStreetMap, видны с любой высоты. В OSM нанесена часть кабелей "
    "мира, больше всего в Атлантике и у Европы. Щелчок по линии "
    "показывает название, владельца и ссылку на объект OpenStreetMap.":
        "Submarine communication lines (turquoise) and power cables "
        "(purple) from OpenStreetMap, visible from any altitude. OSM "
        "holds part of the world's cables, most of them in the Atlantic "
        "and near Europe. A click on a line shows the name, owner and a "
        "link to the OpenStreetMap object.",
    "Подводные кабели не прочитаны.":
        "Submarine cables could not be read.",
    "PlanetX - слои глобуса":
        "PlanetX - globe layers",
    "Силовой кабель":
        "Power cable",
    "Линия связи":
        "Communication line",
    "ЛЭП, кабели и трубопроводы OSM":
        "OSM power lines, cables and pipelines",
    "Линии электропередачи по напряжению, подстанции, кабели и "
    "трубопроводы газа, нефти и воды из OpenStreetMap. Загружаются по "
    "месту вида, когда камера ниже 150 км. Щелчок по линии показывает "
    "напряжение, вещество, оператора и ссылку на объект OpenStreetMap.":
        "Power lines by voltage, substations, cables and gas, oil and "
        "water pipelines from OpenStreetMap. They load for the place in "
        "view when the camera is below 150 km. A click on a line shows "
        "the voltage, substance, operator and a link to the "
        "OpenStreetMap object.",
    "Непрозрачность слоя. Вправо слой непрозрачен, влево прозрачнее.":
        "Layer opacity. To the right the layer is opaque, to the left "
        "more transparent.",
    "Убрать с глобуса":
        "Remove from the globe",
    "Слой «{title}» не записан в «{path}».":
        "The layer «{title}» was not written to «{path}».",
    "В проект добавлено объектов {count}: {title}.":
        "{count} objects added to the project: {title}.",
    "подстанции":
        "substations",
    "Сервер OpenStreetMap не ответил, запрос повторится сам.":
        "The OpenStreetMap server did not answer, the request will repeat "
        "by itself.",
    "ЛЭП":
        "Power line",
    "Трубопровод":
        "Pipeline",
    "Подстанция":
        "Substation",
    "Класс":
        "Class",
    "Объект OSM":
        "OSM object",
    "Напряжение":
        "Voltage",
    "{value} кВ":
        "{value} kV",
    "Вещество":
        "Substance",
    "Прокладка":
        "Location",
    "Владелец":
        "Owner",
    "Уголь":
        "Coal",
    "Газ":
        "Gas",
    "Мазут":
        "Oil",
    "Атомные":
        "Nuclear",
    "ГЭС":
        "Hydro",
    "Биотопливо, отходы, геотермальные":
        "Biomass, waste, geothermal",
    "ЛЭП 500 кВ и выше":
        "Power line 500 kV and above",
    "ЛЭП 220-330 кВ":
        "Power line 220-330 kV",
    "ЛЭП 110-150 кВ":
        "Power line 110-150 kV",
    "ЛЭП ниже 110 кВ и без напряжения":
        "Power line below 110 kV or without voltage",
    "Газопровод":
        "Gas pipeline",
    "Нефте- и продуктопровод":
        "Oil or product pipeline",
    "Вода, тепло, стоки":
        "Water, heat, sewage",
    "Трубопровод, вещество не указано":
        "Pipeline, substance not given",
    "Электростанции WRI":
        "WRI power plants",
    "Размер точки - мощность":
        "Dot size - capacity",
    "Квадрат - подстанция":
        "Square - substation",
    "Электростанции":
        "Power plants",
    "Около 35 тысяч электростанций мира из базы WRI Global Power Plant "
    "Database, данные на 2021 год. Цвет - вид топлива, размер - "
    "мощность. Щелчок по точке показывает название, мощность, год ввода "
    "и владельца. У части станций место в базе указано неверно. Первое "
    "включение скачивает около 4 МБ.":
        "About 35 thousand power plants of the world from the WRI Global "
        "Power Plant Database, data as of 2021. Colour is the fuel, size "
        "is the capacity. A click on a dot shows the name, capacity, "
        "commissioning year and owner. Some plants are placed wrongly in "
        "the database. The first use downloads about 4 MB.",
    "Загрузка электростанций WRI, около 4 МБ…":
        "Loading WRI power plants, about 4 MB…",
    "Электростанций {count}.":
        "{count} power plants.",
    "Электростанции не загрузились, проверьте сеть и включите строку снова.":
        "Power plants did not load, check the network and turn the row "
        "on again.",
    "Электростанции не разобраны.":
        "Power plants could not be read.",
    "Мощность":
        "Capacity",
    "Топливо":
        "Fuel",
    "Год ввода":
        "Commissioning year",
    "Контуры горных разработок не загрузились, проверьте сеть и включите "
    "строку снова.":
        "Mining area outlines did not load, check the network and switch the "
        "row on again.",
    "Файл контуров горных разработок не читается: {path}":
        "The mining area outline file cannot be read: {path}",
    "{value} км²":
        "{value} km²",
    "Горная разработка":
        "Mining area",
    "Контуры горных разработок не записаны: {error}":
        "Mining area outlines are not written: {error}",
    "Объект OpenStreetMap":
        "OpenStreetMap object",
    "Горные разработки":
        "Mining areas",
    "Загрузка контуров горных разработок, около 25 МБ…":
        "Loading mining area outlines, about 25 MB…",
    "Геологическая и литологическая карты, разрез Земли "
    "и палеогеография.":
        "The geological and lithological maps, the Earth cutaway and "
        "palaeogeography.",
    "Землетрясения и плиты": "Earthquakes and plates",
    "Землетрясения за месяц и с 1904 года, границы плит, активные "
    "разломы, скорости плит и вулканы.":
        "Earthquakes of the past month and since 1904, plate boundaries, "
        "active faults, plate velocities and volcanoes.",
    "Геофизика": "Geophysics",
    "Магнитное поле, аномалии силы тяжести, геоид, возраст "
    "океанического дна и тепловой поток.":
        "The magnetic field, gravity anomalies, the geoid, the age of the "
        "ocean floor and heat flow.",
    "Месторождения USGS, горные разработки по снимкам, шахты "
    "и карьеры OpenStreetMap.":
        "USGS mineral deposits, mining areas mapped from imagery, mines "
        "and quarries from OpenStreetMap.",
    "Снимки у точки": "Imagery at a point",
    "Окна поиска снимков Sentinel-2, Landsat, MODIS, ASTER "
    "и облаков точек лидара у точки взгляда.":
        "Windows that search Sentinel-2, Landsat, MODIS and ASTER imagery "
        "and lidar point clouds at the look point.",
    "Исторические карты": "Historical maps",
    "Окна каталогов исторических карт у точки взгляда - "
    "коллекция Рамсея и сайт «Это Место».":
        "Windows of historical map catalogues at the look point - the "
        "Rumsey collection and the Eto Mesto site.",
    "Подоснова, векторная карта, прозрачные наложения карт "
    "и статьи Википедии.":
        "The base map, the vector map, transparent map overlays and "
        "Wikipedia articles.",
    "Земля сейчас": "Earth now",
    "Погода, снимки и карты NASA по дням - огонь, вода, воздух, "
    "жизнь, а также почвы.":
        "Weather, daily NASA imagery and maps of fire, water, air "
        "and life, and soils.",
    "Архив и съёмка": "Archive and surveys",
    "Прежние снимки, исторические карты, космоснимки и облака "
    "точек у точки взгляда.":
        "Past imagery, historical maps, satellite scenes and point "
        "clouds at the look point.",
    "Геология, землетрясения и плиты, геофизика и полезные "
    "ископаемые.":
        "Geology, earthquakes and plates, geophysics and mineral "
        "resources.",
    "Солнце, звёзды, облака, атмосфера и искусственные спутники.":
        "The Sun, stars, clouds, the atmosphere and artificial "
        "satellites.",
    "Энергетика и транспорт": "Energy and transport",
    "Электростанции, ЛЭП, трубопроводы, кабели, поезда, суда "
    "и самолёты.":
        "Power plants, power lines, pipelines, cables, trains, ships "
        "and aircraft.",
    "Окно поиска снимков Sentinel-2, Landsat 1-9, MODIS и ASTER "
    "участка у точки взгляда - облачность над участком, сочетания "
    "каналов и индексы слоями проекта, ряд по датам.":
        "A window that searches Sentinel-2, Landsat 1-9, MODIS and ASTER "
        "scenes of an area at the look point - cloud cover over the area, "
        "band composites and indices as project layers, a time series.",
    "Плитки облаков точек IGN LiDAR HD во Франции и USGS 3DEP "
    "в США у точки взгляда слоями проекта, точки на глобусе.":
        "Point cloud tiles of IGN LiDAR HD in France and USGS 3DEP in the "
        "USA at the look point as project layers, points on the globe.",
    "Карты коллекции Дэвида Рамсея у точки взгляда, привязанные "
    "по опорным точкам Стэнфорда, слоем проекта с годом карты.":
        "Maps of the David Rumsey collection at the look point, "
        "georeferenced by the Stanford control points, as a project layer "
        "with the map year.",
    "Каталог старых карт сайта etomesto.com у точки взгляда. Карта "
    "открывается страницей сайта в браузере.":
        "The catalogue of old maps of etomesto.com at the look point. "
        "A map opens as a site page in the browser.",
    "Окна у точки взгляда": "Windows at the look point",
    "окно у точки взгляда": "window at the look point",
    "Открыть окно": "Open the window",
    "Активные разломы":
        "Active faults",
    "Около 13.7 тысячи активных разломов мира по базе GEM Global Active "
    "Faults, сведённой из региональных каталогов. Цвет показывает вид "
    "смещения. Это сброс, взброс или надвиг, сдвиг, срединный хребет и "
    "складка. Щелчок по линии показывает название, вид смещения, скорость "
    "в мм/год, падение и каталог-источник. Первое включение скачивает около "
    "11 МБ.":
        "About 13.7 thousand active faults of the world from the GEM Global "
        "Active Faults database compiled from regional catalogues. The colour "
        "shows the kind of slip. It is a normal fault, a reverse fault or "
        "thrust, a strike-slip fault, a spreading ridge and a fold. A click "
        "on a line shows the name, the kind of slip, the slip rate in mm/yr, "
        "the dip and the source catalogue. The first switch-on downloads "
        "about 11 MB.",
    "Геологическая карта":
        "Geological map",
    "Геологическая карта мира Macrostrat, сведённая из карт разного "
    "масштаба. Цвет показывает возраст пород. В России и Европе самая "
    "подробная карта - 1:5 000 000, в США карты намного подробнее. Щелчок "
    "в режиме «Определить объекты» показывает подразделение, литологию, "
    "возраст в млн лет и карту-источник. На глобусе одна такая карта - "
    "геологическая или карта значений геофизики.":
        "The Macrostrat geological map of the world compiled from maps of "
        "different scales. The colour shows the age of the rocks. In Russia "
        "and Europe the most detailed map is 1:5 000 000, in the USA the maps "
        "are much more detailed. A click in the Identify features mode shows "
        "the unit, the lithology, the age in Ma and the source map. The "
        "globe shows one such map - the geological map or a geophysical "
        "value map.",
    "Сбросы":
        "Normal faults",
    "Взбросы, надвиги, субдукция":
        "Reverse faults, thrusts, subduction",
    "Сдвиги":
        "Strike-slip faults",
    "Срединные хребты":
        "Spreading ridges",
    "Складки":
        "Folds",
    "Вид смещения не указан":
        "Kind of slip not given",
    "Активные разломы GEM":
        "GEM active faults",
    "Оформление":
        "Appearance",
    "Время и видимость":
        "Time and visibility",
    "Активные разломы, около 11 МБ":
        "Active faults, about 11 MB",
    "Щелчок по линии - сведения":
        "A click on a line - details",
    "Загрузка активных разломов GEM, около 11 МБ…":
        "Loading the GEM active faults, about 11 MB…",
    "Разломов {count}.":
        "Faults: {count}.",
    "Разломы не загрузились, проверьте сеть и включите строку снова.":
        "The faults did not load, check the network and switch the row on "
        "again.",
    "Разломы не разобраны.":
        "The faults could not be read.",
    "Вид смещения":
        "Kind of slip",
    "Запись в базе":
        "Database entry",
    "Скорость смещения":
        "Slip rate",
    "Падение":
        "Dip",
    "Каталог":
        "Catalogue",
    "Запрос к Macrostrat…":
        "Asking Macrostrat…",
    "Копия вида в буфер обмена":
        "Copy the view to the clipboard",
    ("Копия вида в буфер обмена - глобус со шкалами, подписями и надписями, "
     "без панели значков, органов навигации, шкалы времени и панели тура. "
     "Картинку можно сразу вставить в письмо, чат или документ."):
        ("A copy of the view on the clipboard - the globe with the scales, "
         "credits and labels, without the icon bar, the navigation "
         "controls, the time slider and the tour bar. The picture can be "
         "pasted into a letter, a chat or a document at once."),
    "Вид скопирован в буфер обмена.":
        "The view is copied to the clipboard.",
    "Исторических очагов ISC-GEM {count}.":
        "Historical ISC-GEM foci {count}.",
    "Архив снимков с 2014 года":
        "Imagery archive since 2014",
    "Архив снимков":
        "Imagery archive",
    ("Прежние выпуски спутниковой подложки Esri World Imagery с 2014 года "
     "и снимки чрезвычайных событий Vantor и Planet."):
        ("Past releases of the Esri World Imagery basemap since 2014 and "
         "disaster imagery from Vantor and Planet."),
    "Снимки событий":
        "Disaster imagery",
    ("Откуда берутся 3D-здания. Векторная основа - здания OpenStreetMap в "
     "её тайлах. Overture Maps - здания OpenStreetMap, открытые наборы "
     "Microsoft, Esri и других одним архивом, их больше там, где "
     "OpenStreetMap неполон, например в Африке и Азии."):
        ("Where the 3D buildings come from. Vector base - OpenStreetMap "
         "buildings in its tiles. Overture Maps - buildings of "
         "OpenStreetMap and open sets of Microsoft, Esri and others in one "
         "archive, there are more of them where OpenStreetMap is "
         "incomplete, for example in Africa and Asia."),
    "PlanetX - облака точек лидара":
        "PlanetX - lidar point clouds",
    "Облака точек лидара ищутся в каталогах IGN и USGS…":
        "Searching the IGN and USGS catalogues for lidar point clouds…",
    ("У точки нет облаков точек лидара IGN LiDAR HD (Франция) и USGS 3DEP "
     "(США). {error}"):
        ("There are no IGN LiDAR HD (France) or USGS 3DEP (USA) lidar point "
         "clouds at the point. {error}"),
    "Облаков точек лидара в проекте: {count}, {name}.":
        "Lidar point clouds in the project: {count}, {name}.",
    ("Облака точек лидара по сети открываются в QGIS 4. В QGIS 3 открытие "
     "облака по сети останавливает QGIS."):
        ("Lidar point clouds over the network open in QGIS 4. In QGIS 3 "
         "opening a cloud over the network stops QGIS."),
    "Карта тренда…":
        "Trend map…",
    ("Тренд величины в каждом пикселе участка по сценам ряда - наклон "
     "Тейла-Сена за год и значимость по тесту Манна-Кендалла, растром "
     "в проект QGIS. Пиксель без {count} чистых сцен тренда не получает. "
     "Ряд из сцен одного сезона даёт тренд между годами, ряд всех месяцев "
     "смешивает сезон и тренд."):
        ("The trend of the value in every pixel of the area over the "
         "scenes of the series - the Theil-Sen slope per year and the "
         "significance by the Mann-Kendall test, as a raster in the QGIS "
         "project. A pixel without {count} clear scenes gets no trend. A "
         "series of scenes of one season gives the trend between years, "
         "a series of all months mixes the season and the trend."),
    "Считается карта тренда по {count} сценам…":
        "Computing the trend map over {count} scenes…",
    ("Карта тренда в проекте: пикселей с трендом {total}, значимых "
     "(p < {p}) {share} %, медиана наклона {median} за год."):
        ("Trend map in the project: pixels with a trend {total}, "
         "significant (p < {p}) {share} %, median slope {median} per "
         "year."),
    "Тренд «{name}» {first} - {last}, за год":
        "Trend \"{name}\" {first} - {last}, per year",
    "PlanetX - карты тренда":
        "PlanetX - trend maps",
    "Облака точек лидара здесь":
        "Lidar point clouds here",
    "Все слои NASA GIBS":
        "All NASA GIBS layers",
    ("Весь каталог NASA GIBS - больше тысячи слоёв снимков и карт с рядом "
     "дат. Список приходит из каталога службы при первом показе категории "
     "или поиске, строка поиска находит слой по словам названия."):
        ("The whole NASA GIBS catalogue - more than a thousand imagery and "
         "map layers with date series. The list comes from the service "
         "catalogue on the first showing of the category or on a search, "
         "the search field finds a layer by the words of its title."),
    "снимки с {first} по {last}":
        "imagery from {first} to {last}",
    "без ряда дат":
        "without a date series",
    "Слой NASA GIBS {layer}, {when}, подробность до уровня {level}.":
        "NASA GIBS layer {layer}, {when}, detail up to level {level}.",
    "Каталог NASA GIBS не загрузился: {error}":
        "The NASA GIBS catalogue did not load: {error}",
    "Слои NASA GIBS - тоже одна карта на глобусе":
        "NASA GIBS layers - also one map on the globe",
    "3D-здания по выбору, архив PMTiles":
        "3D buildings by choice, PMTiles archive",
    ("Снимки землетрясений, наводнений, пожаров и ураганов из открытых "
     "каталогов Vantor и Planet. Окно выбирает событие, шкала времени - "
     "день снимков, шторка сравнивает снимки до и после. Лицензия CC BY-NC "
     "4.0."):
        ("Imagery of earthquakes, floods, wildfires and hurricanes from the "
         "open Vantor and Planet catalogs. The window selects an event, the "
         "time slider selects the imagery day, the swipe compares the "
         "imagery before and after. Licence CC BY-NC 4.0."),
    ("Снимки землетрясений, наводнений, пожаров и ураганов из открытых "
     "каталогов Vantor и Planet. Шкала времени выбирает день снимков, "
     "шторка сравнивает снимки до и после события. Лицензия снимков CC "
     "BY-NC 4.0 - только некоммерческое использование."):
        ("Imagery of earthquakes, floods, wildfires and hurricanes from the "
         "open Vantor and Planet catalogs. The time slider selects the "
         "imagery day, the swipe compares the imagery before and after the "
         "event. The imagery licence is CC BY-NC 4.0, non-commercial use "
         "only."),
    "Событие":
        "Event",
    "Дата":
        "Date",
    "PlanetX - снимки событий":
        "PlanetX - disaster imagery",
    "Снимков: {count}":
        "Images: {count}",
    "Загрузка списка событий…":
        "Loading the event list…",
    "Список событий не загрузился: {error}":
        "The event list did not load: {error}",
    "Событий: {count}":
        "Events: {count}",
    "Загрузка снимков события «{title}»…":
        "Loading the imagery of the event {title}…",
    "Загрузка снимков события: документов каталога {count}":
        "Loading the event imagery: catalog documents {count}",
    "У события нет снимков, которые глобус может показать. {error}":
        "The event has no imagery the globe can show. {error}",
    ("Снимков: {count}, дней съёмки: {days}. Шкала времени выбирает день, "
     "шторка сравнивает снимки до и после."):
        ("Images: {count}, capture days: {days}. The time slider selects "
         "the day, the swipe compares the imagery before and after."),
    "Esri Wayback":
        "Esri Wayback",
    ("Выпуски подложки Esri World Imagery с 20 февраля 2014 года. Шкала "
     "времени выбирает выпуск, шаги идут по выпускам, где снимок в середине "
     "вида менялся. «Что здесь?» называет дату съёмки, источник и "
     "разрешение снимка."):
        ("Releases of the Esri World Imagery basemap since 20 February 2014. "
         "The time slider selects a release, the steps go through the "
         "releases in which the image at the centre of the view changed. "
         "What's here? names the capture date, the provider and the "
         "resolution of the image."),
    "Выпуск {day}":
        "Release {day}",
    "Сведения":
        "Details",
    "Запрос к Esri…":
        "Asking Esri…",
    "Архив снимков Esri Wayback":
        "Esri Wayback imagery archive",
    "Нет сведений о снимке":
        "No details about the image",
    "Дата съёмки":
        "Capture date",
    "Съёмочная система":
        "Imaging system",
    "Разрешение, м":
        "Resolution, m",
    "Точность, м":
        "Accuracy, m",
    "Геология":
        "Geology",
    "Macrostrat не ответил":
        "Macrostrat did not answer",
    "Карта в точке пуста":
        "The map is empty at the point",
    "Литология":
        "Lithology",
    "Свита":
        "Formation",
    "Примечание":
        "Note",
    "Страница Macrostrat":
        "Macrostrat page",
    "Возраст":
        "Age",
    "Возраст, млн лет":
        "Age, Ma",
    "Ссылка на карту":
        "Map link",
    "В проект добавлен слой «{title}».":
        "Layer {title} added to the project.",
    "Слой «{title}» не добавлен.":
        "Layer {title} was not added.",
    "Контуры карьеров, отвалов, хвостохранилищ и промплощадок мира по "
    "снимкам Sentinel-2 2019 года - около 45 тысяч участков, Maus и "
    "соавторы, 2022. Щелчок по контуру показывает страну и площадь. Первое "
    "включение скачивает около 25 МБ.":
        "Outlines of open pits, waste dumps, tailings and industrial sites of "
        "the world from Sentinel-2 images of 2019 - about 45 thousand areas, "
        "Maus et al., 2022. A click on an outline shows the country and area. "
        "The first switch-on downloads about 25 MB.",
    "Шахты, рудники, стволы и карьеры из OpenStreetMap с названиями "
    "и ископаемым. Загружаются по месту вида, когда камера ниже 150 км. "
    "Цвет - группа ископаемого, как у месторождений. Щелчок по точке "
    "показывает название, оператора и ссылку на объект OpenStreetMap.":
        "Mines, shafts and quarries from OpenStreetMap with names and the "
        "commodity. They load for the place of the view when the camera is "
        "below 150 km. The colour is the commodity group, as for the "
        "deposits. A click on a point shows the name, operator and a link to "
        "the OpenStreetMap object.",
    "Батиметрия по промерам":
        "Bathymetry from soundings",
    "Батиметрия по промерам…":
        "Bathymetry from soundings…",
    "Точки слоя «{name}» - промеры глубин, например галсы эхолота. Из них "
    "строится растр глубин триангуляцией, он ложится в рельеф глобуса дном "
    "водоёма, над ним - вода на уровне водоёма.":
        "The points of the layer «{name}» are depth soundings, for example "
        "echo sounder tracks. A depth raster is built from them by "
        "triangulation, it goes into the globe terrain as the water body "
        "bed, water at the water body level is drawn above it.",
    "Точки слоя - промеры глубин эхолотом. Из них строится растр глубин, "
    "он ложится в рельеф глобуса дном водоёма, над ним - вода на уровне "
    "водоёма.":
        "The points of the layer are echo sounder depth soundings. A depth "
        "raster is built from them, it goes into the globe terrain as the "
        "water body bed, water at the water body level is drawn above it.",
    "Поле с глубиной или Z точки. Знак глубины не важен, берётся её модуль.":
        "The field with the depth or the Z of the point. The sign of the "
        "depth does not matter, its absolute value is taken.",
    "Размер ячейки растра глубин. По умолчанию - по количеству точек на "
    "площадь промеров. Мельче ячейка - подробнее дно и больше файл.":
        "The cell size of the depth raster. By default it follows the "
        "number of points per area of the soundings. A smaller cell gives "
        "a more detailed bed and a larger file.",
    "Ячейка дальше этого расстояния от ближайшего промера остаётся пустой. "
    "Так растр не заливает берег и заливы без промеров. Предел больше "
    "расстояния между галсами, иначе между ними остаются полосы.":
        "A cell farther than this distance from the nearest sounding stays "
        "empty. So the raster does not fill the shore and bays without "
        "soundings. The limit is larger than the distance between tracks, "
        "otherwise strips remain between them.",
    "Высота поверхности воды над уровнем моря в день промеров. Отметка дна "
    "- уровень воды минус глубина.":
        "The height of the water surface above sea level on the day of the "
        "soundings. The bed elevation is the water level minus the depth.",
    "Файл GeoTIFF растра глубин.":
        "The GeoTIFF file of the depth raster.",
    "Ячейка":
        "Cell",
    "Предел от промера":
        "Limit from sounding",
    "Файл":
        "File",
    "Растр глубин":
        "Depth raster",
    "Промеров {count}, глубина от {low:.1f} до {high:.1f} м.":
        "Soundings {count}, depth from {low:.1f} to {high:.1f} m.",
    "Z точки":
        "Point Z",
    "У слоя нет числовых полей и Z точек.":
        "The layer has no numeric fields and no point Z.",
    "Промеров с глубиной меньше трёх.":
        "Fewer than three soundings with a depth.",
    "PlanetX - батиметрия":
        "PlanetX - bathymetry",
    "{name} - глубины":
        "{name} - depths",
    "Растр глубин построен, ячеек {cells} по {cell:g} м.":
        "The depth raster is built, {cells} cells of {cell:g} m.",
    "Растр глубин не построен. Ошибка - {error}.":
        "The depth raster is not built. Error - {error}.",
    "Год карты…":
        "Map year…",
    "Шторка":
        "Swipe",
    "Слева":
        "Left",
    "Справа":
        "Right",
    "На обеих сторонах":
        "Both sides",
    "Слой виден только левее шторки. Правее - слои «Справа» и общие.":
        "The layer is shown only left of the swipe. Right of it are the "
        "Right layers and the shared ones.",
    "Слой виден только правее шторки.":
        "The layer is shown only right of the swipe.",
    "Слой виден по обе стороны шторки.":
        "The layer is shown on both sides of the swipe.",
    "⇆ Шторка слоёв":
        "⇆ Layer swipe",
    "Сравнение слоёв шторкой. Слои «Слева» видны левее шторки, «Справа» - "
    "правее, прочие - на обеих сторонах. Сторона слоя - подменю «Шторка» "
    "меню слоя, шторка тянется мышью.":
        "Compare layers with a swipe. Left layers are shown left of the "
        "swipe, Right layers right of it, the others on both sides. The "
        "side of a layer is set in the Swipe submenu of the layer menu, the "
        "swipe is dragged with the mouse.",
    "Общие слои":
        "Shared layers",
    "Год исторической карты - растра или тайлов. Карты одной группы слоёв "
    "сменяют друг друга на шкале времени - видна последняя карта не позже "
    "момента шкалы. Шаги ◂ ▸ шкалы идут по годам карт.":
        "The year of a historical map, a raster or tiles. Maps of one "
        "layer group replace each other on the time slider - the last "
        "map not later than the slider moment is shown. The ◂ ▸ steps "
        "of the slider go by the map years.",
    "Год карты":
        "Map year",
    "Год карты «{name}». Пустое поле - карта без года, год до н. э. - со "
    "знаком минус.":
        "Year of the map «{name}». An empty field is a map without a year, "
        "a year BC has a minus sign.",
    "Год - целое число, например 1890.":
        "The year is an integer, for example 1890.",
    "1890 или 1890/1910":
        "1890 or 1890/1910",
    "Время картинки, как в KML. Год или дата - момент, у исторической "
    "карты это год карты. Карты-моменты одной папки сменяют друг друга "
    "на шкале времени - видна последняя карта не позже момента шкалы. "
    "Два значения через косую черту - промежуток, картинка видна в нём. "
    "Пустое поле - картинка видна всегда.":
        "The time of the image, as in KML. A year or a date is a moment, "
        "for a historical map it is the map year. Moment maps of one folder "
        "replace each other on the time slider - the last map not later "
        "than the slider moment is shown. Two values with a slash are a "
        "span, the image is shown within it. An empty field shows the "
        "image always.",
    "Москва, исторические карты":
        "Moscow, historical maps",
    "3D-модели, Суздаль и Пермь":
        "3D models, Suzdal and Perm",
    "Ссылка на файл":
        "Link to a file",
    "Где лежат файлы модели. Ссылка - путь к файлу .dae, "
    ".gltf, .glb или .obj, модель читается из него и файлов "
    "рядом, правка в SketchUp или Blender видна на глобусе. "
    "В файле меток - копия всех файлов модели, она видна "
    "и без исходного файла.":
        "Where the model files are. A link is a path to a .dae, .gltf, "
        ".glb or .obj file, the model is read from it and the files "
        "next to it, an edit in SketchUp or Blender shows on the globe. "
        "In the places file is a copy of all model files, it shows "
        "without the source file too.",
    "Путь к файлу модели":
        "Path to the model file",
    "Путь к файлу модели .dae, .gltf, .glb или .obj. Картинки "
    "модели читаются из файлов рядом с ним.":
        "Path to a .dae, .gltf, .glb or .obj model file. The model "
        "images are read from the files next to it.",
    "Выбрать файл модели. В файле меток модель заменяется "
    "копией, у ссылки меняется путь. Место и масштаб "
    "остаются.":
        "Choose a model file. In the places file the model is replaced "
        "by a copy, a link gets a new path. The place and the scale "
        "stay.",
    "Файл модели":
        "Model file",
    "Файл модели по ссылке проверяется через этот промежуток, "
    "пока модель видна. Изменённый файл читается заново. "
    "Ноль - файл читается при показе. Промежуток короче "
    "{low} с поднимается до {low} с.":
        "A linked model file is checked at this interval while the "
        "model is visible. A changed file is read again. Zero means "
        "the file is read when shown. An interval shorter than {low} s "
        "is raised to {low} s.",
    "в файле меток":
        "in the places file",
    "файлов модели нет":
        "no model files",
    "Файлы моделей (*.dae *.gltf *.glb *.obj)":
        "Model files (*.dae *.gltf *.glb *.obj)",
    "Растянуть модель по стороне":
        "Stretch the model along the side",
    "Сдвинуть модель":
        "Move the model",
    "Повернуть модель":
        "Rotate the model",
    "Изменить масштаб от угла, с Shift - от середины":
        "Scale from the corner, with Shift from the centre",
    "План Москвы":
        "Plan of Moscow",
    "Москва, карта Шуберта":
        "Moscow, Schubert map",
    "Окрестности Москвы":
        "Moscow environs",
    "Генеральный план Москвы":
        "General plan of Moscow",
    "Благородные металлы":
        "Precious metals",
    "Цветные металлы":
        "Base metals",
    "Чёрные и легирующие металлы":
        "Iron and alloy metals",
    "Редкие металлы, литий, алюминий":
        "Rare metals, lithium, aluminum",
    "Уголь, уран, геотермальные":
        "Coal, uranium, geothermal",
    "Алмазы и самоцветы":
        "Diamonds and gems",
    "Нерудные и строительные":
        "Industrial and construction",
    "Прочие":
        "Other",
    "Месторождения USGS":
        "USGS mineral deposits",
    "Крупное месторождение мира":
        "Major deposit of the world",
    "Месторождения":
        "Mineral deposits",
    "Месторождения, рудники и проявления полезных ископаемых USGS - база "
    "MRDS, около 300 тысяч точек, больше всего в США, 3 тысячи крупных "
    "месторождений мира и 6.5 тысячи рудников и заводов мира с оператором и "
    "мощностью. Цвет - группа полезного ископаемого, большая точка - крупное "
    "месторождение, рудник или завод. Щелчок по точке показывает название, "
    "ископаемые, тип и ссылку на запись USGS. Первое включение скачивает "
    "около 25 МБ.":
        "Mineral deposits, mines and occurrences of USGS - the MRDS database, "
        "about 300 thousand points, most of them in the USA, 3 thousand major "
        "deposits of the world and 6.5 thousand mines and plants of the world "
        "with the operator and capacity. The colour is the commodity group, a "
        "large point is a major deposit, mine or plant. A click on a point "
        "shows the name, commodities, type and a link to the USGS record. The "
        "first switch-on downloads about 25 MB.",
    "Загрузка месторождений USGS, около 25 МБ…":
        "Loading USGS mineral deposits, about 25 MB…",
    "Месторождения не загрузились: {error}":
        "Mineral deposits did not load: {error}",
    "Месторождения не разобраны: {error}":
        "Mineral deposits were not parsed: {error}",
    "Полезные ископаемые":
        "Commodities",
    "Стадия или модель":
        "Status or model",
    "Страна":
        "Country",
    "Набор":
        "Dataset",
    "Крупные месторождения мира, USGS OFR 2005-1294":
        "Major mineral deposits of the world, USGS OFR 2005-1294",
    "Запись USGS":
        "USGS record",
    "Запрос ключа доступа к файлам…":
        "Requesting the file access key…",
    "Температура поверхности днём, °C":
        "Daytime surface temperature, °C",
    "Температура поверхности ночью, °C":
        "Nighttime surface temperature, °C",
    "EVI - растительность":
        "EVI - vegetation",
    "Снег, % пикселя":
        "Snow, % of pixel",
    "Снег и лёд за 8 суток":
        "Snow and ice over 8 days",
    "Гари, день года":
        "Burned areas, day of year",
    "MODIS - температура за сутки, 1 км":
        "MODIS - temperature per day, 1 km",
    "MODIS - температура за 8 суток, 1 км":
        "MODIS - temperature over 8 days, 1 km",
    "MODIS - NDVI и EVI за 16 суток, 250 м":
        "MODIS - NDVI and EVI over 16 days, 250 m",
    "MODIS - снег за сутки, 500 м":
        "MODIS - snow per day, 500 m",
    "MODIS - снег за 8 суток, 500 м":
        "MODIS - snow over 8 days, 500 m",
    "MODIS - гари по месяцам, 500 м":
        "MODIS - burned areas by month, 500 m",
    "MODIS Terra и Aqua версии 061 (NASA LP DAAC, снег - NSIDC), файлы и "
    "каталог Microsoft Planetary Computer. Слои несут подпись продукта "
    "и архива NASA.":
        "MODIS Terra and Aqua version 061 (NASA LP DAAC, snow - NSIDC), "
        "files and catalogue of Microsoft Planetary Computer. The layers "
        "carry the credit of the product and the NASA archive.",
    "Спутник": "Satellite",
    "Служба ключей Planetary Computer не ответила: {error}. Повторите "
    "поиск позже.":
        "The Planetary Computer key service did not answer: {error}. "
        "Repeat the search later.",
    "Непрозрачность выделенных меток, путей, многоугольников, картинок "
    "и содержимого папок. Влево - прозрачнее. Значение сохраняется "
    "в «Моих метках» и в KML.":
        "Opacity of the selected placemarks, paths, polygons, images and "
        "folder contents. To the left is more transparent. The value is "
        "kept in My Places and in KML.",
    "Стеки потоков C++ по дампу, имена функций приблизительные:":
        "C++ thread stacks from the dump, function names are approximate:",
    "Главный поток": "Main thread",
    "Потоков в ожидании без своих кадров": "Waiting threads without own "
        "frames",
    "Поток": "Thread",
    "Главный поток QGIS не отвечает {seconds} с, дамп процесса со стеками "
    "потоков - {path}":
        "The QGIS main thread does not respond for {seconds} s, the "
        "process dump with thread stacks is {path}",
    "Прошлый сеанс QGIS (процесс {pid}, начат {began}) завершился без "
    "выгрузки модуля - падение или снятие задачи.":
        "The previous QGIS session (process {pid}, started {began}) "
        "ended without unloading the plugin, a crash or a killed task.",
    "Стеки Python в момент падения:": "Python stacks at the crash:",
    "Файла стеков Python этого процесса нет или он пуст.":
        "The Python stack file of this process is missing or empty.",
    "Дамп Windows:": "Windows dump:",
    "{name} ({size} МБ)": "{name} ({size} MB)",
    "Поток {name}.": "Thread {name}.",
    "Память {memory} МБ, выделено {committed} МБ, объектов GDI {gdi}, "
    "USER {user}.":
        "Memory {memory} MB, committed {committed} MB, GDI objects "
        "{gdi}, USER {user}.",
    "Окно глобуса открыто.": "The globe window is open.",
    "Окно глобуса закрыто.": "The globe window is closed.",
    "Загрузка подложки: {done} из {total}":
        "Loading base map: {done} of {total}",
    "Подложка не загрузилась: {error}":
        "Base map failed to load: {error}",
    "Обзор с высоты {height}": "View from {height}",
    "Звёздное небо, поле зрения {fov}°": "Starry sky, field of view {fov}°",
    "Для глобуса нужен модуль Python {name}. В этой сборке QGIS его нет.":
        "The globe needs the Python module {name}. This QGIS build "
        "does not have it.",
    "Поиск": "Search",
    "{name} - метка": "{name} - placemark",
    "{name} - звезда": "{name} - star",
    "{name} - созвездие": "{name} - constellation",
    "{name} - прежний запрос": "{name} - earlier query",
    "Очистить историю поиска": "Clear search history",
    "История поиска очищена.": "The search history is cleared.",
    "Разговор…": "Conversation…",
    "Остановить": "Stop",
    "Помощник ждёт ответ модели.":
        "The assistant is waiting for the model answer.",
    "Идёт поиск места.": "The place search is running.",
    "Помощник создаёт метки, получено {count}.":
        "The assistant is making places, {count} received.",
    "Сервис не принял длинный ответ, запрос повторён с меньшим пределом "
    "длины.":
        "The service refused a long answer, the request is repeated with "
        "a smaller length limit.",
    "Ответ модели оборвался: {error}. Взяты метки, пришедшие целиком.":
        "The model answer broke off: {error}. The places received whole "
        "are taken.",
    "Создание меток остановлено. Взяты метки, пришедшие целиком.":
        "Making places is stopped. The places received whole are taken.",
    "Ответ модели упёрся в предел длины. Взяты метки, пришедшие целиком.":
        "The model answer hit the length limit. The places received whole "
        "are taken.",
    "Очистить «Мои метки»…": "Clear My Places…",
    "Очистить «Мои метки»": "Clear My Places",
    "Удалить все метки и папки «Моих меток», всего меток {count}? "
    "Отменить удаление нельзя.":
        "Remove all placemarks and folders of My Places, placemarks "
        "{count} in all? The removal cannot be undone.",
    "Создать метки": "Make places",
    "Метки, пути и многоугольники по описанию в поле, например "
    "«путешествие Колумба». Модель отвечает одним документом KML, он "
    "сразу записывается новой папкой в «Мои метки».":
        "Placemarks, paths and polygons from the description in the field, "
        "for example \"the voyage of Columbus\". The model answers with "
        "one KML document, it is written to My Places as a new folder at "
        "once.",
    "Модель не вернула документ KML.":
        "The model returned no KML document.",
    "Метки созданы документом KML.":
        "The places are made as a KML document.",
    "Опишите в строке «Поиск», какие метки создать.":
        "Describe in the Search field which places to make.",
    "KML модели не разобран: {error}":
        "The KML of the model is not read: {error}",
    "Создана папка «{name}», меток {count}, со временем {timed}.":
        "The folder {name} is made, placemarks {count}, with time "
        "{timed}.",
    "Созданные метки удалены.": "The made places are removed.",
    "Настройки помощника": "Assistant settings",
    "Настройки…": "Settings…",
    "Сервис, модель и ключ API помощника.":
        "Service, model and API key of the assistant.",
    "Здесь идёт разговор: ваши вопросы, действия помощника на глобусе и "
    "его ответы. Вопрос задаётся в поле ниже или в строке «Поиск» панели.":
        "The conversation goes here: your questions, the assistant's "
        "actions on the globe and its answers. A question is asked in the "
        "field below or in the Search field of the panel.",
    "Сервис: {service}, модель {model}.":
        "Service: {service}, model {model}.",
    "Ключа API нет.": "There is no API key.",
    "Нет ключа API. Его вводят в окне «Настройки помощника».":
        "No API key. It is entered in the Assistant settings window.",
    "ключ не нужен": "no key needed",
    "Сервис на этом компьютере не отвечает. Проверьте, что он запущен, "
    "например Ollama, и что адрес в настройках помощника верный.":
        "The service on this computer does not answer. Check that it is "
        "running, for example Ollama, and that the address in the assistant "
        "settings is right.",
    "Хранить ключ без мастер-пароля":
        "Keep the key without the master password",
    "Ключ сохраняется открытым текстом в настройках профиля QGIS, "
    "мастер-пароль менеджера паролей не спрашивается. Ключ прочитает "
    "любой, у кого есть доступ к папке профиля. Флажок действует на "
    "следующее сохранение ключа.":
        "The key is saved as plain text in the QGIS profile settings, the "
        "password manager does not ask for the master password. Anyone "
        "with access to the profile folder can read the key. The check box "
        "applies to the next key save.",
    "Ключ сохранён в настройках профиля QGIS без мастер-пароля.":
        "The key is saved in the QGIS profile settings without the master "
        "password.",
    "Отвечать на просьбы из строки «Поиск»":
        "Answer requests from the Search field",
    "Просьба словами в строке «Поиск» панели уходит помощнику, ответ "
    "появляется под строкой. Без флажка строка ищет только места "
    "и координаты.":
        "A request in words in the Search field of the panel goes to the "
        "assistant, the answer appears below the field. Without the check "
        "box the field finds only places and coordinates.",
    "Помощник думает…": "The assistant is thinking…",
    "Ключа API нет, просьба не отправлена. Ключ вводится в окне "
    "«Настройки помощника».":
        "There is no API key, the request is not sent. The key is entered "
        "in the Assistant settings window.",
    "Поиск: {text}": "Searching: {text}",
    "Поиск не удался: {error}": "Search failed: {error}",
    "Ничего не найдено: {text}": "Nothing found: {text}",
    "О модуле": "About",
    "Метки": "Places",
    "Свернуть или развернуть «Мои метки».": "Collapse or expand My Places.",
    "Основа": "Base map",
    "Картинки на поверхности в проект QGIS…":
        "Ground overlays to the QGIS project…",
    "Картинку в проект QGIS…": "Image to the QGIS project…",
    "PlanetX - картинки": "PlanetX - images",
    "В папке нет картинок на поверхности.":
        "The folder has no ground overlays.",
    "Картинка в проект QGIS": "Image to the QGIS project",
    "GeoTIFF (*.tif)": "GeoTIFF (*.tif)",
    "В проект добавлено картинок {count}.":
        "Images added to the project: {count}.",
    "Папка для картинок": "Folder for the images",
    "Картинки по ссылкам загружаются, слои добавятся после загрузки.":
        "Linked images are loading, the layers will be added after "
        "loading.",
    "Картинка «{name}» не записана.": "The image “{name}” was not written.",
    "Растянуть от угла, с Shift - от середины":
        "Stretch from the corner, with Shift from the centre",
    "Растянуть сторону": "Stretch the side",
    "Сдвинуть картинку": "Move the image",
    "Повернуть картинку": "Rotate the image",
    "В файле меток": "In the places file",
    "Ссылка на файл или адрес": "Link to a file or address",
    "Где лежит картинка. В файле меток - копия внутри «Моих меток», она "
    "видна и без исходного файла. Ссылка - путь к файлу или адрес в сети, "
    "картинка читается при показе, правка файла видна на глобусе.":
        "Where the image lies. In the places file - a copy inside My "
        "Places, it is shown without the source file. Link - a file path "
        "or a web address, the image is read when shown, an edit of the "
        "file shows on the globe.",
    "Хранение": "Storage",
    "Спутники": "Satellites",
    "Космические станции": "Space stations",
    "Международная космическая станция, китайская станция «Тяньгун» "
    "и пристыкованные к ним корабли.":
        "The International Space Station, the Chinese Tiangong station "
        "and the spacecraft docked to them.",
    "Яркие спутники": "Bright satellites",
    "Около ста спутников и ступеней ракет, которые видны с Земли без "
    "бинокля.":
        "About a hundred satellites and rocket stages visible from the "
        "Earth without binoculars.",
    "Навигация": "Navigation",
    "Спутники GPS, ГЛОНАСС, Galileo и BeiDou на средних орбитах около "
    "20 000 км и геосинхронных.":
        "GPS, GLONASS, Galileo and BeiDou satellites on medium orbits "
        "of about 20 000 km and geosynchronous ones.",
    "Метеоспутники": "Weather satellites",
    "Метеорологические спутники на полярных и геостационарных орбитах.":
        "Weather satellites on polar and geostationary orbits.",
    "Наблюдение Земли": "Earth observation",
    "Спутники съёмки Земли, в том числе Landsat и Sentinel.":
        "Earth imaging satellites, Landsat and Sentinel among them.",
    "Научные": "Science",
    "Научные спутники и обсерватории на околоземных орбитах.":
        "Science satellites and observatories on Earth orbits.",
    "Геостационарные": "Geostationary",
    "Действующие спутники на геосинхронной орбите, около 36 000 км над "
    "экватором. Над Землёй они почти неподвижны.":
        "Active satellites on the geosynchronous orbit, about 36 000 km "
        "above the equator. They stay almost still over the Earth.",
    "Starlink": "Starlink",
    "Спутники связи SpaceX на высоте 340-570 км, их тысячи. Загрузка "
    "и первый расчёт идут дольше прочих групп.":
        "SpaceX communication satellites at 340-570 km, thousands of "
        "them. Loading and the first calculation take longer than for "
        "other groups.",
    "OneWeb": "OneWeb",
    "Спутники связи OneWeb на высоте около 1200 км.":
        "OneWeb communication satellites at about 1200 km.",
    "CelesTrak отказал в группе, новый запрос - через 2 часа после "
    "отказа.":
        "CelesTrak refused the group, a new request goes 2 hours after "
        "the refusal.",
    "Ответ без элементов орбит.": "The answer has no orbital elements.",
    "Номер NORAD": "NORAD number",
    "Группа": "Group",
    "{value} км/с": "{value} km/s",
    "Возраст элементов": "Elements age",
    "Орбита и след": "Orbit and ground track",
    "м/с":
        "m/s",
    "мм/ч":
        "mm/h",
    "Номенклатура листа":
        "Map sheet designation",
    "Горизонтали":
        "Contours",
    "Ошибка Python не PlanetX ({owner}):":
        "Python error not from PlanetX ({owner}):",
    "Copernicus Sentinel-2 L2A (ESA), файлы и каталог Earth Search Element "
    "84 на AWS. Слои несут подпись «Contains modified Copernicus Sentinel "
    "data» с годом снимка.":
        "Copernicus Sentinel-2 L2A (ESA), files and the Earth Search "
        "catalogue by Element 84 on AWS. Layers carry the Contains modified "
        "Copernicus Sentinel data notice with the image year.",
    "NBR - гари":
        "NBR - burned areas",
    "NDMI - влажность растительности":
        "NDMI - vegetation moisture",
    "NDSI - снег":
        "NDSI - snow",
    "NDVI - растительность":
        "NDVI - vegetation",
    "NDWI - открытая вода":
        "NDWI - open water",
    "{cloud} %, данных {valid} %":
        "{cloud} %, data {valid} %",
    "В проект добавлено слоёв {count}: {path}":
        "{count} layers added to the project, {path}",
    "Вся сцена по ссылке, без скачивания":
        "Whole scene by link, no download",
    "Геология (B12 B11 B2)":
        "Geology (B12 B11 B2)",
    "Дата, UTC":
        "Date, UTC",
    "Естественные цвета (B4 B3 B2)":
        "Natural colour (B4 B3 B2)",
    "Загрузка каналов сцены {when}…":
        "Loading the bands of scene {when}…",
    "Застройка (B12 B11 B4)":
        "Urban (B12 B11 B4)",
    "Каталог не ответил: {error}":
        "The catalogue did not answer, {error}",
    "Коротковолновый ИК (B12 B8A B4)":
        "Shortwave infrared (B12 B8A B4)",
    "Ложные цвета, ближний ИК (B8 B4 B3)":
        "False colour, near infrared (B8 B4 B3)",
    "Над участком":
        "Over the area",
    "Найдено сцен {count}, считается облачность над участком…":
        "{count} scenes found, counting the cloud cover over the area…",
    "Не отмечено ни одного продукта.":
        "No product is checked.",
    "Облака и тени - пусто":
        "Clouds and shadows empty",
    "Облачность сцены до":
        "Scene cloud cover up to",
    "Обрезка загружает только участок, значения - отражение, файлы годятся "
    "для расчётов. Ссылка показывает всю сцену Sentinel-2 из сети, данные "
    "загружаются при показе, индексы так не строятся. Исходные файлы - все "
    "каналы сцены, маска облаков и метаданные как есть, в папку сцены, "
    "и слой-набор всех каналов. Сцена Sentinel-2 весит около 1 ГБ.":
        "Clipping loads only the area, values are reflectance, the files "
        "suit calculations. A link shows the whole Sentinel-2 scene from "
        "the web, data load when shown, indices are not built this way. "
        "Source files are all scene bands, the cloud mask and the metadata "
        "as they are, in the scene folder, and a layer set of all bands. "
        "A Sentinel-2 scene weighs about 1 GB.",
    "Вся сцена, исходные файлы": "Whole scene, source files",
    "Кадастр Росреестра": "Rosreestr cadastre",
    "Старые карты «Это Место» здесь": "Eto Mesto old maps here",
    "Старые карты «Это Место» здесь…": "Eto Mesto old maps here…",
    "Старые карты «Это Место»": "Eto Mesto old maps",
    "Запрос к «Это Место»…": "Asking Eto Mesto…",
    "Карт у точки {total}, показано {shown}. Двойной щелчок открывает "
    "карту на сайте.":
        "Maps at the point {total}, shown {shown}. A double click opens "
        "the map on the site.",
    "Карты сайта «Это Место» (etomesto.com), которые накрывают точку. "
    "Карта открывается на сайте, там её можно наложить на современную "
    "и скачать по правилам сайта.":
        "Maps of the Eto Mesto site (etomesto.com) that cover the point. "
        "A map opens on the site, where it can be overlaid on a modern "
        "map and downloaded under the site rules.",
    "Оставляет карты, в названии или годе которых есть все слова.":
        "Keeps the maps whose title or year holds all the words.",
    "Открывает страницу выбранной карты на etomesto.com в браузере.":
        "Opens the page of the chosen map on etomesto.com in the browser.",
    "Открыть на сайте": "Open on the site",
    "Поиск по названию или году": "Search by title or year",
    "Сайт не ответил: {error}": "The site did not answer: {error}",
    "У этой точки карт на сайте нет.":
        "The site has no maps at this point.",
    "Геоид": "Geoid",
    "Геоид EGM2008": "EGM2008 geoid",
    "Высота геоида": "Geoid height",
    "Над": "Above",
    "эллипсоидом WGS84": "the WGS84 ellipsoid",
    "Форма уровенной поверхности Земли - геоида - по модели EGM2008 NGA. "
    "Пока строка включена, высоты глобуса - высоты геоида над "
    "эллипсоидом, от -107 до +86 м, растянутые в 10 000 раз, и Земля "
    "выглядит «измятой». Горбы - там, где сила тяжести больше, например "
    "у Новой Гвинеи, впадины - где меньше, самая глубокая - в Индийском "
    "океане. Рельеф и вода на это время убраны, выключение строки их "
    "возвращает.":
        "The shape of the Earth level surface - the geoid - after the NGA "
        "EGM2008 model. While the row is on, the globe heights are the "
        "geoid heights above the ellipsoid, from -107 to +86 m, stretched "
        "10 000 times, and the Earth looks crumpled. Bulges are where "
        "gravity is stronger, for example near New Guinea, hollows where "
        "it is weaker, the deepest one in the Indian Ocean. Terrain and "
        "water are removed for this time, switching the row off brings "
        "them back.",
    "Магнитная аномалия, нТл": "Magnetic anomaly, nT",
    "Аномалии магнитного поля Земли по сетке EMAG2v3 NOAA NCEI - "
    "отклонение поля от нормального на высоте 4 км над эллипсоидом, шаг "
    "около 4 км. Красные - поле сильнее, синие - слабее. Аномалии выдают "
    "строение коры - хребты и полосы океанского дна, древние щиты, рудные "
    "районы. Пустые места - там съёмки нет. Щелчок в режиме «Определить "
    "объекты» показывает значение в нТл.":
        "Anomalies of the Earth magnetic field after the NOAA NCEI EMAG2v3 "
        "grid - the departure of the field from the normal one at 4 km "
        "above the ellipsoid, a step of about 4 km. Red means a stronger "
        "field, blue a weaker one. The anomalies reveal the crust - "
        "ridges and stripes of the ocean floor, ancient shields, ore "
        "districts. Empty places have no survey. A click in the Identify "
        "features mode shows the value in nT.",
    "Магнитные аномалии": "Magnetic anomalies",
    "4 км над эллипсоидом": "4 km above the ellipsoid",
    "Аномалия поля": "Field anomaly",
    "Высота сетки": "Grid height",
    "Магнитная аномалия": "Magnetic anomaly",
    "загрузка…": "loading…",
    "нет данных": "no data",
    "тайл не прочитан": "the tile was not read",
    "Магнитные полюса": "Magnetic poles",
    "Северный и южный магнитные полюса - точки, где стрелка компаса стоит "
    "отвесно, - на год шкалы времени и их путь с 1590 года по данным NOAA "
    "NCEI. Шкала открывается сама, бегунок ведёт полюса по годам. Щелчок "
    "по глобусу в режиме «Определить объекты» показывает склонение, "
    "наклонение и напряжённость поля в точке на тот же год по моделям "
    "gufm1 и IGRF-14, с 1590 по 2030 год.":
        "The north and south magnetic poles - the points where a compass "
        "needle stands vertical - for the year of the time slider and "
        "their path since 1590 after NOAA NCEI. The slider opens by "
        "itself, its handle moves the poles over the years. A click on "
        "the globe in the Identify features mode shows the declination, "
        "inclination and field intensity at the point for the same year "
        "after the gufm1 and IGRF-14 models, from 1590 to 2030.",
    "{value} нТл": "{value} nT",
    "Горизонтальная составляющая": "Horizontal component",
    "Магнитное поле": "Magnetic field",
    "Магнитные полюса не прочитаны.": "The magnetic poles were not read.",
    "Наклонение": "Inclination",
    "Поле в точке": "Field at the point",
    "Полная напряжённость": "Total intensity",
    "Северный магнитный полюс, {year}": "North magnetic pole, {year}",
    "Склонение": "Declination",
    "Южный магнитный полюс, {year}": "South magnetic pole, {year}",
    "Загрузка файлов демо с GitHub, {size} МБ…":
        "Downloading demo files from GitHub, {size} MB…",
    "Демо не загружено: {error}": "The demo was not downloaded: {error}",
    "размер файла {name} не совпал": "the size of {name} does not match",
    "Кадастровый номер": "Cadastral number",
    "Площадь уточнённая": "Surveyed area",
    "Площадь декларированная": "Declared area",
    "Категория земель": "Land category",
    "Вид разрешённого использования": "Permitted use",
    "Форма собственности": "Form of ownership",
    "Вид права": "Type of right",
    "Кадастровая стоимость": "Cadastral value",
    "Удельная кадастровая стоимость": "Cadastral value per m²",
    "Дата определения стоимости": "Value determined on",
    "Дата применения стоимости": "Value applies from",
    "Дата постановки на учёт": "Registered on",
    "Статус": "Status",
    "Кадастровый квартал": "Cadastral block",
    "Запрос к НСПД…": "Asking NSPD…",
    "НСПД не ответила": "NSPD did not answer",
    "Ошибка": "Error",
    "Участков под точкой нет": "No parcels under the point",
    "Земельный участок {number}": "Land parcel {number}",
    "Карта НСПД": "NSPD map",
    "Двойной щелчок по строке копирует значение в буфер обмена, "
    "ссылку открывает в браузере.":
        "A double click on a row copies the value to the clipboard and "
        "opens a link in the browser.",
    "Земельные участки из Национальной системы пространственных данных "
    "Росреестра поверх снимка, только по России. Видны вблизи, с высоты "
    "около 10 км и ниже. Служба отвечает медленно и отказывает на частые "
    "запросы, поэтому участки приходят по одному тайлу.":
        "Land parcels from the National spatial data system of Rosreestr "
        "over the imagery, for Russia only. They are seen up close, from "
        "about 10 km and lower. The service answers slowly and refuses "
        "frequent requests, so the parcels come one tile at a time.",
    "Условия источника": "Source terms",
    "{name} - сервис, условия которого не разрешают брать его карты "
    "и снимки в сторонних программах по прямому адресу тайлов. Источник "
    "добавляется по вашему решению, ответственность за его использование "
    "несёте вы.<br><br>Условия сервиса: {terms}":
        "{name} is a service whose terms do not allow taking its maps and "
        "imagery into third-party programs by the direct tile address. "
        "The source is added by your decision, you bear the responsibility "
        "for its use.<br><br>Terms of the service: {terms}",
    "Подоснова": "Base maps",
    "Локальные данные": "Local data",
    "Подробные снимки и карты отдельных районов из служб "
    "их владельцев. Строка ставит подоснову, вне района "
    "на глобусе снимки Esri.":
        "Detailed imagery and maps of separate areas from the services of "
        "their owners. The row sets the base map, outside the area the "
        "globe shows Esri imagery.",
    "Подложки глобуса - снимки и карты. На глобусе одна подоснова, под "
    "картами и слоями.":
        "Base maps of the globe - imagery and maps. The globe has one base "
        "map, under the maps and layers.",
    "Подоснова на глобусе - одна": "Base map on the globe - one",
    "Подоснова на глобусе": "Base map on the globe",
    "Поставить подосновой": "Set as base map",
    "Подложка глобуса до уровня {level}. Подпись на глобусе - {credit}.":
        "Base map of the globe up to level {level}. The credit on the "
        "globe is {credit}.",
    "Наложения карт": "Map overlays",
    "Прозрачные карты поверх подложки - морские знаки, пешие "
    "и велосипедные маршруты. Включать можно несколько сразу.":
        "Transparent maps over the base map - sea marks, hiking and "
        "cycling routes. Several can be on at once.",
    "Морские знаки": "Sea marks",
    "Морские навигационные знаки OpenSeaMap - буи, маяки, створы, "
    "фарватеры и якорные стоянки. Знаки видны вблизи, с уровня карты "
    "около 1:500 000. Карта не заменяет навигационную.":
        "OpenSeaMap navigation marks - buoys, lighthouses, leading lines, "
        "fairways and anchorages. The marks are seen close up, from map "
        "scale about 1:500 000. The map does not replace a nautical "
        "chart.",
    "Пешие маршруты": "Hiking routes",
    "Размеченные пешие маршруты из OpenStreetMap по Waymarked Trails - "
    "международные, национальные, региональные и местные тропы цветом "
    "своего уровня.":
        "Waymarked hiking routes from OpenStreetMap by Waymarked Trails - "
        "international, national, regional and local trails in the colour "
        "of their level.",
    "Велосипедные маршруты": "Cycling routes",
    "Размеченные велосипедные маршруты из OpenStreetMap по Waymarked "
    "Trails - от международных веломаршрутов до местных.":
        "Waymarked cycling routes from OpenStreetMap by Waymarked Trails - "
        "from international cycle routes to local ones.",
    "Наложение «{title}» не открыто.":
        "The overlay \"{title}\" is not opened.",
    "Условия сервиса не разрешают брать тайлы по прямому адресу. Перед "
    "добавлением окно предупредит об этом.":
        "The service terms do not allow taking tiles by the direct address. "
        "The window warns about it before adding.",
    "Готовый источник меню «Основа»": "Ready source of the Base map menu",
    "Убрать «{name}» из списка подложек? Вернуть его можно категорией "
    "«Подоснова» каталога «Добавить данные».":
        "Remove «{name}» from the base map list? It can be brought back "
        "by the Base map category of the Add data catalogue.",
    "Ещё подосновы…": "More base maps…",
    "Росреестр": "Rosreestr",
    "НСПД Росреестра": "Rosreestr NSPD",
    "Кадастр - земельные участки": "Cadastre - land parcels",
    "подложкой": "as base map",
    "подложка": "base map",
    "Нет готового источника {key}.": "There is no ready source {key}.",
    "Подложка поставлена: {name}.": "Base map set: {name}.",
    "Пользователь отказался от подложки.":
        "The user declined the base map.",
    "Подложка помощника": "Assistant base map",
    "Адрес не годится: нужен шаблон http или https с {z}, {x} и {y} "
    "или {q}.":
        "The address does not fit: an http or https template with {z}, "
        "{x} and {y} or {q} is needed.",
    "Подложка от помощника": "Base map from the assistant",
    "Помощник предлагает подложку «{name}»:\n{url}\n\nУсловия "
    "использования сервиса проверяете вы. Добавить?":
        "The assistant proposes the base map «{name}»:\n{url}\n\nYou check "
        "the terms of use of the service. Add it?",
    "{name} (PlanetX)": "{name} (PlanetX)",
    "Скачивание файлов сцены {when}: {done} из {total}…":
        "Downloading scene files {when}: {done} of {total}…",
    "у этого спутника сцена целиком не загружается":
        "this satellite gives no whole scene",
    "участок за краем снимка сцены, в каналах нет данных. Каталог знает "
    "только рамку сцены, а полоса съёмки может не доходить до её углов.":
        "the area lies beyond the edge of the scene image, the bands hold "
        "no data. The catalogue knows only the scene frame, and the imaged "
        "strip may not reach its corners.",
    "Обрезка по участку, GeoTIFF":
        "Clip to the area, GeoTIFF",
    "Отмеченные продукты выбранной сцены - слоями проекта в группу дня "
    "внутри группы «Sentinel-2». Слои видны на карте и на глобусе.":
        "The checked products of the selected scene become project layers in "
        "a group of the day inside the Sentinel-2 group. The layers show on "
        "the map and on the globe.",
    "Папка снимков":
        "Image folder",
    "Папка файлов: {path}":
        "File folder, {path}",
    "Папка…":
        "Folder…",
    "Первый день съёмки в поиске.":
        "The first acquisition day searched.",
    "Поиск сцен…":
        "Searching scenes…",
    "Последний день съёмки в поиске.":
        "The last acquisition day searched.",
    "Сельское хозяйство (B11 B8 B2)":
        "Agriculture (B11 B8 B2)",
    "Снимок не загружен: {error}":
        "The image was not loaded, {error}",
    "Сочетания каналов - картинка из трёх каналов отражения, индексы - "
    "нормированная разность двух каналов со шкалой цветов. Каждый отмеченный "
    "продукт ложится своим слоем.":
        "Band combinations are a picture of three reflectance bands, indices "
        "are a normalized difference of two bands with a colour scale. Each "
        "checked product becomes its own layer.",
    "Ссылкой ложатся только сочетания каналов, индексы - обрезкой по "
    "участку.":
        "Only band combinations go by link, indices need clipping to the "
        "area.",
    "Сторона квадрата участка вокруг точки. При открытии окна она равна "
    "ширине видимой полосы глобуса. По участку считается облачность и "
    "обрезаются снимки. Больше участок - дольше загрузка каналов.":
        "The side of the square area around the point. When the window "
        "opens, it equals the width of the visible strip of the globe. The "
        "cloud cover is counted and images are clipped by the area. A larger "
        "area loads the bands longer.",
    "Сторона участка":
        "Area side",
    "Сцен {total}, над участком не облачнее {cloud} % - {count}.":
        "{total} scenes, {count} with at most {cloud} % clouds over the "
        "area.",
    "Сцена":
        "Scene",
    "Съёмка с":
        "Acquired from",
    "Тайл":
        "Tile",
    "Точка {lat}, {lon}":
        "Point {lat}, {lon}",
    "Участок: {name}":
        "Area, {name}",
    "над участком до":
        "over the area up to",
    "по":
        "to",
    "через {step} м, утолщённые через {index} м":
        "every {step} m, thicker every {index} m",
    "В проект QGIS…":
        "To the QGIS project…",
    "Сетевую ссылку…":
        "Network link…",
    "Загрузить заново":
        "Reload",
    "Сетевая ссылка":
        "Network link",
    "Папка «Моих меток» с содержимым документа KML или KMZ по адресу. "
    "Содержимое загружается заново через промежуток обновления, правки "
    "внутри папки при этом теряются.":
        "A My Places folder with the contents of a KML or KMZ document at an "
        "address. The contents are loaded again after the refresh interval, "
        "edits inside the folder are lost then.",
    "Название папки в «Моих метках».":
        "The folder name in My Places.",
    "Адрес документа KML или KMZ в сети (http, https) или путь файла на "
    "диске. Файл перечитывается, когда его меняет другая программа.":
        "The address of a KML or KMZ document on the web (http, https) or a "
        "file path on disk. The file is read again when another program "
        "changes it.",
    "Один раз":
        "Once",
    "Через сколько секунд документ загружается заново. Ноль - один раз за "
    "сеанс. Короче 10 с промежуток не бывает.":
        "After how many seconds the document is loaded again. Zero is once "
        "per session. The interval is never shorter than 10 s.",
    "Сетевая ссылка «{name}» не загружена: {error}":
        "The network link {name} was not loaded, {error}",
    "Тайл суперналожения не загружен: {error}":
        "A super-overlay tile was not loaded, {error}",
    "Суперналожение": "Super-overlay",
    "Высота облёта":
        "Fly-around height",
    "Камера облёта ближе к земле или дальше от неё во всех позах записи. "
    "Посередине - высота записи, края - вчетверо ниже и вчетверо выше. Точки "
    "пути тянутся мышью на глобусе, позы между ними следуют за ними.":
        "The fly-around camera is closer to the ground or farther from it in "
        "all recorded poses. The middle is the recorded height, the ends are "
        "four times lower and four times higher. Path points are dragged "
        "with the mouse on the globe, the poses between them follow.",
    "Выдавливание…":
        "Extrusion…",
    "Объекты слоя поднимаются над рельефом на высоту из числового поля: "
    "многоугольник - призмой, точка - столбиком, линия - стенкой. Цвет - "
    "стиль слоя.":
        "Layer features rise above the terrain to a height from a numeric "
        "field, a polygon as a prism, a point as a column, a line as a wall. "
        "The colour is the layer style.",
    "Выдавливание - {name}":
        "Extrusion - {name}",
    "Объекты слоя поднимаются над рельефом на высоту из поля: многоугольник "
    "- призмой, точка - столбиком, линия - стенкой. Цвет - стиль слоя.":
        "Layer features rise above the terrain to a height from a field, a "
        "polygon as a prism, a point as a column, a line as a wall. The "
        "colour is the layer style.",
    "Не выдавливать":
        "No extrusion",
    "Числовое поле высоты объекта. Объект с пустым, нулевым или "
    "отрицательным значением не выдавливается.":
        "The numeric field with the feature height. A feature with an empty, "
        "zero or negative value is not extruded.",
    "Высота из поля":
        "Height from field",
    "Высота в метрах - значение поля, умноженное на множитель. У поля этажей "
    "множитель около 3.":
        "The height in metres is the field value times the factor. For a "
        "field of storeys the factor is about 3.",
    "Множитель, м":
        "Factor, m",
    "Горизонтали вида в проект QGIS…":
        "View contours to the QGIS project…",
    "Изолинии в проект QGIS…":
        "Contours to the QGIS project…",
    "Изолинии значений растра с тем же шагом, что на гриде глобуса, - около "
    "12 линий на размах значений. Линии ложатся слоем GeoPackage в группу "
    "«PlanetX - горизонтали», каждая пятая толще и подписана.":
        "Contours of the raster values with the same interval as on the "
        "globe grid, about 12 lines over the range of values. The lines go "
        "to a GeoPackage layer in the PlanetX - contours group, every fifth "
        "one is thicker and labelled.",
    "PlanetX - горизонтали":
        "PlanetX - contours",
    "Горизонтали в проект выгружаются только на Земле.":
        "Contours go to the project only on the Earth.",
    "Горизонтали вида в проект QGIS":
        "View contours to the QGIS project",
    "Растр «{name}» не читается.":
        "The raster {name} cannot be read.",
    "У растра «{name}» нет перепада значений.":
        "The raster {name} has no range of values.",
    "Изолинии в проект QGIS":
        "Contours to the QGIS project",
    "Горизонтали не записаны в «{path}».":
        "The contours were not written to {path}.",
    "В проект добавлено горизонталей {count}, сечение {step} м.":
        "{count} contours added to the project, interval {step} m.",
    "Загружены не все высоты, часть горизонталей построена по менее "
    "подробным.":
        "Not all heights were loaded, some contours are built from less "
        "detailed ones.",
    "Линии равных высот рельефа, как на топографической карте. Сечение "
    "подбирается по масштабу вида - от сотен метров издалека до 5-10 м "
    "вблизи, каждая пятая горизонталь утолщённая и подписана отметкой. "
    "Ниже уровня моря - синие "
    "изобаты. Строятся по высотам глобуса и по своему рельефу растром "
    "проекта.":
        "Lines of equal terrain height, as on a topographic map. The "
        "interval follows the view scale - hundreds of metres from afar, "
        "5-10 m close up, every fifth contour is thicker and labelled with "
        "its height. Below sea level "
        "they are blue isobaths. They are built from the globe heights and "
        "from an own terrain raster of the project.",
    "Раскраска поверхности по уклону или по стороне света склона, включается "
    "одна из двух. Горизонтали рельефа поверх них.":
        "Colouring of the surface by slope or by the direction a slope "
        "faces, one of the two is on. Terrain contours lie over them.",
    "В проект QGIS":
        "To QGIS project",
    "Найти":
        "Find",
    "Маршрут не построен: сервис ответил «{error}», а по дорогам векторной "
    "основы маршрут строится до {limit} км по прямой.":
        "No route: the service answered '{error}', and over the roads of the "
        "vector base a route is built up to {limit} km in a straight line.",
    "Маршрут: запрос к сервису…":
        "Route: asking the service…",
    "На велосипеде":
        "By bike",
    "на велосипеде":
        "by bike",
    "Ошибка на карте":
        "Map error",
    "Сервис OSRM, данные © OpenStreetMap":
        "OSRM service, data © OpenStreetMap",
    "Сервис не ответил ({error}), маршрут по тайлам дорог":
        "The service did not answer ({error}), route over road tiles",
    "Точки дальше {limit} км по прямой. Без сервиса маршрут строится по "
    "дорогам района, для дальних поездок он не подходит. Сервис маршрутов "
    "включает окно «Источники данных».":
        "The points are more than {limit} km apart in a straight line. "
        "Without the service a route is built over the roads of the area, it "
        "does not suit long trips. The Data sources window turns the route "
        "service on.",
    "Адрес сервиса маршрутов OSRM с {mode} - профиль car, bike или foot - и "
    "{coords} - точки. Пустое поле - сервер FOSSGIS, к нему не больше "
    "запроса в секунду.":
        "Address of the OSRM route service with {mode} - the car, bike or "
        "foot profile - and {coords} - the points. An empty field is the "
        "FOSSGIS server, at most one request per second goes to it.",
    "Адрес сервиса маршрутов начинается с http или https и содержит "
    "{coords}.":
        "The route service address starts with http or https and contains "
        "{coords}.",
    "Маршруты":
        "Routes",
    "Маршруты на машине, велосипеде и пешком":
        "Routes by car, by bike and on foot",
    "С флажком маршрут меню на глобусе строит сервис OSRM - на любое "
    "расстояние за секунды, точки маршрута уходят на его сервер. Без флажка "
    "или когда сервис не ответил, маршрут строится по тайлам дорог векторной "
    "основы, до 50 км по прямой.":
        "With the box the OSRM service builds the route of the globe menu - "
        "at any distance within seconds, the route points go to its server. "
        "Without the box or when the service did not answer, the route is "
        "built over the road tiles of the vector base, up to 50 km in a "
        "straight line.",
    "Свой сервис":
        "Own service",
    "Строить маршрут через сервис":
        "Build routes with the service",
    "Записать облёт. Движение камеры мышью, клавишами или перелётами "
    "становится туром в «Моих метках», повторный щелчок останавливает "
    "запись. Видео тура пишет кнопка ⏺ панели тура.":
        "Record a flight. Camera movement by mouse, keys or flights becomes "
        "a tour in My Places, a second click stops the recording. The ⏺ "
        "button of the tour bar records a tour to video.",
    "Подземный режим…":
        "Subsurface mode…",
    "Окно «Подземный режим» - прозрачность земли над моделью, вырез блока, "
    "камера под землёй и шаблон данных. Скважины, кровли, гриды, разрезы и "
    "тоннели - слои проекта, их показывают флажки «Слоёв проекта».":
        "The Subsurface mode window - ground transparency above the model, "
        "the block cut, the camera under the ground and the data template. "
        "Drill holes, roofs, grids, sections and tunnels are project layers, "
        "the Project layers boxes show them.",
    "Окно «Подземный режим» - вырез блока, камера под землёй и шаблон "
    "данных.":
        "The Subsurface mode window - the block cut, the camera under the "
        "ground and the data template.",
    "Непрозрачность земли над подземной моделью - гридами по отметкам, "
    "кровлями, скважинами. Вправо земля непрозрачна, влево прозрачнее, у "
    "левого края её не видно. Вне контура данных земля не меняется.":
        "Opacity of the ground above the underground model - grids by "
        "elevations, bed tops, wells. To the right the ground is opaque, to "
        "the left more transparent, at the left edge it is not visible. "
        "Outside the data outline the ground does not change.",
    "Определить объекты. Щелчок по глобусу показывает координаты, высоту или "
    "глубину точки, кору под ней, объекты отмеченных слоёв проекта, метки, "
    "очаги землетрясений, спутники и подземную модель.":
        "Identify features. A click on the globe shows the coordinates, the "
        "elevation or depth of the point, the crust under it, the features "
        "of the checked project layers, placemarks, earthquakes, satellites "
        "and the underground model.",
    "Шкала времени. Она общая для меток, треков, слоёв проекта, "
    "землетрясений, пожаров, карт NASA, прогноза, Солнца и спутников. Пока "
    "шкала открыта, данные вне её промежутка скрыты. Закрытая шкала "
    "показывает все метки и события, карты - на последний день.":
        "Time slider. It is shared by placemarks, tracks, project layers, "
        "earthquakes, fires, NASA maps, the forecast, the Sun and "
        "satellites. While the slider is open, data outside its interval is "
        "hidden. A closed slider shows all placemarks and events, maps show "
        "the last day.",
    "Свойства вида: основа и источники данных, масштаб рельефа и глубины "
    "морей, язык подписей, связь с картой, обновление, формат координат, "
    "помощник.":
        "View properties: base map and data sources, terrain exaggeration "
        "and sea depths, label language, link with the map, update, "
        "coordinate format, assistant.",
    "Земля над гридами":
        "Ground above grids",
    "Поверхность по отметкам":
        "Surface by elevations",
    "Значения растра - абсолютные отметки, растр ложится поверхностью на "
    "свою высоту, под землёй или над ней. Цвет - стиль слоя QGIS. Флажок "
    "слоя показывает и скрывает поверхность, ползунок «Земля над гридами» "
    "раздела «Слои» делает землю над ней прозрачной.":
        "The raster values are absolute elevations, the raster lies as a "
        "surface at its height, under the ground or above it. The colour is "
        "the QGIS layer style. The layer box shows and hides the surface, "
        "the Ground above grids slider of the Layers section makes the "
        "ground above it transparent.",
    "Группы искусственных спутников CelesTrak. Щелчок по группе показывает "
    "её на глобусе или убирает.":
        "Groups of artificial satellites from CelesTrak. A click on a group "
        "shows it on the globe or removes it.",
    "Скрывать дальше":
        "Hide beyond",
    "не скрывать":
        "do not hide",
    "Метка видна, только пока глаз ближе этого расстояния, как Region в KML. "
    "У папки - все её метки. 0 - видна всегда.":
        "The placemark is visible only while the eye is closer than this "
        "distance, as Region in KML. For a folder - all its placemarks. 0 - "
        "always visible.",
    "Открыть в браузере":
        "Open in browser",
    "Добавить или изменить сайты…":
        "Add or edit sites…",
    "Сайты меню «Открыть в браузере»":
        "Sites of the Open in browser menu",
    "Добавить сайт":
        "Add site",
    "Свой адрес":
        "Own address",
    "Готовый сайт из списка или пустая строка для своего адреса.":
        "A ready site from the list or an empty row for your own address.",
    "Адрес начинается не с https:// или http://.":
        "The address does not start with https:// or http://.",
    "В адресе лишние фигурные скобки или места кроме {lat}, {lon} и {zoom}.":
        "The address has extra braces or places other than {lat}, {lon} and "
        "{zoom}.",
    "В адресе нет {lat} или {lon}.":
        "The address has no {lat} or {lon}.",
    "Каждая строка - пункт подменю «Открыть в браузере» меню на глобусе. "
    "Пункт открывает сайт на точке под курсором. «Добавить сайт» ставит "
    "готовый сайт или пустую строку для своего адреса. Двойной щелчок по "
    "ячейке меняет название или адрес. В адресе {{lat}} и {{lon}} - широта "
    "и долгота в градусах, {{zoom}} - масштаб карты по виду.":
        "Each row is an item of the Open in browser submenu of the globe "
        "menu. The item opens the site at the point under the cursor. Add "
        "site puts a ready site or an empty row for your own address. "
        "A double click on a cell changes the name or the address. In the "
        "address {{lat}} and {{lon}} are the latitude and longitude in "
        "degrees, {{zoom}} is the map scale by the view.",
    "Строка {n}: {reason}":
        "Row {n}: {reason}",
    "У пункта нет названия.":
        "The item has no name.",
    "Удалить выделенные строки.":
        "Delete the selected rows.",
    "Шторка сравнения. Левее шторки тема показана на другой день, правее - "
    "на день шкалы. Шторка тянется мышью, её день меняют кнопки ‹ и › над "
    "ней.":
        "Comparison swipe. Left of the swipe the theme is shown for another "
        "day, right of it for the day of the time slider. Drag the swipe "
        "with the mouse, the ‹ and › buttons above it change its day.",
    "Шторка сравнения: тянется мышью.":
        "Comparison swipe: drag it with the mouse.",
    "День левой части на шаг ряда темы назад.":
        "Left side day one step of the theme series back.",
    "День левой части на шаг ряда темы вперёд.":
        "Left side day one step of the theme series forward.",
    "Убрать шторку сравнения.":
        "Remove the comparison swipe.",
    "Искусственные спутники по орбитальным элементам CelesTrak, положение по "
    "модели SGP4. Время - правый бегунок шкалы времени, без шкалы - часы "
    "компьютера. Группы выбирает вкладка «Спутники» витрины. Элементы группы "
    "обновляются не чаще раза в 2 часа.":
        "Artificial satellites from CelesTrak orbital elements, positions by "
        "the SGP4 model. The time is the right handle of the time slider, "
        "without the slider the computer clock. The Satellites tab of the "
        "gallery chooses the groups. The elements of a group update at "
        "most once in 2 hours.",
    "Планета воздуха":
        "Planet of Air",
    "Все":
        "All",
    "Очаги пожаров за последние 24 часа по снимкам VIIRS спутника NOAA-20, "
    "сводка NASA FIRMS. Цвет и размер точки показывают мощность излучения.":
        "Fire spots of the last 24 hours from VIIRS images of the NOAA-20 "
        "satellite, the NASA FIRMS feed. The color and size of a dot show "
        "the radiative power.",
    "Температура поверхности":
        "Surface temperature",
    "Температура суши днём по MODIS за 8 суток и моря по GHRSST MUR за "
    "сутки, данные NASA GIBS.":
        "Daytime land temperature from MODIS over 8 days and sea temperature "
        "from GHRSST MUR for a day, NASA GIBS data.",
    "Карта":
        "Map",
    "Небо и свет":
        "Sky and light",
    "Недра":
        "Inside the Earth",
    "Анализ рельефа":
        "Terrain analysis",
    "Солнце и ночная сторона, звёзды, облака и искусственные спутники.":
        "The sun and the night side, stars, clouds and artificial "
        "satellites.",
    "Температура, осадки, ветер и облачность по модели NOAA GFS, "
    "температура поверхности по NASA и полярное сияние по NOAA SWPC. "
    "Прогноз GFS - до 16 суток вперёд, момент задаёт шкала времени.":
        "Temperature, precipitation, wind and clouds of the NOAA GFS model, "
        "surface temperature from NASA and the aurora from NOAA SWPC. The "
        "GFS forecast goes up to 16 days ahead, the time slider sets the "
        "moment.",
    "прогноз NOAA SWPC":
        "NOAA SWPC forecast",
    "Полярное сияние":
        "Aurora",
    "Вероятность видимого полярного сияния по модели OVATION службы NOAA "
    "SWPC на ближайшие 30-90 минут, сетка 1°. Прогноз один - на сейчас, "
    "шкала времени его не меняет. Огни городов на ночной стороне даёт "
    "строка «Солнце».":
        "The probability of a visible aurora by the OVATION model of NOAA "
        "SWPC for the next 30-90 minutes, 1° grid. There is one forecast, "
        "for now, the time slider does not change it. City lights on the "
        "night side come with the Sun row.",
    "Прогноз сияния не получен: {error}":
        "The aurora forecast was not received: {error}",
    "файл не прочитан":
        "the file was not read",
    "Очаги пожаров, дым, аэрозоль и угарный газ пожаров и промышленности по "
    "данным NASA.":
        "Fire spots, smoke, aerosol and carbon monoxide of fires and "
        "industry from NASA data.",
    "Диоксид азота, диоксид серы, метан, углекислый газ и озон по данным "
    "NASA.":
        "Nitrogen dioxide, sulfur dioxide, methane, carbon dioxide and ozone "
        "from NASA data.",
    "Растительность, пыль, ночные огни и типы покрова по данным NASA.":
        "Vegetation, dust, night lights and land cover types from NASA data.",
    "Мой круг":
        "My circle",
    "Первый щелчок по глобусу ставит центр круга, второй - точку окружности. "
    "Обе точки перетаскиваются мышью. Круг сохраняется многоугольником.":
        "The first click on the globe sets the centre of the circle, the "
        "second sets a point of the circle. Both points can be dragged with "
        "the mouse. The circle is saved as a polygon.",
    "Все номера в окне…":
        "All numbers in a window…",
    "Международная карта мира (IMW)":
        "International Map of the World (IMW)",
    "Российская номенклатура":
        "Russian sheet designation",
    "NATO, JOG":
        "NATO, JOG",
    "MGRS, квадрат 100 км":
        "MGRS, 100 km square",
    "Система":
        "System",
    "Масштаб":
        "Scale",
    "Номер листа":
        "Sheet number",
    "Щелчок по строке копирует номер листа в буфер обмена.":
        "A click on a row copies the sheet number to the clipboard.",
    "Щелчок по строке копирует номер листа. По российской номенклатуре "
    "нумеруются и листы Госгеолкарты-1000 и 200.":
        "A click on a row copies the sheet number. Sheets of the Russian "
        "State Geological Map at 1:1,000,000 and 1:200,000 use the Russian "
        "designation too.",
    "Ю. П.":
        "S. H.",
    "нет листа":
        "no sheet",
    "Скопировано: {number}":
        "Copied: {number}",
    "Погода":
        "Weather",
    "В файле прогноза нет поля «{name}».":
        "The forecast file has no {name} field.",
    "Ветер":
        "Wind",
    "Индекс прогноза не получен: {error}":
        "The forecast index was not received: {error}",
    "Интенсивность осадков в момент шкалы по модели NOAA GFS, мм/ч. Слабее "
    "0.1 мм/ч поле прозрачно.":
        "Precipitation rate at the slider moment from the NOAA GFS model, "
        "mm/h. Below 0.1 mm/h the field is transparent.",
    "Облачность, прогноз GFS":
        "Cloud cover, GFS forecast",
    "Осадки, прогноз GFS": "Precipitation, GFS forecast",
    "Осадки по спутникам IMERG": "Precipitation, IMERG satellites",
    "Общая облачность по модели NOAA GFS, доля неба в процентах. Это расчёт "
    "модели, а не снимок облаков.":
        "Total cloud cover from the NOAA GFS model, the share of the sky in "
        "percent. It is a model calculation, not a cloud image.",
    "Поле прогноза не получено: {error}":
        "The forecast field was not received: {error}",
    "Поле прогноза не прочитано.":
        "The forecast field was not read.",
    "Прогноз GFS не найден: {error}":
        "No GFS forecast found: {error}",
    "Скорость ветра на высоте 10 м по модели NOAA GFS, м/с.":
        "Wind speed at 10 m from the NOAA GFS model, m/s.",
    "Температура воздуха":
        "Air temperature",
    "Температура воздуха на высоте 2 м по модели NOAA GFS, шаг сетки 0.25°, "
    "около 28 км. Прогноз - до 16 суток вперёд, прошлое - анализ модели. "
    "Момент задаёт шкала времени.":
        "Air temperature at 2 m from the NOAA GFS model, a 0.25° grid of "
        "about 28 km. The forecast reaches 16 days ahead, the past is the "
        "model analysis. The time slider sets the moment.",
    "{name}, {units} · {time} UTC":
        "{name}, {units} · {time} UTC",
    "1920 × 1080 (Full HD)":
        "1920 × 1080 (Full HD)",
    "2560 × 1440":
        "2560 × 1440",
    "3840 × 2160 (4K)":
        "3840 × 2160 (4K)",
    "Видео MP4 в размере окна":
        "MP4 video at the window size",
    "Видео не дописано: {error}":
        "The video is not finished: {error}",
    "Видео не начато: {error}":
        "The video did not start: {error}",
    "Видео прервано: {error}":
        "The video stopped: {error}",
    "Видео сразу пишется только в Windows.":
        "A video is written directly only on Windows.",
    "Видео тура записано в {path}. Кадров {count}, {fps} в секунду.":
        "The tour video is written to {path}. {count} frames, {fps} per "
        "second.",
    "Готовый ролик H.264, 25 кадров в секунду. Кодирует Windows, сторонние "
    "программы не нужны. Каждый кадр ждёт загрузки, поэтому запись идёт "
    "дольше тура.":
        "A ready H.264 clip, 25 frames per second. Windows encodes it, no "
        "other programs are needed. Each frame waits for loading, so "
        "recording takes longer than the tour.",
    "Запись тура":
        "Tour recording",
    "Кадр видео не того формата.":
        "The video frame has a wrong format.",
    "Кадры PNG в папку":
        "PNG frames to a folder",
    "Кадры без потери качества в выбранном размере и файл frames.json с "
    "позами камеры. Из кадров ролик собирают программой монтажа или ffmpeg, "
    "см. руководство.":
        "Frames without quality loss at the chosen size and a frames.json "
        "file with camera poses. A clip is assembled from the frames by an "
        "editing program or ffmpeg, see the manual.",
    "Как окно":
        "As the window",
    "Размер кадров PNG. Кадр крупнее окна рисуется заново в этом размере, "
    "надписи и линии крупнее в той же доле.":
        "The size of PNG frames. A frame larger than the window is drawn "
        "anew at this size, labels and lines grow in the same proportion.",
    "Записать тур, 25 кадров в секунду тура: сразу видео MP4 в размере окна "
    "или кадры PNG в папку в выбранном размере. Каждый кадр ждёт загрузки "
    "тайлов, поэтому запись идёт дольше тура.":
        "Record the tour, 25 frames per second of the tour: an MP4 video at "
        "the window size right away or PNG frames to a folder at the chosen "
        "size. Each frame waits for tiles to load, so recording takes longer "
        "than the tour.",
    "Видео MP4 (*.mp4)":
        "MP4 video (*.mp4)",
    "Видео тура":
        "Tour video",
    "Измерить расстояние":
        "Measure distance",
    "Облететь вокруг":
        "Orbit around",
    "Подлететь сюда":
        "Fly here",
    "Проложить маршрут отсюда":
        "Directions from here",
    "Проложить маршрут сюда":
        "Directions to here",
    "Скопировать координаты в буфер обмена.":
        "Copy the coordinates to the clipboard.",
    "Что здесь?":
        "What's here?",
    "Конец маршрута поставлен. Начало - пункт «Проложить маршрут отсюда» "
    "меню на глобусе.":
        "The route end is set. The start is the Directions from here item of "
        "the globe menu.",
    "Начало маршрута поставлено. Конец - пункт «Проложить маршрут сюда» меню "
    "на глобусе.":
        "The route start is set. The end is the Directions to here item of "
        "the globe menu.",
    "не получен: {error}":
        "not received: {error}",
    "нет":
        "none",
    "на машине":
        "by car",
    "пешком":
        "on foot",
    "{value} мин":
        "{value} min",
    "{hours} ч {minutes} мин":
        "{hours} h {minutes} min",
    "Маршрут: адрес дорог векторной основы…":
        "Route: address of the vector base roads…",
    "Маршрут не построен: нет адреса тайлов векторной основы. {error}":
        "No route: the vector base has no tile address. {error}",
    "Маршрут не построен: коридор между точками - {count} тайлов дорог, "
    "предел {limit}.":
        "No route: the corridor between the points is {count} road tiles, "
        "the limit is {limit}.",
    "Маршрут: тайлы дорог {done} из {total}":
        "Route: road tiles {done} of {total}",
    "Маршрут: расчёт…":
        "Route: calculating…",
    "Маршрут не найден: точки не связаны дорогами векторной основы или "
    "дальше {reach} м от них.":
        "No route found: the points are not linked by the vector base roads "
        "or lie more than {reach} m from them.",
    "Маршрут":
        "Route",
    "{name}: {summary}":
        "{name}: {summary}",
    "точка":
        "point",
    "{a} - {b}, {km} км, {time} {mode}":
        "{a} - {b}, {km} km, {time} {mode}",
    "Пешком":
        "On foot",
    "На машине":
        "By car",
    "Сбросить":
        "Clear",
    "{value} сут": "{value} d",
    "Обновлять": "Refresh",
    "не обновлять": "no refresh",
    "Картинка по ссылке читается заново через этот промежуток, "
    "пока она видна. Так на глобусе стоит свежий снимок или "
    "карта, которую сервер или программа обновляет сама. Ноль - "
    "картинка читается при показе. Промежуток короче {low} с "
    "поднимается до {low} с.":
        "A linked image is read again after this interval while it is "
        "shown. The globe then keeps a fresh image or map that a server "
        "or a program updates by itself. Zero - the image is read when "
        "shown. An interval shorter than {low} s is raised to {low} s.",
    "Путь к файлу или адрес http(s)": "File path or http(s) address",
    "Путь к файлу картинки или её адрес в сети. Картинка читается заново "
    "при каждом показе.":
        "The path to the image file or its web address. The image is read "
        "again at each showing.",
    "Обзор…": "Browse…",
    "Выбрать файл картинки. В файле меток картинка заменяется копией, у "
    "ссылки меняется путь. Углы и положение остаются.":
        "Choose an image file. In the places file the image is replaced "
        "with a copy, a link gets the new path. The corners and position "
        "stay.",
    "Перевести в четыре угла": "Convert to four corners",
    "Каждый угол картинки тянется мышью отдельно, картинка может стать "
    "неправильным четырёхугольником, как gx:LatLonQuad в KML. Обратно в "
    "рамку она не переводится.":
        "Each corner of the image is dragged with the mouse on its own, "
        "the image can become an irregular quadrilateral, as gx:LatLonQuad "
        "in KML. It does not convert back to a box.",
    "Север": "North",
    "Юг": "South",
    "Восток": "East",
    "Запад": "West",
    "Поворот": "Rotation",
    "Крест в середине сдвигает картинку, ромб поворачивает, углы и "
    "середины сторон растягивают, с Shift - от середины.":
        "The cross in the middle moves the image, the diamond rotates it, "
        "the corners and the middles of the sides stretch it, with Shift "
        "from the centre.",
    "Поворот картинки вокруг середины против часовой стрелки.":
        "Rotation of the image about its centre counterclockwise.",
    "Край рамки картинки в градусах. Рамка задана сторонами света и "
    "поворотом, как LatLonBox в KML.":
        "An edge of the image box in degrees. The box is set by the "
        "cardinal sides and the rotation, as LatLonBox in KML.",
    "по ссылке {link}": "by link {link}",
    "ссылки нет": "no link",
    "Картинка по ссылке не загрузилась: {link}":
        "The linked image failed to load: {link}",
    "Путешествия Колумба": "Voyages of Columbus",
    "Место, координаты, тема или действие. Название места или "
    "координаты, например Пермь или 58.0105, 56.2294, дают "
    "перелёт. Слой, карта или окно модуля, например «течения», "
    "«линейка» или «снимки», находятся по названию и включаются "
    "из подсказки. Тема становится метками с датами, вопрос "
    "словами уходит помощнику. Ctrl+K из любого места окна ставит "
    "курсор в эту строку.":
        "A place, coordinates, a topic or an action. A place name or "
        "coordinates, for example Perm or 58.0105, 56.2294, fly there. "
        "A layer, map or window of the plugin, for example “currents”, "
        "“ruler” or “images”, is found by its name and turned on from "
        "the suggestion. A topic becomes placemarks with dates, a question "
        "in words goes to the assistant. Ctrl+K from anywhere in the "
        "window puts the cursor into this field.",
    "Найти то, что введено в строке. Место - перелёт к нему, несколько "
    "найденных мест - список ниже. Тема без места на карте - метки по ней "
    "от помощника, если в окне «Свойства вида» настроен помощник.":
        "Find what is typed in the field. A place - a flight to it, several "
        "places found - a list below. A topic without a place on the map - "
        "placemarks for it from the assistant, if the assistant is set up "
        "in the View properties window.",
    "Окно разговора с помощником. В нём вопросы словами, перелёты и метки "
    "KML по просьбе.":
        "The conversation window with the assistant. It takes questions in "
        "words, flights and KML placemarks on request.",
    "Сервис, модель и ключ API помощника. Без ключа тема в строке «Поиск» "
    "меток не создаёт.":
        "Service, model and API key of the assistant. Without a key a topic "
        "in the Search field makes no placemarks.",
    "Стереть прежние запросы строки «Поиск» из профиля QGIS.":
        "Erase the previous queries of the Search field from the QGIS "
        "profile.",
    "Промежуток времени меток и землетрясений. Бегунки тянутся по одному "
    "или вместе за середину, щелчок по полосе переносит промежуток. Тема "
    "NASA показана на день правого бегунка. Метки вне промежутка скрыты, "
    "метки без времени видны всегда.":
        "Time range of placemarks and earthquakes. The handles are dragged "
        "one by one or together by the middle, a click on the bar moves the "
        "range. A NASA theme is shown for the day of the right handle. "
        "Placemarks outside the range are hidden, placemarks without time "
        "are always shown.",
    "Момент времени темы NASA. Щелчок по полосе или протяжка бегунка "
    "ставят день, кнопки ‹ и › сдвигают его на шаг ряда темы.":
        "The moment of the NASA theme. A click on the bar or dragging the "
        "handle sets the day, the ‹ and › buttons move it by a step of the "
        "theme series.",
    "На шаг ряда темы назад.": "One step of the theme series back.",
    "На шаг ряда темы вперёд.": "One step of the theme series forward.",
    "{name} · {kind}": "{name} · {kind}",
    "Подлететь": "Fly to",
    "растр": "raster",
    "облако точек": "point cloud",
    "Облако точек": "Point cloud",
    "Цвет точек": "Point colour",
    "Размер точек": "Point size",
    "Классы точек": "Point classes",
    "Все классы": "All classes",
    "Только земля": "Ground only",
    "Класс 2 - точки поверхности земли.":
        "Class 2 - points of the ground surface.",
    "Цвет съёмки": "Survey colour",
    "Цвет RGB из файла облака. Если цвета в файле нет, точки окрашиваются "
    "по классу.":
        "The RGB colour from the cloud file. If the file has no colour, the "
        "points are coloured by class.",
    "По классу": "By class",
    "Классы ASPRS - земля, растительность, здания, вода и другие. Подписи - "
    "в шкале в углу вида.":
        "ASPRS classes - ground, vegetation, buildings, water and others. "
        "The names are in the legend in the corner of the view.",
    "По высоте": "By height",
    "От синего внизу облака к красному вверху.":
        "From blue at the bottom of the cloud to red at the top.",
    "По интенсивности": "By intensity",
    "Сила отражённого сигнала лидара оттенками серого.":
        "The strength of the returned lidar signal in shades of grey.",
    "{value} пикс.": "{value} px",
    "Класс {code}": "Class {code}",
    "Не классифицировано": "Never classified",
    "Без класса": "Unclassified",
    "Низкая растительность": "Low vegetation",
    "Средняя растительность": "Medium vegetation",
    "Высокая растительность": "High vegetation",
    "Здания": "Buildings",
    "Низкий шум": "Low noise",
    "Ключевые точки": "Model key points",
    "Дорожное покрытие": "Road surface",
    "Перекрытие": "Overlap",
    "Провода, защита": "Wire guard",
    "Провода": "Wire conductor",
    "Опоры ЛЭП": "Transmission towers",
    "Провода, соединители": "Wire connectors",
    "Мосты": "Bridge deck",
    "Высокий шум": "High noise",
    "Широта, долгота": "Latitude, longitude",
    "Интенсивность": "Intensity",
    "Отражение": "Return",
    "{number} из {count}": "{number} of {count}",
    "Облако точек «{name}»": "Point cloud {name}",
    "Точка облака": "Cloud point",
    "Классы облака «{name}»": "Classes of the cloud {name}",
    "Щелчок - точка облака": "A click gives the cloud point",
    "Высоты облака «{name}»": "Heights of the cloud {name}",
    "Облако «{name}» не показано: в составе QGIS нет программы PDAL.":
        "The point cloud {name} is not shown, QGIS has no PDAL program.",
    "Облако «{name}» не прочитано: {error}":
        "The point cloud {name} was not read, {error}",
    "Облако «{name}» переводится в COPC, это делается один раз.":
        "The point cloud {name} is converted to COPC, this is done once.",
    "Облако «{name}» не переведено в COPC, подробности в журнале работы.":
        "The point cloud {name} was not converted to COPC, the details are "
        "in the work log.",
    "Облако «{name}» не открылось.":
        "The point cloud {name} did not open.",
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
    "и отдаляет, левая с Ctrl сдвигает вид вдоль экрана.":
        "A left double click zooms in to the point, a right double click "
        "zooms out. Dragging with the right button zooms in and out, the "
        "left button with Ctrl moves the view along the screen.",
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
    "Созвездия и имена звёзд: d3-celestial, © Olaf Frohn. Планеты: "
    "элементы орбит JPL.":
        "Constellations and star names: d3-celestial, © Olaf Frohn. "
        "Planets: JPL orbital elements.",
    "Марс: NASA, USGS, Viking MDIM2.1, тайлы OpenPlanetaryMap. Луна: "
    "NASA, GSFC, ASU, LRO LROC WAC, USGS.":
        "Mars: NASA, USGS, Viking MDIM2.1, OpenPlanetaryMap tiles. Moon: "
        "NASA, GSFC, ASU, LRO LROC WAC, USGS.",
    "Облака: NASA GIBS, снимки VIIRS.": "Clouds: NASA GIBS, VIIRS imagery.",
    "Звёзды: каталог ярких звёзд Йельского университета.":
        "Stars: the Yale Bright Star Catalogue.",
    "Координатная сетка, звёзды, облака, температура суши и моря, "
    "3D-здания, свет солнца.":
        "A coordinate grid, stars, clouds, land and sea temperature, "
        "3D buildings, sunlight.",
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
    "Атмосфера": "Atmosphere",
    "Во весь экран": "Full screen",
    "Во весь экран (F11) - вид глобуса для показа. Панели "
    "прячутся, органы навигации, шкала времени и тур "
    "остаются. Esc или F11 возвращает окно.":
        "Full screen (F11) - the globe view for a presentation. The "
        "panels hide, the navigation controls, the time slider and the "
        "tour stay. Esc or F11 brings the window back.",
    "Во весь экран. Выход - Esc или F11.":
        "Full screen. Esc or F11 to leave.",
    "Поток по пути": "Flow along the path",
    "Объёмом по отметкам Z": "Solid by Z elevations",
    "Вершины слоя стоят на своих отметках Z - многоугольники "
    "плоскостями, линии трубками, под землёй или над ней, "
    "например вертикальный забор разреза. Цвет - поле color "
    "или стиль слоя QGIS. Ползунок «Земля над гридами» "
    "делает землю над ними прозрачной.":
        "The vertices of the layer stand at their Z elevations - "
        "polygons as planes, lines as tubes, under the ground or above "
        "it, for example a vertical section fence. The colour is the "
        "color field or the QGIS layer style. The Ground above grids "
        "slider makes the ground above them transparent.",
    "Истинные отметки Z": "True Z elevations",
    "При выключенном рельефе вершины стоят на своих отметках "
    "над уровнем моря, например горизонтали поднимаются над "
    "плоской Землёй. Без флажка отметка считается от "
    "поверхности, как глубина скважин и пластов. С рельефом "
    "флажок ничего не меняет.":
        "With terrain off, the vertices stand at their elevations above "
        "sea level, for example contours rise above the flat Earth. "
        "Without the check box the elevation is counted from the "
        "surface, like the depth of drill holes and beds. With terrain "
        "on, the check box changes nothing.",
    "Подписи остановок на кадре. На остановке внизу кадра "
    "крупно стоят название и описание метки, в перелёте подписи "
    "нет. Подписи попадают и в запись тура.":
        "Stop captions on the frame. At a stop the name and the "
        "description of the placemark stand large at the bottom of the "
        "frame, during a flight there is no caption. The captions also "
        "go into the tour recording.",
    "По пути от первой точки к последней бегут короткие "
    "штрихи цвета линии, как поток грузов. Путь лежит на "
    "земле. Признак сохраняется в KML.":
        "Short dashes of the line colour run along the path from the "
        "first point to the last one, like a flow of goods. The path "
        "lies on the ground. The setting is kept in KML.",
    "Поток грузов, схема": "Flow of goods, a scheme",
    "Во сколько раз растянуты высоты геоида над эллипсоидом. "
    "Вправо горбы и впадины глубже, влево Земля круглее. Разрез "
    "Земли следует за поверхностью.":
        "How many times the geoid heights above the ellipsoid are "
        "stretched. To the right the bulges and hollows are deeper, to "
        "the left the Earth is rounder. The Earth cutaway follows the "
        "surface.",
    "Голубое свечение воздуха вокруг планеты, небо над "
    "горизонтом и дымка над далёкой поверхностью. Без флажка "
    "фон вида - чёрный космос, поверхность видна без дымки. "
    "У тел без воздуха строка ничего не меняет.":
        "The blue glow of air around the planet, the sky above the horizon "
        "and the haze over the distant surface. Without the check box the "
        "view background is black space and the surface shows without "
        "haze. On bodies without air the row changes nothing.",
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
    "Солнце": "Sun",
    "Земля": "Earth",
    "Метки и туры": "Placemarks and tours",
    "Снимки и карты": "Imagery and maps",
    "Суперналожение, Маунтин-Вью": "Super-overlay, Mountain View",
    "3D-модели и движение": "3D models and motion",
    "Самосвалы в карьерах": "Haul trucks in open pits",
    "Марс": "Mars",
    "Луна": "Moon",
    "Ио": "Io",
    "Европа": "Europa",
    "Ганимед": "Ganymede",
    "Каллисто": "Callisto",
    "Мимас": "Mimas",
    "Энцелад": "Enceladus",
    "Тефия": "Tethys",
    "Диона": "Dione",
    "Рея": "Rhea",
    "Титан": "Titan",
    "Япет": "Iapetus",
    "Церера": "Ceres",
    "Веста": "Vesta",
    "Планеты": "Planets",
    "Спутники Юпитера": "Moons of Jupiter",
    "Спутники Сатурна": "Moons of Saturn",
    "Астероиды": "Asteroids",
    "Тело глобуса - планета, спутник, карликовая планета или "
    "звёздное небо. У каждого тела свои снимки, у Марса и Луны ещё "
    "и рельеф. Земные слои, поиск и здания на других телах "
    "выключены. Небо показывает созвездия, звёзды и планеты из "
    "центра небесной сферы.":
        "The body of the globe - a planet, a moon, a dwarf planet or the "
        "starry sky. Each body has its own imagery, Mars and the Moon "
        "also have terrain. Earth layers, search and buildings are off "
        "on other bodies. The sky shows constellations, stars and planets "
        "from the centre of the celestial sphere.",
    "Небо": "Sky",
    "Демо: подготовленные сцены с метками и турами на Земле, Марсе, "
    "Луне и небе. Метки ложатся новой папкой в «Мои метки», кнопка ▶ "
    "под списком проводит тур.":
        "Demo: prepared scenes with places and tours on the Earth, Mars, the "
        "Moon and in the sky. The places go to My Places as a new folder, "
        "the ▶ button under the list plays the tour.",
    "Бока-Чика, Starbase": "Boca Chica, Starbase",
    "Японский жёлоб": "Japan Trench",
    "Создать метки по теме «{topic}»": "Make places on \"{topic}\"",
    "Найдены места с этим названием.": "Places with this name are found.",
    "Границы плит": "Plate boundaries",
    "Границы литосферных плит по модели PB2002. Красные - раздвиг плит "
    "на хребтах и рифтах, зелёные - сдвиг по трансформным разломам, синие "
    "- схождение в зонах субдукции и коллизии. Названия плит стоят "
    "надписями. Тип границы и скорость плит показывает окно «Объекты».":
        "Lithospheric plate boundaries after the PB2002 model. Red - plates "
        "moving apart at ridges and rifts, green - plates sliding along "
        "transform faults, blue - plates converging in subduction and "
        "collision zones. Plate names show as labels. The Features window "
        "shows the boundary type and the plate speed.",
    "Граница плит": "Plate boundary",
    "Раздвиг плит": "Plates moving apart",
    "Сдвиг плит": "Plates sliding",
    "Схождение плит": "Plates converging",
    "Океанический спрединговый хребет": "Oceanic spreading ridge",
    "Континентальный рифт": "Continental rift",
    "Океанический трансформный разлом": "Oceanic transform fault",
    "Континентальный трансформный разлом": "Continental transform fault",
    "Зона субдукции": "Subduction zone",
    "Океаническая граница схождения": "Oceanic convergent boundary",
    "Континентальная коллизия": "Continental collision",
    "Плиты": "Plates",
    "Скорость": "Speed",
    "{value} мм/год": "{value} mm/yr",
    "Границы плит не прочитаны: {error}":
        "The plate boundaries are not read: {error}",
    "Места посадок марсоходов": "Rover landing sites",
    "«Аполлоны» и «Луноходы»": "Apollo and Lunokhod sites",
    "Созвездия и яркие объекты": "Constellations and bright objects",
    "Созвездия": "Constellations",
    "Линии фигур и названия созвездий на небе. Без них остаются звёзды, "
    "их имена и светила.":
        "Constellation figures and names in the sky. Without them the "
        "stars, their names and the bodies remain.",
    "Меркурий": "Mercury",
    "Венера": "Venus",
    "Юпитер": "Jupiter",
    "Сатурн": "Saturn",
    "Уран": "Uranus",
    "Нептун": "Neptune",
    "Поиск по названию есть только у Земли. Координаты вводятся числами.":
        "Search by name is available for the Earth only. Coordinates are "
        "entered as numbers.",
    "Свет рельефа, зданий и воздуха по положению солнца. "
    "Ночная сторона Земли тёмная. Время солнца - конец "
    "промежутка открытой шкалы времени, без неё - часы "
    "компьютера. Без флажка свет падает с северо-запада, "
    "как на карте рельефа.":
        "Light of the terrain, buildings and air by the position of the "
        "sun. The night side of the Earth is dark. The sun time is the end "
        "of the interval of the open time slider, without it the computer "
        "clock. Without the check the light falls from the north-west, as "
        "on a relief map.",
    "Объёмные здания из OpenStreetMap по векторным "
    "тайлам OpenFreeMap. Они видны, когда камера ближе "
    "6 км к земле. Высота взята из OSM, иначе из "
    "этажности. Здание без этих сведений получает "
    "высоту 5 м.":
        "3D buildings from OpenStreetMap in OpenFreeMap vector tiles. "
        "They show when the camera is closer than 6 km to the ground. "
        "The height comes from OSM or from the number of floors. A "
        "building without either gets a height of 5 m.",
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
    "Линейка на эллипсоиде WGS84 и по рельефу, 3D-путь "
    "и 3D-многоугольник по зданиям, профиль высот, "
    "координаты в градусах, UTM и MGRS.":
        "A ruler on the WGS84 ellipsoid and along the terrain, a 3D "
        "path and a 3D polygon over buildings, the elevation profile, "
        "coordinates in degrees, UTM and MGRS.",
    "Значки меток, время меток со шкалой времени, подъём "
    "и выдавливание меток.":
        "Placemark icons, placemark time with a time slider, lifting "
        "and extruding places.",
    "Туры по меткам и вдоль путей, запись тура с экрана "
    "и кадрами PNG для видео, демо «Пермь».":
        "Tours over places and along paths, recording a tour from the "
        "screen and as PNG frames for a video, the Perm demo.",
    "Растущие треки и слои проекта по шкале времени глобуса.":
        "Growing tracks and project layers along the globe time slider.",
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
    "Джойстик в кольце поворачивает взгляд, точка в его середине "
    "возвращает отвесный взгляд без наклона и крена. Нижний "
    "джойстик сдвигает вид. "
    "Ползунок задаёт высоту, плюс и минус приближают и отдаляют.":
        "The ring turns the view, the letter N puts north up. The stick "
        "inside the ring looks around, the dot in its middle returns the "
        "vertical view without tilt and roll. The lower stick moves the "
        "view. The slider sets the height, plus and minus zoom in and out.",
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
    "Поддержать разработку": "Support development",
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
    "Границы стран и областей, реки и водоёмы, подписи на "
    "глобусе.":
        "Country and region borders, rivers and water bodies, labels on "
        "the globe.",
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
    "Вершины и охраняемые территории.":
        "Peaks and protected areas.",
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
    "Новая метка, путь, многоугольник или круг в «Мои метки».":
        "A new placemark, path, polygon or circle in My Places.",
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
    "3D-путь": "3D path",
    "3D-многоугольник": "3D polygon",
    "Щелчками отметьте точки пути на рельефе, крышах и стенах "
    "3D-зданий. Длина меряется прямыми отрезками в пространстве.":
        "Click the points of the path on the terrain, roofs and walls of 3D "
        "buildings. The length is measured by straight segments in space.",
    "Щелчками отметьте вершины многоугольника на рельефе, крышах и "
    "стенах 3D-зданий. Площадь меряется в плоскости многоугольника.":
        "Click the vertices of the polygon on the terrain, roofs and walls of "
        "3D buildings. The area is measured in the plane of the polygon.",
    "Угол плоскости многоугольника к горизонту. 0 - ровная крыша, "
    "90 - стена.":
        "Angle of the polygon plane to the horizon. 0 is a flat roof, 90 a "
        "wall.",
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
    "Удалить": "Delete",
    "Добавить слои меток в проект": "Add the places layers to the project",
    "Название": "Name",
    "Удалить метку": "Delete placemark",
    "Удалить «{name}» из «Моих меток»?": "Delete \"{name}\" from My Places?",
    "значения в точке": "values at the point",
    "{point}, высота {height} м": "{point}, elevation {height} m",
    "{point}, глубина {depth} м": "{point}, depth {depth} m",
    "Объекты": "Features",
    "Объект": "Feature",
    "Значение": "Value",
    "Под точкой объектов нет": "No features at the point",
    "Синхронизация с окном карты QGIS. Направление - в свойствах вида.":
        "Synchronization with the QGIS map window. The direction is set "
        "in the view properties.",
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
    "Запись: кадр {n} из {count}": "Recording: frame {n} of {count}",
    "Тур по кругу. После последней остановки тур начинается "
    "с первой. Остановить его - пауза или крестик.":
        "Loop the tour. After the last stop the tour starts again from "
        "the first. Stop it with pause or the cross.",
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
    "В файле нет точек, линий, многоугольников и наложений.":
        "The file has no points, lines, polygons or overlays.",
    "Картинка на поверхности": "Ground overlay",
    "Картинка на экране": "Screen overlay",
    "Фото": "Photo",
    "Название наложения в «Моих метках».":
        "The name of the overlay in My Places.",
    "Описание наложения. Оно уходит в KML вместе с картинкой.":
        "The description of the overlay. It goes into KML with the image.",
    "Картинка": "Image",
    "Непрозрачность картинки. У нуля сквозь неё виден снимок.":
        "Opacity of the image. At zero the imagery shows through it.",
    "Непрозрачность": "Opacity",
    "Картинка наложения": "Overlay image",
    "Картинки (*.png *.jpg *.jpeg *.gif)":
        "Images (*.png *.jpg *.jpeg *.gif)",
    "Углы картинки тянутся мышью на глобусе, пока окно открыто.":
        "The corners of the image are dragged with the mouse on the globe "
        "while the window is open.",
    "Левый верхний": "Top left",
    "Правый верхний": "Top right",
    "Левый нижний": "Bottom left",
    "Правый нижний": "Bottom right",
    "Середина": "Centre",
    "Угол вида, к которому прижата картинка.":
        "The corner of the view the image is pinned to.",
    "свой размер": "own size",
    "Ширина картинки в долях ширины вида. Ноль - картинка своего размера "
    "в пикселях.":
        "Width of the image as a share of the view width. Zero - the image "
        "at its own size in pixels.",
    "{w} × {h} пикселей": "{w} × {h} pixels",
    "картинки нет": "no image",
    "Картинку на поверхности": "Ground overlay",
    "Картинку на экране": "Screen overlay",
    "Картинка не читается: {name}": "The image cannot be read: {name}",

    # Свойства метки.
    "Свойства…": "Properties…",
    "Свойства: {name}": "Properties: {name}",
    "Описание метки. Оно сохраняется в файле меток и уходит в KML.":
        "Description of the place. It is kept in the places file and goes "
        "to KML.",
    "Описание": "Description",
    " м": " m",
    "Подъём над поверхностью или дном, в абсолютном режиме - "
    "высота над уровнем моря.":
        "The rise above the surface or the sea floor, in the absolute "
        "mode the altitude above sea level.",
    "На поверхности": "Clamped to ground",
    "Вдоль морского дна": "Clamped to sea floor",
    "Относительно поверхности": "Relative to ground",
    "Относительно морского дна": "Relative to sea floor",
    "Абсолютная": "Absolute",
    "От чего отсчитывается высота. На поверхности - метка лежит "
    "на земле, над морем на воде. Вдоль морского дна - на дне. "
    "Относительно поверхности и дна - подъём над ними. "
    "Абсолютная - высота над уровнем моря. Режим сохраняется "
    "в KML.":
        "What the altitude is measured from. Clamped to ground - the "
        "placemark lies on the ground, over the sea on the water. "
        "Clamped to sea floor - on the floor. Relative to ground and to "
        "sea floor - the rise above them. Absolute - the altitude above "
        "sea level. The mode is saved in KML.",
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
    "Тур": "Tour",
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
    "Добавить источник тайлов…": "Add tile source…",
    "Новый источник тайлов": "New tile source",
    "Адрес тайлов в любом виде - шаблон с {z}, {x}, {y}, адрес "
    "одного тайла из браузера или адрес с z, x, y в параметрах "
    "запроса. Окно само приводит его к шаблону. Адрес службы WMS "
    "окно узнаёт и предлагает выбрать слой.":
        "A tile address in any form - a template with {z}, {x}, {y}, the "
        "address of one tile from a browser or an address with z, x, y in "
        "the query. The window turns it into a template itself. The window "
        "recognises the address of a WMS service and offers a layer.",
    "Слой": "Layer",
    "Слой службы WMS. Строка «Все слои» показывает все слои группы "
    "вместе. Вне охвата слоя глобус показывает снимки Esri World "
    "Imagery.":
        "The layer of the WMS service. The \"All layers\" row shows all "
        "layers of the group together. Outside the layer extent the globe "
        "shows Esri World Imagery.",
    "Служба WMS - загрузка списка слоёв…":
        "WMS service - loading the layer list…",
    "Служба не ответила на GetCapabilities - {error}.":
        "The service did not answer GetCapabilities - {error}.",
    "Ответ службы не разобран как WMS - {error}.":
        "The service answer is not understood as WMS - {error}.",
    "Все слои - {title}": "All layers - {title}",
    "Слой покрывает весь мир.": "The layer covers the whole world.",
    "Охват слоя - {w:.2f}…{e:.2f}° по долготе, "
    "{s:.2f}…{n:.2f}° по широте. Вне охвата - снимки "
    "Esri World Imagery.":
        "Layer extent - {w:.2f}…{e:.2f}° in longitude, {s:.2f}…{n:.2f}° in "
        "latitude. Outside the extent - Esri World Imagery.",
    "Загрузка картинки слоя…": "Loading the layer picture…",
    "Картинка слоя не пришла - {error}.":
        "The layer picture did not arrive - {error}.",
    "Картинка слоя пришла.": "The layer picture arrived.",
    "Служба WMS": "WMS service",
    "Удалить подложку WMS «{name}»?":
        "Delete the WMS base map \"{name}\"?",
    "Название источника в списке подложек и в обозревателе QGIS. "
    "Предлагается по имени сервера.":
        "The source name in the base map list and in the QGIS browser. It "
        "is suggested from the server name.",
    "Ряды снизу вверх (TMS)": "Rows from the bottom up (TMS)",
    "У части серверов ряды тайлов считаются от южного края. Если "
    "в мозаике ниже север внизу, отметьте флажок.":
        "Some servers count tile rows from the southern edge. If north is "
        "at the bottom of the mosaic below, check the box.",
    "Самый подробный уровень тайлов сервера. Окно находит его само "
    "по точке взгляда глобуса. Глубже этого уровня глобус "
    "увеличивает последний тайл.":
        "The most detailed tile level of the server. The window finds it "
        "itself at the look point of the globe. Below this level the "
        "globe enlarges the last tile.",
    "Подпись источника в углу вида и на снимках. Условия "
    "использования тайлов задаёт их владелец.":
        "The source credit in the corner of the view and on snapshots. The "
        "owner of the tiles sets their terms of use.",
    "Адрес": "Address",
    "Уровни до": "Levels up to",
    "Подпись": "Credit",
    "Шаблон - {url}": "Template - {url}",
    "Загрузка мозаики…": "Loading the mosaic…",
    "не картинка": "not an image",
    "Тайлов мозаики пришло {n} из 4.": "{n} of 4 mosaic tiles arrived.",
    "Ответы с ошибкой - {errors}.": "Error responses - {errors}.",
    "В точке взгляда есть уровень {z}.":
        "Level {z} exists at the look point.",
    "Адрес не разобран. Нужен шаблон с {z}, {x}, {y} или адрес "
    "одного тайла.":
        "The address is not understood. A template with {z}, {x}, {y} or "
        "the address of one tile is needed.",
    "Свойства папки": "Folder properties",
    "Разрешить раскрывать папку": "Allow the folder to be expanded",
    "Без флажка папка в списке не раскрывается, её метки "
    "показывает и скрывает флажок самой папки.":
        "Without the box the folder does not expand in the list, the box "
        "of the folder itself shows and hides its places.",
    "Показать содержание как группу переключателей":
        "Show contents as option buttons",
    "На глобусе видна только одна метка или папка из этой папки. "
    "Флажок одной строки снимает флажки остальных.":
        "Only one place or folder of this folder shows on the globe. "
        "Checking one row clears the others.",
    "Описание папки. Оно хранится в «Моих метках» и в KML.":
        "The folder description. It is kept in My Places and in KML.",
    "Вид папки": "Folder view",
    "Откуда смотрит камера, когда летит к папке. Вид задаётся "
    "вручную числами или снимком текущего вида. Без своего вида "
    "перелёт берёт в кадр все метки папки.":
        "Where the camera looks from when it flies to the folder. The view "
        "is set by hand with numbers or by a snapshot of the current view. "
        "Without a view of its own the flight frames all places of the "
        "folder.",
    "Вернуть вид, который был у папки при открытии окна.":
        "Restore the view the folder had when the window opened.",
    "Широта точки, на которую смотрит камера.":
        "Latitude of the point the camera looks at.",
    "Добавить": "Add",
    "Папку": "Folder",
    "Метку": "Placemark",
    "Записанный тур": "Recorded tour",
    "Вырезать": "Cut",
    "Снимок вида папки": "Snapshot folder view",
    "Сортировать от А до Я": "Sort A-Z",
    "Экспозиция, ровное - серое": "Aspect, flat is grey",
    "Уклон, °": "Slope, °",
    "С": "N",
    "СВ": "NE",
    "В": "E",
    "ЮВ": "SE",
    "Ю": "S",
    "ЮЗ": "SW",
    "З": "W",
    "СЗ": "NW",
    "Уклон": "Slope",
    "Уклон поверхности по высотам рельефа, классами от "
    "ровного до круче 35°. Шкала стоит в левом нижнем "
    "углу вида. Есть у Земли, Марса и Луны.":
        "Surface slope from the terrain heights, in classes from flat to "
        "steeper than 35°. The scale is in the bottom left corner of the "
        "view. Available on the Earth, Mars and the Moon.",
    "Экспозиция": "Aspect",
    "Куда обращён склон - цвет стороны света, ровное "
    "место серое. Включается вместо уклона.":
        "Which way a slope faces - the colour of the compass direction, "
        "flat ground is grey. It replaces the slope when switched on.",
    "Видимость отсюда…": "Viewshed from here…",
    "Видимость из точки": "Viewshed from a point",
    "Высота глаза или мачты над рельефом в точке. Выше - дальше "
    "видно и меньше мест скрыто за рельефом.":
        "Height of the eye or mast above the terrain at the point. A "
        "higher value sees farther and fewer places stay hidden behind "
        "the terrain.",
    "Высота того, что надо увидеть, над рельефом, например "
    "мачты или здания. При нуле проверяется сама земля.":
        "Height above the terrain of what has to be seen, for example a "
        "mast or a building. At zero the ground itself is checked.",
    " км": " km",
    "Радиус круга расчёта. Больше - шаг расчёта крупнее, он "
    "около пятисотой доли радиуса.":
        "Radius of the computed circle. A larger radius gives a coarser "
        "step, the step is about one five-hundredth of the radius.",
    "Точка": "Point",
    "Высота наблюдателя": "Observer height",
    "Высота цели": "Target height",
    "Построить": "Build",
    "Видно {share} площади круга. Шаг расчёта {step} м.":
        "{share} of the circle area is visible. The computation step is "
        "{step} m.",
    "Для этого тела высот нет.": "This body has no heights.",
    "Загрузка высот: {done} из {total}": "Loading heights: {done} of {total}",
    "Загружены не все высоты, расчёт шёл "
    "по менее подробным.":
        "Not all heights are loaded, the computation used less detailed "
        "ones.",
    "Кратер Езеро": "Jezero crater",
    "уровень моря": "sea level",
    "Глубины морей и океанов": "Sea and ocean depths",
    "С флажком дно морей и океанов лежит на своих глубинах, над "
    "ним полупрозрачная вода, строка состояния показывает "
    "глубину под курсором, профиль высот - глубины и уровень "
    "моря. Без флажка высоты ниже уровня моря считаются нулём, "
    "море ровное. Есть только у Земли.":
        "With the box checked the sea and ocean floor lies at its depths "
        "under semi-transparent water, the status bar shows the depth "
        "under the cursor, and the elevation profile shows depths and sea "
        "level. Without it heights below sea level count as zero and the "
        "sea is flat. Exists only on the Earth.",
    "Землетрясения": "Earthquakes",
    "Землетрясения магнитудой от 4.5 за последние 30 "
    "суток по сводке USGS. Кружок стоит в эпицентре "
    "на поверхности. На своей глубине очаг виден в вынутом "
    "секторе строки «Разрез Земли». "
    "Цвет показывает глубину очага, размер - магнитуду. "
    "Сводка загружается при включении строки.":
        "Earthquakes of magnitude 4.5 and above over the last 30 days from "
        "the USGS feed. A circle marks the epicentre on the surface. "
        "The focus is seen at its depth in the removed sector of the Earth "
        "cutaway row. The colour shows the focus "
        "depth, the size shows the magnitude. The feed is loaded when the "
        "row is switched on.",
    "Глубина очага, км": "Focus depth, km",
    "Плита Slab2": "Slab2 slab",
    "Разрез вниз…": "Section down…",
    "Разрез: {name}": "Section: {name}",
    "Разрез": "Section",
    "Глубина": "Depth",
    "Полоса очагов": "Foci band",
    "Нужен путь хотя бы из двух точек.":
        "A path of at least two points is needed.",
    "Мохо {depth}": "Moho {depth}",
    "плита {top}-{bottom}": "slab {top}-{bottom}",
    "кора CRUST1.0": "CRUST1.0 crust",
    "плиты Slab2": "Slab2 slabs",
    "землетрясения": "earthquakes",
    "Загружаются: {what}.": "Loading: {what}.",
    "Длина {length}, глубина {depth}. Очагов землетрясений "
    "в полосе {count}.":
        "Length {length}, depth {depth}. Earthquake foci in the band "
        "{count}.",
    "До какой глубины идёт разрез. 700 км - низ переходной зоны, "
    "глубже землетрясений почти нет. 2891 км - граница ядра, "
    "6371 км - центр Земли.":
        "How deep the section goes. 700 km is the bottom of the "
        "transition zone, there are almost no earthquakes deeper. "
        "2891 km is the core boundary, 6371 km is the centre of the Earth.",
    "Ширина полосы вдоль линии, из которой очаги землетрясений "
    "переносятся на разрез. Шире полоса - больше очагов, но "
    "дальние очаги лежат не там, где линия.":
        "Width of the band along the line from which earthquake foci are "
        "moved onto the section. A wider band gives more foci, but distant "
        "foci do not lie where the line is.",
    "Измерение": "Measurement",
    "Магнитуда": "Magnitude",
    "Глубина очага": "Focus depth",
    "Время, UTC": "Time, UTC",
    "Страница USGS": "USGS page",
    "Мохо": "Moho",
    "Толщина коры": "Crust thickness",
    "Осадочный чехол": "Sediments",
    "загружается": "loading",
    "{top}-{bottom} км": "{top}-{bottom} km",
    "Место": "Site",
    "Под точкой": "Under the point",
    "Тип": "Type",
    "KML не разобран: {error}. Исправь документ.":
        "KML not parsed: {error}. Fix the document.",
    "Адрес сервиса. У Anthropic, xAI, DeepSeek и OpenRouter менять его "
    "не нужно. У своего сервиса - адрес его входа формата OpenAI, "
    "например http://localhost:11434/v1 у Ollama.":
        "Service address. Anthropic, xAI, DeepSeek and OpenRouter need no "
        "change. An own service needs the address of its OpenAI format "
        "entry, for example http://localhost:11434/v1 for Ollama.",
    "В «Мои метки» записано меток: {count}.":
        "Placemarks written to My Places: {count}.",
    "В документе KML нет меток.":
        "The KML document has no placemarks.",
    "Вы":
        "You",
    "Выделенных меток нет.":
        "No placemarks are selected.",
    "Даты не разобраны: {start} - {end}.":
        "Dates not parsed: {start} - {end}.",
    "Действие":
        "Action",
    "Для разреза нужны хотя бы две точки.":
        "A section needs at least two points.",
    "Документ показан пользователю, меток {count}. Запись - после его "
    "подтверждения.":
        "The document is shown to the user, placemarks {count}. It is "
        "written after the user confirms.",
    "Записать в «Мои метки»":
        "Write to My Places",
    "Запрос, точка взгляда и включённые строки раздела «Слои» уходят на "
    "сервер выбранной модели. Слои проекта, их поля и строки уходят, только "
    "когда вы разрешаете чтение. «Мои метки» уходят только выделенными.":
        "The request, the look-at point and the rows switched on in the "
        "Layers section go to the server of the chosen model. Project "
        "layers, their fields and rows go only when you allow the reading. "
        "My Places go only when selected.",
    "ALOS AW3D30 30 м - с лесом и домами":
        "ALOS AW3D30 30 m - with forest and buildings",
    "NASADEM 30 м - SRTM без пустот, до 60° широты":
        "NASADEM 30 m - SRTM without voids, up to 60° latitude",
    "USGS 3DEP 10 м - только США, земля без леса и домов":
        "USGS 3DEP 10 m - USA only, bare ground without forest and buildings",
    "Высоты суши 10 м с уровня 9":
        "Land heights 10 m from level 9",
    "Разрешить":
        "Allow",
    "Выполнить это действие один раз.":
        "Run this action once.",
    "Разрешить в этом разговоре":
        "Allow in this conversation",
    "Точно такой же запрос больше не спрашивается до нового разговора. "
    "Другой слой или другой отбор спросится снова.":
        "Exactly the same request is not asked again until a new "
        "conversation. Another layer or another filter is asked again.",
    "Отказать":
        "Decline",
    "Помощник получает отказ и отвечает без этого действия.":
        "The assistant gets a refusal and answers without this action.",
    "Помощник сделал много действий подряд.":
        "The assistant has made many actions in a row.",
    "Помощник продолжает с того места, где остановился.":
        "The assistant continues where it stopped.",
    "Помощник просит выполнить {name} {args}.":
        "The assistant asks to run {name} {args}.",
    "Отказано.":
        "Declined.",
    "Сервис занят ({error}), повтор через {seconds} с.":
        "The service is busy ({error}), retry in {seconds} s.",
    "Помощник сделал много действий подряд и ждёт «Продолжить».":
        "The assistant has made many actions in a row and waits for "
        "Continue.",
    "В проекте нет слоёв.":
        "The project has no layers.",
    "Слоя нет. Номер берётся из list_project_layers.":
        "No such layer. The number comes from list_project_layers.",
    "Слой «{name}» не векторный, строк у него нет.":
        "The layer {name} is not a vector layer, it has no rows.",
    "Подходящих строк нет.":
        "No matching rows.",
    "Помощник просит список слоёв проекта QGIS - названия, поля, системы "
    "координат и количество объектов.":
        "The assistant asks for the list of QGIS project layers - names, "
        "fields, coordinate systems and feature counts.",
    "Помощник просит прочитать строки слоя «{name}», не больше {limit}.":
        "The assistant asks to read rows of the layer {name}, no more than "
        "{limit}.",
    "Ошибка в выражении отбора: {error}":
        "Error in the filter expression: {error}",
    "Строк больше {limit}, показаны первые.":
        "There are more than {limit} rows, the first ones are shown.",
    "Отбор: {where}.":
        "Filter: {where}.",
    "С координатами объектов.":
        "With feature coordinates.",
    "Помощник просит выполнить «{title}». Откроется окно, которое ждёт "
    "вашего ответа.":
        "The assistant asks to run {title}. A window opens and waits for "
        "your answer.",
    "Ключ":
        "Key",
    "Ключ API выбранного сервиса. Он хранится в менеджере паролей QGIS и "
    "уходит только на адрес сервиса.":
        "API key of the chosen service. It is kept in the QGIS password "
        "manager and goes only to the service address.",
    "Ключ не сохранён: менеджер паролей QGIS отказал.":
        "The key is not saved: the QGIS password manager refused.",
    "Ключ сохранён в менеджере паролей QGIS.":
        "The key is saved in the QGIS password manager.",
    "Модель":
        "Model",
    "Модель не ответила: {error}":
        "The model did not answer: {error}",
    "Модуль":
        "Plugin",
    "Название модели у выбранного сервиса. Модель должна уметь вызывать "
    "инструменты (tools), иначе помощник только отвечает текстом.":
        "Model name at the chosen service. The model must be able to call "
        "tools, otherwise the assistant only answers with text.",
    "Например: покажи разрез через Японский жёлоб":
        "For example: show a section across the Japan Trench",
    "Неизвестная строка: {key}.":
        "Unknown row: {key}.",
    "Неизвестное тело: {body}.":
        "Unknown body: {body}.",
    "Нет такого инструмента: {name}.":
        "No such tool: {name}.",
    "Отменить":
        "Cancel",
    "Ошибка в аргументах {name}: {error}":
        "Error in the arguments of {name}: {error}",
    "Перелёт к {lat:.3f}, {lon:.3f}.":
        "Flight to {lat:.3f}, {lon:.3f}.",
    "Поиск запущен: {query}.":
        "Search started: {query}.",
    "Помощник":
        "Assistant",
    "Помощник предлагает папку «{name}», меток {count}.":
        "The assistant proposes the folder {name}, placemarks {count}.",
    "Разрез Земли есть только у Земли.":
        "The Earth cutaway exists only on the Earth.",
    "Разрез Земли убран.":
        "The Earth cutaway is removed.",
    "Разрез не построен.":
        "The section is not built.",
    "Разрез открыт: длина {length:.0f} км, глубина {depth:.0f} км, очагов "
    "в полосе {count}.":
        "Section open: length {length:.0f} km, depth {depth:.0f} km, foci "
        "in the band {count}.",
    "Разрез помощника":
        "Assistant section",
    "Сведений о точке нет.":
        "No information about the point.",
    "Сводка землетрясений загружается, повтори запрос через несколько секунд.":
        "The earthquake feed is loading, repeat the request in a few seconds.",
    "Сектор: {wedge}.":
        "Sector: {wedge}.",
    "Сервис":
        "Service",
    "Сохранить ключ":
        "Save key",
    "Спросить":
        "Ask",
    "Строка {key}: {state}.":
        "Row {key}: {state}.",
    "Тело: {body}.":
        "Body: {body}.",
    "Нет такого действия: {key}. Ключ берётся из list_actions.":
        "No such action: {key}. Take the key from list_actions.",
    "Выполнено: {title} - {note}.":
        "Done: {title} - {note}.",
    "Слоя {key} нет среди включённых.":
        "Layer {key} is not among the shown layers.",
    "У слоя {key} непрозрачность не меняется.":
        "Layer {key} has no opacity setting.",
    "Непрозрачность {key}: {value:.2f}.":
        "Opacity of {key}: {value:.2f}.",
    "OpenRouter (есть бесплатные модели)":
        "OpenRouter (free models available)",
    "Свой сервис, например Ollama":
        "Own service, for example Ollama",
    "Через какой сервис работает помощник. У каждого сервиса свой ключ, "
    "адрес и модель. У OpenRouter модели с «:free» в названии бесплатны "
    "с ограничением запросов в сутки. Свой сервис работает в формате "
    "OpenAI Chat, на этом компьютере ключ не нужен.":
        "Which service the assistant works through. Each service has its "
        "own key, address and model. OpenRouter models with \":free\" in "
        "the name are free with a daily request limit. An own service "
        "works in the OpenAI Chat format, on this computer it needs no "
        "key.",
    "Шкала времени закрыта.":
        "The time slider is closed.",
    "Шкала времени: {start} - {end}.":
        "Time slider: {start} - {end}.",
    "Шкалы времени нет: у видимых меток и событий нет времени.":
        "There is no time slider: visible placemarks and events have no time.",
    "введите ключ API":
        "enter the API key",
    "включена":
        "on",
    "выключена":
        "off",
    "ключ сохранён":
        "key saved",
    "Разрез Земли": "Earth cutaway",
    "Внутреннее ядро": "Inner core",
    "Внешнее ядро": "Outer core",
    "Нижняя мантия": "Lower mantle",
    "Переходная зона": "Transition zone",
    "Верхняя мантия": "Upper mantle",
    "Кора": "Crust",
    "Оболочки PREM, глубина, км": "PREM shells, depth, km",
    "Кора CRUST1.0, оболочки PREM, глубина, км":
        "CRUST1.0 crust, PREM shells, depth, km",
    "{}, Мохо-{:g}": "{}, Moho-{:g}",
    "Глубины до {:g} км растянуты, у поверхности "
    "×{:g}": "Depths to {:g} km stretched, ×{:g} at the surface",
    "Лёд": "Ice",
    "Верхние осадки": "Upper sediments",
    "Средние осадки": "Middle sediments",
    "Нижние осадки": "Lower sediments",
    "Верхняя кора": "Upper crust",
    "Средняя кора": "Middle crust",
    "Нижняя кора": "Lower crust",
    "нет ответа": "no reply",
    "нТл": "nT",
    "млн лет": "Ma",
    "мВт/м²": "mW/m²",
    "Океаническое дно": "Ocean floor",
    "Возраст коры": "Crust age",
    "Поток тепла": "Heat flow",
    "Скорости плит": "Plate motion",
    "Вулканы": "Volcanoes",
    "Томография мантии": "Mantle tomography",
    "Кора CRUST1.0 в проект QGIS…": "CRUST1.0 crust to the QGIS project…",
    "Кора CRUST1.0 в проект QGIS": "CRUST1.0 crust to the QGIS project",
    "Отметки кровель трёх слоёв осадков, трёх слоёв коры и Мохо "
    "по модели CRUST1.0 в рамке вида - растры GeoTIFF в метрах "
    "с шагом 1°, группой в проект QGIS.": "Elevations of the tops of the "
    "three sediment layers, the three crust layers and the Moho after the "
    "CRUST1.0 model within the view frame - GeoTIFF rasters in metres with "
    "a 1° step, as a group in the QGIS project.",
    "PlanetX - кора CRUST1.0": "PlanetX - CRUST1.0 crust",
    "Источники того, что на глобусе. Щелчок открывает окно "
    "«Источники данных» с полными подписями и условиями.": "Sources of "
    "what the globe shows. A click opens the Data sources window with the "
    "full credits and terms.",
    "кровля верхних осадков": "top of upper sediments",
    "кровля средних осадков": "top of middle sediments",
    "кровля нижних осадков": "top of lower sediments",
    "кровля верхней коры": "top of upper crust",
    "кровля средней коры": "top of middle crust",
    "кровля нижней коры": "top of lower crust",
    "Модель коры загружается, поверхности будут записаны по её приходу.":
    "The crust model is loading, the surfaces will be written when it "
    "arrives.",
    "В проект добавлено поверхностей коры {count}.":
    "Crust surfaces added to the project: {count}.",
    "Поверхности коры не записаны в «{path}».":
    "The crust surfaces were not written to {path}.",
    "Раскрашивает мантию на гранях по отклонению скорости "
    "сейсмических волн от модели PREM - модель SEISGLOB2. "
    "Красная мантия медленнее и горячее, синяя быстрее "
    "и холоднее. Первое включение скачивает около 28 МБ.": "Colours the "
    "mantle on the faces by the deviation of seismic wave speed from the "
    "PREM model, the SEISGLOB2 model. Red mantle is slower and hotter, "
    "blue mantle is faster and colder. The first switch-on downloads "
    "about 28 MB.",
    "Загрузка томографии SEISGLOB2, около 28 МБ…": "Loading the SEISGLOB2 "
    "tomography, about 28 MB…",
    "Томография не загрузилась: {error}": "Tomography did not load: "
    "{error}",
    "Томография не разобрана.": "Tomography could not be read.",
    "Мантия медленнее PREM на 2 % и больше": "Mantle 2 % and more slower "
    "than PREM",
    "Мантия как PREM": "Mantle as PREM",
    "Мантия быстрее PREM на 2 % и больше": "Mantle 2 % and more faster "
    "than PREM",
    "Вулканы голоцена GVP": "Holocene volcanoes, GVP",
    "Размер точки - высота вулкана": "Dot size - volcano height",
    "Извергался с 1900 года": "Erupted since 1900",
    "Извергался в 1500-1899 годах": "Erupted in 1500-1899",
    "Извергался до 1500 года": "Erupted before 1500",
    "Дата извержения неизвестна": "Eruption date unknown",
    "Загрузка списка вулканов GVP, около 2 МБ…": "Loading the GVP volcano "
    "list, about 2 MB…",
    "Список вулканов не загрузился, проверьте сеть и включите строку "
    "снова.": "The volcano list did not load, check the network and turn "
    "the row on again.",
    "Вулканов {count}.": "{count} volcanoes.",
    "Последнее извержение": "Last eruption",
    "{year} до н. э.": "{year} BCE",
    "дата неизвестна": "date unknown",
    "Обстановка": "Setting",
    "Около 1200 вулканов, извергавшихся за последние 12 тысяч лет, "
    "по списку Global Volcanism Program Смитсоновского института. "
    "Цвет - время последнего извержения, размер - высота вулкана. "
    "Щелчок по точке показывает тип вулкана, год последнего "
    "извержения, тектоническую обстановку и страницу вулкана на "
    "сайте GVP. Первое включение скачивает около 2 МБ.": "About 1200 "
    "volcanoes that erupted in the last 12 thousand years after the "
    "Global Volcanism Program list of the Smithsonian Institution. The "
    "colour is the time of the last eruption, the size is the volcano "
    "height. A click on a dot shows the volcano type, the year of the "
    "last eruption, the tectonic setting and the volcano page on the GVP "
    "site. The first switch-on downloads about 2 MB.",
    "Поле до 1900 года не загружено: {error}": "The field before 1900 is "
    "not loaded: {error}",
    "gufm1 с 1590 года, IGRF-14 с 1900 по 2030 год": "gufm1 from 1590, "
    "IGRF-14 from 1900 to 2030",
    "Скорость плиты": "Plate speed",
    "Плита": "Plate",
    "Направление": "Direction",
    "Скорости плит не прочитаны: {error}": "Plate motion not read: {error}",
    "Стрелки движения литосферных плит по модели NNR-MORVEL56 - "
    "скорость относительно среднего движения всех плит. Длина "
    "стрелки растёт со скоростью, число у её начала - мм/год. "
    "Тихоокеанская плита идёт на северо-запад около 70 мм/год, "
    "Евразийская - около 25. Окно «Объекты» показывает плиту, "
    "скорость и направление в точке.": "Arrows of lithospheric plate "
    "motion after the NNR-MORVEL56 model, the speed relative to the mean "
    "motion of all plates. The arrow grows with the speed, the number at "
    "its start is mm/yr. The Pacific plate moves north-west at about "
    "70 mm/yr, the Eurasian plate at about 25. The Features window shows "
    "the plate, speed and direction at the point.",
    "Тепловой поток": "Heat flow",
    "Возраст океанического дна, млн лет": "Ocean floor age, Ma",
    "Тепловой поток, мВт/м²": "Heat flow, mW/m²",
    "Возраст океанического дна": "Ocean floor age",
    "Возраст океанической коры по сетке Seton и соавторов 2020 "
    "года, шаг 0.1°. Молодое дно у срединных хребтов красное, "
    "древнее у окраин океанов - синее и фиолетовое. Суша и "
    "континентальная кора не закрашены. На глобусе одна карта "
    "значений - возраст дна, магнитные аномалии, сила тяжести "
    "или тепловой поток. Щелчок в режиме «Определить объекты» "
    "показывает возраст в млн лет.": "Age of the oceanic crust after the "
    "grid of Seton et al. 2020, 0.1° spacing. Young floor at mid-ocean "
    "ridges is red, old floor at ocean margins is blue and purple. Land "
    "and continental crust are not coloured. The globe shows one value "
    "map at a time - ocean floor age, magnetic anomalies, gravity or heat "
    "flow. A click in the Identify features mode shows the age in Ma.",
    "Аномалии силы тяжести": "Gravity anomalies",
    "Аномалия силы тяжести, мГал": "Gravity anomaly, mGal",
    "Сила тяжести": "Gravity",
    "Аномалия в свободном воздухе": "Free-air anomaly",
    "мГал": "mGal",
    "Аномалии Буге": "Bouguer anomalies",
    "Аномалия Буге": "Bouguer anomaly",
    "Аномалия Буге, мГал": "Bouguer anomaly, mGal",
    "Плотность породы": "Rock density",
    "Аномалия силы тяжести за вычетом притяжения рельефа - "
    "поправка Буге по рельефу ETOPO 2022 с плотностью породы "
    "2670 кг/м³, вода и лёд своей плотностью, и поправка на "
    "рельеф вокруг в круге 167 км. Аномалия показывает плотность "
    "недр без влияния гор и глубин океана. Под горами она "
    "отрицательная, это толстая лёгкая кора, над океаном "
    "положительная. Щелчок в режиме «Определить объекты» "
    "показывает аномалию в мГал.": "Gravity anomaly minus the attraction "
    "of the relief - the Bouguer correction after the ETOPO 2022 relief "
    "with a rock density of 2670 kg/m³, water and ice with their own "
    "densities, and the terrain correction for the surrounding relief "
    "within 167 km. The anomaly shows the density of the interior without "
    "the effect of mountains and ocean depths. Under mountains it is "
    "negative, which is thick light crust, over the ocean it is positive. "
    "A click in the Identify features mode shows the anomaly in mGal.",
    "Аномалия силы тяжести в свободном воздухе по модели XGM2019e "
    "до степени 719, шаг около 28 км. Красные - сила тяжести "
    "больше нормальной, синие - меньше. Над глубоководными "
    "желобами провалы до -300 мГал, над вулканическими островами "
    "и горами - подъём. Щелчок в режиме «Определить объекты» "
    "показывает аномалию в мГал.": "Free-air gravity anomaly after the "
    "XGM2019e model to degree 719, about 28 km spacing. Red marks gravity "
    "above normal, blue marks gravity below normal. Deep-sea trenches show "
    "lows down to -300 mGal, volcanic islands and mountains show highs. A "
    "click in the Identify features mode shows the anomaly in mGal.",
    "Поток тепла из недр через поверхность Земли по сетке 0.5°, "
    "построенной по 91 тысяче измерений базы IHFC 2024. Синие - "
    "холодные древние щиты, красные - рифты, хребты и вулканические "
    "области. Вдали от измерений сетка сглажена. Щелчок в режиме "
    "«Определить объекты» показывает поток в мВт/м².": "Heat flow from "
    "the interior through the Earth's surface on a 0.5° grid built from "
    "91 thousand measurements of the IHFC 2024 database. Blue marks cold "
    "old shields, red marks rifts, ridges and volcanic areas. Far from "
    "measurements the grid is smoothed. A click in the Identify features "
    "mode shows the flow in mW/m².",
    "Линии склонения": "Declination lines",
    "Линии равного магнитного склонения - угла между стрелкой "
    "компаса и направлением на север - через 10° на год шкалы "
    "времени по моделям IGRF-14 с 1900 года и gufm1 с 1590 "
    "года, gufm1 скачивается при первом показе. Красные - "
    "склонение восточное, синие - западное, зелёная - нулевое. "
    "У магнитных полюсов линии сходятся.": "Lines of equal magnetic "
    "declination, the angle between the compass needle and the north, "
    "every 10° for the year of the time scale after the IGRF-14 model "
    "from 1900 and the gufm1 model from 1590, gufm1 is downloaded on "
    "first display. Red lines are east declination, blue lines west, the "
    "green line zero. The lines meet at the magnetic poles.",
    "верхняя": "upper",
    "средняя": "middle",
    "нижняя": "lower",
    "Континентальная кора, {}": "Continental crust, {}",
    "Океаническая кора, {}": "Oceanic crust, {}",
    "Модель коры CRUST1.0 не загружена ({}), кора - слой "
    "PREM": "Crust model CRUST1.0 not loaded ({}), the crust is the "
    "PREM layer",
    "Тип коры": "Crust type",
    "континентальная": "continental",
    "океаническая": "oceanic",
    "Растягивать кору": "Stretch the crust",
    "Растягивает глубины до 400 км тем сильнее, чем дальше камера, "
    "и издалека видны кора и верхняя мантия. Без флажка все глубины "
    "в настоящем масштабе.": "Stretches depths to 400 km, the more the "
    "farther the camera is, so the crust and the upper mantle are seen "
    "from afar. Without the check box all depths are true to scale.",
    "Вынимает из Земли сектор под точкой взгляда - "
    "четверть полушария шириной 90° по долготе. На его "
    "гранях видны кора, мантия и ядро по радиусам "
    "модели PREM. Где грань проходит через зону "
    "субдукции, на ней видна погружающаяся плита. "
    "Углы сектора тянутся мышью. Сектор ставится заново "
    "при каждом включении строки.":
        "Removes a sector of the Earth under the look-at point, a quarter "
        "of a hemisphere 90° wide in longitude. Its faces show the crust, "
        "the mantle and the core by the radii of the PREM model. Where a "
        "face crosses a subduction zone, the subducting slab shows on it. "
        "The corners of the sector can be dragged with the mouse. The "
        "sector is placed anew each time the row is switched on.",
    "Пермские отложения": "Permian deposits",
    "Тоннели Vegas Loop": "Vegas Loop tunnels",
    "Аральское море": "Aral Sea",
    "Рельеф глобуса": "Globe terrain",
    'Источники данных…':
        'Data sources…',
    "Все источники глобуса с условиями использования, проверка их "
    "доступности, свой рельеф и своя векторная основа, добавление, правка и "
    "удаление подложек.":
        "All globe sources with their terms of use, an availability check, "
        "own terrain and own vector base, adding, editing and removing base "
        "maps.",
    'Векторная основа':
        'Vector base',
    'Науки о Земле':
        'Earth sciences',
    'Проверить':
        'Check',
    "Запросить у каждого источника один тайл или файл мимо кэша и показать "
    "ответ и время. Большие файлы вроде картинки звёздного неба не "
    "запрашиваются.":
        "Request one tile or file from each source bypassing the cache and "
        "show the answer and the time. Large files such as the star sky image"
        " are not requested.",
    'Добавить подложку…':
        'Add base map…',
    "Окно нового источника тайлов. Источник записывается подключением XYZ "
    "Tiles QGIS и становится подложкой.":
        "The new tile source window. The source is saved as a QGIS XYZ Tiles "
        "connection and becomes the base map.",
    'Изменить…':
        'Edit…',
    "Адрес, название, уровни и подпись выбранной подложки из подключений XYZ "
    "Tiles QGIS.":
        "Address, name, levels and credit of the selected base map from the "
        "QGIS XYZ Tiles connections.",
    "Удалить выбранное подключение XYZ Tiles из QGIS. Оно пропадает и из "
    "обозревателя QGIS.":
        "Remove the selected XYZ Tiles connection from QGIS. It disappears "
        "from the QGIS browser too.",
    "Как высота записана в цвете тайла. Terrarium - как у рельефа по "
    "умолчанию, Mapbox Terrain-RGB - высота с шагом 0.1 м.":
        "How the height is written in the tile colour. Terrarium is as in the"
        " default terrain, Mapbox Terrain-RGB is the height in 0.1 m steps.",
    'Подпись своего рельефа в углу вида и на снимках.':
        'The credit of the own terrain in the view corner and on snapshots.',
    'Свой рельеф':
        'Own terrain',
    "Высоты суши 30 м с уровня 9":
        "Land heights of 30 m from level 9",
    "Модель высот 30 м поверх тайлов высот. Тайлы дают дно морей и вид "
    "издалека, ближе модель заменяет высоты суши. Copernicus DEM - "
    "поверхность вместе с лесом и домами, файлы на AWS. GEDTM30 - рельеф "
    "самой земли, один большой файл, загрузка медленнее. Модель читается "
    "из сети по участкам.":
        "A 30 m height model over the height tiles. The tiles give the sea "
        "floor and the view from afar, closer the model replaces the land "
        "heights. Copernicus DEM is the surface with forest and buildings, "
        "files on AWS. GEDTM30 is the bare ground, one large file, loading "
        "is slower. The model is read from the network piece by piece.",
    "Адрес TileJSON векторных тайлов в схеме OpenMapTiles. Из них берутся "
    "границы, дороги, воды, названия и 3D-здания. Пустое поле - OpenFreeMap.":
        "The TileJSON address of vector tiles in the OpenMapTiles schema. "
        "Borders, roads, waters, names and 3D buildings come from them. An "
        "empty field gives OpenFreeMap.",
    'Подпись своей основы в углу вида и на снимках.':
        'The credit of the own base in the view corner and on snapshots.',
    'Своя векторная основа':
        'Own vector base',
    'Применить':
        'Apply',
    'Глобус берёт данные по новому адресу.':
        'The globe takes the data from the new address.',
    'Как было':
        'Reset',
    'Вернуть источник по умолчанию.':
        'Return the default source.',
    'Снимок или карта под всеми слоями':
        'Imagery or a map under all layers',
    'Удалить подложку':
        'Remove base map',
    'Удалить подключение «{name}» из QGIS?':
        'Remove the connection “{name}” from QGIS?',
    'Источник':
        'Source',
    'Что показывает':
        'Shows',
    'Условия':
        'Terms',
    'Проверка':
        'Check',
    'Подложки':
        'Base maps',
    'ждём…':
        'waiting…',
    'ошибка':
        'error',
    '{ms} мс, {kb} КБ':
        '{ms} ms, {kb} KB',
    'Высоты суши и дна морей, уровни 0-15':
        'Heights of land and sea floor, levels 0-15',
    'Марс, Луна и другие тела':
        'Mars, the Moon and other bodies',
    "Высоты Марса и Луны - хранилище planetx-bodies-terrain, снимки - "
    "planetx-bodies-imagery, снимки других тел - planetx-terrain":
        "Heights of Mars and the Moon - the planetx-bodies-terrain store, "
        "their imagery - planetx-bodies-imagery, imagery of other bodies "
        "- planetx-terrain",
    'Границы, дороги, воды, названия, 3D-здания':
        'Borders, roads, waters, names, 3D buildings',
    'Облака, температура, темы, огни городов':
        'Clouds, temperature, themes, city lights',
    'Пожары за 24 часа':
        'Fires over 24 hours',
    'Млечный путь, около 10 МБ':
        'Milky Way, about 10 MB',
    'Землетрясения за 30 суток':
        'Earthquakes over 30 days',
    'Плиты на разрезах':
        'Slabs on sections',
    'Кора на разрезах':
        'Crust on sections',
    'Границы плит, файл модуля':
        'Plate boundaries, plugin file',
    'открыть':
        'open',
    'без проверки':
        'not checked',
    'Адрес рельефа - шаблон с {z}, {x} и {y}.':
        'The terrain address is a template with {z}, {x} and {y}.',
    'Адрес TileJSON начинается с http, https или file.':
        'A TileJSON address starts with http, https or file.',
    'Рельеф Земли':
        'Earth terrain',
    'Своя основа':
        'Own base',
    'Подключение XYZ Tiles QGIS':
        'QGIS XYZ Tiles connection',
    'Источник тайлов':
        'Tile source',
    'Рельеф: свой источник':
        'Terrain: own source',
    'Основа: свой источник':
        'Base: own source',
    "Пожары": "Fires",
    "Мощность пожара, МВт": "Fire power, MW",
    "Сводка пожаров не загрузилась: {error}":
        "The fire feed did not load: {error}",
    "Мощность излучения": "Radiative power",
    "{value} МВт": "{value} MW",
    "Время снимка, UTC": "Image time, UTC",
    "Достоверность": "Confidence",
    "Снимок": "Image",
    "ночной": "night",
    "дневной": "day",
    "Карьер, свой рельеф": "Quarry, own terrain",
    "Карьер, съёмка 1 м": "Quarry, 1 m survey",
    "Высоты растра заменяют рельеф глобуса в его охвате. На полосе вдоль "
    "края высоты плавно переходят к общему рельефу. Внутри охвата рельеф "
    "подробнее, до пикселя растра.":
        "The raster heights replace the globe terrain within its extent. "
        "Along a band at the edge the heights change smoothly to the "
        "common terrain. Within the extent the terrain is more detailed, "
        "down to the raster pixel.",
    "Растр «{name}» не стал рельефом глобуса: {why}.":
        "The raster “{name}” did not become globe terrain: {why}.",
    "Подземный режим": "Subsurface mode",
    "Пласты": "Beds",
    "Непрозрачность поверхности. Меньше - сквозь рельеф видны "
    "скважины и кровли пластов.":
        "Opacity of the surface. A lower value shows the drill holes and "
        "the bed roofs through the terrain.",
    "Непрозрачность поверхности": "Surface opacity",
    "Вырез блока": "Block cut",
    "Убрать поверхность и кровли внутри многоугольника выреза. "
    "По краю выреза видны пласты, на дне - низ модели.":
        "Remove the surface and the roofs inside the cut polygon. The beds "
        "show along the cut edge, the model bottom lies at its floor.",
    "Камера под землёй": "Camera under ground",
    "Камера опускается ниже рельефа до низа модели в её рамке. "
    "Над моделью камера ходит по её низу, а не по рельефу.":
        "The camera goes below the terrain down to the model bottom inside "
        "the model frame. Over the model the camera moves along its "
        "bottom, not along the terrain.",
    "GeoPackage (*.gpkg)": "GeoPackage (*.gpkg)",
    "Данных нет: нужны устья скважин, кровли пластов или тоннели.":
        "No data: drill hole collars, bed roofs or tunnels are needed.",
    "Тоннелей {count}.": "Tunnels: {count}.",
    "Скважины, кровли пластов, разрезы, тоннели и картинки разрезов - "
    "обычные слои проекта. Отмеченные в разделе «Слои проекта» встают под "
    "поверхность глобуса. Чтобы посмотреть, как это выглядит, откройте "
    "демо «Пермские отложения» и проведите тур кнопкой ▶ под «Моими "
    "метками». Чтобы начать со своими данными, создайте шаблон у точки "
    "взгляда.":
        "Drill holes, bed roofs, sections, tunnels and section images are "
        "ordinary project layers. Those checked in Project layers go under "
        "the globe surface. To see how it looks, open the Permian deposits "
        "demo and play its tour with the ▶ button under My Places. To start "
        "with your own data, create a template at the view point.",
    "Записать файл GeoPackage со всеми таблицами режима и примером у "
    "точки взгляда - скважина, разрез, тоннель и вырез - и добавить его в "
    "проект группой слоёв. Таблицы заполняются своими данными, глобус "
    "показывает их после правки.":
        "Write a GeoPackage file with all tables of the mode and an example "
        "at the view point - a drill hole, a section, a tunnel and a cut - "
        "and add it to the project as a group of layers. The tables are "
        "filled with your own data, the globe shows them after editing.",
    "Шаблон подземного": "Subsurface template",
    "Разрезов с картинками {count}.": "Image sections: {count}.",
    "Глубина оси": "Axis depth",
    "Отметка оси": "Axis elevation",
    "Диаметр": "Diameter",
    "Тоннель": "Tunnel",
    "Глубина по стволу": "Depth along hole",
    "Глубина под устьем": "Depth below collar",
    "Отметка": "Elevation",
    "Глубина забоя": "End of hole",
    "Пласт": "Bed",
    "Скважина {name}": "Drill hole {name}",
    "Подземное": "Subsurface",
    "Разрез модели…": "Model section…",
    "Стенка разреза модели": "Model section wall",
    "Вырез модели": "Model cut",
    "Вырез модели по «{name}».": "Model cut along \"{name}\".",
    "Вырез модели по «{name}» убран.":
        "Model cut along \"{name}\" removed.",
    "Стенка разреза по «{name}».": "Section wall along \"{name}\".",
    "Стенка разреза по «{name}» убрана.":
        "Section wall along \"{name}\" removed.",
    "Создать шаблон…": "Create template…",
    "Создать шаблон": "Create template",
    "Шаблон не записан: {error}": "Template not written: {error}",
    "Разрез модели: {name}": "Model section: {name}",
    "Разрез модели": "Model section",
    "Полоса скважин и объектов": "Band of holes and objects",
    "Ширина полосы вдоль линии, из которой скважины, тоннели "
    "и объекты с Z переносятся на разрез. Шире полоса - больше "
    "скважин, но дальние лежат не там, где линия.":
        "Width of the band along the line from which drill holes, tunnels "
        "and objects with Z are moved onto the section. A wider band gives "
        "more holes, but the far ones do not lie where the line is.",
    "Слои проекта на разрезе. Растры - кровли пластов, сверху "
    "вниз по порядку таблицы пластов или по средней отметке. "
    "Скважины - устья с интервалами и инклинометрией. Слои с Z - "
    "стенки «3D-забора» и линии с отметками в полосе вдоль "
    "линии.":
        "Project layers on the section. Rasters are bed roofs, from top "
        "to bottom by the order of the beds table or by the mean "
        "elevation. Drill holes are collars with intervals and surveys. "
        "Layers with Z are walls of a 3D fence and lines with elevations "
        "in the band along the line.",
    "Картинка…": "Picture…",
    "Разрез картинкой PNG в размере окна.":
        "The section as a PNG picture of the window size.",
    "Отметки по точкам линии - расстояние, широта, долгота, рельеф "
    "и кровли пластов, нет кровли - пустое поле.":
        "Elevations at the points of the line - distance, latitude, "
        "longitude, terrain and bed roofs, an empty field where there is "
        "no roof.",
    "Кровли - растры": "Roofs - rasters",
    "Скважины": "Drill holes",
    "Скважины проекта": "Project drill holes",
    "Слои с Z": "Layers with Z",
    "В проекте нет растров, скважин и слоёв с Z":
        "The project has no rasters, drill holes or layers with Z",
    "Разрез картинкой": "Section as a picture",
    "Разрез таблицей": "Section as a table",
    "Нужны путь хотя бы из двух точек и слой разреза - растр "
    "кровли, скважины или слой с Z.":
        "A path of at least two points and a section layer - a roof "
        "raster, drill holes or a layer with Z - are needed.",
    "Длина {length}. Кровель {beds}, скважин в полосе {holes}, "
    "тоннелей {tunnels}, частей объектов с Z {fences}.":
        "Length {length}. Roofs {beds}, holes in the band {holes}, "
        "tunnels {tunnels}, parts of objects with Z {fences}.",
    "рельеф {value}": "terrain {value}",
    "Скважин {holes}, кровель {horizons}, разрезов "
    "{sections}. Вершин {vertices}.":
        "Drill holes {holes}, roofs {horizons}, sections {sections}. "
        "Vertices {vertices}.",
    "Не найдены {names}.": "Not found: {names}.",
    "Пропущено строк - {count}.": "Rows skipped: {count}.",
    "Инсоляция": "Insolation",
    "Первые сутки промежутка. Итог - среднее количество часов "
    "прямого солнца в сутки за промежуток.":
        "The first day of the period. The result is the mean number of "
        "hours of direct sunlight per day over the period.",
    "Последние сутки промежутка, включительно. Длинный промежуток "
    "считается по 15 суткам, взятым равномерно.":
        "The last day of the period, inclusive. A long period is computed "
        "over 15 evenly spaced days.",
    "Первые сутки": "First day",
    "Последние сутки": "Last day",
    "Прямое солнце, ч в сутки": "Direct sun, h per day",
    "За {days} сут. прямое солнце светит от {low} "
    "до {high} ч в сутки. Шаг сетки - {step} м.":
        "Over {days} days direct sun shines from {low} to {high} h per "
        "day. The grid step is {step} m.",
    "Инсоляция считается только для Земли.":
        "Insolation is computed only for the Earth.",
    "Расчёт инсоляции: {share}": "Computing insolation: {share}",
    "Высоты узлов сетки: {share}": "Heights of the grid nodes: {share}",
    "К началу шкалы": "To the start of the slider",
    "К концу шкалы": "To the end of the slider",
    "Проигрывание по кругу. Дойдя до конца шкалы, промежуток "
    "начинает с начала.":
        "Play in a loop. At the end of the slider the interval starts "
        "again from the beginning.",
    "Закрыть шкалу времени. Закрытая шкала метки "
    "не скрывает.":
        "Close the time slider. A closed slider does not hide placemarks.",
    "Скорость проигрывания. «Шкала за 20 с» проходит всю шкалу "
    "за 20 секунд. ×1 - время идёт как на часах, ×3600 - час "
    "за секунду, ×86400 - сутки за секунду.":
        "Playback speed. Slider in 20 s crosses the whole slider in 20 "
        "seconds. ×1 - time runs as on a clock, ×3600 - an hour per "
        "second, ×86400 - a day per second.",
    "Шкала за 20 с": "Slider in 20 s",
    "Сейчас": "Now",
    "Момент - по часам компьютера, время идёт со скоростью ×1. "
    "Солнце и спутники встают на свои места в настоящий момент.":
        "The moment follows the computer clock, time runs at ×1. The "
        "Sun and the satellites take their places at the present "
        "moment.",
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
    "Взять вид глобуса сейчас: точку взгляда, расстояние, азимут, "
    "наклон и включённые строки раздела «Слои».":
        "Take the current globe view: look point, range, heading, tilt "
        "and the rows switched on in the Layers section.",
    "как у тура": "as in the tour",
    "Окно с полными подписями, ссылками и условиями всех "
    "источников, которые показывает глобус.":
        "The window with the full credits, links and terms of all sources "
        "the globe shows.",
    "Пауза в туре": "Tour pause",
    "Скорость перелёта": "Flight speed",
    "Сколько секунд камера стоит на этой остановке тура. "
    "«Как у тура» - пауза с панели тура.":
        "How many seconds the camera stays at this tour stop. As in the "
        "tour - the pause from the tour panel.",
    "Во сколько раз перелёт тура к этой метке быстрее обычного. "
    "Меньше единицы - медленнее, плавнее для показа.":
        "How many times faster than usual the tour flies to this "
        "placemark. Below one - slower, smoother for a show.",
    "Слои глобуса со снимка, включено строк {count}":
        "Globe layers from the snapshot, rows switched on: {count}",
    "Строки раздела «Слои», которые были включены при снимке вида. "
    "Перелёт к метке и тур включают их и выключают остальные - "
    "так остановка тура показывает свои слои. Снимок текущего "
    "вида запоминает их заново.":
        "Rows of the Layers section that were switched on at the view "
        "snapshot. A flight to the placemark and a tour switch them on and "
        "the others off - so a tour stop shows its own layers. A new "
        "snapshot of the current view takes them again.",
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
    "Полёт отсюда": "Fly from here",
    "Светлое": "Light",
    "Тёмное": "Dark",
    "Оформление окна глобуса. «Как в QGIS» - тёмные плашки на виде, "
    "окна модуля в оформлении QGIS. «Светлое» - серые плашки с тёмными "
    "значками и светлые окна. «Тёмное» - тёмные плашки и тёмные окна. "
    "Оформление меняется сразу.":
        "Look of the globe window. As in QGIS - dark plates on the view, "
        "module windows in the QGIS look. Light - grey plates with dark "
        "icons and light windows. Dark - dark plates and dark windows. The "
        "look changes at once.",
    "Истребитель": "Fighter jet",
    "Подъём {climb} м/с": "Climb {climb} m/s",
    "Над землёй {height} м": "Above ground {height} m",
    "Тяга {throttle} %": "Thrust {throttle} %",
    "↑ ↓ - нос вниз и вверх · ← → - крен · PageUp, PageDown - тяга · "
    "V - вид из кабины · H - приборы · Esc - выход":
        "↑ ↓ - nose down and up · ← → - bank · PageUp, PageDown - thrust "
        "· V - cockpit view · H - instruments · Esc - exit",
    "Винтовой самолёт": "Propeller aircraft",
    "До 2000 км/ч, старт 900 км/ч, резкий крен.":
        "Up to 2000 km/h, starts at 900 km/h, quick bank.",
    "До 340 км/ч, старт 250 км/ч, плавный.":
        "Up to 340 km/h, starts at 250 km/h, smooth.",
    "Касание земли - полёт окончен.":
        "Touched the ground - the flight is over.",
    "{speed} км/ч · высота {alt} м, над землёй {height} м · "
    "курс {heading}° · подъём {climb} м/с · тяга {throttle} %":
        "{speed} km/h · altitude {alt} m, above ground {height} m · "
        "heading {heading}° · climb {climb} m/s · thrust {throttle} %",
    "км/ч": "km/h",
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
    "Поделиться видом…": "Share View…",
    "Поделиться видом": "Share view",
    "Страница HTML с глобусом, она открывается в браузере без QGIS. "
    "На ней камера этого вида, рельеф, основа OpenStreetMap "
    "и выделенные в «Моих метках» метки с облётом.":
        "An HTML page with the globe that opens in a browser without "
        "QGIS. It holds the camera of this view, the terrain, the "
        "OpenStreetMap base and the placemarks selected in My Places "
        "with a tour.",
    "Исходный вид": "Initial view",
    "▶ Облёт": "▶ Tour",
    "⏹ Остановить": "⏹ Stop",
    "Страница строится только для Земли. Вернитесь на Землю "
    "и повторите.":
        "The page is built for the Earth only. Return to the Earth and "
        "try again.",
    "Страница HTML (*.html)": "HTML page (*.html)",
    "Страница записана: {path}": "Page written: {path}",
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
    "{date} до н. э.": "{date} BC",
    "Палеогеография": "Paleogeography",
    "Рельеф суши и глубины моря в прошлом, до 540 млн лет назад, по "
    "картам PaleoDEM PALEOMAP. Возраст задаёт ползунок в левом нижнем "
    "углу вида. Снимок, границы и подписи на это время убраны.":
        "Land relief and sea depths in the past, up to 540 million years "
        "ago, after the PALEOMAP PaleoDEM maps. The slider in the lower "
        "left corner of the view sets the age. The imagery, borders and "
        "labels are removed meanwhile.",
    "Планета огня": "Planet of Fire",
    "Планета воды": "Planet of Water",
    "Земля и жизнь": "Land and Life",
    "Дым, аэрозольный индекс": "Smoke, aerosol index",
    "Поглощающий аэрозоль - дым пожаров и пыль - по OMPS за сутки, "
    "с 2012 года.":
        "Absorbing aerosol - smoke of fires and dust - from OMPS per day, "
        "since 2012.",
    "Оптическая толщина аэрозоля": "Aerosol optical depth",
    "Насколько воздух ослабляет свет из-за дыма, пыли и смога, MODIS "
    "за сутки, с 2017 года.":
        "How much the air dims light because of smoke, dust and smog, "
        "MODIS per day, since 2017.",
    "Угарный газ": "Carbon monoxide",
    "Доля угарного газа на высоте около 5 км по AIRS за сутки, "
    "с 2002 года. Шлейфы пожаров видны на тысячи километров.":
        "Carbon monoxide mixing ratio at about 5 km from AIRS per day, "
        "since 2002. Fire plumes are seen over thousands of kilometres.",
    "Выбросы угарного газа": "Carbon monoxide emission",
    "Выбросы угарного газа у поверхности по реанализу MERRA-2 за месяц, "
    "с 1980 года. Ряд отстаёт на несколько месяцев.":
        "Surface carbon monoxide emission from the MERRA-2 reanalysis per "
        "month, since 1980. The series lags by several months.",
    "Интенсивность осадков IMERG за сутки, с 2000 года.":
        "IMERG precipitation rate per day, since 2000.",
    "Влажность почвы": "Soil moisture",
    "Влажность верхних сантиметров почвы по SMAP за сутки, "
    "с 2015 года. В ряду бывают пропущенные дни.":
        "Moisture of the top centimetres of soil from SMAP per day, since "
        "2015. The series has missing days.",
    "Снежный покров": "Snow cover",
    "Снег по снимкам MODIS Terra за сутки, с 2000 года. Под облаками и в "
    "полярную ночь пропуски, моря и озёра не раскрашиваются.":
        "Snow from MODIS Terra imagery per day, since 2000. There are gaps "
        "under clouds and in the polar night, seas and lakes are not "
        "coloured.",
    "Снег за 8 суток":
        "Snow over 8 days",
    "Снег и лёд на озёрах по снимкам MODIS Terra, сводка за 8 суток, с 2000 "
    "года. Пропусков под облаками меньше, чем в суточном слое.":
        "Snow and lake ice from MODIS Terra imagery, an 8-day summary, since "
        "2000. There are fewer gaps under clouds than in the daily layer.",
    "Масса снега":
        "Snow mass",
    "Запас снега в килограммах на квадратный метр по модели SMAP Level 4 за "
    "сутки, с 2015 года, ячейка около 9 км. Это расчёт модели по данным "
    "спутника, облака пропусков не дают.":
        "Snow amount in kilograms per square metre from the SMAP Level 4 "
        "model per day, since 2015, a cell of about 9 km. It is a model "
        "calculation from satellite data, clouds leave no gaps.",
    "Морской лёд": "Sea ice",
    "Сплочённость морского льда по GHRSST MUR за сутки, с 2002 года.":
        "Sea ice concentration from GHRSST MUR per day, since 2002.",
    "Водяной пар": "Water vapour",
    "Водяной пар в толще атмосферы по MODIS Terra за сутки, "
    "с 2000 года.":
        "Water vapour in the atmospheric column from MODIS Terra per day, "
        "since 2000.",
    "Хлорофилл": "Chlorophyll",
    "Хлорофилл водорослей в поверхностном слое моря по PACE за сутки, "
    "с 2024 года.":
        "Algae chlorophyll in the surface layer of the sea from PACE per "
        "day, since 2024.",
    "Солёность моря": "Sea salinity",
    "Солёность поверхности моря по SMAP, скользящее среднее за 8 суток, "
    "с 2015 года.":
        "Sea surface salinity from SMAP, an 8-day running mean, since "
        "2015.",
    "Наводнения": "Floods",
    "Вода, вышедшая за обычные берега, по MODIS за 3 суток, "
    "с 2021 года.":
        "Water beyond its usual banks from MODIS over 3 days, since 2021.",
    "Диоксид азота": "Nitrogen dioxide",
    "Диоксид азота в тропосфере по TROPOMI за сутки, с 2018 года. "
    "Видны города, дороги и электростанции.":
        "Tropospheric nitrogen dioxide from TROPOMI per day, since 2018. "
        "Cities, roads and power plants are seen.",
    "Диоксид серы": "Sulphur dioxide",
    "Диоксид серы у поверхности по OMPS за сутки, с 2012 года. Видны "
    "вулканы и заводы.":
        "Near-surface sulphur dioxide from OMPS per day, since 2012. "
        "Volcanoes and plants are seen.",
    "Метан": "Methane",
    "Доля метана на высоте около 7 км по AIRS за месяц, с 2002 года.":
        "Methane mixing ratio at about 7 km from AIRS per month, since "
        "2002.",
    "Углекислый газ": "Carbon dioxide",
    "Среднее содержание углекислого газа в столбе атмосферы по OCO-2, "
    "полосы витков за сутки, с 2014 года. Ряд отстаёт на несколько "
    "месяцев.":
        "Column-average carbon dioxide from OCO-2, orbit swaths per day, "
        "since 2014. The series lags by several months.",
    "Озон": "Ozone",
    "Общее содержание озона по OMI за сутки, с 2004 года. Видна "
    "озоновая дыра над Антарктидой.":
        "Total column ozone from OMI per day, since 2004. The ozone hole "
        "over Antarctica is seen.",
    "Растительность": "Vegetation",
    "Индекс растительности NDVI по MODIS Terra за 16 суток, "
    "с 2000 года. Ряд отстаёт на месяц.":
        "NDVI vegetation index from MODIS Terra over 16 days, since 2000. "
        "The series lags by a month.",
    "Пыль": "Dust",
    "Пыль в атмосфере по AIRS за сутки, с 2002 года.":
        "Dust in the atmosphere from AIRS per day, since 2002.",
    "Ночные огни": "Night lights",
    "Ночной снимок VIIRS за сутки, с 2021 года. Видны огни городов, "
    "пожары, факелы и полярные сияния.":
        "VIIRS night image per day, since 2021. City lights, fires, gas "
        "flares and auroras are seen.",
    "{name}, {units} · {day}": "{name}, {units} · {day}",
    "{name} · {day}": "{name} · {day}",
    "У темы нет дат в ряду.": "The theme has no dates in its series.",
    "Ряд дат темы не загрузился: {error}":
        "The date series of the theme failed to load: {error}",
    "Возраст в миллионах лет назад. Карта рельефа и глубин на этот "
    "возраст - PaleoDEM PALEOMAP, Scotese и Wright 2018.":
        "Age in millions of years ago. The map of relief and depths for "
        "this age is the PALEOMAP PaleoDEM, Scotese and Wright 2018.",
    "Показ от выбранного возраста к настоящему по всем картам набора.":
        "Plays from the chosen age to the present through all maps of "
        "the set.",
    "{age} млн лет назад, {period}": "{age} Myr ago, {period}",
    "{age} млн лет назад": "{age} Myr ago",
    "Настоящее": "Present",
    "Четвертичный период": "Quaternary", "Неоген": "Neogene",
    "Палеоген": "Paleogene", "Мел": "Cretaceous", "Юра": "Jurassic",
    "Триас": "Triassic", "Пермский период": "Permian",
    "Карбон": "Carboniferous", "Девон": "Devonian", "Силур": "Silurian",
    "Ордовик": "Ordovician", "Кембрий": "Cambrian",
    "Докембрий": "Precambrian",
    "Добавить вершину": "Add a vertex",
    "Замкнуть фигуру": "Close the shape",
    "Завершить путь": "Finish the path",
    "Удалить вершину": "Delete vertex",
    "Продолжить рисование": "Continue drawing",
    "Завершить рисование": "Finish drawing",
    "Добавить метку здесь": "Add placemark here",
    "Щелчок по глобусу ставит метку. Метка перетаскивается мышью.":
        "A click on the globe sets the placemark. The placemark can be "
        "dragged with the mouse.",
    "Щелчками по глобусу отметьте точки пути. Щелчок по последней точке "
    "завершает путь, по первой - замыкает фигуру.":
        "Click on the globe to mark the path points. A click on the last "
        "point finishes the path, a click on the first one closes the "
        "shape.",
    "Щелчками по глобусу отметьте вершины многоугольника. Щелчок по "
    "первой вершине завершает рисование.":
        "Click on the globe to mark the polygon vertices. A click on the "
        "first vertex finishes drawing.",
    "Вершины перетаскиваются мышью. Кружок в середине отрезка ставит "
    "новую вершину. Правая кнопка открывает меню.":
        "Vertices are dragged with the mouse. The circle in the middle of "
        "a segment adds a new vertex. The right button opens the menu.",
    "CelesTrak":
        "CelesTrak",
    "NASA FIRMS, 24 часа":
        "NASA FIRMS, 24 hours",
    "NASA GIBS":
        "NASA GIBS",
    "NASA GIBS, {day}":
        "NASA GIBS, {day}",
    "NASA GIBS, суша и море":
        "NASA GIBS, land and sea",
    "OpenFreeMap":
        "OpenFreeMap",
    "{name}. Флажок выключает слой, строка остаётся. Меню «⋯» - "
    "непрозрачность, в проект QGIS, убрать с глобуса.":
        "{name}. The check switches the layer off, the row stays. The ⋯ menu "
        "sets the opacity, saves to the QGIS project or removes the layer "
        "from the globe.",
    "Видимое на глобусе слоем в проект QGIS - объекты в рамке вида или "
    "картинка карты.":
        "What is on the globe as a layer in the QGIS project - features in "
        "the view frame or the map picture.",
    "Все карты и слои каталога.":
        "All maps and layers of the catalogue.",
    "Всё, что сейчас на глобусе, - слои, слои проекта QGIS, основа и рельеф. "
    "Кнопка «Добавить данные» открывает каталог карт NASA, погоды, слоёв недр "
    "и инфраструктуры.":
        "Everything on the globe now - layers, QGIS project layers, the base "
        "map and relief. The Add data button opens the catalogue of NASA "
        "maps, weather, subsurface and infrastructure layers.",
    "Добавить данные":
        "Add data",
    "Карта на глобусе - одна":
        "One map on the globe",
    "Каталог карт и слоёв - карты NASA, прогноз погоды, пожары, небо, недра, "
    "инфраструктура, анализ рельефа и строки векторной основы. Каталог "
    "открывается отдельным окном, его можно держать открытым рядом "
    "с глобусом.":
        "The catalogue of maps and layers - NASA maps, weather forecast, "
        "fires, sky, subsurface, infrastructure, terrain analysis and the "
        "vector base rows. The catalogue opens as a separate window, it can "
        "stay open next to the globe.",
    "Отметка показывает слой на глобусе, видимость на карте QGIS не меняется. "
    "Двойной щелчок переносит к слою, меню «⋯» - перелёт, прозрачность, роль "
    "на глобусе и свойства.":
        "The check shows the layer on the globe, its visibility on the QGIS "
        "map does not change. Double-clicking flies to the layer, the ⋯ menu "
        "flies there, sets opacity, the role on the globe and opens "
        "properties.",
    "Проект QGIS":
        "QGIS project",
    "Свернуть или развернуть слои на глобусе.":
        "Collapse or expand the layers on the globe.",
    "Слои - включаются вместе":
        "Layers - switched on together",
    "Слои текущего проекта QGIS в порядке карты. Отметка показывает слой на "
    "глобусе, видимость на карте QGIS не меняется. Меню слоя - «⋯» справа или "
    "правая кнопка.":
        "Layers of the current QGIS project in map order. The check shows the "
        "layer on the globe, its visibility on the QGIS map does not change. "
        "The layer menu is the ⋯ on the right or the right button.",
    "Флажок показывает карту или слой на глобусе. Строка - описание. Карта на "
    "глобусе одна, слои включаются вместе с ней.":
        "The check shows a map or a layer on the globe. A row shows its "
        "description. There is one map on the globe, layers are switched on "
        "together with it.",
    "прогноз NOAA GFS":
        "NOAA GFS forecast",
    "снег, рудники, ветер":
        "snow, mines, wind",
    "Copernicus 30 м":
        "Copernicus 30 m",
    "3DEP 10 м":
        "3DEP 10 m",
    "Векторная основа OpenFreeMap, координатная сетка, 3D-здания и "
    "горизонтали.":
        "The OpenFreeMap vector base, the coordinate grid, 3D buildings and "
        "contours.",
    "Высоты поднимают поверхность и дают отмывку склонов. Флажок включает "
    "рельеф, щелчок по названию - выбор высот суши и глубины морей. Высоты "
    "Земли - Mapzen Terrain Tiles, Марса - MOLA, Луны - LOLA. Вертикальный "
    "масштаб - в свойствах вида.":
        "Heights raise the surface and shade the slopes. The check turns "
        "relief on, a click on the name chooses the land heights and sea "
        "depths. Earth heights are Mapzen Terrain Tiles, Mars - MOLA, the "
        "Moon - LOLA. The vertical scale is in the view properties.",
    "Дно морей и океанов ниже нуля и вода над ним. Без флажка поверхность "
    "моря ровная, на уровне нуля.":
        "The sea and ocean floor below zero and the water over it. Without "
        "the check the sea surface is flat at zero.",
    "Основа · {name}":
        "Base map · {name}",
    "Рельеф · {name}":
        "Relief · {name}",
    "Снимки или карта на поверхности. Щелчок по строке - выбор подложки и "
    "свой источник тайлов. Esri World Imagery - пример подложки, условия её "
    "использования задаёт Esri.":
        "Imagery or a map on the surface. A click on the row chooses the base "
        "map or adds a tile source of your own. Esri World Imagery is an "
        "example base map, Esri sets its terms of use.",
    "Электростанции мира, линии электропередачи, подстанции, трубопроводы и "
    "подводные кабели.":
        "Power plants of the world, power lines, substations, pipelines and "
        "submarine cables.",
    "Энергетика":
        "Energy",
    "свой источник":
        "own source",
    # 3D-модели.
    "3D-модель": "3D model",
    "3D-модель…": "3D model…",
    "3D-модели (*.dae *.gltf *.glb *.obj *.kmz)":
        "3D models (*.dae *.gltf *.glb *.obj *.kmz)",
    "Модель не читается: {name}": "The model cannot be read: {name}",
    "Модель не читается: {error}": "The model cannot be read: {error}",
    "Модель не читается.": "The model cannot be read.",
    "Треугольников {count}, материалов {parts}, картинок {images}. "
    "Размер {x:.1f} × {y:.1f} × {z:.1f} м.":
        "Triangles {count}, materials {parts}, images {images}. "
        "Size {x:.1f} × {y:.1f} × {z:.1f} m.",
    "Анимированная модель, ветряки": "Animated model, wind turbines",
    "Поезда Финляндии, вживую": "Trains of Finland, live",
    "Самосвалы, Качканар": "Haul trucks, Kachkanar",
    "Самосвалы, Лебединский": "Haul trucks, Lebedinsky",
    "Самосвалы, Качканар, слой QGIS": "Haul trucks, Kachkanar, QGIS layer",
    "Самосвалы, Лебединский, слой QGIS":
        "Haul trucks, Lebedinsky, QGIS layer",
    "Самосвалы в карьере": "Haul trucks in the pit",
    "Самосвалы": "Haul trucks",
    "Анимация {seconds:.1f} с, движется частей {tracks}.":
        "Animation {seconds:.1f} s, moving parts {tracks}.",
    "Широта точки модели. Точка - начало координат файла модели.":
        "Latitude of the model point. The point is the origin of the "
        "model file coordinates.",
    "Долгота точки модели.": "Longitude of the model point.",
    "Высота точки модели. Над рельефом - подъём над землёй, над уровнем "
    "моря - высота от уровня моря. На рельефе высота не действует.":
        "Height of the model point. Above terrain is the rise above the "
        "ground, above sea level is the height from sea level. On terrain "
        "the height has no effect.",
    "Поворот модели по часовой стрелке, если смотреть сверху. Ноль - ось "
    "Y модели смотрит на север.":
        "Clockwise turn of the model as seen from above. At zero the Y "
        "axis of the model points north.",
    "Наклон модели вокруг её оси X.":
        "Tilt of the model around its X axis.",
    "Крен": "Roll",
    "Крен модели вокруг её оси Y.": "Roll of the model around its Y axis.",
    "Отсчёт высоты": "Altitude mode",
    "От чего отсчитывается высота модели, как altitudeMode в KML.":
        "What the model height is measured from, as altitudeMode in KML.",
    "На рельефе": "On terrain",
    "Над рельефом": "Above terrain",
    "Над уровнем моря": "Above sea level",
    "Масштаб модели. Единица - размеры из файла модели. Поле меняет "
    "масштаб по всем осям сразу, разный масштаб осей из KML сохраняется "
    "в их отношении.":
        "Scale of the model. One means the sizes from the model file. The "
        "field changes the scale of all axes at once, different axis "
        "scales from KML keep their ratio.",
    "Открывает руководство PDF программой системы. Без файла "
    "в папке модуля руководство открывает браузер из выпуска "
    "этой версии на GitHub.":
        "Opens the PDF manual with the system program. Without the file "
        "in the plugin folder the browser opens the manual from the "
        "GitHub release of this version.",
    "Открывает в браузере список сообщений об ошибках "
    "в хранилище модуля на GitHub.":
        "Opens the list of bug reports of the plugin repository "
        "on GitHub in the browser.",
    "Открывает в браузере страницу модуля на сайте "
    "ООО «Информ++».":
        "Opens the plugin page on the Inform++ LLC website "
        "in the browser.",
    "Открывает в браузере хранилище модуля на GitHub.":
        "Opens the plugin repository on GitHub in the browser.",
    "Открывает в браузере страницу PlanetX Lite - глобуса PlanetX "
    "без QGIS, отдельной программой.":
        "Opens the page of PlanetX Lite, the PlanetX globe without QGIS "
        "as a separate program, in the browser.",
    "Открывает в браузере страницу модуля в каталоге "
    "модулей QGIS.":
        "Opens the plugin page in the QGIS plugin catalog "
        "in the browser.",
    "Бот в Telegram": "Telegram bot",
    "Открывает бота PlanetX в Telegram. Бот находит разделы "
    "руководства по вопросу, показывает последний выпуск "
    "и передаёт сообщения разработчикам.":
        "Opens the PlanetX bot in Telegram. The bot finds manual sections "
        "for a question, shows the latest release and passes messages "
        "to the developers.",
    "Система не открыла {target}.":
        "The system did not open {target}.",
    "Система не открыла файл руководства {path}. "
    "Открыть руководство в браузере?":
        "The system did not open the manual file {path}. "
        "Open the manual in the browser?",
    "Система не открыла журнал {path}.":
        "The system did not open the log {path}.",
    # Ряд по датам, ui/series.py.
    "Ряд по датам…": "Time series…",
    "Ряд по датам": "Time series",
    "График индекса или температуры участка по всем сценам списка - "
    "медиана участка без облаков на каждую дату. Щелчок по точке "
    "графика выбирает сцену в списке. У сочетаний каналов и у "
    "ASTER ряда нет.":
        "A chart of an index or the temperature of the area over all "
        "scenes of the list - the median of the area without clouds on "
        "each date. A click on a point of the chart selects the scene in "
        "the list. Band composites and ASTER have no series.",
    "Нет точек ряда": "No points in the series",
    "{when}: медиана {median}, 10-90 % {low} - {high}, "
    "без облаков {share} % участка":
        "{when}: median {median}, 10-90 % {low} - {high}, "
        "{share} % of the area without clouds",
    "Величина ряда. Точка - медиана по участку без облаков и теней, "
    "отрезок - от 10-го до 90-го процентиля. Смена величины "
    "считает ряд заново.":
        "The value of the series. A point is the median over the area "
        "without clouds and shadows, a bar runs from the 10th to the 90th "
        "percentile. A change of the value computes the series again.",
    "Таблица CSV…": "CSV table…",
    "Ряд в файл CSV - дата и номер сцены, медиана, 10-й и 90-й "
    "процентили, доля участка без облаков. Сцены без значения "
    "идут пустыми строками.":
        "The series to a CSV file - the date and the scene, the median, "
        "the 10th and 90th percentiles, the share of the area without "
        "clouds. Scenes without a value are rows with empty fields.",
    "Величина": "Value",
    "Участок: {name}, сцен {count}": "Area: {name}, scenes {count}",
    "Облачность остальных сцен ещё считается, "
    "кнопка «Ряд по датам…» потом добавит их.":
        "The cloud cover of the other scenes is still being computed, "
        "the Time series… button adds them later.",
    "Нет сцен для ряда.": "No scenes for the series.",
    "Считается ряд: 0 из {total}…":
        "Computing the series: 0 of {total}…",
    "Считается ряд: {done} из {total}, точек {count}…":
        "Computing the series: {done} of {total}, points {count}…",
    "Точек {count} из {total}. Сцены без точки - участок закрыт "
    "облаками больше чем на {share} % или файлы не прочитаны.":
        "Points {count} of {total}. A scene without a point has clouds "
        "over more than {share} % of the area, or its files were not "
        "read.",
    "Ряд в CSV": "Series to CSV",
    "Ряд записан: {path}": "Series written: {path}",
    # Литология, воды, почвы, исторические землетрясения.
    "Повторяемость воды 1984-2021, %": "Water occurrence 1984-2021, %",
    "Глина в почве 0-5 см, %": "Clay in soil 0-5 cm, %",
    "Песок в почве 0-5 см, %": "Sand in soil 0-5 cm, %",
    "Органический углерод почвы 0-5 см, г/кг":
        "Soil organic carbon 0-5 cm, g/kg",
    "Кислотность почвы 0-5 см, pH в воде": "Soil pH 0-5 cm, in water",
    "Литология GLiM": "GLiM lithology",
    "Изменения воды 1984-2021 JRC": "Water transitions 1984-2021, JRC",
    "Рыхлые отложения": "Unconsolidated sediments",
    "Обломочные осадочные породы": "Siliciclastic sedimentary rocks",
    "Смешанные осадочные породы": "Mixed sedimentary rocks",
    "Карбонатные осадочные породы": "Carbonate sedimentary rocks",
    "Эвапориты": "Evaporites",
    "Пирокластика": "Pyroclastics",
    "Кислые вулканические породы": "Acid volcanic rocks",
    "Средние вулканические породы": "Intermediate volcanic rocks",
    "Основные вулканические породы": "Basic volcanic rocks",
    "Кислые плутонические породы": "Acid plutonic rocks",
    "Средние плутонические породы": "Intermediate plutonic rocks",
    "Основные плутонические породы": "Basic plutonic rocks",
    "Метаморфические породы": "Metamorphic rocks",
    "Лёд и ледники": "Ice and glaciers",
    "Постоянная вода": "Permanent water",
    "Новая постоянная вода": "New permanent water",
    "Исчезнувшая постоянная вода": "Lost permanent water",
    "Сезонная вода": "Seasonal water",
    "Новая сезонная вода": "New seasonal water",
    "Исчезнувшая сезонная вода": "Lost seasonal water",
    "Сезонная стала постоянной": "Seasonal to permanent",
    "Постоянная стала сезонной": "Permanent to seasonal",
    "Временная постоянная вода": "Ephemeral permanent water",
    "Временная сезонная вода": "Ephemeral seasonal water",
    "Щелчок - класс в точке": "Click - the class at the point",
    "Почвы": "Soils",
    "Свойства верхнего слоя почвы 0-5 см по SoilGrids - глина, песок, "
    "органический углерод и кислотность, сетка 250 м.":
        "Properties of the topsoil 0-5 cm from SoilGrids - clay, sand, "
        "organic carbon and pH, a 250 m grid.",
    "Исторические землетрясения": "Historical earthquakes",
    "Сильные землетрясения мира с 1904 по 2024 год по каталогу ISC-GEM "
    "- около 74 тысяч событий магнитудой от 5, места, глубины и магнитуды "
    "пересчитаны одним способом. Кружок стоит в эпицентре, на своей "
    "глубине - в вынутом секторе разреза Земли, цвет показывает "
    "глубину, размер - магнитуду. Промежуток шкалы "
    "времени отбирает события. Щелчок по кружку показывает место, дату, "
    "магнитуду и страницу события USGS. Первое включение скачивает "
    "каталог по частям, около 13 МБ.":
        "Strong earthquakes of the world from 1904 to 2024 from the "
        "ISC-GEM catalogue - about 74 thousand events of magnitude 5 and "
        "above, with locations, depths and magnitudes recomputed in one "
        "way. A circle sits at the epicentre, at its depth - in the "
        "removed sector of the Earth cutaway, the colour shows "
        "the depth and the size the magnitude. The time slider range "
        "selects the events. A click on a circle shows the place, date, "
        "magnitude and the USGS event page. The first use downloads the "
        "catalogue in parts, about 13 MB.",
    "Литологическая карта мира GLiM - породы на поверхности 16 классами: "
    "рыхлые отложения, осадочные, вулканические, плутонические "
    "и метаморфические породы, лёд. Карта сведена из 92 региональных "
    "карт, масштаб около 1:3 750 000. Щелчок в режиме «Определить "
    "объекты» показывает класс пород. На глобусе одна такая карта - "
    "литологическая, геологическая, почвенная, водная или карта значений "
    "геофизики.":
        "The GLiM lithological map of the world - surface rocks in 16 "
        "classes: unconsolidated sediments, sedimentary, volcanic, "
        "plutonic and metamorphic rocks, ice. It is compiled from 92 "
        "regional maps at a scale of about 1:3 750 000. A click in "
        "Identify features mode shows the rock class. The globe shows "
        "one such map - lithological, geological, soil, water or a "
        "geophysical value map.",
    "Повторяемость воды": "Water occurrence",
    "Как часто место было покрыто водой с 1984 по 2021 год по снимкам "
    "Landsat - доля наблюдений с водой, Global Surface Water JRC. Синие - "
    "вода всегда, красные - вода бывает редко. Пиксель 30 м. Щелчок "
    "в режиме «Определить объекты» показывает повторяемость в процентах.":
        "How often a place was covered by water from 1984 to 2021 in "
        "Landsat images - the share of observations with water, JRC "
        "Global Surface Water. Blue is always water, red is rarely "
        "water. The pixel is 30 m. A click in Identify features mode "
        "shows the occurrence in percent.",
    "Изменения воды": "Water transitions",
    "Что стало с водой с 1984 по 2021 год по снимкам Landsat - постоянная "
    "и сезонная вода, новая и исчезнувшая, переходы между ними, Global "
    "Surface Water JRC. Видны новые водохранилища, обмелевшие озёра "
    "и блуждающие русла. Щелчок в режиме «Определить объекты» "
    "показывает класс.":
        "What happened to water from 1984 to 2021 in Landsat images - "
        "permanent and seasonal water, new and lost, transitions between "
        "them, JRC Global Surface Water. New reservoirs, shrunken lakes "
        "and migrating channels are visible. A click in Identify "
        "features mode shows the class.",
    "Глина в почве": "Clay in soil",
    "Доля глинистых частиц в слое почвы 0-5 см по SoilGrids ISRIC - "
    "модель по 240 тысячам почвенных разрезов, сетка 250 м. Щелчок "
    "в режиме «Определить объекты» запрашивает значение у SoilGrids.":
        "The share of clay particles in the soil layer 0-5 cm from ISRIC "
        "SoilGrids - a model built on 240 thousand soil profiles, a "
        "250 m grid. A click in Identify features mode asks SoilGrids "
        "for the value.",
    "Песок в почве": "Sand in soil",
    "Доля песчаных частиц в слое почвы 0-5 см по SoilGrids ISRIC, сетка "
    "250 м. Щелчок в режиме «Определить объекты» запрашивает значение "
    "у SoilGrids.":
        "The share of sand particles in the soil layer 0-5 cm from ISRIC "
        "SoilGrids, a 250 m grid. A click in Identify features mode asks "
        "SoilGrids for the value.",
    "Органический углерод почвы": "Soil organic carbon",
    "Содержание органического углерода в слое почвы 0-5 см по SoilGrids "
    "ISRIC, г/кг, сетка 250 м. Больше всего его в торфяниках тундры "
    "и тайги. Щелчок в режиме «Определить объекты» запрашивает значение "
    "у SoilGrids.":
        "Organic carbon content of the soil layer 0-5 cm from ISRIC "
        "SoilGrids, g/kg, a 250 m grid. The highest values are in the "
        "peatlands of the tundra and taiga. A click in Identify features "
        "mode asks SoilGrids for the value.",
    "Кислотность почвы": "Soil pH",
    "Кислотность почвы pH в водной вытяжке, слой 0-5 см, по SoilGrids "
    "ISRIC, сетка 250 м. Жёлтые - кислые почвы, зелёные - нейтральные, "
    "бирюзовые - щелочные. Щелчок в режиме «Определить объекты» "
    "запрашивает значение у SoilGrids.":
        "Soil pH in water, layer 0-5 cm, from ISRIC SoilGrids, a 250 m "
        "grid. Yellow soils are acid, green neutral, turquoise alkaline. "
        "A click in Identify features mode asks SoilGrids for the value.",
    "Загрузка землетрясений ISC-GEM, {year}…":
        "Loading ISC-GEM earthquakes, {year}…",
    "Исторических землетрясений {count}.":
        "{count} historical earthquakes.",
    "Каталог ISC-GEM не загрузился, проверьте сеть и включите строку "
    "снова.":
        "The ISC-GEM catalogue did not load, check the network and turn "
        "the row on again.",
    "Почва": "Soil",
    "Исторические землетрясения, около 13 МБ":
        "Historical earthquakes, about 13 MB",
    "Литологическая карта": "Lithological map",
    "Повторяемость и изменения воды": "Water occurrence and transitions",
    "Свойства почв 0-5 см": "Soil properties 0-5 cm",
    "Покрытие земель ESA WorldCover 2021": "ESA WorldCover 2021 land cover",
    "Кустарник": "Shrubland",
    "Луга": "Grassland",
    "Пашня": "Cropland",
    "Застройка": "Built-up",
    "Голые и редкие земли": "Bare and sparse vegetation",
    "Снег и лёд": "Snow and ice",
    "Постоянные водоёмы": "Permanent water bodies",
    "Травяные болота": "Herbaceous wetland",
    "Мангры": "Mangroves",
    "Мхи и лишайники": "Moss and lichen",
    "Покрытие земель": "Land cover",
    "Карта покрытия земель ESA WorldCover за 2021 год по снимкам "
    "Sentinel-1 и Sentinel-2 с пикселем 10 м - лес, кустарник, луга, "
    "пашня, застройка, голые земли, снег и лёд, вода, болота, мангры, мхи "
    "и лишайники. Щелчок в режиме «Определить объекты» показывает класс.":
        "The ESA WorldCover land cover map for 2021 from Sentinel-1 and "
        "Sentinel-2 images with a 10 m pixel - forest, shrubland, "
        "grassland, cropland, built-up, bare land, snow and ice, water, "
        "wetland, mangroves, moss and lichen. A click in Identify features "
        "mode shows the class.",
    # Карточка метки и «Объясни это», ui/placecard.py.
    "У метки нет описания. Его пишут в окне «Свойства…» метки.":
        "The placemark has no description. It is written in the "
        "placemark Properties… window.",
    "Объясни это": "Explain this",
    "Спросить помощника, что это за объект и чем интересно место. "
    "Помощнику уходят название, вид, координаты, описание и поля этой "
    "метки и названия включённых слоёв глобуса. Ответ появится "
    "здесь и под строкой «Поиск».":
        "Ask the assistant what this object is and why the place is of "
        "interest. The assistant receives the name, kind, coordinates, "
        "description and fields of this placemark and the names of the "
        "globe layers turned on. The answer appears here and under the "
        "Search box.",
    "Помощник не подключён. Ключ API вводят в окне «Настройки "
    "помощника».":
        "The assistant is not connected. The API key is entered in the "
        "Assistant settings window.",
    "Объясни, что это за объект и чем интересно это место. "
    "{kind} «{name}», точка {lat:.5f}, {lon:.5f}.":
        "Explain what this object is and why this place is of interest. "
        "{kind} \"{name}\", point {lat:.5f}, {lon:.5f}.",
    "Описание метки - {text}": "Placemark description - {text}",
    "Поля объекта - {fields}.": "Object fields - {fields}.",
    # Карточка объекта слоя проекта, ui/placecard.py.
    "Спросить помощника, что это за объект и чем интересно место. "
    "Помощнику уходят название слоя, название и поля этого объекта, "
    "точка щелчка и названия включённых слоёв глобуса. Ответ появится "
    "здесь и под строкой «Поиск».":
        "Ask the assistant what this object is and why the place is of "
        "interest. The assistant receives the layer name, the name and "
        "fields of this object, the clicked point and the names of the "
        "globe layers turned on. The answer appears here and under the "
        "Search box.",
    "Слой «{name}»": "Layer \"{name}\"",
    "Выделить объект в слое QGIS. Выделение видно на карте, в таблице "
    "атрибутов и на глобусе.":
        "Select the object in the QGIS layer. The selection is seen on "
        "the map, in the attribute table and on the globe.",
    "Объясни, что это за объект и чем интересно это место. Объект "
    "«{name}» слоя «{layer}», точка {lat:.5f}, {lon:.5f}.":
        "Explain what this object is and why this place is of interest. "
        "Object \"{name}\" of the layer \"{layer}\", point {lat:.5f}, "
        "{lon:.5f}.",
    "Описание объекта - {text}": "Object description - {text}",
    # Разделы руководства в строке «Поиск», ui/manualcard.py.
    "{name} - раздел руководства": "{name} - manual section",
    "Открыть на GitHub": "Open on GitHub",
    "Раздел руководства этой версии модуля в браузере, с картинками.":
        "The manual section of this plugin version in the browser, with "
        "pictures.",
    # Окно «Свойства…» метки, вид точки и поля объекта, ui/placeprops.py.
    "Размер значка": "Icon size",
    "Без значка": "No icon",
    "Размер значка, доля обычного, как scale IconStyle в KML. 0 - на "
    "глобусе только подпись.":
        "Icon size as a share of the usual one, as the IconStyle scale "
        "in KML. 0 - only the label on the globe.",
    "Цвет подписи": "Label colour",
    "Цвет подписи метки на глобусе, как LabelStyle в KML. Тёмная подпись "
    "получает светлую обводку.":
        "Colour of the placemark label on the globe, as LabelStyle in "
        "KML. A dark label gets a light outline.",
    "Размер подписи": "Label size",
    "Без подписи": "No label",
    "Размер подписи, доля обычного. 0 - на глобусе только значок, "
    "название остаётся в списке.":
        "Label size as a share of the usual one. 0 - only the icon on "
        "the globe, the name stays in the list.",
    "Поля объекта": "Object fields",
    "Поле": "Field",
    "Поля объекта, как ExtendedData в KML. Их показывают карточка метки "
    "и окно «Объекты», «Объясни это» отдаёт их помощнику. Поле без имени "
    "не сохраняется.":
        "Object fields, as ExtendedData in KML. The placemark card and "
        "the Objects window show them, Explain this passes them to the "
        "assistant. A field without a name is not saved.",
    "Добавить поле": "Add field",
    # Слой проекта в «Мои метки», ui/globe/places.py.
    "В «Мои метки»…": "To My Places…",
    "Объекты слоя ложатся в «Мои метки» папкой с именем слоя - "
    "выделенные, иначе все. Цвета - стиль слоя, название - подпись слоя, "
    "атрибуты - поля объекта, время - временные свойства слоя. Папку "
    "можно сохранить в KML.":
        "The layer features go into My Places as a folder named after "
        "the layer - the selected ones, otherwise all. Colours come from "
        "the layer style, names from the layer labels, attributes become "
        "object fields, time comes from the temporal properties of the "
        "layer. The folder can be saved to KML.",
    "Слои проекта ложатся только на Землю.":
        "Project layers lie on the Earth only.",
    "В слое объектов {count}. Взять только объекты в видимой части "
    "глобуса? «Нет» - весь слой.":
        "The layer has {count} features. Take only the features in the "
        "visible part of the globe? No - the whole layer.",
    "В слое нет объектов с геометрией.":
        "The layer has no features with geometry.",
    "Объекты дадут вершин {count}, глобус рисует свои объекты до {limit} "
    "вершин, дальше вид замедлится. Записать всё равно?":
        "The features give {count} vertices, the globe draws its own "
        "objects up to {limit} vertices, beyond that the view slows "
        "down. Write them anyway?",
    "В «Мои метки» записано объектов {count}.":
        "Features written to My Places: {count}.",
    "Удалить поле": "Remove field",
    # Цвета окна «Разрез модели», ui/subsection.py.
    "Между пластами": "Between beds",
    "Цвет породы между пластами…": "Colour of the rock between beds…",
    "Цвет пласта «{name}»…": "Colour of the bed \"{name}\"…",
    "Цвет линии «{name}»…": "Colour of the line \"{name}\"…",
    "Цвета разреза по умолчанию": "Default section colours",
    "Цвет на разрезе": "Colour on the section",
    "Правая кнопка по пласту, породе между пластами или линии кровли "
    "задаёт их цвет. Цвета запоминаются в проекте QGIS.":
        "The right button on a bed, on the rock between beds or on a top "
        "line sets its colour. The colours are kept in the QGIS project.",
    "Помощник занят прежним вопросом или не подключён.":
        "The assistant is busy with the previous question or is not "
        "connected.",
    # Википедия рядом, core/wikipedia.py, ui/globe/wiki.py.
    "Энциклопедия": "Encyclopedia",
    "Статьи Википедии с координатами у точки взгляда. Щелчок "
    "по статье открывает её первый абзац, ссылку и кнопку "
    "«Объясни это».":
        "Wikipedia articles with coordinates near the view point. A click "
        "on an article opens its first paragraph, a link and the Explain "
        "this button.",
    "Википедия рядом": "Wikipedia nearby",
    "Статьи Википедии с координатами - города, памятники, реки, "
    "вершины - подписями с голубым кружком. Статьи просятся, "
    "когда камера ниже 40 км, на языке интерфейса QGIS. Щелчок "
    "по подписи открывает карточку статьи - первый абзац, ссылку "
    "на статью и кнопку «Объясни это». Тексты Википедии - "
    "CC BY-SA 4.0.":
        "Wikipedia articles with coordinates - cities, monuments, rivers, "
        "peaks - as labels with a blue dot. The articles are requested "
        "when the camera is below 40 km, in the language of the QGIS "
        "interface. A click on a label opens the article card - the first "
        "paragraph, a link to the article and the Explain this button. "
        "Wikipedia texts are under CC BY-SA 4.0.",
    "Спросить помощника об этом месте по тексту статьи. Помощнику "
    "уходят заголовок, первый абзац и координаты статьи и названия "
    "включённых слоёв глобуса. Ответ появится здесь и под строкой "
    "«Поиск».":
        "Ask the assistant about this place by the article text. The "
        "assistant receives the title, the first paragraph and the "
        "coordinates of the article and the names of the globe layers "
        "turned on. The answer appears here and under the Search box.",
    "В «Мои метки»": "To My Places",
    "Метка в точке статьи с первым абзацем и ссылкой на статью "
    "в описании.":
        "A placemark at the article point with the first paragraph and "
        "a link to the article in the description.",
    "Текст статьи не загрузился: {error}":
        "The article text did not load: {error}",
    "Загрузка статьи…": "Loading the article…",
    "Статья в Википедии": "Article in Wikipedia",
    "Текст - Википедия, CC BY-SA 4.0": "Text - Wikipedia, CC BY-SA 4.0",
    "На глобусе включены слои - {names}.":
        "Layers turned on on the globe - {names}.",
    "Объясни, что это за объект и чем интересно это место. Статья "
    "Википедии «{title}», точка {lat:.5f}, {lon:.5f}.":
        "Explain what this object is and why this place is of interest. "
        "Wikipedia article \"{title}\", point {lat:.5f}, {lon:.5f}.",
    "Первый абзац статьи - {text}": "First paragraph of the article - {text}",
    "Опирайся на текст статьи и не придумывай того, чего в нём нет.":
        "Rely on the article text and do not invent what is not in it.",
    "Википедия не ответила, повтор через 30 с.":
        "Wikipedia did not answer, retry in 30 s.",
    "Метка «{name}» записана в «Мои метки».":
        "The placemark \"{name}\" is written to My Places.",
    "Статья": "Article",
    "Википедия": "Wikipedia",
    "Затопление": "Flooding",
    "Затопление отсюда…": "Flooding from here…",
    "Сток воды отсюда…": "Water flow from here…",
    "Подъём воды над высотой точки, до {rise} м.":
        "Water rise above the height of the point, up to {rise} m.",
    "Высота точки": "Point height",
    "Подъём": "Rise",
    "{h} м": "{h} m",
    "Сток воды": "Water flow",
    "Линия стока": "Flow line",
    "Водосбор": "Catchment",
    "Уровень не выше точки, воды нет.":
        "The level is not above the point, there is no water.",
    "Затоплено {area} км², объём воды {volume} млн м³, "
    "наибольшая глубина {depth} м.":
        "Flooded {area} km², water volume {volume} million m³, "
        "greatest depth {depth} m.",
    "Вода дошла до края участка и может идти "
    "дальше. Нужен больший участок.":
        "The water reached the edge of the area and may go further. "
        "A larger area is needed.",
    "Шаг сетки {step} м.": "Grid step {step} m.",
    "Вода видна при включённом рельефе.":
        "The water is visible with the terrain switched on.",
    "Затопление не записано в «{path}».":
        "The flooding is not written to \"{path}\".",
    "{name} - глубина": "{name} - depth",
    "{name} - контур": "{name} - outline",
    "Вода из точки никуда не стекает.":
        "Water from the point does not flow anywhere.",
    "Длина {km} км, падение {drop} м.": "Length {km} km, drop {drop} m.",
    "Линия дошла до края участка, дальше вода "
    "идёт за его пределы.":
        "The line reached the edge of the area, beyond it the water "
        "leaves the area.",
    "Линия кончается у края данных высот.":
        "The line ends at the edge of the height data.",
    "К точке вода не стекает: водосбора "
    "нет.": "No water flows to the point, there is no catchment.",
    "Створ перенесён на русло в {m} м от точки.":
        "The outlet moved to the channel {m} m from the point.",
    "Водосбор доходит до края участка, его часть "
    "за краем не учтена. Нужен больший участок.":
        "The catchment reaches the edge of the area, its part beyond the "
        "edge is not counted. A larger area is needed.",
    "Площадь {area} км², высоты {low}-{high} м, средняя "
    "{mean} м.": "Area {area} km², heights {low}-{high} m, mean {mean} m.",
    "Средний уклон склонов {slope} промилле по "
    "СП 33-101-2003.":
        "Mean hillslope gradient {slope} per mille by SP 33-101-2003.",
    "Густота речной сети {dens} км на км², водотоки "
    "с водосбором от {area} км².":
        "Stream network density {dens} km per km², streams with a "
        "catchment from {area} km².",
    "Главный водоток {km} км, падение {fall} м, уклон {slope} "
    "промилле.":
        "Main stream {km} km, fall {fall} m, gradient {slope} per mille.",
    "Речная сеть - водотоки с водосбором не меньше этой площади. "
    "Меньше - сеть гуще, с ручьями и оврагами.":
        "The stream network takes streams with a catchment of at least "
        "this area. Smaller means a denser network with brooks and "
        "gullies.",
    " км²": " km²",
    "Водотоки от": "Streams from",
    "Порядок от": "Order from",
    "Наименьший порядок водотока по Стралеру в речной сети. "
    "Исток - порядок 1, после слияния двух водотоков одного "
    "порядка - на единицу больше. Больше - в проект идут только "
    "крупные реки, порядки считаются по всей сети.":
        "The lowest Strahler order of a stream in the network. A source "
        "has order 1, the confluence of two streams of the same order "
        "gives one more. A larger value sends only large rivers to the "
        "project, the orders are counted over the whole network.",
    "Радиус поиска русла": "Channel search radius",
    "В этом радиусе от точки ищется русло - место с наибольшим "
    "водосбором, водосбор строится от него. Щелчок рядом с "
    "рекой так даёт водосбор реки. 0 - водосбор ровно от точки.":
        "Within this radius of the point the channel is searched for, "
        "the place with the largest catchment, and the catchment starts "
        "there. So a click near a river gives the catchment of the "
        "river. 0 means the catchment starts exactly at the point.",
    "Обрывать на водотоке": "Stop at a stream",
    "Обрывать на выполаживании": "Stop where the slope flattens",
    "Линия стока кончается там, где средний уклон на длине "
    "участка ниже порога - у подножия склона, на террасе, на "
    "пойме. Короткая полка на крутом склоне линию не обрывает.":
        "The flow line ends where the mean slope over the segment "
        "length is below the threshold, at the foot of a slope, on "
        "a terrace, on a floodplain. A short ledge on a steep slope "
        "does not end the line.",
    "Уклон выполаживания": "Flattening slope",
    "Уклон, ниже которого рельеф считается выположенным.":
        "The slope below which the terrain counts as flattened.",
    "Длина участка": "Segment length",
    "Длина участка, на которой меряется средний уклон. Больше - "
    "линию обрывает только долгое выполаживание.":
        "The length over which the mean slope is measured. A larger "
        "value ends the line only on a long flattening.",
    "Обрывать при слиянии": "Stop at a confluence",
    "Линии от метки кончаются, вливаясь в линию, построенную "
    "раньше, и общее русло идёт одной линией. Без флажка каждая "
    "линия идёт до конца, и по общему руслу проходят все.":
        "Lines from the placemark end where they join a line built "
        "earlier, and a shared channel is one line. Without the check "
        "box each line runs to its end, and all of them follow the "
        "shared channel.",
    "Бассейны": "Basins",
    "Вода от метки никуда не стекает.":
        "Water from the placemark does not flow anywhere.",
    "Линии стока «{name}»": "Flow lines of {name}",
    "Самых коротких линий не вошло {count}.":
        "{count} of the shortest lines are left out.",
    "Бассейны не записаны в «{path}».":
        "The basins were not written to {path}.",
    "Линия кончается на водотоке.": "The line ends at a stream.",
    "Линия кончается, где рельеф выполаживается.":
        "The line ends where the terrain flattens.",
    "Линия вливается в другую линию стока.":
        "The line joins another flow line.",
    "Линии стока от метки…": "Flow lines from placemark…",
    "Уклон и экспозиция здесь…": "Slope and aspect here…",
    "Уклон и экспозиция квадрата вокруг точки по высотам, сводка, "
    "растры и вершины с ямами.":
        "Slope and aspect of the square around the point from the "
        "heights, a summary, rasters, peaks and pits.",
    "Что видно из точки в круге заданного радиуса.":
        "What is visible from the point within a circle of the given "
        "radius.",
    "Часы прямого солнца в сутки вокруг точки.":
        "Hours of direct sun per day around the point.",
    "север": "north",
    "северо-восток": "north-east",
    "восток": "east",
    "юго-восток": "south-east",
    "юг": "south",
    "юго-запад": "south-west",
    "запад": "west",
    "северо-запад": "north-west",
    "Уклон от {low}° до {high}°, медиана {median}°.":
        "Slope from {low}° to {high}°, median {median}°.",
    "Площади по уклону: {parts}.": "Areas by slope: {parts}.",
    "{side} {share}": "{side} {share}",
    "Вершины и ямы {point}": "Peaks and pits {point}",
    "{low}-{high}° - {area} км²": "{low}-{high}° - {area} km²",
    "Чаще всего склоны смотрят на {sides}.":
        "Most slopes face {sides}.",
    "Ровного места {share}.": "Flat ground {share}.",
    "Уклон и экспозиция": "Slope and aspect",
    "Вершина выше всего вокруг себя в этом радиусе, яма ниже. Больше - "
    "остаются только крупные вершины и ямы.":
        "A peak is higher than everything around it within this radius, "
        "a pit is lower. A larger value keeps only large peaks and pits.",
    "Наименьший перепад вершины над низшей точкой вокруг неё или ямы "
    "под высшей. Меньше - больше мелких бугров и западин.":
        "The least rise of a peak above the lowest point around it or "
        "depth of a pit below the highest. A smaller value gives more "
        "small mounds and hollows.",
    "Показывать": "Show",
    "Радиус вершины": "Peak radius",
    "Перепад от": "Rise from",
    "Вершины и ямы": "Peaks and pits",
    "{name} - уклон, °": "{name} - slope, °",
    "{name} - экспозиция, °": "{name} - aspect, °",
    "Растры не записаны в «{path}».":
        "The rasters were not written to {path}.",
    "Речная сеть": "Stream network",
    "Уровень моря": "Sea level",
    "Уровень моря над нынешним. Вода заливает всё ниже уровня, "
    "ниже нуля открывает шельф. Около -120 м - последний "
    "ледниковый максимум, около +70 м - таяние всех ледников.":
        "Sea level above the present one. Water fills everything below "
        "the level, below zero it uncovers the shelf. About -120 m is the "
        "last glacial maximum, about +70 m is the melting of all "
        "glaciers.",
    "Уровень": "Level",
    "Нынешний": "Present",
    "Вернуть нынешний уровень моря.": "Return to the present sea level.",
    "Нынешний уровень моря.": "Present sea level.",
    "Вода заливает всё ниже уровня по всему глобусу. "
    "Связь с морем не проверяется, поэтому низины "
    "внутри материков тоже заливаются.":
        "Water fills everything below the level over the whole globe. "
        "The connection with the sea is not checked, so lowlands inside "
        "continents are flooded too.",
    "Речная сеть не записана в "
    "«{path}».": "The stream network is not written to \"{path}\".",
    "В проект добавлено водотоков {count}, наибольший "
    "порядок {order}.":
        "Streams added to the project: {count}, highest order {order}.",
    "Метка за краем данных высот.":
        "The placemark is beyond the height data.",
    "К метке вода не стекает: водосбора "
    "нет.": "No water flows to the placemark, there is no catchment.",
    "Водосбор «{name}»": "Catchment of \"{name}\"",
    "Водосбор метки": "Placemark catchment",
    "Гидрология": "Hydrology",
    "Вода от точки до заданной отметки, площадь, объём "
    "и глубины.":
        "Water from the point up to a chosen level, area, volume and "
        "depths.",
    "Линия стока, водосбор и речная сеть вокруг точки.":
        "Flow line, catchment and stream network around the point.",
    "Уровень моря…": "Sea level…",
    "Подъём и опускание уровня моря по всему глобусу.":
        "Raising and lowering the sea level over the whole globe.",
    # Изменения местности по эмбеддингам AlphaEarth (ui/aef.py).
    "Годы сравнения. Каждая клетка 10 м за год описана 64 числами - "
    "сводкой снимков Sentinel, Landsat и радара. Степень изменения - "
    "насколько отличаются описания двух лет.":
        "Years to compare. Each 10 m cell is described for a year by 64 "
        "numbers, a summary of Sentinel and Landsat images and radar. The "
        "degree of change shows how much the two years' descriptions "
        "differ.",
    "Степень изменения {before}-{after}":
        "Degree of change {before}-{after}",
    "Изменения {before}-{after}": "Change {before}-{after}",
    "Изменения местности": "Land change",
    "Пиксель подробного участка. Файлы набора хранят блоки 1024 × 1024 "
    "пикселя, блок за год - 40-50 МБ при любом пикселе: 10 м покрывают "
    "10 км блоком, 80 м - 82 км.":
        "Pixel of the detail area. The dataset files store blocks of "
        "1024 × 1024 pixels, one block per year is 40-50 MB at any pixel "
        "size: at 10 m a block covers 10 km, at 80 m 82 km.",
    "Годы": "Years",
    "Степень от": "Degree from",
    "Подробный участок": "Detail area",
    "Пиксель участка": "Area pixel",
    "Подробно": "Detail",
    "Места изменений": "Change spots",
    "Данные - AlphaEarth Foundations Satellite Embedding, CC BY 4.0.":
        "Data - AlphaEarth Foundations Satellite Embedding, CC BY 4.0.",
    "Загрузка около {mb} МБ": "Download about {mb} MB",
    "Участок грузится при приближении к нему. {volume}.":
        "The area loads when the view comes close to it. {volume}.",
    "Считается степень изменения участка…":
        "Computing the degree of change of the area…",
    "Растр {cols} × {rows} пикселей в проекте.":
        "Raster of {cols} × {rows} pixels added to the project.",
    "Ищутся места изменений…": "Looking for change spots…",
    "Показывать клетки со степенью изменения в этом промежутке, прочие "
    "прозрачны. У неизменённой местности степень около 0.05, у стройки, "
    "вырубки, нового карьера - 0.5 и выше.":
        "Cells with a degree of change in this range are shown, others "
        "are transparent. Unchanged land is about 0.05, construction, "
        "logging or a new quarry 0.5 and higher.",
    "{pixel} м": "{pixel} m",
    "до": "to",
    "и": "and",
    "Изменения местности: нет библиотеки zstd, файлы AlphaEarth не "
    "прочитать.":
        "Land change: the zstd library is missing, AlphaEarth files "
        "cannot be read.",
    "Для участка нет данных.": "No data for the area.",
    "Растр не записан в «{path}».": "The raster was not written to "
                                    "\"{path}\".",
    "Изменений сильнее 0.3 на участке нет.":
        "No change stronger than 0.3 in the area.",
    "Данные не получены: {error}": "Data not received: {error}",
    "Изменения местности здесь": "Land change here",
    "Анализ участка": "Site analysis",
    "Изменения местности здесь…": "Land change here…",
    "Где местность изменилась между двумя годами 2017-2025 - по "
    "эмбеддингам AlphaEarth, клетка 10 м.":
        "Where the land changed between two years of 2017-2025, from "
        "AlphaEarth embeddings, 10 m cells.",
    "Степень изменения": "Degree of change",
    "Где местность изменилась между двумя годами 2017-2025 - по "
    "эмбеддингам AlphaEarth Foundations.":
        "Where the land changed between two years of 2017-2025, from "
        "AlphaEarth Foundations embeddings.",
    "Окно сравнения двух лет у точки взгляда - годы, промежуток степени "
    "изменения, подробный участок с пикселем от 10 м, растр в проект "
    "QGIS и места изменений в «Мои метки».":
        "Window comparing two years at the view point - years, range of "
        "the degree of change, a detail area with a pixel from 10 m, a "
        "raster to the QGIS project and change spots to My Places.",
    "Степень изменения местности между двумя годами по эмбеддингам "
    "AlphaEarth Foundations - описаниям каждой клетки 10 м за год по "
    "снимкам и радару. Чёрные - без изменений, жёлтые - стройка, "
    "вырубка, карьер, разлив. Глобус показывает обзор с пикселем 160 м "
    "и крупнее, подробный участок и годы - окно «Изменения местности» "
    "подменю «Анализ участка» меню на глобусе.":
        "Degree of land change between two years from AlphaEarth "
        "Foundations embeddings, descriptions of each 10 m cell for a "
        "year from images and radar. Black is no change, yellow is "
        "construction, logging, a quarry, a flood. The globe shows an "
        "overview with a pixel of 160 m or coarser, the detail area and "
        "years are set by the Land change window of the Site analysis "
        "submenu of the globe menu.",
    # Классификация участка (ui/aefclass.py).
    "Классы {year} года: {parts}.": "Classes of {year}: {parts}.",
    "Щелчок по глобусу ставит точку этого класса.":
        "A click on the globe places a point of this class.",
    "Цвет класса на глобусе и в растре.":
        "Class color on the globe and in the raster.",
    "Контрольных точек класса.": "Control points of the class.",
    "Убрать класс и его точки.": "Remove the class and its points.",
    "Классификация": "Classification",
    "Год, по векторам которого клетки делятся на классы. Точки ставятся "
    "по снимку глобуса, он может быть другого года.":
        "The year whose vectors divide the cells into classes. Points are "
        "placed on the globe imagery, which may be of another year.",
    "Квадрат": "Square",
    "Участок - квадрат стороной из поля слева.":
        "The area is a square with the side from the field on the left.",
    "Нарисовать": "Draw",
    "Щёлкайте по глобусу вершины участка. Щелчок по первой вершине "
    "замыкает его.":
        "Click the area vertices on the globe. A click on the first "
        "vertex closes it.",
    "Участок не замкнут.": "The area is not closed.",
    "Участок больше {km} км, уменьшите его.":
        "The area is larger than {km} km, make it smaller.",
    "Замкните участок щелчком по его первой вершине.":
        "Close the area with a click on its first vertex.",
    "Пиксель классификации. Блок файла за год - 40-50 МБ при любом "
    "пикселе. Блок пикселя 10 м покрывает 10 км, 80 м - 82 км. «Авто» "
    "берёт пиксель с наименьшей загрузкой, при котором на участке от "
    "14 до 640 тысяч клеток.":
        "Classification pixel. A file block for a year is 40-50 MB at any "
        "pixel. A 10 m block covers 10 km, an 80 m block covers 82 km. "
        "Auto takes the pixel with the smallest download at which the "
        "area has 14 to 640 thousand cells.",
    "Авто": "Auto",
    "Убрать результат с глобуса и закрыть окно.":
        "Remove the result from the globe and close the window.",
    "Видимость {time}": "Viewshed {time}",
    "Инсоляция {time}, ч в сутки": "Insolation {time}, h per day",
    "Видно": "Visible",
    "Скрыто": "Hidden",
    "Высоты участка": "Area heights",
    "Изменения местности - места изменений": "Land change - change spots",
    "Изменения местности - участок в проект":
        "Land change - area to the project",
    "Остановить всё": "Stop all",
    "Остановить «{what}»": "Stop {what}",
    "Расчёт остановлен.": "The calculation is stopped.",
    "Щелчок - остановить расчёт.": "Click to stop the calculation.",
    "Пиксель {pixel} м, загрузка около {mb} МБ":
        "Pixel {pixel} m, download about {mb} MB",
    "Загружаются векторы участка, блок {n} из {total}…":
        "Loading the area vectors, block {n} of {total}…",
    "Добавить класс": "Add class",
    "Непрозрачность классов на глобусе.":
        "Opacity of the classes on the globe.",
    "Щёлкните по глобусу, чтобы поставить точку выбранного класса. Нужно "
    "хотя бы два класса по три точки.":
        "Click the globe to place a point of the selected class. At least "
        "two classes with three points each are needed.",
    "Пиксель": "Pixel",
    "Каждая клетка участка относится к классу ближайших контрольных точек "
    "по векторам AlphaEarth.":
        "Each cell of the area goes to the class of the nearest control "
        "points by AlphaEarth vectors.",
    "Убрать точку": "Remove point",
    "Загружаются векторы участка…": "Loading the area vectors…",
    "Классификация {year}": "Classification {year}",
    "Растр классов в проекте.": "The class raster is in the project.",
    "Классы": "Classes",
    "Класс {n}": "Class {n}",
    "Нет библиотеки zstd, файлы AlphaEarth не прочитать.":
        "No zstd library, AlphaEarth files cannot be read.",
    "Нужно хотя бы два класса по три точки.":
        "At least two classes with three points each are needed.",
    "Все точки вне участка.": "All points are outside the area.",
    "Точек вне участка: {n}.": "Points outside the area: {n}.",
    "Классификация здесь…": "Classification here…",
    "Классы участка по контрольным точкам на глобусе - по эмбеддингам "
    "AlphaEarth, клетка 10 м.":
        "Area classes by control points on the globe, from AlphaEarth "
        "embeddings, 10 m cells.",
    "Классификация здесь": "Classification here",
    "Окно классификации участка у точки взгляда - классы с цветом "
    "и названием, контрольные точки щелчком по глобусу, год, растр "
    "классов в проект QGIS.":
        "Window classifying the area at the view point - classes with a "
        "color and a name, control points by a click on the globe, the "
        "year, a class raster to the QGIS project.",
    'В проект добавлен слой «{name}». {text}':
        'Layer “{name}” added to the project. {text}',
    'В проект добавлено вершин {peaks} и ям {pits}.':
        '{peaks} peaks and {pits} pits added to the project.',
    'В проект добавлено мест изменений: {n}.':
        'Change spots added to the project: {n}.',
    'Водосбор {point}':
        'Catchment {point}',
    'Главный водоток {point}':
        'Main stream {point}',
    'Контрольные точки {year}':
        'Training points {year}',
    'Линий {count}, общая длина {km} км.':
        '{count} lines, total length {km} km.',
    'Линия стока {point}':
        'Flow line {point}',
    'Места изменений {before}-{after}':
        'Change spots {before}-{after}',
    'Места самых сильных изменений участка слоем точек в проект QGIS. '
    'Дальше их удобно смотреть архивом снимков Wayback и шторкой.':
        'Spots of the strongest change in the area as a point layer in '
        'the QGIS project. The Wayback imagery archive and the swipe '
        'show them next.',
    'Площадь, с которой вода стекает к точке, и главный водоток - два '
    'слоя в проект QGIS с площадью, высотами, длиной и уклоном '
    'водотока. Водосбор строится от русла рядом с точкой.':
        'The area from which water flows to the point and the main '
        'stream, two layers in the QGIS project with the area, '
        'elevations, the stream length and slope. The catchment starts '
        'at the channel next to the point.',
    'Путь воды от точки вниз по рельефу - слой линии в проект QGIS. '
    'Впадины заполнены до перелива, поэтому линия проходит через озёра '
    'и бессточные котловины. У пути и многоугольника - линии от всех их '
    'узлов одним слоем.':
        'The path of water from the point down the terrain, a line '
        'layer in the QGIS project. Depressions are filled up to their '
        'spill level, so the line passes through lakes and closed '
        'basins. For a path or a polygon, lines from all their nodes in '
        'one layer.',
    'Слой «{name}» не записан.':
        'Layer “{name}” was not written.',
    'Слой не записан в «{path}».':
        'The layer was not written to “{path}”.',
    'Яма':
        'Pit',
    'В папке «Временные метки» есть несохранённые элементы. Сохранить '
    'их в папке «Мои метки»?':
        'The Temporary Places folder has unsaved items. Save them to My '
        'Places?',
    'Временные метки':
        'Temporary Places',
    'Не сохранять':
        "Don't save",
    'Новые метки, пути и измерения ложатся сюда, пока строка выделена. '
    'При закрытии окна глобуса содержимое можно перенести в «Мои метки» '
    'или удалить. Метку, которую надо сохранить сразу, перетащите в '
    '«Мои метки».':
        'New placemarks, paths and measurements go here while the row '
        'is selected. When the globe window closes, the contents can be '
        'moved to My Places or deleted. Drag a placemark to My Places '
        'to keep it at once.',
    'Очистить «Временные метки»':
        'Clear Temporary Places',
    'Очистить «Временные метки»…':
        'Clear Temporary Places…',
    'Сохранить в «Мои метки»':
        'Save to My Places',
    'Удалить содержимое «Временных меток», меток и папок {count}? '
    'Отменить удаление нельзя.':
        'Delete the contents of Temporary Places, {count} placemarks '
        'and folders? Deletion cannot be undone.',
    "PlanetX - анализ участка": "PlanetX - site analysis",
    "Видимость": "Viewshed",
    "Нет точки окна.": "The window has no point.",
    "На участке нет высот.": "No heights in the area.",
    "Точка вне участка или в ней нет высот.":
        "The point is outside the area or has no heights.",
    "Больше - шаг сетки крупнее. Тени гор берутся с расстояния не меньше "
    "половины участка и не меньше 5 км.":
        "Larger means a coarser grid step. Mountain shadows are taken from a "
        "distance of at least half the area and at least 5 km.",
    "В проект добавлено бассейнов {count}, они покрывают {area} км² участка.":
        "{count} basins added to the project, they cover {area} km² of the "
        "area.",
    "Вершин и ям с таким перепадом на участке нет.":
        "No peaks or pits with such a rise in the area.",
    "Вершины и замкнутые понижения участка - слой точек в проект QGIS с "
    "отметкой и перепадом.":
        "Peaks and closed depressions of the area, a point layer in the QGIS "
        "project with the elevation and the rise.",
    "Водотоки участка с порядком по Стралеру - слой линий GeoPackage в проект"
    " QGIS, толщина линии растёт с порядком.":
        "Streams of the area with the Strahler order, a GeoPackage line layer"
        " in the QGIS project, the line width grows with the order.",
    "Водотоков с таким водосбором и порядком на участке нет.":
        "There are no streams with such a catchment and order in the area.",
    "Водотоков с таким водосбором у края участка нет.":
        "No streams with such a catchment at the edge of the area.",
    "Записать результат в проект QGIS и закрыть окно. Расчёт ложится "
    "подгруппой группы «PlanetX - анализ участка» вместе с контуром участка, "
    "удаление подгруппы убирает его целиком.":
        "Write the result to the QGIS project and close the window. The "
        "calculation goes into a subgroup of the PlanetX - site analysis "
        "group together with the area outline, removing the subgroup removes "
        "all of it.",
    "Линия стока кончается у края участка, водосбор больше участка "
    "учитывается не целиком.":
        "A flow line ends at the edge of the area, a catchment larger than "
        "the area is not counted in full.",
    "Линия стока кончается, дойдя до водотока с водосбором от площади поля "
    "«Водотоки от». Без флажка линия идёт до края участка.":
        "The flow line ends where it reaches a stream with a catchment of at "
        "least the area of the Streams from field. Without the check box the "
        "line runs to the edge of the area.",
    "Нарисовать участок многоугольником щелчками по глобусу. Щелчок по первой"
    " вершине замыкает его. Результат считается только внутри участка.":
        "Draw the area as a polygon by clicks on the globe. A click on the "
        "first vertex closes it. The result is computed only inside the area.",
    "Отметка поверхности воды над уровнем моря. Вода заливает всё ниже "
    "отметки внутри участка, куда она доходит от точки. Котловины за более "
    "высоким гребнем остаются сухими.":
        "Elevation of the water surface above sea level. Water fills "
        "everything below it inside the area that it reaches from the point. "
        "Basins behind a higher ridge stay dry.",
    "Степень изменения участка с выбранным пикселем. Вне участка глобус "
    "показывает обзор с пикселем 160 м и крупнее.":
        "Degree of change of the area at the chosen pixel. Outside the area "
        "the globe shows an overview with a pixel of 160 m or coarser.",
    "Сторона квадрата участка с серединой в точке окна. Вершины участка "
    "тянутся мышью, кружок на середине стороны ставит новую вершину. Участок "
    "не больше {km} км.":
        "Side of the area square centred at the window point. The area "
        "vertices are dragged with the mouse, the circle in the middle of a "
        "side adds a new vertex. The area is at most {km} km.",
    "Уклон и экспозиция участка по высотам, ядро 3 × 3 - раскраска на глобусе"
    " и сводка по классам уклона и сторонам света.":
        "Slope and aspect of the area from the heights, 3 × 3 kernel, "
        "colouring on the globe and a summary by slope classes and "
        "directions.",
    "Участок, поделённый на бассейны устьев - мест, где водотоки с водосбором"
    " от площади поля «Водотоки от» уходят из участка. Слой многоугольников "
    "GeoPackage в проект QGIS.":
        "The area divided into basins of outlets, the places where streams "
        "with a catchment of at least the area of the Streams from field "
        "leave the area. A GeoPackage polygon layer in the QGIS project.",
    "Что показывает участок на глобусе - крутизну склона или сторону света, "
    "куда он обращён. Строки «Уклон» и «Экспозиция» раздела «Слои» на это "
    "время гаснут.":
        "What the area shows on the globe, the steepness of the slope or the "
        "direction it faces. The Slope and Aspect rows of the Layers section "
        "switch off meanwhile.",
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
