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
взгляда ею считается сама метка. GroundOverlay, ScreenOverlay
и PhotoOverlay становятся наложениями KOverlay (core/overlays.py),
картинка из KMZ берётся по href внутри архива. Модели и сетевые
ссылки не переносятся.

Значок точки - Icon в IconStyle, адрес узнаётся по имени картинки
(core/icons.py). Время метки - TimeStamp или TimeSpan, время вида -
gx:TimeStamp или gx:TimeSpan внутри LookAt, как у Google Earth.
Время папки достаётся её меткам без своего времени. Время хранится
строками, как в файле (core/when.py). gx:Tour - записанный тур:
позы LookAt у gx:FlyTo по времени, gx:Wait держит позу.

Высота над землёй переносится у altitudeMode relativeToGround
и gx:relativeToSeaFloor: высота первой вершины становится подъёмом
метки, extrude - стеной до земли. absolute у точки отсчитывается от
уровня моря, рельефа при чтении ещё нет, такая точка ложится на землю.
Линия и многоугольник с absolute и высотой у каждой вершины - 3D-объект
линейки: высоты вершин переносятся как есть. Высоты рельефа Terrarium
отсчитаны от уровня моря, глобус ставит их над эллипсоидом, так же
ставятся и высоты 3D-объекта.

Цвет в KML записан как aabbggrr в шестнадцатеричном виде, в меткам
идёт RGBA 0-255.

KMZ - архив ZIP, из него читается первый файл .kml, doc.kml
раньше других.

