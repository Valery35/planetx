# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Кадастр Росреестра: адрес и разбор сведений об участке."""
import json
import os
import sys
import unittest
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import cadastre  # noqa: E402

# Ответ службы 13 октября 2026 года у Перми, контур сокращён до пяти
# точек.
ANSWER = {"type": "FeatureCollection", "features": [{
    "id": 49685861, "type": "Feature",
    "geometry": {"type": "Polygon", "coordinates": [[
        [6261773.53, 7969657.97], [6261726.05, 7969634.44],
        [6261733.47, 7969477.28], [6261867.92, 7969545.83],
        [6261773.53, 7969657.97]]],
        "crs": {"type": "name", "properties": {"name": "EPSG:3857"}}},
    "properties": {
        "category": 36368, "categoryName": "Земельные участки ЕГРН",
        "label": "59:01:4410120:9",
        "options": {
            "area": None, "cad_num": "59:01:4410120:9",
            "cost_application_date": "2023-01-01",
            "cost_determination_date": "2022-01-01",
            "cost_index": 11880.86, "cost_value": 51337211.59,
            "declared_area": None,
            "land_record_category_type": "Земли населенных пунктов",
            "land_record_reg_date": "2003-05-15",
            "ownership_type": "Частная",
            "permitted_use_established_by_document":
                "Под жилой дом со встроенными помещениями",
            "quarter_cad_number": "59:01:4410120",
            "readable_address": "Пермский край, г. Пермь, Ленинский р-н, "
                                "ул. Луначарского, 34",
            "right_type": "Общая долевая собственность",
            "specified_area": 4321, "status": "Ранее учтенный"}}}]}


class TestInfo(unittest.TestCase):
    def test_url_has_format_and_point_in_middle(self):
        # Без FORMAT служба отвечает 500 «invalid request».
        query = parse_qs(urlsplit(cadastre.info_url(58.0105, 56.2502)).query)
        self.assertEqual(query["FORMAT"], ["image/png"])
        self.assertEqual(query["REQUEST"], ["GetFeatureInfo"])
        self.assertEqual(query["QUERY_LAYERS"], [str(cadastre.LAYER)])
        x0, y0, x1, y1 = (float(v) for v in query["BBOX"][0].split(","))
        x, y = cadastre.mercator(58.0105, 56.2502)
        self.assertAlmostEqual((x0 + x1) / 2, x, places=1)
        self.assertAlmostEqual((y0 + y1) / 2, y, places=1)
        # Окно - 256 м местности, в метрах Web Mercator шире на 1/cos.
        self.assertAlmostEqual(x1 - x0, 256 / 0.5299, delta=1.0)
        self.assertEqual(query["I"], ["128"])

    def test_parcel_values_and_outline(self):
        parcels = cadastre.parse_info(json.dumps(ANSWER).encode("utf-8"))
        self.assertEqual(len(parcels), 1)
        parcel = parcels[0]
        self.assertEqual(parcel["number"], "59:01:4410120:9")
        values = dict(parcel["values"])
        self.assertEqual(values["specified_area"], "4 321 м²")
        self.assertEqual(values["cost_value"], "51 337 211.59 ₽")
        self.assertEqual(values["cost_index"], "11 880.86 ₽/м²")
        self.assertNotIn("declared_area", values)
        self.assertEqual([v[0] for v in parcel["values"]][:2],
                         ["cad_num", "readable_address"])
        ring = parcel["rings"][0]
        self.assertEqual(len(ring), 4)
        # Контур - в сотне метров от точки запроса 58.0105, 56.2502.
        lat, lon = ring[0]
        self.assertAlmostEqual(lat, 58.0111, places=3)
        self.assertAlmostEqual(lon, 56.2502, places=3)

    def test_empty_and_bad_answers(self):
        self.assertEqual(cadastre.parse_info(
            {"type": "FeatureCollection", "features": []}), [])
        with self.assertRaises(ValueError):
            cadastre.parse_info(b"<ServiceExceptionReport/>")

    def test_mercator_round_trip(self):
        lat, lon = cadastre.geographic(*cadastre.mercator(58.0105, 56.2502))
        self.assertAlmostEqual(lat, 58.0105, places=9)
        self.assertAlmostEqual(lon, 56.2502, places=9)

    def test_map_link_points_at_parcel(self):
        link = cadastre.map_link(58.0105, 56.2502)
        self.assertTrue(link.startswith("https://nspd.gov.ru/map?"))
        self.assertIn("active_layers=36048", link)


if __name__ == "__main__":
    unittest.main()
