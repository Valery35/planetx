#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""measure.py - измеритель текста по своду RULES.

Считает то, что считается: длину предложений, разброс, стоп-слова,
пунктуацию и имя файла. Всё остальное ловится чтением, а не прогоном.

    python measure.py RULES.ru.md
    python measure.py --band note AGENTS.example.ru.md
    python measure.py --lang en --band register *.md

Нормы длины разведены по языкам. Английская фраза при том же содержании
длиннее русской, поэтому предел один на язык, а не один на оба.
Язык определяется по доле кириллицы, ключ --lang его задаёт явно.

Код возврата 1, если есть нарушение уровня error.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from pathlib import Path

# --------------------------------------------------------------------------
# Нормы
# --------------------------------------------------------------------------

# Предел длины предложения: warn - смотреть глазами, error - переписать.
LIMITS = {
    "ru": {"warn": 28, "error": 34},
    "en": {"warn": 38, "error": 45},
}

# Полосы ритма. mean - допустимая средняя, short - доля предложений до 8 слов
# включительно, long - доля предложений от 19 слов.
BANDS = {
    "ru": {
        "register": {"mean": (8, 11), "short_max": 0.67, "long_min": 0.05},
        "note": {"mean": (12, 14), "short_max": 0.34, "long_min": 0.15},
        "letter": {"mean": (8, 12), "short_max": 0.50, "long_min": 0.05},
    },
    "en": {
        "register": {"mean": (10, 14), "short_max": 0.50, "long_min": 0.00},
        "note": {"mean": (15, 20), "short_max": 0.25, "long_min": 0.25},
        "letter": {"mean": (10, 15), "short_max": 0.40, "long_min": 0.00},
    },
}

BAND_TITLES = {
    "register": "ведомости, подписи, перечни / registers, labels, lists",
    "note": "состав работ, записка, концепция / scope of work, note, concept",
    "letter": "письмо, объявление / letter, announcement",
}

# Подписи вывода идут на языке текста. Ключи находок внутри программы
# русские и не меняются, на них стоят проверки в tests/.
MSG = {
    "ru": {
        "sentences": "предложений", "mean": "средняя", "norm": "норма",
        "short": "коротких", "long": "длинных", "run": "подряд коротких",
        "limit": "предел", "over": "длиннее", "none": "находок нет",
        "no_prose": "прозы не найдено",
        "total": "итог: нарушений {e}, к просмотру {w}",
        "mean_out": "средняя {mean:.1f} вне полосы {lo}-{hi}",
        "short_out": "коротких {pct:.0f} %, предел {lim:.0f} %",
        "long_out": "длинных {pct:.1f} %, нужно от {lim:.0f} %",
        "run_out": "подряд коротких {run} при пределе {lim}: {s}...",
        "len_err": "{w} слов при пределе {lim}: {s}...",
        "len_warn": "{w} слов, смотреть глазами: {s}...",
        "yo": "буква ё портится при передаче",
        "space": "пробел ломает командную строку",
        "ascii": "знаки вне ASCII: {bad}",
    },
    "en": {
        "sentences": "sentences", "mean": "mean", "norm": "norm",
        "short": "short", "long": "long", "run": "short in a row",
        "limit": "limit", "over": "longer than", "none": "no findings",
        "no_prose": "no prose found",
        "total": "total: breaches {e}, for the eye {w}",
        "mean_out": "mean {mean:.1f} outside the band {lo}-{hi}",
        "short_out": "short {pct:.0f} %, limit {lim:.0f} %",
        "long_out": "long {pct:.1f} %, needs {lim:.0f} % or more",
        "run_out": "{run} short sentences in a row, limit {lim}: {s}...",
        "len_err": "{w} words, limit {lim}: {s}...",
        "len_warn": "{w} words, look at it: {s}...",
        "yo": "the letter ё breaks in transfer",
        "space": "a space breaks the command line",
        "ascii": "characters outside ASCII: {bad}",
    },
}

KIND_EN = {
    "ритм / rhythm": "rhythm",
    "длина": "length",
    "стоп-слово / stop word": "stop word",
    "длинное тире": "em dash",
    "точка с запятой": "semicolon",
    "математический минус": "mathematical minus",
    "абзац открывается «А потом»": "paragraph opens with «А потом»",
    "двоеточие внутри предложения": "colon inside a sentence",
    "возможная сцепка / comma splice": "possible comma splice",
    "имя файла": "file name",
}


