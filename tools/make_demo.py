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
- japan - Японский жёлоб: землетрясения, сектор разреза Земли через
  зону субдукции, эпицентр Тохоку 2011 года, путь для окна «Разрез».
- jezero - кратер Езеро на Марсе: место посадки «Персеверанса»,
  окрестности, профиль через кратер, точка для видимости, облёт,
  уклон склонов. Экспозиция на равнинах Марса при пикселе высот 2.6 км
  давала пёструю рябь, поэтому в демо включён уклон. Шаг 5 плана
  фазы 3.
- vegas - тоннели Vegas Loop компании The Boring Company в Лас-Вегасе
  со станциями, данные - OpenStreetMap, tools/make_tunnel_demo.py.
- aral - Аральское море: снимки MODIS 2000, 2014 и 2023 годов на
  поверхности, фото у Муйнака и карта бассейна на экране, все картинки
  по ссылкам.
- quarry - карьер у Березников: синтетическая съёмка 1 м рельефом
  глобуса, профиль через уступы, отвал.
- mars - места посадок марсоходов и крупные формы рельефа Марса.
- moon - места посадок «Аполлонов» и «Луноходов».
- sky - созвездия и яркие объекты неба.

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
    ("Галактика Андромеды (M31)", 10.7, 41.3, 10.0,
     "Ближайшая крупная галактика, около 2.5 млн световых лет."),
    ("Кассиопея", 15.0, 60.0, 30.0, "Созвездие в форме буквы W."),
    ("Большая Медведица", 165.0, 55.0, 45.0, "Ковш из семи звёзд."),
    ("Лира с Вегой", 282.0, 36.0, 20.0,
     "Вега - одна из ярчайших звёзд неба."),
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


def mars_orbit(lat, lon, distance, seconds=40.0, step=0.5):
    """Записанный облёт точки на Марсе: круг азимута, наклон 50°."""
    samples = []
    count = int(seconds / step)
    for k in range(count + 1):
        t = k * step
        share = t / seconds
        samples.append((t, lat, lon, distance, (360.0 * share) % 360.0,
                        50.0))
    return samples


def mars_circle(lat, lon, radius_km, count=72):
    """Круг радиуса radius_km на сфере Марса, замкнутый путь."""
    radius = 3389.5  # км, core/ellipsoid.py
    points = []
    for k in range(count + 1):
        a = 2.0 * math.pi * k / count
        d = radius_km / radius
        la = math.asin(math.sin(math.radians(lat)) * math.cos(d)
                       + math.cos(math.radians(lat)) * math.sin(d)
                       * math.cos(a))
        lo = math.radians(lon) + math.atan2(
            math.sin(a) * math.sin(d) * math.cos(math.radians(lat)),
            math.cos(d) - math.sin(math.radians(lat)) * math.sin(la))
        points.append((math.degrees(la), math.degrees(lo)))
    return points


# Кратер Езеро: центр 18.38° с. ш., 77.58° в. д., диаметр около 45 км.
# Место посадки «Персеверанса» - опубликованное NASA, остальные
# точки - центры областей по номенклатуре МАС, округлены до десятых.
JEZERO = (18.38, 77.58)
JEZERO_SITES = (
    ("«Персеверанс», место посадки «Октавия Батлер»", 18.4447, 77.4508,
     "flag", RED, (60000.0, 0.0, 45.0),
     "Марсоход NASA сел здесь 18 февраля 2021 года, у западного края "
     "кратера Езеро. В кратере около 3.5 млрд лет назад было озеро."),
    ("Кратер Езеро", 18.38, 77.58, "dot", YELLOW, (150000.0, 0.0, 40.0),
     "Кратер диаметром около 45 км на западном краю равнины Исиды."),
    ("Борозды Нили", 22.6, 76.8, "dot", ORANGE, (600000.0, 0.0, 30.0),
     "Система борозд к северо-западу от Езеро."),
    ("Равнина Исиды", 12.9, 87.0, "dot", ORANGE, (1500000.0, 0.0, 20.0),
     "Ударный бассейн диаметром около 1500 км к востоку от Езеро."),
    ("Плато Большой Сирт", 8.4, 69.5, "dot", ORANGE,
     (1500000.0, 0.0, 20.0), "Вулканическое плато к юго-западу."),
)


