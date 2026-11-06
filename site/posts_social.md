# PlanetX - первые публикации в LinkedIn, Facebook и X (1.9.0)

Раньше в этих сетях о PlanetX не писали, поэтому тексты знакомят
с модулем целиком, а не только с выпуском 1.9.

Опубликовано 22 октября 2026 года с личных страниц автора, отдельно
по-русски и по-английски. LinkedIn и Facebook - полные тексты ниже
с картинками `site/shots/brienz.jpg`, `site/shots/plates.jpg`,
`site/planetx_insolation_perm.png`. X - одним сообщением, с озером
и глобусом.

Картинки и ролик (подходят ко всем трём сетям):
- `site/shots/models.jpg` - 3D-модели на рельефе
- `site/shots/geology.jpg` - геологическая карта на глобусе
- `site/shots/b2_section.png` - геологический разрез по слоям проекта
- `Dropbox\ИИ\PlanetX\planetx_insolation_perm.png` - инсоляция
  центра Перми со зданиями
- `Dropbox\ИИ\PlanetX\planetx_haul_kachkanar.mp4` - самосвал
  в карьере Качканара, камера следом

В LinkedIn и Facebook лучше всего работают 3-4 картинки альбомом или
ролик, в X - одна картинка или ролик к первому сообщению.

---

## LinkedIn - по-русски

PlanetX - трёхмерный глобус внутри QGIS

Мы в ООО «Информ++» разрабатываем бесплатный модуль PlanetX для QGIS.
Он открывает в QGIS трёхмерный глобус с рельефом, космоснимками
и атмосферой. Слои текущего проекта ложатся на глобус в своём стиле,
и с ними можно работать, не выходя из QGIS.

Что умеет модуль:

• Рельеф и дно океанов по открытым данным - Terrarium, Copernicus DEM
30 м, GEBCO 2026, а также свой рельеф растром проекта.
• Космоснимки Sentinel-2, Landsat 1-9, ASTER и MODIS по участку -
индексы и сочетания каналов сразу слоями проекта.
• Недра - скважины и пласты слоями проекта, геологический разрез вдоль
линии, разрез Земли с корой CRUST1.0 и плитами Slab2, землетрясения.
• Геофизика мира - аномалии силы тяжести и Буге, магнитные аномалии,
возраст дна, тепловой поток, геоид.
• Видимость из точки и инсоляция с учётом зданий.
• 3D-модели glTF, Collada и OBJ, облака точек LAS, LAZ и COPC.
• Метки, туры и сцены в KML и KMZ, запись облёта в видео.
• Марс, Луна и звёздное небо.

Модуль бесплатный, лицензия GPL 3. Работает в QGIS 3.36 и новее
и в QGIS 4, ставится из каталога модулей QGIS по слову PlanetX.

Будем рады отзывам и вопросам - особенно от геологов, горняков
и всех, кто показывает свои данные на карте.

Страница модуля: https://www.informpp.ru/главная-страница/qgis-planetx
Исходный код: https://github.com/Valery35/planetx
Новости в Telegram: https://t.me/qgis_isolines

#QGIS #ГИС #геология #ДЗЗ #3D #OpenSource

---

## LinkedIn - in English

PlanetX - a 3D globe inside QGIS

At Inform++ we develop PlanetX, a free QGIS plugin. It opens a 3D globe
with terrain, satellite imagery and atmosphere right inside QGIS. Layers
of the current project are drawn on the globe in their own style, and
you keep working with them without leaving QGIS.

What it does:

• Terrain and ocean floor from open data - Terrarium, Copernicus DEM
30 m, GEBCO 2026, or your own elevation raster from the project.
• Sentinel-2, Landsat 1-9, ASTER and MODIS imagery for an area -
indices and band composites go straight into the project as layers.
• Subsurface - drill holes and beds from project layers, a geological
section along a line, an Earth cutaway with CRUST1.0 crust and Slab2
slabs, earthquakes.
• Global geophysics - free-air and Bouguer gravity anomalies, magnetic
anomalies, seafloor age, heat flow, geoid.
• Viewshed and insolation that take buildings into account.
• 3D models in glTF, Collada and OBJ, point clouds in LAS, LAZ and COPC.
• Placemarks, tours and scenes in KML and KMZ, fly-through video export.
• Mars, the Moon and the night sky.

The plugin is free and licensed under GPL 3. It runs in QGIS 3.36 and
later and in QGIS 4. Install it from the QGIS plugin catalogue by
searching for PlanetX.

Feedback and questions are welcome, especially from geologists, mining
engineers and anyone who presents their data on a map.

Plugin page: https://plugins.qgis.org/plugins/planetx/
Source code: https://github.com/Valery35/planetx

#QGIS #GIS #Geology #RemoteSensing #3D #OpenSource

---

## Facebook - по-русски

Сделали для QGIS трёхмерный глобус - PlanetX 🌍

