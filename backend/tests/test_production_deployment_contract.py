from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class ProductionDeploymentContractTest(unittest.TestCase):
    def test_backend_entrypoint_is_single_worker_and_threaded(self) -> None:
        requirements = (REPOSITORY_ROOT / "backend" / "requirements.txt").read_text(
            encoding="utf-8"
        )
        self.assertIn("gunicorn==", requirements)

        script_path = REPOSITORY_ROOT / "backend" / "scripts" / "start-prod.sh"
        script = script_path.read_text(encoding="utf-8")
        self.assertTrue(script_path.stat().st_mode & stat.S_IXUSR)
        self.assertIn('export APP_ENV="production"', script)
        self.assertIn("--workers 1", script)
        self.assertIn("--worker-class gthread", script)
        self.assertIn('BIND_ADDRESS="${MIRA_BACKEND_BIND:-127.0.0.1:8000}"', script)
        self.assertIn('"127.0.0.1:8000"|"0.0.0.0:8000"', script)
        self.assertIn('--bind "${BIND_ADDRESS}"', script)
        self.assertNotIn("GUNICORN_WORKERS", script)
        subprocess.run(["bash", "-n", str(script_path)], check=True)

    def test_backend_image_excludes_secrets_and_joins_private_runtime_network(
        self,
    ) -> None:
        dockerfile = (REPOSITORY_ROOT / "backend" / "Dockerfile").read_text(
            encoding="utf-8"
        )
        self.assertIn('CMD ["./scripts/start-prod.sh"]', dockerfile)
        self.assertIn("USER mira", dockerfile)

        dockerignore = (REPOSITORY_ROOT / "backend" / ".dockerignore").read_text(
            encoding="utf-8"
        )
        for ignored in (".env", ".env.*", "!.env.example", "data/", ".git"):
            self.assertIn(ignored, dockerignore)

        compose = (
            REPOSITORY_ROOT / "openmaic-runtime" / "docker-compose.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("  backend:", compose)
        self.assertIn("context: ../backend", compose)
        self.assertIn(
            "${MIRA_BACKEND_ENV_FILE:?MIRA_BACKEND_ENV_FILE must point to a production env file}",
            compose,
        )
        self.assertIn("MIRA_BACKEND_BIND: 0.0.0.0:8000", compose)
        self.assertIn(
            "OPENMAIC_FULL_RUNTIME_INTERNAL_URL: http://openmaic:3000", compose
        )
        self.assertIn(
            "OPENMAIC_FULL_RUNTIME_PUBLIC_URL: ${MIRA_RUNTIME_PUBLIC_ORIGIN:?MIRA_RUNTIME_PUBLIC_ORIGIN must be an HTTPS origin}",
            compose,
        )
        self.assertIn(
            "INTERNAL_API_TOKEN: ${MIRA_INTERNAL_API_TOKEN:?MIRA_INTERNAL_API_TOKEN is required}",
            compose,
        )
        self.assertIn(
            '"127.0.0.1:${MIRA_BACKEND_PORT:-8000}:8000"', compose
        )
        self.assertIn("MIRA_BACKEND_INTERNAL_URL: http://backend:8000", compose)
        self.assertNotIn("host.docker.internal", compose)
        self.assertIn("backend-learning-media:/app/data/learning-media", compose)

    def test_caddy_edge_exposes_only_student_gateway_and_backend(self) -> None:
        caddy = (REPOSITORY_ROOT / "deploy" / "Caddyfile").read_text(
            encoding="utf-8"
        )
        self.assertIn("{$MIRA_STUDENT_ORIGIN}", caddy)
        self.assertIn("{$MIRA_CLASSROOM_ORIGIN}", caddy)
        self.assertIn("{$MIRA_API_ORIGIN}", caddy)
        self.assertIn("reverse_proxy 127.0.0.1:3000", caddy)
        self.assertIn("reverse_proxy 127.0.0.1:3101", caddy)
        self.assertIn("reverse_proxy 127.0.0.1:8000", caddy)
        self.assertNotIn("3100", caddy)

        lan_caddy = (REPOSITORY_ROOT / "deploy" / "Caddyfile.lan").read_text(
            encoding="utf-8"
        )
        self.assertEqual(lan_caddy.count("tls internal"), 3)
        self.assertNotIn("3100", lan_caddy)

    def test_runtime_ports_require_the_tls_edge(self) -> None:
        compose = (
            REPOSITORY_ROOT / "openmaic-runtime" / "docker-compose.yml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            '"127.0.0.1:${OPENMAIC_ADMIN_PORT:-3100}:3000"', compose
        )
        self.assertIn(
            '"127.0.0.1:${MIRA_RUNTIME_PORT:-3101}:3101"', compose
        )
        self.assertIn(
            "ALLOWED_FRAME_ANCESTORS: ${MIRA_STUDENT_WEB_ORIGIN:?MIRA_STUDENT_WEB_ORIGIN must be an HTTPS origin}",
            compose,
        )
        self.assertIn(
            "MIRA_RUNTIME_PUBLIC_ORIGIN: ${MIRA_RUNTIME_PUBLIC_ORIGIN:?MIRA_RUNTIME_PUBLIC_ORIGIN must be an HTTPS origin}",
            compose,
        )
        self.assertIn(
            "MIRA_STUDENT_WEB_ORIGIN: ${MIRA_STUDENT_WEB_ORIGIN:?MIRA_STUDENT_WEB_ORIGIN must be an HTTPS origin}",
            compose,
        )

    def test_production_origin_validator_requires_https_root_origins(self) -> None:
        validator = REPOSITORY_ROOT / "deploy" / "validate_production_origins.py"
        valid_env = {
            **os.environ,
            "MIRA_STUDENT_ORIGIN": "https://learn.example.com",
            "MIRA_CLASSROOM_ORIGIN": "https://classroom.example.com",
            "MIRA_API_ORIGIN": "https://api.example.com",
            "MIRA_STUDENT_WEB_ORIGIN": "https://learn.example.com",
            "MIRA_RUNTIME_PUBLIC_ORIGIN": "https://classroom.example.com",
        }
        valid = subprocess.run(
            [sys.executable, str(validator)],
            env=valid_env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(valid.returncode, 0, valid.stderr)

        for name, value in (
            ("MIRA_STUDENT_WEB_ORIGIN", "http://learn.example.com"),
            ("MIRA_API_ORIGIN", "https://api.example.com/v1"),
            ("MIRA_RUNTIME_PUBLIC_ORIGIN", "https://other.example.com"),
        ):
            with self.subTest(name=name, value=value):
                invalid = subprocess.run(
                    [sys.executable, str(validator)],
                    env={**valid_env, name: value},
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(invalid.returncode, 2)
                self.assertIn(name, invalid.stderr)

    def test_runbook_documents_secure_lan_microphone_requirements(self) -> None:
        runbook = (
            REPOSITORY_ROOT
            / "docs"
            / "runbooks"
            / "production-service-entrypoints.md"
        ).read_text(encoding="utf-8")
        for required in (
            "npm run build",
            "npm run start",
            "docker compose up --build",
            "backend/scripts/start-prod.sh",
            "MIRA_STUDENT_WEB_PUBLIC_URL",
            "OPENMAIC_FULL_RUNTIME_PUBLIC_URL",
            "Secure Context",
            "tls internal",
            "受信",
            "127.0.0.1:3100",
            "validate_production_origins.py",
            "http://backend:8000",
        ):
            self.assertIn(required, runbook)


if __name__ == "__main__":
    unittest.main()