def msg(lang, key, **kw):
    return MSG[lang][key].format(**kw)


SHORT_WORDS = 8  # предложение считается коротким при длине до этого числа
LONG_WORDS = 19  # и длинным начиная с этого
MAX_SHORT_RUN = 3  # подряд коротких предложений не больше

# Стоп-слова. У каждого записана замена: без неё запрет применяют
# вычёркиванием, потому что вычеркнуть дешевле, чем переписать.
STOP_WORDS = {
    "ru": [
        (r"честн(ый|ее|ая|ое|ые|о)", "корректнее, правильнее"),
        (r"вр(ать|ёт|ет|ут|ал|ала)", "корректнее, правильнее"),
        (r"главные грабли", "главная ошибка"),
        (r"софт(а|у|ом|е)?", "программа, пакет"),
        (r"кучк(а|и|е|у|ой)", "группа, набор"),
        (r"членени(е|я|ю|ем)", "разбивка на участки"),
        (r"наблюдённ(ый|ая|ое|ые|ых|ым)", "наблюдаемый"),
        (r"мерк(а|и|е|у|ой)", "измеритель про инструмент, измерение про действие"),
        (r"глад(ь|и|ью)", "поверхность, урез воды"),
        (r"скучн(ый|ая|ое|ые|о)", "по смыслу места"),
        (r"лаг(а|у|ом|е|и)?", "расстояние про пару, шаг про параметр"),
        (r"предъявить", "описанием действия"),
        (r"соблазн(а|у|ом|е)?", "по смыслу места"),
        (r"лесенк(а|и|е|у|ой)", "по смыслу места"),
        (r"сходит с рук", "по смыслу места"),
        (r"деваться некуда", "по смыслу места"),
        (r"вперемешку", "по смыслу места"),
        (r"крутить параметры", "подбирать параметры"),
        (r"руками", "вручную"),
        (r"кучу", "количество, набор"),
        (r"под рукой", "доступен, имеется"),
        (r"мелоч(ь|и|ью)", "по смыслу места"),
        (r"молча", "без сообщения, без записи об ошибке"),
    ],
    "en": [
        (r"leverage[sd]?", "use"),
        (r"utili[sz]e[sd]?", "use"),
        (r"in order to", "to"),
        (r"simply", "nothing, cut the word"),
        (r"obviously", "nothing, cut the word"),
        (r"seamless(ly)?", "what the thing actually does"),
        (r"robust", "what the thing actually does"),
        (r"powerful", "what the thing actually does"),
        (r"easy to use", "the number of steps it takes"),
        (r"intuitive", "the number of steps it takes"),
        (r"state of the art", "the measured figure"),
        (r"best in class", "the measured figure"),
        (r"a number of", "the count, or nothing"),
    ],
}

# Зацепка на сцепку. Измеритель только показывает место, решение за человеком:
# английская запятая перед самостоятельным предложением грамматике противоречит,
# но та же запятая после придаточного законна, и различает их смысл.
SPLICE = (r",\s+(it|this|these|those|they|there|we|he|she)\s+"
          r"(is|are|was|were|has|have|had|does|do|did|will|can|may)\b")

SUBORDINATOR = re.compile(
    r"\b(when|if|because|although|though|while|after|before|since|unless|"
    r"until|whereas|as|once|where)\b", re.IGNORECASE)


# --------------------------------------------------------------------------
# Разбор текста
# --------------------------------------------------------------------------

# Значок это картинка внутри ссылки. Строка из одних значков - разметка.
BADGE = r"\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)"
BADGE_LINE = re.compile(r"(?:%s|\s)+" % BADGE)

# Ссылка markdown. В счёт идёт её текст, адрес словами не считается.
LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")

# Сущность html - один знак, а её точка с запятой пунктуацией не является.
ENTITY = re.compile(r"&(?:[A-Za-z][A-Za-z0-9]{1,10}|#\d{1,5}|#x[0-9A-Fa-f]{1,5});")


def detect_lang(text: str) -> str:
    cyr = len(re.findall(r"[А-Яа-яЁё]", text))
    lat = len(re.findall(r"[A-Za-z]", text))
    return "ru" if cyr > lat else "en"


