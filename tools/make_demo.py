# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Демо PlanetX: сцена «Пермь» со всеми возможностями меток.

    $PY tools/make_demo.py

Пишет planetx/demo/perm.planetx - файл сцены (core/scene.py) с папкой
меток в KML. Открывается меню «Сцена» - «Демо «Пермь»». В демо метки
со значками и временем прогулки по часам, виды меток с датой,
маршрут, многоугольник с выдавливанием, путь с измерением и
записанный облёт центра. В сцене включены 3D-здания и звёзды.

Координаты мест - из Nominatim, 30 сентября 2026 года. Время
прогулки - пример, 30 сентября 2026 года по времени Перми (+05:00).
"""
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "planetx", "core"))

from kml import KFolder, KPlace, write_kml  # noqa: E402
from scene import Scene, write_scene  # noqa: E402

OUT = os.path.join(ROOT, "planetx", "demo", "perm.planetx")
FOLDER = "PlanetX: демо, Пермь"

ORANGE = (255, 140, 0, 255)
BLUE = (30, 144, 255, 255)
GREEN = (60, 180, 75, 255)
RED = (230, 40, 40, 255)
YELLOW = (255, 214, 0, 255)
WHITE = (255, 255, 255, 255)

# Места: название, широта, долгота, значок, цвет, время прогулки.
WALK = (
    ("Вокзал Пермь-1", 58.0200943, 56.2513640, "rail", BLUE, "09:00"),
    ("Речной вокзал", 58.0207397, 56.2515247, "ship", BLUE, "09:30"),
    ("Театр оперы и балета", 58.0160238, 56.2458075, "museum", RED,
     "11:00"),
    ("Эспланада", 58.0093034, 56.2228252, "tree", GREEN, "12:30"),
    ("Пермский университет", 58.0076735, 56.1874542, "school", ORANGE,
     "15:00"),
)
AROUND = (
    ("Камская ГЭС", 58.1147715, 56.3303374, "water", BLUE),
    ("Аэропорт Большое Савино", 57.9204465, 56.0194435, "airport", WHITE),
    ("Мотовилиха", 58.0358870, 56.3073378, "flag", RED),
)
DAY = "2026-09-30T{}:00+05:00"


def at(clock):
    return DAY.format(clock)


def walk_folder():
    places = []
    for name, lat, lon, icon, color, clock in WALK:
        places.append(KPlace(
            name, "point", [(lat, lon)], color=color, icon=icon,
            time=(at(clock), at(clock)),
            view=(lat, lon, 900.0, 20.0, 60.0),
            view_time=(at(clock), at(clock)),
            description="Остановка прогулки в {}. Метка видна на шкале "
                        "времени с этого часа.".format(clock)))
    route = [(lat, lon) for _, lat, lon, _, _, _ in WALK]
    places.append(KPlace(
        "Маршрут прогулки", "line", route, color=ORANGE, width=4.0,
        time=(at("09:00"), at("16:00")),
        description="Путь со временем от 09:00 до 16:00. Меню - «Тур по "
                    "пути», «Профиль высот»."))
    return KFolder("Прогулка 30 сентября 2026", children=places)


def esplanade():
    """Эспланада прямоугольником, выдавлена на 30 м для примера."""
    return [(58.0100, 56.2140), (58.0100, 56.2320), (58.0086, 56.2320),
            (58.0086, 56.2140)]


def orbit(lat, lon, seconds=30.0, step=0.5):
    """Записанный облёт точки: полный круг азимута, наклон 60°."""
    samples = []
    count = int(seconds / step)
    for k in range(count + 1):
        t = k * step
        share = t / seconds
        samples.append((t, lat, lon, 2500.0 - 800.0 * math.sin(
            math.pi * share), (360.0 * share) % 360.0, 60.0))
    return samples


def around_folder():
    places = [KPlace(name, "point", [(lat, lon)], color=color, icon=icon,
                     view=(lat, lon, 3000.0, 0.0, 55.0))
              for name, lat, lon, icon, color in AROUND]
    places.append(KPlace(
        "Эспланада, выдавлена на 30 м", "polygon", esplanade(),
        color=WHITE, fill=(60, 180, 75, 110), height=30.0, extrude=True,
        description="Многоугольник с подъёмом и стеной до земли, как "
                    "«Выдавить до земли» в Google Earth."))
    kama = [(58.0207397, 56.2515247), (58.0300, 56.2700),
            (58.0500, 56.2900), (58.0800, 56.3100),
            (58.1147715, 56.3303374)]
    places.append(KPlace(
        "Вдоль Камы до ГЭС", "line", kama, color=YELLOW, width=3.0,
        description="Путь линейки. Длина, профиль высот и тур по пути "
                    "- из меню метки."))
    samples = orbit(58.0093034, 56.2228252)
    places.append(KPlace("Облёт центра", "line",
                         [(s[1], s[2]) for s in samples], tour=samples,
                         description="Записанный тур, как запись тура "
                                     "Google Earth."))
    return KFolder("Окрестности", children=places)


def main():
    root = KFolder(FOLDER, children=[walk_folder(), around_folder()])
    view = {"basemap": "Esri World Imagery", "relief": True, "scale": 1.0,
            "groups": ["borders", "places", "roads", "water_names"],
            "extras": {"grid": False, "stars": True, "clouds": False,
                       "temperature": False, "buildings": True}}
    scene = Scene((58.0105, 56.2294, 5000.0, 20.0, 55.0), None, [], view,
                  FOLDER, "Пермь")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "wb") as fh:
        fh.write(write_scene(scene, write_kml(root)))
    print(OUT, os.path.getsize(OUT))


if __name__ == "__main__":
    main()
