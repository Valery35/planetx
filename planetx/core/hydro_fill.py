# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
# Перенесено из Isoliner, grid_isolines/hydro_fill.py.
# Там - GPL-2.0-or-later, владелец тот же.
"""Заполнение понижений по Planchon-Darboux (2001) с epsilon.

Чистый NumPy. Вместо параллельной итерации Якоби используем четыре
направленных прохода (сверху вниз, снизу вверх, слева направо,
справа налево). Каждый проход идёт последовательно вдоль своей оси
и векторизован по перпендикулярной, при этом ячейка видит три
соседа из уже обработанной линии, включая диагонали. Вода стекает
через весь грид за один проход, поэтому сходимость занимает
единицы полных циклов, а не тысячи итераций.

Скорость держится на двух вещах. Первая: линия пересчитывается
только когда с прошлого пересчёта менялась она сама или её сосед,
для этого по каждому направлению ведётся вектор грязных линий.
После второго-третьего цикла меняются единицы линий из тысяч, и
поздние циклы почти бесплатны. Результат от пропусков не меняется
ни в одной ячейке: пропускается только линия, чьи входы не
менялись, а пересчёт с теми же входами дал бы её же значения.
Вторая: горизонтальные проходы идут по транспонированной копии.
Столбец исходного массива лежит в памяти с шагом в целую строку, и
операция над ним раз в двадцать медленнее операции над строкой.
Копия синхронизируется адресно, по списку изменённых ячеек, а при
массовых изменениях первых циклов переснимается целиком.

Epsilon задаёт минимальный уклон на плоских участках, чтобы поток
не останавливался. Ячейки на границе грида и ячейки, соседние
с nodata, считаются стоками: через них вода уходит с грида.
"""

import numpy as np

DEFAULT_EPSILON = 0.001
DEFAULT_MAX_PASSES = 100
_BIG = np.float64(1e30)


class _Axis:
    """Рабочее состояние одной оси: массивы в её ориентации и буферы.

    Для вертикальных проходов линия это строка w, для горизонтальных -
    строка транспонированной копии. Обе копии живут одновременно и
    синхронизируются списком изменённых ячеек.
    """

    __slots__ = ("w", "z", "noint", "full_int", "nmin", "out",
                 "ge", "neq", "dirty")

    def __init__(self, w, z, interior):
        self.w = w
        self.z = z
        self.noint = ~interior
        # линия целиком внутренняя: маску на ней можно не накладывать
        self.full_int = interior.all(axis=1)
        n, m = w.shape
        self.nmin = np.empty(m)
        self.out = np.empty(m)
        self.ge = np.empty(m, dtype=bool)
        self.neq = np.empty(m, dtype=bool)
        # свой вектор грязных линий на каждое направление оси
        self.dirty = [np.ones(n, dtype=bool), np.ones(n, dtype=bool)]


def _mark(vec, idx):
    """Пометить линии idx и обе соседние. Клип по границам."""
    n = vec.shape[0]
    vec[idx] = True
    up = idx + 1
    vec[up[up < n]] = True
    dn = idx - 1
    vec[dn[dn >= 0]] = True


def _sweep(ax, other, eps, reverse):
    """Один направленный проход по оси ax.

    reverse=False: линии сверху вниз, каждая видит предыдущую сверху.
    reverse=True: снизу вверх. Пересчитываются только грязные линии
    этого направления, флаг снимается при пересчёте. Изменённая линия
    метит соседей у себя и перпендикулярные линии у другой оси, а сами
    изменения копятся списком для синхронизации второй копии.

    Возвращает (число изменённых ячеек, список (линия, индексы)).
    """
    w, z = ax.w, ax.z
    n = w.shape[0]
    dirty = ax.dirty[1 if reverse else 0]
    # Крайнюю линию это направление не обходит: сверху вниз недостижима
    # нулевая, снизу вверх - последняя. Её флаг ничего не означает, и
    # снимать его надо здесь, иначе он остаётся поднятым навсегда,
    # сходимость не распознаётся и проходы идут до предела вхолостую.
    dirty[n - 1 if reverse else 0] = False
    if not dirty.any():
        return 0, []
    lines = range(n - 2, -1, -1) if reverse else range(1, n)
    step = 1 if reverse else -1
    nmin, out, ge, neq = ax.nmin, ax.out, ax.ge, ax.neq
    od0, od1 = other.dirty
    d0, d1 = ax.dirty
    changed = []
    total = 0
    for i in lines:
        if not dirty[i]:
            continue
        dirty[i] = False
        prev = w[i + step]
        wi = w[i]
        # минимум трёх соседей обработанной линии, включая диагонали
        np.copyto(nmin, prev)
        np.minimum(nmin[1:], prev[:-1], out=nmin[1:])
        np.minimum(nmin[:-1], prev[1:], out=nmin[:-1])
        nmin += eps                            # теперь это cand
        zi = z[i]
        np.minimum(wi, nmin, out=out)          # вода не ниже cand
        np.greater_equal(zi, nmin, out=ge)
        np.copyto(out, zi, where=ge)           # суша остаётся сушей
        if not ax.full_int[i]:
            np.copyto(out, wi, where=ax.noint[i])
        np.not_equal(out, wi, out=neq)
        idx = np.flatnonzero(neq)
        if idx.size == 0:
            continue
        wi[idx] = out[idx]
        total += idx.size
        changed.append((i, idx))
        # соседние линии обоих направлений своей оси
        d0[i] = d1[i] = True
        if i + 1 < n:
            d0[i + 1] = d1[i + 1] = True
        if i > 0:
            d0[i - 1] = d1[i - 1] = True
        # перпендикулярные линии другой оси: изменённые столбцы
        _mark(od0, idx)
        _mark(od1, idx)
    return total, changed


