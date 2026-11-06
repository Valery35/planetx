# Письмо adsb.lol о лицензии выдачи API

Кому: info@adsb.lol
Тема: Licence of the api.adsb.lol output for an open-source QGIS plugin

---

Hello,

We develop PlanetX, a free open-source 3D globe plugin for QGIS
(GPL-3.0, https://github.com/Valery35/planetx). We would like to show
live aircraft from api.adsb.lol on the globe: the plugin asks
/v2/point/{lat}/{lon}/{radius} for the area in view, no more than once
every 10 seconds per user, and draws the aircraft with their callsign,
type, altitude and speed. The data is not stored or passed on.

Your privacy and licence page puts the data sent by feeders under CC0.
We did not find the terms for the API output itself. Could you tell us:

1. Under which licence or terms the output of api.adsb.lol may be used
   in third-party software, including by users who work commercially.
2. How you would like the source to be credited on the map.
3. Whether the API key you plan to introduce will be required for such
   use, and how a plugin should identify itself in its requests.

The plugin sends a User-Agent of the form
"PlanetX/1.3 (+https://github.com/Valery35/planetx)".

Thank you.

Valery
PlanetX, Inform++ LLC
