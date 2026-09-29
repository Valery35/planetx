# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""KML и KMZ: папки, геометрии, стили, виды, запись и чтение."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import kml  # noqa: E402

SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"
     xmlns:gx="http://www.google.com/kml/ext/2.2">
<Document>
  <name>Поездка</name>
  <Style id="red"><LineStyle><color>ff0000ff</color><width>4</width>
    </LineStyle><PolyStyle><color>7f00ff00</color></PolyStyle></Style>
  <StyleMap id="map"><Pair><key>normal</key><styleUrl>#red</styleUrl>
    </Pair><Pair><key>highlight</key><styleUrl>#none</styleUrl></Pair>
  </StyleMap>
  <Placemark><name>Пермь</name><description>город &amp; порт</description>
    <LookAt><longitude>56.23</longitude><latitude>58.01</latitude>
      <heading>30</heading><tilt>45</tilt><range>2500</range></LookAt>
    <Point><coordinates>56.2294,58.0105,0</coordinates></Point>
  </Placemark>
  <Folder><name>Маршруты</name><visibility>0</visibility>
    <Placemark><name>Путь</name><styleUrl>#map</styleUrl>
      <LineString><coordinates>
        56.0,58.0,120 56.1,58.1,130
      </coordinates></LineString></Placemark>
    <Folder><name>Участки</name>
      <Placemark><name>Поле</name><styleUrl>#red</styleUrl>
        <Polygon><outerBoundaryIs><LinearRing><coordinates>
          56,58 56.2,58 56.2,58.1 56,58
        </coordinates></LinearRing></outerBoundaryIs></Polygon>
      </Placemark>
      <Placemark><name>Двойная</name><MultiGeometry>
        <Point><coordinates>56.5,58.5</coordinates></Point>
        <LineString><coordinates>56.5,58.5 56.6,58.6</coordinates>
        </LineString></MultiGeometry></Placemark>
    </Folder>
  </Folder>
</Document>
</kml>""".encode("utf-8")


class TestRead(unittest.TestCase):

    def setUp(self):
        self.tree = kml.read_kml(SAMPLE)

    def test_document_becomes_root_with_folders(self):
        self.assertEqual(self.tree.name, "Поездка")
        names = [c.name for c in self.tree.children]
        self.assertEqual(names, ["Пермь", "Маршруты"])
        routes = self.tree.children[1]
        self.assertFalse(routes.visible)
        self.assertEqual([c.name for c in routes.children],
                         ["Путь", "Участки"])

    def test_point_with_view_and_description(self):
        perm = self.tree.children[0]
        self.assertEqual(perm.kind, "point")
        self.assertEqual(perm.points, [(58.0105, 56.2294)])
        # Точка взгляда LookAt не совпадает с меткой, как в Google Earth.
        self.assertEqual(perm.view, (58.01, 56.23, 2500.0, 30.0, 45.0))
        self.assertEqual(perm.description, "город & порт")

    def test_view_of_polygon_and_without_look_point(self):
        data = b"""<kml><Document><Placemark><name>A</name>
            <LookAt><heading>10</heading><tilt>20</tilt><range>900</range>
            </LookAt><Polygon><outerBoundaryIs><LinearRing><coordinates>
            56,58 56.2,58 56.2,58.1 56,58</coordinates></LinearRing>
            </outerBoundaryIs></Polygon></Placemark></Document></kml>"""
        field = kml.read_kml(data).children[0]
        # Без точки взгляда ею становится первая вершина метки.
        self.assertEqual(field.view, (58.0, 56.0, 900.0, 10.0, 20.0))

    def test_style_through_stylemap(self):
        path = self.tree.children[1].children[0]
        self.assertEqual(path.kind, "line")
        self.assertEqual(path.color, (255, 0, 0, 255))  # ff0000ff - красный
        self.assertEqual(path.width, 4.0)
        self.assertEqual(path.points, [(58.0, 56.0), (58.1, 56.1)])

    def test_polygon_ring_and_fill(self):
        field = self.tree.children[1].children[1].children[0]
        self.assertEqual(field.kind, "polygon")
        self.assertEqual(len(field.points), 3)  # замыкающая точка снята
        self.assertEqual(field.fill, (0, 255, 0, 127))

    def test_multigeometry_splits(self):
        parts = self.tree.children[1].children[1].children[1:]
        self.assertEqual([(p.name, p.kind) for p in parts],
                         [("Двойная", "point"), ("Двойная", "line")])
        self.assertEqual(len(self.tree.places()), 5)

    def test_root_name_from_document_then_file(self):
        self.assertEqual(kml.read_kml(SAMPLE, "файл").name, "Поездка")
        bare = b'<kml><Document><Placemark><Point><coordinates>1,2' \
            b'</coordinates></Point></Placemark></Document></kml>'
        self.assertEqual(kml.read_kml(bare, "файл").name, "файл")

    def test_bad_input(self):
        for data in (b"not xml", b"<html/>", b"PK\x03\x04broken"):
            with self.assertRaises(kml.KmlError):
                kml.read_file(data)

    def test_entities_are_refused(self):
        bomb = b"""<?xml version="1.0"?><!DOCTYPE kml [
            <!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;">]>
            <kml><Document><name>&b;</name></Document></kml>"""
        with self.assertRaises(kml.KmlError):
            kml.read_kml(bomb)


class TestWrite(unittest.TestCase):

    def test_round_trip_kml_and_kmz(self):
        tree = kml.read_kml(SAMPLE)
        for data in (kml.write_kml(tree).encode("utf-8"),
                     kml.write_kmz(tree)):
            again = kml.read_file(data, "Поездка")
            self.assertEqual(len(again.places()), 5)
            perm = again.children[0]
            self.assertEqual(perm.view, (58.01, 56.23, 2500.0, 30.0, 45.0))
            self.assertAlmostEqual(perm.points[0][0], 58.0105)
            self.assertEqual(perm.description, "город & порт")
            path = again.children[1].children[0]
            self.assertEqual(path.color, (255, 0, 0, 255))
            self.assertFalse(again.children[1].visible)

    def test_height_and_extrude(self):
        data = b"""<kml><Document><Placemark><name>Wall</name><LineString>
            <extrude>1</extrude><altitudeMode>relativeToGround</altitudeMode>
            <coordinates>56,58,120 56.1,58.1,120</coordinates></LineString>
            </Placemark><Placemark><name>Sea</name><Point>
            <altitudeMode>absolute</altitudeMode>
            <coordinates>56,58,300</coordinates></Point></Placemark>
            </Document></kml>"""
        wall, sea = kml.read_kml(data).children
        self.assertEqual((wall.height, wall.extrude), (120.0, True))
        # absolute - от уровня моря, рельефа нет, метка на земле.
        self.assertEqual((sea.height, sea.extrude), (0.0, False))
        again = kml.read_kml(kml.write_kml(kml.KFolder("x", True, [wall]))
                             .encode("utf-8")).children[0]
        self.assertEqual((again.height, again.extrude), (120.0, True))

    def test_colors(self):
        self.assertEqual(kml.color_kml((255, 128, 0, 200)), "c80080ff")
        self.assertEqual(kml.kml_color("c80080ff", None), (255, 128, 0, 200))
        self.assertIsNone(kml.kml_color("zz", None))


if __name__ == "__main__":
    unittest.main()
