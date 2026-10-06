# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «Карты и слои»: витрина карт и слоёв глобуса с превью.

Просьба автора от 7 октября 2026 года - «компактный красивый интерфейс
к картам NASA». Карта - тема NASA GIBS, поле прогноза GFS, пожары FIRMS
или температура суши и моря, включена одна из всех. Превью темы GIBS -
её тайл уровня 1 над Евразией на последний готовый день поверх тайла
подложки, у поля прогноза и пожаров - полоса цветов шкалы. Кнопки
групп сужают витрину, строка поиска ищет по названию. Окно немодальное,
одно на глобус, выбор делает окно глобуса (`GlobeWindow.set_theme`).

Тем же днём автор перенёс сюда и слои «Небо и свет», «Недра»
и «Анализ рельефа» («добавь остальные слои рядом и исключим их из
списка»). Слои включаются независимо, щелчок переключает строку окна
глобуса (`GlobeWindow.set_extra`), включённый слой отмечен бирочкой.
"""
import math
import os
import time

import numpy as np
from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from qgis.PyQt.QtWidgets import (QButtonGroup, QDialog, QHBoxLayout, QLabel,
                                 QLineEdit, QListView, QListWidget,
                                 QListWidgetItem, QMenu, QPushButton,
                                 QToolButton, QVBoxLayout)

from ..core import (clouds, cutaway, fires, paleo, plates, quakes, slope,
                    stars, sun, temperature, themes, weather)
from ..i18n import tr
from ..net.overlay import fetch_bytes
from ..qt_compat import enum, enum_int
from .satellites import group_names as satellite_group_names
from .themes import group_names, theme_names

THUMB = 104  # пикселей стороны превью
PARALLEL = 4  # запросов превью сразу
KEY_ROLE = enum_int(enum(Qt, "ItemDataRole", "UserRole"))
ALL = ""  # кнопка «Все» групп
LAYER = "layer"  # вид строки витрины: слой глобуса со своим флажком
# Слои витрины: ключ строки окна глобуса и группа.
LAYERS = (("stars", "sky"), ("clouds", "sky"), ("sun", "sky"),
          ("satellites", "sky"), ("quakes", "depths"), ("plates", "depths"),
          ("cutaway", "depths"), ("paleo", "depths"), ("slope", "terrain"),
          ("aspect", "terrain"))
# Слои, которые есть и вне Земли: звёзды везде, уклон - где есть высоты.
ANY_BODY = ("stars",)
RELIEF_BODY = ("slope", "aspect")
PALEO_AGE = 100  # млн лет, возраст карты на превью палеогеографии
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "data")


def layer_group_names():
    """Группы слоёв витрины: ключ, название, подсказка."""
    return (
        ("sky", tr("Небо и свет"), tr(
            "Солнце и ночная сторона, звёзды, облака "
            "и искусственные спутники.")),
        ("depths", tr("Недра"), tr(
            "Землетрясения, границы плит, разрез Земли "
            "и палеогеография.")),
        ("terrain", tr("Анализ рельефа"), tr(
            "Раскраска поверхности по уклону или по стороне "
            "света склона. Включается одна из двух.")))


def layer_names():
    """Слой витрины: ключ - (название, подсказка)."""
    return {
        "stars": (tr("Звёзды"), tr(
            "Звёзды каталога ярких звёзд Йельского университета "
            "и Млечный путь по карте неба NASA. Картинка неба "
            "скачивается при первом показе. Звёзды видны "
            "из космоса и гаснут, когда камера опускается "
            "в атмосферу.")),
        "clouds": (tr("Облака"), tr(
            "Облака по снимкам VIIRS из NASA GIBS за последние "
            "полные сутки. Они лежат полупрозрачной пеленой "
            "поверх снимка. Снег и лёд тоже белые и остаются "
            "видны.")),
        "sun": (tr("Солнце"), tr(
            "Свет рельефа, зданий и воздуха по положению солнца. "
            "Ночная сторона Земли тёмная. Время солнца - конец "
            "промежутка открытой шкалы времени, без неё - часы "
            "компьютера. Без флажка свет падает с северо-запада, "
            "как на карте рельефа.")),
        "satellites": (tr("Спутники"), tr(
            "Искусственные спутники по орбитальным элементам CelesTrak, "
            "положение по модели SGP4. Время - правый бегунок шкалы "
            "времени, без шкалы - часы компьютера. Группы выбирает "
            "кнопка «Группы спутников». Элементы группы обновляются "
            "не чаще раза в 2 часа.")),
        "quakes": (tr("Землетрясения"), tr(
            "Землетрясения магнитудой от 4.5 за последние 30 "
            "суток по сводке USGS. Кружок стоит в очаге на его "
            "глубине, линия ведёт к эпицентру на поверхности. "
            "Цвет показывает глубину очага, размер - магнитуду. "
            "Сводка загружается при включении строки.")),
        "plates": (tr("Границы плит"), tr(
            "Границы литосферных плит по модели PB2002. Красные - "
            "раздвиг плит на хребтах и рифтах, зелёные - сдвиг "
            "по трансформным разломам, синие - схождение "
            "в зонах субдукции и коллизии. Названия плит стоят "
            "надписями. Тип границы и скорость плит показывает "
            "окно «Объекты».")),
        "cutaway": (tr("Разрез Земли"), tr(
            "Вынимает из Земли сектор под точкой взгляда - "
            "четверть полушария шириной 90° по долготе. На его "
            "гранях видны кора, мантия и ядро по радиусам "
            "модели PREM. Где грань проходит через зону "
            "субдукции, на ней видна погружающаяся плита. "
            "Углы сектора тянутся мышью. Сектор ставится заново "
            "при каждом включении строки.")),
        "paleo": (tr("Палеогеография"), tr(
            "Рельеф суши и глубины моря в прошлом, до 540 млн "
            "лет назад, по картам PaleoDEM PALEOMAP. Возраст "
            "задаёт ползунок в левом нижнем углу вида. Снимок, "
            "границы и подписи на это время убраны.")),
        "slope": (tr("Уклон"), tr(
            "Уклон поверхности по высотам рельефа, классами от "
            "ровного до круче 35°. Шкала стоит в левом нижнем "
            "углу вида. Есть у Земли, Марса и Луны.")),
        "aspect": (tr("Экспозиция"), tr(
            "Куда обращён склон - цвет стороны света, ровное "
            "место серое. Включается вместо уклона.")),
    }


def map_names():
    """Карта витрины: ключ - (название, подсказка)."""
    names = dict(theme_names())
    names[themes.FIRES] = (tr("Пожары"), tr(
        "Очаги пожаров за последние 24 часа по снимкам VIIRS спутника "
        "NOAA-20, сводка NASA FIRMS. Цвет и размер точки показывают "
        "мощность излучения."))
    names[themes.TEMPERATURE] = (tr("Температура поверхности"), tr(
        "Температура суши днём по MODIS за 8 суток и моря по GHRSST MUR "
        "за сутки, данные NASA GIBS."))
    return names


def ramp_image(colors, base=None):
    """Превью из полосы цветов шкалы поверх картинки подложки."""
    image = QImage(THUMB, THUMB, enum(QImage, "Format", "Format_ARGB32"))
    image.fill(QColor(40, 48, 60))
    painter = QPainter(image)
    if base is not None:
        painter.drawImage(image.rect(), base)
    band = THUMB // 4
    count = max(len(colors), 1)
    for n, color in enumerate(colors):
        left = THUMB * n // count
        right = THUMB * (n + 1) // count
        painter.fillRect(left, THUMB - band, right - left, band,
                         QColor(*color[:3]))
    painter.end()
    return image


def tile_image(data, base=None, clear=()):
    """Превью из тайла темы поверх тайла подложки. Цвета clear -
    прозрачные классы темы."""
    image = QImage(THUMB, THUMB, enum(QImage, "Format", "Format_ARGB32"))
    image.fill(QColor(40, 48, 60))
    tile = QImage.fromData(data) if data else QImage()
    painter = QPainter(image)
    if base is not None:
        painter.drawImage(image.rect(), base)
    if not tile.isNull():
        if clear:
            tile = _cleared(tile, clear)
        painter.setOpacity(themes.OPACITY)
        painter.drawImage(image.rect(), tile)
    painter.end()
    return image


def _rgba_array(tile):
    """Пиксели картинки массивом (высота, ширина, 4) RGBA uint8."""
    tile = tile.convertToFormat(enum(QImage, "Format", "Format_RGBA8888"))
    width, height, line = tile.width(), tile.height(), tile.bytesPerLine()
    ptr = tile.constBits()
    ptr.setsize(height * line)
    return np.frombuffer(ptr, np.uint8).reshape(height, line)[
        :, :width * 4].reshape(height, width, 4).copy()


def _rgba_image(pixels, premultiplied=False):
    """Картинка из массива RGBA uint8."""
    name = "Format_RGBA8888_Premultiplied" if premultiplied \
        else "Format_RGBA8888"
    height, width = pixels.shape[:2]
    return QImage(np.ascontiguousarray(pixels).tobytes(), width, height,
                  width * 4, enum(QImage, "Format", name)).copy()


def _over(under, top):
    """Превью из двух картинок одна над другой, любая может быть None."""
    image = _blank()
    painter = QPainter(image)
    for picture in (under, top):
        if picture is not None:
            painter.drawImage(image.rect(), picture)
    painter.end()
    return image


def _cleared(tile, clear):
    """Тайл, у которого пиксели цветов clear прозрачны."""
    pixels = _rgba_array(tile)
    for color in clear:
        pixels[np.all(pixels[..., :3] == color, axis=-1), 3] = 0
    return _rgba_image(pixels)


def ramp_of(key):
    """Цвета шкалы карты без тайла: поле прогноза или пожары."""
    if key == themes.FIRES:
        return [color for _, color in fires.FRP_STOPS]
    return weather.legend(weather.BY_KEY[key[len("weather_"):]])["colors"]


def _blank(color=(40, 48, 60)):
    image = QImage(THUMB, THUMB, enum(QImage, "Format", "Format_ARGB32"))
    image.fill(QColor(*color))
    return image


def _thumb_xy(lat, lon):
    """Пиксель превью для точки: тайл THUMB_TILE в Web Mercator."""
    z, x, y = themes.THUMB_TILE
    world = THUMB * (1 << z)
    lat = max(-85.0, min(85.0, lat))
    mx = (lon + 180.0) / 360.0 * world - x * THUMB
    s = math.sin(math.radians(lat))
    my = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * world \
        - y * THUMB
    return mx, my


def stars_image():
    """Превью звёзд: Орион и соседи из каталога модуля, восток слева."""
    image = _blank((8, 10, 22))
    try:
        data = np.load(os.path.join(DATA_DIR, "stars.npy"))
    except OSError:
        return image
    ra_lo, ra_hi, dec_lo, dec_hi = 1.0, 1.9, -0.45, 0.45
    pick = (data[:, 0] > ra_lo) & (data[:, 0] < ra_hi) \
        & (data[:, 1] > dec_lo) & (data[:, 1] < dec_hi)
    data = data[pick]
    sizes = stars.sizes(data[:, 2]) * 0.8
    colors = np.clip(stars.colors(data[:, 3]) * 255.0, 0, 255)
    painter = QPainter(image)
    painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
    painter.setPen(enum(Qt, "PenStyle", "NoPen"))
    for (ra, dec), size, color in zip(data[:, :2], sizes, colors):
        painter.setBrush(QColor(*(int(c) for c in color)))
        x = (ra_hi - ra) / (ra_hi - ra_lo) * THUMB
        y = (dec_hi - dec) / (dec_hi - dec_lo) * THUMB
        painter.drawEllipse(int(x - size / 2), int(y - size / 2),
                            max(1, int(size)), max(1, int(size)))
    painter.end()
    return image


def satellites_image(base=None):
    """Превью спутников: шар с подложкой, орбиты и точки."""
    image = _blank((8, 10, 22))
    painter = QPainter(image)
    painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
    radius = THUMB * 0.3
    cx = cy = THUMB / 2.0
    painter.setPen(enum(Qt, "PenStyle", "NoPen"))
    painter.setBrush(QColor(40, 90, 160))
    painter.drawEllipse(int(cx - radius), int(cy - radius),
                        int(2 * radius), int(2 * radius))
    pen = painter.pen()
    for n, (tilt, color) in enumerate(((20, (255, 255, 255)),
                                       (-45, (255, 200, 80)),
                                       (70, (120, 220, 255)))):
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(tilt)
        painter.setBrush(enum(Qt, "BrushStyle", "NoBrush"))
        painter.setPen(QColor(*color))
        a, b = THUMB * (0.42 - 0.04 * n), THUMB * (0.14 + 0.03 * n)
        painter.drawEllipse(int(-a), int(-b), int(2 * a), int(2 * b))
        painter.setPen(enum(Qt, "PenStyle", "NoPen"))
        painter.setBrush(QColor(*color))
        for k in range(5):
            angle = 2 * math.pi * (k / 5.0 + 0.1 * n)
            painter.drawEllipse(int(a * math.cos(angle)) - 2,
                                int(b * math.sin(angle)) - 2, 4, 4)
        painter.restore()
    painter.setPen(pen)
    painter.end()
    return image


def cutaway_image():
    """Превью разреза: оболочки PREM кольцами, вынут сектор."""
    image = _blank((8, 10, 22))
    painter = QPainter(image)
    painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
    painter.setPen(enum(Qt, "PenStyle", "NoPen"))
    outer = THUMB * 0.44
    cx = cy = THUMB / 2.0
    painter.setBrush(QColor(40, 90, 160))
    painter.drawEllipse(int(cx - outer), int(cy - outer), int(2 * outer),
                        int(2 * outer))
    top = cutaway.SHELLS[-1][2]
    for name, low, high, color in reversed(cutaway.SHELLS):
        r = outer * high / top
        painter.setBrush(QColor(*color))
        # Сектор 90° справа сверху, углы Qt - в шестнадцатых градуса.
        painter.drawPie(int(cx - r), int(cy - r), int(2 * r), int(2 * r),
                        0, 90 * 16)
    painter.end()
    return image


def plates_image(base=None):
    """Превью границ плит: линии PB2002 над Евразией по группам."""
    image = _blank()
    painter = QPainter(image)
    painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
    if base is not None:
        painter.drawImage(image.rect(), base)
    try:
        with open(os.path.join(DATA_DIR, "plates.json"),
                  encoding="utf-8") as fh:
            data = plates.Plates.from_text(fh.read())
    except (OSError, ValueError):
        painter.end()
        return image
    pen = painter.pen()
    pen.setWidthF(1.6)
    for line in data.boundaries:
        pen.setColor(QColor(*plates.color(line.code)[:3]))
        painter.setPen(pen)
        points = [_thumb_xy(la, lo) for la, lo in zip(line.lats, line.lons)]
        for a, b in zip(points, points[1:]):
            if abs(a[0] - b[0]) < THUMB / 2:
                painter.drawLine(int(a[0]), int(a[1]), int(b[0]), int(b[1]))
    painter.end()
    return image


def sun_image(base, lights):
    """Превью солнца: правая половина в ночи с огнями городов."""
    image = _blank()
    painter = QPainter(image)
    if base is not None:
        painter.drawImage(image.rect(), base)
    for x in range(THUMB):
        night = min(1.0, max(0.0, (x - THUMB * 0.35) / (THUMB * 0.25)))
        painter.fillRect(x, 0, 1, THUMB, QColor(4, 6, 16, int(225 * night)))
    if lights is not None:
        painter.setClipRect(int(THUMB * 0.5), 0, THUMB, THUMB)
        painter.drawImage(image.rect(), lights)
    painter.end()
    return image


def layer_ramp(key):
    """Цвета шкалы слоя без своей картинки."""
    if key == "quakes":
        return [color for _, color in quakes.DEPTH_STOPS]
    if key == "slope":
        return [color for _, color in slope.SLOPE_STOPS]
    return [color for _, color in slope.ASPECT_STOPS]


def layer_url(key):
    """Адрес тайла превью слоя или None, если картинка рисуется сама."""
    z, x, y = themes.THUMB_TILE
    if key == "clouds":
        template = clouds.url_template(time.time())
    elif key == "paleo":
        template = paleo.TILE_URL.replace("{age}", str(PALEO_AGE))
    elif key == "sun":
        template = sun.LIGHTS_URL
    else:
        return None
    return template.replace("{z}", str(z)).replace("{x}", str(x)).replace(
        "{y}", str(y))


def day_text(day):
    """«2026-10-05» в «05.10.2026»."""
    if not day:
        return ""
    year, month, date = day.split("-")
    return "{}.{}.{}".format(date, month, year)


class NasaMaps(QDialog):
    """Витрина карт и слоёв. window - окно глобуса."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle(tr("Карты и слои"))
        self.resize(700, 580)
        self.names = dict(map_names(), **layer_names())
        self.lights = None  # тайл огней городов для превью солнца
        self.items = {}
        self.thumbs = {}  # ключ - превью QImage
        self.base = None  # тайл подложки под превью
        self._queue = []
        self._replies = {}
        self._group = ALL
        top = QHBoxLayout()
        self.chips = QButtonGroup(self)
        self.chips.setExclusive(True)
        for key, title, tip in [(ALL, tr("Все"), tr("Все карты витрины."))] \
                + list(group_names()) + list(layer_group_names()):
            chip = QToolButton(self)
            chip.setText(title)
            chip.setToolTip(tip)
            chip.setCheckable(True)
            chip.setChecked(key == ALL)
            chip.setAutoRaise(True)
            chip.clicked.connect(lambda *a, k=key: self._set_group(k))
            self.chips.addButton(chip)
            top.addWidget(chip)
        top.addStretch(1)
        self.search = QLineEdit(self)
        self.search.setPlaceholderText(tr("Найти карту"))
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(140)
        self.search.setMaximumWidth(180)
        self.search.textChanged.connect(self._filter)
        top.addWidget(self.search)
        self.list = QListWidget(self)
        self.list.setViewMode(enum(QListView, "ViewMode", "IconMode"))
        self.list.setResizeMode(enum(QListView, "ResizeMode", "Adjust"))
        self.list.setMovement(enum(QListView, "Movement", "Static"))
        self.list.setIconSize(QSize(THUMB, THUMB))
        self.list.setGridSize(QSize(THUMB + 44, THUMB + 66))
        self.list.setTextElideMode(enum(Qt, "TextElideMode", "ElideNone"))
        self.list.setWordWrap(True)
        self.list.setSpacing(4)
        self.list.itemClicked.connect(self._clicked)
        self.note = QLabel(self)
        self.note.setWordWrap(True)
        off = QPushButton(tr("Выключить"), self)
        off.setToolTip(tr("Убрать карту с глобуса."))
        off.clicked.connect(lambda *a: self.window.set_theme(""))
        # Группы спутников - меню флажков, любые сразу.
        self.sat_button = QToolButton(self)
        self.sat_button.setText(tr("Группы спутников"))
        self.sat_button.setToolTip(tr(
            "Какие группы спутников CelesTrak показывает слой «Спутники»."))
        self.sat_button.setPopupMode(enum(QToolButton, "ToolButtonPopupMode",
                                          "InstantPopup"))
        self.sat_menu = QMenu(self.sat_button)
        self.sat_actions = {}
        for key, title, tip in satellite_group_names():
            action = self.sat_menu.addAction(title)
            action.setToolTip(tip)
            action.setCheckable(True)
            action.toggled.connect(self._sat_groups)
            self.sat_actions[key] = action
        self.sat_button.setMenu(self.sat_menu)
        bottom = QHBoxLayout()
        bottom.addWidget(self.note, 1)
        bottom.addWidget(self.sat_button)
        bottom.addWidget(off)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.list, 1)
        layout.addLayout(bottom)
        for key, group, kind in themes.gallery_items():
            name, tip = self.names[key]
            item = QListWidgetItem(name, self.list)
            item.setData(KEY_ROLE, key)
            item.setToolTip(tip)
            item.setTextAlignment(enum(Qt, "AlignmentFlag", "AlignHCenter"))
            self.items[key] = (item, group, kind)
            self.thumbs[key] = ramp_image(ramp_of(key)) \
                if kind in ("weather", themes.FIRES) else ramp_image([])
        for key, group in LAYERS:
            name, tip = self.names[key]
            item = QListWidgetItem(name, self.list)
            item.setData(KEY_ROLE, key)
            item.setToolTip(tip)
            item.setTextAlignment(enum(Qt, "AlignmentFlag", "AlignHCenter"))
            self.items[key] = (item, group, LAYER)
            self.thumbs[key] = self._layer_thumb(key)
        self._load_base()
        self.refresh()

    # Превью.

    def _load_base(self):
        """Тайл подложки под превью, затем тайлы тем."""
        source = self.window.sources[self.window._basemap]
        url = source.tile_url(*themes.THUMB_TILE)
        self._replies["base"] = fetch_bytes(url, self._base_done)

    def _base_done(self, data, error):
        self._replies.pop("base", None)
        image = QImage.fromData(data) if data else QImage()
        self.base = None if image.isNull() else image
        for key, (item, group, kind) in self.items.items():
            if kind in ("gibs", themes.TEMPERATURE) or layer_url(key):
                self._queue.append(key)
            elif kind == LAYER:
                self._set_thumb(key, self._layer_thumb(key))
            else:
                self._set_thumb(key, ramp_image(ramp_of(key), self.base))
        self._pump()

    def _layer_thumb(self, key, data=None):
        """Превью слоя. data - байты его тайла, если он есть."""
        if key == "stars":
            return stars_image()
        if key == "satellites":
            return satellites_image()
        if key == "cutaway":
            return cutaway_image()
        if key == "plates":
            return plates_image(self.base)
        if key == "sun":
            lights = QImage.fromData(data) if data else QImage()
            return sun_image(self.base, None if lights.isNull() else lights)
        if key == "clouds":
            # Облака, как на глобусе: прозрачность по белизне снимка.
            tile = QImage.fromData(data) if data else QImage()
            if not tile.isNull():
                tile = _rgba_image(clouds.cloud_rgba(
                    _rgba_array(tile), themes.THUMB_TILE), premultiplied=True)
            return _over(self.base, None if tile.isNull() else tile)
        if key == "paleo":
            tile = QImage.fromData(data) if data else QImage()
            return _over(None if tile.isNull() else tile, None)
        return ramp_image(layer_ramp(key), self.base)

    def _pump(self):
        """Следующие запросы превью, не больше PARALLEL сразу. Теме
        нужен ряд дат - его просит окно глобуса."""
        waiting = []
        while self._queue and len(self._replies) < PARALLEL:
            key = self._queue.pop(0)
            url = self._thumb_url(key)
            if url is None:
                waiting.append(key)
                continue
            self._replies[key] = fetch_bytes(
                url, lambda data, error, k=key: self._thumb_done(k, data))
        self._queue[:0] = waiting

    def _thumb_url(self, key):
        if self.items[key][2] == LAYER:
            return layer_url(key)
        if key == themes.TEMPERATURE:
            z, x, y = themes.THUMB_TILE
            return temperature.url_template(temperature.LAND).replace(
                "{z}", str(z)).replace("{x}", str(x)).replace("{y}", str(y))
        intervals = self.window._theme_domains.get(key)
        if intervals is None:
            theme = themes.BY_KEY[key]
            self.window._theme_fetch(key, "domains", theme.domains_url())
            return None
        day = themes.pick_day(intervals)
        if day is None:
            return None
        return themes.thumb_url(themes.BY_KEY[key], day)

    def _thumb_done(self, key, data):
        self._replies.pop(key, None)
        if self.items[key][2] == LAYER:
            self._set_thumb(key, self._layer_thumb(key, data))
        else:
            self._set_thumb(key, tile_image(data, self.base,
                                            themes.CLEAR.get(key, ())))
        self._pump()

    def _set_thumb(self, key, image):
        self.thumbs[key] = image
        self._label(key)

    def _show_icon(self, key, badge, on=False):
        """Значок карты: превью с бирочкой в левом верхнем углу. on -
        включённый слой, бирочка зелёная."""
        image = QImage(self.thumbs.get(key) or ramp_image([]))
        if badge:
            painter = QPainter(image)
            font = painter.font()
            font.setPixelSize(12)
            painter.setFont(font)
            width = painter.fontMetrics().horizontalAdvance(badge) + 8
            painter.setPen(enum(Qt, "PenStyle", "NoPen"))
            painter.setBrush(QColor(30, 140, 70, 230) if on
                             else QColor(20, 26, 36, 200))
            painter.drawRoundedRect(3, 3, width, 17, 3, 3)
            painter.setPen(QColor(240, 244, 250))
            painter.drawText(7, 16, badge)
            painter.end()
        self.items[key][0].setIcon(QIcon(QPixmap.fromImage(image)))

    def domains_arrived(self, key):
        """Окно глобуса получило ряд дат темы: подпись дня и превью."""
        if key not in self.items:
            return
        self._label(key)
        if key in self._queue:
            self._pump()

    # Выбор и вид.

    def _label(self, key):
        item, group, kind = self.items[key]
        name = self.names[key][0]
        if kind == LAYER:
            on = bool(self.window.extras.get(key))
            item.setText(name)
            self._show_icon(key, tr("✓ вкл") if on else "", on)
            return
        if kind == "gibs":
            intervals = self.window._theme_domains.get(key)
            day = themes.pick_day(intervals) if intervals else None
            sub = day_text(day) if day else ""
        elif kind == "weather":
            sub = tr("прогноз GFS")
        elif kind == themes.FIRES:
            sub = tr("24 часа")
        else:
            sub = tr("суша и море")
        item.setText(name)
        self._show_icon(key, sub)

    def refresh(self):
        """Подписи, выбранная карта и строка внизу."""
        for key in self.items:
            self._label(key)
        current = self.window.gallery_key()
        self.list.blockSignals(True)
        self.list.clearSelection()
        if current in self.items:
            self.items[current][0].setSelected(True)
            self.list.setCurrentItem(self.items[current][0])
        self.list.blockSignals(False)
        planet = self.window.planet
        relief = bool(getattr(planet, "terrain", None)) or planet.earth
        for key, (item, group, kind) in self.items.items():
            usable = planet.earth or key in ANY_BODY \
                or (key in RELIEF_BODY and relief)
            flags = item.flags()
            enabled = enum(Qt, "ItemFlag", "ItemIsEnabled")
            item.setFlags(flags | enabled if usable else flags & ~enabled)
        groups = self.window.satellite_manager.groups
        for key, action in self.sat_actions.items():
            action.blockSignals(True)
            action.setChecked(key in groups)
            action.blockSignals(False)
        if current in self.items:
            self.note.setText(tr("На глобусе: {name}. Повторный щелчок "
                                 "убирает карту.",
                                 name=self.names[current][0]))
        else:
            self.note.setText(tr("Щелчок по карте показывает её на "
                                 "глобусе. День задаёт шкала времени. "
                                 "Слои включаются независимо от карты."))

    def _clicked(self, item):
        key = item.data(KEY_ROLE)
        if self.items[key][2] == LAYER:
            self.window.set_extra(key, not self.window.extras.get(key))
            self.refresh()
            return
        if key == self.window.gallery_key():
            key = ""
        self.window.set_theme(key)

    def _sat_groups(self, *args):
        """Отметки меню групп спутников в окно глобуса."""
        self.window.satellite_manager.set_groups(
            {key for key, action in self.sat_actions.items()
             if action.isChecked()})

    def _set_group(self, group):
        self._group = group
        self._filter()

    def _filter(self, *args):
        text = self.search.text().strip().lower()
        for key, (item, group, kind) in self.items.items():
            shown = (self._group == ALL or group == self._group) and (
                not text or text in self.names[key][0].lower())
            item.setHidden(not shown)

    def closeEvent(self, event):
        for reply in list(self._replies.values()):
            reply.abort()
        self._replies.clear()
        self._queue = []
        super().closeEvent(event)
