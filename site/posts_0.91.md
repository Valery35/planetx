# PlanetX 0.91 - объявление

## Telegram

PlanetX 0.91 - трёхмерный глобус для QGIS.

Что нового после 0.90:

✨ Глобус стал плавнее - новый тайл снимка не «хлопает» резкостью, а за доли секунды проявляется из разрешения предка. Названия городов тоже проявляются, а не возникают разом.
🎬 Остановка тура со своими слоями - «Снимок текущего вида» в окне свойств метки запоминает и включённые строки раздела «Слои». В туре каждая остановка включает свои слои и ставит своё время, например сначала аномалии силы тяжести, потом разрез Земли с очагами землетрясений.
🧲 Аномалии Буге считаются с поправкой на рельеф вокруг - в горах карта точнее.
🏷 На снимке вида и в записи тура в углу стоит PlanetX.

Плагин бесплатный, ставится из каталога QGIS по слову PlanetX. Работает в QGIS 3.36 и новее и в QGIS 4.

Страница: https://www.informpp.ru/главная-страница/qgis-planetx
Выпуск 0.91.0: https://github.com/Valery35/planetx/releases/tag/v0.91.0

## Выпуск на GitHub

Новые тайлы проявляются плавно - тайл, сменивший предка, за доли секунды становится резким, новые надписи проявляются из прозрачности.

«Снимок текущего вида» в окне свойств метки запоминает и включённые строки раздела «Слои». Перелёт к метке и тур включают их, так каждая остановка тура показывает свои слои.

Аномалии Буге считаются с поправкой на рельеф вокруг в круге 167 км. На снимке вида и в записи тура в углу стоит PlanetX.

New tiles appear smoothly - a tile that replaces its parent sharpens from the parent resolution, new labels fade in. The view snapshot of a placemark also remembers the rows of the Layers section, a flight to the placemark and a tour stop switch them on. The Bouguer anomalies include the terrain correction within 167 km. Snapshots of the view and tour recordings carry the PlanetX name in the corner.

Руководство: PlanetX.pdf, PlanetX_en.pdf.
