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
- текст в личном чате - разделы руководства, поиск core/manualindex.py
  по указателю data/manual_ru.json или manual_en.json, кнопка под
  разделом присылает его текст;
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
# Выпуск с GitHub помнится, с.
RELEASE_KEEP = 600
# Предел текста сообщения Telegram 4096 знаков, берётся с запасом.
TEXT_LIMIT = 3500
# Разделов руководства в ответе не больше.
FOUND = 3

_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_MARKUP = re.compile(r"[*`]+|^\|?[-:| ]{3,}\|?$", re.MULTILINE)

TEXTS = {
    "ru": {
        "start": (
            "Это бот PlanetX - трёхмерного глобуса для QGIS.\n\n"
            "Напишите вопрос, например «как добавить 3D-модель», бот "
            "найдёт разделы руководства.\n\n"
            "/latest - последний выпуск\n"
            "/docs - руководство\n"
            "/report текст - сообщение разработчикам об ошибке или "
            "пожелание. Вместе с текстом уходят ваше имя и ник в Telegram."),
        "none": ("В руководстве ничего не нашлось. Попробуйте другие слова "
                 "или откройте руководство: /docs"),
        "found": "Разделы руководства:",
        "show": "Показать раздел",
        "docs": ("Руководство PlanetX:\n{manual}\n\nPDF прикладывается "
                 "к каждому выпуску: {releases}\nСтраница модуля: {site}"),
        "latest": "{name} {tag} от {date}",
        "zip": "Архив модуля",
        "catalog": "Каталог QGIS",
        "no_release": "Не удалось узнать последний выпуск, попробуйте позже.",
        "report_empty": ("Напишите текст после команды, например:\n"
                         "/report глобус не открывается в QGIS 3.40"),
        "report_done": "Спасибо, сообщение передано разработчикам.",
        "report_off": "Приём сообщений пока не настроен.",
        "more": "Полный раздел: {url}",
    },
    "en": {
        "start": (
            "This is the bot of PlanetX, a 3D globe for QGIS.\n\n"
            "Ask a question, for example \"how to add a 3D model\", and the "
            "bot finds the manual sections.\n\n"
            "/latest - the latest release\n"
            "/docs - the manual\n"
            "/report text - a bug report or a wish for the developers. "
            "Your Telegram name and user name go with the text."),
        "none": ("Nothing was found in the manual. Try other words or open "
                 "the manual: /docs"),
        "found": "Manual sections:",
        "show": "Show the section",
        "docs": ("PlanetX manual:\n{manual}\n\nA PDF comes with every "
                 "release: {releases}\nPlugin page: {site}"),
        "latest": "{name} {tag} of {date}",
        "zip": "Plugin archive",
        "catalog": "QGIS catalog",
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
            ("latest", "Последний выпуск и что нового"),
            ("docs", "Руководство пользователя"),
            ("report", "Сообщение разработчикам - ошибка или пожелание"),
            ("help", "Что умеет бот"),
        ],
        "description": (
            "PlanetX - трёхмерный глобус внутри QGIS. Снимки и рельеф "
            "всей Земли, слои проекта на глобусе, метки, туры, разрезы "
            "недр, 3D-модели.\n\n"
            "Бот отвечает на вопросы по руководству, показывает последний "
            "выпуск и передаёт сообщения разработчикам."),
        "short": "Трёхмерный глобус для QGIS - руководство, выпуски, "
                 "сообщения разработчикам",
    },
    "en": {
        "commands": [
            ("latest", "The latest release and what is new"),
            ("docs", "User manual"),
            ("report", "A bug report or a wish for the developers"),
            ("help", "What the bot does"),
        ],
        "description": (
            "PlanetX is a 3D globe inside QGIS. Imagery and terrain of the "
            "whole Earth, project layers on the globe, places, tours, "
            "subsurface sections, 3D models.\n\n"
            "The bot answers questions from the manual, shows the latest "
            "release and passes messages to the developers."),
        "short": "A 3D globe for QGIS - manual, releases, messages to "
                 "the developers",
    },
}


def language(user):
    """ru для пользователя Telegram с русским, иначе en."""
    code = (user or {}).get("language_code") or ""
    return "ru" if code.split("-")[0] in ("ru", "uk", "be", "kk") else "en"


def manual_file(lang):
    return "MANUAL.md" if lang == "ru" else "MANUAL.en.md"


def section_url(lang, anchor):
    return "{}/blob/main/doc/{}#{}".format(
        REPOSITORY, manual_file(lang), urllib.parse.quote(anchor))


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
        path = os.path.join(PLUGIN, "data", "manual_{}.json".format(lang))
        with open(path, encoding="utf-8") as f:
            out[lang] = manualindex.Index.from_json(f.read())
    return out


def found_reply(index, lang, query):
    """Текст ответа HTML и кнопки по запросу или None без находок."""
    numbers = index.search(query, FOUND)
    if not numbers:
        return None
    lines = [TEXTS[lang]["found"]]
    buttons = []
    for n in numbers:
        title, anchor, _ = index.items[n]
        lines.append('\n<b><a href="{}">{}</a></b>\n{}'.format(
            html.escape(section_url(lang, anchor), quote=True),
            html.escape(title), html.escape(index.snippet(n, query))))
        buttons.append([{"text": "{}: {}".format(
            TEXTS[lang]["show"], title)[:60],
            "callback_data": "s:{}:{}".format(lang, n)}])
    return "\n".join(lines), {"inline_keyboard": buttons}


def section_reply(index, lang, n):
    title, anchor, text = index.items[n]
    more = TEXTS[lang]["more"].format(url=section_url(lang, anchor))
    body = cut(plain(text), TEXT_LIMIT - len(title) - len(more) - 4)
    return "{}\n\n{}\n\n{}".format(title, body, more)


def release_reply(release, lang, repo="planetx"):
    """Ответ /latest HTML и кнопки по ответу GitHub."""
    tag = release.get("tag_name", "")
    date = (release.get("published_at") or "")[:10]
    body = cut(plain(release.get("body") or ""), 2500)
    name, catalog = PLUGINS.get(repo.lower(), (repo, None))
    text = "<b>{}</b>\n\n{}".format(
        html.escape(TEXTS[lang]["latest"].format(
            name=name, tag=tag, date=date)),
        html.escape(body))
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
        self.release = None
        self.release_at = 0.0

    def call(self, method, **params):
        body = json.dumps(params).encode("utf-8")
        request = urllib.request.Request(
            self.api + method, data=body,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
            data = json.loads(answer.read().decode("utf-8"))
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

    def latest(self):
        if self.release and time.time() - self.release_at < RELEASE_KEEP:
            return self.release
        self.release = github(RELEASES.format("planetx", "latest"))
        self.release_at = time.time()
        return self.release

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
            self.send(chat, TEXTS[lang]["docs"].format(
                manual="{}/blob/main/doc/{}".format(
                    REPOSITORY, manual_file(lang)),
                releases=REPOSITORY + "/releases", site=SITE))
        elif command == "/latest":
            try:
                text, markup = release_reply(self.latest(), lang)
            except (urllib.error.URLError, OSError, ValueError) as error:
                log("GitHub: {}".format(error))
                self.send(chat, TEXTS[lang]["no_release"])
                return
            self.send(chat, text, markup, html_text=True)
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
