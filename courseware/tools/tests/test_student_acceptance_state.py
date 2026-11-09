from email.message import Message
import json
from pathlib import Path
import tempfile
import unittest

from courseware.tools.student_acceptance_state import ACCESS, COOKIE_NAMES, ensure_state


class StudentAcceptanceStateTests(unittest.TestCase):
    def test_unlocks_once_and_reuses_the_verified_fixture(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = self.fixture(directory, access_expires=900)
            calls = []

            def request(route, method, cookie, body=None):
                calls.append((route, method))
                headers = Message()
                if route == "/api/auth/unlock":
                    self.assertIn("mira_student_device=fixture", cookie)
                    self.assertEqual(body, {"pin": "0000"})
                    headers.add_header("Set-Cookie", f"{ACCESS}=updated; Path=/; Max-Age=900; HttpOnly; SameSite=Lax")
                    return 200, headers, {}
                self.assertIn(f"{ACCESS}=updated", cookie)
                return 200, headers, {"student": {"childId": "fixture", "gradeCode": "primary_1"}}

            self.assertEqual(ensure_state(directory, request=request, clock=lambda: 1000)["mode"], "unlocked")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(ensure_state(directory, request=request, clock=lambda: 1000)["mode"], "existing")
            self.assertEqual(calls, [("/api/auth/unlock", "POST"), ("/api/auth/me", "GET"), ("/api/auth/me", "GET")])

    def test_different_identity_does_not_replace_the_existing_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            path = self.fixture(directory, access_expires=1900)
            previous = path.read_bytes()

            def request(route, method, cookie):
                return 200, Message(), {"student": {"childId": "different", "gradeCode": "primary_1"}}

            with self.assertRaisesRegex(ValueError, "identity mismatch"):
                ensure_state(directory, request=request, clock=lambda: 1000)
            self.assertEqual(path.read_bytes(), previous)

    def fixture(self, directory, access_expires):
        path = directory / "courseware-acceptance.storage.json"
        cookies = [{"name": name, "value": "fixture", "domain": "localhost", "path": "/",
                    "expires": access_expires if name == ACCESS else 3000} for name in sorted(COOKIE_NAMES)]
        path.write_text(json.dumps({"cookies": cookies, "origins": []}))
        demo = directory / "pictures.json"
        demo.write_text(json.dumps({"childId": "fixture", "pin": "0000"}))
        for file in (path, demo):
            file.chmod(0o600)
        return path
