# PlanetX 0.90 - объявление

## Telegram

PlanetX 0.90 - трёхмерный глобус для QGIS.

Что нового после 0.89:

🧲 Аномалии Буге в категории «Недра» каталога - сила тяжести без притяжения гор и глубин океана, по рельефу ETOPO 2022. Под горами аномалия отрицательная, над океаном положительная.
🪨 Кора CRUST1.0 в проект QGIS - пункт в меню «⋯» строки «Разрез Земли». Кровли трёх слоёв осадков, трёх слоёв коры и Мохо в рамке вида ложатся в проект растрами GeoTIFF, например на всю Восточно-Европейскую платформу.
🏢 Слои многогранников PolyhedralSurfaceZ и TIN Z встают на глобус объёмом, как MultiPolygonZ, - пункт «Объёмом по отметкам Z» меню слоя.
🌋 Плиты Slab2 на гранях разреза рисуются сплошной полосой, при косом взгляде они рвались на обрывки.
🏷 Подпись источников на карте стала короткой строкой, щелчок по ней открывает окно «Источники данных». В правом нижнем углу - PlanetX.

Плагин бесплатный, ставится из каталога QGIS по слову PlanetX. Работает в QGIS 3.36 и новее и в QGIS 4.

Страница: https://www.informpp.ru/главная-страница/qgis-planetx
Выпуск 0.90.1: https://github.com/Valery35/planetx/releases/tag/v0.90.1

## Выпуск на GitHub

Строка «Аномалии Буге» категории «Недра» каталога - аномалия силы тяжести XGM2019e за вычетом простой поправки Буге по рельефу ETOPO 2022.

Пункт «Кора CRUST1.0 в проект QGIS…» меню «⋯» строки «Разрез Земли» записывает кровли трёх слоёв осадков, трёх слоёв коры и Мохо в рамке вида растрами GeoTIFF и кладёт их в проект группой.

Подпись источников на карте - короткие названия одной строкой, щелчок открывает окно «Источники данных». В правом нижнем углу стоит PlanetX.

Слои PolyhedralSurfaceZ и TIN Z показываются объёмом. Подсказки строки «Поиск» прячутся при щелчке по глобусу. Над дальней стенкой блока гридов больше нет чёрной полосы.

The Bouguer anomalies row of the Inside the Earth category shows the XGM2019e gravity anomaly minus the simple Bouguer correction after the ETOPO 2022 relief. The CRUST1.0 crust to the QGIS project item of the Earth cutaway menu writes the tops of the sediment and crust layers and the Moho within the view as GeoTIFF rasters. The source credits on the map are a short line, a click opens the Data sources window, and PlanetX stands in the bottom right corner. PolyhedralSurfaceZ and TIN Z layers show in volume, search hints hide on a click on the globe, and the dark strip above the far wall of the grid block is gone.

Руководство: PlanetX.pdf, PlanetX_en.pdf.
