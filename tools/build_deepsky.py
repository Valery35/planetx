# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Собирает planetx/data/deepsky.json - объекты глубокого неба.

Источник - OpenNGC (github.com/mattiaverga/OpenNGC, CC BY-SA 4.0),
файлы database_files/NGC.csv и addendum.csv. Берутся все объекты
Мессье и объекты NGC и IC ярче LIMIT или с общим названием, кроме
звёзд, дублей и несуществующих. Запуск:

    python tools/build_deepsky.py <папка с NGC.csv и addendum.csv>

Строка объекта - [обозначение, RA°, Dec°, блеск или null, размер ′
или null, вид, созвездие, название en, название ru, обозначение NGC
или IC]. Русские названия - RU, выбор помощника по принятым в русской
литературе.
"""
import csv
import json
import os
import sys

LIMIT = 10.0  # звёздная величина
SKIP = ("*", "**", "Dup", "NonEx", "Nova")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))), "planetx", "data", "deepsky.json")

# Русские названия по обозначению OpenNGC.
RU = {
    "NGC1952": "Крабовидная туманность",
    "NGC6523": "Туманность Лагуна",
    "NGC6205": "Шаровое скопление в Геркулесе",
    "NGC6611": "Туманность Орёл",
    "NGC6618": "Туманность Омега",
    "NGC6514": "Туманность Трёхраздельная",
    "NGC6853": "Туманность Гантель",
    "NGC0224": "Галактика Андромеды",
    "NGC0598": "Галактика Треугольника",
    "NGC1976": "Туманность Ориона",
    "NGC2632": "Ясли",
    "Mel022": "Плеяды",
    "NGC5194": "Галактика Водоворот",
    "NGC6720": "Туманность Кольцо",
    "NGC4826": "Галактика Чёрный Глаз",
    "NGC3031": "Галактика Боде",
    "NGC3034": "Галактика Сигара",
    "NGC3587": "Туманность Сова",
    "NGC5457": "Галактика Вертушка",
    "NGC4594": "Галактика Сомбреро",
    "NGC5055": "Галактика Подсолнух",
    "NGC5236": "Южная Вертушка",
    "NGC6405": "Скопление Бабочка",
    "NGC6475": "Скопление Птолемея",
    "NGC6705": "Дикая Утка",
    "NGC0650": "Малая Гантель",
    "NGC4486": "Галактика Дева A",
    "NGC7000": "Туманность Северная Америка",
    "NGC0869": "Скопление h Персея",
    "NGC0884": "Скопление χ Персея",
    "NGC5139": "Омега Центавра",
    "NGC0104": "47 Тукана",
    "NGC0292": "Малое Магелланово Облако",
    "ESO056-115": "Большое Магелланово Облако",
    "NGC2237": "Туманность Розетка",
    "NGC6960": "Туманность Вуаль",
    "NGC6992": "Туманность Вуаль",
    "NGC3372": "Туманность Киля",
    "NGC7293": "Туманность Улитка",
    "NGC2264": "Скопление Рождественская Ёлка",
    "NGC0457": "Скопление Сова",
    "NGC2392": "Туманность Эскимос",
    "NGC7009": "Туманность Сатурн",
    "NGC6543": "Туманность Кошачий Глаз",
    "NGC4565": "Галактика Игла",
    "NGC0253": "Галактика Скульптор",
    "NGC5128": "Центавр A",
    "IC4715": "Малое звёздное облако Стрельца",
    "Cl399": "Вешалка",
    "IC1805": "Туманность Сердце",
    "IC1848": "Туманность Душа",
    "NGC1499": "Туманность Калифорния",
    "NGC2070": "Туманность Тарантул",
    "NGC6888": "Туманность Полумесяц",
    "NGC7635": "Туманность Пузырь",
    "NGC2068": "Туманность M78",
}


def magnitude(row):
    for key in ("V-Mag", "B-Mag"):
        if row[key]:
            return float(row[key])
    return None


def degrees(text, hours):
    sign = -1.0 if text.startswith("-") else 1.0
    h, m, s = (float(v) for v in text.lstrip("+-").split(":"))
    value = sign * (h + m / 60.0 + s / 3600.0)
    return value * 15.0 if hours else value


def designation(name):
    """NGC0224 - NGC 224, IC0434 - IC 434, прочие как есть."""
    for prefix in ("NGC", "IC"):
        if name.startswith(prefix) and name[len(prefix):].isdigit():
            return "{} {}".format(prefix, int(name[len(prefix):]))
    return name


def other(name):
    """Обозначение NGC или IC объекта Мессье, иного - пусто."""
    text = designation(name)
    return "" if text == name else text


def is_messier(label):
    return label[:1] == "M" and label[1:].isdigit()


def build(folder):
    rows = []
    for name in ("NGC.csv", "addendum.csv"):
        with open(os.path.join(folder, name), encoding="utf-8") as fh:
            rows += list(csv.DictReader(fh, delimiter=";"))
    out, messier = [], set()
    for row in rows:
        m = row["M"]
        mag = magnitude(row)
        common = row["Common names"].split(",")[0].strip()
        if not m and (row["Type"] in SKIP or not row["RA"]):
            continue
        if m and m in messier:
            continue
        if not m and not common and (mag is None or mag > LIMIT):
            continue
        if m:
            messier.add(m)
        label = "M{}".format(int(m)) if m else designation(row["Name"])
        size = float(row["MajAx"]) if row["MajAx"] else None
        out.append([label, round(degrees(row["RA"], True), 5),
                    round(degrees(row["Dec"], False), 5), mag, size,
                    row["Type"], row["Const"], common,
                    RU.get(row["Name"], ""),
                    other(row["Name"]) if m else ""])
    out.sort(key=lambda r: (not is_messier(r[0]), r[0]))
    return out


if __name__ == "__main__":
    data = build(sys.argv[1])
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump({"source": "OpenNGC, CC BY-SA 4.0",
                   "objects": data}, fh, ensure_ascii=False,
                  separators=(",", ":"))
        fh.write("\n")
    print(len(data), "objects,", sum(1 for r in data if is_messier(r[0])),
          "Messier")
