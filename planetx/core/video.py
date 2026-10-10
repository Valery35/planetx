# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Запись видео MP4 H.264 через Windows Media Foundation.

Быстрый режим записи тура - сразу видео, просьба автора от 6 октября
2026 года. Qt Multimedia из QGIS 4 свои кадры не пишет: модуль Windows
Media Foundation в Qt отвечает «Failed to start recording» на
QVideoFrameInput, модуля FFmpeg для Qt в составе QGIS нет, в Qt 5 входа
своих кадров нет совсем. Поэтому кодирование идёт напрямую через
Media Foundation, встроенную часть Windows 10 и 11, вызовами COM через
ctypes, без сторонних модулей. Вне Windows видео нет, available()
отвечает False.

Вход - кадры RGB32: байты B, G, R, X строками сверху вниз, так их
отдаёт QImage формата RGB32. Стороны кадра чётные, нечётный размер
кодировщик дополнял бы полосой. Проба 6 октября 2026 года - 50 кадров
2592×1860 за 1.4 с, кадр, прочитанный обратно, совпал по ориентации
и цветам.

Модуль Qt и QGIS не знает.
"""
import ctypes
import sys
import uuid
from ctypes import (POINTER, c_long, c_longlong, c_ubyte, c_uint,
                    c_ulong, c_ulonglong, c_ushort, c_void_p, c_wchar_p)

# Указатель на переменную для параметров вызовов COM. Не byref: его
# тип PyOpenGL с Python 3.12 не узнаёт, правило test_hygiene.
ref = ctypes.pointer
BITS_PER_PIXEL = 0.25  # средний поток H.264, бит на пиксель кадра
MF_VERSION = 0x00020070
COINIT_APARTMENTTHREADED = 2


class VideoError(Exception):
    """Media Foundation недоступна или вызов вернул ошибку."""


class _GUID(ctypes.Structure):
    # DWORD - 32 бита. unsigned long на Linux 64 бита, структура выходила
    # в 24 байта, и импорт модуля падал - глобус не открывался на
    # AltLinux с QGIS 4.2, письмо пользователя 10 октября 2026 года.
    _fields_ = [("Data1", ctypes.c_uint32), ("Data2", c_ushort),
                ("Data3", c_ushort), ("Data4", c_ubyte * 8)]


def _guid(text):
    return _GUID.from_buffer_copy(uuid.UUID(text).bytes_le)


MF_MT_MAJOR_TYPE = _guid("48eba18e-f8c9-4687-bf11-0a74c9f96a8f")
MF_MT_SUBTYPE = _guid("f7e34c9a-42e8-4714-b74b-cb29d72c35e5")
MF_MT_AVG_BITRATE = _guid("20332624-fb0d-4d9e-bd0d-cbf6786c102e")
MF_MT_INTERLACE_MODE = _guid("e2724bb8-e676-4806-b4b2-a8d6efb44ccd")
MF_MT_FRAME_SIZE = _guid("1652c33d-d6b2-4012-b834-72030849a37d")
MF_MT_FRAME_RATE = _guid("c459a2e8-3d2c-4e44-b132-fee5156c7bb0")
MF_MT_PIXEL_ASPECT_RATIO = _guid("c6376a1e-8d0a-4027-be45-6d9a0ad39bb6")
MF_MT_DEFAULT_STRIDE = _guid("644b4e48-1e02-4516-b0eb-c01ca9d49ac6")
MF_MEDIATYPE_VIDEO = _guid("73646976-0000-0010-8000-00aa00389b71")
MF_VIDEOFORMAT_H264 = _guid("34363248-0000-0010-8000-00aa00389b71")
MF_VIDEOFORMAT_RGB32 = _guid("00000016-0000-0010-8000-00aa00389b71")
MF_HARDWARE_TRANSFORMS = _guid("a634a91c-822b-41b9-a494-4de4643612b0")

# Номера методов в таблицах COM (mfobjects.h, mfreadwrite.h).
RELEASE = 2
SET_UINT32 = 21
SET_UINT64 = 22
SET_GUID = 24
ADD_STREAM = 3
SET_INPUT_MEDIA_TYPE = 4
BEGIN_WRITING = 5
WRITE_SAMPLE = 6
FINALIZE = 11
SET_SAMPLE_TIME = 36
SET_SAMPLE_DURATION = 38
ADD_BUFFER = 42
LOCK = 3
UNLOCK = 4
SET_CURRENT_LENGTH = 6


def available():
    """Есть ли Media Foundation: Windows с mfplat и mfreadwrite."""
    if sys.platform != "win32":
        return False
    try:
        ctypes.WinDLL("mfplat")
        ctypes.WinDLL("mfreadwrite")
    except OSError:
        return False
    return True


def even_size(width, height):
    """Стороны кадра, округлённые вниз до чётных, не меньше 2."""
    return max(2, int(width) // 2 * 2), max(2, int(height) // 2 * 2)


def bitrate(width, height, fps):
    return int(width * height * fps * BITS_PER_PIXEL)


def _check(result, what):
    if result < 0:
        raise VideoError("{}: 0x{:08X}".format(what, result & 0xFFFFFFFF))
    return result


def _method(obj, index, *argtypes):
    """Метод index таблицы COM объекта obj."""
    table = ctypes.cast(obj, POINTER(POINTER(c_void_p)))[0]
    proto = ctypes.WINFUNCTYPE(c_long, c_void_p, *argtypes)
    function = proto(table[index])
    return lambda *args: function(obj, *args)


def _release(obj):
    if obj:
        _method(obj, RELEASE)()


class Mp4Writer:
    """Видео MP4 H.264 из кадров RGB32. write - кадр, close - конец
    файла. Размер кадра должен быть чётным (even_size)."""

    def __init__(self, path, width, height, fps=25):
        if not available():
            raise VideoError("Media Foundation")
        if width % 2 or height % 2:
            raise VideoError("odd frame size {}x{}".format(width, height))
        self.width, self.height, self.fps = width, height, fps
        self.size = width * height * 4
        self.duration = 10_000_000 // fps  # единицы 100 нс
        self.count = 0
        self._plat = ctypes.WinDLL("mfplat")
        rw = ctypes.WinDLL("mfreadwrite")
        # COM в главном потоке Qt уже есть, повтор вызова безвреден.
        ctypes.WinDLL("ole32").CoInitializeEx(None, COINIT_APARTMENTTHREADED)
        _check(self._plat.MFStartup(MF_VERSION, 0), "MFStartup")
        self._objects = []
        try:
            attrs = self._new(self._plat.MFCreateAttributes, 1)
            self._set_u32(attrs, MF_HARDWARE_TRANSFORMS, 1)
            self.writer = c_void_p()
            _check(rw.MFCreateSinkWriterFromURL(
                c_wchar_p(path), None, attrs, ref(self.writer)),
                "MFCreateSinkWriterFromURL")
            self._objects.append(self.writer)
            output = self._media_type(MF_VIDEOFORMAT_H264,
                                      bitrate(width, height, fps))
            stream = c_ulong()
            _check(_method(self.writer, ADD_STREAM, c_void_p,
                           POINTER(c_ulong))(output, ref(stream)),
                   "AddStream")
            self.stream = stream.value
            source = self._media_type(MF_VIDEOFORMAT_RGB32, None, width * 4)
            _check(_method(self.writer, SET_INPUT_MEDIA_TYPE, c_ulong,
                           c_void_p, c_void_p)(self.stream, source, None),
                   "SetInputMediaType")
            _check(_method(self.writer, BEGIN_WRITING)(), "BeginWriting")
        except VideoError:
            self._free()
            raise

    def _new(self, factory, *args):
        obj = c_void_p()
        _check(factory(ref(obj), *args), factory.__name__)
        self._objects.append(obj)
        return obj

    @staticmethod
    def _set_u32(attrs, key, value):
        _check(_method(attrs, SET_UINT32, POINTER(_GUID), c_uint)(
            ref(key), value), "SetUINT32")

    @staticmethod
    def _set_u64(attrs, key, value):
        _check(_method(attrs, SET_UINT64, POINTER(_GUID), c_ulonglong)(
            ref(key), value), "SetUINT64")

    def _media_type(self, subtype, rate=None, stride=None):
        kind = self._new(self._plat.MFCreateMediaType)
        set_guid = _method(kind, SET_GUID, POINTER(_GUID), POINTER(_GUID))
        _check(set_guid(ref(MF_MT_MAJOR_TYPE), ref(MF_MEDIATYPE_VIDEO)),
               "SetGUID")
        _check(set_guid(ref(MF_MT_SUBTYPE), ref(subtype)), "SetGUID")
        if rate:
            self._set_u32(kind, MF_MT_AVG_BITRATE, rate)
        self._set_u32(kind, MF_MT_INTERLACE_MODE, 2)  # прогрессивная
        self._set_u64(kind, MF_MT_FRAME_SIZE,
                      (self.width << 32) | self.height)
        self._set_u64(kind, MF_MT_FRAME_RATE, (self.fps << 32) | 1)
        self._set_u64(kind, MF_MT_PIXEL_ASPECT_RATIO, (1 << 32) | 1)
        if stride is not None:
            # Положительный шаг строки - кадр сверху вниз, как у QImage.
            self._set_u32(kind, MF_MT_DEFAULT_STRIDE, stride)
        return kind

    def write(self, address):
        """Кадр по адресу памяти address: width × height × 4 байта RGB32
        строками сверху вниз."""
        buffer = c_void_p()
        sample = c_void_p()
        try:
            _check(self._plat.MFCreateMemoryBuffer(self.size, ref(buffer)),
                   "MFCreateMemoryBuffer")
            data = POINTER(c_ubyte)()
            _check(_method(buffer, LOCK, POINTER(POINTER(c_ubyte)),
                           c_void_p, c_void_p)(ref(data), None, None),
                   "Lock")
            ctypes.memmove(data, address, self.size)
            _check(_method(buffer, UNLOCK)(), "Unlock")
            _check(_method(buffer, SET_CURRENT_LENGTH, c_ulong)(self.size),
                   "SetCurrentLength")
            _check(self._plat.MFCreateSample(ref(sample)), "MFCreateSample")
            _check(_method(sample, ADD_BUFFER, c_void_p)(buffer), "AddBuffer")
            _check(_method(sample, SET_SAMPLE_TIME, c_longlong)(
                self.count * self.duration), "SetSampleTime")
            _check(_method(sample, SET_SAMPLE_DURATION, c_longlong)(
                self.duration), "SetSampleDuration")
            _check(_method(self.writer, WRITE_SAMPLE, c_ulong, c_void_p)(
                self.stream, sample), "WriteSample")
        finally:
            _release(sample)
            _release(buffer)
        self.count += 1

    def close(self):
        """Дописать файл. Видео из уже записанных кадров годно и после
        прерванной записи."""
        if self.writer is None:
            return
        try:
            if self.count:
                _check(_method(self.writer, FINALIZE)(), "Finalize")
        finally:
            self._free()

    def _free(self):
        for obj in reversed(self._objects):
            _release(obj)
        self._objects = []
        self.writer = None
        self._plat.MFShutdown()
