# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Стеки потоков из дампа Windows (minidump) без отладчика.

Дамп пишет журнал модуля при зависании главного потока QGIS. Отладчика
и символов на машине пользователя нет, поэтому стек восстанавливается
просмотром памяти стека: восьмибайтовое число внутри образа модуля,
перед которым в файле модуля стоит команда call, считается адресом
возврата. Имя функции - ближайший экспорт модуля не дальше
NEAR_EXPORT байт, у Qt и QGIS экспортируются почти все функции классов.
Разбор только x64, формат - описание MINIDUMP_* в dbghelp.h.
"""
import os
import struct

THREAD_LIST = 3
MODULE_LIST = 4
THREAD_INFO_LIST = 17
CONTEXT_RSP = 0x98
CONTEXT_RIP = 0xF8
NEAR_EXPORT = 0x4000  # байт от экспорта, дальше имя не даётся
FRAMES = 40  # адресов возврата на поток, не больше


class Dump:
    """Разобранный дамп: потоки и модули."""

    def __init__(self, data):
        if data[:4] != b"MDMP":
            raise ValueError("not a minidump")
        self.data = data
        count, rva = struct.unpack_from("<II", data, 8)
        self.streams = {}
        for i in range(count):
            kind, size, where = struct.unpack_from("<III", data,
                                                   rva + 12 * i)
            self.streams[kind] = (where, size)
        self.modules = self._modules()
        self.threads = self._threads()

    def _string(self, rva):
        length = struct.unpack_from("<I", self.data, rva)[0]
        return self.data[rva + 4:rva + 4 + length].decode("utf-16-le")

    def _modules(self):
        found = []
        if MODULE_LIST not in self.streams:
            return found
        rva = self.streams[MODULE_LIST][0]
        count = struct.unpack_from("<I", self.data, rva)[0]
        for i in range(count):
            at = rva + 4 + 108 * i
            base, size = struct.unpack_from("<QI", self.data, at)
            name = self._string(struct.unpack_from("<I", self.data,
                                                   at + 20)[0])
            found.append((base, size, name))
        found.sort()
        return found

    def _threads(self):
        found = []
        if THREAD_LIST not in self.streams:
            return found
        rva = self.streams[THREAD_LIST][0]
        count = struct.unpack_from("<I", self.data, rva)[0]
        created = self._created()
        for i in range(count):
            at = rva + 4 + 48 * i
            tid = struct.unpack_from("<I", self.data, at)[0]
            start, size, mem = struct.unpack_from("<QII", self.data, at + 24)
            csize, crva = struct.unpack_from("<II", self.data, at + 40)
            rip = rsp = 0
            if csize >= CONTEXT_RIP + 8:
                rsp = struct.unpack_from("<Q", self.data,
                                         crva + CONTEXT_RSP)[0]
                rip = struct.unpack_from("<Q", self.data,
                                         crva + CONTEXT_RIP)[0]
            found.append({"id": tid, "stack": (start, mem, size),
                          "rip": rip, "rsp": rsp,
                          "created": created.get(tid, 0)})
        return found

    def _created(self):
        """Время создания потоков - самый ранний поток главный."""
        found = {}
        if THREAD_INFO_LIST not in self.streams:
            return found
        rva = self.streams[THREAD_INFO_LIST][0]
        head, entry, count = struct.unpack_from("<III", self.data, rva)
        for i in range(count):
            at = rva + head + entry * i
            tid = struct.unpack_from("<I", self.data, at)[0]
            found[tid] = struct.unpack_from("<Q", self.data, at + 24)[0]
        return found

    def module_at(self, address):
        for base, size, name in self.modules:
            if base <= address < base + size:
                return base, name
        return None

    def main_thread(self):
        """Номер главного потока - созданного раньше всех."""
        timed = [t for t in self.threads if t["created"]]
        if timed:
            return min(timed, key=lambda t: t["created"])["id"]
        return self.threads[0]["id"] if self.threads else None


class Image:
    """Файл модуля на диске: секции, экспорты, байты по RVA."""

    def __init__(self, path):
        with open(path, "rb") as fh:
            self.data = fh.read()
        pe = struct.unpack_from("<I", self.data, 0x3C)[0]
        if self.data[pe:pe + 4] != b"PE\0\0":
            raise ValueError("not a PE file")
        sections, optional = struct.unpack_from("<H12xH", self.data, pe + 6)
        opt = pe + 24
        self.sections = []
        at = opt + optional
        for i in range(sections):
            vsize, vaddr, rsize, raw = struct.unpack_from(
                "<IIII", self.data, at + 40 * i + 8)
            self.sections.append((vaddr, max(vsize, rsize), raw, rsize))
        magic = struct.unpack_from("<H", self.data, opt)[0]
        directory = opt + (112 if magic == 0x20B else 96)
        export_rva, export_size = struct.unpack_from("<II", self.data,
                                                     directory)
        self.exports = self._exports(export_rva, export_size)

    def offset(self, rva):
        for vaddr, size, raw, rsize in self.sections:
            if vaddr <= rva < vaddr + size:
                if rva - vaddr >= rsize:
                    return None
                return raw + rva - vaddr
        return None

    def bytes_at(self, rva, count):
        at = self.offset(rva)
        if at is None or at + count > len(self.data):
            return b""
        return self.data[at:at + count]

    def _cstring(self, rva):
        at = self.offset(rva)
        if at is None:
            return ""
        end = self.data.find(b"\0", at)
        return self.data[at:end].decode("latin-1")

    def _exports(self, rva, size):
        if not rva:
            return []
        at = self.offset(rva)
        if at is None:
            return []
        (count, names, functions, name_table,
         ordinal_table) = struct.unpack_from("<20xIIIII", self.data, at)
        found = []
        func_at = self.offset(functions)
        name_at = self.offset(name_table)
        ord_at = self.offset(ordinal_table)
        if None in (func_at, name_at, ord_at):
            return []
        for i in range(names):
            name_rva = struct.unpack_from("<I", self.data, name_at + 4 * i)[0]
            ordinal = struct.unpack_from("<H", self.data, ord_at + 2 * i)[0]
            if ordinal >= count:
                continue
            func = struct.unpack_from("<I", self.data,
                                      func_at + 4 * ordinal)[0]
            if rva <= func < rva + size:
                continue  # переадресованный экспорт
            found.append((func, self._cstring(name_rva)))
        found.sort()
        return found

    def name_at(self, rva):
        """Ближайший экспорт не дальше NEAR_EXPORT байт перед rva."""
        low, high = 0, len(self.exports)
        while low < high:
            mid = (low + high) // 2
            if self.exports[mid][0] <= rva:
                low = mid + 1
            else:
                high = mid
        if low == 0:
            return None
        func, name = self.exports[low - 1]
        if rva - func > NEAR_EXPORT:
            return None
        return "{}+0x{:x}".format(name, rva - func)


def after_call(code):
    """Стоит ли перед адресом возврата команда call. code - 7 байт
    перед адресом."""
    if len(code) < 7:
        return False
    if code[2] == 0xE8:  # call rel32
        return True
    for at in (0, 1, 4, 5):  # call r/m64 с ModRM и смещением
        if code[at] == 0xFF and (code[at + 1] >> 3) & 7 == 2:
            return True
    return False


class Symbols:
    """Файлы модулей по путям из дампа, читаются один раз."""

    def __init__(self):
        self.images = {}

    def image(self, path):
        if path not in self.images:
            try:
                self.images[path] = Image(path)
            except (OSError, ValueError, struct.error):
                self.images[path] = None
        return self.images[path]

    def frame(self, dump, address, check=True):
        """Строка кадра «модуль!функция» или None, если адрес не похож
        на адрес возврата."""
        hit = dump.module_at(address)
        if hit is None:
            return None
        base, path = hit
        rva = address - base
        image = self.image(path)
        if check:
            if image is None or not after_call(image.bytes_at(rva - 7, 7)):
                return None
        name = image.name_at(rva) if image is not None else None
        module = os.path.basename(path)
        return "{}!{}".format(module, name) if name \
            else "{}+0x{:x}".format(module, rva)


def stacks(dump, symbols=None, frames=FRAMES):
    """Стеки потоков: [(номер, главный ли, [кадры])], главный первым."""
    symbols = symbols or Symbols()
    main = dump.main_thread()
    found = []
    for thread in dump.threads:
        start, rva, size = thread["stack"]
        lines = []
        top = symbols.frame(dump, thread["rip"], check=False)
        if top:
            lines.append(top)
        memory = dump.data[rva:rva + size]
        skip = max(0, thread["rsp"] - start) if thread["rsp"] else 0
        for at in range(skip - skip % 8, len(memory) - 7, 8):
            value = struct.unpack_from("<Q", memory, at)[0]
            line = symbols.frame(dump, value)
            if line and (not lines or lines[-1] != line):
                lines.append(line)
            if len(lines) >= frames:
                break
        found.append((thread["id"], thread["id"] == main, lines))
    found.sort(key=lambda item: not item[1])
    return found


SYSTEM = ("ntdll.dll", "kernel32.dll", "kernelbase.dll")


def idle(lines):
    """Поток без своих кадров - только ожидание в модулях Windows."""
    return all(line.split("!")[0].split("+")[0].lower() in SYSTEM
               for line in lines)


def report(path, main_label="main thread", label="thread",
           idle_label="idle threads", frames=FRAMES):
    """Текст стеков потоков дампа path для журнала. Потоки без своих
    кадров сводятся в строку с количеством. Подписи задаёт вызывающий,
    ядро без перевода строк."""
    with open(path, "rb") as fh:
        dump = Dump(fh.read())
    out = []
    quiet = 0
    for tid, main, lines in stacks(dump, frames=frames):
        if not main and idle(lines):
            quiet += 1
            continue
        out.append("{} {}".format(main_label if main else label, tid))
        out.extend("  " + line for line in lines)
    if quiet:
        out.append("{} {}".format(idle_label, quiet))
    return "\n".join(out)
