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
    "Щелчок по карте показывает её на глобусе. День задаёт шкала времени. "
    "Слои включаются независимо от карты.":
        "A click on a map shows it on the globe. The time slider sets the "
        "day. Layers are switched on independently of the map.",
    "Карты и слои":
        "Maps and layers",
    "Группы спутников":
        "Satellite groups",
    "Какие группы спутников CelesTrak показывает слой «Спутники».":
        "Which CelesTrak satellite groups the Satellites layer shows.",
    "✓ вкл":
        "✓ on",
    "Искусственные спутники по орбитальным элементам CelesTrak, положение по "
    "модели SGP4. Время - правый бегунок шкалы времени, без шкалы - часы "
    "компьютера. Группы выбирает кнопка «Группы спутников». Элементы группы "
    "обновляются не чаще раза в 2 часа.":
        "Artificial satellites from CelesTrak orbital elements, positions by "
        "the SGP4 model. The time is the right handle of the time slider, "
        "without the slider the computer clock. The Satellite groups button "
        "chooses the groups. The elements of a group update at most once in "
        "2 hours.",
    "Карты NASA, прогноз погоды, пожары, небо, недра и анализ рельефа с "
    "превью. Щелчок открывает витрину.":
        "NASA maps, weather forecast, fires, sky, inside the Earth and "
        "terrain analysis with previews. A click opens the gallery.",
    "Карты и слои. Витрина с превью - карты NASA, прогноз погоды, пожары, "
    "звёзды, облака, солнце, спутники, недра и анализ рельефа. Значок "
    "нажат, пока карта витрины на глобусе. Крестик на её шкале в углу "
    "вида убирает карту.":
        "Maps and layers. A gallery with previews - NASA maps, weather "
        "forecast, fires, stars, clouds, sun, satellites, inside the Earth "
        "and terrain analysis. The icon stays pressed while a gallery map "
        "is on the globe. The cross on its scale in the corner of the "
        "view removes the map.",
    "Планета воздуха":
        "Planet of Air",
    "Все":
        "All",
    "Все карты витрины.":
        "All maps of the gallery.",
    "Найти карту":
        "Find a map",
    "На глобусе: {name}. Повторный щелчок убирает карту.":
        "On the globe: {name}. A second click removes the map.",
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
    "прогноз GFS":
        "GFS forecast",
    "24 часа":
        "24 hours",
    "суша и море":
        "land and sea",
    "{title}: {name}":
        "{title}: {name}",
    "Карта":
        "Map",
    "Небо и свет":
        "Sky and light",
    "Недра":
        "Inside the Earth",
    "Анализ рельефа":
        "Terrain analysis",
    "Векторная основа OpenFreeMap, координатная сетка и 3D-здания.":
        "The OpenFreeMap vector base, the coordinate grid and 3D buildings.",
    "Солнце и ночная сторона, звёзды, облака и искусственные спутники.":
        "The sun and the night side, stars, clouds and artificial "
        "satellites.",
    "Землетрясения, границы плит, разрез Земли и палеогеография.":
        "Earthquakes, plate boundaries, the Earth cutaway and "
        "paleogeography.",
    "Раскраска поверхности по уклону или по стороне света склона. Включается "
    "одна из двух.":
        "Surface coloring by slope or by the direction a slope faces. One of "
        "the two is on.",
    "Температура, осадки, ветер и облачность по модели NOAA GFS и "
    "температура поверхности по NASA. Прогноз - до 16 суток вперёд, момент "
    "задаёт шкала времени.":
        "Temperature, precipitation, wind and clouds of the NOAA GFS model "
        "and surface temperature from NASA. The forecast goes up to 16 days "
        "ahead, the time slider sets the moment.",
    "Очаги пожаров, дым, аэрозоль и угарный газ пожаров и промышленности по "
    "данным NASA.":
        "Fire spots, smoke, aerosol and carbon monoxide of fires and "
        "industry from NASA data.",
    "Осадки, влажность почвы, снег, лёд, пар, хлорофилл, солёность и "
    "наводнения по данным NASA.":
        "Precipitation, soil moisture, snow, ice, water vapor, chlorophyll, "
        "salinity and floods from NASA data.",
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
    "Облачность":
        "Clouds",
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
    "Скопировать ссылку на место":
        "Copy link to place",
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
    "Ссылка на место скопирована.":
        "The link to the place is copied.",
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
    "Точки дальше {limit} км по прямой. Маршрут строится по дорогам района, "
    "для дальних поездок он не подходит.":
        "The points are more than {limit} km apart in a straight line. The "
        "route follows the roads of the area and does not suit long trips.",
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
    "Место, координаты или тема. Название места или координаты, например "
    "Пермь или 58.0105, 56.2294, дают перелёт. Тема, например «путешествия "
    "Колумба», становится метками с датами в «Моих метках». Вопрос словами "
    "уходит помощнику. Ctrl+Enter сразу создаёт метки по теме.":
        "A place, coordinates or a topic. A place name or coordinates, for "
        "example Perm or 58.0105, 56.2294, fly there. A topic, for example "
        "“voyages of Columbus”, becomes placemarks with dates in My Places. "
        "A question in words goes to the assistant. Ctrl+Enter makes "
        "placemarks for the topic at once.",
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
    "Шаблон тайлов высот с {z}, {x}, {y}, например своё хранилище или сервер."
    " Пустое поле - рельеф по умолчанию. Глобус просит тайлы до уровня 15, "
    "глубже берёт их предков.":
        "A height tile template with {z}, {x}, {y}, for example an own store "
        "or server. An empty field gives the default terrain. The globe asks "
        "for tiles down to level 15 and takes their ancestors deeper.",
    "Как высота записана в цвете тайла. Terrarium - как у рельефа по "
    "умолчанию, Mapbox Terrain-RGB - высота с шагом 0.1 м.":
        "How the height is written in the tile colour. Terrarium is as in the"
        " default terrain, Mapbox Terrain-RGB is the height in 0.1 m steps.",
    'Подпись своего рельефа в углу вида и на снимках.':
        'The credit of the own terrain in the view corner and on snapshots.',
    'Свой рельеф':
        'Own terrain',
    'Запись высот':
        'Height encoding',
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
    'Высоты и снимки тел из хранилища planetx-terrain':
        'Heights and imagery of bodies from the planetx-terrain store',
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
    "Подземный режим - скважины, горизонты, разрезы и вырез "
    "блока под поверхностью.":
        "Subsurface mode - drill holes, horizons, sections and a block "
        "cut under the surface.",
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
    "Полоса скважин и тоннелей": "Band of holes and tunnels",
    "Ширина полосы вдоль линии, из которой скважины и тоннели "
    "переносятся на разрез. Шире полоса - больше скважин, но "
    "дальние лежат не там, где линия.":
        "Width of the band along the line from which drill holes and "
        "tunnels are moved onto the section. A wider band gives more holes, "
        "but the far ones do not lie where the line is.",
    "Нужны подземная модель и путь хотя бы из двух точек.":
        "A subsurface model and a path of at least two points are needed.",
    "Длина {length}. Скважин в полосе {holes}, тоннелей {tunnels}.":
        "Length {length}. Holes in the band: {holes}, tunnels: {tunnels}.",
    "рельеф {value}": "terrain {value}",
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
    "Типы покрова": "Land cover",
    "Типы земного покрова IGBP по MODIS за год, с 2001 года. Классы - "
    "в шкале в углу вида.":
        "IGBP land cover types from MODIS per year, since 2001. The "
        "classes are in the legend in the corner of the view.",
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
