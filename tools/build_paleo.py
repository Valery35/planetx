# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Маски суши палеогеографии для хранилища planetx-terrain.

    $PY tools/build_paleo.py fetch СЫРЬЁ
    $PY tools/build_paleo.py build СЫРЬЁ ХРАНИЛИЩЕ [ВОЗРАСТ ...]

fetch скачивает берега модели MERDITH2021 у веб-службы GPlates на все
возрасты 0-1000 млн лет с шагом 5 - по одному запросу, с паузой,
ответы сжатыми в папку СЫРЬЁ. Уже скачанный возраст не запрашивается.
Решение автора от 4 октября 2026 года - один раз скачать и положить
в planetx-terrain, служба отвечает 6-25 с на возраст и кэшировать
не разрешает.

build рисует из полных контуров маску суши - PNG в одном бите на
пиксель, MASK_WIDTH × MASK_WIDTH / 2, долгота -180 слева, север
вверху, суша белая - в ХРАНИЛИЩЕ/paleo/merdith2021/<возраст>.png,
и указатель index.json. Контуры не прореживаются и не отбрасываются,
как прежде у модуля (500 контуров из 2919, треть точек), отсюда дыры
в материках. Контур через линию перемены дат и вокруг полюса
раскладывает core.paleo.unwrapped, как у прежней маски.

Данные - модель Merdith et al. 2021 (Earth-Science Reviews 214,
103477), CC BY 4.0, zenodo.org/records/4485738, через GPlates Web
Service (EarthByte, AuScope).
"""
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.request

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "planetx", "core"))

import paleo  # noqa: E402

AGENT = "PlanetX (+https://github.com/Valery35/planetx)"
PAUSE = 1.0  # с между запросами к службе
TRIES = 3
TIMEOUT = 300  # с на ответ службы
MASK_WIDTH = paleo.MASK_FILE_WIDTH
FOLDER = os.path.join("paleo", "merdith2021")


def ages():
    return list(range(0, paleo.MAX_AGE + 1, paleo.STEP))


def raw_path(raw, age):
    return os.path.join(raw, "{}.json.gz".format(age))


def fetch(raw):
    """Скачать недостающие возрасты по одному."""
    os.makedirs(raw, exist_ok=True)
    todo = [a for a in ages() if not os.path.exists(raw_path(raw, a))]
    print("скачать", len(todo), "из", len(ages()), flush=True)
    for n, age in enumerate(todo):
        started = time.monotonic()
        body = None
        for attempt in range(TRIES):
            request = urllib.request.Request(paleo.url(age),
                                             headers={"User-Agent": AGENT})
            try:
                with urllib.request.urlopen(request,
                                            timeout=TIMEOUT) as reply:
                    body = reply.read()
                json.loads(body)
                break
            except (urllib.error.URLError, OSError, ValueError) as error:
                print("возраст", age, "попытка", attempt + 1, error,
                      flush=True)
                body = None
                time.sleep(10.0 * (attempt + 1))
        if body is None:
            print("возраст", age, "не скачан", flush=True)
            continue
        part = raw_path(raw, age) + ".part"
        with gzip.open(part, "wb") as fh:
            fh.write(body)
        os.replace(part, raw_path(raw, age))
        print("{}/{} возраст {} {:.1f} с {} КБ".format(
            n + 1, len(todo), age, time.monotonic() - started,
            len(body) // 1024), flush=True)
        time.sleep(PAUSE)


def rings_of(data):
    """Все внешние контуры ответа службы целиком: без прореживания и без
    отбрасывания мелких."""
    return paleo.parse(data, limit=10 ** 9, min_span=0.0, count=10 ** 9)


def draw_mask(rings, width=MASK_WIDTH):
    """Маска суши в один бит: Image «1», суша - 1."""
    height = width // 2
    image = Image.new("1", (width, height), 0)
    draw = ImageDraw.Draw(image)
    for ring in rings:
        points = paleo.unwrapped(ring)
        for shift in (-360.0, 0.0, 360.0):
            xy = [((lon + shift + 180.0) / 360.0 * width,
                   (90.0 - lat) / 180.0 * height) for lat, lon in points]
            if len(xy) >= 3:
                draw.polygon(xy, fill=1)
    return image


def build(raw, store, only=()):
    out = os.path.join(store, FOLDER)
    os.makedirs(out, exist_ok=True)
    done = []
    for age in ages():
        if only and age not in only:
            continue
        path = raw_path(raw, age)
        if not os.path.exists(path):
            continue
        with gzip.open(path, "rb") as fh:
            data = json.loads(fh.read())
        rings = rings_of(data)
        image = draw_mask(rings)
        target = os.path.join(out, "{}.png".format(age))
        image.save(target, optimize=True)
        pixels = image.convert("L").histogram()
        land = pixels[255] / float(image.width * image.height)
        done.append(age)
        print("возраст {} контуров {} точек {} суша {:.1%} {} КБ".format(
            age, len(rings), sum(len(r) for r in rings), land,
            os.path.getsize(target) // 1024), flush=True)
    present = sorted(int(name[:-4]) for name in os.listdir(out)
                     if name.endswith(".png") and name[:-4].isdigit())
    index = {"model": paleo.MODEL, "step": paleo.STEP,
             "max_age": paleo.MAX_AGE, "width": MASK_WIDTH,
             "ages": present,
             "source": "Merdith et al. 2021, CC BY 4.0, "
                       "zenodo.org/records/4485738, GPlates Web Service"}
    with open(os.path.join(out, "index.json"), "w", encoding="utf-8",
              newline="\n") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=1)
    print("собрано", len(done), "в указателе", len(present))


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "fetch":
        fetch(sys.argv[2])
    elif len(sys.argv) >= 4 and sys.argv[1] == "build":
        build(sys.argv[2], sys.argv[3],
              tuple(int(a) for a in sys.argv[4:]))
    else:
        print(__doc__)