def prose_lines(text: str):
    """Строки прозы. Заголовки, строки таблиц и блоки кода прозой не считаются.

    Слева от двоеточия в подписи таблицы, в заголовке раздела, в подписи к
    рисунку и в графе ведомости стоит имя, а не предложение, поэтому такие
    строки в счёт не идут.
    """
    out = []
    in_code = False
    in_item = False
    for ln, raw in enumerate(text.splitlines(), 1):
        s = raw.strip()
        if s.startswith("```") or s.startswith("~~~"):
            in_code = not in_code
            in_item = False
            continue
        if in_code:
            continue
        # Пустая строка и заголовок закрывают абзац, а прозой не являются.
        if not s or s.startswith("#") or s.startswith("|") \
                or s.startswith(">") or s.startswith("!["):
            out.append((None, False, ln))
            in_item = False
            continue
        # Строка значков - разметка, а не текст. Значок это картинка в
        # ссылке, и строка из одних значков слов автора не содержит.
        if BADGE_LINE.fullmatch(s):
            out.append((None, False, ln))
            in_item = False
            continue
        item = bool(re.match(r"^([-*+]\s+|\d+[.)]\s+)", s))
        # Пункт перечня, продолженный на следующей строке с отступом, это
        # один пункт. Иначе его продолжение считается своим предложением, и
        # перечень рассыпается на обрывки.
        if in_item and not item and raw[:1].isspace() and out and out[-1][0]:
            out[-1] = (out[-1][0] + " " + s, out[-1][1], out[-1][2])
            continue
        s = re.sub(r"^([-*+]\s+|\d+[.)]\s+)", "", s)
        in_item = item
        out.append((s, item, ln))
    return out


def sentences_at(text: str):
    """Предложения прозы, каждое с пометкой «строка перечня» и номером строки.

    Номер нужен обёрткам продуктов: находка без места в файле заставляет
    искать её глазами по всему тексту.

    Подпись абзаца вида **Пунктуация.** предложением не считается: слева
    стоит имя раздела, а не утверждение. Угловые скобки образца закрывают
    подстановку, поэтому конец подстановки завершает предложение.
    """
    chunks = []
    buf = []
    at = 0
    for s, item, ln in prose_lines(text):
        if s is None or item:
            if buf:
                chunks.append((" ".join(buf), False, at))
                buf = []
            if item:
                chunks.append((s, True, ln))
        else:
            if not buf:
                at = ln
            buf.append(s)
    if buf:
        chunks.append((" ".join(buf), False, at))


    out = []
    for chunk, is_item, at in chunks:
        first = True
        body = re.sub(r"[ \t]+", " ", chunk)
        body = re.sub(r"`[^`]*`", "CODE", body)
        # Картинка слов не содержит, а у ссылки в счёт идёт только текст:
        # закодированный адрес иначе даёт десятки мнимых слов.
        body = IMAGE.sub(" ", body)
        body = LINK.sub(r"\1", body)
        # Сущность html это знак, а не пунктуация: «&nbsp;» иначе читается
        # как точка с запятой.
        body = ENTITY.sub(" ", body)
        body = re.sub(r"^\*\*.+?\*\*\s*", "", body)
        # Предложение начинается и с цифры, и со ссылки, и с жирного слова:
        # «15 января 2026 года…» и «**collar** это…» стоят после точки так
        # же, как заглавная буква. Звёздочки снимаются после деления, иначе
        # жирное слово со строчной буквы к делению не подходит.
        body = re.sub(r"(?<=[.!?>])\s+(?=[A-ZА-ЯЁ«\"(<\[0-9*])", "\n", body)
        body = re.sub(r"\*\*(.+?)\*\*", r"\1", body)
        for p in body.split("\n"):
            p = p.strip()
            if len(p) < 2:
                continue
            # Угловые скобки образца - место подстановки, а не текст автора.
            if re.fullmatch(r"<[^<>]*>[.,]?", p):
                continue
            out.append((p, is_item, first, at))
            first = False
    return out


def sentences(text: str):
    """Предложения прозы без номера строки, по три поля на каждое."""
    return [(p, is_item, first) for p, is_item, first, _ in sentences_at(text)]


