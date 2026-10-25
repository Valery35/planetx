# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
# Перенесено из Isoliner, grid_isolines/topo_flow.py.
# Там - GPL-2.0-or-later, владелец тот же.
"""Гидрология рельефа на чистом NumPy: направления стока D8
(Jenson-Domingue 1988), аккумуляция векторизованным обходом Кана,
трассировка речной сети с порядком Стралера, бассейны через
прыжки указателей (pointer doubling).

Соглашения. Ось строк направлена на юг (стандартный GeoTIFF с
отрицательным шагом по Y): строка 0 северная. Коды направлений ESRI:
E=1, SE=2, S=4, SW=8, W=16, NW=32, N=64, NE=128, сток (яма или выход
с грида) = 0. Вход - ЦМР после заполнения понижений с epsilon больше
нуля: на плоскостях без уклона D8 не определён.
"""

import numpy as np

# (dr, dc, esri, dist)
_D8 = (
    (0, 1, 1, 1.0),
    (1, 1, 2, 2.0 ** 0.5),
    (1, 0, 4, 1.0),
    (1, -1, 8, 2.0 ** 0.5),
    (0, -1, 16, 1.0),
    (-1, -1, 32, 2.0 ** 0.5),
    (-1, 0, 64, 1.0),
    (-1, 1, 128, 2.0 ** 0.5),
)

ESRI_CODES = tuple(d[2] for d in _D8)
NODIR = -1  # внутренний индекс: сток


def _shift(a, dr, dc, fill):
    """Сдвиг массива: значение соседа (r+dr, c+dc) в ячейке (r, c)."""
    out = np.full_like(a, fill)
    _shift_into(a, dr, dc, fill, out)
    return out


def _shift_into(a, dr, dc, fill, out):
    """Тот же сдвиг в готовый буфер: без аллокации на каждый вызов."""
    out.fill(fill)
    src_r = slice(max(dr, 0), a.shape[0] + min(dr, 0))
    dst_r = slice(max(-dr, 0), a.shape[0] + min(-dr, 0))
    src_c = slice(max(dc, 0), a.shape[1] + min(dc, 0))
    dst_c = slice(max(-dc, 0), a.shape[1] + min(-dc, 0))
    out[dst_r, dst_c] = a[src_r, src_c]


def d8_directions(z, nodata_mask=None):
    """Направления стока D8.

    Возвращает (dir_idx, downstream):
    dir_idx int8 (ny, nx): индекс направления 0..7 в _D8, NODIR у стока
    (нет соседа ниже, выход с грида или в nodata) и в nodata-ячейках.
    downstream int64 (ny*nx,): плоский индекс приёмника, -1 у стока.

    Сосед nodata (море, вырез) считается бесконечно низким: береговая
    ячейка льёт в него. Заграничье, наоборот, недостижимо: ячейка на
    рамке уходит с грида только если у неё нет более низкого соседа
    внутри, иначе поток вдоль рамки рвался бы. Из двух равных уклонов
    берётся первый по списку _D8 (детерминизм).
    """
    z = np.asarray(z, dtype=np.float64)
    ny, nx = z.shape
    if nodata_mask is None:
        nodata_mask = ~np.isfinite(z)

    best_slope = np.full(z.shape, 0.0)
    dir_idx = np.full(z.shape, NODIR, dtype=np.int8)
    # Буферы заводятся один раз на все восемь направлений: раньше
    # каждое направление рождало пять временных массивов размером с
    # грид, и на сорока мегапикселях аллокации стоили дороже самой
    # арифметики. Значения не меняются, меняется только адресат записи.
    nb = np.empty(z.shape)
    nb_nd = np.empty(z.shape, dtype=bool)
    better = np.empty(z.shape, dtype=bool)
    for k, (dr, dc, _esri, dist) in enumerate(_D8):
        _shift_into(z, dr, dc, np.inf, nb)           # заграничье: стенка
        _shift_into(nodata_mask, dr, dc, False, nb_nd)
        nb[nb_nd] = -np.inf                          # nodata-сосед: слив
        np.subtract(z, nb, out=nb)                   # nb становится уклоном
        nb /= dist
        np.greater(nb, best_slope, out=better)
        dir_idx[better] = k
        np.copyto(best_slope, nb, where=better)
    dir_idx[nodata_mask] = NODIR

    downstream = np.full(ny * nx, -1, dtype=np.int64)
    dflat = dir_idx.ravel()
    has_nodata = bool(nodata_mask.any())
    nd = nodata_mask.ravel() if has_nodata else None
    # Строка и столбец считаются только для ячеек текущего направления,
    # а не для всего грида восемь раз подряд.
    for k, (dr, dc, _esri, _dist) in enumerate(_D8):
        idx = np.flatnonzero(dflat == k)
        if idx.size == 0:
            continue
        rr, cc = np.divmod(idx, nx)
        rr += dr
        cc += dc
        ok = (rr >= 0) & (rr < ny) & (cc >= 0) & (cc < nx)
        tgt = np.where(ok, rr * nx + cc, -1)
        # приёмник в nodata равносилен выходу с грида
        if has_nodata:
            inside = tgt >= 0
            tgt[inside & nd[np.maximum(tgt, 0)]] = -1
        downstream[idx] = tgt
    return dir_idx, downstream


