from __future__ import annotations

import os

from flask import Flask, jsonify
from flask_cors import CORS

from core.config import AppConfig, apply_test_defaults, validate_flask_config
from routes.api.v1.ai import ai_bp
from routes.api.v1.account import account_bp
from routes.api.v1.auth import auth_bp
from routes.api.v1.camera_bridge import camera_bp
from routes.api.v1.children import children_bp
from routes.api.v1.contacts import contacts_bp
from routes.api.v1.dev import dev_bp
from routes.api.v1.devices import devices_bp
from routes.api.v1.family import family_bp
from routes.api.v1.feedback import feedback_bp
from routes.api.v1.firmware import firmware_bp
from routes.api.v1.app_info import app_info_bp
from routes.api.v1.legal import legal_bp
from routes.api.v1.points import points_bp
from routes.api.v1.profile import profile_bp
from routes.api.v1.reports import growth_bp, reports_bp
from routes.api.v1.rewards import rewards_bp
from routes.api.v1.settings import settings_bp
from routes.api.v1.setup import setup_bp
from routes.api.v1.subscription import subscription_bp, subscriptions_bp
from routes.api.v1.tasks import tasks_bp
from services.task_event_stream import start_task_event_stream
from services.task_scheduler_runner import start_task_scheduler


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.update(AppConfig.from_env().to_flask_config())
    if test_config:
        app.config.update(apply_test_defaults(test_config))

    validate_flask_config(app.config)
    CORS(app, origins=app.config["CORS_ORIGINS"])

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(setup_bp, url_prefix="/api/setup")
    app.register_blueprint(profile_bp, url_prefix="/api/profile")
    app.register_blueprint(account_bp, url_prefix="/api/account")
    app.register_blueprint(family_bp, url_prefix="/api/family")
    app.register_blueprint(children_bp, url_prefix="/api/children")
    app.register_blueprint(contacts_bp, url_prefix="/api/contacts")
    app.register_blueprint(devices_bp, url_prefix="/api/devices")
    app.register_blueprint(tasks_bp, url_prefix="/api/tasks")
    app.register_blueprint(points_bp, url_prefix="/api/points")
    app.register_blueprint(rewards_bp, url_prefix="/api/rewards")
    app.register_blueprint(settings_bp, url_prefix="/api/settings")
    app.register_blueprint(legal_bp, url_prefix="/api/legal")
    app.register_blueprint(app_info_bp, url_prefix="/api/app")
    app.register_blueprint(reports_bp, url_prefix="/api/reports")
    app.register_blueprint(growth_bp, url_prefix="/api/growth")
    app.register_blueprint(subscription_bp, url_prefix="/api/subscription")
    app.register_blueprint(subscriptions_bp, url_prefix="/api/subscriptions")
    app.register_blueprint(feedback_bp, url_prefix="/api/feedback")
    app.register_blueprint(firmware_bp, url_prefix="/api/firmware")
    app.register_blueprint(camera_bp, url_prefix="/api/camera")
    app.register_blueprint(dev_bp, url_prefix="/api/dev")
    app.register_blueprint(ai_bp, url_prefix="/api/ai")

    @app.get("/api/health")
    def health():
        return jsonify(
            {
                "ok": True,
                "service": app.config["SERVICE_NAME"],
                "auth": "ready",
                "apiVersion": "v1",
                "environment": app.config["APP_ENV"],
                "cameraBridge": {
                    "adapter": app.config["CAMERA_RUNTIME_PROVIDER"],
                    "configured": bool(app.config["AI_CAMERA_TEST_BASE_URL"]),
                },
            }
        )

    start_task_event_stream(app)
    start_task_scheduler(app)

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("APP_PORT", os.getenv("PORT", app.config["PORT"])))
    app.run(host=app.config["HOST"], port=port, debug=app.config["DEBUG"])
