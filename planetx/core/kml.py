# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Чтение и запись KML и KMZ для «Моих меток», как в Google Earth.

Расчёт без Qt. Чтение даёт дерево: папки KFolder и метки KPlace.
Document и Folder становятся папками, Placemark - меткой. Point,
LineString и внешнее кольцо Polygon переносятся, MultiGeometry
разбивается на отдельные метки с тем же названием. Высоты вершин
отбрасываются, метки лежат на рельефе. Стиль берётся из styleUrl,
у StyleMap - вариант normal, и из вложенного Style. LookAt метки
становится её видом, core/lookat.py: точка взгляда longitude
и latitude, расстояние range, азимут heading, наклон tilt. Без точки
взгляда ею считается сама метка. Camera, модели, наложения картинок
и сетевые ссылки не переносятся.

Высота над землёй переносится у altitudeMode relativeToGround
и gx:relativeToSeaFloor: высота первой вершины становится подъёмом
метки, extrude - стеной до земли. absolute отсчитывается от уровня
моря, рельефа при чтении ещё нет, такие метки ложатся на землю.

Цвет в KML записан как aabbggrr в шестнадцатеричном виде, в меткам
идёт RGBA 0-255.

KMZ - архив ZIP, из него читается первый файл .kml, doc.kml
раньше других.

Разбор идёт через expat напрямую, в своё лёгкое дерево. Объявления
сущностей в DTD запрещены, файл с ними не читается: так чужой файл
не раздует память вложенными сущностями. xml.etree и xml.sax сканер
Bandit каталога QGIS считает опасными для чужих файлов.
"""
import io
import re
import zipfile
from xml.parsers import expat

try:  # внутри плагина QGIS
    from . import lookat
except ImportError:  # headless-тесты
    import lookat

NS = "http://www.opengis.net/kml/2.2"
# Цвета Google Earth по умолчанию: жёлтая линия, белая заливка.
LINE_COLOR = (255, 255, 0, 255)
FILL_COLOR = (255, 255, 255, 64)
LINE_WIDTH = 2.0


class KmlError(ValueError):
    """Файл не читается как KML или KMZ."""


class _Node:
    """Элемент XML: имя без пространства имён, атрибуты, текст, дети."""

    def __init__(self, tag, attrib):
        self.tag = tag.rsplit("}", 1)[-1].rsplit(":", 1)[-1]
        self.attrib = attrib
        self.text = ""
        self.children = []

    def __iter__(self):
        return iter(self.children)

    def get(self, name, default=None):
        return self.attrib.get(name, default)

    def iter(self):
        yield self
        for child in self.children:
            yield from child.iter()


def _parse(data):
    """Корень _Node из байтов XML. Сущности DTD запрещены."""
    parser = expat.ParserCreate()
    stack = []
    root = []

    def start(tag, attrib):
        node = _Node(tag, attrib)
        if stack:
            stack[-1].children.append(node)
        else:
            root.append(node)
        stack.append(node)

    def end(tag):
        stack.pop()

    def chars(data):
        if stack:
            stack[-1].text += data

    def entity(*args):
        raise KmlError("DTD entities are not allowed")

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = chars
    parser.EntityDeclHandler = entity
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    try:
        parser.Parse(data, True)
    except expat.ExpatError as error:
        raise KmlError(str(error)) from error
    if not root:
        raise KmlError("empty XML")
    return root[0]


def escape(text):
    """Текст для XML: &, <, > заменены."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;") \
        .replace(">", "&gt;")


class KFolder:
    """Папка KML: название, флажок, дети KFolder и KPlace."""

    def __init__(self, name="", visible=True, children=None):
        self.name = name
        self.visible = visible
        self.children = children if children is not None else []

    def places(self):
        """Все метки внутри, на любой глубине."""
        out = []
        for child in self.children:
            out.extend(child.places() if isinstance(child, KFolder)
                       else [child])
        return out


