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
    "Звёздное небо, поле зрения {fov}°": "Starry sky, field of view {fov}°",
    "Для глобуса нужен модуль Python {name}. В этой сборке QGIS его нет.":
        "The globe needs the Python module {name}. This QGIS build "
        "does not have it.",
    "Поиск": "Search",
    "Название места или координаты в градусах, например Пермь или "
    "58.0105, 56.2294. Enter запускает поиск или перелёт, несколько "
    "найденных мест показываются списком ниже. Просьба словами, например "
    "«покажи разрез через Японский жёлоб», уходит помощнику, если в его "
    "настройках сохранён ключ API. При вводе под строкой появляются "
    "подсказки - свои метки, прежние запросы, на небе звёзды и созвездия. "
    "Клавиша «вниз» выбирает подсказку, в пустой строке она показывает "
    "прежние запросы.":
        "A place name or coordinates in degrees, for example Perm or "
        "58.0105, 56.2294. Enter starts the search or the flight, several "
        "places found are listed below. A request in words, for example "
        "\"show a section across the Japan Trench\", goes to the "
        "assistant if an API key is saved in its settings. Suggestions "
        "appear below the field while typing - own placemarks, earlier "
        "queries and, in the sky, stars and constellations. The Down key "
        "selects a suggestion, in an empty field it shows the earlier "
        "queries.",
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
    "Разговор с помощником…": "Conversation with the assistant…",
    "Настройки помощника…": "Assistant settings…",
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
    "Создать метки по описанию в строке, например «путешествие Колумба» "
    "или «битвы Столетней войны». Помощник отвечает одним документом KML "
    "с датами событий. Метки сразу записываются новой папкой в «Мои "
    "метки», камера летит к ним. Ссылка «Отменить» под строкой удаляет "
    "папку. То же делает Ctrl+Enter в строке. Стрелка открывает разговор "
    "с помощником и его настройки.":
        "Make places from the description in the field, for example \"the "
        "voyage of Columbus\" or \"battles of the Hundred Years' War\". The "
        "assistant answers with one KML document with the dates of the "
        "events. The places are written to My Places as a new folder at "
        "once, the camera flies to them. The Cancel link below the field "
        "removes the folder. Ctrl+Enter in the field does the same. The "
        "arrow opens the conversation with the assistant and its settings.",
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
    "Основа": "Base map",
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
    "Созвездия и имена звёзд: d3-celestial, © Olaf Frohn. Планеты: "
    "элементы орбит JPL.":
        "Constellations and star names: d3-celestial, © Olaf Frohn. "
        "Planets: JPL orbital elements.",
    "Марс: NASA, USGS, Viking MDIM2.1. Луна: USGS, LRO LOLA. Тайлы: "
    "OpenPlanetaryMap.":
        "Mars: NASA, USGS, Viking MDIM2.1. Moon: USGS, LRO LOLA. Tiles: "
        "OpenPlanetaryMap.",
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
    "Пермь": "Perm",
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
    "Высоты поднимают поверхность и дают отмывку склонов. "
    "Высоты Земли - Mapzen Terrain Tiles, Марса - MOLA, Луны - "
    "LOLA. Без рельефа шар гладкий, высоты не загружаются. "
    "Вертикальный масштаб - в свойствах вида.":
        "Heights raise the surface and shade the slopes. Earth heights "
        "come from Mapzen Terrain Tiles, Mars heights from MOLA, Moon "
        "heights from LOLA. Without terrain the globe is smooth and no "
        "heights are loaded. Vertical exaggeration is in the view "
        "properties.",
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
    "Снимки или карта на поверхности. Esri World Imagery - пример "
    "подложки, условия её использования задаёт Esri. Свой источник "
    "добавляет строка «Добавить источник тайлов…».":
        "Imagery or a map on the surface. Esri World Imagery is an example "
        "base map, Esri sets its terms of use. The row Add tile source… "
        "adds a source of your own.",
    "Свой источник тайлов по адресу. Окно разбирает адрес, "
    "показывает пробную мозаику и находит самый подробный "
    "уровень.":
        "A tile source of your own by its address. The window parses the "
        "address, shows a test mosaic and finds the most detailed level.",
    "Добавить источник тайлов…": "Add tile source…",
    "Новый источник тайлов": "New tile source",
    "Адрес тайлов в любом виде - шаблон с {z}, {x}, {y}, адрес "
    "одного тайла из браузера или адрес с z, x, y в параметрах "
    "запроса. Окно само приводит его к шаблону.":
        "A tile address in any form - a template with {z}, {x}, {y}, the "
        "address of one tile from a browser or an address with z, x, y in "
        "the query. The window turns it into a template itself.",
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
    "Убрать": "Remove",
    "Убрать слой видимости с глобуса.":
        "Remove the viewshed layer from the globe.",
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
    "суток по сводке USGS. Кружок стоит в очаге на его "
    "глубине, линия ведёт к эпицентру на поверхности. "
    "Цвет показывает глубину очага, размер - магнитуду. "
    "Сводка загружается при включении строки.":
        "Earthquakes of magnitude 4.5 and above over the last 30 days from "
        "the USGS feed. A circle marks the focus at its depth, and a line "
        "leads to the epicentre on the surface. The colour shows the focus "
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
    "Осадки": "Sediments",
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
    "сервер выбранной модели. Названия слоёв проекта и «Моих меток» не "
    "уходят.":
        "The request, the look-at point and the rows switched on in the "
        "Layers section go to the server of the chosen model. Names of "
        "project layers and My Places do not.",
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
    "Помощник остановлен: слишком много действий подряд.":
        "The assistant stopped: too many actions in a row.",
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
    "Подземный режим": "Subsurface mode",
    "Подземный режим - скважины, горизонты, разрезы и вырез "
    "блока под поверхностью.":
        "Subsurface mode - drill holes, horizons, sections and a block "
        "cut under the surface.",
    "Файл GeoPackage": "GeoPackage file",
    "Таблицы collar, interval, survey, beds, sections и cut "
    "в одном файле, как у Isoliner. Кровли пластов - растры, "
    "их файлы названы в поле surface таблицы beds.":
        "Tables collar, interval, survey, beds, sections and cut in one "
        "file, as in Isoliner. Bed roofs are rasters, their files are "
        "named in the surface field of the beds table.",
    "Таблицы и растры кровель - слои текущего проекта.":
        "The tables and the roof rasters are layers of the current "
        "project.",
    "Обзор…": "Browse…",
    "Устья": "Collars",
    "Точки устьев с полями hole_id, z - отметка устья, eoh - "
    "глубина забоя по стволу.":
        "Collar points with the fields hole_id, z - collar elevation, "
        "eoh - end-of-hole depth along the hole.",
    "Интервалы": "Intervals",
    "Таблица hole_id, from, to, code. Глубины по стволу, "
    "code - пласт или литология, от него цвет.":
        "Table hole_id, from, to, code. Depths along the hole, code is "
        "the bed or lithology and sets the colour.",
    "Инклинометрия": "Survey",
    "Таблица hole_id, depth, azimuth, dip или zenith. "
    "Без неё скважины вертикальные.":
        "Table hole_id, depth, azimuth, dip or zenith. Without it the "
        "holes are vertical.",
    "Пласты": "Beds",
    "Таблица code, ord, color - порядок пластов сверху "
    "вниз и их цвета. Без неё цвет - по коду.":
        "Table code, ord, color - the order of beds from top to bottom and "
        "their colours. Without it the colour follows the code.",
    "Разрезы": "Sections",
    "Линии, вдоль которых строятся стенки разреза "
    "между кровлями пластов.":
        "Lines along which section walls are built between the bed "
        "roofs.",
    "Вырез": "Cut",
    "Многоугольник выреза блока. Внутри него поверхность "
    "и кровли убираются, по краю встают стенки.":
        "Polygon of the block cut. The surface and the roofs are removed "
        "inside it, walls stand along its edge.",
    "Растры отметок кровель пластов. Код пласта - имя слоя.":
        "Elevation rasters of bed roofs. The bed code is the layer name.",
    "Кровли": "Roofs",
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
    "Убрать подземное с глобуса.":
        "Remove the subsurface objects from the globe.",
    "GeoPackage (*.gpkg)": "GeoPackage (*.gpkg)",
    "Файл не найден.": "The file is not found.",
    "Данных нет: нужны устья скважин или "
    "кровли пластов.":
        "No data: drill hole collars or bed roofs are needed.",
    "Скважин {holes}, кровель {horizons}, разрезов "
    "{sections}. Вершин {vertices}.":
        "Drill holes {holes}, roofs {horizons}, sections {sections}. "
        "Vertices {vertices}.",
    "Не найдены {names}.": "Not found: {names}.",
    "Пропущено строк - {count}.": "Rows skipped: {count}.",
    "Инсоляция": "Insolation",
    "Инсоляция…": "Insolation…",
    "Первые сутки промежутка. Итог - среднее количество часов "
    "прямого солнца в сутки за промежуток.":
        "The first day of the period. The result is the mean number of "
        "hours of direct sunlight per day over the period.",
    "Последние сутки промежутка, включительно. Длинный промежуток "
    "считается по 15 суткам, взятым равномерно.":
        "The last day of the period, inclusive. A long period is computed "
        "over 15 evenly spaced days.",
    "Радиус круга расчёта. Больше - шаг сетки крупнее. Тени "
    "гор берутся с расстояния не меньше радиуса и не меньше "
    "5 км.":
        "Radius of the computed circle. A larger radius gives a coarser "
        "grid. Mountain shadows are taken from a distance of at least the "
        "radius and at least 5 km.",
    "Первые сутки": "First day",
    "Последние сутки": "Last day",
    "Убрать слой инсоляции с глобуса.":
        "Remove the insolation layer from the globe.",
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
    "{date} до н. э.": "{date} BC",
    "Палеогеография": "Paleogeography",
    "Берега материков в прошлом, до миллиарда лет назад, по модели "
    "движения плит из веб-службы GPlates. Возраст задаёт ползунок в "
    "левом нижнем углу вида. Снимок, границы и подписи на это время "
    "убраны.":
        "Continental coastlines in the past, up to a billion years ago, "
        "from the plate motion model of the GPlates Web Service. The "
        "slider in the lower left corner of the view sets the age. The "
        "imagery, borders and labels are removed meanwhile.",
    "Палеогеография не загрузилась: {error}":
        "Paleogeography failed to load: {error}",
    "Возраст в миллионах лет назад. Суша на этот возраст собрана по "
    "модели Merdith 2021 из веб-службы GPlates.":
        "Age in millions of years ago. The land for this age is built "
        "after the Merdith 2021 model from the GPlates Web Service.",
    "Показ от выбранного возраста к настоящему, шаг 5 млн лет.":
        "Plays from the chosen age to the present, 5 Myr per step.",
    "{age} млн лет назад, {period}": "{age} Myr ago, {period}",
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
    "Переместиться сюда": "Fly here",
    "Скопировать координаты": "Copy coordinates",
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
