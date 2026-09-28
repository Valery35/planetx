# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Проверка согласованности документации.

    $PY tools/check_docs.py

Следит за тем, что легко упустить при правках: битые внутренние ссылки,
отсутствие английской пары у русского файла, ссылки пары друг на друга,
кириллица в английских текстах за пределами ссылки на русскую версию.
Образец - одноимённая проверка Topoliner.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PAIRS = [("README.md", "README.en.md"),
         ("doc/MANUAL.md", "doc/MANUAL.en.md")]

# Подписи ссылок на русскую версию в английском файле кириллицей
# допустимы, как и русский адрес страницы на сайте.
ALLOWED_CYRILLIC = ("Русский", "Русская версия", "главная-страница")


def documents():
    names = [n for n in os.listdir(ROOT) if n.endswith(".md")]
    doc = os.path.join(ROOT, "doc")
    names += [os.path.join("doc", n) for n in os.listdir(doc)
              if n.endswith(".md")]
    return names


def read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
        return fh.read()


def main():
    problems = []
    for ru, en in PAIRS:
        for name in (ru, en):
            if not os.path.exists(os.path.join(ROOT, name)):
                problems.append("нет файла %s" % name)
    for name in documents():
        text = read(name)
        base = os.path.dirname(os.path.join(ROOT, name))
        for link in re.findall(r"\[[^\]]*\]\(([^)#:]+\.(?:md|jpg|png))\)",
                               text):
            if not os.path.exists(os.path.join(base, link)):
                problems.append("%s ссылается на несуществующий %s"
                                % (name, link))
        if name.endswith(".en.md"):
            cleaned = text
            for allowed in ALLOWED_CYRILLIC:
                cleaned = cleaned.replace(allowed, "")
            found = re.findall(r"[А-Яа-яЁё]+", cleaned)
            if found:
                problems.append("%s: кириллица в английском тексте: %r"
                                % (name, found[:5]))
    for ru, en in PAIRS:
        if not all(os.path.exists(os.path.join(ROOT, n)) for n in (ru, en)):
            continue
        if os.path.basename(en) not in read(ru):
            problems.append("%s не ссылается на %s" % (ru, en))
        if os.path.basename(ru) not in read(en):
            problems.append("%s не ссылается на %s" % (en, ru))
    if problems:
        print("Проблемы в документации:")
        for line in problems:
            print("  " + line)
        return 1
    print("Документация согласована.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
