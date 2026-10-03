# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «Помощник»: разговор с моделью, которая управляет глобусом.

Просьба автора от 3 октября 2026 года. Запросы, разбор ответов
и инструменты - core/assistant.py, исполняет инструменты окно глобуса
(GlobeWindow.assistant_tool). Ключ API лежит в менеджере паролей QGIS
(authcfg), в настройках хранится только номер записи.

Разговор: запрос пользователя -> модель -> вызовы инструментов ->
их ответы -> модель, пока модель не ответит текстом, но не больше
core.assistant.MAX_ROUNDS кругов.
"""
import html

from qgis.core import QgsApplication, QgsAuthMethodConfig, QgsSettings
from qgis.PyQt.QtWidgets import (QComboBox, QDialog, QFormLayout,
                                 QHBoxLayout, QLabel, QLineEdit,
                                 QPushButton, QTextBrowser, QVBoxLayout,
                                 QWidget)

from ..core import assistant as ai
from ..i18n import tr
from ..net.overlay import post_json
from ..qt_compat import enum

SETTINGS = "PlanetX/assistant/"


def _auth_key(provider):
    return SETTINGS + provider + "/authcfg"


def load_key(provider):
    """Ключ подключения из менеджера паролей QGIS или пустая строка."""
    auth_id = QgsSettings().value(_auth_key(provider), "")
    if not auth_id:
        return ""
    config = QgsAuthMethodConfig()
    found = QgsApplication.authManager().loadAuthenticationConfig(
        auth_id, config, True)
    if isinstance(found, tuple):
        found, config = found[0], found[-1]
    return config.config("password") if found else ""


def save_key(provider, key):
    """Ключ - в менеджер паролей QGIS, номер записи - в настройки.
    Прежняя запись того же подключения заменяется."""
    manager = QgsApplication.authManager()
    settings = QgsSettings()
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


class AssistantDialog(QDialog):
    """Немодальное окно помощника. executor(вызов core.assistant.Call)
    исполняет инструмент и даёт текст ответа, context() - словарь
    контекста вида для модели."""

    def __init__(self, executor, context, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Помощник"))
        self.setModal(False)
        self.executor = executor
        self.context = context
        self.dialog = []
        self.rounds = 0
        self.reply = None
        self.pending = None  # предложенная метка: функция записи
        settings = QgsSettings()
        self.provider = QComboBox(self)
        self.provider.addItem("Claude (Anthropic)", ai.ANTHROPIC)
        self.provider.addItem(tr("Формат OpenAI Responses (Grok и др.)"),
                              ai.RESPONSES)
        self.provider.setToolTip(tr(
            "Через какой сервис работает помощник. Anthropic - модели "
            "Claude. Формат OpenAI Responses - xAI Grok и другие сервисы "
            "этого формата. У каждого подключения свой ключ."))
        current = settings.value(SETTINGS + "provider", ai.ANTHROPIC)
        self.provider.setCurrentIndex(max(0, self.provider.findData(
            current)))
        self.base = QLineEdit(self)
        self.base.setToolTip(tr(
            "Адрес сервиса. Для Anthropic и xAI менять его не нужно."))
        self.model = QLineEdit(self)
        self.model.setToolTip(tr(
            "Название модели у выбранного сервиса, например "
            "claude-sonnet-5-5 или grok-4.7."))
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
        form = QFormLayout()
        form.addRow(tr("Сервис"), self.provider)
        form.addRow(tr("Адрес"), self.base)
        form.addRow(tr("Модель"), self.model)
        form.addRow(tr("Ключ"), key_row)
        self.provider.currentIndexChanged.connect(self._provider_changed)
        self.base.editingFinished.connect(self._remember)
        self.model.editingFinished.connect(self._remember)
        self.history = QTextBrowser(self)
        self.history.setOpenExternalLinks(True)
        self.note = QLabel(tr(
            "Запрос, точка взгляда и включённые строки раздела «Слои» "
            "уходят на сервер выбранной модели. Названия слоёв проекта "
            "и «Моих меток» не уходят."), self)
        self.note.setWordWrap(True)
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
        ask = QHBoxLayout()
        ask.addWidget(self.input, 1)
        ask.addWidget(self.send_button)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.history, 1)
        layout.addWidget(self.proposal)
        layout.addLayout(ask)
        layout.addWidget(self.note)
        self._provider_changed()
        self.resize(560, 620)

    # Настройки подключения.

    def provider_key(self):
        return self.provider.currentData()

    def _provider_changed(self, *args):
        provider = self.provider_key()
        settings = QgsSettings()
        base, model = ai.DEFAULTS[provider]
        self.base.setText(settings.value(SETTINGS + provider + "/base",
                                         base))
        self.model.setText(settings.value(SETTINGS + provider + "/model",
                                          model))
        self.key.clear()
        self.key.setPlaceholderText(
            tr("ключ сохранён") if load_key(provider)
            else tr("введите ключ API"))
        settings.setValue(SETTINGS + "provider", provider)

    def _remember(self):
        provider = self.provider_key()
        settings = QgsSettings()
        settings.setValue(SETTINGS + provider + "/base",
                          self.base.text().strip())
        settings.setValue(SETTINGS + provider + "/model",
                          self.model.text().strip())

    def _save_key(self):
        key = self.key.text().strip()
        if not key:
            return
        ok = save_key(self.provider_key(), key)
        self.key.clear()
        self.key.setPlaceholderText(tr("ключ сохранён") if ok
                                    else tr("введите ключ API"))
        self._say("note", tr("Ключ сохранён в менеджере паролей QGIS.")
                  if ok else tr("Ключ не сохранён: менеджер паролей QGIS "
                                "отказал."))

    # Разговор.

    def _say(self, who, text):
        colors = {"user": "#1f5fa8", "assistant": "#222222",
                  "tool": "#7a7a7a", "note": "#a05a00"}
        names = {"user": tr("Вы"), "assistant": tr("Помощник"),
                 "tool": tr("Действие"), "note": tr("Модуль")}
        self.history.append('<p style="color:{}"><b>{}:</b> {}</p>'.format(
            colors[who], html.escape(names[who]),
            html.escape(text).replace("\n", "<br>")))

    def send(self):
        text = self.input.text().strip()
        if not text or self.reply is not None:
            return
        self.input.clear()
        self._say("user", text)
        self.dialog.append({"role": "user", "text": text})
        self.rounds = 0
        self._ask()

    def _ask(self):
        provider = self.provider_key()
        key = load_key(provider)
        if not key:
            self._say("note", tr("Нет ключа API. Введите его в поле "
                                 "«Ключ» и нажмите «Сохранить ключ»."))
            return
        url, headers, body = ai.request(
            provider, self.base.text().strip() or ai.DEFAULTS[provider][0],
            self.model.text().strip() or ai.DEFAULTS[provider][1], key,
            ai.system_text(self.context()), self.dialog)
        self.send_button.setEnabled(False)
        self.reply = post_json(url, headers, body, self._answered)

    def _answered(self, data, error):
        self.reply = None
        self.send_button.setEnabled(True)
        answer = ai.parse(self.provider_key(), data)
        if answer.error or (data is None and error):
            self._say("note", tr("Модель не ответила: {error}",
                                 error=answer.error or error))
            # Неудачный вопрос не остаётся в разговоре: разговор
            # откатывается к состоянию до последнего вопроса
            # пользователя вместе с начатыми вызовами инструментов.
            for n in range(len(self.dialog) - 1, -1, -1):
                m = self.dialog[n]
                if m["role"] == "user" and not m.get("results"):
                    del self.dialog[n:]
                    break
            return
        self.dialog.append(ai.assistant_message(answer))
        if answer.text:
            self._say("assistant", answer.text)
        if not answer.calls:
            return
        results = []
        for call in answer.calls:
            text = self.executor(call)
            self._say("tool", text)
            results.append(ai.Result(call.id, text))
        self.dialog.append(ai.results_message(results))
        self.rounds += 1
        if self.rounds >= ai.MAX_ROUNDS:
            self._say("note", tr("Помощник остановлен: слишком много "
                                 "действий подряд."))
            return
        self._ask()

    # Предложенная метка.

    def propose(self, text, write):
        """Показать предложенную метку, write() записывает её."""
        self.pending = write
        self.proposal_text.setText(text)
        self.proposal.show()

    def _accept_place(self):
        if self.pending is not None:
            self._say("note", self.pending())
        self._reject_place()

    def _reject_place(self):
        self.pending = None
        self.proposal.hide()

    def closeEvent(self, event):
        if self.reply is not None:
            self.reply.abort()
            self.reply = None
        super().closeEvent(event)
