# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Бот PlanetX в Telegram. Только стандартная библиотека Python.

Запуск - Python 3.9 и новее, например из состава QGIS:

    python bot/planetx_bot.py

Два способа работы:
- опрос - бот опрашивает Telegram сам (getUpdates с долгим ожиданием),
  сервер с внешним адресом не нужен, работает, пока запущен;
- приём на сервере - application, приложение WSGI (PythonAnywhere),
  адрес ставит `planetx_bot.py --webhook https://адрес`, порядок -
  bot/DEPLOY.md. Запуск опросом снимает адрес приёма.

Токен - переменная окружения PLANETX_BOT_TOKEN или поле token файла
настроек CONFIG (%APPDATA%\\PlanetX-bot\\config.json, вне Windows -
~/.config/PlanetX-bot/config.json). В хранилище токена нет. Поле
owner - номер чата автора, туда идут сообщения /report, свой номер
бот называет по /id. Поле secret - секрет адреса приёма. Поле
channel - канал постов о выпусках (@имя или номер), бот в нём
администратор.

Посты о выпусках. Автор пишет /post [метка] или нажимает «Подготовить
пост» в сообщении о выпуске, которое шлёт GitHub Actions
(.github/workflows/telegram-release.yml). Бот присылает автору
черновик с кнопкой «Опубликовать», кнопка ставит пост в канал. Кнопки
и /post действуют только у автора (owner).

Ответы:
- /latest - последний выпуск на GitHub, что нового, архив;
- /docs - руководство;
- текст в личном чате - разделы руководств модулей линейки, поиск
  core/manualindex.py по указателю bot/data/manuals_ru.json или
  manuals_en.json (собирает bot/build_index.py), имя модуля в вопросе
  ограничивает поиск его руководством, кнопка под разделом присылает
  его текст;
