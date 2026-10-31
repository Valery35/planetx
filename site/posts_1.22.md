# PlanetX 1.22 - черновик для групп

Картинка - `site/planetx_post_1.22.jpg`, шаг
`post_raster_class_shot`, сцена Sentinel-2 от 1 октября 2024 года,
контрольные точки выбраны по индексам NDVI и NDWI самого снимка.

## ВКонтакте и Telegram

PlanetX 1.22 - трёхмерный глобус для QGIS

Классификация по своему растру. Окно «Классификация» теперь работает не только с эмбеддингами AlphaEarth, но и с любым растром проекта QGIS. Многоканальный снимок, ортофото, набор геофизических полей или стопка производных рельефа подходят одинаково, сеть при этом не нужна.

Порядок прежний. На глобусе рисуется участок, щелчками ставятся контрольные точки каждого класса, например лес, поле, застройка или вода. Кнопка «Построить» относит каждую клетку участка к классу ближайших точек. Классы сразу видны на глобусе, OK записывает их растром в проект QGIS вместе с контрольными точками.

Каждый канал растра - признак клетки. Единицы каналов могут быть разными, например высоты в метрах и отражение в долях единицы, модуль приводит каналы к одному разбросу. Клетки без данных остаются без класса, а строка итога называет долю участка, которую покрывает растр. Классы могут иметь разное количество точек.

На картинке - участок 8 км в Перми, классы по пяти каналам снимка Sentinel-2 от 1 октября 2024 года: вода синим, лес зелёным, луга и поля жёлтым, застройка красным. Тени высоких домов снимок отдаёт в класс воды. Содержит изменённые данные Copernicus Sentinel 2024.

Плагин бесплатный, лицензия GNU GPL. Ставится из каталога модулей QGIS по слову PlanetX, работает в QGIS 3.36 и новее и в QGIS 4.

Страница: https://www.informpp.ru/главная-страница/qgis-planetx
Выпуски и руководство: https://github.com/Valery35/planetx/releases
Поддержать разработку: https://github.com/Valery35#поддержать-разработку

## English

PlanetX 1.22 - a 3D globe for QGIS

Classification by your own raster. The Classification window now works not only with AlphaEarth embeddings but with any QGIS project raster. A multiband image, an orthophoto, a set of geophysical fields or a stack of terrain derivatives all work the same way, and no network is needed.

The steps are the same. Draw a site on the globe, click control points for each class, such as forest, field, buildings or water, and press Build. Each cell of the site goes to the class of the nearest points. The classes appear on the globe at once, and OK writes them to the QGIS project as a raster together with the control points.

Each raster band is a feature of a cell. Bands may be in different units, such as heights in meters and reflectance in fractions of one, because the plugin brings them to one spread. Cells without data stay without a class, and the result line gives the share of the site covered by the raster. Classes may have different numbers of points.

The picture shows an 8 km site in Perm with classes by five bands of a Sentinel-2 image of 1 October 2024: water in blue, forest in green, meadows and fields in yellow, buildings in red. The shadows of tall buildings fall into the water class. Contains modified Copernicus Sentinel data 2024.

The plugin is free, under the GNU GPL. Install it from the QGIS plugin catalog by the word PlanetX. It works in QGIS 3.36 and newer and in QGIS 4.

Page: https://www.informpp.ru/главная-страница/qgis-planetx
Releases and manual: https://github.com/Valery35/planetx/releases
