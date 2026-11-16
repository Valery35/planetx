# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""
Проверка готовности к публикации.

Перенесена из Topoliner. Смотрит на то, что обычно возвращает модератор
каталога: заполненность метаданных, лицензию, внешние зависимости, единый
номер версии. Запуск из корня репозитория:

    python tools/preflight.py          без сети - так зовёт build_zip.py
    python tools/preflight.py --net    ещё адреса и метки выпусков

Без сети проверяются и адреса metadata.txt: процент-кодировка (из-за
неё каталог не принял выпуск Routeliner), https, www у сайта Информ++,
первая запись поля changelog с номером версии. С --net адреса
открываются, метки v* берутся с GitHub, номер сверяется с ними -
выданный номер закрыт. Так preflight зовёт release_check.py.

Прежние отказы каталога из-за кода (Bandit, энтропия строк, плоские
имена Qt 6, xml.etree) стерегут тесты planetx/tests/test_hygiene.py.

Код возврата 1 означает ошибки. Замечания код возврата не меняют.
"""

import ast
import configparser
import importlib.util
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = "planetx"
SKIP_DIRS = {"tests", "__pycache__", "libs"}

REQUIRED = ("name", "qgisMinimumVersion", "qgisMaximumVersion",
            "description", "version", "author", "email", "about",
            "repository", "tracker", "icon")

# Кроме стандартной библиотеки допустимы модули, которые есть в QGIS.
# osgeo - привязки GDAL, они входят в состав QGIS.
ALLOWED = {"qgis", "PyQt5", "PyQt6", "numpy", "OpenGL", "osgeo"}

# Номер ищется и с приставкой: «v1.44.1». Граница слова \b между «v»
# и цифрой не срабатывает, и прежний шаблон \b(\d+\.\d+\.\d+)\b такой
# номер пропускал молча (находка Routeliner, ноябрь 2026 года).
VERSION = re.compile(r"(?<![\d.])(\d+\.\d+\.\d+)(?!\.?\d)")
# Файлы, где номер версии плагина повторяется. Ищется номер рядом
# с именем плагина или в заголовке раздела журнала изменений.
VERSION_FILES = ("README.md", "README.ru.md")


def module_level_imports(path):
    """Имена всех модулей, которые файл импортирует.

    Учитываются и импорты внутри try и функций. Откат вида
    ``try: PyQt6 ... except ImportError`` тоже внешний импорт, если модуля
    нет в списке допустимых.
    """
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    # Запасной импорт в обработчике ImportError нужен тестам без QGIS.
    # Внутри плагина срабатывает относительный импорт перед ним.
    fallback = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is not None \
                and ast.unparse(node.type) == "ImportError":
            for sub in ast.walk(node):
                fallback.add(id(sub))
    names = set()
    for node in ast.walk(tree):
        if id(node) in fallback:
            continue
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module \
                and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def plugin_files():
    for folder, dirs, files in os.walk(os.path.join(ROOT, PLUGIN)):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            if name.endswith(".py"):
                yield os.path.join(folder, name)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def version_mentions():
    """Пары место и номер для всех упоминаний версии плагина."""
    found = []
    for name in VERSION_FILES:
        path = os.path.join(ROOT, name)
        if not os.path.exists(path):
            continue
        for number, line in enumerate(read(path).split("\n"), 1):
            if re.search(r"PlanetX|[Вв]ерси|[Vv]ersion", line):
                for match in VERSION.finditer(line):
                    found.append(("%s:%d" % (name, number), match.group(1)))
    changelog = os.path.join(ROOT, "CHANGELOG.md")
    if os.path.exists(changelog):
        for number, line in enumerate(read(changelog).split("\n"), 1):
            match = VERSION.search(line) if line.startswith("## ") else None
            if match:
                found.append(("CHANGELOG.md:%d" % number, match.group(1)))
                break
    for path in plugin_files():
        for number, line in enumerate(read(path).split("\n"), 1):
            for match in re.finditer(r"PlanetX v?(\d+\.\d+\.\d+)", line):
                found.append(("%s:%d" % (os.path.relpath(path, ROOT),
                                         number), match.group(1)))
    return found


URL_FIELDS = ("homepage", "repository", "tracker")


def url_problems(general):
    """Адреса metadata.txt без сети. Каталог не принял выпуск Routeliner
    с адресом страницы в процент-кодировке (ноябрь 2026 года), адрес
    кириллицей он берёт. Сайт без www не открывается (AGENTS.md)."""
    out = []
    for field in URL_FIELDS:
        url = general.get(field, "").strip()
        if not url:
            continue
        if re.search(r"%[0-9A-Fa-f]{2}", url):
            out.append("metadata.txt: %s в процент-кодировке, каталог её "
                       "не принимает - адрес пишется буквами" % field)
        if not url.startswith("https://"):
            out.append("metadata.txt: %s не https - %s" % (field, url))
        if re.match(r"https?://informpp\.ru", url):
            out.append("metadata.txt: %s без www, сайт так не открывается"
                       % field)
    return out


def url_answers(general):
    """Ответ сервера по адресам metadata.txt - только с ключом --net."""
    import urllib.error
    import urllib.parse
    import urllib.request
    out = []
    for field in URL_FIELDS:
        url = general.get(field, "").strip()
        if not url:
            continue
        parts = urllib.parse.urlsplit(url)
        wire = urllib.parse.urlunsplit(parts._replace(
            path=urllib.parse.quote(parts.path, safe="/")))
        request = urllib.request.Request(
            wire, headers={"User-Agent": "PlanetX release check"})
        try:
            with urllib.request.urlopen(request, timeout=20) as reply:
                status = reply.status
        except urllib.error.HTTPError as error:
            status = error.code
        except (urllib.error.URLError, OSError) as error:
            out.append("metadata.txt: %s не открылся - %s" % (field, error))
            continue
        if status >= 400:
            out.append("metadata.txt: %s ответил %d" % (field, status))
    return out


def number(text):
    return tuple(int(part) for part in text.split("."))


def tag_problems(version):
    """Номер версии против меток выпусков v* - только с ключом --net,
    метки сначала берутся с GitHub. Выданный номер закрыт: метка этого
    номера на другом коммите значит, что номер не подняли."""
    from gittool import GitError, git
    out = []
    try:
        try:
            git("fetch", "--tags", "--quiet", "origin")
        except GitError as error:
            out.append(("warn", "метки с GitHub не получены - %s"
                        % str(error).splitlines()[-1]))
        tags = [t.strip() for t in git("tag", "-l", "v*").splitlines()]
        head = git("rev-parse", "HEAD").strip()
        own = "v" + version
        if own in tags:
            at = git("rev-list", "-n", "1", own).strip()
            if at != head:
                out.append(("error", "номер %s уже выпущен меткой %s на "
                            "другом коммите - номер не поднят"
                            % (version, own)))
        valid = [t for t in tags if re.fullmatch(r"v\d+\.\d+\.\d+", t)]
        if valid:
            last = max(valid, key=lambda t: number(t[1:]))
            if number(version) < number(last[1:]):
                out.append(("error", "номер %s меньше последнего выпуска %s"
                            % (version, last)))
    except GitError as error:
        out.append(("error", "метки выпусков не прочитаны - %s" % error))
    return out


def main(argv=()):
    errors, warnings = [], []
    net = "--net" in argv

    meta_path = os.path.join(ROOT, PLUGIN, "metadata.txt")
    cp = configparser.ConfigParser()
    cp.read(meta_path, encoding="utf-8")
    general = cp["general"]
    # Каталог и QGIS читают каждое поле с подстановкой, одиночный «%»
    # в журнале 0.78.1 сорвал загрузку в каталог 13 октября 2026 года.
    for field in general:
        try:
            general.get(field)
        except configparser.InterpolationError as error:
            errors.append("metadata.txt: поле %s - %s" % (field, error))

    for field in REQUIRED:
        if not general.get(field, "").strip():
            errors.append("metadata.txt: не заполнено поле %s" % field)
    if re.search(r"[А-Яа-яЁё]", general.get("description", "")):
        warnings.append("description на русском, каталог международный")
    if general.get("experimental", "").lower() not in ("false", ""):
        warnings.append("плагин помечен как experimental")

    # Без qgisMaximumVersion QGIS подставляет 3.99 и на четвёртой версии
    # объявляет плагин несовместимым.
    maximum = general.get("qgisMaximumVersion", "").strip()
    if maximum and int(maximum.split(".")[0]) < 4:
        errors.append("qgisMaximumVersion=%s не покрывает QGIS 4" % maximum)

    icon = general.get("icon", "").strip()
    if icon and not os.path.exists(os.path.join(ROOT, PLUGIN, icon)):
        errors.append("нет файла значка %s/%s" % (PLUGIN, icon))

    for name in ("__init__.py", "metadata.txt", "LICENSE"):
        if not os.path.exists(os.path.join(ROOT, PLUGIN, name)):
            errors.append("нет файла %s/%s" % (PLUGIN, name))
    license_path = os.path.join(ROOT, "LICENSE")
    if not os.path.exists(license_path):
        errors.append("нет файла LICENSE")
    elif "GNU GENERAL PUBLIC LICENSE" not in read(license_path):
        errors.append("LICENSE не является текстом GPL")

    version = general.get("version", "").strip()
    for place, mention in version_mentions():
        if mention != version:
            errors.append("%s: версия %s, в metadata.txt %s"
                          % (place, mention, version))
    # Журнал для каталога - первая запись поля changelog metadata.txt.
    log = general.get("changelog", "").strip()
    if log and not log.startswith(version + " "):
        errors.append("metadata.txt: changelog начинается не с %s"
                      % version)

    errors += url_problems(general)
    if net:
        errors += url_answers(general)
        for level, text in tag_problems(version):
            (errors if level == "error" else warnings).append(text)

    allowed = ALLOWED | set(sys.stdlib_module_names)
    for path in plugin_files():
        for module in sorted(module_level_imports(path) - allowed):
            errors.append("%s: внешний импорт %s"
                          % (os.path.relpath(path, ROOT), module))

    # Каталог прогоняет код анализатором и возвращает загрузку
    # с замечаниями. Если pyflakes установлен, они ловятся здесь.
    if importlib.util.find_spec("pyflakes") is None:
        warnings.append("pyflakes не установлен, анализ кода пропущен")
    else:
        out = subprocess.run(
            [sys.executable, "-m", "pyflakes", os.path.join(ROOT, PLUGIN)],
            capture_output=True, text=True, timeout=120)
        for line in out.stdout.splitlines():
            if line.strip():
                warnings.append("pyflakes: " + line.strip())

    print("Проверка готовности PlanetX %s" % (version or "?"))
    if errors:
        print("\nОшибки:")
        for line in errors:
            print("  " + line)
    if warnings:
        print("\nЗамечания:")
        for line in warnings:
            print("  " + line)
    if not errors and not warnings:
        print("\nВсё в порядке.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
