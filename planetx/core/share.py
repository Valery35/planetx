# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""«Поделиться видом»: страница HTML с глобусом, открывается без QGIS.

Выбор автора от 12 октября 2026 года. Страница - один файл. Глобус
рисует MapLibre GL JS (BSD) в проекции globe, библиотека грузится
с CDN unpkg.com. Основа - векторный стиль OpenFreeMap, рельеф - тайлы
Terrarium, те же, что у модуля. Подложка Esri на страницу не идёт,
её условия задаёт Esri. Камера ставится по позе глобуса. Метки, пути
и многоугольники выбранного в «Моих метках» ложатся в страницу
данными GeoJSON. Облёт страницы - записанный тур, а без него -
перелёты по видам меток. Слои проекта QGIS, наложения картинок
и время меток на страницу не идут.

Модуль Qt не знает.
"""
import json
import math

try:  # внутри плагина QGIS
    from .kml import KFolder, KPlace, escape
except ImportError:  # headless-тесты
    from kml import KFolder, KPlace, escape

# Версия библиотеки закреплена, страница не меняется с выходом новой.
MAPLIBRE = "https://unpkg.com/maplibre-gl@5.6.0/dist/maplibre-gl"
STYLE = "https://tiles.openfreemap.org/styles/liberty"
TERRAIN = ("https://s3.amazonaws.com/elevation-tiles-prod/terrarium/"
           "{z}/{x}/{y}.png")
TERRAIN_CREDIT = ('Terrain: <a href="https://github.com/tilezen/joerd/'
                  'blob/master/docs/attribution.md">Mapzen, SRTM, GMTED, '
                  'ETOPO1 and others</a>')
TERRAIN_MAX = 15
# MapLibre не наклоняет камеру сильнее.
MAX_PITCH = 85.0
# Вид точки без своего вида в облёте: расстояние и наклон. Выбор
# помощника, утверждает автор.
POINT_DISTANCE = 3000.0  # м
POINT_TILT = 45.0
PAUSE = 3.0  # секунд на остановке облёта, как у тура модуля
FOV = 45.0  # вертикальный угол обзора камеры глобуса, градусы
# Записанный облёт не длиннее, вершин линии - не больше. Страница
# остаётся лёгкой.
TOUR_SAMPLES = 20000
DIGITS = 6  # знаков после запятой у градусов, около 0.1 м


def hex_color(rgba):
    """Цвет RGBA 0-255 строкой #rrggbb и непрозрачностью 0-1."""
    r, g, b = (max(0, min(255, int(v))) for v in rgba[:3])
    alpha = rgba[3] / 255.0 if len(rgba) > 3 else 1.0
    return "#%02x%02x%02x" % (r, g, b), round(max(0.0, min(1.0, alpha)), 3)


def _coords(points):
    return [[round(float(lon), DIGITS), round(float(lat), DIGITS)]
            for lat, lon in points]


def _view(view):
    """Вид core.lookat списком чисел или None."""
    if view is None:
        return None
    return [round(float(v), DIGITS) for v in tuple(view)[:5]]


def feature(place):
    """Метка KPlace объектом GeoJSON Feature или None."""
    if not place.points:
        return None
    coords = _coords(place.points)
    if place.kind == "point":
        geometry = {"type": "Point", "coordinates": coords[0]}
    elif place.kind == "line":
        if len(coords) < 2:
            return None
        geometry = {"type": "LineString", "coordinates": coords}
    elif place.kind == "polygon":
        if len(coords) < 3:
            return None
        geometry = {"type": "Polygon",
                    "coordinates": [coords + [coords[0]]]}
    else:
        return None
    color, opacity = hex_color(place.color)
    props = {"kind": place.kind, "name": place.name or "",
             "description": place.description or "",
             "color": color, "opacity": opacity,
             "width": float(place.width or 2.0)}
    if place.fill is not None:
        props["fill"], props["fill_opacity"] = hex_color(place.fill)
    else:
        props["fill"], props["fill_opacity"] = color, 0.0
    view = _view(place.view)
    if view is not None:
        props["view"] = view
    return {"type": "Feature", "geometry": geometry, "properties": props}


def visible_places(folder):
    """Видимые метки папки по порядку, без записанных туров. Скрытая
    папка скрывает всё внутри, как на глобусе."""
    out = []
    for child in folder.children:
        if not getattr(child, "visible", True):
            continue
        if isinstance(child, KFolder):
            out.extend(visible_places(child))
        elif isinstance(child, KPlace) and not child.tour:
            out.append(child)
    return out


def recorded_tour(folder):
    """Позы первого записанного тура папки или None."""
    for child in folder.children:
        if isinstance(child, KFolder):
            found = recorded_tour(child)
            if found is not None:
                return found
        elif isinstance(child, KPlace) and child.tour:
            return child.tour
    return None