def jezero():
    title = "PlanetX: демо, кратер Езеро"
    lat, lon = JEZERO
    places = [KPlace(name, "point", [(la, lo)], color=color, icon=icon,
                     view=(la, lo) + view, description=text)
              for name, la, lo, icon, color, view, text in JEZERO_SITES]
    places.append(KPlace(
        "Край кратера, восточный", "point", [(lat, lon + 0.42)],
        color=WHITE, icon="flag", view=(lat, lon + 0.42, 120000.0, 270.0,
                                         45.0),
        description="Точка у восточного края кратера, около. В меню метки "
                    "- «Видимость отсюда…» с радиусом 30 км."))
    places.append(KPlace(
        "Круг 45 км вокруг центра Езеро", "line",
        mars_circle(lat, lon, 22.5), color=YELLOW, width=2.0,
        description="Круг диаметром 45 км, по нему виден размер кратера."))
    places.append(KPlace(
        "Профиль через кратер Езеро", "line",
        [(lat, lon - 0.6), (lat, lon + 0.6)], color=WHITE, width=3.0,
        description="Путь с запада на восток через центр кратера, около "
                    "67 км. В меню - «Профиль высот». Высоты MOLA, пиксель "
                    "около 2.6 км."))
    samples = mars_orbit(lat, lon, 160000.0)
    places.append(KPlace("Облёт кратера Езеро", "line",
                         [(s[1], s[2]) for s in samples], tour=samples,
                         description="Записанный тур вокруг кратера."))
    root = KFolder(title, children=places)
    view = {"relief": True, "scale": 3.0,
            "extras": {"stars": True, "slope": True}}
    scene = Scene((lat, lon, 200000.0, 0.0, 40.0), None, [], view, title,
                  "Кратер Езеро", body="mars")
    save("jezero", scene, root)


# Японский жёлоб: Тихоокеанская плита уходит под Японские острова.
# Эпицентр Тохоку - каталог USGS (событие 11 марта 2011 года, 05:46 UTC,
# 38.297° с. ш., 142.373° в. д., глубина 29 км, M9.1). Точка жёлоба -
# примерная, у оси жёлоба на широте эпицентра. Путь разреза по 38.5° с. ш.
# от 146° до 132° в. д. - тот же, что у шагов section_* проверки: на нём
# плита Slab2 идёт до 471 км. Сектор разреза Земли - от экватора до
# 38.5° с. ш., его северная грань режет зону субдукции по широте пути.
# Выбор помощника.
JAPAN_WEDGE = [120.0, 160.0, 0.0, 38.5]
JAPAN_SECTION = [(38.5, 146.0), (38.5, 132.0)]
JAPAN_SITES = (
    ("Японский жёлоб", 38.3, 143.9, "water", BLUE,
     (900000.0, 0.0, 35.0),
     "Здесь Тихоокеанская плита уходит под Японские острова. Точка у оси "
     "жёлоба примерная."),
    ("Эпицентр землетрясения Тохоку, 11 марта 2011 года", 38.297, 142.373,
     "info", RED, (600000.0, 0.0, 40.0),
     "Магнитуда 9.1, глубина очага 29 км по каталогу USGS."),
    ("Вулкан Фудзи", 35.3606, 138.7274, "peak", ORANGE,
     (60000.0, 0.0, 60.0), "Действующий вулкан высотой 3776 м."),
)


