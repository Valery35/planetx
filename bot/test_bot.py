# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тесты постов о выпусках бота без сети:

    python -m unittest bot/test_bot.py
"""
import datetime
import os
import re
import shutil
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import planetx_bot as bot  # noqa: E402
import health  # noqa: E402
import make_bundle  # noqa: E402


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

    def test_extension_repo_outside_rule(self):
        names = ["rustplanetx-0.6.1-linux.rgplugin",
                 "rustplanetx-0.6.1-macos.rgplugin",
                 "rustplanetx-0.6.1-windows.rgplugin",
                 "rustplanetx-0.6.1.rgplugin"]
        text, markup = bot.release_reply(
            release("v0.6.1", "v0.6.1", names), "ru", "rustplanetx")
        self.assertEqual(head(text),
                         "<b>RustPlanetX для RustGIS 0.6.1 от 2026-11-14</b>")
        button = markup["inline_keyboard"][0][0]
        self.assertEqual(button["text"], "Файл расширения")
        self.assertTrue(button["url"].endswith("rustplanetx-0.6.1.rgplugin"))

    def test_bare_version_name_is_not_title(self):
        for name in ("v0.2.0", "0.2.0", "rustgis-v0.2.0"):
            text, _ = bot.release_reply(release("v0.2.0", name), "ru",
                                        "topoliner-rustgis")
            self.assertEqual(head(text), "<b>Topoliner для RustGIS 0.2.0 от "
                             "2026-11-14</b>")

    def test_platform_packages_without_common(self):
        url, _ = bot.download_of(release("v1.0.0", assets=[
            "x-1.0.0-linux.rgplugin", "x-1.0.0-macos.rgplugin",
            "x-1.0.0-windows.rgplugin"]))
        self.assertTrue(url.endswith("-windows.rgplugin"))
        url, _ = bot.download_of(release("v1.0.0", assets=[
            "x-1.0.0-linux.rgplugin", "x-1.0.0-macos.rgplugin"]))
        self.assertTrue(url.endswith("-linux.rgplugin"))

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


class FakeBot(bot.Bot):
    """Бот без сети: вызовы Telegram пишутся в список."""

    def __init__(self, published):
        self.owner = 1
        self.channel = "@channel"
        self.published = published
        self.releases = {}
        self.calls = []

    def call(self, method, **params):
        self.calls.append((method, params))
        return {}

    def release_of(self, repo, tag):
        return release(tag, "Isoliner3D " + tag, ["isoliner3d.zip"])

    def channel_posts(self):
        return [p for m, p in self.calls
                if m == "sendMessage" and p["chat_id"] == self.channel]


class TestDoublePost(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.path = os.path.join(self.folder, "published.txt")

    def tearDown(self):
        shutil.rmtree(self.folder)

    def query(self):
        return {"message": {"chat": {"id": 1}, "message_id": 7}}

    def test_second_publish_does_not_post(self):
        one = FakeBot(self.path)
        one.publish("qgis-isoliner3d", "1.5.4", self.query())
        one.publish("qgis-isoliner3d", "1.5.4", self.query())
        self.assertEqual(len(one.channel_posts()), 1)
        # Перезапуск приложения: отметка в файле, не в памяти.
        two = FakeBot(self.path)
        two.publish("qgis-isoliner3d", "1.5.4", self.query())
        self.assertEqual(two.channel_posts(), [])
        two.publish("qgis-isoliner3d", "1.5.5", self.query())
        self.assertEqual(len(two.channel_posts()), 1)

    def test_failed_post_is_not_marked(self):
        one = FakeBot(self.path)

        def broken(method, **params):
            if params.get("chat_id") == "@channel":
                raise RuntimeError("sendMessage: Bad Request")
            return {}
        one.call = broken
        one.publish("qgis-isoliner3d", "1.5.4", self.query())
        self.assertEqual(bot.read_published(self.path), set())


class TestLineup(unittest.TestCase):
    def test_every_product_described_and_fits(self):
        for entry in bot.LINEUP:
            for lang in ("ru", "en"):
                self.assertIn(entry[0], bot.ABOUT[lang])
            self.assertLessEqual(len(("l:" + entry[0]).encode("utf-8")),
                                 bot.CALLBACK_LIMIT)
        docs = bot.docs_reply("ru")
        for name in ("Isoliner Scene", "RustPlanetX",
                     "Isoliner3D для RustGIS", "Isoliner для RustGIS",
                     "Topoliner для RustGIS", "PlanetX Lite"):
            self.assertIn(name, docs)
        self.assertIn("valery35.github.io/isoliner-scene", docs)

    def test_latest_by_tag_prefix_in_shared_repo(self):
        listing = [release("rustgis-v0.5.1"), release("v0.4.0"),
                   release("rustgis-v0.5.0"), release("v0.3.0")]
        listing[0]["prerelease"] = False

        def fetch(url):
            self.assertIn("isoliner-scene", url)
            return listing
        scene = bot.pick_release(bot.lineup_entry("isoliner-scene"), fetch)
        ext = bot.pick_release(bot.lineup_entry("isoliner3d-rustgis"), fetch)
        self.assertEqual(scene["tag_name"], "v0.4.0")
        self.assertEqual(ext["tag_name"], "rustgis-v0.5.1")
        with self.assertRaises(LookupError):
            bot.pick_release(bot.lineup_entry("isoliner-scene"),
                             lambda url: [release("rustgis-v0.5.1")])

    def test_latest_word(self):
        self.assertEqual(bot.lineup_of("RustPlanetX"), "rustplanetx")
        self.assertEqual(bot.lineup_of("isoliner для rustgis"),
                         "isoliner-rustgis")
        self.assertEqual(bot.lineup_of("Isoliner"), "qgis-isoliner")


class TestHealth(unittest.TestCase):
    TODAY = datetime.date(2026, 11, 16)
    NOW = 1_800_000_000

    def good(self):
        return {"url": "https://x.pythonanywhere.com/telegram",
                "pending_update_count": 0}

    def test_healthy(self):
        self.assertEqual(health.problems(
            self.good(), 404, "PlanetX bot abc1234 2026-11-16T10:00Z",
            self.TODAY, self.NOW), [])

    def test_each_trouble_found(self):
        info = {"url": "", "pending_update_count": 9,
                "last_error_date": self.NOW - 600,
                "last_error_message": "Connection refused"}
        found = health.problems(info, None, "timed out", self.TODAY,
                                self.NOW)
        self.assertEqual(len(found), 4)
        found = health.problems(self.good(), 404,
                                "PlanetX bot mismatch bot=a data=b",
                                self.TODAY, self.NOW)
        self.assertEqual(len(found), 1)
        self.assertIn("Половинная", found[0])

    def test_expiry_warned_two_weeks_ahead(self):
        due = health.APP_EXPIRES
        quiet = due - datetime.timedelta(days=health.WARN_DAYS + 1)
        warned = due - datetime.timedelta(days=health.WARN_DAYS)
        ok = (self.good(), 404, "PlanetX bot x")
        self.assertEqual(health.problems(*ok, quiet, self.NOW), [])
        self.assertEqual(len(health.problems(*ok, warned, self.NOW)), 1)
        late = health.problems(*ok, due + datetime.timedelta(days=1),
                               self.NOW)
        self.assertIn("наступил", late[0])
        self.assertEqual(health.APP_EXPIRES, datetime.date(2027, 2, 16))


class TestBundle(unittest.TestCase):
    def test_bundle_is_whole_and_half_is_seen(self):
        folder = tempfile.mkdtemp()
        try:
            out = make_bundle.bundle(os.path.join(folder, "b.zip"),
                                     "abc1234 2026-11-16T10:00Z")
            with zipfile.ZipFile(out) as z:
                names = set(z.namelist())
                z.extractall(folder)
            for name in make_bundle.FILES + (make_bundle.STAMP,):
                self.assertIn("planetx-bot/" + name, names)
            base = os.path.join(folder, "planetx-bot")
            with open(os.path.join(base, "bot", "planetx_bot.py"),
                      encoding="utf-8") as f:
                built = re.search(r'^BUILD = "([^"]*)"$', f.read(),
                                  re.MULTILINE).group(1)
            stamp = os.path.join(base, "bot", "data", "build.json")
            self.assertEqual(bot.build_state(built, stamp), built)
            # Новый бот со старыми данными - половинная выкладка.
            self.assertTrue(bot.build_state("def5678 2026-12-01T00:00Z",
                                            stamp).startswith("mismatch"))
            self.assertEqual(bot.build_state("", os.path.join(
                folder, "none.json")), "dev")
        finally:
            shutil.rmtree(folder)


if __name__ == "__main__":
    unittest.main()
