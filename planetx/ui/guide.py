# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Знакомство с модулем: подсказки поверх окна глобуса при первом
открытии.

Решение автора от 11 октября 2026 года, шаг 3 плана «интерфейс над
возможностями» в AGENTS.md. Пять остановок - глобус под мышью, строка
«Поиск», раздел «Слои», меню правой кнопки, шкала времени. Остановка
затемняет окно, кроме места, о котором рассказывает, рядом стоит
окошко с текстом и кнопками. Затемнение мышь пропускает, глобус под
ним можно пробовать. Окно показывается один раз (настройка
GUIDE_KEY), потом - по действию «Знакомство с модулем» строки «Поиск».
"""
from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QEvent, QPoint, QRect, Qt, QTimer
from qgis.PyQt.QtGui import QColor, QPainter, QPainterPath
from qgis.PyQt.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                                 QVBoxLayout, QWidget)

from ..i18n import tr
from ..qt_compat import enum

GUIDE_KEY = "PlanetX/guide_shown"
SHADE = QColor(0, 0, 0, 110)  # затемнение вне подсвеченного места
EDGE = QColor(90, 170, 255)  # рамка подсвеченного места
MARGIN = 6  # пикселей запаса вокруг подсвеченного виджета
BUBBLE_WIDTH = 340
PLACE_AGAIN = 150  # мс, второй расчёт выреза после раскрытия раздела
LAYERS_MIN = 160  # пикселей высоты раздела «Слои» на его остановке


def stops():
    """Остановки: (что подсветить, заголовок, текст). Что подсветить -
    имя, его понимает Guide.target."""
    return (
        ("view", tr("Глобус"), tr(
            "С нажатой левой кнопкой Земля поворачивается вслед "
            "за курсором. Колесо приближает "
            "к точке под курсором. Средняя кнопка или левая с Shift "
            "наклоняет и поворачивает вид. Двойной щелчок - перелёт "
            "к точке.")),
        ("search", tr("Строка «Поиск»"), tr(
            "Здесь ищутся места, координаты и темы. Здесь же находятся "
            "возможности модуля - наберите «течения», «линейка» или "
            "«снимки» и выберите подсказку. Ctrl+K из любого места окна "
            "ставит курсор в эту строку.")),
        ("layers", tr("Раздел «Слои»"), tr(
            "Основа, рельеф и слои глобуса. Строка «Набор» вверху "
            "включает слои под задачу одним выбором - геолог, горняк, "
            "гидролог, историк. Строка «Карты и слои» открывает витрину "
            "карт NASA, погоды и слоёв недр.")),
        ("menu", tr("Меню правой кнопки"), tr(
            "Правая кнопка на глобусе открывает меню точки - что здесь, "
            "снимки Sentinel-2 и Landsat, исторические карты, маршрут, "
            "номенклатура листа, линейка и метка.")),
        ("time", tr("Шкала времени"), tr(
            "Значок открывает шкалу времени, когда у данных есть время - "
            "метки с датами, землетрясения, карты NASA, течения, "
            "исторические карты. Бегунок задаёт день, кнопки проигрывают "
            "время.")),
    )


class Shade(QWidget):
    """Затемнение окна с вырезом вокруг подсвеченного места. Мышь
    проходит сквозь него."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(enum(Qt, "WidgetAttribute",
                               "WA_TransparentForMouseEvents"))
        self.hole = QRect()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        path = QPainterPath()
        path.addRect(0.0, 0.0, float(self.width()), float(self.height()))
        if not self.hole.isNull():
            inner = QPainterPath()
            inner.addRoundedRect(float(self.hole.x()), float(self.hole.y()),
                                 float(self.hole.width()),
                                 float(self.hole.height()), 8.0, 8.0)
            path = path.subtracted(inner)
            painter.setPen(EDGE)
            painter.drawPath(inner)
        painter.fillPath(path, SHADE)