Разбор идёт через expat напрямую, в своё лёгкое дерево. Объявления
сущностей в DTD запрещены, файл с ними не читается: так чужой файл
не раздует память вложенными сущностями. xml.etree и xml.sax сканер
Bandit каталога QGIS считает опасными для чужих файлов.
"""
import html
import io
import re
import zipfile
from urllib.parse import unquote
from xml.parsers import expat

try:  # внутри плагина QGIS
    from . import icons, lookat, overlays
except ImportError:  # headless-тесты
    import icons
    import lookat
    import overlays

NS = "http://www.opengis.net/kml/2.2"
GX = "http://www.google.com/kml/ext/2.2"
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


_TEXT_TAGS = re.compile(r"(<(name|description)\b[^>]*>)(.*?)(</\2\s*>)",
                        re.S)
_XML_ENTITY = re.compile(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)")


def _plain(text):
    """Текст name или description без разметки HTML, для XML."""
    if text.lstrip().startswith("<![CDATA["):
        return text
    text = re.sub(r"<\s*(br|/p|p)\b[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]*>", "", text)
    return escape(html.unescape(text))


def _mend(data):
    """Байты KML, которые expat не разобрал, после правки частых ошибок
    моделей помощника: разметка HTML и голые &, < в name и description,
    сущности HTML вроде &nbsp; и &mdash;. Одна такая ошибка теряла весь
    документ. Файл с объявлениями сущностей не правится."""
    text = data.decode("utf-8", "replace") if isinstance(data, bytes) \
        else str(data)
    if "<!ENTITY" in text:
        return None
    text = _TEXT_TAGS.sub(lambda m: m.group(1) + _plain(m.group(3))
                          + m.group(4), text)
    text = re.sub(r"&([a-zA-Z][a-zA-Z0-9]*);", lambda m: m.group(0)
                  if m.group(1) in ("amp", "lt", "gt", "quot", "apos")
                  else escape(html.unescape(m.group(0))), text)
    text = _XML_ENTITY.sub("&amp;", text)
    text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text)
    return text.encode("utf-8")


def escape(text):
    """Текст для XML: &, <, > заменены."""
    return str(text).replace("&", "&amp;").replace("<", "&lt;") \
        .replace(">", "&gt;")


class KFolder:
    """Папка KML: название, флажок, дети KFolder и KPlace.

    description - описание, view - вид core.lookat или None. Стиль
    списка, как в окне свойств папки Google Earth: radio - содержимое
    группой переключателей (listItemType radioFolder), expandable -
    папку можно раскрыть (без него checkHideChildren).
    """

    def __init__(self, name="", visible=True, children=None,
                 description="", view=None, radio=False, expandable=True):
        self.name = name
        self.visible = visible
        self.children = children if children is not None else []
        self.description = description
        self.view = view
        self.radio = radio
        self.expandable = expandable

    def places(self):
        """Все метки внутри, на любой глубине."""
        out = []
        for child in self.children:
            out.extend(child.places() if isinstance(child, KFolder)
                       else [child] if isinstance(child, KPlace) else [])
        return out

    def overlays(self):
        """Все наложения внутри, на любой глубине."""
        out = []
        for child in self.children:
            out.extend(child.overlays() if isinstance(child, KFolder)
                       else [child] if isinstance(child, KOverlay) else [])
        return out


class KPlace:
    """Метка KML в виде «Моих меток».

    kind - "point", "line", "polygon". points - (широта, долгота).
    color, fill - RGBA 0-255, fill только у многоугольника. view -
    вид core.lookat: (широта, долгота, расстояние, азимут, наклон)
    или None. icon - значок точки core.icons. time и view_time -
    время метки и вида, пара строк core.when или None. tour -
    записанный тур: позы (время, широта, долгота, расстояние,
    азимут, наклон), тогда points - точки взгляда. alts - высоты вершин
    3D-линии или 3D-многоугольника, в KML это altitudeMode absolute.
    """

    def __init__(self, name, kind, points, color=LINE_COLOR,
                 width=LINE_WIDTH, fill=None, visible=True, view=None,
                 description="", height=0.0, extrude=False,
                 icon=icons.DEFAULT, time=None, view_time=None,
                 tour=None, alts=None):
        self.alts = alts
        self.tour = tour
        self.icon = icon
        self.time = time
        self.view_time = view_time
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


class KOverlay:
    """Наложение KML: GroundOverlay, ScreenOverlay или PhotoOverlay.

    overlay - свойства core.overlays.Overlay. image - байты картинки или
    None, href - адрес картинки из файла. view, time - как у метки."""

    def __init__(self, name, overlay, image=None, href="", visible=True,
                 description="", view=None, time=None):
        self.name = name
        self.overlay = overlay
        self.image = image
        self.href = href
        self.visible = visible
        self.description = description
        self.view = view
        self.time = time

    @property
    def kind(self):
        return self.overlay.kind

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
    или вне пределов. Долгота 180-360 - запись 0-360, она переводится
    в ±180."""
    parts = item.replace("−", "-").split(",")
    try:
        lon, lat = float(parts[0]), float(parts[1])
    except (ValueError, IndexError):
        return None
    if 180.0 < abs(lon) <= 360.0:
        lon = (lon + 180.0) % 360.0 - 180.0
    if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
        return lat, lon
    return None


def _items(node):
    """Записи «lon,lat[,alt]» из coordinates узла. Пробелы вокруг
    запятых снимаются: модели помощника пишут «lon, lat, alt», 4 октября
    2026 года так пропали все метки документа о Колумбе."""
    text = _text(node, "coordinates") if node is not None else ""
    return re.sub(r"\s*,\s*", ",", text).split()


def _coords(node):
    """Вершины (широта, долгота) из coordinates: «lon,lat[,alt] ...»."""
    pairs = (_pair(item) for item in _items(node))
    return [pair for pair in pairs if pair is not None]


RELATIVE = ("relativeToGround", "relativeToSeaFloor")


def _raise(node, coords):
    """Подъём над землёй и выдавливание геометрии node."""
    mode = _text(node, "altitudeMode")
    if mode not in RELATIVE:
        return 0.0, False
    first = _items(coords)[:1]
    parts = first[0].split(",") if first else []
    try:
        height = max(float(parts[2]), 0.0) if len(parts) > 2 else 0.0
    except ValueError:
        height = 0.0
    return height, _text(node, "extrude", "0") == "1"


def _alts(node, coords, count):
    """Высоты вершин линии или многоугольника с altitudeMode absolute,
    если высота есть у каждой из count вершин, иначе None."""
    if coords is None or _text(node, "altitudeMode") != "absolute":
        return None
    alts = []
    for item in _items(coords):
        parts = item.split(",")
        if _pair(item) is None:
            continue
        try:
            alts.append(float(parts[2]))
        except (ValueError, IndexError):
            return None
    if len(alts) == count + 1:  # замкнутое кольцо повторяет первую
        alts = alts[:-1]
    return tuple(alts) if len(alts) == count else None


