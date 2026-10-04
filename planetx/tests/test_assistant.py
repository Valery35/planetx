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


class TestChat(unittest.TestCase):

    def test_request_and_round_trip(self):
        dialog = [{"role": "user", "text": "Покажи Японию"}]
        url, headers, body = ai.request(
            ai.OPENROUTER, "https://openrouter.ai/api/v1/", "m:free", "k",
            "sys", dialog)
        self.assertEqual(url, "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(headers["Authorization"], "Bearer k")
        self.assertEqual(body["messages"][0],
                         {"role": "system", "content": "sys"})
        self.assertEqual(body["tools"][0]["function"]["name"], "fly_to")
        reply = ai.parse(ai.OPENROUTER, {"choices": [{"message": {
            "role": "assistant", "content": None, "tool_calls": [
                {"id": "c1", "type": "function", "function": {
                    "name": "fly_to",
                    "arguments": '{"lat": 36, "lon": 138}'}}]}}]})
        self.assertEqual(reply.calls[0].args, {"lat": 36, "lon": 138})
        dialog += [ai.assistant_message(reply),
                   ai.results_message([ai.Result("c1", "Перелёт.")])]
        body = ai.build_chat("m", "sys", dialog)
        self.assertEqual(body["messages"][2]["tool_calls"][0]["id"], "c1")
        self.assertEqual(body["messages"][3], {
            "role": "tool", "tool_call_id": "c1", "content": "Перелёт."})

    def test_text_error_and_arguments_as_object(self):
        reply = ai.parse(ai.LOCAL, {"choices": [{"message": {
            "content": "Готово.", "tool_calls": [{"function": {
                "name": "get_kml", "arguments": {}}}]}}]})
        self.assertEqual(reply.text, "Готово.")
        self.assertEqual(reply.calls[0].id, "call0")
        self.assertEqual(ai.parse(ai.LOCAL, {"error": {"message": "x"}})
                         .error, "x")
        self.assertEqual(ai.parse(ai.LOCAL, {"choices": []}).error,
                         "no choices")

    def test_local_service_needs_no_key(self):
        url, headers, body = ai.request(ai.LOCAL, "http://localhost:11434/v1",
                                        "qwen3", "", "sys", [])
        self.assertNotIn("Authorization", headers)
        self.assertFalse(ai.needs_key("http://localhost:11434/v1"))
        self.assertFalse(ai.needs_key("http://127.0.0.1:1234/v1"))
        self.assertFalse(ai.needs_key("http://[::1]:11434/v1"))
        self.assertTrue(ai.needs_key("https://openrouter.ai/api/v1"))

    def test_provider_error_details_and_cut_answer(self):
        reply = ai.parse(ai.OPENROUTER, {"error": {
            "message": "Provider returned error", "code": 429,
            "metadata": {"provider_name": "ModelRun",
                         "raw": "rate limited upstream"}}})
        self.assertEqual(reply.error, "Provider returned error (ModelRun): "
                         "rate limited upstream")
        # Рассуждение съело предел, ответа нет - это ошибка, а не тишина.
        reply = ai.parse(ai.OPENROUTER, {"choices": [{
            "finish_reason": "length",
            "message": {"content": None, "reasoning": "..."}}]})
        self.assertIn("finish_reason length", reply.error)

    def test_openrouter_asks_for_short_reasoning(self):
        dialog = [{"role": "user", "text": "Привет"}]
        body = ai.request(ai.OPENROUTER, "https://openrouter.ai/api/v1", "m",
                          "k", "sys", dialog)[2]
        self.assertEqual(body["reasoning"], {"effort": "low"})
        self.assertEqual(body["max_tokens"], ai.CHAT_MAX_TOKENS)
        self.assertNotIn("models", body)
        body = ai.request(ai.LOCAL, "http://localhost:11434/v1", "m", "",
                          "sys", dialog)[2]
        self.assertNotIn("reasoning", body)

    def test_free_model_falls_back_to_free_router(self):
        body = ai.request(ai.OPENROUTER, "https://openrouter.ai/api/v1",
                          "qwen/qwen3.8-27b:free", "k", "sys", [])[2]
        self.assertEqual(body["models"], ["qwen/qwen3.8-27b:free",
                                          "openrouter/free"])
        self.assertEqual(ai.DEFAULTS[ai.OPENROUTER][1], "openrouter/free")
        body = ai.request(ai.OPENROUTER, "https://openrouter.ai/api/v1",
                          "openrouter/free", "k", "sys", [])[2]
        self.assertNotIn("models", body)

    def test_deepseek_speaks_anthropic(self):
        url, headers, body = ai.request(
            ai.DEEPSEEK, *ai.DEFAULTS[ai.DEEPSEEK], key="k", system="sys",
            dialog=[{"role": "user", "text": "Привет"}])
        self.assertEqual(url,
                         "https://api.deepseek.com/anthropic/v1/messages")
        self.assertEqual(headers["x-api-key"], "k")
        self.assertEqual(body["system"], "sys")

    def test_every_provider_has_format_and_defaults(self):
        for provider in ai.PROVIDERS:
            self.assertIn(provider, ai.FORMAT)
            self.assertIn(provider, ai.DEFAULTS)


class TestKmlGeneration(unittest.TestCase):

    def test_request_without_tools_and_with_limit(self):
        dialog = [{"role": "user", "text": "Путешествие Колумба"}]
        for provider, field in ((ai.ANTHROPIC, "max_tokens"),
                                (ai.OPENROUTER, "max_tokens"),
                                (ai.RESPONSES, "max_output_tokens")):
            body = ai.request(provider, ai.DEFAULTS[provider][0], "m", "k",
                              ai.kml_system_text({}), dialog, tools=False,
                              max_tokens=ai.KML_MAX_TOKENS)[2]
            self.assertNotIn("tools", body, provider)
            self.assertEqual(body[field], ai.KML_MAX_TOKENS, provider)
        # Обычный запрос инструменты несёт.
        self.assertIn("tools", ai.request(ai.ANTHROPIC, "b", "m", "k", "s",
                                          dialog)[2])

    def test_extract_kml_from_fenced_answer(self):
        doc = '<kml xmlns="x"><Document><name>А</name></Document></kml>'
        text = "Вот документ:\n```xml\n<?xml version=\"1.0\"?>\n" + doc \
            + "\n```\nГотово."
        self.assertEqual(ai.extract_kml(text), doc)
        self.assertIsNone(ai.extract_kml("Не могу."))
        self.assertIsNone(ai.extract_kml(""))

    def test_extract_kml_closes_cut_document(self):
        text = ('<kml xmlns="x"><Document><name>А</name><Folder>'
                "<name>Ф</name><Placemark><name>1</name></Placemark>"
                "<Placemark><name>2</name><Point><coord")
        got = ai.extract_kml(text)
        self.assertTrue(got.endswith(
            "<Placemark><name>1</name></Placemark></Folder></Document>"
            "</kml>"))
        # Оборван до первой целой метки - документа нет.
        self.assertIsNone(ai.extract_kml('<kml><Document><Placemark><na'))

    def test_extract_kml_odd_answers(self):
        one = '<kml xmlns="x"><Document><name>А</name></Document></kml>'
        self.assertEqual(ai.extract_kml(one + "\nи ещё\n" + one), one)
        got = ai.extract_kml("Вот:\n<Document><name>Б</name></Document>")
        self.assertTrue(got.startswith("<kml "))
        self.assertTrue(got.endswith("</Document></kml>"))
        cut = ('<kml><Document><Folder><name>Ф</name></Folder>'
               "<Folder><name>Г</name><LineString><coordinates>1,2")
        self.assertEqual(ai.extract_kml(cut),
                         '<kml><Document><Folder><name>Ф</name></Folder>'
                         "</Document></kml>")

    def test_prompt_asks_time_and_space_everywhere(self):
        text = ai.kml_system_text({})
        for word in ("TimeStamp", "TimeSpan", "-0264", "этап", "растёт",
                     "LineString", "Polygon", "сменяют", "styleUrl",
                     str(ai.KML_PLACES)):
            self.assertIn(word, text)
        # Разговор с инструментами получает те же правила документа.
        self.assertIn("сменяют", ai.system_text({}))

    def test_stream_flag(self):
        dialog = [{"role": "user", "text": "Тема"}]
        for provider in (ai.ANTHROPIC, ai.OPENROUTER, ai.RESPONSES):
            body = ai.request(provider, "b", "m", "k", "s", dialog,
                              tools=False, stream=True)[2]
            self.assertIs(body["stream"], True, provider)
        self.assertNotIn("stream", ai.request(ai.ANTHROPIC, "b", "m", "k",
                                              "s", dialog)[2])

    def test_length_refused(self):
        self.assertTrue(ai.length_refused(
            "max_tokens: 16000 > 8192, which is the maximum allowed"))
        self.assertTrue(ai.length_refused("Token limit exceeded"))
        self.assertFalse(ai.length_refused("Provider returned error"))
        self.assertFalse(ai.length_refused(""))

    def test_time_span_and_bc_dates_read(self):
        import kml
        text = ('<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
                "<name>Пунические войны</name><Placemark><name>Первая "
                "война</name><TimeSpan><begin>-0263</begin><end>-0240"
                "</end></TimeSpan><Point><coordinates>10.3,36.8,0"
                "</coordinates></Point></Placemark><Placemark><name>Канны"
                "</name><TimeStamp><when>-0215-08-02</when></TimeStamp>"
                "<Point><coordinates>16.13,41.3,0</coordinates></Point>"
                "</Placemark></Document></kml>")
        tree = kml.read_kml(ai.extract_kml(text).encode("utf-8"))
        times = [p.time for p in tree.places()]
        self.assertEqual(times[0], ("-0263", "-0240"))
        self.assertEqual(times[1], ("-0215-08-02", "-0215-08-02"))

    def test_cut_document_reads_as_kml(self):
        import kml
        text = ('<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
                "<name>Колумб</name><Folder><name>Первое</name><Placemark>"
                "<name>Палос</name><Point><coordinates>-6.89,37.23,0"
                "</coordinates></Point></Placemark><Placemark><name>Сан")
        tree = kml.read_kml(ai.extract_kml(text).encode("utf-8"))
        self.assertEqual([p.name for p in tree.places()], ["Палос"])


def sse(*events):
    """Поток SSE из событий: словарь - строка data с JSON, строка -
    как есть."""
    lines = []
    for event in events:
        lines.append(event if isinstance(event, str)
                     else "data: " + json.dumps(event, ensure_ascii=False))
        lines.append("")
    return ("\n".join(lines) + "\n").encode("utf-8")


class TestStreamText(unittest.TestCase):

    def feed_in_pieces(self, provider, data, size):
        stream = ai.StreamText(provider)
        grew = 0
        for i in range(0, len(data), size):
            grew += bool(stream.feed(data[i:i + size]))
        stream.finish()
        return stream, grew

    def test_chat_deltas_in_any_cut(self):
        data = sse(": OPENROUTER PROCESSING",
                   {"choices": [{"delta": {"reasoning": "думаю"}}]},
                   {"choices": [{"delta": {"content": "<kml><Docu"}}]},
                   {"choices": [{"delta": {"content": "ment>Колумб"}}]},
                   {"choices": [{"delta": {}, "finish_reason": "stop"}]},
                   "data: [DONE]")
        # Порез по 1, 3 и 7 байт рвёт строки и символы UTF-8.
        for size in (1, 3, 7, 4096):
            stream, grew = self.feed_in_pieces(ai.OPENROUTER, data, size)
            self.assertEqual(stream.text, "<kml><Document>Колумб", size)
            self.assertEqual(stream.error, "")
            self.assertFalse(stream.cut)
            self.assertTrue(stream.done)
            self.assertGreaterEqual(grew, 1)

    def test_chat_cut_and_error(self):
        stream, _ = self.feed_in_pieces(ai.LOCAL, sse(
            {"choices": [{"delta": {"content": "<kml>"},
                          "finish_reason": "length"}]}), 5)
        self.assertTrue(stream.cut)
        stream, _ = self.feed_in_pieces(ai.OPENROUTER, sse(
            {"choices": [{"delta": {"content": "<kml>"}}]},
            {"error": {"message": "Provider returned error", "metadata": {
                "provider_name": "ModelRun", "raw": "overloaded"}}}), 9)
        self.assertEqual(stream.error,
                         "Provider returned error (ModelRun): overloaded")
        # Пришедший до ошибки текст остаётся.
        self.assertEqual(stream.text, "<kml>")

    def test_anthropic_events(self):
        data = sse("event: message_start",
                   {"type": "message_start", "message": {"id": "m"}},
                   "event: ping", {"type": "ping"},
                   {"type": "content_block_delta", "index": 0, "delta": {
                       "type": "thinking_delta", "thinking": "думаю"}},
                   {"type": "content_block_delta", "index": 1, "delta": {
                       "type": "text_delta", "text": "<kml>"}},
                   {"type": "content_block_delta", "index": 1, "delta": {
                       "type": "text_delta", "text": "</kml>"}},
                   {"type": "message_delta",
                    "delta": {"stop_reason": "max_tokens"}},
                   {"type": "message_stop"})
        stream, _ = self.feed_in_pieces(ai.ANTHROPIC, data, 11)
        self.assertEqual(stream.text, "<kml></kml>")
        self.assertTrue(stream.cut)
        stream, _ = self.feed_in_pieces(ai.DEEPSEEK, sse({
            "type": "error", "error": {"type": "overloaded_error",
                                       "message": "Overloaded"}}), 6)
        self.assertEqual(stream.error, "Overloaded")

    def test_responses_events(self):
        data = sse({"type": "response.created", "response": {}},
                   {"type": "response.output_text.delta", "delta": "<kml>"},
                   {"type": "response.output_text.delta", "delta": "</kml>"},
                   {"type": "response.completed", "response": {}})
        stream, _ = self.feed_in_pieces(ai.RESPONSES, data, 13)
        self.assertEqual(stream.text, "<kml></kml>")
        self.assertFalse(stream.cut)
        stream, _ = self.feed_in_pieces(ai.RESPONSES, sse(
            {"type": "response.output_text.delta", "delta": "<kml>"},
            {"type": "response.incomplete", "response": {}}), 13)
        self.assertTrue(stream.cut)
        stream, _ = self.feed_in_pieces(ai.RESPONSES, sse({
            "type": "response.failed",
            "response": {"error": {"message": "bad key"}}}), 13)
        self.assertEqual(stream.error, "bad key")

    def test_plain_json_answer_instead_of_stream(self):
        # Ошибка HTTP приходит телом JSON, не потоком.
        refused = json.dumps({"error": {
            "message": "max_tokens: 16000 > 8192"}}).encode("utf-8")
        stream, _ = self.feed_in_pieces(ai.OPENROUTER, refused, 10)
        self.assertEqual(stream.error, "max_tokens: 16000 > 8192")
        self.assertTrue(ai.length_refused(stream.error))
        # Сервис без потока отвечает обычным телом - текст берётся.
        whole = json.dumps({"choices": [{"message": {
            "content": "<kml></kml>"}}]}).encode("utf-8")
        stream, _ = self.feed_in_pieces(ai.LOCAL, whole, 10)
        self.assertEqual(stream.text, "<kml></kml>")
        self.assertEqual(stream.error, "")
        whole = json.dumps({"type": "error", "error": {
            "message": "invalid x-api-key"}}).encode("utf-8")
        stream, _ = self.feed_in_pieces(ai.ANTHROPIC, whole, 10)
        self.assertEqual(stream.error, "invalid x-api-key")

    def test_progress_counts_whole_placemarks(self):
        text = ("<kml><Document><Placemark><name>1</name></Placemark>"
                "<Placemark><name>2</name></Placemark><Placemark><na")
        self.assertEqual(ai.kml_progress(text), 2)
        self.assertEqual(ai.kml_progress(""), 0)


class TestIsRequest(unittest.TestCase):

    def test_places_and_coordinates_are_not_requests(self):
        for text in ("Пермь", "Нью-Йорк", "Красная площадь", "Mount Everest",
                     "58.0105, 56.2294", "ул. Ленина 1, Пермь", ""):
            self.assertFalse(ai.is_request(text), text)

    def test_requests(self):
        for text in ("покажи разрез через Японский жёлоб",
                     "Где самые глубокие землетрясения у Японии",
                     "что под Березниками?", "Show Mars",
                     "fly, please, to the deepest point of the ocean now",
                     "Эльбрус?"):
            self.assertTrue(ai.is_request(text), text)


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
