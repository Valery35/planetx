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
from ..core.searchbar import Suggestion
from ..i18n import tr
from .nasamaps import ANY_BODY, LAYERS, RELIEF_BODY, layer_names, map_names

# Строки группы «Карта» раздела «Слои»: ключ - название.
MAP_ROWS = ("grid", "buildings", "contours", "infra_osm", "cables")
# Слои, которые есть вне Земли.
ANY_PLANET = ANY_BODY + RELIEF_BODY + ("grid", "contours")
# Другие слова слоёв и карт: ключ - слова.
WORDS = {
    "stars": ("звёзды", "небо", "млечный путь", "stars", "milky way"),
    "clouds": ("облачность", "clouds"),
    "sun": ("ночь", "день", "освещение", "тень", "огни городов", "sun",
            "night", "city lights"),
    "satellites": ("мкс", "спутники", "орбиты", "starlink", "iss",
                   "satellites"),
    "quakes": ("землетрясения", "сейсмика", "очаги", "earthquakes"),
    "plates": ("тектоника", "плиты", "разломы", "plates", "tectonics"),
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
    add("tool:place", tr("Новая метка"), open_, bar.place_button.click,
        ("метка", "путь", "многоугольник", "круг", "нарисовать",
         "placemark", "path", "polygon"))
    add("tool:save_view", tr("Сохранить вид"), tr("выполнить"),
        bar.save_button.click, ("закладка", "вид", "bookmark"))
    add("tool:snapshot", tr("Снимок вида"), open_,
        lambda: window._open_snapshot(False),
        ("скриншот", "картинка", "png", "screenshot"))
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
    add("tool:subsurface", tr("Подземный режим"), open_,
        window.subsurface.open_dialog, ("скважины", "геология",
                                        "subsurface", "drillholes"))
    if not earth:
        return
    add("here:sentinel", tr("Снимки Sentinel-2 и Landsat здесь"), open_,
        lambda: window.sentinel_here(*_here(window)),
        ("космоснимки", "спутниковые снимки", "ndvi", "landsat",
         "sentinel", "modis", "imagery"))
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
