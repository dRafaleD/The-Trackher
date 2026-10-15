import asyncio
import ctypes
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from main import build_parser
from osint.request_policy import PoliteAsyncClient
from osint.username_checker import _request_timeout
from utils.helpers import iter_files, safe_remove
from utils.safe_paths import pinned_directories
from footprint.shredder import shred_file


class SecurityBoundaryTests(unittest.TestCase):
    def test_missing_and_invalid_timeouts_keep_client_default(self):
        for value in (None, "bad", float("nan"), float("inf")):
            self.assertIs(_request_timeout({"timeout_seconds": value}), httpx.USE_CLIENT_DEFAULT)
        self.assertEqual(_request_timeout({"timeout_seconds": 20}), 20)

    @unittest.skipUnless(os.name == "nt", "Windows shell and junction behavior")
    def test_context_placeholder_stays_one_argument(self):
        import setup_context_menu
        commands = []
        class Key:
            def __enter__(self): return self
            def __exit__(self, *args): pass
        with patch("winreg.CreateKey", return_value=Key()), patch("winreg.SetValueEx"), patch(
            "winreg.SetValue", side_effect=lambda key, name, kind, value: commands.append(value)
        ):
            setup_context_menu.setup_windows_context_menu()
        command = next(value for value in commands if value.endswith(' "%1"'))
        path = r"C:\Downloads\sample --clean-all --yes"
        expanded = command.replace("%1", path)
        count = ctypes.c_int()
        parse = ctypes.windll.shell32.CommandLineToArgvW
        parse.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
        parse.restype = ctypes.POINTER(ctypes.c_wchar_p)
        args = parse(expanded, ctypes.byref(count))
        try:
            values = [args[i] for i in range(count.value)]
        finally:
            ctypes.windll.kernel32.LocalFree.argtypes = [ctypes.c_void_p]
            ctypes.windll.kernel32.LocalFree(args)
        parsed = build_parser().parse_args(values[values.index("--shred"):])
        self.assertEqual(parsed.shred, path)
        self.assertFalse(parsed.clean_all)
        self.assertFalse(parsed.yes)

    @unittest.skipUnless(os.name == "nt", "Windows junction regression")
    def test_nested_and_root_junctions_never_delete_external_files(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            target, outside = base / "selected", base / "outside"
            target.mkdir(); outside.mkdir()
            sentinel = outside / "keep.txt"
            sentinel.write_text("untouched")
            link = target / "junction"
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            try:
                self.assertEqual(list(iter_files(target)), [])
                self.assertFalse(safe_remove(link))
                self.assertFalse(safe_remove(target))
                self.assertEqual(sentinel.read_text(), "untouched")
            finally:
                if link.exists():
                    link.rmdir()

    @unittest.skipUnless(os.name == "nt", "Windows directory replacement protection")
    def test_pinned_parent_cannot_be_renamed_during_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder) / "selected"
            parent.mkdir()
            target = parent / "file"
            target.write_text("ordinary")
            with pinned_directories(target):
                with self.assertRaises(OSError):
                    parent.rename(parent.with_name("renamed"))
            self.assertTrue(shred_file(str(target), passes=1))
            self.assertFalse(target.exists())


class BoundedHttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_stall_is_cancelled_and_next_request_can_finish(self):
        async def handler(request):
            if request.url.path == "/stall":
                await asyncio.sleep(10)
            return httpx.Response(200, text="ordinary")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as raw:
            client = PoliteAsyncClient(raw, max_concurrent=1, request_deadline_seconds=0.05, origin_interval_seconds=0)
            with self.assertRaises(httpx.TimeoutException):
                await client.get("https://example.test/stall")
            self.assertEqual((await client.get("https://example.test/ok")).text, "ordinary")

    async def test_oversized_and_compressed_responses_are_rejected(self):
        for headers, body in (({}, b"x" * 100), ({"Content-Encoding": "gzip"}, b"")):
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, headers=headers, content=body))) as raw:
                client = PoliteAsyncClient(raw, max_response_bytes=16)
                with self.assertRaises(httpx.DecodingError):
                    await client.get("https://example.test/")

    async def test_redirect_body_has_the_same_budget_as_final_response(self):
        class Chunks(httpx.AsyncByteStream):
            async def __aiter__(self):
                for _ in range(10):
                    yield b"x" * 8
        def handler(request):
            if request.url.path == "/redirect":
                return httpx.Response(302, headers={"Location": "/ok"}, stream=Chunks())
            return httpx.Response(200, text="ok")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as raw:
            client = PoliteAsyncClient(raw, max_response_bytes=16)
            with self.assertRaises(httpx.DecodingError):
                await client.get("https://example.test/redirect")

    async def test_normal_redirects_keep_history_and_readable_response(self):
        def handler(request):
            if request.url.path == "/redirect":
                return httpx.Response(302, headers={"Location": "/ok"}, content=b"small")
            return httpx.Response(200, json={"ok": True})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True) as raw:
            response = await PoliteAsyncClient(raw).get("https://example.test/redirect")
            self.assertEqual(response.json(), {"ok": True})
            self.assertEqual(len(response.history), 1)
