# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""
Файл созвездий planetx/data/constellations.json из данных d3-celestial.

    python tools/build_constellations.py папка

В папке лежат файлы из https://github.com/ofrohn/d3-celestial/tree/master/data:
constellations.lines.json, constellations.json, starnames.json,
stars.6.json. Данные d3-celestial - © 2015 Olaf Frohn, лицензия BSD
с тремя пунктами, текст лицензии лежит рядом с файлом созвездий.

В файл идут:
- lines - линии фигур созвездий, ломаные из точек [RA, Dec] в градусах
- names - созвездия: латинское сокращение, название по-русски
  и латинское название МАС, место подписи
- stars - собственные имена звёзд ярче STAR_MAG: имена по-русски
  и по-английски, место, величина

Координаты - J2000. В d3-celestial прямое восхождение больше 180°
записано отрицательной долготой, здесь оно от 0 до 360°.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "planetx", "data", "constellations.json")
STAR_MAG = 2.0  # имена звёзд ярче этой величины


def ra(value):
    return round(value % 360.0, 4)


def text(value):
    """Название с обычными пробелами: в d3-celestial встречаются
    узкие пробелы U+2005 и U+2009."""
    return " ".join(value.replace(" ", " ").replace(" ", " ")
                    .split())


def load(folder, name):
    with open(os.path.join(folder, name), encoding="utf-8") as fh:
        return json.load(fh)


def build(folder):
    lines = []
    for feature in load(folder, "constellations.lines.json")["features"]:
        for part in feature["geometry"]["coordinates"]:
            lines.append([[ra(lon), round(lat, 4)] for lon, lat in part])
    names = []
    for feature in load(folder, "constellations.json")["features"]:
        props = feature["properties"]
        lon, lat = feature["geometry"]["coordinates"]
        # По-английски - латинское название МАС: «en» d3-celestial
        # у Большой Медведицы - Big Dipper, это астеризм.
        names.append({"id": feature["id"],
                      "ru": text(props.get("ru") or props["name"]),
                      "en": text(props["name"]),
                      "ra": ra(lon), "dec": round(lat, 4),
                      "rank": int(props.get("rank") or 3)})
    places = {}
    for feature in load(folder, "stars.6.json")["features"]:
        lon, lat = feature["geometry"]["coordinates"]
        places[str(feature["id"])] = (ra(lon), round(lat, 4),
                                      feature["properties"]["mag"])
    stars = []
    for hip, props in load(folder, "starnames.json").items():
        if not props.get("name") or hip not in places:
            continue
        star_ra, star_dec, mag = places[hip]
        if mag >= STAR_MAG:
            continue
        stars.append({"ru": text(props.get("ru") or props["name"]),
                      "en": text(props["name"]), "ra": star_ra,
                      "dec": star_dec,
                      "mag": mag})
    stars.sort(key=lambda s: s["mag"])
    return {"source": "d3-celestial, (c) 2015 Olaf Frohn, BSD 3-Clause",
            "lines": lines, "names": names, "stars": stars}


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    data = build(sys.argv[1])
    with open(TARGET, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
    print("lines %d, names %d, stars %d, %d bytes" % (
        len(data["lines"]), len(data["names"]), len(data["stars"]),
        os.path.getsize(TARGET)))


if __name__ == "__main__":
    main()
