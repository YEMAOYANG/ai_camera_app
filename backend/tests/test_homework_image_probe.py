from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from PIL import Image

from scripts import serve_homework_probe_images as probe


class HomeworkImageProbeTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.first = self.jpeg("one.jpg", color="white")
        self.second = self.jpeg("two.jpg", color="black")

    def jpeg(self, name, *, size=(80, 100), color="white", **kwargs):
        path = self.root / name
        Image.new("RGB", size, color).save(path, "JPEG", **kwargs)
        return path

    def server(self, *, files=None, ttl_seconds=20):
        server = probe.ImageProbe(files or [self.first, self.second], self.root / "run", ttl_seconds=ttl_seconds)
        thread = threading.Thread(target=server.serve)
        thread.start()
        def close():
            server.stop()
            thread.join(2)
            self.assertFalse(thread.is_alive())
        self.addCleanup(close)
        return server, thread

    def request(self, server, path, *, method="GET", user_agent="unit-test"):
        connection = http.client.HTTPConnection("127.0.0.1", server.server.server_port, timeout=2)
        try:
            connection.request(method, path, headers={"User-Agent": user_agent})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_exact_allowlisted_bytes_head_and_private_state(self):
        server, _ = self.server()
        self.assertEqual(server.server.server_address[0], "127.0.0.1")
        self.assertLessEqual(server.server.timeout, 1)
        for index, source in enumerate((self.first, self.second)):
            status, headers, body = self.request(server, server.paths[index])
            self.assertEqual((status, body), (200, source.read_bytes()))
            self.assertEqual(headers["Content-Type"], "image/jpeg")
            self.assertEqual(headers["Cache-Control"], "private, no-store")
            status, headers, body = self.request(server, server.paths[index], method="HEAD")
            self.assertEqual((status, body), (200, b""))
            self.assertEqual(int(headers["Content-Length"]), source.stat().st_size)
            self.assertEqual(headers["ETag"], '"' + hashlib.sha256(source.read_bytes()).hexdigest() + '"')
        state = json.loads((server.folder / "state.json").read_bytes())
        self.assertEqual(state["pid"], os.getpid())
        self.assertRegex(state["images"][0]["path"], r"^/homework-probe/[0-9a-f]{64}/0\.jpg$")
        self.assertEqual(state["images"][0]["sha256"], hashlib.sha256(self.first.read_bytes()).hexdigest())
        self.assertEqual([state["images"][0][key] for key in ("width", "height")], [80, 100])
        self.assertEqual(server.folder.stat().st_mode & 0o777, 0o700)
        for name in ("state.json", "access.jsonl"):
            self.assertEqual((server.folder / name).stat().st_mode & 0o777, 0o600)

    def test_other_paths_queries_traversal_and_methods_are_rejected_without_leaks(self):
        server, _ = self.server()
        token = server.paths[0].split("/")[2]
        paths = ["/", "/state.json", server.paths[0] + "?", server.paths[0] + "?x=1",
                 server.paths[0].replace("/0.jpg", "/2.jpg"), server.paths[0].replace("/0.jpg", "/../0.jpg"),
                 server.paths[0].replace(token, "0" * 64), server.paths[0].replace("0.jpg", "%30.jpg"),
                 server.paths[0] + "/"]
        with redirect_stderr(io.StringIO()) as errors:
            for path in paths:
                status, _, body = self.request(server, path, user_agent=token + "x" * 1000)
                self.assertIn(status, (400, 404))
                self.assertEqual(body, b"")
            for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE", "CONNECT", "CUSTOM"):
                status, headers, body = self.request(server, server.paths[0], method=method)
                self.assertEqual((status, body), (405, b""))
                self.assertEqual(headers["Allow"], "GET, HEAD")
        events = (server.folder / "access.jsonl").read_text()
        self.assertNotIn(token, events + errors.getvalue())
        self.assertNotIn("127.0.0.1", events + errors.getvalue())
        self.assertNotIn("?x=1", events)
        for row in map(json.loads, events.splitlines()):
            self.assertEqual(set(row), {"pageIndex", "status", "method", "elapsedSeconds", "userAgentLength"})
            self.assertLessEqual(row["userAgentLength"], 128)

    def test_frozen_images_do_not_follow_file_edits_or_deletion(self):
        expected = self.first.read_bytes()
        server, _ = self.server()
        self.first.write_bytes(b"changed")
        self.second.unlink()
        self.assertEqual(self.request(server, server.paths[0])[2], expected)
        self.assertEqual(hashlib.sha256(self.request(server, server.paths[0])[2]).hexdigest(), server.images[0].sha256)
        self.assertEqual(self.request(server, server.paths[1])[0], 200)

    def test_expired_requests_are_rejected_and_server_stops_automatically(self):
        server, thread = self.server(ttl_seconds=1)
        started = time.monotonic()
        thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertLess(time.monotonic() - started, 2)
        self.assertEqual(json.loads((server.folder / "state.json").read_bytes())["status"], "expired")
        with self.assertRaises(OSError):
            self.request(server, server.paths[0])

    def test_deadline_checked_at_request_time(self):
        server = probe.ImageProbe([self.first], self.root / "run")
        self.addCleanup(server.close)
        with patch.object(server, "expired", return_value=True):
            thread = threading.Thread(target=server.server.handle_request)
            thread.start()
            try:
                self.assertEqual(self.request(server, server.paths[0])[0], 410)
            finally:
                thread.join(2)
            self.assertFalse(thread.is_alive())

    def test_slow_partial_headers_cannot_extend_expiry(self):
        server, thread = self.server(ttl_seconds=1)
        with socket.create_connection(("127.0.0.1", server.server.server_port), timeout=2) as connection:
            connection.sendall(b"GET /")
            until = time.monotonic() + 2
            while thread.is_alive() and time.monotonic() < until:
                try:
                    connection.sendall(b"x")
                except OSError:
                    break
                time.sleep(0.1)
            thread.join(0.5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(json.loads((server.folder / "state.json").read_bytes())["status"], "expired")

    def test_bad_jpeg_dimensions_oversize_and_metadata_are_rejected(self):
        bad = self.root / "bad.jpg"
        bad.write_bytes(b"not jpeg")
        png = self.root / "png.jpg"
        Image.new("RGB", (20, 20)).save(png, "PNG")
        large = self.root / "large.jpg"
        large.write_bytes(b"\xff\xd8" + b"x" * probe.MAX_BYTES)
        wide = self.jpeg("wide.jpg", size=(2049, 20))
        exif = Image.Exif()
        exif[315] = "PRIVATE ARTIST"
        metadata = self.jpeg("metadata.jpg", exif=exif)
        comment = self.jpeg("comment.jpg", comment=b"PRIVATE COMMENT")
        truncated = self.root / "truncated.jpg"
        truncated.write_bytes(self.first.read_bytes()[:-2])
        for source in (bad, png, large, wide, metadata, comment, truncated):
            with self.subTest(file=source.name), self.assertRaises(probe.ProbeError):
                probe.load_image(source)
        link = self.root / "link.jpg"
        link.symlink_to(self.first)
        with self.assertRaises(OSError):
            probe.load_image(link)

    def test_output_directory_is_never_reused_or_overwritten(self):
        server = probe.ImageProbe([self.first], self.root / "run")
        server.close()
        original = (server.folder / "state.json").read_bytes()
        with self.assertRaisesRegex(probe.ProbeError, "output_directory_already_exists"):
            probe.ImageProbe([self.second], self.root / "run")
        self.assertEqual((server.folder / "state.json").read_bytes(), original)
        self.assertEqual(json.loads(original)["status"], "stopped")

    def test_bounds_and_no_configurable_public_bind(self):
        for ttl in (0, 1801, True, 1.5):
            with self.assertRaises(probe.ProbeError):
                probe.ImageProbe([self.first], self.root / "unused", ttl_seconds=ttl)
        for port in (-1, 65536, True):
            with self.assertRaises(probe.ProbeError):
                probe.ImageProbe([self.first], self.root / "unused", port=port)
        for sources in ([], [self.first] * 3):
            with self.assertRaises(probe.ProbeError):
                probe.ImageProbe(sources, self.root / "unused")
        with self.assertRaises(probe.ProbeError):
            probe.load_image("relative.jpg")
        with self.assertRaises(probe.ProbeError):
            probe.ImageProbe([self.first], "relative-output")
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            probe.main(["--image", str(self.first), "--output-dir", str(self.root / "unused"), "--host", "0.0.0.0"])

    def test_cli_expires_in_foreground_without_printing_bearer_urls(self):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(io.StringIO()):
            code = probe.main(["--image", str(self.first), "--output-dir", str(self.root / "cli"), "--ttl-seconds", "1"])
        self.assertEqual(code, 0)
        state = json.loads((self.root / "cli/state.json").read_bytes())
        token = state["images"][0]["path"].split("/")[2]
        self.assertNotIn(token, output.getvalue())
        self.assertNotIn("http://", output.getvalue())
        self.assertEqual([json.loads(line)["status"] for line in output.getvalue().splitlines()], ["serving", "expired"])

    def test_interrupt_closes_listener_and_preserves_files(self):
        output = io.StringIO()
        with patch.object(probe.ImageProbe, "serve", side_effect=KeyboardInterrupt), redirect_stdout(output):
            code = probe.main(["--image", str(self.first), "--output-dir", str(self.root / "interrupted")])
        self.assertEqual(code, 0)
        state = json.loads((self.root / "interrupted/state.json").read_bytes())
        self.assertEqual(state["status"], "stopped")
        self.assertTrue(self.first.is_file())
        self.assertTrue((self.root / "interrupted/access.jsonl").is_file())
        with socket.socket() as connection:
            self.assertNotEqual(connection.connect_ex(("127.0.0.1", int(state["localBaseUrl"].rsplit(":", 1)[1]))), 0)


if __name__ == "__main__":
    unittest.main()
