# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Круг разговора помощника, разрешения, бюджет ответов и руководство."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import assistant as ai  # noqa: E402
import manualindex  # noqa: E402


def reply(text="", calls=(), error=""):
    return ai.Reply(text, list(calls), None, error)


def call(name, n=1, **args):
    return ai.Call("c%d" % n, name, args)


class TestDocs(unittest.TestCase):

    def setUp(self):
        self.index = manualindex.Index([
            ("Линейка", "линейка",
             "Линейка меряет расстояние.\n\nВторая строка.\nТретья."),
            ("Снимок вида", "снимок-вида", "Снимок вида пишет картинку."),
        ])

    def test_search_gives_anchor_and_title(self):
        text = ai.search_docs_text(self.index, "линейка расстояние")
        self.assertTrue(text.startswith("линейка - Линейка:"))

    def test_nothing_found(self):
        self.assertIn("ничего", ai.search_docs_text(self.index, "зебры"))

    def test_read_part_and_next_offset(self):
        text = ai.read_doc_text(self.index, "#линейка", offset=1, limit=2)
        self.assertIn("Строки 2-3 из 4.", text)
        self.assertIn("Вторая строка.", text)
        self.assertNotIn("меряет", text)
        self.assertIn("offset 3", text)

    def test_read_by_title_and_unknown(self):
        self.assertIn("картинку",
                      ai.read_doc_text(self.index, "Снимок вида"))
        self.assertIn("нет", ai.read_doc_text(self.index, "нет-такого"))


class TestApproval(unittest.TestCase):

    def test_gated(self):
        self.assertTrue(ai.needs_approval(call("read_features", layer="1")))
        self.assertTrue(ai.needs_approval(call("list_project_layers")))
        self.assertTrue(ai.needs_approval(
            call("run_action", key="tool:scene_save")))
        self.assertFalse(ai.needs_approval(
            call("run_action", key="extra:grid")))
        self.assertFalse(ai.needs_approval(call("fly_to", lat=1, lon=2)))

    def test_assistant_window_stays_skipped(self):
        self.assertEqual(ai.ACTION_SKIP, ("tool:assistant",))
        self.assertNotIn("tool:assistant", ai.ACTION_GATED)

    def test_key_ignores_argument_order(self):
        a = ai.Call("x", "read_features", {"layer": "1", "limit": 5})
        b = ai.Call("y", "read_features", {"limit": 5, "layer": "1"})
        c = ai.Call("z", "read_features", {"layer": "2", "limit": 5})
        self.assertEqual(ai.approval_key(a), ai.approval_key(b))
        self.assertNotEqual(ai.approval_key(a), ai.approval_key(c))


class TestBudget(unittest.TestCase):

    def test_bounded_keeps_head_and_tail(self):
        text = "А" * 50 + "Б" * 50
        out = ai.bounded(text, limit=30)
        self.assertTrue(out.startswith("А" * 20))
        self.assertTrue(out.endswith("Б" * 10))
        self.assertIn("пропущено 70", out)
        self.assertEqual(ai.bounded("коротко", limit=30), "коротко")

    def test_trimmed_old_results_only(self):
        dialog = []
        for n in range(4):
            dialog.append({"role": "user", "text": "q"})
            dialog.append(ai.results_message([ai.Result("r%d" % n,
                                                        "x" * 100)]))
        out = ai.trimmed(dialog, limit=250, keep=2)
        texts = [m["results"][0].text for m in out if m.get("results")]
        self.assertEqual(texts[:2], [ai.TRIMMED, ai.TRIMMED])
        self.assertEqual(texts[2:], ["x" * 100, "x" * 100])
        # Сам разговор не меняется.
        self.assertEqual(dialog[1]["results"][0].text, "x" * 100)
        self.assertEqual(ai.trimmed(dialog, limit=10 ** 6), dialog)

    def test_transient(self):
        for text in ("Overloaded", "rate-limited upstream",
                     "server replied: Service Unavailable",
                     "Error 529", "Too Many Requests"):
            self.assertTrue(ai.transient(text), text)
        for text in ("Connection refused", "invalid x-api-key", ""):
            self.assertFalse(ai.transient(text), text)


