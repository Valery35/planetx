# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Действия модуля для строки «Поиск» и Ctrl+K.

Просьба автора от 11 октября 2026 года - «хороший интерфейс над пачкой
возможностей». Слои, карты витрины, окна, инструменты панели значков,
демо и тела глобуса находятся по названию или по другому слову и
выполняются из подсказки или по Enter. Подсказка - Suggestion вида
"action" (core/searchbar.py), действие - функция без аргументов
в словаре по ключу подсказки.

build(window) собирает список заново на каждый ввод: «включить» или
«выключить» у слоя зависит от того, что на глобусе сейчас. Слова words
не показываются, их не переводят - в них русские и английские названия
и близкие слова. Состав слов - выбор помощника, утверждает автор.
"""
from ..core import basemap
from ..core.searchbar import Suggestion
from ..i18n import is_russian, tr
from .nasamaps import ANY_BODY, LAYERS, RELIEF_BODY, layer_names, map_names

# Строки группы «Карта» раздела «Слои»: ключ - название.
MAP_ROWS = ("grid", "buildings", "contours", "cadastre", "infra_osm",
            "cables")
# Слои, которые есть вне Земли.
ANY_PLANET = ANY_BODY + RELIEF_BODY + ("grid", "contours")
# Другие слова слоёв и карт: ключ - слова.
WORDS = {
    "stars": ("звёзды", "небо", "млечный путь", "stars", "milky way"),
    "air": ("атмосфера", "воздух", "дымка", "гало", "atmosphere", "haze",
            "air"),
    "clouds": ("облачность", "clouds"),
    "sun": ("ночь", "день", "освещение", "тень", "огни городов", "sun",
            "night", "city lights"),
    "satellites": ("мкс", "спутники", "орбиты", "starlink", "iss",
                   "satellites"),
    "trains": ("поезда", "железная дорога", "финляндия", "vr", "trains",
               "railway", "finland", "digitraffic"),
    "vessels": ("суда", "корабли", "ais", "балтика", "морской трафик",
                "ships", "vessels", "marine traffic"),
    "aircraft": ("самолёты", "самолеты", "авиация", "рейсы", "ads-b",
                 "flightradar", "aircraft", "planes", "flights"),
    "quakes": ("землетрясения", "сейсмика", "очаги", "earthquakes"),
    "plates": ("тектоника", "плиты", "plates", "tectonics"),
    "faults": ("разломы", "активные разломы", "сбросы", "надвиги", "сдвиги",
               "gem", "faults", "active faults"),
    "geology": ("геология", "геологическая карта", "стратиграфия",
                "возраст пород", "macrostrat", "geology", "geologic map"),
    "glim": ("литология", "литологическая карта", "породы", "типы пород",
             "glim", "lithology", "rock types"),
    "iscgem": ("исторические землетрясения", "землетрясения с 1900",
               "старые землетрясения", "каталог землетрясений", "isc-gem",
               "iscgem", "historical earthquakes"),
    "worldcover": ("покрытие земель", "растительность", "лес", "пашня",
                   "застройка", "землепользование", "worldcover",
                   "land cover"),
    "water_occurrence": ("повторяемость воды", "поверхностные воды",
                         "вода landsat", "jrc", "surface water",
                         "water occurrence"),
    "water_transitions": ("изменения воды", "исчезнувшие озёра",
                          "новые водохранилища", "обмеление",
                          "water change", "water transitions"),
    "soil_clay": ("глина", "почвы", "почва", "гранулометрия",
                  "soilgrids", "clay", "soil"),
    "soil_sand": ("песок", "песчаные почвы", "sand"),
    "soil_soc": ("органический углерод", "гумус", "углерод почвы",
                 "soil carbon", "soc"),
    "soil_ph": ("кислотность", "ph", "кислые почвы", "soil ph",
                "acidity"),
    "geoid": ("геоид", "картошка", "потсдамская картошка", "egm2008",
              "фигура земли", "geoid"),
    "emag": ("магнитные аномалии", "магнитка", "аэромагнитка",
             "магниторазведка", "emag", "magnetic anomaly"),
    "magpoles": ("магнитный полюс", "магнитные полюса",
                 "компас", "геомагнетизм", "igrf", "magnetic pole",
                 "compass"),
    "volcanoes": ("вулканы", "вулкан", "извержения", "gvp", "volcanoes",
                  "volcano"),
    "platemotion": ("скорости плит", "движение плит", "дрейф",
                    "дрейф континентов", "morvel", "plate motion"),
    "seafloor_age": ("возраст дна", "возраст океанического дна",
                     "возраст коры", "спрединг", "seafloor age",
                     "ocean age"),
    "gravity": ("сила тяжести", "гравитация", "гравиметрия",
                "аномалии силы тяжести", "xgm2019e", "gravity",
                "free-air"),
    "bouguer": ("буге", "аномалия буге", "аномалии буге", "bouguer"),
    "heatflow": ("тепловой поток", "геотермия", "теплопоток",
                 "heat flow", "geothermal"),
    "magdecl": ("склонение", "изогоны", "линии склонения", "агона",
                "магнитное склонение", "declination", "isogonic"),
    "deposits": ("полезные ископаемые", "руды", "рудники", "usgs", "mrds",
                 "minerals", "deposits"),
    "mining": ("карьеры", "отвалы", "горные работы", "mining", "pits"),
    "osm_mines": ("шахты", "карьеры", "mines", "quarries"),
    "plants": ("электростанции", "энергетика", "тэц", "гэс", "аэс",
               "power plants"),
    "currents": ("течения", "океан", "гольфстрим", "currents", "ocean"),
    "cutaway": ("разрез земли", "недра", "ядро", "мантия", "кора",
                "cutaway", "core", "mantle"),
    "paleo": ("палеогеография", "пангея", "древняя земля", "paleo",
              "pangaea"),
    "slope": ("крутизна", "уклон", "slope"),
    "aspect": ("экспозиция", "стороны света", "aspect"),
    "grid": ("сетка", "градусы", "экватор", "graticule", "grid"),
    "buildings": ("здания", "дома", "3d", "buildings"),
    "contours": ("изолинии", "горизонтали", "изобаты", "contours"),
    "infra_osm": ("лэп", "электросети", "подстанции", "трубопроводы",
                  "газопровод", "нефтепровод", "power lines", "pipelines"),
    "cables": ("подводные кабели", "кабели", "submarine cables"),
    "sea_marks": ("морские знаки", "буи", "маяки", "фарватер",
                  "openseamap", "sea marks", "buoys"),
    "hiking": ("пешие маршруты", "тропы", "туризм", "походы", "hiking",
               "trails"),
    "cycling": ("велосипед", "веломаршруты", "cycling", "bike routes"),
    "cadastre": ("кадастр", "росреестр", "нспд", "участки",
                 "земельные участки", "пкк", "cadastre", "parcels"),
    "fires": ("пожары", "огонь", "fires", "firms"),
    "temperature": ("температура", "жара", "temperature"),
    "weather_aurora": ("сияние", "северное сияние", "аврора",
                       "aurora", "northern lights", "ovation"),
}
# Карты витрины - ещё слово «карта».
MAP_WORDS = ("карта", "map", "nasa")



def _words(key, *more):
    return tuple(WORDS.get(key, ())) + tuple(more)


def build(window):
    """Действия окна глобуса: список Suggestion и словарь ключ -
    функция. Состав зависит от тела и того, что сейчас включено."""
    items, run = [], {}

    def add(key, title, note, func, words=()):
        items.append(Suggestion("action", title, key, None, None, None,
                                note, tuple(words)))
        run[key] = func

    planet = getattr(window, "planet", None)
    earth = planet is None or planet.earth
    extras = getattr(window, "extras", {})
    names = layer_names()
    titles = dict((key, value[0]) for key, value in names.items())
    titles.update({"grid": tr("Координатная сетка"),
                   "buildings": tr("3D-здания")})
    keys = [key for key, _ in LAYERS] + list(MAP_ROWS)
    for key in keys:
        if key not in titles or (not earth and key not in ANY_PLANET):
            continue
        on = bool(extras.get(key))
        add("layer:" + key, titles[key],
            tr("выключить") if on else tr("включить"),
            lambda key=key, on=on: window.set_extra(key, not on),
            _words(key))
    if earth:
        current = window.gallery_key()
        for key, (title, _) in map_names().items():
            on = key == current
            add("map:" + key, title,
                tr("убрать карту") if on else tr("показать карту"),
                lambda key=key, on=on: window.set_theme("" if on else key),
                _words(key, *MAP_WORDS))
        add("open:gallery", tr("Добавить данные"), tr("открыть каталог"),
            window.open_gallery, ("витрина", "каталог", "gallery",
                                  "карты и слои", "nasa", "погода",
                                  "weather", "add data"))
        # Готовые подложки меню «Основа»: у сервисов без разрешения
        # окно сначала предупреждает (GlobeWindow.add_ready_source).
        for key, ru, en, *_ in basemap.READY:
            add("basemap:" + key, ru if is_russian() else en,
                tr("подложкой"),
                lambda key=key: window.add_ready_source(key),
                (ru.lower(), en.lower(), tr("подложка"), "basemap"))
    _tools(window, add, earth)
    _menus(window, add)
    return items, run


def _open_journal():
    """Журнал работы программой системы, как кнопка окна «О модуле»."""
    from .. import journal
    journal.open_journal()


def _here(window):
    """Точка взгляда - место для действий «здесь»."""
    pose = window.view.navigator.pose
    return pose.lat, pose.lon


def _tools(window, add, earth):
    """Окна и инструменты панели значков и меню на глобусе."""
    bar = window.toolbar
    open_ = tr("открыть окно")
    add("tool:ruler", tr("Линейка"), open_, bar.ruler_button.click,
        ("измерить", "расстояние", "площадь", "длина", "ruler",
         "measure"))
    add("tool:place", tr("Новая метка"), open_, window._open_place,
        ("метка", "путь", "многоугольник", "круг", "нарисовать",
         "placemark", "path", "polygon"))
    add("tool:save_view", tr("Сохранить вид"), tr("выполнить"),
        bar.save_button.click, ("закладка", "вид", "bookmark"))
    add("tool:snapshot", tr("Снимок вида"), open_,
        lambda: window._open_snapshot(False),
        ("скриншот", "картинка", "png", "screenshot"))
    add("tool:copy_view", tr("Копия вида в буфер обмена"), tr("выполнить"),
        window.copy_view, ("копия экрана", "копия вида", "скриншот",
                           "буфер обмена", "copy", "clipboard",
                           "screenshot"))
    add("tool:layout", tr("Вид в макет QGIS"), open_,
        lambda: window._open_snapshot(True), ("макет", "печать", "layout"))
    add("tool:record", tr("Записать облёт"),
        tr("остановить") if bar.record.isChecked() else tr("начать"),
        bar.record.click, ("тур", "запись", "облёт", "tour", "record"))
    if bar.time.isEnabled():
        add("tool:time", tr("Шкала времени"),
            tr("закрыть") if bar.time.isChecked() else tr("открыть"),
            bar.time.click, ("время", "дата", "time", "timeline"))
    add("tool:identify", tr("Определить объекты"),
        tr("выключить") if bar.identify.isChecked() else tr("включить"),
        bar.identify.click, ("опрос", "сведения", "identify"))
    add("tool:sync", tr("Синхронизация с картой QGIS"),
        tr("выключить") if bar.sync.isChecked() else tr("включить"),
        bar.sync.click, ("карта qgis", "связь", "sync"))
    add("tool:properties", tr("Свойства вида"), open_,
        window._show_properties, ("настройки", "рельеф", "подписи",
                                  "язык", "settings", "properties"))
    add("tool:sources", tr("Источники данных"), open_,
        window.open_sources, ("подложка", "основа", "рельеф", "dem",
                              "copernicus", "sources", "basemap"))
    add("tool:assistant", tr("Разговор с помощником"), open_,
        window.open_assistant, ("ии", "ai", "помощник", "chat",
                                "assistant"))
    add("tool:journal", tr("Журнал работы"), open_, _open_journal,
        ("журнал", "лог", "ошибки", "отладка", "log", "journal", "debug"))
    add("tool:about", tr("О модуле"), open_,
        lambda: bar.about_clicked.emit(), ("версия", "about", "version"))
    add("tool:guide", tr("Знакомство с модулем"), open_,
        window.start_guide, ("помощь", "справка", "обучение",
                             "как пользоваться", "help", "guide", "tour"))
    add("tool:scene_save", tr("Сохранить сцену"), open_,
        window.save_scene, ("сцена", "scene"))
    add("tool:scene_open", tr("Открыть сцену"), open_,
        window.open_scene, ("сцена", "scene"))
    add("tool:fullscreen", tr("Во весь экран"), tr("выполнить"),
        window.toggle_fullscreen,
        ("полный экран", "весь экран", "показ", "презентация", "f11",
         "fullscreen", "full screen", "presentation"))
    add("tool:crust", tr("Кора CRUST1.0 в проект QGIS"), tr("выполнить"),
        window.crust_to_project,
        ("кора", "crust1.0", "crust", "осадочный чехол", "фундамент",
         "мохо", "поверхности коры", "moho", "sediments"))
    add("tool:share", tr("Поделиться видом"), open_, window.share_view,
        ("html", "страница", "браузер", "отправить", "share", "web",
         "page", "browser"))
    add("tool:subsurface", tr("Подземный режим"), open_,
        window.subsurface.open_dialog, ("скважины", "геология",
                                        "subsurface", "drillholes"))
    if not earth:
        return
    add("here:sentinel", tr("Космоснимки здесь"), open_,
        lambda: window.sentinel_here(*_here(window)),
        ("космоснимки", "спутниковые снимки", "ndvi", "landsat",
         "sentinel", "modis", "imagery"))
    add("here:mss", tr("Ранние снимки Landsat 1972-1993 здесь"), open_,
        lambda: window.sentinel_here(*_here(window), mission="mss"),
        ("mss", "landsat mss", "ранние снимки", "старые снимки",
         "архивные снимки", "1970-е", "1980-е", "landsat 1", "landsat 2",
         "landsat 3", "old imagery", "early landsat"))
    add("here:aster", tr("Снимки ASTER здесь"), open_,
        lambda: window.sentinel_here(*_here(window), mission="aster"),
        ("aster", "астер", "минералы", "изменённые породы", "каолинит",
         "геологические индексы", "swir", "terra aster"))
    add("here:etomesto", tr("Старые карты «Это Место» здесь"), open_,
        lambda: window.etomesto_here(*_here(window)),
        ("это место", "etomesto", "старые карты", "межевые", "пгм",
         "менде", "шуберт", "стрельбицкий", "ркка", "трёхвёрстка"))
    add("here:rumsey", tr("Исторические карты Рамсея здесь"), open_,
        lambda: window.rumsey_here(*_here(window)),
        ("старые карты", "исторические карты", "рамсей", "rumsey",
         "old maps"))
    add("here:sheets", tr("Номенклатура листа здесь"), open_,
        lambda: window.sheets_here(*_here(window)),
        ("номенклатура", "лист карты", "разграфка", "sheet"))
    add("here:what", tr("Что здесь?"), tr("выполнить"),
        lambda: window.what_here(window.view.width() / 2.0,
                                 window.view.height() / 2.0),
        ("адрес", "где я", "address"))
    if window.extras.get("contours"):
        add("here:contours", tr("Горизонтали вида в проект QGIS"),
            open_, window.contour_export.view_contours,
            ("выгрузка горизонталей", "export contours"))


def _menus(window, add):
    """Демо и тела глобуса из меню панели значков."""
    bar = window.toolbar
    for action in bar.demo.menu().actions():
        if action.isSeparator() or not action.text():
            continue
        add("demo:" + action.text(), action.text(), tr("открыть демо"),
            action.trigger, ("демо", "пример", "demo"))
    for key, action in bar.body_actions.items():
        if action.isChecked():
            continue
        add("body:" + key, action.text(), tr("перейти на тело"),
            action.trigger, ("тело", "планета", "body", "planet"))