def _outer_rings(polygon):
    """Узлы внешних колец Polygon с coordinates. По стандарту это
    outerBoundaryIs/LinearRing, модели пишут и LinearRing без
    outerBoundaryIs, и coordinates прямо в Polygon. Дыры innerBoundaryIs
    не берутся."""
    found = []
    for outer in _children(polygon, "outerBoundaryIs"):
        ring = _child(outer, "LinearRing")
        found.append(ring if ring is not None else outer)
    if found:
        return found
    found = _children(polygon, "LinearRing")
    if found:
        return found
    return [polygon] if _child(polygon, "coordinates") is not None else []


def _geometries(node):
    """(вид, вершины, подъём, выдавливание, высоты) всех геометрий
    Placemark, MultiGeometry по частям. Высоты - у 3D-линий
    и многоугольников с altitudeMode absolute, иначе None."""
    out = []
    for child in node:
        name = _local(child.tag)
        if name == "Point":
            points = _coords(child)[:1]
            if points:
                out.append(("point", points) + _raise(child, child)
                           + (None,))
        elif name in ("LineString", "LinearRing"):
            points = _coords(child)
            if len(points) >= 2:
                out.append(("line", points) + _raise(child, child)
                           + (_alts(child, child, len(points)),))
        elif name == "Polygon":
            for ring in _outer_rings(child):
                points = _coords(ring)
                if len(points) > 1 and points[0] == points[-1]:
                    points = points[:-1]
                if len(points) >= 3:
                    out.append(("polygon", points) + _raise(child, ring)
                               + (_alts(child, ring, len(points)),))
        elif name in ("MultiGeometry", "MultiTrack"):
            out.extend(_geometries(child))
        elif name == "Track":
            # gx:Track - путь точками с моментами времени. На глобусе
            # это линия, время - от первого момента до последнего
            # (_track_time): линия с промежутком растёт по шкале времени.
            points = _track_points(child)
            if len(points) >= 2:
                out.append(("line", points, 0.0, False, None))
    return out


def _track_points(node):
    """Вершины gx:Track: gx:coord «долгота широта высота» через пробел."""
    points = []
    for child in _children(node, "coord"):
        pair = _pair(",".join((child.text or "").split()))
        if pair is not None:
            points.append(pair)
    return points


def _track_time(node):
    """Промежуток времени треков узла: первый и последний when
    gx:Track, в том числе внутри gx:MultiTrack и MultiGeometry."""
    whens = []
    for child in node:
        name = _local(child.tag)
        if name == "Track":
            whens += [(w.text or "").strip()
                      for w in _children(child, "when")]
        elif name in ("MultiTrack", "MultiGeometry"):
            span = _track_time(child)
            if span is not None:
                whens += list(span)
    whens = [w for w in whens if w]
    return (whens[0], whens[-1]) if whens else None


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
        style["href"] = _text(_child(icon, "Icon"), "href") or None
    listing = _child(node, "ListStyle")
    if listing is not None:
        style["list_type"] = _text(listing, "listItemType") or None
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


def _time_of(node):
    """Время узла: TimeStamp - момент, TimeSpan - промежуток."""
    stamp = _child(node, "TimeStamp")
    if stamp is not None and _text(stamp, "when"):
        when = _text(stamp, "when")
        return (when, when)
    span = _child(node, "TimeSpan")
    if span is not None:
        begin, end = _text(span, "begin"), _text(span, "end")
        if begin or end:
            return (begin, end)
    return None


def _geometry_time(node):
    """Время, записанное внутри геометрии Placemark: модели кладут
    TimeSpan этапа пути в его LineString."""
    for child in node:
        if _local(child.tag) in GEOMETRY and _local(child.tag) != "Track":
            found = _time_of(child) or _geometry_time(child)
            if found:
                return found
    return None


