from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, jsonify
from flask_cors import CORS

from routes.auth import auth_bp
from routes.camera_bridge import camera_bp


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(
        AUTH_DB_PATH=str(Path(__file__).resolve().parent / "data" / "mira_guardian.db"),
        AUTH_ACCESS_TOKEN_SECONDS=int(os.getenv("MIRA_AUTH_ACCESS_SECONDS", "900")),
        AUTH_REFRESH_TOKEN_SECONDS=int(
            os.getenv("MIRA_AUTH_REFRESH_SECONDS", str(60 * 60 * 24 * 30))
        ),
        AUTH_DEV_SMS_CODE=os.getenv("MIRA_AUTH_DEV_SMS_CODE", "0426"),
        CAMERA_BACKEND_URL=os.getenv("MIRA_CAMERA_BACKEND_URL", "http://127.0.0.1:8767"),
    )
    if test_config:
        app.config.update(test_config)

    CORS(app)

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(camera_bp, url_prefix="/api/camera")

    @app.get("/api/health")
    def health():
        return jsonify(
            {
                "ok": True,
                "service": "mira-guardian-app-backend",
                "auth": "ready",
                "cameraBridge": {
                    "target": app.config["CAMERA_BACKEND_URL"],
                    "mode": "proxy-to-ai-camera-test",
                },
            }
        )

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="127.0.0.1", port=port, debug=os.getenv("FLASK_DEBUG") == "1")
