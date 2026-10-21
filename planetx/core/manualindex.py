# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Поиск по руководству для строки «Поиск». Без Qt.

Просьба автора от 20 октября 2026 года - «умная документация» из пакета
задач Telegram-бота, но внутри модуля, без сервера и ключей. Руководство
doc/MANUAL.md и doc/MANUAL.en.md режется по заголовкам ## - #### на
разделы (sections), tools/build_manual_index.py пишет их в
data/manual_ru.json и manual_en.json - папки doc в архиве модуля нет.

Раздел - [заголовок, якорь GitHub, текст Markdown без картинок].
Поиск (Index.search) - по основам слов: у слова запроса снимается
окончание (stem), основа совпадает со всеми словами раздела, которые
с неё начинаются. Так «модель ветряка» находит «модели» и «ветряки».
Синонимы и чередования основ («снимок» - «снимки», «экспорт» -
«выгрузка») - группы SYNONYMS. Раздел ранжируется сначала по лучшему
абзацу - сколько слов запроса в одном абзаце вместе с заголовком,
затем по словам в заголовке и по весу: слово в заголовке весит
TITLE_WEIGHT, в тексте - 1, при равенстве выше раздел, где слова
встречаются чаще. Подходит раздел, где нашлась хотя бы половина
значимых слов запроса. Вопросительные и служебные слова (STOP) не
считаются. Полной морфологии нет, приставки не узнаются.
"""
import bisect
import json
import re

# Основа слова запроса не короче STEM_MIN знаков. Выбор помощника.
STEM_MIN = 3
# Вес слова, найденного в заголовке раздела, против слова в тексте.
TITLE_WEIGHT = 3
# Слово запроса в заголовке раздела добавляет к лучшему абзацу эту долю:
# раздел о самом предмете вопроса выше строки таблицы, где все слова
# стоят рядом. Выбор помощника по пробным вопросам.
HEAD_SHARE = 0.5
# Строка таблицы засчитывается абзацем на эту долю слова меньше:
# при равном покрытии выше обычный абзац.
ROW_PENALTY = 0.5
# Разделов в подсказках не больше.
LIMIT = 3
# Запрос короче - разделы руководства не ищутся.
MIN_QUERY = 4
# Вхождений слова в тексте раздела в счёт не больше.
OFTEN = 8
# Длина фрагмента под подсказкой, знаков.
SNIPPET = 160

STOP = frozenset((
    "как", "где", "что", "чем", "зачем", "почему", "какой", "какая",
    "какие", "каким", "можно", "нельзя", "нужно", "надо", "ли", "это",
    "этот", "эта", "эти", "для", "при", "или", "без", "под", "над", "про",
    "мне", "меня", "мой", "моя", "мои", "свой", "свою", "сделать", "есть",
    "the", "and", "for", "how", "what", "where", "why", "can", "does",
    "with", "from", "into", "this", "that", "are", "you", "your", "use"))

# Окончания, которые снимает основа слова запроса, длинные первыми.
ENDINGS_RU = (
    "иями", "ями", "ами", "ого", "его", "ому", "ему", "ыми", "ими",
    "ать", "ять", "ить", "еть", "ует", "ают", "яют", "ует",
    "ой", "ей", "ий", "ый", "ая", "яя", "ое", "ее", "ые", "ие", "ую",
    "юю", "ов", "ев", "ам", "ям", "ах", "ях", "ом", "ем", "ию", "ия",
    "ет", "ит", "ут", "ют", "ть",
    "а", "я", "о", "е", "и", "ы", "у", "ю", "ь", "й")
ENDINGS_EN = ("ing", "ies", "es", "ed", "s")
# Основы, которые запрос считает одним словом: синонимы и чередования
# основ, которых обрезка окончаний не ловит («снимок» - «снимки»).
# Выбор помощника по пробным вопросам к руководствам линейки.
SYNONYMS = (
    ("выгруз", "экспорт"),
    ("измер", "линейк", "расстоя", "длин"),
    ("анимац", "анимир", "анимиров"),
    ("видео", "ролик", "mp4"),
    ("снимо", "снимк"),
    ("удали", "удал", "убра"),
    ("тен", "тень", "инсоляц"),
    ("export", "save"),
    ("distance", "length", "measure", "ruler"),
    ("video", "movie", "clip", "mp4"),
    ("shadow", "insolation"),
)

_HEADING = re.compile(r"^(#{2,4})\s+(.*?)\s*#*\s*$")
_IMAGE = re.compile(r"^\s*!\[[^\]]*\]\([^)]*\)\s*$")
_WORD = re.compile(r"\w+", re.UNICODE)
_SLUG_DROP = re.compile(r"[^\w\- ]", re.UNICODE)
# Разметка Markdown во фрагменте: столбцы таблиц, выделение, код.
_MARKUP = re.compile(r"[|*`#]+|^-{3,}$", re.MULTILINE)


def words(text):
    """Слова текста в нижнем регистре, ё как е, без цифр отдельно."""
    return [w for w in _WORD.findall((text or "").lower().replace("ё", "е"))
            if not w.isdigit()]


def stem(word):
    """Основа слова запроса для сравнения началом: без окончания из
    ENDINGS_RU или ENDINGS_EN, не короче STEM_MIN знаков. «картой»
    находит «карта» и «карты», «ветряков» - «ветряки»."""
    ends = ENDINGS_EN if word.isascii() else ENDINGS_RU
    for end in ends:
        if word.endswith(end) and len(word) - len(end) >= STEM_MIN:
            return word[:-len(end)]
    return word


def alternatives(base):
    """Основы, которые считаются одним словом запроса: сама основа и её
    группа SYNONYMS, если основа начинается с основы группы или группа
    с неё."""
    out = [base]
    for group in SYNONYMS:
        if any(base.startswith(g) or g.startswith(base) for g in group):
            out.extend(g for g in group if g not in out)
    return out


def slug(title, taken):
    """Якорь заголовка, как его ставит GitHub: нижний регистр, без
    знаков препинания, пробелы - дефисы, повтор - с номером -1, -2.
    taken - словарь уже выданных якорей, он пополняется."""
    base = _SLUG_DROP.sub("", title.strip().lower()).replace(" ", "-")
    count = taken.get(base, 0)
    taken[base] = count + 1
    return base if not count else "{}-{}".format(base, count)


def sections(markdown):
    """Разделы руководства: [[заголовок, якорь, текст]]. Строки внутри
    ```...``` заголовками не считаются, строки-картинки снимаются."""
    out = []
    taken = {}
    title = anchor = None
    lines = []
    fence = False

    def close():
        if title is not None:
            out.append([title, anchor, "\n".join(lines).strip()])

    for line in (markdown or "").splitlines():
        if line.lstrip().startswith("```"):
            fence = not fence
        found = None if fence else _HEADING.match(line)
        if line.startswith("# ") and not fence:
            slug(line[2:], taken)  # заголовок документа - тоже якорь
            continue
        if found:
            close()
            title = found.group(2)
            anchor = slug(title, taken)
            lines = []
            continue
        if title is not None and not _IMAGE.match(line):
            lines.append(line)
    close()
    return out


def parts(text):
    """Абзацы текста раздела для оценки близости слов: [(текст, строка
    таблицы ли)]. Строка таблицы Markdown - свой абзац: таблица демо
    и источников иначе собрала бы в один абзац слова всех тем."""
    out = []
    for part in re.split(r"\n\s*\n", text):
        lines = part.splitlines()
        if lines and all(line.lstrip().startswith("|") for line in lines):
            out.extend((line, True) for line in lines)
        else:
            out.append((part, False))
    return out


class Index:
    """Разделы руководства с наборами слов заголовка и текста."""

    def __init__(self, items):
        self.items = [tuple(item) for item in items]
        # Слово - номера разделов с ним в заголовке, в тексте и номера
        # абзацев с ним. Слова отсортированы: основа ищется делением
        # пополам, а не перебором.
        self._title = {}
        self._text = {}  # слово - {номер раздела: сколько раз}
        self._para = {}  # слово - номера абзацев
        self._owner = []  # абзац - номер раздела
        self._row = set()  # абзацы - строки таблиц
        for n, (title, _, text) in enumerate(self.items):
            for w in set(words(title)):
                self._title.setdefault(w, set()).add(n)
            for w in words(text):
                seen = self._text.setdefault(w, {})
                seen[n] = seen.get(n, 0) + 1
            for part, row in parts(text):
                if row:
                    self._row.add(len(self._owner))
                for w in set(words(part)):
                    self._para.setdefault(w, set()).add(len(self._owner))
                self._owner.append(n)
        self._vocab = sorted(set(self._title) | set(self._text))

    def _having(self, prefixes):
        """Разделы со словом на одну из основ prefixes: номера с ним
        в заголовке, {номер: сколько раз в тексте} и номера абзацев."""
        title, text, paras = set(), {}, set()
        for prefix in prefixes:
            n = bisect.bisect_left(self._vocab, prefix)
            while (n < len(self._vocab)
                   and self._vocab[n].startswith(prefix)):
                w = self._vocab[n]
                title |= self._title.get(w, set())
                for k, count in self._text.get(w, {}).items():
                    text[k] = text.get(k, 0) + count
                paras |= self._para.get(w, set())
                n += 1
        return title, text, paras

    @classmethod
    def from_json(cls, text):
        return cls(json.loads(text))

    def __len__(self):
        return len(self.items)

    def search(self, query, limit=LIMIT):
        """Номера разделов к запросу, лучшие первыми."""
        if len((query or "").strip()) < MIN_QUERY:
            return []
        stems = self.stems(query)
        if not stems:
            return []
        need = (len(stems) + 1) // 2
        score, hits, often = {}, {}, {}
        # Абзац - сколько слов запроса в нём и в заголовке его раздела.
        # Раздел ранжируется сначала по лучшему абзацу: в длинном разделе
        # слова, разбросанные по разным абзацам, весят меньше, чем все
        # слова вопроса в одном абзаце.
        found = []  # слово запроса - (разделы по заголовку, абзацы)
        for s in stems:
            title, text, paras = self._having(alternatives(s))
            found.append((title, paras))
            for n in title | set(text):
                score[n] = score.get(n, 0) + (TITLE_WEIGHT if n in title
                                              else 1)
                hits[n] = hits.get(n, 0) + 1
                # Вхождения в тексте - не больше OFTEN на слово, иначе
                # длинный раздел перевешивал бы точный.
                often[n] = often.get(n, 0) + min(text.get(n, 0), OFTEN)
        # Слово заголовка дополняет любой абзац своего раздела.
        heads = {n: sum(1 for title, _ in found if n in title)
                 for n in score}
        best = dict(heads)
        for p in set().union(*(paras for _, paras in found)):
            n = self._owner[p]
            if n in best:
                count = sum(1 for title, paras in found
                            if p in paras or n in title)
                if p in self._row:
                    # Строка таблицы - перечень: слова в ней рядом,
                    # но о предмете вопроса там одна строка.
                    count -= ROW_PENALTY
                best[n] = max(best[n], count)
        scored = [(-best[n] - HEAD_SHARE * heads[n], -heads[n], -score[n],
                   -often[n], -hits[n], n)
                  for n in score if hits[n] >= need]
        scored.sort()
        return [item[-1] for item in scored[:limit]]

    def snippet(self, n, query, size=SNIPPET):
        """Абзац раздела n, где больше всего слов запроса, не длиннее
        size знаков, без разметки таблиц и выделения."""
        groups = [alternatives(s) for s in self.stems(query)]
        best, found = "", -1
        for part in re.split(r"\n\s*\n", self.items[n][2]):
            have = words(part)
            hit = sum(1 for group in groups
                      if any(w.startswith(g) for w in have for g in group))
            if hit > found:
                best, found = part, hit
        text = " ".join(_MARKUP.sub(" ", best).split())
        if len(text) > size:
            text = text[:size].rsplit(" ", 1)[0] + "…"
        return text

    def stems(self, query):
        """Основы значимых слов запроса без повторов."""
        out = []
        for word in words(query):
            if len(word) < 3 or word in STOP:
                continue
            s = stem(word)
            if s not in out:
                out.append(s)
        return out

    def find(self, anchor):
        """Номер раздела по якорю или None."""
        for n, (_, a, _) in enumerate(self.items):
            if a == anchor:
                return n
        return None