def tour(folder):
    """Облёт страницы: {"record": позы} или {"stops": виды}, None без
    облёта. Остановка - вид метки, у точки без вида - вид сверху
    на POINT_DISTANCE с наклоном POINT_TILT."""
    samples = recorded_tour(folder)
    if samples:
        step = max(1, int(math.ceil(len(samples) / TOUR_SAMPLES)))
        return {"record": [[round(float(v), DIGITS) for v in pose]
                           for pose in samples[::step]]}
    stops = []
    for place in visible_places(folder):
        view = _view(place.view)
        if view is None and place.kind == "point":
            lat, lon = place.points[0]
            view = [round(float(lat), DIGITS), round(float(lon), DIGITS),
                    POINT_DISTANCE, 0.0, POINT_TILT]
        if view is not None:
            stops.append({"name": place.name or "", "view": view})
    return {"stops": stops, "pause": PAUSE} if stops else None


def page_data(pose, folder=None, relief=True, scale=1.0, texts=None,
              fov=FOV):
    """Данные страницы словарём: камера (широта, долгота, расстояние,
    азимут, наклон), метки, облёт, рельеф и подписи кнопок. fov -
    вертикальный угол обзора глобуса в градусах, с ним кадр страницы
    тот же, что у глобуса."""
    places = visible_places(folder) if folder is not None else []
    features = [f for f in (feature(p) for p in places) if f is not None]
    camera = [round(float(v), DIGITS) for v in tuple(pose)[:5]]
    camera[4] = min(camera[4], MAX_PITCH)
    return {"camera": camera,
            "places": {"type": "FeatureCollection", "features": features},
            "tour": tour(folder) if folder is not None else None,
            "relief": bool(relief), "scale": float(scale),
            "style": STYLE, "terrain": TERRAIN,
            "terrain_credit": TERRAIN_CREDIT, "terrain_max": TERRAIN_MAX,
            "max_pitch": MAX_PITCH, "fov": float(fov),
            "texts": dict(texts or {})}


def _script_json(data):
    """JSON для вставки в <script>: «</» не закрывает тег."""
    return json.dumps(data, ensure_ascii=False).replace("</", "<\\/")


def page(title, data, language="ru"):
    """Текст страницы HTML."""
    return TEMPLATE.replace("{{LANG}}", escape(language)) \
        .replace("{{TITLE}}", escape(title)) \
        .replace("{{MAPLIBRE}}", MAPLIBRE) \
        .replace("{{DATA}}", _script_json(data))


