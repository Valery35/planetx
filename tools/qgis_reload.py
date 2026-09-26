# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Выгрузка и повторная загрузка плагина PlanetX внутри QGIS.

Запускается через мост:
import runpy; runpy.run_path(r"C:\\Dev\\planetx\\tools\\qgis_reload.py")

Печатает строку вида «planetx 0.0.1 loaded» и ошибки Python из журнала,
появившиеся за время перезагрузки. Сборщик пишет в журнал пробу
и печатает, дошла ли она. Без пробы ноль ошибок ничего не значит.
"""
import configparser
import os
import sys

import qgis.utils
from qgis.core import Qgis, QgsApplication, QgsMessageLog, QgsSettings

NAME = "planetx"
PROBE_TAG = "PlanetX проверка журнала"
ERROR_TAGS = ("Python error", "Ошибка Python", "Python warning",
              "Предупреждение Python")


def log_signal():
    """В QGIS 4 журнал шлёт только messageReceivedWithFormat."""
    log = QgsApplication.messageLog()
    return getattr(log, "messageReceivedWithFormat", None) \
        or log.messageReceived


def _reload():
    errors = []
    probe = []

    def on_message(message, tag, level, *extra):
        if tag == PROBE_TAG:
            probe.append(message)
        elif tag in ERROR_TAGS:
            errors.append(message.strip().splitlines()[-1])

    signal = log_signal()
    signal.connect(on_message)
    try:
        QgsMessageLog.logMessage("проба", PROBE_TAG, Qgis.MessageLevel.Info)
        qgis.utils.updateAvailablePlugins()
        if NAME in qgis.utils.plugins:
            qgis.utils.unloadPlugin(NAME)
        for mod in [m for m in sys.modules
                    if m == NAME or m.startswith(NAME + ".")]:
            del sys.modules[mod]
        loaded = qgis.utils.loadPlugin(NAME) and qgis.utils.startPlugin(NAME)
        QgsSettings().setValue("PythonPlugins/" + NAME, bool(loaded))
    finally:
        signal.disconnect(on_message)

    path = os.path.dirname(sys.modules[NAME].__file__) if loaded else ""
    meta = configparser.ConfigParser()
    meta.read(os.path.join(path, "metadata.txt"), encoding="utf-8")
    version = meta.get("general", "version", fallback="?")
    print(NAME, version, "loaded" if loaded else "NOT loaded")
    print("path:", os.path.realpath(path) if path else "-")
    print("проба журнала дошла:", bool(probe))
    print("python errors:", len(errors) if probe else "не проверено")
    for text in errors:
        print(text)


_reload()
