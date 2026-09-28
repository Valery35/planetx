# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Двуязычный лендинг PlanetX для www.informpp.ru.

    $PY tools/build_site.py

Пишет site/planetx_landing.html. Страница самодостаточная, снимки
из doc/images встроены в файл, язык переключается без перезагрузки.
Снимки ужимаются до WEB_WIDTH пикселей по ширине. Страница вставляется
кодом в Google Сайты, и объём держится около объёма лендингов соседей,
360-460 КБ. Ужатие делает Pillow из Python QGIS.
Устройство и оформление взяты из лендинга Isoliner3D. Тексты обоих
языков лежат здесь в одном месте, править лучше их, а не готовую
страницу.
"""
import base64
import io
import json
import os
import re

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES = os.path.join(ROOT, "doc", "images")
OUT = os.path.join(ROOT, "site", "planetx_landing.html")
WEB_WIDTH = 960  # пикселей, ширина снимка на странице
WEB_QUALITY = 70  # качество JPEG


def version():
    with open(os.path.join(ROOT, "planetx", "metadata.txt"),
              encoding="utf-8") as fh:
        return re.search(r"^version=(\S+)", fh.read(), re.M).group(1)


def image(name):
    """Снимок в строке data: JPEG шириной не больше WEB_WIDTH."""
    with Image.open(os.path.join(IMAGES, name)) as picture:
        picture = picture.convert("RGB")
        if picture.width > WEB_WIDTH:
            height = round(picture.height * WEB_WIDTH / picture.width)
            picture = picture.resize((WEB_WIDTH, height), Image.LANCZOS)
        out = io.BytesIO()
        picture.save(out, "JPEG", quality=WEB_QUALITY, optimize=True,
                     progressive=True)
    data = base64.b64encode(out.getvalue()).decode("ascii")
    return "data:image/jpeg;base64," + data


RU = {
    "title": "PlanetX - трёхмерный глобус для QGIS · Информ++",
    "desc": "PlanetX показывает всю Землю в отдельном окне QGIS: "
            "космоснимки, рельеф, атмосферу, границы, дороги, подписи "
            "и слои проекта. Навигация как в Google Earth.",
    "brand.sub": "для QGIS",
    "nav.idea": "Глобус",
    "nav.layers": "Слои",
    "nav.project": "Проект",
    "nav.controls": "Управление",
    "hero.eyebrow": "Плагин QGIS · 3D-глобус",
    "hero.h1": "Вся Земля в окне QGIS, от космоса до улицы",
    "hero.lead": "PlanetX открывает глобус в духе Google Earth "
                 "в QGIS. Космоснимки лежат на рельефе, вокруг планеты "
                 "светится атмосфера, границы, дороги и названия "
                 "включаются флажками. Слои текущего проекта ложатся "
                 "на глобус в порядке карты.",
    "hero.shot": "Кавказ с наклоном камеры. Эльбрус, Сванетия, вершины "
                 "с высотой, заповедники и национальные парки.",
    "cta.release": "Скачать выпуск",
    "cta.install": "Каталог модулей QGIS",
    "cta.code": "Исходный код",
    "idea.eyebrow": "Как устроен глобус",
    "idea.h2": "Своё окно, свой движок, данные из открытых источников",
    "idea.sub": "Глобус рисуется на OpenGL 3.3 собственным движком, "
                "а не штатным 3D-видом QGIS. Камера держит точку "
                "взгляда, расстояние, азимут и наклон, как в Google "
                "Earth. Тайлы подложки, высот и векторной основы идут "
                "через сетевые настройки и кэш QGIS.",
    "idea.c1.h": "Космоснимки и рельеф",
    "idea.c1.p": "По умолчанию подложка - Esri World Imagery как пример. "
                 "Её можно сменить на OpenStreetMap или на любое "
                 "подключение XYZ Tiles из обозревателя QGIS. Рельеф "
                 "Mapzen Terrain Tiles с отмывкой склонов, вертикальный "
                 "масштаб настраивается.",
    "idea.c2.h": "Точность от космоса до метров",
    "idea.c2.p": "В видеокарту попадают только смещения от центра тайла "
                 "и от глаза. На уровне улиц ошибка положения точки "
                 "на экране меньше тысячной доли пикселя, картинка "
                 "не дрожит.",
    "layers.eyebrow": "Панель «Слои»",
    "layers.h2": "Границы, дороги и названия поверх снимков",
    "layers.sub": "Внизу слева, как в Google Earth, лежат группы "
                  "«Границы и названия», «Транспорт» и «Природа». "
                  "Данные берутся из векторных тайлов OpenFreeMap "
                  "и ложатся по рельефу. Флажки срабатывают сразу.",
    "layers.fig": "Евразия с высоты 9000 км. Названия стран и городов, "
                  "границы стран жёлтые, границы областей тонкие белые.",
    "layers.c1.h": "Подписи как в Google Earth",
    "layers.c1.p": "Надписи остаются ровными при любом повороте и наклоне "
                   "и не налезают друг на друга. Пункт за горой или "
                   "за горизонтом не подписан. При приближении "
                   "появляются всё более мелкие пункты, вершины, "
                   "аэропорты и номера дорог.",
    "layers.c2.h": "Язык подписей",
    "layers.c2.p": "По умолчанию подписи на языке QGIS. В свойствах вида "
                   "выбираются местные названия или один из 15 языков, "
                   "среди них русский, английский, немецкий, казахский "
                   "и китайский.",
    "project.eyebrow": "Слои проекта",
    "project.h2": "Карта проекта ложится на глобус",
    "project.sub": "Векторные и растровые слои проекта рисует сам QGIS "
                   "с их стилями и подписями, глобус кладёт картинку "
                   "на рельеф в порядке карты. Отметка слоя в списке "
                   "окна показывает его на глобусе и не меняет карту. "
                   "Пункт меню «Подлететь» ведёт камеру к охвату слоя.",
    "project.fig": "Пермь с высоты 40 км. Магистрали, железные дороги, "
                   "номера дорог и названия пунктов поверх космоснимка.",
    "controls.eyebrow": "Управление",
    "controls.h2": "Земля тянется мышью",
    "controls.sub": "Навигация повторяет Google Earth. Значок "
                    "«Свойства вида» открывает свойства вида, кнопка "
                    "«О модуле» напоминает управление и источники.",
    "g1": "Мышь и клавиатура",
    "c1.h": "Захват Земли",
    "c1.p": "Точка под курсором следует за мышью. После отпускания "
            "Земля вращается по инерции.",
    "c2.h": "Приближение к курсору",
    "c2.p": "Колесо приближает к точке под курсором, точка остаётся "
            "на месте.",
    "c3.h": "Поворот и наклон",
    "c3.p": "Средняя кнопка или левая с Shift поворачивают и наклоняют "
            "вид, у горизонта видно небо.",
    "c4.h": "Поиск",
    "c4.p": "Название места или координаты и Enter. Камера плавно "
            "перелетает туда, место отмечено красной меткой.",
    "c5.h": "Обновление",
    "c5.p": "Новая подложка и слои проекта видны после кнопки "
            "«Обновить». Можно включить автоматическое обновление.",
    "k1": "ЛКМ", "k2": "Колесо", "k3": "СКМ", "k4": "Enter",
    "k5": "Кнопка",
    "c6.h": "Как в Google Earth",
    "c6.p": "Двойной щелчок подлетает к точке, правая кнопка "
            "приближает и отдаляет, Ctrl поворачивает взгляд. Стрелки, "
            "PageUp, PageDown, N, U и R работают как в Google Earth.",
    "c7.h": "Органы на экране",
    "c7.p": "В правом верхнем углу вида кольцо компаса, джойстики "
            "взгляда и сдвига и ползунок высоты. Они появляются, когда "
            "курсор подходит к углу.",
    "k6": "2×", "k7": "Угол",
    "fact1": "кадров в секунду при вращении глобуса, не меньше, "
             "в любую секунду замера.",
    "fact2": "языков подписей и местные названия.",
    "fact3": "внешних зависимостей. PyOpenGL берётся из состава QGIS.",
    "fam.eyebrow": "Набор плагинов",
    "fam.h2": "PlanetX в линейке Информ++",
    "fam.sub": "Isoliner строит контуры, Topoliner приводит их "
               "в порядок, Isoliner3D показывает геологию в объёме, "
               "PlanetX показывает Землю целиком. Все плагины работают "
               "независимо.",
    "fam.c1.p": "Кригинг, изолинии, рельеф и водосборы, разрезы "
                "с чертежами, геологическая модель пласта.",
    "fam.c2.p": "Чистка топологии контуров и полигонов, прореживание "
                "с сохранением топологии.",
    "fam.c3.p": "Тела пластов, скважины и разрезы в объёме, карта "
                "текстурой на рельефе, блочная модель.",
    "fam.a": "Открыть в каталоге QGIS",
    "ftr.line1": "лицензия GNU GPL v3 · QGIS 3.36 и новее, QGIS 4",
    "ftr.line2": "Разработано ООО «Информ++»",
    "ftr.line3": "Космоснимки Esri, Vantor, Earthstar Geographics, "
                 "and the GIS User Community. Картографические данные "
                 "© участники OpenStreetMap, векторные тайлы OpenFreeMap. "
                 "Рельеф Mapzen Terrain Tiles.",
}

EN = {
    "title": "PlanetX - a 3D globe for QGIS · Inform++",
    "desc": "PlanetX shows the whole Earth in its own QGIS window: "
            "satellite imagery, terrain, atmosphere, borders, roads, "
            "labels and project layers. Navigation as in Google Earth.",
    "brand.sub": "for QGIS",
    "nav.idea": "Globe",
    "nav.layers": "Layers",
    "nav.project": "Project",
    "nav.controls": "Controls",
    "hero.eyebrow": "QGIS plugin · 3D globe",
    "hero.h1": "The whole Earth in a QGIS window, from space to the street",
    "hero.lead": "PlanetX opens a globe in the spirit of Google Earth "
                 "right inside QGIS. Satellite imagery lies on the "
                 "terrain, the atmosphere glows around the planet, and "
                 "borders, roads and names are switched on with check "
                 "boxes. Layers of the current project lie on the globe "
                 "in the map order.",
    "hero.shot": "The Caucasus with a tilted camera. Elbrus, Svaneti, "
                 "peaks with their heights, nature reserves and national "
                 "parks.",
    "cta.release": "Download the release",
    "cta.install": "QGIS plugin catalogue",
    "cta.code": "Source code",
    "idea.eyebrow": "How the globe works",
    "idea.h2": "Its own window, its own engine, data from open sources",
    "idea.sub": "The globe is drawn with OpenGL 3.3 by its own engine "
                "rather than the built-in QGIS 3D view. The camera holds "
                "the look-at point, distance, heading and tilt, as in "
                "Google Earth. Base map, terrain and vector tiles go "
                "through the QGIS network settings and cache.",
    "idea.c1.h": "Satellite imagery and terrain",
    "idea.c1.p": "The default base map is Esri World Imagery as an "
                 "example. It can be switched to OpenStreetMap or to any "
                 "XYZ Tiles connection from the QGIS browser. Mapzen "
                 "Terrain Tiles with hill shading, vertical exaggeration "
                 "is adjustable.",
    "idea.c2.h": "Precision from space to metres",
    "idea.c2.p": "Only offsets from the tile centre and from the eye "
                 "reach the graphics card. At street level the on-screen "
                 "position error of a point is below a thousandth of a "
                 "pixel, and the picture does not jitter.",
    "layers.eyebrow": "The Layers panel",
    "layers.h2": "Borders, roads and names over the imagery",
    "layers.sub": "At the bottom left, as in Google Earth, there are the "
                  "groups Borders and names, Transport and Nature. The "
                  "data come from OpenFreeMap vector tiles and follow the "
                  "terrain. Check boxes take effect at once.",
    "layers.fig": "Eurasia from 9000 km. Names of countries and cities, "
                  "country borders in yellow, region borders thin and "
                  "white.",
    "layers.c1.h": "Labels as in Google Earth",
    "layers.c1.p": "Labels stay upright at any turn and tilt and do not "
                   "overlap. A place behind a mountain or beyond the "
                   "horizon is not labelled. Zooming in brings smaller "
                   "places, peaks, airports and road numbers.",
    "layers.c2.h": "Label language",
    "layers.c2.p": "By default the labels follow the QGIS language. In "
                   "the view properties you can choose local names or "
                   "one of 15 languages, among them English, Russian, "
                   "German, Kazakh and Chinese.",
    "project.eyebrow": "Project layers",
    "project.h2": "The project map lies on the globe",
    "project.sub": "QGIS itself renders the vector and raster layers of "
                   "the project with their styles and labels, and the "
                   "globe lays the picture on the terrain in the map "
                   "order. A check mark in the window list shows a layer "
                   "on the globe and leaves the map unchanged. The Fly to "
                   "menu item takes the camera to the layer extent.",
    "project.fig": "Perm from 40 km. Motorways, railways, road numbers "
                   "and place names over satellite imagery.",
    "controls.eyebrow": "Controls",
    "controls.h2": "Drag the Earth with the mouse",
    "controls.sub": "Navigation follows Google Earth. The View "
                    "properties icon opens the view properties, the About "
                    "button lists the controls and the sources.",
    "g1": "Mouse and keyboard",
    "c1.h": "Grab the Earth",
    "c1.p": "The point under the cursor follows the mouse. After "
            "release the Earth keeps rotating by inertia.",
    "c2.h": "Zoom to the cursor",
    "c2.p": "The wheel zooms to the point under the cursor, and the "
            "point stays in place.",
    "c3.h": "Turn and tilt",
    "c3.p": "The middle button or Shift with the left button turns and "
            "tilts the view, the sky shows at the horizon.",
    "c4.h": "Search",
    "c4.p": "A place name or coordinates and Enter. The camera flies "
            "there smoothly, the place gets a red pin.",
    "c5.h": "Refresh",
    "c5.p": "A new base map and project layers appear after the Refresh "
            "button. Automatic refresh can be switched on.",
    "k1": "Left", "k2": "Wheel", "k3": "Middle", "k4": "Enter",
    "k5": "Button",
    "c6.h": "As in Google Earth",
    "c6.p": "A double click flies to the point, the right button zooms "
            "in and out, Ctrl looks around. Arrows, PageUp, PageDown, N, "
            "U and R work as in Google Earth.",
    "c7.h": "On-screen controls",
    "c7.p": "The top right corner of the view holds the compass ring, "
            "the look and move sticks and the height slider. They appear "
            "when the cursor comes near the corner.",
    "k6": "2×", "k7": "Corner",
    "fact1": "frames per second at least while the globe rotates, in "
             "every second of the measurement.",
    "fact2": "label languages and local names.",
    "fact3": "external dependencies. PyOpenGL ships with QGIS.",
    "fam.eyebrow": "The set of plugins",
    "fam.h2": "PlanetX in the Inform++ family",
    "fam.sub": "Isoliner builds contours, Topoliner puts them in order, "
               "Isoliner3D shows geology in three dimensions, PlanetX "
               "shows the whole Earth. All plugins work independently.",
    "fam.c1.p": "Kriging, isolines, relief and catchments, sections "
                "with drawings, a geological bed model.",
    "fam.c2.p": "Topology cleaning of contours and polygons, thinning "
                "that preserves topology.",
    "fam.c3.p": "Bed bodies, boreholes and sections in three dimensions, "
                "a map draped on the relief, a block model.",
    "fam.a": "Open in the QGIS catalogue",
    "ftr.line1": "GNU GPL v3 · QGIS 3.36 and newer, QGIS 4",
    "ftr.line2": "Developed by Inform++ LLC",
    "ftr.line3": "Imagery Esri, Vantor, Earthstar Geographics, and the "
                 "GIS User Community. Map data © OpenStreetMap "
                 "contributors, vector tiles OpenFreeMap. Terrain Mapzen "
                 "Terrain Tiles.",
}

CONTROLS = "".join(
    '<div class="tool"><div class="num" data-i18n="k{0}"></div>'
    '<div class="txt"><b data-i18n="c{0}.h"></b>'
    '<span data-i18n="c{0}.p"></span></div></div>'.format(i)
    for i in range(1, 8))

PAGE = """<!-- ============================================================ -->
<!-- PlanetX - лендинг для www.informpp.ru                          -->
<!-- Самодостаточная двуязычная страница: снимки встроены в файл,   -->
<!-- переключатель языка работает без перезагрузки.                 -->
<!-- Собирается скриптом tools/build_site.py, править лучше его:    -->
<!-- тексты обоих языков лежат там в одном месте.                   -->
<!-- ============================================================ -->
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" data-i18n-attr="desc" content="">
<title data-i18n="title"></title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Bitter:wght@500;600;700\\
&family=Golos+Text:wght@400;500;600&display=swap');

