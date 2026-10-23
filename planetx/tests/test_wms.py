# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Подложка из службы WMS: разбор GetCapabilities, адрес GetMap,
тайл района поверх подложки."""
import os
import sys
import unittest

import numpy as np

CORE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core")
sys.path.insert(0, CORE)

import basemap  # noqa: E402
import wms  # noqa: E402

BASE = ("https://imagery.pasda.psu.edu/arcgis/services/pasda/DVRPC2020/"
        "MapServer/WMSServer")

# Разметка службы ArcGIS PASDA DVRPC 2020 от 23 октября 2026 года,
# сокращена: группа без имени и именованные слои в ней.
PASDA = b"""<?xml version="1.0" encoding="UTF-8"?>
<WMS_Capabilities version="1.3.0" xmlns="http://www.opengis.net/wms"
 xmlns:xlink="http://www.w3.org/1999/xlink">
<Service><Name><![CDATA[WMS]]></Name>
<Title><![CDATA[pasda_DVRPC2020]]></Title></Service>
<Capability><Request><GetMap>
<Format>image/bmp</Format><Format>image/jpeg</Format>
<Format>image/png</Format></GetMap></Request>
<Layer><Title><![CDATA[DVRPC2020]]></Title>
<CRS>CRS:84</CRS><CRS>EPSG:4326</CRS><CRS>EPSG:6347</CRS>
<EX_GeographicBoundingBox><westBoundLongitude>-76.151356</westBoundLongitude>
<eastBoundLongitude>-74.381466</eastBoundLongitude>
<southBoundLatitude>39.509339</southBoundLatitude>
<northBoundLatitude>40.608742</northBoundLatitude></EX_GeographicBoundingBox>
<Layer queryable="1"><Name>0</Name>
<Title><![CDATA[PhiladelphiaCo_PA_Nearmap_Sp20.jp2]]></Title>
<EX_GeographicBoundingBox><westBoundLongitude>-75.280979</westBoundLongitude>
<eastBoundLongitude>-74.955702</eastBoundLongitude>
<southBoundLatitude>39.866627</southBoundLatitude>
<northBoundLatitude>40.137942</northBoundLatitude></EX_GeographicBoundingBox>
</Layer>
<Layer queryable="1"><Name>1</Name>
<Title><![CDATA[MontgomeryCo_PA_Nearmap_Sp20.jp2]]></Title></Layer>
</Layer></Capability></WMS_Capabilities>"""

OLD = b"""<?xml version="1.0"?>
<WMT_MS_Capabilities version="1.1.1"><Service><Title>Old</Title></Service>
<Capability><Request><GetMap><Format>image/jpeg</Format></GetMap></Request>
<Layer><Name>world</Name><Title>World</Title><SRS>EPSG:900913</SRS>
<LatLonBoundingBox minx="-180" miny="-90" maxx="180" maxy="90"/>
<Attribution><Title>Old maps</Title></Attribution>
</Layer></Capability></WMT_MS_Capabilities>"""


class TestAddress(unittest.TestCase):

    def test_is_wms(self):
        self.assertTrue(wms.is_wms(BASE))
        self.assertTrue(wms.is_wms("https://h.org/geo?service=WMS"))
        self.assertTrue(wms.is_wms("https://h.org/ows/wms/"))
        self.assertFalse(wms.is_wms(
            "https://tile.openstreetmap.org/{z}/{x}/{y}.png"))

    def test_base_drops_own_params(self):
        self.assertEqual(
            wms.base_url(BASE + "?request=GetCapabilities&service=WMS"),
            BASE)
        self.assertEqual(
            wms.base_url("https://h.org/cgi?map=a.map&SERVICE=WMS"),
            "https://h.org/cgi?map=a.map")
        self.assertEqual(wms.capabilities_url(BASE),
                         BASE + "?SERVICE=WMS&REQUEST=GetCapabilities")


class TestParse(unittest.TestCase):

    def test_group_without_name_gives_all_layers(self):
        caps = wms.parse(PASDA)
        self.assertEqual(caps.version, "1.3.0")
        self.assertEqual(caps.title, "pasda_DVRPC2020")
        self.assertEqual([l.names for l in caps.layers],
                         [("0", "1"), ("0",), ("1",)])
        group = caps.layers[0]
        self.assertTrue(group.group)
        self.assertEqual(group.title, "DVRPC2020")
        self.assertAlmostEqual(group.box[0], -76.151356)
        # Слой без своего охвата наследует охват группы.
        self.assertAlmostEqual(caps.layers[2].box[3], 40.608742)
        self.assertAlmostEqual(caps.layers[1].box[0], -75.280979)
        self.assertIn("EPSG:6347", caps.layers[1].crs)
        self.assertEqual(wms.pick_format(caps.formats), "image/png")
        self.assertEqual(wms.mercator_code(caps.layers[1].crs), "EPSG:3857")

    def test_old_version(self):
        caps = wms.parse(OLD)
        self.assertEqual(caps.version, "1.1.1")
        layer = caps.layers[0]
        self.assertEqual(wms.mercator_code(layer.crs), "EPSG:900913")
        self.assertTrue(wms.is_world(layer.box))
        self.assertEqual(caps.attribution, "Old maps")
        self.assertEqual(wms.pick_format(caps.formats), "image/jpeg")
        url = wms.getmap_template("https://h.org/wms", "1.1.1",
                                  layer.names, "EPSG:900913", "image/jpeg")
        self.assertIn("SRS=EPSG:900913", url)

    def test_not_capabilities(self):
        with self.assertRaises(wms.WmsError):
            wms.parse(b"<html><body>no</body></html>")
        with self.assertRaises(wms.WmsError):
            wms.parse(b"<ServiceExceptionReport><ServiceException>"
                      b"bad</ServiceException></ServiceExceptionReport>")
        with self.assertRaises(wms.WmsError):
            wms.parse(b"not xml")


class TestSource(unittest.TestCase):

    def entry(self, box):
        url = wms.getmap_template(BASE, "1.3.0", ("0", "1"), "EPSG:3857",
                                  "image/png")
        return {"name": "DVRPC", "template": url, "box": box, "level": 19,
                "credit": "PASDA"}

    def test_template(self):
        url = self.entry(None)["template"]
        self.assertIn("LAYERS=0,1", url)
        self.assertIn("CRS=EPSG:3857", url)
        self.assertIn("FORMAT=image%2Fpng", url)
        self.assertTrue(url.endswith("BBOX={bbox}"))

    def test_region_over_base(self):
        caps = wms.parse(PASDA)
        source = wms.source(self.entry(caps.layers[0].box))
        # Тайл Филадельфии уровня 12 - две части, подложка первой.
        parts = source.parts(12, 1191, 1550)
        self.assertEqual(len(parts), 2)
        self.assertIn("World_Imagery", parts[0])
        self.assertIn("BBOX=", parts[1])
        self.assertNotIn("{bbox}", parts[1])
        # Тайл Перми - только подложка.
        self.assertIsNone(source.parts(12, 2687, 1197))
        self.assertIn("World_Imagery", source.tile_url(12, 2687, 1197))
        self.assertIn("PASDA; Esri", source.attribution[0])
        # Тайл много больше района - подложка, у группы с уровня 6.
        self.assertEqual(source.min_level, 6)
        self.assertIsNone(source.parts(5, 9, 12))
        self.assertIn("World_Imagery", source.tile_url(5, 9, 12))
        self.assertEqual(wms.first_level(caps.layers[1].box), 8)

    def test_world_service_has_no_base(self):
        source = wms.source(self.entry((-180, -90, 180, 90)))
        self.assertIsNone(source.parts(2, 1, 1))
        self.assertIn("BBOX=", source.tile_url(2, 1, 1))
        self.assertEqual(source.attribution[0], "PASDA")

    def test_transparent_part_shows_base(self):
        base = np.full((4, 4, 4), 100, np.uint8)
        top = np.zeros((4, 4, 4), np.uint8)
        top[0, 0] = (200, 0, 0, 255)
        out = basemap.over(base, top)
        self.assertEqual(tuple(out[0, 0]), (200, 0, 0, 255))
        self.assertEqual(tuple(out[1, 1]), (100, 100, 100, 255))

    def test_entries_round_trip(self):
        items = [self.entry((-75.3, 39.8, -74.9, 40.2)),
                 {"name": "bad", "template": "https://h.org/{z}"}]
        back = wms.entries_parse(wms.entries_text(items))
        self.assertEqual(len(back), 1)
        self.assertEqual(back[0]["box"], (-75.3, 39.8, -74.9, 40.2))
        self.assertEqual(wms.entries_parse("garbage"), [])


if __name__ == "__main__":
    unittest.main()
