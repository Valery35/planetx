# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""git для проверочных инструментов: check_texts.py --new, preflight.py.

У автора git не в PATH, он стоит в папке GitHub Desktop.
"""
import os
import shutil
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class GitError(Exception):
    """git не найден или команда кончилась ошибкой."""


def git_program():
    """git из PATH, иначе из GitHub Desktop. Папку app-* берём самую
    свежую по дате: по имени app-3.6.9 встаёт после app-3.6.11."""
    found = shutil.which("git")
    if found:
        return found
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "GitHubDesktop")
    paths = []
    if os.path.isdir(base):
        for name in os.listdir(base):
            exe = os.path.join(base, name, "resources", "app", "git", "cmd",
                               "git.exe")
            if name.startswith("app-") and os.path.exists(exe):
                paths.append(exe)
    if not paths:
        raise GitError("git не найден ни в PATH, ни в папке GitHub Desktop.")
    return max(paths, key=os.path.getmtime)


def git(*args):
    """Вывод команды git в корне хранилища."""
    done = subprocess.run([git_program()] + list(args), cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8")
    if done.returncode:
        raise GitError("git %s: %s" % (" ".join(args),
                                         done.stderr.strip()))
    return done.stdout