class Guide(QWidget):
    """Знакомство с модулем поверх окна глобуса. Окошко с текстом -
    отдельный виджет окна, затемнение - Shade под ним."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.index = 0
        self.items = stops()
        self.shade = Shade(window)
        self.setObjectName("planetxGuide")
        self.setStyleSheet(
            "#planetxGuide {background: palette(window); "
            "border: 1px solid #5aaaff; border-radius: 8px;}")
        self.setAttribute(enum(Qt, "WidgetAttribute", "WA_StyledBackground"))
        self.setFixedWidth(BUBBLE_WIDTH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        self.title = QLabel(self)
        font = self.title.font()
        font.setBold(True)
        self.title.setFont(font)
        self.text = QLabel(self)
        self.text.setWordWrap(True)
        self.count = QLabel(self)
        buttons = QHBoxLayout()
        buttons.addWidget(self.count, 1)
        self.back = QPushButton(tr("Назад"), self)
        self.back.clicked.connect(lambda: self.show_stop(self.index - 1))
        self.next = QPushButton(tr("Далее"), self)
        self.next.clicked.connect(self._next)
        close = QPushButton(tr("Закрыть"), self)
        close.clicked.connect(self.finish)
        for button in (self.back, self.next, close):
            buttons.addWidget(button)
        line = QFrame(self)
        line.setFrameShape(enum(QFrame, "Shape", "HLine"))
        layout.addWidget(self.title)
        layout.addWidget(self.text)
        layout.addWidget(line)
        layout.addLayout(buttons)
        window.installEventFilter(self)

    def start(self):
        """Первая остановка. Настройка запоминает, что знакомство было."""
        QgsSettings().setValue(GUIDE_KEY, True)
        self.show_stop(0)

    def _next(self):
        if self.index + 1 >= len(self.items):
            self.finish()
        else:
            self.show_stop(self.index + 1)

    def finish(self):
        """Знакомство закрыто."""
        self.window.removeEventFilter(self)
        self.shade.hide()
        self.shade.deleteLater()
        self.hide()
        self.deleteLater()
        if getattr(self.window, "guide", None) is self:
            self.window.guide = None

    def show_stop(self, index):
        self.index = max(0, min(index, len(self.items) - 1))
        target, title, text = self.items[self.index]
        self.title.setText(title)
        self.text.setText(text)
        self.count.setText("{} / {}".format(self.index + 1, len(self.items)))
        self.back.setEnabled(self.index > 0)
        self.next.setText(tr("Готово") if self.index + 1 == len(self.items)
                          else tr("Далее"))
        self._prepare(target)
        self.place()
        # Развёрнутый раздел получает высоту после прохода цикла
        # событий, вырез считается ещё раз. Без этого у «Слоёв» был
        # вырез в 22 пикселя, шаг guide_tour 11 октября 2026 года.
        QTimer.singleShot(PLACE_AGAIN, self._place_if_alive)
        self.shade.show()
        self.shade.raise_()
        self.show()
        self.raise_()

    def _prepare(self, target):
        """Подсвеченное место видно: панель открыта, раздел развёрнут."""
        window = self.window
        if target in ("search", "layers") and window.panel.isHidden():
            window.set_sidebar(True)
        if target == "layers":
            panel = window.panel
            panel.sections[2].set_open(True)
            # Раскрытый раздел разделитель оставляет высотой заголовка,
            # ему отдаётся треть панели от самого высокого раздела.
            sizes = panel.split.sizes()
            if len(sizes) == 3 and sizes[2] < LAYERS_MIN:
                want = max(LAYERS_MIN, sum(sizes) // 3)
                big = sizes.index(max(sizes[:2]))
                give = min(want - sizes[2], sizes[big] - LAYERS_MIN)
                if give > 0:
                    sizes[big] -= give
                    sizes[2] += give
                    panel.split.setSizes(sizes)

    def target(self, name):
        """Виджет остановки или None."""
        window = self.window
        return {"view": window.view, "menu": window.view,
                "search": window.panel.place,
                "layers": window.panel.geo,
                "time": window.toolbar.time}.get(name)

    def place(self):
        """Вырез вокруг виджета остановки и окошко рядом с ним."""
        window = self.window
        self.shade.setGeometry(0, 0, window.width(), window.height())
        widget = self.target(self.items[self.index][0])
        if widget is None or not widget.isVisible():
            self.shade.hole = QRect()
            hole = QRect(window.width() // 2, window.height() // 3, 0, 0)
        else:
            corner = widget.mapTo(window, QPoint(0, 0))
            # У вида вырез - весь вид, затемнена только панель, окошко
            # встаёт в верхнюю треть вида.
            hole = QRect(corner, widget.size()).adjusted(
                -MARGIN, -MARGIN, MARGIN, MARGIN)
            self.shade.hole = hole
        self.shade.update()
        self.adjustSize()
        width, height = self.width(), self.height()
        if self.shade.hole.isNull() or hole.width() > window.width() / 2:
            x = hole.center().x() - width // 2
            y = hole.top() + hole.height() // 3
        elif self.items[self.index][0] == "search":
            # Справа от строки стоит кнопка «Поиск» - окошко под строкой.
            x, y = hole.left(), hole.bottom() + 12
        elif hole.right() + width + 12 < window.width():
            x, y = hole.right() + 12, hole.top()
        else:
            x, y = hole.left(), hole.bottom() + 12
        x = max(8, min(x, window.width() - width - 8))
        y = max(8, min(y, window.height() - height - 8))
        self.move(x, y)

    def _place_if_alive(self):
        if self.isVisible():
            self.place()

    def eventFilter(self, watched, event):
        if watched is self.window and event.type() in (
                enum(QEvent, "Type", "Resize"), enum(QEvent, "Type", "Show")):
            self.place()
        return False

    def keyPressEvent(self, event):
        if event.key() == enum(Qt, "Key", "Key_Escape"):
            self.finish()
            return
        super().keyPressEvent(event)


def first_time():
    """Знакомство ещё не показывалось в этом профиле QGIS."""
    return not QgsSettings().value(GUIDE_KEY, False, type=bool)
