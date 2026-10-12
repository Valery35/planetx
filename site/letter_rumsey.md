Кому: David Rumsey, carto@davidrumsey.com
Копия: rumsey@luna-img.com
Тема: PlanetX - old maps by year on a 3D globe in QGIS

Dear David,

This is Valery Hronusov (Valery35 on GitHub). We were in contact years
ago on the Google Earth Community forum, back in the Keyhole days. I
develop PlanetX, a free 3D globe plugin for QGIS under the
GPL 3 licence: https://github.com/Valery35/planetx

Version 0.66.0 adds old maps with time:
https://github.com/Valery35/planetx/releases/tag/v0.66.0

A georeferenced map gets a year. Maps of one group replace each other
on the time slider of the globe. The globe shows the last map not
later than the slider moment. The slider steps go from one map year to
the next. A swipe compares the maps of two years in one view.

A map can come in three forms:
- a raster in the QGIS project, for example a GeoTIFF exported from
  your georeferencer;
- XYZ tiles in the QGIS project;
- an image on the ground with a KML TimeStamp, the same form Google
  Earth reads.

The demo of the release uses five public domain maps of Moscow from
1813 to 1935 from Wikimedia Commons, as tiles of Wikimaps Warper.

I looked at your collection for the demo. The georeferenced tiles and
GeoTIFF files require a sign-in, and the images are under CC BY-NC-SA,
so the demo does not include them. A user with access can add your
maps to a QGIS project and give them years, and the globe will show
them on the time slider.

Google stopped active development of Google Earth Pro. PlanetX
continues that line of work inside QGIS. As the author, I can add
functions for showing history on maps, and I would welcome your ideas
and wishes.

Two questions:
1. Is there a public XYZ or WMTS address for georeferenced maps of
   your collection that a free plugin may use with attribution?
2. What functions would you want for showing the history of places
   with your maps?

Screenshots of the swipe and the time slider are attached.

Valery Hronusov (Valery35)
PlanetX, Inform++ LLC
https://github.com/Valery35/planetx