def _view_time(node):
    """Время вида: gx:TimeStamp или gx:TimeSpan внутри LookAt."""
    look = _child(node, "LookAt")
    return _time_of(look) if look is not None else None


def _visible(node):
    return _text(node, "visibility", "1") != "0"


def _placemark(node, styles, inherited=None):
    style = dict(styles.get(_text(node, "styleUrl").lstrip("#"), {}))
    inline = _child(node, "Style")
    if inline is not None:
        style.update(_style_of(inline))
    name = _text(node, "name")
    out = []
    found = _geometries(node)
    look = _child(node, "LookAt")
    if not found and look is not None:
        # Метка одним видом, без геометрии: точкой взгляда.
        spot = _pair("{},{}".format(_text(look, "longitude"),
                                    _text(look, "latitude")))
        if spot is not None:
            found = [("point", [spot], 0.0, False, None)]
    time = _time_of(node) or _geometry_time(node) or _track_time(node) \
        or inherited
    for kind, points, height, extrude, alts in found:
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
                          height=height, extrude=extrude,
                          icon=icons.from_href(style.get("href"))
                          if kind == "point" else icons.DEFAULT,
                          time=time,
                          view_time=_view_time(node), alts=alts))
    return out


# Геометрии KML. По стандарту они лежат внутри Placemark.
GEOMETRY = ("Point", "LineString", "LinearRing", "Polygon", "MultiGeometry",
            "Track", "MultiTrack")


def _bare(geometry, parent, styles, inherited):
    """Метки из геометрии, которая лежит в папке без Placemark.

    Стандарт так не разрешает, но модели помощника кладут линию
    маршрута прямо в <Folder>, стиль - атрибутом styleUrl. 4 октября
    2026 года так пропали четыре маршрута плаваний Колумба, в «Мои
    метки» попали только точки. Метка получает название, описание,
    стиль и время самой геометрии, без них - название и время папки.
    """
    holder = _Node("Placemark", {})
    for tag in ("name", "description", "styleUrl", "Style", "TimeStamp",
                "TimeSpan"):
        own = _child(geometry, tag)
        if own is not None:
            holder.children.append(own)
    if _child(holder, "name") is None:
        name = _Node("name", {})
        name.text = _text(parent, "name")
        holder.children.append(name)
    if _child(holder, "styleUrl") is None and geometry.get("styleUrl"):
        url = _Node("styleUrl", {})
        url.text = geometry.get("styleUrl")
        holder.children.append(url)
    holder.children.append(geometry)
    return _placemark(holder, styles, inherited)


def _tour(node):
    """Записанный тур из gx:Tour: позы LookAt у gx:FlyTo по времени,
    gx:Wait держит позу. FlyTo с Camera и прочие шаги пропускаются."""
    playlist = _child(node, "Playlist")
    if playlist is None:
        return None
    samples = []
    t = 0.0
    for step in playlist:
        name = _local(step.tag)
        duration = max(_float(step, "duration", 0.0), 0.0)
        if name == "FlyTo":
            look = _child(step, "LookAt")
            if look is None:
                continue
            t += duration
            samples.append((t, _float(look, "latitude", 0.0),
                            _float(look, "longitude", 0.0),
                            _float(look, "range", 1000.0),
                            _float(look, "heading", 0.0),
                            _float(look, "tilt", 0.0)))
        elif name == "Wait" and samples:
            t += duration
            samples.append((t,) + tuple(samples[-1][1:]))
    if len(samples) < 2:
        return None
    points = [(s[1], s[2]) for s in samples]
    return KPlace(_text(node, "name"), "line", points, visible=_visible(node),
                  description=_text(node, "description"), tour=samples)


def _list_type(node, styles):
    """listItemType стиля папки: свой Style или Style по styleUrl."""
    style = dict(styles.get(_text(node, "styleUrl").lstrip("#"), {}))
    inline = _child(node, "Style")
    if inline is not None:
        style.update(_style_of(inline))
    return style.get("list_type", "")


def _xy(node, name, default):
    """overlayXY, screenXY или size: (x, y, единицы x, единицы y)."""
    item = _child(node, name)
    if item is None:
        return default
    try:
        return (float(item.get("x", default[0])),
                float(item.get("y", default[1])),
                item.get("xunits", "fraction"),
                item.get("yunits", "fraction"))
    except ValueError:
        return default


