# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Демо «Тоннели Vegas Loop»: тоннели The Boring Company в Лас-Вегасе.

    $PY tools/make_tunnel_demo.py

Геометрия - OpenStreetMap (© OpenStreetMap contributors, ODbL), один
запрос к Overpass API: дороги оператора The Boring Company и станции
сети Vegas Loop. Пишет planetx/demo/vegas/vegas_loop.gpkg - таблица
tunnels подземного режима (ui/subsurface.py) - и stations.json для
меток сцены (tools/make_demo.py).

Глубины в OSM нет. Ось тоннеля - на DEPTH под поверхностью, около
40 футов по открытым сведениям о тоннелях LVCC Loop, одно значение на
всю сеть. Дорога с incline - спуск к порталу: от поверхности до DEPTH
по ходу линии (down) или обратно (up). В расчёт идут дороги с tunnel
или covered, а также спуски. Открытые участки у станций на поверхности
и в выемке (cutting) не рисуются. Выбор помощника, утверждает автор.
"""
import json
import os
import urllib.parse
import urllib.request

from osgeo import ogr, osr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "planetx", "demo", "vegas")
GPKG = os.path.join(OUT, "vegas_loop.gpkg")
STATIONS = os.path.join(OUT, "stations.json")
AGENT = "PlanetX (+https://github.com/Valery35/planetx)"
OVERPASS = "https://overpass-api.de/api/interpreter"
BOX = (36.05, -115.25, 36.20, -115.10)  # юг, запад, север, восток
DEPTH = 12.0  # м, ось тоннеля под поверхностью
DIAMETER = 3.7  # м, 12 футов
COLOR = "#5aa0dc"
QUERY = """[out:json][timeout:90];
(way["operator"="The Boring Company"]({s},{w},{n},{e});
 node["operator"="The Boring Company"]["amenity"]({s},{w},{n},{e}););
out geom tags;"""


def fetch():
    body = urllib.parse.urlencode({"data": QUERY.format(
        s=BOX[0], w=BOX[1], n=BOX[2], e=BOX[3])}).encode("ascii")
    request = urllib.request.Request(OVERPASS, data=body,
                                     headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=120) as reply:
        return json.loads(reply.read())


def depths(tags):
    """Глубины начала и конца линии или None - участок не тоннель."""
    incline = tags.get("incline")
    if incline == "down":
        return 0.0, DEPTH
    if incline == "up":
        return DEPTH, 0.0
    if tags.get("tunnel") == "yes" or tags.get("covered") == "yes":
        return DEPTH, DEPTH
    return None


def main():
    ogr.UseExceptions()
    osr.UseExceptions()
    data = fetch()
    os.makedirs(OUT, exist_ok=True)
    if os.path.exists(GPKG):
        os.remove(GPKG)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    ds = ogr.GetDriverByName("GPKG").CreateDataSource(GPKG)
    layer = ds.CreateLayer("tunnels", srs, ogr.wkbLineString)
    for name, kind in (("name", ogr.OFTString), ("depth", ogr.OFTReal),
                       ("depth_end", ogr.OFTReal),
                       ("diameter", ogr.OFTReal), ("color", ogr.OFTString),
                       ("osm_id", ogr.OFTInteger64)):
        layer.CreateField(ogr.FieldDefn(name, kind))
    count = 0
    length = 0.0
    stations = []
    for element in data.get("elements", []):
        tags = element.get("tags", {})
        if element["type"] == "node":
            stations.append({"name": tags.get("name", ""),
                             "lat": element["lat"], "lon": element["lon"]})
            continue
        found = depths(tags)
        points = element.get("geometry") or []
        if found is None or len(points) < 2:
            continue
        line = ogr.Geometry(ogr.wkbLineString)
        for p in points:
            line.AddPoint_2D(p["lon"], p["lat"])
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetField("name", tags.get("name", "Vegas Loop"))
        feature.SetField("depth", found[0])
        feature.SetField("depth_end", found[1])
        feature.SetField("diameter", DIAMETER)
        feature.SetField("color", COLOR)
        feature.SetField("osm_id", element["id"])
        feature.SetGeometry(line)
        layer.CreateFeature(feature)
        count += 1
        length += line.Length() * 111000.0
    ds = None
    stations.sort(key=lambda s: s["name"])
    with open(STATIONS, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(stations, fh, ensure_ascii=False, indent=1)
    print(GPKG, "линий", count, "длина около %.1f км" % (length / 1000.0),
          "станций", len(stations))


if __name__ == "__main__":
    main()
