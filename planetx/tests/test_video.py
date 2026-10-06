# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тесты core/video.py: MP4 через Media Foundation, кадр читается
обратно с той же ориентацией и цветами. Вне Windows пропускаются."""
import ctypes
import os
import sys
import tempfile
import unittest
from ctypes import POINTER, byref, c_longlong, c_ubyte, c_ulong, c_void_p, \
    c_wchar_p

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import video  # noqa: E402

W, H = 320, 240
FIRST_VIDEO = 0xFFFFFFFC
ENABLE_PROCESSING = video._guid("fb394f3d-ccf1-42ee-bbb3-f9b845d5681d")


def frame(n):
    """Кадр RGB32: серый фон, красный квадрат вверху слева, синий внизу
    справа, полоса едет слева направо."""
    img = np.full((H, W, 4), 128, np.uint8)
    img[:40, :40, :3] = (0, 0, 255)
    img[H - 40:, W - 40:, :3] = (255, 0, 0)
    x = 40 + n * 10
    img[:, x:x + 8, :3] = 255
    return np.ascontiguousarray(img)


def read_frame(path, index):
    """Кадр index файла path как массив (H, W, 4) BGRX."""
    plat = ctypes.WinDLL("mfplat")
    rw = ctypes.WinDLL("mfreadwrite")
    video._check(plat.MFStartup(video.MF_VERSION, 0), "MFStartup")
    attrs, reader, kind = c_void_p(), c_void_p(), c_void_p()
    try:
        video._check(plat.MFCreateAttributes(byref(attrs), 1), "attrs")
        video.Mp4Writer._set_u32(attrs, ENABLE_PROCESSING, 1)
        video._check(rw.MFCreateSourceReaderFromURL(
            c_wchar_p(path), attrs, byref(reader)), "reader")
        video._check(plat.MFCreateMediaType(byref(kind)), "type")
        set_guid = video._method(kind, video.SET_GUID,
                                 POINTER(video._GUID), POINTER(video._GUID))
        set_guid(byref(video.MF_MT_MAJOR_TYPE),
                 byref(video.MF_MEDIATYPE_VIDEO))
        set_guid(byref(video.MF_MT_SUBTYPE),
                 byref(video.MF_VIDEOFORMAT_RGB32))
        video._check(video._method(reader, 7, c_ulong, c_void_p, c_void_p)(
            FIRST_VIDEO, None, kind), "SetCurrentMediaType")
        got = 0
        while True:
            actual, flags, stamp = c_ulong(), c_ulong(), c_longlong()
            sample = c_void_p()
            video._check(video._method(
                reader, 9, c_ulong, c_ulong, POINTER(c_ulong),
                POINTER(c_ulong), POINTER(c_longlong), POINTER(c_void_p))(
                FIRST_VIDEO, 0, byref(actual), byref(flags), byref(stamp),
                byref(sample)), "ReadSample")
            if flags.value & 2:
                return None
            if not sample:
                continue
            try:
                if got == index:
                    buffer = c_void_p()
                    video._check(video._method(
                        sample, 41, POINTER(c_void_p))(byref(buffer)),
                        "ConvertToContiguousBuffer")
                    data, length = POINTER(c_ubyte)(), c_ulong()
                    video._method(buffer, video.LOCK,
                                  POINTER(POINTER(c_ubyte)), c_void_p,
                                  POINTER(c_ulong))(byref(data), None,
                                                    byref(length))
                    raw = ctypes.string_at(data, length.value)
                    video._method(buffer, video.UNLOCK)()
                    video._release(buffer)
                    return np.frombuffer(raw, np.uint8)[:W * H * 4] \
                        .reshape(H, W, 4)
            finally:
                video._release(sample)
            got += 1
    finally:
        for obj in (kind, reader, attrs):
            video._release(obj)
        plat.MFShutdown()


@unittest.skipUnless(video.available(), "нет Media Foundation")
class TestMp4(unittest.TestCase):

    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "probe.mp4")

    def test_frames_round_trip(self):
        writer = video.Mp4Writer(self.path, W, H, 25)
        frames = [frame(n) for n in range(20)]
        for img in frames:
            writer.write(img.ctypes.data)
        writer.close()
        with open(self.path, "rb") as fh:
            head = fh.read(12)
        self.assertEqual(head[4:8], b"ftyp")
        back = read_frame(self.path, 10)
        self.assertIsNotNone(back)
        # Красный вверху слева, синий внизу справа: кадр не перевёрнут,
        # каналы на месте. H.264 сжимает с потерями, допуск 40.
        np.testing.assert_allclose(back[20, 20, :3], (0, 0, 255), atol=40)
        np.testing.assert_allclose(back[H - 20, W - 20, :3], (255, 0, 0),
                                   atol=40)
        # Полоса кадра 10 - на x = 140..148.
        self.assertGreater(int(back[H // 2, 144, 1]), 200)
        self.assertLess(int(back[H // 2, 120, 1]), 170)

    def test_odd_size_refused(self):
        with self.assertRaises(video.VideoError):
            video.Mp4Writer(self.path, W + 1, H, 25)

    def test_even_size(self):
        self.assertEqual(video.even_size(2593, 1861), (2592, 1860))
        self.assertEqual(video.even_size(1, 1), (2, 2))


if __name__ == "__main__":
    unittest.main()
