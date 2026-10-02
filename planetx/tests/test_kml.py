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


TIMED = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"
     xmlns:gx="http://www.google.com/kml/ext/2.2">
<Document>
  <Style id="hike"><IconStyle><color>ff00ff00</color><Icon>
    <href>http://maps.google.com/mapfiles/kml/shapes/hiker.png</href>
  </Icon></IconStyle></Style>
  <Placemark><name>Поход</name><styleUrl>#hike</styleUrl>
    <TimeStamp><when>2026-09-30</when></TimeStamp>
    <LookAt><gx:TimeSpan><begin>2026-09-01</begin><end>2026-09-30</end>
      </gx:TimeSpan><longitude>56.2</longitude><latitude>58.0</latitude>
      <range>900</range></LookAt>
    <Point><coordinates>56.2,58.0</coordinates></Point></Placemark>
  <Folder><name>Лето</name>
    <TimeSpan><begin>2026-06</begin><end>2026-08</end></TimeSpan>
    <Placemark><name>Кнопка</name><Style><IconStyle><Icon>
      <href>http://maps.google.com/mapfiles/kml/pushpin/red-pushpin.png</href>
      </Icon></IconStyle></Style>
      <Point><coordinates>56.3,58.1</coordinates></Point></Placemark>
    <Placemark><name>Своё</name>
      <TimeStamp><when>2026-07-15T10:00:00Z</when></TimeStamp>
      <Style><IconStyle><Icon><href>http://example.com/x.png</href>
      </Icon></IconStyle></Style>
      <Point><coordinates>56.4,58.2</coordinates></Point></Placemark>
  </Folder>
