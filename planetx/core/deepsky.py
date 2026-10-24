# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Объекты глубокого неба: каталог, подписи, поиск имени, без Qt.

Часть 2 снимка неба, как Google Sky, - решение автора от 24 октября
2026 года. Каталог data/deepsky.json собирает tools/build_deepsky.py
из OpenNGC (CC BY-SA 4.0) - все объекты Мессье и яркие NGC и IC.
Объект вне каталога ищет служба имён Sesame CDS (sesame_url,
parse_sesame) по Enter в строке «Поиск» вида неба.
"""
import json
import math
import os
import re
from collections import namedtuple
from urllib.parse import quote

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))), "data", "deepsky.json")
SESAME = "https://cds.unistra.fr/cgi-bin/nph-sesame/-oI/SNV?"
SIMBAD = "https://simbad.cds.unistra.fr/simbad/sim-id?Ident="

# Объекты NGC и IC подписываются при поле зрения не шире NGC_FOV,
# объекты Мессье - при любом. Выбор помощника.
NGC_FOV = 40.0
# Поле зрения перелёта к объекту - FIT размеров объекта, в пределах
# FOV_RANGE, градусы. Объект без размера - FOV_UNKNOWN.
FIT = 4.0
FOV_RANGE = (0.5, 30.0)
FOV_UNKNOWN = 2.0

DeepObject = namedtuple("DeepObject", "label ra dec mag size kind const "
                        "en ru other")
DeepObject.__doc__ = """Объект каталога. label - M31, NGC 7000; ra, dec -
градусы J2000; mag - звёздная величина или None; size - больший
поперечник в угловых минутах или None; kind - вид OpenNGC (G, OCl,
GCl, PN...); const - созвездие (три буквы); en, ru - общее название
или пусто; other - обозначение NGC или IC объекта Мессье или пусто."""

# Виды OpenNGC: название по-русски и по-английски.
KINDS = {
    "G": ("Галактика", "Galaxy"),
    "GPair": ("Пара галактик", "Galaxy pair"),
    "GTrpl": ("Тройка галактик", "Galaxy triplet"),
    "GGroup": ("Группа галактик", "Galaxy group"),
    "OCl": ("Рассеянное скопление", "Open cluster"),
    "GCl": ("Шаровое скопление", "Globular cluster"),
    "Cl+N": ("Скопление с туманностью", "Cluster with nebula"),
    "PN": ("Планетарная туманность", "Planetary nebula"),
    "Neb": ("Туманность", "Nebula"),
    "HII": ("Область HII", "HII region"),
    "EmN": ("Эмиссионная туманность", "Emission nebula"),
    "RfN": ("Отражательная туманность", "Reflection nebula"),
    "DrkN": ("Тёмная туманность", "Dark nebula"),
    "SNR": ("Остаток сверхновой", "Supernova remnant"),
    "*Ass": ("Звёздная ассоциация", "Stellar association"),
    "**": ("Двойная звезда", "Double star"),
    "*": ("Звезда", "Star"),
    "Other": ("Прочее", "Other"),
}


def load(path=DATA):
    """Объекты каталога, DeepObject."""
    with open(path, encoding="utf-8") as fh:
        return [DeepObject(*row) for row in json.load(fh)["objects"]]


def is_messier(obj):
    return obj.label[:1] == "M" and obj.label[1:].isdigit()


def kind_name(kind, language="ru"):
    names = KINDS.get(kind, KINDS["Other"])
    return names[0] if language == "ru" else names[1]


def title(obj, language="ru"):
    """Подпись на небе: название на языке, иначе обозначение."""
    return (obj.ru if language == "ru" else obj.en) or obj.label


def names(obj, language="ru"):
    """Имена, по которым объект находится строкой «Поиск»: обозначение
    слитно и через пробел, NGC или IC объекта Мессье, общие названия."""
    out = [obj.label, obj.label.replace(" ", "")]
    if is_messier(obj):
        out.append("M " + obj.label[1:])
    if obj.other:
        out += [obj.other, obj.other.replace(" ", "")]
    out += [n for n in (obj.ru, obj.en) if n]
    seen, unique = set(), []
    for name in out:
        if name.lower() not in seen:
            seen.add(name.lower())
            unique.append(name)
    return unique


def shown(obj, fov):
    """Подписывается ли объект при поле зрения fov, градусы."""
    return is_messier(obj) or fov <= NGC_FOV


def rank(obj):
    """Старшинство подписи - меньше раньше, как у подписей неба
    ui/skylabels.py: звёзды 10 + блеск, созвездия 20 + ранг."""
    mag = obj.mag if obj.mag is not None else 12.0
    return (15.0 if is_messier(obj) else 30.0) + mag


def fov_for(obj):
    """Поле зрения перелёта к объекту, градусы."""
    if not obj.size:
        return FOV_UNKNOWN
    return min(max(FIT * obj.size / 60.0, FOV_RANGE[0]), FOV_RANGE[1])


def radius_pixels(obj, radians_per_pixel):
    """Половина поперечника объекта в пикселях кадра, без размера - 0."""
    if not obj.size or radians_per_pixel <= 0.0:
        return 0.0
    return math.radians(obj.size / 120.0) / radians_per_pixel


def ra_text(ra):
    """Прямое восхождение в часах, минутах и секундах: 0ч 42м 44с."""
    seconds = int(round((ra % 360.0) / 15.0 * 3600.0)) % 86400
    return "{}h {:02d}m {:02d}s".format(seconds // 3600,
                                        seconds // 60 % 60, seconds % 60)


def dec_text(dec):
    """Склонение в градусах, минутах и секундах: +41° 16′ 07″."""
    seconds = int(round(abs(dec) * 3600.0))
    return "{}{}° {:02d}′ {:02d}″".format("-" if dec < 0 else "+",
                                          seconds // 3600,
                                          seconds // 60 % 60, seconds % 60)


def sesame_url(name):
    """Запрос службы имён Sesame CDS: Simbad, NED, VizieR."""
    return SESAME + quote(name.strip())


def simbad_url(obj):
    return SIMBAD + quote(obj.other or obj.label)


_J = re.compile(r"^%J\s+([-+]?\d+(?:\.\d*)?)\s+([-+]?\d+(?:\.\d*)?)",
                re.M)
_NAME = re.compile(r"^%I\.0\s+(.+?)\s*$", re.M)


def parse_sesame(text):
    """Ответ Sesame в (RA°, Dec°, имя) первого найденного или None."""
    found = _J.search(text or "")
    if found is None:
        return None
    ra, dec = float(found.group(1)), float(found.group(2))
    if not (0.0 <= ra <= 360.0 and -90.0 <= dec <= 90.0):
        return None
    name = _NAME.search(text)
    return ra, dec, " ".join(name.group(1).split()) if name else ""
