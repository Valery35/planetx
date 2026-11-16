# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""
Проверка текстов по требованиям из AGENTS.md.

Смотрит на всё, что читает человек: файлы markdown и подсказки полей
в вызовах setHelp.

    python tools/check_texts.py                  все тексты
    python tools/check_texts.py AGENTS.md doc    выбранные файлы и папки
    python tools/check_texts.py --strict         код возврата 1 при находках
    python tools/check_texts.py --band letter X  одна полоса ритма всем

Markdown разбирает measure.py - заголовки, таблицы, код и цитаты
предложениями не считаются, строки перечня идут отдельно.

Прозу - ритм, длину предложений, общие стоп-слова, тире, точку
с запятой, двоеточие - меряет tools/measure.py, копия измерителя
линейки (tools/TEXTS.md). Здесь только своё: подсказки setHelp,
стоп-слова модуля сверх общих, «число» вместо «количества» и полоса
ритма по виду текста (BANDS). Свой счёт длины предложений убран, чтобы
два инструмента не спорили числами.

Проверка машинная и находок не исправляет. Каждая находка - это файл,
цитата и суть расхождения.

В AGENTS.md лексика не проверяется. В нём стоит список стоп-слов, и каждое
слово этого списка обернулось бы находкой на себя же. Пунктуация и ритм
в AGENTS.md проверяются.
"""

import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PLUGIN = os.path.join(ROOT, "planetx")
SKIP_DIRS = {"__pycache__", "libs", "tests"}

def _load_measure():
    """Измеритель линейки по пути файла. Простой import measure взял бы
    первый measure в sys.path, а у модуля есть свой core/measure.py
    (линейка на глобусе) - в общем прогоне тестов он стоит раньше."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "planetx_text_measure", os.path.join(HERE, "measure.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


measure = _load_measure()

# Стоп-слова модуля сверх общих measure.STOP_WORDS.
STOP_WORDS = ("схват",)
# Слова, которые ловятся только целиком: у них есть законные
# родственники (прямой, прямого, напрямую).
STOP_WHOLE = ("прямо",)

# Полоса ритма measure.py по виду текста - таблица свода линейки
# C:\Dev\workplace\TEXTS.md, первое подходящее правило пути. Роспись -
# tools/TEXTS.md. Ключ --band задаёт одну полосу всем файлам прогона.
LENGTH_ONLY = "length"
BANDS = (
    (r"^AGENTS\.md$", None),
    (r"^README", LENGTH_ONLY),
    (r"^CHANGELOG", "letter"),
    (r"^site[/\\]posts_", "letter"),
    (r"^doc[/\\]PLAN_", "register"),
    (r"DEPLOY", "register"),
    (r".", "note"),
)


def band_of(name):
    """Полоса ритма файла по пути от корня хранилища, None - ритм
    и длина не меряются, LENGTH_ONLY - меряется только длина."""
    for pattern, band in BANDS:
        if re.search(pattern, name):
            return band
    return "note"


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


def own_words(text):
    """Находки модуля сверх measure.py: стоп-слова и «число»."""
    out = []
    low = measure.strip_mentions(re.sub(r"`[^`]*`", " ", text)).lower()
    for word in STOP_WORDS:
        for match in re.finditer(r"\b%s" % re.escape(word), low):
            out.append((word, "стоп-слово"))
    for word in STOP_WHOLE:
        for match in re.finditer(r"\b%s\b" % re.escape(word), low):
            out.append((word, "стоп-слово"))
    for match in re.finditer(r"\bчисл[оа]\b", low):
        quote = low[max(0, match.start() - 18):match.end() + 18]
        out.append((quote.strip(), "«число» вместо «количества»"))
    return out


