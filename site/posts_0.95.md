# PlanetX 0.95 - объявление

## Telegram

PlanetX 0.95 - трёхмерный глобус для QGIS.

Что нового после 0.94:

🌊 Дно морей и океанов по сетке глубин GEBCO 2026 с шагом около 450 м. Вблизи в открытом море больше нет пустых мест на нуле - Японский жёлоб виден целиком, Марианский уходит глубже 10.7 км.

🪨 Геологическая карта мира Macrostrat в разделе «Недра». Цвет показывает возраст пород, щелчок - подразделение, литологию, возраст в млн лет и карту-источник. Карта добавляется в проект QGIS слоем тайлов.

〰️ Активные разломы мира по базе GEM - около 13.7 тысячи линий. Цвет - вид смещения: сброс, взброс и надвиг, сдвиг. Щелчок показывает скорость смещения и падение.

Так геологию и тектонику района можно посмотреть на глобусе рядом с рельефом, гридами и скважинами проекта.

Плагин бесплатный, ставится из каталога QGIS по слову PlanetX. Работает в QGIS 3.36 и новее и в QGIS 4.

Страница: https://www.informpp.ru/главная-страница/qgis-planetx
Выпуск 0.95.0: https://github.com/Valery35/planetx/releases/tag/v0.95.0

## Выпуск на GitHub

Дно морей и океанов берётся из сетки глубин GEBCO 2026 с шагом около 450 м, в открытом море вблизи больше нет пустых мест на нуле. Строка «Активные разломы» раздела «Недра» показывает около 13.7 тысячи разломов базы GEM, цвет линии - вид смещения, щелчок - скорость смещения и падение. Строка «Геологическая карта» показывает карту мира Macrostrat с возрастом пород, щелчок - подразделение, литологию и возраст, карта добавляется в проект слоем тайлов.

The sea floor comes from the GEBCO 2026 depth grid of about 450 m, the open sea has no more empty spots at zero up close. The Active faults row of Inside the Earth shows about 13.7 thousand faults of the GEM database, the line colour is the kind of slip, a click shows the slip rate and dip. The Geological map row shows the Macrostrat map of the world with the age of the rocks, a click shows the unit, the lithology and the age, the map can be added to the project as a tile layer.

Руководство: PlanetX.pdf, PlanetX_en.pdf.
