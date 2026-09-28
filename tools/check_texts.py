# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""
Проверка текстов по требованиям из AGENTS.md.

Перенесена из Topoliner. Смотрит на всё, что читает человек: файлы
markdown и подсказки полей в вызовах setHelp.

    python tools/check_texts.py                  все тексты
    python tools/check_texts.py AGENTS.md doc    выбранные файлы и папки
    python tools/check_texts.py --strict         код возврата 1 при находках

Проверка машинная и находок не исправляет. Каждая находка - это файл,
строка, цитата и суть расхождения.

В AGENTS.md лексика не проверяется. В нём стоит список стоп-слов, и каждое
слово этого списка обернулось бы находкой на себя же. Пунктуация
в AGENTS.md проверяется.
"""

import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, "planetx")
SKIP_DIRS = {"__pycache__", "libs", "tests"}

STOP_WORDS = (
    "честный", "честнее", "честно", "врать", "врёт", "главные грабли",
    "софт", "кучка", "гладь", "скучный", "лаг", "членение", "наблюдённый",
    "предъявить", "соблазн", "лесенка", "сходит с рук", "деваться некуда",
    "вперемешку", "крутить параметры", "руками", "кучу", "под рукой",
    "мелочь",
)
# Слова, которые ловятся только целиком: у них есть законные
# родственники (прямой, прямого, напрямую).
STOP_WHOLE = ("прямо",)

LONG_DASH = re.compile(r"[–—]")
SENTENCE = re.compile(r"[^.!?]+[.!?]")
LIST_ITEM = re.compile(r"^(-|\*|\d+\.)\s+")


def markdown_in(folder):
    for name in sorted(os.listdir(folder)):
        if name.endswith(".md"):
            yield os.path.join(folder, name)


def markdown_files(targets):
    """Файлы markdown из перечня. Пустой перечень - корень и doc."""
    if not targets:
        targets = [ROOT, os.path.join(ROOT, "doc")]
    for target in targets:
        path = os.path.join(ROOT, target)
        if os.path.isdir(path):
            yield from markdown_in(path)
        elif path.endswith(".md") and os.path.exists(path):
            yield path
        else:
            raise SystemExit("Нет такого файла или папки: %s" % target)


def help_strings():
    """Подсказки полей в вызовах setHelp, четвёрки файл, ключ, строка, текст.
    """
    out = []
    for folder, dirs, files in os.walk(PLUGIN):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            path = os.path.join(folder, name)
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if getattr(node.func, "attr", "") != "setHelp":
                    continue
                text = literal_text(node.args[0]) if node.args else None
                if text is not None:
                    out.append((os.path.relpath(path, ROOT), "setHelp",
                                node.lineno, text))
    return out


def literal_text(node):
    """Строка из литерала. Выражение, вычисляемое при запуске, даёт None."""
    try:
        value = ast.literal_eval(node)
    except ValueError:
        return None
    return value if isinstance(value, str) else None


def clean_markdown(text):
    """Текст без кода, таблиц и заголовков. Остаётся проза.

    Блоки кода заменяются пустыми строками, а не вырезаются. Иначе номера
    строк в находках уезжают относительно исходного файла.
    """
    text = re.sub(r"```.*?```",
                  lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    text = re.sub(r"`[^`]*`", "", text)
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith(("|", "#", "![", "[!")):
            lines.append("")
            continue
        lines.append(line)
    return "\n".join(lines)


def colon_is_fine(before, after):
    """Двоеточие перед списком, в подписи, в соотношении и в адресе."""
    if not after.strip():
        return True
    if before.rstrip().endswith("**") or after.lstrip().startswith("**"):
        return True
    if re.search(r"\d\s*$", before) and re.match(r"\s*\d", after):
        return True
    if re.search(r"(https?|file|mailto)$", before) or after.startswith("//"):
        return True
    return False


def check_prose(where, text, problems, russian=True):
    """Пунктуация и лексика в одном куске текста."""
    plain = re.sub(r"<[^>]+>", " ", text)
    for number, line in enumerate(plain.split("\n"), 1):
        place = "%s:%d" % (where, number)
        if LONG_DASH.search(line):
            problems.append((place, line.strip(), "длинное тире"))
        if ";" in line:
            problems.append((place, line.strip(), "точка с запятой"))
        for match in re.finditer(r":", line):
            if colon_is_fine(line[:match.start()], line[match.end():]):
                continue
            quote = line[max(0, match.start() - 18):match.start() + 18]
            problems.append((place, quote.strip(), "двоеточие внутри строки"))
        if not russian:
            continue
        low = line.lower()
        for word in STOP_WORDS:
            if re.search(r"\b%s" % re.escape(word), low):
                problems.append((place, word, "стоп-слово"))
        for word in STOP_WHOLE:
            if re.search(r"\b%s\b" % re.escape(word), low):
                problems.append((place, word, "стоп-слово"))
        for match in re.finditer(r"\bчисл[оа]\b", low):
            near = low[max(0, match.start() - 1):match.end() + 1]
            if near.startswith("«") or near.endswith("»"):
                continue
            quote = line[max(0, match.start() - 18):match.end() + 18]
            problems.append((place, quote.strip(),
                             "«число» вместо «количества»"))


def text_blocks(text):
    """Куски текста, внутри которых ищутся предложения.

    Граница куска - пустая строка и начало пункта списка. Пункт списка
    часто идёт без точки, и без этой границы счётчик склеивает весь список
    со следующим предложением. В Topoliner счётчик этой границы не знает.
    """
    plain = re.sub(r"<[^>]+>", " ", text)
    blocks, current = [], []
    for line in plain.split("\n"):
        stripped = line.strip()
        if not stripped or LIST_ITEM.match(stripped):
            if current:
                blocks.append(" ".join(current))
            current = []
        if stripped:
            current.append(stripped)
    if current:
        blocks.append(" ".join(current))
    return blocks


def sentence_stats(text):
    lengths = []
    for block in text_blocks(text):
        block = LIST_ITEM.sub("", block)
        if not block.rstrip().endswith((".", "!", "?")):
            block += "."
        lengths += [len(s.split()) for s in SENTENCE.findall(block)
                    if s.strip()]
    if not lengths:
        return 0.0, 0, 0, 0
    mean = sum(lengths) / len(lengths)
    return (mean, len(lengths), sum(1 for n in lengths if n > 28),
            sum(1 for n in lengths if n > 34))


def main(argv):
    strict = "--strict" in argv
    targets = [a for a in argv if not a.startswith("--")]

    problems = []
    texts = []

    for path in markdown_files(targets):
        name = os.path.relpath(path, ROOT)
        with open(path, encoding="utf-8") as fh:
            body = clean_markdown(fh.read())
        russian = not name.endswith(".en.md") and name != "AGENTS.md"
        check_prose(name, body, problems, russian=russian)
        texts.append((name, body))

    if not targets:
        for name, key, line, text in help_strings():
            where = "%s (%s, строка %d)" % (name, key, line)
            check_prose(where, text, problems,
                        russian=bool(re.search(r"[А-Яа-я]", text)))
            texts.append((where, text))

    print("Проверка текстов")
    print("")
    if problems:
        print("Находок: %d" % len(problems))
        for place, quote, reason in problems:
            print("  %-40s %-40s %s" % (place, quote[:40], reason))
    else:
        print("Находок нет.")

    print("")
    print("Длина предложений")
    rows = []
    for name, text in texts:
        mean, total, over28, over34 = sentence_stats(text)
        if total:
            rows.append((over34, over28, mean, total, name))
    rows.sort(reverse=True)
    for over34, over28, mean, total, name in rows[:12]:
        print("  %-30s средняя %4.1f, предложений %4d, длиннее 28: %d, "
              "длиннее 34: %d" % (name, mean, total, over28, over34))
    return 1 if (problems and strict) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
