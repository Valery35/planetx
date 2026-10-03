# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""ИИ-помощник: инструменты, запросы и разбор ответов моделей. Без Qt.

Просьба автора от 3 октября 2026 года - помощник внутри модуля,
модели Claude (Anthropic) и Grok (xAI). Подключения два:

- «anthropic» - Messages API, POST {base}/v1/messages, заголовки
  x-api-key и anthropic-version;
- «responses» - формат OpenAI Responses, POST {base}/responses,
  заголовок Authorization: Bearer. Так работает xAI
  (https://api.x.ai/v1, сверено по документации xAI 3 октября 2026
  года), и другие сервисы этого формата.

Метки помощник предлагает документом KML (add_kml), как вставка KML из
буфера обмена, решение автора того же дня - «KML в основе». Обратно
модель получает KML через get_kml: вид камеры и метки, выделенные
пользователем. Выделение - согласие пользователя отдать эти метки
модели.

Ключ - у пользователя, в менеджере паролей QGIS. В модель уходят текст
запроса, точка взгляда и включённые строки раздела «Слои», названия
слоёв проекта и «Моих меток» не уходят (решение автора того же дня).

Диалог - список сообщений в нейтральном виде: {"role": "user" |
"assistant", "text": ..., "calls": [Call], "results": [Result]}.
build_* переводит его в тело запроса подключения, parse_* разбирает
ответ в Reply.
"""
import json
from collections import namedtuple

ANTHROPIC = "anthropic"
RESPONSES = "responses"
PROVIDERS = (ANTHROPIC, RESPONSES)
# Подключения по умолчанию: адрес и модель. Выбор помощника, модели
# утверждает автор. grok-4.7 - пример модели из документации xAI.
DEFAULTS = {
    ANTHROPIC: ("https://api.anthropic.com", "claude-sonnet-5-5"),
    RESPONSES: ("https://api.x.ai/v1", "grok-4.7"),
}
ANTHROPIC_VERSION = "2023-06-01"
MAX_TOKENS = 2048
MAX_ROUNDS = 6  # вызовов инструментов подряд в одном ответе, не больше

Call = namedtuple("Call", "id name args")
Call.__doc__ = """Вызов инструмента моделью: номер вызова, имя, словарь
аргументов."""
Result = namedtuple("Result", "id text")
Result.__doc__ = """Ответ инструмента на вызов id, текст."""
Reply = namedtuple("Reply", "text calls raw error")
Reply.__doc__ = """Разобранный ответ модели: текст, вызовы инструментов,
исходные элементы ответа для следующего запроса (формат Responses
требует вернуть их как есть), ошибка или пустая строка."""


def _obj(properties, required):
    return {"type": "object", "properties": properties,
            "required": list(required)}


NUMBER = {"type": "number"}
STRING = {"type": "string"}
POINTS = {"type": "array", "items": {"type": "array", "items": NUMBER,
                                     "minItems": 2, "maxItems": 2},
          "description": "Точки [широта, долгота] в градусах."}

# Инструменты: имя, описание для модели, схема аргументов. Описания -
# для модели, на русском, как и системная подсказка.
TOOLS = (
    ("fly_to", "Перелёт к точке. distance_km - расстояние камеры до точки "
     "взгляда, по умолчанию 500 км.",
     _obj({"lat": NUMBER, "lon": NUMBER, "distance_km": NUMBER},
          ("lat", "lon"))),
    ("search_place", "Найти место по названию и подлететь к нему.",
     _obj({"query": STRING}, ("query",))),
    ("set_body", "Показать тело: earth, mars, moon, sky или другое тело "
     "из списка body_keys контекста.",
     _obj({"body": STRING}, ("body",))),
    ("set_layer", "Включить или выключить строку раздела «Слои» по ключу "
     "из списка layer_keys контекста.",
     _obj({"key": STRING, "on": {"type": "boolean"}}, ("key", "on"))),
    ("set_time", "Открыть шкалу времени на промежуток дат ISO 8601 или "
     "закрыть её (start и end пустые).",
     _obj({"start": STRING, "end": STRING}, ())),
    ("earth_cutaway", "Вынуть из Земли сектор с гранями коры, мантии, "
     "ядра и плит: долготы west, east и широты south, north в градусах. "
     "off=true убирает сектор.",
     _obj({"west": NUMBER, "east": NUMBER, "south": NUMBER,
           "north": NUMBER, "off": {"type": "boolean"}}, ())),
    ("section_down", "Разрез Земли вниз вдоль пути по точкам до глубины "
     "depth_km (100, 300, 700, 2891 или 6371).",
     _obj({"points": POINTS, "depth_km": NUMBER}, ("points",))),
    ("point_info", "Сведения о точке: высота или глубина моря, Мохо, "
     "толщина коры и осадков (CRUST1.0), плита Slab2 под точкой.",
     _obj({"lat": NUMBER, "lon": NUMBER}, ("lat", "lon"))),
    ("quakes_summary", "Землетрясения за 30 суток (сводка USGS, M4.5+) "
     "в рамке south, north, west, east: количество, самые сильные "
     "и самые глубокие.",
     _obj({"south": NUMBER, "north": NUMBER, "west": NUMBER,
           "east": NUMBER}, ("south", "north", "west", "east"))),
    ("add_kml", "Предложить пользователю документ KML 2.2 для «Моих "
     "меток»: Placemark с Point, LineString, Polygon, Folder, Style, "
     "LookAt, TimeStamp и TimeSpan, gx:Tour. Координаты KML - долгота, "
     "широта, высота. Пользователь видит состав документа и подтверждает "
     "запись сам, документ ложится новой папкой с именем документа.",
     _obj({"kml": STRING}, ("kml",))),
    ("get_kml", "Получить KML: вид камеры (LookAt) и метки, пути, "
     "многоугольники и папки, которые пользователь выделил в «Моих "
     "метках». Невыделенные метки недоступны. Так помощник читает "
     "и правит метки пользователя: правка возвращается через add_kml.",
     _obj({}, ())),
)
TOOL_NAMES = tuple(t[0] for t in TOOLS)


def system_text(context):
    """Системная подсказка: роль помощника и контекст вида. context -
    словарь, его собирает окно (точка взгляда, тело, строки)."""
    return (
        "Ты - помощник трёхмерного глобуса PlanetX внутри QGIS. "
        "Отвечай кратко, на языке пользователя. Действуй через "
        "инструменты, координаты - широта и долгота в градусах. Если "
        "для ответа нужны данные - вызови point_info или "
        "quakes_summary, не выдумывай чисел. Метки, пути, "
        "многоугольники, папки и туры - только документом KML через "
        "add_kml, пользователь подтверждает запись сам.\n"
        "Контекст вида: " + json.dumps(context, ensure_ascii=False))


def build_anthropic(model, system, dialog):
    """Тело запроса Messages API."""
    messages = []
    for m in dialog:
        if m["role"] == "user":
            if m.get("results"):
                content = [{"type": "tool_result", "tool_use_id": r.id,
                            "content": r.text} for r in m["results"]]
            else:
                content = m["text"]
            messages.append({"role": "user", "content": content})
        else:
            content = []
            if m.get("text"):
                content.append({"type": "text", "text": m["text"]})
            for c in m.get("calls", ()):
                content.append({"type": "tool_use", "id": c.id,
                                "name": c.name, "input": c.args})
            messages.append({"role": "assistant", "content": content})
    return {"model": model, "max_tokens": MAX_TOKENS, "system": system,
            "tools": [{"name": n, "description": d, "input_schema": s}
                      for n, d, s in TOOLS],
            "messages": messages}


def parse_anthropic(data):
    """Ответ Messages API в Reply."""
    if not isinstance(data, dict):
        return Reply("", [], None, "no data")
    if data.get("type") == "error":
        error = data.get("error") or {}
        return Reply("", [], None, str(error.get("message") or error))
    texts, calls = [], []
    for block in data.get("content") or []:
        if block.get("type") == "text":
            texts.append(block.get("text", ""))
        elif block.get("type") == "tool_use":
            calls.append(Call(block.get("id", ""), block.get("name", ""),
                              block.get("input") or {}))
    return Reply("\n".join(t for t in texts if t), calls, None, "")


def build_responses(model, system, dialog):
    """Тело запроса формата OpenAI Responses. Элементы ответа модели
    (raw) возвращаются в input как есть, за ними - ответы инструментов."""
    items = []
    for m in dialog:
        if m["role"] == "user":
            if m.get("results"):
                items += [{"type": "function_call_output", "call_id": r.id,
                           "output": r.text} for r in m["results"]]
            else:
                items.append({"role": "user", "content": m["text"]})
        elif m.get("raw"):
            items += m["raw"]
        elif m.get("text"):
            items.append({"role": "assistant", "content": m["text"]})
    return {"model": model, "instructions": system, "input": items,
            "tools": [{"type": "function", "name": n, "description": d,
                       "parameters": s} for n, d, s in TOOLS]}


def parse_responses(data):
    """Ответ формата Responses в Reply."""
    if not isinstance(data, dict):
        return Reply("", [], None, "no data")
    if data.get("error"):
        error = data["error"]
        return Reply("", [], None, str(error.get("message") or error)
                     if isinstance(error, dict) else str(error))
    texts, calls, raw = [], [], []
    for item in data.get("output") or []:
        kind = item.get("type")
        if kind == "message":
            raw.append(item)
            for part in item.get("content") or []:
                if part.get("type") in ("output_text", "text"):
                    texts.append(part.get("text", ""))
        elif kind == "function_call":
            raw.append(item)
            try:
                args = json.loads(item.get("arguments") or "{}")
            except ValueError:
                args = {}
            calls.append(Call(item.get("call_id", ""),
                              item.get("name", ""), args))
    return Reply("\n".join(t for t in texts if t), calls, raw, "")


def request(provider, base, model, key, system, dialog):
    """Адрес, заголовки и тело запроса для подключения provider."""
    base = base.rstrip("/")
    if provider == ANTHROPIC:
        url = base + "/v1/messages"
        headers = {"x-api-key": key,
                   "anthropic-version": ANTHROPIC_VERSION,
                   "content-type": "application/json"}
        body = build_anthropic(model, system, dialog)
    else:
        url = base + "/responses"
        headers = {"Authorization": "Bearer " + key,
                   "content-type": "application/json"}
        body = build_responses(model, system, dialog)
    return url, headers, body


def parse(provider, data):
    return parse_anthropic(data) if provider == ANTHROPIC \
        else parse_responses(data)


def look_at_kml(lat, lon, distance, heading, tilt):
    """Документ KML с видом камеры: LookAt, расстояние в метрах."""
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
            "<LookAt><longitude>{:.6f}</longitude>"
            "<latitude>{:.6f}</latitude><altitude>0</altitude>"
            "<heading>{:.2f}</heading><tilt>{:.2f}</tilt>"
            "<range>{:.0f}</range>"
            "<altitudeMode>relativeToGround</altitudeMode></LookAt>"
            "</Document></kml>").format(lon, lat, heading, tilt, distance)


def in_box(lat, lon, box):
    """Точка в рамке (юг, север, запад, восток), рамка через линию
    перемены дат - запад больше востока."""
    south, north, west, east = box
    lon = (lon + 180.0) % 360.0 - 180.0
    across = west <= lon <= east if west <= east \
        else (lon >= west or lon <= east)
    return south <= lat <= north and across


def quakes_text(events, box, top=3):
    """Сводка землетрясений в рамке для модели: количество, самые
    сильные и самые глубокие. events - core.quakes.Quake."""
    inside = [q for q in events if in_box(q.lat, q.lon, box)]
    if not inside:
        return "В рамке землетрясений M4.5+ за 30 суток нет."

    def line(q):
        return "M{:.1f}, глубина {:.0f} км, {:.2f}, {:.2f}, {}".format(
            q.mag, q.depth, q.lat, q.lon, q.place)
    strongest = sorted(inside, key=lambda q: -q.mag)[:top]
    deepest = sorted(inside, key=lambda q: -q.depth)[:top]
    return "\n".join(
        ["Событий в рамке: {}.".format(len(inside)), "Самые сильные:"]
        + [line(q) for q in strongest] + ["Самые глубокие:"]
        + [line(q) for q in deepest])


def assistant_message(reply):
    """Сообщение модели для диалога."""
    return {"role": "assistant", "text": reply.text,
            "calls": list(reply.calls), "raw": reply.raw}


def results_message(results):
    """Ответы инструментов - следующее сообщение пользователя."""
    return {"role": "user", "results": list(results)}