class KPlace:
    """Метка KML в виде «Моих меток».

    kind - "point", "line", "polygon". points - (широта, долгота).
    color, fill - RGBA 0-255, fill только у многоугольника. view -
    вид core.lookat: (широта, долгота, расстояние, азимут, наклон)
    или None.
    """

    def __init__(self, name, kind, points, color=LINE_COLOR,
                 width=LINE_WIDTH, fill=None, visible=True, view=None,
                 description="", height=0.0, extrude=False):
        self.height = height
        self.extrude = extrude
        self.name = name
        self.kind = kind
        self.points = points
        self.color = color
        self.width = width
        self.fill = fill
        self.visible = visible
        self.view = view
        self.description = description


def _local(tag):
    return tag


def _child(node, name):
    for child in node:
        if _local(child.tag) == name:
            return child
    return None


def _children(node, name):
    return [child for child in node if _local(child.tag) == name]


def _text(node, name, default=""):
    child = _child(node, name) if node is not None else None
    if child is None or child.text is None:
        return default
    return child.text.strip()


def _float(node, name, default):
    try:
        return float(_text(node, name, ""))
    except ValueError:
        return default


def kml_color(text, default):
    """RGBA из цвета KML aabbggrr или default."""
    text = (text or "").strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{8}", text):
        return default
    a, b, g, r = (int(text[i:i + 2], 16) for i in range(0, 8, 2))
    return (r, g, b, a)


def color_kml(rgba):
    """Цвет KML aabbggrr из RGBA."""
    r, g, b, a = (int(v) & 255 for v in rgba)
    return "{:02x}{:02x}{:02x}{:02x}".format(a, b, g, r)


def _pair(item):
    """(широта, долгота) из «lon,lat[,alt]» или None, если не число
    или вне пределов."""
    parts = item.split(",")
    try:
        lon, lat = float(parts[0]), float(parts[1])
    except (ValueError, IndexError):
        return None
    if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
        return lat, lon
    return None


def _coords(node):
    """Вершины (широта, долгота) из coordinates: «lon,lat[,alt] ...»."""
    text = _text(node, "coordinates")
    pairs = (_pair(item) for item in text.split())
    return [pair for pair in pairs if pair is not None]


RELATIVE = ("relativeToGround", "relativeToSeaFloor")


def _raise(node, coords):
    """Подъём над землёй и выдавливание геометрии node."""
    mode = _text(node, "altitudeMode")
    if mode not in RELATIVE:
        return 0.0, False
    first = _text(coords, "coordinates").split()[:1] if coords is not None \
        else []
    parts = first[0].split(",") if first else []
    try:
        height = max(float(parts[2]), 0.0) if len(parts) > 2 else 0.0
    except ValueError:
        height = 0.0
    return height, _text(node, "extrude", "0") == "1"


def _geometries(node):
    """(вид, вершины, подъём, выдавливание) всех геометрий Placemark,
    MultiGeometry по частям."""
    out = []
    for child in node:
        name = _local(child.tag)
        if name == "Point":
            points = _coords(child)[:1]
            if points:
                out.append(("point", points) + _raise(child, child))
        elif name in ("LineString", "LinearRing"):
            points = _coords(child)
            if len(points) >= 2:
                out.append(("line", points) + _raise(child, child))
        elif name == "Polygon":
            outer = _child(child, "outerBoundaryIs")
            ring = _child(outer, "LinearRing") if outer is not None else None
            points = _coords(ring) if ring is not None else []
            if len(points) > 1 and points[0] == points[-1]:
                points = points[:-1]
            if len(points) >= 3:
                out.append(("polygon", points) + _raise(child, ring))
        elif name == "MultiGeometry":
            out.extend(_geometries(child))
    return out


