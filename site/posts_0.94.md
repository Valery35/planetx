# PlanetX 0.94 - объявление

## Telegram

PlanetX 0.94 - трёхмерный глобус для QGIS.

Что нового после 0.93:

🪨 Геологический разрез по слоям проекта. Проведите путь в «Моих метках» и выберите «Разрез модели…» - слева флажками отмечаются любые растры отметок проекта как кровли пластов, скважины и слои с Z, например «3D-забор» из Isoliner3D. Пласты закрашены и подписаны, скважины идут цветами интервалов, стенки забора ложатся своим цветом.

📄 Разрез записывается картинкой PNG и таблицей отметок CSV по точкам пути.

Так разрез по гридам и скважинам строится прямо из проекта QGIS, без подготовки подземной модели.

Плагин бесплатный, ставится из каталога QGIS по слову PlanetX. Работает в QGIS 3.36 и новее и в QGIS 4.

Страница: https://www.informpp.ru/главная-страница/qgis-planetx
Выпуск 0.94.0: https://github.com/Valery35/planetx/releases/tag/v0.94.0

## Выпуск на GitHub

Окно «Разрез модели» пути строит и геологический разрез по слоям проекта. Флажки слева выбирают кровлями любые одноканальные растры проекта, скважины и слои с отметками Z, например «3D-забор». Цвета пластов подписаны на графике, разрез записывается картинкой PNG и таблицей отметок CSV. Растр, которого нет в таблице пластов, встаёт по своей средней отметке, а не под нижним пластом.

The Model section window of a path is also a geological section by the project layers. Checkboxes on the left choose any single-band rasters of the project as bed roofs, the drill holes and layers with Z such as a 3D fence. The bed colours are named on the chart, the section is written to a PNG picture and a CSV table of elevations. A raster missing from the beds table takes its place by its mean elevation instead of going under the lowest bed.

Руководство: PlanetX.pdf, PlanetX_en.pdf.
