from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urlparse

from core.errors import AuthError
from services.auth_service import AuthService
from websockets.exceptions import ConnectionClosed
from websockets.sync.server import ServerConnection, serve


TASK_STREAM_UPDATE = "task.updated"
TASK_STREAM_CONNECTED = "task.connected"


@dataclass
class TaskEventStreamState:
    enabled: bool = False
    running: bool = False
    host: str = ""
    port: int = 0
    path: str = ""
    connection_count: int = 0
    started_at: int | None = None
    last_error: str = ""
    last_broadcast_at: int | None = None
    last_broadcast_task_ids: list[str] = field(default_factory=list)


class TaskEventStreamServer:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._connections: dict[str, set[ServerConnection]] = {}
        self._server = None
        self._auth_service: AuthService | None = None
        self._path = "/api/tasks/stream"
        self._state = TaskEventStreamState()

    def start(self, app) -> None:
        if not app.config.get("TASK_WEBSOCKET_ENABLED"):
            with self._lock:
                self._state.enabled = False
                self._state.running = False
            return
        if app.config.get("TESTING"):
            return
        if app.config.get("DEBUG") and os.environ.get("WERKZEUG_RUN_MAIN") == "false":
            return
        if self._thread and self._thread.is_alive():
            return

        host = str(app.config.get("TASK_WEBSOCKET_HOST") or app.config.get("HOST") or "127.0.0.1")
        port = int(app.config.get("TASK_WEBSOCKET_PORT") or 8001)
        path = str(app.config.get("TASK_WEBSOCKET_PATH") or "/api/tasks/stream")
        self._path = path
        self._auth_service = AuthService(
            app.config["DATABASE_URL"],
            access_token_seconds=int(app.config.get("AUTH_ACCESS_TOKEN_SECONDS", 900)),
            refresh_token_seconds=int(app.config.get("AUTH_REFRESH_TOKEN_SECONDS", 60 * 60 * 24 * 30)),
        )

        with self._lock:
            self._state = TaskEventStreamState(
                enabled=True,
                running=False,
                host=host,
                port=port,
                path=path,
            )

        self._thread = threading.Thread(
            target=self._run,
            args=(host, port),
            name="task-websocket",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        server = self._server
        if server is not None:
            server.shutdown()

    def status(self) -> dict:
        with self._lock:
            return {
                "enabled": self._state.enabled,
                "running": self._state.running,
                "host": self._state.host,
                "port": self._state.port,
                "path": self._state.path,
                "connectionCount": self._state.connection_count,
                "startedAt": self._state.started_at,
                "lastError": self._state.last_error,
                "lastBroadcastAt": self._state.last_broadcast_at,
                "lastBroadcastTaskIds": self._state.last_broadcast_task_ids,
            }

    def broadcast(self, family_id: str, payload: dict[str, Any]) -> None:
        if not family_id:
            return
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            targets = list(self._connections.get(family_id, set()))
        if not targets:
            return

        failed: list[ServerConnection] = []
        for connection in targets:
            try:
                connection.send(text)
            except Exception:
                failed.append(connection)

        if failed:
            with self._lock:
                active = self._connections.get(family_id)
                if active is not None:
                    for connection in failed:
                        active.discard(connection)
                    if not active:
                        self._connections.pop(family_id, None)
                self._state.connection_count = sum(len(items) for items in self._connections.values())

        with self._lock:
            self._state.last_broadcast_at = _now_ms()
            self._state.last_broadcast_task_ids = list(payload.get("taskIds") or [])

    def _run(self, host: str, port: int) -> None:
        try:
            with serve(self._handle, host, port, ping_interval=25, ping_timeout=20) as server:
                self._server = server
                with self._lock:
                    self._state.running = True
                    self._state.started_at = _now_ms()
                    self._state.last_error = ""
                server.serve_forever()
        except Exception as exc:  # pragma: no cover - exercised by local runtime.
            with self._lock:
                self._state.running = False
                self._state.last_error = str(exc)
        finally:
            with self._lock:
                self._state.running = False

    def _handle(self, connection: ServerConnection) -> None:
        family_id = ""
        try:
            family_id = self._authenticate_connection(connection)
            self._register(family_id, connection)
            connection.send(
                json.dumps(
                    {
                        "type": TASK_STREAM_CONNECTED,
                        "familyId": family_id,
                        "sentAt": _now_ms(),
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
            while True:
                message = connection.recv()
                if message == "ping":
                    connection.send(
                        json.dumps(
                            {"type": "pong", "sentAt": _now_ms()},
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    )
        except (AuthError, ValueError):
            try:
                connection.close(code=1008, reason="not allowed")
            except Exception:
                pass
        except ConnectionClosed:
            pass
        finally:
            if family_id:
                self._unregister(family_id, connection)

    def _authenticate_connection(self, connection: ServerConnection) -> str:
        request = getattr(connection, "request", None)
        request_path = getattr(request, "path", "") if request is not None else ""
        parsed = urlparse(request_path)
        if parsed.path != self._path:
            raise ValueError("unexpected websocket path")
        token = (parse_qs(parsed.query).get("token") or [""])[0]
        if self._auth_service is None:
            raise ValueError("task websocket auth is not configured")
        context = self._auth_service.authenticate(token)
        return str(context["family"]["id"])

    def _register(self, family_id: str, connection: ServerConnection) -> None:
        with self._lock:
            self._connections.setdefault(family_id, set()).add(connection)
            self._state.connection_count = sum(len(items) for items in self._connections.values())

    def _unregister(self, family_id: str, connection: ServerConnection) -> None:
        with self._lock:
            active = self._connections.get(family_id)
            if active is not None:
                active.discard(connection)
                if not active:
                    self._connections.pop(family_id, None)
            self._state.connection_count = sum(len(items) for items in self._connections.values())


task_event_stream_server = TaskEventStreamServer()


def start_task_event_stream(app) -> None:
    task_event_stream_server.start(app)


def task_event_stream_status() -> dict:
    return task_event_stream_server.status()


def publish_task_update(
    *,
    family_id: str,
    tasks: list[dict] | None = None,
    events: list[dict] | None = None,
    source: str = "task",
) -> None:
    payload = task_update_message(
        tasks=tasks or [],
        events=events or [],
        source=source,
    )
    if payload["taskIds"]:
        task_event_stream_server.broadcast(family_id, payload)


def publish_task_runtime_result(result: dict[str, Any]) -> None:
    for family_id, payload in task_runtime_messages_by_family(result).items():
        task_event_stream_server.broadcast(family_id, payload)


def task_runtime_messages_by_family(result: dict[str, Any]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, dict[str, list[dict]]] = {}
    for task in result.get("changedTasks") or []:
        family_id = str(task.get("familyId") or "")
        if not family_id:
            continue
        grouped.setdefault(family_id, {"tasks": [], "events": []})["tasks"].append(task)
    for event in result.get("events") or []:
        family_id = str(event.get("familyId") or "")
        if not family_id:
            continue
        grouped.setdefault(family_id, {"tasks": [], "events": []})["events"].append(event)
    return {
        family_id: task_update_message(
            tasks=items["tasks"],
            events=items["events"],
            source="scheduler",
            checked_at=result.get("checkedAt"),
        )
        for family_id, items in grouped.items()
    }


def task_update_message(
    *,
    tasks: list[dict],
    events: list[dict],
    source: str,
    checked_at: int | None = None,
) -> dict[str, Any]:
    task_ids = {
        str(task.get("taskId") or task.get("id"))
        for task in tasks
        if task.get("taskId") or task.get("id")
    }
    task_ids.update(
        str(event.get("taskId"))
        for event in events
        if event.get("taskId")
    )
    return {
        "type": TASK_STREAM_UPDATE,
        "source": source,
        "taskIds": sorted(task_ids),
        "tasks": tasks,
        "events": events,
        "checkedAt": checked_at,
        "sentAt": _now_ms(),
    }


def _now_ms() -> int:
    return int(time.time() * 1000)
