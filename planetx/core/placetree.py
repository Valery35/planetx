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


def move_plan(nodes, key, parent, index):
    """Новые (родитель, номер) узлов после переноса key в parent перед
    его ребёнком номер index. index за концом - в конец.

    Возвращает {ключ: (родитель, номер)} только для изменившихся узлов,
    пустой словарь - переноса нет. Папку нельзя перенести в неё саму
    и в её потомков.
    """
    by_key = {n.key: n for n in nodes}
    node = by_key.get(key)
    if node is None or parent is not None and parent not in by_key:
        return {}
    if is_folder(key) and (parent == key
                           or parent in descendants(nodes, key)):
        return {}
    siblings = children(nodes, parent)
    index = max(0, min(index, len(siblings)))
    if node in siblings:
        i = siblings.index(node)
        if index > i:
            index -= 1
        siblings.pop(i)
    siblings.insert(index, node)
    plan = {}
    for n, item in enumerate(siblings):
        if item.parent != parent or item.position != n:
            plan[item.key] = (parent, n)
    return plan


def next_position(nodes, parent):
    """Номер для нового узла в конце папки parent."""
    kids = children(nodes, parent)
    numbered = [n.position for n in kids if n.position is not None]
    return max(numbered + [len(kids) - 1]) + 1
