from __future__ import annotations

import logging
import os
import signal
import time
import uuid
from pathlib import Path

from core.database import Database
from core.security import now_ms
from repositories.device_repository import DeviceRepository
from services.camera_command_service import CameraCommandService
from services.conversation_policy_service import ConversationPolicyService
from services.conversation_sync_service import ConversationSyncService
from services.speech_gateway import SpeechGateway
from services.voice_conversation_service import VoiceConversationService
from services.voice_runtime_store import VoiceRuntimeStore
from services.voice_wake_service import match_wake_names, wake_ack_text


log = logging.getLogger("camera_voice_worker")
RUNNING = True


class CameraVoiceWorker:
    def __init__(
        self,
        *,
        database_url: str,
        family_id: str,
        device_id: str | None = None,
        mock_phrases: list[str] | None = None,
        require_confirmation: bool = True,
        poll_seconds: float = 2.0,
    ):
        self.database = Database(database_url)
        self.device_repository = DeviceRepository(self.database)
        self.family_id = family_id
        self.device_id = device_id
        self.mock_phrases = list(mock_phrases or ["小暖小暖", "小暖你好，讲个故事"])
        self.require_confirmation = require_confirmation
        self.poll_seconds = poll_seconds
        self.sync_service = ConversationSyncService(database_url)
        self.policy_service = ConversationPolicyService(database_url)
        self.conversation_service = VoiceConversationService(database_url)
        self.speech_gateway = SpeechGateway(
            asr_provider=os.getenv("SPEECH_ASR_PROVIDER", "text"),
            tts_provider=os.getenv("SPEECH_TTS_PROVIDER", "text"),
        )

    def resolve_device_id(self) -> str:
        if self.device_id:
            return self.device_id
        with self.database.transaction() as conn:
            device = self.device_repository.ensure_default_device(
                conn,
                family_id=self.family_id,
                now=now_ms(),
            )
            if device is None:
                raise RuntimeError("No default device for voice worker")
            return device["id"]

    def _heartbeat(self, *, device_id: str, profile: dict, state: str, **extra) -> None:
        snapshot = {
            "state": state,
            "wakeName": profile.get("wakeName"),
            "last_wake_match": extra.get("wake_match"),
            "last_command": extra.get("command", ""),
            "last_reply": extra.get("reply", ""),
            "last_error": extra.get("last_error", ""),
        }
        VoiceRuntimeStore.update_snapshot(
            family_id=self.family_id,
            device_id=device_id,
            snapshot=snapshot,
            running=True,
        )
        VoiceRuntimeStore.set_profile(
            family_id=self.family_id,
            device_id=device_id,
            profile=profile,
        )

    def _speak(self, *, device_id: str, text: str) -> None:
        database_url = os.getenv("DATABASE_URL") or os.getenv("APP_DATABASE_URL") or ""
        from services.auth_service import AuthService

        auth = AuthService(database_url)
        camera = CameraCommandService(database_url, auth_service=auth)
        camera.internal_speak(
            family_id=self.family_id,
            text=text,
            device_id=device_id,
            source="voice_worker",
        )

    def run_once(self) -> dict:
        device_id = self.resolve_device_id()
        self.sync_service.sync_family_conversation(family_id=self.family_id)
        profile = self.sync_service.load_profile_for_device(
            family_id=self.family_id,
            device_id=device_id,
        )
        phrase = self.mock_phrases[0]
        wake_match = match_wake_names(
            phrase,
            profile.get("wakeName") or "",
            profile.get("fallbackWakeName") or "小暖",
            require_confirmation=self.require_confirmation,
        )
        if not wake_match.get("matched"):
            self._heartbeat(device_id=device_id, profile=profile, state="listening", wake_match=wake_match)
            return {"ok": True, "stage": "listening", "wakeMatch": wake_match}

        self._heartbeat(device_id=device_id, profile=profile, state="wake_detected", wake_match=wake_match)
        ack = wake_ack_text(str(profile.get("wakeName") or "小暖"))
        self._speak(device_id=device_id, text=ack)

        command_phrase = phrase
        if len(self.mock_phrases) > 1:
            command_phrase = self.mock_phrases[1]
        with self.database.transaction() as conn:
            active = self.policy_service.conversation_repository.active_session(
                conn,
                family_id=self.family_id,
                session_type="free_chat",
            )
            if active is None:
                self.policy_service.start_free_chat_session(
                    conn,
                    family_id=self.family_id,
                    device_id=device_id,
                    session_id=f"cs_{uuid.uuid4().hex}",
                )
            result = self.conversation_service.reply(
                conn,
                family_id=self.family_id,
                device_id=device_id,
                text=command_phrase,
                profile=profile,
            )
            if not result.get("allowed"):
                self.policy_service.end_active_free_chat_session(conn, family_id=self.family_id)

        reply = str(result.get("reply") or "")
        if reply:
            self._speak(device_id=device_id, text=reply)
        self._heartbeat(
            device_id=device_id,
            profile=profile,
            state="speaking" if reply else "listening",
            wake_match=wake_match,
            command=command_phrase,
            reply=reply,
        )
        return {"ok": True, "stage": "reply", "wakeMatch": wake_match, "result": result}

    def run_forever(self) -> None:
        while RUNNING:
            try:
                outcome = self.run_once()
                log.info("voice worker tick: %s", outcome.get("stage"))
            except Exception as exc:  # pragma: no cover
                log.exception("voice worker tick failed: %s", exc)
            deadline = time.monotonic() + self.poll_seconds
            while RUNNING and time.monotonic() < deadline:
                time.sleep(min(0.2, max(0.0, deadline - time.monotonic())))


def build_worker_from_env(environ: dict[str, str] | None = None) -> CameraVoiceWorker:
    env = environ or os.environ
    database_url = str(env.get("DATABASE_URL") or env.get("APP_DATABASE_URL") or "").strip()
    family_id = str(env.get("VOICE_WORKER_FAMILY_ID") or "").strip()
    device_id = str(env.get("VOICE_WORKER_DEVICE_ID") or "").strip() or None
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for camera voice worker")
    if not family_id:
        raise RuntimeError("VOICE_WORKER_FAMILY_ID is required for camera voice worker")
    phrases = [item.strip() for item in str(env.get("VOICE_MOCK_PHRASES") or "小暖小暖|小暖你好，讲个故事").split("|") if item.strip()]
    require_confirmation = str(env.get("WAKE_REQUIRE_CONFIRMED_PHRASE", "1")).strip().lower() in {"1", "true", "yes", "on"}
    poll_seconds = float(env.get("VOICE_WORKER_POLL_SECONDS", "5"))
    return CameraVoiceWorker(
        database_url=database_url,
        family_id=family_id,
        device_id=device_id,
        mock_phrases=phrases,
        require_confirmation=require_confirmation,
        poll_seconds=poll_seconds,
    )


def _load_worker_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.is_file():
        load_dotenv(env_path)


def _shutdown(_signum=None, _frame=None):
    global RUNNING
    RUNNING = False


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    _load_worker_env()
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    worker = build_worker_from_env()
    if str(os.getenv("VOICE_WORKER_RUN_ONCE") or "").strip().lower() in {"1", "true", "yes", "on"}:
        log.info("voice worker run-once: %s", worker.run_once())
        return 0
    worker.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
