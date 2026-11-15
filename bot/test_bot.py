# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тесты постов о выпусках бота без сети:

    python -m unittest bot/test_bot.py
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import planetx_bot as bot  # noqa: E402


def release(tag, name="", assets=()):
    return {"tag_name": tag, "name": name, "body": "Новое.",
            "published_at": "2026-11-14T04:28:39Z",
            "assets": [{"name": a, "browser_download_url":
                        "https://example.org/" + a} for a in assets]}


def head(text):
    return text.split("\n", 1)[0]


class TestExtensions(unittest.TestCase):
    def test_extension_by_tag_takes_release_name(self):
        text, markup = bot.release_reply(
            release("rustgis-v0.5.1", "Isoliner3D для RustGIS 0.5.1",
                    ["isoliner3d-0.5.1.rgplugin", "isoliner3d-rustgis.ru.md"]),
            "ru", "isoliner-scene")
        self.assertEqual(head(text),
                         "<b>Isoliner3D для RustGIS 0.5.1 от 2026-11-14</b>")
        rows = markup["inline_keyboard"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0]["text"], "Файл расширения")
        self.assertTrue(rows[0][0]["url"].endswith(".rgplugin"))

    def test_extension_repo_without_name(self):
        for repo, tag, product in (
                ("topoliner-rustgis", "v0.2.0", "Topoliner"),
                ("isoliner-rustgis", "rustgis-v1.0.0", "Isoliner"),
                ("routeliner-rustgis", "v0.1.0", "Routeliner"),
                ("newliner-rustgis", "v0.1.0", "newliner-rustgis")):
            text, markup = bot.release_reply(release(tag), "ru", repo)
            version = bot.version_of(tag)
            self.assertEqual(head(text), "<b>{} для RustGIS {} от "
                             "2026-11-14</b>".format(product, version))
            self.assertEqual(markup["inline_keyboard"], [])

    def test_extension_in_plugin_repo_has_no_catalog(self):
        text, markup = bot.release_reply(
            release("rustgis-v0.3.0", assets=["a.rgplugin"]), "en",
            "topoliner")
        self.assertEqual(head(text),
                         "<b>Topoliner for RustGIS 0.3.0 of 2026-11-14</b>")
        self.assertEqual([r[0]["text"] for r in markup["inline_keyboard"]],
                         ["Extension file"])

    def test_plugin_post_unchanged(self):
        text, markup = bot.release_reply(
            release("1.5.4", "Isoliner3D 1.5.4", ["isoliner3d.zip"]),
            "ru", "qgis-isoliner3d")
        self.assertEqual(head(text), "<b>Isoliner3D 1.5.4 от 2026-11-14</b>")
        self.assertEqual([r[0]["text"] for r in markup["inline_keyboard"]],
                         ["Архив модуля", "Каталог QGIS"])

    def test_program_takes_release_name(self):
        text, markup = bot.release_reply(
            release("v0.4.0", "Isoliner Scene 0.4.0", ["s-windows-x64.zip"]),
            "ru", "isoliner-scene")
        self.assertEqual(head(text),
                         "<b>Isoliner Scene 0.4.0 от 2026-11-14</b>")
        self.assertEqual(markup["inline_keyboard"][0][0]["text"], "Скачать")

    def test_one_repo_gives_program_and_extension(self):
        for tag, title in (("v0.4.0", "Isoliner Scene 0.4.0"),
                           ("rustgis-v0.5.1", "Isoliner3D для RustGIS 0.5.1")):
            text, _ = bot.release_reply(release(tag), "ru", "isoliner-scene")
            self.assertEqual(head(text),
                             "<b>{} от 2026-11-14</b>".format(title))

    def test_callback_fits_telegram_limit(self):
        for repo in ("isoliner-scene", "isoliner-rustgis",
                     "topoliner-rustgis", "routeliner-rustgis",
                     "repoliner-rustgis", "qgis-isoliner3d"):
            for tag in ("rustgis-v10.20.30", "v10.20.30"):
                data = "draft:{}:{}".format(repo, tag)
                self.assertLessEqual(len(data.encode("utf-8")),
                                     bot.CALLBACK_LIMIT, data)
                self.assertTrue(bot._REPO.fullmatch(repo))

    def test_post_args_extension_tag(self):
        self.assertEqual(bot.post_args("isoliner-scene rustgis-v0.5.1"),
                         ("isoliner-scene", "rustgis-v0.5.1"))
        self.assertEqual(bot.post_args("isoliner v1.2.0"),
                         ("isoliner", "v1.2.0"))


if __name__ == "__main__":
    unittest.main()