def japan():
    """Японский жёлоб: землетрясения, разрез Земли через зону субдукции,
    путь для окна «Разрез». Окно открывает GlobeWindow.open_demo."""
    title = "PlanetX: демо, Японский жёлоб"
    places = [KPlace("Разрез через Японский жёлоб по 38.5° с. ш.", "line",
                     JAPAN_SECTION, color=YELLOW, width=3.0,
                     description="Путь для окна «Разрез»: кора CRUST1.0, "
                                 "плита Slab2 и очаги в полосе 100 км. "
                                 "В меню пути - «Разрез вниз…».")]
    places += [KPlace(name, "point", [(la, lo)], color=color, icon=icon,
                      view=(la, lo) + view, description=text)
               for name, la, lo, icon, color, view, text in JAPAN_SITES]
    root = KFolder(title, children=places)
    view = dict(EARTH_VIEW, wedge=list(JAPAN_WEDGE),
                extras=dict(EARTH_VIEW["extras"], buildings=False,
                            quakes=True, cutaway=True))
    scene = Scene((34.0, 139.0, 2200000.0, 0.0, 72.0), None, [], view,
                  title, "Японский жёлоб")
    save("japan", scene, root)


def subsurface():
    """Пермские отложения: только вид, данные - planetx/demo/subsurface,
    их собирает tools/make_subsurface_demo.py, открывает окно глобуса
    (GlobeWindow.open_demo). Масштаб рельефа 2 - выбор помощника."""
    title = "PlanetX: демо, пермские отложения"
    # Остановки тура объясняют режим по шагам, описание видно под
    # панелью тура. Координаты - из perm_subsurface.gpkg: вырез, разрез
    # 3-3, скважина C-04 и первый ряд скважин. Виды - выбор помощника.
    stops = (
        ("1. Модель под поверхностью", "point", [(59.455, 56.88)],
         (59.445, 56.885, 9000.0, 30.0, 60.0),
         "Синтетический участок 4 на 3 км у Березников. Поверхность в "
         "рамке модели полупрозрачная, под ней скважины, кровли пластов "
         "и разрезы. Настройки - значок «Подземный режим»."),
        ("2. Вырез блока", "point", [(59.4557, 56.8959)],
         (59.452, 56.893, 3500.0, 30.0, 62.0),
         "В северо-восточной четверти поверхность и кровли убраны. По "
         "краю выреза видны пласты своих цветов, шкала «Пласты» внизу "
         "слева называет их."),
        ("3. Разрез с картинкой", "point", [(59.4566, 56.896)],
         (59.4535, 56.896, 1800.0, 0.0, 70.0),
         "Картинка разреза 3-3 натянута на стенку вдоль линии под "
         "поверхностью. Так на модель ставится готовый геологический "
         "разрез из файла PNG или JPG."),
        ("4. Наклонная скважина C-04", "point", [(59.45995, 56.88476)],
         (59.4585, 56.8848, 1200.0, 0.0, 68.0),
         "Ствол идёт по инклинометрии, интервалы окрашены цветами "
         "пластов. В режиме «Объекты» щелчок по стволу показывает пласт "
         "и глубину в этой точке."),
        ("5. Путь для разреза модели", "line",
         [(59.4594, 56.845), (59.4594, 56.915)], None,
         "В меню этого пути в «Моих метках» пункт «Разрез модели…» "
         "открывает разрез вдоль него с пластами и скважинами в метрах."))
    places = []
    for name, kind, points, view, text in stops:
        places.append(KPlace(name, kind, points,
                             color=ORANGE if kind == "point" else YELLOW,
                             width=3.0, icon="flag", view=view,
                             description=text))
    root = KFolder(title, children=places)
    view = dict(EARTH_VIEW, scale=2.0,
                extras=dict(EARTH_VIEW["extras"], buildings=False))
    scene = Scene((59.445, 56.885, 9000.0, 30.0, 60.0), None, [], view,
                  title, "Пермские отложения")
    save("subsurface", scene, root)


