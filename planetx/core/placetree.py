# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Дерево «Моих меток»: папки и метки, порядок, перенос, обход.

Расчёт без Qt. Узел - метка или папка с ключом, ключом родительской
папки (None - корень «Мои метки»), номером среди соседей и названием.
Метки и папки одного родителя нумеруются вместе, как строки списка.
Узлы без номера, из файлов до поля position, стоят после нумерованных
по названию.

Папки как в Google Earth, решение автора от 28 сентября 2026 года:
любая вложенность, перенос мышью, тур по папке, удаление папки вместе
с содержимым.
"""

FOLDER = "folder"  # вид ключа папки: "folder:<номер>"


def is_folder(key):
    return bool(key) and key.startswith(FOLDER + ":")


class Node:
    """Узел дерева: ключ, родитель, номер среди соседей, название."""

    def __init__(self, key, parent, position, name):
        self.key = key
        self.parent = parent
        self.position = position
        self.name = name

    def order(self):
        return (self.position is None, self.position or 0,
                self.name.lower())


def children(nodes, parent):
    """Дети папки parent по порядку списка."""
    return sorted((n for n in nodes if n.parent == parent),
                  key=Node.order)


def walk(nodes, parent=None):
    """Все узлы под parent в порядке списка, папка раньше своих детей."""
    out = []
    for node in children(nodes, parent):
        out.append(node)
        if is_folder(node.key):
            out.extend(walk(nodes, node.key))
    return out


def descendants(nodes, folder):
    """Ключи всех узлов внутри папки folder, на любой глубине."""
    return [n.key for n in walk(nodes, folder)]


def top_keys(nodes, keys):
    """Выбранные ключи без тех, что лежат внутри выбранной папки, в
    порядке списка. Папка и так переносится и удаляется с содержимым."""
    chosen = set(keys)
    inside = set()
    for key in chosen:
        if is_folder(key):
            inside.update(descendants(nodes, key))
    return [n.key for n in walk(nodes)
            if n.key in chosen and n.key not in inside]


def move_plan(nodes, key, parent, index):
    """Новые (родитель, номер) узлов после переноса key в parent перед
    его ребёнком номер index. index за концом - в конец.

    Возвращает {ключ: (родитель, номер)} только для изменившихся узлов,
    пустой словарь - переноса нет. Папку нельзя перенести в неё саму
    и в её потомков.
    """
    return move_many_plan(nodes, [key], parent, index)


def move_many_plan(nodes, keys, parent, index):
    """То же для нескольких выбранных узлов. Они встают подряд в порядке
    списка, вложенные в выбранную папку едут вместе с ней."""
    by_key = {n.key: n for n in nodes}
    if parent is not None and parent not in by_key:
        return {}
    keys = top_keys(nodes, [k for k in keys if k in by_key])
    if not keys:
        return {}
    for key in keys:
        if is_folder(key) and (parent == key
                               or parent in descendants(nodes, key)):
            return {}
    moved = [by_key[k] for k in keys]
    siblings = children(nodes, parent)
    index = max(0, min(index, len(siblings)))
    index -= sum(1 for n in siblings[:index] if n in moved)
    siblings = [n for n in siblings if n not in moved]
    siblings[index:index] = moved
    plan = {}
    for n, item in enumerate(siblings):
        if item.parent != parent or item.position != n:
            plan[item.key] = (parent, n)
    return plan



def sort_plan(nodes, parent):
    """Номера детей папки parent по названию от А до Я, как «Сортировать
    от А до Я» Google Earth. Папки и метки сортируются вместе,
    без учёта регистра. Возвращает {ключ: номер}."""
    kids = sorted(children(nodes, parent),
                  key=lambda n: ((n.name or "").casefold(), n.key))
    return {n.key: i for i, n in enumerate(kids)}


def radio_states(nodes, radio, states):
    """Флажки с учётом папок-переключателей radio (ключи папок): в такой
    папке включён не больше чем один ребёнок. Если включили одного -
    соседи гаснут. Если включили сразу несколько, как флажком самой
    папки, остаётся первый по списку. Выбранный ребёнок щелчком
    по нему не гаснет, как переключатель, погасить всех можно только
    флажком самой папки. states - {ключ: включён}, возвращается
    дополненный словарь."""
    out = dict(states)
    for folder in radio:
        kids = [n.key for n in children(nodes, folder)]
        lit = [k for k in kids if states.get(k)]
        if not lit:
            if folder not in states:
                for key in kids:
                    if key in states:
                        out[key] = True
            continue
        keep = lit[0]
        for key in kids:
            out[key] = key == keep
    return out

def next_position(nodes, parent):
    """Номер для нового узла в конце папки parent."""
    kids = children(nodes, parent)
    numbered = [n.position for n in kids if n.position is not None]
    return max(numbered + [len(kids) - 1]) + 1


def numbered_name(base, names):
    """Название «base N» для новой метки, как «Моя метка 3».

    N - следующий номер после наибольшего среди названий вида
    «base число». Удалённые номера в середине не занимаются заново,
    так новая метка всегда встаёт последней по номеру.
    """
    prefix = base + " "
    numbers = [0]
    for name in names:
        tail = name[len(prefix):] if name.startswith(prefix) else ""
        if tail.isdigit():
            numbers.append(int(tail))
    return prefix + str(max(numbers) + 1)