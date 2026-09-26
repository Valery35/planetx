# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Сведения о плагине из metadata.txt."""
import configparser
import os

METADATA = os.path.join(os.path.dirname(__file__), "metadata.txt")


def metadata(field, fallback=""):
    meta = configparser.ConfigParser(interpolation=None)
    meta.read(METADATA, encoding="utf-8")
    return meta.get("general", field, fallback=fallback)


def plugin_version():
    return metadata("version", "0")