class TestAgent(unittest.TestCase):

    def test_plain_answer(self):
        agent = ai.Agent()
        self.assertEqual(agent.ask("привет").kind, ai.SEND)
        step = agent.answered(reply("здравствуй"))
        self.assertEqual((step.kind, step.text), (ai.DONE, "здравствуй"))

    def test_runs_then_confirms_then_remembers(self):
        agent = ai.Agent()
        agent.ask("слои")
        gated = call("read_features", 2, layer="1")
        step = agent.answered(reply(calls=[call("fly_to", 1, lat=1, lon=2),
                                           gated]))
        self.assertEqual(step.kind, ai.RUN)
        step = agent.result("ok")
        self.assertEqual((step.kind, step.call), (ai.CONFIRM, gated))
        step = agent.decide(ai.ALLOW_ALWAYS)
        self.assertEqual(step.kind, ai.RUN)
        self.assertEqual(agent.result("строки").kind, ai.SEND)
        # Тот же вызов в этом разговоре - без вопроса, другой - с ним.
        step = agent.answered(reply(calls=[ai.Call("c3", "read_features",
                                                   {"layer": "1"})]))
        self.assertEqual(step.kind, ai.RUN)
        agent.result("строки")
        step = agent.answered(reply(calls=[call("read_features", 4,
                                                layer="2")]))
        self.assertEqual(step.kind, ai.CONFIRM)

    def test_deny_answers_model(self):
        agent = ai.Agent()
        agent.ask("слои")
        agent.answered(reply(calls=[call("list_project_layers")]))
        self.assertEqual(agent.decide(ai.DENY).kind, ai.SEND)
        self.assertEqual(agent.dialog[-1]["results"][0].text, ai.DENIED)

    def test_long_result_bounded(self):
        agent = ai.Agent()
        agent.ask("q")
        agent.answered(reply(calls=[call("fly_to", lat=1, lon=2)]))
        agent.result("x" * (ai.OUTPUT_CHARS * 2))
        text = agent.dialog[-1]["results"][0].text
        self.assertLess(len(text), ai.OUTPUT_CHARS + 100)

    def test_retry_then_fail_rolls_back(self):
        agent = ai.Agent()
        agent.ask("q")
        delays = []
        for n in range(ai.MAX_RETRIES):
            step = agent.answered(reply(error="Overloaded"))
            self.assertEqual(step.kind, ai.RETRY)
            delays.append(step.delay)
        self.assertEqual(delays, list(ai.RETRY_DELAYS))
        self.assertEqual(agent.answered(reply(error="Overloaded")).kind,
                         ai.FAILED)
        self.assertEqual(agent.dialog, [])

    def test_network_error_wins_over_no_data(self):
        agent = ai.Agent()
        agent.ask("q")
        step = agent.answered(reply(error="no data"), "Connection refused")
        self.assertEqual((step.kind, step.text),
                         (ai.FAILED, "Connection refused"))

    def test_retry_count_resets_after_answer(self):
        agent = ai.Agent()
        agent.ask("q")
        agent.answered(reply(error="Too Many Requests"))
        agent.answered(reply(calls=[call("fly_to", lat=1, lon=2)]))
        agent.result("ok")
        self.assertEqual(agent.retries, 0)

    def test_limit_and_resume(self):
        agent = ai.Agent()
        agent.ask("q")
        for n in range(ai.MAX_ROUNDS):
            agent.answered(reply(calls=[call("fly_to", n, lat=1, lon=2)]))
            step = agent.result("ok")
        self.assertEqual(step.kind, ai.LIMIT)
        self.assertEqual(agent.resume().kind, ai.SEND)
        self.assertEqual(agent.rounds, 0)

    def test_roles_alternate_after_cancel(self):
        """Сторож: вопрос после остановки на ответах инструментов шёл
        сообщением пользователя подряд за ответами."""
        agent = ai.Agent()
        agent.ask("q")
        agent.answered(reply(calls=[call("list_project_layers")]))
        agent.cancel()
        self.assertEqual(agent.dialog[-1]["results"][0].text, ai.CANCELLED)
        agent.ask("другое")
        body = ai.build_anthropic("m", "s", agent.dialog_for_request())
        roles = [m["role"] for m in body["messages"]]
        self.assertEqual(roles, ["user", "assistant", "user", "assistant",
                                 "user"])


if __name__ == "__main__":
    unittest.main()