</Document>
</kml>""".encode("utf-8")


class TestIconsAndTime(unittest.TestCase):

    def setUp(self):
        self.tree = kml.read_kml(TIMED)
        self.places = {p.name: p for p in self.tree.places()}

    def test_icons(self):
        self.assertEqual(self.places["Поход"].icon, "hiker")
        self.assertEqual(self.places["Поход"].color, (0, 255, 0, 255))
        self.assertEqual(self.places["Кнопка"].icon, "pushpin")
        self.assertEqual(self.places["Своё"].icon, "dot")

    def test_times(self):
        hike = self.places["Поход"]
        self.assertEqual(hike.time, ("2026-09-30", "2026-09-30"))
        self.assertEqual(hike.view_time, ("2026-09-01", "2026-09-30"))
        # Время папки достаётся метке без своего времени.
        self.assertEqual(self.places["Кнопка"].time, ("2026-06", "2026-08"))
        self.assertEqual(self.places["Своё"].time,
                         ("2026-07-15T10:00:00Z", "2026-07-15T10:00:00Z"))

    def test_round_trip(self):
        again = kml.read_kml(kml.write_kml(self.tree).encode("utf-8"))
        places = {p.name: p for p in again.places()}
        for name, place in self.places.items():
            self.assertEqual(places[name].icon, place.icon, name)
            self.assertEqual(places[name].time, place.time, name)
            self.assertEqual(places[name].view_time, place.view_time, name)

class TestTour(unittest.TestCase):
    """Записанный тур как gx:Tour туда и обратно, gx:Wait держит позу."""

    def test_round_trip(self):
        samples = [(0.0, 58.0, 56.0, 3000.0, 10.0, 30.0),
                   (1.5, 58.01, 56.02, 2500.0, 20.0, 45.0),
                   (4.0, 58.02, 56.03, 2000.0, 30.0, 60.0)]
        root = kml.KFolder("Туры", children=[kml.KPlace(
            "Облёт", "line", [(s[1], s[2]) for s in samples],
            tour=samples)])
        text = kml.write_kml(root)
        self.assertIn("<gx:Tour>", text)
        back = kml.read_kml(text.encode("utf-8")).places()[0]
        self.assertEqual(back.name, "Облёт")
        for got, want in zip(back.tour, samples):
            for a, b in zip(got, want):
                self.assertAlmostEqual(a, b, places=2)

    def test_wait(self):
        data = """<kml xmlns="http://www.opengis.net/kml/2.2"
          xmlns:gx="http://www.google.com/kml/ext/2.2"><Document>
          <gx:Tour><name>Ждать</name><gx:Playlist>
            <gx:FlyTo><gx:duration>2</gx:duration><LookAt>
              <longitude>56</longitude><latitude>58</latitude>
              <range>1000</range></LookAt></gx:FlyTo>
            <gx:Wait><gx:duration>3</gx:duration></gx:Wait>
            <gx:FlyTo><gx:duration>1</gx:duration><Camera>
              <longitude>57</longitude><latitude>59</latitude>
              </Camera></gx:FlyTo>
          </gx:Playlist></gx:Tour></Document></kml>""".encode("utf-8")
        tour = kml.read_kml(data).places()[0].tour
        self.assertEqual([s[0] for s in tour], [2.0, 5.0])
        self.assertEqual(tour[0][1:], tour[1][1:])


class TestSpace(unittest.TestCase):
    """3D-путь и 3D-многоугольник - altitudeMode absolute с высотой
    у каждой вершины, отрезки не садятся на рельеф."""

    def test_round_trip(self):
        path = kml.KPlace("Крыши", "line", [(58.0, 56.0), (58.001, 56.002)],
                          alts=(152.5, 187.25))
        roof = kml.KPlace("Скат", "polygon",
                          [(58.0, 56.0), (58.0, 56.001), (58.001, 56.001)],
                          alts=(140.0, 140.0, 151.5))
        text = kml.write_kml(kml.KFolder("3D", children=[path, roof]))
        self.assertIn("<altitudeMode>absolute</altitudeMode>", text)
        self.assertNotIn("<tessellate>", text)
        back = {p.name: p for p in kml.read_kml(text.encode()).places()}
        self.assertEqual(back["Крыши"].alts, (152.5, 187.25))
        self.assertEqual(back["Скат"].alts, (140.0, 140.0, 151.5))

    def test_flat_objects_have_no_heights(self):
        line = kml.KPlace("Путь", "line", [(58.0, 56.0), (58.1, 56.1)])
        text = kml.write_kml(kml.KFolder("2D", children=[line]))
        self.assertIn("<tessellate>1</tessellate>", text)
        self.assertIsNone(kml.read_kml(text.encode()).places()[0].alts)
        # Высота есть не у каждой вершины - не 3D-объект.
        data = """<kml xmlns="http://www.opengis.net/kml/2.2"><Placemark>
          <LineString><altitudeMode>absolute</altitudeMode>
          <coordinates>56,58,100 56.1,58.1</coordinates></LineString>
          </Placemark></kml>""".encode("utf-8")
        self.assertIsNone(kml.read_kml(data).places()[0].alts)


class TestFolderProperties(unittest.TestCase):
    """Свойства папки, как в окне папки Google Earth: описание, вид,
    группа переключателей, запрет раскрытия."""

    def test_round_trip(self):
        inner = kml.KFolder("Б", radio=True,
                            children=[kml.KPlace("т", "point", [(1.0, 2.0)])])
        closed = kml.KFolder("В", expandable=False)
        top = kml.KFolder("А", children=[inner, closed],
                          description="о папке",
                          view=(58.0, 56.2, 5000.0, 30.0, 45.0))
        back = kml.read_kml(kml.write_kml(top).encode("utf-8"))
        self.assertEqual(back.description, "о папке")
        self.assertEqual(tuple(round(v, 6) for v in back.view),
                         (58.0, 56.2, 5000.0, 30.0, 45.0))
        b, c = back.children
        self.assertEqual((b.radio, b.expandable), (True, True))
        self.assertEqual((c.radio, c.expandable), (False, False))
        self.assertEqual((back.radio, back.expandable), (False, True))

    def test_list_style_by_url(self):
        data = (b'<kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
                b'<Style id="r"><ListStyle><listItemType>radioFolder'
                b'</listItemType></ListStyle></Style>'
                b'<Folder><name>x</name><styleUrl>#r</styleUrl></Folder>'
                b'<Folder><name>y</name></Folder></Document></kml>')
        x, y = kml.read_kml(data).children
        self.assertTrue(x.radio)
        self.assertFalse(y.radio)


if __name__ == "__main__":
    unittest.main()