- /report текст - сообщение автору.
"""
import hmac
import html
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.join(os.path.dirname(HERE), "planetx")
sys.path.insert(0, os.path.join(PLUGIN, "core"))
import manualindex  # noqa: E402

OWNER = "Valery35"
REPOSITORY = "https://github.com/Valery35/planetx"
RELEASES = "https://api.github.com/repos/Valery35/{}/releases/{}"
# Язык постов о выпусках в канале.
CHANNEL_LANG = "ru"
# Посты о выпусках идут из любого хранилища OWNER. Название модуля
# и адрес в каталоге QGIS - по имени хранилища, без записи - имя
# хранилища и без кнопки каталога.
PLUGINS = {
    "planetx": ("PlanetX", "https://plugins.qgis.org/plugins/planetx/"),
    "qgis-isoliner": ("Isoliner",
                      "https://plugins.qgis.org/plugins/grid_isolines/"),
    "qgis-isoliner3d": ("Isoliner3D",
                        "https://plugins.qgis.org/plugins/isoliner3d/"),
    "topoliner": ("Topoliner",
                  "https://plugins.qgis.org/plugins/topoliner/"),
    "routeliner": ("Routeliner",
                   "https://plugins.qgis.org/plugins/routeliner/"),
    "repoliner": ("Repoliner",
                  "https://plugins.qgis.org/plugins/repoliner/"),
    "planetx-lite": ("PlanetX Lite", None),
}
# Слова вопроса, которые ограничивают поиск руководством PlanetX Lite.
LITE_WORDS = ("lite", "лайт", "лайте", "лайта", "лайтом", "planetx-lite")
# Страница в браузере у программ без каталога QGIS, для /docs.
WEB_PAGES = {
    "planetx-lite": "https://valery35.github.io/planetx-lite/",
}
# Страницы программ на сайте www.informpp.ru, для /docs.
SITE_PAGES = {
    "planetx-lite": "https://www.informpp.ru/главная-страница/planetx-lite",
}
# Что делает модуль, для /docs - по описаниям metadata.txt модулей.
ABOUT = {
    "ru": {
        "planetx": "трёхмерный глобус внутри QGIS",
        "qgis-isoliner": "кригинг и изолинии, контурные полигоны",
        "qgis-isoliner3d": "3D-просмотр поверхностей, пластов, скважин "
                           "и подсчёт запасов",
        "topoliner": "проверка и исправление топологии линий "
                     "и полигонов",
        "routeliner": "события на трассе и пикетаж, продольные профили",
        "repoliner": "свой репозиторий модулей QGIS из архивов",
        "planetx-lite": "глобус PlanetX без QGIS - программа для "
                        "Windows, Linux и macOS и страница в браузере",
    },
    "en": {
        "planetx": "a 3D globe inside QGIS",
        "qgis-isoliner": "kriging and isolines, contour polygons",
        "qgis-isoliner3d": "3D view of surfaces, beds, boreholes "
                           "and reserves",
        "topoliner": "topology check and cleanup of lines and polygons",
        "routeliner": "route events and chainage, longitudinal profiles",
        "repoliner": "your own QGIS plugin repository from archives",
        "planetx-lite": "the PlanetX globe without QGIS - a program for "
                        "Windows, Linux and macOS and a web page",
    },
}
_REPO = re.compile(r"[A-Za-z0-9_.-]{1,40}")
SITE = "https://www.informpp.ru/главная-страница/qgis-planetx"
CONFIG = os.path.join(
    os.environ.get("APPDATA") or os.path.expanduser("~/.config"),
    "PlanetX-bot", "config.json")
# Путь приёма обновлений Telegram на сервере.
WEBHOOK_PATH = "/telegram"
USER_AGENT = "PlanetX-bot (+https://github.com/Valery35/planetx)"

# Ожидание ответа getUpdates на сервере Telegram и предел запроса, с.
POLL_WAIT = 50
TIMEOUT = 65
# Пауза после ошибки сети, с.
RETRY = 10
# Попытки запроса к Telegram и пауза между ними, с. Прокси бесплатного
# PythonAnywhere время от времени отвечает 503 на соединение, 22-23
# октября 2026 года так пропадали ответы на вопросы.
CALL_TRIES = 3
CALL_PAUSE = 2
# Выпуск с GitHub помнится, с.
RELEASE_KEEP = 600
# Предел текста сообщения Telegram 4096 знаков, берётся с запасом.
TEXT_LIMIT = 3500
# Разделов руководства в ответе не больше.
FOUND = 3

_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_MARKUP = re.compile(r"[*`]+|^\|?[-:| ]{3,}\|?$|^#+\s*", re.MULTILINE)
# Описание выпуска: ссылка Markdown (картинка - с «!»), код, жирный.
_RELEASE_LINK = re.compile(r"(!?)\[([^\]]*)\]\(([^)\s]+)\)")
_CODE = re.compile(r"`([^`\n]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_ITALIC = re.compile(r"(?<![\w*])\*(?!\s)([^*\n]+?)\*(?![\w*])")
_HEADING = re.compile(r"^#+[ \t]*(.+?)[ \t]*#*$", re.MULTILINE)
_BULLET = re.compile(r"^([ \t]*)[*\-+][ \t]+", re.MULTILINE)
_TABLE_RULE = re.compile(r"^\|?[-:| ]{3,}\|?$", re.MULTILINE)
# Имена файлов с расширением - доменной зоной: Telegram делает
# из «isoliner3d.zip» ссылку на сайт http://isoliner3d.zip (задание
# автора от 28 октября 2026 года). Такое имя идёт кодом или ссылкой
# на одноимённый файл выпуска.
FILE_ZONES = ("zip", "mov", "app", "py", "md", "sh", "pl", "rs", "kmz",
              "gz", "ps", "so", "ai", "cs", "tv", "io", "sql")
_FILE_NAME = re.compile(
    r"(?<![\w./@-])([\w.-]+\.(?:%s))(?![\w/-])" % "|".join(FILE_ZONES),
    re.IGNORECASE)

TEXTS = {
    "ru": {
        "start": (
            "Это бот модулей QGIS PlanetX, Isoliner, Isoliner3D, "
            "Topoliner, Routeliner, Repoliner и программы PlanetX Lite.\n\n"
            "Напишите вопрос, например «как добавить 3D-модель» или "
            "«topoliner висячие узлы», бот найдёт разделы руководств "
            "модулей.\n\n"
            "/latest - последний выпуск модуля\n"
            "/docs - модули, руководства и каталог QGIS\n"
            "/report текст - сообщение разработчикам об ошибке или "
            "пожелание. Вместе с текстом уходят ваше имя и ник в Telegram."),
        "none": ("В руководстве ничего не нашлось. Попробуйте другие слова "
                 "или откройте руководство: /docs"),
        "found": "Разделы руководства:",
        "show": "Показать раздел",
        "docs": "Модули QGIS ООО «Информ++»:",
        "pick": "Выпуск какого модуля показать?",
        "manual": "Руководство PlanetX",
        "site": "PlanetX на сайте",
        "latest": "{name} {tag} от {date}",
        "zip": "Архив модуля",
        "catalog": "Каталог QGIS",
        "web": "В браузере",
        "on_site": "На сайте",
        "no_release": "Не удалось узнать последний выпуск, попробуйте позже.",
        "report_empty": ("Напишите текст после команды, например:\n"
                         "/report глобус не открывается в QGIS 3.40"),
        "report_done": "Спасибо, сообщение передано разработчикам.",
        "report_off": "Приём сообщений пока не настроен.",
        "more": "Полный раздел: {url}",
    },
    "en": {
        "start": (
            "This is the bot of the QGIS plugins PlanetX, Isoliner, "
            "Isoliner3D, Topoliner, Routeliner, Repoliner and of the "
            "PlanetX Lite program.\n\n"
            "Ask a question, for example \"how to add a 3D model\" or "
            "\"topoliner dangles\", and the bot finds the sections of "
            "the plugin manuals.\n\n"
            "/latest - the latest release of a plugin\n"
            "/docs - plugins, manuals and the QGIS catalog\n"
            "/report text - a bug report or a wish for the developers. "
            "Your Telegram name and user name go with the text."),
        "none": ("Nothing was found in the manual. Try other words or open "
                 "the manual: /docs"),
        "found": "Manual sections:",
        "show": "Show the section",
        "docs": "QGIS plugins of Inform++ LLC:",
        "pick": "Which plugin release to show?",
        "manual": "PlanetX manual",
        "site": "PlanetX website",
        "latest": "{name} {tag} of {date}",
        "zip": "Plugin archive",
        "catalog": "QGIS catalog",
        "web": "In the browser",
        "on_site": "Website",
        "no_release": "The latest release is unavailable, try again later.",
        "report_empty": ("Write the text after the command, for example:\n"
                         "/report the globe does not open in QGIS 3.40"),
        "report_done": "Thank you, the message went to the developers.",
        "report_off": "Messages are not accepted yet.",
        "more": "Whole section: {url}",
    },
}


# Профиль бота в Telegram: команды в меню «/», описание до «Запустить»
# (до 512 знаков) и строка в профиле (до 120). Без языка - английский.
PROFILE = {
    "ru": {
        "commands": [
            ("latest", "Последний выпуск модуля и что нового"),
            ("docs", "Модули, руководства и каталог QGIS"),
            ("report", "Сообщение разработчикам - ошибка или пожелание"),
            ("help", "Что умеет бот"),
        ],
        "description": (
            "Модули QGIS ООО «Информ++» - PlanetX, Isoliner, Isoliner3D, "
            "Topoliner, Routeliner, Repoliner.\n\n"
            "Бот показывает последние выпуски модулей, отвечает на "
            "вопросы по руководствам модулей и передаёт сообщения "
            "разработчикам."),
        "short": "Модули QGIS PlanetX, Isoliner, Topoliner и другие - "
                 "выпуски, руководства, сообщения разработчикам",
    },
    "en": {
        "commands": [
            ("latest", "The latest plugin release and what is new"),
            ("docs", "Plugins, manuals and the QGIS catalog"),
            ("report", "A bug report or a wish for the developers"),
            ("help", "What the bot does"),
        ],
        "description": (
            "QGIS plugins of Inform++ LLC - PlanetX, Isoliner, Isoliner3D, "
            "Topoliner, Routeliner, Repoliner.\n\n"
            "The bot shows the latest plugin releases, answers questions "
            "from the plugin manuals and passes messages to the "
            "developers."),
        "short": "QGIS plugins PlanetX, Isoliner, Topoliner and more - "
                 "releases, manuals, messages to the developers",
    },
}


def language(user):
    """ru для пользователя Telegram с русским, иначе en."""
    code = (user or {}).get("language_code") or ""
    return "ru" if code.split("-")[0] in ("ru", "uk", "be", "kk") else "en"


def manual_file(lang):
    return "MANUAL.md" if lang == "ru" else "MANUAL.en.md"


class Manuals:
    """Руководства модулей линейки одного языка: общий указатель
    разделов (core/manualindex.py), хранилище и файл каждого раздела.
    Данные - bot/data/manuals_<язык>.json, их собирает
    bot/build_index.py."""

    def __init__(self, data):
        self.index = manualindex.Index(data["sections"])
        self.plugins = data["plugins"]
        self.paths = data["paths"]

    def __len__(self):
        return len(self.index)

    def url(self, n):
        repo = self.plugins[n]
        return "https://github.com/{}/{}/blob/main/{}#{}".format(
            OWNER, repo, self.paths[repo],
            urllib.parse.quote(self.index.items[n][1]))

    def name(self, n):
        repo = self.plugins[n]
        return PLUGINS.get(repo, (repo, None))[0]

    def search(self, query, limit=FOUND):
        """Разделы к запросу. Имя модуля в запросе ограничивает поиск
        его руководством."""
        words = query.split()
        repo = None
        clean = [word.strip(",.?!").lower() for word in words]
        # «PlanetX Lite», «Lite», «лайт» - программа без QGIS, а не модуль.
        for i, word in enumerate(clean):
            if word in LITE_WORDS:
                repo = "planetx-lite"
                drop = [i - 1, i] if i and clean[i - 1] == "planetx" else [i]
                words = [w for j, w in enumerate(words) if j not in drop]
                break
        for word in ([] if repo else words):
            repo = plugin_of(word.strip(",.?!"))
            if repo:
                words.remove(word)
                break
        rest = " ".join(words)
        if repo is None:
            return self.index.search(query, limit)
        if not rest.strip():
            rest = query
        found = self.index.search(rest, len(self.index))
        return [n for n in found if self.plugins[n] == repo][:limit]


def plain(markdown):
    """Текст раздела без разметки ссылок, выделения и таблиц."""
    text = _LINK.sub(r"\1", markdown)
    text = _MARKUP.sub("", text)
    # Строки руководства свёрстаны по 79 знаков, абзац - одной строкой,
    # пункты списков и таблиц остаются с новой строки.
    text = re.sub(r"(?<=\S)\n(?![\-|>\d\n]|\s*\n)", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def cut(text, limit=TEXT_LIMIT):
    if len(text) <= limit:
        return text
    return text[:limit].rsplit("\n", 1)[0].rstrip() + "\n…"


def load_indexes():
    out = {}
    for lang in ("ru", "en"):
        path = os.path.join(HERE, "data", "manuals_{}.json".format(lang))
        with open(path, encoding="utf-8") as f:
            out[lang] = Manuals(json.load(f))
    return out


def found_reply(manuals, lang, query):
    """Текст ответа HTML и кнопки по запросу или None без находок."""
    numbers = manuals.search(query, FOUND)
    if not numbers:
        return None
    lines = [TEXTS[lang]["found"]]
    buttons = []
    for n in numbers:
        title = manuals.index.items[n][0]
        name = manuals.name(n)
        lines.append('\n<b><a href="{}">{} · {}</a></b>\n{}'.format(
            html.escape(manuals.url(n), quote=True), html.escape(name),
            html.escape(title),
            html.escape(manuals.index.snippet(n, query))))
        buttons.append([{"text": "{}: {}".format(name, title)[:60],
                         "callback_data": "s:{}:{}".format(lang, n)}])
    return "\n".join(lines), {"inline_keyboard": buttons}


def section_reply(manuals, lang, n):
    title, _, text = manuals.index.items[n]
    head = "{} · {}".format(manuals.name(n), title)
    more = TEXTS[lang]["more"].format(url=manuals.url(n))
    body = cut(plain(text), TEXT_LIMIT - len(head) - len(more) - 4)
    return "{}\n\n{}\n\n{}".format(head, body, more)


def release_html(markdown, assets=()):
    """Описание выпуска в Markdown - текстом HTML для Telegram. Ссылки
    остаются ссылками, жирный и заголовки - жирным, код - кодом, имя
    файла с расширением - доменной зоной идёт ссылкой на файл выпуска
    с тем же именем, иначе кодом, остальное экранируется."""
    files = {a.get("name", "").lower(): a.get("browser_download_url")
             for a in assets if a.get("browser_download_url")}
    text = _TABLE_RULE.sub("", markdown.replace("\r\n", "\n"))
    text = re.sub(r"(?<=\S)\n(?![\-*+|>#\d\n]|\s*\n)", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    out = []
    at = 0
    for match in _RELEASE_LINK.finditer(text):
        out.append(_release_text(text[at:match.start()], files))
        image, label, url = match.groups()
        if not image and url.startswith(("http://", "https://")):
            out.append('<a href="{}">{}</a>'.format(
                html.escape(url, quote=True), html.escape(label)))
        elif not image:
            out.append(html.escape(label))
        at = match.end()
    out.append(_release_text(text[at:], files))
    return "".join(out)


def _release_text(part, files):
    """Кусок описания вне ссылок: код, выделение, имена файлов."""
    out = []
    at = 0
    for match in _CODE.finditer(part):
        out.append(_release_words(part[at:match.start()], files))
        out.append("<code>{}</code>".format(html.escape(match.group(1))))
        at = match.end()
    out.append(_release_words(part[at:], files))
    return "".join(out)


def _release_words(part, files):
    text = html.escape(part, quote=False)
    text = _HEADING.sub(r"<b>\1</b>", text)
    text = _BOLD.sub(lambda m: "<b>{}</b>".format(m.group(1) or m.group(2)),
                     text)
    text = _BULLET.sub(r"\1• ", text)
    text = _ITALIC.sub(r"<i>\1</i>", text)
    # Звёздочки обрезанного выделения не остаются в тексте.
    text = text.replace("**", "")

    def file_name(match):
        name = match.group(1)
        url = files.get(name.lower())
        if url:
            return '<a href="{}">{}</a>'.format(
                html.escape(url, quote=True), name)
        return "<code>{}</code>".format(name)
    return _FILE_NAME.sub(file_name, text)


def release_reply(release, lang, repo="planetx"):
    """Ответ /latest HTML и кнопки по ответу GitHub."""
    tag = release.get("tag_name", "")
    date = (release.get("published_at") or "")[:10]
    body = release_html(cut(release.get("body") or "", 2500),
                        release.get("assets") or ())
    name, catalog = PLUGINS.get(repo.lower(), (repo, None))
    text = "<b>{}</b>\n\n{}".format(
        html.escape(TEXTS[lang]["latest"].format(
            name=name, tag=tag, date=date)),
        body)
    buttons = []
    for asset in release.get("assets") or ():
        if asset.get("name", "").endswith(".zip"):
            buttons.append([{"text": TEXTS[lang]["zip"],
                             "url": asset["browser_download_url"]}])
            break
    if catalog:
        buttons.append([{"text": TEXTS[lang]["catalog"], "url": catalog}])
    return text, {"inline_keyboard": buttons}


def github(url):
    """Ответ JSON API GitHub."""
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT,
                      "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
        return json.loads(answer.read().decode("utf-8"))


def post_args(text):
    """Хранилище и метка команды /post: «/post», «/post v1.7.0»,
    «/post isoliner», «/post isoliner v1.2.0»."""
    repo, tag = "planetx", None
    for word in text.split():
        if re.match(r"v?\d", word):
            tag = word
        elif _REPO.fullmatch(word):
            repo = word
    return repo, tag


def plugin_of(text):
    """Хранилище модуля по слову /latest: имя модуля или хранилища
    в любом регистре, иначе None."""
    word = (text or "").strip().lower()
    for key, (name, _) in PLUGINS.items():
        if word in (key, name.lower()):
            return key
    return None


def docs_reply(lang):
    """Список модулей HTML: описание, ссылки на GitHub и каталог."""
    lines = [html.escape(TEXTS[lang]["docs"])]
    for key, (name, catalog) in PLUGINS.items():
        if catalog:
            other = '<a href="{}">{}</a>'.format(
                catalog, html.escape(TEXTS[lang]["catalog"]))
        else:
            other = '<a href="{}">{}</a>'.format(
                WEB_PAGES[key], html.escape(TEXTS[lang]["web"]))
        if key in SITE_PAGES:
            other += ' · <a href="{}">{}</a>'.format(
                html.escape(urllib.parse.quote(SITE_PAGES[key], safe=":/"),
                            quote=True),
                html.escape(TEXTS[lang]["on_site"]))
        lines.append(
            '\n<b>{}</b> - {}\n<a href="https://github.com/{}/{}">'
            'GitHub</a> · {}'.format(
                html.escape(name), html.escape(ABOUT[lang][key]), OWNER,
                key, other))
    lines.append('\n<a href="{}">{}</a> · <a href="{}">{}</a>'.format(
        html.escape("{}/blob/main/doc/{}".format(
            REPOSITORY, manual_file(lang)), quote=True),
        html.escape(TEXTS[lang]["manual"]),
        html.escape(urllib.parse.quote(SITE, safe=":/"), quote=True),
        html.escape(TEXTS[lang]["site"])))
    return "\n".join(lines)


def read_settings():
    """Поля файла настроек: token, owner, secret. Файл - JSON или один
    токен строкой."""
    data = {}
    if os.path.exists(CONFIG):
        with open(CONFIG, encoding="utf-8-sig") as f:
            text = f.read().strip()
        data = json.loads(text) if text.startswith("{") else {"token": text}
    if os.environ.get("PLANETX_BOT_TOKEN"):
        data["token"] = os.environ["PLANETX_BOT_TOKEN"]
    return data


def write_settings(data):
    folder = os.path.dirname(CONFIG)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(data, f)
    if os.name != "nt":
        os.chmod(CONFIG, 0o600)


def read_config():
    data = read_settings()
    owner = data.get("owner")
    return data.get("token"), int(owner) if owner else None


def make_bot():
    """Бот по файлу настроек или None без токена."""
    token, owner = read_config()
    channel = read_settings().get("channel")
    return Bot(token, owner, channel) if token else None


def application(environ, start_response):
    """Приложение WSGI для приёма обновлений Telegram (webhook).

    Telegram шлёт POST на WEBHOOK_PATH с заголовком секрета, который
    задан при setWebhook. Ответ всегда 200, иначе Telegram повторяет
    обновление."""
    global _BOT
    if (environ.get("REQUEST_METHOD") != "POST"
            or environ.get("PATH_INFO") != WEBHOOK_PATH):
        start_response("404 Not Found", [("Content-Type", "text/plain")])
        return [b"PlanetX bot"]
    secret = read_settings().get("secret") or ""
    given = environ.get("HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN", "")
    if not secret or not hmac.compare_digest(secret, given):
        start_response("403 Forbidden", [("Content-Type", "text/plain")])
        return [b"forbidden"]
    try:
        size = int(environ.get("CONTENT_LENGTH") or 0)
        update = json.loads(environ["wsgi.input"].read(size).decode("utf-8"))
    except ValueError as error:
        log("Обновление не разобрано: {}".format(error))
        update = None
    if update:
        if _BOT is None:
            _BOT = make_bot()
        if _BOT is not None:
            _BOT.handle(update)
    start_response("200 OK", [("Content-Type", "text/plain")])
    return [b"ok"]


_BOT = None


class Bot:
    def __init__(self, token, owner, channel=None):
        self.api = "https://api.telegram.org/bot{}/".format(token)
        self.owner = owner
        self.channel = channel
        self.index = load_indexes()
        self.releases = {}  # хранилище - (время, ответ GitHub)

    def call(self, method, **params):
        body = json.dumps(params).encode("utf-8")
        request = urllib.request.Request(
            self.api + method, data=body,
            headers={"Content-Type": "application/json"})
        for attempt in range(CALL_TRIES):
            try:
                with urllib.request.urlopen(request,
                                            timeout=TIMEOUT) as answer:
                    data = json.loads(answer.read().decode("utf-8"))
                break
            except urllib.error.HTTPError:
                raise  # ответ Telegram, повтор его не изменит
            except urllib.error.URLError as error:
                if attempt + 1 == CALL_TRIES:
                    raise
                log("Повтор {}: {}".format(method, error))
                time.sleep(CALL_PAUSE)
        if not data.get("ok"):
            raise RuntimeError("{}: {}".format(
                method, data.get("description")))
        return data["result"]

    def send(self, chat, text, markup=None, html_text=False):
        params = {"chat_id": chat, "text": text,
                  "disable_web_page_preview": True}
        if html_text:
            params["parse_mode"] = "HTML"
        if markup:
            params["reply_markup"] = markup
        self.call("sendMessage", **params)

    def latest(self, repo="planetx"):
        """Последний выпуск хранилища, ответ помнится RELEASE_KEEP."""
        kept = self.releases.get(repo)
        if kept and time.time() - kept[0] < RELEASE_KEEP:
            return kept[1]
        release = github(RELEASES.format(repo, "latest"))
        self.releases[repo] = (time.time(), release)
        return release

    def show_latest(self, chat, lang, repo):
        try:
            text, markup = release_reply(self.latest(repo), lang, repo)
        except (urllib.error.URLError, OSError, ValueError) as error:
            log("GitHub {}: {}".format(repo, error))
            self.send(chat, TEXTS[lang]["no_release"])
            return
        self.send(chat, text, markup, html_text=True)

    def on_message(self, message):
        chat = message["chat"]["id"]
        user = message.get("from") or {}
        lang = language(user)
        text = (message.get("text") or "").strip()
        if not text:
            return
        command, _, rest = text.partition(" ")
        command = command.split("@")[0].lower()
        private = message["chat"].get("type") == "private"
        if command in ("/start", "/help"):
            self.send(chat, TEXTS[lang]["start"])
        elif command == "/id":
            self.send(chat, str(chat))
        elif command == "/docs":
            self.send(chat, docs_reply(lang), html_text=True)
        elif command == "/latest":
            repo = plugin_of(rest)
            if repo:
                self.show_latest(chat, lang, repo)
            else:
                self.send(chat, TEXTS[lang]["pick"], {"inline_keyboard": [
                    [{"text": name, "callback_data": "l:" + key}]
                    for key, (name, _) in PLUGINS.items()]})
        elif command == "/report":
            self.report(chat, user, lang, rest.strip())
        elif command == "/post" and user.get("id") == self.owner:
            repo, tag = post_args(rest)
            self.draft(repo, tag)
        elif private and not command.startswith("/"):
            reply = found_reply(self.index[lang], lang, text)
            if reply is None:
                self.send(chat, TEXTS[lang]["none"])
            else:
                self.send(chat, reply[0], reply[1], html_text=True)

    def report(self, chat, user, lang, text):
        if not text:
            self.send(chat, TEXTS[lang]["report_empty"])
            return
        if not self.owner:
            self.send(chat, TEXTS[lang]["report_off"])
            return
        who = " ".join(filter(None, (user.get("first_name"),
                                     user.get("last_name"))))
        if user.get("username"):
            who += " @" + user["username"]
        self.send(self.owner, "Сообщение от {} (чат {}):\n\n{}".format(
            who or "?", chat, text))
        self.send(chat, TEXTS[lang]["report_done"])

    def release_of(self, repo, tag):
        """Выпуск хранилища repo по метке, без метки - последний."""
        if not tag:
            return github(RELEASES.format(repo, "latest"))
        return github(RELEASES.format(
            repo, "tags/" + urllib.parse.quote(tag)))

    def draft(self, repo="planetx", tag=None):
        """Черновик поста о выпуске автору с кнопкой публикации."""
        if not self.channel:
            self.send(self.owner, "Канал не задан - поле channel файла "
                      "настроек.")
            return
        try:
            release = self.release_of(repo, tag)
        except (urllib.error.URLError, OSError, ValueError) as error:
            self.send(self.owner, "Выпуск {} {} не найден: {}".format(
                repo, tag or "", error))
            return
        text, markup = release_reply(release, CHANNEL_LANG, repo)
        markup["inline_keyboard"].append([{
            "text": "Опубликовать в {}".format(self.channel),
            "callback_data": "pub:{}:{}".format(
                repo, release.get("tag_name", ""))}])
        self.send(self.owner, text, markup, html_text=True)

    def publish(self, repo, tag, query):
        """Пост о выпуске в канал по кнопке черновика."""
        try:
            release = self.release_of(repo, tag)
            text, markup = release_reply(release, CHANNEL_LANG, repo)
            self.send(self.channel, text, markup, html_text=True)
        except (urllib.error.URLError, OSError, RuntimeError,
                ValueError) as error:
            self.send(self.owner, "Пост не опубликован: {}".format(error))
            return
        name = str(self.channel)
        link = ("https://t.me/" + name[1:] if name.startswith("@")
                else REPOSITORY + "/releases")
        message = query["message"]
        self.call("editMessageReplyMarkup", chat_id=message["chat"]["id"],
                  message_id=message["message_id"],
                  reply_markup={"inline_keyboard": [[{
                      "text": "Опубликовано в {}".format(name),
                      "url": link}]]})
        log("Пост о {} {} в {}".format(repo, tag, name))

    def on_callback(self, query):
        self.call("answerCallbackQuery", callback_query_id=query["id"])
        data = query.get("data") or ""
        message = query.get("message")
        owner = (query.get("from") or {}).get("id") == self.owner
        # pub:хранилище:метка, draft:хранилище:метка, прежнее draft:метка
        # - PlanetX.
        action, _, rest = data.partition(":")
        repo, _, tag = rest.rpartition(":")
        repo = repo or "planetx"
        if (owner and message and action in ("pub", "draft")
                and _REPO.fullmatch(repo)):
            if action == "pub":
                self.publish(repo, tag, query)
            else:
                self.draft(repo, tag)
            return
        if action == "l" and message and rest in PLUGINS:
            self.show_latest(message["chat"]["id"],
                             language(query.get("from")), rest)
            return
        found = re.fullmatch(r"s:(ru|en):(\d+)", data)
        if not found or not message:
            return
        lang, n = found.group(1), int(found.group(2))
        if n < len(self.index[lang]):
            self.send(message["chat"]["id"],
                      section_reply(self.index[lang], lang, n))

    def set_profile(self):
        """Команды и описание бота на русском и по умолчанию."""
        for lang, code in (("en", None), ("ru", "ru")):
            item = PROFILE[lang]
            extra = {"language_code": code} if code else {}
            self.call("setMyCommands", commands=[
                {"command": c, "description": d}
                for c, d in item["commands"]], **extra)
            self.call("setMyDescription", description=item["description"],
                      **extra)
            self.call("setMyShortDescription",
                      short_description=item["short"], **extra)

    def handle(self, update):
        """Одно обновление Telegram, ошибки отправки - в журнал."""
        try:
            if "message" in update:
                self.on_message(update["message"])
            elif "callback_query" in update:
                self.on_callback(update["callback_query"])
        except (urllib.error.URLError, OSError, RuntimeError,
                ValueError, KeyError) as error:
            log("Ответ не отправлен: {}".format(error))

    def profile(self):
        try:
            self.set_profile()
        except (urllib.error.URLError, OSError, RuntimeError) as error:
            log("Профиль бота не обновлён: {}".format(error))

    def set_webhook(self, url, secret):
        self.profile()
        self.call("setWebhook", url=url, secret_token=secret,
                  allowed_updates=["message", "callback_query"],
                  drop_pending_updates=True)
        info = self.call("getWebhookInfo")
        log("Адрес приёма: {}, ждут {}, ошибка: {}".format(
            info.get("url"), info.get("pending_update_count"),
            info.get("last_error_message") or "нет"))

    def run(self):
        me = self.call("getMe")
        # Опрос и адрес приёма несовместимы - адрес снимается.
        self.call("deleteWebhook")
        self.profile()
        log("Бот @{} запущен, Ctrl+C - остановка".format(me["username"]))
        offset = 0
        while True:
            try:
                updates = self.call("getUpdates", offset=offset,
                                    timeout=POLL_WAIT,
                                    allowed_updates=["message",
                                                     "callback_query"])
            except (urllib.error.URLError, OSError, RuntimeError,
                    ValueError) as error:
                log("Telegram: {}".format(error))
                time.sleep(RETRY)
                continue
            for update in updates:
                offset = update["update_id"] + 1
                self.handle(update)


def log(text):
    print(time.strftime("%H:%M:%S"), text, flush=True)


def main(args):
    bot = make_bot()
    if bot is None:
        print("Нет токена. Задайте PLANETX_BOT_TOKEN или поле token "
              "в {}".format(CONFIG))
        return 1
    token = bot.api.split("/bot", 1)[1].rstrip("/")
    if not re.fullmatch(r"\d+:[A-Za-z0-9_-]+", token):
        print("Токен в {} не похож на токен Telegram - цифры, двоеточие, "
              "латинские буквы. Вставьте токен из сообщения "
              "BotFather.".format(CONFIG))
        return 1
    if args[:1] == ["--webhook"] and len(args) == 2:
        # Адрес приёма на сервере, секрет заводится один раз.
        data = read_settings()
        if not data.get("secret"):
            data["secret"] = secrets.token_urlsafe(32)
            write_settings(data)
        bot.set_webhook(args[1].rstrip("/") + WEBHOOK_PATH, data["secret"])
        return 0
    try:
        bot.run()
    except KeyboardInterrupt:
        log("Остановлен")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
