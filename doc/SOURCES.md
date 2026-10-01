# Источники данных PlanetX и условия их использования

PlanetX не хранит и не распространяет картографические данные. Каждый
тайл показывает сервис-источник по запросу, так же как в обозревателе
QGIS. Запросы идут через сетевые настройки и дисковый кэш QGIS.
Загружается только видимая часть Земли, массового скачивания впрок
модуль не делает. Подпись источников стоит в правом нижнем углу окна
глобуса и меняется вместе с подложкой.

Условия источников сверены на их сайтах 26 сентября 2026 года. Это
изложение для ориентира, а не юридическое заключение. Обязательны
сами условия владельцев данных по ссылкам ниже.

| Источник | Что показывает | Условия | Подпись на экране |
|---|---|---|---|
| Esri World Imagery | космоснимки, подложка по умолчанию | [Esri Master License Agreement](https://www.esri.com/en-us/legal/terms/full-master-agreement) | Esri, Vantor, Earthstar Geographics, and the GIS User Community |
| OpenStreetMap | карта, подложка на выбор | [ODbL и правила использования тайлов](https://www.openstreetmap.org/copyright) | © OpenStreetMap contributors |
| OpenFreeMap | границы, реки, дороги, названия пунктов, 3D-здания | [бесплатно, в том числе коммерчески, с подписью](https://openfreemap.org/) | OpenFreeMap © OpenMapTiles, © OpenStreetMap contributors |
| Mapzen Terrain Tiles | высоты рельефа | [условия по источникам высот](https://github.com/tilezen/joerd/blob/master/docs/attribution.md) | Terrain: Mapzen, SRTM, GMTED, ETOPO1 and others |
| NASA GIBS, VIIRS SNPP Corrected Reflectance | облака, строка «Облака» | [данные NASA открыты, NASA просит указать источник](https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/gibs-api) | NASA GIBS, VIIRS |
| NASA GIBS, MODIS Terra LST 8 дней и GHRSST MUR | температура суши и моря, строка «Температура» | [данные NASA открыты, NASA просит указать источник](https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/gibs-api) | NASA GIBS, MODIS, GHRSST MUR |
| NASA SVS Deep Star Maps 2020 | Млечный путь, строка «Звёзды» | [страница SVS](https://svs.gsfc.nasa.gov/4851), SVS просит указать источник, запретов нет. Переведённая картинка лежит в выпуске `sky-2020` хранилища | NASA/Goddard SVS, Gaia DR2: ESA/Gaia/DPAC, в окне «О модуле» |
| Yale Bright Star Catalogue, 5-е издание | звёзды, строка «Звёзды» | каталог CDS V/50, условия CDS не сверены, автор принял это 29 сентября 2026 года | нет |
| OpenPlanetaryMap, Viking MDIM2.1 | снимки Марса | условия не указаны, см. раздел «Марс и Луна» | NASA, USGS, Viking MDIM2.1, OpenPlanetaryMap |
| OpenPlanetaryMap, LOLA hillshaded albedo | снимки Луны | условия не указаны, см. раздел «Марс и Луна» | USGS, LRO LOLA, OpenPlanetaryMap |
| NASA MGS MOLA MEGDR, 32 точки на градус | рельеф Марса | данные NASA PDS в общественном достоянии, см. раздел «Марс и Луна» | Terrain: NASA MGS MOLA MEGDR |
| NASA LRO LOLA GDR, 64 точки на градус | рельеф Луны | данные NASA PDS в общественном достоянии, см. раздел «Марс и Луна» | Terrain: NASA LRO LOLA GDR |
| USGS Astrogeology, глобальные мозаики | снимки Меркурия, Венеры, спутников Юпитера, Сатурна и Нептуна, Цереры, Весты, Плутона и Харона | общественное достояние, у части мозаик USGS просит указать авторов, см. раздел «Другие тела» | своя у каждого тела, в углу вида |
| NASA Photojournal, PIA07782 и PIA17214 | снимки Юпитера и Мимаса | изображения NASA, условия NASA для изображений, см. раздел «Другие тела» | NASA, JPL, Space Science Institute, Cassini |
| d3-celestial, Olaf Frohn | линии и названия созвездий, имена ярких звёзд, вид неба | [BSD с тремя пунктами](https://github.com/ofrohn/d3-celestial/blob/master/LICENSE), текст лицензии лежит в `planetx/data` | Constellations: d3-celestial © Olaf Frohn |
| JPL, Approximate Positions of the Planets | положения планет на небе | [страница JPL](https://ssd.jpl.nasa.gov/planets/approx_pos.html), формулы, данные не скачиваются | Planets: JPL approximate elements |
| Астрономический альманах, формулы малой точности | положение Луны на небе | формулы, данные не скачиваются | нет |
| Nominatim | поиск места по названию | [правила использования Nominatim](https://operations.osmfoundation.org/policies/nominatim/) | © OpenStreetMap contributors, в окне «О модуле» |

## Nominatim - поиск места

Поле «Поиск» отправляет название места в Nominatim, геокодер
OpenStreetMap. Правила сервиса соблюдаются в коде. Запрос уходит только
по Enter или кнопке «Поиск», подсказок по мере ввода нет. Запросы идут
не чаще одного в секунду. Заголовок `User-Agent` называет PlanetX
и адрес хранилища. Ответы запоминаются до закрытия окна, повторный поиск
того же слова в сеть не ходит. Координаты в поле разбираются без сети.

## Esri World Imagery - пример подложки

Esri World Imagery стоит в PlanetX подложкой по умолчанию как пример.
В свойствах вида она так и названа, «Esri World Imagery - пример».
Вместо неё можно выбрать OpenStreetMap или любое своё подключение XYZ
Tiles из обозревателя QGIS.

В описании слоя в ArcGIS Online сказано, что слой лицензирован
по Esri Master License Agreement. Для показа слоя в сторонней
программе важны такие пункты соглашения в редакции от 1 августа
2025 года:

- Данные разрешено показывать и включать в отчёты с подписью Esri
  и её поставщиков как источника, пункт 3.2 b.
- Данные разрешено использовать с продуктами, для которых их
  предоставила Esri. Иное использование требует письменного
  разрешения, пункт 3.2 a. Использовать данные в неразрешённом
  сервисе или продукте нельзя, пункт 3.3 a.
- Скачивать и хранить данные нельзя, кроме пакетов Esri для работы
  без сети, пункт 3.2 c. В описании слоя отдельно сказано, что он
  не предназначен для выгрузки тайлов для работы без сети.

Прямого разрешения показывать World Imagery в программах не от Esri
соглашение не содержит. Прямого запрета именно на такой показ в нём
тоже нет. PlanetX показывает слой с подписью, без массового
скачивания и без выгрузки для работы без сети. Кому нужна
определённость, особенно в коммерческой работе, сверяет условия
с Esri или выбирает в свойствах вида другую подложку.

## Марс и Луна

Снимки Марса и Луны дают базовые карты OpenPlanetaryMap. Это
сообщество, которое публикует тайлы планетных данных для веб-карт.
Марс - цветная мозаика Viking MDIM2.1 NASA и USGS, Луна - альбедо
с отмывкой рельефа LOLA от USGS. Страница базовых карт
[OPM Basemaps](https://github.com/openplanetary/opm/wiki/OPM-Basemaps)
просит подписи «NASA/Viking/USGS» и «LOLA/USGS». Условий
использования она не называет. Сверено 1 октября 2026 года.

Тайлы обоих тел лежат в разметке TMS, ряды считаются от юга. Для Луны
страница называет разметку XYZ, проверка расположения тайлов показала
разметку TMS.

Высоты Марса и Луны взяты из сеток PDS Geosciences Node. Марс -
MOLA MEGDR `megt90n000fb`, 32 точки на градус, высоты над ареоидом.
Луна - LOLA GDR `ldem_64`, 64 точки на градус, высоты над сферой
радиусом 1737.4 км. Данные миссий NASA находятся в общественном
достоянии, NASA просит указывать источник. Из сеток собраны тайлы
Terrarium уровней 0-5, по 1365 тайлов на тело. Они лежат в отдельном
хранилище [planetx-terrain](https://github.com/Valery35/planetx-terrain)
и загружаются по одному тайлу через сеть и кэш QGIS.

## Другие тела

Снимки остальных тел меню «Тело» нарезаны из глобальных мозаик
в простой цилиндрической проекции. Мозаики выбраны 1 октября 2026
года, адреса проверены в тот же день.

| Тело | Мозаика | Пиксель мозаики |
|---|---|---|
| Меркурий | MESSENGER MDIS Basemap MD3 Color, USGS | 665 м |
| Венера | Magellan C3-MDIR ClrTopo, USGS | 6.6 км |
| Юпитер | Cassini, PIA07782, NASA Photojournal | около 120 км |
| Ио | Galileo SSI и Voyager, цветная, USGS | 1 км |
| Европа | Voyager и Galileo SSI, USGS | 500 м |
| Ганимед | Voyager и Galileo SSI, цветная, USGS | 1.4 км |
| Каллисто | Voyager и Galileo SSI, USGS | 1 км |
| Мимас | Cassini, PIA17214, NASA Photojournal | 216 м |
| Энцелад | Cassini ISS, USGS | 110 м |
| Тефия | Cassini ISS, USGS | 293 м |
| Диона | Cassini ISS и Voyager, USGS | 154 м |
| Рея | Cassini ISS и Voyager, USGS | 417 м |
| Титан | Cassini ISS, ближний ИК, USGS | 4 км |
| Япет | Cassini ISS и Voyager, USGS | 803 м |
| Тритон | Voyager 2, цветная, USGS | 600 м |
| Церера | Dawn FC, USGS | 400 м |
| Веста | Dawn FC HAMO, USGS | 60 м |
| Плутон | New Horizons LORRI и MVIC, USGS | 300 м |
| Харон | New Horizons LORRI и MVIC, USGS | 300 м |

Мозаики USGS лежат на `planetarymaps.usgs.gov/mosaic/`, описания -
на страницах Astropedia `astrogeology.usgs.gov/search`. По описаниям
у одних мозаик ограничений использования нет, у других USGS просит
указать авторов. Подпись каждого тела называет миссию, институты
и USGS. Карты Юпитера и Мимаса - изображения NASA Photojournal,
подпись взята из строки Credit страницы.

Глобальной карты Сатурна в общественном достоянии не нашлось.
Карта Björn Jónsson - работа частного лица без указанной лицензии,
поэтому Сатурна в меню нет. Фобос сильно несферичен, его мозаика
на сфере исказилась бы, его тоже нет.

Из мозаик `tools/build_body_imagery.py` нарезает тайлы JPEG в сетке
Web Mercator, они лежат в хранилище
[planetx-terrain](https://github.com/Valery35/planetx-terrain)
в папке `imagery` и загружаются по одному тайлу.

## Другие открытые покрытия

Открытых глобальных космоснимков детальнее 10 м нет. Ниже два
источника, которые можно завести подключением XYZ Tiles в QGIS.

- **NASA GIBS.** Blue Marble около 500 м, ежедневные снимки MODIS
  и VIIRS 250-375 м. NASA открывает данные полностью и просит указать
  источник. [Условия](https://nasa-gibs.github.io/gibs-api-docs/).
- **EOxCloudless, Sentinel-2 без облаков.** 10 м. Свободно только для
  некоммерческого использования по CC BY-NC-SA 4.0, то есть для науки,
  обучения, некоммерческих организаций и личного использования. Для
  коммерческой работы нужна лицензия EOX.
  [Условия](https://cloudless.eox.at/documentation/license).

Google и Bing в PlanetX не предлагаются. Прямые адреса их тайлов
используются в обход их программных интерфейсов с ключами и нарушают
их условия.

## Своя подложка

Подключение добавляется в обозревателе QGIS, в разделе **XYZ Tiles**.
Оно появляется в списке подложек свойств вида при следующем открытии
окна глобуса. Условия использования снимков своего подключения задаёт
его владелец.