def vegas():
    """Тоннели Vegas Loop: станции из planetx/demo/vegas/stations.json,
    тоннели - таблица tunnels того же каталога, их собирает
    tools/make_tunnel_demo.py из OpenStreetMap, строит подземный режим
    (GlobeWindow.open_demo). Вид и прозрачность - выбор помощника."""
    import json
    title = "PlanetX: демо, тоннели Vegas Loop"
    with open(os.path.join(DEMO, "vegas", "stations.json"),
              encoding="utf-8") as fh:
        stations = json.load(fh)
    places = []
    for s in stations:
        # «Rivera» - написание в OpenStreetMap, станция у отеля Riviera.
        name = s["name"].replace("Rivera", "Riviera")
        places.append(KPlace(
            name, "point", [(s["lat"], s["lon"])], color=BLUE, icon="rail",
            view=(s["lat"], s["lon"], 600.0, 0.0, 60.0),
            description="Станция Vegas Loop, The Boring Company. Данные - "
                        "OpenStreetMap."))
    root = KFolder(title, children=places)
    view = dict(EARTH_VIEW, extras=dict(EARTH_VIEW["extras"],
                                        buildings=False))
    scene = Scene((36.1315, -115.1555, 1100.0, 20.0, 62.0), None, [], view,
                  title, "Тоннели Vegas Loop")
    save("vegas", scene, root)


# Аральское море: наложения картинок по ссылкам, картинки в файл сцены
# не входят. Снимки MODIS Terra в истинных цветах - запрос GetMap WMS
# NASA GIBS, рамка запроса - рамка картинки. Дни без облаков выбраны
# по снимкам 5 октября 2026 года. Фото и карта - Wikimedia Commons,
# авторы и лицензии в описаниях. Камера фото у Муйнака примерная.
# Выбор помощника.
ARAL_BOX = (47.0, 43.0, 62.5, 57.5, 0.0)  # север, юг, восток, запад
ARAL_WMS = ("https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?"
            "SERVICE=WMS&REQUEST=GetMap&VERSION=1.1.1"
            "&LAYERS=MODIS_Terra_CorrectedReflectance_TrueColor&STYLES="
            "&SRS=EPSG:4326&BBOX=57.5,43.0,62.5,47.0&WIDTH=1250&HEIGHT=1000"
            "&FORMAT=image/jpeg&TIME={}")
ARAL_DAYS = ("2000-08-24", "2014-08-25", "2023-09-04")
ARAL_SHIPS = ("https://upload.wikimedia.org/wikipedia/commons/c/c1/"
              "Moynaq%2C_Aral_Lake%2C_Ship_Wrecks%2C_Uzbekistan.jpg")
ARAL_MAP = "https://upload.wikimedia.org/wikipedia/commons/8/85/Aral_map.png"
MOYNAQ = (43.785, 59.025)


