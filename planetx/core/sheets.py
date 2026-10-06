# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Номенклатура листов карт в точке: общемировые разграфки.

Всё считается формулой по широте и долготе, данных не нужно.

- Международная карта мира 1:1 000 000 (IMW): лист 4° по широте
  и 6° по долготе. Пояс - буква A-V от экватора, перед ней N или S
  полушария, выше 88° - Z. Колонна - номер 1-60 от 180° на восток.
- Российская номенклатура (ГОСТ Р 51607, советская система) до
  1:200 000. 1:1 000 000 - O-40, между 60° и 76° листы сдвоены по
  долготе (P-39,40), между 76° и 88° счетверены (T-37,38,39,40).
  1:500 000 - четверть листа, буквы А-Г, севернее 60° сдвоены
  (R-39-А,Б). 1:200 000 - 36 листов 40′ × 1°, римские I-XXXVI,
  между 60° и 76° сдвоены, между 76° и 88° строены
  (U-40-XXXI,XXXII,XXXIII). Южное полушарие помечается «(Ю. П.)».
  По той же номенклатуре нумеруются листы Госгеолкарты-1000 и 200.
- NATO, JOG 1:250 000 (серия 1501): лист IMW делится на 16 листов
  1° × 1.5°, номера 1-16 с северо-западного угла по рядам. Между 60°
  и 68° лист IMW сдвоен (NQ 33,34) и делится на 16 листов 1° × 3°,
  между 68° и 72° - на 12 листов 1° × 4°. Правила сверены по листам
  NH 42-5 (Кветта), NM 11-3 (Банф), NQ 33,34-1…4 (Будё, Сулитьельма,
  Кируна, Виттанги) и NR 33,34-11 (Нарвик) 7 октября 2026 года.
  Севернее 72° разграфка не найдена, номер не даётся.
- MGRS: зона, полоса и квадрат 100 км, расчёт - core/coords.py.
"""
try:  # внутри плагина QGIS
    from .coords import to_mgrs
except ImportError:  # headless-тесты
    from coords import to_mgrs

LETTERS = "ABCDEFGHIJKLMNOPQRSTUV"  # пояса по 4° от экватора
QUARTERS = "АБВГ"  # листы 1:500 000, кириллица
SOUTH_MARK = " (Ю. П.)"
JOG_LIMIT = 72.0  # севернее разграфка JOG не найдена


def roman(number):
    """Римская запись числа 1-39."""
    out = ""
    for value, sign in ((10, "X"), (9, "IX"), (5, "V"), (4, "IV"),
                        (1, "I")):
        while number >= value:
            out += sign
            number -= value
    return out


def _lon(lon):
    return (lon + 180.0) % 360.0 - 180.0


class Cell:
    """Лист 1:1 000 000 под точкой: буква, колонна, северный и западный
    край и место точки от северо-западного угла в градусах."""

    def __init__(self, lat, lon):
        lat = max(-90.0, min(90.0, lat))
        lon = _lon(lon)
        self.south = lat < 0.0
        index = int(abs(lat) // 4.0)
        self.polar = index >= len(LETTERS)
        self.letter = "Z" if self.polar else LETTERS[index]
        self.band = abs(lat)  # широта от экватора
        self.column = min(int((lon + 180.0) // 6.0) + 1, 60)
        north = -4.0 * index if self.south else 4.0 * (index + 1)
        west = (self.column - 1) * 6.0 - 180.0
        self.down = min(max(north - lat, 0.0), 4.0 - 1e-9)
        self.right = min(max(lon - west, 0.0), 6.0 - 1e-9)

    def group(self, size):
        """Номера колонн сдвоенного или счетверённого листа."""
        start = self.column - (self.column - 1) % size
        return list(range(start, start + size))


def imw(lat, lon):
    """Лист Международной карты мира 1:1 000 000: «NO 40»."""
    cell = Cell(lat, lon)
    prefix = ("S" if cell.south else "N") + cell.letter
    if cell.polar:
        return prefix
    return "{} {}".format(prefix, cell.column)


def _million(cell):
    if cell.band >= 76.0:
        columns = cell.group(4)
    elif cell.band >= 60.0:
        columns = cell.group(2)
    else:
        columns = [cell.column]
    return "{}-{}".format(cell.letter, ",".join(map(str, columns)))


def russian(lat, lon, scale, south_mark=SOUTH_MARK):
    """Номенклатура листа масштаба 1 000 000, 500 000 или 200 000.
    Выше 88° - лист Z, листов крупнее него нет (None)."""
    cell = Cell(lat, lon)
    mark = south_mark if cell.south else ""
    if cell.polar:
        return "Z" + mark if scale == 1000000 else None
    base = "{}-{}".format(cell.letter, cell.column)
    if scale == 1000000:
        return _million(cell) + mark
    if scale == 500000:
        row = int(cell.down // 2.0)
        if cell.band >= 60.0:
            pair = QUARTERS[2 * row:2 * row + 2]
            return "{}-{}{}".format(base, ",".join(pair), mark)
        col = int(cell.right // 3.0)
        return "{}-{}{}".format(base, QUARTERS[2 * row + col], mark)
    if scale == 200000:
        row = min(int(cell.down * 1.5), 5)
        col = int(cell.right)
        size = 3 if cell.band >= 76.0 else 2 if cell.band >= 60.0 else 1
        start = col - col % size
        numbers = [roman(row * 6 + c + 1)
                   for c in range(start, start + size)]
        return "{}-{}{}".format(base, ",".join(numbers), mark)
    raise ValueError(scale)


def jog(lat, lon):
    """Лист JOG 1:250 000: «NO 40-6», «NQ 33,34-3». Севернее 72° -
    None."""
    cell = Cell(lat, lon)
    if cell.band >= JOG_LIMIT:
        return None
    prefix = ("S" if cell.south else "N") + cell.letter
    row = int(cell.down)
    if cell.band < 60.0:
        sheet = row * 4 + int(cell.right // 1.5) + 1
        return "{} {}-{}".format(prefix, cell.column, sheet)
    columns = cell.group(2)
    right = cell.right + (cell.column - columns[0]) * 6.0
    if cell.band < 68.0:
        sheet = row * 4 + int(right // 3.0) + 1
    else:
        sheet = row * 3 + int(right // 4.0) + 1
    return "{} {}-{}".format(prefix, ",".join(map(str, columns)), sheet)


def mgrs_square(lat, lon):
    """Зона, полоса и квадрат 100 км MGRS: «40V DK». Вне UTM - None."""
    text = to_mgrs(lat, lon, 1)
    if text is None:
        return None
    return " ".join(text.split()[:2])


def sheets(lat, lon, south_mark=SOUTH_MARK):
    """Строки окна: (система, знаменатель масштаба или None, номер).
    Номер None - листа в этой разграфке нет."""
    return [
        ("imw", 1000000, imw(lat, lon)),
        ("russian", 1000000, russian(lat, lon, 1000000, south_mark)),
        ("russian", 500000, russian(lat, lon, 500000, south_mark)),
        ("russian", 200000, russian(lat, lon, 200000, south_mark)),
        ("jog", 250000, jog(lat, lon)),
        ("mgrs", None, mgrs_square(lat, lon)),
    ]
