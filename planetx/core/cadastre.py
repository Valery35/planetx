# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Кадастр Росреестра - слой земельных участков НСПД поверх снимка.

Служба - WMS Национальной системы пространственных данных (nspd.gov.ru),
она заменила публичную кадастровую карту. Проверено 13 октября 2026
года у Перми:

- без заголовка Referer с адресом карты НСПД ответ 403;
- сертификат сервера выдан «Russian Trusted Sub CA» Минцифры, корневой
  «Russian Trusted Root CA» в Windows по умолчанию не входит. Он лежит
  в модуле (CA_FILE, отпечаток SHA-1 CA_SHA1, скачан с gu-st.ru,
  страницы Госуслуг) и действует только на запросы PlanetX к HOST,
  net/loader.py;
- на частые запросы подряд служба отвечает кодом 597, поэтому запросы
  идут по одному с паузой GAP, а тайлы мельче MIN_LEVEL не просятся;
- слой 36048 - земельные участки. Номера других слоёв не подтверждены,
  список слоёв (GetCapabilities) служба не отдала.

Модуль Qt не знает.
"""

HOST = "nspd.gov.ru"
LAYER = 36048  # земельные участки
URL = ("https://nspd.gov.ru/api/aeggis/v3/{layer}/wms?SERVICE=WMS"
       "&REQUEST=GetMap&VERSION=1.3.0&LAYERS={layer}&STYLES="
       "&FORMAT=image/png&TRANSPARENT=true&CRS=EPSG:3857&BBOX={{bbox}}"
       "&WIDTH=256&HEIGHT=256").format(layer=LAYER)
REFERER = "https://nspd.gov.ru/map"
ATTRIBUTION = ("Rosreestr NSPD", "https://nspd.gov.ru/")
MIN_LEVEL = 14  # мельче участки не просятся: их тысячи в тайле
MAX_LEVEL = 18  # глубже - часть картинки уровня 18
GAP = 0.5  # с между запросами к службе
CA_FILE = "russian_trusted_root_ca.pem"
CA_SHA1 = "8FF915CCAB7BC16F8C5C8099D53E0E115B3AEC2F"