def _overlay(node, styles, inherited):
    """KOverlay из GroundOverlay, ScreenOverlay или PhotoOverlay, или
    None, если места наложения в нём нет."""
    tag = _local(node.tag)
    icon = _child(node, "Icon")
    href = _text(icon, "href").strip() if icon is not None else ""
    color = kml_color(_text(node, "color"), overlays.WHITE)
    order = int(_float(node, "drawOrder", 0.0))
    if tag == "GroundOverlay":
        quad = _child(node, "LatLonQuad")
        box = _child(node, "LatLonBox")
        if quad is not None:
            corners = _coords(quad)[:4]
            if len(corners) != 4:
                return None
            overlay = overlays.Overlay("ground", corners, color, order)
        elif box is not None:
            overlay = overlays.Overlay("ground", color=color, order=order,
                                       box=(_float(box, "north", 0.0),
                                            _float(box, "south", 0.0),
                                            _float(box, "east", 0.0),
                                            _float(box, "west", 0.0),
                                            _float(box, "rotation", 0.0)))
        else:
            return None
    elif tag == "ScreenOverlay":
        base = overlays.Overlay("screen")
        overlay = overlays.Overlay(
            "screen", color=color, order=order,
            overlay_xy=_xy(node, "overlayXY", base.overlay_xy),
            screen_xy=_xy(node, "screenXY", base.screen_xy),
            size=_xy(node, "size", base.size),
            rotation=_float(node, "rotation", 0.0))
    else:
        camera = _child(node, "Camera")
        if camera is None:
            return None
        volume = _child(node, "ViewVolume")
        base = overlays.Overlay("photo")
        fov = base.fov if volume is None else tuple(
            _float(volume, name, value) for name, value in zip(
                ("leftFov", "rightFov", "bottomFov", "topFov"), base.fov))
        overlay = overlays.Overlay(
            "photo", color=color, order=order,
            camera=(_float(camera, "latitude", 0.0),
                    _float(camera, "longitude", 0.0),
                    _float(camera, "altitude", 0.0),
                    _float(camera, "heading", 0.0),
                    _float(camera, "tilt", 0.0),
                    _float(camera, "roll", 0.0)),
            fov=fov, near=_float(volume, "near", base.near)
            if volume is not None else base.near)
    anchor = overlay.corners[0] if overlay.corners else (
        (overlay.camera[0], overlay.camera[1]) if overlay.camera else None)
    return KOverlay(_text(node, "name"), overlay, href=href,
                    visible=_visible(node),
                    description=_text(node, "description"),
                    view=_view(node, anchor),
                    time=_time_of(node) or inherited)

def _walk(node, styles, folder, inherited=None):
    for child in node:
        name = _local(child.tag)
        if name in ("Folder", "Document"):
            kind = _list_type(child, styles)
            sub = KFolder(_text(child, "name"), _visible(child),
                          description=_text(child, "description"),
                          view=_view(child, None),
                          radio=kind == "radioFolder",
                          expandable=kind != "checkHideChildren")
            _walk(child, styles, sub, _time_of(child) or inherited)
            folder.children.append(sub)
        elif name == "Placemark":
            folder.children.extend(_placemark(child, styles, inherited))
        elif name in GEOMETRY:
            folder.children.extend(_bare(child, node, styles, inherited))
        elif name == "Tour":
            tour = _tour(child)
            if tour is not None:
                folder.children.append(tour)
        elif name in ("GroundOverlay", "ScreenOverlay", "PhotoOverlay"):
            item = _overlay(child, styles, inherited)
            if item is not None:
                folder.children.append(item)


