# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Демо PlanetX: сцены для кнопки «Демо» панели значков.

    $PY tools/make_demo.py

Пишет в planetx/demo файлы сцен (core/scene.py) с папкой меток в KML:

- perm - Пермь со всеми возможностями меток: значки и время прогулки
  по часам, виды меток с датой, маршрут, многоугольник с выдавливанием,
  путь с измерением и записанный облёт центра, 3D-здания и звёзды.
  Координаты - из Nominatim, 30 сентября 2026 года. Время прогулки -
  пример, 30 сентября 2026 года по времени Перми (+05:00).
- bocachica - Starbase у Бока-Чики, Техас: стартовая площадка,
  завод, пляж, соседние города и облёт площадки. Координаты - из
  Nominatim, 1 октября 2026 года.
- mars - места посадок марсоходов и крупные формы рельефа Марса.
- moon - места посадок «Аполлонов» и «Луноходов».
- sky - созвездия и объекты осеннего и зимнего неба.

Координаты посадок - опубликованные NASA и CNSA, округлены до сотых
градуса. Виды меток - выбор помощника.
"""
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "planetx", "core"))

from kml import KFolder, KPlace, write_kml  # noqa: E402
from scene import Scene, write_scene  # noqa: E402
from skyview import distance_for  # noqa: E402

DEMO = os.path.join(ROOT, "planetx", "demo")
OUT = os.path.join(DEMO, "perm.planetx")
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


EARTH_VIEW = {"basemap": "Esri World Imagery", "relief": True, "scale": 1.0,
              "groups": ["borders", "places", "roads", "water_names"],
              "extras": {"grid": False, "stars": True, "clouds": False,
                         "temperature": False, "buildings": True}}


def save(name, scene, root):
    path = os.path.join(DEMO, name + ".planetx")
    os.makedirs(DEMO, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(write_scene(scene, write_kml(root)))
    print(path, os.path.getsize(path))


def perm():
    root = KFolder(FOLDER, children=[walk_folder(), around_folder()])
    scene = Scene((58.0105, 56.2294, 5000.0, 20.0, 55.0), None, [],
                  EARTH_VIEW, FOLDER, "Пермь")
    save("perm", scene, root)


# Starbase: название, широта, долгота, значок, цвет, вид (расстояние,
# азимут, наклон), описание.
STARBASE = (
    ("Стартовая площадка Starbase", 25.9968827, -97.1546195, "flag", RED,
     (2500.0, 300.0, 55.0),
     "Стартовый комплекс SpaceX у Бока-Чики, отсюда летает Starship."),
    ("Завод Starfactory", 25.9875974, -97.1863973, "house", ORANGE,
     (1500.0, 20.0, 60.0),
     "Сборочные цеха Starbase, в 3 км от стартовой площадки."),
    ("Пляж Бока-Чика", 26.0091148, -97.1515492, "swim", BLUE,
     (3000.0, 180.0, 50.0),
     "Песчаный пляж у Мексиканского залива, с него смотрят старты."),
    ("Порт-Изабел", 26.0734119, -97.2085844, "ship", BLUE,
     (4000.0, 0.0, 45.0), "Город у лагуны Лагуна-Мадре."),
    ("Саут-Падре-Айленд", 26.1036887, -97.1646938, "hotel", GREEN,
     (5000.0, 0.0, 45.0), "Курортный остров к северу от Starbase."),
)


def bocachica():
    name = "PlanetX: демо, Бока-Чика"
    places = [KPlace(title, "point", [(lat, lon)], color=color, icon=icon,
                     view=(lat, lon) + view, description=text)
              for title, lat, lon, icon, color, view, text in STARBASE]
    road = [(25.9024289, -97.4981698), (25.9530, -97.3900),
            (25.9750, -97.2600), (25.9914611, -97.1829783),
            (25.9968827, -97.1546195)]
    places.append(KPlace(
        "Шоссе 4 из Браунсвилла", "line", road, color=YELLOW, width=3.0,
        description="Дорога к Starbase. В меню - «Тур по пути» "
                    "и «Профиль высот»."))
    samples = orbit(25.9968827, -97.1546195)
    places.append(KPlace("Облёт стартовой площадки", "line",
                         [(s[1], s[2]) for s in samples], tour=samples,
                         description="Записанный тур вокруг площадки."))
    root = KFolder(name, children=places)
    scene = Scene((25.995, -97.17, 12000.0, 60.0, 50.0), None, [],
                  EARTH_VIEW, name, "Бока-Чика")
    save("bocachica", scene, root)


# Марс и Луна: название, широта, долгота, расстояние вида, описание.
MARS = (
    ("Гора Олимп", 18.65, -133.80, 1.5e6,
     "Самый высокий вулкан Солнечной системы, около 22 км над равниной."),
    ("Долины Маринер", -13.90, -59.20, 2.5e6,
     "Система каньонов длиной около 4000 км."),
    ("«Кьюриосити», кратер Гейл", -4.59, 137.44, 6.0e5,
     "Марсоход NASA, посадка 6 августа 2012 года."),
    ("«Персеверанс», кратер Езеро", 18.44, 77.45, 5.0e5,
     "Марсоход NASA, посадка 18 февраля 2021 года."),
    ("«Чжужун», равнина Утопия", 25.07, 109.93, 5.0e5,
     "Марсоход CNSA, посадка 14 мая 2021 года."),
    ("«Спирит», кратер Гусев", -14.57, 175.47, 5.0e5,
     "Марсоход NASA, посадка 4 января 2004 года."),
    ("«Оппортьюнити», плато Меридиана", -1.95, -5.53, 5.0e5,
     "Марсоход NASA, посадка 25 января 2004 года."),
)
MOON = (
    ("«Аполлон-11»", 0.67, 23.47, 4.0e5,
     "Первая высадка людей на Луну, 20 июля 1969 года, Море Спокойствия."),
    ("«Аполлон-12»", -3.01, -23.42, 4.0e5,
     "Океан Бурь, 19 ноября 1969 года."),
    ("«Аполлон-14»", -3.65, -17.47, 4.0e5,
     "Район Фра Мауро, 5 февраля 1971 года."),
    ("«Аполлон-15»", 26.13, 3.63, 4.0e5,
     "Борозда Хэдли, 30 июля 1971 года, первый луноход экипажа."),
    ("«Аполлон-16»", -8.97, 15.50, 4.0e5,
     "Нагорье Декарта, 21 апреля 1972 года."),
    ("«Аполлон-17»", 20.19, 30.77, 4.0e5,
     "Долина Таурус-Литтров, 11 декабря 1972 года, последняя высадка."),
    ("«Луноход-1»", 38.24, -35.00, 4.0e5,
     "Первый луноход, Море Дождей, 17 ноября 1970 года."),
    ("«Луноход-2»", 25.83, 30.92, 4.0e5,
     "Кратер Лемонье, 15 января 1973 года."),
)


def body_demo(name, title, sites, color, camera, body):
    places = [KPlace(site, "point", [(lat, lon)], color=color, icon="flag",
                     view=(lat, lon, distance, 0.0, 0.0), description=text)
              for site, lat, lon, distance, text in sites]
    root = KFolder(title, children=places)
    scene = Scene(camera, None, [], {"extras": {"stars": True}}, title,
                  title, body=body)
    save(name, scene, root)


# Небо: название, прямое восхождение и склонение в градусах, поле
# зрения, описание.
SKY = (
    ("Орион", 84.0, -1.0, 35.0,
     "Бетельгейзе, Ригель и пояс из трёх звёзд."),
    ("Плеяды", 56.9, 24.1, 6.0, "Рассеянное звёздное скопление в Тельце."),
    ("Туманность Андромеды", 10.7, 41.3, 10.0,
     "Ближайшая крупная галактика, 2.5 млн световых лет."),
    ("Кассиопея", 15.0, 60.0, 30.0, "Созвездие в форме буквы W."),
    ("Большая Медведица", 165.0, 55.0, 45.0, "Ковш из семи звёзд."),
    ("Вега и Лира", 282.0, 36.0, 20.0, "Вега - одна из ярчайших звёзд."),
    ("Южный Крест", 187.0, -60.0, 20.0,
     "Созвездие южного неба, из России не видно."),
)


def sky():
    title = "PlanetX: демо, небо"
    places = []
    for name, ra, dec, fov, text in SKY:
        lon = ra - 360.0 if ra > 180.0 else ra
        places.append(KPlace(name, "point", [(dec, lon)], color=YELLOW,
                             icon="dot", description=text,
                             view=(dec, lon, distance_for(fov), 0.0, 0.0)))
    root = KFolder(title, children=places)
    ra, dec, fov = SKY[0][1:4]
    view = {"extras": {"stars": True}, "sky": [ra, dec, fov]}
    scene = Scene((dec, ra, distance_for(fov)), None, [], view, title,
                  "Небо", body="sky")
    save("sky", scene, root)


def main():
    perm()
    bocachica()
    body_demo("mars", "PlanetX: демо, Марс", MARS, RED,
              (10.0, -80.0, 1.2e7), "mars")
    body_demo("moon", "PlanetX: демо, Луна", MOON, YELLOW,
              (10.0, 0.0, 5.5e6), "moon")
    sky()


if __name__ == "__main__":
    main()
