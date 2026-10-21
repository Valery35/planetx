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
Поиск (Index.search) - по основам слов: слово запроса длиннее
STEM_LONG знаков обрезается на STEM_CUT знака, но не короче STEM_MIN,
и совпадает со всеми словами раздела, которые с этой основы
начинаются. Так «модель ветряка» находит «модели» и «ветряки». Слово
в заголовке весит TITLE_WEIGHT, в тексте - 1, при равенстве выше
раздел, где слова встречаются чаще. Подходит раздел, где нашлась хотя
бы половина значимых слов запроса. Вопросительные и служебные слова
(STOP) не считаются. Морфологии нет, приставки и чередования основ не узнаются.
"""
import bisect
import json
import re

# Основа слова: длиннее STEM_LONG знаков - без последних STEM_CUT,
# но не короче STEM_MIN. Выбор помощника.
STEM_LONG = 5
STEM_CUT = 3
STEM_MIN = 5
# Вес слова, найденного в заголовке раздела, против слова в тексте.
TITLE_WEIGHT = 3
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
    """Основа слова запроса для сравнения началом."""
    if len(word) > STEM_LONG:
        return word[:max(STEM_MIN, len(word) - STEM_CUT)]
    return word


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


class Index:
    """Разделы руководства с наборами слов заголовка и текста."""

    def __init__(self, items):
        self.items = [tuple(item) for item in items]
        # Слово - номера разделов с ним в заголовке и в тексте. Слова
        # отсортированы: основа ищется делением пополам, а не перебором.
        self._title = {}
        self._text = {}  # слово - {номер раздела: сколько раз}
        for n, (title, _, text) in enumerate(self.items):
            for w in set(words(title)):
                self._title.setdefault(w, set()).add(n)
            for w in words(text):
                seen = self._text.setdefault(w, {})
                seen[n] = seen.get(n, 0) + 1
        self._vocab = sorted(set(self._title) | set(self._text))

    def _having(self, prefix):
        """Разделы со словом на prefix: номера с ним в заголовке
        и {номер: сколько раз в тексте}."""
        title, text = set(), {}
        n = bisect.bisect_left(self._vocab, prefix)
        while n < len(self._vocab) and self._vocab[n].startswith(prefix):
            w = self._vocab[n]
            title |= self._title.get(w, set())
            for k, count in self._text.get(w, {}).items():
                text[k] = text.get(k, 0) + count
            n += 1
        return title, text

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
        for s in stems:
            title, text = self._having(s)
            for n in title | set(text):
                score[n] = score.get(n, 0) + (TITLE_WEIGHT if n in title
                                              else 1)
                hits[n] = hits.get(n, 0) + 1
                # Вхождения в тексте - не больше OFTEN на слово, иначе
                # длинный раздел перевешивал бы точный.
                often[n] = often.get(n, 0) + min(text.get(n, 0), OFTEN)
        scored = [(-score[n], -often[n], -hits[n], n)
                  for n in score if hits[n] >= need]
        scored.sort()
        return [n for _, _, _, n in scored[:limit]]

    def snippet(self, n, query, size=SNIPPET):
        """Абзац раздела n, где больше всего слов запроса, не длиннее
        size знаков, без разметки таблиц и выделения."""
        stems = self.stems(query)
        best, found = "", -1
        for part in re.split(r"\n\s*\n", self.items[n][2]):
            have = words(part)
            hit = sum(1 for s in stems if any(w.startswith(s) for w in have))
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
