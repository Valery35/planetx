# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «Помощник»: разговор с моделью, которая управляет глобусом.

Просьба автора от 3 октября 2026 года. Запросы, разбор ответов
и инструменты - core/assistant.py, исполняет инструменты окно глобуса
(GlobeWindow.assistant_tool).

В окне «Помощник» - только разговор и поле вопроса. Сервис, адрес,
модель, ключ и флажки - в окне «Настройки помощника», решение автора
того же дня. По умолчанию - OpenRouter с бесплатной моделью.

Ключ API лежит в менеджере паролей QGIS (authcfg, в настройках только
номер записи) или, с флажком «Хранить ключ без мастер-пароля»,
открытым текстом в настройках профиля.

Разговор: запрос пользователя -> модель -> вызовы инструментов ->
их ответы -> модель, пока модель не ответит текстом. Круг ведёт
core.assistant.Agent, окно посылает запросы, исполняет вызовы
и спрашивает пользователя - разрешить чтение слоёв проекта
и действия с окнами, продолжить после MAX_ROUNDS кругов.
"""
import html
import json

from qgis.core import QgsApplication, QgsAuthMethodConfig, QgsSettings
from qgis.PyQt.QtCore import QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDialog,
                                 QDialogButtonBox, QFormLayout, QHBoxLayout,
                                 QLabel, QLineEdit, QPushButton,
                                 QTextBrowser, QVBoxLayout, QWidget)

from ..core import assistant as ai
from ..i18n import tr
from ..net.overlay import post_json, post_stream
from ..qt_compat import enum

SETTINGS = "PlanetX/assistant/"
# Сервис по умолчанию - бесплатная модель OpenRouter, решение автора
# от 3 октября 2026 года. Выбор пользователя хранится в настройках.
PROVIDER_DEFAULT = ai.OPENROUTER


def _auth_key(provider):
    return SETTINGS + provider + "/authcfg"


# Ключ без мастер-пароля: открытым текстом в настройках профиля QGIS.
# Выбор пользователя, флажок окна настроек, просьба автора от 3 октября
# 2026 года - мастер-пароль менеджера паролей мешал. По умолчанию
# включён, решение автора того же дня.
PLAIN_KEY = SETTINGS + "plain_key"
PLAIN_DEFAULT = True


def _plain_key(provider):
    return SETTINGS + provider + "/key"


def plain_enabled():
    return QgsSettings().value(PLAIN_KEY, PLAIN_DEFAULT, type=bool)


def load_key(provider):
    """Ключ подключения или пустая строка. Ключ из настроек профиля
    берётся первым, так мастер-пароль не спрашивается."""
    plain = QgsSettings().value(_plain_key(provider), "")
    if plain:
        return plain
    auth_id = QgsSettings().value(_auth_key(provider), "")
    if not auth_id:
        return ""
    config = QgsAuthMethodConfig()
    found = QgsApplication.authManager().loadAuthenticationConfig(
        auth_id, config, True)
    if isinstance(found, tuple):
        found, config = found[0], found[-1]
    return config.config("password") if found else ""


def save_key(provider, key, plain=False):
    """Ключ - в менеджер паролей QGIS, номер записи - в настройки.
    Прежняя запись того же подключения заменяется. plain - ключ
    открытым текстом в настройки профиля, менеджер паролей не
    трогается, ссылка на его запись снимается."""
    settings = QgsSettings()
    if plain:
        settings.setValue(_plain_key(provider), key)
        settings.remove(_auth_key(provider))
        return True
    settings.remove(_plain_key(provider))
    manager = QgsApplication.authManager()
    old = settings.value(_auth_key(provider), "")
    if old:
        manager.removeAuthenticationConfig(old)
    config = QgsAuthMethodConfig("Basic")
    config.setName("PlanetX " + provider)
    config.setConfig("username", provider)
    config.setConfig("password", key)
    stored = manager.storeAuthenticationConfig(config)
    if isinstance(stored, tuple):
        stored, config = stored[0], stored[-1]
    if stored:
        settings.setValue(_auth_key(provider), config.id())
    return bool(stored)


def current_provider():
    """Подключение, выбранное в настройках помощника последним."""
    provider = QgsSettings().value(SETTINGS + "provider", PROVIDER_DEFAULT)
    return provider if provider in ai.PROVIDERS else PROVIDER_DEFAULT


def provider_base(provider):
    """Адрес подключения из настроек или по умолчанию."""
    return QgsSettings().value(SETTINGS + provider + "/base", "") \
        or ai.DEFAULTS[provider][0]


def provider_model(provider):
    """Модель подключения из настроек или по умолчанию."""
    return QgsSettings().value(SETTINGS + provider + "/model", "") \
        or ai.DEFAULTS[provider][1]


def ready(provider, base=None):
    """Можно ли спрашивать: ключ сохранён или сервис на этом
    компьютере и ключ ему не нужен."""
    base = base or provider_base(provider)
    return bool(load_key(provider)) or not ai.needs_key(base)


# Просьбы из строки поиска глобуса уходят помощнику. Выбор
# пользователя, флажок окна настроек. Умолчание - включён, автор
# утвердил 3 октября 2026 года.
SEARCH_KEY = SETTINGS + "search"
SEARCH_DEFAULT = True


def search_enabled():
    """Отвечает ли помощник на просьбы из строки поиска."""
    return QgsSettings().value(SEARCH_KEY, SEARCH_DEFAULT, type=bool)


def service_names():
    """Подключения и их названия в списке, в порядке списка."""
    return ((ai.ANTHROPIC, "Claude (Anthropic)"),
            (ai.RESPONSES, "Grok (xAI)"),
            (ai.DEEPSEEK, "DeepSeek"),
            (ai.OPENROUTER, tr("OpenRouter (есть бесплатные модели)")),
            (ai.LOCAL, tr("Свой сервис, например Ollama")))


def service_name(provider):
    return dict(service_names()).get(provider, provider)


class AssistantSettings(QDialog):
    """Окно «Настройки помощника»: сервис, адрес, модель, ключ, флажки.
    Всё пишется в настройки QGIS сразу, changed сообщает об этом."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Настройки помощника"))
        self.provider = QComboBox(self)
        for key, name in service_names():
            self.provider.addItem(name, key)
        self.provider.setToolTip(tr(
            "Через какой сервис работает помощник. У каждого сервиса свой "
            "ключ, адрес и модель. У OpenRouter модели с «:free» в названии "
            "бесплатны с ограничением запросов в сутки. Свой сервис "
            "работает в формате OpenAI Chat, на этом компьютере ключ "
            "не нужен."))
        self.provider.setCurrentIndex(max(0, self.provider.findData(
            current_provider())))
        self.base = QLineEdit(self)
        self.base.setToolTip(tr(
            "Адрес сервиса. У Anthropic, xAI, DeepSeek и OpenRouter менять "
            "его не нужно. У своего сервиса - адрес его входа формата "
            "OpenAI, например http://localhost:11434/v1 у Ollama."))
        self.model = QLineEdit(self)
        self.model.setToolTip(tr(
            "Название модели у выбранного сервиса. Модель должна уметь "
            "вызывать инструменты (tools), иначе помощник только "
            "отвечает текстом."))
        self.key = QLineEdit(self)
        self.key.setEchoMode(enum(QLineEdit, "EchoMode", "Password"))
        self.key.setToolTip(tr(
            "Ключ API выбранного сервиса. Он хранится в менеджере паролей "
            "QGIS и уходит только на адрес сервиса."))
        save = QPushButton(tr("Сохранить ключ"), self)
        save.clicked.connect(self._save_key)
        key_row = QHBoxLayout()
        key_row.addWidget(self.key, 1)
        key_row.addWidget(save)
        self.plain = QCheckBox(tr("Хранить ключ без мастер-пароля"), self)
        self.plain.setChecked(plain_enabled())
        self.plain.setToolTip(tr(
            "Ключ сохраняется открытым текстом в настройках профиля QGIS, "
            "мастер-пароль менеджера паролей не спрашивается. Ключ "
            "прочитает любой, у кого есть доступ к папке профиля. "
            "Флажок действует на следующее сохранение ключа."))
        self.plain.toggled.connect(
            lambda on: QgsSettings().setValue(PLAIN_KEY, bool(on)))
        self.search = QCheckBox(tr("Отвечать на просьбы из строки «Поиск»"),
                                self)
        self.search.setChecked(search_enabled())
        self.search.setToolTip(tr(
            "Просьба словами в строке «Поиск» панели уходит помощнику, "
            "ответ появляется под строкой. Без флажка строка ищет только "
            "места и координаты."))
        self.search.toggled.connect(
            lambda on: QgsSettings().setValue(SEARCH_KEY, bool(on)))
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        form = QFormLayout()
        form.addRow(tr("Сервис"), self.provider)
        form.addRow(tr("Адрес"), self.base)
        form.addRow(tr("Модель"), self.model)
        form.addRow(tr("Ключ"), key_row)
        form.addRow("", self.plain)
        form.addRow("", self.search)
        buttons = QDialogButtonBox(
            enum(QDialogButtonBox, "StandardButton", "Close"), self)
        buttons.rejected.connect(self.close)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.status)
        layout.addWidget(buttons)
        self.provider.currentIndexChanged.connect(self._provider_changed)
        self.base.textEdited.connect(self._remember)
        self.model.textEdited.connect(self._remember)
        self._provider_changed()
        self.resize(560, 0)

    def provider_key(self):
        return self.provider.currentData()

    def _provider_changed(self, *args):
        provider = self.provider_key()
        QgsSettings().setValue(SETTINGS + "provider", provider)
        self.base.setText(provider_base(provider))
        self.model.setText(provider_model(provider))
        self.key.clear()
        self._key_state()
        self.status.clear()
        self.changed.emit()

    def _key_state(self):
        provider = self.provider_key()
        if load_key(provider):
            text = tr("ключ сохранён")
        elif not ai.needs_key(self.base.text().strip()
                              or ai.DEFAULTS[provider][0]):
            text = tr("ключ не нужен")
        else:
            text = tr("введите ключ API")
        self.key.setPlaceholderText(text)

    def _remember(self, *args):
        provider = self.provider_key()
        settings = QgsSettings()
        settings.setValue(SETTINGS + provider + "/base",
                          self.base.text().strip())
        settings.setValue(SETTINGS + provider + "/model",
                          self.model.text().strip())
        self._key_state()
        self.changed.emit()

    def _save_key(self):
        key = self.key.text().strip()
        if not key:
            return
        plain = self.plain.isChecked()
        ok = save_key(self.provider_key(), key, plain)
        self.key.clear()
        self._key_state()
        if plain:
            self.status.setText(tr("Ключ сохранён в настройках профиля "
                                   "QGIS без мастер-пароля."))
        else:
            self.status.setText(
                tr("Ключ сохранён в менеджере паролей QGIS.") if ok
                else tr("Ключ не сохранён: менеджер паролей QGIS "
                        "отказал."))
        self.changed.emit()