def _style_of(node):
    """Стиль узла Style: цвет и толщина линии, цвет и флаг заливки."""
    style = {}
    line = _child(node, "LineStyle")
    if line is not None:
        style["color"] = kml_color(_text(line, "color"), None)
        style["width"] = _float(line, "width", None)
    poly = _child(node, "PolyStyle")
    if poly is not None:
        style["fill"] = kml_color(_text(poly, "color"), None)
        style["filled"] = _text(poly, "fill", "1") != "0"
    icon = _child(node, "IconStyle")
    if icon is not None:
        style["icon"] = kml_color(_text(icon, "color"), None)
    return {k: v for k, v in style.items() if v is not None}


def _styles(root):
    """Стили документа по id: Style и StyleMap (вариант normal)."""
    styles = {}
    maps = {}
    for node in root.iter():
        name = _local(node.tag)
        sid = node.get("id")
        if not sid:
            continue
        if name == "Style":
            styles[sid] = _style_of(node)
        elif name == "StyleMap":
            for pair in _children(node, "Pair"):
                if _text(pair, "key") == "normal":
                    maps[sid] = _text(pair, "styleUrl").lstrip("#")
    for sid, target in maps.items():
        styles[sid] = styles.get(target, {})
    return styles


def _view(node, anchor):
    """Вид из LookAt. Без точки взгляда ею считается anchor."""
    look = _child(node, "LookAt")
    if look is None:
        return None
    lat = _float(look, "latitude", anchor[0]) if anchor else \
        _float(look, "latitude", 0.0)
    lon = _float(look, "longitude", anchor[1]) if anchor else \
        _float(look, "longitude", 0.0)
    return lookat.make(lat, lon, _float(look, "range", 0.0),
                       _float(look, "heading", 0.0),
                       _float(look, "tilt", 0.0))


def _visible(node):
    return _text(node, "visibility", "1") != "0"


def _placemark(node, styles):
    style = dict(styles.get(_text(node, "styleUrl").lstrip("#"), {}))
    inline = _child(node, "Style")
    if inline is not None:
        style.update(_style_of(inline))
    name = _text(node, "name")
    out = []
    for kind, points, height, extrude in _geometries(node):
        view = _view(node, points[0] if points else None)
        color = style.get("icon" if kind == "point" else "color") \
            or LINE_COLOR
        fill = None
        if kind == "polygon":
            fill = style.get("fill", FILL_COLOR) if style.get(
                "filled", True) else None
        out.append(KPlace(name, kind, points, color=color,
                          width=style.get("width", LINE_WIDTH), fill=fill,
                          visible=_visible(node),
                          view=view,
                          description=_text(node, "description"),
                          height=height, extrude=extrude))
    return out


def _walk(node, styles, folder):
    for child in node:
        name = _local(child.tag)
        if name in ("Folder", "Document"):
            sub = KFolder(_text(child, "name"), _visible(child))
            _walk(child, styles, sub)
            folder.children.append(sub)
        elif name == "Placemark":
            folder.children.extend(_placemark(child, styles))


def read_kml(data, name=""):
    """Дерево KFolder из байтов KML. name - название корня."""
    root = _parse(data)
    if _local(root.tag) != "kml":
        raise KmlError("not KML")
    styles = _styles(root)
    top = KFolder(name)
    _walk(root, styles, top)
    # Один Document - его содержимое и есть корень. Название - имя
    # документа, как в Google Earth, без него - name, обычно имя файла.
    if len(top.children) == 1 and isinstance(top.children[0], KFolder):
        only = top.children[0]
        top = KFolder(only.name or name, only.visible, only.children)
    return top