TEMPLATE = """<!doctype html>
<html lang="{{LANG}}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="PlanetX">
<title>{{TITLE}}</title>
<link rel="stylesheet" href="{{MAPLIBRE}}.css">
<script src="{{MAPLIBRE}}.js"></script>
<style>
html, body { margin: 0; height: 100%; background: #000; }
#map { position: absolute; inset: 0; }
#bar { position: absolute; top: 10px; left: 10px; display: flex;
  gap: 6px; flex-wrap: wrap; font: 14px system-ui, sans-serif; }
#bar button { border: 0; border-radius: 4px; padding: 6px 10px;
  background: #1f6fd1; color: #fff; cursor: pointer; }
#bar button:hover { background: #2a7fe6; }
#title { color: #fff; padding: 6px 4px; text-shadow: 0 0 3px #000; }
.maplibregl-popup-content { max-width: 320px; white-space: pre-wrap; }
</style>
</head>
<body>
<div id="map"></div>
<div id="bar"><span id="title"></span></div>
<script id="planetx-data" type="application/json">{{DATA}}</script>
<script>
"use strict";
const D = JSON.parse(document.getElementById("planetx-data").textContent);
const R = 6378137;
document.getElementById("title").textContent = document.title;

// Поза PlanetX - широта, долгота, расстояние до точки взгляда в метрах,
// азимут, наклон - в камеру MapLibre. Масштаб пикселя в центре
// globe равен масштабу Меркатора на широте центра.
function camera(map, v) {
  const h = map.getCanvas().clientHeight || 600;
  const fov = map.getVerticalFieldOfView ? map.getVerticalFieldOfView()
                                         : 36.87;
  const lat = Math.max(-85, Math.min(85, v[0]));
  const px = h / 2 / Math.tan(fov * Math.PI / 360);
  const zoom = Math.log2(px * 2 * Math.PI * R *
                         Math.cos(lat * Math.PI / 180) / (512 * v[2]));
  return {center: [v[1], v[0]], zoom: Math.max(0, Math.min(22, zoom)),
          bearing: v[3], pitch: Math.min(D.max_pitch, Math.max(0, v[4]))};
}

const map = new maplibregl.Map({container: "map", style: D.style,
  maxPitch: D.max_pitch, attributionControl: {compact: true}});
if (map.setVerticalFieldOfView) map.setVerticalFieldOfView(D.fov);
map.jumpTo(camera(map, D.camera));
map.addControl(new maplibregl.NavigationControl({visualizePitch: true}));
map.addControl(new maplibregl.ScaleControl(), "bottom-left");

map.on("style.load", () => {
  map.setProjection({type: "globe"});
  if (D.relief) {
    map.addSource("planetx-terrain", {type: "raster-dem",
      tiles: [D.terrain], tileSize: 256, encoding: "terrarium",
      maxzoom: D.terrain_max, attribution: D.terrain_credit});
    map.setTerrain({source: "planetx-terrain", exaggeration: D.scale});
  }
  // Подписи - своим источником: без шрифтов стиля пропадают только
  // они, геометрия того же источника осталась бы без тайлов.
  map.addSource("planetx", {type: "geojson", data: D.places});
  map.addSource("planetx-names", {type: "geojson", data: D.places});
  map.addLayer({id: "planetx-fill", type: "fill", source: "planetx",
    filter: ["==", ["get", "kind"], "polygon"],
    paint: {"fill-color": ["get", "fill"],
            "fill-opacity": ["get", "fill_opacity"]}});
  map.addLayer({id: "planetx-line", type: "line", source: "planetx",
    filter: ["!=", ["get", "kind"], "point"],
    layout: {"line-join": "round", "line-cap": "round"},
    paint: {"line-color": ["get", "color"], "line-width": ["get", "width"],
            "line-opacity": ["get", "opacity"]}});
  map.addLayer({id: "planetx-point", type: "circle", source: "planetx",
    filter: ["==", ["get", "kind"], "point"],
    paint: {"circle-color": ["get", "color"], "circle-radius": 6,
            "circle-opacity": ["get", "opacity"],
            "circle-stroke-color": "#000", "circle-stroke-width": 1}});
  map.addLayer({id: "planetx-name", type: "symbol",
    source: "planetx-names",
    layout: {"text-field": ["get", "name"], "text-size": 13,
             "text-font": ["Noto Sans Regular"],
             "text-offset": [0, 1.1], "text-anchor": "top",
             "symbol-placement": "point"},
    paint: {"text-color": "#fff", "text-halo-color": "#000",
            "text-halo-width": 1.5}});
});

// Щелчок по метке - название и описание текстом.
for (const id of ["planetx-point", "planetx-line", "planetx-fill"]) {
  map.on("click", id, (e) => {
    const p = e.features[0].properties;
    const box = document.createElement("div");
    const name = document.createElement("b");
    name.textContent = p.name;
    box.appendChild(name);
    if (p.description) {
      box.appendChild(document.createElement("br"));
      box.appendChild(document.createTextNode(p.description));
    }
    new maplibregl.Popup().setLngLat(e.lngLat).setDOMContent(box)
      .addTo(map);
  });
  map.on("mouseenter", id, () => map.getCanvas().style.cursor = "pointer");
  map.on("mouseleave", id, () => map.getCanvas().style.cursor = "");
}

const bar = document.getElementById("bar");
function button(text, run) {
  const b = document.createElement("button");
  b.textContent = text;
  b.onclick = run;
  bar.insertBefore(b, document.getElementById("title"));
  return b;
}
button(D.texts.home || "Home", () => {
  stop();
  map.flyTo(camera(map, D.camera));
});

// Облёт: записанный тур идёт позами по времени, остановки - перелётами
// с паузой.
let playing = 0;
function stop() {
  playing += 1;
  map.stop();
  if (play) play.textContent = D.texts.play || "Play";
}
function mix(a, b, s) { return a + (b - a) * s; }
function turn(a, b, s) { const d = ((b - a + 540) % 360) - 180;
                         return a + d * s; }
function record(run, poses) {
  const t0 = performance.now() / 1000 - poses[0][0];
  let i = 0;
  function frame() {
    if (run !== playing) return;
    const t = performance.now() / 1000 - t0;
    while (i < poses.length - 2 && poses[i + 1][0] <= t) i += 1;
    const a = poses[i], b = poses[i + 1] || a;
    const s = b[0] > a[0] ? Math.max(0, Math.min(1, (t - a[0]) /
                                                   (b[0] - a[0]))) : 1;
    map.jumpTo(camera(map, [mix(a[1], b[1], s), turn(a[2], b[2], s),
      mix(a[3], b[3], s), turn(a[4], b[4], s), mix(a[5], b[5], s)]));
    if (t >= poses[poses.length - 1][0]) { stop(); return; }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}
function stops(run, list, pause, i) {
  if (run !== playing) return;
  if (i >= list.length) { stop(); return; }
  map.flyTo(Object.assign(camera(map, list[i].view), {essential: true}));
  map.once("moveend", () => {
    if (run === playing) setTimeout(() => stops(run, list, pause, i + 1),
                                    pause * 1000);
  });
}
let play = null;
if (D.tour) {
  play = button(D.texts.play || "Play", () => {
    if (play.textContent !== (D.texts.play || "Play")) { stop(); return; }
    playing += 1;
    play.textContent = D.texts.stop || "Stop";
    if (D.tour.record) record(playing, D.tour.record);
    else stops(playing, D.tour.stops, D.tour.pause, 0);
  });
}
</script>
</body>
</html>
"""
