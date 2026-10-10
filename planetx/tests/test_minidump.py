# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Стеки потоков из дампа Windows без отладчика."""
import ctypes
import os
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
import minidump  # noqa: E402


class TestAfterCall(unittest.TestCase):
    def test_call_forms(self):
        self.assertTrue(minidump.after_call(bytes([0, 0, 0xE8, 1, 2, 3, 4])))
        self.assertTrue(minidump.after_call(
            bytes([0xFF, 0x15, 1, 2, 3, 4, 5])))   # call [rip+disp32]
        self.assertTrue(minidump.after_call(
            bytes([0, 0, 0, 0, 0, 0xFF, 0xD0])))   # call rax
        self.assertTrue(minidump.after_call(
            bytes([0, 0, 0, 0, 0xFF, 0x50, 0x18])))  # call [rax+18h]

    def test_not_call(self):
        self.assertFalse(minidump.after_call(bytes(7)))
        self.assertFalse(minidump.after_call(
            bytes([0, 0, 0, 0, 0, 0xFF, 0xE0])))   # jmp rax
        self.assertFalse(minidump.after_call(b"\xe8"))


@unittest.skipUnless(os.name == "nt", "только Windows")
class TestOwnDump(unittest.TestCase):
    """Процесс пишет дамп сам себя, поток в time.sleep виден
    в ожидании ядра."""

    def test_sleeping_thread_waits(self):
        kernel = ctypes.WinDLL("kernel32")
        kernel.GetCurrentProcess.restype = ctypes.c_void_p
        help_ = ctypes.WinDLL("dbghelp")
        help_.MiniDumpWriteDump.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p,
            ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_void_p]
        import msvcrt
        sleeper = threading.Thread(target=time.sleep, args=(2,))
        sleeper.start()
        time.sleep(0.2)
        name = os.path.join(tempfile.mkdtemp(), "own.dmp")
        with open(name, "wb") as fh:
            ok = help_.MiniDumpWriteDump(
                kernel.GetCurrentProcess(), os.getpid(),
                msvcrt.get_osfhandle(fh.fileno()), 0x1020, None, None,
                None)
        self.assertTrue(ok)
        with open(name, "rb") as fh:
            dump = minidump.Dump(fh.read())
        os.remove(name)
        self.assertTrue(any(n.lower().endswith("ntdll.dll")
                            for _, _, n in dump.modules))
        stacks = minidump.stacks(dump)
        self.assertEqual(sum(1 for _, main, _ in stacks if main), 1)
        self.assertTrue(stacks[0][1])
        waits = [lines for _, _, lines in stacks
                 if any("Wait" in line for line in lines[:4])]
        self.assertTrue(waits)
        python = os.path.basename(sys.executable).lower()
        self.assertTrue(any("python" in line.lower()
                            for _, _, lines in stacks for line in lines),
                        python)
        sleeper.join()

    def test_exports_of_kernel32(self):
        path = os.path.join(os.environ["SystemRoot"], "System32",
                            "kernel32.dll")
        image = minidump.Image(path)
        names = [name for _, name in image.exports]
        self.assertIn("Sleep", names)
        rva = dict((name, rva) for rva, name in image.exports)["Sleep"]
        self.assertEqual(image.name_at(rva + 4), "Sleep+0x4")


if __name__ == "__main__":
    unittest.main()