:root{
  --paper:#EEF2F6; --paper-2:#E2E8EF; --ink:#131C26; --ink-soft:#4A5866;
  --teal:#1D5FA8; --teal-deep:#12457D; --amber:#C2622C;
  --line:rgba(19,28,38,.14); --r:14px; --maxw:1080px;
  --display:'Bitter',Georgia,serif;
  --body:'Golos Text','Segoe UI',system-ui,sans-serif;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
section[id],[id]{scroll-margin-top:74px}
body{margin:0;background:var(--paper);color:var(--ink);
  font-family:var(--body);font-size:17px;line-height:1.6;
  -webkit-font-smoothing:antialiased}
.wrap{max-width:var(--maxw);margin:0 auto;padding:0 24px}
a{color:inherit}
h1,h2,h3{font-family:var(--display);font-weight:700;line-height:1.1;margin:0;
  letter-spacing:-.01em}
p{margin:0}
.eyebrow{font-size:13px;font-weight:600;letter-spacing:.16em;
  text-transform:uppercase;color:var(--teal-deep);margin-bottom:18px;
  display:inline-flex;gap:10px;align-items:center}
.eyebrow::before{content:"";width:26px;height:2px;background:var(--amber);
  display:inline-block}
.hdr{position:sticky;top:0;z-index:20;background:rgba(238,242,246,.86);
  backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
.hdr .wrap{display:flex;align-items:center;justify-content:space-between;
  height:62px;gap:18px}
.brand{display:flex;align-items:baseline;gap:10px;
  font-family:var(--display);font-weight:700;text-decoration:none;
  font-size:20px}
.brand span{font-family:var(--body);font-weight:500;font-size:13px;
  color:var(--ink-soft)}
.right{display:flex;align-items:center;gap:22px}
.nav{display:flex;gap:22px;font-size:15px}
.nav a{text-decoration:none;color:var(--ink-soft)}
.nav a:hover{color:var(--teal-deep)}
@media(max-width:860px){.nav{display:none}}
.lang{display:flex;border:1px solid var(--line);border-radius:10px;
  overflow:hidden;font-size:13px;font-weight:600}
.lang button{border:0;background:transparent;padding:6px 11px;cursor:pointer;
  font:inherit;color:var(--ink-soft)}
.lang button.on{background:var(--teal);color:#fff}
.hero{padding:74px 0 48px}
.hero h1{font-size:clamp(34px,5vw,56px);max-width:18ch}
.hero .lead{margin-top:22px;font-size:20px;max-width:64ch;
  color:var(--ink-soft)}
.cta{margin-top:34px;display:flex;gap:14px;flex-wrap:wrap}
.btn{display:inline-block;padding:13px 22px;border-radius:var(--r);
  text-decoration:none;font-weight:600;font-size:16px}
.btn-main{background:var(--teal);color:#fff}
.btn-main:hover{background:var(--teal-deep)}
.btn-ghost{border:1px solid var(--line);color:var(--ink)}
.btn-ghost:hover{border-color:var(--teal)}
section{padding:56px 0;border-top:1px solid var(--line)}
section h2{font-size:clamp(26px,3.3vw,38px);max-width:24ch}
section .sub{margin-top:16px;max-width:70ch;color:var(--ink-soft)}
.pair{display:grid;grid-template-columns:1fr 1fr;gap:28px;margin-top:34px}
.trio{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;
  margin-top:34px}
@media(max-width:860px){.pair,.trio{grid-template-columns:1fr}}
.card{background:var(--paper-2);border:1px solid var(--line);
  border-radius:var(--r);padding:22px 24px}
.card h3{font-size:19px;margin-bottom:10px}
.card p{color:var(--ink-soft);font-size:16px}
.card p + p{margin-top:10px}
figure{margin:30px 0 0}
figure img{width:100%;height:auto;display:block;border-radius:var(--r);
  border:1px solid var(--line);background:#000}
.shot{margin-top:38px}
figcaption{margin-top:10px;font-size:14px;color:var(--ink-soft)}
.tools{margin-top:34px;border:1px solid var(--line);border-radius:var(--r);
  overflow:hidden;background:#fff}
.group{background:var(--paper-2);padding:10px 20px;font-weight:600;
  font-size:14px;letter-spacing:.04em;border-bottom:1px solid var(--line)}
.tool{display:grid;grid-template-columns:88px 1fr;gap:10px;padding:14px 20px;
  border-bottom:1px solid var(--line)}
.tool:last-child{border-bottom:0}
.num{font-family:var(--display);font-weight:700;color:var(--teal-deep)}
.txt b{display:block;font-size:16px}
.txt span{color:var(--ink-soft);font-size:15px}
.facts{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;
  margin-top:40px}
@media(max-width:860px){.facts{grid-template-columns:1fr}}
.fact b{display:block;font-family:var(--display);font-size:30px;
  line-height:1.1}
.fact span{color:var(--ink-soft);font-size:15px}
.ftr{padding:40px 0 60px;border-top:1px solid var(--line);
  color:var(--ink-soft);font-size:15px}
.ftr a{color:var(--teal-deep)}
</style>

<header class="hdr">
  <div class="wrap">
    <a class="brand" href="#">PlanetX
      <span data-i18n="brand.sub"></span></a>
    <div class="right">
      <nav class="nav">
        <a href="#idea" data-i18n="nav.idea"></a>
        <a href="#layers" data-i18n="nav.layers"></a>
        <a href="#project" data-i18n="nav.project"></a>
        <a href="#controls" data-i18n="nav.controls"></a>
        <a href="#family" data-i18n="fam.eyebrow"></a>
      </nav>
      <div class="lang">
        <button type="button" data-lang="ru">RU</button>
        <button type="button" data-lang="en">EN</button>
      </div>
    </div>
  </div>
</header>

<div class="wrap hero">
  <div class="eyebrow" data-i18n="hero.eyebrow"></div>
  <h1 data-i18n="hero.h1"></h1>
  <p class="lead" data-i18n="hero.lead"></p>
  <div class="cta">
    <a class="btn btn-main" data-i18n="cta.release"
       href="https://github.com/Valery35/planetx/releases/latest"></a>
    <a class="btn btn-ghost" data-i18n="cta.install"
       href="https://plugins.qgis.org/plugins/planetx/"></a>
    <a class="btn btn-ghost" data-i18n="cta.code"
       href="https://github.com/Valery35/planetx"></a>
  </div>
  <figure class="shot">
    <img alt="" src="@CAUCASUS@">
    <figcaption data-i18n="hero.shot"></figcaption>
  </figure>
</div>

<section id="idea">
  <div class="wrap">
    <div class="eyebrow" data-i18n="idea.eyebrow"></div>
    <h2 data-i18n="idea.h2"></h2>
    <p class="sub" data-i18n="idea.sub"></p>
    <div class="pair">
      <div class="card"><h3 data-i18n="idea.c1.h"></h3>
        <p data-i18n="idea.c1.p"></p></div>
      <div class="card"><h3 data-i18n="idea.c2.h"></h3>
        <p data-i18n="idea.c2.p"></p></div>
    </div>
  </div>
</section>

<section id="layers">
  <div class="wrap">
    <div class="eyebrow" data-i18n="layers.eyebrow"></div>
    <h2 data-i18n="layers.h2"></h2>
    <p class="sub" data-i18n="layers.sub"></p>
    <figure><img alt="" src="@EARTH@">
      <figcaption data-i18n="layers.fig"></figcaption></figure>
    <div class="pair">
      <div class="card"><h3 data-i18n="layers.c1.h"></h3>
        <p data-i18n="layers.c1.p"></p></div>
      <div class="card"><h3 data-i18n="layers.c2.h"></h3>
        <p data-i18n="layers.c2.p"></p></div>
    </div>
  </div>
</section>

<section id="project">
  <div class="wrap">
    <div class="eyebrow" data-i18n="project.eyebrow"></div>
    <h2 data-i18n="project.h2"></h2>
    <p class="sub" data-i18n="project.sub"></p>
    <figure><img alt="" src="@PERM@">
      <figcaption data-i18n="project.fig"></figcaption></figure>
  </div>
</section>

<section id="controls">
  <div class="wrap">
    <div class="eyebrow" data-i18n="controls.eyebrow"></div>
    <h2 data-i18n="controls.h2"></h2>
    <p class="sub" data-i18n="controls.sub"></p>
    <div class="tools">
      <div class="group" data-i18n="g1"></div>
      @CONTROLS@
    </div>
    <div class="facts">
      <div class="fact"><b>55</b><span data-i18n="fact1"></span></div>
      <div class="fact"><b>15</b><span data-i18n="fact2"></span></div>
      <div class="fact"><b>0</b><span data-i18n="fact3"></span></div>
    </div>
    <div class="cta">
      <a class="btn btn-main" data-i18n="cta.release"
         href="https://github.com/Valery35/planetx/releases/latest"></a>
      <a class="btn btn-ghost" data-i18n="cta.install"
         href="https://plugins.qgis.org/plugins/planetx/"></a>
    </div>
  </div>
</section>

<section id="family">
  <div class="wrap">
    <div class="eyebrow" data-i18n="fam.eyebrow"></div>
    <h2 data-i18n="fam.h2"></h2>
    <p class="sub" data-i18n="fam.sub"></p>
    <div class="trio">
      <div class="card"><h3>Isoliner</h3>
        <p data-i18n="fam.c1.p"></p>
        <p><a href="https://plugins.qgis.org/plugins/grid_isolines/"
              data-i18n="fam.a"></a></p></div>
      <div class="card"><h3>Topoliner</h3>
        <p data-i18n="fam.c2.p"></p>
        <p><a href="https://plugins.qgis.org/plugins/topoliner/"
              data-i18n="fam.a"></a></p></div>
      <div class="card"><h3>Isoliner3D</h3>
        <p data-i18n="fam.c3.p"></p>
        <p><a href="https://plugins.qgis.org/plugins/isoliner3d/"
              data-i18n="fam.a"></a></p></div>
    </div>
  </div>
</section>

<footer class="ftr">
  <div class="wrap">
    PlanetX @VERSION@ &middot; <span data-i18n="ftr.line1"></span><br>
    <span data-i18n="ftr.line2"></span>,
    <a href="https://www.informpp.ru/">www.informpp.ru</a><br>
    <span data-i18n="ftr.line3"></span>
  </div>
</footer>

<script>
var TEXTS = @TEXTS@;

function apply(lang){
  var d = TEXTS[lang] || TEXTS.ru;
  document.documentElement.lang = lang;
  document.querySelectorAll('[data-i18n]').forEach(function(el){
    var value = d[el.getAttribute('data-i18n')];
    if (value !== undefined) el.innerHTML = value;
  });
  document.querySelectorAll('[data-i18n-attr]').forEach(function(el){
    var value = d[el.getAttribute('data-i18n-attr')];
    if (value !== undefined) el.setAttribute('content', value);
  });
  document.querySelectorAll('.lang button').forEach(function(b){
    b.classList.toggle('on', b.getAttribute('data-lang') === lang);
  });
  try { localStorage.setItem('planetx-lang', lang); } catch (e) {}
}

// Меню прокручивает кодом, а не якорем. Внутри CMS ссылка вида
// «#idea» может вести на другую страницу.
document.querySelectorAll('.nav a[href^="#"]').forEach(function(a){
  a.addEventListener('click', function(ev){
    var el = document.getElementById(a.getAttribute('href').slice(1));
    if (!el) return;
    ev.preventDefault();
    el.scrollIntoView({behavior: 'smooth', block: 'start'});
  });
});

document.querySelectorAll('.lang button').forEach(function(b){
  b.addEventListener('click', function(){
    apply(b.getAttribute('data-lang'));
  });
});

// По умолчанию русский: страница живёт на русском сайте.
var saved = null;
try { saved = localStorage.getItem('planetx-lang'); } catch (e) {}
apply(saved || 'ru');

// Тексты подставляются после разбора страницы, переход по адресу
// с решёткой доводится до места вручную.
(function () {
  var id = (location.hash || '').slice(1);
  if (!id) return;
  var go = function () {
    var el = document.getElementById(id);
    if (el) el.scrollIntoView({block: 'start'});
  };
  go();
  setTimeout(go, 0);
  window.addEventListener('load', go);
})();
</script>
"""


def main():
    missing = sorted(set(RU) ^ set(EN))
    if missing:
        raise SystemExit("ключи без пары: " + ", ".join(missing))
    page = PAGE
    for mark, value in (
            ("@CAUCASUS@", image("caucasus.jpg")),
            ("@EARTH@", image("earth.jpg")),
            ("@PERM@", image("perm.jpg")),
            ("@CONTROLS@", CONTROLS),
            ("@VERSION@", version()),
            ("@TEXTS@", json.dumps({"ru": RU, "en": EN},
                                   ensure_ascii=False))):
        if page.count(mark) != 1:
            raise SystemExit("метка %s найдена %d раз" % (mark,
                                                          page.count(mark)))
        page = page.replace(mark, value)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "wb") as fh:
        fh.write(page.encode("utf-8"))
    print("%s, %d КБ" % (os.path.relpath(OUT, ROOT), len(page) // 1024))


if __name__ == "__main__":
    main()