def read_kml(data, name=""):
    """Дерево KFolder из байтов KML. name - название корня."""
    try:
        root = _parse(data)
    except KmlError:
        mended = _mend(data)
        if mended is None:
            raise
        root = _parse(mended)
    if _local(root.tag) != "kml":
        raise KmlError("not KML")
    styles = _styles(root)
    top = KFolder(name)
    _walk(root, styles, top)
    # Один Document - его содержимое и есть корень. Название - имя
    # документа, как в Google Earth, без него - name, обычно имя файла.
    if len(top.children) == 1 and isinstance(top.children[0], KFolder):
        only = top.children[0]
        top = KFolder(only.name or name, only.visible, only.children,
                      only.description, only.view, only.radio,
                      only.expandable)
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
            tree = read_kml(archive.read(names[0]), name)
            # Картинки наложений - файлы архива по href, путь от
            # папки файла KML.
            files = {n.replace("\\", "/").lower(): n
                     for n in archive.namelist()}
            base = names[0].rsplit("/", 1)[0] + "/" \
                if "/" in names[0] else ""
            for item in tree.overlays():
                ref = unquote(item.href.replace("\\", "/"))
                while ref.startswith("./"):
                    ref = ref[2:]
                found = files.get((base + ref).lower()) \
                    or files.get(ref.lower())
                if found is not None:
                    item.image = archive.read(found)
            return tree
    except zipfile.BadZipFile as error:
        raise KmlError(str(error)) from error


def read_file(data, name=""):
    """KML или KMZ по содержимому: KMZ начинается с подписи ZIP."""
    if data[:2] == b"PK":
        return read_kmz(data, name)
    return read_kml(data, name)


# Запись.

def _coord_text(points, close=False, height=0.0, alts=None):
    pts = list(points) + (list(points[:1]) if close else [])
    if alts is not None:
        heights = list(alts) + (list(alts[:1]) if close else [])
        return " ".join("{:.8f},{:.8f},{:.3f}".format(lon, lat, h)
                        for (lat, lon), h in zip(pts, heights))
    return " ".join("{:.8f},{:.8f},{:g}".format(lon, lat, height)
                    for lat, lon in pts)


def _space(place):
    """Высоты 3D-объекта или None."""
    alts = getattr(place, "alts", None)
    if place.kind == "point" or alts is None \
            or len(alts) != len(place.points):
        return None
    return alts


def _raise_kml(place):
    """Режим высоты и выдавливание геометрии для записи."""
    if not place.height:
        return ""
    return "<extrude>{}</extrude><altitudeMode>relativeToGround" \
        "</altitudeMode>".format(int(bool(place.extrude)))


def _time_kml(time, prefix=""):
    """TimeStamp или TimeSpan для записи. prefix «gx:» - время вида."""
    if not time or not (time[0] or time[1]):
        return ""
    if time[0] == time[1]:
        return "<{p}TimeStamp><when>{}</when></{p}TimeStamp>".format(
            escape(time[0]), p=prefix)
    parts = "".join(
        "<{0}>{1}</{0}>".format(tag, escape(value))
        for tag, value in (("begin", time[0]), ("end", time[1])) if value)
    return "<{p}TimeSpan>{}</{p}TimeSpan>".format(parts, p=prefix)