def aral():
    """Аральское море: три снимка на поверхности группой переключателей,
    фото у Муйнака и карта бассейна на экране."""
    from kml import KOverlay
    from overlays import Overlay
    title = "PlanetX: демо, Аральское море"
    frames = []
    for k, day in enumerate(ARAL_DAYS):
        frames.append(KOverlay(
            "Снимок {}".format(day), Overlay("ground", box=ARAL_BOX),
            href=ARAL_WMS.format(day), visible=k == 0,
            description="MODIS Terra в истинных цветах, {}. Источник - NASA "
                        "GIBS, картинка по ссылке. Меню - «Картинку в "
                        "проект QGIS…».".format(day),
            view=(45.0, 60.0, 600000.0, 0.0, 0.0)))
    folder = KFolder(
        "Снимки MODIS 2000, 2014, 2023", children=frames, radio=True,
        description="Группа переключателей - виден один снимок. Картинки "
                    "на поверхности задаются рамкой по ссылке на запрос "
                    "WMS NASA GIBS.")
    lat, lon = MOYNAQ
    ships = KOverlay(
        "Корабли у Муйнака", Overlay(
            "photo", camera=(lat, lon, 120.0, 0.0, 82.0, 0.0),
            fov=(-30.0, 30.0, -20.0, 20.0), near=150.0),
        href=ARAL_SHIPS,
        description="Фото на бывшем дне моря у Муйнака, 2014 год. Автор - "
                    "THORSTEN, Wikimedia Commons, CC BY-SA 4.0. Место камеры "
                    "примерное. «Подлететь» ставит глаз в точку камеры.")
    basin = KOverlay(
        "Бассейн Аральского моря", Overlay(
            "screen", overlay_xy=(1.0, 0.0, "fraction", "fraction"),
            screen_xy=(1.0, 40.0, "fraction", "pixels")),
        href=ARAL_MAP,
        description="Карта бассейна на экране. Автор - Kmusser, Wikimedia "
                    "Commons, CC BY-SA 2.5.")
    root = KFolder(title, children=[folder, ships, basin])
    view = dict(EARTH_VIEW, extras=dict(EARTH_VIEW["extras"],
                                        buildings=False))
    scene = Scene((45.0, 60.0, 700000.0, 0.0, 0.0), None, [], view, title,
                  "Аральское море")
    save("aral", scene, root)


# Карьер: синтетическая съёмка 1 м, planetx/demo/quarry/quarry_dem.tif,
# её собирает tools/make_quarry_demo.py. Окно кладёт растр в проект
# и включает его рельефом глобуса (GlobeWindow.open_demo). Координаты
# меток - от центра карьера по размерам из того же скрипта, вид -
# выбор помощника.
QUARRY = (59.490, 56.970)
QUARRY_LON_M = 1.0 / (111320.0 * math.cos(math.radians(QUARRY[0])))
QUARRY_LAT_M = 1.0 / 111320.0


def quarry():
    title = "PlanetX: демо, карьер"
    lat, lon = QUARRY
    west = lon - 1000.0 * QUARRY_LON_M
    east = lon + 1000.0 * QUARRY_LON_M
    places = [
        KPlace("Профиль через карьер", "line", [(lat, west), (lat, east)],
               color=YELLOW, width=3.0,
               description="Путь с запада на восток через дно карьера, "
                           "2 км. В меню - «Профиль высот»: уступы по 15 м "
                           "и дно на 150 м ниже бровки."),
        KPlace("Дно карьера", "point", [(lat, lon)], color=ORANGE,
               icon="flag", view=(lat, lon, 1800.0, 0.0, 55.0),
               description="Синтетическая съёмка 1 м. Растр в проекте QGIS, "
                           "в меню слоя раздела «Слои проекта» отмечен "
                           "пункт «Рельеф глобуса»."),
        KPlace("Отвал", "point",
               [(lat + 640.0 * QUARRY_LAT_M, lon + 760.0 * QUARRY_LON_M)],
               color=WHITE, icon="peak",
               view=(lat + 640.0 * QUARRY_LAT_M, lon + 760.0 * QUARRY_LON_M,
                     1200.0, 220.0, 60.0),
               description="Отвал высотой 40 м в два яруса."),
    ]
    root = KFolder(title, children=places)
    view = dict(EARTH_VIEW, scale=1.0,
                extras=dict(EARTH_VIEW["extras"], buildings=False))
    scene = Scene((lat - 0.004, lon, 2600.0, 10.0, 62.0), None, [], view,
                  title, "Карьер")
    save("quarry", scene, root)


def main():
    perm()
    bocachica()
    jezero()
    japan()
    subsurface()
    vegas()
    aral()
    quarry()
    body_demo("mars", "PlanetX: демо, Марс", MARS, RED,
              (10.0, -80.0, 1.2e7), "mars")
    body_demo("moon", "PlanetX: демо, Луна", MOON, YELLOW,
              (10.0, 0.0, 5.5e6), "moon")
    sky()


if __name__ == "__main__":
    main()
