# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Короткая проверка перед выпуском вместо полного прогона шагов.

    $PY tools/release_check.py              всё
    $PY tools/release_check.py --no-qgis    только проверки без QGIS
    $PY tools/release_check.py --qgis 4     только QGIS 4 (или 3)

Просьба автора от 17 октября 2026 года, пункт списка возможностей после
0.67.1 - «короткий набор шагов перед выпуском вместо полного прогона на
3 часа». По порядку:
- тесты ядра без QGIS;
- согласованность пар документов (tools/check_docs.py);
- готовность к каталогу (tools/preflight.py);
- тексты для пользователя (tools/check_texts.py) - находки идут
  замечанием и проверку не останавливают, в старых текстах есть
  и ложные находки, двоеточия подписей источников;
- набор шагов SMOKE файла tools/qgis_check_steps.py в отдельных
  профилях QGIS 4 и QGIS 3 по очереди (PLANETX_STEPS=smoke).

QGIS ищется в папках PLANETX_QGIS4 и PLANETX_QGIS3, по умолчанию
C:\\Program Files\\QGIS 4.0.3 и C:\\Program Files\\QGIS 3.36.1, профили -
%TEMP%\\planetx_stress и %TEMP%\\planetx_qt5, как у полного прогона.
Итог прогона QGIS - %TEMP%\\planetx_release_q4.json и _q3.json. Код
выхода 0 - всё прошло, 1 - есть ошибки. Полный прогон всех шагов
остаётся для больших правок движка.
"""
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMP = os.environ.get("TEMP", ".")
QGIS_TIMEOUT = 30 * 60  # с на один QGIS, набор идёт 10-20 мин
QGIS = {
    "4": (os.environ.get("PLANETX_QGIS4",
                         r"C:\Program Files\QGIS 4.0.3"),
          "planetx_stress", "qt6"),
    "3": (os.environ.get("PLANETX_QGIS3",
                         r"C:\Program Files\QGIS 3.36.1"),
          "planetx_qt5", "qt5"),
}
USER_TEXTS = ("README.md", "README.ru.md", "CHANGELOG.md",
              os.path.join("doc", "MANUAL.md"),
              os.path.join("doc", "MANUAL.en.md"), "planetx")


def run(title, args, timeout=900, keep=None):
    """Команда в папке хранилища: (прошла ли, последние строки вывода
    или строки, начинающиеся с keep)."""
    started = time.monotonic()
    try:
        done = subprocess.run(args, cwd=ROOT, capture_output=True,
                              timeout=timeout, encoding="utf-8",
                              errors="replace")
    except subprocess.TimeoutExpired:
        return False, "{}: срок {} с вышел".format(title, timeout)
    lines = (done.stdout + done.stderr).strip().splitlines()
    chosen = [line for line in lines if keep and line.startswith(keep)]
    tail = "\n".join(chosen or lines[-4:])
    seconds = time.monotonic() - started
    return done.returncode == 0, "{} ({:.0f} с)\n{}".format(
        title, seconds, tail)


def stuck_step():
    """Шаг, который QGIS начал последним: сценарий шагов пишет его
    в файл падения перед запуском."""
    try:
        with open(os.path.join(TEMP, "planetx_steps_crash.txt"),
                  encoding="utf-8", errors="replace") as fh:
            steps = [line.split(" ", 1)[1].strip() for line in fh
                     if line.startswith("step ")]
    except OSError:
        return "?"
    return steps[-1] if steps else "?"


def bat_text(root, profile, qt):
    """Командный файл запуска QGIS со сценарием шагов."""
    lines = ["@echo off",
             'call "{}\\bin\\o4w_env.bat"'.format(root)]
    if qt == "qt6":
        lines.append('call "{}\\bin\\qt6_env.bat"'.format(root))
    lines += [
        r"path %OSGEO4W_ROOT%\apps\qgis\bin;%PATH%",
        r"set QGIS_PREFIX_PATH=%OSGEO4W_ROOT:\=/%/apps/qgis",
        "set GDAL_FILENAME_IS_UTF8=YES",
        r"set QT_PLUGIN_PATH=%OSGEO4W_ROOT%\apps\qgis\qtplugins;"
        r"%OSGEO4W_ROOT%\apps\{}\plugins".format(qt),
        r'"%OSGEO4W_ROOT%\bin\qgis-bin.exe" --profiles-path '
        r'"%TEMP%\{}" --code "{}"'.format(
            profile, os.path.join(ROOT, "tools", "qgis_check_steps.py")),
    ]
    return "\r\n".join(lines) + "\r\n"


def run_qgis(key):
    """Набор шагов SMOKE в QGIS key: (прошла ли, описание)."""
    root, profile, qt = QGIS[key]
    if not os.path.isfile(os.path.join(root, "bin", "qgis-bin.exe")):
        return False, "QGIS {}: не найден в {}".format(key, root)
    bat = os.path.join(TEMP, "planetx_release_q{}.bat".format(key))
    out = os.path.join(TEMP, "planetx_release_q{}.json".format(key))
    with open(bat, "w", encoding="cp866", newline="") as fh:
        fh.write(bat_text(root, profile, qt))
    if os.path.exists(out):
        os.remove(out)
    env = dict(os.environ, PLANETX_STEPS="smoke", PLANETX_STEPS_OUT=out)
    started = time.monotonic()
    launch = subprocess.Popen(["cmd", "/c", bat], env=env,
                              stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL)
    try:
        launch.wait(timeout=QGIS_TIMEOUT)
    except subprocess.TimeoutExpired:
        # Проверочный QGIS - потомок cmd, закрывается вместе с ним.
        step = stuck_step()
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(launch.pid)],
                       capture_output=True)
        return False, "QGIS {}: срок {} мин вышел на шаге {}, итог - {}" \
            .format(key, QGIS_TIMEOUT // 60, step, out)
    minutes = (time.monotonic() - started) / 60.0
    try:
        with open(out, encoding="utf-8") as fh:
            report = json.load(fh)
    except (OSError, ValueError):
        return False, "QGIS {}: итога нет, последний шаг {}, стек - {}" \
            .format(key, stuck_step(),
                    os.path.join(TEMP, "planetx_steps_crash.txt"))
    errors = report.get("errors", [])
    finished = bool(report.get("finished"))
    text = "QGIS {} ({:.0f} мин): шагов {}, ошибок {}, {}".format(
        key, minutes, report.get("steps_run", "?"), len(errors),
        "до конца" if finished else
        "оборвался на шаге " + stuck_step())
    if errors:
        text += "\n  " + "\n  ".join(errors[:12])
    return finished and not errors, text


def main(argv):
    keys = ["4", "3"]
    if "--no-qgis" in argv:
        keys = []
    elif "--qgis" in argv:
        keys = [argv[argv.index("--qgis") + 1]]
    py = sys.executable
    checks = [
        ("Тесты ядра", [py, "-m", "unittest", "discover", "-s",
                        os.path.join("planetx", "tests")]),
        ("Пары документов", [py, os.path.join("tools", "check_docs.py")]),
        ("Готовность к каталогу", [py, os.path.join("tools",
                                                    "preflight.py")]),
    ]
    failed = []
    for title, args in checks:
        ok, text = run(title, args)
        print(("ПРОШЛА  " if ok else "ОШИБКА  ") + text + "\n", flush=True)
        if not ok:
            failed.append(title)
    ok, text = run("Тексты для пользователя",
                   [py, os.path.join("tools", "check_texts.py"),
                    "--strict"] + list(USER_TEXTS), keep="Находок")
    print(("ПРОШЛА  " if ok else "ЗАМЕЧАНИЕ  ") + text + "\n", flush=True)
    for key in keys:
        ok, text = run_qgis(key)
        print(("ПРОШЛА  " if ok else "ОШИБКА  ") + text + "\n", flush=True)
        if not ok:
            failed.append("QGIS " + key)
    if failed:
        print("Не прошли: " + ", ".join(failed))
        return 1
    print("Всё прошло.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