def _placemark_kml(place, indent):
    pad = "  " * indent
    style = ""
    if place.kind == "point":
        style = "<IconStyle><color>{}</color><Icon><href>{}</href>" \
            "</Icon></IconStyle>".format(
                color_kml(place.color), escape(icons.href(place.icon)))
    else:
        style = "<LineStyle><color>{}</color><width>{:g}</width>" \
            "</LineStyle>".format(color_kml(place.color), place.width)
        if place.kind == "polygon":
            style += "<PolyStyle><color>{}</color><fill>{}</fill>" \
                "</PolyStyle>".format(color_kml(place.fill or FILL_COLOR),
                                      1 if place.fill else 0)
    mode = _raise_kml(place)
    h = float(place.height or 0.0)
    alts = _space(place)
    # 3D-объект: прямые отрезки на своих высотах, без посадки на рельеф.
    tessellate = "<tessellate>1</tessellate>"
    if alts is not None:
        mode = "<altitudeMode>absolute</altitudeMode>"
        tessellate = ""
    if place.kind == "point":
        geometry = "<Point>{}<coordinates>{}</coordinates></Point>".format(
            mode, _coord_text(place.points, height=h))
    elif place.kind == "line":
        geometry = "<LineString>{}{}<coordinates>" \
            "{}</coordinates></LineString>".format(
                tessellate, mode,
                _coord_text(place.points, height=h, alts=alts))
    else:
        geometry = "<Polygon>{}{}" \
            "<outerBoundaryIs><LinearRing><coordinates>{}</coordinates>" \
            "</LinearRing></outerBoundaryIs></Polygon>".format(
                tessellate, mode,
                _coord_text(place.points, close=True, height=h, alts=alts))
    look = ""
    if place.view is not None:
        lat, lon, distance, heading, tilt = place.view
        look = "<LookAt>{}<longitude>{:.8f}</longitude><latitude>{:.8f}" \
            "</latitude><altitude>0</altitude><heading>{:g}</heading>" \
            "<tilt>{:g}</tilt><range>{:g}</range></LookAt>".format(
                _time_kml(place.view_time, "gx:"), lon, lat, heading,
                tilt, distance)
    parts = ["<Placemark>", "<name>{}</name>".format(escape(place.name))]
    if place.description:
        parts.append("<description>{}</description>".format(
            escape(place.description)))
    parts += ["<visibility>{}</visibility>".format(int(place.visible)),
              _time_kml(place.time), look,
              "<Style>{}</Style>".format(style), geometry, "</Placemark>"]
    return pad + "".join(p for p in parts if p)


def _tour_kml(place, indent):
    """Записанный тур как gx:Tour: gx:FlyTo плавно к каждой позе."""
    pad = "  " * indent
    steps = []
    last = None
    for t, lat, lon, distance, heading, tilt in place.tour:
        duration = 0.0 if last is None else t - last
        last = t
        steps.append(
            "<gx:FlyTo><gx:duration>{:.3f}</gx:duration><gx:flyToMode>"
            "smooth</gx:flyToMode><LookAt><longitude>{:.8f}</longitude>"
            "<latitude>{:.8f}</latitude><altitude>0</altitude><heading>"
            "{:.3f}</heading><tilt>{:.3f}</tilt><range>{:.2f}</range>"
            "</LookAt></gx:FlyTo>".format(duration, lon, lat, heading, tilt,
                                          distance))
    return pad + "<gx:Tour><name>{}</name><gx:Playlist>{}</gx:Playlist>" \
        "</gx:Tour>".format(escape(place.name), "".join(steps))


def _look_kml(view):
    """LookAt вида core.lookat."""
    lat, lon, distance, heading, tilt = view
    return "<LookAt><longitude>{:.8f}</longitude><latitude>{:.8f}" \
        "</latitude><altitude>0</altitude><heading>{:g}</heading>" \
        "<tilt>{:g}</tilt><range>{:g}</range></LookAt>".format(
            lon, lat, heading, tilt, distance)