Это бесплатный модуль. Он открывает в QGIS Землю с рельефом,
космоснимками и атмосферой, а слои вашего проекта ложатся на неё
в том же стиле, что и на карте.

Что можно сделать на глобусе:
🛰 загрузить снимки Sentinel-2, Landsat и ASTER по участку и сразу
получить индексы слоями проекта
⛰ посмотреть свой рельеф, карьер или дно озера в объёме
🪨 показать скважины, пласты и разрез вдоль линии, вынуть сектор Земли
и увидеть кору, мантию и очаги землетрясений
☀️ посчитать видимость из точки и часы солнца с учётом зданий
🏛 поставить 3D-модели зданий и показать облака точек с дрона
🎬 собрать тур по меткам и записать облёт в видео
🪐 улететь на Марс или Луну

Работает в QGIS 3.36 и новее и в QGIS 4. Ставится из каталога модулей
QGIS по слову PlanetX. Свежая версия - 1.9.

Подробнее и с картинками: https://www.informpp.ru/главная-страница/qgis-planetx
Новости модуля: https://t.me/qgis_isolines

---

## Facebook - in English

We made a 3D globe for QGIS - PlanetX 🌍

It is a free plugin. It opens the Earth with terrain, satellite imagery
and atmosphere right inside QGIS, and your project layers are drawn on
it in the same style as on the map.

What you can do on the globe:
🛰 load Sentinel-2, Landsat and ASTER imagery for an area and get
indices straight into the project
⛰ see your own terrain, open-pit mine or lake bed in 3D
🪨 show drill holes, beds and a section along a line, cut a sector out
of the Earth to see the crust, mantle and earthquake foci
☀️ compute viewshed and hours of sunlight with buildings
🏛 place 3D building models and show drone point clouds
🎬 build a tour of placemarks and record a fly-through video
🪐 fly to Mars or the Moon

Works in QGIS 3.36 and later and in QGIS 4. Install it from the QGIS
plugin catalogue by searching for PlanetX. The current version is 1.9.

Plugin page: https://plugins.qgis.org/plugins/planetx/
Source code: https://github.com/Valery35/planetx

---

## X - одним сообщением, по-русски (опубликовано)

PlanetX - бесплатный трёхмерный глобус для QGIS 🌍

Рельеф, космоснимки Sentinel-2 и Landsat, скважины и разрезы, 3D-модели
и облака точек, туры и видео облёта - на одном глобусе, не выходя
из QGIS. QGIS 3.36+ и QGIS 4, код открыт.

https://www.informpp.ru/главная-страница/qgis-planetx
#QGIS #ГИС

## X - одним сообщением, in English (опубликовано)

PlanetX is a free 3D globe for QGIS 🌍

Terrain, Sentinel-2 and Landsat imagery, drill holes and sections, 3D
models and point clouds, tours and fly-through video - on one globe,
without leaving QGIS. QGIS 3.36+ and QGIS 4, open source.

https://plugins.qgis.org/plugins/planetx/
#QGIS #GIS

---

## X (Twitter) - по-русски, цепочкой

Каждое сообщение - не больше 280 знаков, ссылка считается за 23.

1/4
PlanetX - бесплатный трёхмерный глобус для QGIS 🌍
Рельеф, космоснимки и слои вашего проекта в объёме, не выходя
из QGIS. Работает в QGIS 3.36+ и QGIS 4.
https://www.informpp.ru/главная-страница/qgis-planetx
#QGIS #ГИС

2/4
🛰 Снимки Sentinel-2, Landsat, ASTER и MODIS по участку - индексы
и сочетания каналов сразу слоями проекта.
⛰ Свой рельеф, карьер или дно озера в объёме.

3/4
🪨 Скважины, пласты и разрез вдоль линии. Разрез Земли с корой,
плитами и очагами землетрясений.
☀️ Видимость и инсоляция с учётом зданий.

4/4
🏛 3D-модели и облака точек с дрона. 🎬 Туры и запись облёта в видео.
Бесплатно, GPL 3, код открыт:
https://github.com/Valery35/planetx

---

## X (Twitter) - in English

1/4
PlanetX is a free 3D globe for QGIS 🌍
Terrain, satellite imagery and your project layers in 3D, without
leaving QGIS. Works in QGIS 3.36+ and QGIS 4.
https://plugins.qgis.org/plugins/planetx/
#QGIS #GIS

2/4
🛰 Sentinel-2, Landsat, ASTER and MODIS imagery for an area - indices
and band composites go straight into the project.
⛰ Your own terrain, open-pit mine or lake bed in 3D.

3/4
🪨 Drill holes, beds and a section along a line. An Earth cutaway with
crust, slabs and earthquake foci.
☀️ Viewshed and insolation with buildings.

4/4
🏛 3D models and drone point clouds. 🎬 Tours and fly-through video.
Free, GPL 3, open source:
https://github.com/Valery35/planetx
