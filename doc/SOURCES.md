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
| OSRM FOSSGIS, routing.openstreetmap.de | маршруты на машине, велосипеде и пешком, меню на глобусе | [не больше запроса в секунду, User-Agent программы, подпись и ссылка «сообщить об ошибке», без массовых запросов](https://www.fossgis.de/arbeitsgruppen/osm-server/nutzungsbedingungen/), сверено 8 октября 2026 года | © OpenStreetMap под строкой маршрута, ссылка «Ошибка на карте» |
| Copernicus Sentinel-2 L2A, файлы Element 84 на AWS | каналы и индексы слоями проекта, окно «Снимки Sentinel-2» | [правовое уведомление Copernicus](https://sentinels.copernicus.eu/documents/247904/690755/Sentinel_Data_Legal_Notice) - свободное воспроизведение, распространение и изменение. Изменённые данные несут подпись «Contains modified Copernicus Sentinel data [год]». Сверено 9 октября 2026 года | подпись в метаданных слоя и в окне |
| Landsat Collection 2 Level-2 (USGS) и MODIS версии 061 (NASA LP DAAC, NSIDC), Microsoft Planetary Computer | снимки Landsat 4-9 и продукты MODIS в окне снимков | данные USGS и NASA открыты, USGS и NASA просят указывать источник. Каталог и временный ключ SAS Planetary Computer - без учётной записи. Условия Planetary Computer не сверялись | подпись в метаданных слоя: «Landsat N image courtesy of the U.S. Geological Survey» или продукт MODIS с архивом NASA |
| Earth Search, Element 84 | каталог сцен Sentinel-2, STAC API `earth-search.aws.element84.com/v1` | открытый каталог [Registry of Open Data on AWS](https://registry.opendata.aws/sentinel-2-l2a-cogs/), учётная запись AWS не нужна. Сверено 9 октября 2026 года | подпись окна «Снимки Sentinel-2» |
| Mapzen Terrain Tiles | высоты рельефа | [условия по источникам высот](https://github.com/tilezen/joerd/blob/master/docs/attribution.md) | Terrain: Mapzen, SRTM, GMTED, ETOPO1 and others |
| Copernicus DEM GLO-30, файлы на AWS (copernicus-dem-30m) | высоты суши 30 м поверх Terrain Tiles с уровня 9, выбор «Модель 30 м» окна «Источники данных» | [лицензия ESA для Copernicus DEM](https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM) - бесплатно, у изменённых данных обязательна подпись «produced using Copernicus WorldDEM-30 © DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved». Коммерческое использование на странице не описано. Часть градусов в открытом наборе не выпущена, над морем файлов нет. Сверено 10 октября 2026 года | та же подпись в углу вида |
| GEDTM30 v1.2, OpenGeoHub, Ho и др., PeerJ 2025, doi:10.7717/peerj.19673 | высоты суши 30 м без леса и домов поверх Terrain Tiles с уровня 9 | [CC BY 4.0, запись Zenodo](https://zenodo.org/records/14900180), сверено 10 октября 2026 года. Авторы называют набор тестовым и дают его «как есть». Файл COG читается участками с s3.opengeohub.org | GEDTM30 v1.2: OpenGeoHub, Ho et al. 2025, CC BY 4.0 |
| Mapzen Terrain Tiles, производный растр | демо «Карьер, свой рельеф»: высоты вокруг синтетического карьера, файл `planetx/demo/quarry/quarry_dem.tif`, собран `tools/make_quarry_demo.py` 5 октября 2026 года | те же условия, что у Terrain Tiles. Карьер и отвал выдуманы | подпись Terrain Tiles на экране |
| NASA GIBS, VIIRS SNPP Corrected Reflectance | облака, строка «Облака» | [данные NASA открыты, NASA просит указать источник](https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/gibs-api) | NASA GIBS, VIIRS |
| NASA GIBS, MODIS Terra LST 8 дней и GHRSST MUR | температура суши и моря, строка «Температура» | [данные NASA открыты, NASA просит указать источник](https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/gibs-api) | NASA GIBS, MODIS, GHRSST MUR |
| NASA SVS Deep Star Maps 2020 | Млечный путь, строка «Звёзды» | [страница SVS](https://svs.gsfc.nasa.gov/4851), SVS просит указать источник, запретов нет. Переведённая картинка лежит в выпуске `sky-2020` хранилища | NASA/Goddard SVS, Gaia DR2: ESA/Gaia/DPAC, в окне «О модуле» |
| Yale Bright Star Catalogue, 5-е издание | звёзды, строка «Звёзды» | каталог CDS V/50, условия CDS не сверены, автор принял это 29 сентября 2026 года | нет |
| OpenPlanetaryMap, Viking MDIM2.1 | снимки Марса | условия не указаны, см. раздел «Марс и Луна» | NASA, USGS, Viking MDIM2.1, OpenPlanetaryMap |
| OpenPlanetaryMap, LOLA hillshaded albedo | снимки Луны | условия не указаны, см. раздел «Марс и Луна» | USGS, LRO LOLA, OpenPlanetaryMap |
| NASA MGS MOLA MEGDR, 32 точки на градус | рельеф Марса | данные NASA PDS в общественном достоянии, см. раздел «Марс и Луна» | Terrain: NASA MGS MOLA MEGDR |
| NASA LRO LOLA GDR, 64 точки на градус | рельеф Луны | данные NASA PDS в общественном достоянии, см. раздел «Марс и Луна» | Terrain: NASA LRO LOLA GDR |
| USGS Astrogeology, глобальные мозаики | снимки Меркурия, Венеры, спутников Юпитера и Сатурна, Цереры и Весты | общественное достояние, у части мозаик USGS просит указать авторов, см. раздел «Другие тела» | своя у каждого тела, в углу вида |
| NASA Photojournal, PIA07782 и PIA17214 | снимки Юпитера и Мимаса | изображения NASA, условия NASA для изображений, см. раздел «Другие тела» | NASA, JPL, Space Science Institute, Cassini |
| d3-celestial, Olaf Frohn | линии и названия созвездий, имена ярких звёзд, вид неба | [BSD с тремя пунктами](https://github.com/ofrohn/d3-celestial/blob/master/LICENSE), текст лицензии лежит в `planetx/data` | Constellations: d3-celestial © Olaf Frohn |
| JPL, Approximate Positions of the Planets | положения планет на небе | [страница JPL](https://ssd.jpl.nasa.gov/planets/approx_pos.html), формулы, данные не скачиваются | Planets: JPL approximate elements |
| Астрономический альманах, формулы малой точности | положение Луны на небе | формулы, данные не скачиваются | нет |
| Границы плит PB2002, Bird 2003, G-cubed 4(3), 1027; в GIS - Hugo Ahlenius, Nordpil | границы литосферных плит, строка «Границы плит» | [Open Data Commons Attribution 1.0](https://github.com/fraxen/tectonicplates), авторы просят указывать Hugo Ahlenius, Nordpil и Peter Bird. Шаги границ склеены в 1679 линий в файле модуля `data/plates.json`, сверено 4 октября 2026 года | Plate boundaries: Bird 2003, PB2002, Hugo Ahlenius, Nordpil |
| USGS, сводка землетрясений M4.5+ за 30 суток | землетрясения, строка «Землетрясения» | [данные USGS в общественном достоянии США, USGS просит указать источник](https://www.usgs.gov/information-policies-and-instructions/copyrights-and-credits), сверено 2 октября 2026 года | Earthquakes: USGS |
| PREM, Dziewonski, Anderson, 1981 | радиусы оболочек, строка «Разрез Земли» | опубликованная модель, радиусы границ записаны в код, данные не скачиваются | PREM, в шкале оболочек |
| CRUST1.0, Laske, Masters, Ma, Pasyanos, 2013 | слои коры на гранях, строка «Разрез Земли» | [страница модели](https://igppweb.ucsd.edu/~gabi/crust1.html), лицензии нет, авторы просят ссылку на сайт или статью EGU2013-2658. Модуль не распространяет модель, а скачивает архив с сайта UCSD при первом показе, сверено 2 октября 2026 года | CRUST1.0, Laske, Masters, Ma, Pasyanos |
| USGS Slab2, Hayes, 2018, doi:10.5066/F7PV6JNV | плиты на гранях разреза Земли | [данные USGS в общественном достоянии США](https://www.usgs.gov/data/slab2-a-comprehensive-subduction-zone-geometry-model), USGS просит ссылку. Условие выпуска - вне контура зоны модель не применять, узлы вне контура удалены. Сетки глубины, толщины и падения прорежены до 0.1° и лежат файлами зон в хранилище planetx-terrain, папка `slab2`, сверено 2 октября 2026 года | Slabs: USGS Slab2 |
| PALEOMAP PaleoDEM, Scotese & Wright 2018, doi:10.5281/zenodo.5460860 | рельеф суши и глубины моря в прошлом, строка «Палеогеография» | [Creative Commons Attribution 4.0](https://zenodo.org/records/5460860), сверено 5 октября 2026 года. Источник выбрал автор 5 октября 2026 года вместо масок суши модели Merdith et al. 2021 из веб-службы GPlates. Сетки 0.1° на 109 возрастов 0-540 млн лет раскрашены по высоте с отмывкой и лежат тайлами в planetx-terrain, папка `paleo/paleomap` | Paleogeography: PALEOMAP PaleoDEM, Scotese & Wright 2018, CC BY 4.0 |
| NASA GIBS, 23 слоя тем: OMPS, MODIS, AIRS, MERRA-2, IMERG, SMAP, GHRSST MUR, PACE, TROPOMI, OMI, OCO-2, VIIRS | группы тем «Планета огня», «Планета воды», «Планета воздуха», «Земля и жизнь» | [открытые данные NASA, GIBS просит указывать источник](https://nasa-gibs.github.io/gibs-api-docs/), сверено 5 октября 2026 года. Условия отдельных наборов, например TROPOMI программы Copernicus, не сверялись. Тайлы запрашиваются у GIBS по дням ряда, модуль их не хранит | NASA GIBS |
| OpenStreetMap, тоннели Vegas Loop | демо «Тоннели Vegas Loop»: трассы тоннелей The Boring Company и станции, файл `planetx/demo/vegas`, собран `tools/make_tunnel_demo.py` 4 октября 2026 года | [ODbL](https://www.openstreetmap.org/copyright), файл демо - производная база данных под ODbL. Глубина 12 м - допущение по открытым сведениям, в OpenStreetMap её нет | © OpenStreetMap contributors, в описании меток демо |
| NASA GIBS WMS, MODIS Terra Corrected Reflectance True Color | демо «Аральское море»: снимки 24 августа 2000, 25 августа 2014 и 4 сентября 2023 года | [открытые данные NASA, GIBS просит указывать источник](https://nasa-gibs.github.io/gibs-api-docs/), сверено 5 октября 2026 года. В демо лежат ссылки на запрос GetMap, картинки модуль не хранит | NASA GIBS, в описании картинок демо |
| Wikimedia Commons, «Moynaq, Aral Lake, Ship Wrecks, Uzbekistan.jpg», автор THORSTEN | демо «Аральское море», фото у Муйнака | [CC BY-SA 4.0](https://commons.wikimedia.org/wiki/File:Moynaq,_Aral_Lake,_Ship_Wrecks,_Uzbekistan.jpg), сверено 5 октября 2026 года. В демо лежит ссылка на файл | THORSTEN, CC BY-SA 4.0, в описании фото |
| Wikimedia Commons, «Aral map.png», автор Kmusser | демо «Аральское море», карта бассейна на экране | [CC BY-SA 2.5](https://commons.wikimedia.org/wiki/File:Aral_map.png), сверено 5 октября 2026 года. В демо лежит ссылка на файл | Kmusser, CC BY-SA 2.5, в описании карты |
| NASA Black Marble 2016, VIIRS_Night_Lights в NASA GIBS | огни городов на ночной стороне при строке «Солнце» | [открытые данные NASA, GIBS просит указывать источник](https://nasa-gibs.github.io/gibs-api-docs/), сверено 5 октября 2026 года. Тайлы уровней 0-8 запрашиваются у GIBS через кэш QGIS, модуль их не хранит | NASA Black Marble |
| NASA FIRMS, VIIRS NOAA-20, сводка за 24 часа | строка «Пожары» группы «Планета огня» | [открытые данные NASA](https://www.earthdata.nasa.gov/data/tools/firms), сверено 5 октября 2026 года, источник выбрал автор в тот же день. При передаче данных третьим лицам NASA просит указать FIRMS, LANCE и ESDIS, данные даются «как есть». Сводка CSV скачивается при включении строки, модуль её не хранит и не передаёт | Fires: NASA FIRMS VIIRS NOAA-20 |
| NOAA GFS 0.25°, файлы GRIB2 на AWS (noaa-gfs-bdp-pds) | группа «Погода» раздела «Слои» | [открытые данные NOAA, «can be used as desired»](https://registry.opendata.aws/noaa-gfs-bdp-pds/), сверено 6 октября 2026 года. NOAA просит указывать источник и не выдавать изменённые данные за исходные. Поле берётся участком файла по индексу .idx, сервер NOMADS не используется - он просит 10 с между запросами фильтра | NOAA GFS |
| CelesTrak, орбитальные элементы GP в CSV по группам | строка «Спутники» раздела «Слои» | [правила использования CelesTrak](https://celestrak.org/usage-policy.php), сверены 6 октября 2026 года, источник выбрал автор в тот же день. Группа скачивается не чаще одного обновления, данные обновляются раз в 2 часа, после ответа с ошибкой запросы прекращаются. Требований к подписи и передаче данных в правилах нет. Группа хранится файлом в профиле QGIS, модуль её не передаёт | Satellites: CelesTrak |
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
| Церера | Dawn FC, USGS | 400 м |
| Веста | Dawn FC HAMO, USGS | 60 м |

Мозаики USGS лежат на `planetarymaps.usgs.gov/mosaic/`, описания -
на страницах Astropedia `astrogeology.usgs.gov/search`. По описаниям
у одних мозаик ограничений использования нет, у других USGS просит
указать авторов. Подпись каждого тела называет миссию, институты
и USGS. Карты Юпитера и Мимаса - изображения NASA Photojournal,
подпись взята из строки Credit страницы.

Глобальной карты Сатурна в общественном достоянии не нашлось.
Карта Björn Jónsson - работа частного лица без указанной лицензии,
поэтому Сатурна в меню нет. Фобос сильно несферичен, его мозаика
на сфере исказилась бы, его тоже нет. Мозаики Плутона, Харона
и Тритона по съёмке New Horizons и Voyager 2 не покрывают 24-33 %
шара, по решению автора от 1 октября 2026 года в меню только тела,
снятые целиком.

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