def _sync(dst, src_changed, wholesale_from, threshold, total):
    """Перенести изменения в транспонированную копию.

    При массовых правках копия переснимается целиком, иначе адресно
    по списку (линия, индексы): так поздние циклы не платят за полное
    транспонирование.
    """
    if total == 0:
        return
    if total > threshold:
        np.copyto(dst, wholesale_from.T)
        return
    for i, idx in src_changed:
        dst[idx, i] = wholesale_from[i, idx]


def fill_depressions(z, nodata_mask=None, epsilon=DEFAULT_EPSILON,
                     max_passes=DEFAULT_MAX_PASSES, feedback=None,
                     outlets=None):
    """Возвращает (заполненный_грид, число_поднятых_ячеек, макс_подъём).

    z: 2D float ndarray. nodata_mask: True там, где данных нет.
    Значения в nodata-ячейках не меняются и на соседей не влияют.
    outlets: булев массив своих стоков вместо края грида и соседей
    nodata (PlanetX: уровень перелива от точки, core/hydro.py).
    """
    z_in = np.asarray(z, dtype=np.float64)
    if z_in.ndim != 2 or z_in.shape[0] < 2 or z_in.shape[1] < 2:
        raise ValueError("Ожидается двумерный грид не меньше 2x2.")
    eps = np.float64(epsilon)
    if eps < 0:
        raise ValueError("Epsilon не может быть отрицательным.")

    if nodata_mask is None:
        nodata_mask = ~np.isfinite(z_in)
    else:
        nodata_mask = np.asarray(nodata_mask, dtype=bool) | ~np.isfinite(z_in)
    valid = ~nodata_mask

    own = None if outlets is None else np.asarray(outlets, dtype=bool)
    # Стоки: граница грида и валидные ячейки, соседние с nodata.
    outlets = np.zeros(z_in.shape, dtype=bool)
    outlets[0, :] = outlets[-1, :] = True
    outlets[:, 0] = outlets[:, -1] = True
    pad = np.pad(nodata_mask, 1, constant_values=False)
    near_nodata = np.zeros(z_in.shape, dtype=bool)
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            if di == 0 and dj == 0:
                continue
            near_nodata |= pad[1 + di:1 + di + z_in.shape[0],
                               1 + dj:1 + dj + z_in.shape[1]]
    outlets = (outlets | near_nodata) & valid
    if own is not None:
        outlets = own & valid
    interior = valid & ~outlets

    z_work = np.where(nodata_mask, -_BIG, z_in)
    w = np.where(outlets | nodata_mask, z_work, _BIG)

    vert = _Axis(w, z_work, interior)
    horz = _Axis(np.ascontiguousarray(w.T),
                 np.ascontiguousarray(z_work.T),
                 np.ascontiguousarray(interior.T))
    threshold = max(1, w.size // 16)

    converged = False
    for n_pass in range(1, int(max_passes) + 1):
        c1, ch1 = _sweep(vert, horz, eps, reverse=False)
        c2, ch2 = _sweep(vert, horz, eps, reverse=True)
        _sync(horz.w, ch1 + ch2, w, threshold, c1 + c2)
        c3, ch3 = _sweep(horz, vert, eps, reverse=False)
        c4, ch4 = _sweep(horz, vert, eps, reverse=True)
        _sync(w, ch3 + ch4, horz.w, threshold, c3 + c4)
        if not (vert.dirty[0].any() or vert.dirty[1].any()
                or horz.dirty[0].any() or horz.dirty[1].any()):
            converged = True
            if feedback:
                feedback.pushInfo(
                    "Заполнение сошлось, проходов: {}.".format(n_pass))
            break
    if not converged and feedback:
        # это предупреждение, а не сводка: заполнение не сошлось.
        # Не у всякой обратной связи есть pushWarning, отсюда getattr
        warn = getattr(feedback, "pushWarning", feedback.pushInfo)
        warn(
            "Достигнут предел {} проходов, результат может быть "
            "неполным на очень сложном рельефе.".format(max_passes))

    filled = np.where(valid, w, z_in)
    diff = filled - np.where(valid, z_in, filled)
    raised = valid & (diff > 1e-9)
    n_raised = int(np.count_nonzero(raised))
    max_raise = float(diff[raised].max()) if n_raised else 0.0
    return filled, n_raised, max_raise
