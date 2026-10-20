# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Архив бота для сервера: dist/planetx-bot.zip.

Внутри папка planetx-bot с тем же устройством, что в хранилище -
bot/planetx_bot.py, planetx/core/manualindex.py и указатели
руководств модулей bot/data/manuals_ru.json, manuals_en.json. Настроек
и токена в архиве нет. Указатели сценарий собирает заново из рабочих
копий модулей (bot/build_index.py), их в хранилище нет.
"""
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_index  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = (
    "bot/planetx_bot.py",
    "planetx/core/manualindex.py",
    "bot/data/manuals_ru.json",
    "bot/data/manuals_en.json",
)


def main():
    build_index.main()
    out = os.path.join(ROOT, "dist", "planetx-bot.zip")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name in FILES:
            z.write(os.path.join(ROOT, *name.split("/")),
                    "planetx-bot/" + name)
    print(out, os.path.getsize(out))


if __name__ == "__main__":
    main()
