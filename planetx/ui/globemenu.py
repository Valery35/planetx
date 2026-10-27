# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Меню по правой кнопке на глобусе.

Щелчок правой кнопкой без сдвига открывает меню под курсором. Состав
зависит от того, что под ним: вершина рисуемого объекта, сохранённая
метка или просто поверхность. Перетаскивание правой кнопкой по-прежнему
приближает, двойной щелчок отдаляет.
"""
import numpy as np
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QCursor
from qgis.PyQt.QtWidgets import QApplication, QMenu

from ..core import editing, flightsim, sheets
from ..core.ellipsoid import geodetic_to_ecef
from ..core.features import has_alts
from ..i18n import tr
from .identify import point_text
from .menulinks import saved as saved_links
from .sheets import scale_text, system_names
from ..qt_compat import enum

HIT_PIXELS = 8.0  # логических пикселей до линии или контура
POINT_PIXELS = 14.0  # до значка точечной метки
KIND_MODE = {"point": "point", "line": "path", "polygon": "polygon"}
MAX_POINTS = 20000  # вершин у метки, с которыми она ещё ищется щелчком


def editable(place):
    """Можно ли править форму метки на глобусе: не тур и не 3D-объект."""
    return not place.tour and not has_alts(place.shape) \
        and place.kind in KIND_MODE


def place_under(window, px, py):
    """Видимая метка текущего тела под пикселем кадра или None. Точки
    и линии старше многоугольников, верхняя в списке старше нижней."""
    view = window.view
    ratio = view.devicePixelRatioF()
    best = None
    for place in window.myplaces.places:
        shape = place.shape
        if not place.visible or place.tour or not window._time_ok(place) \
                or place.body != window.planet.key \
                or not shape.points or len(shape.points) > MAX_POINTS:
            continue
        lats = np.array([p[0] for p in shape.points])
        lons = np.array([p[1] for p in shape.points])
        heights = np.asarray(shape.alts, dtype=np.float64) \
            if has_alts(shape) else view.store.heights_at(lats, lons)
        pixels, front = view.camera.project(
            geodetic_to_ecef(lats, lons, heights))
        radius = (POINT_PIXELS if place.kind == "point" else HIT_PIXELS) \
            * ratio
        if not editing.hit(place.kind, np.asarray(pixels).reshape(-1, 2),
                           front, px, py, radius):
            continue
        if place.kind != "polygon":
            return place
        if best is None:
            best = place
    return best


def show(window, px, py):
    """Собрать и показать меню для пикселя кадра (px, py)."""
    view = window.view
    if view.sky_view is not None:
        return
    menu = QMenu(window)
    menu.setAttribute(enum(Qt, "WidgetAttribute", "WA_DeleteOnClose"))
    drawer = window.drawer
    drawing = window._place_open() and bool(drawer.points)
    place = None
    ground = window._ground(px, py)
    if ground is not None:
        # Координаты - первой строкой, щелчок копирует их в формате
        # строки состояния. Просьба автора от 6 октября 2026 года.
        text = point_text(ground[0], ground[1], fmt=window.coords)
        copy = menu.addAction(text)
        copy.setToolTip(tr("Скопировать координаты в буфер обмена."))
        # Текст - значением по умолчанию: имя text ниже занимает цикл
        # подменю «Полёт отсюда», и в буфер уходило «Винтовой самолёт».
        copy.triggered.connect(
            lambda *a, t=text: QApplication.clipboard().setText(t))
        menu.setToolTipsVisible(True)
        menu.addSeparator()
    if drawing:
        found = window.draw_vertices.under(px, py)
        if found is not None and found[0] == editing.VERTEX:
            menu.addAction(tr("Удалить вершину")).triggered.connect(
                lambda *a, i=found[1]: drawer.remove(i))
        if drawer.mode != "point":
            if drawer.finished:
                menu.addAction(tr("Продолжить рисование")) \
                    .triggered.connect(lambda *a: drawer.resume())
            else:
                menu.addAction(tr("Завершить рисование")) \
                    .triggered.connect(lambda *a: drawer.finish())
        save = menu.addAction(tr("Сохранить"))
        save.setEnabled(drawer.shape(rubber=False) is not None)
        save.triggered.connect(lambda *a: window._save_place())
        menu.addAction(tr("Очистить")).triggered.connect(
            lambda *a: drawer.clear())
    else:
        place = place_under(window, px, py)
        if place is not None:
            title = menu.addAction(place.name or tr("Без названия"))
            title.setEnabled(False)
            menu.addAction(tr("Свойства…")).triggered.connect(
                lambda *a, p=place: window._open_place_properties(p))
        satellite_items(window, menu, px, py)
        live_items(window, menu, px, py)
        track_items(window, menu, px, py)
        model_track_items(window, menu, px, py)
    if ground is not None:
        lat, lon = ground
        if not menu.actions()[-1].isSeparator():
            menu.addSeparator()
        if not drawing:
            menu.addAction(tr("Добавить метку здесь")).triggered.connect(
                lambda *a: window.add_place_here(lat, lon))
            menu.addAction(tr("Измерить расстояние")).triggered.connect(
                lambda *a: window.measure_from(lat, lon))
            menu.addSeparator()
        menu.addAction(tr("Подлететь сюда")).triggered.connect(
            lambda *a: fly_here(view, lat, lon))
        menu.addAction(tr("Облететь вокруг")).triggered.connect(
            lambda *a: window.spin_here(lat, lon))
        if not drawing and window.planet.earth:
            route_items(window, menu, place, lat, lon)
        if not drawing:
            fly = menu.addMenu(tr("Полёт отсюда"))
            fly.setToolTipsVisible(True)
            for kind, text, tip in (
                    (flightsim.FIGHTER, tr("Истребитель"), tr(
                        "До 2000 км/ч, старт 900 км/ч, резкий крен.")),
                    (flightsim.LIGHT, tr("Винтовой самолёт"), tr(
                        "До 340 км/ч, старт 250 км/ч, плавный."))):
                action = fly.addAction(text)
                action.setToolTip(tip)
                action.triggered.connect(
                    lambda *a, k=kind: window.flight.start(lat, lon, k))
        menu.addSeparator()
        if not drawing and window.planet.earth:
            menu.addAction(tr("Что здесь?")).triggered.connect(
                lambda *a: window.what_here(px, py))
        # Окна расчёта и снимков у точки - одной группой, исторические
        # карты - другой. Просьба автора от 20 октября 2026 года.
        menu.addSeparator()
        if not drawing and window._surface_source() is not None:
            relief_items(window, menu, lat, lon)
            hydro_items(window, menu, lat, lon)
        if not drawing and window.planet.earth:
            # Один пункт на все спутники, окно открывается на прежнем
            # спутнике.
            menu.addAction(tr("Космоснимки здесь…")) \
                .triggered.connect(lambda *a: window.sentinel_here(lat, lon))
            menu.addAction(tr("Облака точек лидара здесь")).triggered.connect(
                lambda *a: window.lidar_here(lat, lon))
            menu.addSeparator()
            menu.addAction(tr("Исторические карты Рамсея здесь…")) \
                .triggered.connect(lambda *a: window.rumsey_here(lat, lon))
            menu.addAction(tr("Старые карты «Это Место» здесь…")) \
                .triggered.connect(lambda *a: window.etomesto_here(lat, lon))
            if window.extras.get("contours"):
                menu.addAction(tr("Горизонтали вида в проект QGIS…")) \
                    .triggered.connect(
                        lambda *a: window.contour_export.view_contours())
        if window.planet.earth:
            menu.addSeparator()
            link_items(window, menu, lat, lon)
            if not drawing:
                sheet_items(window, menu, lat, lon)
    if menu.isEmpty():
        menu.deleteLater()
        return
    menu.popup(QCursor.pos())


def relief_items(window, menu, lat, lon):
    """Подменю «Анализ участка»: уклон и экспозиция квадрата у точки
    (ui/relief.py), видимость, инсоляция и изменения местности (ui/aef.py).
    Просьба автора от 26 октября 2026 года - по образцу «Гидрологии».
    С 28 октября 2026 года, изменения местности рядом с видимостью по
    слову автора, подменю названо, как у Google Earth."""
    sub = menu.addMenu(tr("Анализ участка"))
    sub.setToolTipsVisible(True)
    items = [
        (tr("Уклон и экспозиция здесь…"),
         tr("Уклон и экспозиция квадрата вокруг точки по высотам, "
            "сводка, растры и вершины с ямами."),
         lambda *a: window.relief.relief_here(lat, lon)),
        (tr("Видимость отсюда…"),
         tr("Что видно из точки в круге заданного радиуса."),
         lambda *a: window.viewshed_here(lat, lon))]
    if window.planet.earth:
        items.append((tr("Инсоляция здесь…"),
                      tr("Часы прямого солнца в сутки вокруг точки."),
                      lambda *a: window.insolation_here(lat, lon)))
        items.append((tr("Изменения местности здесь…"),
                      tr("Где местность изменилась между двумя годами "
                         "2017-2025 - по эмбеддингам AlphaEarth, клетка "
                         "10 м."),
                      lambda *a: window.change_tool.open_here(lat, lon)))
    for text, tip, slot in items:
        action = sub.addAction(text)
        action.setToolTip(tip)
        action.triggered.connect(slot)


def hydro_items(window, menu, lat, lon):
    """Подменю «Гидрология»: затопление, сток и водосбор, речная сеть
    у точки, уровень моря по всему глобусу (ui/hydro.py). Просьба
    автора от 25 октября 2026 года - вынести в подменю."""
    sub = menu.addMenu(tr("Гидрология"))
    sub.setToolTipsVisible(True)
    for text, tip, slot in (
            (tr("Затопление отсюда…"),
             tr("Вода от точки до заданной отметки, площадь, объём "
                "и глубины."),
             lambda *a: window.hydro.flood_here(lat, lon)),
            (tr("Сток воды отсюда…"),
             tr("Линия стока, водосбор и речная сеть вокруг точки."),
             lambda *a: window.hydro.flow_here(lat, lon)),
            (tr("Уровень моря…"),
             tr("Подъём и опускание уровня моря по всему глобусу."),
             lambda *a: window.hydro.sea_level_here())):
        action = sub.addAction(text)
        action.setToolTip(tip)
        action.triggered.connect(slot)


def sheet_items(window, menu, lat, lon):
    """Подменю «Номенклатура листа»: номер листа в каждой системе
    разграфки, щелчок копирует номер. Последний пункт открывает окно
    с теми же номерами."""
    sub = menu.addMenu(tr("Номенклатура листа"))
    mark = " ({})".format(tr("Ю. П."))
    names = system_names()
    for system, scale, number in sheets.sheets(lat, lon, south_mark=mark):
        if not number:
            continue
        label = names[system]
        if scale is not None:
            label = "{}, {}".format(label, scale_text(scale))
        action = sub.addAction("{}\t{}".format(number, label))
        action.triggered.connect(
            lambda *a, n=number: window.copy_sheet(n))
    sub.addSeparator()
    sub.addAction(tr("Все номера в окне…")).triggered.connect(
        lambda *a: window.sheets_here(lat, lon))
    return sub


def link_items(window, menu, lat, lon):
    """Подменю «Открыть в браузере»: свои пункты пользователя - адреса
    с точкой под курсором (ui/menulinks.py). Последний пункт открывает
    окно списка."""
    sub = menu.addMenu(tr("Открыть в браузере"))
    for name, template in saved_links():
        sub.addAction(name).triggered.connect(
            lambda *a, t=template: window.open_menu_link(t, lat, lon))
    if not sub.isEmpty():
        sub.addSeparator()
    sub.addAction(tr("Добавить или изменить сайты…")).triggered.connect(
        lambda *a: window.edit_menu_links())
    return sub


def route_items(window, menu, place, lat, lon):
    """«Проложить маршрут отсюда» и «сюда». Точечная метка под курсором
    даёт маршруту свою точку и название, иначе - точка поверхности."""
    name = ""
    if place is not None and place.kind == "point" and place.shape.points:
        lat, lon = place.shape.points[0]
        name = place.name
    menu.addSeparator()
    menu.addAction(tr("Проложить маршрут отсюда")).triggered.connect(
        lambda *a: window.route_point(lat, lon, name, end=False))
    menu.addAction(tr("Проложить маршрут сюда")).triggered.connect(
        lambda *a: window.route_point(lat, lon, name, end=True))


def satellite_items(window, menu, px, py):
    """Пункты спутника под курсором: виток и след, камера следом. Если
    камера идёт следом, а спутника под курсором нет, - пункт, который
    её отпускает."""
    manager = getattr(window, "satellite_manager", None)
    if manager is None:
        return
    number = manager.under(px, py)
    if number is None:
        if not manager.follow:
            return
        number = manager.selected
    if not menu.isEmpty():
        menu.addSeparator()
    title = menu.addAction(manager.name_of(number) or str(number))
    title.setEnabled(False)
    chosen = manager.selected == number
    path = menu.addAction(tr("Орбита и след"))
    path.setCheckable(True)
    path.setChecked(chosen)
    path.toggled.connect(
        lambda on, n=number: manager.select(n if on else None))
    follow = menu.addAction(tr("Камера следом"))
    follow.setCheckable(True)
    follow.setChecked(chosen and manager.follow)
    follow.toggled.connect(
        lambda on, n=number: follow_satellite(manager, n, on))


def live_items(window, menu, px, py):
    """Поезд, судно или самолёт под курсором: «Камера следом». Если
    камера идёт следом, а объекта под курсором нет, - пункт, который её
    отпускает."""
    for manager in getattr(window, "live_managers", ()):
        key = manager.under(px, py) if manager.on else None
        if key is None:
            key = manager.followed
        if key is None:
            continue
        if not menu.isEmpty():
            menu.addSeparator()
        title = menu.addAction(manager.label(key))
        title.setEnabled(False)
        follow = menu.addAction(tr("Камера следом"))
        follow.setCheckable(True)
        follow.setChecked(manager.followed == key)
        follow.toggled.connect(
            lambda on, m=manager, k=key: m.set_follow(k if on else None))
        return


def track_items(window, menu, px, py):
    """Объект трека слоя проекта под курсором: «Камера следом». Если
    камера идёт следом, а объекта под курсором нет, - пункт, который её
    отпускает."""
    tracks = getattr(window, "tracks", None)
    if tracks is None:
        return
    target = tracks.under(px, py) or tracks.followed
    if target is None:
        return
    if not menu.isEmpty():
        menu.addSeparator()
    title = menu.addAction(tracks.label(target))
    title.setEnabled(False)
    follow = menu.addAction(tr("Камера следом"))
    follow.setCheckable(True)
    follow.setChecked(tracks.followed == target)
    follow.toggled.connect(
        lambda on, t=target: follow_track(window, t, on))


def follow_track(window, target, on):
    """Камера следом за объектом трека: живые объекты и модели треков
    KML отпускают её."""
    if on:
        for manager in getattr(window, "live_managers", ()):
            if getattr(manager, "followed", None) is not None:
                manager.set_follow(None)
        models = getattr(window, "model_tracks", None)
        if models is not None and models.followed is not None:
            models.set_follow(None)
    window.tracks.set_follow(target if on else None)


def model_track_items(window, menu, px, py):
    """Модель трека KML (gx:Track с Model) под курсором: «Камера
    следом», как у объекта трека слоя."""
    models = getattr(window, "model_tracks", None)
    if models is None:
        return
    target = models.under(px, py) or models.followed
    if target is None:
        return
    if not menu.isEmpty():
        menu.addSeparator()
    title = menu.addAction(models.label(target) or tr("Модель"))
    title.setEnabled(False)
    follow = menu.addAction(tr("Камера следом"))
    follow.setCheckable(True)
    follow.setChecked(models.followed == target)
    follow.toggled.connect(
        lambda on, t=target: follow_model(window, t, on))


def follow_model(window, target, on):
    """Камера следом за моделью трека KML: треки слоёв и живые объекты
    отпускают её."""
    if on:
        for manager in getattr(window, "live_managers", ()):
            if getattr(manager, "followed", None) is not None:
                manager.set_follow(None)
        if window.tracks.followed is not None:
            window.tracks.set_follow(None)
    window.model_tracks.set_follow(target if on else None)


def follow_satellite(manager, number, on):
    """Камера следом за спутником, выбор - вместе с ней."""
    if on and manager.selected != number:
        manager.select(number)
    manager.set_follow(on)


def fly_here(view, lat, lon):
    """Перелёт к точке с прежними высотой, азимутом и наклоном."""
    pose = view.navigator.pose
    view.fly_pose(lat, lon, pose.distance, pose.heading, pose.tilt)
