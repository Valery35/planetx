# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Положения спутников по орбитальным элементам, модель SGP4/SDP4.

Расчёт без Qt. Модель - SGP4 в редакции Vallado, Crawford, Hujsak,
Kelso, «Revisiting Spacetrack Report #3», AIAA 2006-6753, режим
improved, постоянные WGS72, как у элементов NORAD. Формулы перенесены
из опубликованного кода авторов статьи. Начальные величины считаются
для каждого спутника отдельно, один раз (`Orbits`). Положения
на момент считаются сразу для всех спутников массивами NumPy
(`Orbits.at`), в том числе глубокая часть модели - Луна, Солнце
и резонансы суточных и полусуточных орбит.

Состояния между вызовами нет. Резонансы интегрируются от эпохи
элементов шагами по 720 мин при каждом вызове, как в эталоне при
первом вызове. Результат - положение и скорость в системе TEME, км
и км/с, `teme_to_ecef` поворачивает их в систему Земли по звёздному
времени. Полярное движение и разность UT1-UTC не учитываются, это
до сотен метров на орбите.

Коды ошибок - как в эталоне: 1 - эксцентриситет вне 0-1, 2 -
среднее движение не больше нуля, 3 - возмущённый эксцентриситет вне
0-1, 4 - отрицательный фокальный параметр, 6 - спутник ниже
поверхности Земли. При ошибках 1-4 положение - NaN.
"""
import math

import numpy as np

TWOPI = 2.0 * math.pi
X2O3 = 2.0 / 3.0
DEG = math.pi / 180.0

# Постоянные WGS72, с ними строятся элементы NORAD.
MU = 398600.8  # км³/с²
RADIUS = 6378.135  # км
XKE = 60.0 / math.sqrt(RADIUS ** 3 / MU)
TUMIN = 1.0 / XKE
J2 = 0.001082616
J3 = -0.00000253881
J4 = -0.00000165597
J3OJ2 = J3 / J2
VKMPERSEC = RADIUS * XKE / 60.0

JD_EPOCH0 = 2433281.5  # 0 января 1950 года, 0 ч - начало отсчёта эпох
JD_1970 = 2440587.5
DEEP_PERIOD = 225.0  # мин, с этого периода орбита считается глубокой

# Глубокая часть модели.
ZNS = 1.19459e-5
ZES = 0.01675
ZNL = 1.5835218e-4
ZEL = 0.05490
RPTIM = 4.37526908801129966e-3  # вращение Земли, рад/мин
STEP = 720.0  # мин, шаг интегрирования резонансов
STEP2 = 259200.0

# Поля спутника, которые хранит Orbits. Порядок не важен.
FIELDS = (
    "bstar", "ecco", "argpo", "inclo", "mo", "no", "nodeo", "epoch",
    "isimp", "deep", "irez", "gsto",
    "mdot", "argpdot", "nodedot", "nodecf", "cc1", "cc4", "cc5", "t2cof",
    "t3cof", "t4cof", "t5cof", "omgcof", "eta", "xmcof", "delmo", "sinmao",
    "d2", "d3", "d4", "con41", "x1mth2", "x7thm1", "xlcof", "aycof",
    "d2201", "d2211", "d3210", "d3222", "d4410", "d4422", "d5220", "d5232",
    "d5421", "d5433", "dedt", "didt", "dmdt", "dnodt", "domdt", "del1",
    "del2", "del3", "xfact", "xlamo",
    "e3", "ee2", "peo", "pgho", "pho", "pinco", "plo", "se2", "se3", "sgh2",
    "sgh3", "sgh4", "sh2", "sh3", "si2", "si3", "sl2", "sl3", "sl4", "xgh2",
    "xgh3", "xgh4", "xh2", "xh3", "xi2", "xi3", "xl2", "xl3", "xl4", "zmol",
    "zmos")


def gstime(jdut1):
    """Звёздное время Гринвича, рад, по юлианской дате. Принимает
    число или массив."""
    tut1 = (np.asarray(jdut1, dtype=float) - 2451545.0) / 36525.0
    temp = (-6.2e-6 * tut1 * tut1 * tut1 + 0.093104 * tut1 * tut1
            + (876600.0 * 3600 + 8640184.812866) * tut1 + 67310.54841)
    return np.mod(temp * DEG / 240.0, TWOPI)


def jday(year, month, day, hour=0, minute=0, second=0.0):
    """Юлианская дата по дате и времени UTC, как jday эталона."""
    return (367.0 * year
            - (7 * (year + ((month + 9) // 12))) * 0.25 // 1.0
            + 275 * month / 9.0 // 1.0
            + day + 1721013.5
            + ((second / 60.0 + minute) / 60.0 + hour) / 24.0)


class Elements:
    """Средние элементы спутников массивами, единицы SGP4.

    name - названия, number - номера NORAD, epoch - эпоха, сутки от
    0 января 1950 года, bstar, ecco - эксцентриситет, углы в радианах
    (argpo, inclo, mo, nodeo), no - среднее движение по Козаи, рад/мин.
    """

    def __init__(self, name, number, epoch, bstar, ecco, argpo, inclo, mo,
                 no, nodeo):
        self.name = list(name)
        self.number = np.asarray(number, dtype=np.int64)
        self.epoch = np.asarray(epoch, dtype=float)
        self.bstar = np.asarray(bstar, dtype=float)
        self.ecco = np.asarray(ecco, dtype=float)
        self.argpo = np.asarray(argpo, dtype=float)
        self.inclo = np.asarray(inclo, dtype=float)
        self.mo = np.asarray(mo, dtype=float)
        self.no = np.asarray(no, dtype=float)
        self.nodeo = np.asarray(nodeo, dtype=float)

    def __len__(self):
        return len(self.name)


def _float(text, default=None):
    try:
        return float(text)
    except (TypeError, ValueError):
        return default


def _iso_epoch(text):
    """Сутки от 0 января 1950 года по записи ISO «2026-10-05T01:07:02.3»
    или None."""
    try:
        date, clock = text.strip().split("T")
        year, month, day = (int(v) for v in date.split("-"))
        parts = clock.split(":")
        hour, minute = int(parts[0]), int(parts[1])
        second = float(parts[2]) if len(parts) > 2 else 0.0
    except (ValueError, IndexError, AttributeError):
        return None
    return jday(year, month, day, hour, minute, second) - JD_EPOCH0


def parse_csv(text):
    """Elements из CSV CelesTrak (запись OMM). Строки без нужных полей
    пропускаются."""
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        return Elements([], [], [], [], [], [], [], [], [], [])
    head = [h.strip().upper() for h in lines[0].split(",")]
    need = ("OBJECT_NAME", "NORAD_CAT_ID", "EPOCH", "MEAN_MOTION",
            "ECCENTRICITY", "INCLINATION", "RA_OF_ASC_NODE",
            "ARG_OF_PERICENTER", "MEAN_ANOMALY", "BSTAR")
    if any(n not in head for n in need):
        return Elements([], [], [], [], [], [], [], [], [], [])
    at = {n: head.index(n) for n in need}
    rows = {n: [] for n in need}
    for line in lines[1:]:
        cells = _split_csv(line)
        if len(cells) < len(head):
            continue
        epoch = _iso_epoch(cells[at["EPOCH"]])
        values = [_float(cells[at[n]]) for n in need[3:]]
        number = _float(cells[at["NORAD_CAT_ID"]])
        if epoch is None or number is None or None in values:
            continue
        rows["OBJECT_NAME"].append(cells[at["OBJECT_NAME"]].strip())
        rows["NORAD_CAT_ID"].append(int(number))
        rows["EPOCH"].append(epoch)
        for name, value in zip(need[3:], values):
            rows[name].append(value)
    return Elements(
        rows["OBJECT_NAME"], rows["NORAD_CAT_ID"], rows["EPOCH"],
        rows["BSTAR"], rows["ECCENTRICITY"],
        np.array(rows["ARG_OF_PERICENTER"]) * DEG,
        np.array(rows["INCLINATION"]) * DEG,
        np.array(rows["MEAN_ANOMALY"]) * DEG,
        np.array(rows["MEAN_MOTION"]) / 720.0 * math.pi,
        np.array(rows["RA_OF_ASC_NODE"]) * DEG)


def _split_csv(line):
    """Ячейки строки CSV, кавычки снимаются. Запятых внутри названий
    у CelesTrak нет, но кавычки учитываются."""
    cells, cell, quoted = [], [], False
    for ch in line:
        if ch == '"':
            quoted = not quoted
        elif ch == "," and not quoted:
            cells.append("".join(cell))
            cell = []
        else:
            cell.append(ch)
    cells.append("".join(cell))
    return cells


def parse_tle(lines):
    """Elements из двухстрочных элементов. Строка названия перед парой
    необязательна."""
    rows = []
    name = ""
    first = None
    for raw in lines:
        line = raw.rstrip()
        if line.startswith("1 ") and len(line) >= 64:
            first = line
            continue
        if line.startswith("2 ") and len(line) >= 63 and first:
            rows.append((name or first[2:7].strip(), first, line))
            name, first = "", None
            continue
        if line and not line.startswith("#"):
            name = line.strip()
            first = None
    out = {k: [] for k in ("name", "number", "epoch", "bstar", "ecco",
                           "argpo", "inclo", "mo", "no", "nodeo")}
    for name, one, two in rows:
        year = int(one[18:20])
        year += 2000 if year < 57 else 1900
        days = float(one[20:32])
        bstar = float(one[53] + "." + one[54:59]) * 10.0 ** int(one[59:61])
        out["name"].append(name)
        out["number"].append(int(one[2:7]))
        out["epoch"].append(jday(year, 1, 1) + days - 1.0 - JD_EPOCH0)
        out["bstar"].append(bstar)
        out["ecco"].append(float("0." + two[26:33].replace(" ", "0")))
        out["argpo"].append(float(two[34:42]) * DEG)
        out["inclo"].append(float(two[8:16]) * DEG)
        out["mo"].append(float(two[43:51]) * DEG)
        out["no"].append(float(two[52:63]) * TWOPI / 1440.0)
        out["nodeo"].append(float(two[17:25]) * DEG)
    return Elements(**out)


# Начальные величины одного спутника.

def _init_one(epoch, bstar, ecco, argpo, inclo, mo, no_kozai, nodeo):
    """Поля FIELDS одного спутника словарём, как sgp4init эталона."""
    s = dict.fromkeys(FIELDS, 0.0)
    s.update(bstar=bstar, ecco=ecco, argpo=argpo, inclo=inclo, mo=mo,
             nodeo=nodeo, epoch=epoch)
    ss = 78.0 / RADIUS + 1.0
    qzms2t = ((120.0 - 78.0) / RADIUS) ** 4

    # initl: среднее движение без поправки Козаи, звёздное время.
    eccsq = ecco * ecco
    omeosq = 1.0 - eccsq
    rteosq = math.sqrt(omeosq)
    cosio = math.cos(inclo)
    cosio2 = cosio * cosio
    ak = (XKE / no_kozai) ** X2O3
    d1 = 0.75 * J2 * (3.0 * cosio2 - 1.0) / (rteosq * omeosq)
    delta = d1 / (ak * ak)
    adel = ak * (1.0 - delta * delta - delta
                 * (1.0 / 3.0 + 134.0 * delta * delta / 81.0))
    delta = d1 / (adel * adel)
    no = no_kozai / (1.0 + delta)
    ao = (XKE / no) ** X2O3
    sinio = math.sin(inclo)
    po = ao * omeosq
    con42 = 1.0 - 5.0 * cosio2
    s["con41"] = -con42 - cosio2 - cosio2
    posq = po * po
    rp = ao * (1.0 - ecco)
    s["gsto"] = float(gstime(epoch + JD_EPOCH0))
    s["no"] = no

    s["isimp"] = 1.0 if rp < 220.0 / RADIUS + 1.0 else 0.0
    sfour = ss
    qzms24 = qzms2t
    perige = (rp - 1.0) * RADIUS
    if perige < 156.0:
        sfour = perige - 78.0
        if perige < 98.0:
            sfour = 20.0
        qzms24 = ((120.0 - sfour) / RADIUS) ** 4
        sfour = sfour / RADIUS + 1.0
    pinvsq = 1.0 / posq
    tsi = 1.0 / (ao - sfour)
    eta = ao * ecco * tsi
    s["eta"] = eta
    etasq = eta * eta
    eeta = ecco * eta
    psisq = abs(1.0 - etasq)
    coef = qzms24 * tsi ** 4
    coef1 = coef / psisq ** 3.5
    cc2 = coef1 * no * (ao * (1.0 + 1.5 * etasq + eeta * (4.0 + etasq))
                        + 0.375 * J2 * tsi / psisq * s["con41"]
                        * (8.0 + 3.0 * etasq * (8.0 + etasq)))
    cc1 = bstar * cc2
    s["cc1"] = cc1
    cc3 = 0.0
    if ecco > 1.0e-4:
        cc3 = -2.0 * coef * tsi * J3OJ2 * no * sinio / ecco
    s["x1mth2"] = 1.0 - cosio2
    s["cc4"] = 2.0 * no * coef1 * ao * omeosq * (
        eta * (2.0 + 0.5 * etasq) + ecco * (0.5 + 2.0 * etasq)
        - J2 * tsi / (ao * psisq) * (
            -3.0 * s["con41"] * (1.0 - 2.0 * eeta + etasq
                                 * (1.5 - 0.5 * eeta))
            + 0.75 * s["x1mth2"] * (2.0 * etasq - eeta * (1.0 + etasq))
            * math.cos(2.0 * argpo)))
    s["cc5"] = 2.0 * coef1 * ao * omeosq * (
        1.0 + 2.75 * (etasq + eeta) + eeta * etasq)
    cosio4 = cosio2 * cosio2
    temp1 = 1.5 * J2 * pinvsq * no
    temp2 = 0.5 * temp1 * J2 * pinvsq
    temp3 = -0.46875 * J4 * pinvsq * pinvsq * no
    s["mdot"] = (no + 0.5 * temp1 * rteosq * s["con41"] + 0.0625 * temp2
                 * rteosq * (13.0 - 78.0 * cosio2 + 137.0 * cosio4))
    s["argpdot"] = (-0.5 * temp1 * con42 + 0.0625 * temp2
                    * (7.0 - 114.0 * cosio2 + 395.0 * cosio4)
                    + temp3 * (3.0 - 36.0 * cosio2 + 49.0 * cosio4))
    xhdot1 = -temp1 * cosio
    s["nodedot"] = xhdot1 + (0.5 * temp2 * (4.0 - 19.0 * cosio2)
                             + 2.0 * temp3 * (3.0 - 7.0 * cosio2)) * cosio
    xpidot = s["argpdot"] + s["nodedot"]
    s["omgcof"] = bstar * cc3 * math.cos(argpo)
    if ecco > 1.0e-4:
        s["xmcof"] = -X2O3 * coef * bstar / eeta
    s["nodecf"] = 3.5 * omeosq * xhdot1 * cc1
    s["t2cof"] = 1.5 * cc1
    if abs(cosio + 1.0) > 1.5e-12:
        s["xlcof"] = (-0.25 * J3OJ2 * sinio * (3.0 + 5.0 * cosio)
                      / (1.0 + cosio))
    else:
        s["xlcof"] = -0.25 * J3OJ2 * sinio * (3.0 + 5.0 * cosio) / 1.5e-12
    s["aycof"] = -0.5 * J3OJ2 * sinio
    s["delmo"] = (1.0 + eta * math.cos(mo)) ** 3
    s["sinmao"] = math.sin(mo)
    s["x7thm1"] = 7.0 * cosio2 - 1.0

    if TWOPI / no >= DEEP_PERIOD:
        s["deep"] = 1.0
        s["isimp"] = 1.0
        com = _dscom(epoch, ecco, argpo, 0.0, inclo, nodeo, no)
        for key in ("e3", "ee2", "se2", "se3", "sgh2", "sgh3", "sgh4",
                    "sh2", "sh3", "si2", "si3", "sl2", "sl3", "sl4",
                    "xgh2", "xgh3", "xgh4", "xh2", "xh3", "xi2", "xi3",
                    "xl2", "xl3", "xl4", "zmol", "zmos"):
            s[key] = com[key]
        _dsinit(s, com, eccsq, xpidot)

    if not s["isimp"]:
        cc1sq = cc1 * cc1
        d2 = 4.0 * ao * tsi * cc1sq
        temp = d2 * tsi * cc1 / 3.0
        d3 = (17.0 * ao + sfour) * temp
        d4 = 0.5 * temp * ao * tsi * (221.0 * ao + 31.0 * sfour) * cc1
        s.update(d2=d2, d3=d3, d4=d4)
        s["t3cof"] = d2 + 2.0 * cc1sq
        s["t4cof"] = 0.25 * (3.0 * d3 + cc1 * (12.0 * d2 + 10.0 * cc1sq))
        s["t5cof"] = 0.2 * (3.0 * d4 + 12.0 * cc1 * d3 + 6.0 * d2 * d2
                            + 15.0 * cc1sq * (2.0 * d2 + cc1sq))
    return s


def _dscom(epoch, ep, argpp, tc, inclp, nodep, np_):
    """Общие величины глубокой части - солнечные и лунные члены."""
    c1ss = 2.9864797e-6
    c1l = 4.7968065e-7
    zsinis = 0.39785416
    zcosis = 0.91744867
    zcosgs = 0.1945905
    zsings = -0.98088458
    nm = np_
    em = ep
    snodm = math.sin(nodep)
    cnodm = math.cos(nodep)
    sinomm = math.sin(argpp)
    cosomm = math.cos(argpp)
    sinim = math.sin(inclp)
    cosim = math.cos(inclp)
    emsq = em * em
    betasq = 1.0 - emsq
    rtemsq = math.sqrt(betasq)
    day = epoch + 18261.5 + tc / 1440.0
    xnodce = (4.5236020 - 9.2422029e-4 * day) % TWOPI
    stem = math.sin(xnodce)
    ctem = math.cos(xnodce)
    zcosil = 0.91375164 - 0.03568096 * ctem
    zsinil = math.sqrt(1.0 - zcosil * zcosil)
    zsinhl = 0.089683511 * stem / zsinil
    zcoshl = math.sqrt(1.0 - zsinhl * zsinhl)
    gam = 5.8351514 + 0.0019443680 * day
    zx = 0.39785416 * stem / zsinil
    zy = zcoshl * ctem + 0.91744867 * zsinhl * stem
    zx = math.atan2(zx, zy)
    zx = gam + zx - xnodce
    zcosgl = math.cos(zx)
    zsingl = math.sin(zx)

    zcosg, zsing, zcosi, zsini = zcosgs, zsings, zcosis, zsinis
    zcosh, zsinh = cnodm, snodm
    cc = c1ss
    xnoi = 1.0 / nm
    out = {}
    for lunar in (False, True):
        a1 = zcosg * zcosh + zsing * zcosi * zsinh
        a3 = -zsing * zcosh + zcosg * zcosi * zsinh
        a7 = -zcosg * zsinh + zsing * zcosi * zcosh
        a8 = zsing * zsini
        a9 = zsing * zsinh + zcosg * zcosi * zcosh
        a10 = zcosg * zsini
        a2 = cosim * a7 + sinim * a8
        a4 = cosim * a9 + sinim * a10
        a5 = -sinim * a7 + cosim * a8
        a6 = -sinim * a9 + cosim * a10
        x1 = a1 * cosomm + a2 * sinomm
        x2 = a3 * cosomm + a4 * sinomm
        x3 = -a1 * sinomm + a2 * cosomm
        x4 = -a3 * sinomm + a4 * cosomm
        x5 = a5 * sinomm
        x6 = a6 * sinomm
        x7 = a5 * cosomm
        x8 = a6 * cosomm
        z31 = 12.0 * x1 * x1 - 3.0 * x3 * x3
        z32 = 24.0 * x1 * x2 - 6.0 * x3 * x4
        z33 = 12.0 * x2 * x2 - 3.0 * x4 * x4
        z1 = 3.0 * (a1 * a1 + a2 * a2) + z31 * emsq
        z2 = 6.0 * (a1 * a3 + a2 * a4) + z32 * emsq
        z3 = 3.0 * (a3 * a3 + a4 * a4) + z33 * emsq
        z11 = -6.0 * a1 * a5 + emsq * (-24.0 * x1 * x7 - 6.0 * x3 * x5)
        z12 = (-6.0 * (a1 * a6 + a3 * a5) + emsq
               * (-24.0 * (x2 * x7 + x1 * x8) - 6.0 * (x3 * x6 + x4 * x5)))
        z13 = -6.0 * a3 * a6 + emsq * (-24.0 * x2 * x8 - 6.0 * x4 * x6)
        z21 = 6.0 * a2 * a5 + emsq * (24.0 * x1 * x5 - 6.0 * x3 * x7)
        z22 = (6.0 * (a4 * a5 + a2 * a6) + emsq
               * (24.0 * (x2 * x5 + x1 * x6) - 6.0 * (x4 * x7 + x3 * x8)))
        z23 = 6.0 * a4 * a6 + emsq * (24.0 * x2 * x6 - 6.0 * x4 * x8)
        z1 = z1 + z1 + betasq * z31
        z2 = z2 + z2 + betasq * z32
        z3 = z3 + z3 + betasq * z33
        s3 = cc * xnoi
        s2 = -0.5 * s3 / rtemsq
        s4 = s3 * rtemsq
        s1 = -15.0 * em * s4
        s5 = x1 * x3 + x2 * x4
        s6 = x2 * x3 + x1 * x4
        s7 = x2 * x4 - x1 * x3
        prefix = "" if lunar else "s"
        for name, value in (("1", s1), ("2", s2), ("3", s3), ("4", s4),
                            ("5", s5), ("6", s6), ("7", s7)):
            out[prefix + "s" + name if not lunar else "s" + name] = value
        zname = "z" if lunar else "sz"
        for name, value in (("1", z1), ("2", z2), ("3", z3), ("11", z11),
                            ("12", z12), ("13", z13), ("21", z21),
                            ("22", z22), ("23", z23), ("31", z31),
                            ("32", z32), ("33", z33)):
            out[zname + name] = value
        if not lunar:
            zcosg, zsing, zcosi, zsini = zcosgl, zsingl, zcosil, zsinil
            zcosh = zcoshl * cnodm + zsinhl * snodm
            zsinh = snodm * zcoshl - cnodm * zsinhl
            cc = c1l
    o = out
    out.update(
        zmol=(4.7199672 + 0.22997150 * day - gam) % TWOPI,
        zmos=(6.2565837 + 0.017201977 * day) % TWOPI,
        se2=2.0 * o["ss1"] * o["ss6"], se3=2.0 * o["ss1"] * o["ss7"],
        si2=2.0 * o["ss2"] * o["sz12"],
        si3=2.0 * o["ss2"] * (o["sz13"] - o["sz11"]),
        sl2=-2.0 * o["ss3"] * o["sz2"],
        sl3=-2.0 * o["ss3"] * (o["sz3"] - o["sz1"]),
        sl4=-2.0 * o["ss3"] * (-21.0 - 9.0 * emsq) * ZES,
        sgh2=2.0 * o["ss4"] * o["sz32"],
        sgh3=2.0 * o["ss4"] * (o["sz33"] - o["sz31"]),
        sgh4=-18.0 * o["ss4"] * ZES,
        sh2=-2.0 * o["ss2"] * o["sz22"],
        sh3=-2.0 * o["ss2"] * (o["sz23"] - o["sz21"]),
        ee2=2.0 * o["s1"] * o["s6"], e3=2.0 * o["s1"] * o["s7"],
        xi2=2.0 * o["s2"] * o["z12"],
        xi3=2.0 * o["s2"] * (o["z13"] - o["z11"]),
        xl2=-2.0 * o["s3"] * o["z2"],
        xl3=-2.0 * o["s3"] * (o["z3"] - o["z1"]),
        xl4=-2.0 * o["s3"] * (-21.0 - 9.0 * emsq) * ZEL,
        xgh2=2.0 * o["s4"] * o["z32"],
        xgh3=2.0 * o["s4"] * (o["z33"] - o["z31"]),
        xgh4=-18.0 * o["s4"] * ZEL,
        xh2=-2.0 * o["s2"] * o["z22"],
        xh3=-2.0 * o["s2"] * (o["z23"] - o["z21"]),
        emsq=emsq, sinim=sinim, cosim=cosim, nm=nm, em=em)
    return out


def _dsinit(s, c, eccsq, xpidot):
    """Вековые члены Луны и Солнца и резонансы суточных и полусуточных
    орбит, поля пишутся в s."""
    q22 = 1.7891679e-6
    q31 = 2.1460748e-6
    q33 = 2.2123015e-7
    root22 = 1.7891679e-6
    root44 = 7.3636953e-9
    root54 = 2.1765803e-9
    root32 = 3.7393792e-7
    root52 = 1.1428639e-7
    nm, em, emsq = c["nm"], c["em"], c["emsq"]
    sinim, cosim = c["sinim"], c["cosim"]
    inclm = s["inclo"]
    irez = 0
    if 0.0034906585 < nm < 0.0052359877:
        irez = 1
    if 8.26e-3 <= nm <= 9.24e-3 and em >= 0.5:
        irez = 2
    s["irez"] = float(irez)

    ses = c["ss1"] * ZNS * c["ss5"]
    sis = c["ss2"] * ZNS * (c["sz11"] + c["sz13"])
    sls = -ZNS * c["ss3"] * (c["sz1"] + c["sz3"] - 14.0 - 6.0 * emsq)
    sghs = c["ss4"] * ZNS * (c["sz31"] + c["sz33"] - 6.0)
    shs = -ZNS * c["ss2"] * (c["sz21"] + c["sz23"])
    flat = inclm < 5.2359877e-2 or inclm > math.pi - 5.2359877e-2
    if flat:
        shs = 0.0
    if sinim != 0.0:
        shs = shs / sinim
    sgs = sghs - cosim * shs
    s["dedt"] = ses + c["s1"] * ZNL * c["s5"]
    s["didt"] = sis + c["s2"] * ZNL * (c["z11"] + c["z13"])
    s["dmdt"] = sls - ZNL * c["s3"] * (c["z1"] + c["z3"] - 14.0
                                       - 6.0 * emsq)
    sghl = c["s4"] * ZNL * (c["z31"] + c["z33"] - 6.0)
    shll = -ZNL * c["s2"] * (c["z21"] + c["z23"])
    if flat:
        shll = 0.0
    domdt = sgs + sghl
    dnodt = shs
    if sinim != 0.0:
        domdt = domdt - cosim / sinim * shll
        dnodt = dnodt + shll / sinim
    s["domdt"] = domdt
    s["dnodt"] = dnodt
    if irez == 0:
        return
    theta = s["gsto"] % TWOPI
    aonv = (nm / XKE) ** X2O3
    mo, nodeo, argpo, no = s["mo"], s["nodeo"], s["argpo"], s["no"]
    if irez == 2:
        cosisq = cosim * cosim
        em = s["ecco"]
        emsq = eccsq
        eoc = em * emsq
        g201 = -0.306 - (em - 0.64) * 0.440
        if em <= 0.65:
            g211 = 3.616 - 13.2470 * em + 16.2900 * emsq
            g310 = (-19.302 + 117.3900 * em - 228.4190 * emsq
                    + 156.5910 * eoc)
            g322 = (-18.9068 + 109.7927 * em - 214.6334 * emsq
                    + 146.5816 * eoc)
            g410 = (-41.122 + 242.6940 * em - 471.0940 * emsq
                    + 313.9530 * eoc)
            g422 = (-146.407 + 841.8800 * em - 1629.014 * emsq
                    + 1083.4350 * eoc)
            g520 = (-532.114 + 3017.977 * em - 5740.032 * emsq
                    + 3708.2760 * eoc)
        else:
            g211 = -72.099 + 331.819 * em - 508.738 * emsq + 266.724 * eoc
            g310 = (-346.844 + 1582.851 * em - 2415.925 * emsq
                    + 1246.113 * eoc)
            g322 = (-342.585 + 1554.908 * em - 2366.899 * emsq
                    + 1215.972 * eoc)
            g410 = (-1052.797 + 4758.686 * em - 7193.992 * emsq
                    + 3651.957 * eoc)
            g422 = (-3581.690 + 16178.110 * em - 24462.770 * emsq
                    + 12422.520 * eoc)
            if em > 0.715:
                g520 = (-5149.66 + 29936.92 * em - 54087.36 * emsq
                        + 31324.56 * eoc)
            else:
                g520 = 1464.74 - 4664.75 * em + 3763.64 * emsq
        if em < 0.7:
            g533 = (-919.22770 + 4988.6100 * em - 9064.7700 * emsq
                    + 5542.21 * eoc)
            g521 = (-822.71072 + 4568.6173 * em - 8491.4146 * emsq
                    + 5337.524 * eoc)
            g532 = (-853.66600 + 4690.2500 * em - 8624.7700 * emsq
                    + 5341.4 * eoc)
        else:
            g533 = (-37995.780 + 161616.52 * em - 229838.20 * emsq
                    + 109377.94 * eoc)
            g521 = (-51752.104 + 218913.95 * em - 309468.16 * emsq
                    + 146349.42 * eoc)
            g532 = (-40023.880 + 170470.89 * em - 242699.48 * emsq
                    + 115605.82 * eoc)
        sini2 = sinim * sinim
        f220 = 0.75 * (1.0 + 2.0 * cosim + cosisq)
        f221 = 1.5 * sini2
        f321 = 1.875 * sinim * (1.0 - 2.0 * cosim - 3.0 * cosisq)
        f322 = -1.875 * sinim * (1.0 + 2.0 * cosim - 3.0 * cosisq)
        f441 = 35.0 * sini2 * f220
        f442 = 39.3750 * sini2 * sini2
        f522 = 9.84375 * sinim * (
            sini2 * (1.0 - 2.0 * cosim - 5.0 * cosisq)
            + 0.33333333 * (-2.0 + 4.0 * cosim + 6.0 * cosisq))
        f523 = sinim * (
            4.92187512 * sini2 * (-2.0 - 4.0 * cosim + 10.0 * cosisq)
            + 6.56250012 * (1.0 + 2.0 * cosim - 3.0 * cosisq))
        f542 = 29.53125 * sinim * (
            2.0 - 8.0 * cosim + cosisq * (-12.0 + 8.0 * cosim
                                          + 10.0 * cosisq))
        f543 = 29.53125 * sinim * (
            -2.0 - 8.0 * cosim + cosisq * (12.0 + 8.0 * cosim
                                           - 10.0 * cosisq))
        xno2 = nm * nm
        ainv2 = aonv * aonv
        temp1 = 3.0 * xno2 * ainv2
        temp = temp1 * root22
        s["d2201"] = temp * f220 * g201
        s["d2211"] = temp * f221 * g211
        temp1 = temp1 * aonv
        temp = temp1 * root32
        s["d3210"] = temp * f321 * g310
        s["d3222"] = temp * f322 * g322
        temp1 = temp1 * aonv
        temp = 2.0 * temp1 * root44
        s["d4410"] = temp * f441 * g410
        s["d4422"] = temp * f442 * g422
        temp1 = temp1 * aonv
        temp = temp1 * root52
        s["d5220"] = temp * f522 * g520
        s["d5232"] = temp * f523 * g532
        temp = 2.0 * temp1 * root54
        s["d5421"] = temp * f542 * g521
        s["d5433"] = temp * f543 * g533
        s["xlamo"] = (mo + nodeo + nodeo - theta - theta) % TWOPI
        s["xfact"] = (s["mdot"] + s["dmdt"]
                      + 2.0 * (s["nodedot"] + s["dnodt"] - RPTIM) - no)
    else:
        g200 = 1.0 + emsq * (-2.5 + 0.8125 * emsq)
        g310 = 1.0 + 2.0 * emsq
        g300 = 1.0 + emsq * (-6.0 + 6.60937 * emsq)
        f220 = 0.75 * (1.0 + cosim) * (1.0 + cosim)
        f311 = (0.9375 * sinim * sinim * (1.0 + 3.0 * cosim)
                - 0.75 * (1.0 + cosim))
        f330 = 1.875 * (1.0 + cosim) ** 3
        del1 = 3.0 * nm * nm * aonv * aonv
        s["del2"] = 2.0 * del1 * f220 * g200 * q22
        s["del3"] = 3.0 * del1 * f330 * g300 * q33 * aonv
        s["del1"] = del1 * f311 * g310 * q31 * aonv
        s["xlamo"] = (mo + nodeo + argpo - theta) % TWOPI
        s["xfact"] = (s["mdot"] + xpidot - RPTIM + s["dmdt"] + s["domdt"]
                      + s["dnodt"] - no)


# Положения на момент сразу для всех спутников.

class Orbits:
    """Начальные величины спутников массивами и расчёт положений."""

    def __init__(self, elements):
        self.elements = elements
        count = len(elements)
        self.f = {key: np.zeros(count) for key in FIELDS}
        self._done = 0
        self.ready = count == 0

    def init_some(self, budget=None):
        """Посчитать начальные величины следующих спутников. budget -
        количество спутников за вызов, None - все. Возвращает True,
        когда посчитаны все."""
        e = self.elements
        count = len(e)
        stop = count if budget is None else min(count, self._done + budget)
        for i in range(self._done, stop):
            values = _init_one(float(e.epoch[i]), float(e.bstar[i]),
                               float(e.ecco[i]), float(e.argpo[i]),
                               float(e.inclo[i]), float(e.mo[i]),
                               float(e.no[i]), float(e.nodeo[i]))
            for key, value in values.items():
                self.f[key][i] = value
        self._done = stop
        self.ready = stop >= count
        return self.ready

    def at(self, jd):
        """Положения и скорости в TEME на юлианскую дату jd: (r км,
        v км/с, коды ошибок). r и v - массивы N×3."""
        if not self.ready:
            self.init_some()
        if self._cache is None:
            self._cache = Cache(self.f)
        tsince = (jd - JD_EPOCH0 - self.f["epoch"]) * 1440.0
        return propagate(self.f, tsince, self._cache)

    _cache = None


class Cache:
    """Подмножества глубоких и резонансных спутников и состояние
    интегратора резонансов между вызовами. Как в исходном коде на C++,
    следующий момент продолжает счёт с последнего шага, если он дальше
    от эпохи в ту же сторону. Иначе счёт идёт от эпохи. Шаги одни
    и те же, поэтому результат от запоминания не зависит."""

    def __init__(self, f):
        self.deep = np.flatnonzero(f["deep"])
        self.sub = {key: value[self.deep] for key, value in f.items()}
        res = np.flatnonzero(self.sub["irez"])
        self.res = res
        self.res_sub = {key: value[res] for key, value in self.sub.items()}
        self.atime = np.zeros(res.size)
        self.xli = self.res_sub["xlamo"].copy()
        self.xni = self.res_sub["no"].copy()


def propagate(f, tsince, cache=None):
    """SGP4 для всех спутников f на время tsince минут от эпохи каждого:
    (r, v, error). f - словарь массивов полей FIELDS, cache - Cache
    тех же спутников или None."""
    t = np.asarray(tsince, dtype=float)
    count = t.shape[0]
    if cache is None:
        cache = Cache(f)
    with np.errstate(all="ignore"):
        return _propagate(f, t, count, cache)


def _propagate(f, t, count, cache):
    no = f["no"]
    xmdf = f["mo"] + f["mdot"] * t
    argpdf = f["argpo"] + f["argpdot"] * t
    nodedf = f["nodeo"] + f["nodedot"] * t
    t2 = t * t
    nodem = nodedf + f["nodecf"] * t2
    tempa = 1.0 - f["cc1"] * t
    tempe = f["bstar"] * f["cc4"] * t
    templ = f["t2cof"] * t2
    full = f["isimp"] == 0.0
    delomg = f["omgcof"] * t
    delmtemp = 1.0 + f["eta"] * np.cos(xmdf)
    delm = f["xmcof"] * (delmtemp * delmtemp * delmtemp - f["delmo"])
    temp = delomg + delm
    mm = np.where(full, xmdf + temp, xmdf)
    argpm = np.where(full, argpdf - temp, argpdf)
    t3 = t2 * t
    t4 = t3 * t
    tempa = np.where(full, tempa - f["d2"] * t2 - f["d3"] * t3
                     - f["d4"] * t4, tempa)
    tempe = np.where(full, tempe + f["bstar"] * f["cc5"]
                     * (np.sin(mm) - f["sinmao"]), tempe)
    templ = np.where(full, templ + f["t3cof"] * t3
                     + t4 * (f["t4cof"] + t * f["t5cof"]), templ)
    nm = no.copy()
    em = f["ecco"].copy()
    inclm = f["inclo"].copy()
    deep = cache.deep
    if deep.size:
        (em[deep], argpm[deep], inclm[deep], mm[deep], nodem[deep],
         nm[deep]) = _dspace(cache, t[deep], em[deep], argpm[deep],
                             inclm[deep], mm[deep], nodem[deep])

    error = np.zeros(count, dtype=np.int8)
    bad_n = nm <= 0.0
    am = (XKE / nm) ** X2O3 * tempa * tempa
    nm = XKE / am ** 1.5
    em = em - tempe
    bad_e = (em >= 1.0) | (em < -0.001)
    em = np.where(em < 1.0e-6, 1.0e-6, em)
    mm = mm + no * templ
    xlm = mm + argpm + nodem
    nodem = np.fmod(nodem, TWOPI)
    argpm = np.mod(argpm, TWOPI)
    xlm = np.mod(xlm, TWOPI)
    mm = np.mod(xlm - argpm - nodem, TWOPI)

    ep = em
    xincp = inclm
    argpp = argpm
    nodep = nodem
    mp = mm
    sinip = np.sin(inclm)
    cosip = np.cos(inclm)
    aycof = f["aycof"].copy()
    xlcof = f["xlcof"].copy()
    con41 = f["con41"].copy()
    x1mth2 = f["x1mth2"].copy()
    x7thm1 = f["x7thm1"].copy()
    bad_p = np.zeros(count, dtype=bool)
    if deep.size:
        e, i, n, a, m = _dpper(cache.sub, t[deep], ep[deep], xincp[deep],
                               nodep[deep], argpp[deep], mp[deep])
        negative = i < 0.0
        i = np.where(negative, -i, i)
        n = np.where(negative, n + math.pi, n)
        a = np.where(negative, a - math.pi, a)
        ep = ep.copy()
        xincp = xincp.copy()
        nodep = nodep.copy()
        argpp = argpp.copy()
        mp = mp.copy()
        ep[deep], xincp[deep], nodep[deep] = e, i, n
        argpp[deep], mp[deep] = a, m
        bad_p[deep] = (e < 0.0) | (e > 1.0)
        si = np.sin(i)
        ci = np.cos(i)
        sinip = sinip.copy()
        cosip = cosip.copy()
        sinip[deep], cosip[deep] = si, ci
        aycof[deep] = -0.5 * J3OJ2 * si
        flip = np.abs(ci + 1.0) > 1.5e-12
        xlcof[deep] = (-0.25 * J3OJ2 * si * (3.0 + 5.0 * ci)
                       / np.where(flip, 1.0 + ci, 1.5e-12))
        cosisq = ci * ci
        con41[deep] = 3.0 * cosisq - 1.0
        x1mth2[deep] = 1.0 - cosisq
        x7thm1[deep] = 7.0 * cosisq - 1.0

    axnl = ep * np.cos(argpp)
    temp = 1.0 / (am * (1.0 - ep * ep))
    aynl = ep * np.sin(argpp) + temp * aycof
    xl = mp + argpp + nodep + temp * xlcof * axnl

    # Уравнение Кеплера: не больше 10 шагов, каждый спутник до своей
    # сходимости, как в эталоне.
    u = np.mod(xl - nodep, TWOPI)
    eo1 = u.copy()
    tem5 = np.full(count, 9999.9)
    sineo1 = np.zeros(count)
    coseo1 = np.zeros(count)
    for _ in range(10):
        active = np.abs(tem5) >= 1.0e-12
        if not active.any():
            break
        s = np.sin(eo1)
        c = np.cos(eo1)
        step = (u - aynl * c + axnl * s - eo1) / (1.0 - c * axnl - s * aynl)
        step = np.clip(step, -0.95, 0.95)
        sineo1 = np.where(active, s, sineo1)
        coseo1 = np.where(active, c, coseo1)
        tem5 = np.where(active, step, tem5)
        eo1 = np.where(active, eo1 + step, eo1)

    ecose = axnl * coseo1 + aynl * sineo1
    esine = axnl * sineo1 - aynl * coseo1
    el2 = axnl * axnl + aynl * aynl
    pl = am * (1.0 - el2)
    bad_l = pl < 0.0
    rl = am * (1.0 - ecose)
    rdotl = np.sqrt(am) * esine / rl
    rvdotl = np.sqrt(pl) / rl
    betal = np.sqrt(1.0 - el2)
    temp = esine / (1.0 + betal)
    sinu = am / rl * (sineo1 - aynl - axnl * temp)
    cosu = am / rl * (coseo1 - axnl + aynl * temp)
    su = np.arctan2(sinu, cosu)
    sin2u = (cosu + cosu) * sinu
    cos2u = 1.0 - 2.0 * sinu * sinu
    temp = 1.0 / pl
    temp1 = 0.5 * J2 * temp
    temp2 = temp1 * temp
    mrt = (rl * (1.0 - 1.5 * temp2 * betal * con41)
           + 0.5 * temp1 * x1mth2 * cos2u)
    su = su - 0.25 * temp2 * x7thm1 * sin2u
    xnode = nodep + 1.5 * temp2 * cosip * sin2u
    xinc = xincp + 1.5 * temp2 * cosip * sinip * cos2u
    mvt = rdotl - nm * temp1 * x1mth2 * sin2u / XKE
    rvdot = rvdotl + nm * temp1 * (x1mth2 * cos2u + 1.5 * con41) / XKE
    sinsu = np.sin(su)
    cossu = np.cos(su)
    snod = np.sin(xnode)
    cnod = np.cos(xnode)
    sini = np.sin(xinc)
    cosi = np.cos(xinc)
    xmx = -snod * cosi
    xmy = cnod * cosi
    ux = xmx * sinsu + cnod * cossu
    uy = xmy * sinsu + snod * cossu
    uz = sini * sinsu
    vx = xmx * cossu - cnod * sinsu
    vy = xmy * cossu - snod * sinsu
    vz = sini * cossu
    mr = mrt * RADIUS
    r = np.stack([mr * ux, mr * uy, mr * uz], axis=1)
    v = np.stack([(mvt * ux + rvdot * vx) * VKMPERSEC,
                  (mvt * uy + rvdot * vy) * VKMPERSEC,
                  (mvt * uz + rvdot * vz) * VKMPERSEC], axis=1)

    # Коды ошибок в порядке проверки эталона: первая найденная главнее.
    error[mrt < 1.0] = 6
    error[bad_l] = 4
    error[bad_p] = 3
    error[bad_e] = 1
    error[bad_n] = 2
    lost = (error > 0) & (error < 6)
    r[lost] = np.nan
    v[lost] = np.nan
    return r, v, error


def _dpper(s, t, ep, inclp, nodep, argpp, mp):
    """Долгопериодические члены Луны и Солнца на время t."""
    zm = s["zmos"] + ZNS * t
    zf = zm + 2.0 * ZES * np.sin(zm)
    sinzf = np.sin(zf)
    f2 = 0.5 * sinzf * sinzf - 0.25
    f3 = -0.5 * sinzf * np.cos(zf)
    ses = s["se2"] * f2 + s["se3"] * f3
    sis = s["si2"] * f2 + s["si3"] * f3
    sls = s["sl2"] * f2 + s["sl3"] * f3 + s["sl4"] * sinzf
    sghs = s["sgh2"] * f2 + s["sgh3"] * f3 + s["sgh4"] * sinzf
    shs = s["sh2"] * f2 + s["sh3"] * f3
    zm = s["zmol"] + ZNL * t
    zf = zm + 2.0 * ZEL * np.sin(zm)
    sinzf = np.sin(zf)
    f2 = 0.5 * sinzf * sinzf - 0.25
    f3 = -0.5 * sinzf * np.cos(zf)
    sel = s["ee2"] * f2 + s["e3"] * f3
    sil = s["xi2"] * f2 + s["xi3"] * f3
    sll = s["xl2"] * f2 + s["xl3"] * f3 + s["xl4"] * sinzf
    sghl = s["xgh2"] * f2 + s["xgh3"] * f3 + s["xgh4"] * sinzf
    shll = s["xh2"] * f2 + s["xh3"] * f3
    pe = ses + sel - s["peo"]
    pinc = sis + sil - s["pinco"]
    pl = sls + sll - s["plo"]
    pgh = sghs + sghl - s["pgho"]
    ph = shs + shll - s["pho"]
    inclp = inclp + pinc
    ep = ep + pe
    sinip = np.sin(inclp)
    cosip = np.cos(inclp)

    # Наклон от 0.2 рад - члены напрямую, иначе поправка Лиддейна.
    high = inclp >= 0.2
    ph_h = ph / sinip
    argp_h = argpp + pgh - cosip * ph_h
    node_h = nodep + ph_h
    m_h = mp + pl

    sinop = np.sin(nodep)
    cosop = np.cos(nodep)
    alfdp = sinip * sinop + ph * cosop + pinc * cosip * sinop
    betdp = sinip * cosop - ph * sinop + pinc * cosip * cosop
    node_l = np.fmod(nodep, TWOPI)
    xls = mp + argpp + pl + pgh + (cosip - pinc * sinip) * node_l
    xnoh = node_l
    node_l = np.arctan2(alfdp, betdp)
    far = np.abs(xnoh - node_l) > math.pi
    node_l = np.where(far & (node_l < xnoh), node_l + TWOPI,
                      np.where(far, node_l - TWOPI, node_l))
    m_l = mp + pl
    argp_l = xls - m_l - cosip * node_l
    return (ep, inclp, np.where(high, node_h, node_l),
            np.where(high, argp_h, argp_l), np.where(high, m_h, m_l))


def _dspace(cache, t, em, argpm, inclm, mm, nodem):
    """Вековые члены Луны и Солнца и резонансы на время t:
    (em, argpm, inclm, mm, nodem, nm). Состояние интегратора
    резонансов берётся из cache и пишется туда же."""
    s = cache.sub
    fasx2 = 0.13130908
    fasx4 = 2.8843198
    fasx6 = 0.37448087
    g22 = 5.7686396
    g32 = 0.95240898
    g44 = 1.8014998
    g52 = 1.0508330
    g54 = 4.4108898
    no = s["no"]
    theta = np.mod(s["gsto"] + t * RPTIM, TWOPI)
    em = em + s["dedt"] * t
    inclm = inclm + s["didt"] * t
    argpm = argpm + s["domdt"] * t
    nodem = nodem + s["dnodt"] * t
    mm = mm + s["dmdt"] * t
    nm = no.copy()
    res = cache.res
    if not res.size:
        return em, argpm, inclm, mm, nodem, nm
    r = cache.res_sub
    tr = t[res]
    irez = r["irez"]
    half = irez == 2.0
    # Счёт от эпохи, если запомненный шаг по другую сторону от эпохи
    # или дальше от неё, чем новый момент.
    atime = cache.atime
    restart = (atime == 0.0) | (tr * atime <= 0.0) \
        | (np.abs(tr) < np.abs(atime))
    atime = np.where(restart, 0.0, atime)
    xni = np.where(restart, r["no"], cache.xni)
    xli = np.where(restart, r["xlamo"], cache.xli)
    delt = np.where(tr > 0.0, STEP, -STEP)
    done = np.zeros(res.size, dtype=bool)
    ft = np.zeros(res.size)
    xndt_f = np.zeros(res.size)
    xldot_f = np.zeros(res.size)
    xnddt_f = np.zeros(res.size)
    while not done.all():
        # Члены суточного резонанса.
        xndt1 = (r["del1"] * np.sin(xli - fasx2)
                 + r["del2"] * np.sin(2.0 * (xli - fasx4))
                 + r["del3"] * np.sin(3.0 * (xli - fasx6)))
        xnddt1 = (r["del1"] * np.cos(xli - fasx2)
                  + 2.0 * r["del2"] * np.cos(2.0 * (xli - fasx4))
                  + 3.0 * r["del3"] * np.cos(3.0 * (xli - fasx6)))
        # Члены полусуточного резонанса.
        xomi = r["argpo"] + r["argpdot"] * atime
        x2omi = xomi + xomi
        x2li = xli + xli
        xndt2 = (r["d2201"] * np.sin(x2omi + xli - g22)
                 + r["d2211"] * np.sin(xli - g22)
                 + r["d3210"] * np.sin(xomi + xli - g32)
                 + r["d3222"] * np.sin(-xomi + xli - g32)
                 + r["d4410"] * np.sin(x2omi + x2li - g44)
                 + r["d4422"] * np.sin(x2li - g44)
                 + r["d5220"] * np.sin(xomi + xli - g52)
                 + r["d5232"] * np.sin(-xomi + xli - g52)
                 + r["d5421"] * np.sin(xomi + x2li - g54)
                 + r["d5433"] * np.sin(-xomi + x2li - g54))
        xnddt2 = (r["d2201"] * np.cos(x2omi + xli - g22)
                  + r["d2211"] * np.cos(xli - g22)
                  + r["d3210"] * np.cos(xomi + xli - g32)
                  + r["d3222"] * np.cos(-xomi + xli - g32)
                  + r["d5220"] * np.cos(xomi + xli - g52)
                  + r["d5232"] * np.cos(-xomi + xli - g52)
                  + 2.0 * (r["d4410"] * np.cos(x2omi + x2li - g44)
                           + r["d4422"] * np.cos(x2li - g44)
                           + r["d5421"] * np.cos(xomi + x2li - g54)
                           + r["d5433"] * np.cos(-xomi + x2li - g54)))
        xndt = np.where(half, xndt2, xndt1)
        xldot = xni + r["xfact"]
        xnddt = np.where(half, xnddt2, xnddt1) * xldot
        stepping = ~done & (np.abs(tr - atime) >= STEP)
        finished = ~done & ~stepping
        ft = np.where(finished, tr - atime, ft)
        xndt_f = np.where(finished, xndt, xndt_f)
        xldot_f = np.where(finished, xldot, xldot_f)
        xnddt_f = np.where(finished, xnddt, xnddt_f)
        done = done | finished
        xli = np.where(stepping, xli + xldot * delt + xndt * STEP2, xli)
        xni = np.where(stepping, xni + xndt * delt + xnddt * STEP2, xni)
        atime = np.where(stepping, atime + delt, atime)
    cache.atime, cache.xli, cache.xni = atime, xli, xni
    nm_r = xni + xndt_f * ft + xnddt_f * ft * ft * 0.5
    xl = xli + xldot_f * ft + xndt_f * ft * ft * 0.5
    th = theta[res]
    mm_r = np.where(irez != 1.0, xl - 2.0 * nodem[res] + 2.0 * th,
                    xl - nodem[res] - argpm[res] + th)
    mm = mm.copy()
    mm[res] = mm_r
    nm[res] = nm_r
    return em, argpm, inclm, mm, nodem, nm


def teme_to_ecef(r, jd):
    """Положения TEME в систему, связанную с Землёй, поворотом на
    звёздное время Гринвича. r - массив N×3 или вектор, jd - число."""
    g = float(gstime(jd))
    c, s = math.cos(g), math.sin(g)
    r = np.asarray(r, dtype=float)
    out = np.empty_like(r)
    out[..., 0] = c * r[..., 0] + s * r[..., 1]
    out[..., 1] = -s * r[..., 0] + c * r[..., 1]
    out[..., 2] = r[..., 2]
    return out


def unix_jd(seconds):
    """Юлианская дата по секундам UTC от 1970 года."""
    return JD_1970 + seconds / 86400.0
