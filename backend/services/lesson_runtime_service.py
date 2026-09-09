from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Mapping

from core.database import Database
from core.errors import ApiError
from core.security import now_ms
from repositories.lesson_package_repository import LessonPackageRepository
from repositories.openmaic_runtime_repository import OpenMaicRuntimeRepository


_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_RESULT_KEYS = frozenset(
    {
        "completed",
        "played",
        "viewed",
        "continued",
        "watchRatio",
        "durationMs",
    }
)


class LessonRuntimeService:
    """Run one immutable, public lesson package for an isolated student session."""

    def __init__(self, database_url: str | Path):
        database = Database(database_url)
        self.repository = LessonPackageRepository(database)
        self.formal_runtime_repository = OpenMaicRuntimeRepository(database)

    def attach_classroom(
        self,
        *,
        family_id: str,
        child_id: str,
        start_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        with self.repository.transaction() as conn:
            return self.attach_classroom_in_transaction(
                conn,
                family_id=family_id,
                child_id=child_id,
                start_payload=start_payload,
            )

    def attach_classroom_in_transaction(
        self,
        conn,
        *,
        family_id: str,
        child_id: str,
        start_payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Bind the package and formal release before session commit."""

        payload = dict(start_payload)
        public_session = payload.get("session")
        if not isinstance(public_session, Mapping):
            return payload
        session_id = str(public_session.get("id") or "")
        if not session_id:
            return payload

        session = self.repository.get_session(
            conn,
            family_id=family_id,
            child_id=child_id,
            session_id=session_id,
            for_update=True,
        )
        if session is None:
            raise ApiError("learning_session_not_found", "学习记录不存在", 404)
        formal_package_selected = False
        if not session.get("lesson_package_id"):
            package = self.repository.get_active_formal_package(
                conn,
                course_id=str(session["course_id"]),
                course_version=str(session["course_version"]),
                family_id=family_id,
                child_id=child_id,
            )
            formal_package_selected = package is not None
            if package is None:
                # A grade controlled by a formal pointer must never fall
                # back to a legacy package.  Otherwise the student could
                # open an unpinned classroom which fails only at launch.
                if self.repository.has_formal_grade_pointer_for_course(
                    conn,
                    course_id=str(session["course_id"]),
                    course_version=str(session["course_version"]),
                ):
                    raise ApiError(
                        "learning_classroom_release_changed",
                        "正式课程刚刚更新，请重新打开这节课",
                        409,
                    )
                # Legacy package resolution remains only for installations
                # where this grade has never entered formal publication.
                package = self.repository.get_active_package(
                    conn,
                    course_id=str(session["course_id"]),
                    course_version=str(session["course_version"]),
                )
            if package is None:
                return payload
            session = self.repository.bind_session_package(
                conn,
                session=session,
                package=package,
                now=now_ms(),
            )
        formal_binding = (
            self.formal_runtime_repository.bind_formal_session_to_active_release(
                conn,
                family_id=family_id,
                child_id=child_id,
                learning_session_id=session_id,
                now=now_ms(),
            )
        )
        if formal_package_selected and formal_binding is None:
            # A grade publication raced package selection.  The caller owns
            # this transaction, so raising also removes a newly made session.
            raise ApiError(
                "learning_classroom_release_changed",
                "正式课程刚刚更新，请重新打开这节课",
                409,
            )
        if formal_binding is not None:
            # A formal OpenMAIC candidate package is an immutable launch
            # authority, not a legacy ``lesson-package.v2`` player payload.
            # Returning it as ``classroom/package/cursor`` makes Student Web
            # validate the candidate envelope as the legacy scene contract
            # and prevents the subsequent OpenMAIC launch request entirely.
            return payload
        package, classroom = self._package_for_session(conn, session)
        runtime = self._runtime_payload(
            session=session,
            package=package,
            classroom=classroom,
        )

        payload["classroom"] = classroom
        payload["package"] = runtime["classroom"]
        payload["cursor"] = runtime["cursor"]
        return payload

    def has_formal_runtime_binding_in_transaction(
        self,
        conn,
        *,
        family_id: str,
        child_id: str,
        learning_session_id: str,
    ) -> bool:
        if not learning_session_id:
            return False
        return (
            self.formal_runtime_repository.get_formal_session_binding_for_update(
                conn,
                family_id=family_id,
                child_id=child_id,
                learning_session_id=learning_session_id,
            )
            is not None
        )

    def runtime(
        self,
        *,
        family_id: str,
        child_id: str,
        session_id: str,
    ) -> dict[str, Any]:
        with self.repository.transaction() as conn:
            session = self.repository.get_session(
                conn,
                family_id=family_id,
                child_id=child_id,
                session_id=session_id,
            )
            if session is None:
                raise ApiError("learning_session_not_found", "学习记录不存在", 404)
            if not session.get("lesson_package_id"):
                raise ApiError(
                    "learning_classroom_not_available",
                    "本次学习暂时没有互动课堂",
                    404,
                )
            package, classroom = self._package_for_session(conn, session)
            return self._runtime_payload(
                session=session,
                package=package,
                classroom=classroom,
            )

    def complete_action(
        self,
        *,
        family_id: str,
        child_id: str,
        session_id: str,
        action_id: str,
        data: Mapping[str, Any],
    ) -> dict[str, Any]:
        revision = data.get("cursorRevision")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise ApiError(
                "invalid_cursor_revision",
                "cursorRevision 必须是非负整数",
            )
        idempotency_key = str(data.get("idempotencyKey") or "").strip()
        if not _IDEMPOTENCY_KEY.fullmatch(idempotency_key):
            raise ApiError(
                "invalid_idempotency_key",
                "idempotencyKey 格式无效",
            )
        result = self._result(data.get("result"))
        request_record = {
            "cursorRevision": revision,
            "result": result,
        }

        with self.repository.transaction() as conn:
            session = self.repository.get_session(
                conn,
                family_id=family_id,
                child_id=child_id,
                session_id=session_id,
                for_update=True,
            )
            if session is None:
                raise ApiError("learning_session_not_found", "学习记录不存在", 404)
            prior = self.repository.get_runtime_record_by_idempotency(
                conn,
                session_id=session_id,
                idempotency_key=idempotency_key,
            )
            if prior is not None:
                prior_payload = self.repository.decode_json(prior.get("payload_json"))
                if str(prior.get("action_id") or "") != action_id or prior_payload != request_record:
                    raise ApiError(
                        "learning_idempotency_conflict",
                        "idempotencyKey 已用于另一项课堂操作",
                        409,
                    )
                response = self.repository.decode_json(prior.get("response_json"))
                if response is None:
                    raise ApiError(
                        "learning_runtime_record_invalid",
                        "课堂操作记录不可用",
                        503,
                    )
                return response
            if not session.get("lesson_package_id"):
                raise ApiError(
                    "learning_classroom_not_available",
                    "本次学习暂时没有互动课堂",
                    404,
                )
            package, classroom = self._package_for_session(conn, session)
            runtime = self._runtime_payload(
                session=session,
                package=package,
                classroom=classroom,
            )
            if runtime["completed"]:
                raise ApiError(
                    "learning_classroom_completed",
                    "本次互动课堂已经完成",
                    409,
                )
            if int(session.get("cursor_revision") or 0) != revision:
                raise ApiError(
                    "learning_cursor_conflict",
                    "课堂进度已更新，请刷新后继续",
                    409,
                )
            scene = runtime["scene"]
            action = runtime["action"]
            if not isinstance(scene, Mapping) or not isinstance(action, Mapping):
                raise ApiError("learning_runtime_invalid", "课堂进度异常", 409)
            if str(action.get("id") or "") != action_id:
                raise ApiError(
                    "learning_action_conflict",
                    "当前课堂操作已变化，请刷新后继续",
                    409,
                )
            self._validate_result(scene=scene, action=action, result=result, session=session)

            scene_index = int(session.get("current_scene_index") or 0)
            action_index = int(session.get("current_action_index") or 0)
            actions = scene.get("actions") if isinstance(scene.get("actions"), list) else []
            if action_index + 1 < len(actions):
                next_scene_index = scene_index
                next_action_index = action_index + 1
            else:
                next_scene_index = scene_index + 1
                next_action_index = 0
            scenes = classroom.get("scenes") if isinstance(classroom.get("scenes"), list) else []
            completed_at = now_ms() if next_scene_index >= len(scenes) else None
            next_revision = revision + 1
            self.repository.update_session_cursor(
                conn,
                session_id=session_id,
                scene_index=next_scene_index,
                action_index=next_action_index,
                cursor_revision=next_revision,
                classroom_completed_at=completed_at,
                now=now_ms(),
            )
            updated = self.repository.get_session(
                conn,
                family_id=family_id,
                child_id=child_id,
                session_id=session_id,
                for_update=True,
            )
            response = self._runtime_payload(
                session=updated,
                package=package,
                classroom=classroom,
            )
            self.repository.append_runtime_record(
                conn,
                session_id=session_id,
                idempotency_key=idempotency_key,
                scene_id=str(scene["id"]),
                action_id=action_id,
                record_type="action_completed",
                payload=request_record,
                response=response,
                now=now_ms(),
            )
            return response

    def _package_for_session(self, conn, session):
        package = self.repository.get_package(
            conn,
            package_id=str(session.get("lesson_package_id") or ""),
            package_version=int(session.get("lesson_package_version") or 0),
        )
        if package is None or str(package.get("public_content_hash") or "") != str(
            session.get("lesson_package_content_hash") or ""
        ):
            raise ApiError(
                "learning_classroom_version_unavailable",
                "本次课堂版本不可用",
                409,
            )
        classroom = self.repository.decode_json(package.get("public_payload_json"))
        if classroom is None:
            raise ApiError("learning_classroom_invalid", "互动课堂内容不可用", 503)
        return package, classroom

    @staticmethod
    def _runtime_payload(
        *,
        session: Mapping[str, Any],
        package: Mapping[str, Any],
        classroom: Mapping[str, Any],
    ) -> dict[str, Any]:
        scenes = classroom.get("scenes") if isinstance(classroom.get("scenes"), list) else []
        scene_index = max(int(session.get("current_scene_index") or 0), 0)
        action_index = max(int(session.get("current_action_index") or 0), 0)
        completed = bool(session.get("classroom_completed_at")) or scene_index >= len(scenes)
        if completed and scenes:
            display_scene_index = len(scenes) - 1
            scene = scenes[display_scene_index]
        else:
            display_scene_index = scene_index
            scene = None if completed else scenes[scene_index]
        actions = (
            scene.get("actions")
            if isinstance(scene, Mapping) and isinstance(scene.get("actions"), list)
            else []
        )
        if completed:
            display_action_index = len(actions)
        else:
            display_action_index = action_index
        if not completed and action_index >= len(actions):
            raise ApiError("learning_runtime_invalid", "课堂进度异常", 409)
        action = None if completed else actions[action_index]
        if completed:
            progress = 1.0
        elif scenes:
            action_progress = action_index / max(len(actions), 1)
            progress = round((scene_index + action_progress) / len(scenes), 4)
        else:
            progress = 0.0
        return {
            "ok": True,
            "sessionId": str(session["id"]),
            "classroom": {
                "id": str(package["id"]),
                "version": int(package["version"]),
                "contentHash": str(package["public_content_hash"]),
            },
            "scene": scene,
            "action": action,
            "cursor": {
                "revision": int(session.get("cursor_revision") or 0),
                "sceneId": str(scene.get("id") or "") if isinstance(scene, Mapping) else None,
                "actionId": str(action.get("id") or "") if isinstance(action, Mapping) else None,
                "sceneIndex": display_scene_index,
                "actionIndex": display_action_index,
                "sceneCount": len(scenes),
                "progress": progress,
            },
            "completed": completed,
        }

    @staticmethod
    def _result(value: object) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, Mapping):
            raise ApiError("invalid_classroom_action_result", "result 必须是对象")
        extras = set(value) - _RESULT_KEYS
        if extras:
            raise ApiError("invalid_classroom_action_result", "result 包含不支持的字段")
        result = dict(value)
        for key in ("completed", "played", "viewed", "continued"):
            if key in result and not isinstance(result[key], bool):
                raise ApiError("invalid_classroom_action_result", f"result.{key} 必须是布尔值")
        if "watchRatio" in result:
            ratio = result["watchRatio"]
            if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not 0 <= ratio <= 1:
                raise ApiError("invalid_classroom_action_result", "result.watchRatio 必须在 0 到 1 之间")
            result["watchRatio"] = float(ratio)
        if "durationMs" in result:
            duration = result["durationMs"]
            if isinstance(duration, bool) or not isinstance(duration, int) or not 0 <= duration <= 86_400_000:
                raise ApiError("invalid_classroom_action_result", "result.durationMs 无效")
        if len(json.dumps(result, ensure_ascii=False)) > 1024:
            raise ApiError("invalid_classroom_action_result", "result 过大")
        return result

    @staticmethod
    def _validate_result(
        *,
        scene: Mapping[str, Any],
        action: Mapping[str, Any],
        result: Mapping[str, Any],
        session: Mapping[str, Any],
    ) -> None:
        action_type = str(action.get("type") or "")
        if action_type == "play_media" and scene.get("type") == "video":
            minimum = float(scene.get("minWatchRatio") or 0)
            if float(result.get("watchRatio") or 0) < minimum:
                raise ApiError(
                    "learning_media_not_completed",
                    "视频观看进度不足，暂时不能继续",
                    409,
                )
        if (
            action_type == "await_interaction"
            and scene.get("type") == "interactive"
            and scene.get("phaseRole") == "guided"
        ):
            refs = scene.get("questionRefs")
            if not isinstance(refs, list) or not refs:
                raise ApiError(
                    "learning_runtime_invalid",
                    "引导练习配置不可用",
                    409,
                )
            if result.get("completed") is not True:
                raise ApiError(
                    "learning_guided_not_completed",
                    "请先完成引导练习中的作答和反馈",
                    409,
                )
            if int(session.get("current_question_index") or 0) < len(refs):
                raise ApiError(
                    "learning_guided_not_completed",
                    "请先完成两道引导练习，不能只点击继续",
                    409,
                )
        if action_type == "await_interaction" and scene.get("type") == "quiz":
            if str(session.get("status") or "") != "completed":
                raise ApiError(
                    "learning_quiz_not_completed",
                    "请先完成本课练习题",
                    409,
                )
