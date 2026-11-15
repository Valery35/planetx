# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Архив бота для сервера: dist/planetx-bot.zip.

Внутри папка planetx-bot с тем же устройством, что в хранилище -
bot/planetx_bot.py, planetx/core/manualindex.py, указатели руководств
модулей bot/data/manuals_ru.json, manuals_en.json и метка сборки
bot/data/build.json. Настроек и токена в архиве нет. Указатели
сценарий собирает заново из рабочих копий модулей (bot/build_index.py),
их в хранилище нет.

Метка сборки - коммит рабочей копии и время UTC. Она вписывается
в BUILD копии planetx_bot.py в архиве и в build.json. Адрес бота
отвечает «PlanetX bot <метка>», файлы из разных архивов -
«PlanetX bot mismatch …», так видна половинная выкладка.
"""
import json
import os
import re
import sys
import time
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOT = "bot/planetx_bot.py"
FILES = (
    BOT,
    "planetx/core/manualindex.py",
    "bot/data/manuals_ru.json",
    "bot/data/manuals_en.json",
)
STAMP = "bot/data/build.json"
_BUILD_LINE = re.compile(r'^BUILD = "[^"\n]*"$', re.MULTILINE)


def commit(root=ROOT):
    """Короткий номер коммита рабочей копии по .git без программы git."""
    git = os.path.join(root, ".git")
    try:
        with open(os.path.join(git, "HEAD"), encoding="utf-8") as f:
            head = f.read().strip()
        if not head.startswith("ref: "):
            return head[:7]
        ref = head[5:]
        path = os.path.join(git, *ref.split("/"))
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return f.read().strip()[:7]
        with open(os.path.join(git, "packed-refs"), encoding="utf-8") as f:
            for line in f:
                if line.rstrip().endswith(" " + ref):
                    return line[:7]
    except OSError:
        pass
    return "nogit"


def stamped(source, build):
    """Текст planetx_bot.py с меткой сборки в BUILD."""
    text, count = _BUILD_LINE.subn('BUILD = "{}"'.format(build), source)
    if count != 1:
        raise ValueError("BUILD не найден в " + BOT)
    return text


def bundle(out, build, root=ROOT):
    """Архив out с меткой build, без сборки указателей."""
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name in FILES:
            path = os.path.join(root, *name.split("/"))
            if name == BOT:
                with open(path, encoding="utf-8") as f:
                    z.writestr("planetx-bot/" + name,
                               stamped(f.read(), build))
            else:
                z.write(path, "planetx-bot/" + name)
        z.writestr("planetx-bot/" + STAMP, json.dumps({"build": build}))
    return out


def main():
    import build_index
    build_index.main()
    build = "{} {}".format(commit(), time.strftime("%Y-%m-%dT%H:%MZ",
                                                   time.gmtime()))
    out = bundle(os.path.join(ROOT, "dist", "planetx-bot.zip"), build)
    print(out, os.path.getsize(out))
    print("Метка сборки:", build)


if __name__ == "__main__":
    main()