def check_prose(where, text, problems, russian=True, band=None,
                lexicon=True, lines=False):
    """Проза одного текста. measure.py - пунктуация, общие стоп-слова
    и при заданной полосе ритм и длина, здесь - свои слова. Находки -
    тройки место, цитата, суть. При lines место - «файл:строка», строка -
    начало абзаца или пункта перечня с находкой (measure.sentences_at).
    Находки ритма относятся ко всему тексту и идут без строки.
    Возвращает сводку ритма или None."""
    lang = "ru" if russian else "en"
    rows = measure.sentences_at(text)
    pairs = [(s, item, first) for s, item, first, _ in rows]

    def place(line):
        return "%s:%d" % (where, line) if lines and line else where

    def keep(level, kind):
        return level == "error" or kind == "двоеточие внутри предложения"

    # Пунктуация и слова - по одному предложению, чтобы знать строку.
    for s, item, first, line in rows:
        found = measure.check_punctuation([(s, item, first)], lang)
        if lexicon:
            found += measure.check_words([(s, item, first)], lang)
        for level, kind, detail in found:
            if keep(level, kind):
                problems.append((place(line), detail, kind.split(" / ")[0]))
        if russian and lexicon:
            for quote, reason in own_words(s):
                problems.append((place(line), quote, reason))
    stats = None
    if band:
        length_only = band == LENGTH_ONLY or not russian
        stats, rhythm = measure.check_rhythm(
            pairs, lang, "note" if band == LENGTH_ONLY else band)
        for level, kind, detail in rhythm:
            # У английских текстов своих полос у линейки пока нет, ритм
            # README не меряется вовсе (свод C:\Dev\workplace\TEXTS.md) -
            # меряется только длина.
            if length_only and kind.startswith("ритм"):
                continue
            if keep(level, kind):
                problems.append((place(line_of(detail, rows)), detail,
                                 kind.split(" / ")[0]))
        if band == LENGTH_ONLY:
            stats = None
    return stats


def line_of(detail, rows):
    """Строка предложения, начало которого measure.py привёл в находке
    длины или ритма. Находка о всём тексте строки не имеет - 0."""
    for s, _, _, line in rows:
        for cut in (90, 60):
            if s[:cut] and s[:cut] in detail:
                return line
    return 0


def main(argv):
    strict = "--strict" in argv
    forced = None
    rest = []
    args = iter(argv)
    for arg in args:
        if arg == "--band":
            forced = next(args, None)
        elif arg.startswith("--band="):
            forced = arg.split("=", 1)[1]
        else:
            rest.append(arg)
    if forced is not None and forced not in measure.BANDS["ru"] \
            and forced != LENGTH_ONLY:
        raise SystemExit("Полоса --band - одна из: %s" % ", ".join(
            measure.BANDS["ru"]))
    targets = [a for a in rest if not a.startswith("--")]

    problems = []
    rows = []

    for path in markdown_files(targets):
        name = os.path.relpath(path, ROOT)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        russian = measure.detect_lang(text) == "ru"
        band = forced or band_of(name)
        stats = check_prose(name, text, problems, russian=russian,
                            band=band, lexicon=name != "AGENTS.md",
                            lines=True)
        if stats:
            rows.append((name, band, stats))

    if not targets:
        for name, key, line, text in help_strings():
            where = "%s (%s, строка %d)" % (name, key, line)
            check_prose(where, text, problems,
                        russian=bool(re.search(r"[А-Яа-я]", text)))

    print("Проверка текстов")
    print("")
    if problems:
        print("Находок: %d" % len(problems))
        for place, quote, reason in problems:
            print("  %-40s %-40s %s" % (place, quote[:40], reason))
    else:
        print("Находок нет.")

    print("")
    print("Ритм по measure.py")
    for name, band, s in rows:
        print("  %-30s %-8s средняя %4.1f (%s), коротких %2.0f %%, "
              "длинных %2.0f %%, длиннее %d: %d" % (
                  name, band, s["mean"], s["mean_band"], s["short_pct"],
                  s["long_pct"], s["error_at"], s["over_error"]))
    return 1 if (problems and strict) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
