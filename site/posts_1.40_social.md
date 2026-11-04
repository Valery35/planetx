# PlanetX 1.40 - тексты для площадок

## RU - форум OSM, Facebook

PlanetX 1.40 для QGIS - анализ участка одним набором. Вопрос - что делать дальше?

Шесть окон распознавания сведены в одно окно «Распознавание». Источник - снимки Sentinel-2 (окно само подбирает летний снимок и снимок со снегом), подложка глобуса, свой растр или эмбеддинги AlphaEarth. Задачи - свои образцы, цвета снимка, похожие на образец, леса и рубки, поля, вода, заросшие поля. По OK в проект ложатся растр классов и сглаженные многоугольники, у задач лесов, полей и воды - ещё осевые линии дорог, рек и просек.

Рядом в подменю «Анализ участка» - уклон и экспозиция, видимость с учётом зданий, инсоляция и тени, затопление, сток и водосборы, уровень моря, изменения местности 2017-2025, минералы по спектру и EMIT, земляные работы. Данные открытые и бесплатные.

Что делать дальше? Варианты - точность классов и матрица ошибок, ряды снимков за годы, радарные снимки Sentinel-1, пакетный расчёт по многоугольникам слоя, свои правила классов, отчёт по участку - или упростить. Особенно интересны примеры ваших задач.

Описание всего набора - https://vk.ru/@qgismodules-planetx-140-analiz-uchastka-v-qgis-chto-uzhe-est-i-chto
Выпуск и руководство - https://github.com/Valery35/planetx/releases/tag/v1.40.0

## EN - OSM forum, OSGeo, LinkedIn

PlanetX 1.40 for QGIS - site analysis as one toolkit. What should come next?

Six recognition windows are merged into one Recognition window. The source is Sentinel-2 images (the window picks a summer image and a snow image itself), the globe base map, a project raster or AlphaEarth embeddings. Tasks - own samples, image colors, similar to a sample, forests and clear-cuts, fields, water, overgrown fields. OK puts a class raster and smoothed polygons into the project, the forest, field and water tasks also give center lines of roads, rivers and cuttings.

The same Site analysis submenu has slope and aspect, viewshed with buildings, insolation and shadows, flooding, flow lines and catchments, sea level, land change 2017-2025, minerals by spectrum and EMIT, earthworks. All data are open and free.

What next? Options - class accuracy and an error matrix, image time series over years, Sentinel-1 radar, batch runs over layer polygons, own class rules, a site report - or simplify. Examples of your own tasks are most welcome.

Release and manual - https://github.com/Valery35/planetx/releases/tag/v1.40.0
Plugin - https://plugins.qgis.org/plugins/planetx/

#QGIS #GIS #RemoteSensing #Sentinel2 #OpenSource

## X

PlanetX 1.40 for QGIS: one Recognition window instead of six, plus slope, viewshed, shadows, hydrology, land change, minerals and earthworks on a 3D globe. Free, GPL. What should come next? https://github.com/Valery35/planetx/releases/tag/v1.40.0 #QGIS #GIS

## Reddit r/QGIS (публикует автор, редактор в режиме Markdown)

Заголовок: PlanetX 1.40 – a free 3D globe plugin for QGIS, now with one Recognition window for site analysis. What would you want next?

PlanetX is a free (GPL) 3D globe plugin for QGIS 3.36+ and QGIS 4. Version 1.40 merges six classification windows into one **Recognition** window.

**Recognition – classes of a site**

- Source: Sentinel-2 images of the site (the window finds a summer image and a snow image itself), the globe base map, a project raster or Google AlphaEarth embeddings.
- Tasks: own samples (points or outlined areas), image colors, similar to a sample, forests and clear-cuts, fields, water, overgrown fields (spring and autumn images over 4 years).
- Rule-based classes can be corrected with samples. A "Names from the assistant" button suggests class names from band means.
- OK puts a class raster and smoothed class polygons into the project, plus center lines of roads, rivers and cuttings.

**The rest of the Site analysis submenu**

- slope and aspect, viewshed with OSM buildings, insolation, shadows for any moment
- flooding, flow lines, catchments, stream order, sea level from -130 to +100 m
- land change 2017-2025 (AlphaEarth), minerals by spectrum (USGS library) and NASA EMIT maps
- earthworks: cut and fill to a flat pad

All data are open; only EMIT files need a free NASA Earthdata token.

**Question:** what should come next?

1. Accuracy check – control points, error matrix
2. Time series of images instead of two dates
3. Sentinel-1 radar (works through clouds)
4. Batch runs over all polygons of a layer
5. Own class rules by index thresholds
6. A one-document site report
7. Simplify – there are already enough tools

Examples of your real tasks are most welcome.

- Plugin: https://plugins.qgis.org/plugins/planetx/
- Release and manual (RU/EN PDF): https://github.com/Valery35/planetx/releases/tag/v1.40.0

## Reddit r/gis (публикует автор, флэр Discussion или Open Source)

Заголовок: Free site-analysis toolkit on a 3D globe inside QGIS: land cover from Sentinel-2, hydrology, shadows, change detection. Looking for feedback on what to build next

We develop PlanetX, a free open-source (GPL) 3D globe plugin for QGIS. Over the last weeks it grew a set of site-analysis tools, and in 1.40 we merged six classification windows into one. Before going further we'd like to hear what is actually useful.

**How it works:** right-click on the globe – Site analysis. A site is drawn once (square, polygon or a layer polygon) and is shared by all tools. Every tool has Build (preview on the globe), OK (results go to the QGIS project as a subgroup) and Cancel.

**What is there now**

- **Recognition** – land classes from Sentinel-2 (summer + snow image picked automatically), a base map, your raster or AlphaEarth embeddings. Own samples, image colors, "similar to a sample", rule-based forests / clear-cuts / fields / water, overgrown fields from 4 years of spring and autumn images. Output: class raster, smoothed polygons, center lines.
- **Terrain** – slope and aspect with stats, viewshed with buildings, earthworks (cut/fill volumes).
- **Sun** – insolation hours per day, shadows following the time slider.
- **Water** – flooding to a level, flow lines, catchments, Strahler stream network, sea level.
- **Change and minerals** – AlphaEarth change 2017-2025, spectral matching against the USGS library, NASA EMIT mineral maps.

Data: Copernicus Sentinel-2, Copernicus DEM / ALOS / NASADEM / 3DEP, AlphaEarth, USGS and NASA, OSM and Overture buildings. No accounts needed except a free Earthdata token for EMIT.

**What next?** Accuracy assessment, image time series, Sentinel-1 radar, batch runs over layer polygons, own index rules, a site report – or simplify? Tell us your use case.

Plugin: https://plugins.qgis.org/plugins/planetx/
Release, manual and source: https://github.com/Valery35/planetx/releases/tag/v1.40.0
