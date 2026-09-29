# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Значки меток, как в Google Earth. Расчёт без Qt.

Картинки берутся из библиотеки SVG, которая входит в QGIS 3.36 и 4.
Значки Google Earth под условиями Google, копировать их нельзя. В KML
значок пишется адресом стандартного значка Google Earth той же темы,
так файл открывается в Google Earth со своим значком. Адрес из чужого
файла узнаётся по имени файла картинки. Незнакомый адрес даёт кружок.
Решение помощника от 30 сентября 2026 года, его утверждает автор.

Геодезическому пункту и карьеру точной пары в Google Earth нет, им
отданы «треугольник» и «падающие камни».
"""
import posixpath

GE_BASE = "http://maps.google.com/mapfiles/kml/"
DEFAULT = "dot"

# Номер значка, путь SVG в библиотеке QGIS и значок Google Earth.
# У кружка SVG нет, его рисует система надписей.
ICONS = (
    ("dot", None, "shapes/placemark_circle.png"),
    ("pushpin", "symbol/red-marker.svg", "pushpin/ylw-pushpin.png"),
    ("flag", "gpsicons/flag.svg", "shapes/flag.png"),
    ("info", "amenity/amenity_information.svg", "shapes/info-i.png"),
    ("camera", "gpsicons/camera.svg", "shapes/camera.png"),
    ("house", "gpsicons/house.svg", "shapes/homegardenbusiness.png"),
    ("peak", "symbol/poi_peak.svg", "shapes/mountains.png"),
    ("tree", "gpsicons/tree.svg", "shapes/parks.png"),
    ("water", "symbol/fountain.svg", "shapes/water.png"),
    ("survey", "amenity/amenity_survey_point.svg", "shapes/triangle.png"),
    ("quarry", "symbol/landuse_quary.svg", "shapes/falling_rocks.png"),
    ("hiker", "gpsicons/walker.svg", "shapes/hiker.png"),
    ("camp", "accommodation/accommodation_camping.svg",
     "shapes/campground.png"),
    ("car", "gpsicons/car.svg", "shapes/cabs.png"),
    ("bus", "transport/transport_bus_stop.svg", "shapes/bus.png"),
    ("rail", "transport/transport_train_station.svg", "shapes/rail.png"),
    ("tram", "transport/transport_tram_stop.svg", "shapes/tram.png"),
    ("airport", "transport/transport_airport.svg", "shapes/airports.png"),
    ("ship", "gpsicons/boat.svg", "shapes/ferry.png"),
    ("fuel", "transport/transport_fuel.svg", "shapes/gas_stations.png"),
    ("parking", "transport/transport_parking.svg", "shapes/parking_lot.png"),
    ("hospital", "health/health_hospital.svg", "shapes/hospitals.png"),
    ("pharmacy", "health/health_pharmacy.svg", "shapes/pharmacy_rx.png"),
    ("school", "symbol/education_school.svg", "shapes/schools.png"),
    ("church", "religion/place_of_worship_christian.svg",
     "shapes/church.png"),
    ("museum", "landmark/tourism=museum.svg", "shapes/arts.png"),
    ("hotel", "accommodation/accommodation_hotel.svg", "shapes/lodging.png"),
    ("food", "entertainment/amenity=restaurant.svg", "shapes/dining.png"),
    ("cafe", "entertainment/amenity=cafe.svg", "shapes/coffee.png"),
    ("shop", "shopping/shopping_supermarket.svg", "shapes/shopping.png"),
    ("police", "amenity/amenity_police.svg", "shapes/police.png"),
    ("fire", "amenity/amenity_firestation.svg", "shapes/firedept.png"),
    ("post", "amenity/amenity_post_office.svg", "shapes/post_office.png"),
    ("ski", "sport/sport_skiing_downhill.svg", "shapes/ski.png"),
    ("swim", "sport/sport_swimming_outdoor.svg", "shapes/swimming.png"),
)
IDS = tuple(icon for icon, _, _ in ICONS)
_SVG = {icon: svg for icon, svg, _ in ICONS}
_GE = {icon: GE_BASE + ge for icon, _, ge in ICONS}
_BY_FILE = {posixpath.basename(ge): icon for icon, _, ge in ICONS}


def svg(icon):
    """Путь SVG значка в библиотеке QGIS или None."""
    return _SVG.get(icon)


def href(icon):
    """Адрес значка Google Earth для KML."""
    return _GE.get(icon, _GE[DEFAULT])


def from_href(link):
    """Значок по адресу из KML. Кнопки любого цвета - кнопка,
    незнакомый адрес - кружок."""
    if not link:
        return DEFAULT
    name = posixpath.basename(link.strip().split("?")[0]).lower()
    if name in _BY_FILE:
        return _BY_FILE[name]
    if name.endswith("-pushpin.png"):
        return "pushpin"
    return DEFAULT


def normal(icon):
    """Известный номер значка или кружок."""
    return icon if icon in _SVG else DEFAULT
