# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Сборка руководства в PDF на двух языках.

    $PY tools/build_manual.py

Источник - doc/MANUAL.md и doc/MANUAL.en.md, картинки - doc/figures,
их снимает tools/qgis_figures.py. PDF ложится внутрь модуля,
в planetx/doc, окно «О модуле» открывает его на языке интерфейса.

Pandoc превращает Markdown в самодостаточную страницу HTML со
встроенными картинками и оглавлением, Edge или Chrome печатает её
в PDF. Pandoc берётся из PATH или из пакета pypandoc_binary. Образец -
одноимённый сборщик Topoliner. Без pandoc или браузера скрипт говорит
об этом и выходит.
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC_SRC = os.path.join(ROOT, "doc")
DOC_OUT = os.path.join(ROOT, "planetx", "doc")

# Архив модуля для каталога QGIS не больше 10 МБ, PDF двух языков -
# его заметная часть. Картинки руководства идут в PDF в JPEG шириной
# не больше FIGURE_WIDTH пикселей - это 140 точек на дюйм на ширине
# страницы A4 без полей. Исходные снимки в doc/figures не меняются.
# Просьба автора от 13 октября 2026 года, величины - выбор помощника.
FIGURE_WIDTH = 1000
FIGURE_QUALITY = 60
FIGURE_LINK = re.compile(r"figures/[^\s)\"']+\.(?:png|jpe?g)",
                         re.IGNORECASE)

BOOKS = [
    ("MANUAL.md", "PlanetX.pdf", "ru", "Содержание"),
    ("MANUAL.en.md", "PlanetX_en.pdf", "en", "Contents"),
]

# Поля и размер страницы идут через @page, колонтитулы браузера
# отключены ключом печати.
CSS = """
@page { size: A4; margin: 18mm 16mm; }
html { -webkit-print-color-adjust: exact; }
body {
  font-family: "Segoe UI", "DejaVu Sans", sans-serif;
  font-size: 10.5pt; line-height: 1.45; color: #111; margin: 0;
}
h1, h2, h3 { color: #13325b; line-height: 1.25; margin: 1.1em 0 0.4em;
  page-break-after: avoid; }
h1 { font-size: 20pt; border-bottom: 2px solid #1f5fae;
  padding-bottom: 4px; }
h2 { font-size: 15pt; }
h3 { font-size: 12.5pt; }
p { margin: 0.45em 0; orphans: 3; widows: 3; }
a { color: #1f5fae; text-decoration: none; }
code { font-family: Consolas, monospace; font-size: 9pt;
  background: #eef2f7; padding: 0 2px; border-radius: 2px; }
table { border-collapse: collapse; width: 100%; margin: 0.7em 0;
  font-size: 9pt; }
th, td { border: 1px solid #c8d0db; padding: 4px 6px;
  vertical-align: top; }
th { background: #eef2f7; text-align: left; }
tr { page-break-inside: avoid; }
img { max-width: 100%; height: auto; display: block; margin: 0.6em auto;
  page-break-inside: avoid; }
hr { border: 0; border-top: 1px solid #d8dee8; margin: 1.2em 0; }
#TOC { page-break-after: always; }
#TOC ul { list-style: none; padding-left: 1.1em; margin: 0.2em 0; }
#TOC > ul { padding-left: 0; }
#TOC a { color: #111; }
"""


def find_pandoc():
    """Pandoc из PATH, иначе из пакета pypandoc_binary."""
    found = shutil.which("pandoc")
    if found:
        return found
    try:
        import pypandoc
    except ImportError:
        return None
    path = pypandoc.get_pandoc_path()
    for candidate in (path, path + ".exe"):
        if os.path.isfile(candidate):
            return candidate
    return None


