from __future__ import annotations

import os

from flask import Flask, jsonify
from flask_cors import CORS

from core.config import AppConfig, apply_test_defaults, validate_flask_config
from routes.api.v1.ai import ai_bp
from routes.api.v1.account import account_bp
from routes.api.v1.auth import auth_bp
from routes.api.v1.camera_bridge import camera_bp
from routes.api.v1.care import care_bp
from routes.api.v1.children import children_bp
from routes.api.v1.contacts import contacts_bp
from routes.api.v1.conversation import conversation_bp
from routes.api.v1.dev import dev_bp
from routes.api.v1.voice import voice_bp
from routes.api.v1.devices import devices_bp
from routes.api.v1.family import family_bp
from routes.api.v1.feedback import feedback_bp
from routes.api.v1.firmware import firmware_bp
from routes.api.v1.app_info import app_info_bp
from routes.api.v1.legal import legal_bp
from routes.api.v1.learning import learning_bp
from routes.api.v1.points import points_bp
from routes.api.v1.profile import profile_bp
from routes.api.v1.reports import growth_bp, reports_bp
from routes.api.v1.reminders import reminders_bp
from routes.api.v1.rewards import rewards_bp
from routes.api.v1.settings import settings_bp
from routes.api.v1.setup import setup_bp
from routes.api.v1.subscription import subscription_bp, subscriptions_bp
from routes.api.v1.tasks import tasks_bp
from routes.api.v2.parent_student_access import parent_student_access_bp
from routes.api.v2.student_auth import student_auth_bp
from routes.api.v2.student_learning import student_learning_bp
from routes.api.v2.student_learning_media import student_learning_media_bp
from routes.internal.camera_observations import internal_camera_observations_bp
from routes.internal.learning_content import internal_learning_content_bp
from routes.internal.learning_classrooms import internal_learning_classrooms_bp
from routes.internal.learning_curriculum_preparations import (
    internal_learning_curriculum_preparations_bp,
)
from routes.internal.learning_media import internal_learning_media_bp
from routes.internal.openmaic_runtime import internal_openmaic_runtime_bp
from routes.internal.voice import internal_voice_bp
from routes.internal.reminders import internal_reminders_bp
from services.task_event_stream import start_task_event_stream
from services.task_scheduler_runner import start_task_scheduler
from services.learning_daily_preparation_runner import (
    start_learning_daily_preparation,
)
from services.learning_curriculum_preparation_runner import (
    start_learning_curriculum_preparation,
)
from services.formal_learning_health import formal_learning_health_attestation
from services.learning_classroom_generation_runner import (
    start_learning_classroom_generation,
)
from services.learning_media_worker_runner import start_learning_media_worker
from services.openmaic_runtime_generation_runner import (
    start_openmaic_runtime_generation,
)


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
    app.register_blueprint(learning_bp, url_prefix="/api/learning")
    app.register_blueprint(app_info_bp, url_prefix="/api/app")
    app.register_blueprint(reports_bp, url_prefix="/api/reports")
    app.register_blueprint(growth_bp, url_prefix="/api/growth")
    app.register_blueprint(subscription_bp, url_prefix="/api/subscription")
    app.register_blueprint(subscriptions_bp, url_prefix="/api/subscriptions")
    app.register_blueprint(feedback_bp, url_prefix="/api/feedback")
    app.register_blueprint(firmware_bp, url_prefix="/api/firmware")
    app.register_blueprint(camera_bp, url_prefix="/api/camera")
    app.register_blueprint(care_bp, url_prefix="/api/care")
    app.register_blueprint(reminders_bp, url_prefix="/api/reminders")
    app.register_blueprint(dev_bp, url_prefix="/api/dev")
    app.register_blueprint(ai_bp, url_prefix="/api/ai")
    app.register_blueprint(conversation_bp, url_prefix="/api/conversation")
    app.register_blueprint(voice_bp, url_prefix="/api/voice")
    app.register_blueprint(parent_student_access_bp, url_prefix="/api/v2/parent")
    app.register_blueprint(student_auth_bp, url_prefix="/api/v2/student")
    app.register_blueprint(
        student_learning_bp,
        url_prefix="/api/v2/student/learning",
    )
    app.register_blueprint(
        student_learning_media_bp,
        url_prefix="/api/v2/student/learning",
    )
    app.register_blueprint(internal_camera_observations_bp, url_prefix="/internal/camera")
    app.register_blueprint(
        internal_learning_content_bp, url_prefix="/internal/learning/content"
    )
    app.register_blueprint(
        internal_learning_classrooms_bp,
        url_prefix="/internal/learning/classrooms",
    )
    app.register_blueprint(
        internal_learning_curriculum_preparations_bp,
        url_prefix="/internal/learning/curriculum-preparations",
    )
    app.register_blueprint(
        internal_learning_media_bp,
        url_prefix="/internal/learning/media",
    )
    app.register_blueprint(
        internal_openmaic_runtime_bp,
        url_prefix="/internal/learning/openmaic",
    )
    app.register_blueprint(internal_reminders_bp, url_prefix="/internal/reminders")
    app.register_blueprint(internal_voice_bp, url_prefix="/internal/voice")

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
                "formalLearning": formal_learning_health_attestation(app.config),
            }
        )

    process_role = str(os.getenv("MIRA_PROCESS_ROLE") or "all").strip().lower()
    if process_role not in {"all", "api", "api-passive", "curriculum-worker"}:
        raise RuntimeError(
            "MIRA_PROCESS_ROLE must be all, api, api-passive, or "
            "curriculum-worker."
        )

    # Development keeps the historical all-in-one process. Production runs
    # curriculum preparation in its own supervised process so an API restart
    # cannot interrupt a paid Provider phase and strand a dispatch lease.
    # api-passive serves the same contracts without starting any scheduler or
    # Provider-capable worker, which is useful for safe local acceptance.
    if process_role in {"all", "api"}:
        start_task_event_stream(app)
        start_task_scheduler(app)
    if process_role == "all":
        # The standalone curriculum worker owns the complete formal pipeline.
        # Legacy all-in-one runners must not compete with it in an API process.
        start_learning_daily_preparation(app)
        start_learning_classroom_generation(app)
        start_learning_media_worker(app)
    if process_role in {"all", "curriculum-worker"}:
        start_openmaic_runtime_generation(app)
    if process_role == "all":
        start_learning_curriculum_preparation(app)

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("APP_PORT", os.getenv("PORT", app.config["PORT"])))
    app.run(host=app.config["HOST"], port=port, debug=app.config["DEBUG"])