def strip_mentions(s: str) -> str:
    """Убирает закавыченные слова: упоминание слова не есть его употребление."""
    s = re.sub(r"«[^»]{1,40}»", " ", s)
    s = re.sub(r'"[^"]{1,40}"', " ", s)
    return s


def word_count(s: str) -> int:
    return len(re.findall(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9'-]*", s))


# --------------------------------------------------------------------------
# Проверки
# --------------------------------------------------------------------------

def check_rhythm(pairs, lang, band):
    sents = [s for s, _, _ in pairs]
    lens = [word_count(s) for s in sents]
    n = len(lens)
    if n == 0:
        return {}, []
    spec = BANDS[lang][band]
    lim = LIMITS[lang]

    short = [w for w in lens if w <= SHORT_WORDS]
    long_ = [w for w in lens if w >= LONG_WORDS]
    mean = sum(lens) / n

    # Абзац целиком из коротких допустим, когда он и есть перечень, поэтому
    # строки перечня в счёт подряд идущих коротких не входят.
    run = best = 0
    run_at = best_at = 0
    for i, (w, (_, is_item, is_first)) in enumerate(zip(lens, pairs)):
        if is_first:
            run = 0
        if is_item:
            run = 0
            continue
        if w <= SHORT_WORDS:
            run += 1
            if run == 1:
                run_at = i
        else:
            run = 0
        if run > best:
            best, best_at = run, run_at

    findings = []
    lo, hi = spec["mean"]
    if not lo <= mean <= hi:
        findings.append(("error", "ритм / rhythm",
                         msg(lang, "mean_out", mean=mean, lo=lo, hi=hi)))
    if len(short) / n > spec["short_max"]:
        findings.append(("error", "ритм / rhythm",
                         msg(lang, "short_out", pct=100 * len(short) / n,
                             lim=100 * spec["short_max"])))
    if len(long_) / n < spec["long_min"]:
        findings.append(("error", "ритм / rhythm",
                         msg(lang, "long_out", pct=100 * len(long_) / n,
                             lim=100 * spec["long_min"])))
    if best > MAX_SHORT_RUN:
        findings.append(("warn", "ритм / rhythm",
                         msg(lang, "run_out", run=best, lim=MAX_SHORT_RUN,
                             s=sents[best_at][:60])))

    for s, w in zip(sents, lens):
        if w > lim["error"]:
            findings.append(("error", "длина",
                             msg(lang, "len_err", w=w, lim=lim["error"], s=s[:90])))
        elif w > lim["warn"]:
            findings.append(("warn", "длина",
                             msg(lang, "len_warn", w=w, s=s[:90])))

    stats = {
        "sentences": n,
        "mean": mean,
        "short": len(short),
        "short_pct": 100 * len(short) / n,
        "long": len(long_),
        "long_pct": 100 * len(long_) / n,
        "run": best,
        "band": band,
        "mean_band": f"{lo}-{hi}",
        "over_warn": sum(1 for w in lens if w > lim["warn"]),
        "over_error": sum(1 for w in lens if w > lim["error"]),
        "warn_at": lim["warn"],
        "error_at": lim["error"],
    }
    return stats, findings


def check_words(pairs, lang):
    findings = []
    body = strip_mentions(" ".join(s for s, _, _ in pairs))
    for pattern, replacement in STOP_WORDS[lang]:
        for m in re.finditer(r"\b" + pattern + r"\b", body, re.IGNORECASE):
            findings.append(("error", "стоп-слово / stop word",
                             f"«{m.group(0)}» -> {replacement}"))
    return findings


def check_punctuation(pairs, lang):
    findings = []
    if lang == "ru":
        for s, is_item, _ in pairs:
            if "—" in s or "–" in s:
                findings.append(("error", "длинное тире", s[:80]))
            if "−" in s:
                findings.append(("error", "математический минус", s[:80]))
            if s.startswith("А потом"):
                findings.append(("error", "абзац открывается «А потом»", s[:60]))
            if is_item:
                # Строка перечня. Точка с запятой в конце и двоеточие в
                # заголовке перечня нарушением прозы не считаются.
                continue
            if ";" in s:
                findings.append(("error", "точка с запятой", s[:80]))
            if s.rstrip().endswith(":"):
                continue
            bare = strip_mentions(s)
            for m in re.finditer(r"(?<![\d\s]):\s+\S", bare):
                tail = bare[m.start() + 1:]
                # Двоеточие перед перечнем законно, перечень виден по запятым.
                if "," in tail:
                    continue
                findings.append(("warn", "двоеточие внутри предложения",
                                 s[:80]))
                break
    else:
        for s, _, _ in pairs:
            if SUBORDINATOR.match(s):
                # Придаточное впереди, запятая отделяет его от главного.
                continue
            for m in re.finditer(SPLICE, s, re.IGNORECASE):
                head = s[:m.start()]
                if SUBORDINATOR.search(head) or "that is" in m.group(0).lower():
                    continue
                if not re.search(r"\b(is|are|was|were|has|have|had|does|do|"
                                 r"did|will|can|may|goes|runs|stays|holds)\b",
                                 head, re.IGNORECASE):
                    continue
                findings.append(("warn", "возможная сцепка / comma splice",
                                 s[:90]))
                break
    return findings


def check_filename(path: Path, lang: str):
    findings = []
    name = path.name
    if "ё" in name or "Ё" in name:
        findings.append(("error", "имя файла", msg(lang, "yo")))
    if " " in name:
        findings.append(("error", "имя файла", msg(lang, "space")))
    if any(ord(c) > 127 for c in name):
        bad = "".join(sorted({c for c in name if ord(c) > 127}))
        findings.append(("warn", "имя файла", msg(lang, "ascii", bad=bad)))
    return findings


# --------------------------------------------------------------------------
# Вывод
# --------------------------------------------------------------------------

def report(path: Path, lang: str, band: str, stats, findings, quiet=False):
    L = lambda key: msg(lang, key)  # noqa: E731
    title = BAND_TITLES[band].split(" / ")[0 if lang == "ru" else 1]
    print(f"== {path.name}   [{lang}, {band}: {title}]")
    if not stats:
        print("   " + L("no_prose"))
        return 0
    w = 16
    print(f"   {L('sentences'):<{w}} {stats['sentences']}")
    print(f"   {L('mean'):<{w}} {stats['mean']:.1f}   {L('norm')} {stats['mean_band']}")
    print(f"   {L('short') + ' <=' + str(SHORT_WORDS):<{w}} {stats['short']}  "
          f"{stats['short_pct']:.0f} %")
    print(f"   {L('long') + ' >=' + str(LONG_WORDS):<{w}} {stats['long']}  "
          f"{stats['long_pct']:.0f} %")
    print(f"   {L('run'):<{w}} {stats['run']}   {L('limit')} {MAX_SHORT_RUN}")
    print(f"   {L('over') + ' ' + str(stats['warn_at']):<{w}} {stats['over_warn']}")
    print(f"   {L('over') + ' ' + str(stats['error_at']):<{w}} {stats['over_error']}"
          f"   {L('limit')}")

    errors = [f for f in findings if f[0] == "error"]
    warns = [f for f in findings if f[0] == "warn"]
    if not errors and not warns:
        print("   " + L("none"))
    for level, kind, detail in (errors if quiet else errors + warns):
        mark = "!" if level == "error" else "?"
        shown = KIND_EN.get(kind, kind) if lang == "en" else kind.split(" / ")[0]
        print(f"   {mark} {shown}: {detail}")
    print("   " + msg(lang, "total", e=len(errors), w=len(warns)))
    print()
    return len(errors)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Измеритель текста по своду RULES")
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--lang", choices=["ru", "en"],
                    help="язык текста, по умолчанию определяется по доле кириллицы")
    ap.add_argument("--band", choices=list(BANDS["ru"]), default="note",
                    help="полоса ритма, по умолчанию note")
    ap.add_argument("--quiet", action="store_true",
                    help="показывать только нарушения, без замечаний к просмотру")
    args = ap.parse_args(argv)

    total = 0
    for path in args.files:
        text = path.read_text(encoding="utf-8")
        text = unicodedata.normalize("NFC", text)
        lang = args.lang or detect_lang(text)
        sents = sentences(text)
        stats, findings = check_rhythm(sents, lang, args.band)
        findings += check_words(sents, lang)
        findings += check_punctuation(sents, lang)
        findings += check_filename(path, lang)
        total += report(path, lang, args.band, stats, findings, args.quiet)

    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
