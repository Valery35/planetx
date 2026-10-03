# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""ИИ-помощник: запросы и ответы Anthropic Messages и OpenAI Responses."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import assistant as ai  # noqa: E402


class TestAnthropic(unittest.TestCase):

    def test_request_and_round_trip(self):
        dialog = [{"role": "user", "text": "Покажи Японию"}]
        url, headers, body = ai.request(ai.ANTHROPIC, "https://h/", "m",
                                        "k", "sys", dialog)
        self.assertEqual(url, "https://h/v1/messages")
        self.assertEqual(headers["x-api-key"], "k")
        self.assertEqual(body["messages"][0]["content"], "Покажи Японию")
        self.assertEqual({t["name"] for t in body["tools"]},
                         set(ai.TOOL_NAMES))
        reply = ai.parse(ai.ANTHROPIC, {"content": [
            {"type": "text", "text": "Лечу."},
            {"type": "tool_use", "id": "t1", "name": "fly_to",
             "input": {"lat": 36.0, "lon": 138.0}}],
            "stop_reason": "tool_use"})
        self.assertEqual(reply.text, "Лечу.")
        self.assertEqual(reply.calls, [ai.Call("t1", "fly_to",
                                               {"lat": 36.0, "lon": 138.0})])
        dialog += [ai.assistant_message(reply),
                   ai.results_message([ai.Result("t1", "готово")])]
        body = ai.build_anthropic("m", "sys", dialog)
        self.assertEqual(body["messages"][1]["content"][1]["type"],
                         "tool_use")
        self.assertEqual(body["messages"][2]["content"][0],
                         {"type": "tool_result", "tool_use_id": "t1",
                          "content": "готово"})

    def test_error(self):
        reply = ai.parse(ai.ANTHROPIC, {"type": "error", "error": {
            "type": "authentication_error", "message": "invalid x-api-key"}})
        self.assertEqual(reply.error, "invalid x-api-key")


class TestResponses(unittest.TestCase):

    def test_request_and_round_trip(self):
        dialog = [{"role": "user", "text": "Где глубокие землетрясения?"}]
        url, headers, body = ai.request(ai.RESPONSES, "https://api.x.ai/v1",
                                        "grok", "k", "sys", dialog)
        self.assertEqual(url, "https://api.x.ai/v1/responses")
        self.assertEqual(headers["Authorization"], "Bearer k")
        self.assertEqual(body["instructions"], "sys")
        self.assertEqual(body["tools"][0]["type"], "function")
        call = {"type": "function_call", "call_id": "c1",
                "name": "quakes_summary",
                "arguments": json.dumps({"south": 30, "north": 45,
                                         "west": 130, "east": 150})}
        reply = ai.parse(ai.RESPONSES, {"output": [call]})
        self.assertEqual(reply.calls[0].name, "quakes_summary")
        self.assertEqual(reply.calls[0].args["north"], 45)
        dialog += [ai.assistant_message(reply),
                   ai.results_message([ai.Result("c1", "12 событий")])]
        body = ai.build_responses("grok", "sys", dialog)
        # Вызов модели возвращается как есть, за ним - ответ инструмента.
        self.assertEqual(body["input"][1], call)
        self.assertEqual(body["input"][2], {"type": "function_call_output",
                                            "call_id": "c1",
                                            "output": "12 событий"})

    def test_text_and_bad_arguments(self):
        reply = ai.parse(ai.RESPONSES, {"output": [
            {"type": "message", "content": [
                {"type": "output_text", "text": "Готово."}]},
            {"type": "function_call", "call_id": "c2", "name": "fly_to",
             "arguments": "{oops"}]})
        self.assertEqual(reply.text, "Готово.")
        self.assertEqual(reply.calls[0].args, {})

    def test_error(self):
        reply = ai.parse(ai.RESPONSES, {"error": {"message": "bad key"}})
        self.assertEqual(reply.error, "bad key")


class TestHelpers(unittest.TestCase):

    def test_look_at_kml_reads_back(self):
        import kml
        text = ai.look_at_kml(38.5, 142.0, 500000.0, 30.0, 60.0)
        self.assertIn("<range>500000</range>", text)
        kml.read_kml(text.encode("utf-8"), "вид")

    def test_quakes_text(self):
        import quakes as qk
        events = [qk.Quake(38.0, 142.0, 30.0, 6.1, None, "A", ""),
                  qk.Quake(40.0, 179.5, 600.0, 5.0, None, "B", ""),
                  qk.Quake(0.0, 0.0, 10.0, 7.0, None, "C", "")]
        text = ai.quakes_text(events, (30.0, 45.0, 140.0, -170.0))
        self.assertIn("Событий в рамке: 2.", text)
        self.assertNotIn(", C", text)
        self.assertTrue(text.index("M6.1") < text.index("Самые глубокие"))
        self.assertIn("нет", ai.quakes_text(events, (-10, -5, 0, 1)))

    def test_tools_have_schemas(self):
        self.assertIn("add_kml", ai.TOOL_NAMES)
        self.assertIn("get_kml", ai.TOOL_NAMES)
        for name, text, schema in ai.TOOLS:
            self.assertEqual(schema["type"], "object", name)
            self.assertTrue(text, name)


if __name__ == "__main__":
    unittest.main()
