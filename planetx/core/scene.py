# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Сцена - вид глобуса целиком, который сохраняется и передаётся.

Расчёт без Qt. Сцена - тело, камера, промежуток шкалы времени, слои
проекта на глобусе ссылкой на источник, настройки вида и название
папки меток сцены. Сами метки лежат рядом в KML (core/kml.py).

Файл сцены - архив ZIP с scene.json и places.kml. Решение автора
от 28 сентября 2026 года (шаг 12). Номер формата FORMAT растёт при
несовместимых изменениях, более новый формат не читается.
"""
import io
import json
import zipfile

FORMAT = 1
SCENE_FILE = "scene.json"
PLACES_FILE = "places.kml"
EXTENSION = ".planetx"


class SceneError(ValueError):
    """Файл не читается как сцена PlanetX."""


def _number(data, key, default=None):
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        if default is None:
            raise SceneError("bad {}".format(key))
        return default
    return float(value)


class Scene:
    """Сцена глобуса.

    camera - (широта, долгота, расстояние, азимут, наклон). time -
    промежуток открытой шкалы времени глобуса или None: start, end -
    время KML в UTC. В сценах до 6 октября 2026 года это словарь
    временного контроллера QGIS: mode (0 выключен, 1 анимация,
    2 промежуток), start, end - время ISO 8601, frame - номер кадра,
    step - длина кадра в секундах. layers - список
    словарей name, provider, source, kind ("vector" или "raster").
    view - настройки вида: basemap, relief, scale, groups, language,
    extras - включены ли строки раздела «Слои» по ключам.
    places - название папки меток сцены или "". body - ключ тела
    из core.ellipsoid, камера и метки сцены стоят на нём. В сценах
    до планет тела нет, это Земля.
    """

    def __init__(self, camera, time=None, layers=(), view=None, places="",
                 name="", body="earth"):
        # Азимут и наклон по умолчанию нули.
        self.camera = (tuple(float(v) for v in camera) + (0.0, 0.0))[:5]
        self.time = dict(time) if time else None
        self.layers = [dict(layer) for layer in layers]
        self.view = dict(view or {})
        self.places = places
        self.name = name
        self.body = body

    def to_dict(self):
        lat, lon, distance, heading, tilt = self.camera
        return {"format": FORMAT, "name": self.name,
                "camera": {"lat": lat, "lon": lon, "distance": distance,
                           "heading": heading, "tilt": tilt,
                           "body": self.body},
                "time": self.time, "layers": self.layers,
                "view": self.view, "places": self.places}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise SceneError("not a scene")
        version = data.get("format")
        if not isinstance(version, int) or version < 1:
            raise SceneError("no format")
        if version > FORMAT:
            raise SceneError("format {} is newer than {}".format(version,
                                                                 FORMAT))
        cam = data.get("camera")
        if not isinstance(cam, dict):
            raise SceneError("no camera")
        camera = (_number(cam, "lat"), _number(cam, "lon"),
                  _number(cam, "distance"), _number(cam, "heading", 0.0),
                  _number(cam, "tilt", 0.0))
        if not (-90.0 <= camera[0] <= 90.0 and -180.0 <= camera[1] <= 180.0
                and camera[2] > 0.0):
            raise SceneError("camera out of range")
        layers = [layer for layer in data.get("layers") or []
                  if isinstance(layer, dict) and layer.get("source")]
        time = data.get("time") if isinstance(data.get("time"), dict) \
            else None
        view = data.get("view") if isinstance(data.get("view"), dict) \
            else {}
        places = data.get("places") if isinstance(data.get("places"),
                                                  str) else ""
        name = data.get("name") if isinstance(data.get("name"), str) else ""
        body = cam.get("body") if isinstance(cam.get("body"), str) \
            else "earth"
        return cls(camera, time, layers, view, places, name, body)


def write_scene(scene, kml_text=""):
    """Байты файла сцены: scene.json и, если есть, places.kml."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(SCENE_FILE, json.dumps(
            scene.to_dict(), ensure_ascii=False, indent=1).encode("utf-8"))
        if kml_text:
            archive.writestr(PLACES_FILE, kml_text.encode("utf-8"))
    return buffer.getvalue()


def read_scene(data):
    """Сцена и байты places.kml (или b"") из байтов файла сцены."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
            if SCENE_FILE not in names:
                raise SceneError("no scene.json")
            try:
                raw = json.loads(archive.read(SCENE_FILE).decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as error:
                raise SceneError(str(error)) from error
            kml = archive.read(PLACES_FILE) if PLACES_FILE in names \
                else b""
    except zipfile.BadZipFile as error:
        raise SceneError(str(error)) from error
    return Scene.from_dict(raw), kml
