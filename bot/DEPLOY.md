# Бот PlanetX на PythonAnywhere

Бесплатный тариф PythonAnywhere даёт веб-приложение по адресу
`https://ИМЯ.pythonanywhere.com`. Telegram отправляет на него
сообщения боту, приложение отвечает. Постоянно работающих задач
у бесплатного тарифа нет, поэтому бот там принимает сообщения адресом
приёма (webhook), а не опросом. Ниже `ИМЯ` - имя учётной записи
PythonAnywhere.

## Первая установка

1. Учётная запись. На pythonanywhere.com - «Pricing & signup»,
   тариф «Beginner» (бесплатный). Имя учётной записи станет адресом.
2. Архив. На своём компьютере архив собирает
   `python bot/make_bundle.py`, он ложится в `dist/planetx-bot.zip`.
   На PythonAnywhere вкладка «Files» - «Upload a file» в папку
   `/home/ИМЯ/`.
3. Распаковка. Вкладка «Consoles» - «Bash», в консоли:

   ```
   unzip -o planetx-bot.zip
   ```

4. Токен. В той же консоли:

   ```
   mkdir -p ~/.config/PlanetX-bot
   nano ~/.config/PlanetX-bot/config.json
   ```

   В файл одной строкой - `{"token": "ТОКЕН", "owner": 227506193}`,
   сохранение - Ctrl+O, Enter, выход - Ctrl+X.
5. Веб-приложение. Вкладка «Web» - «Add a new web app» - «Next» -
   «Manual configuration» - самый новый Python. На странице приложения
   ссылка «WSGI configuration file» открывает файл, его содержимое
   заменяется тремя строками:

   ```
   import sys
   sys.path.insert(0, "/home/ИМЯ/planetx-bot/bot")
   from planetx_bot import application
   ```

   «Save», затем на вкладке «Web» - «Reload».
6. Проверка. `https://ИМЯ.pythonanywhere.com/` в браузере показывает
   «PlanetX bot».
7. Адрес приёма. Бот на своём компьютере останавливается (Ctrl+C),
   иначе он снимет адрес. В консоли Bash:

   ```
   python3 ~/planetx-bot/bot/planetx_bot.py --webhook https://ИМЯ.pythonanywhere.com
   ```

   Строка «Адрес приёма: …, ошибка: нет» - бот работает на сервере.

## Посты о выпусках

1. Бот - администратор канала с правом публиковать сообщения.
2. В файле настроек на сервере поле `"channel": "@имя_канала"`, затем
   «Reload» на вкладке «Web».
3. В хранилище модуля на GitHub - файл
   `.github/workflows/telegram-release.yml` (один и тот же для всех
   модулей) и секреты Settings - Secrets and variables - Actions:
   `TELEGRAM_BOT_TOKEN` - токен бота, `TELEGRAM_OWNER` - номер чата
   автора.

При выпуске на GitHub автору приходит сообщение с кнопкой «Подготовить
пост», по ней - черновик, «Опубликовать» ставит пост в канал. Черновик
вручную - `/post`, `/post v1.7.0`, `/post isoliner`,
`/post isoliner v1.2.0`. Название модуля и кнопка каталога QGIS -
словарь `PLUGINS` в `planetx_bot.py`, модуль без записи называется
именем хранилища и идёт без кнопки каталога.

## Обслуживание

- Раз в три месяца на вкладке «Web» нажимается «Run until 3 months
  from today», PythonAnywhere напоминает письмом. Без этого
  приложение останавливается.
- Новая версия бота или руководства - новый архив, шаги 2, 3
  и «Reload» на вкладке «Web».
- Ошибки - «Error log» и «Server log» на вкладке «Web».
- Запуск бота опросом на своём компьютере снимает адрес приёма.
  Вернуть - шаг 7.