def find_browser():
    """Edge или Chrome, они печатают страницу в PDF без окна."""
    for name in ("msedge", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    for pattern in (
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        hit = glob.glob(pattern)
        if hit:
            return hit[0]
    return None


def small_figure(source, target):
    """Картинка руководства в JPEG не шире FIGURE_WIDTH."""
    from PIL import Image
    with Image.open(source) as image:
        image = image.convert("RGBA")
        flat = Image.new("RGB", image.size, (255, 255, 255))
        flat.paste(image, mask=image.getchannel("A"))
        if flat.width > FIGURE_WIDTH:
            flat = flat.resize(
                (FIGURE_WIDTH,
                 max(round(flat.height * FIGURE_WIDTH / flat.width), 1)),
                Image.LANCZOS)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        flat.save(target, "JPEG", quality=FIGURE_QUALITY, optimize=True)


def small_source(source, folder):
    """Копия Markdown в folder со ссылками на ужатые картинки."""
    with open(os.path.join(DOC_SRC, source), encoding="utf-8") as fh:
        text = fh.read()

    def swap(match):
        link = match.group(0)
        small = os.path.splitext(link)[0] + ".jpg"
        target = os.path.join(folder, small)
        if not os.path.exists(target):
            small_figure(os.path.join(DOC_SRC, link), target)
        return small

    text = FIGURE_LINK.sub(swap, text)
    with open(os.path.join(folder, source), "w", encoding="utf-8") as fh:
        fh.write(text)


def to_html(pandoc, source, target, language, toc_title, folder=DOC_SRC):
    """Markdown в страницу со встроенными картинками и оглавлением."""
    css_path = os.path.join(folder, "_print.css")
    with open(css_path, "w", encoding="utf-8") as fh:
        fh.write(CSS)
    command = [pandoc, source, "-f", "gfm", "-t", "html5", "-o", target,
               "--standalone", "--embed-resources", "--toc",
               "--toc-depth=2", "--metadata", "lang=" + language,
               "--metadata", "pagetitle=PlanetX",
               "--variable", "toc-title=" + toc_title,
               "--css", "_print.css", "--resource-path=" + folder]
    result = subprocess.run(command, cwd=folder, capture_output=True,
                            text=True)
    os.remove(css_path)
    if result.returncode != 0:
        print(result.stderr[-2000:])
        raise SystemExit("pandoc вернул ошибку на %s" % source)


def to_pdf(browser, html_path, pdf_path):
    """Печать страницы в PDF без окна браузера."""
    url = "file:///" + os.path.abspath(html_path).replace("\\", "/")
    command = [browser, "--headless=new", "--disable-gpu",
               "--no-pdf-header-footer",
               "--run-all-compositor-stages-before-draw",
               "--virtual-time-budget=20000",
               "--print-to-pdf=" + os.path.abspath(pdf_path), url]
    result = subprocess.run(command, capture_output=True, text=True,
                            timeout=300)
    if not os.path.exists(pdf_path) or os.path.getsize(pdf_path) < 10000:
        print(result.stderr[-2000:])
        raise SystemExit("браузер не напечатал %s" % pdf_path)


def main():
    pandoc = find_pandoc()
    if pandoc is None:
        print("Нет pandoc, руководство не собрано. Пакет - pypandoc_binary.")
        return 1
    browser = find_browser()
    if browser is None:
        print("Нет браузера для печати, руководство не собрано.")
        return 1
    os.makedirs(DOC_OUT, exist_ok=True)
    folder = tempfile.mkdtemp(prefix="planetx_manual_")
    try:
        for source, target, language, toc_title in BOOKS:
            small_source(source, folder)
            html_path = os.path.join(folder,
                                     "_" + target.replace(".pdf", ".html"))
            pdf_path = os.path.join(DOC_OUT, target)
            to_html(pandoc, source, html_path, language, toc_title, folder)
            to_pdf(browser, html_path, pdf_path)
            print("%-16s %8.1f КБ" % (target,
                                      os.path.getsize(pdf_path) / 1024))
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