def read_kmz(data, name=""):
    """Дерево KFolder из байтов KMZ."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = [n for n in archive.namelist()
                     if n.lower().endswith(".kml")]
            if not names:
                raise KmlError("no KML in KMZ")
            names.sort(key=lambda n: (n.lower() != "doc.kml", n))
            return read_kml(archive.read(names[0]), name)
    except zipfile.BadZipFile as error:
        raise KmlError(str(error)) from error


def read_file(data, name=""):
    """KML или KMZ по содержимому: KMZ начинается с подписи ZIP."""
    if data[:2] == b"PK":
        return read_kmz(data, name)
    return read_kml(data, name)


# Запись.

def _coord_text(points, close=False, height=0.0):
    pts = list(points) + (list(points[:1]) if close else [])
    return " ".join("{:.8f},{:.8f},{:g}".format(lon, lat, height)
                    for lat, lon in pts)


def _raise_kml(place):
    """Режим высоты и выдавливание геометрии для записи."""
    if not place.height:
        return ""
    return "<extrude>{}</extrude><altitudeMode>relativeToGround" \
        "</altitudeMode>".format(int(bool(place.extrude)))


def _placemark_kml(place, indent):
    pad = "  " * indent
    style = ""
    if place.kind == "point":
        style = "<IconStyle><color>{}</color></IconStyle>".format(
            color_kml(place.color))
    else:
        style = "<LineStyle><color>{}</color><width>{:g}</width>" \
            "</LineStyle>".format(color_kml(place.color), place.width)
        if place.kind == "polygon":
            style += "<PolyStyle><color>{}</color><fill>{}</fill>" \
                "</PolyStyle>".format(color_kml(place.fill or FILL_COLOR),
                                      1 if place.fill else 0)
    mode = _raise_kml(place)
    h = float(place.height or 0.0)
    if place.kind == "point":
        geometry = "<Point>{}<coordinates>{}</coordinates></Point>".format(
            mode, _coord_text(place.points, height=h))
    elif place.kind == "line":
        geometry = "<LineString><tessellate>1</tessellate>{}<coordinates>" \
            "{}</coordinates></LineString>".format(
                mode, _coord_text(place.points, height=h))
    else:
        geometry = "<Polygon><tessellate>1</tessellate>{}" \
            "<outerBoundaryIs><LinearRing><coordinates>{}</coordinates>" \
            "</LinearRing></outerBoundaryIs></Polygon>".format(
                mode, _coord_text(place.points, close=True, height=h))
    look = ""
    if place.view is not None:
        lat, lon, distance, heading, tilt = place.view
        look = "<LookAt><longitude>{:.8f}</longitude><latitude>{:.8f}" \
            "</latitude><altitude>0</altitude><heading>{:g}</heading>" \
            "<tilt>{:g}</tilt><range>{:g}</range></LookAt>".format(
                lon, lat, heading, tilt, distance)
    parts = ["<Placemark>", "<name>{}</name>".format(escape(place.name))]
    if place.description:
        parts.append("<description>{}</description>".format(
            escape(place.description)))
    parts += ["<visibility>{}</visibility>".format(int(place.visible)),
              look, "<Style>{}</Style>".format(style), geometry,
              "</Placemark>"]
    return pad + "".join(p for p in parts if p)


def _folder_kml(folder, indent, tag="Folder"):
    pad = "  " * indent
    lines = [pad + "<{}>".format(tag),
             pad + "  <name>{}</name>".format(escape(folder.name)),
             pad + "  <visibility>{}</visibility>".format(
                 int(folder.visible))]
    for child in folder.children:
        if isinstance(child, KFolder):
            lines.extend(_folder_kml(child, indent + 1))
        else:
            lines.append(_placemark_kml(child, indent + 1))
    lines.append(pad + "</{}>".format(tag))
    return lines


def write_kml(folder):
    """Текст KML папки: Document с вложенными Folder и Placemark."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<kml xmlns="{}">'.format(NS)]
    lines.extend(_folder_kml(folder, 1, "Document"))
    lines.append("</kml>")
    return "\n".join(lines) + "\n"


def write_kmz(folder):
    """Байты KMZ: архив с doc.kml."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("doc.kml", write_kml(folder).encode("utf-8"))
    return buffer.getvalue()
