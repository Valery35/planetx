# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Суточная проверка бота PlanetX, только стандартная библиотека.

Запускает .github/workflows/bot-health.yml раз в сутки. Секреты
TELEGRAM_BOT_TOKEN и TELEGRAM_OWNER - те же, что у «Telegram
о выпуске». Проверка:
- getWebhookInfo - адрес приёма стоит, свежей ошибки нет, нажатия
  не копятся;
- адрес бота отвечает «PlanetX bot <метка>», без «mismatch»;
- срок бесплатного приложения PythonAnywhere не ближе WARN_DAYS дней.
Найденное уходит автору сообщением, шаг Actions краснеет. Без
неполадок сообщения нет.
"""
import datetime
import json
import os
import sys
import urllib.error
import urllib.request

BOT_URL = "https://valery35.pythonanywhere.com/"
WEBHOOK_PATH = "/telegram"
# Срок бесплатного приложения PythonAnywhere. После «Run until 3 months
# from today» на вкладке Web - новая дата здесь и в bot/DEPLOY.md.
# Продлено 16 ноября 2026 года.
APP_EXPIRES = datetime.date(2027, 2, 16)
# Предупреждение за столько дней до срока. Письмо PythonAnywhere
# приходит за 3 дня, двух недель хватает и на отпуск автора.
WARN_DAYS = 14
# Ошибка адреса приёма свежее стольких часов - неполадка.
ERROR_HOURS = 26
# Нажатий, которые Telegram не смог доставить, больше - неполадка.
PENDING_MAX = 3
TIMEOUT = 30


def problems(info, status, body, today, now):
    """Неполадки по ответу getWebhookInfo, ответу адреса бота (код и
    текст, код None - адрес не ответил), дате и времени UNIX."""
    out = []
    url = (info or {}).get("url") or ""
    if not url.endswith(WEBHOOK_PATH):
        out.append("Адрес приёма не стоит: «{}». Вернуть - шаг 7 "
                   "bot/DEPLOY.md.".format(url))
    error_at = (info or {}).get("last_error_date") or 0
    if error_at and now - error_at < ERROR_HOURS * 3600:
        out.append("Telegram не доставил обновление: {}.".format(
            info.get("last_error_message") or "?"))
    pending = (info or {}).get("pending_update_count") or 0
    if pending > PENDING_MAX:
        out.append("Недоставленных нажатий и сообщений: {}.".format(
            pending))
    if status is None:
        out.append("Адрес бота не отвечает: {}.".format(body))
    elif not body.startswith("PlanetX bot"):
        out.append("Адрес бота отвечает не ботом: {} {}.".format(
            status, body[:80]))
    elif "mismatch" in body:
        out.append("Половинная выкладка: {}. Выложить архив "
                   "make_bundle целиком.".format(body))
    left = (APP_EXPIRES - today).days
    if left <= WARN_DAYS:
        out.append("Срок приложения PythonAnywhere {} - {}. Нажать "
                   "«Run until 3 months from today» на вкладке Web и "
                   "вписать новую дату в bot/health.py и bot/DEPLOY.md."
                   .format(APP_EXPIRES.isoformat(),
                           "через {} дн.".format(left) if left > 0
                           else "наступил"))
    return out


def telegram(token, method, **params):
    request = urllib.request.Request(
        "https://api.telegram.org/bot{}/{}".format(token, method),
        data=json.dumps(params).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
        return json.loads(answer.read().decode("utf-8"))["result"]


def fetch_root(url=BOT_URL):
    """Код и текст ответа адреса бота, без ответа - None и причина."""
    request = urllib.request.Request(url, headers={
        "User-Agent": "PlanetX-bot-health"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as answer:
            return answer.status, answer.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as error:
        return None, str(error)


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    owner = os.environ.get("TELEGRAM_OWNER")
    if not token or not owner:
        print("Секреты TELEGRAM_BOT_TOKEN и TELEGRAM_OWNER не заданы")
        return 1
    try:
        info = telegram(token, "getWebhookInfo")
    except (urllib.error.URLError, OSError, ValueError, KeyError) as error:
        info = {"url": "", "last_error_message": str(error)}
    status, body = fetch_root()
    found = problems(info, status, body.strip(), datetime.date.today(),
                     datetime.datetime.now().timestamp())
    print("Адрес бота:", status, body.strip()[:80])
    if not found:
        print("Неполадок нет")
        return 0
    text = "Проверка бота PlanetX:\n\n" + "\n".join(
        "• " + line for line in found)
    print(text)
    telegram(token, "sendMessage", chat_id=owner, text=text,
             disable_web_page_preview=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
