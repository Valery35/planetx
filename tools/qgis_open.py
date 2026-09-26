# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Проверка шага 0.5: окно глобуса открывается и рисует без дыр.

Запускается через мост в два вызова. Между ними главный поток QGIS
свободен, и тайлы успевают загрузиться.

    import runpy
    runpy.run_path(r"C:\\Dev\\planetx\\tools\\qgis_open.py")["start"]()
    runpy.run_path(r"C:\\Dev\\planetx\\tools\\qgis_open.py")["report"]()

Второй вызов включает проверочный режим, снимает кадр и печатает версию
контекста, количество тайлов, количество пурпурных пикселей фона внутри
диска Земли и количество зелёных пикселей подстилки. Фон внутри диска -
это дыра. Подстилка - это подложка уровня 2 в щели шире нуля и уже
пикселя. Снимок кладётся в папку временных файлов.
"""
import os
import tempfile

import qgis.utils

SHOT = os.path.join(tempfile.gettempdir(), "planetx_open.png")
LIMB_PX = 2  # полоса по краю диска, где фон законен


def _window():
    plugin = qgis.utils.plugins["planetx"]
    return plugin.window


PROBE_TAG = "PlanetX проверка журнала"


def log_signal():
    """Сигнал журнала сообщений QGIS.

    В QGIS 4 сообщения идут только через messageReceivedWithFormat,
    messageReceived не срабатывает. В QGIS 3 второго сигнала нет.
    """
    from qgis.core import QgsApplication
    log = QgsApplication.messageLog()
    return getattr(log, "messageReceivedWithFormat", None) \
        or log.messageReceived


def _collect_errors(plugin):
    """Собирать ошибки Python из журнала QGIS с момента открытия окна.

    Список живёт на объекте плагина, потому что runpy.run_path даёт
    новое пространство имён на каждый вызов. Сборщик сам пишет в журнал
    пробу, отчёт показывает, дошла ли она. Глухой сборщик виден сразу.
    """
    from qgis.core import Qgis, QgsMessageLog
    signal = log_signal()
    old = getattr(plugin, "_open_listener", None)
    if old is not None:
        signal.disconnect(old)
    plugin._open_errors = []
    plugin._open_probe = False

    def listener(message, tag, level, *extra):
        if tag == PROBE_TAG:
            plugin._open_probe = True
        elif tag in ("Python error", "Ошибка Python", "Python warning",
                     "Предупреждение Python"):
            plugin._open_errors.append(message.strip().splitlines()[-1])

    plugin._open_listener = listener
    signal.connect(listener)
    QgsMessageLog.logMessage("проба", PROBE_TAG, Qgis.MessageLevel.Info)


def start():
    plugin = qgis.utils.plugins["planetx"]
    _collect_errors(plugin)
    if plugin.window is not None:
        plugin.window.close()
        plugin.window = None
    plugin.run()
    print("окно открыто, загрузка идёт")


def report():
    from planetx.net.loader import image_to_rgba
    from planetx.render.view import start_keys

    window = _window()
    view = window.view
    keys = start_keys()
    loaded = sum(1 for key in keys if view.has(key))
    print("контекст:", view.gl_info.get("gl"), "|",
          view.gl_info.get("version"), view.gl_info.get("profile"))
    print("видеокарта:", view.gl_info.get("renderer"))
    print("загружено тайлов: %d из %d, ошибок %d, одновременно до %d"
          % (loaded, len(keys), len(window.errors), window.loader.max_seen))
    if window.errors:
        print("ошибки:", window.errors)
    print("User-Agent последнего запроса:", window.loader.last_user_agent)

    view.show_holes = True
    image = view.grabFramebuffer()
    view.show_holes = False
    view.update()
    image.save(SHOT)

    rgba = image_to_rgba(image)
    h, w = rgba.shape[:2]
    view.camera.width, view.camera.height = w, h
    mask = view.camera.earth_mask(erode=LIMB_PX)
    magenta = ((rgba[..., 0] == 255) & (rgba[..., 1] == 0)
               & (rgba[..., 2] == 255))
    green = ((rgba[..., 0] == 0) & (rgba[..., 1] == 255)
             & (rgba[..., 2] == 0))
    print("кадр %d×%d, нарисовано тайлов %d, в памяти %d"
          % (w, h, view.drawn, len(view.textures)))
    print("уровни в кадре:", dict(sorted(view.drawn_levels.items())))
    print("ошибок OpenGL за время окна:", dict(view.gl_errors) or 0)
    print("пикселей диска Земли: %d" % int(mask.sum()))
    print("пурпурных пикселей внутри диска: %d" % int((magenta & mask)
                                                      .sum()))
    print("пурпурных пикселей всего: %d" % int(magenta.sum()))
    print("пикселей подстилки внутри диска: %d" % int((green & mask).sum()))
    print("снимок:", SHOT)
    plugin = qgis.utils.plugins["planetx"]
    errors = getattr(plugin, "_open_errors", None)
    print("проба журнала дошла до сборщика:",
          getattr(plugin, "_open_probe", False))
    if errors is None:
        print("ошибки Python с открытия окна: не собирались")
    else:
        print("ошибок и предупреждений Python с открытия окна: %d"
              % len(errors))
        for line in sorted(set(errors))[:5]:
            print("  ", line)
    return {"gl": view.gl_info.get("version"),
            "profile": str(view.gl_info.get("profile")),
            "drawn": view.drawn,
            "holes": int((magenta & mask).sum()),
            "underlay": int((green & mask).sum())}