def dir_to_esri(dir_idx):
    """Индексы 0..7 в коды ESRI, сток и nodata в 0."""
    esri = np.zeros(dir_idx.shape, dtype=np.uint8)
    for k, (_dr, _dc, code, _dist) in enumerate(_D8):
        esri[dir_idx == k] = code
    return esri


def flow_accumulation(downstream, shape, nodata_mask=None):
    """Аккумуляция: число ячеек, стекающих в ячейку, включая её саму.

    Векторизованный обход Кана: считаем входящие степени, двигаем
    фронт готовых ячеек, передаём их суммы приёмникам через np.add.at.
    Работает и на конфигурациях с равными высотами: важен только сам
    граф downstream (без циклов, что гарантирует заполнение с epsilon).
    """
    n = shape[0] * shape[1]
    acc = np.ones(n, dtype=np.float64)
    if nodata_mask is not None:
        acc[nodata_mask.ravel()] = 0.0
    indeg = np.zeros(n, dtype=np.int64)
    valid = downstream >= 0
    indeg += np.bincount(downstream[valid], minlength=n)

    frontier = np.flatnonzero((indeg == 0))
    if nodata_mask is not None:
        frontier = frontier[~nodata_mask.ravel()[frontier]]
    # Порог переключения. На широком фронте суммы передаются через
    # bincount: он на порядок быстрее небуферизованного np.add.at, а
    # цена полноразмерного результата тонет в объёме работы. На узком
    # фронте наоборот: полный массив на горстку ячеек не окупается, и
    # точечный np.add.at с np.unique дешевле. Итог тот же с точностью
    # до бита: суммируются целые счётчики, порядок сложения не важен.
    wide = max(1024, n // 32)
    while frontier.size:
        ds = downstream[frontier]
        has_ds = ds >= 0
        ds = ds[has_ds]
        if ds.size >= wide:
            acc += np.bincount(ds, weights=acc[frontier[has_ds]],
                               minlength=n)
            got = np.bincount(ds, minlength=n)
            indeg -= got
            cand = np.flatnonzero(got)
            frontier = cand[indeg[cand] == 0]
        else:
            np.add.at(acc, ds, acc[frontier[has_ds]])
            np.add.at(indeg, ds, -1)
            cand = np.unique(ds)
            frontier = cand[indeg[cand] == 0]
    return acc.reshape(shape)


def _in_degree_masked(downstream, mask_flat):
    """Входящая степень внутри маски: сколько ячеек маски стекают сюда."""
    indeg = np.zeros(mask_flat.size, dtype=np.int32)
    src = np.flatnonzero(mask_flat)
    ds = downstream[src]
    ok = (ds >= 0)
    ds = ds[ok]
    ds = ds[mask_flat[ds]]
    np.add.at(indeg, ds, 1)
    return indeg


def river_network(downstream, acc, threshold, shape):
    """Речная сеть по порогу аккумуляции.

    Возвращает список звеньев: dict(cells=[плоские индексы вниз по
    течению], order=Стралер, acc_out=аккумуляция в замыкании звена).
    Звено идёт от истока или узла слияния до следующего слияния или
    до выхода из сети. Направление вершин - вниз по течению.
    """
    n = shape[0] * shape[1]
    mask = (acc.ravel() >= float(threshold))
    accf = acc.ravel()

    # Ячейки сети делятся на старты (исток indeg=0 или слияние indeg>=2)
    # и внутренние (indeg=1). У внутренней ровно один сетевой исток,
    # поэтому цепочки собираются без обхода: указатель prev на исток,
    # прыжками указателей каждой ячейке находится её старт и номер в
    # цепочке, а сортировка по паре (старт, номер) выкладывает звенья
    # подряд. Обход по одной ячейке на шаг делал то же самое в цикле
    # Python и на миллионе сетевых ячеек стоил секунды. Вся арифметика
    # идёт в локальной нумерации сетевых ячеек: полноразмерный там
    # только словарь перевода nid.
    nodes = np.flatnonzero(mask)
    m = nodes.size
    if m == 0:
        return []
    nid = np.full(n, -1, dtype=np.int64)
    nid[nodes] = np.arange(m)

    ds_all = downstream[nodes]
    src_ok = np.flatnonzero((ds_all >= 0) & mask[np.maximum(ds_all, 0)])
    tgt_local = nid[ds_all[src_ok]]
    deg = np.bincount(tgt_local, minlength=m)    # входящая степень в сети

    p = np.arange(m, dtype=np.int64)             # старты держат сами себя
    tin = deg[tgt_local] == 1                    # prev есть лишь у внутренних
    p[tgt_local[tin]] = src_ok[tin]

    # Прыжки указателей: root уходит к старту, dist копит номер в цепочке.
    root = p.copy()
    dist = (root != np.arange(m)).astype(np.int64)
    for _ in range(64):                          # 2**64 ячеек хватит всем
        rr = root[root]
        if np.array_equal(rr, root):
            break
        dist += dist[root]
        root = rr

    # порядок звеньев прежний: истоки по возрастанию, затем слияния
    loc_heads = np.flatnonzero(deg == 0)
    loc_juncs = np.flatnonzero(deg >= 2)
    srank = np.full(m, -1, dtype=np.int64)
    srank[loc_heads] = np.arange(loc_heads.size)
    srank[loc_juncs] = loc_heads.size + np.arange(loc_juncs.size)

    key1 = srank[root]
    order_idx = np.lexsort((dist, key1))
    key1 = key1[order_idx]
    glob = nodes[order_idx]
    # ячейка вне какой-либо цепочки (замкнутый круг без старта) у обхода
    # не посещалась, здесь она отбрасывается тем же исходом
    ok = key1 >= 0
    key1 = key1[ok]
    glob = glob[ok]
    bounds = np.flatnonzero(np.diff(key1)) + 1
    seg_starts = np.concatenate(([0], bounds))
    seg_ends = np.concatenate((bounds, [key1.size]))

    links = []
    for a, b in zip(seg_starts, seg_ends):
        cells = glob[a:b].tolist()
        d = int(downstream[cells[-1]])
        if d >= 0 and mask[d]:
            cells.append(d)                      # замыкающее слияние
        if len(cells) < 2:
            # исток, сразу упирающийся в край: точка не звено
            continue
        links.append({"cells": cells, "order": 0,
                      "acc_out": float(accf[cells[-1]])})

    # Стралер: вливающиеся звенья каждого узла
    inflows = {}
    for li, lk in enumerate(links):
        end = lk["cells"][-1]
        inflows.setdefault(end, []).append(li)

    # Порядок считается явным стеком, а не рекурсией: цепочка звеньев
    # длиной в тысячи узлов упиралась бы в предел глубины интерпретатора.
    state = [0] * len(links)                     # 0 нов, 1 в работе, 2 готов
    for root_li in range(len(links)):
        if state[root_li] == 2:
            continue
        stack = [root_li]
        while stack:
            cur = stack[-1]
            if state[cur] == 2:
                stack.pop()
                continue
            lk = links[cur]
            start = lk["cells"][0]
            ups = inflows.get(start, []) if deg[nid[start]] >= 2 else []
            if state[cur] == 0:
                state[cur] = 1
                todo = [u for u in ups if state[u] == 0]
                if todo:
                    stack.extend(todo)
                    continue
            # звено в работе среди притоков означало бы круг: как и
            # прежняя защита по глубине, такой приток идёт за порядок 1
            vals = [links[u]["order"] if state[u] == 2 else 1 for u in ups]
            if not vals:
                lk["order"] = 1
            else:
                top = max(vals)
                lk["order"] = top + 1 if vals.count(top) >= 2 else top
            state[cur] = 2
            stack.pop()
    return links


def basins(downstream, shape, seeds=None, nodata_mask=None,
           acc=None, threshold=None):
    """Бассейны: метка каждой ячейки по её конечному стоку.

    seeds: dict {плоский индекс: метка > 0} - точки замыкания
    (ячейка-семя рвёт путь: всё, что стекает через неё, получает её
    метку). Без seeds метятся устья: ячейки, чей сток уходит с грида,
    а при заданных acc и threshold - только устья с аккумуляцией не
    ниже порога (остальное получает 0).

    Прыжки указателей: log(L) векторных проходов вместо обхода.
    """
    n = shape[0] * shape[1]
    down = downstream.copy()
    label = np.zeros(n, dtype=np.int32)

    if seeds:
        for idx, lab in seeds.items():
            label[idx] = lab
            down[idx] = -1  # семя терминально
    else:
        outlets = np.flatnonzero(down < 0)
        if nodata_mask is not None:
            outlets = outlets[~nodata_mask.ravel()[outlets]]
        if acc is not None and threshold is not None:
            outlets = outlets[acc.ravel()[outlets] >= float(threshold)]
        label[outlets] = np.arange(1, outlets.size + 1, dtype=np.int32)

    # терминалы указывают сами на себя
    term = down < 0
    ptr = np.where(term, np.arange(n, dtype=np.int64), down)
    for _ in range(64):  # 2**64 ячеек хватит всем
        nxt = ptr[ptr]
        if np.array_equal(nxt, ptr):
            break
        ptr = nxt
    out = label[ptr]
    if nodata_mask is not None:
        out[nodata_mask.ravel()] = 0
    return out.reshape(shape)


# --- линии стока: ход вниз по D8 от заданных ячеек ---------------------------

def trace_downhill(downstream, starts, shape, stop=None, seen=None,
                   max_steps=None):
    """Ход вниз по течению от каждой стартовой ячейки.

    Возвращает список списков плоских индексов, от старта и вниз. Путь
    обрывается в четырёх случаях, и каждый из них естественный: сток
    (ниже некуда), выход за край листа, приход в ячейку из `stop`
    (водоём или водоток, куда трасса вливается) и попадание в уже
    пройденную ячейку, когда передан `seen`.

    `seen` это множество или булев массив на всю решётку: с ним трассы
    сливаются в дерево, и каждая ячейка проходится один раз. Без него
    каждая линия идёт целиком от своего старта, и по общему руслу пройдёт
    столько линий, сколько ячеек выше по склону. На отвале в тысячу
    ячеек это тысяча копий одного русла.

    Зацикливание у D8 после заполнения впадин невозможно, но `max_steps`
    всё равно ограничивает ход: указатели приходят и от чужих
    инструментов.
    """
    n = int(shape[0]) * int(shape[1])
    limit = int(max_steps) if max_steps else n + 1
    stop_set = stop
    if stop is not None and not isinstance(stop, (set, frozenset)):
        stop_set = set(int(i) for i in np.flatnonzero(
            np.asarray(stop).ravel()))
    if seen is not None and not isinstance(seen, (set, frozenset)):
        seen = set(int(i) for i in np.flatnonzero(np.asarray(seen).ravel()))
    out = []
    for s0 in starts:
        cur = int(s0)
        if cur < 0 or cur >= n:
            out.append([])
            continue
        path = [cur]
        local = {cur}
        while len(path) < limit:
            if seen is not None and cur in seen and cur != int(s0):
                break
            if stop_set is not None and cur in stop_set and cur != int(s0):
                break
            nxt = int(downstream[cur])
            if nxt < 0 or nxt >= n:
                break                      # сток или выход за край листа
            if nxt in local:
                break                      # петля: грид пришёл не от нас
            path.append(nxt)
            local.add(nxt)
            cur = nxt
            if stop_set is not None and cur in stop_set:
                break
            if seen is not None and cur in seen:
                break
        if seen is not None:
            seen.update(path)
        out.append(path)
    return out


def path_metrics(path, z, shape, cell_x, cell_y=None):
    """Длина, перепад и средний уклон трассы.

    Длина считается по осям ячейки, поэтому годится и для растра с
    неквадратной ячейкой. Перепад берётся от старта к концу: у трассы
    вниз по склону он не бывает отрицательным, и отрицательное значение
    означает, что грид не заполнен и трасса вышла из впадины вверх.
    """
    nx = int(shape[1])
    cy = float(cell_x if cell_y is None else cell_y)
    cx = float(cell_x)
    zf = np.asarray(z, dtype=np.float64).ravel()
    if len(path) < 2:
        z0 = float(zf[path[0]]) if path else float("nan")
        return {"length": 0.0, "drop": 0.0, "slope": 0.0,
                "z_start": z0, "z_end": z0, "cells": len(path)}
    idx = np.asarray(path, dtype=np.int64)
    r, c = np.divmod(idx, nx)
    dl = np.hypot(np.diff(c) * cx, np.diff(r) * cy)
    length = float(np.sum(dl))
    z0, z1 = float(zf[idx[0]]), float(zf[idx[-1]])
    drop = z0 - z1
    return {"length": length, "drop": drop,
            "slope": (drop / length) if length > 0 else 0.0,
            "z_start": z0, "z_end": z1, "cells": int(idx.size)}


def path_reason(path, downstream, shape, stop=None, seen=None):
    """Чем закончилась трасса: сток, край листа, приёмник или слияние."""
    n = int(shape[0]) * int(shape[1])
    if not path:
        return "пусто"
    last = int(path[-1])
    if stop is not None and last in stop:
        return "приёмник"
    ny, nx = int(shape[0]), int(shape[1])
    lr, lc = divmod(last, nx)
    on_edge = lr in (0, ny - 1) or lc in (0, nx - 1)
    nxt = int(downstream[last])
    if nxt < 0:
        # у рамки листа сток и уход за край неотличимы по указателю,
        # но для отчёта это разные вещи: за краем рельеф просто кончился
        return "край листа" if on_edge else "сток"
    if nxt >= n:
        return "край листа"
    if seen is not None and nxt in seen:
        return "слияние"
    if len(path) > 1 and nxt == int(path[-2]):
        return "сток"
    return "обрыв"


def cut_on_flattening(path, z, shape, cell_x, min_slope, window,
                      cell_y=None):
    """Обрезать трассу там, где рельеф выполаживается.

    Линия стока обрывается там, где поток теряет силу: у подножия
    склона, на террасе, на пойме. Признак - уклон вдоль трассы упал ниже
    порога и держится низким на протяжении, а не на одном шаге.

    Уклон меряется осреднённо по последним `window` метрам пути. По
    одному шагу D8 он на грубой ЦМР скачет, и ступенька в одну ячейку
    читалась бы как выполаживание. Короткая полка внутри крутого склона
    среднее не уронит, настоящее выполаживание уронит.

    Режется по началу окна: точка, с которой пошло выполаживание, и есть
    место, где поток растекается. Возвращает (путь, обрезано ли).
    """
    if len(path) < 3 or min_slope <= 0 or window <= 0:
        return list(path), False
    nx = int(shape[1])
    cy = float(cell_x if cell_y is None else cell_y)
    cx = float(cell_x)
    zf = np.asarray(z, dtype=np.float64).ravel()
    idx = np.asarray(path, dtype=np.int64)
    r, c = np.divmod(idx, nx)
    step = np.hypot(np.diff(c) * cx, np.diff(r) * cy)
    s = np.concatenate(([0.0], np.cumsum(step)))
    zz = zf[idx]
    win = float(window)
    if s[-1] <= win:
        return list(path), False
    j0 = 0
    for j in range(1, len(idx)):
        # Начало окна - последний узел, от которого до j не меньше
        # окна. Прежде начало шло до первого узла не дальше окна, и уклон
        # мерился, только когда путь ровно равен окну: при шаге, не
        # кратном окну, выполаживание не находилось никогда.
        while j0 < j - 1 and s[j] - s[j0 + 1] >= win:
            j0 += 1
        if s[j] - s[j0] < win:
            continue
        drop = zz[j0] - zz[j]
        if drop / (s[j] - s[j0]) < float(min_slope):
            return list(idx[:j0 + 1]), True
    return list(path), False


def steep_run(path, z, shape, cell_x, min_slope, cell_y=None):
    """Самый длинный участок трассы круче порога.

    Мера зоны зарождения: лавина срывается там, где склон держит уклон на
    протяжении, а не в одной ячейке. Ищется наибольший отрезок пути, у
    которого средний уклон не ниже порога, и возвращается его длина в
    метрах вместе с индексами концов в пути.

    Средний уклон по отрезку, а не по шагу: у D8 шаг скачет, и на грубой
    ЦМР отдельная ячейка легко даёт и ноль, и вертикаль.
    """
    if len(path) < 2 or min_slope <= 0:
        return 0.0, 0, 0
    nx = int(shape[1])
    cy = float(cell_x if cell_y is None else cell_y)
    cx = float(cell_x)
    zf = np.asarray(z, dtype=np.float64).ravel()
    idx = np.asarray(path, dtype=np.int64)
    r, c = np.divmod(idx, nx)
    s = np.concatenate(([0.0], np.cumsum(
        np.hypot(np.diff(c) * cx, np.diff(r) * cy))))
    zz = zf[idx]
    thr = float(min_slope)
    # Участок держит порог, когда (z_i - z_j) >= thr * (s_j - s_i). Это
    # то же самое, что g(i) >= g(j) для g(k) = z_k + thr * s_k, и задача
    # сводится к самой широкой паре с невозрастающим g. Двигать начало
    # вперёд по одному нельзя: условие не монотонно, и окно проскакивает
    g = zz + thr * s
    # кандидаты на начало: индексы, где g строго растёт. Всякое начало
    # вне этой цепочки перекрыто более ранним с большим g
    stack = [0]
    for k in range(1, len(g)):
        if g[k] > g[stack[-1]]:
            stack.append(k)
    best, bi, bj = 0.0, 0, 0
    for j in range(len(g) - 1, 0, -1):
        while stack and g[stack[-1]] >= g[j]:
            i = stack.pop()
            if s[j] - s[i] > best:
                best, bi, bj = float(s[j] - s[i]), int(i), int(j)
        if not stack:
            break
    return best, bi, bj


def slope_from_degrees(deg):
    """Уклон в м/м из градусов: лавинные пороги задают углом."""
    return float(np.tan(np.radians(float(deg))))