def image_ext(data):
    """Расширение картинки по первым байтам."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"GIF":
        return "gif"
    return "jpg"


def _xy_kml(tag, value):
    x, y, xu, yu = value
    return '<{} x="{:g}" y="{:g}" xunits="{}" yunits="{}"/>'.format(
        tag, x, y, escape(xu), escape(yu))


def _overlay_kml(item, indent, href):
    """Наложение KML, href - адрес картинки в файле."""
    pad = "  " * indent
    overlay = item.overlay
    tag = {"ground": "GroundOverlay", "screen": "ScreenOverlay",
           "photo": "PhotoOverlay"}[overlay.kind]
    parts = ["<{}>".format(tag), "<name>{}</name>".format(escape(item.name))]
    if item.description:
        parts.append("<description>{}</description>".format(
            escape(item.description)))
    parts += ["<visibility>{}</visibility>".format(int(item.visible)),
              _time_kml(item.time)]
    if item.view is not None:
        parts.append(_look_kml(item.view))
    parts += ["<color>{}</color>".format(color_kml(overlay.color)),
              "<drawOrder>{}</drawOrder>".format(overlay.order)]
    if href:
        parts.append("<Icon><href>{}</href></Icon>".format(escape(href)))
    if overlay.kind == "ground":
        box = overlay.box
        if box is None:
            plain = overlays.corners_box(overlay.corners)
            box = plain + (0.0,) if plain else None
        if box is not None:
            parts.append("<LatLonBox><north>{:.8f}</north><south>{:.8f}"
                         "</south><east>{:.8f}</east><west>{:.8f}</west>"
                         "<rotation>{:g}</rotation></LatLonBox>".format(
                             *box))
        else:
            parts.append("<gx:LatLonQuad><coordinates>{}</coordinates>"
                         "</gx:LatLonQuad>".format(
                             _coord_text(overlay.corners)))
    elif overlay.kind == "screen":
        parts += [_xy_kml("overlayXY", overlay.overlay_xy),
                  _xy_kml("screenXY", overlay.screen_xy),
                  _xy_kml("size", overlay.size),
                  "<rotation>{:g}</rotation>".format(overlay.rotation)]
    else:
        lat, lon, alt, heading, tilt, roll = overlay.camera
        left, right, bottom, top = overlay.fov
        parts += ["<Camera><longitude>{:.8f}</longitude><latitude>{:.8f}"
                  "</latitude><altitude>{:.3f}</altitude><heading>{:g}"
                  "</heading><tilt>{:g}</tilt><roll>{:g}</roll>"
                  "<altitudeMode>absolute</altitudeMode></Camera>".format(
                      lon, lat, alt, heading, tilt, roll),
                  "<ViewVolume><leftFov>{:g}</leftFov><rightFov>{:g}"
                  "</rightFov><bottomFov>{:g}</bottomFov><topFov>{:g}"
                  "</topFov><near>{:g}</near></ViewVolume>".format(
                      left, right, bottom, top, overlay.near),
                  "<Point><coordinates>{:.8f},{:.8f},{:.3f}</coordinates>"
                  "</Point>".format(lon, lat, alt)]
    parts.append("</{}>".format(tag))
    return pad + "".join(p for p in parts if p)

def _folder_kml(folder, indent, tag="Folder", hrefs=None):
    pad = "  " * indent
    lines = [pad + "<{}>".format(tag),
             pad + "  <name>{}</name>".format(escape(folder.name)),
             pad + "  <visibility>{}</visibility>".format(
                 int(folder.visible))]
    if getattr(folder, "description", ""):
        lines.append(pad + "  <description>{}</description>".format(
            escape(folder.description)))
    if getattr(folder, "view", None) is not None:
        lines.append(pad + "  " + _look_kml(folder.view))
    kind = "radioFolder" if getattr(folder, "radio", False) else \
        "checkHideChildren" if not getattr(folder, "expandable", True) \
        else ""
    if kind:
        lines.append(pad + "  <Style><ListStyle><listItemType>{}"
                     "</listItemType></ListStyle></Style>".format(kind))
    for child in folder.children:
        if isinstance(child, KFolder):
            lines.extend(_folder_kml(child, indent + 1, hrefs=hrefs))
        elif isinstance(child, KOverlay):
            href = (hrefs or {}).get(id(child), child.href)
            lines.append(_overlay_kml(child, indent + 1, href))
        elif child.tour:
            lines.append(_tour_kml(child, indent + 1))
        else:
            lines.append(_placemark_kml(child, indent + 1))
    lines.append(pad + "</{}>".format(tag))
    return lines


def write_kml(folder, hrefs=None):
    """Текст KML папки: Document с вложенными Folder и Placemark.
    hrefs - адреса картинок наложений {id(KOverlay): href}, без них -
    href из исходного файла."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<kml xmlns="{}" xmlns:gx="{}">'.format(NS, GX)]
    lines.extend(_folder_kml(folder, 1, "Document", hrefs))
    lines.append("</kml>")
    return "\n".join(lines) + "\n"


def write_kmz(folder):
    """Байты KMZ: архив с doc.kml и картинками наложений в files/."""
    hrefs = {}
    files = []
    for n, item in enumerate(folder.overlays()):
        if item.image:
            name = "files/overlay{}.{}".format(n + 1, image_ext(item.image))
            hrefs[id(item)] = name
            files.append((name, item.image))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("doc.kml", write_kml(folder, hrefs).encode("utf-8"))
        for name, data in files:
            archive.writestr(name, data)
    return buffer.getvalue()