class AssistantDialog(QDialog):
    """Немодальное окно помощника. executor(вызов core.assistant.Call)
    исполняет инструмент и даёт текст ответа, context() - словарь
    контекста вида для модели, describe(вызов) - что сделает вызов,
    для вопроса о разрешении. Разговор идёт и в скрытом окне, так
    работает строка поиска глобуса (ask). Вопрос о разрешении окно
    показывает."""

    # Каждая реплика разговора: кто («user», «assistant», «tool»,
    # «note») и текст.
    said = pyqtSignal(str, str)
    # Ответ модели ждётся или уже пришёл.
    busy_changed = pyqtSignal(bool)
    # Документ KML, созданный одним запросом (generate).
    generated = pyqtSignal(str)
    # Метки идут потоком: сколько меток уже пришло целиком.
    progress = pyqtSignal(int)

    # Ждёт ли разговор ответа пользователя: разрешения или «Продолжить».
    waiting_changed = pyqtSignal(bool)

    def __init__(self, executor, context, parent=None, describe=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Помощник"))
        self.setModal(False)
        self.executor = executor
        self.context = context
        self.describe = describe
        self.agent = ai.Agent()
        self.reply = None
        # Пауза перед повтором запроса после временного отказа.
        self.retry_timer = QTimer(self)
        self.retry_timer.setSingleShot(True)
        self.retry_timer.timeout.connect(self._ask)
        self.asked = None  # подключение запроса, который ждёт ответа
        # Поток ответа создания меток (core.assistant.StreamText), число
        # пришедших меток, предел длины запроса и признак остановки.
        self.stream = None
        self.stream_places = 0
        self.stream_tokens = 0
        self.stopped = False
        # Почему документ создания меток неполон, пусто - документ целый.
        self.partial = ""
        self.pending = None  # предложенная метка: функция записи
        self.settings = None
        self.service = QLabel(self)
        self.service.setWordWrap(True)
        setup = QPushButton(tr("Настройки…"), self)
        setup.setToolTip(tr("Сервис, модель и ключ API помощника."))
        setup.clicked.connect(self.open_settings)
        top = QHBoxLayout()
        top.addWidget(self.service, 1)
        top.addWidget(setup)
        self.history = QTextBrowser(self)
        self.history.setOpenExternalLinks(True)
        self.history.setPlaceholderText(tr(
            "Здесь идёт разговор: ваши вопросы, действия помощника на "
            "глобусе и его ответы. Вопрос задаётся в поле ниже или "
            "в строке «Поиск» панели."))
        self.note = QLabel(tr(
            "Запрос, точка взгляда и включённые строки раздела «Слои» "
            "уходят на сервер выбранной модели. Слои проекта, их поля "
            "и строки уходят, только когда вы разрешаете чтение. "
            "«Мои метки» уходят только выделенными."), self)
        self.note.setWordWrap(True)
        # Вопрос о разрешении вызова: core.assistant.CONFIRM.
        self.confirm = QWidget(self)
        self.confirm_text = QLabel(self.confirm)
        self.confirm_text.setWordWrap(True)
        self.allow_button = QPushButton(tr("Разрешить"), self.confirm)
        self.allow_button.setToolTip(tr("Выполнить это действие один раз."))
        self.allow_button.clicked.connect(
            lambda: self._decide(ai.ALLOW))
        self.always_button = QPushButton(tr("Разрешить в этом разговоре"),
                                         self.confirm)
        self.always_button.setToolTip(tr(
            "Точно такой же запрос больше не спрашивается до нового "
            "разговора. Другой слой или другой отбор спросится снова."))
        self.always_button.clicked.connect(
            lambda: self._decide(ai.ALLOW_ALWAYS))
        self.deny_button = QPushButton(tr("Отказать"), self.confirm)
        self.deny_button.setToolTip(tr(
            "Помощник получает отказ и отвечает без этого действия."))
        self.deny_button.clicked.connect(lambda: self._decide(ai.DENY))
        confirm_row = QHBoxLayout(self.confirm)
        confirm_row.setContentsMargins(0, 0, 0, 0)
        confirm_row.addWidget(self.confirm_text, 1)
        confirm_row.addWidget(self.allow_button)
        confirm_row.addWidget(self.always_button)
        confirm_row.addWidget(self.deny_button)
        self.confirm.hide()
        # Круги кончились: core.assistant.LIMIT.
        self.more = QWidget(self)
        more_text = QLabel(tr("Помощник сделал много действий подряд."),
                           self.more)
        more_text.setWordWrap(True)
        self.more_button = QPushButton(tr("Продолжить"), self.more)
        self.more_button.setToolTip(tr(
            "Помощник продолжает с того места, где остановился."))
        self.more_button.clicked.connect(self._resume)
        stop = QPushButton(tr("Остановить"), self.more)
        stop.clicked.connect(self.stop_talk)
        more_row = QHBoxLayout(self.more)
        more_row.setContentsMargins(0, 0, 0, 0)
        more_row.addWidget(more_text, 1)
        more_row.addWidget(self.more_button)
        more_row.addWidget(stop)
        self.more.hide()
        self.proposal = QWidget(self)
        self.proposal_text = QLabel(self.proposal)
        self.proposal_text.setWordWrap(True)
        accept = QPushButton(tr("Записать в «Мои метки»"), self.proposal)
        accept.clicked.connect(self._accept_place)
        reject = QPushButton(tr("Отменить"), self.proposal)
        reject.clicked.connect(self._reject_place)
        row = QHBoxLayout(self.proposal)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.proposal_text, 1)
        row.addWidget(accept)
        row.addWidget(reject)
        self.proposal.hide()
        self.input = QLineEdit(self)
        self.input.setPlaceholderText(tr(
            "Например: покажи разрез через Японский жёлоб"))
        self.input.returnPressed.connect(self.send)
        self.send_button = QPushButton(tr("Спросить"), self)
        self.send_button.clicked.connect(self.send)
        self.make_button = QPushButton(tr("Создать метки"), self)
        self.make_button.setToolTip(tr(
            "Метки, пути и многоугольники по описанию в поле, например "
            "«путешествие Колумба». Модель отвечает одним документом KML, "
            "он сразу записывается новой папкой в «Мои метки»."))
        self.make_button.clicked.connect(self._make)
        ask = QHBoxLayout()
        ask.addWidget(self.input, 1)
        ask.addWidget(self.send_button)
        ask.addWidget(self.make_button)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.history, 1)
        layout.addWidget(self.proposal)
        layout.addWidget(self.confirm)
        layout.addWidget(self.more)
        layout.addLayout(ask)
        layout.addWidget(self.note)
        self._show_service()
        self.resize(560, 520)

    # Настройки.

    def provider_key(self):
        return current_provider()

    def open_settings(self):
        """Окно «Настройки помощника», одно на окно помощника."""
        if self.settings is None:
            self.settings = AssistantSettings(self)
            self.settings.changed.connect(self._show_service)
        self.settings.show()
        self.settings.raise_()

    def _show_service(self):
        provider = self.provider_key()
        text = tr("Сервис: {service}, модель {model}.",
                  service=service_name(provider),
                  model=provider_model(provider))
        if not ready(provider):
            text += " " + tr("Ключа API нет.")
        self.service.setText(text)

    # Разговор.

    def _say(self, who, text):
        colors = {"user": "#1f5fa8", "assistant": "#222222",
                  "tool": "#7a7a7a", "note": "#a05a00"}
        names = {"user": tr("Вы"), "assistant": tr("Помощник"),
                 "tool": tr("Действие"), "note": tr("Модуль")}
        self.history.append('<p style="color:{}"><b>{}:</b> {}</p>'.format(
            colors[who], html.escape(names[who]),
            html.escape(text).replace("\n", "<br>")))
        self.said.emit(who, text)

    def send(self):
        text = self.input.text().strip()
        if self.ask(text):
            self.input.clear()

    def _make(self):
        if self.generate(self.input.text()):
            self.input.clear()

    @property
    def dialog(self):
        """Разговор в нейтральном виде core.assistant."""
        return self.agent.dialog

    def busy(self):
        return self.reply is not None or self.retry_timer.isActive()

    def waiting(self):
        """Ждёт ли разговор разрешения или «Продолжить»."""
        return not self.confirm.isHidden() or not self.more.isHidden()

    def ask(self, text):
        """Вопрос модели из поля окна или из строки поиска глобуса.
        Пока ждётся прежний ответ, вопрос не принимается. Новый вопрос
        снимает ждущий вопрос о разрешении и «Продолжить»."""
        text = text.strip()
        if not text or self.busy():
            return False
        if not ready(self.provider_key()):
            # Без ключа вопрос не уходит и не остаётся в разговоре,
            # иначе следующий запрос нёс бы два вопроса подряд.
            self._say("note", tr("Нет ключа API. Его вводят в окне "
                                 "«Настройки помощника»."))
            self.show()
            self.open_settings()
            return False
        if self.waiting():
            self.stop_talk()
        self._say("user", text)
        self._step(self.agent.ask(text))
        return True

    def generate(self, text):
        """Метки по описанию одним запросом: модель без инструментов
        возвращает KML текстом, документ уходит сигналом generated.
        Кругов инструментов нет, разговор в запрос не идёт. Ответ идёт
        потоком: число пришедших меток сообщает сигнал progress."""
        text = text.strip()
        if not text or self.busy() or self.waiting():
            return False
        if not ready(self.provider_key()):
            self._say("note", tr("Нет ключа API. Его вводят в окне "
                                 "«Настройки помощника»."))
            self.show()
            self.open_settings()
            return False
        self._say("user", text)
        self._start_stream(text, ai.KML_MAX_TOKENS)
        return True

    def _start_stream(self, text, max_tokens):
        provider = self.provider_key()
        url, headers, body = ai.request(
            provider, provider_base(provider), provider_model(provider),
            load_key(provider), ai.kml_system_text(self.context()),
            [{"role": "user", "text": text}], tools=False,
            max_tokens=max_tokens, stream=True)
        self.send_button.setEnabled(False)
        self.make_button.setEnabled(False)
        self.asked = provider
        self.stream = ai.StreamText(provider)
        self.stream_places = 0
        self.stream_tokens = max_tokens
        self.stopped = False
        self.partial = ""
        self.reply = post_stream(
            url, headers, body, self._stream_chunk,
            lambda error: self._generated(text, error))
        self.busy_changed.emit(True)

    def _stream_chunk(self, data):
        stream = self.stream
        if stream is None or not stream.feed(data):
            return
        count = ai.kml_progress(stream.text)
        if count != self.stream_places:
            self.stream_places = count
            self.progress.emit(count)

    def stop_generation(self):
        """Остановить создание меток. Метки, пришедшие целиком,
        остаются: документ закрывается по последней целой метке."""
        if self.reply is not None and self.stream is not None:
            self.stopped = True
            self.reply.abort()

    def _generated(self, text, error):
        stream, self.stream = self.stream, None
        if stream is None:
            return  # окно закрыто, поток снят
        self.reply = None
        stream.finish()
        stopped, self.stopped = self.stopped, False
        reason = stream.error or ("" if stopped else error)
        if (reason and not stream.text
                and self.stream_tokens > ai.KML_SAFE_TOKENS
                and ai.length_refused(reason)):
            # Сервис не принял предел длины ответа - повтор с меньшим.
            self._say("note", tr("Сервис не принял длинный ответ, запрос "
                                 "повторён с меньшим пределом длины."))
            self._start_stream(text, ai.KML_SAFE_TOKENS)
            return
        self.send_button.setEnabled(True)
        self.make_button.setEnabled(True)
        self.busy_changed.emit(False)
        kml = ai.extract_kml(stream.text)
        if kml is None:
            if not reason:
                self._say("note", tr("Модель не вернула документ KML."))
                return
            self._say("note", tr("Модель не ответила: {error}",
                                 error=reason))
            if not ai.needs_key(provider_base(self.asked
                                              or self.provider_key())):
                self._say("note", tr(
                    "Сервис на этом компьютере не отвечает. Проверьте, "
                    "что он запущен, например Ollama, и что адрес "
                    "в настройках помощника верный."))
            return
        whole = "</kml>" in stream.text
        if reason:
            self.partial = tr("Ответ модели оборвался: {error}. Взяты "
                              "метки, пришедшие целиком.", error=reason)
        elif stopped:
            self.partial = tr("Создание меток остановлено. Взяты метки, "
                              "пришедшие целиком.")
        elif not whole:
            self.partial = tr("Ответ модели упёрся в предел длины. Взяты "
                              "метки, пришедшие целиком.")
        if self.partial:
            self._say("note", self.partial)
        # В разговоре остаётся короткий след, сам документ в запросы
        # разговора не идёт.
        self.agent.ask(text)
        self.dialog.append({"role": "assistant",
                            "text": tr("Метки созданы документом KML.")})
        self.generated.emit(kml)

    def say_note(self, text):
        """Строка модуля в разговоре, от окна глобуса."""
        self._say("note", text)

    def _ask(self):
        provider = self.provider_key()
        base = provider_base(provider)
        key = load_key(provider)
        if not key and ai.needs_key(base):
            self._say("note", tr("Нет ключа API. Его вводят в окне "
                                 "«Настройки помощника»."))
            return
        url, headers, body = ai.request(
            provider, base, provider_model(provider), key,
            ai.system_text(self.context()), self.agent.dialog_for_request())
        self.send_button.setEnabled(False)
        self.asked = provider
        self.reply = post_json(url, headers, body, self._answered)
        self.busy_changed.emit(True)

    def _answered(self, data, error):
        self.reply = None
        self.send_button.setEnabled(True)
        self.busy_changed.emit(False)
        provider = self.asked or self.provider_key()
        answer = ai.parse(provider, data)
        if not answer.error and answer.text:
            self._say("assistant", answer.text)
        # Без тела ответа причина - в ошибке сети, а не в «no data».
        step = self.agent.answered(answer, error if data is None else "")
        if step.kind == ai.FAILED and data is None \
                and not ai.needs_key(provider_base(provider)):
            self._say("note", tr("Модель не ответила: {error}",
                                 error=step.text))
            self._say("note", tr(
                "Сервис на этом компьютере не отвечает. Проверьте, "
                "что он запущен, например Ollama, и что адрес "
                "в настройках помощника верный."))
            return
        self._step(step)

    def _step(self, step):
        """Следующий шаг круга разговора core.assistant.Agent. Вызовы
        без разрешения исполняются сразу, подряд."""
        while step.kind == ai.RUN:
            text = self.executor(step.call)
            self._say("tool", text)
            step = self.agent.result(text)
        if step.kind == ai.SEND:
            self._ask()
        elif step.kind == ai.RETRY:
            self._say("note", tr(
                "Сервис занят ({error}), повтор через {seconds} с.",
                error=step.text, seconds="{:g}".format(step.delay)))
            self.retry_timer.start(int(step.delay * 1000))
            self.busy_changed.emit(True)
        elif step.kind == ai.CONFIRM:
            self._ask_user(step.call)
        elif step.kind == ai.LIMIT:
            self.more.show()
            self.waiting_changed.emit(True)
            self._say("note", tr("Помощник сделал много действий подряд "
                                 "и ждёт «Продолжить»."))
            self._bring_up()
        elif step.kind == ai.FAILED:
            self._say("note", tr("Модель не ответила: {error}",
                                 error=step.text))

    def _ask_user(self, call):
        """Вопрос о разрешении вызова в окне. Вопрос из строки поиска
        идёт в скрытом окне - окно показывается."""
        text = self.describe(call) if self.describe else ""
        self.confirm_text.setText(text or tr(
            "Помощник просит выполнить {name} {args}.", name=call.name,
            args=json.dumps(call.args or {}, ensure_ascii=False)))
        self.confirm.show()
        self.waiting_changed.emit(True)
        self._say("note", self.confirm_text.text())
        self._bring_up()

    def _bring_up(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _decide(self, choice):
        """Ответ пользователя на вопрос о разрешении."""
        if self.confirm.isHidden():
            return
        self.confirm.hide()
        self.waiting_changed.emit(False)
        if choice == ai.DENY:
            self._say("note", tr("Отказано."))
        self._step(self.agent.decide(choice))

    def _resume(self):
        self.more.hide()
        self.waiting_changed.emit(False)
        self._step(self.agent.resume())

    def stop_talk(self):
        """Остановить круг разговора: ждущий вопрос о разрешении,
        «Продолжить» и повтор после отказа снимаются."""
        self.retry_timer.stop()
        was = self.waiting()
        self.confirm.hide()
        self.more.hide()
        self.agent.cancel()
        if was:
            self.waiting_changed.emit(False)
        self.busy_changed.emit(self.reply is not None)

    # Предложенная метка.

    def propose(self, text, write):
        """Показать предложенную метку, write() записывает её."""
        self.pending = write
        self.proposal_text.setText(text)
        self.proposal.show()
        # Вопрос из строки поиска идёт в скрытом окне. Предложение
        # видно под строкой поиска со ссылкой «Записать»
        # (GlobeWindow._assistant_said), окно само не всплывает.
        if self.isVisible():
            self.raise_()

    def _accept_place(self):
        # Предложение снимается до сообщения о записи, иначе строка
        # поиска показала бы его снова со ссылкой «Записать».
        write = self.pending
        self._reject_place()
        if write is not None:
            self._say("note", write())

    def _reject_place(self):
        self.pending = None
        self.proposal.hide()

    def closeEvent(self, event):
        if self.waiting() or self.retry_timer.isActive():
            self.stop_talk()
        if self.reply is not None:
            # Поток создания меток снимается без записи пришедшего.
            self.stream = None
            self.reply.abort()
            self.reply = None
            self.busy_changed.emit(False)
        if self.settings is not None:
            self.settings.close()
        super().closeEvent(event)
